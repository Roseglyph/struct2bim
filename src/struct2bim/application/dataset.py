"""Build reproducible YOLO-ready datasets from clean Blender renders."""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

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

    for scene_seed in range(config.scene_seed_start, config.scene_seed_start + config.scene_count):
        scene = generate_reference_scene(scene_seed, config.scene)
        scene_path = scene_directory / f"scene_{scene_seed}.json"
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(scene.canonical_json(), encoding="utf-8", newline="\n")
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
            sample_records.append(
                SampleRecord(
                    sample_id=sample_id,
                    scene_seed=scene_seed,
                    variant=profile.value,
                    image_path=common_image.relative_to(output_root).as_posix(),
                    segmentation_label_path=segmentation_label.relative_to(output_root).as_posix(),
                    obb_label_path=obb_label.relative_to(output_root).as_posix(),
                    entity_counts=_entity_counts(transformed),
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
