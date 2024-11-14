"""Orchestrate generation of a consistent public showcase asset set."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from struct2bim.rendering.blender_runner import BlenderRunner
from struct2bim.rendering.ifc_manifest import build_ifc_render_manifest
from struct2bim.rendering.previews import render_annotation_preview, render_geometry_preview
from struct2bim.showcase.composition import compose_pipeline_hero


@dataclass(frozen=True)
class ShowcaseArtifacts:
    drawing: Path
    annotation: Path
    geometry: Path
    ifc_render: Path
    hero: Path
    manifest: Path


def _write_scene(scene: Path | dict[str, Any] | Any, destination: Path) -> Path:
    if isinstance(scene, Path):
        return scene
    if hasattr(scene, "canonical_json"):
        payload = scene.canonical_json()
    else:
        payload = json.dumps(scene, indent=2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")
    return destination


def build_showcase(
    scene: Path | dict[str, Any] | Any,
    ifc_path: Path,
    output_directory: Path,
    runner: BlenderRunner,
    *,
    seed: int = 24017,
) -> ShowcaseArtifacts:
    """Build all hero stages from one canonical scene and its corresponding IFC."""
    output_directory.mkdir(parents=True, exist_ok=True)
    scene_path = _write_scene(scene, output_directory / "canonical_scene.json")
    drawing = output_directory / "structural_drawing.png"
    annotation = output_directory / "annotation_ground_truth.png"
    geometry = output_directory / "normalized_geometry.png"
    ifc_manifest = output_directory / "ifc_render_manifest.json"
    ifc_render = output_directory / "ifc_isometric.png"
    hero = output_directory / "pipeline_overview.png"
    runner.render_clean_drawing(scene_path, drawing, seed=seed)
    render_annotation_preview(scene_path, drawing, annotation)
    render_geometry_preview(scene_path, geometry)
    build_ifc_render_manifest(ifc_path, ifc_manifest)
    runner.render_ifc_manifest(ifc_manifest, ifc_render, seed=seed)
    compose_pipeline_hero(drawing, annotation, geometry, ifc_render, hero)
    manifest = {
        "seed": seed,
        "provenance": "synthetic_ground_truth",
        "model_predictions_included": False,
        "artifacts": {
            "drawing": drawing.name,
            "annotation": annotation.name,
            "geometry": geometry.name,
            "ifc_render": ifc_render.name,
            "hero": hero.name,
        },
    }
    manifest_path = output_directory / "showcase_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return ShowcaseArtifacts(drawing, annotation, geometry, ifc_render, hero, manifest_path)
