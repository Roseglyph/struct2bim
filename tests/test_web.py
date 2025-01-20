from pathlib import Path

from fastapi.testclient import TestClient

from struct2bim.web import create_app
from struct2bim.web.app import GeneratorParameters, _build_preview


def test_web_interface_and_defaults_are_available() -> None:
    root = Path(__file__).resolve().parents[1]
    client = TestClient(create_app(root))

    page = client.get("/")
    defaults = client.get("/api/defaults")

    assert page.status_code == 200
    assert "Dataset generator" in page.text
    assert defaults.status_code == 200
    assert defaults.json()["scene_count"] == 12
    assert defaults.json()["foundation_type"] == "isolated_tie_beams"
    assert defaults.json()["design_code"] == "ACI 318-19"
    assert "Drafting and annotation" in page.text


def test_generator_parameters_reject_unsafe_output_name() -> None:
    try:
        GeneratorParameters(output_name="../outside")
    except ValueError as error:
        assert "output name" in str(error)
    else:
        raise AssertionError("unsafe output name was accepted")


def test_quick_preview_uses_dense_automatic_layout(tmp_path: Path) -> None:
    result = _build_preview(tmp_path, GeneratorParameters())

    assert result["layout"] == "automatic irregular"
    assert int(result["entities"]) > 1
    assert result["exchange_status"] == "validated during full generation"
    assert result["model"]["grids"]
    assert (tmp_path / "outputs" / "gui" / "previews" / "reference_dataset" / "drawing.png").is_file()
