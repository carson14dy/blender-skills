"""Construction extras on a construction_kit.py building: house wrap and flashing tape, rake lookouts and frieze
blocks, window sash locks and screens, and the wall, sheathing, siding and trim nails of the nailing schedules
(references/construction-detail.md). Same building.json; lengths are inches.
Usage:
  blender -b f.blend -P construction_extras.py -- --build building.json [--only wrap blocking hardware nails] --save F
  MCP: import construction_extras as cx; print(cx.run(build="C:/work/building.json"))
Returns {"ok", "built", "parts", "nails"}. Each nail group is one object; its nails are its islands, and
construction_kit.py --plan writes a count check (of: islands) for each.
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bpyx as bx  # noqa: E402
import construction_finish as cf  # noqa: E402
import construction_kit as ck  # noqa: E402
from construction_finish import JT, WALLS, Sink, clear, ext, lathe, merge, on, rect, skin, xz  # noqa: E402

STAGES = ("wrap", "blocking", "hardware", "nails")
TAG = {"wrap": "Wrap", "blocking": "Blocking", "hardware": "Windows", "nails": "Nails"}
D16, D6, FIN = (3.5, .081, .172), (2.0, .0565, .133), (2.0, .031, .045)   # 16d, 6d common; 16 ga finish nail
NOTE = {"Frame": "R602.3(1): 17 stud to plate 2-16d end nails; 13 top plates 16d at 16 in.; 18 corner laps 2-16d; "
                 "10 headers 16d at 16 in. each edge; 12 king to header 3-16d; 8 jack to king 16d at 24 in.; gable "
                 "studs 3 toe nails (17)", "Sheathing": "R602.3(1) item 31: 6d common, 6 in. at panel edges, 12 in. "
                 "at intermediate studs", "Siding": "R703.3(1) note f: one 6d common through the lap at each stud",
        "Trim": "Hardie Trim Table 1: 2 nails every 16 in. (4 in. boards), 3 (8 in. fascia, rake), 1 in. from ends",
        "Roof": "R602.3(1): 6 rafter to plate 3 toe nails; 7 rafter to ridge 3-10d toe nails; 1 blocking 3-8d toe nails; "
                "R802.5.2(1) tie heel joint 7-16d (5:12 row: no 6:12 row, the lower slope needs more)"}
D10, D8 = (3.0, .074, .156), (2.5, .066, .141)   # 10d, 8d common


def nail(p, a, L, rs, rh):
    """Nail along unit vector a from surface point p. Its head is drawn 1.2 mm under the surface: a flush head lies
    inside qa_check's 1 mm coplanar test."""
    e1 = (a[1], -a[0], 0) if abs(a[2]) < .9 else (0, a[2], -a[1])
    m = math.hypot(*e1)
    e1 = [c / m for c in e1]
    e2 = (a[1] * e1[2] - a[2] * e1[1], a[2] * e1[0] - a[0] * e1[2], a[0] * e1[1] - a[1] * e1[0])
    c, s = .966, .259                                  # turned 15 degrees: no facet parallel to a wall or plate
    e1, e2 = [x * c + y * s for x, y in zip(e1, e2)], [y * c - x * s for x, y in zip(e1, e2)]
    return lathe([(0, .047), (rh, .047), (rh, .117), (rs, .117), (rs, L - 3 * rs), (0, L)], 6,
                 lambda x, y, z: tuple(p[i] + e1[i] * x + e2[i] * y + a[i] * z for i in range(3)))


def framing(s, G):
    """The kit's and finish's parts, dry: names and bounds to place nails by."""
    d = Sink(False, G)
    for fn in (ck.walls, ck.roof_frame, cf.siding, cf.trim):
        fn(d, s, G)
    return d.parts


