"""Build meshes and PBR materials in Blender from a JSON part list, such as gpt_model_spec.py writes.

The spec is treated as data and is never executed. Numbers are checked, names are cleaned, and metallic
snaps to 0 or 1. Everything lives in the SPEC_<name> collection, and re-running replaces it, so you can
edit the JSON and rebuild without another API call.
Spec: {name, uncertainties[], materials[{name, base_color{r,g,b sRGB}, metallic, roughness}],
parts[{name, shape, material, center{x,y,z}, rotation_deg{x,y,z}, size{x,y,z}, taper, bevel,
profile[{r,z}], outline[{x,y}]}]}. Shapes: box, cylinder, sphere, torus, lathe, extrude.
Usage:
  blender -b f.blend -P build_from_spec.py -- --spec spec.json [--height 0.28] [--no-ground] [--save out.blend]
  MCP: import build_from_spec as b; print(b.run(spec="C:/work/spec.json", height=0.28))
Returns the object names (pass them to qa_check.py), tris, overall dimensions and warnings.
"""
import json
import math
import os
import re
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

SHAPES = {"box", "cylinder", "sphere", "torus", "lathe", "extrude"}
MAX_PARTS, MAX_MATERIALS, MAX_POINTS = 200, 64, 256
SEGMENTS = 48
SHARP_ANGLE = math.radians(40)


def _name(text, fallback):
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_")[:40]
    return clean or fallback


def _num(value, label, lo=-1e4, hi=1e4):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a number, got {value!r}")
    if not lo <= value <= hi:
        raise ValueError(f"{label} must be from {lo} to {hi}, got {value}")
    return float(value)


def _vec(data, keys, label, lo=-1e4, hi=1e4):
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object with {keys}")
    return tuple(_num(data.get(k), f"{label}.{k}", lo, hi) for k in keys)


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _ring(bm, radius_x, radius_y, z):
    return [bm.verts.new((radius_x * math.cos(a), radius_y * math.sin(a), z))
            for a in (2 * math.pi * i / SEGMENTS for i in range(SEGMENTS))]


def _torus(bm, size, warnings, label):
    x, y, tube = size
    if tube >= min(x, y):
        warnings.append(f"{label}: tube thickness reduced to fit its diameter")
        tube = min(x, y) * 0.5
    minor = 12
    rows = []
    for i in range(SEGMENTS):
        u = 2 * math.pi * i / SEGMENTS
        row = []
        for j in range(minor):
            v = 2 * math.pi * j / minor
            bend = tube / 2 * math.cos(v)
            row.append(bm.verts.new((((x - tube) / 2 + bend) * math.cos(u), ((y - tube) / 2 + bend) * math.sin(u),
                                     tube / 2 * math.sin(v))))
        rows.append(row)
    for i in range(SEGMENTS):
        for j in range(minor):
            a, b = rows[i], rows[(i + 1) % SEGMENTS]
            bm.faces.new((a[j], b[j], b[(j + 1) % minor], a[(j + 1) % minor]))


def _lathe(bm, profile, label):
    pts = []
    for i, p in enumerate(profile[:MAX_POINTS]):
        q = (_num(p.get("r"), f"{label}.profile[{i}].r", 0), _num(p.get("z"), f"{label}.profile[{i}].z"))
        if not pts or q != pts[-1]:
            pts.append(q)
    if len(pts) < 2:
        raise ValueError(f"{label}: a lathe needs at least 2 profile points")
    eps = 1e-6
    rings = [[bm.verts.new((0, 0, z))] if r < eps else _ring(bm, r, r, z) for r, z in pts]
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for i in range(SEGMENTS):
            if len(a) == 1:
                bm.faces.new((a[0], b[i], b[(i + 1) % SEGMENTS]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[(i + 1) % SEGMENTS], b[0]))
            else:
                bm.faces.new((a[i], a[(i + 1) % SEGMENTS], b[(i + 1) % SEGMENTS], b[i]))
    for end in (rings[0], rings[-1]):
        if len(end) > 1:
            bm.faces.new(end)


def _extrude(bm, outline, height, label):
    pts = []
    for i, p in enumerate(outline[:MAX_POINTS]):
        q = (_num(p.get("x"), f"{label}.outline[{i}].x"), _num(p.get("y"), f"{label}.outline[{i}].y"))
        if not pts or q != pts[-1]:
            pts.append(q)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 3:
        raise ValueError(f"{label}: an extrude needs at least 3 outline points")
    low = [bm.verts.new((x, y, -height / 2)) for x, y in pts]
    high = [bm.verts.new((x, y, height / 2)) for x, y in pts]
    n = len(pts)
    bm.faces.new(low)
    bm.faces.new(high)
    for i in range(n):
        bm.faces.new((low[i], low[(i + 1) % n], high[(i + 1) % n], high[i]))


def _mesh(name, part, warnings):
    shape = part["shape"]
    size = _vec(part.get("size"), "xyz", f"{name}.size", 1e-5, 1e4)
    bm = bmesh.new()
    stretch = Matrix.Diagonal((*size, 1))
    if shape == "box":
        bmesh.ops.create_cube(bm, size=1.0, matrix=stretch)
    elif shape == "cylinder":
        taper = _num(part.get("taper", 1), f"{name}.taper", 0, 1)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=SEGMENTS, radius1=0.5, radius2=0.5 * taper, depth=1.0,
                              matrix=stretch)
    elif shape == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=SEGMENTS, v_segments=SEGMENTS // 2, radius=0.5, matrix=stretch)
    elif shape == "torus":
        _torus(bm, size, warnings, name)
    elif shape == "lathe":
        _lathe(bm, part.get("profile") or [], name)
    else:
        _extrude(bm, part.get("outline") or [], size[2], name)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = e.calc_face_angle(math.pi) < SHARP_ANGLE
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.validate()
    return me


