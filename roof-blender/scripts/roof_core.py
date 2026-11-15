"""Roof layer pipeline for Blender (4.2 LTS and 5.x).

One module, three ways to run it:
  * through blender-mcp: roof-blender.mjs sends this file plus a run({...}) call
  * headless:  blender -b house.blend -P roof_core.py -- '{"cmd": "all", ...}'
  * as a module from the pip `bpy` package (used by the tests)

Commands (cfg["cmd"]):
  demo      build a demo house whose roof object is named "Roof"
  layers    rebuild every roofing layer on the roof planes (RT_Layers collection)
  material  put a supplier photo or procedural shingle on the covering
  build     keyframe the tear-off -> finish sequence from a plan JSON
  explode   keyframe (or set) the exploded "layers view" with labels
  scene     sun, physical sky, ground, camera, Cycles + AgX settings
  render    render a still or the animation frames
  export    export RT_Layers as GLB for the web viewer
  all       demo (if no roof) + layers + material + scene + build/explode + render

Geometry mirrors roof-visualizer/viewer/js/roof-geometry.js so a plan or
layer stack looks the same in the browser and in Cycles. Units are metres,
Z is up, the front of the demo house faces -Y.
"""

import bpy
import bmesh
import json
import math
import os
import sys
from mathutils import Vector

IN = 0.0254
UP = Vector((0.0, 0.0, 1.0))
COLL = "RT_Layers"

# stack heights above the rafters (metres), same as the web viewer
H = {
    "deck": 0.0111, "oldFelt": 0.0128, "oldShingles": 0.0145, "dripEave": 0.0122, "iceWater": 0.0134,
    "underlayment": 0.0146, "dripRake": 0.0158, "starter": 0.0168, "nails": 0.0222, "covering": 0.0190,
    "ridgeVent": 0.0235, "cap": 0.0262,
}

LAYER_INFO = {
    "oldShingles": ("Existing shingles", "Worn 3-tab, torn off"),
    "oldFelt": ("Existing felt", "#15 felt, removed"),
    "deck": ("Roof deck", '7/16" OSB sheathing'),
    "deckRepair": ("Deck repair", "Replacement sheets"),
    "dripEdge": ("Drip edge", "Eaves under, rakes over"),
    "iceWater": ("Ice & water shield", "Eaves + valleys"),
    "underlayment": ("Underlayment", 'Synthetic, 4" laps'),
    "starter": ("Starter strip", "Eaves + rakes"),
    "nails": ("Fasteners", '1-1/4" coil nails'),
    "covering": ("Shingles", "Architectural laminate"),
    "ridgeVent": ("Ridge vent", "Shingle-over vent"),
    "ridgeCap": ("Hip & ridge cap", "Matching cap shingles"),
}
STACK = ["oldFelt", "oldShingles", "deck", "deckRepair", "dripEdge", "iceWater", "underlayment", "starter",
         "nails", "covering", "ridgeVent", "ridgeCap"]


def log(*a):
    print("[roof]", *a)


# ---------------------------------------------------------------------------
# 2D helpers (u = along the eave, v = up the slope)

def area2(t):
    return (t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1])


def poly_area2(poly):
    s = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        s += a[0] * b[1] - b[0] * a[1]
    return s


