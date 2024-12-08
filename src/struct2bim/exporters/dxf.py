"""Create an interoperable DXF view from canonical structural geometry."""

from __future__ import annotations

from math import cos, radians, sin
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Mapping

os.environ.setdefault("XDG_CACHE_HOME", str(Path(__file__).resolve().parents[3] / ".cache"))

import ezdxf

from struct2bim.validation import require_valid_scene


@dataclass(frozen=True, slots=True)
class DxfValidationResult:
    is_valid: bool
    errors: tuple[str, ...]
    counts: dict[str, int]
    units: str


def _xy(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value["x"]), float(value["y"])
    return float(value[0]), float(value[1])


def _column_points(entity: Mapping[str, Any]) -> list[tuple[float, float]]:
    x, y = _xy(entity["center_mm"])
    width = entity["dimensions_mm"]["width"]
    depth = entity["dimensions_mm"]["depth"]
    angle = radians(float(entity.get("rotation_deg", 0)))
    return [
        (x + local_x * cos(angle) - local_y * sin(angle),
         y + local_x * sin(angle) + local_y * cos(angle))
        for local_x, local_y in (
            (-width / 2, -depth / 2), (width / 2, -depth / 2),
            (width / 2, depth / 2), (-width / 2, depth / 2)
        )
    ]


def export_dxf(scene: Any, destination: str | Path) -> Path:
    """Export columns and grid axes as a millimetre-based ASCII DXF."""
    data = require_valid_scene(scene)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = ezdxf.new("R2013", setup=True)  # type: ignore[attr-defined]
    document.units = ezdxf.units.MM
    for name, color in (("S2B_COLUMNS", 1), ("S2B_GRIDS", 8), ("S2B_LABELS", 7)):
        if name not in document.layers:
            document.layers.add(name, color=color)
    modelspace = document.modelspace()
    entities = list(data["entities"])
    entities.extend(dict(axis, type="grid_axis") for axis in data.get("grids", []))
    for entity in entities:
        entity_type = entity["type"]
        if entity_type == "column":
            dimensions = entity["dimensions_mm"]
            if entity.get("subtype") == "circular":
                modelspace.add_circle(_xy(entity["center_mm"]), float(dimensions["diameter"]) / 2,
                                      dxfattribs={"layer": "S2B_COLUMNS"})
            else:
                points = _column_points(entity)
                modelspace.add_lwpolyline(points, close=True, dxfattribs={"layer": "S2B_COLUMNS"})
            label = entity.get("label", entity.get("classification", {}).get("label", entity["id"]))
            modelspace.add_text(str(label), height=125, dxfattribs={"layer": "S2B_LABELS"}).set_placement(_xy(entity["center_mm"]))
        elif entity_type == "grid_axis":
            modelspace.add_line(_xy(entity["start_mm"]), _xy(entity["end_mm"]), dxfattribs={"layer": "S2B_GRIDS"})
    document.header["$PROJECTNAME"] = str(data.get("project", {}).get("name", "Struct2BIM"))
    document.saveas(path)
    result = validate_dxf_file(path, expected_scene=data)
    if not result.is_valid:
        path.unlink(missing_ok=True)
        raise ValueError("Exported DXF failed reopen validation: " + "; ".join(result.errors))
    return path


def validate_dxf_file(path: str | Path, expected_scene: Any | None = None) -> DxfValidationResult:
    """Reopen a DXF and verify units, layers, and expected structural entities."""
    errors: list[str] = []
    try:
        document = ezdxf.readfile(path)  # type: ignore[attr-defined]
    except Exception as exc:
        return DxfValidationResult(False, (f"unable to open DXF: {exc}",), {}, "unknown")
    modelspace = document.modelspace()
    counts = {
        "columns": len(modelspace.query("LWPOLYLINE[layer=='S2B_COLUMNS']"))
        + len(modelspace.query("CIRCLE[layer=='S2B_COLUMNS']")),
        "grids": len(modelspace.query("LINE[layer=='S2B_GRIDS']")),
        "labels": len(modelspace.query("TEXT[layer=='S2B_LABELS']")),
    }
    units = str(ezdxf.units.unit_name(document.units))
    if document.units != ezdxf.units.MM:
        errors.append(f"expected millimetres, found {units}")
    required_layers = {"S2B_COLUMNS", "S2B_GRIDS", "S2B_LABELS"}
    missing_layers = required_layers - {layer.dxf.name for layer in document.layers}
    if missing_layers:
        errors.append(f"missing layers: {sorted(missing_layers)}")
    if expected_scene is not None:
        data = require_valid_scene(expected_scene)
        expected_columns = sum(entity["type"] == "column" for entity in data["entities"])
        expected_grids = len(data.get("grids", [])) + sum(
            entity["type"] == "grid_axis" for entity in data["entities"]
        )
        if counts["columns"] != expected_columns:
            errors.append(f"expected {expected_columns} columns, found {counts['columns']}")
        if counts["grids"] != expected_grids:
            errors.append(f"expected {expected_grids} grids, found {counts['grids']}")
    return DxfValidationResult(not errors, tuple(errors), counts, units)
