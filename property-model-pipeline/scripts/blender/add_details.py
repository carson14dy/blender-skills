"""Add the rest of the house to a measured model: openings, trim, gutters, decks, stairs, railings.

    python add_details.py MODEL.blend details.json OUT.blend   (bpy module, or blender -b -P ... --)

Works on a scene built by build_model.py (collections "Roof facets", "Walls", "Roof edges") and
the project's model.json (walls with bottom/profile; edges with kind/p0/p1). Everything added
lives in collection "Details" so measurements are untouched: these objects are presentation
geometry, placed from photo measurements. details.json (metres, model frame):

{
  "model_json": "path/to/model.json",
  "siding": {"exposure": 0.1803, "color": [0.42, 0.42, 0.30]},
  "roof": {"exposure": 0.1429, "color": [0.17, 0.17, 0.18]},          # shingle course lines
  "trim_color": [0.85, 0.85, 0.82], "deck_color": [0.07, 0.12, 0.09],
  "fascia_height": 0.2, "gutters": true, "soffits": true,
  "foundation": {"default_reveal": 0.25, "walls": {"M:-u": 0.54, "M:+v": 0.62}},   # siding-bottom z per wall
  "openings": [ {"wall": "M:-u", "u": 9.98, "sill_z": 1.55, "width": 1.56, "height": 1.52,
                 "kind": "window|slider|door|garage|egress", "label": "..."} ],      # u = distance from wall start
  "decks": [ {"polygon": [[x,y],...], "top_z": 0.95, "rail_edges": [[i,j],...], "rail_gaps": [[x0,y0,x1,y1]],
              "rail_height": 0.9, "post_spacing": 2.0} ],
  "stairs": [ {"top": [x,y], "dir": [dx,dy], "width": 1.0, "top_z": 0.95, "bottom_z": 0.2, "risers": 4} ],
  "ceilings": [ {"polygon": [[x,y],...], "z": 3.19} ],
  "boxes": [ {"name": "...", "min": [x,y,z], "max": [x,y,z], "material": "brick|concrete|trim|deck"} ],
  "downspouts": [ {"xy": [x,y], "top_z": 3.5, "bottom_z": 0.2} ],
  "roof_vents": [ {"xy": [x,y], "size": 0.32} ],        # placed on the roof surface; ridge caps are automatic
  "corner_boards": true,
  "lights": [ {"wall": "M:-v", "u": 5.4, "z": 2.9} ],
  "text": [ {"wall": "G:+u", "u": 0.5, "z": 0.9, "text": "1601", "size": 0.16} ]
}
Walls are named "<wing>:<side>" as in model.json (e.g. "M:-u"); u runs from bottom[0] to bottom[1].
"""
import json
import math
import sys

import bpy
from mathutils import Vector


def args():
    a = globals().get("PM_ARGS")
    if a is None:
        a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return a


