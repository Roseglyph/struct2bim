"""Render a canonical structural scene as a clean plan drawing in Blender.

Invoked by BlenderRunner; this module intentionally depends only on Blender's
bundled Python standard library and bpy.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=24017)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def material(name: str, color: tuple[float, float, float, float]):
    result = bpy.data.materials.new(name)
    result.diffuse_color = color
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 1.0
    return result


def cube(name: str, center, dimensions, mat) -> None:
    bpy.ops.mesh.primitive_cube_add(location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    obj.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def text_label(name, value, location, size, mat, rotation=0.0) -> None:
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = str(value)
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.002
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler[2] = rotation
    obj.data.materials.append(mat)


def entity_values(entity):
    center = entity.get("center_mm", [0.0, 0.0])
    dimensions = entity.get("dimensions_mm", {})
    if isinstance(center, dict):
        center = [center.get("x", 0.0), center.get("y", 0.0)]
    diameter = dimensions.get("diameter")
    return (
        float(center[0]) / 1000.0,
        float(center[1]) / 1000.0,
        float(dimensions.get("width") or diameter or entity.get("width_mm", 300.0)) / 1000.0,
        float(dimensions.get("depth") or diameter or entity.get("depth_mm", 300.0)) / 1000.0,
        math.radians(float(entity.get("rotation_deg", 0.0))),
        entity.get("subtype", "rectangular"),
    )


def main() -> None:
    args = arguments()
    args.output = args.output.resolve()
    random.seed(args.seed)
    scene = json.loads(args.scene.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    columns = [entity for entity in scene.get("entities", []) if entity.get("type", "column") == "column"]
    values = [entity_values(entity) for entity in columns]
    if values:
        min_x = min(x - width / 2 for x, _, width, _, _, _ in values)
        max_x = max(x + width / 2 for x, _, width, _, _, _ in values)
        min_y = min(y - depth / 2 for _, y, _, depth, _, _ in values)
        max_y = max(y + depth / 2 for _, y, _, depth, _, _ in values)
    else:
        min_x, min_y, max_x, max_y = -5.0, -4.0, 5.0, 4.0
    span_x, span_y = max(max_x - min_x, 1.0), max(max_y - min_y, 1.0)
    center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    ink = material("Drawing Ink", (0.045, 0.070, 0.090, 1.0))
    grid = material("Reference Grid", (0.38, 0.45, 0.50, 1.0))
    paper = material("Paper", (0.985, 0.99, 1.0, 1.0))
    white = material("Label White", (1.0, 1.0, 1.0, 1.0))
    pad = max(span_x, span_y) * 0.18
    cube("Drawing Sheet", (center_x, center_y, -0.025), (span_x + pad * 2, span_y + pad * 2, 0.04), paper)
    # Inferred grid axes provide a readable structural context even when a
    # canonical scene does not expose a dedicated grid representation yet.
    xs = sorted({round(x, 5) for x, _, _, _, _, _ in values})
    ys = sorted({round(y, 5) for _, y, _, _, _, _ in values})
    line_width = max(span_x, span_y) * 0.0018
    for index, x in enumerate(xs):
        cube(f"Grid X {index + 1}", (x, center_y, 0.005), (line_width, span_y + pad, 0.006), grid)
    for index, y in enumerate(ys):
        cube(f"Grid Y {index + 1}", (center_x, y, 0.005), (span_x + pad, line_width, 0.006), grid)
    for index, (x, y, width, depth, rotation, subtype) in enumerate(values):
        if subtype == "circular":
            bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=width / 2, depth=0.035, location=(x, y, 0.02))
            bpy.context.object.name = f"Column {index + 1}"
            bpy.context.object.data.materials.append(ink)
        else:
            cube(f"Column {index + 1}", (x, y, 0.02), (width, depth, 0.035), ink)
            bpy.context.object.rotation_euler[2] = rotation
        text_label(f"Column Label {index + 1}", f"C{index + 1}", (x + 0.34, y + 0.26, 0.05), 0.22, ink)

    # Drafting context is generated separately from document/photo augmentation.
    bubble_radius = max(span_x, span_y) * 0.018
    grid_by_id = scene.get("grids", [])
    for index, axis in enumerate(grid_by_id):
        start = axis["start_mm"]
        end = axis["end_mm"]
        start_x, start_y = float(start["x"]) / 1000.0, float(start["y"]) / 1000.0
        end_x, end_y = float(end["x"]) / 1000.0, float(end["y"]) / 1000.0
        location = (start_x, start_y, 0.025) if abs(end_y - start_y) > abs(end_x - start_x) else (end_x, end_y, 0.025)
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=bubble_radius, depth=0.018, location=location)
        bpy.context.object.name = f"Grid Bubble {index + 1}"
        bpy.context.object.data.materials.append(ink)
        text_label(
            f"Grid Label {index + 1}",
            axis.get("label", index + 1),
            (location[0], location[1], 0.045),
            bubble_radius * 1.05,
            white,
        )

    dimension_y = min_y - pad * 0.62
    cube("Overall X Dimension", (center_x, dimension_y, 0.01), (span_x, line_width * 1.4, 0.008), grid)
    cube("Overall X Tick 1", (min_x, dimension_y, 0.01), (line_width * 1.4, 0.38, 0.008), grid)
    cube("Overall X Tick 2", (max_x, dimension_y, 0.01), (line_width * 1.4, 0.38, 0.008), grid)
    text_label("Overall X Text", f"{span_x * 1000:.0f} mm", (center_x, dimension_y - 0.3, 0.04), 0.22, ink)

    source = scene["source"]
    transform = scene["transform"]
    render_width, render_height = int(source["width_px"]), int(source["height_px"])
    pixels_per_mm = float(transform["pixels_per_mm"])
    origin_px = transform["origin_px"]
    origin_world = transform.get("origin_world_mm", {"x": 0.0, "y": 0.0})
    min_world_x = float(origin_world["x"]) + (0.0 - float(origin_px["x"])) / pixels_per_mm
    max_world_x = float(origin_world["x"]) + (render_width - float(origin_px["x"])) / pixels_per_mm
    max_world_y = float(origin_world["y"]) + float(origin_px["y"]) / pixels_per_mm
    min_world_y = float(origin_world["y"]) + (float(origin_px["y"]) - render_height) / pixels_per_mm
    center_x = (min_world_x + max_world_x) / 2000.0
    center_y = (min_world_y + max_world_y) / 2000.0
    ortho_width = (max_world_x - min_world_x) / 1000.0
    camera_data = bpy.data.cameras.new("Plan Camera")
    camera = bpy.data.objects.new("Plan Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (center_x, center_y, 20.0)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = ortho_width
    bpy.context.scene.camera = camera
    world = bpy.data.worlds.new("White World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = world
    render = bpy.context.scene.render
    render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.display.shading.light = "FLAT"
    bpy.context.scene.display.shading.color_type = "MATERIAL"
    bpy.context.scene.display.shading.show_shadows = False
    bpy.context.scene.display.shading.show_cavity = False
    bpy.context.scene.display.shading.background_type = "VIEWPORT"
    bpy.context.scene.display.shading.background_color = (1.0, 1.0, 1.0)
    render.resolution_x = render_width
    render.resolution_y = render_height
    render.resolution_percentage = 100
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGB"
    render.film_transparent = False
    render.filepath = str(args.output)
    render.use_file_extension = True
    render.image_settings.color_depth = "8"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    sidecar = {
        "image_size": [render_width, render_height],
        "world_bounds_mm": [
            min_world_x,
            min_world_y,
            max_world_x,
            max_world_y,
        ],
        "seed": args.seed,
        "provenance": "synthetic_ground_truth",
    }
    args.output.with_suffix(args.output.suffix + ".render.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
