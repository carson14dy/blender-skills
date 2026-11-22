"""Pilot 024: build the garden shed of brief.md in stages, each saved to out/shed.blend.

Usage: $LAB_BPY_PYTHON build_shed.py -- --stage blockout|detail|materials|scene
Sizes come from brief.md and acceptance.json (assumed values are marked there). Metres inside, feet in the file.
Parts that rest on each other overlap by OV (2 mm), so qa_check sees no coplanar faces.
"""
import math
import os
import sys

import bpy  # first: under pip bpy, bmesh and mathutils resolve only after it
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
BLEND = os.path.join(OUT, "shed.blend")
SKILL = os.path.join(HERE, "..", "..", "..", ".claude", "skills", "blender-suite", "scripts")
FT, IN, OV = 0.3048, 0.0254, 0.002
W, D, H = 10 * FT, 12 * FT, 8 * FT           # walls (given)
PAD, MARGIN = 4 * IN, 2 * IN                 # pad (standard thickness, assumed margin)
T, R = 1 * IN, 1 * IN                        # siding + sheathing; roof deck + shingles
PITCH, OH = 6 / 12, 6 * IN                   # 6/12 (assumed, shortcut 1); overhangs (assumed)
ZW = PAD + H                                 # wall top
COS, SIN = 12 / math.hypot(12, 6), 6 / math.hypot(12, 6)
DOOR_W, DOOR_H, SILL_GAP = 36 * IN, 80 * IN, 0.5 * IN    # standard door (gap 2 in brief.md)
HEAD = PAD + SILL_GAP + DOOR_H                # door head; window heads line up with it
WIN_W, WIN_H, WIN_D, RO = 24 * IN, 36 * IN, 2.5 * IN, 0.25 * IN   # window unit (given size); rough opening gap
STUD_W, STUD_D = 1.5 * IN, 3.5 * IN


def under(x):
    """Roof underside height at x: through the wall top at the outer wall line, rising to the ridge."""
    return ZW + PITCH * min(x, W - x)


def coll():
    c = bpy.data.collections.get("Shed") or bpy.data.collections.new("Shed")
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def obj(name, bm, mat=None):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll().objects.link(ob)
    if mat:
        me.materials.append(bpy.data.materials[mat])
    return ob


def box(bm, lo, hi):
    c = [(a + b) / 2 for a, b in zip(lo, hi)]
    s = [b - a for a, b in zip(lo, hi)]
    bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Translation(c) @ Matrix.Diagonal((*s, 1)))
    return bm


def prism(bm, pts, a, b, axis="y"):
    """Closed prism: polygon pts (2D, in the plane across `axis`) from a to b along `axis`."""
    def p(u, v, w):
        return {"y": (u, w, v), "x": (w, u, v), "z": (u, v, w)}[axis]
    va = [bm.verts.new(p(u, v, a)) for u, v in pts]
    vb = [bm.verts.new(p(u, v, b)) for u, v in pts]
    bm.faces.new(va)
    bm.faces.new(vb[::-1])
    n = len(pts)
    for i in range(n):
        bm.faces.new((va[i], vb[i], vb[(i + 1) % n], va[(i + 1) % n]))
    return bm


def frame(bm, axis, cu, cv, ow, oh, iw, ih, a, b):
    """Picture frame: outer ow x oh, hole iw x ih, centred at (cu, cv), from a to b along `axis` (x or y)."""
    def ring(w, h, d):
        pts = ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))
        return [bm.verts.new((d, cu + u, cv + v) if axis == "x" else (cu + u, d, cv + v)) for u, v in pts]
    oa, ia, ob_, ib = ring(ow, oh, a), ring(iw, ih, a), ring(ow, oh, b), ring(iw, ih, b)
    for k in range(4):
        j = (k + 1) % 4
        bm.faces.new((oa[k], oa[j], ia[j], ia[k]))
        bm.faces.new((ob_[k], ib[k], ib[j], ob_[j]))
        bm.faces.new((oa[k], ob_[k], ob_[j], oa[j]))
        bm.faces.new((ia[k], ia[j], ib[j], ib[k]))
    return bm


def windows():
    """(name, wall x of the outer face, inward sign, y centre) for the four windows: two per long side."""
    return [(f"L{i}", 0.0, 1, y) for i, y in ((1, 4 * FT), (2, 8 * FT))] + \
           [(f"R{i}", W, -1, y) for i, y in ((1, 4 * FT), (2, 8 * FT))]


