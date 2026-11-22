#!/usr/bin/env python3
"""Roof pitch, never assumed: from a gable photo, scan points, a reading, a design rule, or combined.

Plain Python + numpy. Formats and rules: references/roof-pitch.md.
Usage: python roof_pitch.py COMMAND ...    (one JSON line; --out F saves it; exit 1 only on bad input)
  photo --image gable.jpg --points pts.json [--overlay o.png] [--synthetic]
  points --file facet.npy|facet.txt   (ONE facet: x y z rows, metres)
  record --method gauge|lidar|model|report|plans --value 6/12 [--sigma S] --source T  (sigma per 12)
  rule --covering asphalt_shingle|metal_lapped|metal_sealed|standing_seam --building accessory|house
       [--match 5.95/12] [--rules F]
  combine a.json b.json [...]       (MCP: run("photo", image=F, points=F))
"""
import argparse
import json
import math
import os
import struct
import sys
import zlib

try:
    import numpy as np
except ImportError:  # --help works
    np = None

UNIT = {"in": 0.0254, "ft": 0.3048, "mm": 0.001, "cm": 0.01, "m": 1.0}  # m last
REC = {"gauge": 0.25, "lidar": 0.1, "model": 0.1, "report": 0.5, "plans": 0.5}
M = "IRC R905.10.2"
MIN = {"asphalt_shingle": (2, "IRC R905.2.2"), "metal_lapped": (3, M), "metal_sealed": (.5, M),
       "standing_seam": (.25, M)}
K = [1 / 16, .25, .375, .25, 1 / 16]
FLOOR = 0.25  # photo sigma floor
RULES = os.path.join("lab", "data", "design-rules.json")
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 4)


class Bad(Exception):
    pass


def _w(x):
    return int(math.floor(x + 0.5))


def _pitch(v):  # "5.95/12" -> rise over run
    try:
        a, b = map(float, str(v).split("/"))
        return a / b
    except (ValueError, ZeroDivisionError):
        raise Bad(f"pitch {v!r}: write 6/12") from None


def _len(v):  # "36in", "0.91m", 36 (inches) -> metres
    v = str(v).strip()
    u = next((k for k in UNIT if v.endswith(k)), "in")
    try:
        return float(v.removesuffix(u)) * UNIT[u]
    except ValueError:
        raise Bad(f"length {v!r}: write 36in or 0.91m") from None


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def result(slope, sigma, method, source, checks, notes=(), low=()):
    r, s = round(slope * 12, 2), round(sigma * 12, 3)
    near = abs(r - _w(r)) <= 2 * s + 1e-9
    how = {"report": "per report", "plans": "per plans", "combined": "combined"}.get(method, "measured")
    return {"ok": True, "method": method, "source": source, "slope": round(slope, 5), "rise_per_12": r,
            "sigma_per_12": s, "degrees": round(math.degrees(math.atan(slope)), 2),
            "sigma_degrees": round(math.degrees(sigma / (1 + slope ** 2)), 2), "nearest_whole": f"{_w(r)}/12",
            "whole_within_2_sigma": near, "label": f"{slope * 12:g}/12 (design rule)" if method == "rule" else
            f"{_w(r)}/12 ({how} {r:.2f} ± {s:.2f})" if near else f"{r:.2f}/12 ± {s:.2f}",
            "confidence": "low" if low else "ok", "checks": checks, "notes": [*low, *notes]}


# photo: refine each rough line on the image, then vanishing points
def _sample(g, p):  # bilinear
    x, y = np.clip(p[..., 0], 0, g.shape[1] - 1.001), np.clip(p[..., 1], 0, g.shape[0] - 1.001)
    i, j = x.astype(int), y.astype(int)
    fx, fy = x - i, y - j
    return (g[j, i] * (1 - fx) + g[j, i + 1] * fx) * (1 - fy) + (g[j + 1, i] * (1 - fx) + g[j + 1, i + 1] * fx) * fy


def _fit(pts):  # total least squares line: centre, direction, residuals
    c = pts.mean(0)
    d = np.linalg.svd(pts - c)[2][0]
    return c, d, (pts - c) @ [-d[1], d[0]]


def _across(g, c, d, L, s):  # smoothed gradient across the line, offsets s
    t, n = np.linspace(-0.42, 0.42, 48) * L, np.array([-d[1], d[0]])
    pr = np.apply_along_axis(np.convolve, 1, _sample(g, c + t[:, None, None] * d + s[:, None] * n), K, mode="same")
    return t, n, np.gradient(pr, axis=1)[:, 3:-3]