def wrap(sk, s, G):
    P, dp = G["P"], G["st"][1]
    ws = {}
    for w, n, ps in ck.sheets(s, G):
        ws.setdefault(w, []).extend(ps)
    for w, ps in ws.items():   # R703.2; drawn 1.8 mm thick, 1.1 mm off the sheathing (qa_check's 1 mm rule)
        sk.add(f"{P}_Wrap_{w}", merge(on(skin(w, G, 0), q, .045, .115) for q in ps), "M_Wrap", [f"{P}_Wrap_*"], "Wrap")
    for k, o in enumerate(s.get("openings") or [], 1):   # R703.4: tape lines each rough opening, sill pan first
        r, f, t = ck.ro(o), skin(o["wall"], G, 0), .045
        u0, u1, h0, h1 = r["c"] - r["w"] / 2, r["c"] + r["w"] / 2, G["pad"] + r["zb"], G["pad"] + r["zt"]
        bs = [(u0, u0 + t, h0, h1), (u1 - t, u1, h0, h1), (u0 + t, u1 - t, h1 - t, h1)] + \
            ([] if r["door"] else [(u0 + t, u1 - t, h0, h0 + t)])
        sk.add(f"{P}_Tape_{k}", merge(on(f, rect(*b), -G["tsh"] - dp, .115) for b in bs), "M_Tape", [f"{P}_Tape_*"], "Wrap")


def blocking(sk, s, G):
    P, W, D, zb, zt, ztp, t = G["P"], G["W"], G["D"], G["zb"], G["zt"], G["ztp"], G["ra"][0]
    o, yb, k, xe = G["tsh"] + G["dw"], G["yb"], G["k"], W / 2 - G["ri"][0] / 2
    xs, c = [], 12 / k                                 # lookouts 24 in. o.c. along the rake, the first 12 in. out
    while c + .75 < xe:
        xs, c = xs + [c], c + 24 / k
    n = 0
    for e, y0, y1 in (("front", -yb + t, -o), ("back", D + o, D + yb - t)):
        for c in xs:
            for sd in "LR":
                pts = [(x, zb(x)) for x in (c - .75, c + .75)] + [(x, zt(x)) for x in (c + .75, c - .75)]
                n += 1
                sk.add(f"{P}_Lookout_{n}", ext(pts if sd == "L" else [(W - x, z) for x, z in pts], xz, y0, y1),
                       "M_Lumber", [f"{P}_Lookout_*"], "Blocking")
    n, x0 = 0, -G["tsh"]
    for y0, b in bays(framing(s, G), G):               # frieze blocks between rafters, clear of the ties
        for sd in "LR":
            pts = [(x0, ztp), (x0 + 1.5, ztp), (x0 + 1.5, zt(x0 + 1.5)), (x0, zt(x0))]
            n += 1
            sk.add(f"{P}_Frieze_{n}", ext(pts if sd == "L" else [(W - x, z) for x, z in pts], xz, y0, b), "M_Lumber",
                   [f"{P}_Frieze_*"], "Blocking")


def bays(parts, G):
    """(y0, y1) of each rafter bay over the long walls, starting clear of the rafter and of its tie."""
    ys = sorted(p[2][1] for p in parts if p[0].startswith(G["P"] + "_Rafter_") and p[0].endswith("_L") and "Barge" not in p[0])
    return [(a + G["ra"][0] + (G["ti"][0] if i else 0), b) for i, (a, b) in enumerate(zip(ys, ys[1:]))]


def hardware(sk, s, G):
    P, n = G["P"], 0
    for o in [o for o in s.get("openings") or [] if o["type"] == "window"]:
        n += 1
        f, u, hb = skin(o["wall"], G), o["center_ft"] * 12, G["pad"] + o["sill_in"]
        il, ir, ib = u - o["width_in"] / 2 + JT, u + o["width_in"] / 2 - JT, hb + 1.5
        hm = ib + (hb + o["height_in"] - JT - ib + 1.5) / 2       # top of the lower sash's meeting rail
        sk.add(f"{P}_Window_{n}_Lock", merge([on(f, rect(u - 1, u + 1, hm, hm + .5), -3.1, -2.1),
                                             on(f, rect(u + 1, u + 2.2, hm, hm + .5), -2.1, -1.875)]),
               "M_Hardware", [f"{P}_Window_{n}_*", f"{P}_Window_*_Lock"], "Windows")
        bs = [(il, il + .75, ib, hm), (ir - .75, ir, ib, hm), (il + .75, ir - .75, ib, ib + .75), (il + .75, ir - .75, hm - .75, hm)]
        sk.add(f"{P}_Window_{n}_Screen", merge([on(f, rect(*b), -.4, -.1) for b in bs] +
                                               [on(f, rect(il + .375, ir - .375, ib + .375, hm - .375), -.27, -.23)]),
               "M_Screen", [f"{P}_Window_{n}_*", f"{P}_Window_*_Screen"], "Windows")


