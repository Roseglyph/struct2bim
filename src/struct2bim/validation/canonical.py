"""Canonical scene validation at the export boundary.

The adapter deliberately accepts mappings, dataclasses and Pydantic models.  This
keeps file exporters independent from the producer while preserving a strict
wire-format contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from math import cos, radians, sin
from typing import Any, Mapping, TypeGuard

from shapely.geometry import Polygon  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    path: str
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def is_valid(self) -> bool:
        return not self.errors


class CanonicalValidationError(ValueError):
    """Raised when a canonical scene cannot be safely exported."""

    def __init__(self, report: ValidationReport):
        self.report = report
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in report.errors)
        super().__init__(f"Canonical scene validation failed: {details}")


def scene_as_dict(scene: Any) -> dict[str, Any]:
    """Return a plain mapping for a mapping, dataclass, or Pydantic model."""
    if isinstance(scene, Mapping):
        return dict(scene)
    model_dump = getattr(scene, "model_dump", None)
    if callable(model_dump):
        result = model_dump(mode="json")
        if isinstance(result, Mapping):
            return dict(result)
    if is_dataclass(scene):
        result = asdict(scene)  # type: ignore[arg-type]
        if isinstance(result, dict):
            return result
    raise TypeError("scene must be a mapping, dataclass, or Pydantic model")


def _number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _xy(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        value = (value.get("x"), value.get("y"))
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(_number(v) for v in value):
        return float(value[0]), float(value[1])
    return None


def _column_polygon(entity: Mapping[str, Any]) -> Polygon | None:
    center = _xy(entity.get("center_mm"))
    dimensions = entity.get("dimensions_mm", {})
    if center is None:
        return None
    if not isinstance(dimensions, Mapping):
        return None
    width, depth = dimensions.get("width"), dimensions.get("depth")
    if not _number(width) or not _number(depth) or width <= 0 or depth <= 0:
        return None
    width_value, depth_value = float(width), float(depth)
    angle = radians(float(entity.get("rotation_deg", 0)))
    points: list[tuple[float, float]] = []
    for x, y in ((-width_value / 2, -depth_value / 2), (width_value / 2, -depth_value / 2),
                 (width_value / 2, depth_value / 2), (-width_value / 2, depth_value / 2)):
        points.append((center[0] + x * cos(angle) - y * sin(angle),
                       center[1] + x * sin(angle) + y * cos(angle)))
    return Polygon(points)


def validate_scene(scene: Any) -> ValidationReport:
    data = scene_as_dict(scene)
    issues: list[ValidationIssue] = []

    def error(code: str, message: str, path: str) -> None:
        issues.append(ValidationIssue(code, message, path))

    project = data.get("project")
    if not isinstance(project, Mapping):
        error("missing_project", "project metadata is required", "project")
    elif project.get("units") not in {"mm", "millimetres", "millimeters"}:
        error("unsupported_units", "project units must be millimetres", "project.units")

    transform = data.get("transform")
    if not isinstance(transform, Mapping):
        error("missing_transform", "an explicit coordinate transform is required", "transform")
    else:
        scale_source = data.get("scale_source", transform.get("scale_source"))
        if scale_source in {None, "unknown"}:
            error("unknown_scale", "physical scale provenance is required", "transform.scale_source")
        ppm = transform.get("pixels_per_mm")
        if ppm is not None and (not _number(ppm) or ppm <= 0):
            error("invalid_scale", "pixels_per_mm must be positive", "transform.pixels_per_mm")

    raw_storeys = data.get("storeys")
    if not isinstance(raw_storeys, list) or not raw_storeys:
        error("missing_storeys", "at least one storey is required", "storeys")
        raw_storeys = []
    storey_ids: set[str] = set()
    for index, storey in enumerate(raw_storeys):
        if not isinstance(storey, Mapping) or not storey.get("id"):
            error("invalid_storey", "storey requires an id", f"storeys[{index}]")
            continue
        identifier = str(storey["id"])
        if identifier in storey_ids:
            error("duplicate_storey", f"duplicate storey id {identifier!r}", f"storeys[{index}].id")
        storey_ids.add(identifier)
        height = storey.get("height_mm")
        if not _number(height) or float(height) <= 0:
            error("invalid_storey_height", "height_mm must be positive", f"storeys[{index}].height_mm")

    entities = data.get("entities")
    if not isinstance(entities, list):
        error("missing_entities", "entities must be a list", "entities")
        entities = []
    grids = data.get("grids", [])
    if isinstance(grids, list):
        entities = list(entities) + [dict(grid, type="grid_axis") for grid in grids if isinstance(grid, Mapping)]
    ids: set[str] = set()
    column_polygons: list[tuple[int, str, Polygon]] = []
    supported = {"column", "grid_axis", "slab"}
    for index, entity in enumerate(entities):
        path = f"entities[{index}]"
        if not isinstance(entity, Mapping):
            error("invalid_entity", "entity must be an object", path)
            continue
        entity_identifier = entity.get("id")
        if not entity_identifier:
            error("missing_entity_id", "entity id is required", f"{path}.id")
        elif str(entity_identifier) in ids:
            error("duplicate_entity", f"duplicate entity id {entity_identifier!r}", f"{path}.id")
        else:
            ids.add(str(entity_identifier))
        entity_type = entity.get("type")
        if entity_type not in supported:
            error("unsupported_entity", f"no export mapping for {entity_type!r}", f"{path}.type")
            continue
        storey_id = entity.get("storey_id")
        if storey_id is not None and str(storey_id) not in storey_ids:
            error("unknown_storey", f"storey {storey_id!r} does not exist", f"{path}.storey_id")
        if entity_type == "column":
            dimensions = entity.get("dimensions_mm", {})
            if entity.get("subtype") == "circular" and isinstance(dimensions, Mapping):
                center = _xy(entity.get("center_mm"))
                diameter = dimensions.get("diameter")
                if center and _number(diameter) and diameter > 0:
                    diameter_value = float(diameter)
                    polygon = Polygon([
                        (center[0] + cos(radians(step * 11.25)) * diameter_value / 2,
                         center[1] + sin(radians(step * 11.25)) * diameter_value / 2)
                        for step in range(32)
                    ])
                else:
                    polygon = None
            else:
                polygon = _column_polygon(entity)
            if polygon is None or not polygon.is_valid:
                error("invalid_column_geometry", "column needs positive dimensions and a valid center", path)
            else:
                dimensions = entity["dimensions_mm"]
                height = dimensions.get("height")
                if not _number(height) or float(height) <= 0:
                    error("invalid_column_height", "column height must be positive", f"{path}.dimensions_mm.height")
                column_polygons.append((index, str(entity_identifier), polygon))
        elif entity_type == "grid_axis":
            for key in ("start_mm", "end_mm"):
                point = _xy(entity.get(key))
                if point is None:
                    error("invalid_grid_axis", f"{key} must contain two coordinates", f"{path}.{key}")

    for offset, (index_a, id_a, polygon_a) in enumerate(column_polygons):
        for index_b, id_b, polygon_b in column_polygons[offset + 1:]:
            intersection = polygon_a.intersection(polygon_b).area
            denominator = min(polygon_a.area, polygon_b.area)
            if denominator and intersection / denominator > 0.8:
                issues.append(ValidationIssue(
                    "overlapping_columns", f"columns {id_a!r} and {id_b!r} overlap substantially",
                    f"entities[{index_a}],entities[{index_b}]", "warning"))

    return ValidationReport(tuple(issues))


def require_valid_scene(scene: Any) -> dict[str, Any]:
    data = scene_as_dict(scene)
    report = validate_scene(data)
    if not report.is_valid:
        raise CanonicalValidationError(report)
    return data
