"""Task-neutral exact annotation records."""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field, model_validator

from struct2bim.domain.entities import ColumnShape, StructuralEntity
from struct2bim.domain.errors import AnnotationOutOfBoundsError
from struct2bim.domain.geometry import DomainModel, Point2D, Polygon2D
from struct2bim.domain.provenance import SourceType
from struct2bim.domain.scene import StructuralScene


class OntologyClass(IntEnum):
    COLUMN_RECTANGULAR = 0
    COLUMN_CIRCULAR = 1


class AnnotationRecord(DomainModel):
    id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    class_id: int = Field(ge=0)
    class_name: str = Field(min_length=1)
    polygon_px: Polygon2D
    obb_px: tuple[Point2D, Point2D, Point2D, Point2D]
    provenance: SourceType


class AnnotationSet(DomainModel):
    schema_version: str = "1.0"
    scene_seed: int
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    records: tuple[AnnotationRecord, ...]

    @model_validator(mode="after")
    def validate_bounds(self) -> AnnotationSet:
        tolerance = 1e-7
        for record in self.records:
            for point in record.polygon_px.points + record.obb_px:
                if not (
                    -tolerance <= point.x <= self.width_px + tolerance
                    and -tolerance <= point.y <= self.height_px + tolerance
                ):
                    raise AnnotationOutOfBoundsError(
                        f"annotation {record.id} point {point.as_tuple()} is outside "
                        f"{self.width_px}x{self.height_px}"
                    )
        return self

    def normalized(self, point: Point2D) -> Point2D:
        return Point2D(x=point.x / self.width_px, y=point.y / self.height_px)


def _obb_for_entity(
    entity: StructuralEntity, polygon_px: Polygon2D
) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    if entity.subtype == ColumnShape.RECTANGULAR:
        if len(polygon_px.points) != 4:
            raise ValueError("rectangular footprint must have four corners")
        return (
            polygon_px.points[0],
            polygon_px.points[1],
            polygon_px.points[2],
            polygon_px.points[3],
        )
    min_x, min_y, max_x, max_y = polygon_px.bounds
    return (
        Point2D(x=min_x, y=min_y),
        Point2D(x=max_x, y=min_y),
        Point2D(x=max_x, y=max_y),
        Point2D(x=min_x, y=max_y),
    )


def annotations_from_scene(scene: StructuralScene, *, circle_vertices: int = 32) -> AnnotationSet:
    """Project scene truth into image space without inspecting rendered pixels."""

    records: list[AnnotationRecord] = []
    for entity in scene.entities:
        polygon_px = scene.transform.polygon_to_image(entity.footprint(circle_vertices))
        expected_class = (
            OntologyClass.COLUMN_CIRCULAR
            if entity.subtype == ColumnShape.CIRCULAR
            else OntologyClass.COLUMN_RECTANGULAR
        )
        if entity.class_id != int(expected_class):
            raise ValueError(
                f"entity {entity.id} class_id {entity.class_id} disagrees with {entity.subtype}"
            )
        records.append(
            AnnotationRecord(
                id=f"ANN-{entity.id}",
                entity_id=entity.id,
                class_id=entity.class_id,
                class_name=expected_class.name.lower(),
                polygon_px=polygon_px,
                obb_px=_obb_for_entity(entity, polygon_px),
                provenance=entity.provenance.source,
            )
        )
    return AnnotationSet(
        scene_seed=scene.source.scene_seed,
        width_px=scene.source.width_px,
        height_px=scene.source.height_px,
        records=tuple(records),
    )
