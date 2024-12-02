"""Supplied-checkpoint inference and calibrated prediction conversion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field

from struct2bim.domain import (
    ColumnDimensions,
    ColumnShape,
    CoordinateTransform,
    Point2D,
    Provenance,
    ScaleSource,
    SceneProject,
    SceneSource,
    SourceType,
    Storey,
    StructuralEntity,
    StructuralScene,
)
from struct2bim.inputs import prepare_document
from struct2bim.training.runner import _require_ultralytics


class Prediction(BaseModel):
    class_id: int
    class_name: str
    confidence: float = Field(ge=0, le=1)
    polygon_px: tuple[tuple[float, float], ...]


class PredictionPage(BaseModel):
    image: str
    width_px: int
    height_px: int
    predictions: tuple[Prediction, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_predictions(result: Any) -> tuple[Prediction, ...]:
    names = result.names
    boxes = result.boxes
    class_ids = boxes.cls.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    polygons: list[Any]
    if getattr(result, "masks", None) is not None:
        polygons = result.masks.xy
    elif getattr(result, "obb", None) is not None:
        polygons = result.obb.xyxyxyxy.cpu().tolist()
    else:
        polygons = []
        for x1, y1, x2, y2 in boxes.xyxy.cpu().tolist():
            polygons.append(((x1, y1), (x2, y1), (x2, y2), (x1, y2)))
    return tuple(
        Prediction(
            class_id=int(class_id),
            class_name=str(names[int(class_id)]),
            confidence=float(confidence),
            polygon_px=tuple((float(point[0]), float(point[1])) for point in polygon),
        )
        for class_id, confidence, polygon in zip(class_ids, confidences, polygons, strict=True)
    )


def _canonical_scene(
    page: PredictionPage,
    *,
    millimetres_per_pixel: float,
    storey_height_mm: float,
    checkpoint: Path,
) -> StructuralScene:
    entities: list[StructuralEntity] = []
    for index, prediction in enumerate(page.predictions, 1):
        points = cv2.convexHull(np.asarray(prediction.polygon_px, dtype=np.float32))
        (center_x, center_y), (width, depth), angle = cv2.minAreaRect(points)
        center = Point2D(
            x=center_x * millimetres_per_pixel,
            y=(page.height_px - center_y) * millimetres_per_pixel,
        )
        is_circle = prediction.class_id == 1 or "circular" in prediction.class_name.lower()
        dimensions = (
            ColumnDimensions(
                diameter=max(width, depth) * millimetres_per_pixel,
                height=storey_height_mm,
            )
            if is_circle
            else ColumnDimensions(
                width=max(width, 1.0) * millimetres_per_pixel,
                depth=max(depth, 1.0) * millimetres_per_pixel,
                height=storey_height_mm,
            )
        )
        entities.append(
            StructuralEntity(
                id=f"PRED-COL-{index:03d}",
                subtype=ColumnShape.CIRCULAR if is_circle else ColumnShape.RECTANGULAR,
                storey_id="L01",
                center_mm=center,
                dimensions_mm=dimensions,
                rotation_deg=0.0 if is_circle else float(angle),
                label=f"C{index}",
                class_id=prediction.class_id,
                provenance=Provenance(
                    source=SourceType.MODEL_PREDICTION,
                    confidence=prediction.confidence,
                    checkpoint=checkpoint.name,
                ),
            )
        )
    return StructuralScene(
        project=SceneProject(name=f"Struct2BIM inference - {Path(page.image).stem}"),
        source=SceneSource(
            type=SourceType.MODEL_PREDICTION,
            image=page.image,
            width_px=page.width_px,
            height_px=page.height_px,
            scene_seed=0,
        ),
        transform=CoordinateTransform(
            pixels_per_mm=1.0 / millimetres_per_pixel,
            origin_px=Point2D(x=0, y=page.height_px),
        ),
        scale_source=ScaleSource.MANUAL_CALIBRATION,
        storeys=(Storey(id="L01", name="Detected Storey", elevation_mm=0, height_mm=storey_height_mm),),
        entities=tuple(entities),
    )


def run_inference(
    source: Path,
    weights: Path,
    output: Path,
    *,
    confidence: float = 0.25,
    millimetres_per_pixel: float | None = None,
    storey_height_mm: float = 3200.0,
) -> Path:
    """Run a supplied model; export IFC only when a real-world scale is supplied."""
    if not weights.is_file():
        raise FileNotFoundError(f"MODEL_WEIGHTS_REQUIRED: checkpoint not found: {weights}")
    prepared = prepare_document(source, output / "prepared")
    YOLO = _require_ultralytics()
    model = YOLO(str(weights))
    results = model.predict(source=[str(path) for path in prepared], conf=confidence, save=False)
    pages: list[PredictionPage] = []
    for image_path, result in zip(prepared, results, strict=True):
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"unable to read prepared image: {image_path}")
        pages.append(
            PredictionPage(
                image=image_path.name,
                width_px=image.shape[1],
                height_px=image.shape[0],
                predictions=_result_predictions(result),
            )
        )
    output.mkdir(parents=True, exist_ok=True)
    report = output / "predictions.json"
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "checkpoint": weights.name,
        "checkpoint_sha256": _sha256(weights),
        "source": source.name,
        "pages": [page.model_dump() for page in pages],
        "scale_status": "calibrated" if millimetres_per_pixel else "pixel_space_only",
    }
    if millimetres_per_pixel is not None:
        from struct2bim.exporters import export_ifc

        canonical_files = []
        for index, page in enumerate(pages, 1):
            scene = _canonical_scene(
                page,
                millimetres_per_pixel=millimetres_per_pixel,
                storey_height_mm=storey_height_mm,
                checkpoint=weights,
            )
            scene_path = output / f"page_{index:03d}_scene.json"
            ifc_path = output / f"page_{index:03d}.ifc"
            scene_path.write_text(scene.canonical_json(), encoding="utf-8", newline="\n")
            export_ifc(scene, ifc_path)
            canonical_files.append({"scene": scene_path.name, "ifc": ifc_path.name})
        payload["calibrated_outputs"] = canonical_files
    report.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    return report
