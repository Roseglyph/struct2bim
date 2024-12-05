"""Visual QA contact sheets produced from generated YOLO labels."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from struct2bim.curriculum.manifest import DatasetManifest


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def render_dataset_preview(dataset: Path, output: Path, *, limit: int = 6) -> Path:
    """Overlay manifest-linked segmentation labels for human alignment review."""
    manifest = DatasetManifest.model_validate_json(
        (dataset / "manifest.json").read_text(encoding="utf-8")
    )
    samples = manifest.samples[:limit]
    if not samples:
        raise ValueError("dataset manifest contains no samples")
    cell_w, cell_h = 560, 430
    columns = min(3, len(samples))
    rows = (len(samples) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_w + 60, rows * cell_h + 130), "#EDF2F6")
    draw = ImageDraw.Draw(canvas)
    draw.text((30, 22), "Generated dataset alignment preview", font=_font(34, True), fill="#17232E")
    draw.text((30, 68), "YOLO segmentation labels - synthetic ground truth", font=_font(20), fill="#5D6B78")
    for index, sample in enumerate(samples):
        source = Image.open(dataset / sample.image_path).convert("RGB")
        source_draw = ImageDraw.Draw(source, "RGBA")
        label_path = dataset / sample.segmentation_label_path
        for line in label_path.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            coordinates = [float(value) for value in fields[1:]]
            points = [
                (coordinates[offset] * source.width, coordinates[offset + 1] * source.height)
                for offset in range(0, len(coordinates), 2)
            ]
            source_draw.polygon(
                points, fill=(217, 119, 6, 72), outline=(217, 119, 6, 255), width=3
            )
        fitted = ImageOps.contain(source, (520, 340), method=Image.Resampling.LANCZOS)
        x = 30 + (index % columns) * cell_w
        y = 110 + (index // columns) * cell_h
        canvas.paste(fitted, (x + (520 - fitted.width) // 2, y))
        draw.text(
            (x, y + 350),
            f"{sample.sample_id}  |  {sample.split.value}",
            font=_font(17, True),
            fill="#17232E",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    return output
