from pathlib import Path

from typer.testing import CliRunner

from struct2bim.cli import app


runner = CliRunner()


def test_infer_reports_missing_weights_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    source.write_bytes(b"placeholder")

    result = runner.invoke(
        app,
        ["infer", "--source", str(source), "--weights", str(tmp_path / "missing.pt")],
    )

    assert result.exit_code == 2
    assert "MODEL_WEIGHTS_REQUIRED" in result.output
    assert "Traceback" not in result.output


def test_evaluate_reports_missing_weights_without_traceback(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    data = dataset / "dataset.yaml"
    data.write_text("names: {}\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--weights",
            str(tmp_path / "missing.pt"),
            "--dataset",
            str(dataset),
            "--data",
            str(data),
        ],
    )

    assert result.exit_code == 2
    assert "MODEL_WEIGHTS_REQUIRED" in result.output
    assert "Traceback" not in result.output
