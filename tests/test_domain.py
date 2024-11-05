import math

import pytest
from pydantic import ValidationError

from struct2bim.curriculum import generate_reference_scene
from struct2bim.domain import ColumnDimensions, CoordinateTransform, Point2D, Polygon2D
from struct2bim.domain.geometry import rotated_rectangle


def test_coordinate_transform_round_trip() -> None:
    transform = CoordinateTransform(
        pixels_per_mm=0.2,
        origin_px=Point2D(x=1024, y=1024),
        origin_world_mm=Point2D(x=100, y=-50),
    )
    original = Point2D(x=2600, y=1750)

    restored = transform.image_to_drawing(transform.drawing_to_image(original))

    assert restored.x == pytest.approx(original.x)
    assert restored.y == pytest.approx(original.y)


def test_rotated_rectangle_preserves_area() -> None:
    polygon = rotated_rectangle(Point2D(x=0, y=0), 300, 600, 37)

    assert polygon.area == pytest.approx(180_000)
    assert len(polygon.points) == 4


def test_polygon_rejects_degenerate_geometry() -> None:
    with pytest.raises(ValidationError, match="non-zero area"):
        Polygon2D(
            points=(Point2D(x=0, y=0), Point2D(x=1, y=1), Point2D(x=2, y=2))
        )


def test_column_dimensions_require_one_profile_kind() -> None:
    with pytest.raises(ValidationError, match="either width/depth or diameter"):
        ColumnDimensions(width=300, depth=600, diameter=400, height=3200)


def test_scene_json_round_trip_is_stable() -> None:
    scene = generate_reference_scene(7301)

    restored = type(scene).model_validate_json(scene.canonical_json())

    assert restored == scene
    assert restored.sha256 == scene.sha256
    assert len(scene.sha256) == 64
    assert not math.isnan(scene.entities[0].footprint().area)


def test_scene_rejects_missing_storey_reference() -> None:
    scene = generate_reference_scene(42)
    bad_entity = scene.entities[0].model_copy(update={"storey_id": "MISSING"})

    with pytest.raises(ValidationError, match="missing storeys"):
        type(scene)(**scene.model_dump(exclude={"entities"}), entities=(bad_entity,))
