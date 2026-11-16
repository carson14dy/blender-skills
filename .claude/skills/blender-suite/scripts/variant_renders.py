"""Render one shot per HDRI or per material, build a comparison grid, then restore the scene.

Modes: hdri (each file lights the scene through a temporary world), material (each existing material
goes on the objects' slot in turn). Uses the scene's camera, engine and resolution. The scene's world,
materials, output path and image format are restored even when a render fails.
Usage:
  blender -b f.blend -P variant_renders.py -- --hdris a.hdr b.exr --out //variants/ [--strength 1]
      [--rotation 0] [--columns 3] [--samples 64] [--engine CYCLES]
  blender -b f.blend -P variant_renders.py -- --materials M_Oak M_Steel --objects Hero --out //variants/
      [--slot 0] [--no-grid]
  MCP: import variant_renders as v; print(v.run(hdris=["C:/hdri/a.hdr"], out="//variants/"))
Returns one file per variant, plus the grid and which cell holds which variant.
"""
import math
import os
import re
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX = "PH_"


def _slug(name):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "variant"


def _hdri_world(path, strength, rotation):
    world = bpy.data.worlds.new(PREFIX + "Variant")
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    mapping = nt.nodes.new("ShaderNodeMapping")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    env.image = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
    mapping.inputs["Rotation"].default_value[2] = math.radians(rotation)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def _grid(paths, columns, dest):
    """Tile same-sized PNGs into one image, left to right, top to bottom."""
    cells = []
    for path in paths:
        img = bpy.data.images.load(path, check_existing=False)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        cells.append(px.reshape(h, w, 4))
        bpy.data.images.remove(img)
    h, w = cells[0].shape[:2]
    rows = math.ceil(len(cells) / columns)
    sheet = np.zeros((rows * h, columns * w, 4), dtype=np.float32)
    sheet[..., 3] = 1.0
    for i, cell in enumerate(cells):
        # image rows run bottom to top, so row 0 of the grid goes at the end of the array
        r, c = (rows - 1 - i // columns), i % columns
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = cell
    img = bpy.data.images.new(PREFIX + "Grid", columns * w, rows * h, alpha=True)
    img.pixels.foreach_set(sheet.ravel())
    img.filepath_raw, img.file_format = dest, "PNG"
    img.save()
    bpy.data.images.remove(img)
    return dest


def run(hdris=None, materials=None, objects=None, slot=0, out="//variants/", columns=3, strength=1.0,
        rotation=0.0, samples=None, engine=None, no_grid=False, **_):
    if bool(hdris) == bool(materials):
        raise ValueError("pass either --hdris or --materials")
    bx.object_mode()
    sc = bpy.context.scene
    if sc.camera is None:
        raise ValueError("scene has no camera (see blender-lighting-lookdev or blender-camera-moves)")
    r = sc.render
    base = bpy.path.abspath(out)
    os.makedirs(base, exist_ok=True)
    saved_scene = (r.filepath, r.image_settings.media_type, r.image_settings.file_format,
                   r.image_settings.color_mode, sc.world, r.engine)
    saved_slots = []
    temp_worlds = []
    targets = []
    if materials:
        missing = [m for m in materials if m not in bpy.data.materials]
        if missing:
            raise KeyError(f"materials not found: {missing} (build them with build_pbr_material.py)")
        targets = bx.objects(objects)
        if not targets:
            raise ValueError("no objects to apply materials to")
        for ob in targets:
            if len(ob.material_slots) <= slot:
                raise ValueError(f"{ob.name} has no material slot {slot}")
            saved_slots.append((ob, ob.material_slots[slot].material))
    if engine:
        bx.set_enum(r, "engine", engine)
    if samples and r.engine == "CYCLES":
        sc.cycles.samples = samples
    r.image_settings.media_type = "IMAGE"  # 5.0+: must precede file_format
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    files, variants = [], list(hdris or materials)
    try:
        for variant in variants:
            if hdris:
                world = _hdri_world(variant, strength, rotation)
                temp_worlds.append(world)
                sc.world = world
                stem = os.path.splitext(os.path.basename(bpy.path.abspath(variant)))[0]
            else:
                for ob in targets:
                    ob.material_slots[slot].material = bpy.data.materials[variant]
                stem = variant
            r.filepath = os.path.join(base, _slug(stem) + ".png")
            bpy.ops.render.render(write_still=True)
            files.append(r.filepath)
        grid = None
        if not no_grid and len(files) > 1:
            grid = _grid(files, min(columns, len(files)), os.path.join(base, "grid.png"))
    finally:
        r.filepath = saved_scene[0]
        r.image_settings.media_type = saved_scene[1]
        r.image_settings.file_format = saved_scene[2]
        r.image_settings.color_mode = saved_scene[3]
        sc.world = saved_scene[4]
        r.engine = saved_scene[5]
        for ob, mat in saved_slots:
            ob.material_slots[slot].material = mat
        for world in temp_worlds:
            bpy.data.worlds.remove(world)
    return {"ok": all(os.path.exists(f) for f in files), "mode": "hdri" if hdris else "material",
            "files": files, "grid": grid, "columns": min(columns, len(files)),
            "cells": [os.path.basename(f) for f in files], "res": [r.resolution_x, r.resolution_y]}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--hdris", nargs="*", default=None)
    p.add_argument("--materials", nargs="*", default=None)
    p.add_argument("--slot", type=int, default=0)
    p.add_argument("--out", default="//variants/")
    p.add_argument("--columns", type=int, default=3)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--rotation", type=float, default=0.0)
    p.add_argument("--samples", type=int, default=None)
    p.add_argument("--engine", default=None)
    p.add_argument("--no-grid", action="store_true")
    bx.cli(run, p)
