"""House JSON -> Blender scene (needs only bpy + numpy, so it also runs under ``blender -b -P``).

The roof object's base mesh is exactly the measured roof surface (the answer-key facets); thickness, fascia,
gutters and details are added around it. ``roof_surface_area()`` re-measures that base mesh in Blender so every
build proves the rendered roof equals the answer key.

All textures are procedural and keyed to world / facet coordinates in metres (no image files, no tiling), with
fine granular detail so photogrammetry can match features.
"""
from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOF_DECK_M = 0.04          # shingles + sheathing thickness below the measured top surface
FASCIA_H, FASCIA_T = 0.20, 0.03
GUTTER_W, GUTTER_H = 0.127, 0.11


# ---------------------------------------------------------------------------------------------------------------
# small helpers

def srgb_to_linear(c):
    c = [x / 255.0 if x > 1.0 else x for x in c]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def _coll(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in (parent or bpy.context.scene.collection).children:
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def _obj(name, verts, faces, coll, mats=(), uvs=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [list(f) for f in faces])
    me.validate()
    if uvs is not None:
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv.data[li].uv = uvs[me.loops[li].vertex_index]
    for m in mats:
        me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def _box(name, coll, mat, center, x_axis, y_axis, size, z_axis=None):
    """Oriented box: ``size`` = (sx, sy, sz) along x_axis, y_axis, z_axis (z defaults to x cross y)."""
    x = np.asarray(x_axis, float); x /= np.linalg.norm(x)
    y = np.asarray(y_axis, float); y /= np.linalg.norm(y)
    z = np.cross(x, y) if z_axis is None else np.asarray(z_axis, float)
    z /= np.linalg.norm(z)
    c = np.asarray(center, float)
    hx, hy, hz = (s / 2.0 for s in size)
    vs = [c + sx * hx * x + sy * hy * y + sz * hz * z for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return _obj(name, vs, faces, coll, [mat] if mat else [])


def _cyl(name, coll, mat, base, axis, radius, height, n=20, r_top=None):
    axis = np.asarray(axis, float); axis /= np.linalg.norm(axis)
    t = np.cross(axis, [0.0, 0.0, 1.0] if abs(axis[2]) < 0.9 else [1.0, 0.0, 0.0]); t /= np.linalg.norm(t)
    b = np.cross(axis, t)
    rt = radius if r_top is None else r_top
    base = np.asarray(base, float)
    vs = []
    for k in range(n):
        a = 2 * math.pi * k / n
        d = math.cos(a) * t + math.sin(a) * b
        vs.append(base + radius * d)
        vs.append(base + axis * height + rt * d)
    faces = [(2 * k, 2 * ((k + 1) % n), 2 * ((k + 1) % n) + 1, 2 * k + 1) for k in range(n)]
    faces.append(tuple(2 * k + 1 for k in range(n)))
    faces.append(tuple(2 * k for k in reversed(range(n))))
    return _obj(name, vs, faces, coll, [mat] if mat else [], smooth=True)


# ---------------------------------------------------------------------------------------------------------------
# materials

def _mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes["Principled BSDF"]


def _noise(nodes, links, vec_src, scale, detail=4.0, rough=0.6):
    n = nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    if vec_src is not None:
        links.new(vec_src, n.inputs["Vector"])
    return n


def _math(nodes, links, op, a, b=None, clamp=False):
    m = nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            links.new(v, m.inputs[i])
    return m.outputs[0]


def _mix_rgb(nodes, links, fac, c1, c2, blend="MIX"):
    m = nodes.new("ShaderNodeMix")
    m.data_type = "RGBA"
    m.blend_type = blend
    for sock, v in ((m.inputs[0], fac), (m.inputs[6], c1), (m.inputs[7], c2)):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            sock.default_value = (*v, 1.0) if len(v) == 3 else v
        else:
            links.new(v, sock)
    return m.outputs[2]


def _world_pos(nodes):
    return nodes.new("ShaderNodeNewGeometry").outputs["Position"]


def shingle_material(color, style, seed):
    m, nodes, links, bsdf = _mat("Shingles")
    uv = nodes.new("ShaderNodeTexCoord").outputs["UV"]
    base = srgb_to_linear(color)
    dark = tuple(c * 0.55 for c in base)
    light = tuple(min(1.0, c * 1.25) for c in base)
    if style == "three_tab":
        widths, row = (0.3333, 0.3333), 0.127
    else:
        widths, row = (0.23, 0.37), 0.143
    bricks = []
    for k, w in enumerate(widths):
        br = nodes.new("ShaderNodeTexBrick")
        br.offset = 0.5 if k == 0 else 0.31
        br.offset_frequency = 1 if k == 0 else 2
        br.squash = 1.0
        br.inputs["Scale"].default_value = 1.0
        br.inputs["Brick Width"].default_value = w
        br.inputs["Row Height"].default_value = row
        br.inputs["Mortar Size"].default_value = 0.0045 if k == 0 else 0.0
        br.inputs["Mortar Smooth"].default_value = 0.2
        br.inputs["Bias"].default_value = -0.1 + 0.2 * k
        br.inputs["Color1"].default_value = (*dark, 1.0) if style != "three_tab" else (*base, 1.0)
        br.inputs["Color2"].default_value = (*light, 1.0) if style != "three_tab" else (*[c * 0.85 for c in base], 1.0)
        br.inputs["Mortar"].default_value = (*[c * 0.25 for c in base], 1.0)
        links.new(uv, br.inputs["Vector"])
        bricks.append(br)
    col = bricks[0].outputs["Color"]
    if style != "three_tab":
        col = _mix_rgb(nodes, links, 0.45, col, bricks[1].outputs["Color"])
        col = _mix_rgb(nodes, links, bricks[0].outputs["Fac"], col, tuple(c * 0.25 for c in base))
    gran = _noise(nodes, links, uv, 420.0, 6.0, 0.7)
    speck = _math(nodes, links, "MULTIPLY_ADD", gran.outputs["Fac"], 0.7)
    speck.node.inputs[2].default_value = 0.65
    blotch = _noise(nodes, links, uv, 1.3, 3.0, 0.5)
    tone = _math(nodes, links, "MULTIPLY_ADD", blotch.outputs["Fac"], 0.35)
    tone.node.inputs[2].default_value = 0.82
    col = _mix_rgb(nodes, links, 1.0, col, speck, "MULTIPLY")
    col = _mix_rgb(nodes, links, 1.0, col, tone, "MULTIPLY")
    links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.004
    h = _math(nodes, links, "ADD", _math(nodes, links, "SUBTRACT", 1.0, bricks[0].outputs["Fac"]),
              _math(nodes, links, "MULTIPLY", gran.outputs["Fac"], 0.25))
    links.new(h, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def siding_material(color, exposure, foundation_h):
    m, nodes, links, bsdf = _mat("Siding")
    pos = _world_pos(nodes)
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(pos, sep.inputs[0])
    lap = _math(nodes, links, "FRACT", _math(nodes, links, "DIVIDE", sep.outputs["Z"], exposure))
    base = srgb_to_linear(color)
    grain = _noise(nodes, links, pos, 60.0, 5.0, 0.6)
    tone = _math(nodes, links, "MULTIPLY_ADD", grain.outputs["Fac"], 0.25)
    tone.node.inputs[2].default_value = 0.87
    shade = _math(nodes, links, "MULTIPLY_ADD", lap, 0.18)
    shade.node.inputs[2].default_value = 0.86
    col = _mix_rgb(nodes, links, 1.0, base, tone, "MULTIPLY")
    col = _mix_rgb(nodes, links, 1.0, col, shade, "MULTIPLY")
    conc = _noise(nodes, links, pos, 25.0, 8.0, 0.65)
    concol = _mix_rgb(nodes, links, conc.outputs["Fac"], (0.30, 0.29, 0.27), (0.48, 0.47, 0.44))
    below = _math(nodes, links, "LESS_THAN", sep.outputs["Z"], foundation_h)
    col = _mix_rgb(nodes, links, below, col, concol)
    links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.01
    links.new(_math(nodes, links, "MULTIPLY", lap, _math(nodes, links, "SUBTRACT", 1.0, below)), bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def flat_material(name, color, rough=0.5, metal=0.0, noise=0.12, scale=40.0):
    m, nodes, links, bsdf = _mat(name)
    base = srgb_to_linear(color) if max(color) > 1.0 else tuple(color)
    if noise > 0:
        n = _noise(nodes, links, _world_pos(nodes), scale, 6.0, 0.6)
        t = _math(nodes, links, "MULTIPLY_ADD", n.outputs["Fac"], 2 * noise)
        t.node.inputs[2].default_value = 1.0 - noise
        links.new(_mix_rgb(nodes, links, 1.0, base, t, "MULTIPLY"), bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return m


def grass_material():
    m, nodes, links, bsdf = _mat("Lawn")
    pos = _world_pos(nodes)
    big = _noise(nodes, links, pos, 0.08, 4.0, 0.6)
    mid = _noise(nodes, links, pos, 1.5, 6.0, 0.7)
    fine = _noise(nodes, links, pos, 140.0, 4.0, 0.8)
    c = _mix_rgb(nodes, links, big.outputs["Fac"], (0.035, 0.085, 0.015), (0.10, 0.12, 0.035))
    c = _mix_rgb(nodes, links, _math(nodes, links, "POWER", mid.outputs["Fac"], 3.0), c, (0.16, 0.13, 0.06))
    t = _math(nodes, links, "MULTIPLY_ADD", fine.outputs["Fac"], 0.9)
    t.node.inputs[2].default_value = 0.55
    links.new(_mix_rgb(nodes, links, 1.0, c, t, "MULTIPLY"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def glass_material():
    m, nodes, links, bsdf = _mat("Window glass")
    bsdf.inputs["Base Color"].default_value = (0.012, 0.014, 0.018, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.04
    bsdf.inputs["Specular IOR Level"].default_value = 0.8
    return m


def checker_material():
    m, nodes, links, bsdf = _mat("Scale marker")
    ck = nodes.new("ShaderNodeTexChecker")
    ck.inputs["Scale"].default_value = 8.0
    ck.inputs["Color1"].default_value = (0.85, 0.85, 0.85, 1.0)
    ck.inputs["Color2"].default_value = (0.01, 0.01, 0.01, 1.0)
    links.new(nodes.new("ShaderNodeTexCoord").outputs["UV"], ck.inputs["Vector"])
    links.new(ck.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    return m


# ---------------------------------------------------------------------------------------------------------------
# geometry builders

def build_roof(house, coll, mats):
    verts, faces, uvs = [], [], []
    for f in house["facets"]:
        e = np.array(f["frame"]["eave"]); up = np.array(f["frame"]["up"])
        for poly in f["rings"]:
            if poly["holes"]:
                raise NotImplementedError("roof facets with holes are not built yet")
            ring = poly["outer"]
            off = len(verts)
            for v in ring:
                v = np.asarray(v, float)
                verts.append(v)
                uvs.append((float(np.dot(v, e)), float(np.dot(v, up))))
            faces.append(list(range(off, off + len(ring))))
    ob = _obj("Roof surface (measured)", verts, faces, coll, [mats["shingle"], mats["soffit"], mats["trim"]], uvs)
    for p in ob.data.polygons:
        if p.normal.z < 0:
            p.flip()
    ob.data.update()
    sol = ob.modifiers.new("Deck thickness", "SOLIDIFY")
    sol.thickness = ROOF_DECK_M
    sol.offset = -1.0
    sol.use_even_offset = True
    sol.material_offset = 1
    sol.material_offset_rim = 2
    ob["measured_surface"] = "base mesh faces (before modifiers) are the answer-key roof facets"
    return ob


def roof_surface_area(ob):
    return sum(p.area for p in ob.data.polygons)


def _line_items(key, kind):
    return [l for l in key["lines"] if l["kind"] == kind]


def build_trim(house, key, coll, mats):
    facets = {f["id"]: f for f in house["facets"]}
    for k, l in enumerate(_line_items(key, "eave")):
        p0, p1 = np.array(l["p0"]), np.array(l["p1"])
        along = p1 - p0; L = np.linalg.norm(along); along /= L
        up = np.array(facets[l["facets"][0]]["frame"]["up"])
        out = -np.array([up[0], up[1], 0.0]); out /= np.linalg.norm(out)
        top = p0[2] - ROOF_DECK_M
        mid = (p0 + p1) / 2
        # fascia board (vertical), its face 1.5 cm inside the drip edge
        c = mid - out * (0.015 + FASCIA_T / 2)
        c[2] = top - FASCIA_H / 2
        _box(f"Fascia {k}", coll, mats["trim"], c, along, out, (L, FASCIA_T, FASCIA_H), z_axis=[0, 0, 1])
        build_gutter(f"Gutter {k}", coll, mats["gutter"], p0 - out * 0.015, p1 - out * 0.015, along, out, top - 0.01)
        overhang = next((e["overhang_m"] for e in key["materials"]["ice_and_water"]["eaves"]
                         if e["facet"] == l["facets"][0] and abs(e["length_ft"] - l["length_ft"]) < 1e-6), 0.4)
        build_downspouts(k, coll, mats["gutter"], p0 - out * 0.015, p1 - out * 0.015, along, out, top - 0.01 - GUTTER_H,
                         overhang, house)
    for k, l in enumerate(_line_items(key, "rake")):
        p0, p1 = np.array(l["p0"]), np.array(l["p1"])
        f = facets[l["facets"][0]]
        e = np.array(f["frame"]["eave"])
        mid = (p0 + p1) / 2
        centroid = np.mean(np.asarray(f["rings"][0]["outer"], float), axis=0)
        out = e if np.dot(mid - centroid, e) > 0 else -e
        along = p1 - p0; L = np.linalg.norm(along); along /= L
        c = mid - out * (0.015 + FASCIA_T / 2) - np.array([0, 0, ROOF_DECK_M + FASCIA_H / 2])
        zax = np.cross(along, out); zax = zax if zax[2] > 0 else -zax
        _box(f"Rake board {k}", coll, mats["trim"], c, along, out, (L, FASCIA_T, FASCIA_H), z_axis=zax)
    for k, l in enumerate(_line_items(key, "ridge") + _line_items(key, "hip")):
        p0, p1 = np.array(l["p0"]), np.array(l["p1"])
        along = p1 - p0; L = np.linalg.norm(along); along /= L
        side = np.cross([0, 0, 1.0], along); side /= np.linalg.norm(side)
        zax = np.cross(along, side)
        _box(f"Ridge cap {k}", coll, mats["cap"], (p0 + p1) / 2 + zax * 0.012, along, side, (L, 0.30, 0.035), z_axis=zax)


def build_gutter(name, coll, mat, a, b, along, out, top_z):
    prof = [(0, 0), (0, -GUTTER_H), (GUTTER_W, -GUTTER_H), (GUTTER_W, 0.01), (GUTTER_W - 0.006, 0.01),
            (GUTTER_W - 0.006, -GUTTER_H + 0.004), (0.004, -GUTTER_H + 0.004), (0.004, 0)]
    vs = []
    for end in (a, b):
        for (o, z) in prof:
            p = np.array([end[0], end[1], 0.0]) + out * o
            p[2] = top_z + z
            vs.append(p)
    n = len(prof)
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    faces += [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    _obj(name, vs, faces, coll, [mat])


def build_downspouts(k, coll, mat, a, b, along, out, bottom_z, overhang, house):
    L = np.linalg.norm(b - a)
    rake = house["spec"]["wings"][0]["rake_overhang"]
    ends = [a + along * (rake + 0.25)] + ([b - along * (rake + 0.25)] if L > 10.0 else [])
    for j, p in enumerate(ends):
        outlet = p + out * (GUTTER_W / 2)
        wall = p - out * (overhang - 0.06)
        z_mid = bottom_z - 0.35
        o2 = outlet.copy(); o2[2] = bottom_z
        w2 = wall.copy(); w2[2] = z_mid
        d = w2 - o2; Ld = np.linalg.norm(d)
        _box(f"Downspout {k}.{j} elbow", coll, mat, (o2 + w2) / 2, d, along, (Ld, 0.075, 0.055))
        c = wall.copy(); c[2] = (z_mid + 0.25) / 2
        _box(f"Downspout {k}.{j}", coll, mat, c, along, out, (0.075, 0.055, z_mid - 0.25), z_axis=[0, 0, 1])
        kick = wall + out * 0.25; kick[2] = 0.15
        _box(f"Downspout {k}.{j} kick-out", coll, mat, kick, out, along, (0.5, 0.075, 0.055))


def build_walls(house, coll, mats, rng):
    sp = house["spec"]
    fh = sp["materials"]["foundation_height_m"]
    plate = house["heights"]["plate_m"]
    for w in house["walls"]:
        P = np.asarray(w["polygon"], float)
        _obj(f"Wall {w['id']}", P, [list(range(len(P)))], coll, [mats["siding"]])
        b = math.radians(w["bearing"])
        n = np.array([math.sin(b), math.cos(b), 0.0])
        a0, a1 = P[0], P[1]
        along = a1 - a0; Lw = np.linalg.norm(along); along /= Lw
        is_front = float(np.dot(n[:2], house["front_dir"])) > 0.7
        storeys = sp["storeys"]
        floors = [fh + 0.0] + ([fh + 3.0] if storeys == 2 else [])
        gable = len(P) > 4
        nwin = max(1, int(Lw // (3.6 if not gable else 4.5)))
        slots = [(i + 0.5) / nwin for i in range(nwin)]
        door_slot = None
        if is_front:
            door_slot = int(rng.integers(len(slots)))
        for fi, fz in enumerate(floors):
            for si, s in enumerate(slots):
                u = s * Lw + rng.uniform(-0.3, 0.3)
                if fi == 0 and si == door_slot:
                    build_opening(f"Front door {w['id']}", coll, mats, a0, along, n, u, fz, 0.91, 2.03, door=True)
                    continue
                ww, wh = float(rng.uniform(0.8, 1.3)), float(rng.uniform(1.1, 1.5))
                sill = fz + 0.9
                if sill + wh > (plate if not gable else plate + 1.5) - 0.25:
                    continue
                if u - ww / 2 < 0.5 or u + ww / 2 > Lw - 0.5:
                    continue
                build_opening(f"Window {w['id']} {fi}.{si}", coll, mats, a0, along, n, u, sill, ww, wh)
        if gable:
            apex = P[np.argmax(P[:, 2])]
            u = float(np.dot(apex - a0, along))
            build_opening(f"Gable vent {w['id']}", coll, mats, a0, along, n, u, apex[2] - 1.4, 0.6, 0.6, vent=True)


def build_opening(name, coll, mats, a0, along, n, u, z0, w, h, door=False, vent=False):
    base = a0 + along * u
    c = base.copy(); c[2] = z0 + h / 2
    _box(name + " trim", coll, mats["trim"], c + n * 0.015, along, [0, 0, 1], (w + 0.14, h + 0.14, 0.03), z_axis=n)
    inner = mats["door"] if door else (mats["vent"] if vent else mats["glass"])
    _box(name, coll, inner, c + n * 0.02, along, [0, 0, 1], (w, h, 0.03), z_axis=n)
    if not door and not vent:
        _box(name + " mullion", coll, mats["trim"], c + n * 0.037, along, [0, 0, 1], (w, 0.04, 0.01), z_axis=n)


def build_details(house, coll, mats):
    for k, d in enumerate(house["details"]):
        c = np.array(d["center"]); n = np.array(d["normal"]); e = np.array(d["eave_dir"]); up = np.array(d["up_dir"])
        if d["kind"] == "box_vent":
            _box(f"Box vent {k} flashing", coll, mats["vent"], c + n * 0.004, e, up, (d["base_m"], d["base_m"], 0.008),
                 z_axis=n)
            _box(f"Box vent {k}", coll, mats["vent"], c + n * (d["height_m"] / 2), e, up,
                 (d["hood_m"], d["hood_m"], d["height_m"]), z_axis=n)
        elif d["kind"] == "pipe_boot":
            _box(f"Pipe boot {k} flashing", coll, mats["boot"], c + n * 0.004, e, up, (d["base_m"], d["base_m"], 0.008),
                 z_axis=n)
            _cyl(f"Pipe boot {k}", coll, mats["boot"], c, [0, 0, 1], d["pipe_d_m"] * 0.9 + 0.03, 0.14,
                 r_top=d["pipe_d_m"] / 2 + 0.005)
            _cyl(f"Vent pipe {k}", coll, mats["pipe"], c, [0, 0, 1], d["pipe_d_m"] / 2, d["height_m"])
    for k, r in enumerate(house.get("ridge_vents", [])):
        p0, p1 = np.array(r["p0"]), np.array(r["p1"])
        along = p1 - p0; L = np.linalg.norm(along); along /= L
        side = np.cross([0, 0, 1.0], along); side /= np.linalg.norm(side)
        _box(f"Ridge vent {k}", coll, mats["cap"], (p0 + p1) / 2 + np.array([0, 0, r["height_m"] / 2 + 0.012]), along,
             side, (L, r["width_m"], r["height_m"]))


def build_markers(house, coll, mat):
    for m in house["markers"]:
        c = np.array(m["center"]); ax = np.array(m["x_axis"]); ay = np.array(m["y_axis"]); n = np.array(m["normal"])
        s = m["size_m"] / 2
        corners = [c - ax * s - ay * s, c + ax * s - ay * s, c + ax * s + ay * s, c - ax * s + ay * s]
        bottom = [p - n * 0.006 for p in corners]
        vs = corners + bottom
        faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)] * 2
        ob = _obj(f"Scale marker {m['id']}", vs, faces, coll, [mat], uvs)
        ob["size_m"] = m["size_m"]
        ob["note"] = "8 x 8 checkerboard; printed face = first 4 vertices (corners in answer_key.json)"


def build_site(house, coll, mats, rng):
    half = 150.0
    _obj("Lawn", [(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [(0, 1, 2, 3)], coll,
         [mats["lawn"]])
    sp = house["spec"]; w = sp["wings"][0]
    fd = np.array(house["front_dir"] + [0.0])
    az = math.radians(w["azimuth"])
    u = np.array([math.sin(az), math.cos(az), 0.0])
    yard = w["width"] / 2 + w["eave_overhang"] + float(rng.uniform(7.0, 11.0))
    street_c = fd * (yard + 1.5 + 4.5)
    _box("Street", coll, mats["asphalt"], street_c + np.array([0, 0, 0.0015]), u, fd, (240.0, 9.0, 0.003))
    _box("Sidewalk", coll, mats["concrete"], fd * (yard + 0.75) + np.array([0, 0, 0.0025]), u, fd, (240.0, 1.5, 0.005))
    side = float(rng.choice([-1.0, 1.0]))
    dw_u = side * (w["length"] / 2 - 3.2)
    start = fd * (w["width"] / 2) + u * dw_u
    depth = yard - w["width"] / 2
    _box("Driveway", coll, mats["concrete"], start + fd * depth / 2 + np.array([0, 0, 0.002]), u, fd,
         (5.5, depth, 0.004))
    walk_u = -side * w["length"] / 6
    s2 = fd * (w["width"] / 2) + u * walk_u
    _box("Front walk", coll, mats["concrete"], s2 + fd * depth / 2 + np.array([0, 0, 0.0022]), u, fd,
         (1.1, depth, 0.0044))


def setup_world(house):
    sc = bpy.context.scene
    lt = house["spec"]["lighting"]
    world = bpy.data.worlds.new("Sky")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(lt["sun_elevation_deg"])
    sky.sun_rotation = math.radians(90.0 - lt["sun_azimuth_deg"])     # Blender: 0 = +X, CCW; compass: 0 = N, CW
    sky.air_density = lt["air_density"]
    sky.aerosol_density = lt["aerosol_density"]
    bg = nodes["Background"]
    bg.inputs["Strength"].default_value = 0.25
    links.new(sky.outputs["Color"], bg.inputs["Color"])
    sun_d = bpy.data.lights.new("Sun", "SUN")
    sun_d.energy = 4.5
    sun_d.angle = math.radians(0.53)
    sun = bpy.data.objects.new("Sun", sun_d)
    sc.collection.objects.link(sun)
    az, el = math.radians(lt["sun_azimuth_deg"]), math.radians(lt["sun_elevation_deg"])
    to_sun = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
    sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()


def setup_render(samples=64, device="auto", seed=0):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.seed = seed
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "None"
    except Exception:
        pass
    used = "CPU"
    if device in ("auto", "gpu"):
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dt in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = dt
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == dt]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type == dt
                    sc.cycles.device = "GPU"
                    used = dt
                    break
            except Exception:
                continue
    if used == "CPU":
        sc.cycles.device = "CPU"
    return used


def build(house: dict, key: dict, blend_path: str | None = None) -> dict:
    """Build the full scene from house.json + answer_key.json; optionally save it. Returns build facts."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    rng = np.random.default_rng(house["spec"]["seed"] + 104729)
    mt = house["spec"]["materials"]
    mats = {
        "shingle": shingle_material(mt["shingle_color"], mt["shingle_style"], house["spec"]["seed"]),
        "cap": shingle_material([c * 0.85 for c in mt["shingle_color"]], "three_tab", house["spec"]["seed"]),
        "siding": siding_material(mt["siding_color"], mt["siding_exposure_m"], mt["foundation_height_m"]),
        "trim": flat_material("Trim", mt["trim_color"], 0.45, noise=0.05),
        "soffit": flat_material("Soffit", mt["trim_color"], 0.6, noise=0.06),
        "gutter": flat_material("Gutter", mt["gutter_color"], 0.35, metal=0.2, noise=0.03),
        "glass": glass_material(),
        "door": flat_material("Door", [(150, 30, 30), (30, 30, 34), (40, 60, 90), (120, 80, 50)][int(rng.integers(4))],
                              0.4, noise=0.04),
        "vent": flat_material("Vent metal", (45, 42, 40), 0.5, metal=0.4, noise=0.08),
        "boot": flat_material("Pipe boot", (30, 30, 30), 0.7, noise=0.05),
        "pipe": flat_material("PVC pipe", (205, 205, 198), 0.4, noise=0.03),
        "lawn": grass_material(),
        "concrete": flat_material("Concrete", (150, 147, 140), 0.8, noise=0.22, scale=12.0),
        "asphalt": flat_material("Asphalt", (52, 52, 54), 0.9, noise=0.25, scale=30.0),
        "marker": checker_material(),
    }
    house_c = _coll("House")
    roof = build_roof(house, house_c, mats)
    build_trim(house, key, _coll("Trim and gutters"), mats)
    build_walls(house, _coll("Walls and openings"), mats, rng)
    build_details(house, _coll("Roof details"), mats)
    build_markers(house, _coll("Scale markers"), mats["marker"])
    build_site(house, _coll("Site"), mats, rng)
    setup_world(house)
    area = roof_surface_area(roof)
    want = key["totals"]["roof_area_m2"]
    if abs(area - want) > 1e-6 * max(1.0, want):
        raise AssertionError(f"Blender roof surface {area:.6f} m2 != answer key {want:.6f} m2")
    sc["answer_key_roof_area_m2"] = want
    if blend_path:
        bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    return {"roof_area_blender_m2": area, "roof_area_key_m2": want, "objects": len(bpy.data.objects)}