def nails(sk, s, G):
    P, W, D, parts, out = G["P"], G["W"], G["D"], framing(s, G), {}
    get = (lambda pre: [p for p in parts if p[0].startswith(P + pre)])
    ax = {"front": (1, 1), "back": (1, -1), "left": (0, 1), "right": (0, -1)}   # depth axis, inward sign

    def put(key, p, a, spec):
        out.setdefault(key, []).append(nail(p, a, *spec))
    for w in WALLS:
        da, sg = ax[w]
        mid = lambda p: [(a + b) / 2 for a, b in zip(p[2], p[3])]  # noqa: E731
        hz = get(f"_Plate_{w}_") + get(f"_Sill_{w}_")
        vt = get(f"_Stud_{w}_") + get(f"_King_{w}_") + get(f"_Jack_{w}_") + get(f"_Cripple_{w}_")
        for v in vt:                                   # item 17: through a plate or sill into each stud end
            c = mid(v)
            for h in hz:
                if h[2][0] <= c[0] <= h[3][0] and h[2][1] <= c[1] <= h[3][1]:
                    for zz, z0, a in ((h[3][2], h[2][2], 1), (h[2][2], h[3][2], -1)):
                        if abs(zz - (v[2][2] if a > 0 else v[3][2])) < 1e-6:
                            for dd in (-.875, .875):
                                q = list(c)
                                q[da], q[2] = c[da] + dd, z0
                                put(f"Frame_{w}", q, (0, 0, a), D16)
        ua = 1 - da
        tops = sorted(get(f"_Plate_{w}_T"), key=lambda p: p[2][2])[-1:]
        for h in tops:                                 # 13: upper top plate into the lower; 18: 2 at each corner lap
            c, ends = mid(h), [h[2][ua] + 1.75, h[3][ua] - 1.75] if da else []
            for x, dd in [(x, 0) for x in frange(h[2][ua] + 8, h[3][ua] - 4, 16)] + [(x, e) for x in ends for e in (-.875, .875)]:
                q = list(c)
                q[ua], q[da], q[2] = x, c[da] + dd, h[3][2]
                put(f"Frame_{w}", q, (0, 0, -1), D16)
        hd = [h for h in get(f"_Header_{w}_") if abs((h[2][da] if sg > 0 else h[3][da]) - (0 if sg > 0 else (D, W)[da == 0])) < 1e-6]
        for h in hd:                                   # item 10: through the outer member, both edges
            a = [0, 0, 0]
            a[da] = sg
            for x in frange(h[2][ua] + 2, h[3][ua] - 2, 16):
                for z in (h[2][2] + .75, h[3][2] - .75):
                    q = list(mid(h))
                    q[ua], q[da], q[2] = x, (h[2][da] if sg > 0 else h[3][da]), z
                    put(f"Frame_{w}", q, a, D16)
            for kg in get(f"_King_{w}_"):              # item 12: 3 end nails through each king into the header end
                for side, face, toward in ((kg[3][ua], kg[2][ua], 1), (kg[2][ua], kg[3][ua], -1)):
                    if abs(side - (h[2][ua] if toward > 0 else h[3][ua])) < 1e-6:
                        for j in range(3):
                            q = list(mid(h))
                            q[ua], q[2] = face, h[2][2] + 1.375 * (j + 1)
                            q[da] = (h[2][da] if sg > 0 else h[3][da]) + sg * (.75, 2.75, .75)[j]
                            a = [0, 0, 0]
                            a[ua] = toward
                            put(f"Frame_{w}", q, a, D16)
        for j in get(f"_Jack_{w}_"):                   # item 8: jack to king, 16d at 24 in.
            kg = [k for k in get(f"_King_{w}_") if abs(k[3][ua] - j[2][ua]) < 1e-6 or abs(k[2][ua] - j[3][ua]) < 1e-6]
            for k in kg:
                toward = 1 if k[2][ua] >= j[3][ua] - 1e-6 else -1
                for z in frange(j[2][2] + 12, j[3][2] - 2, 24):
                    q = mid(j)
                    q[ua], q[2] = j[2][ua] if toward > 0 else j[3][ua], z
                    a = [0, 0, 0]
                    a[ua] = toward
                    put(f"Frame_{w}", q, a, D16)
        for g in get(f"_GableStud_{w}_"):             # item 17 toe nails: 2 on one face, 1 on the other
            c = mid(g)
            for face, sx, dd in ((g[2][ua], 1, -.875), (g[2][ua], 1, .875), (g[3][ua], -1, 0)):
                q = list(c)
                q[ua], q[da], q[2] = face, c[da] + dd, g[2][2] + 1.5
                a = [0, 0, -.866]
                a[ua] = .5 * sx
                put(f"Frame_{w}", q, a, D16)
        lines = [v for v in vt + get(f"_GableStud_{w}_")]
        f0, fs = skin(w, G, 0), skin(w, G)
        inward = [(b - a) for a, b in zip(f0(0, 0, 0), f0(0, -1, 0))]
        for _, _, ps in [x for x in ck.sheets(s, G) if x[0] == w]:   # item 31, sheathing
            pts = []
            for poly in ps:
                cu, ch = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
                for a, b in zip(poly, poly[1:] + poly[:1]):
                    ln = math.dist(a, b)
                    nx, nz = (a[1] - b[1]) / ln, (b[0] - a[0]) / ln
                    sgn = 1 if (cu - a[0]) * nx + (ch - a[1]) * nz > 0 else -1
                    ins = .375 + (G["tsh"] if abs(nz) < 1e-6 and not 0 <= a[0] <= W else 0)   # corner: past the sheathing
                    for i in range(max(1, round(ln / 6))):   # corner edges: half a space up, clear of the next wall's
                        r_ = (i + (1 if ins > .375 else .5)) / max(1, round(ln / 6))
                        pts.append((a[0] + (b[0] - a[0]) * r_ + sgn * nx * ins, a[1] + (b[1] - a[1]) * r_ + sgn * nz * ins))
                for v in lines:
                    u = mid(v)[ua]
                    zs = [a[1] + (b[1] - a[1]) * (u - a[0]) / (b[0] - a[0]) for a, b in zip(poly, poly[1:] + poly[:1])
                          if (a[0] - u) * (b[0] - u) <= 0 and a[0] != b[0]]
                    lo_, hi_ = max(v[2][2], min(zs or [0])), min(v[3][2], max(zs or [0]))
                    if min(p[0] for p in poly) + 3 < u < max(p[0] for p in poly) - 3 and hi_ - lo_ > 6:
                        nn = max(1, round((hi_ - lo_) / 12))
                        pts += [(u, lo_ + (hi_ - lo_) * (i + .5) / nn) for i in range(nn)]
            kept = []
            for q in pts:
                if all(math.dist(q, r) > 3 for r in kept):
                    kept.append(q)
            for x, z in kept:
                put(f"Sheathing_{w}", f0(x, 0, z), inward, D6)
        dm = cf.dims(s, G)
        for p in get(f"_Siding_{w}_"):                 # R703.3(1) note f: through the lap at each stud
            hb = dm["h0"] + (int(p[0].split("_")[-2]) - 1) * dm["E"]
            z = p[2][2] + .75
            for v in lines:
                u = mid(v)[ua]
                if p[2][ua] + 1 <= u <= p[3][ua] - 1 and v[2][2] <= z <= v[3][2]:
                    put(f"Siding_{w}", fs(u, dm["a"] * (1 - (z - hb) / dm["Wb"]) + dm["t"], z), inward, D6)
    for p in get("_Trim_Corner_") + get("_Window_") + get("_Door_Casing"):   # Hardie Trim Table 1
        if "Casing" in p[0] or "Corner" in p[0]:
            sz = [b - a for a, b in zip(p[2], p[3])]
            th = 0 if sz[0] < sz[1] else 1             # the board's thickness axis; its face is the outer one
            out_, a = (p[2][th], [0, 0, 0]) if p[3][th] < (W, D)[th] / 2 else (p[3][th], [0, 0, 0])
            a[th] = 1 if out_ == p[2][th] else -1
            la = 2 if sz[2] >= sz[1 - th] else 1 - th
            wa = 1 - th if la == 2 else 2
            top = p[3][2] - (1.75 if "Corner" in p[0] else 0)   # gable-face corner boards: their low top corner
            for x in frange(p[2][la] + 1, (top if la == 2 else p[3][la]) - 1, 16, True):
                for e in (p[2][wa] + .75, p[3][wa] - .75):
                    q = [0, 0, 0]
                    q[th], q[la], q[wa] = out_, x, e
                    put("Trim", q, a, FIN)
    ztp, xr, zt = G["ztp"], W / 2 - G["ri"][0] / 2, G["zt"]
    for r in get("_Rafter_"):                          # roof framing: 2 toe nails one side, 1 the other
        y0, L = r[2][1], r[0].endswith("_L")
        X = (lambda x: x) if L else (lambda x: W - x)  # noqa: E731
        for y, sy, dx in ((y0, 1, -.5), (y0, 1, .5), (y0 + 1.5, -1, 0)):
            if "Barge" not in r[0]:                    # item 6, rafter to plate
                put("Roof", (X(1.75 + dx), y, ztp + 1.5), (0, .5 * sy, -.866), D16)
            put("Roof", (X(xr - 1.5), y, zt(xr - 1.5) - G["Dp"] / 2 + 2 * dx), (.866 if L else -.866, .5 * sy, 0), D10)
    for tie in get("_Tie_"):                           # tie heel joints, both ends
        for x in [1 + 1.25 * j for j in range(7)] + [W - 1 - 1.25 * j for j in range(7)]:
            put("Roof", (x, tie[3][1], ztp + 3.0), (0, -1, 0), D16)
    for y0, y1 in bays(parts, G):                      # item 1, blocking to plate
        for y in (y0 + (y1 - y0) * f for f in (.25, .5, .75)):
            for x, ax in ((1.5 - G["tsh"], -.5), (W - 1.5 + G["tsh"], .5)):
                put("Roof", (x, y, ztp + 1.0), (ax, 0, -.866), D8)
    fa, rk, ov, ovr, yb, zt = G["fa"][1], G["rk"][1] * G["k"], G["ove"], G["ovr"], G["yb"], G["zt"]
    for sd in (1, -1):                                 # fascia and rake boards: 3 nails every 16 in.
        X = (lambda x: x) if sd > 0 else (lambda x: W - x)  # noqa: E731
        for y in frange(-yb + 1, D + yb - 1, 16, True):
            for z in (.75, fa / 2, fa - .75):
                put("Trim", (X(-ov), y, zt(-ov) - z), (sd, 0, 0), FIN)
        for x in frange(-ov + 1, W / 2 - 1, 16 / G["k"], True):
            for z in (.75 * G["k"], rk / 2, rk - .75 * G["k"]):
                for y, ay in ((-ovr, 1), (D + ovr, -1)):
                    put("Trim", (X(x), y, zt(x) - z), (0, ay, 0), FIN)
    n = 0
    for key, vf in out.items():
        sk.add(f"{P}_Nails_{key}", merge(vf), "M_Hardware", [f"{P}_Nails_*"], "Nails")
        sk.__dict__.setdefault("islands", {})[f"{P}_Nails_{key}"] = (len(vf), NOTE[key.split("_")[0]])
        n += len(vf)
    return n


