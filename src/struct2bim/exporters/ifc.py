"""IFC4 export and independent reopen checks."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin
from pathlib import Path
from typing import Any, Iterable, Mapping
import uuid

import ifcopenshell
import ifcopenshell.guid

from struct2bim.validation import require_valid_scene


@dataclass(frozen=True, slots=True)
class IfcValidationResult:
    is_valid: bool
    errors: tuple[str, ...]
    counts: dict[str, int]


def _guid(key: str) -> str:
    """Return a stable IFC GUID so identical canonical scenes reproduce exactly."""
    return str(ifcopenshell.guid.compress(uuid.uuid5(uuid.NAMESPACE_URL, key).hex))  # type: ignore[no-untyped-call]


def _point(model: ifcopenshell.file, coordinates: Iterable[float]) -> Any:
    return model.create_entity("IfcCartesianPoint", Coordinates=tuple(float(v) for v in coordinates))


def _direction(model: ifcopenshell.file, ratios: Iterable[float]) -> Any:
    return model.create_entity("IfcDirection", DirectionRatios=tuple(float(v) for v in ratios))


def _xy(value: Any) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return float(value["x"]), float(value["y"])
    return float(value[0]), float(value[1])


def _axis_placement(model: ifcopenshell.file, xyz: tuple[float, float, float], rotation: float = 0) -> Any:
    angle = radians(rotation)
    return model.create_entity(
        "IfcAxis2Placement3D", Location=_point(model, xyz),
        Axis=_direction(model, (0, 0, 1)), RefDirection=_direction(model, (cos(angle), sin(angle), 0)))


def _local_placement(model: ifcopenshell.file, parent: Any | None,
                     xyz: tuple[float, float, float], rotation: float = 0) -> Any:
    return model.create_entity(
        "IfcLocalPlacement", PlacementRelTo=parent,
        RelativePlacement=_axis_placement(model, xyz, rotation))


def _rectangle_representation(model: ifcopenshell.file, context: Any, width_m: float,
                              depth_m: float, height_m: float) -> Any:
    profile = model.create_entity(
        "IfcRectangleProfileDef", ProfileType="AREA", XDim=width_m, YDim=depth_m,
        Position=model.create_entity("IfcAxis2Placement2D", Location=_point(model, (0, 0))))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=profile,
        Position=_axis_placement(model, (0, 0, 0)),
        ExtrudedDirection=_direction(model, (0, 0, 1)), Depth=height_m)
    shape = model.create_entity(
        "IfcShapeRepresentation", ContextOfItems=context, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=(solid,))
    return model.create_entity("IfcProductDefinitionShape", Representations=(shape,))


def _circle_representation(model: ifcopenshell.file, context: Any, diameter_m: float,
                           height_m: float) -> Any:
    profile = model.create_entity(
        "IfcCircleProfileDef", ProfileType="AREA", Radius=diameter_m / 2,
        Position=model.create_entity("IfcAxis2Placement2D", Location=_point(model, (0, 0))))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=profile, Position=_axis_placement(model, (0, 0, 0)),
        ExtrudedDirection=_direction(model, (0, 0, 1)), Depth=height_m)
    shape = model.create_entity(
        "IfcShapeRepresentation", ContextOfItems=context, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=(solid,))
    return model.create_entity("IfcProductDefinitionShape", Representations=(shape,))


def _single_value(model: ifcopenshell.file, name: str, value: Any) -> Any:
    if isinstance(value, float):
        nominal = model.create_entity("IfcReal", value)
    else:
        nominal = model.create_entity("IfcText", str(value))
    return model.create_entity("IfcPropertySingleValue", Name=name, NominalValue=nominal)


def _attach_provenance(model: ifcopenshell.file, product: Any, entity: Mapping[str, Any],
                       scene: Mapping[str, Any]) -> None:
    provenance = entity.get("provenance", {})
    classification = entity.get("classification", {})
    source = scene.get("source", {})
    values = {
        "SourceType": provenance.get("source", source.get("type", "unknown")),
        "SourceFile": source.get("image", ""),
        "DetectionClass": entity.get("label", classification.get("label", entity.get("type", ""))),
        "Confidence": float(provenance.get("confidence", 1.0)),
        "ScaleSource": scene.get("scale_source", scene.get("transform", {}).get("scale_source", "unknown")),
        "SchemaVersion": scene.get("schema_version", "1.0"),
        "GeneratorVersion": scene.get("generator_version", "struct2bim"),
    }
    properties = tuple(_single_value(model, key, value) for key, value in values.items())
    product_key = str(product.GlobalId)
    pset = model.create_entity(
        "IfcPropertySet", GlobalId=_guid(f"{product_key}:provenance"), Name="Pset_Struct2BIMProvenance",
        HasProperties=properties)
    model.create_entity(
        "IfcRelDefinesByProperties", GlobalId=_guid(f"{product_key}:provenance-relation"), RelatedObjects=(product,),
        RelatingPropertyDefinition=pset)


def _create_units(model: ifcopenshell.file) -> Any:
    length = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    area = model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
    volume = model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
    angle = model.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")
    return model.create_entity("IfcUnitAssignment", Units=(length, area, volume, angle))


def export_ifc(scene: Any, destination: str | Path) -> Path:
    """Export a validated canonical scene to a self-contained IFC4 model."""
    data = require_valid_scene(scene)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    model = ifcopenshell.file(schema="IFC4")
    model.header.file_name.time_stamp = "1970-01-01T00:00:00"  # type: ignore[union-attr]
    origin = _point(model, (0, 0, 0))
    context = model.create_entity(
        "IfcGeometricRepresentationContext", ContextIdentifier="Model",
        ContextType="Model", CoordinateSpaceDimension=3, Precision=1e-6,
        WorldCoordinateSystem=model.create_entity("IfcAxis2Placement3D", Location=origin))
    project_name = str(data.get("project", {}).get("name", "Struct2BIM Project"))
    project = model.create_entity(
        "IfcProject", GlobalId=_guid(f"{project_name}:project"), Name=project_name,
        RepresentationContexts=(context,), UnitsInContext=_create_units(model))
    site_placement = _local_placement(model, None, (0, 0, 0))
    site = model.create_entity("IfcSite", GlobalId=_guid(f"{project_name}:site"), Name="Site", ObjectPlacement=site_placement)
    building_placement = _local_placement(model, site_placement, (0, 0, 0))
    building = model.create_entity(
        "IfcBuilding", GlobalId=_guid(f"{project_name}:building"), Name="Building", ObjectPlacement=building_placement)
    model.create_entity("IfcRelAggregates", GlobalId=_guid(f"{project_name}:project-site"), RelatingObject=project, RelatedObjects=(site,))
    model.create_entity("IfcRelAggregates", GlobalId=_guid(f"{project_name}:site-building"), RelatingObject=site, RelatedObjects=(building,))

    storeys: dict[str, Any] = {}
    storey_products: dict[str, list[Any]] = {}
    for item in data["storeys"]:
        elevation_m = float(item.get("elevation_mm", 0)) / 1000
        placement = _local_placement(model, building_placement, (0, 0, elevation_m))
        storey = model.create_entity(
            "IfcBuildingStorey", GlobalId=_guid(f"{project_name}:storey:{item['id']}"), Name=str(item.get("name", item["id"])),
            ObjectPlacement=placement, Elevation=elevation_m)
        storeys[str(item["id"])] = storey
        storey_products[str(item["id"])] = []
    model.create_entity(
        "IfcRelAggregates", GlobalId=_guid(f"{project_name}:building-storeys"), RelatingObject=building,
        RelatedObjects=tuple(storeys.values()))

    grid_axes: list[tuple[Mapping[str, Any], Any]] = []
    default_storey_id = next(iter(storeys))
    entities = list(data["entities"])
    entities.extend(dict(axis, type="grid_axis") for axis in data.get("grids", []))
    for entity in entities:
        entity_type = entity["type"]
        storey_id = str(entity.get("storey_id", default_storey_id))
        storey = storeys[storey_id]
        if entity_type == "column":
            dimensions = entity["dimensions_mm"]
            height = float(dimensions["height"]) / 1000
            center = _xy(entity["center_mm"])
            placement = _local_placement(
                model, storey.ObjectPlacement, (center[0] / 1000, center[1] / 1000, 0),
                float(entity.get("rotation_deg", 0)))
            product = model.create_entity(
                "IfcColumn", GlobalId=_guid(f"{project_name}:column:{entity['id']}"), Name=str(entity["id"]),
                Tag=str(entity.get("label", entity.get("classification", {}).get("label", entity["id"]))),
                ObjectPlacement=placement,
                Representation=(_circle_representation(model, context, float(dimensions["diameter"]) / 1000, height)
                                if entity.get("subtype") == "circular"
                                else _rectangle_representation(model, context, float(dimensions["width"]) / 1000,
                                                               float(dimensions["depth"]) / 1000, height)))
            storey_products[storey_id].append(product)
            _attach_provenance(model, product, entity, data)
        elif entity_type == "grid_axis":
            start, end = _xy(entity["start_mm"]), _xy(entity["end_mm"])
            curve = model.create_entity(
                "IfcPolyline", Points=(_point(model, (start[0] / 1000, start[1] / 1000)),
                                        _point(model, (end[0] / 1000, end[1] / 1000))))
            axis = model.create_entity(
                "IfcGridAxis", AxisTag=str(entity.get("label", entity["id"])),
                AxisCurve=curve, SameSense=True)
            grid_axes.append((entity, axis))

    if grid_axes:
        u_axes: list[Any] = []
        v_axes: list[Any] = []
        for entity, axis in grid_axes:
            start, end = _xy(entity["start_mm"]), _xy(entity["end_mm"])
            (u_axes if abs(end[1] - start[1]) >= abs(end[0] - start[0]) else v_axes).append(axis)
        # IFC requires at least one U and V axis. A one-direction fixture remains useful as DXF,
        # but is not emitted as an invalid IfcGrid.
        if u_axes and v_axes:
            first_storey = storeys[default_storey_id]
            grid = model.create_entity(
                "IfcGrid", GlobalId=_guid(f"{project_name}:grid"), Name="Structural Grid",
                ObjectPlacement=_local_placement(model, first_storey.ObjectPlacement, (0, 0, 0)),
                UAxes=tuple(u_axes), VAxes=tuple(v_axes))
            storey_products[default_storey_id].append(grid)

    for storey_id, products in storey_products.items():
        if products:
            model.create_entity(
                "IfcRelContainedInSpatialStructure", GlobalId=_guid(f"{project_name}:contains:{storey_id}"),
                RelatedElements=tuple(products), RelatingStructure=storeys[storey_id])

    model.write(str(path))
    result = validate_ifc_file(path, expected_scene=data)
    if not result.is_valid:
        path.unlink(missing_ok=True)
        raise ValueError("Exported IFC failed reopen validation: " + "; ".join(result.errors))
    return path


def validate_ifc_file(path: str | Path, expected_scene: Any | None = None) -> IfcValidationResult:
    """Reopen an IFC and verify hierarchy, containment, and expected object counts."""
    errors: list[str] = []
    try:
        model = ifcopenshell.open(str(path))
    except Exception as exc:  # IfcOpenShell exposes parser failures through runtime exceptions.
        return IfcValidationResult(False, (f"unable to open IFC: {exc}",), {})
    type_names = ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcColumn", "IfcGrid")
    counts = {name: len(model.by_type(name)) for name in type_names}
    for required in ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey"):
        if counts[required] < 1:
            errors.append(f"missing required {required}")
    if not model.by_type("IfcRelAggregates"):
        errors.append("missing spatial hierarchy relationships")
    columns = model.by_type("IfcColumn")
    for column in columns:
        if column.ContainedInStructure == ():
            errors.append(f"column {column.Name!r} is not spatially contained")
        if column.Representation is None:
            errors.append(f"column {column.Name!r} has no representation")
    if expected_scene is not None:
        data = require_valid_scene(expected_scene)
        expected_columns = sum(item["type"] == "column" for item in data["entities"])
        if counts["IfcColumn"] != expected_columns:
            errors.append(f"expected {expected_columns} columns, found {counts['IfcColumn']}")
        if counts["IfcBuildingStorey"] != len(data["storeys"]):
            errors.append("storey count differs from canonical scene")
    return IfcValidationResult(not errors, tuple(errors), counts)