def refine_line(g, p0, p1):
    """Edge points along the rough segment p0-p1, then a trimmed line fit."""
    L = np.linalg.norm(p1 - p0)
    if L < 4:
        raise Bad("line points under 4 px apart")
    c, d = (p0 + p1) / 2, (p1 - p0) / L
    for k in range(3):
        w = max(4.0, 18 / 2 ** k)
        t, n, gr = _across(g, c, d, L, s := np.arange(-w, w + 0.5, 0.5))
        ro = np.arange(len(gr))
        gs = gr * (1.0 if np.median(gr[ro, np.abs(gr).argmax(1)]) >= 0 else -1.0)
        i = gs.argmax(1)
        ok = (i > 0) & (i < gs.shape[1] - 1) & (gs[ro, i] > 0.25 * np.median(gs.max(1)))
        i = np.clip(i, 1, gs.shape[1] - 2)
        a, b, e = gs[ro, i - 1], gs[ro, i], gs[ro, i + 1]
        den = a - 2 * b + e
        pos = s[3:-3][i] + np.where(np.abs(den) > 1e-12, 0.5 * (a - e) / den, 0.0) * 0.5
        q = (c + t[:, None] * d + pos[:, None] * n)[ok]
        if len(q) < 4:
            raise Bad("no clear edge near a line: move its points onto the edge")
        for _ in range(3):
            res = _fit(q)[2]
            keep = np.abs(res) < 3 * (np.median(np.abs(res - np.median(res))) * 1.4826 + 0.05)
            if keep.all() or keep.sum() < 8:
                break
            q = q[keep]
        c, d = _fit(q)[:2]
    s = ((p0 + p1) / 2 - c) @ [-d[1], d[0]] + np.arange(-19.5, 20, 0.5)  # rival edge: window around the clicks
    gr, near = np.abs(_across(g, c, d, L, s)[2]), np.abs(s[3:-3]) <= 2
    rival = np.median(gr[:, ~near].max(1) / np.maximum(gr[:, near].max(1), 1e-9)) if near.any() else 9
    return {"points": q, "rms": float(np.sqrt(np.mean(_fit(q)[2] ** 2))), "n": len(q), "rival": float(rival)}


def _hline(pts):
    c, d, _ = _fit(pts)
    ln = np.cross([*c, 1.0], [*(c + d), 1.0])
    return ln / np.linalg.norm(ln[:2])


def _solve(H, nh, nv, ratio):  # H: rect b r t l, horizontals, verticals, rakes
    j = 4 + nh + nv
    vh, vv = (np.linalg.svd(np.array(x))[2][-1] for x in ([H[0], H[2], *H[4:4 + nh]], [H[1], H[3], *H[4 + nh:j]]))
    linf, M = np.cross(vh, vv), np.column_stack([vh, vv])
    b, r, t, lf = H[:4]

    def co(line):  # vanishing pt = a vh + b vv: |b / a|
        a, bb = np.linalg.lstsq(M, np.cross(line, linf), rcond=None)[0]
        return abs(bb / a)
    ks = [co(np.cross(np.cross(b, lf), np.cross(t, r))), co(np.cross(np.cross(b, r), np.cross(t, lf)))]  # diagonals
    k = sum(ks) / 2
    return [co(x) / k / ratio for x in H[j:]], abs(ks[0] - ks[1]) / k  # rake slopes, diagonal gap


def read_image(path):  # RGB 0-1, top row first: Pillow, else bpy
    try:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            return np.asarray(ImageOps.exif_transpose(im).convert("RGB"), float) / 255
    except ImportError:
        pass
    try:
        import bpy
        im = bpy.data.images.load(os.path.abspath(path), check_existing=False)
    except (ImportError, RuntimeError) as e:
        raise Bad(f"{path}: {e} (needs Pillow or Blender's Python)") from None
    (w, h), c = im.size, im.channels
    px = np.empty(w * h * c, np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    a = px.reshape(h, w, c)[::-1].astype(float)  # Blender stores the bottom row first
    return a[..., :3] if c >= 3 else np.repeat(a[..., :1], 3, 2)


def _overlay(path, img, lines, n_rakes):  # green wall, red rakes; PNG by zlib
    out = (np.dstack([img] * 3) if np.ndim(img) == 2 else np.asarray(img)[..., :3]) * 255.0
    h, w = out.shape[:2]
    r = max(1, round(min(h, w) / 700))
    for j, f in enumerate(lines):
        c, d, _ = _fit(f["points"])
        t = (f["points"] - c) @ d
        q = np.rint(c + np.linspace(1.1 * t.min(), 1.1 * t.max(), int(3 * np.ptp(t)) + 2)[:, None] * d).astype(int)
        for o in np.ndindex(2 * r + 1, 2 * r + 1):
            x, y = (q + o - r).T
            ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
            out[y[ok], x[ok]] = (255, 0, 40) if j >= len(lines) - n_rakes else (0, 230, 0)
    raw = np.hstack([np.zeros((h, 1)), np.clip(out, 0, 255).reshape(h, -1)]).astype(np.uint8).tobytes()
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        for t, d in (b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)), (b"IDAT", zlib.compress(raw)), (
                b"IEND", b""):
            f.write(struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))


