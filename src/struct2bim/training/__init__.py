"""Optional local model-training integration."""

from struct2bim.training.config import TrainingConfig
from struct2bim.training.evaluation import run_evaluation
from struct2bim.training.inference import run_inference
from struct2bim.training.runner import TrainingDependencyError, run_training

__all__ = [
    "TrainingConfig",
    "TrainingDependencyError",
    "run_evaluation",
    "run_inference",
    "run_training",
]
