"""Strict validation for generated YOLO datasets and their manifest."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path

from pydantic import BaseModel

from struct2bim.curriculum.manifest import DatasetManifest


class DatasetValidationReport(BaseModel):
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    sample_count: int
    split_counts: dict[str, int]
    checked_label_files: int


def _validate_label(path: Path, *, expected_values: int | None) -> list[str]:
    if not path.is_file():
        return [f"missing label: {path}"]
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        try:
            class_id = int(fields[0])
            values = [float(value) for value in fields[1:]]
        except ValueError:
            errors.append(f"{path}:{line_number}: label contains non-numeric values")
            continue
        if class_id not in {0, 1}:
            errors.append(f"{path}:{line_number}: unsupported class id {class_id}")
        if expected_values is not None and len(values) != expected_values:
            errors.append(f"{path}:{line_number}: expected {expected_values} coordinates")
        if expected_values is None and (len(values) < 6 or len(values) % 2):
            errors.append(f"{path}:{line_number}: segmentation polygon is malformed")
        if any(value < 0.0 or value > 1.0 for value in values):
            errors.append(f"{path}:{line_number}: coordinate outside [0, 1]")
    return errors


def validate_dataset(root: Path) -> DatasetValidationReport:
    """Validate file pairs, labels, non-empty splits and scene-level isolation."""
    root = root.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return DatasetValidationReport(
            valid=False,
            errors=(f"missing manifest: {manifest_path}",),
            warnings=(),
            sample_count=0,
            split_counts={},
            checked_label_files=0,
        )
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    split_counts: Counter[str] = Counter()
    seed_splits: dict[int, set[str]] = defaultdict(set)
    checked = 0
    for sample in manifest.samples:
        split = sample.split.value
        split_counts[split] += 1
        seed_splits[sample.scene_seed].add(split)
        if not (root / sample.image_path).is_file():
            errors.append(f"missing image: {root / sample.image_path}")
        for relative, expected_values in (
            (sample.segmentation_label_path, None),
            (sample.obb_label_path, 8),
        ):
            errors.extend(_validate_label(root / relative, expected_values=expected_values))
            checked += 1
        for optional_path in (
            sample.semantic_mask_path,
            sample.instance_mask_path,
            sample.metadata_path,
            sample.scene_path,
            sample.dxf_path,
        ):
            if optional_path is not None and not (root / optional_path).is_file():
                errors.append(f"missing declared artifact: {root / optional_path}")
        for artifact, expected_hash in sample.artifact_sha256.items():
            path_by_name = {
                "image": root / sample.image_path,
                "segmentation_label": root / sample.segmentation_label_path,
                "obb_label": root / sample.obb_label_path,
                "semantic_mask": root / sample.semantic_mask_path if sample.semantic_mask_path else None,
                "instance_mask": root / sample.instance_mask_path if sample.instance_mask_path else None,
            }
            artifact_path = path_by_name.get(artifact)
            if artifact_path is not None and artifact_path.is_file():
                actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    errors.append(f"checksum mismatch: {artifact_path}")
    for split in ("train", "validation", "test"):
        if split_counts[split] == 0:
            errors.append(f"split is empty: {split}")
    for seed, splits in seed_splits.items():
        if len(splits) > 1:
            errors.append(f"scene seed {seed} leaks across splits: {sorted(splits)}")
    reported_counts = {key: value for key, value in split_counts.items()}
    if manifest.sample_counts_by_split != reported_counts:
        errors.append("manifest split counts do not match its sample records")
    return DatasetValidationReport(
        valid=not errors,
        errors=tuple(errors),
        warnings=() if manifest.samples else ("dataset contains no samples",),
        sample_count=len(manifest.samples),
        split_counts=reported_counts,
        checked_label_files=checked,
    )
