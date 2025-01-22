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


def _dashed_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    fill: str,
    width: int = 1,
    dash: int = 8,
    gap: int = 6,
) -> None:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(math.hypot(dx, dy), 1)
    ux, uy = dx / length, dy / length
    cursor = 0.0
    while cursor < length:
        finish = min(length, cursor + dash)
        draw.line(
            (
                start[0] + ux * cursor,
                start[1] + uy * cursor,
                start[0] + ux * finish,
                start[1] + uy * finish,
            ),
            fill=fill,
            width=width,
        )
        cursor += dash + gap


def _centered_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str,
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (position[0] - (box[2] - box[0]) / 2, position[1] - (box[3] - box[1]) / 2),
        text,
        font=font,
        fill=fill,
    )


def _dimension_chain(
    draw: ImageDraw.ImageDraw,
    positions: list[int],
    ordinate: int,
    labels: list[str],
    *,
    vertical: bool = False,
    outward: int = 1,
) -> None:
    color = "#62686C"
    font = _font(10)
    if len(positions) < 2:
        return
    first, last = positions[0], positions[-1]
    if vertical:
        draw.line((ordinate, first, ordinate, last), fill=color, width=1)
        for index, position in enumerate(positions):
            draw.line((ordinate - 5, position - 5, ordinate + 5, position + 5), fill=color, width=1)
            draw.line((ordinate, position, ordinate - outward * 13, position), fill="#9CA2A6", width=1)
            if index < len(labels):
                midpoint = (position + positions[index + 1]) / 2
                _centered_text(draw, (ordinate - outward * 19, midpoint), labels[index], font=font, fill=color)
    else:
        draw.line((first, ordinate, last, ordinate), fill=color, width=1)
        for index, position in enumerate(positions):
            draw.line((position - 5, ordinate + 5, position + 5, ordinate - 5), fill=color, width=1)
            draw.line((position, ordinate, position, ordinate + outward * 13), fill="#9CA2A6", width=1)
            if index < len(labels):
                midpoint = (position + positions[index + 1]) / 2
                _centered_text(draw, (midpoint, ordinate + outward * 14), labels[index], font=font, fill=color)


def _north_arrow(draw: ImageDraw.ImageDraw, center: tuple[int, int]) -> None:
    x, y = center
    draw.line((x, y + 26, x, y - 22), fill="#2D3337", width=2)
    draw.polygon([(x, y - 34), (x - 9, y - 15), (x, y - 20)], fill="#2D3337")
    draw.polygon([(x, y - 34), (x + 9, y - 15), (x, y - 20)], outline="#2D3337")
    draw.ellipse((x - 22, y - 22, x + 22, y + 22), outline="#8C9398", width=1)
    _centered_text(draw, (x, y - 47), "N", font=_font(12, True), fill="#2D3337")


