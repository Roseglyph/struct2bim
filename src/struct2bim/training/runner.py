"""Lazy Ultralytics runner used only when local training is requested."""

from __future__ import annotations

import importlib.util
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from struct2bim.training.config import TrainingConfig
from struct2bim.validation import validate_dataset


class TrainingDependencyError(RuntimeError):
    """Raised when optional local-training packages are absent."""


def _require_ultralytics() -> Any:
    if importlib.util.find_spec("ultralytics") is None:
        raise TrainingDependencyError(
            "Local training dependencies are not installed. Follow docs/training.md and "
            "install requirements-training.txt in a separate environment."
        )
    from ultralytics import YOLO  # type: ignore[import-not-found]

    return YOLO


def run_training(config_path: Path, project_root: Path) -> Path:
    """Start or resume a local training run and return its expected run directory."""
    config = TrainingConfig.from_yaml(config_path)
    dataset = (project_root / config.dataset).resolve()
    project = (project_root / config.project).resolve()

    if not dataset.is_file():
        raise FileNotFoundError(f"Dataset configuration was not found: {dataset}")
    dataset_root = dataset.parent.parent
    validation = validate_dataset(dataset_root)
    if not validation.valid:
        raise ValueError(f"Dataset failed validation before training: {validation.errors}")

    YOLO = _require_ultralytics()
    model_source = config.resume_checkpoint or Path(config.model)
    if config.resume_checkpoint is not None:
        model_source = (project_root / config.resume_checkpoint).resolve()
        if not model_source.is_file():
            raise FileNotFoundError(f"Resume checkpoint was not found: {model_source}")

    model = YOLO(str(model_source))
    device = None if config.device == "auto" else config.device
    model.train(
        data=str(dataset),
        project=str(project),
        name=config.name,
        task=config.task,
        epochs=config.epochs,
        imgsz=config.image_size,
        batch=config.batch_size,
        workers=config.workers,
        device=device,
        seed=config.seed,
        save_period=config.save_period,
        resume=config.resume_checkpoint is not None,
    )
    run_directory = project / config.name
    run_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_root / "manifest.json"
    run_manifest = {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "task": config.task,
        "model_source": str(model_source),
        "dataset_yaml": str(dataset),
        "dataset_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "training_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "resume": config.resume_checkpoint is not None,
    }
    (run_directory / "struct2bim_run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2), encoding="utf-8", newline="\n"
    )
    return run_directory
