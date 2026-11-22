"""Construction-grade building kit: the counts a building.json implies, then pad, wall framing, roof framing,
wall sheathing and the `Roof` planes roof_core.py roofs (references/construction-detail.md). Rectangle, gable
roof, rectangular openings; anything else, or a size the code tables read do not cover, fails with a message.
Usage:
  blender -b -P construction_kit.py -- --plan building.json            (counts and checks only)
  blender -b -P construction_kit.py -- --build building.json [--only pad walls roof_frame sheathing roofing]
      [--roof-core PATH] --save F
  MCP: import construction_kit as ck; print(ck.run(plan="C:/work/building.json"))
roofing: roof_core.py layers on `Roof` (--roof-core, $ROOF_CORE or the RoofTec repo; else a note).
"""
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bpyx as bx  # noqa: E402
import construction_finish as cf  # noqa: E402
from construction_finish import IN, RULES, WALLS, Bad, Sink, clear, coll, ext, merge, need, on, pieces, rect, skin, xz  # noqa: E402

THK = {"1": 0.75, "5/4": 1.0, "2": 1.5, "3": 2.5, "4": 3.5}  # PS 20-20 Table 3, dry
WID = {"2": 1.5, "3": 2.5, "4": 3.5, "6": 5.5, "8": 7.25, "10": 9.25, "12": 11.25}
# IRC R602.7(1) roof + ceiling, 2 members: spans (in.) at ground snow 30/50/70 psf x width 12/24/36 ft
HDR = {"2x4": (48, 37, 31, 41, 31, 26, 36, 28, 24), "2x6": (72, 55, 46, 61, 47, 39, 54, 42, 35)}
NJ2 = {("2x6", 50, 36), ("2x6", 70, 24), ("2x6", 70, 36)}       # cells needing 2 jack studs
RAF70 = {"2x4": 56, "2x6": 83, "2x8": 105, "2x10": 128, "2x12": 148}   # R802.4.1(7): SPF #2, 24 in., 70 psf
STAGES = ("pad", "walls", "roof_frame", "sheathing", "roofing")


def lum(s):
    """Nominal '2x4' -> actual (thickness, width), inches."""
    try:
        t, w = str(s).lower().split("x")
        return THK[t], WID[w]
    except (ValueError, KeyError):
        raise Bad(f"lumber {s!r}: a nominal size such as 2x4, 1x8, 5/4x4") from None


def rise(v):
    try:
        a, b = str(v).split("/")
        return 12 * float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        raise Bad(f"pitch {v!r}: write rise/12") from None


def load(path):
    """(spec, G): sizes in inches; zb(x), zt(x): rafter underside and top."""
    path = os.path.abspath(bpy.path.abspath(path))
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    r, fp = s.get("roof") or {}, s.get("footprint")
    if r.get("type", "gable") != "gable":
        raise Bad(f"roof type {r.get('type')!r}: gable roofs only (a hip or other roof is not supported yet)")
    if not (isinstance(fp, list) and len(fp) == 2 and all(isinstance(v, (int, float)) and v > 0 for v in fp)):
        raise Bad("footprint must be [width, depth]: rectangles only (an L or other outline is not supported)")
    if r.get("ridge_axis", "y") != "y" or s.get("units", "ft") not in ("ft", "in"):
        raise Bad("ridge_axis 'y' (footprint [across the ridge, along it]); units ft or in")
    src, want = need(r, "pitch_source", "roof"), rise(need(r, "pitch", "roof"))
    try:
        with open(os.path.join(os.path.dirname(path), src), encoding="utf-8") as f:
            pr = json.load(f)
    except (OSError, ValueError) as e:
        raise Bad(f"roof.pitch_source {src}: {e}") from None
    if not pr.get("ok") or pr.get("confidence") == "low" or pr.get("agree") is False:
        raise Bad(f"roof.pitch_source {src}: low confidence or sources disagree")
    got = [pr.get("rise_per_12")] + ([rise(pr["nearest_whole"])] if pr.get("whole_within_2_sigma") else [])
    if all(g is None or abs(float(g) - want) > 0.005 for g in got):
        raise Bad(f"roof.pitch {r['pitch']} does not match {src} ({pr.get('label')})")
    fr, pad, tr = (s.get(k) or {} for k in ("framing", "pad", "trim"))
    u = 12.0 if s.get("units", "ft") == "ft" else 1.0
    W, D, sl = fp[0] * u, fp[1] * u, want / 12
    G = dict(P=s.get("prefix", "Bld"), W=W, D=D, H=need(s, "wall_height", "building") * u, s=sl, k=math.hypot(1, sl),
             pad=need(pad, "thickness_in", "pad"), mg=pad.get("margin_in", 0), oc=need(fr, "oc_in", "framing"),
             roc=need(fr, "rafter_oc_in", "framing"), ti=lum(fr.get("tie", "2x4")), ove=need(r, "overhang_eave_in", "roof"),
             ovr=need(r, "overhang_rake_in", "roof"), tsh=(s.get("sheathing") or {}).get("thickness_in", 0.4375),
             tso=tr.get("soffit_in", 0.25) if tr.get("soffit", True) else 0.0, src=src, pr=pr)
    for k, d, n in (("st", fr, "stud"), ("ra", fr, "rafter"), ("ri", fr, "ridge"), ("hd", fr, "header"),
                    ("fa", tr, "fascia"), ("rk", tr, "rake")):
        G[k] = lum(need(d, n, "framing" if d is fr else "trim"))
    G["ztp"], G["Dp"], G["tv"], G["yb"] = G["pad"] + G["H"], G["ra"][1] * G["k"], G["tso"] * G["k"], G["ovr"] - G["rk"][0]
    G["zb"] = lambda x: G["ztp"] + (min(x, W - x) - G["st"][1]) * sl   # rafter underside: seat at the plate's inner edge
    G["zt"] = lambda x: G["zb"](x) + G["Dp"]                         # top of rafters = the Roof planes
    _code(s, G, fr)
    return s, G


