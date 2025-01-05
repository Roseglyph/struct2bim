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
    "docs/assets/generator-interface.png",
    "docs/assets/workflow_diagram.png",
    "docs/assets/workspace_drawing.png",
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
    for path in tracked_files():
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
        "generator-interface.png",
        "workflow_diagram.png",
        "workspace_drawing.png",
        "pipeline_overview.png",
        "dataset_alignment_preview.png",
    ):
        with Image.open(ROOT / "docs" / "assets" / asset) as image:
            if image.width < 1200 or image.height < 500:
                failures.append(f"portfolio image is unexpectedly small: {asset}")
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
