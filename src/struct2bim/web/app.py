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
from struct2bim.exporters import export_dxf, export_ifc, validate_dxf_file, validate_ifc_file
from struct2bim.rendering import BlenderRunner, BlenderToolConfig
from struct2bim.showcase import build_showcase
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
    pixels_per_mm: float = Field(default=0.12, gt=0, le=2.0)
    columns_x: int = Field(default=4, ge=2, le=12)
    columns_y: int = Field(default=3, ge=2, le=12)
    spacing_x_mm: float = Field(default=4000, ge=500, le=20000)
    spacing_y_mm: float = Field(default=4500, ge=500, le=20000)
    storey_height_mm: float = Field(default=3200, ge=1000, le=10000)
    irregularity_ratio: float = Field(default=0.12, ge=0, le=0.25)

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


def _runner(root: Path) -> BlenderRunner:
    return BlenderRunner(BlenderToolConfig.discover(root), root)


def _safe_output(root: Path, *parts: str) -> Path:
    output_root = (root / "outputs" / "gui").resolve()
    output = output_root.joinpath(*parts).resolve()
    if output != output_root and output_root not in output.parents:
        raise ValueError("output path escapes the project output directory")
    return output


def _build_preview(root: Path, parameters: GeneratorParameters) -> dict[str, object]:
    output = _safe_output(root, "previews", parameters.output_name)
    scene = generate_reference_scene(parameters.seed, parameters.scene_config())
    output.mkdir(parents=True, exist_ok=True)
    scene_path = output / "structural_scene.json"
    scene_path.write_text(scene.canonical_json(), encoding="utf-8", newline="\n")
    dxf_path = export_dxf(scene, output / "model.dxf")
    ifc_path = export_ifc(scene, output / "model.ifc")
    artifacts = build_showcase(scene, ifc_path, output, _runner(root), seed=parameters.seed)
    return {
        "message": "Preview generated",
        "entities": len(scene.entities),
        "layout": parameters.layout_modes[0],
        "drawing": f"/outputs/gui/previews/{parameters.output_name}/{artifacts.drawing.name}",
        "labels": f"/outputs/gui/previews/{parameters.output_name}/{artifacts.annotation.name}",
        "ifc_render": f"/outputs/gui/previews/{parameters.output_name}/{artifacts.ifc_render.name}",
        "pipeline": f"/outputs/gui/previews/{parameters.output_name}/{artifacts.hero.name}",
        "ifc_valid": validate_ifc_file(ifc_path, scene).is_valid,
        "dxf_valid": validate_dxf_file(dxf_path, scene).is_valid,
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
