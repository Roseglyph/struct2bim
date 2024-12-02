from __future__ import annotations

import ifcopenshell
import pytest

from struct2bim.exporters import export_ifc, validate_ifc_file
from struct2bim.curriculum import generate_reference_scene
from struct2bim.validation import CanonicalValidationError


def fixture_scene() -> dict:
    return {
        "schema_version": "1.0",
        "project": {"name": "IFC Fixture", "units": "mm"},
        "source": {"type": "synthetic_ground_truth", "image": "fixture.png"},
        "transform": {"scale_source": "synthetic_ground_truth", "pixels_per_mm": 0.2},
        "storeys": [{"id": "L01", "name": "Ground", "elevation_mm": 0, "height_mm": 3200}],
        "entities": [
            {"id": "C1", "type": "column", "storey_id": "L01", "center_mm": [1000, 2000],
             "dimensions_mm": {"width": 300, "depth": 600, "height": 3200}, "rotation_deg": 90,
             "classification": {"label": "C1"},
             "provenance": {"source": "synthetic_ground_truth", "confidence": 1.0}},
            {"id": "C2", "type": "column", "storey_id": "L01", "center_mm": [4000, 2000],
             "dimensions_mm": {"width": 400, "depth": 400, "height": 3200}, "rotation_deg": 0},
            {"id": "A", "type": "grid_axis", "storey_id": "L01",
             "start_mm": [0, 0], "end_mm": [0, 5000]},
            {"id": "1", "type": "grid_axis", "storey_id": "L01",
             "start_mm": [0, 0], "end_mm": [5000, 0]},
        ],
    }


def test_ifc_reopens_with_hierarchy_geometry_and_provenance(tmp_path) -> None:
    path = export_ifc(fixture_scene(), tmp_path / "fixture.ifc")
    result = validate_ifc_file(path, fixture_scene())
    assert result.is_valid, result.errors
    assert result.counts["IfcColumn"] == 2
    assert result.counts["IfcGrid"] == 1
    model = ifcopenshell.open(path)
    assert model.schema == "IFC4"
    assert len(model.by_type("IfcExtrudedAreaSolid")) == 2
    assert {item.Name for item in model.by_type("IfcPropertySet")} == {"Pset_Struct2BIMProvenance"}
    first = model.by_type("IfcColumn")[0]
    assert first.ContainedInStructure[0].RelatingStructure.is_a("IfcBuildingStorey")


def test_ifc_export_rejects_unknown_scale(tmp_path) -> None:
    scene = fixture_scene()
    scene["transform"]["scale_source"] = "unknown"
    with pytest.raises(CanonicalValidationError):
        export_ifc(scene, tmp_path / "invalid.ifc")
    assert not (tmp_path / "invalid.ifc").exists()


def test_invalid_ifc_reports_parse_failure(tmp_path) -> None:
    path = tmp_path / "broken.ifc"
    path.write_text("not an IFC", encoding="utf-8")
    result = validate_ifc_file(path)
    assert not result.is_valid
    assert result.errors


def test_domain_reference_scene_exports_without_adapter_code(tmp_path) -> None:
    scene = generate_reference_scene(42)
    path = export_ifc(scene, tmp_path / "reference.ifc")
    model = ifcopenshell.open(path)
    assert len(model.by_type("IfcColumn")) == len(scene.entities)
    assert len(model.by_type("IfcCircleProfileDef")) == sum(
        entity.subtype.value == "circular" for entity in scene.entities
    )


def test_ifc_export_is_byte_reproducible(tmp_path) -> None:
    scene = generate_reference_scene(77)

    first = export_ifc(scene, tmp_path / "first.ifc")
    second = export_ifc(scene, tmp_path / "second.ifc")

    assert first.read_bytes() == second.read_bytes()
