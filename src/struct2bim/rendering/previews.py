"""Lightweight, deterministic annotation and geometry preview rendering."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from collections.abc import Callable, Iterable
from typing import Any, cast

from PIL import Image, ImageChops, ImageDraw, ImageFont

_BLUE = "#2563A6"
_GREEN = "#16845B"
_AMBER = "#D97706"
_CHARCOAL = "#19232D"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _load_scene(scene: Path | dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(scene, Path):
        return cast(dict[str, Any], json.loads(scene.read_text(encoding="utf-8")))
    if hasattr(scene, "canonical_json"):
        return cast(dict[str, Any], json.loads(scene.canonical_json()))
    return cast(dict[str, Any], scene)


def _entities(scene: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return cast(Iterable[dict[str, Any]], scene.get("entities", scene.get("structural_entities", [])))


def _column_polygon(entity: dict[str, Any]) -> list[tuple[float, float]]:
    if polygon := entity.get("polygon_mm"):
        return [(float(x), float(y)) for x, y in polygon]
    center = entity.get("center_mm", [0.0, 0.0])
    cx, cy = (center.get("x", 0.0), center.get("y", 0.0)) if isinstance(center, dict) else center
    dimensions = entity.get("dimensions_mm", {})
    if entity.get("subtype") == "circular" and dimensions.get("diameter"):
        radius = float(dimensions["diameter"]) / 2
        return [
            (float(cx) + math.cos(index * math.tau / 32) * radius, float(cy) + math.sin(index * math.tau / 32) * radius)
            for index in range(32)
        ]
    width = float(dimensions.get("width", entity.get("width_mm", 300.0)))
    depth = float(dimensions.get("depth", entity.get("depth_mm", 300.0)))
    angle = math.radians(float(entity.get("rotation_deg", 0.0)))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    points = []
    for x, y in [(-width / 2, -depth / 2), (width / 2, -depth / 2), (width / 2, depth / 2), (-width / 2, depth / 2)]:
        points.append((float(cx) + x * cos_a - y * sin_a, float(cy) + x * sin_a + y * cos_a))
    return points


def _center(entity: dict[str, Any]) -> tuple[float, float]:
    center = entity.get("center_mm", [0.0, 0.0])
    if isinstance(center, dict):
        return float(center.get("x", 0.0)), float(center.get("y", 0.0))
    return float(center[0]), float(center[1])


def _bounds(polygons: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    points = [point for polygon in polygons for point in polygon]
    if not points:
        return 0.0, 0.0, 1000.0, 1000.0
    xs, ys = zip(*points)
    pad = max(max(xs) - min(xs), max(ys) - min(ys), 1000.0) * 0.14
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _scene_bounds(
    scene: dict[str, Any], polygons: list[list[tuple[float, float]]]
) -> tuple[float, float, float, float]:
    points = [point for polygon in polygons for point in polygon]
    for axis in scene.get("grids", []):
        for endpoint in (axis.get("start_mm", {}), axis.get("end_mm", {})):
            if isinstance(endpoint, dict):
                points.append((float(endpoint.get("x", 0)), float(endpoint.get("y", 0))))
    if not points:
        return _bounds(polygons)
    xs, ys = zip(*points)
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1000.0)
    pad = span * 0.12
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _rect(center: tuple[float, float], width: float, height: float) -> list[tuple[float, float]]:
    x, y = center
    return [
        (x - width / 2, y - height / 2),
        (x + width / 2, y - height / 2),
        (x + width / 2, y + height / 2),
        (x - width / 2, y + height / 2),
    ]


def _draw_hatch(
    image: Image.Image, polygon: list[tuple[int, int]], color: str, spacing: int = 9
) -> None:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    hatch = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hatch_draw = ImageDraw.Draw(hatch)
    bounds = mask.getbbox()
    if bounds is None:
        return
    left, top, right, bottom = bounds
    for offset in range(left - (bottom - top), right + (bottom - top), spacing):
        hatch_draw.line((offset, bottom, offset + bottom - top, top), fill=color, width=1)
    alpha = ImageChops.multiply(hatch.getchannel("A"), mask)
    image.paste(hatch, (0, 0), alpha)


def _projector(
    bounds: tuple[float, float, float, float], size: tuple[int, int]
) -> Callable[[tuple[float, float]], tuple[int, int]]:
    min_x, min_y, max_x, max_y = bounds
    width, height = size
    usable_w, usable_h = width - 80, height - 110
    scale = min(usable_w / max(max_x - min_x, 1), usable_h / max(max_y - min_y, 1))

    def project(point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        return int(40 + (x - min_x) * scale), int(height - 45 - (y - min_y) * scale)

    return project


def _camera_projector(
    bounds: tuple[float, float, float, float], size: tuple[int, int]
) -> Callable[[tuple[float, float]], tuple[int, int]]:
    """Project world bounds exactly as Blender's orthographic camera does."""
    min_x, min_y, max_x, max_y = bounds
    width, height = size

    def project(point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        px = (x - min_x) / max(max_x - min_x, 1.0) * width
        py = height - (y - min_y) / max(max_y - min_y, 1.0) * height
        return int(px), int(py)

    return project


def _badge(draw: ImageDraw.ImageDraw, text: str = "SYNTHETIC GROUND TRUTH") -> None:
    font = _font(22, bold=True)
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    draw.rounded_rectangle((22, 18, 54 + width, 56), radius=8, fill=_AMBER)
    draw.text((38, 25), text, font=font, fill="white")


def render_annotation_preview(
    scene: Path | dict[str, Any], source_image: Path, output: Path
) -> Path:
    """Overlay exact instance polygons and identifiers on a source drawing."""
    data = _load_scene(scene)
    image = Image.open(source_image).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    polygons = [_column_polygon(entity) for entity in _entities(data)]
    sidecar = source_image.with_suffix(source_image.suffix + ".render.json")
    render_data = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else None
    project = _camera_projector(tuple(render_data["world_bounds_mm"]), image.size) if render_data else _projector(_bounds(polygons), image.size)
    label_font = _font(max(14, image.width // 70), bold=True)
    for index, (entity, polygon) in enumerate(zip(_entities(data), polygons, strict=False), start=1):
        points = [project(point) for point in polygon]
        draw.polygon(points, fill=(217, 119, 6, 80), outline=(217, 119, 6, 255), width=3)
        center = project(_center(entity))
        label = str(entity.get("label", entity.get("classification", {}).get("label", entity.get("id", index))))
        draw.text((center[0] + 6, center[1] - 12), label, font=label_font, fill=_CHARCOAL, stroke_width=2, stroke_fill="white")
    _badge(draw)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, compress_level=1)
    return output


def render_geometry_preview(
    scene: Path | dict[str, Any], output: Path, *, size: tuple[int, int] = (1200, 900)
) -> Path:
    """Render a fast structural-plan preview without launching Blender."""
    data = _load_scene(scene)
    image = Image.new("RGB", size, "#FFFEFA")
    draw = ImageDraw.Draw(image)
    entities = list(_entities(data))
    polygons = [_column_polygon(entity) for entity in entities]
    bounds = _scene_bounds(data, polygons)
    project = _camera_projector(bounds, size)
    seed = int(data.get("source", {}).get("scene_seed", 0))
    rng = random.Random(seed)
    context = data.get("drawing_context", {})
    hatch_probability = float(context.get("hatch_probability", 0.34))
    outline_probability = float(context.get("outline_probability", 0.32))
    diagonal_probability = float(context.get("diagonal_beam_probability", 0.24))
    overlap_probability = float(context.get("footing_overlap_probability", 0.28))
    annotation_density = float(context.get("annotation_density", 0.8))

    grid_color = "#E8A2AC"
    beam_color = "#18BFC4"
    footing_color = "#37C95A"
    column_color = "#148B42"
    label_color = "#B59B00"
    grid_font = _font(max(11, size[0] // 105), bold=True)

    # Grid axes, bubbles, and labels recreate the visual load around targets.
    for axis in data.get("grids", []):
        start, end = axis["start_mm"], axis["end_mm"]
        start_px = project((float(start["x"]), float(start["y"])))
        end_px = project((float(end["x"]), float(end["y"])))
        draw.line((*start_px, *end_px), fill=grid_color, width=1)
        bubble = start_px if abs(end_px[1] - start_px[1]) > abs(end_px[0] - start_px[0]) else end_px
        radius = max(10, size[0] // 90)
        draw.ellipse((bubble[0] - radius, bubble[1] - radius, bubble[0] + radius, bubble[1] + radius), outline=grid_color, width=2)
        label = str(axis.get("label", ""))
        box = draw.textbbox((0, 0), label, font=grid_font)
        draw.text((bubble[0] - (box[2] - box[0]) / 2, bubble[1] - (box[3] - box[1]) / 2), label, font=grid_font, fill="#B75E69")

    centers = [_center(entity) for entity in entities]
    # Neighbour connections become double-line tie and grade beams. Some are
    # diagonal and pass through target columns, matching real foundation plans.
    sorted_by_y = sorted(centers, key=lambda point: (round(point[1], -2), point[0]))
    sorted_by_x = sorted(centers, key=lambda point: (round(point[0], -2), point[1]))
    edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for ordered in (sorted_by_y, sorted_by_x):
        for first, second in zip(ordered, ordered[1:], strict=False):
            dx, dy = abs(second[0] - first[0]), abs(second[1] - first[1])
            aligned = dy < 900 if ordered is sorted_by_y else dx < 900
            distance = math.hypot(second[0] - first[0], second[1] - first[1])
            if aligned or (distance < 7500 and rng.random() < diagonal_probability):
                edge = tuple(sorted((first, second)))
                edges.add(edge)  # type: ignore[arg-type]
    for first, second in edges:
        a, b = project(first), project(second)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = max(math.hypot(dx, dy), 1)
        offset_x, offset_y = int(-dy / length * 3), int(dx / length * 3)
        draw.line((a[0] + offset_x, a[1] + offset_y, b[0] + offset_x, b[1] + offset_y), fill=beam_color, width=2)
        draw.line((a[0] - offset_x, a[1] - offset_y, b[0] - offset_x, b[1] - offset_y), fill=beam_color, width=2)

    font = _font(max(12, size[0] // 80), bold=True)
    for index, (entity, polygon) in enumerate(zip(entities, polygons, strict=False), start=1):
        center_mm = _center(entity)
        center_px = project(center_mm)
        dimensions = entity.get("dimensions_mm", {})
        diameter = dimensions.get("diameter") or 350
        column_span = max(
            float(dimensions.get("width") or diameter),
            float(dimensions.get("depth") or diameter),
        )
        footing_width = column_span * rng.uniform(4.2, 8.0)
        footing_depth = column_span * rng.uniform(3.8, 7.0)
        if rng.random() < overlap_probability:
            footing_width *= rng.uniform(1.25, 1.8)
        outer = [project(point) for point in _rect(center_mm, footing_width, footing_depth)]
        inner = [project(point) for point in _rect(center_mm, footing_width * 0.72, footing_depth * 0.72)]
        draw.polygon(outer, outline=footing_color, width=2)
        draw.polygon(inner, outline=footing_color, width=2)
        if rng.random() < hatch_probability:
            _draw_hatch(image, inner, "#6FD77F", spacing=max(6, size[0] // 170))

        points = [project(point) for point in polygon]
        if rng.random() < outline_probability:
            draw.polygon(points, fill="#FFFEFA", outline=column_color, width=3)
        else:
            draw.polygon(points, fill="#9BE1A9", outline=column_color, width=3)
        if rng.random() < hatch_probability:
            _draw_hatch(image, points, column_color, spacing=max(4, size[0] // 220))
        label = str(entity.get("label", entity.get("classification", {}).get("label", entity.get("id", "column"))))
        draw.text((center_px[0] + 7, center_px[1] - 18), label, font=font, fill=label_color)
        if rng.random() < annotation_density:
            draw.text((center_px[0] - 10, center_px[1] + 10), f"F{1 + index % 8}", font=_font(max(9, size[0] // 115), True), fill=label_color)

    # Dimension strings and a small stair symbol create realistic non-target clutter.
    min_x, min_y, max_x, max_y = bounds
    dim_y = project((min_x, min_y + (max_y - min_y) * 0.035))[1]
    left, right = project((min_x + (max_x - min_x) * 0.1, min_y)), project((max_x - (max_x - min_x) * 0.1, min_y))
    draw.line((left[0], dim_y, right[0], dim_y), fill=grid_color, width=1)
    draw.text(((left[0] + right[0]) // 2 - 35, dim_y - 18), f"{max_x - min_x:.0f}", font=_font(max(9, size[0] // 120)), fill="#C7717E")
    stair_x, stair_y = int(size[0] * 0.47), int(size[1] * 0.47)
    for step in range(8):
        draw.line((stair_x, stair_y + step * 5, stair_x + 42, stair_y + step * 5), fill="#565F62", width=1)
    draw.text((stair_x + 46, stair_y + 8), "STAIR", font=_font(max(9, size[0] // 120), True), fill="#565F62")

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, compress_level=1)
    output.with_suffix(output.suffix + ".render.json").write_text(
        json.dumps({"image_size": list(size), "world_bounds_mm": list(bounds), "seed": seed}, indent=2),
        encoding="utf-8",
    )
    return output