def frange(a, b, step, ends=False):
    """a, a + step, ... up to b; ends: evenly spaced from a to b, no gap over step."""
    if ends:
        n = max(1, math.ceil((b - a) / step - 1e-9))
        return [a + (b - a) * i / n for i in range(n + 1)]
    out = []
    while a <= b + 1e-9:
        out, a = out + [a], a + step
    return out


FN = {"wrap": wrap, "blocking": blocking, "hardware": hardware, "nails": nails}


def build_all(sk, s, G):
    for k in STAGES:
        FN[k](sk, s, G)


def run(build=None, only=None, **_):
    bx.object_mode()
    if not build:
        raise ValueError("pass --build building.json")
    s, G = ck.load(build)
    if set(only or []) - set(STAGES):
        raise ck.Bad(f"--only: use {', '.join(STAGES)}")
    sk, res = Sink(True, G, ck.colors(s)), {}
    for k in only or STAGES:
        if k != "hardware":
            clear(f"{G['P']}_{TAG[k]}")
        else:
            for o in [o for o in bpy.data.objects if o.name.endswith(("_Lock", "_Screen"))]:
                bpy.data.objects.remove(o)
        res[k] = FN[k](sk, s, G)
    return {"ok": True, "built": list(only or STAGES), "parts": len(sk.parts), "nails": res.get("nails")}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--build", help="building.json")
    p.add_argument("--only", nargs="*", help=f"stages: {' '.join(STAGES)} (default: all)")
    p.add_argument("--save", help="save the .blend here")
    bx.cli(run, p)