def cutters():
    out = []
    zd = (PAD - 0.1, HEAD + RO)
    out.append(box(bmesh.new(), (W / 2 - DOOR_W / 2 - RO, -0.1, zd[0]), (W / 2 + DOOR_W / 2 + RO, T + 0.1, zd[1])))
    for _, x, _, y in windows():
        out.append(box(bmesh.new(), (x - 0.1, y - WIN_W / 2 - RO, HEAD - WIN_H - RO),
                       (x + 0.1, y + WIN_W / 2 + RO, HEAD + RO)))
    return out


def stud_positions(length, start, openings):
    """Left edges of 16 in. OC studs from `start`, plus an end stud, skipping any that overlap an opening."""
    xs, x = [], start
    while x + STUD_W <= start + length - STUD_W:
        xs.append(x)
        x += 16 * IN
    xs.append(start + length - STUD_W)
    return [x for x in xs if not any(x < b and x + STUD_W > a for a, b in openings)]


def stage_blockout():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "IMPERIAL"
    os.makedirs(OUT, exist_ok=True)
    obj("Shed_Pad", box(bmesh.new(), (-MARGIN, -MARGIN, 0), (W + MARGIN, D + MARGIN, PAD)))
    wall = obj("Shed_Wall", box(bmesh.new(), (0, 0, PAD - OV), (W, D, ZW)))
    cuts = [obj(f"CUT_{i}", bm) for i, bm in enumerate([box(bmesh.new(), (T, T, 0), (W - T, D - T, ZW + 1))]
                                                       + cutters())]
    for c in cuts:
        m = wall.modifiers.new(c.name, "BOOLEAN")
        m.object, m.operation, m.solver = c, "DIFFERENCE", "EXACT"
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(wall.evaluated_get(dg))
    wall.modifiers.clear()
    old, wall.data = wall.data, me
    bpy.data.meshes.remove(old)
    me.name = "Shed_Wall"
    for c in cuts:
        bpy.data.objects.remove(c)
    for name, y0, y1 in (("Shed_Gable_F", OV, T - OV), ("Shed_Gable_B", D - T + OV, D - OV)):
        pts = [(OV, ZW - OV), (W - OV, ZW - OV), (W - OV, under(W - OV) + OV), (W / 2, under(W / 2) + OV),
               (OV, under(OV) + OV)]
        obj(name, prism(bmesh.new(), pts, y0, y1))
    e, rx, rz = -OH, R * SIN, R * COS                     # roof: one bent slab, square-cut eaves
    pts = [(e, under(0) - PITCH * OH), (W / 2, under(W / 2)), (W - e, under(0) - PITCH * OH),
           (W - e + rx, under(0) - PITCH * OH + rz), (W / 2, under(W / 2) + R / COS), (e - rx, under(0) - PITCH * OH + rz)]
    obj("Shed_Roof", prism(bmesh.new(), pts, -OH, D + OH))
    for name, x, s, y in windows():                       # blockout: a box per window unit
        obj(f"Shed_Window_{name}", box(bmesh.new(), (min(x, x + s * WIN_D), y - WIN_W / 2, HEAD - WIN_H),
                                       (max(x, x + s * WIN_D), y + WIN_W / 2, HEAD)))
    obj("Shed_Door", box(bmesh.new(), (W / 2 - DOOR_W / 2, 0, PAD + SILL_GAP), (W / 2 + DOOR_W / 2, 1.75 * IN, HEAD)))
    studs()


def studs():
    z0, z1 = PAD - OV, ZW - 1.5 * IN                       # no plates (shortcut): studs stand on the pad
    door = [(W / 2 - DOOR_W / 2 - RO, W / 2 + DOOR_W / 2 + RO)]
    side_open = [(y - WIN_W / 2 - RO, y + WIN_W / 2 + RO) for y in (4 * FT, 8 * FT)]
    inner = W - 2 * T + 2 * OV                            # end studs reach 2 mm into the side walls
    rows = [("B", stud_positions(inner, T - OV, []), "x", (D - T - STUD_D, D - T + OV)),
            ("F", stud_positions(inner, T - OV, door), "x", (T - OV, T + STUD_D))]
    y0 = T + STUD_D + 0.25 * IN                           # side studs start behind the front studs
    side = stud_positions(D - 2 * T - 2 * (STUD_D + 0.25 * IN), y0, side_open)
    rows += [("L", side, "y", (T - OV, T + STUD_D)), ("R", side, "y", (W - T - STUD_D, W - T + OV))]
    for tag, pos, along, (a, b) in rows:
        for i, p in enumerate(pos):
            lo, hi = ((p, a, z0), (p + STUD_W, b, z1)) if along == "x" else ((a, p, z0), (b, p + STUD_W, z1))
            obj(f"Shed_Stud_{tag}{i + 1:02d}", box(bmesh.new(), lo, hi))


