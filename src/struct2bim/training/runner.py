"""Lazy Ultralytics runner used only when local training is requested."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from struct2bim.training.config import TrainingConfig


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
    return project / config.name
