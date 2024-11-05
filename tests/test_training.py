from pathlib import Path

import pytest
from pydantic import ValidationError

from struct2bim.training import TrainingConfig, TrainingDependencyError, run_training


def test_training_config_loads() -> None:
    config = TrainingConfig.from_yaml(Path("configs/training/columns-seg.yaml"))
    assert config.task == "segment"
    assert config.image_size == 1024
    assert config.resume_checkpoint is None


def test_training_config_rejects_wrong_model_family() -> None:
    with pytest.raises(ValidationError):
        TrainingConfig(
            task="segment",
            model="yolo11n-obb.pt",
            dataset=Path("dataset.yaml"),
            project=Path("runs"),
            name="bad",
        )


def test_training_without_dataset_fails_before_optional_import(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_training(Path("configs/training/columns-seg.yaml"), tmp_path)


def test_training_dependency_error_message() -> None:
    assert "not installed" in str(TrainingDependencyError("not installed"))

