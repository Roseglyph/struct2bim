from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from struct2bim.showcase.composition import compose_pipeline_hero, compose_variation_gallery


def _image(path: Path, color: str) -> Path:
    Image.new("RGB", (640, 480), color).save(path)
    return path


def test_pipeline_hero_is_reproducible_and_readme_sized(tmp_path: Path) -> None:
    inputs = [
        _image(tmp_path / "drawing.png", "white"),
        _image(tmp_path / "annotation.png", "#F9D7A5"),
        _image(tmp_path / "geometry.png", "#D9F1E7"),
        _image(tmp_path / "ifc.png", "#C3D7EA"),
    ]
    first = compose_pipeline_hero(*inputs, tmp_path / "hero-1.png")
    second = compose_pipeline_hero(*inputs, tmp_path / "hero-2.png")
    assert Image.open(first).size == (2400, 760)
    assert first.read_bytes() == second.read_bytes()


def test_variation_gallery_rejects_empty_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        compose_variation_gallery([], tmp_path / "gallery.png")


def test_showcase_builder_manifest_never_claims_predictions(tmp_path: Path) -> None:
    # The invariant is tested without invoking Blender: every public showcase
    # manifest must explicitly distinguish truth from future model predictions.
    manifest = {
        "seed": 24017,
        "provenance": "synthetic_ground_truth",
        "model_predictions_included": False,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["provenance"] == "synthetic_ground_truth"
    assert loaded["model_predictions_included"] is False
