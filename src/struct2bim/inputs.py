"""Prepare image, PDF and basic DXF documents for detector inference."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import ezdxf
import fitz  # type: ignore[import-untyped]
import numpy as np


def _render_dxf(source: Path, destination: Path, size: int = 1600) -> None:
    doc = ezdxf.readfile(source)  # type: ignore[attr-defined]
    primitives: list[tuple[str, tuple[float, ...]]] = []
    points: list[tuple[float, float]] = []
    for raw_entity in doc.modelspace():
        entity: Any = raw_entity
        kind = entity.dxftype()
        if kind == "LINE":
            line_values = (float(entity.dxf.start.x), float(entity.dxf.start.y), float(entity.dxf.end.x), float(entity.dxf.end.y))
            primitives.append((kind, line_values))
            points.extend(((line_values[0], line_values[1]), (line_values[2], line_values[3])))
        elif kind == "LWPOLYLINE":
            vertices = [(float(x), float(y)) for x, y, *_ in entity.get_points()]
            following = vertices[1:] + vertices[:1] if entity.closed else vertices[1:]
            for start, end in zip(vertices, following, strict=False):
                line_values = (*start, *end)
                primitives.append(("LINE", line_values))
                points.extend((start, end))
        elif kind == "CIRCLE":
            circle_values = (float(entity.dxf.center.x), float(entity.dxf.center.y), float(entity.dxf.radius))
            primitives.append((kind, circle_values))
            points.extend(((circle_values[0] - circle_values[2], circle_values[1] - circle_values[2]), (circle_values[0] + circle_values[2], circle_values[1] + circle_values[2])))
    if not points:
        raise ValueError("DXF contains no supported LINE, LWPOLYLINE or CIRCLE geometry")
    xs, ys = zip(*points)
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    scale = (size - 120) / max(span_x, span_y, 1.0)
    width = max(256, int(span_x * scale + 120))
    height = max(256, int(span_y * scale + 120))
    image = np.full((height, width, 3), 255, dtype=np.uint8)

    def project(x: float, y: float) -> tuple[int, int]:
        return int(60 + (x - min(xs)) * scale), int(height - 60 - (y - min(ys)) * scale)

    for kind, values in primitives:
        if kind == "LINE":
            cv2.line(image, project(values[0], values[1]), project(values[2], values[3]), (30, 40, 50), 2)
        else:
            cv2.circle(image, project(values[0], values[1]), max(1, int(values[2] * scale)), (30, 40, 50), 2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destination), image)


def prepare_document(source: Path, output: Path, *, dpi: int = 200) -> tuple[Path, ...]:
    """Normalize a supported document into one or more detector-ready PNG files."""
    suffix = source.suffix.lower()
    output.mkdir(parents=True, exist_ok=True)
    if suffix == ".dwg":
        raise ValueError("DWG is not supported directly; export the drawing to DXF or PDF first")
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        destination = output / f"{source.stem}.png"
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"unable to decode image: {source}")
        cv2.imwrite(str(destination), image)
        return (destination,)
    if suffix == ".pdf":
        document = fitz.open(source)
        scale = dpi / 72.0
        pages: list[Path] = []
        for index, page in enumerate(document):
            destination = output / f"{source.stem}_page_{index + 1:03d}.png"
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(destination)
            pages.append(destination)
        return tuple(pages)
    if suffix == ".dxf":
        destination = output / f"{source.stem}.png"
        _render_dxf(source, destination)
        return (destination,)
    raise ValueError(f"unsupported input format: {suffix or '<none>'}")
