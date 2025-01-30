"""Check the repository's public artifacts and release constraints."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

from struct2bim.exporters import validate_dxf_file, validate_ifc_file


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "docs/assets/workflow_diagram.png",
    "docs/assets/foundation-drawing.png",
    "docs/assets/foundation-annotations.png",
    "docs/assets/foundation-ifc.png",
    "docs/assets/pipeline_overview.png",
    "docs/assets/dataset_alignment_preview.png",
    "examples/reference/model.ifc",
    "examples/reference/model.dxf",
    "examples/reference/structural_scene.json",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
)
FORBIDDEN_CONTENT = (
    re.compile(r"late[ -]?2024", re.IGNORECASE),
    re.compile(r"2024-12-31"),
    re.compile(r"exclude-newer", re.IGNORECASE),
    re.compile(r"C:\\dev", re.IGNORECASE),
    re.compile(r"SSJ Rose", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
)
TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".json", ".txt", ".ps1"}
WEIGHT_SUFFIXES = {".pt", ".pth", ".onnx", ".ckpt", ".safetensors"}
CANONICAL_PORTFOLIO_ASSETS = (
    "docs/assets/foundation-drawing.png",
    "docs/assets/foundation-annotations.png",
    "docs/assets/foundation-ifc.png",
)
LEGACY_PORTFOLIO_ASSETS = (
    "docs/assets/generator-interface.png",
    "docs/assets/workspace_drawing.png",
    "docs/assets/workspace_annotations.png",
    "docs/assets/workspace-ifc-scene.png",
    "docs/assets/workspace-annotations-interface.png",
    "docs/assets/workspace-ifc-interface.png",
)


def tracked_files() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return tuple(ROOT / line for line in result.stdout.splitlines() if line)


def main() -> int:
    failures: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            failures.append(f"missing required portfolio artifact: {relative}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for relative in CANONICAL_PORTFOLIO_ASSETS:
        if relative not in readme:
            failures.append(f"README does not reference canonical portfolio asset: {relative}")
    for relative in LEGACY_PORTFOLIO_ASSETS:
        if (ROOT / relative).exists() or relative in readme:
            failures.append(f"legacy portfolio asset is still present or referenced: {relative}")
    for path in tracked_files():
        if not path.exists():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in WEIGHT_SUFFIXES:
            failures.append(f"tracked model weight is not allowed: {relative}")
        if path.stat().st_size > 5 * 1024 * 1024:
            failures.append(f"tracked file exceeds 5 MiB: {relative}")
        if path.suffix.lower() in TEXT_SUFFIXES and path.name != "release_audit.py":
            contents = path.read_text(encoding="utf-8", errors="replace")
            for pattern in FORBIDDEN_CONTENT:
                if pattern.search(contents):
                    failures.append(f"forbidden private/secret pattern in {relative}")
                    break
    for asset in (
        "workflow_diagram.png",
        "foundation-drawing.png",
        "foundation-annotations.png",
        "foundation-ifc.png",
        "pipeline_overview.png",
        "dataset_alignment_preview.png",
    ):
        with Image.open(ROOT / "docs" / "assets" / asset) as image:
            if image.width < 1200 or image.height < 500:
                failures.append(f"portfolio image is unexpectedly small: {asset}")
    for asset in ("foundation-drawing.png", "foundation-annotations.png"):
        with Image.open(ROOT / "docs" / "assets" / asset) as image:
            if image.size != (1334, 1900):
                failures.append(f"sheet asset is not the expected chrome-free render: {asset}")
            pixels = image.convert("RGB").resize((320, 456)).getdata()
            green = sum(
                1 for red, value, blue in pixels if value > 150 and red < 100 and blue < 160
            )
            cyan = sum(
                1 for red, value, blue in pixels if blue > 150 and value > 120 and red < 100
            )
            pink = sum(
                1 for red, value, blue in pixels if red > 180 and blue > 100 and value < 190
            )
            if min(green, cyan, pink) < 25:
                failures.append(f"sheet asset is missing expected CAD color layers: {asset}")
    preview_root = ROOT / "outputs" / "gui" / "previews" / "reference_dataset"
    for source_name, asset_name in (
        ("drawing.png", "foundation-drawing.png"),
        ("annotations.png", "foundation-annotations.png"),
    ):
        preview_source = preview_root / source_name
        portfolio_asset = ROOT / "docs" / "assets" / asset_name
        if preview_source.is_file() and preview_source.read_bytes() != portfolio_asset.read_bytes():
            failures.append(f"portfolio asset does not match the latest generated preview: {asset_name}")
    if not validate_ifc_file(ROOT / "examples" / "reference" / "model.ifc").is_valid:
        failures.append("committed IFC example failed reopen validation")
    if not validate_dxf_file(ROOT / "examples" / "reference" / "model.dxf").is_valid:
        failures.append("committed DXF example failed reopen validation")
    remotes = subprocess.run(
        ["git", "remote"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    if remotes:
        failures.append("repository must remain local-only: Git remote is configured")
    if failures:
        print("Release audit failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Release audit passed: artifacts, formats, privacy, size, and local-only policy verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