def photo(image, points, overlay=None, synthetic=False, **_):
    """image: file or array (h, w[, 3]) 0-1; points: file or dict."""
    sp = _load(points) if isinstance(points, str) else points
    img = read_image(image) if isinstance(image, str) else np.asarray(image, float)
    h, w = img.shape[:2]
    vw, vh = sp.get("view_size") or (1, 0)
    if not h * vh or abs(vw * h / (vh * w) - 1) > 0.01:
        raise Bad(f"view_size: [w, h] of the image as you saw it (file {w}x{h})")
    rk, rs, hor, ver = (sp.get(k) or [] for k in ("rakes", "rect_size", "horizontals", "verticals"))
    if not 0 < len(rk) < 3 or len(rs) != 2 or np.shape(sp.get("rect")) != (4, 2):
        raise Bad("points file needs rect (4 corners), rect_size and 1 or 2 rakes")
    g, k = img if img.ndim == 2 else img[..., :3] @ [0.2126, 0.7152, 0.0722], w / vw
    bl, br, tr, tl = np.asarray(sp["rect"], float) * k
    ln = [refine_line(g, *v) for v in [(bl, br), (br, tr), (tl, tr), (bl, tl)] + [
        np.array(v, float).reshape(2, 2) * k for v in hor + ver + rk]]
    (sw, sh), tol = [_len(x) for x in rs], _len(sp.get("rect_tol", "0.25in"))
    fit = lambda pick, ratio: _solve([_hline(pick(f["points"])) for f in ln], len(hor), len(ver), ratio)  # noqa: E731
    slopes, gap = fit(lambda p: p, sw / sh)
    rng = np.random.default_rng(0)
    sims = [fit(lambda p: p[rng.integers(0, len(p), len(p))], (sw + rng.normal(0, tol)) / (sh + rng.normal(0, tol)))[0]
            for _ in range(200)]
    spread = float(np.ptp(slopes))
    sigma = math.sqrt(float(np.mean(np.array(sims).std(0) ** 2)) / len(slopes) + (spread / 2) ** 2)
    ch = {"rakes_rise_per_12": [round(float(s) * 12, 2) for s in slopes], "rake_spread_per_12": round(spread * 12, 2),
          "diagonals_disagree_pct": round(float(gap) * 100, 2), "line_rms_px": round(max(f["rms"] for f in ln), 2),
          "lines": len(ln), "fewest_edge_points": min(f["n"] for f in ln),
          "rect_second_edge": round(max(f["rival"] for f in ln[:4]), 2)}
    low = [f"{k} > {v}" for k, v in (("line_rms_px", 1.5), ("rake_spread_per_12", .5), ("diagonals_disagree_pct", 1),
                                     ("rect_second_edge", .75)) if ch[k] > v] + ["fewest_edge_points < 8"] * (
        ch["fewest_edge_points"] < 8)
    notes = [f"open {overlay}: is each line on its edge? (green wall, red rake)" if overlay else
             "no --overlay: write one and look at it"]
    if not synthetic and sigma * 12 < FLOOR:
        notes.append(f"sigma raised to the {FLOOR}/12 photo floor (fit {sigma * 12:.3f})")
        sigma = FLOOR / 12
    if overlay:
        _overlay(overlay, img, ln, len(rk))
    name = os.path.basename(image) if isinstance(image, str) else "array"
    return result(float(np.mean(slopes)), sigma, "photo", f"{name}, {sp.get('rect_name', 'rect')} {rs[0]} x {rs[1]}",
                  ch, notes, low)