def coll(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def mat(name, rgb, rough=0.7, metal=0.0, alpha=1.0, emission=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        try:
            m.blend_method = "BLEND"
        except AttributeError:
            pass
    m.diffuse_color = (*rgb, alpha)
    return m


def siding_material(rgb, exposure):
    """Lap siding: colour + horizontal shadow lines every `exposure` metres (bump from world Z)."""
    m = mat("Siding (lap)", rgb, rough=0.85)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = exposure
    fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "FRACT"
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], div.inputs[0])
    nt.links.new(div.outputs[0], fr.inputs[0])
    nt.links.new(fr.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def shingle_material(rgb, exposure, slope):
    """Asphalt shingles: course shadow lines every `exposure` metres up the slope (bump from world Z)."""
    m = mat("Roof shingle (courses)", rgb, rough=0.9)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"
    div.inputs[1].default_value = exposure * slope / math.sqrt(1 + slope * slope)   # vertical spacing
    fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "FRACT"
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.5
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], div.inputs[0])
    nt.links.new(div.outputs[0], fr.inputs[0])
    nt.links.new(fr.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mesh(name, verts, faces, c, m):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    ob.data.materials.append(m)
    return ob


def box(name, lo, hi, c, m):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return mesh(name, v, f, c, m)


def oriented_box(name, origin, ex, ey, ez, c, m):
    """Box spanned by vectors ex, ey, ez from origin."""
    o = Vector(origin)
    ex, ey, ez = Vector(ex), Vector(ey), Vector(ez)
    v = [o, o + ex, o + ex + ey, o + ey, o + ez, o + ex + ez, o + ex + ey + ez, o + ey + ez]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return mesh(name, v, f, c, m)


def wall_frames(model):
    """{'M:-u': (start, along_unit, outward_unit, length, bottom_z(u))}"""
    out = {}
    for w in model["walls"]:
        a, b = Vector(w["bottom"][0]), Vector(w["bottom"][1])
        d = Vector((b.x - a.x, b.y - a.y, 0))
        L = d.length
        d.normalize()
        t = math.radians(w["bearing"])
        n = Vector((math.sin(t), math.cos(t), 0))
        za, zb = a.z, b.z
        out[f'{w["wing"]}:{w["side"]}'] = (Vector((a.x, a.y, 0)), d, n, L, lambda u, za=za, zb=zb, L=L: za + (zb - za) * u / max(L, 1e-9))
    return out


def add_opening(o, frames, c, mats):
    a, d, n, L, _ = frames[o["wall"]]
    w, h = o["width"], o["height"]
    u0 = o["u"] - w / 2
    base = a + d * u0 + Vector((0, 0, o["sill_z"]))
    kind = o.get("kind", "window")
    T, D = 0.07, 0.04          # frame width, frame projection
    name = o.get("label", kind)[:40]
    # recessed glass / door leaf, slightly proud of the wall so it never z-fights
    leaf = mats["glass"] if kind in ("window", "slider", "egress") else (mats["garage"] if kind == "garage" else mats["door"])
    if kind == "slider" and h > 1.6:   # patio door: glass leaf
        leaf = mats["glass"]
    oriented_box(f"{name} leaf", base + n * 0.005, d * w, n * 0.01, Vector((0, 0, h)), c, leaf)
    # frame (4 bars)
    fm = mats["trim"]
    oriented_box(f"{name} head", base + d * (-T) + Vector((0, 0, h)), d * (w + 2 * T), n * D, Vector((0, 0, T)), c, fm)
    if kind not in ("door", "garage"):
        oriented_box(f"{name} sill", base + d * (-T) + Vector((0, 0, -T)), d * (w + 2 * T), n * (D + 0.02), Vector((0, 0, T)), c, fm)
    oriented_box(f"{name} jamb L", base + d * (-T), d * T, n * D, Vector((0, 0, h)), c, fm)
    oriented_box(f"{name} jamb R", base + d * w, d * T, n * D, Vector((0, 0, h)), c, fm)
    if kind in ("window", "slider") and h <= 1.6:   # meeting rail of a 2-lite slider
        oriented_box(f"{name} mullion", base + d * (w / 2 - 0.02), d * 0.04, n * 0.02, Vector((0, 0, h)), c, fm)
    if kind == "garage":   # 4 horizontal section joints
        for k in range(1, 4):
            oriented_box(f"{name} joint {k}", base + n * 0.016 + Vector((0, 0, h * k / 4 - 0.006)), d * w, n * 0.004, Vector((0, 0, 0.012)), c, mats["shadow"])


def add_trim(model, frames, c, mats, fascia_h, gutters, soffits):
    for i, e in enumerate(model["edges"]):
        if e["kind"] not in ("eave", "rake") or e["length_m"] < 0.15:
            continue
        p0, p1 = Vector(e["p0"]), Vector(e["p1"])
        d = (p1 - p0)
        dh = Vector((d.x, d.y, 0))
        if dh.length < 1e-6:
            continue
        # outward = away from the facet the edge belongs to
        fid = e["facets"][0]
        f = next(f for f in model["facets"] if f["id"] == fid)
        cx = sum(v[0] for p in f["polygons"] for v in p["outer"]) / sum(len(p["outer"]) for p in f["polygons"])
        cy = sum(v[1] for p in f["polygons"] for v in p["outer"]) / sum(len(p["outer"]) for p in f["polygons"])
        nrm = Vector((dh.y, -dh.x, 0)).normalized()
        mid = (p0 + p1) / 2
        if (Vector((cx, cy, 0)) - Vector((mid.x, mid.y, 0))).dot(nrm) > 0:
            nrm = -nrm
        down = Vector((0, 0, -fascia_h))
        # fascia: a thin board just inside the roof edge
        oriented_box(f"fascia {i}", p0 - nrm * 0.03, d, nrm * 0.03, down, c, mats["trim"])
        if e["kind"] == "eave":
            if gutters:
                g0 = p0 + nrm * 0.005 + Vector((0, 0, -0.03))
                oriented_box(f"gutter {i}", g0, d, nrm * 0.13, Vector((0, 0, -0.12)), c, mats["gutter"])
            if soffits:
                # horizontal soffit from the fascia back to the nearest parallel wall face (<= 2.5 m)
                best = None
                for k, (a, wd, wn, L, _) in frames.items():
                    if abs(wd.dot(dh.normalized())) < 0.99:
                        continue
                    dist = (Vector((mid.x, mid.y, 0)) - a).dot(wn)
                    along = (Vector((mid.x, mid.y, 0)) - a).dot(wd)
                    if 0.05 < dist < 2.5 and -0.5 < along < L + 0.5 and (best is None or dist < best):
                        best = dist
                if best:
                    z = min(p0.z, p1.z) - fascia_h
                    s0 = Vector((p0.x, p0.y, z)) - nrm * 0.03
                    oriented_box(f"soffit {i}", s0, Vector((d.x, d.y, 0)), -nrm * (best - 0.03), Vector((0, 0, -0.012)), c, mats["soffit"])


def add_foundation(frames, fnd, c, mats):
    for k, (a, d, n, L, zb) in frames.items():
        top = fnd.get("walls", {}).get(k)
        steps = 12
        verts, faces = [], []
        for s in range(steps + 1):
            u = L * s / steps
            p = a + d * u + n * 0.015
            z0 = zb(u)
            z1 = top if top is not None else z0 + fnd.get("default_reveal", 0.25)
            verts += [(p.x, p.y, z0 - 0.15), (p.x, p.y, max(z1, z0))]
        for s in range(steps):
            i = 2 * s
            faces.append([i, i + 2, i + 3, i + 1])
        mesh(f"foundation {k}", verts, faces, c, mats["concrete"])


def add_deck(dk, c, mats, idx):
    poly = [Vector((x, y, 0)) for x, y in dk["polygon"]]
    z = dk["top_z"]
    t = 0.04
    top = [(p.x, p.y, z) for p in poly]
    bot = [(p.x, p.y, z - t) for p in poly]
    n = len(poly)
    faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    mesh(f"deck {idx} boards", top + bot, faces, c, mats["deck"])
    # rim joist + support posts
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        oriented_box(f"deck {idx} rim {i}", a + Vector((0, 0, z - t - 0.24)), b - a, Vector((0, 0, 0)) + (b - a).cross(Vector((0, 0, 1))).normalized() * -0.04, Vector((0, 0, 0.24)), c, mats["deck"])
    sp = dk.get("post_spacing", 2.0)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        L = (b - a).length
        for s in range(int(L // sp) + 1):
            p = a + (b - a) * (s * sp / max(L, 1e-9))
            box(f"deck {idx} post", (p.x - 0.045, p.y - 0.045, dk.get("grade_z", 0.2)), (p.x + 0.045, p.y + 0.045, z - t), c, mats["deck"])
    # railings
    H = dk.get("rail_height", 0.9)
    gaps = dk.get("rail_gaps", [])
    for (i, j) in dk.get("rail_edges", []):
        a, b = poly[i], poly[j]
        L = (b - a).length
        u = (b - a) / max(L, 1e-9)
        segs = [(0.0, L)]
        for g in gaps:
            g0, g1 = Vector((g[0], g[1], 0)), Vector((g[2], g[3], 0))
            t0, t1 = sorted([(g0 - a).dot(u), (g1 - a).dot(u)])
            if (g0 - a).cross(u).length < 0.3 and t1 > 0 and t0 < L:
                segs = [s for seg in segs for s in ((seg[0], min(seg[1], t0)), (max(seg[0], t1), seg[1])) if s[1] - s[0] > 0.05]
        for s0, s1 in segs:
            pa = a + u * s0 + Vector((0, 0, z))
            pb = a + u * s1 + Vector((0, 0, z))
            side = u.cross(Vector((0, 0, 1))).normalized() * 0.07
            oriented_box(f"deck {idx} rail top", pa + Vector((0, 0, H - 0.07)) - side / 2, pb - pa, side, Vector((0, 0, 0.07)), c, mats["deck"])
            oriented_box(f"deck {idx} rail bottom", pa + Vector((0, 0, 0.08)) - side / 2, pb - pa, side * 0.6, Vector((0, 0, 0.05)), c, mats["deck"])
            for pend in (pa, pb):
                box(f"deck {idx} rail post", (pend.x - 0.045, pend.y - 0.045, z), (pend.x + 0.045, pend.y + 0.045, z + H + 0.05), c, mats["deck"])
            nb = int((s1 - s0) / 0.13)
            for k in range(1, nb):
                q = pa + (pb - pa) * (k / nb)
                box(f"deck {idx} baluster", (q.x - 0.02, q.y - 0.02, z + 0.08), (q.x + 0.02, q.y + 0.02, z + H - 0.07), c, mats["deck"])


def add_stairs(st, c, mats, idx):
    top = Vector((*st["top"], 0))
    dvec = Vector((*st["dir"], 0)).normalized()
    side = dvec.cross(Vector((0, 0, 1))).normalized()
    W, r = st["width"], st["risers"]
    rise = (st["top_z"] - st["bottom_z"]) / r
    run = st.get("run", 0.27)
    for k in range(1, r):
        z = st["top_z"] - k * rise
        p0 = top + dvec * (run * (k - 1)) - side * (W / 2) + Vector((0, 0, z - 0.04))
        oriented_box(f"stair {idx} tread {k}", p0, dvec * run, side * W, Vector((0, 0, 0.04)), c, mats["deck"])
    for sgn in (-1, 1):   # stringers
        p0 = top - side * (sgn * W / 2) + Vector((0, 0, st["bottom_z"]))
        oriented_box(f"stair {idx} stringer", p0, dvec * run * (r - 1), side * 0.05 * sgn, Vector((0, 0, st["top_z"] - st["bottom_z"])), c, mats["deck"])


def facet_z(model, x, y):
    """Top roof surface z at (x, y) from the facet planes (point-in-polygon on the outer rings)."""
    best = None
    for f in model["facets"]:
        a, b, c0 = f["plane"]
        for poly in f["polygons"]:
            ring = poly["outer"]
            inside = False
            for i in range(len(ring)):
                x1, y1 = ring[i][:2]; x2, y2 = ring[(i + 1) % len(ring)][:2]
                if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
                    inside = not inside
            if inside:
                z = a * x + b * y + c0
                best = z if best is None else max(best, z)
    return best


def add_roof_extras(model, D, c, mats):
    up = Vector((0, 0, 1))
    for i, e in enumerate(model["edges"]):
        if e["kind"] not in ("ridge", "hip") or e["length_m"] < 0.3:
            continue
        p0, p1 = Vector(e["p0"]), Vector(e["p1"])
        side = (p1 - p0).cross(up).normalized()
        oriented_box(f"ridge cap {i}", p0 - side * 0.15 + up * 0.005, p1 - p0, side * 0.30, up * 0.05, c, mats["cap"])
    for i, v in enumerate(D.get("roof_vents", [])):
        x, y = v["xy"]
        z = facet_z(model, x, y)
        if z is None:
            continue
        w = v.get("size", 0.32)
        box(f"roof vent {i}", (x - w / 2, y - w / 2, z - 0.05), (x + w / 2, y + w / 2, z + v.get("height", 0.16)), c, mats["vent"])


def add_corner_boards(model, frames, fnd, c, mats, width=0.1):
    for w in model["walls"]:
        key = f'{w["wing"]}:{w["side"]}'
        a, d, n, L, zb = frames[key]
        top0, top1 = w["profile"][0][2], w["profile"][-1][2]
        sb = fnd.get("walls", {}).get(key)
        for u, zt, sgn in ((0.0, top0, 1), (L, top1, -1)):
            z0 = sb if sb is not None else zb(u) + fnd.get("default_reveal", 0.25)
            p = a + d * u + n * 0.012 + Vector((0, 0, z0))
            oriented_box(f"corner board {key}", p, d * (width * sgn), n * 0.02, Vector((0, 0, zt - z0 - 0.05)), c, mats["trim"])


def add_lights_and_text(D, frames, c, mats):
    for i, l in enumerate(D.get("lights", [])):
        a, d, n, L, _ = frames[l["wall"]]
        p = a + d * l["u"] + Vector((0, 0, l["z"]))
        oriented_box(f"light {i} plate", p - d * 0.06 - Vector((0, 0, 0.08)), d * 0.12, n * 0.03, Vector((0, 0, 0.16)), c, mats["fixture"])
        oriented_box(f"light {i} arm", p - d * 0.015 + Vector((0, 0, 0.04)), d * 0.03, n * 0.22, Vector((0, 0, 0.03)), c, mats["fixture"])
        oriented_box(f"light {i} shade", p - d * 0.12 + n * 0.12 - Vector((0, 0, 0.1)), d * 0.24, n * 0.24, Vector((0, 0, 0.12)), c, mats["fixture"])
    for i, t in enumerate(D.get("text", [])):
        a, d, n, L, _ = frames[t["wall"]]
        cu = bpy.data.curves.new(f"text {i}", "FONT")
        cu.body = t["text"]; cu.size = t.get("size", 0.15); cu.align_x = "CENTER"; cu.extrude = 0.004
        ob = bpy.data.objects.new(f"text {t['text']}", cu)
        p = a + d * t["u"] + n * t.get("offset", 0.12) + Vector((0, 0, t["z"]))
        ob.location = p
        # text faces +Z by default: rotate to stand up and face outward
        import mathutils
        ob.rotation_euler = mathutils.Matrix((d, Vector((0, 0, 1)), n)).transposed().to_euler()
        cu.materials.append(mats.get(t.get("material", "trim")))
        c.objects.link(ob)


def main():
    blend, details, out = args()[:3]
    bpy.ops.wm.open_mainfile(filepath=blend)
    D = json.load(open(details))
    model = json.load(open(D["model_json"]))
    frames = wall_frames(model)
    c = coll("Details")
    sid = D.get("siding", {})
    mats = {
        "trim": mat("Trim (white)", tuple(D.get("trim_color", (0.85, 0.85, 0.82))), 0.5),
        "soffit": mat("Soffit", (0.8, 0.8, 0.77), 0.6),
        "gutter": mat("Gutter", (0.88, 0.88, 0.86), 0.35, 0.2),
        "glass": mat("Glass", (0.03, 0.05, 0.07), 0.05, 0.0),
        "door": mat("Door", tuple(D.get("door_color", (0.82, 0.82, 0.8))), 0.45),
        "garage": mat("Garage door", (0.9, 0.9, 0.88), 0.4),
        "shadow": mat("Joint shadow", (0.25, 0.25, 0.25), 0.8),
        "deck": mat("Deck (painted)", tuple(D.get("deck_color", (0.07, 0.12, 0.09))), 0.75),
        "concrete": mat("Concrete", (0.55, 0.55, 0.53), 0.95),
        "brick": mat("Brick", (0.35, 0.12, 0.08), 0.9),
        "cap": mat("Ridge cap", (0.12, 0.12, 0.13), 0.9),
        "vent": mat("Roof vent", (0.1, 0.1, 0.11), 0.6, 0.3),
        "fixture": mat("Light fixture (black)", (0.02, 0.02, 0.02), 0.4, 0.5),
    }
    # siding on the existing walls
    sm = siding_material(tuple(sid.get("color", (0.42, 0.42, 0.30))), sid.get("exposure", 0.1803))
    for ob in bpy.data.collections["Walls"].objects:
        ob.data.materials.clear()
        ob.data.materials.append(sm)
    rf = D.get("roof", {})
    if rf.get("courses", True):
        slope = rf.get("slope") or max(f["pitch_rise_per_12"] for f in model["facets"]) / 12.0
        rm = shingle_material(tuple(rf.get("color", (0.17, 0.17, 0.18))), rf.get("exposure", 0.1429), slope)
        for ob in bpy.data.collections["Roof facets"].objects:
            ob.data.materials.clear()
            ob.data.materials.append(rm)
    add_foundation(frames, D.get("foundation", {}), c, mats)
    add_trim(model, frames, c, mats, D.get("fascia_height", 0.2), D.get("gutters", True), D.get("soffits", True))
    for o in D.get("openings", []):
        add_opening(o, frames, c, mats)
    add_roof_extras(model, D, c, mats)
    if D.get("corner_boards", True):
        add_corner_boards(model, frames, D.get("foundation", {}), c, mats)
    add_lights_and_text(D, frames, c, mats)
    for i, dk in enumerate(D.get("decks", [])):
        add_deck(dk, c, mats, i)
    for i, st in enumerate(D.get("stairs", [])):
        add_stairs(st, c, mats, i)
    for i, ce in enumerate(D.get("ceilings", [])):
        pts = [(x, y, ce["z"]) for x, y in ce["polygon"]]
        mesh(f"porch ceiling {i}", pts, [list(range(len(pts)))], c, mats["soffit"])
    for b in D.get("boxes", []):
        box(b["name"], b["min"], b["max"], c, mats.get(b.get("material", "trim"), mats["trim"]))
    for i, ds in enumerate(D.get("downspouts", [])):
        x, y = ds["xy"]
        box(f"downspout {i}", (x - 0.04, y - 0.04, ds.get("bottom_z", 0.2)), (x + 0.04, y + 0.04, ds["top_z"]), c, mats["gutter"])
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("details added:", len(c.objects), "objects ->", out)


main()
