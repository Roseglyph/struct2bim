"""FastAPI application for configuring and running Struct2BIM generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from struct2bim.application import DatasetBuildConfig, build_dataset
from struct2bim.augmentation import AugmentationProfile
from struct2bim.curriculum import ReferenceSceneConfig, generate_reference_scene
from struct2bim.rendering import (
    BlenderRunner,
    BlenderToolConfig,
    render_annotation_preview,
    render_geometry_preview,
)
from struct2bim.validation import validate_dataset


LayoutMode = Literal["isolated", "regular", "irregular"]


class GeneratorParameters(BaseModel):
    project_name: str = Field(default="struct2bim_reference", min_length=1, max_length=80)
    output_name: str = Field(default="reference_dataset", min_length=1, max_length=50)
    seed: int = 24017
    scene_seed_start: int = 1000
    scene_count: int = Field(default=12, ge=3, le=500)
    layout_modes: tuple[LayoutMode, ...] = ("isolated", "regular", "irregular")
    variants: tuple[AugmentationProfile, ...] = (
        AugmentationProfile.CLEAN,
        AugmentationProfile.SCAN,
        AugmentationProfile.PERSPECTIVE_PHOTO,
    )
    canvas_width_px: int = Field(default=2048, ge=512, le=8192)
    canvas_height_px: int = Field(default=2048, ge=512, le=8192)
    pixels_per_mm: float = Field(default=0.075, gt=0, le=2.0)
    columns_x: int = Field(default=5, ge=2, le=12)
    columns_y: int = Field(default=6, ge=2, le=12)
    spacing_x_mm: float = Field(default=3600, ge=500, le=20000)
    spacing_y_mm: float = Field(default=3900, ge=500, le=20000)
    storey_height_mm: float = Field(default=3200, ge=1000, le=10000)
    irregularity_ratio: float = Field(default=0.12, ge=0, le=0.25)
    drawing_complexity: float = Field(default=0.78, ge=0, le=1)
    rotation_probability: float = Field(default=0.38, ge=0, le=1)
    hatch_probability: float = Field(default=0.34, ge=0, le=1)
    footing_overlap_probability: float = Field(default=0.28, ge=0, le=1)
    diagonal_beam_probability: float = Field(default=0.24, ge=0, le=1)
    occupancy_probability: float = Field(default=0.78, gt=0, le=1)
    building_outline: Literal["rectangular", "irregular_polygon"] = "irregular_polygon"
    foundation_type: Literal["isolated_tie_beams"] = "isolated_tie_beams"
    footing_bottom_m: float = Field(default=-1.8, ge=-10, le=0)
    column_embedment_m: float = Field(default=0.6, ge=0.1, le=3)
    footing_thickness_m: float = Field(default=0.6, ge=0.2, le=3)
    tie_beam_width_m: float = Field(default=0.3, ge=0.15, le=1.5)
    tie_beam_depth_m: float = Field(default=0.6, ge=0.2, le=2)
    concrete_cover_m: float = Field(default=0.075, ge=0.02, le=0.2)
    design_code: Literal["ACI 318-19", "ECP 203-2020"] = "ACI 318-19"
    soil_bearing_capacity_kpa: float = Field(default=200, ge=50, le=1000)
    column_load_variation: float = Field(default=0.2, ge=0, le=0.8)
    footing_size_variation: float = Field(default=0.15, ge=0, le=0.8)
    hatch_density: float = Field(default=0.65, ge=0, le=1)
    lineweight_variation: float = Field(default=0.35, ge=0, le=1)
    dimension_jitter_mm: float = Field(default=75, ge=0, le=500)
    extra_dimension_probability: float = Field(default=0.6, ge=0, le=1)
    leader_note_probability: float = Field(default=0.55, ge=0, le=1)
    revision_cloud_probability: float = Field(default=0.18, ge=0, le=1)
    section_callout_probability: float = Field(default=0.35, ge=0, le=1)

    @field_validator("output_name")
    @classmethod
    def validate_output_name(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value) is None:
            raise ValueError("output name may contain letters, numbers, underscores, and hyphens")
        return value

    @field_validator("layout_modes", "variants")
    @classmethod
    def require_choices(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if not value:
            raise ValueError("select at least one option")
        return value

    def scene_config(self, *, layout_mode: LayoutMode | None = None) -> ReferenceSceneConfig:
        return ReferenceSceneConfig(
            project_name=self.project_name,
            canvas_width_px=self.canvas_width_px,
            canvas_height_px=self.canvas_height_px,
            pixels_per_mm=self.pixels_per_mm,
            columns_x=self.columns_x,
            columns_y=self.columns_y,
            spacing_x_mm=self.spacing_x_mm,
            spacing_y_mm=self.spacing_y_mm,
            storey_height_mm=self.storey_height_mm,
            irregularity_ratio=self.irregularity_ratio,
            drawing_complexity=self.drawing_complexity,
            rotation_probability=self.rotation_probability,
            hatch_probability=self.hatch_probability,
            footing_overlap_probability=self.footing_overlap_probability,
            diagonal_beam_probability=self.diagonal_beam_probability,
            occupancy_probability=self.occupancy_probability,
            layout_mode=layout_mode or self.layout_modes[0],
        )

    def build_config(self) -> DatasetBuildConfig:
        return DatasetBuildConfig(
            project_seed=self.seed,
            scene_seed_start=self.scene_seed_start,
            scene_count=self.scene_count,
            variants=self.variants,
            layout_modes=self.layout_modes,
            scene=self.scene_config(layout_mode="regular"),
        )

    def preview_options(self) -> dict[str, object]:
        """Return drafting controls used by the fast sheet renderer."""
        return {
            "building_outline": self.building_outline,
            "foundation_type": self.foundation_type,
            "footing_bottom_m": self.footing_bottom_m,
            "column_embedment_m": self.column_embedment_m,
            "footing_thickness_m": self.footing_thickness_m,
            "tie_beam_width_m": self.tie_beam_width_m,
            "tie_beam_depth_m": self.tie_beam_depth_m,
            "concrete_cover_m": self.concrete_cover_m,
            "design_code": self.design_code,
            "soil_bearing_capacity_kpa": self.soil_bearing_capacity_kpa,
            "column_load_variation": self.column_load_variation,
            "footing_size_variation": self.footing_size_variation,
            "hatch_density": self.hatch_density,
            "lineweight_variation": self.lineweight_variation,
            "dimension_jitter_mm": self.dimension_jitter_mm,
            "extra_dimension_probability": self.extra_dimension_probability,
            "leader_note_probability": self.leader_note_probability,
            "revision_cloud_probability": self.revision_cloud_probability,
            "section_callout_probability": self.section_callout_probability,
        }


def _runner(root: Path) -> BlenderRunner:
    return BlenderRunner(BlenderToolConfig.discover(root), root)


def _safe_output(root: Path, *parts: str) -> Path:
    output_root = (root / "outputs" / "gui").resolve()
    output = output_root.joinpath(*parts).resolve()
    if output != output_root and output_root not in output.parents:
        raise ValueError("output path escapes the project output directory")
    return output


def _interactive_model(scene: object) -> dict[str, object]:
    """Return the compact metric geometry used by the browser's 3D viewer."""
    data = scene.model_dump(mode="json")  # type: ignore[attr-defined]
    columns: list[dict[str, object]] = []
    for entity in data["entities"]:
        if entity.get("type", "column") != "column":
            continue
        dimensions = entity["dimensions_mm"]
        diameter = dimensions.get("diameter") or 350
        columns.append(
            {
                "id": entity["id"],
                "label": entity.get("label", entity["id"]),
                "x": entity["center_mm"]["x"],
                "y": entity["center_mm"]["y"],
                "width": dimensions.get("width") or diameter,
                "depth": dimensions.get("depth") or diameter,
                "height": dimensions["height"],
                "rotation": entity.get("rotation_deg", 0),
                "shape": entity.get("subtype", "rectangular"),
            }
        )
    grids = [
        {
            "label": axis["label"],
            "start": [axis["start_mm"]["x"], axis["start_mm"]["y"]],
            "end": [axis["end_mm"]["x"], axis["end_mm"]["y"]],
        }
        for axis in data["grids"]
    ]
    return {"units": "mm", "columns": columns, "grids": grids}


