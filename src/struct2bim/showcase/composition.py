"""Compose generated project artifacts into truthful README visuals."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps

_INK = "#17232E"
_MUTED = "#5D6B78"
_BLUE = "#2563A6"
_AMBER = "#D97706"
_PANEL = "#FFFFFF"
_BACKGROUND = "#EDF2F6"


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)


def compose_pipeline_hero(
    drawing: Path,
    annotation: Path,
    geometry: Path,
    ifc_render: Path,
    output: Path,
) -> Path:
    """Create the canonical four-stage README hero from generated artifacts."""
    width, height = 2400, 760
    canvas = Image.new("RGB", (width, height), _BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.text((70, 34), "STRUCTURAL DRAWING  >  TRAINING DATA  >  BIM / IFC", font=_font(42, True), fill=_INK)
    draw.text(
        (70, 88),
        "Reproducible synthetic ground-truth pipeline",
        font=_font(25),
        fill=_MUTED,
    )
    panels = [drawing, annotation, geometry, ifc_render]
    titles = [
        "1  SYNTHETIC DRAWING",
        "2  GROUND-TRUTH LABELS",
        "3  NORMALIZED GEOMETRY",
        "4  RENDERED IFC MODEL",
    ]
    panel_w, panel_h, gap, start_x, top = 535, 465, 42, 70, 170
    for index, (path, title) in enumerate(zip(panels, titles, strict=True)):
        x = start_x + index * (panel_w + gap)
        draw.rounded_rectangle((x, top, x + panel_w, top + panel_h + 68), radius=16, fill=_PANEL, outline="#D7E0E8", width=2)
        canvas.paste(_fit(Image.open(path), (panel_w, panel_h)), (x, top))
        draw.text((x + 18, top + panel_h + 18), title, font=_font(20, True), fill=_INK)
        if index < 3:
            arrow_x = x + panel_w + gap // 2
            draw.polygon([(arrow_x - 8, top + 220), (arrow_x + 12, top + 235), (arrow_x - 8, top + 250)], fill=_BLUE)
    badge = "SYNTHETIC GROUND TRUTH - NO MODEL PREDICTIONS SHOWN"
    badge_font = _font(20, True)
    bounds = draw.textbbox((0, 0), badge, font=badge_font)
    badge_w = bounds[2] - bounds[0]
    draw.rounded_rectangle((70, 700, 110 + badge_w, 742), radius=8, fill=_AMBER)
    draw.text((90, 709), badge, font=badge_font, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    return output


def compose_variation_gallery(
    images: Sequence[Path], output: Path, *, title: str = "Synthetic curriculum variations"
) -> Path:
    """Create a labeled contact sheet from actual generated drawing variations."""
    if not images:
        raise ValueError("at least one generated image is required")
    columns = min(3, len(images))
    rows = (len(images) + columns - 1) // columns
    cell_w, cell_h = 520, 390
    canvas = Image.new("RGB", (columns * cell_w + 80, rows * cell_h + 150), _BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 28), title, font=_font(36, True), fill=_INK)
    draw.text((40, 76), "Generated examples - synthetic ground truth", font=_font(21), fill=_MUTED)
    for index, path in enumerate(images):
        col, row = index % columns, index // columns
        x, y = 40 + col * cell_w, 125 + row * cell_h
        canvas.paste(_fit(Image.open(path), (480, 330)), (x, y))
        draw.text((x, y + 340), f"Variation {index + 1:02d}", font=_font(18, True), fill=_INK)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    return output
