"""Coordinate-space and planar geometry primitives."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from struct2bim.domain.errors import InvalidGeometryError


class DomainModel(BaseModel):
    """Strict immutable base for deterministic domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Point2D(DomainModel):
    """A point in a documented coordinate space."""

    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


class Polygon2D(DomainModel):
    """A simple polygon represented without a repeated closing vertex."""

    points: tuple[Point2D, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_area(self) -> Polygon2D:
        if abs(self.signed_area) <= 1e-9:
            raise InvalidGeometryError("polygon must have non-zero area")
        return self

    @property
    def signed_area(self) -> float:
        pairs = zip(self.points, self.points[1:] + self.points[:1], strict=True)
        return 0.5 * sum(a.x * b.y - b.x * a.y for a, b in pairs)

    @property
    def area(self) -> float:
        return abs(self.signed_area)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs = [point.x for point in self.points]
        ys = [point.y for point in self.points]
        return min(xs), min(ys), max(xs), max(ys)


class CoordinateTransform(DomainModel):
    """Reversible drawing-mm to top-left-origin image-pixel transform."""

    pixels_per_mm: float = Field(gt=0)
    origin_px: Point2D
    origin_world_mm: Point2D = Point2D(x=0.0, y=0.0)

    def drawing_to_image(self, point: Point2D) -> Point2D:
        return Point2D(
            x=self.origin_px.x + (point.x - self.origin_world_mm.x) * self.pixels_per_mm,
            y=self.origin_px.y - (point.y - self.origin_world_mm.y) * self.pixels_per_mm,
        )

    def image_to_drawing(self, point: Point2D) -> Point2D:
        return Point2D(
            x=(point.x - self.origin_px.x) / self.pixels_per_mm + self.origin_world_mm.x,
            y=(self.origin_px.y - point.y) / self.pixels_per_mm + self.origin_world_mm.y,
        )

    def polygon_to_image(self, polygon: Polygon2D) -> Polygon2D:
        return Polygon2D(points=tuple(self.drawing_to_image(point) for point in polygon.points))


def rotated_rectangle(
    center: Point2D, width: float, depth: float, rotation_deg: float
) -> Polygon2D:
    """Return exact counter-clockwise corners for a rotated rectangle."""

    if width <= 0 or depth <= 0:
        raise InvalidGeometryError("rectangle dimensions must be positive")
    radians = math.radians(rotation_deg)
    cosine, sine = math.cos(radians), math.sin(radians)
    corners: list[Point2D] = []
    for local_x, local_y in (
        (-width / 2, -depth / 2),
        (width / 2, -depth / 2),
        (width / 2, depth / 2),
        (-width / 2, depth / 2),
    ):
        corners.append(
            Point2D(
                x=center.x + local_x * cosine - local_y * sine,
                y=center.y + local_x * sine + local_y * cosine,
            )
        )
    return Polygon2D(points=tuple(corners))


def regular_polygon(center: Point2D, radius: float, vertices: int = 32) -> Polygon2D:
    """Approximate a circular annotation with a deterministic polygon."""

    if radius <= 0 or vertices < 8:
        raise InvalidGeometryError("circle radius must be positive and vertices at least eight")
    return Polygon2D(
        points=tuple(
            Point2D(
                x=center.x + radius * math.cos(2 * math.pi * index / vertices),
                y=center.y + radius * math.sin(2 * math.pi * index / vertices),
            )
            for index in range(vertices)
        )
    )
