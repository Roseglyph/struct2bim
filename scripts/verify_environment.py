"""Verify the local non-training development environment."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path


IMPORTS = {
    "albumentations": "albumentations",
    "ezdxf": "ezdxf",
    "FastAPI": "fastapi",
    "ifcopenshell": "ifcopenshell",
    "networkx": "networkx",
    "numpy": "numpy",
    "OpenCV": "cv2",
    "Pillow": "PIL",
    "pydantic": "pydantic",
    "PyMuPDF": "fitz",
    "PyYAML": "yaml",
    "rich": "rich",
    "shapely": "shapely",
    "typer": "typer",
    "Uvicorn": "uvicorn",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("XDG_CACHE_HOME", str(project_root() / ".cache"))


def verify_imports() -> list[str]:
    failures: list[str] = []
    for label, module_name in IMPORTS.items():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - environment diagnostic
            failures.append(f"{label}: {exc}")
    return failures


def verify_blender() -> str:
    executable = project_root() / ".tools" / "blender-4.2.0-windows-x64" / "blender.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"Portable Blender was not found: {executable}")

    result = subprocess.run(
        [
            str(executable),
            "--factory-startup",
            "--background",
            "--python-expr",
            "print('STRUCT2BIM_BLENDER_OK')",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if "STRUCT2BIM_BLENDER_OK" not in result.stdout:
        raise RuntimeError("Blender verification marker was not returned")
    return result.stdout.splitlines()[0]


def main() -> int:
    failures = verify_imports()
    if failures:
        print("Dependency verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Python: {sys.version.split()[0]}")
    print(verify_blender())
    print("Non-training environment verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