def points(file, **_):
    p = np.load(file) if str(file).endswith(".npy") else np.loadtxt(file, ndmin=2)
    if p.ndim != 2 or p.shape[1] < 3 or len(p) < 4:
        raise Bad(f"{file}: needs 4 or more rows of x y z")
    p = p[:, :3] - p[:, :3].mean(0)  # centred: no intercept to fit
    X = p[:, :2]
    co = np.linalg.lstsq(X, p[:, 2], rcond=None)[0]
    s2 = np.sum((p[:, 2] - X @ co) ** 2) / (len(p) - 3)
    slope = math.hypot(*co)
    gr = co / max(slope, 1e-12)
    return result(slope, math.sqrt(gr @ (s2 * np.linalg.inv(X.T @ X)) @ gr), "points", os.path.basename(str(file)),
                  {"points": len(p), "rms_m": round(math.sqrt(s2), 4)})


def record(method, value, source=None, sigma=None, **_):
    src = (source or "").strip()
    s = float(REC.get(method, 0) if sigma is None else sigma)
    if method not in REC or not src or s <= 0:
        raise Bad(f"--method: {', '.join(REC)}; --source is required (report and date, sheet, file); --sigma > 0")
    return result(_pitch(value), s / 12, method, src, {"value": str(value)},
                  ["design intent, not as built: cross-check with a measurement"] * (method == "plans"))


def rule(covering, building, match=None, rules=None, **_):
    if covering not in MIN or building not in ("accessory", "house"):
        raise Bad(f"--covering: {', '.join(MIN)}; --building: accessory or house")
    path = rules or next((p for p in (RULES, os.path.join(REPO, RULES)) if os.path.isfile(p)), RULES)
    d = _load(path) if os.path.isfile(path) else {}
    v = match or (d.get("new_build_pitch") or {}).get(building)
    if not (d.get("approved_by") and d.get("approved_on") and v):
        raise Bad(f"no approved design rules: ask the user once, then save them ({path})")
    src = f"design rule {os.path.basename(path)}, approved by {d['approved_by']} on {d['approved_on']}"
    rise = _w(_pitch(v) * 12) if match else _pitch(v) * 12
    src = f"matches the main house (measured {v}), rounded; {src}" if match else f"{src}: new {building} {v}"
    least, code = MIN[covering]
    if rise < least - 1e-9:
        raise Bad(f"{rise:g}/12 is below the {least:g}/12 minimum for {covering} ({code})")
    return result(rise / 12, 0.0, "rule", f"{src}; {covering} needs {least:g}/12 or more ({code})", {
        "covering": covering, "building": building, "min_per_12": least, "code": code},
        ["double underlayment (IRC R905.2.2)"] * (covering == "asphalt_shingle" and rise < 4))


def combine(files, **_):
    # inverse-variance mean; over 3 of its own sigma from it is a conflict
    it = [f if isinstance(f, dict) else _load(f) for f in files]
    if len(it) < 2 or not all(i.get("ok") for i in it):
        raise Bad("combine needs two or more roof_pitch.py results")
    if any(i["method"] == "rule" for i in it):
        raise Bad("a rule result cannot be combined with measurements")
    s, e = np.array([i["slope"] for i in it]), np.array([max(i["sigma_per_12"], 0.001) / 12 for i in it])
    w = 1 / e ** 2
    m = float(w @ s / w.sum())
    bad = [f"{i['method']} ({i['source']}): {i['rise_per_12']}/12, {z:.1f} sigma from the mean"
           for i, z in zip(it, abs(s - m) / e) if z > 3]
    r = result(m, math.sqrt(1 / w.sum()), "combined", "; ".join(f"{i['method']}: {i['source']}" for i in it), {
        "inputs": len(it), "conflicts": bad}, low=["sources disagree: tell the user; do not use the mean"] * bool(bad))
    r["agree"] = not bad
    return r


def run(cmd, out=None, **kw):
    """Python entry (MCP); bad input gives {"ok": False, "error": ...}."""
    try:
        if np is None:
            raise Bad("needs numpy (pip install numpy)")
        res = {"photo": photo, "points": points, "record": record, "rule": rule, "combine": combine}[cmd](**kw)
    except Exception as e:  # noqa: BLE001 - reported as JSON, never a traceback
        return {"ok": False, "error": str(e) if isinstance(e, Bad) else f"{type(e).__name__}: {e}"}
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
    return res


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd, args in (("photo", "image! points! overlay synthetic?"), ("points", "file!"), ("combine", "files+"),
                      ("record", "method! value! sigma source"), ("rule", "covering! building! match rules")):
        s = sub.add_parser(cmd)
        for x in args.split() + ["out"]:
            s.add_argument(("" if x[-1] == "+" else "--") + x.strip("?!+"), **{
                "?": {"action": "store_true"}, "!": {"required": True}, "+": {"nargs": "+"}}.get(x[-1], {}))
    a = vars(p.parse_args(argv))
    res = run(a.pop("cmd"), **a)
    print(json.dumps(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
