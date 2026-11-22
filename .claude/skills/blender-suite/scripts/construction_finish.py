"""Construction-grade finish on a construction_kit.py building, from the same building.json: lap siding boards
(starter strip; courses cut at corner boards, casings and rakes), trim (corner boards, fascia, rake boards,
soffits), double-hung windows and a panel door (references/construction-detail.md). Lengths are inches.
Also the shared geometry both scripts use: equal shapes share one mesh (linked duplicates).
Usage:
  blender -b f.blend -P construction_finish.py -- --build building.json [--only siding trim windows doors] --save F
  MCP: import construction_finish as cf; print(cf.run(build="C:/work/building.json"))
Returns {"ok", "built", "parts", "tris", "meshes"}. Counts and checks: construction_kit.py --plan.
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bpyx as bx  # noqa: E402

IN = 0.0254
WALLS = ("front", "back", "left", "right")
STAGES = ("siding", "trim", "windows", "doors")
TAG = {"siding": "Siding", "trim": "Trim", "windows": "Windows", "doors": "Doors"}
JT, GAP, TH, SWEEP, CAP = 0.75, 0.125, 1.0, 0.25, 0.75   # jamb, slab gap, threshold, sweep gap, drip cap height
KNOB = [(0, 0), (1.25, 0), (1.25, 0.375), (0.4, 0.375), (0.4, 1.0), (0.95, 1.1), (1.1, 1.45), (1.0, 1.85),
        (0.6, 2.1), (0, 2.15)]                          # rose, neck, knob: radius, distance off the slab
MATS = {"M_Concrete": ("#8c8a84", .9, 0), "M_Lumber": ("#c8a36a", .8, 0), "M_OSB": ("#b38b52", .85, 0),
        "M_Window": ("#f1f0ea", .4, 0), "M_Glass": ("#dfe8ea", .02, 0), "M_Hardware": ("#a9a79f", .35, 1),
        "M_Wrap": ("#e9e9e4", .7, 0), "M_Tape": ("#3a3a3a", .5, 0), "M_Screen": ("#2e2e2e", .8, 0)}
RULES = {
    "Pad": "footprint + margin each side", "Plate": "bottom plate (cut at doors), double top plate lapped "
    "3.5 in. at corners (R602.3.2)", "Stud": "end stud each end; layout studs every oc from the wall's start "
    "(R602.3(5)); dropped if touching an end stud, king or jack; cripples inside an opening",
    "King": "1 each side (R602.7.5, span <= 4 ft)", "Jack": "1 each side (R602.7(1) NJ)",
    "Header": "2 members on edge (R602.7(1) span)", "Cripple": "layout inside an opening: above the header, "
    "below a window sill", "Sill": "rough sill per window", "Rafter": "pairs at each end and every rafter_oc_in, "
    "+ a barge pair per rake (R802.4.1(7) span)", "Ridge": "as deep as the plumb cut (R802.3)", "Tie": "beside "
    "each pair between the gable walls (R802.5.2)", "GableStud": "on the wall layout, plate to end rafter",
    "Sheathing": "4 ft panels from the corner, cut at openings and the rake", "Siding": "course pieces between "
    "corner boards, casings and rakes", "Siding_course": "ceil((top - bottom) / exposure)", "Starter": "strip "
    "(board - exposure) under course 1", "Trim": "corners 2 each, fascia 2, rakes 4, soffits 6",
    "Window": "frame, 2 sashes, casing, drip cap", "Door": "jambs, stops, threshold, panel slab, 3 hinges, 2 knobs"}


class Bad(Exception):
    pass


def need(d, k, where):
    if d.get(k) is None:
        raise Bad(f"{where}.{k} is missing: look it up or ask before building, never assume it")
    return d[k]


# ---------------------------------------------------------------------------- geometry (inches, world axes)

def ext(pts, f, a, b):
    """Outline pts (2D) extruded from depth a to b (numbers, or callables of the point); f(p, depth) -> xyz."""
    n, g = len(pts), (lambda t, p: t(p) if callable(t) else t)
    return [f(p, g(a, p)) for p in pts] + [f(p, g(b, p)) for p in pts], \
        [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]


def rect(u0, u1, h0, h1):
    return [(u0, h0), (u1, h0), (u1, h1), (u0, h1)]


def xz(p, y):
    return p[0], y, p[1]


def merge(parts):
    V, F = [], []
    for v, f in parts:
        F += [tuple(i + len(V) for i in q) for q in f]
        V += v
    return V, F


def clip(poly, a, b, c):
    """Part of a convex polygon where a*u + b*h <= c."""
    out = []
    for i, p in enumerate(poly):
        q = poly[i - 1]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if (fp <= 0) != (fq <= 0):
            t = fq / (fq - fp)
            out.append((q[0] + t * (p[0] - q[0]), q[1] + t * (p[1] - q[1])))
        if fp <= 0:
            out.append(p)
    return out


def pieces(u0, u1, h0, h1, region=(), cuts=()):
    """A rectangle minus cut rectangles (u0, u1, h0, h1), clipped to the region's half-planes: convex polygons,
    left to right. A board that crosses an opening's edge comes out notched (one piece per side)."""
    cs = [c for c in cuts if c[0] < u1 and c[1] > u0 and c[2] < h1 and c[3] > h0]
    xs, out = sorted({u0, u1, *[min(max(v, u0), u1) for c in cs for v in c[:2]]}), []
    for a, b in zip(xs, xs[1:]):
        hs = [(h0, h1)]
        for c in cs:
            if c[0] < (a + b) / 2 < c[1]:
                hs = [r for lo, hi in hs for r in ((lo, min(hi, c[2])), (max(lo, c[3]), hi)) if r[1] - r[0] > 1e-6]
        for lo, hi in hs:
            poly = rect(a, b, lo, hi)
            for hp in region:
                poly = clip(poly, *hp)
            poly = [p for i, p in enumerate(poly) if abs(p[0] - poly[i - 1][0]) + abs(p[1] - poly[i - 1][1]) > 1e-6]
            if len(poly) > 2 and abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(poly, poly[1:] + poly[:1]))) > 1:
                out.append(poly)
    return out


