"""Build reproducible YOLO-ready datasets from clean Blender renders."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

import cv2
import numpy as np
import numpy.typing as npt
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from struct2bim.annotations import (
    AnnotationSet,
    annotations_from_scene,
    export_yolo_obb,
    export_yolo_segmentation,
    write_yolo_labels,
)
from struct2bim.augmentation import (
    AugmentationProfile,
    augment_document,
    transform_annotation_set,
)
from struct2bim.curriculum import (
    DatasetSplit,
    ReferenceSceneConfig,
    SampleRecord,
    assign_grouped_splits,
    build_manifest,
    generate_reference_scene,
)
from struct2bim.validation import validate_dataset
from struct2bim.exporters import export_dxf

UInt8Image = npt.NDArray[np.uint8]


class CleanDrawingRenderer(Protocol):
    def render_clean_drawing(
        self, scene_json: Path, output_png: Path, *, seed: int = 24017
    ) -> None: ...


class DatasetBuildConfig(BaseModel):
    """Configuration for a complete synthetic dataset build."""

    project_seed: int = 24017
    scene_seed_start: int = 1000
    scene_count: int = Field(default=12, ge=3)
    variants: tuple[AugmentationProfile, ...] = (
        AugmentationProfile.CLEAN,
        AugmentationProfile.SCAN,
        AugmentationProfile.PERSPECTIVE_PHOTO,
    )
    scene: ReferenceSceneConfig = ReferenceSceneConfig()
    layout_modes: tuple[Literal["isolated", "regular", "irregular"], ...] = Field(
        default=("isolated", "regular", "irregular"), min_length=1
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "DatasetBuildConfig":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Dataset configuration must contain a YAML mapping")
        return cls.model_validate(payload)


@dataclass(frozen=True)
class DatasetBuildResult:
    root: Path
    manifest: Path
    segmentation_yaml: Path
    obb_yaml: Path
    sample_count: int


@dataclass
class _Variant:
    scene_seed: int
    profile: AugmentationProfile


def _split_map(config: DatasetBuildConfig) -> dict[int, DatasetSplit]:
    variants = [
        _Variant(seed, profile)
        for seed in range(config.scene_seed_start, config.scene_seed_start + config.scene_count)
        for profile in config.variants
    ]
    assignments = assign_grouped_splits(variants, project_seed=config.project_seed)
    return {
        variant.scene_seed: split
        for split, grouped_variants in assignments.items()
        for variant in grouped_variants
    }


def _write_image(path: Path, image: UInt8Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to write generated image: {path}")


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _write_dataset_yaml(root: Path, task: str) -> Path:
    task_root = root / task
    payload = {
        "path": str(task_root.resolve()),
        "train": "images/train",
        "val": "images/validation",
        "test": "images/test",
        "names": {0: "column_rectangular", 1: "column_circular"},
    }
    path = task_root / "dataset.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8", newline="\n")
    return path


def _entity_counts(annotations: AnnotationSet) -> dict[str, int]:
    counts = Counter(record.class_name for record in annotations.records)
    return dict(sorted(counts.items()))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_masks(annotations: AnnotationSet, semantic_path: Path, instance_path: Path) -> None:
    semantic = np.zeros((annotations.height_px, annotations.width_px), dtype=np.uint8)
    instances = np.zeros((annotations.height_px, annotations.width_px), dtype=np.uint16)
    for index, record in enumerate(annotations.records, 1):
        polygon = np.asarray(
            [[round(point.x), round(point.y)] for point in record.polygon_px.points],
            dtype=np.int32,
        )
        cv2.fillPoly(semantic, [polygon], (record.class_id + 1,))
        cv2.fillPoly(instances, [polygon], (index,))
    semantic_path.parent.mkdir(parents=True, exist_ok=True)
    instance_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(semantic_path), semantic):
        raise RuntimeError(f"Failed to write semantic mask: {semantic_path}")
    if not cv2.imwrite(str(instance_path), instances):
        raise RuntimeError(f"Failed to write instance mask: {instance_path}")


def build_dataset(
    config: DatasetBuildConfig,
    output_root: Path,
    renderer: CleanDrawingRenderer,
) -> DatasetBuildResult:
    """Generate all configured scenes and package both supported YOLO tasks."""
    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    scene_directory = output_root / "scenes"
    split_by_seed = _split_map(config)
    sample_records: list[SampleRecord] = []

    for scene_index, scene_seed in enumerate(
        range(config.scene_seed_start, config.scene_seed_start + config.scene_count)
    ):
        layout_mode = config.layout_modes[scene_index % len(config.layout_modes)]
        scene_config = config.scene.model_copy(update={"layout_mode": layout_mode})
        scene = generate_reference_scene(scene_seed, scene_config)
        scene_path = scene_directory / f"scene_{scene_seed}.json"
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(scene.canonical_json(), encoding="utf-8", newline="\n")
        dxf_path = export_dxf(scene, scene_directory / f"scene_{scene_seed}.dxf")
        clean_path = staging / f"scene_{scene_seed}_clean.png"
        renderer.render_clean_drawing(scene_path, clean_path, seed=scene_seed)
        loaded = cv2.imread(str(clean_path), cv2.IMREAD_COLOR)
        if loaded is None:
            raise RuntimeError(f"Blender did not create a readable drawing: {clean_path}")
        clean_image = cast(UInt8Image, loaded)
        annotations = annotations_from_scene(scene)
        split = split_by_seed[scene_seed]

        for profile in config.variants:
            sample_id = f"scene_{scene_seed}_{profile.value}"
            augmented = augment_document(clean_image, profile, seed=scene_seed + len(sample_id))
            transformed = transform_annotation_set(annotations, augmented.homography)
            common_image = output_root / "artifacts" / "images" / split.value / f"{sample_id}.png"
            _write_image(common_image, augmented.image)

            segmentation_image = output_root / "segment" / "images" / split.value / f"{sample_id}.png"
            obb_image = output_root / "obb" / "images" / split.value / f"{sample_id}.png"
            _link_or_copy(common_image, segmentation_image)
            _link_or_copy(common_image, obb_image)

            segmentation_label = (
                output_root / "segment" / "labels" / split.value / f"{sample_id}.txt"
            )
            obb_label = output_root / "obb" / "labels" / split.value / f"{sample_id}.txt"
            write_yolo_labels(segmentation_label, export_yolo_segmentation(transformed))
            write_yolo_labels(obb_label, export_yolo_obb(transformed))
            semantic_mask = output_root / "artifacts" / "semantic_masks" / split.value / f"{sample_id}.png"
            instance_mask = output_root / "artifacts" / "instance_masks" / split.value / f"{sample_id}.png"
            _write_masks(transformed, semantic_mask, instance_mask)
            metadata_path = output_root / "artifacts" / "metadata" / split.value / f"{sample_id}.json"
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "sample_id": sample_id,
                        "scene_seed": scene_seed,
                        "layout_mode": layout_mode,
                        "augmentation_profile": profile.value,
                        "split": split.value,
                        "provenance": "synthetic_ground_truth",
                        "homography": augmented.homography.tolist(),
                        "scene": scene_path.relative_to(output_root).as_posix(),
                        "dxf": dxf_path.relative_to(output_root).as_posix(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
                newline="\n",
            )
            sample_records.append(
                SampleRecord(
                    sample_id=sample_id,
                    scene_seed=scene_seed,
                    variant=profile.value,
                    image_path=common_image.relative_to(output_root).as_posix(),
                    segmentation_label_path=segmentation_label.relative_to(output_root).as_posix(),
                    obb_label_path=obb_label.relative_to(output_root).as_posix(),
                    entity_counts=_entity_counts(transformed),
                    semantic_mask_path=semantic_mask.relative_to(output_root).as_posix(),
                    instance_mask_path=instance_mask.relative_to(output_root).as_posix(),
                    metadata_path=metadata_path.relative_to(output_root).as_posix(),
                    scene_path=scene_path.relative_to(output_root).as_posix(),
                    dxf_path=dxf_path.relative_to(output_root).as_posix(),
                    artifact_sha256={
                        "image": _sha256(common_image),
                        "segmentation_label": _sha256(segmentation_label),
                        "obb_label": _sha256(obb_label),
                        "semantic_mask": _sha256(semantic_mask),
                        "instance_mask": _sha256(instance_mask),
                    },
                )
            )

    config_payload = config.model_dump_json(indent=2)
    manifest = build_manifest(
        sample_records,
        project_seed=config.project_seed,
        config_payload=config_payload,
    )
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8", newline="\n")
    shutil.rmtree(staging, ignore_errors=True)
    segmentation_yaml = _write_dataset_yaml(output_root, "segment")
    obb_yaml = _write_dataset_yaml(output_root, "obb")
    validation = validate_dataset(output_root)
    validation_path = output_root / "validation_report.json"
    validation_path.write_text(
        json.dumps(
            {
                **validation.model_dump(),
                "scene_count": config.scene_count,
                "manifest_sha256": manifest.sha256,
            },
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    if not validation.valid:
        raise RuntimeError(f"Generated dataset failed validation: {validation.errors}")
    return DatasetBuildResult(
        root=output_root,
        manifest=manifest_path,
        segmentation_yaml=segmentation_yaml,
        obb_yaml=obb_yaml,
        sample_count=len(sample_records),
    )
