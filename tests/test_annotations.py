from pathlib import Path

import pytest
from pydantic import ValidationError

from struct2bim.annotations import (
    AnnotationSet,
    annotations_from_scene,
    export_yolo_obb,
    export_yolo_segmentation,
    write_yolo_labels,
)
from struct2bim.curriculum import generate_reference_scene
from struct2bim.domain.errors import AnnotationOutOfBoundsError


def _numbers(line: str) -> list[float]:
    return [float(value) for value in line.split()]


def test_scene_exports_one_exact_annotation_per_column() -> None:
    scene = generate_reference_scene(2048)

    annotations = annotations_from_scene(scene)

    assert len(annotations.records) == len(scene.entities)
    assert {record.entity_id for record in annotations.records} == {
        entity.id for entity in scene.entities
    }
    assert all(record.provenance.value == "synthetic_ground_truth" for record in annotations.records)


def test_segmentation_export_is_normalized_and_task_shaped() -> None:
    annotations = annotations_from_scene(generate_reference_scene(12))

    lines = export_yolo_segmentation(annotations).splitlines()

    assert len(lines) == len(annotations.records)
    for line, record in zip(lines, annotations.records, strict=True):
        values = _numbers(line)
        assert int(values[0]) == record.class_id
        assert len(values) == 1 + 2 * len(record.polygon_px.points)
        assert all(0.0 <= value <= 1.0 for value in values[1:])


def test_obb_export_has_four_normalized_corners() -> None:
    annotations = annotations_from_scene(generate_reference_scene(73))

    lines = export_yolo_obb(annotations).splitlines()

    assert len(lines) == len(annotations.records)
    assert all(len(_numbers(line)) == 9 for line in lines)
    assert all(0 <= value <= 1 for line in lines for value in _numbers(line)[1:])


def test_label_exports_are_byte_deterministic() -> None:
    first = annotations_from_scene(generate_reference_scene(440))
    second = annotations_from_scene(generate_reference_scene(440))

    assert export_yolo_segmentation(first) == export_yolo_segmentation(second)
    assert export_yolo_obb(first) == export_yolo_obb(second)


def test_out_of_bounds_annotation_is_rejected() -> None:
    annotations = annotations_from_scene(generate_reference_scene(11))
    first = annotations.records[0]
    outside = first.model_copy(
        update={
            "polygon_px": first.polygon_px.model_copy(
                update={
                    "points": (
                        first.polygon_px.points[0].model_copy(update={"x": -100.0}),
                        *first.polygon_px.points[1:],
                    )
                }
            )
        }
    )

    with pytest.raises(ValidationError) as error:
        AnnotationSet(
            scene_seed=annotations.scene_seed,
            width_px=annotations.width_px,
            height_px=annotations.height_px,
            records=(outside,),
        )
    assert AnnotationOutOfBoundsError.code in str(error.value) or "outside" in str(error.value)


def test_write_yolo_labels_creates_parent_directory(tmp_path: Path) -> None:
    destination = tmp_path / "labels_seg" / "sample.txt"
    contents = export_yolo_segmentation(annotations_from_scene(generate_reference_scene(8)))

    write_yolo_labels(destination, contents)

    assert destination.read_text(encoding="utf-8") == contents