def stage_detail():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    for name, x, s, y in windows():                       # frame, meeting rail, two panes; trim outside
        fx = (x, x + s * WIN_D)
        bm = frame(bmesh.new(), "x", y, HEAD - WIN_H / 2, WIN_W, WIN_H, WIN_W - 3 * IN, WIN_H - 3 * IN, *fx)
        mid = HEAD - WIN_H / 2
        box(bm, (min(fx) + 0.5 * IN, y - WIN_W / 2 + 1.5 * IN - OV, mid - 0.75 * IN),
            (max(fx) - 0.5 * IN, y + WIN_W / 2 - 1.5 * IN + OV, mid + 0.75 * IN))
        gx = x + s * 1.1 * IN
        for z0, z1 in ((HEAD - WIN_H + 1.5 * IN - OV, mid - 0.75 * IN + OV), (mid + 0.75 * IN - OV, HEAD - 1.5 * IN + OV)):
            box(bm, (min(gx, gx + s * 0.25 * IN), y - WIN_W / 2 + 1.5 * IN - OV, z0),
                (max(gx, gx + s * 0.25 * IN), y + WIN_W / 2 - 1.5 * IN + OV, z1))
        obj(f"Shed_Window_{name}", bm)
        obj(f"Shed_Trim_W{name}", frame(bmesh.new(), "x", y, HEAD - WIN_H / 2, WIN_W + 7 * IN, WIN_H + 7 * IN,
                                        WIN_W - 1 * IN, WIN_H - 1 * IN, x - s * 0.75 * IN, x + s * OV))
    door = box(bmesh.new(), (W / 2 - DOOR_W / 2, 0, PAD + SILL_GAP), (W / 2 + DOOR_W / 2, 1.75 * IN, HEAD))
    bmesh.ops.create_cone(door, cap_ends=True, segments=16, radius1=1.25 * IN, radius2=1.25 * IN, depth=2.5 * IN,
                          matrix=Matrix.Translation((W / 2 + 15 * IN, -1.25 * IN + OV, PAD + 36 * IN))
                          @ Matrix.Rotation(math.pi / 2, 4, "X"))            # knob, 2 mm into the door
    obj("Shed_Door", door)
    x0, x1 = W / 2 - DOOR_W / 2 - RO - 3.5 * IN, W / 2 + DOOR_W / 2 + RO + 3.5 * IN    # U-shaped door casing
    i0, i1, top = W / 2 - DOOR_W / 2 + 0.5 * IN, W / 2 + DOOR_W / 2 - 0.5 * IN, HEAD - 0.5 * IN
    pts = [(x0, PAD - OV), (i0, PAD - OV), (i0, top), (i1, top), (i1, PAD - OV), (x1, PAD - OV), (x1, HEAD + RO + 3.5 * IN),
           (x0, HEAD + RO + 3.5 * IN)]
    obj("Shed_Trim_Door", prism(bmesh.new(), pts, -0.75 * IN, OV))
    unwrap([o for o in bpy.data.objects if o.name.startswith("Shed_")])


