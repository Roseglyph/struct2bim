"""Convert IFC tessellation into a Blender-independent render manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_ifc_render_manifest(ifc_path: Path, output: Path) -> Path:
    """Tessellate visible IFC products and write a portable mesh manifest."""
    try:
        import ifcopenshell
        import ifcopenshell.geom
    except ImportError as error:  # pragma: no cover - installation failure path
        raise RuntimeError("IfcOpenShell is required to prepare an IFC render") from error

    model = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    meshes: list[dict[str, Any]] = []
    for product in model.by_type("IfcProduct"):
        if product.is_a() in {"IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcGrid"}:
            continue
        if getattr(product, "Representation", None) is None:
            continue
        try:
            shape = ifcopenshell.geom.create_shape(settings, product)
        except RuntimeError:
            continue
        vertices = list(shape.geometry.verts)
        faces = list(shape.geometry.faces)
        meshes.append(
            {
                "id": product.GlobalId,
                "name": product.Name or product.is_a(),
                "ifc_type": product.is_a(),
                "vertices": [vertices[index : index + 3] for index in range(0, len(vertices), 3)],
                "faces": [faces[index : index + 3] for index in range(0, len(faces), 3)],
            }
        )
    manifest = {
        "schema_version": "1.0",
        "source": str(ifc_path.name),
        "coordinate_units": "metres",
        "meshes": meshes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output