def clip_half(poly, hp):
    a, b, c = hp
    out = []
    f = lambda p: a * p[0] + b * p[1] + c
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = f(p), f(q)
        if fp >= 0:
            out.append(p)
        if (fp >= 0) != (fq >= 0):
            t = fp / (fp - fq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    if len(out) >= 3 and poly_area2(out) < 0:
        out.reverse()
    return out


def point_in_tri(u, v, t, margin=0.0):
    s = area2(t)
    if abs(s) < 1e-12:
        return False
    sign = 1 if s > 0 else -1
    for p, q in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
        ex, ey = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(ex, ey) or 1.0
        if (ex * (v - p[1]) - ey * (u - p[0])) * sign / ln < margin - 1e-9:
            return False
    return True


class Plane:
    """One planar roof face set with its own (u, v) frame."""

    def __init__(self, tris3, normal=None, pid=0):
        self.id = pid
        n = (normal or (tris3[0][1] - tris3[0][0]).cross(tris3[0][2] - tris3[0][0])).normalized()
        if n.z < 0:
            n = -n
        self.n = n
        h = UP.cross(n)
        if h.length < 1e-6:
            h = Vector((1, 0, 0))
        self.h = h.normalized()
        self.b = n.cross(self.h).normalized()
        self.slope = math.acos(min(1.0, n.z))
        o = tris3[0][0].copy()
        raw = [[((p - o).dot(self.h), (p - o).dot(self.b)) for p in t] for t in tris3]
        umin = min(p[0] for t in raw for p in t)
        vmin = min(p[1] for t in raw for p in t)
        self.origin = o + self.h * umin + self.b * vmin
        self.tris = [[(p[0] - umin, p[1] - vmin) for p in t] for t in raw]
        self.tris = [t if area2(t) > 0 else [t[0], t[2], t[1]] for t in self.tris]
        self.umax = max(p[0] for t in self.tris for p in t)
        self.vmax = max(p[1] for t in self.tris for p in t)
        self.area = sum(abs(area2(t)) / 2 for t in self.tris)
        self.edges = [{"a": a, "b": b, "A": self.to3(*a), "B": self.to3(*b), "type": "unknown"} for a, b in boundary_edges(self.tris)]

    @staticmethod
    def from_polygon(pts, pid=0):
        tris = [[pts[0], pts[i], pts[i + 1]] for i in range(1, len(pts) - 1)]  # convex roof faces
        n = (pts[1] - pts[0]).cross(pts[2] - pts[0]).normalized()
        return Plane(tris, n, pid)

    def to3(self, u, v, off=0.0):
        return self.origin + self.h * u + self.b * v + self.n * off

    def from3(self, p):
        d = p - self.origin
        return (d.dot(self.h), d.dot(self.b))

    def distance(self, p):
        return (p - self.origin).dot(self.n)

    def contains2(self, u, v, margin=0.0):
        return any(point_in_tri(u, v, t, margin) for t in self.tris)

    def region(self, half_planes=()):
        out = []
        for t in self.tris:
            poly = list(t)
            for hp in half_planes:
                poly = clip_half(poly, hp)
                if len(poly) < 3:
                    break
            if len(poly) >= 3 and abs(poly_area2(poly)) > 1e-8:
                out.append(poly)
        return out


def _k(p):
    return (round(p[0] * 500), round(p[1] * 500))


def boundary_edges(tris):
    m = {}
    for t in tris:
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            k1, k2 = (_k(a), _k(b)), (_k(b), _k(a))
            if k2 in m:
                del m[k2]
            else:
                m[k1] = (a, b)
    edges = list(m.values())
    by_start = {_k(e[0]): e for e in edges}
    used, out = set(), []
    for e in edges:
        if id(e) in used:
            continue
        used.add(id(e))
        a, b = e
        nxt = by_start.get(_k(b))
        while nxt and id(nxt) not in used and _collinear(a, b, nxt[1]):
            used.add(id(nxt))
            b = nxt[1]
            nxt = by_start.get(_k(b))
        out.append((a, b))
    return out


def _collinear(a, b, c):
    abx, aby, bcx, bcy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
    cross = abx * bcy - aby * bcx
    return abs(cross) < 1e-4 * math.hypot(abx, aby) * math.hypot(bcx, bcy) + 1e-9 and abx * bcx + aby * bcy > 0


def inward2(P, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy) or 1.0
    m = (-dy / ln, dx / ln)
    mid = ((a[0] + b[0]) / 2 + m[0] * 0.05, (a[1] + b[1]) / 2 + m[1] * 0.05)
    if not P.contains2(*mid):
        m = (-m[0], -m[1])
    return m


def analyze_roof(planes, tol=0.03):
    segs = {"eave": [], "rake": [], "ridge": [], "hip": [], "valley": [], "top": []}
    seen = set()
    for P in planes:
        for e in P.edges:
            mid = (e["A"] + e["B"]) / 2
            inward = inward2(P, e["a"], e["b"])
            match, interior = None, False
            for Q in planes:
                if Q is P or abs(Q.distance(e["A"])) > tol or abs(Q.distance(e["B"])) > tol:
                    continue
                if any(_overlap(e, f, tol) for f in Q.edges):
                    match = Q
                    break
                mu, mv = Q.from3(mid)
                if Q.contains2(mu, mv, -0.01):
                    match, interior = Q, True
                    break
            horizontal = abs(e["A"].z - e["B"].z) < 0.01 + 0.01 * (e["A"] - e["B"]).length
            if match:
                if interior:
                    kind = "valley"
                else:
                    mu, mv = P.from3(mid)
                    probe = P.to3(mu + inward[0] * 0.15, mv + inward[1] * 0.15)
                    convex = match.distance(probe) < 0
                    kind = ("ridge" if horizontal else "hip") if convex else "valley"
                e["type"] = kind
                key = tuple(sorted([tuple(round(x * 50) for x in e["A"]), tuple(round(x * 50) for x in e["B"])]))
                if key not in seen:
                    seen.add(key)
                    segs[kind].append({"A": e["A"].copy(), "B": e["B"].copy(), "planes": [P, match]})
            else:
                kind = ("eave" if inward[1] > 0 else "top") if horizontal else "rake"
                e["type"] = kind
                segs[kind].append({"A": e["A"].copy(), "B": e["B"].copy(), "planes": [P]})
    return segs


def _overlap(e, f, tol):
    same = lambda p, q: (p - q).length < tol
    if (same(e["A"], f["A"]) and same(e["B"], f["B"])) or (same(e["A"], f["B"]) and same(e["B"], f["A"])):
        return True

    def on_seg(p, s):
        ab = s["B"] - s["A"]
        t = (p - s["A"]).dot(ab) / max(ab.length_squared, 1e-12)
        return -0.01 <= t <= 1.01 and ((s["A"] + ab * t) - p).length < tol

    s, l = (e, f) if (e["A"] - e["B"]).length < (f["A"] - f["B"]).length else (f, e)
    return on_seg(s["A"], l) and on_seg(s["B"], l)


def full_parts(planes):
    return [(P, P.region()) for P in planes]


def strip_parts(planes, segs, width, extend=0.0):
    parts = []
    for P in planes:
        polys = []
        for s in segs:
            if abs(P.distance(s["A"])) > 0.03 or abs(P.distance(s["B"])) > 0.03:
                continue
            a, b = P.from3(s["A"]), P.from3(s["B"])
            d = (b[0] - a[0], b[1] - a[1])
            ln = math.hypot(*d)
            if ln < 1e-3:
                continue
            t = (d[0] / ln, d[1] / ln)
            m = (-t[1], t[0])
            c0 = -(m[0] * a[0] + m[1] * a[1])
            hp = [
                (m[0], m[1], c0 + width),
                (-m[0], -m[1], -c0 + width),
                (t[0], t[1], -(t[0] * a[0] + t[1] * a[1]) + extend),
                (-t[0], -t[1], (t[0] * b[0] + t[1] * b[1]) + extend),
            ]
            polys += P.region(hp)
        if polys:
            parts.append((P, polys))
    return parts


# ---------------------------------------------------------------------------
# geometry buffers -> Blender meshes

class Buf:
    def __init__(self):
        self.verts, self.faces, self.uvs, self.up, self.along = [], [], [], [], []

    def tri(self, pts, uvs, ups, alongs):
        base = len(self.verts)
        self.verts += [tuple(p) for p in pts]
        self.faces.append(tuple(range(base, base + len(pts))))
        self.uvs += uvs
        self.up += ups
        self.along += alongs


def build_surface(parts, offset, course_h=None, step_h=0.005, thickness=None):
    buf = Buf()
    for P, polys in parts:
        al = lambda u: min(0.9999, u / max(P.umax, 1e-6))
        if course_h:
            e = course_h
            rows = int(P.vmax / e) + 2
            for r in range(rows):
                v0, v1 = r * e, (r + 1) * e
                hof = lambda v: offset + step_h * (1 - (v - v0) / e)
                for poly in polys:
                    strip = clip_half(clip_half(poly, (0, 1, -v0)), (0, -1, v1))
                    if len(strip) < 3:
                        continue
                    buf.tri([P.to3(u, v, hof(v)) for u, v in strip], [(u, v) for u, v in strip], [v for _, v in strip], [al(u) for u, _ in strip])
                    for i in range(len(strip)):
                        a, b = strip[i], strip[(i + 1) % len(strip)]
                        if abs(a[1] - v0) < 1e-5 and abs(b[1] - v0) < 1e-5:
                            x0, x1 = (a, b) if a[0] < b[0] else (b, a)
                            lo, hi = offset - (0.004 if r == 0 else 0), offset + step_h
                            vv = v0 + 1e-4
                            pts = [P.to3(x0[0], vv, lo), P.to3(x0[0], vv, hi), P.to3(x1[0], vv, hi), P.to3(x1[0], vv, lo)]
                            buf.tri(pts, [(x0[0], 0), (x0[0], step_h), (x1[0], step_h), (x1[0], 0)], [vv] * 4, [al(x0[0]), al(x0[0]), al(x1[0]), al(x1[0])])
        else:
            for poly in polys:
                buf.tri([P.to3(u, v, offset) for u, v in poly], [(u, v) for u, v in poly], [v for _, v in poly], [al(u) for u, _ in poly])
        if thickness:
            for poly in polys:
                for i in range(len(poly)):
                    a, b = poly[i], poly[(i + 1) % len(poly)]
                    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    ln = math.hypot(dx, dy) or 1
                    m = (-dy / ln * 0.02, dx / ln * 0.02)
                    if P.contains2(mid[0] + m[0], mid[1] + m[1]) == P.contains2(mid[0] - m[0], mid[1] - m[1]):
                        continue
                    pts = [P.to3(a[0], a[1], offset - thickness), P.to3(b[0], b[1], offset - thickness), P.to3(b[0], b[1], offset), P.to3(a[0], a[1], offset)]
                    buf.tri(pts, [(0, 0), (ln, 0), (ln, thickness), (0, thickness)], [a[1], b[1], b[1], a[1]], [al(a[0]), al(b[0]), al(b[0]), al(a[0])])
    return buf


def drip_edge_buf(segs, flange=0.05, drop=0.045):
    buf = Buf()
    for kind, off, kup in (("eave", H["dripEave"], 0.0), ("rake", H["dripRake"], 1.0)):
        lst = segs[kind]
        total = sum((s["A"] - s["B"]).length for s in lst) or 1
        acc = 0.0
        for s in lst:
            P = s["planes"][0]
            ln = (s["A"] - s["B"]).length
            k0, k1 = acc / total, min(0.9999, (acc + ln) / total)
            acc += ln
            a2, b2 = P.from3(s["A"]), P.from3(s["B"])
            inn = inward2(P, a2, b2)
            A, B = P.to3(*a2, off), P.to3(*b2, off)
            A1 = P.to3(a2[0] + inn[0] * flange, a2[1] + inn[1] * flange, off)
            B1 = P.to3(b2[0] + inn[0] * flange, b2[1] + inn[1] * flange, off)
            outw = -(P.h * inn[0] + P.b * inn[1])
            outw.z = 0
            outw.normalize()
            dz = Vector((0, 0, -drop))
            A2, B2 = A + dz, B + dz
            kick = outw * 0.012 + Vector((0, 0, -0.006))
            for q in ((A1, B1, B, A), (A, B, B2, A2), (A2, B2, B2 + kick, A2 + kick)):
                buf.tri(list(q), [(0, 0), (ln, 0), (ln, 0.05), (0, 0.05)], [kup] * 4, [k0, k1, k1, k0])
    return buf


def cap_buf(lines, width=0.16, off=H["cap"]):
    buf = Buf()
    total = sum((l["A"] - l["B"]).length for l in lines) or 1
    acc = 0.0
    for l in lines:
        A, B = l["A"], l["B"]
        if A.z > B.z + 0.01:
            A, B = B, A
        ln = (A - B).length
        k0, k1 = acc / total, min(0.9999, (acc + ln) / total)
        acc += ln
        for P in l["planes"]:
            a2, b2 = P.from3(A), P.from3(B)
            inn = inward2(P, a2, b2)
            crest = P.n * 0.006
            pA, pB = P.to3(*a2, off) + crest, P.to3(*b2, off) + crest
            qA = P.to3(a2[0] + inn[0] * width, a2[1] + inn[1] * width, off - 0.004)
            qB = P.to3(b2[0] + inn[0] * width, b2[1] + inn[1] * width, off - 0.004)
            buf.tri([qA, qB, pB, pA], [(0, width), (ln, width), (ln, 0), (0, 0)], [0.0] * 4, [k0, k1, k1, k0])
    return buf


def nail_buf(planes, exposure, spacing, off, margin=0.04):
    """Real nail geometry (head + shank) on the nail line of every course."""
    buf = Buf()
    r_head, t_head, seg = 0.0055, 0.0012, 6
    for P in planes:
        rows = int(P.vmax / exposure) + 1
        for r in range(rows):
            v = (r + 1) * exposure + 0.016
            u = margin + (r % 2) * spacing * 0.5
            while u < P.umax - margin:
                if P.contains2(u, v, margin):
                    c = P.to3(u, v, off)
                    al = min(0.9999, u / max(P.umax, 1e-6))
                    up = r * exposure + 1e-3  # floor(up / exposure) == r: same key as its course
                    ring = [c + (P.h * math.cos(2 * math.pi * k / seg) + P.b * math.sin(2 * math.pi * k / seg)) * r_head for k in range(seg)]
                    buf.tri(ring, [(0, 0)] * seg, [up] * seg, [al] * seg)
                    low = [p - P.n * t_head for p in ring]
                    for k in range(seg):
                        q = [ring[k], ring[(k + 1) % seg], low[(k + 1) % seg], low[k]]
                        buf.tri(q, [(0, 0)] * 4, [up] * 4, [al] * 4)
                    tip = c - P.n * 0.033
                    sh = [c - P.n * t_head + (P.h * math.cos(2 * math.pi * k / 3) + P.b * math.sin(2 * math.pi * k / 3)) * 0.0016 for k in range(3)]
                    for k in range(3):
                        buf.tri([sh[k], sh[(k + 1) % 3], tip], [(0, 0)] * 3, [up] * 3, [al] * 3)
                u += spacing
    return buf


def deck_patch_parts(planes, count=3):
    W, Hh = 2.438, 1.219
    cands = []
    for P in planes:
        v = 0.2
        while v + Hh < P.vmax:
            u = 0.2
            while u + W < P.umax:
                corners = [(u, v), (u + W, v), (u + W, v + Hh), (u, v + Hh)]
                if all(P.contains2(a, b, 0.05) for a, b in corners):
                    cands.append((P, [corners]))
                u += W * 0.5
            v += Hh
    step = max(1, len(cands) // max(1, count))
    return cands[::step][:count]


def ensure_collection(name=COLL, parent=None):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def mesh_object(name, buf, material=None, coll=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(buf.verts, [], buf.faces)
    me.validate(clean_customdata=False)
    uv = me.uv_layers.new(name="UVMeters")
    loop_uvs = []
    for poly in me.polygons:
        for vi in poly.vertices:
            loop_uvs.extend(buf.uvs[vi])
    uv.data.foreach_set("uv", loop_uvs)
    for attr, vals in (("rt_up", buf.up), ("rt_along", buf.along)):
        a = me.attributes.new(attr, "FLOAT", "POINT")
        a.data.foreach_set("value", vals)
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    (coll or ensure_collection()).objects.link(ob)
    if material:
        me.materials.append(material)
    return ob


# ---------------------------------------------------------------------------
# roof source

def roof_source(name=None):
    """Return (planes, source_objects). Uses the object named `name`, else any
    object whose name contains roof/shingle, else upward-facing faces in the
    top part of the scene."""
    objs = []
    if name and bpy.data.objects.get(name):
        objs = [bpy.data.objects[name]]
    if not objs:
        objs = [o for o in bpy.data.objects if o.type == "MESH" and any(k in o.name.lower() for k in ("roof", "shingle")) and not o.name.startswith("RT_")]
    heuristic = not objs
    if heuristic:
        objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("RT_")]
    tris = []
    zmin, zmax = 1e9, -1e9
    deps = bpy.context.evaluated_depsgraph_get()
    data = []
    for o in objs:
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        mw = o.matrix_world
        for lt in me.loop_triangles:
            pts = [mw @ me.vertices[i].co for i in lt.vertices]
            data.append(pts)
            for p in pts:
                zmin, zmax = min(zmin, p.z), max(zmax, p.z)
        ev.to_mesh_clear()
    zcut = zmin + (zmax - zmin) * 0.4
    for pts in data:
        n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
        ar = n.length / 2
        if ar < 1e-5:
            continue
        n.normalize()
        if heuristic and (n.z < 0.22 or sum(p.z for p in pts) / 3 < zcut):
            continue
        if n.z < 0.05:
            continue  # walls, fascia and the underside of thick roof meshes
        tris.append((pts, n, n.dot(pts[0]), ar))
    clusters = []
    for pts, n, d, ar in tris:
        for cl in clusters:
            if cl["n"].dot(n) > math.cos(math.radians(4)) and abs(cl["d"] - d) < 0.06:
                cl["tris"].append(pts)
                cl["area"] += ar
                break
        else:
            clusters.append({"n": n.copy(), "d": d, "tris": [pts], "area": ar})
    planes = []
    for i, cl in enumerate(c for c in clusters if c["area"] > 0.5):
        proj = [[p + cl["n"] * (cl["d"] - cl["n"].dot(p)) for p in t] for t in cl["tris"]]
        planes.append(Plane(proj, cl["n"], i))
    if heuristic and sum(p.area for p in planes) < 8.0:
        return [], []  # nothing roof-sized (e.g. the default cube)
    return planes, objs


# ---------------------------------------------------------------------------
# demo house

def blk_roof(b, pitch, overhang):
    p = pitch / 12.0
    swap = b.get("axis") == "y"
    L = b["d"] if swap else b["w"]
    S = b["w"] if swap else b["d"]
    X, Z = L / 2 + overhang, S / 2 + overhang
    ye = b["wall"] - overhang * p
    yr = ye + Z * p

    def V(x, z, s):
        # local: x along ridge, s across (front = +s); world front = -Y
        return Vector((b["cx"] + s, b["cy"] - x, z)) if swap else Vector((b["cx"] + x, b["cy"] - s, z))

    roof, gables = [], []
    ext = 12.0 if b.get("attach") else 0.0
    if b["roof"] == "hip":
        rx = max(0.0, X - Z)
        roof += [[V(-X, ye, Z), V(X, ye, Z), V(rx, yr, 0), V(-rx, yr, 0)],
                 [V(X, ye, -Z), V(-X, ye, -Z), V(-rx, yr, 0), V(rx, yr, 0)],
                 [V(X, ye, Z), V(X, ye, -Z), V(rx, yr, 0)],
                 [V(-X, ye, -Z), V(-X, ye, Z), V(-rx, yr, 0)]]
    else:
        xb = -X - ext
        roof += [[V(xb, ye, Z), V(X, ye, Z), V(X, yr, 0), V(xb, yr, 0)],
                 [V(X, ye, -Z), V(xb, ye, -Z), V(xb, yr, 0), V(X, yr, 0)]]
        hw = S / 2
        for sx in ([1] if b.get("attach") else [1, -1]):
            x = sx * L / 2
            gables.append([V(x, b["wall"], hw), V(x, b["wall"], -hw), V(x, b["wall"] + hw * p, 0)])
    return roof, gables


def _clip_poly3(poly, point, n):
    out = []
    f = lambda p: (p - point).dot(n)
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        fa, fb = f(a), f(b)
        if fa >= -1e-6:
            out.append(a)
        if (fa >= -1e-6) != (fb >= -1e-6):
            out.append(a.lerp(b, fa / (fa - fb)))
    return out


def make_demo_house(pitch=6.0, preset="ranch-hip"):
    """Ranch with a hip roof and a front-gable garage (valleys included)."""
    blocks = {
        "ranch-hip": [dict(id="main", cx=0, cy=0, w=16, d=10, wall=2.75, roof="hip"),
                      dict(id="garage", cx=-4.2, cy=-7.6, w=7.2, d=5.6, wall=2.75, roof="gable", axis="y", attach="main")],
        "two-story": [dict(id="main", cx=0, cy=0, w=12.5, d=9, wall=5.6, roof="gable")],
        "cottage": [dict(id="main", cx=0, cy=0, w=11, d=9, wall=2.9, roof="hip")],
    }[preset]
    overhang = 0.4
    coll = ensure_collection("RT_House")
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    roofs = {}
    for b in blocks:
        roofs[b["id"]] = blk_roof(b, pitch, overhang)
    polys = []
    for b in blocks:
        roof, _ = roofs[b["id"]]
        if not b.get("attach"):
            polys += roof
            continue
        parent = next(x for x in blocks if x["id"] == b["attach"])
        toward = Vector((b["cx"] - parent["cx"], b["cy"] - parent["cy"], 0)).normalized()
        for poly in roof:
            for pp in roofs[parent["id"]][0]:
                n = (pp[1] - pp[0]).cross(pp[2] - pp[0]).normalized()
                if n.z < 0:
                    n = -n
                hn = Vector((n.x, n.y, 0)).normalized()
                if hn.dot(toward) < 0.7:
                    continue
                poly = _clip_poly3(poly, pp[0], n)
            if len(poly) >= 3:
                polys.append(poly)
    # roof object (faces = roof planes at rafter height)
    bm = bmesh.new()
    for poly in polys:
        vs = [bm.verts.new(p) for p in poly]
        f = bm.faces.new(vs)
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
    me = bpy.data.meshes.new("Roof")
    bm.to_mesh(me)
    bm.free()
    roof_ob = bpy.data.objects.new("Roof", me)
    coll.objects.link(roof_ob)
    # walls + gable ends
    wall_mat = simple_material("RT_Siding", (0.78, 0.76, 0.70), 0.6)
    trim_mat = simple_material("RT_Trim", (0.92, 0.91, 0.88), 0.5)
    for b in blocks:
        cy, d = b["cy"], b["d"]
        if b.get("attach"):
            parent = next(x for x in blocks if x["id"] == b["attach"])
            front = b["cy"] - b["d"] / 2
            back = parent["cy"] - parent["d"] / 2 + 0.3
            d, cy = back - front, (front + back) / 2
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector((b["w"], d, b["wall"])), verts=bm.verts)
        bmesh.ops.translate(bm, vec=Vector((b["cx"], cy, b["wall"] / 2)), verts=bm.verts)
        me = bpy.data.meshes.new(f"Walls_{b['id']}")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"Walls_{b['id']}", me)
        ob.data.materials.append(wall_mat)
        coll.objects.link(ob)
        for tri in roofs[b["id"]][1]:
            bm = bmesh.new()
            bm.faces.new([bm.verts.new(p) for p in tri])
            me = bpy.data.meshes.new(f"Gable_{b['id']}")
            bm.to_mesh(me)
            bm.free()
            ob = bpy.data.objects.new(f"Gable_{b['id']}", me)
            ob.data.materials.append(wall_mat)
            coll.objects.link(ob)
    # fascia boards along eaves and rakes
    planes = [Plane.from_polygon(p, i) for i, p in enumerate(polys)]
    segs = analyze_roof(planes)
    bm = bmesh.new()
    for kind in ("eave", "rake"):
        for s in segs[kind]:
            dz = Vector((0, 0, -0.19))
            vs = [bm.verts.new(p) for p in (s["A"], s["B"], s["B"] + dz, s["A"] + dz)]
            bm.faces.new(vs)
    me = bpy.data.meshes.new("Fascia")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Fascia", me)
    ob.data.materials.append(trim_mat)
    coll.objects.link(ob)
    roof_ob.hide_render = True  # the layer stack replaces it
    log(f"demo house: {len(polys)} roof planes")
    return {"roof": "Roof", "planes": len(polys)}


