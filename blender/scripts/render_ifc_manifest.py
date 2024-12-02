"""Render an IFC tessellation manifest into a clean isometric showcase."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=24017)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])


def make_material(name, color, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.66
    shader.inputs["Metallic"].default_value = metallic
    return mat


def look_at(camera, point):
    camera.rotation_euler = (Vector(point) - camera.location).to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    args = arguments()
    args.output = args.output.resolve()
    random.seed(args.seed)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    column_mat = make_material("Structural Columns", (0.12, 0.38, 0.66, 1.0))
    slab_mat = make_material("Slab", (0.72, 0.78, 0.83, 1.0))
    neutral_mat = make_material("Other BIM Elements", (0.36, 0.46, 0.54, 1.0))
    grid_mat = make_material("IFC Grid Axes", (0.38, 0.48, 0.58, 1.0))
    all_vertices = []
    for item in manifest.get("meshes", []):
        vertices = [tuple(float(value) for value in vertex) for vertex in item.get("vertices", [])]
        faces = [tuple(int(value) for value in face) for face in item.get("faces", [])]
        if not vertices or not faces:
            continue
        mesh = bpy.data.meshes.new(str(item.get("name", "IFC Mesh")))
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(str(item.get("name", "IFC Mesh")), mesh)
        bpy.context.collection.objects.link(obj)
        ifc_type = str(item.get("ifc_type", ""))
        obj.data.materials.append(column_mat if ifc_type == "IfcColumn" else slab_mat if ifc_type == "IfcSlab" else neutral_mat)
        all_vertices.extend(vertices)
    for index, item in enumerate(manifest.get("grid_lines", [])):
        points = [tuple(float(value) for value in point) for point in item.get("points", [])]
        if len(points) < 2:
            continue
        curve_data = bpy.data.curves.new(f"IFC Grid {index + 1}", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.bevel_depth = 0.018
        curve_data.bevel_resolution = 2
        spline = curve_data.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, coordinates in zip(spline.points, points, strict=True):
            point.co = (*coordinates[:2], 0.02, 1.0)
        obj = bpy.data.objects.new(f"IFC Grid {item.get('label', index + 1)}", curve_data)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(grid_mat)
        all_vertices.extend((*coordinates[:2], 0.02) for coordinates in points)
    if not all_vertices:
        raise RuntimeError("The IFC render manifest contains no renderable geometry")
    xs, ys, zs = zip(*all_vertices)
    min_x, max_x, min_y, max_y, min_z, max_z = min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)
    center = ((min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2)
    span = max(max_x - min_x, max_y - min_y, max_z - min_z, 1.0)
    # A receiving plane creates grounded shadows without altering IFC geometry.
    base_x = max_x - min_x + span * 0.18
    base_y = max_y - min_y + span * 0.18
    bpy.ops.mesh.primitive_cube_add(location=(center[0], center[1], min_z - 0.06))
    ground = bpy.context.object
    ground.name = "Showcase Ground (not IFC)"
    ground.dimensions = (base_x, base_y, 0.08)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ground.data.materials.append(make_material("Ground", (0.96, 0.97, 0.98, 1.0)))
    camera_data = bpy.data.cameras.new("Isometric Camera")
    camera = bpy.data.objects.new("Isometric Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (center[0] + span * 1.35, center[1] - span * 1.55, center[2] + span * 1.15)
    look_at(camera, center)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = span * 1.75
    camera_data.lens = 50
    bpy.context.scene.camera = camera
    world = bpy.data.worlds.new("Studio World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.93, 0.95, 0.97, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
    bpy.context.scene.world = world
    bpy.ops.object.light_add(type="AREA", location=(center[0] - span, center[1] - span, center[2] + span * 2))
    key = bpy.context.object
    key.name = "Key Light"
    key.data.energy = 1100
    key.data.shape = "DISK"
    key.data.size = span * 1.5
    look_at(key, center)
    render = bpy.context.scene.render
    render.engine = "BLENDER_EEVEE_NEXT"
    render.resolution_x = 1600
    render.resolution_y = 1200
    render.resolution_percentage = 100
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGB"
    render.image_settings.color_depth = "8"
    render.filepath = str(args.output)
    render.film_transparent = False
    bpy.context.scene.view_settings.look = "AgX - Medium High Contrast"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