def _revision_cloud(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    radius = 6
    for x in range(left, right, radius * 2):
        draw.arc((x, top - radius, x + radius * 2, top + radius), 180, 360, fill="#777D81")
        draw.arc((x, bottom - radius, x + radius * 2, bottom + radius), 0, 180, fill="#777D81")
    for y in range(top, bottom, radius * 2):
        draw.arc((left - radius, y, left + radius, y + radius * 2), 90, 270, fill="#777D81")
        draw.arc((right - radius, y, right + radius, y + radius * 2), 270, 90, fill="#777D81")


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


def _render_geometry_preview_legacy(
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

    grid_color = "#A8AFB4"
    beam_color = "#4E565B"
    footing_color = "#555D62"
    column_color = "#252B2F"
    label_color = "#30363A"
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
        draw.text((bubble[0] - (box[2] - box[0]) / 2, bubble[1] - (box[3] - box[1]) / 2), label, font=grid_font, fill="#636B70")

    # A slightly irregular double-line foundation boundary gives dense scenes
    # the same document hierarchy as a real foundation sheet.
    min_x, min_y, max_x, max_y = bounds
    inset_x = (max_x - min_x) * 0.075
    inset_y = (max_y - min_y) * 0.075
    boundary_mm = [
        (min_x + inset_x * 1.35, max_y - inset_y),
        (max_x - inset_x * 1.55, max_y - inset_y * 0.82),
        (max_x - inset_x * 0.78, max_y - inset_y * 2.05),
        (max_x - inset_x * 0.88, min_y + inset_y * 1.3),
        (max_x - inset_x * 1.65, min_y + inset_y * 0.72),
        (min_x + inset_x * 1.55, min_y + inset_y * 0.88),
        (min_x + inset_x * 0.72, min_y + inset_y * 2.0),
        (min_x + inset_x * 0.82, max_y - inset_y * 1.85),
    ]
    boundary = [project(point) for point in boundary_mm]
    draw.polygon(boundary, outline="#42494E", width=3)
    center_boundary = (
        sum(point[0] for point in boundary_mm) / len(boundary_mm),
        sum(point[1] for point in boundary_mm) / len(boundary_mm),
    )
    inner_boundary = [
        project((center_boundary[0] + (point[0] - center_boundary[0]) * 0.985,
                 center_boundary[1] + (point[1] - center_boundary[1]) * 0.985))
        for point in boundary_mm
    ]
    draw.polygon(inner_boundary, outline="#8B9297", width=1)

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
        draw.polygon(outer, fill="#FAFAF8", outline=footing_color, width=2)
        draw.polygon(inner, fill="#F2F3F1", outline=footing_color, width=2)
        if rng.random() < hatch_probability:
            _draw_hatch(image, inner, "#9DA3A7", spacing=max(6, size[0] // 170))

        points = [project(point) for point in polygon]
        if rng.random() < outline_probability:
            draw.polygon(points, fill="#FFFEFA", outline=column_color, width=3)
        else:
            draw.polygon(points, fill="#4B5256", outline=column_color, width=3)
        if rng.random() < hatch_probability:
            _draw_hatch(image, points, column_color, spacing=max(4, size[0] // 220))
        label = str(entity.get("label", entity.get("classification", {}).get("label", entity.get("id", "column"))))
        draw.text((center_px[0] + 7, center_px[1] - 18), label, font=font, fill=label_color)
        if rng.random() < annotation_density:
            draw.text((center_px[0] - 10, center_px[1] + 10), f"F{1 + index % 8}", font=_font(max(9, size[0] // 115), True), fill=label_color)

    # Dimension strings and a small stair symbol create realistic non-target clutter.
    dim_y = project((min_x, min_y + (max_y - min_y) * 0.035))[1]
    left, right = project((min_x + (max_x - min_x) * 0.1, min_y)), project((max_x - (max_x - min_x) * 0.1, min_y))
    draw.line((left[0], dim_y, right[0], dim_y), fill=grid_color, width=1)
    draw.text(((left[0] + right[0]) // 2 - 35, dim_y - 18), f"{max_x - min_x:.0f}", font=_font(max(9, size[0] // 120)), fill="#626A6F")
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


def render_geometry_preview(
    scene: Path | dict[str, Any], output: Path, *, size: tuple[int, int] = (1200, 900)
) -> Path:
    """Render a deterministic structural foundation sheet without Blender."""
    data = _load_scene(scene)
    image = Image.new("RGB", size, "#FEFDF9")
    draw = ImageDraw.Draw(image)
    entities = list(_entities(data))
    polygons = [_column_polygon(entity) for entity in entities]
    seed = int(data.get("source", {}).get("scene_seed", 0))
    rng = random.Random(seed)
    context = data.get("drawing_context", {})
    options = data.get("preview_options", {})

    vertical_axes = sorted(
        (
            axis for axis in data.get("grids", [])
            if abs(float(axis["start_mm"]["x"]) - float(axis["end_mm"]["x"])) < 1
        ),
        key=lambda axis: float(axis["start_mm"]["x"]),
    )
    horizontal_axes = sorted(
        (
            axis for axis in data.get("grids", [])
            if abs(float(axis["start_mm"]["y"]) - float(axis["end_mm"]["y"])) < 1
        ),
        key=lambda axis: float(axis["start_mm"]["y"]),
    )
    x_values = [float(axis["start_mm"]["x"]) for axis in vertical_axes]
    y_values = [float(axis["start_mm"]["y"]) for axis in horizontal_axes]
    if not x_values or not y_values:
        bounds = _scene_bounds(data, polygons)
        x_values = [bounds[0], bounds[2]]
        y_values = [bounds[1], bounds[3]]
    min_grid_x, max_grid_x = min(x_values), max(x_values)
    min_grid_y, max_grid_y = min(y_values), max(y_values)
    span_x = max(max_grid_x - min_grid_x, 1000)
    span_y = max(max_grid_y - min_grid_y, 1000)
    bounds = (
        min_grid_x - span_x * 0.18,
        min_grid_y - span_y * 0.29,
        max_grid_x + span_x * 0.18,
        max_grid_y + span_y * 0.19,
    )
    project = _camera_projector(bounds, size)

    grid_color = "#9BA1A5"
    ink = "#30363A"
    beam_color = "#555C60"
    footing_color = "#555C60"
    grid_font = _font(max(10, size[0] // 125), bold=True)
    note_font = _font(max(9, size[0] // 145))
    label_font = _font(max(10, size[0] // 120), bold=True)
    lineweight = float(options.get("lineweight_variation", 0.35))
    primary_width = 1 + round(lineweight * 2)

    # Grid axes extend beyond the structural envelope and terminate in bubbles
    # at both sides, as they do on real foundation sheets.
    axis_extend_x = span_x * 0.105
    axis_extend_y = span_y * 0.10
    bubble_radius = max(10, size[0] // 115)
    for axis in vertical_axes:
        x = float(axis["start_mm"]["x"])
        start = project((x, min_grid_y - axis_extend_y))
        end = project((x, max_grid_y + axis_extend_y))
        _dashed_line(draw, start, end, fill=grid_color, dash=7, gap=5)
        for bubble in (start, end):
            draw.ellipse(
                (bubble[0] - bubble_radius, bubble[1] - bubble_radius,
                 bubble[0] + bubble_radius, bubble[1] + bubble_radius),
                fill="#FEFDF9", outline="#636A6F", width=1,
            )
            _centered_text(draw, bubble, str(axis.get("label", "")), font=grid_font, fill=ink)
    for axis in horizontal_axes:
        y = float(axis["start_mm"]["y"])
        start = project((min_grid_x - axis_extend_x, y))
        end = project((max_grid_x + axis_extend_x, y))
        _dashed_line(draw, start, end, fill=grid_color, dash=7, gap=5)
        for bubble in (start, end):
            draw.ellipse(
                (bubble[0] - bubble_radius, bubble[1] - bubble_radius,
                 bubble[0] + bubble_radius, bubble[1] + bubble_radius),
                fill="#FEFDF9", outline="#636A6F", width=1,
            )
            _centered_text(draw, bubble, str(axis.get("label", "")), font=grid_font, fill=ink)

    # The perimeter is separate from the grid so the axis system remains clear.
    edge_x, edge_y = span_x * 0.055, span_y * 0.055
    if options.get("building_outline") == "rectangular":
        boundary_mm = [
            (min_grid_x - edge_x, min_grid_y - edge_y),
            (max_grid_x + edge_x, min_grid_y - edge_y),
            (max_grid_x + edge_x, max_grid_y + edge_y),
            (min_grid_x - edge_x, max_grid_y + edge_y),
        ]
    else:
        boundary_mm = [
            (min_grid_x - edge_x * 0.8, min_grid_y - edge_y),
            (max_grid_x + edge_x * 0.25, min_grid_y - edge_y * 1.05),
            (max_grid_x + edge_x, min_grid_y + span_y * 0.14),
            (max_grid_x + edge_x * 0.92, max_grid_y - span_y * 0.18),
            (max_grid_x + edge_x * 0.35, max_grid_y + edge_y),
            (min_grid_x - edge_x * 0.5, max_grid_y + edge_y * 0.9),
            (min_grid_x - edge_x, max_grid_y - span_y * 0.15),
            (min_grid_x - edge_x * 0.92, min_grid_y + span_y * 0.12),
        ]
    boundary = [project(point) for point in boundary_mm]
    draw.polygon(boundary, outline="#4A5054", width=primary_width)
    center_boundary = (
        sum(point[0] for point in boundary_mm) / len(boundary_mm),
        sum(point[1] for point in boundary_mm) / len(boundary_mm),
    )
    inner_boundary = [
        project((center_boundary[0] + (point[0] - center_boundary[0]) * 0.985,
                 center_boundary[1] + (point[1] - center_boundary[1]) * 0.985))
        for point in boundary_mm
    ]
    draw.polygon(inner_boundary, outline="#A1A6AA", width=1)

    centers = [_center(entity) for entity in entities]
    sorted_by_y = sorted(centers, key=lambda point: (round(point[1], -2), point[0]))
    sorted_by_x = sorted(centers, key=lambda point: (round(point[0], -2), point[1]))
    diagonal_probability = float(context.get("diagonal_beam_probability", 0.24))
    edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for ordered, tolerance in ((sorted_by_y, 900), (sorted_by_x, 900)):
        for first, second in zip(ordered, ordered[1:], strict=False):
            dx, dy = abs(second[0] - first[0]), abs(second[1] - first[1])
            aligned = dy < tolerance if ordered is sorted_by_y else dx < tolerance
            distance = math.hypot(second[0] - first[0], second[1] - first[1])
            if aligned or (distance < max(span_x, span_y) * 0.42 and rng.random() < diagonal_probability):
                edges.add(tuple(sorted((first, second))))  # type: ignore[arg-type]
    beam_depth = float(options.get("tie_beam_depth_m", 0.6))
    beam_width = float(options.get("tie_beam_width_m", 0.3))
    for edge_index, (first, second) in enumerate(sorted(edges), start=1):
        a, b = project(first), project(second)
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = max(math.hypot(dx, dy), 1)
        offset_x, offset_y = int(-dy / length * 2.5), int(dx / length * 2.5)
        draw.line((a[0] + offset_x, a[1] + offset_y, b[0] + offset_x, b[1] + offset_y), fill=beam_color, width=primary_width)
        draw.line((a[0] - offset_x, a[1] - offset_y, b[0] - offset_x, b[1] - offset_y), fill=beam_color, width=primary_width)
        if edge_index % 2 == 0:
            midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            draw.multiline_text(
                (midpoint[0] + 4, midpoint[1] - 19),
                f"TB{1 + edge_index % 4}\n{beam_width:.2f}x{beam_depth:.2f}",
                font=note_font,
                fill=ink,
                spacing=0,
            )

    hatch_probability = float(context.get("hatch_probability", 0.34))
    outline_probability = float(context.get("outline_probability", 0.32))
    overlap_probability = float(context.get("footing_overlap_probability", 0.28))
    variation = float(options.get("footing_size_variation", 0.15))
    load_variation = float(options.get("column_load_variation", 0.2))
    hatch_density = float(options.get("hatch_density", 0.65))
    annotation_density = float(context.get("annotation_density", 0.8))
    leader_probability = float(options.get("leader_note_probability", annotation_density))
    revision_probability = float(options.get("revision_cloud_probability", 0.18))
    cloud_drawn = False
    footing_types: dict[tuple[int, int], int] = {}
    for index, (entity, polygon) in enumerate(zip(entities, polygons, strict=False), start=1):
        center_mm = _center(entity)
        center_px = project(center_mm)
        dimensions = entity.get("dimensions_mm", {})
        diameter = float(dimensions.get("diameter") or 350)
        column_span = max(float(dimensions.get("width") or diameter), float(dimensions.get("depth") or diameter))
        load_factor = 1 + rng.uniform(-variation, variation) + rng.uniform(-load_variation, load_variation) * 0.35
        footing_width = column_span * rng.uniform(4.4, 6.2) * load_factor
        footing_depth = column_span * rng.uniform(4.2, 5.9) * load_factor
        if rng.random() < overlap_probability:
            footing_width *= rng.uniform(1.12, 1.3)
        type_key = (round(footing_width / 300), round(footing_depth / 300))
        footing_type = footing_types.setdefault(type_key, len(footing_types) + 1)
        outer = [project(point) for point in _rect(center_mm, footing_width, footing_depth)]
        draw.polygon(outer, fill="#FCFBF7", outline=footing_color, width=max(1, primary_width - 1))
        if rng.random() < hatch_probability:
            _draw_hatch(image, outer, "#B6BABD", spacing=max(5, int(12 - hatch_density * 7)))
        points = [project(point) for point in polygon]
        if rng.random() < outline_probability:
            draw.polygon(points, fill="#FEFDF9", outline="#242A2E", width=2)
        else:
            draw.polygon(points, fill="#3F4549", outline="#242A2E", width=2)
        label = str(entity.get("label", f"C{index}"))
        draw.text((center_px[0] + 5, center_px[1] - 13), label, font=label_font, fill=ink)
        if rng.random() < leader_probability:
            label_x = center_px[0] + (14 if index % 2 else -58)
            label_y = center_px[1] - 45 if index % 3 else center_px[1] + 20
            draw.line((center_px[0], center_px[1], label_x, label_y + 8), fill="#737A7E", width=1)
            footing_text = f"F{footing_type}\n{footing_width / 1000:.2f} x {footing_depth / 1000:.2f}\nT={float(options.get('footing_thickness_m', 0.6)):.2f}"
            draw.multiline_text((label_x, label_y), footing_text, font=note_font, fill=ink, spacing=1)
        if not cloud_drawn and rng.random() < revision_probability:
            xs = [point[0] for point in outer]
            ys = [point[1] for point in outer]
            _revision_cloud(draw, (min(xs) - 9, min(ys) - 9, max(xs) + 9, max(ys) + 9))
            cloud_drawn = True

    # Complete grid dimension chains on all four sides.
    x_pixels = [project((value, min_grid_y))[0] for value in x_values]
    y_pixels = [project((min_grid_x, value))[1] for value in reversed(y_values)]
    x_labels = [f"{abs(second - first):.0f}" for first, second in zip(x_values, x_values[1:], strict=False)]
    reversed_y = list(reversed(y_values))
    y_labels = [f"{abs(second - first):.0f}" for first, second in zip(reversed_y, reversed_y[1:], strict=False)]
    jitter_px = int(float(options.get("dimension_jitter_mm", 75)) / max(span_y, 1) * size[1])
    top_y = project((min_grid_x, max_grid_y + span_y * 0.145))[1] + rng.randint(-jitter_px, jitter_px)
    bottom_y = project((min_grid_x, min_grid_y - span_y * 0.118))[1] + rng.randint(-jitter_px, jitter_px)
    left_x = project((min_grid_x - span_x * 0.14, min_grid_y))[0]
    right_x = project((max_grid_x + span_x * 0.14, min_grid_y))[0]
    _dimension_chain(draw, x_pixels, top_y, x_labels, outward=-1)
    _dimension_chain(draw, y_pixels, left_x, y_labels, vertical=True, outward=1)
    if rng.random() < float(options.get("extra_dimension_probability", 0.6)):
        _dimension_chain(draw, x_pixels, bottom_y, x_labels, outward=1)
        _dimension_chain(draw, y_pixels, right_x, y_labels, vertical=True, outward=-1)
    overall_x = f"{max_grid_x - min_grid_x:.0f}"
    _centered_text(draw, ((x_pixels[0] + x_pixels[-1]) / 2, top_y - 24), overall_x, font=note_font, fill=ink)

    # Bottom sheet furniture makes the preview legible as an engineering deliverable.
    title_y = int(size[1] * 0.925)
    draw.ellipse((38, title_y - 19, 72, title_y + 15), outline="#555C60", width=1)
    _centered_text(draw, (55, title_y - 2), "1", font=_font(14, True), fill=ink)
    draw.text((86, title_y - 18), "FOUNDATION PLAN", font=_font(18, True), fill=ink)
    draw.line((86, title_y + 5, 280, title_y + 5), fill="#555C60", width=1)
    draw.text((86, title_y + 9), "SCALE 1:100  |  ALL DIMENSIONS IN mm", font=note_font, fill=ink)

    notes_x = int(size[0] * 0.48)
    notes_y = title_y - 26
    draw.rectangle((notes_x, notes_y, notes_x + 320, notes_y + 70), outline="#858C91", width=1)
    draw.text((notes_x + 9, notes_y + 7), "GENERAL NOTES", font=label_font, fill=ink)
    notes = [
        f"1. DESIGN CODE: {options.get('design_code', 'ACI 318-19')}",
        f"2. ALLOWABLE SOIL PRESSURE = {float(options.get('soil_bearing_capacity_kpa', 200)):.0f} kPa",
        f"3. FOOTING LEVEL = {float(options.get('footing_bottom_m', -1.8)):.2f} m; EMBEDMENT = {float(options.get('column_embedment_m', 0.6)):.2f} m",
        f"4. MINIMUM CONCRETE COVER = {float(options.get('concrete_cover_m', 0.075)):.3f} m",
    ]
    for line_index, line in enumerate(notes):
        draw.text((notes_x + 9, notes_y + 23 + line_index * 13), line, font=note_font, fill=ink)

    legend_x = int(size[0] * 0.76)
    draw.rectangle((legend_x, notes_y, legend_x + 180, notes_y + 70), outline="#858C91", width=1)
    draw.text((legend_x + 8, notes_y + 7), "LEGEND", font=label_font, fill=ink)
    draw.rectangle((legend_x + 9, notes_y + 27, legend_x + 38, notes_y + 42), outline=footing_color, width=1)
    _draw_hatch(image, [(legend_x + 9, notes_y + 27), (legend_x + 38, notes_y + 27), (legend_x + 38, notes_y + 42), (legend_x + 9, notes_y + 42)], "#B6BABD", 5)
    draw.text((legend_x + 47, notes_y + 27), "ISOLATED FOOTING", font=note_font, fill=ink)
    draw.line((legend_x + 9, notes_y + 55, legend_x + 38, notes_y + 55), fill=beam_color, width=2)
    draw.text((legend_x + 47, notes_y + 49), "TIE BEAM", font=note_font, fill=ink)
    _north_arrow(draw, (size[0] - 62, title_y - 2))

    # Occasional drafting artifacts are controlled but never obscure target geometry.
    if rng.random() < float(options.get("section_callout_probability", 0.35)):
        callout = project(((min_grid_x + max_grid_x) / 2, max_grid_y + span_y * 0.035))
        draw.polygon([(callout[0], callout[1] - 13), (callout[0] - 13, callout[1] + 9), (callout[0] + 13, callout[1] + 9)], outline=ink)
        _centered_text(draw, (callout[0], callout[1] + 2), "A", font=note_font, fill=ink)
        draw.text((callout[0] + 18, callout[1] - 8), "S-301", font=note_font, fill=ink)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, compress_level=1)
    output.with_suffix(output.suffix + ".render.json").write_text(
        json.dumps({"image_size": list(size), "world_bounds_mm": list(bounds), "seed": seed}, indent=2),
        encoding="utf-8",
    )
    return output