def _material(prefix, data, warnings):
    label = _name(data.get("name"), "Mat")
    color = _vec(data.get("base_color"), "rgb", f"material {label}.base_color", 0, 1)
    raw_metal = _num(data.get("metallic", 0), f"material {label}.metallic", 0, 1)
    metal = 1.0 if raw_metal >= 0.5 else 0.0
    if raw_metal != metal:
        warnings.append(f"material {label}: metallic {raw_metal} snapped to {metal:.0f}")
    full = f"M_{prefix}_{label}"
    mat = bpy.data.materials.get(full) or bpy.data.materials.new(full)
    rgba = (*(_srgb_to_linear(c) for c in color), 1.0)
    bsdf = bx.node(mat.node_tree, "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = _num(data.get("roughness", 0.5), f"material {label}.roughness", 0, 1)
    mat.diffuse_color = rgba
    return label, mat


def _clear(col):
    for ob in list(col.objects):
        data = ob.data
        bpy.data.objects.remove(ob)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)


def _bounds(obs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def run(spec=None, height=None, no_ground=False, **_):
    if not spec:
        raise ValueError("--spec is required")
    with open(bpy.path.abspath(spec), encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("the spec must be a JSON object")
    parts, materials = data.get("parts"), data.get("materials")
    if not isinstance(parts, list) or not parts or not isinstance(materials, list) or not materials:
        raise ValueError("the spec needs non-empty parts and materials lists")
    if len(parts) > MAX_PARTS or len(materials) > MAX_MATERIALS:
        raise ValueError(f"the spec is limited to {MAX_PARTS} parts and {MAX_MATERIALS} materials")
    if height is not None:
        _num(height, "height", 1e-4, 1e4)
    bx.object_mode()
    prefix = _name(data.get("name"), "Model")
    warnings = []
    # check everything before touching the scene, so a bad spec can't destroy the previous build
    built = []
    mats = {}
    try:
        for i, part in enumerate(parts):
            if not isinstance(part, dict) or part.get("shape") not in SHAPES:
                raise ValueError(f"part {i}: shape must be one of {sorted(SHAPES)}")
            label = _name(part.get("name"), f"Part{i}")
            me = _mesh(f"SPECTMP_{prefix}_{i}", part, warnings)  # the final name is free only after _clear
            built.append((part, label, me))
            _vec(part.get("center"), "xyz", f"{label}.center")
            _vec(part.get("rotation_deg"), "xyz", f"{label}.rotation_deg", -3600, 3600)
            _num(part.get("bevel", 0), f"{label}.bevel", 0, 1e3)
        for m in materials:
            if not isinstance(m, dict):
                raise ValueError("each material must be an object")
            label, mat = _material(prefix, m, warnings)
            mats[label] = mat
    except Exception:
        for _p, _l, me in built:
            bpy.data.meshes.remove(me)
        raise
    sc = bpy.context.scene
    col = bpy.data.collections.get(f"SPEC_{prefix}") or bpy.data.collections.new(f"SPEC_{prefix}")
    if col.name not in sc.collection.children:
        sc.collection.children.link(col)
    _clear(col)
    fallback = next(iter(mats.values()))
    obs = []
    for part, label, me in built:
        me.name = f"SM_{prefix}_{label}"
        ob = bpy.data.objects.new(me.name, me)
        col.objects.link(ob)
        ob.location = _vec(part["center"], "xyz", label)
        ob.rotation_euler = Euler(tuple(math.radians(v) for v in _vec(part["rotation_deg"], "xyz", label, -3600, 3600)))
        wanted = _name(part.get("material"), "")
        if wanted not in mats:
            warnings.append(f"{label}: unknown material {part.get('material')!r}, used {fallback.name}")
        me.materials.append(mats.get(wanted, fallback))
        width = float(part.get("bevel", 0))
        if width > 0:
            mod = ob.modifiers.new("Bevel", "BEVEL")
            mod.width, mod.segments, mod.limit_method = width, 3, "ANGLE"
            mod.use_clamp_overlap = True
        obs.append(ob)
    lo, hi = _bounds(obs)
    if height is not None and hi.z - lo.z > 1e-6:
        factor = height / (hi.z - lo.z)
        for ob in obs:
            ob.data.transform(Matrix.Scale(factor, 4))
            ob.location = ob.location * factor
            for mod in ob.modifiers:
                mod.width *= factor
        lo, hi = _bounds(obs)
    if not no_ground:
        for ob in obs:
            ob.location.z -= lo.z
        lo, hi = _bounds(obs)
    dims = hi - lo
    if max(dims) > 100 or min(dims) < 1e-3:
        warnings.append(f"overall size {tuple(round(v, 4) for v in dims)} m looks wrong: check the units or pass --height")
    tris = sum(bx.mesh_tris(o) for o in obs)
    return {"ok": True, "collection": col.name, "objects": [o.name for o in obs], "materials": [m.name for m in mats.values()],
            "tris": tris, "dimensions_m": [round(v, 4) for v in dims], "warnings": warnings,
            "uncertainties": [str(u) for u in (data.get("uncertainties") or [])][:50]}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--spec", required=True)
    p.add_argument("--height", type=float, default=None, help="scale the model to this real height in meters")
    p.add_argument("--no-ground", action="store_true", help="don't move the lowest point to Z = 0")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
