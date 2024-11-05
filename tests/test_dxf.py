from __future__ import annotations

import ezdxf

from struct2bim.exporters import export_dxf
from struct2bim.curriculum import generate_reference_scene


def test_dxf_contains_closed_column_and_grid(tmp_path) -> None:
    scene = {
        "project": {"name": "DXF Fixture", "units": "mm"},
        "transform": {"scale_source": "synthetic_ground_truth", "pixels_per_mm": 0.2},
        "storeys": [{"id": "L01", "height_mm": 3000}],
        "entities": [
            {"id": "C1", "type": "column", "storey_id": "L01", "center_mm": [1000, 2000],
             "dimensions_mm": {"width": 300, "depth": 500, "height": 3000}, "rotation_deg": 30},
            {"id": "G-A", "type": "grid_axis", "storey_id": "L01",
             "start_mm": [0, 0], "end_mm": [0, 5000], "label": "A"},
        ],
    }
    path = export_dxf(scene, tmp_path / "model.dxf")
    document = ezdxf.readfile(path)
    modelspace = document.modelspace()
    polylines = list(modelspace.query("LWPOLYLINE[layer=='S2B_COLUMNS']"))
    assert document.units == ezdxf.units.MM
    assert len(polylines) == 1
    assert polylines[0].closed
    assert len(list(modelspace.query("LINE[layer=='S2B_GRIDS']"))) == 1
    assert len(list(modelspace.query("TEXT[layer=='S2B_LABELS']"))) == 1


def test_domain_reference_scene_exports_all_entities(tmp_path) -> None:
    scene = generate_reference_scene(42)
    document = ezdxf.readfile(export_dxf(scene, tmp_path / "reference.dxf"))
    modelspace = document.modelspace()
    assert len(list(modelspace.query("LWPOLYLINE"))) + len(list(modelspace.query("CIRCLE"))) == len(scene.entities)
    assert len(list(modelspace.query("LINE[layer=='S2B_GRIDS']"))) == len(scene.grids)
