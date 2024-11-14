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

    render_width, render_height = 1600, 1200
    aspect = render_width / render_height
    framed_x, framed_y = span_x + pad * 2, span_y + pad * 2
    # Blender's orthographic scale describes camera width; height follows the
    # output aspect ratio.
    ortho_width = max(framed_x, framed_y * aspect)
    ortho_height = ortho_width / aspect
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
            (center_x - ortho_width / 2) * 1000,
            (center_y - ortho_height / 2) * 1000,
            (center_x + ortho_width / 2) * 1000,
            (center_y + ortho_height / 2) * 1000,
        ],
        "seed": args.seed,
        "provenance": "synthetic_ground_truth",
    }
    args.output.with_suffix(args.output.suffix + ".render.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
