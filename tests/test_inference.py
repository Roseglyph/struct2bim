from pathlib import Path

import pytest

from struct2bim.training import run_evaluation, run_inference


def test_inference_requires_real_checkpoint_before_processing(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    source.write_bytes(b"not needed")

    with pytest.raises(FileNotFoundError, match="MODEL_WEIGHTS_REQUIRED"):
        run_inference(source, tmp_path / "missing.pt", tmp_path / "output")


def test_evaluation_requires_real_checkpoint(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="MODEL_WEIGHTS_REQUIRED"):
        run_evaluation(
            tmp_path / "missing.pt",
            tmp_path / "dataset",
            tmp_path / "dataset.yaml",
            tmp_path / "report.json",
        )
