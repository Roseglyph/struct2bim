"""YOLO segmentation and oriented-bounding-box text exporters."""

from __future__ import annotations

from pathlib import Path

from struct2bim.annotations.records import AnnotationSet


def _number(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text if text else "0"


def export_yolo_segmentation(annotations: AnnotationSet) -> str:
    """Return Ultralytics segmentation labels with normalized polygon vertices."""

    lines: list[str] = []
    for record in annotations.records:
        coordinates = [
            coordinate
            for point in record.polygon_px.points
            for coordinate in (
                _number(point.x / annotations.width_px),
                _number(point.y / annotations.height_px),
            )
        ]
        lines.append(" ".join((str(record.class_id), *coordinates)))
    return "\n".join(lines) + ("\n" if lines else "")


def export_yolo_obb(annotations: AnnotationSet) -> str:
    """Return Ultralytics OBB labels as four normalized image-space corners."""

    lines: list[str] = []
    for record in annotations.records:
        coordinates = [
            coordinate
            for point in record.obb_px
            for coordinate in (
                _number(point.x / annotations.width_px),
                _number(point.y / annotations.height_px),
            )
        ]
        lines.append(" ".join((str(record.class_id), *coordinates)))
    return "\n".join(lines) + ("\n" if lines else "")


def write_yolo_labels(path: Path, contents: str) -> None:
    """Write deterministic UTF-8 labels, creating the destination directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8", newline="\n")
