"""Optional local model-training integration."""

from struct2bim.training.config import TrainingConfig
from struct2bim.training.runner import TrainingDependencyError, run_training

__all__ = ["TrainingConfig", "TrainingDependencyError", "run_training"]

