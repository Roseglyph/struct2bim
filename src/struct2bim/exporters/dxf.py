"""Create an interoperable DXF view from canonical structural geometry."""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path
from typing import Any, Mapping

import ezdxf

from struct2bim.validation import require_valid_scene


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
    return path
