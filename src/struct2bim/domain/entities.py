"""Structural entities represented independently from IFC and drawing software."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from struct2bim.domain.geometry import DomainModel, Point2D, Polygon2D, regular_polygon
from struct2bim.domain.geometry import rotated_rectangle
from struct2bim.domain.provenance import Provenance


class EntityType(StrEnum):
    COLUMN = "column"


class ColumnShape(StrEnum):
    RECTANGULAR = "rectangular"
    CIRCULAR = "circular"


class Storey(DomainModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    elevation_mm: float
    height_mm: float = Field(gt=0)


class ColumnDimensions(DomainModel):
    width: float | None = Field(default=None, gt=0)
    depth: float | None = Field(default=None, gt=0)
    diameter: float | None = Field(default=None, gt=0)
    height: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_profile(self) -> ColumnDimensions:
        rectangular = self.width is not None and self.depth is not None and self.diameter is None
        circular = self.diameter is not None and self.width is None and self.depth is None
        if not (rectangular or circular):
            raise ValueError("dimensions must define either width/depth or diameter")
        return self


class StructuralEntity(DomainModel):
    id: str = Field(min_length=1)
    type: EntityType = EntityType.COLUMN
    subtype: ColumnShape
    storey_id: str = Field(min_length=1)
    center_mm: Point2D
    dimensions_mm: ColumnDimensions
    rotation_deg: float = 0.0
    label: str = Field(min_length=1)
    class_id: int = Field(ge=0)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_shape_dimensions(self) -> StructuralEntity:
        if self.subtype == ColumnShape.CIRCULAR and self.dimensions_mm.diameter is None:
            raise ValueError("circular columns require diameter")
        if self.subtype == ColumnShape.RECTANGULAR and self.dimensions_mm.width is None:
            raise ValueError("rectangular columns require width and depth")
        return self

    def footprint(self, circle_vertices: int = 32) -> Polygon2D:
        if self.subtype == ColumnShape.CIRCULAR:
            assert self.dimensions_mm.diameter is not None
            return regular_polygon(self.center_mm, self.dimensions_mm.diameter / 2, circle_vertices)
        assert self.dimensions_mm.width is not None
        assert self.dimensions_mm.depth is not None
        return rotated_rectangle(
            self.center_mm,
            self.dimensions_mm.width,
            self.dimensions_mm.depth,
            self.rotation_deg,
        )


class GridAxis(DomainModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    start_mm: Point2D
    end_mm: Point2D

    @model_validator(mode="after")
    def validate_length(self) -> GridAxis:
        if self.start_mm == self.end_mm:
            raise ValueError("grid axis endpoints must differ")
        return self
