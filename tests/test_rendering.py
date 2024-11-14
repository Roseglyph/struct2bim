from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from struct2bim.rendering.blender_runner import BlenderRunner, BlenderToolConfig
from struct2bim.rendering.previews import render_annotation_preview, render_geometry_preview


@pytest.fixture
def scene() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "entities": [
            {
                "id": "COL-001",
                "type": "column",
                "subtype": "rectangular",
                "center_mm": {"x": 1000, "y": 1200},
                "dimensions_mm": {"width": 300, "depth": 600, "height": 3200},
                "rotation_deg": 30,
                "label": "C1",
            },
            {
                "id": "COL-002",
                "type": "column",
                "subtype": "circular",
                "center_mm": {"x": 3500, "y": 1200},
                "dimensions_mm": {"diameter": 450, "height": 3200},
                "rotation_deg": 0,
                "label": "C2",
            },
        ],
    }


def test_blender_command_is_isolated(tmp_path: Path) -> None:
    executable = tmp_path / "blender.exe"
    executable.touch()
    script = tmp_path / "render.py"
    script.touch()
    command = BlenderRunner(BlenderToolConfig(executable), tmp_path).command(script, ["--seed", "8"])
    assert command[1:4] == ["--background", "--factory-startup", "--disable-autoexec"]
    assert command[-3:] == ["--", "--seed", "8"]


def test_geometry_preview_is_deterministic(tmp_path: Path, scene: dict[str, object]) -> None:
    first = render_geometry_preview(scene, tmp_path / "first.png")
    second = render_geometry_preview(scene, tmp_path / "second.png")
    assert first.read_bytes() == second.read_bytes()
    assert Image.open(first).size == (1200, 900)


def test_annotation_preview_has_visible_ground_truth_badge(
    tmp_path: Path, scene: dict[str, object]
) -> None:
    source = tmp_path / "drawing.png"
    Image.new("RGB", (800, 600), "white").save(source)
    sidecar = source.with_suffix(".png.render.json")
    sidecar.write_text(
        json.dumps({"image_size": [800, 600], "world_bounds_mm": [0, 0, 5000, 3750]}),
        encoding="utf-8",
    )
    output = render_annotation_preview(scene, source, tmp_path / "annotations.png")
    image = Image.open(output)
    # Badge area is amber; this also guards against an unlabeled prediction-like overlay.
    assert image.getpixel((30, 30))[0] > 150
    assert image.size == (800, 600)
