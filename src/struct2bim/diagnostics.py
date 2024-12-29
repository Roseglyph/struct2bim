"""Machine-readable readiness diagnostics for local portfolio use."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pydantic import BaseModel

from struct2bim.exporters import validate_dxf_file, validate_ifc_file
from struct2bim.rendering import BlenderToolConfig


class DiagnosticReport(BaseModel):
    ready: bool
    python: str
    blender: str | None
    base_dependencies: dict[str, bool]
    optional_training_dependencies: dict[str, bool]
    example_ifc_valid: bool
    example_dxf_valid: bool
    notes: tuple[str, ...]


def diagnose(project_root: Path) -> DiagnosticReport:
    """Check the local base runtime without downloading or installing anything."""
    modules = {
        "OpenCV": "cv2",
        "IfcOpenShell": "ifcopenshell",
        "Pillow": "PIL",
        "PyMuPDF": "fitz",
        "Pydantic": "pydantic",
        "ezdxf": "ezdxf",
    }
    base = {label: importlib.util.find_spec(module) is not None for label, module in modules.items()}
    optional = {
        "torch": importlib.util.find_spec("torch") is not None,
        "ultralytics": importlib.util.find_spec("ultralytics") is not None,
    }
    notes: list[str] = []
    try:
        blender = str(BlenderToolConfig.discover(project_root).executable)
    except FileNotFoundError as exc:
        blender = None
        notes.append(str(exc))
    example_root = project_root / "examples" / "reference"
    ifc_valid = validate_ifc_file(example_root / "model.ifc").is_valid
    dxf_valid = validate_dxf_file(example_root / "model.dxf").is_valid
    if not all(optional.values()):
        notes.append("Optional training dependencies are not installed; base workflows remain available")
    ready = sys.version_info[:2] == (3, 11) and all(base.values()) and blender is not None
    ready = ready and ifc_valid and dxf_valid
    return DiagnosticReport(
        ready=ready,
        python=sys.version.split()[0],
        blender=blender,
        base_dependencies=base,
        optional_training_dependencies=optional,
        example_ifc_valid=ifc_valid,
        example_dxf_valid=dxf_valid,
        notes=tuple(notes),
    )