def unwrap(obs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def save_png(name, rgb, data=False):
    """Write rgb (rows top to bottom) as out/textures/<name>.png and load it back as a file image."""
    h, w = rgb.shape[:2]
    tmp = bpy.data.images.new(name + "_tmp", w, h)
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = rgb if rgb.ndim == 3 else rgb[..., None]
    tmp.pixels.foreach_set(px[::-1].ravel())
    path = os.path.join(OUT, "textures", name + ".png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp.filepath_raw, tmp.file_format = path, "PNG"
    tmp.save()
    bpy.data.images.remove(tmp)
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    im = bpy.data.images.load(path)
    im.name, im.filepath = name, bpy.path.relpath(path)
    im.colorspace_settings.is_data = data
    return im


def textures():
    rng = np.random.default_rng(24)
    n = 512                                               # siding: 4 ft tile, 8 laps of 6 in.
    v = (np.arange(n) % 64) / 64.0                        # 0 at a lap's top, 1 at its bottom edge
    height = np.tile(v[:, None], (1, n))
    shade = 0.82 + 0.18 * height - 0.35 * (height > 0.94)
    grain = 1 + 0.04 * rng.standard_normal((n, n)).cumsum(1) / np.sqrt(np.arange(1, n + 1))
    sage = np.array([0.55, 0.63, 0.50])
    siding = np.clip(shade[..., None] * grain[..., None] * sage, 0, 1)
    rows, cols = 640, 576                                 # shingles: 40 in. x 36 in., 8 rows of 5 in., 12 in. tabs
    r = np.arange(rows)[:, None] // 80
    yy = (np.arange(rows)[:, None] % 80) / 80.0
    xx = (np.arange(cols)[None, :] + (r % 2) * 96) % 192
    slot = (xx < 4) & (yy > 0.35)
    tone = 0.18 + 0.05 * rng.random((8, 1))[r[:, 0]] + 0.05 * rng.random((rows, cols))
    shing = np.clip(tone * (1 - 0.5 * slot - 0.55 * (yy > 0.88)), 0, 1)
    shingle_rgb = shing[..., None] * np.array([1.0, 0.98, 0.95])
    return (save_png("T_Siding_Sage", siding), save_png("T_Siding_Height", height, True),
            save_png("T_Shingle_Asphalt", shingle_rgb), save_png("T_Shingle_Height", shing / shing.max(), True))


def principled(name, rgb, rough=0.5, **inputs):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    for k, val in inputs.items():
        b.inputs[k.replace("_", " ")].default_value = val
    return m, b


def mapped(m, b, col, hgt, uv_expr, strength):
    """Image colour + height-to-bump, mapped in object space by uv_expr(tree, separate) -> vector socket."""
    nt = m.node_tree
    tc, sep = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    vec = uv_expr(nt, sep)
    tci, tch = nt.nodes.new("ShaderNodeTexImage"), nt.nodes.new("ShaderNodeTexImage")
    tci.image, tch.image = col, hgt
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    for t in (tci, tch):
        nt.links.new(vec, t.inputs["Vector"])
    nt.links.new(tci.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tch.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])


def edges_plain(m, b, rgb):
    """Faces that do not face up (rake and eave edges, underside) get a plain colour: the texture only fits the slope."""
    nt = m.node_tree
    tex = b.inputs["Base Color"].links[0].from_socket
    geo, sep, mix = nt.nodes.new("ShaderNodeNewGeometry"), nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    sock = {s.identifier: s for s in mix.inputs}
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    nt.links.new(_math(nt, "GREATER_THAN", sep.outputs[2], 0.5), sock["Factor_Float"])
    sock["A_Color"].default_value = (*rgb, 1)
    nt.links.new(tex, sock["B_Color"])
    nt.links.new(next(o for o in mix.outputs if o.identifier == "Result_Color"), b.inputs["Base Color"])


def _math(nt, op, a, b):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if isinstance(v, float):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def stage_materials():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    sid, sidh, shi, shih = textures()
    m, b = principled("M_Siding_Sage", (0.5, 0.6, 0.45), 0.6)

    def siding_uv(nt, sep):                                # along the wall (x + y), up the wall (z); 4 ft tile
        c = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(_math(nt, "DIVIDE", _math(nt, "ADD", sep.outputs[0], sep.outputs[1]), 4 * FT), c.inputs[0])
        nt.links.new(_math(nt, "DIVIDE", sep.outputs[2], 4 * FT), c.inputs[1])
        return c.outputs[0]
    mapped(m, b, sid, sidh, siding_uv, 0.4)
    m, b = principled("M_Shingle_Asphalt", (0.2, 0.2, 0.2), 0.85)

    def roof_uv(nt, sep):                                 # along the ridge (y), down the slope (|x - ridge| / cos)
        c = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(_math(nt, "DIVIDE", sep.outputs[1], 36 * IN), c.inputs[0])
        down = _math(nt, "DIVIDE", _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", sep.outputs[0], W / 2), 0.0), COS)
        nt.links.new(_math(nt, "DIVIDE", down, -40 * IN), c.inputs[1])
        return c.outputs[0]
    mapped(m, b, shi, shih, roof_uv, 0.8)
    edges_plain(m, b, (0.05, 0.05, 0.05))
    principled("M_Trim_White", (0.86, 0.86, 0.84), 0.45)
    principled("M_Door_White", (0.83, 0.83, 0.81), 0.4)
    principled("M_Knob_Brass", (0.8, 0.62, 0.32), 0.3, Metallic=1.0)
    principled("M_Glass", (0.9, 0.95, 0.95), 0.03, Transmission_Weight=1.0)
    principled("M_Concrete", (0.52, 0.51, 0.48), 0.85)
    principled("M_Wood_Stud", (0.62, 0.47, 0.31), 0.7)
    rules = [("Shed_Wall", "M_Siding_Sage"), ("Shed_Gable", "M_Siding_Sage"), ("Shed_Roof", "M_Shingle_Asphalt"),
             ("Shed_Trim", "M_Trim_White"), ("Shed_Pad", "M_Concrete"), ("Shed_Stud", "M_Wood_Stud")]
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.name.startswith("Shed_"):
            continue
        o.data.materials.clear()
        if o.name.startswith("Shed_Window"):
            window_materials(o)
        elif o.name == "Shed_Door":
            door_materials(o)
        else:
            o.data.materials.append(bpy.data.materials[next(mt for p, mt in rules if o.name.startswith(p))])


def _islands_by(o, pick):
    """Give each mesh island the material index pick(island bounds) returns."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        while stack:
            g = stack.pop()
            if g.index in seen:
                continue
            seen.add(g.index)
            isl.append(g)
            stack += [h for e in g.edges for h in e.link_faces if h.index not in seen]
        lo = Vector([min(v.co[i] for g in isl for v in g.verts) for i in range(3)])
        hi = Vector([max(v.co[i] for g in isl for v in g.verts) for i in range(3)])
        for g in isl:
            g.material_index = pick(lo, hi)
    bm.to_mesh(o.data)
    bm.free()


def window_materials(o):
    o.data.materials.append(bpy.data.materials["M_Trim_White"])
    o.data.materials.append(bpy.data.materials["M_Glass"])
    _islands_by(o, lambda lo, hi: 1 if (hi.x - lo.x) < 0.5 * IN else 0)


def door_materials(o):
    o.data.materials.append(bpy.data.materials["M_Door_White"])
    o.data.materials.append(bpy.data.materials["M_Knob_Brass"])
    _islands_by(o, lambda lo, hi: 1 if (hi.x - lo.x) < 3 * IN else 0)


def stage_scene():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    sys.path.insert(0, os.path.abspath(SKILL))
    import scene_mood
    for name in ("Cam_Hero", "Ground_Lawn"):              # re-runnable
        if bpy.data.objects.get(name):
            bpy.data.objects.remove(bpy.data.objects[name])
    if bpy.data.materials.get("M_Lawn"):
        bpy.data.materials.remove(bpy.data.materials["M_Lawn"])
    lawn = obj("Ground_Lawn", box(bmesh.new(), (-300, -300, -0.05), (300, 300, 0.003)))   # reaches the horizon
    coll().objects.unlink(lawn)
    bpy.context.scene.collection.objects.link(lawn)
    m, b = principled("M_Lawn", (0.16, 0.3, 0.09), 0.9)
    nt = m.node_tree
    noise, ramp = nt.nodes.new("ShaderNodeTexNoise"), nt.nodes.new("ShaderNodeValToRGB")
    noise.inputs["Scale"].default_value = 40.0
    ramp.color_ramp.elements[0].color = (0.12, 0.24, 0.07, 1)
    ramp.color_ramp.elements[1].color = (0.22, 0.36, 0.12, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    lawn.data.materials.append(m)
    cam = bpy.data.objects.new("Cam_Hero", bpy.data.cameras.new("Cam_Hero"))
    bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = 28
    cam.location = Vector((-3.9, -5.6, 1.75))
    cam.rotation_euler = (Vector((1.45, 1.75, 1.45)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    res = scene_mood.run(time="afternoon")               # no heading: it picks a side light for this camera
    r = bpy.context.scene.render
    r.resolution_x, r.resolution_y = 1920, 1080
    print("scene_mood:", {k: res[k] for k in res if k in ("ok", "time", "sun", "elevation", "heading", "warning")})


if __name__ == "__main__":
    stage = sys.argv[sys.argv.index("--stage") + 1]
    globals()["stage_" + stage]()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    print(f"saved {BLEND} after stage {stage}")
