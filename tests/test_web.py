from pathlib import Path

from fastapi.testclient import TestClient

from struct2bim.web import create_app
from struct2bim.web.app import GeneratorParameters


def test_web_interface_and_defaults_are_available() -> None:
    root = Path(__file__).resolve().parents[1]
    client = TestClient(create_app(root))

    page = client.get("/")
    defaults = client.get("/api/defaults")

    assert page.status_code == 200
    assert "Dataset parameters" in page.text
    assert defaults.status_code == 200
    assert defaults.json()["scene_count"] == 12


def test_generator_parameters_reject_unsafe_output_name() -> None:
    try:
        GeneratorParameters(output_name="../outside")
    except ValueError as error:
        assert "output name" in str(error)
    else:
        raise AssertionError("unsafe output name was accepted")