def skin(w, G, off=None):
    """(u, d, h) -> xyz: u along +x or +y, d outward, h up; d = 0 on the house wrap's face (off=0: the sheathing's)."""
    o, W, D = G["tsh"] + (G["dw"] if off is None else off), G["W"], G["D"]
    return {"front": lambda u, d, h: (u, -o - d, h), "back": lambda u, d, h: (u, D + o + d, h),
            "left": lambda u, d, h: (-o - d, u, h), "right": lambda u, d, h: (W + o + d, u, h)}[w]


def on(f, poly, d0, d1):
    return ext(poly, lambda p, d: f(p[0], d, p[1]), d0, d1)


def lathe(prof, n, at):
    """Solid of revolution: prof [(radius, z)], radius 0 is a pole; at(x, y, z) -> world."""
    V, F, rings = [], [], []
    for r, z in prof:
        k = 1 if r < 1e-9 else n
        rings.append(list(range(len(V), len(V) + k)))
        V += [at(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(k)]
    for a, b in zip(rings, rings[1:]):
        F += [tuple(dict.fromkeys((a[i % len(a)], a[(i + 1) % n % len(a)], b[(i + 1) % n % len(b)], b[i % len(b)])))
              for i in range(n)]
    return V, [q for q in F if len(q) > 2]


class Sink:
    """Collects parts. Dry (plan): names, groups, bounds, triangles. Build: objects; equal shapes share a mesh."""

    def __init__(s, build, G, colors=None):
        s.build, s.G, s.parts, s.cache, s.colors = build, G, [], {}, colors or {}

    def add(s, name, VF, mat, grp, stage):
        V, F = VF
        lo, hi = [min(v[i] for v in V) for i in range(3)], [max(v[i] for v in V) for i in range(3)]
        s.parts.append((name, grp, lo, hi, sum(len(f) - 2 for f in F)))
        if not s.build:
            return
        key = (mat, tuple(round(c - lo[i], 4) for v in V for i, c in enumerate(v)), tuple(F))
        me = s.cache.get(key)
        if me is None:
            import bmesh
            bm = bmesh.new()
            vs = [bm.verts.new([(c - lo[i]) * IN for i, c in enumerate(v)]) for v in V]
            for q in F:
                bm.faces.new([vs[i] for i in q])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            me = s.cache[key] = bpy.data.meshes.new(name)
            bm.to_mesh(me)
            bm.free()
            me.materials.append(material(mat, s.colors))
        ob = bpy.data.objects.new(name, me)
        ob.location = [c * IN for c in lo]
        coll(f"{s.G['P']}_{stage}").objects.link(ob)


def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def clear(name):
    c = bpy.data.collections.get(name)
    for o in list(c.objects) if c else []:
        bpy.data.objects.remove(o, do_unlink=True)
    for m in [m for m in bpy.data.meshes if not m.users]:
        bpy.data.meshes.remove(m)


def material(name, colors):
    m = bpy.data.materials.get(name)
    if m:
        return m
    hexc, rough, metal = MATS.get(name) or (colors.get(name, "#cccccc"), .5, 0)
    rgb = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    p = bx.node(m.node_tree, "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*[c / 12.92 if c <= 0.04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb], 1)
    p.inputs["Roughness"].default_value, p.inputs["Metallic"].default_value = rough, metal
    p.inputs["Transmission Weight"].default_value = 1.0 if name == "M_Glass" else 0.0
    p.inputs["Alpha"].default_value = .4 if name == "M_Screen" else 1.0   # insect screen: mostly see-through
    return m


# ---------------------------------------------------------------------------- finish parts

def dims(s, G):
    sd, tr = s.get("siding") or {}, s.get("trim") or {}
    d = dict(Wb=need(sd, "board_in", "siding"), E=need(sd, "exposure_in", "siding"), t=need(sd, "thickness_in", "siding"),
             cw=need(tr, "corner_in", "trim"), cs=need(tr, "casing_in", "trim"), ct=tr.get("thickness_in", 1.0),
             h0=G["pad"] - sd.get("lap_in", 1.0) if G["mg"] <= 0 else G["pad"] + sd.get("clear_in", 1.0))
    # flush slab: the first course laps 1 in. below the bottom plate, so no plate or sheathing edge shows; a slab
    # that sticks out past the wall: siding and trim stop 1 in. above it (James Hardie)
    d["a"] = d["t"] * d["Wb"] / d["E"]   # the butt stands off the wall so each board lies on the one below
    if d["ct"] < d["a"] + d["t"]:
        raise Bad(f"trim {d['ct']} in. is thinner than the siding ({d['a'] + d['t']:.2f} in.): use 5/4 trim")
    return d


def zso(G, x):
    return G["zb"](x) - G["tv"]   # underside of the soffit


def door_geom(o, G):
    u, fw, sb = o["center_ft"] * 12, o["width_in"] + 2 * GAP + 2 * JT, G["pad"] + TH + SWEEP
    return u - fw / 2, u + fw / 2, sb, sb + o["height_in"], sb + o["height_in"] + GAP + JT


def zones(s, G, w, d):
    """This wall's casings and drip caps (u0, u1, h0, h1): the siding stops at them."""
    out, cs = [], d["cs"]
    for o in [o for o in s.get("openings") or [] if o["wall"] == w]:
        if o["type"] == "door":
            ul, ur, _, _, top = door_geom(o, G)
            out.append((ul - cs, ur + cs, -1e9, top + cs + CAP))
        else:
            u, hb = o["center_ft"] * 12, G["pad"] + o["sill_in"]
            out.append((u - o["width_in"] / 2 - cs, u + o["width_in"] / 2 + cs, hb - cs, hb + o["height_in"] + cs + CAP))
    return out


def siding(sk, s, G):
    d, P, W, D, o, sl = dims(s, G), G["P"], G["W"], G["D"], G["tsh"] + G["dw"], G["s"]
    Wb, E, t, a, h0 = d["Wb"], d["E"], d["t"], d["a"], d["h0"]
    for w in WALLS:
        f = skin(w, G)
        if w in ("left", "right"):
            u0, u1, reg, top = -o + d["cw"], D + o - d["cw"], (), zso(G, -o - a - t)
        else:
            c = G["ztp"] - G["st"][1] * sl - G["tv"]
            u0, u1, top = -o - d["ct"] + d["cw"], W + o + d["ct"] - d["cw"], zso(G, W / 2)
            reg = [(-sl, 1, c), (sl, 1, c + W * sl)]
        cuts, i = zones(s, G, w, d), -1               # course 0 is the starter strip
        while h0 + i * E < top:
            hb = h0 + i * E

            def back(p, hb=hb):
                return a * (1 - (p[1] - hb) / Wb)
            for k, q in enumerate(pieces(u0, u1, max(hb, h0), min(hb + Wb, top), reg, cuts), 1):
                VF = on(f, q, back, lambda p, b=back: b(p) + t)
                if i < 0:
                    sk.add(f"{P}_Starter_{w}_{k}", VF, "M_Siding", [f"{P}_Starter_{w}_*"], "Siding")
                else:
                    sk.add(f"{P}_Siding_{w}_{i + 1:02d}_{k}", VF, "M_Siding",
                           [f"{P}_Siding_{w}_*"] + ([f"{P}_Siding_{w}_*_1"] if k == 1 else []), "Siding")
            i += 1


def trim(sk, s, G):
    d, P, W, D, o, zb, zt = dims(s, G), G["P"], G["W"], G["D"], G["tsh"] + G["dw"], G["zb"], G["zt"]
    ct, cw, n = d["ct"], d["cw"], 0
    for w in WALLS:                                  # corner boards: the gable-face board covers the other's edge
        side, f = w in ("left", "right"), skin(w, G)
        for u0, u1 in [(-o, -o + cw), (D + o - cw, D + o)] if side else [(-o - ct, cw - o - ct), (W + o + ct - cw, W + o + ct)]:
            z0, z1 = (zso(G, -o - ct),) * 2 if side else (zso(G, u0), zso(G, u1))
            n += 1
            sk.add(f"{P}_Trim_Corner_{n}", on(f, [(u0, d["h0"]), (u1, d["h0"]), (u1, z1), (u0, z0)], 0, ct), "M_Trim",
                   [f"{P}_Trim_Corner_*"], "Trim")
    ov, xt, yb, ovr, tv, fa, dv = G["ove"], G["fa"][0] - G["ove"], G["yb"], G["ovr"], G["tv"], G["fa"][1], G["rk"][1] * G["k"]
    prof = {"Fascia": [(-ov, zt(-ov) - fa), (xt, zt(-ov) - fa), (xt, zt(xt)), (-ov, zt(-ov))],   # top bevelled
            "Rake": [(-ov, zt(-ov) - dv), (W / 2, zt(W / 2) - dv), (W / 2, zt(W / 2)), (-ov, zt(-ov))],
            "Eave": [(xt, zb(xt) - tv), (-o, zb(-o) - tv), (-o, zb(-o)), (xt, zb(xt))],
            "Rks": [(-o, zb(-o) - tv), (W / 2, zb(W / 2) - tv), (W / 2, zb(W / 2)), (-o, zb(-o))]}
    rows = [("Fascia_", "Fascia", -yb, D + yb), ("Rake_front_", "Rake", -ovr, -yb), ("Rake_back_", "Rake", D + yb, D + ovr)]
    rows += [("Soffit_Eave_", "Eave", -yb, D + yb), ("Soffit_Rake_front_", "Rks", -yb, -o),
             ("Soffit_Rake_back_", "Rks", D + o, D + yb)] if tv else []
    for sd in "LR":
        for nm, key, y0, y1 in rows:
            pts = prof[key] if sd == "L" else [(W - x, z) for x, z in prof[key]]
            sk.add(f"{P}_Trim_{nm}{sd}", ext(pts, xz, y0, y1), "M_Trim", [f"{P}_Trim_{nm.split('_')[0]}_*"], "Trim")


def cap(f, u0, u1, h, ct):
    """Drip cap over a head casing, its top bevelled to shed water."""
    return ext([(0, h), (ct + 0.25, h), (ct + 0.25, h + 0.25), (0, h + CAP)], lambda p, u: f(u, p[0], p[1]), u0, u1)


def windows(sk, s, G):
    d, P, n, jd = dims(s, G), G["P"], 0, G["tsh"] + G["st"][1]
    cs, ct = d["cs"], d["ct"]
    for o in [o for o in s.get("openings") or [] if o["type"] == "window"]:
        if o.get("style", "double_hung") != "double_hung":
            raise Bad(f"window style {o.get('style')!r}: only double_hung is built in this round")
        n += 1
        f, u, hb = skin(o["wall"], G), o["center_ft"] * 12, G["pad"] + o["sill_in"]
        ul, ur, ht = u - o["width_in"] / 2, u + o["width_in"] / 2, hb + o["height_in"]

        def part(name, VF, mat="M_Window", n=n):
            sk.add(f"{P}_Window_{n}_{name}", VF, mat, [f"{P}_Window_{n}_*"] +
                   ([f"{P}_Window_*_Frame_Head"] if name == "Frame_Head" else []), "Windows")

        def bxw(u0, u1, h0, h1, d0, d1):
            return on(f, rect(u0, u1, h0, h1), d0, d1)
        part("Frame_Head", bxw(ul, ur, ht - JT, ht, -jd, 0))
        part("Frame_Sill", bxw(ul, ur, hb, hb + 1.5, -jd, 0))
        for sd, x in (("L", ul), ("R", ur - JT)):
            part(f"Frame_{sd}", bxw(x, x + JT, hb + 1.5, ht - JT, -jd, 0))
        il, ir, ib, it = ul + JT, ur - JT, hb + 1.5, ht - JT
        hs = (it - ib + 1.5) / 2                         # meeting rails overlap 1.5 in.
        for sn, h0, h1, d0, rb, rt in (("SashU", it - hs, it, -1.875, 1.5, 2.0), ("SashL", ib, ib + hs, -3.25, 2.5, 1.5)):
            d1, dm = d0 + 1.375, d0 + 0.6875
            for nm, q in (("StileL", (il, il + 2, h0, h1)), ("StileR", (ir - 2, ir, h0, h1)),
                          ("RailBottom", (il + 2, ir - 2, h0, h0 + rb)), ("RailTop", (il + 2, ir - 2, h1 - rt, h1))):
                part(f"{sn}_{nm}", bxw(*q, d0, d1))
            part(f"{sn}_Glass", bxw(il + 1.625, ir - 1.625, h0 + rb - .375, h1 - rt + .375, dm - .25, dm + .25), "M_Glass")
        for nm, q in (("Head", (ul - cs, ur + cs, ht, ht + cs)), ("Bottom", (ul - cs, ur + cs, hb - cs, hb)),
                      ("L", (ul - cs, ul, hb, ht)), ("R", (ur, ur + cs, hb, ht))):
            part(f"Casing_{nm}", bxw(*q, 0, ct), "M_Trim")
        part("DripCap", cap(f, ul - cs, ur + cs, ht + cs, ct), "M_Trim")


def frustum(f, u0, u1, h0, h1, d0, d1, b):
    """Raised panel: base rectangle at depth d0, field inset b at depth d1."""
    V = [f(u, d0, h) for u, h in rect(u0, u1, h0, h1)] + [f(u, d1, h) for u, h in rect(u0 + b, u1 - b, h0 + b, h1 - b)]
    return V, [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]


def doors(sk, s, G):
    d, P, jd, hb = dims(s, G), G["P"], G["tsh"] + G["st"][1], G["pad"]
    cs, ct = d["cs"], d["ct"]
    ds = [o for o in s.get("openings") or [] if o["type"] == "door"]
    if len(ds) > 1:
        raise Bad("one door per building in this round")
    for o in ds:
        f, (ul, ur, sb, se, top) = skin(o["wall"], G), door_geom(o, G)

        def part(name, VF, mat="M_Door"):
            sk.add(f"{P}_Door_{name}", VF, mat, [f"{P}_Door_*"], "Doors")

        def bxd(u0, u1, h0, h1, d0, d1, mat="M_Trim", name=None):
            part(name, on(f, rect(u0, u1, h0, h1), d0, d1), mat)
        part("Threshold", ext([(-jd, hb), (.75, hb), (.75, hb + .3), (-1.25, hb + TH), (-jd, hb + TH)],
                              lambda p, u: f(u, p[0], p[1]), ul, ur), "M_Hardware")
        sl_, sr_, ss, out = ul + JT + GAP, ur - JT - GAP, 0.4375, need(o, "swing", "door") == "out"
        e, i = (-0.25, -2.0) if out else (-1.25, -3.0)       # the slab's exterior and interior faces
        sd = (-jd, i) if out else (e, 0)                       # stops: on the side the slab closes against
        lo = (need(o, "hinges", "door") == "left") == (o["wall"] in ("front", "right"))   # hinges on the low-u side
        for nm, q in (("Jamb_L", (ul, ul + JT, hb + TH, top - JT, -jd, 0)), ("Jamb_R", (ur - JT, ur, hb + TH, top - JT, -jd, 0)),
                      ("Jamb_Head", (ul, ur, top - JT, top, -jd, 0)), ("Stop_L", (ul + JT, ul + JT + ss, hb + TH, top - JT, *sd)),
                      ("Stop_R", (ur - JT - ss, ur - JT, hb + TH, top - JT, *sd)),
                      ("Stop_Head", (ul + JT + ss, ur - JT - ss, top - JT - ss, top - JT, *sd)),
                      ("Casing_L", (ul - cs, ul, d["h0"], top, 0, ct)), ("Casing_R", (ur, ur + cs, d["h0"], top, 0, ct)),
                      ("Casing_Head", (ul - cs, ur + cs, top, top + cs, 0, ct))):
            bxd(*q, name=nm)
        bxd(sl_, sr_, sb, se, i, e, "M_Door", "Slab")
        npan = need(o, "panels", "door")
        if npan % 2 or npan > 6:
            raise Bad(f"door panels {npan}: 0, 2, 4 or 6 (two columns)")
        rows, rails = npan // 2, [8, 4.75][:max(0, npan // 2 - 1)]   # lock rail, then intermediate rail
        wts, free = (21, 22, 10)[:rows], se - sb - 9.5 - 4.75 - sum(rails)   # bottom rail 9.5, top rail 4.75
        pw, h, k = (sr_ - sl_ - 13.5) / 2, sb + 9.5, 0                        # stiles 4.75, mullion 4
        for r in range(rows):
            ph = free * wts[r] / sum(wts)
            for c in range(2):
                u0, k = sl_ + 4.75 + c * (pw + 4), k + 1
                part(f"Panel_E{k}", frustum(f, u0, u0 + pw, h, h + ph, e, e + .25, 1.0))
                part(f"Panel_I{k}", frustum(f, u0, u0 + pw, h, h + ph, i, i - .25, 1.0))
            h += ph + (rails[r] if r < len(rails) else 0)
        hu, sg = (ul + JT, 1) if lo else (ur - JT, -1)
        bf = e if out else i                               # knuckles on the side the door swings to
        dl = sorted((bf, bf + (-1.4 if out else 1.4)))
        for n, hc in enumerate((se - 9, (se + sb + 4) / 2, sb + 13), 1):   # 7 in. from the top, 11 from the bottom
            part(f"Hinge_{n}", merge([on(f, rect(*sorted((hu, hu + sg * .06)), hc - 2, hc + 2), *dl),
                                      on(f, rect(*sorted((hu + sg * .065, hu + sg * GAP)), hc - 2, hc + 2), *dl),
                                      lathe([(0, hc - 2.1), (.25, hc - 2.1), (.25, hc + 2.1), (0, hc + 2.1)], 12,
                                            lambda x, y, z: f(hu + sg * GAP / 2 + x, bf + y, z))]), "M_Hardware")
        ku, kh = (sr_ - 2.375) if lo else (sl_ + 2.375), hb + need(o, "knob_in", "door")   # 2-3/8 in. backset
        part("Knob_Ext", lathe(KNOB, 16, lambda x, y, z: f(ku + x, e + z, kh + y)), "M_Hardware")
        part("Knob_Int", lathe(KNOB, 16, lambda x, y, z: f(ku + x, i - z, kh + y)), "M_Hardware")
        part("DripCap", cap(f, ul - cs, ur + cs, top + cs, ct), "M_Trim")


FN = {"siding": siding, "trim": trim, "windows": windows, "doors": doors}


def build_all(sk, s, G):
    for k in STAGES:
        FN[k](sk, s, G)


def run(build=None, only=None, **_):
    import construction_kit as ck
    bx.object_mode()
    if not build:
        raise ValueError("pass --build building.json")
    s, G = ck.load(build)
    if [x for x in only or [] if x not in STAGES]:
        raise Bad(f"--only: use {', '.join(STAGES)}")
    sk = Sink(True, G, ck.colors(s))
    for k in only or STAGES:
        clear(f"{G['P']}_{TAG[k]}")
        FN[k](sk, s, G)
    return {"ok": True, "built": list(only or STAGES), "parts": len(sk.parts), "tris": sum(p[4] for p in sk.parts),
            "meshes": len(sk.cache)}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--build", help="building.json")
    p.add_argument("--only", nargs="*", help=f"stages: {' '.join(STAGES)} (default: all)")
    p.add_argument("--save", help="save the .blend here")
    bx.cli(run, p)