def simple_material(name, rgb, rough=0.5, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    _use_nodes(m)
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return m


def _use_nodes(idblock):
    if not getattr(idblock, "node_tree", None) or not idblock.node_tree:
        try:
            idblock.use_nodes = True
        except Exception:
            pass


# ---------------------------------------------------------------------------
# materials with build reveal

def layer_material(name, base=None, row_h=1000.0, rough=0.85, metal=0.0, image=None, size_m=(1.0, 1.0),
                   bump=0.3, procedural=None, rotation_deg=0.0):
    """Principled material. Every layer material carries the build-reveal test:
    visible where floor(rt_up / row_h) + rt_along < RT_Reveal (a keyframable Value node)."""
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    _use_nodes(m)
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (500, 0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    uv = nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMeters"
    uv.location = (-1200, 0)
    if image:
        mapping = nodes.new("ShaderNodeMapping")
        mapping.location = (-1000, 0)
        mapping.inputs["Scale"].default_value = (1.0 / size_m[0], 1.0 / size_m[1], 1.0)
        mapping.inputs["Rotation"].default_value = (0, 0, math.radians(rotation_deg))
        links.new(uv.outputs["UV"], mapping.inputs["Vector"])
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-750, 0)
        tex.image = bpy.data.images.load(image, check_existing=True)
        tex.extension = "REPEAT"
        tex.interpolation = "Cubic"
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bw = nodes.new("ShaderNodeRGBToBW")
        bw.location = (-450, -250)
        links.new(tex.outputs["Color"], bw.inputs["Color"])
        bmp = nodes.new("ShaderNodeBump")
        bmp.location = (200, -300)
        bmp.inputs["Strength"].default_value = bump
        bmp.inputs["Distance"].default_value = 0.004
        links.new(bw.outputs["Val"], bmp.inputs["Height"])
        links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
        rr = nodes.new("ShaderNodeMapRange")
        rr.location = (200, -100)
        rr.inputs["To Min"].default_value = min(1.0, rough + 0.06)
        rr.inputs["To Max"].default_value = max(0.0, rough - 0.08)
        links.new(bw.outputs["Val"], rr.inputs["Value"])
        links.new(rr.outputs["Result"], bsdf.inputs["Roughness"])
    elif procedural:
        _procedural(nt, uv, bsdf, procedural)
    elif base is not None:
        bsdf.inputs["Base Color"].default_value = (*base, 1)
        noise = nodes.new("ShaderNodeTexNoise")
        noise.location = (-700, -300)
        noise.inputs["Scale"].default_value = 180.0
        links.new(uv.outputs["UV"], noise.inputs["Vector"])
        bmp = nodes.new("ShaderNodeBump")
        bmp.location = (200, -300)
        bmp.inputs["Strength"].default_value = bump * 0.5
        bmp.inputs["Distance"].default_value = 0.002
        links.new(noise.outputs["Fac"], bmp.inputs["Height"])
        links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    # reveal: key = floor(up/row_h) + along ; show where key < RT_Reveal
    a_up = nodes.new("ShaderNodeAttribute")
    a_up.attribute_name = "rt_up"
    a_up.location = (-200, 400)
    a_al = nodes.new("ShaderNodeAttribute")
    a_al.attribute_name = "rt_along"
    a_al.location = (-200, 250)
    div = _math(nodes, "DIVIDE", (0, 450))
    div.inputs[1].default_value = row_h
    links.new(a_up.outputs["Fac"], div.inputs[0])
    flo = _math(nodes, "FLOOR", (150, 450))
    links.new(div.outputs[0], flo.inputs[0])
    add = _math(nodes, "ADD", (300, 400))
    links.new(flo.outputs[0], add.inputs[0])
    links.new(a_al.outputs["Fac"], add.inputs[1])
    reveal = nodes.new("ShaderNodeValue")
    reveal.name = reveal.label = "RT_Reveal"
    reveal.outputs[0].default_value = 1e6
    reveal.location = (300, 250)
    lt = _math(nodes, "LESS_THAN", (500, 400))
    links.new(add.outputs[0], lt.inputs[0])
    links.new(reveal.outputs[0], lt.inputs[1])
    transp = nodes.new("ShaderNodeBsdfTransparent")
    transp.location = (500, 200)
    mix = nodes.new("ShaderNodeMixShader")
    mix.location = (720, 100)
    links.new(lt.outputs[0], mix.inputs[0])
    links.new(transp.outputs[0], mix.inputs[1])
    links.new(bsdf.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "DITHERED"
    m["rt_row_h"] = row_h
    return m


def _math(nodes, op, loc):
    n = nodes.new("ShaderNodeMath")
    n.operation = op
    n.location = loc
    return n


def _procedural(nt, uv, bsdf, recipe):
    """Node-based architectural shingle: courses from the UV (metres),
    random laminated tabs from Voronoi cells, granules from noise."""
    nodes, links = nt.nodes, nt.links
    exp = recipe.get("exposure", 5.625 * IN)
    pal = [hex_rgb(c) for c in recipe.get("palette", ["#3a3d42", "#2b2d30", "#4d5157", "#1f2124"])]
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-1000, 200)
    links.new(uv.outputs["UV"], sep.inputs["Vector"])
    # course index and position within the course
    dv = _math(nodes, "DIVIDE", (-800, 300))
    dv.inputs[1].default_value = exp
    links.new(sep.outputs["Y"], dv.inputs[0])
    row = _math(nodes, "FLOOR", (-650, 350))
    links.new(dv.outputs[0], row.inputs[0])
    frac = _math(nodes, "FRACT", (-650, 250))
    links.new(dv.outputs[0], frac.inputs[0])
    # tabs: voronoi over (u * 7, row * 3.1) -> random colour per tab
    cx = _math(nodes, "MULTIPLY", (-800, 100))
    cx.inputs[1].default_value = 7.0
    links.new(sep.outputs["X"], cx.inputs[0])
    cy = _math(nodes, "MULTIPLY", (-500, 350))
    cy.inputs[1].default_value = 3.1
    links.new(row.outputs[0], cy.inputs[0])
    comb = nodes.new("ShaderNodeCombineXYZ")
    comb.location = (-350, 150)
    links.new(cx.outputs[0], comb.inputs["X"])
    links.new(cy.outputs[0], comb.inputs["Y"])
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.location = (-200, 150)
    vor.voronoi_dimensions = "2D"
    vor.inputs["Scale"].default_value = 1.0
    links.new(comb.outputs["Vector"], vor.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (0, 150)
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    while len(els) < len(pal):
        els.new(0.5)
    for i, c in enumerate(pal):
        els[i].position = i / len(pal)
        els[i].color = (*c, 1)
    sepc = nodes.new("ShaderNodeSeparateColor")
    sepc.location = (-50, 0)
    links.new(vor.outputs["Color"], sepc.inputs["Color"])
    links.new(sepc.outputs[0], ramp.inputs["Fac"])
    # shadow band on the lower part of each course, darker at the butt edge
    band = _math(nodes, "LESS_THAN", (-450, 450))
    band.inputs[1].default_value = 0.42
    links.new(frac.outputs[0], band.inputs[0])
    shade = _math(nodes, "MULTIPLY_ADD", (-250, 450))
    shade.inputs[1].default_value = -0.35
    shade.inputs[2].default_value = 1.0
    links.new(band.outputs[0], shade.inputs[0])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-200, -150)
    noise.inputs["Scale"].default_value = 420.0
    noise.inputs["Detail"].default_value = 4.0
    links.new(uv.outputs["UV"], noise.inputs["Vector"])
    gran = _math(nodes, "MULTIPLY_ADD", (0, -150))
    gran.inputs[1].default_value = 0.35
    gran.inputs[2].default_value = 0.82
    links.new(noise.outputs["Fac"], gran.inputs[0])
    k = _math(nodes, "MULTIPLY", (150, 300))
    links.new(shade.outputs[0], k.inputs[0])
    links.new(gran.outputs[0], k.inputs[1])
    sc = nodes.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    sc.location = (300, 150)
    links.new(ramp.outputs["Color"], sc.inputs[0])
    links.new(k.outputs[0], sc.inputs["Scale"])
    links.new(sc.outputs["Vector"], bsdf.inputs["Base Color"])
    bmp = nodes.new("ShaderNodeBump")
    bmp.location = (300, -200)
    bmp.inputs["Strength"].default_value = 0.35
    bmp.inputs["Distance"].default_value = 0.003
    links.new(noise.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])