def _build_preview(root: Path, parameters: GeneratorParameters) -> dict[str, object]:
    output = _safe_output(root, "previews", parameters.output_name)
    scene = generate_reference_scene(parameters.seed, parameters.scene_config(layout_mode="irregular"))
    output.mkdir(parents=True, exist_ok=True)
    scene_path = output / "structural_scene.json"
    scene_path.write_text(scene.canonical_json(), encoding="utf-8", newline="\n")
    preview_scene = scene.model_dump()
    preview_scene["preview_options"] = parameters.preview_options()
    drawing = render_geometry_preview(preview_scene, output / "drawing.png", size=(1400, 900))
    annotation = render_annotation_preview(scene.model_dump(), drawing, output / "annotations.png")
    return {
        "message": "Fast preview generated",
        "entities": len(scene.entities),
        "layout": "automatic irregular",
        "drawing": f"/outputs/gui/previews/{parameters.output_name}/{drawing.name}",
        "labels": f"/outputs/gui/previews/{parameters.output_name}/{annotation.name}",
        "ifc_render": "/portfolio/ifc_isometric.png",
        "exchange_status": "validated during full generation",
        "seed": parameters.seed,
        "model": _interactive_model(scene),
    }


def _build_full_dataset(root: Path, parameters: GeneratorParameters) -> dict[str, object]:
    output = _safe_output(root, "datasets", parameters.output_name)
    result = build_dataset(parameters.build_config(), output, _runner(root))
    validation = validate_dataset(result.root)
    return {
        "message": "Dataset generated and validated",
        "sample_count": result.sample_count,
        "split_counts": validation.split_counts,
        "manifest": f"/outputs/gui/datasets/{parameters.output_name}/manifest.json",
        "validation_report": f"/outputs/gui/datasets/{parameters.output_name}/validation_report.json",
    }


def create_app(project_root: Path | None = None) -> FastAPI:
    root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    static = root / "src" / "struct2bim" / "web" / "static"
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Struct2BIM", version="0.1.0")
    app.mount("/static", StaticFiles(directory=static), name="static")
    app.mount("/outputs", StaticFiles(directory=outputs), name="outputs")
    app.mount("/portfolio", StaticFiles(directory=root / "docs" / "assets"), name="portfolio")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/api/defaults")
    def defaults() -> dict[str, object]:
        return json.loads(GeneratorParameters().model_dump_json())  # type: ignore[no-any-return]

    @app.post("/api/preview")
    async def preview(parameters: GeneratorParameters) -> dict[str, object]:
        try:
            return await run_in_threadpool(_build_preview, root, parameters)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/generate")
    async def generate(parameters: GeneratorParameters) -> dict[str, object]:
        try:
            return await run_in_threadpool(_build_full_dataset, root, parameters)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def run_server(project_root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run(create_app(project_root), host=host, port=port, log_level="info")
