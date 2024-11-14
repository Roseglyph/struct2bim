"""Lightweight, deterministic annotation and geometry preview rendering."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

_BLUE = "#2563A6"
_GREEN = "#16845B"
_AMBER = "#D97706"
_CHARCOAL = "#19232D"


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _load_scene(scene: Path | dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(scene, Path):
        return json.loads(scene.read_text(encoding="utf-8"))
    if hasattr(scene, "canonical_json"):
        return json.loads(scene.canonical_json())
    return scene


def _entities(scene: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return scene.get("entities", scene.get("structural_entities", []))


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


def _projector(bounds: tuple[float, float, float, float], size: tuple[int, int]):
    min_x, min_y, max_x, max_y = bounds
    width, height = size
    usable_w, usable_h = width - 80, height - 110
    scale = min(usable_w / max(max_x - min_x, 1), usable_h / max(max_y - min_y, 1))

    def project(point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        return int(40 + (x - min_x) * scale), int(height - 45 - (y - min_y) * scale)

    return project


def _camera_projector(bounds: tuple[float, float, float, float], size: tuple[int, int]):
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
    image.save(output, optimize=True)
    return output


def render_geometry_preview(
    scene: Path | dict[str, Any], output: Path, *, size: tuple[int, int] = (1200, 900)
) -> Path:
    """Render normalized metric geometry without requiring Blender."""
    data = _load_scene(scene)
    image = Image.new("RGB", size, "#F7F9FB")
    draw = ImageDraw.Draw(image)
    entities = list(_entities(data))
    polygons = [_column_polygon(entity) for entity in entities]
    project = _projector(_bounds(polygons), size)
    # A restrained metric grid makes the normalized coordinate space explicit.
    for x in range(60, size[0] - 20, 100):
        draw.line((x, 70, x, size[1] - 35), fill="#E3E9EF", width=1)
    for y in range(70, size[1] - 20, 100):
        draw.line((40, y, size[0] - 35, y), fill="#E3E9EF", width=1)
    font = _font(19, bold=True)
    for entity, polygon in zip(entities, polygons, strict=False):
        points = [project(point) for point in polygon]
        draw.polygon(points, fill="#D9F1E7", outline=_GREEN, width=4)
        center = project(_center(entity))
        label = str(entity.get("label", entity.get("classification", {}).get("label", entity.get("id", "column"))))
        draw.ellipse((center[0] - 4, center[1] - 4, center[0] + 4, center[1] + 4), fill=_GREEN)
        draw.text((center[0] + 9, center[1] - 13), label, font=font, fill=_CHARCOAL)
    draw.text((28, size[1] - 34), "Normalized structural geometry - millimetres", font=_font(17), fill="#52616F")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    return output
