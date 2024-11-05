"""Keep exact annotations aligned with 2D document transforms."""

from __future__ import annotations

import numpy as np

from struct2bim.annotations import AnnotationRecord, AnnotationSet
from struct2bim.augmentation.document import FloatArray, transform_points
from struct2bim.domain import Point2D, Polygon2D


def _transform_point_sequence(
    points: tuple[Point2D, ...], homography: FloatArray
) -> tuple[Point2D, ...]:
    coordinates = np.array([point.as_tuple() for point in points], dtype=np.float64)
    transformed = transform_points(coordinates, homography)
    return tuple(Point2D(x=float(point[0]), y=float(point[1])) for point in transformed)


def transform_annotation_set(
    annotations: AnnotationSet,
    homography: FloatArray,
) -> AnnotationSet:
    """Apply one image homography to every polygon and oriented box."""
    transformed_records: list[AnnotationRecord] = []
    for record in annotations.records:
        transformed_obb = _transform_point_sequence(record.obb_px, homography)
        transformed_records.append(
            AnnotationRecord(
                id=record.id,
                entity_id=record.entity_id,
                class_id=record.class_id,
                class_name=record.class_name,
                polygon_px=Polygon2D(
                    points=_transform_point_sequence(record.polygon_px.points, homography)
                ),
                obb_px=(
                    transformed_obb[0],
                    transformed_obb[1],
                    transformed_obb[2],
                    transformed_obb[3],
                ),
                provenance=record.provenance,
            )
        )
    return AnnotationSet(
        scene_seed=annotations.scene_seed,
        width_px=annotations.width_px,
        height_px=annotations.height_px,
        records=tuple(transformed_records),
    )