def _code(s, G, fr):
    """Code tables and fit rules, before anything is built."""
    snow = need(s.get("site") or {}, "ground_snow_psf", "site")
    col = next((c for c in (30, 50, 70) if snow <= c), None)
    wc = next((i for i, c in enumerate((12, 24, 36)) if G["W"] / 12 <= c), None)
    hs = HDR.get(fr["header"])
    tests = [(col is None, f"ground snow {snow} psf: above the tables read (70 psf)"),
             (fr["stud"] != "2x4" or G["H"] - 4.5 > 120 or G["oc"] > 24, "studs: 2x4, <= 24 in., <= 10 ft (R602.3(5))"),
             (G["W"] / 2 > RAF70.get(fr["rafter"], 0) or G["roc"] > 24, f"rafter {fr['rafter']} does not span "
              f"{G['W'] / 2:.0f} in. at {G['roc']} in. (R802.4.1(7), SPF #2, 70 psf)"),
             (G["ri"][1] < G["Dp"] - 1e-6, f"ridge shallower than the plumb cut ({G['Dp']:.2f} in.), R802.3"),
             (G["ti"][1] > G["zt"](0) - G["ztp"], "rafter tie above the roof plane: deeper rafter"),
             (G["fa"][1] < G["Dp"] + G["tv"] - G["fa"][0] * G["s"], "fascia shallower than rafter tail + soffit"),
             (G["rk"][1] * G["k"] < G["Dp"] + G["tv"], "rake board shallower than barge rafter + soffit"),
             (hs is None or wc is None, f"header {fr['header']} or width: not in the R602.7(1) rows read")]
    for o in s.get("openings") or []:
        span = ro(o)["w"]
        tests += [(o.get("wall") not in WALLS, f"opening wall {o.get('wall')!r}: use {', '.join(WALLS)}"),
                  (span > 48, f"opening {span} in.: needs 2 kings (R602.7.5), not supported yet"),
                  (hs and col and wc is not None and (span > hs[(col // 20 - 1) * 3 + wc] or
                   (fr["header"], col, (12, 24, 36)[wc]) in NJ2), f"header over {span} in.: fails R602.7(1)")]
    for bad, msg in tests:
        if bad:
            raise Bad(msg)


def colors(s):
    t = need(s.get("trim") or {}, "color", "trim")
    dr = next((o["color"] for o in s.get("openings") or [] if o.get("type") == "door" and o.get("color")), t)
    return {"M_Siding": need(s.get("siding") or {}, "color", "siding"), "M_Trim": t, "M_Door": dr}


# ---------------------------------------------------------------------------- framing rules

def frame_wall(L, H, oc, ops, st=(1.5, 3.5), lap=0.0, hd=(1.5, 5.5)):
    """A stud wall's members (name stem, u0, u1, z0, z1, d0, d1); z = 0 under the bottom plate, H plate to plate.
    ops: {"c", "w" (rough opening), "zb", "zt", "door"}; the upper top plate runs `lap` past each end."""
    t, dp = st
    out, zones, top = [], [], H - 2 * t

    def m(kind, u0, u1, z0, z1, d0=0.0, d1=dp):
        out.append((kind, u0, u1, z0, z1, d0, d1))
    a = 0.0
    for c0, c1 in sorted((o["c"] - o["w"] / 2, o["c"] + o["w"] / 2) for o in ops if o["door"]):
        m("Plate_{w}_B", a, c0, 0, t)                    # the bottom plate is cut at a door
        a = c1
    m("Plate_{w}_B", a, L, 0, t)
    m("Plate_{w}_T", 0, L, top, top + t)
    m("Plate_{w}_T", -lap, L + lap, top + t, H)
    m("Stud_{w}_E", 0, t, t, top)
    m("Stud_{w}_E", L - t, L, t, top)
    for o in ops:
        r0, r1 = o["c"] - o["w"] / 2, o["c"] + o["w"] / 2
        if r0 - 2 * t < t or r1 + 2 * t > L - t or any(r0 - 2 * t < z[1] and r1 + 2 * t > z[0] for z in zones):
            raise Bad(f"opening at {o['c']:.2f} in.: studs hit an end stud or opening")
        if o["zt"] + hd[1] > top:
            raise Bad("a header does not fit under the top plates")
        zones.append((r0 - 2 * t, r1 + 2 * t, r0, r1, o))
        for u in (r0 - 2 * t, r1 + t):
            m("King_{w}_", u, u + t, t, top)
        for u in (r0 - t, r1):
            m("Jack_{w}_", u, u + t, t, o["zt"])
        for d0 in (0, dp - hd[0]):
            m("Header_{w}_", r0 - t, r1 + t, o["zt"], o["zt"] + hd[1], d0, d0 + hd[0])
        if not o["door"]:
            m("Sill_{w}_", r0, r1, o["zb"] - t, o["zb"])
    p = oc
    while p + t / 2 < L - t:                         # touching the end stud: dropped
        lo, hi = p - t / 2, p + t / 2
        z = next((z for z in zones if lo < z[1] and hi > z[0]), None)
        if z is None:
            m("Stud_{w}_", lo, hi, t, top)
        elif z[2] <= lo and hi <= z[3]:              # inside the rough opening: cripples keep the layout
            if top - z[4]["zt"] > hd[1] + .25:
                m("Cripple_{w}_", lo, hi, z[4]["zt"] + hd[1], top)
            if not z[4]["door"]:
                m("Cripple_{w}_", lo, hi, t, z[4]["zb"] - t)
        p += oc
    return out


def ro(o, w=None, dp=0.0):
    """Rough opening, wall coordinates: door + 2 x 2.5 in. (Pease Doors), window + 0.5 in. (JELD-WEN)."""
    c = o["center_ft"] * 12 - (dp if w in ("front", "back") else 0)
    if o.get("type") == "door":
        return dict(c=c, w=o["width_in"] + 2, zb=0.0, zt=o["height_in"] + 2.5, door=True)
    if o.get("type") != "window":
        raise Bad(f"opening type {o.get('type')!r}: door or window")
    return dict(c=c, w=o["width_in"] + 0.5, zb=o["sill_in"] - 0.25, zt=o["sill_in"] + o["height_in"] + 0.25, door=False)


def walls(sk, s, G):
    P, W, D, dp = G["P"], G["W"], G["D"], G["st"][1]
    for w in WALLS:
        side, f = w in ("left", "right"), skin(w, G)   # long walls run through
        ops = [ro(o, w, dp) for o in s.get("openings") or [] if o["wall"] == w]
        n = {}
        for kind, u0, u1, z0, z1, d0, d1 in sorted(frame_wall(D if side else W - 2 * dp, G["H"], G["oc"], ops, G["st"],
                                                              -dp if side else dp, G["hd"]), key=lambda q: q[:2] + q[3:6:2]):
            stem = kind.format(w=w)
            n[stem] = n.get(stem, 0) + 1
            sk.add(f"{P}_{stem}{n[stem]}", ext(rect(u0, u1, z0 + G["pad"], z1 + G["pad"]),
                                               lambda p, d: f(p[0] + (0 if side else dp), -G["tsh"] - d, p[1]), d0, d1), "M_Lumber",
                   [f"{P}_{stem[:-1] if stem.endswith('_E') else stem}*"], "Framing")


def roof_frame(sk, s, G):
    P, W, D, zb, zt, ztp, t, dp = G["P"], G["W"], G["D"], G["zb"], G["zt"], G["ztp"], G["ra"][0], G["st"][1]
    xr, xt, xh, yb = W / 2 - G["ri"][0] / 2, G["fa"][0] - G["ove"], -G["tsh"], G["yb"]
    com = [(xt, zb(xt)), (xh, zb(xh)), (xh, ztp), (dp, ztp), (xr, zb(xr)), (xr, zt(xr)), (xt, zt(xt))]  # birdsmouth
    barge = [(xt, zb(xt)), (xr, zb(xr)), (xr, zt(xr)), (xt, zt(xt))]
    ys, c = [0.0], G["roc"]
    while c + t / 2 < D - t:
        ys, c = ys + [c - t / 2], c + G["roc"]
    rows = [(f"{i + 1:02d}", y0, com, "[0-9]") for i, y0 in enumerate(ys + [D - t])]
    rows += [(f"Barge_{e}", y0, barge, "Barge_") for e, y0 in (("front", -yb), ("back", D + yb - t))]
    for i, (nm, y0, pts, g) in enumerate(rows):
        for sd in "LR":
            sk.add(f"{P}_Rafter_{nm}_{sd}", ext(pts if sd == "L" else [(W - x, z) for x, z in pts], xz, y0, y0 + t),
                   "M_Lumber", [f"{P}_Rafter_*", f"{P}_Rafter_{g}*"], "RoofFrame")
        if 0 < i < len(ys):                          # the gable walls tie the end pairs
            sk.add(f"{P}_Tie_{i}", ext(rect(0, W, ztp, ztp + G["ti"][1]), xz, y0 + t, y0 + t + G["ti"][0]), "M_Lumber",
                   [f"{P}_Tie_*"], "RoofFrame")
    top, eb, fb = zt(xr), zb(W / 2), zt(xr) - G["ri"][1]      # past the gable walls it is cut to the rafter line
    prof = [(-yb, eb), (0, eb), (0, fb), (D, fb), (D, eb), (D + yb, eb), (D + yb, top), (-yb, top)]
    sk.add(f"{P}_Ridge", ext(prof, lambda p, x: (x, p[0], p[1]), xr, xr + G["ri"][0]), "M_Lumber", [f"{P}_Ridge"],
           "RoofFrame")
    st, rx = G["st"][0], (xr, xr + G["ri"][0])
    for w, y0 in (("front", 0.0), ("back", D - dp)):
        p, n = G["oc"], 0
        while p + st / 2 < W - 2 * dp - st:
            x0, x1 = dp + p - st / 2, dp + p + st / 2
            xs = [x1, *([W / 2] if x0 < W / 2 < x1 else []), x0]
            tops = [min(zb(x), fb if x0 < rx[1] and x1 > rx[0] else 1e9) for x in xs]
            if min(tops) - ztp > st:
                n += 1
                sk.add(f"{P}_GableStud_{w}_{n}", ext([(x0, ztp), (x1, ztp), *zip(xs, tops)], xz, y0, y0 + dp),
                       "M_Lumber", [f"{P}_GableStud_{w}_*"], "RoofFrame")
            p += G["oc"]
    if sk.build:   # Roof: rafter tops out to the fascia and rake faces
        x0, y0, y1 = -G["ove"], -G["ovr"], D + G["ovr"]
        v = [(x0, y0, zt(x0)), (W / 2, y0, zt(W / 2)), (W / 2, y1, zt(W / 2)), (x0, y1, zt(x0)), (W - x0, y0, zt(x0)),
             (W - x0, y1, zt(x0))]
        me = bpy.data.meshes.new("Roof")
        me.from_pydata([[c * IN for c in p] for p in v], [], [(0, 1, 2, 3), (1, 4, 5, 2)])
        coll(f"{P}_RoofFrame").objects.link(bpy.data.objects.new("Roof", me))


def sheathing(sk, s, G):
    P, W, D, o = G["P"], G["W"], G["D"], G["tsh"]
    k0 = G["ztp"] - G["st"][1] * G["s"] + G["Dp"]
    gable = [(-G["s"], 1, k0), (G["s"], 1, k0 + W * G["s"])]   # up to the roof planes
    notch = (W / 2 - G["ri"][0] / 2, W / 2 + G["ri"][0] / 2, G["zb"](W / 2), 1e9)   # the ridge's end
    for w in WALLS:
        side, f = w in ("left", "right"), skin(w, G)
        u0, u1 = (0.0, D) if side else (-o, W + o)
        holes = [(r["c"] - r["w"] / 2, r["c"] + r["w"] / 2, G["pad"] + r["zb"], G["pad"] + r["zt"])
                 for r in (ro(op) for op in s.get("openings") or [] if op["wall"] == w)]
        bands = [("", G["pad"], G["ztp"], (), holes)] + ([] if side else [("G", G["ztp"], G["zt"](W / 2), gable, [notch])])
        for tag, h0, h1, reg, cut in bands:
            x, n = u0, 0
            while x < u1 - 1e-6:
                ps = pieces(x, min(x + 48, u1), h0, h1, reg, cut)
                if ps:
                    n += 1
                    sk.add(f"{P}_Sheathing_{w}_{tag}{n}", merge(on(f, q, -o, 0) for q in ps), "M_OSB",
                           [f"{P}_Sheathing_{w}_*"], "Sheathing")
                x += 48


def pad(sk, s, G):
    m = G["mg"]
    sk.add(f"{G['P']}_Pad", ext(rect(-m, G["W"] + m, 0, G["pad"]), xz, -m, G["D"] + m), "M_Concrete", [f"{G['P']}_Pad"], "Pad")


def roofing(s, G, path=None):
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 4, "roof-blender", "scripts", "roof_core.py")
    rc_path = next((p for p in (path, os.environ.get("ROOF_CORE"), here) if p and os.path.isfile(p)), None)
    if rc_path is None:
        return None
    sys.path.insert(0, os.path.dirname(os.path.abspath(rc_path)))
    import bmesh
    import roof_core as rc
    r = s["roof"]   # ice barrier (R905.1.2): eave to 24 in. inside the wall line, 36 in. rolls lapped 3 in.
    ice = 1 + max(0, math.ceil(((G["ove"] + G["tsh"] + 24) * G["k"] - 36) / 33)) if need(r, "ice_barrier", "roof") else 0
    res = rc.run({"cmd": "layers", "roof": "Roof", "old_roof": False, "deck_repair": False, "ice_rows": ice,
                  "ridge_vent": bool(need(r, "ridge_vent", "roof")), "exposure_in": need(r, "exposure_in", "roof")})
    for lid in res["layers"]:   # roof_core's clip keeps a corner twice where a clip line meets it: drop the slivers
        bm, me = bmesh.new(), bpy.data.objects[f"RT_layer_{lid}"].data
        bm.from_mesh(me)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
        bm.to_mesh(me)
    return res


BUILD = {"pad": (pad, "Pad"), "walls": (walls, "Framing"), "roof_frame": (roof_frame, "RoofFrame"),
         "sheathing": (sheathing, "Sheathing")}


def plan(s, G):
    """Every part both scripts make, counted by group, and acceptance checks."""
    sk, groups, P, out = Sink(False, G), {}, G["P"], []
    for fn, _ in BUILD.values():
        fn(sk, s, G)
    cf.build_all(sk, s, G)
    for p in sk.parts:
        for g in p[1]:
            groups.setdefault(g, []).append(p)

    def chk(cid, typ, obj, src="standard", **kw):
        out.append({"id": cid, "type": typ, "objects": obj, "source": src, **kw,
                    **({"unit": "in"} if typ in ("size", "extent", "spacing") else {})})
    for g, ps in groups.items():
        kind = g[len(P) + 1:].split("_")[0] + ("_course" if g.endswith("*_1") else "")
        cid = g[len(P) + 1:].replace("_*_1", "_courses").replace("_*_", "_").replace("[0-9]*", "common")
        cid = cid.replace("*", "").strip("_").replace("_", "-").lower()
        chk("n-" + cid, "count", g, expect=len(ps), note=RULES.get(kind, ""))
        dims = {tuple(sorted(round(b - a, 4) for a, b in zip(p[2], p[3]))) for p in ps}
        if len(dims) == 1 and kind in ("Stud", "King", "Jack", "Header", "Tie", "Ridge"):
            chk("size-" + cid, "size", g, each=True, sorted=True, expect=list(dims.pop()), note="PS 20-20 Table 3")
    for w in WALLS:   # layout stud spacing, per unbroken run
        ax, runs = int(w in ("left", "right")), [[]]
        for p in sorted((p for p in sk.parts if p[0].startswith(f"{P}_Stud_{w}_") and "_E" not in p[0][len(P):]),
                        key=lambda p: p[2][ax]):
            if runs[-1] and abs(p[2][ax] - runs[-1][-1][2][ax] - G["oc"]) > 1e-6:
                runs.append([])
            runs[-1].append(p)
        for i, r in enumerate(x for x in runs if len(x) > 1):
            chk(f"spacing-{w}-{i + 1}", "spacing", [p[0] for p in r], axis="xy"[ax], expect=G["oc"])
    src = "standard" if G["pr"].get("method") == "rule" else "measured"
    top = next(p for p in sk.parts if p[0] == f"{P}_Ridge")[3][2]
    chk("footprint", "size", f"{P}_Plate_*_B*", "given", expect=[G["W"], G["D"], G["st"][0]])
    chk("wall-top", "extent", f"{P}_Plate_*_T*", "given", axis="z", expect=G["ztp"], note="pad + wall height")
    chk("ridge-top", "extent", f"{P}_Ridge", src, axis="z", expect=round(top, 4), note="top of rafters, ridge face")
    chk("pitch-rafters", "slope", f"{P}_Rafter_*", src, expect=s["roof"]["pitch"], note=f"{G['src']}: {G['pr'].get('label')}")
    for p in sk.parts:
        if p[0].endswith("_Frame_Head") or p[0] == f"{P}_Door_Slab":
            win = "_Window_" in p[0]
            g = p[0][:-10] + "*" if win else f"{P}_Door_*"
            chk("tris-" + g[len(P) + 1:-2].lower().replace("_", "-"), "tris", g, min=150 if win else 400,
                note="detail floor: " + RULES["Window" if win else "Door"])
    return {"ok": True, "name": s.get("name"), "parts": len(sk.parts), "tris": sum(p[4] for p in sk.parts),
            "counts": {g: len(ps) for g, ps in groups.items()}, "checks": out}


def run(plan=None, build=None, only=None, roof_core=None, **_):
    bx.object_mode()
    if plan:
        return globals()["plan"](*load(plan))
    if not build:
        raise ValueError("pass --plan or --build building.json")
    s, G = load(build)
    if set(only or []) - set(STAGES):
        raise Bad(f"--only: use {', '.join(STAGES)}")
    sk, notes = Sink(True, G, colors(s)), []
    for k in only or STAGES:
        if k == "roofing":
            res = roofing(s, G, roof_core)
            if res is None and only:
                raise Bad("roofing needs roof_core.py (RoofTec repo, roof-blender/scripts): pass --roof-core PATH")
            notes.append(f"roofing: {len(res['layers'])} layers" if res else "roofing skipped: no roof_core.py")
            continue
        clear(f"{G['P']}_{BUILD[k][1]}")
        if k == "roof_frame" and "Roof" in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects["Roof"])
        BUILD[k][0](sk, s, G)
    return {"ok": True, "built": list(only or STAGES), "parts": len(sk.parts), "tris": sum(p[4] for p in sk.parts),
            "meshes": len(sk.cache), "notes": notes}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--plan", help="building.json: counts and acceptance checks, no geometry")
    p.add_argument("--build", help="building.json to build")
    p.add_argument("--only", nargs="*", help=f"stages: {' '.join(STAGES)} (default: all)")
    p.add_argument("--roof-core", dest="roof_core", help="roof_core.py for the roofing stage")
    p.add_argument("--save", help="save the .blend here")
    bx.cli(run, p)