def hex_rgb(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


# ---------------------------------------------------------------------------
# layers

def build_layers(cfg):
    planes, srcs = roof_source(cfg.get("roof"))
    if not planes:
        raise RuntimeError("No roof planes found. Name the roof object 'Roof' or pass roof=<object name>.")
    segs = analyze_roof(planes)
    coll = ensure_collection()
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    exposure = cfg.get("exposure_in", 5.625) * IN
    ice_rows = int(cfg.get("ice_rows", 2))
    nails_per = int(cfg.get("nails_per_shingle", 6))
    made = {}

    def add(lid, buf, mat, row_h, key_max):
        if not buf.faces:
            return
        ob = mesh_object(f"RT_layer_{lid}", buf, mat, coll)
        label, spec = LAYER_INFO.get(lid, (lid, ""))
        ob["rt_layer"], ob["rt_label"], ob["rt_spec"] = lid, label, spec
        ob["rt_row_h"], ob["rt_key_max"], ob["rt_level"] = row_h, key_max, STACK.index(lid) if lid in STACK else 99
        made[lid] = ob

    vmax = max(p.vmax for p in planes)
    rows = lambda rh: int(vmax / rh) + 1
    if cfg.get("old_roof", True):
        add("oldFelt", build_surface(full_parts(planes), H["oldFelt"]), layer_material("RT_oldFelt", (0.03, 0.03, 0.03), 34 * IN, 0.8), 34 * IN, rows(34 * IN))
        add("oldShingles", build_surface(full_parts(planes), H["oldShingles"], 5 * IN, 0.004),
            layer_material("RT_oldShingles", row_h=5 * IN, procedural={"exposure": 5 * IN, "palette": ["#57534c", "#4a4741", "#605b52"]}), 5 * IN, rows(5 * IN))
    add("deck", build_surface(full_parts(planes), H["deck"], thickness=H["deck"]), layer_material("RT_deck", (0.42, 0.30, 0.17), 1.2192, 0.8), 1.2192, rows(1.2192))
    add("deckRepair", build_surface(deck_patch_parts(planes), H["deck"] + 0.0006), layer_material("RT_deckRepair", (0.62, 0.45, 0.26), 1000.0, 0.8), 1000.0, 1)
    add("dripEdge", drip_edge_buf(segs), layer_material("RT_dripEdge", (0.88, 0.88, 0.85), 1.0, 0.35, 0.3), 1.0, 2)
    roll, lap = 36 * IN, 3 * IN
    ice = strip_parts(planes, segs["eave"], ice_rows * (roll - lap) + lap)
    if segs["valley"] and cfg.get("valleys", True):
        ice += strip_parts(planes, segs["valley"], roll / 2)
    add("iceWater", build_surface(ice, H["iceWater"]), layer_material("RT_iceWater", (0.025, 0.028, 0.035), roll - lap, 0.85), roll - lap, ice_rows + 1)
    und_h = 44 * IN
    add("underlayment", build_surface(full_parts(planes), H["underlayment"]), layer_material("RT_underlayment", (0.26, 0.28, 0.30), und_h, 0.7), und_h, rows(und_h))
    starter = strip_parts(planes, segs["eave"], 7 * IN) + strip_parts(planes, segs["rake"], 7 * IN)
    add("starter", build_surface(starter, H["starter"]), layer_material("RT_starter", (0.03, 0.03, 0.03), 1000.0, 0.85), 1000.0, 1)
    spacing = 39.375 * IN / (6 if nails_per >= 6 else 4)
    add("nails", nail_buf(planes, exposure, spacing, H["nails"]), layer_material("RT_nails", (0.55, 0.56, 0.58), exposure, 0.35, 0.9), exposure, rows(exposure))
    cov_mat = layer_material("RT_covering", row_h=exposure, procedural={"exposure": exposure, "palette": cfg.get("palette") or ["#3a3d42", "#2b2d30", "#4d5157", "#1f2124"]})
    add("covering", build_surface(full_parts(planes), H["covering"], exposure, 0.005), cov_mat, exposure, rows(exposure))
    has_vent = bool(segs["ridge"]) and cfg.get("ridge_vent", True)
    if has_vent:
        vent_lines = []
        for l in segs["ridge"]:
            ln = (l["B"] - l["A"]).length
            if ln > 0.9:
                d = (l["B"] - l["A"]).normalized()
                vent_lines.append({"A": l["A"] + d * 0.3, "B": l["B"] - d * 0.3, "planes": l["planes"]})
        add("ridgeVent", cap_buf(vent_lines, 0.14, H["covering"] + 0.036), layer_material("RT_ridgeVent", (0.02, 0.02, 0.022), 1000.0, 0.7), 1000.0, 1)
    cap = cap_buf(segs["hip"] + ([] if has_vent else segs["ridge"]))
    if has_vent:
        extra = cap_buf(segs["ridge"], 0.17, H["covering"] + 0.044)
        n0 = len(cap.verts)
        cap.verts += extra.verts
        cap.faces += [tuple(i + n0 for i in f) for f in extra.faces]
        cap.uvs += extra.uvs
        cap.up += extra.up
        cap.along += extra.along
    add("ridgeCap", cap, layer_material("RT_ridgeCap", row_h=1000.0, procedural={"exposure": 5 * IN, "palette": cfg.get("palette") or ["#3a3d42", "#2b2d30", "#4d5157"]}), 1000.0, 1)
    for s in srcs:
        s.hide_render = True
    area = sum(p.area for p in planes)
    measure = {k: sum((s["A"] - s["B"]).length for s in v) for k, v in segs.items()}
    log(f"layers: {len(made)} on {len(planes)} planes, {area / 9.290304:.1f} squares")
    return {"layers": list(made), "planes": len(planes), "squares": round(area / 9.290304, 2), "lengths_m": {k: round(v, 2) for k, v in measure.items()}}


# ---------------------------------------------------------------------------
# covering material

def apply_material(cfg):
    ob = bpy.data.objects.get("RT_layer_covering")
    if not ob:
        raise RuntimeError("Run the layers command first.")
    row_h = ob.get("rt_row_h", 5.625 * IN)
    img = cfg.get("image")
    if img:
        img = os.path.abspath(os.path.expanduser(img))
        w_in = float(cfg.get("width_in", 36))
        size = (w_in * IN, float(cfg.get("height_in", 0)) * IN or None)
        if not size[1]:
            im = bpy.data.images.load(img, check_existing=True)
            size = (size[0], size[0] * im.size[1] / max(1, im.size[0]))
        mat = layer_material("RT_covering", row_h=row_h, image=img, size_m=size, rough=float(cfg.get("roughness", 0.86)),
                             metal=0.5 if cfg.get("category") == "metal" else 0.0, bump=float(cfg.get("relief", 0.4)), rotation_deg=float(cfg.get("rotation", 0)))
    else:
        mat = layer_material("RT_covering", row_h=row_h, procedural={"exposure": row_h, "palette": cfg.get("palette") or ["#3a3d42", "#2b2d30", "#4d5157", "#1f2124"]})
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    log(f"covering material: {img or 'procedural'}")
    return {"material": mat.name, "image": img}


# ---------------------------------------------------------------------------
# build sequence

def default_plan():
    S = lambda t, d, acts, detail="": {"title": t, "duration": d, "detail": detail, "actions": acts}
    return {"title": "Full replacement", "steps": [
        S("Tear off existing shingles", 6, [{"layer": "oldShingles", "op": "remove"}]),
        S("Remove old felt", 2, [{"layer": "oldFelt", "op": "remove"}]),
        S("Replace damaged deck", 2.5, [{"layer": "deckRepair", "op": "install"}]),
        S("Drip edge at eaves", 1.5, [{"layer": "dripEdge", "op": "install", "from": 0, "to": 0.5}]),
        S("Ice & water shield", 2.5, [{"layer": "iceWater", "op": "install"}]),
        S("Underlayment", 3, [{"layer": "underlayment", "op": "install"}]),
        S("Drip edge at rakes", 1.5, [{"layer": "dripEdge", "op": "install", "from": 0.5, "to": 1}]),
        S("Starter strip", 1.5, [{"layer": "starter", "op": "install"}]),
        S("Shingles", 8, [{"layer": "covering", "op": "install"}, {"layer": "nails", "op": "install"}]),
        S("Ridge vent", 1.5, [{"layer": "ridgeVent", "op": "install"}]),
        S("Hip & ridge cap", 2, [{"layer": "ridgeCap", "op": "install"}]),
    ]}


def _reveal_node(ob):
    if not ob.data.materials:
        return None
    m = ob.data.materials[0]
    return m.node_tree.nodes.get("RT_Reveal") if m and m.node_tree else None


def animate_build(cfg):
    plan = cfg.get("plan") or default_plan()
    if isinstance(plan, str):
        with open(os.path.expanduser(plan)) as f:
            plan = json.load(f)
    fps = int(cfg.get("fps", 24))
    speed = float(cfg.get("speed", 1.0))  # plan seconds per real second
    start = int(cfg.get("frame_start", 1))
    scene = bpy.context.scene
    scene.render.fps = fps
    layers = {o["rt_layer"]: o for o in bpy.data.objects if o.get("rt_layer")}
    touched = {a["layer"] for s in plan["steps"] for a in s.get("actions", [])}
    deck_installed = any(a["layer"] == "deck" and a.get("op", "install") == "install" for s in plan["steps"] for a in s.get("actions", []))
    state = {lid: (1.0 if lid in ("oldShingles", "oldFelt") else (0.0 if lid in touched else 1.0)) for lid in layers}
    if not deck_installed and "deck" in state:
        state["deck"] = 1.0
    t = 0.0
    keys = {lid: [(start, v)] for lid, v in state.items()}
    for s in plan["steps"]:
        dur = max(0.2, float(s.get("duration", 2))) / speed
        f0, f1 = start + t * fps, start + (t + dur) * fps
        for a in s.get("actions", []):
            lid = a["layer"]
            if lid not in layers:
                continue
            fr, to = float(a.get("from", 0)), float(a.get("to", 1))
            op = a.get("op", "install")
            if op == "install":
                keys[lid] += [(f0, fr), (f1, to)]
            elif op == "remove":
                keys[lid] += [(f0, to), (f1, fr)]
            elif op == "show":
                keys[lid] += [(f0, 1.0)]
            elif op == "hide":
                keys[lid] += [(f0, 0.0)]
        t += dur
    end = int(start + t * fps) + int(cfg.get("hold_seconds", 2) * fps)
    for lid, ks in keys.items():
        ob = layers[lid]
        node = _reveal_node(ob)
        if not node:
            continue
        km = float(ob.get("rt_key_max", 1))
        sock = node.outputs[0]
        nt = ob.data.materials[0].node_tree
        if nt.animation_data:
            nt.animation_data_clear()
        for frame, frac in ks:
            sock.default_value = -0.001 if frac <= 0 else (km + 1.0 if frac >= 1 else frac * km)
            sock.keyframe_insert("default_value", frame=frame)
        _linear(nt)
    scene.frame_start, scene.frame_end = start, end
    if cfg.get("orbit", True):
        _orbit_camera(start, end, float(cfg.get("orbit_degrees", 50)))
    log(f"build: {len(plan['steps'])} steps, frames {start}-{end}")
    return {"frame_start": start, "frame_end": end, "steps": len(plan["steps"])}


def _linear(idblock):
    ad = idblock.animation_data
    action = ad.action if ad else None
    if not action:
        return
    curves = []
    if hasattr(action, "fcurves"):
        try:
            curves = list(action.fcurves)
        except Exception:
            curves = []
    if not curves and hasattr(action, "layers"):  # Blender 4.4+/5.x layered actions
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    curves += list(bag.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def explode(cfg):
    gap = float(cfg.get("gap", 0.8))
    animate = cfg.get("animate", True)
    fps = bpy.context.scene.render.fps
    obs = sorted([o for o in bpy.data.objects if o.get("rt_layer") and o["rt_layer"] not in ("oldFelt", "oldShingles", "deckRepair")], key=lambda o: o["rt_level"])
    cam = bpy.context.scene.camera
    start = int(cfg.get("frame_start", bpy.context.scene.frame_start))
    f_open, f_hold = start + int(1 * fps), start + int(3 * fps)
    f_close, f_end = f_hold + int(cfg.get("hold_seconds", 4) * fps), f_hold + int(cfg.get("hold_seconds", 4) * fps) + int(2 * fps)
    lbl_mat = simple_material("RT_LabelText", (0.95, 0.96, 0.98), 0.5)
    for level, o in enumerate(obs):
        z = level * gap
        o.animation_data_clear()
        if animate:
            for fr, val in ((start, 0.0), (f_open, 0.0), (f_hold, z), (f_close, z), (f_end, 0.0)):
                o.location.z = val
                o.keyframe_insert("location", index=2, frame=fr)
        else:
            o.location.z = z
        if cfg.get("labels", True):
            _label(o, lbl_mat, cam, animate, (start, f_open, f_hold, f_close, f_end))
    if animate:
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = start, f_end
    log(f"explode: {len(obs)} layers, gap {gap} m")
    return {"layers": [o["rt_layer"] for o in obs], "frame_end": f_end if animate else None}


def _label(o, mat, cam, animate, frames):
    name = f"RT_label_{o['rt_layer']}"
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = f"{o['rt_label']}  ·  {o['rt_spec']}"
    cu.size = 0.32
    cu.align_y = "CENTER"
    t = bpy.data.objects.new(name, cu)
    t.data.materials.append(mat)
    o.users_collection[0].objects.link(t)
    # anchor: the vertex furthest toward the front-right
    vs = o.data.vertices
    best = max(range(0, len(vs), max(1, len(vs) // 3000)), key=lambda i: vs[i].co.x - vs[i].co.y * 0.35 - vs[i].co.z * 0.5)
    t.parent = o
    t.location = vs[best].co + Vector((0.6, 0, 0.05))
    if cam:
        c = t.constraints.new("TRACK_TO")
        c.target = cam
        c.track_axis = "TRACK_Z"
        c.up_axis = "UP_Y"
    if animate:
        s, f_open, f_hold, f_close, f_end = frames
        for fr, val in ((s, 0.0), (f_open + (f_hold - f_open) // 2, 0.0), (f_hold, 1.0), (f_close, 1.0), (f_close + 6, 0.0)):
            t.scale = (val, val, val)
            t.keyframe_insert("scale", frame=fr)


# ---------------------------------------------------------------------------
# scene: sun, sky, ground, camera, render settings

def setup_scene(cfg):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = int(cfg.get("samples", 128))
    cy.use_denoising = True
    cy.use_adaptive_sampling = True
    device = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    device = "GPU"
                    break
            except Exception:
                continue
    except Exception:
        pass
    cy.device = device
    sc.render.resolution_x, sc.render.resolution_y = cfg.get("resolution", (3840, 2160))
    sc.render.resolution_percentage = int(cfg.get("percentage", 100))
    sc.render.image_settings.file_format = "PNG"
    for vt in ("AgX", "Filmic"):
        try:
            sc.view_settings.view_transform = vt
            break
        except Exception:
            continue
    # world: physical sky
    world = bpy.data.worlds.get("RT_Sky") or bpy.data.worlds.new("RT_Sky")
    _use_nodes(world)
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    kinds = sky.bl_rna.properties["sky_type"].enum_items.keys()
    for k in ("MULTIPLE_SCATTERING", "NISHITA", "HOSEK_WILKIE"):
        if k in kinds:
            sky.sky_type = k
            break
    elev = math.radians(float(cfg.get("sun_elevation", 38)))
    rot = math.radians(float(cfg.get("sun_azimuth", 215)))
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation, sky.sun_rotation = elev, rot
        if hasattr(sky, "sun_disc"):
            sky.sun_disc = False  # the sun lamp below carries direct light
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = float(cfg.get("sky_strength", 0.35))
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    sc.world = world
    sun = bpy.data.objects.get("RT_Sun")
    if not sun:
        sun = bpy.data.objects.new("RT_Sun", bpy.data.lights.new("RT_Sun", "SUN"))
        sc.collection.objects.link(sun)
    sun.data.energy = float(cfg.get("sun_strength", 4.0))
    sun.data.angle = math.radians(0.6)
    sun.rotation_euler = (math.pi / 2 - elev, 0, rot)
    if cfg.get("ground", True) and not bpy.data.objects.get("RT_Ground"):
        me = bpy.data.meshes.new("RT_Ground")
        s = 400
        me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("RT_Ground", me)
        g.data.materials.append(simple_material("RT_Grass", (0.10, 0.16, 0.06), 0.95))
        sc.collection.objects.link(g)
    _camera(cfg)
    log(f"scene: Cycles {device}, {cy.samples} spp, {sc.render.resolution_x}x{sc.render.resolution_y}")
    return {"device": device}


def _scene_center():
    pts = [o.matrix_world @ Vector(c) for o in bpy.data.objects if o.type == "MESH" and o.name != "RT_Ground" for c in o.bound_box]
    if not pts:
        return Vector((0, 0, 3)), 10.0
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (mn + mx) / 2, (mx - mn).length


def _camera(cfg):
    sc = bpy.context.scene
    cam = bpy.data.objects.get("RT_Camera")
    if not cam:
        cam = bpy.data.objects.new("RT_Camera", bpy.data.cameras.new("RT_Camera"))
        sc.collection.objects.link(cam)
    cam.data.lens = float(cfg.get("lens", 35))
    center, size = _scene_center()
    fov = 2 * math.atan(cam.data.sensor_width / 2 / cam.data.lens)
    pivot = bpy.data.objects.get("RT_CamPivot")
    if not pivot:
        pivot = bpy.data.objects.new("RT_CamPivot", None)
        sc.collection.objects.link(pivot)
    pivot.location = center
    # fit the bounding sphere, then scale by `distance` (1.0 = tight fit)
    dist = (size / 2) / math.tan(fov / 2) * float(cfg.get("distance", 1.0)) * 1.08
    az = math.radians(float(cfg.get("view_azimuth", -35)))
    el = math.radians(float(cfg.get("view_elevation", 24)))
    cam.parent = pivot
    cam.location = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist
    direction = -cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    return cam


def _orbit_camera(start, end, degrees):
    pivot = bpy.data.objects.get("RT_CamPivot")
    if not pivot:
        return
    pivot.animation_data_clear()
    pivot.rotation_euler.z = 0
    pivot.keyframe_insert("rotation_euler", index=2, frame=start)
    pivot.rotation_euler.z = math.radians(degrees)
    pivot.keyframe_insert("rotation_euler", index=2, frame=end)
    _linear(pivot)


def render(cfg):
    sc = bpy.context.scene
    out = os.path.abspath(os.path.expanduser(cfg.get("output", "//roof_render")))
    if cfg.get("animation"):
        os.makedirs(out, exist_ok=True)
        sc.render.filepath = os.path.join(out, "frame_")
        if cfg.get("frame_step"):
            sc.frame_step = int(cfg["frame_step"])
        bpy.ops.render.render(animation=True)
        log(f"frames -> {out}")
        return {"frames": out}
    if cfg.get("frame") is not None:
        sc.frame_set(int(cfg["frame"]))
    path = out if out.lower().endswith(".png") else out + ".png"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    log(f"still -> {path}")
    return {"still": path}


def export_glb(cfg):
    path = os.path.abspath(os.path.expanduser(cfg.get("output", "roof-layers.glb")))
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if o.name.startswith("RT_layer_") or (cfg.get("include_house", True) and any(c.name == "RT_House" for c in o.users_collection)):
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_extras=True, export_apply=True)
    log(f"glb -> {path}")
    return {"glb": path}


# ---------------------------------------------------------------------------

def run(cfg):
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    if isinstance(cfg, list):  # several commands in one Blender session
        return [run(c) for c in cfg]
    cmd = cfg.get("cmd", "all")
    res = {}
    if cmd == "demo":
        res = make_demo_house(float(cfg.get("pitch", 6)), cfg.get("preset", "ranch-hip"))
    elif cmd == "layers":
        res = build_layers(cfg)
    elif cmd == "material":
        res = apply_material(cfg)
    elif cmd == "scene":
        res = setup_scene(cfg)
    elif cmd == "build":
        res = animate_build(cfg)
    elif cmd == "explode":
        res = explode(cfg)
    elif cmd == "render":
        res = render(cfg)
    elif cmd == "export":
        res = export_glb(cfg)
    elif cmd == "ensure":
        # headless runs start from a plain .blend: make sure the layer stack exists
        if cfg.get("fresh"):
            # factory startup scene: drop the default cube, camera and light
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o, do_unlink=True)
        if not any(o.get("rt_layer") for o in bpy.data.objects):
            if not roof_source(cfg.get("roof"))[0]:
                res["demo"] = make_demo_house(float(cfg.get("pitch", 6)), cfg.get("preset", "ranch-hip"))
            res["layers"] = build_layers(cfg)
        else:
            res["layers"] = "existing"
    elif cmd == "save":
        path = os.path.abspath(os.path.expanduser(cfg["path"]))
        bpy.ops.wm.save_as_mainfile(filepath=path)
        res = {"blend": path}
    elif cmd == "all":
        if not roof_source(cfg.get("roof"))[0]:
            res["demo"] = make_demo_house(float(cfg.get("pitch", 6)), cfg.get("preset", "ranch-hip"))
        res["layers"] = build_layers(cfg)
        if cfg.get("image"):
            res["material"] = apply_material(cfg)
        res["scene"] = setup_scene(cfg)
        mode = cfg.get("mode", "still")
        if mode == "build":
            res["build"] = animate_build(cfg)
        elif mode == "explode":
            res["explode"] = explode(cfg)
        if cfg.get("output"):
            res["render"] = render(cfg)
    else:
        raise ValueError(f"unknown cmd {cmd}")
    print("RT_RESULT " + json.dumps(res))
    return res


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if argv:
        arg = argv[0].strip()
        run(arg if arg[:1] in "{[" else open(arg).read())
