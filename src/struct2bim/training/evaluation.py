"""Checkpoint-linked local evaluation with machine-readable provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from struct2bim.training.runner import _require_ultralytics
from struct2bim.validation import validate_dataset


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_evaluation(
    weights: Path,
    dataset_root: Path,
    dataset_yaml: Path,
    output: Path,
    *,
    split: str = "test",
) -> Path:
    """Validate a dataset, evaluate supplied weights and record actual returned metrics."""
    if not weights.is_file():
        raise FileNotFoundError(f"MODEL_WEIGHTS_REQUIRED: checkpoint not found: {weights}")
    if not dataset_yaml.is_file():
        raise FileNotFoundError(f"dataset YAML not found: {dataset_yaml}")
    validation = validate_dataset(dataset_root)
    if not validation.valid:
        raise ValueError(f"dataset failed validation: {validation.errors}")
    YOLO = _require_ultralytics()
    model = YOLO(str(weights))
    result: Any = model.val(data=str(dataset_yaml), split=split)
    metrics = cast(dict[str, float], getattr(result, "results_dict", {}))
    manifest = dataset_root / "manifest.json"
    payload = {
        "schema_version": "1.0",
        "checkpoint": weights.name,
        "checkpoint_sha256": _file_sha256(weights),
        "dataset_manifest_sha256": _file_sha256(manifest),
        "dataset_yaml": dataset_yaml.name,
        "split": split,
        "metrics": metrics,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    return output
