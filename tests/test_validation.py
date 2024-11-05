from __future__ import annotations

import pytest

from struct2bim.validation import CanonicalValidationError, require_valid_scene, validate_scene


def scene() -> dict:
    return {
        "schema_version": "1.0",
        "project": {"name": "Test", "units": "mm"},
        "source": {"type": "synthetic_ground_truth", "image": "drawing.png"},
        "transform": {"pixels_per_mm": 0.2, "scale_source": "synthetic_ground_truth"},
        "storeys": [{"id": "L01", "name": "Ground", "elevation_mm": 0, "height_mm": 3200}],
        "entities": [{
            "id": "COL-001", "type": "column", "storey_id": "L01",
            "center_mm": [1000, 2000],
            "dimensions_mm": {"width": 300, "depth": 600, "height": 3200},
            "rotation_deg": 90,
        }],
    }


def test_valid_scene_passes() -> None:
    report = validate_scene(scene())
    assert report.is_valid
    assert require_valid_scene(scene())["schema_version"] == "1.0"


def test_unknown_scale_and_duplicate_ids_block_export() -> None:
    value = scene()
    value["transform"]["scale_source"] = "unknown"
    value["entities"].append(dict(value["entities"][0]))
    report = validate_scene(value)
    assert {issue.code for issue in report.errors} >= {"unknown_scale", "duplicate_entity"}
    with pytest.raises(CanonicalValidationError):
        require_valid_scene(value)


def test_substantial_column_overlap_is_warning() -> None:
    value = scene()
    second = dict(value["entities"][0], id="COL-002")
    value["entities"].append(second)
    report = validate_scene(value)
    assert report.is_valid
    assert [warning.code for warning in report.warnings] == ["overlapping_columns"]


def test_unknown_storey_and_negative_geometry_fail() -> None:
    value = scene()
    value["entities"][0]["storey_id"] = "MISSING"
    value["entities"][0]["dimensions_mm"]["width"] = -1
    codes = {issue.code for issue in validate_scene(value).errors}
    assert {"unknown_storey", "invalid_column_geometry"} <= codes
