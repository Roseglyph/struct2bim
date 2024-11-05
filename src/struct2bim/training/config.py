"""Validated local-training configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator


class TrainingConfig(BaseModel):
    """Configuration accepted by the optional Ultralytics runner."""

    task: Literal["segment", "obb"]
    model: str = Field(min_length=1)
    dataset: Path
    project: Path
    name: str = Field(min_length=1)
    epochs: int = Field(default=100, ge=1)
    image_size: int = Field(default=1024, ge=128)
    batch_size: int = Field(default=4, ge=1)
    workers: int = Field(default=2, ge=0)
    device: str = "auto"
    seed: int = 42
    save_period: int = Field(default=5, ge=1)
    resume_checkpoint: Path | None = None

    @model_validator(mode="after")
    def validate_task_model(self) -> "TrainingConfig":
        expected_marker = "-seg" if self.task == "segment" else "-obb"
        if expected_marker not in self.model and self.resume_checkpoint is None:
            raise ValueError(f"Model name must contain {expected_marker!r} for task {self.task!r}")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "TrainingConfig":
        """Load a configuration file without resolving machine-specific paths."""
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Training configuration must contain a YAML mapping")
        return cls.model_validate(payload)
