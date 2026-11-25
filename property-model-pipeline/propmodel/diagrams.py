"""EagleView-style roof report pages drawn from the fitted model (model.json + report.json): no AI, no imagery.

Pages (each letter size, SVG + PNG):
  length   every roof edge drawn in plan (north up) and labelled with its TRUE 3-D length, coloured by kind
           (ridge, hip, valley, eave, rake, step flashing, headwall, transition), legend with per-kind totals
  pitch    each facet labelled x/12 with an arrow pointing down the slope
  area     each facet's area (ft2) and the roof total in squares
  summary  totals, predominant pitch, facet count, waste table (suggested row by report.py's rule), accessory
           lengths (ridge cap, starter, drip edge, valley, step flashing, headwall, ice barrier), access flags
           (walkable / steep / very steep), north arrow and the LiDAR flight line

Every number on a page is computed here from model.json; ``check_totals`` compares the totals with report.json
(lengths to 0.1 ft, areas to 1 ft2) so a stale report or model can never be drawn silently.

Labels are placed by :class:`LabelPlacer`: on the edge (or inside the facet) first; where that would overlap another
label, leave the drawing frame, or cross another edge, the label moves along the edge, then out to a leader line
(a thin grey line from the label to its edge / facet). A label that still overlaps after every candidate is
reported as unresolved (the CLI exits non-zero).

Pure matplotlib + shapely + numpy. The CLI is scripts/roof_diagrams.py.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polylabel, unary_union

M_PER_FT = 0.3048
SQFT_PER_M2 = 1.0 / M_PER_FT ** 2

# edge kinds in drawing / legend order; "sidewall" is shown as step flashing (what a roofer orders)
KINDS = ("ridge", "hip", "valley", "eave", "rake", "sidewall", "headwall", "transition")
KIND_LABEL = {"ridge": "Ridge", "hip": "Hip", "valley": "Valley", "eave": "Eave", "rake": "Rake",
              "sidewall": "Step flashing", "headwall": "Headwall", "transition": "Transition"}
# colour (fixed order, never cycled) + line style as the secondary encoding, so no kind relies on colour alone
KIND_STYLE = {
    "ridge": {"color": "#ec4647", "ls": "-", "lw": 2.4},
    "hip": {"color": "#f47230", "ls": "-", "lw": 2.0},
    "valley": {"color": "#257de0", "ls": "-", "lw": 2.0},
    "eave": {"color": "#008a17", "ls": "-", "lw": 2.0},
    "rake": {"color": "#6a4ce2", "ls": (0, (5, 2)), "lw": 2.0},
    "sidewall": {"color": "#00a888", "ls": (0, (6, 2, 1.5, 2)), "lw": 2.0},
    "headwall": {"color": "#d28e05", "ls": (0, (1.5, 1.5)), "lw": 2.2},
    "transition": {"color": "#666666", "ls": (0, (3, 2)), "lw": 1.6},
}
REPORT_EDGE_KEYS = ("ridge", "hip", "valley", "rake", "eave", "headwall", "sidewall")   # report.json imperial *_ft
WASTE_ROWS = (0, 10, 12, 15, 17, 20)
WALKABLE_MAX_X12, STEEP_MAX_X12 = 6.0, 9.0
TOL = {"ft": 0.1, "sqft": 1.0, "squares": 0.01}

INK, INK2, LINE_GREY = "#191919", "#666666", "#9c9c9c"
FACET_FILL, FACET_HIDDEN = "#f4f4f1", "#e6e6e1"


def ft(m):
    return m / M_PER_FT


def sqft(m2):
    return m2 * SQFT_PER_M2


def fmt_len(m, units="ft"):
    if units == "m":
        return f"{m:.2f} m" if m >= 0.005 else "<0.01 m"
    return f"{ft(m):.1f}'" if ft(m) >= 0.05 else "<0.1'"


def fmt_pitch(x12):
    return f"{x12:.1f}/12"


# ---------------------------------------------------------------------------------------------------------------
# geometry from model.json

def facet_polygon(f):
    polys = []
    for q in f.get("polygons", []):
        outer = np.asarray(q["outer"], float)[:, :2]
        holes = [np.asarray(h, float)[:, :2] for h in q.get("holes", [])]
        if len(outer) >= 3:
            polys.append(Polygon(outer, holes).buffer(0))
    return unary_union(polys) if polys else Polygon()


def facet_rows(model):
    """Facets with plan polygon, pitch, downslope direction (unit plan vector) and area."""
    out = []
    for f in model.get("facets", []):
        a, b = float(f["plane"][0]), float(f["plane"][1])
        g = math.hypot(a, b)
        zs = [c[2] for q in f.get("polygons", []) for c in q["outer"]]
        pitch = float(f.get("pitch_rise_per_12", g * 12))
        out.append({"id": f["id"], "poly": facet_polygon(f), "pitch_x12": pitch, "slope": g,
                    "down": (None if g < 1e-3 else np.array([-a / g, -b / g])),
                    "azimuth": f.get("azimuth"), "area_m2": float(f["area_m2"]),
                    "area_sqft": sqft(float(f["area_m2"])), "hidden": bool(f.get("hidden_from_above")),
                    "zmax": max(zs) if zs else 0.0, "zmean": float(np.mean(zs)) if zs else 0.0})
    return out


def edge_rows(model):
    out = []
    for i, e in enumerate(model.get("edges", [])):
        p0, p1 = np.asarray(e["p0"], float), np.asarray(e["p1"], float)
        L = float(e.get("length_m", np.linalg.norm(p1 - p0)))
        out.append({"index": i, "kind": e["kind"], "facets": list(e.get("facets", [])), "p0": p0, "p1": p1,
                    "length_m": L, "length_ft": ft(L), "penetration": e.get("penetration")})
    return out


def visible_regions(facets):
    """Painter's order (low to high mean z): the part of each facet not covered by a facet drawn after it."""
    order = sorted(range(len(facets)), key=lambda i: facets[i]["zmean"])
    vis = {}
    for k, i in enumerate(order):
        above = [facets[j]["poly"] for j in order[k + 1:]]
        p = facets[i]["poly"]
        if above:
            p = p.difference(unary_union(above).buffer(1e-6))
        vis[facets[i]["id"]] = p
    return order, vis


def largest(geom):
    if geom.is_empty:
        return geom
    if geom.geom_type == "Polygon":
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
    return max(parts, key=lambda g: g.area) if parts else Polygon()


# ---------------------------------------------------------------------------------------------------------------
# numbers

def totals(model):
    """Totals keyed like report.json 'imperial' (+ transition_ft and the facet count)."""
    er, fr = edge_rows(model), facet_rows(model)
    area_m2 = sum(f["area_m2"] for f in fr)
    t = {"roof_area_sqft": sqft(area_m2), "roof_squares": sqft(area_m2) / 100.0}
    for k in REPORT_EDGE_KEYS + ("transition",):
        t[f"{k}_ft"] = ft(sum(e["length_m"] for e in er if e["kind"] == k))
    t["facets"] = len(fr)
    return t


def by_kind(model):
    er = edge_rows(model)
    out = {}
    for k in KINDS:
        es = [e for e in er if e["kind"] == k]
        if es:
            L = sum(e["length_m"] for e in es)
            out[k] = {"count": len(es), "length_m": L, "length_ft": ft(L)}
    return out


def check_totals(tot, report, facets=None):
    """[(key, drawn, report)] for every total that differs from report.json beyond the tolerance (lengths 0.1 ft,
    areas 1 ft2, squares 0.01); with ``facets`` (facet_rows) also the facet count and each facet's area."""
    imp = (report or {}).get("imperial", {}) or {}
    diffs = []
    for k, v in tot.items():
        if k not in imp or not isinstance(imp[k], (int, float)):
            continue
        tol = TOL["sqft"] if k.endswith("sqft") else TOL["ft"] if k.endswith("_ft") else TOL["squares"]
        if abs(float(v) - float(imp[k])) > tol:
            diffs.append((k, float(v), float(imp[k])))
    rf = (report or {}).get("facets")
    if facets is not None and isinstance(rf, list):
        if len(rf) != len(facets):
            diffs.append(("facets", float(len(facets)), float(len(rf))))
        else:
            rep = {f.get("id"): f for f in rf}
            for f in facets:
                r = rep.get(f["id"])
                if r is None:
                    diffs.append((f"facet {f['id']} missing from report.json", f["area_sqft"], float("nan")))
                elif "area_sqft" in r and abs(float(r["area_sqft"]) - f["area_sqft"]) > TOL["sqft"]:
                    diffs.append((f"facet {f['id']} area_sqft", f["area_sqft"], float(r["area_sqft"])))
    return diffs


def suggested_waste(model):
    """report.py's rule (WASTE_BY_COMPLEXITY on the hip + valley count), applied to model.json edges."""
    try:
        from .report import WASTE_BY_COMPLEXITY
    except Exception:  # noqa: BLE001
        WASTE_BY_COMPLEXITY = [(0, 10), (2, 12), (6, 15), (12, 17), (20, 20)]
    n = sum(1 for e in model.get("edges", []) if e["kind"] in ("hip", "valley"))
    w = 10
    for k, pct in WASTE_BY_COMPLEXITY:
        if n >= k:
            w = pct
    return w, n


def waste_table(area_sqft, suggested, chosen=None):
    rows = []
    for p in sorted(set(WASTE_ROWS) | ({chosen} if chosen is not None else set())):
        a = area_sqft * (1 + p / 100.0)
        rows.append({"pct": p, "area_sqft": a, "squares": a / 100.0, "bundles": int(math.ceil(a / 100.0 * 3 - 1e-9)),
                     "suggested": p == suggested, "chosen": chosen is not None and p == chosen})
    return rows


def accessories(tot):
    g = lambda k: tot.get(f"{k}_ft", 0.0)  # noqa: E731
    return {"ridge_cap": g("ridge") + g("hip"), "starter": g("eave") + g("rake"), "drip_edge": g("eave") + g("rake"),
            "valley": g("valley"), "step_flashing": g("sidewall"), "headwall_flashing": g("headwall"),
            "ice_barrier": g("eave") + g("valley")}


ACCESSORY_ROWS = (("ridge_cap", "Ridge / hip cap", "ridges + hips"), ("starter", "Starter", "eaves + rakes"),
                  ("drip_edge", "Drip edge", "eaves + rakes"), ("valley", "Valley lining", "valleys"),
                  ("step_flashing", "Step flashing", "roof-to-wall, sloped"),
                  ("headwall_flashing", "Headwall flashing", "roof-to-wall, level"),
                  ("ice_barrier", "Ice barrier (length)", "eaves + valleys; width per local code"))


def access_class(x12):
    if x12 <= WALKABLE_MAX_X12:
        return "walkable"
    return "steep" if x12 <= STEEP_MAX_X12 else "very steep"


def _covered_edge(e, model, clear=0.1):
    """True when a higher roof plane lies over the edge's midpoint (an edge tucked under another roof)."""
    mid = (np.asarray(e["p0"], float) + np.asarray(e["p1"], float)) / 2
    own = set(e.get("facets", []))
    for f in model.get("facets", []):
        if f["id"] in own:
            continue
        a, b, c = f["plane"]
        if a * mid[0] + b * mid[1] + c > mid[2] + clear and facet_polygon(f).buffer(-0.02).contains(Point(mid[0], mid[1])):
            return True
    return False


def access_summary(facets, model, report):
    rows = [{"id": f["id"], "pitch_x12": f["pitch_x12"], "area_sqft": f["area_sqft"], "class": access_class(f["pitch_x12"])}
            for f in facets]
    tot = sum(r["area_sqft"] for r in rows) or 1.0
    summ = {c: {"facets": sum(1 for r in rows if r["class"] == c),
                "share": sum(r["area_sqft"] for r in rows if r["class"] == c) / tot}
            for c in ("walkable", "steep", "very steep")}
    eave_z = [max(e["p0"][2], e["p1"][2]) for e in model.get("edges", [])
              if e["kind"] == "eave" and not _covered_edge(e, model)]
    meas = (report or {}).get("measurements_si", {}) or {}
    grade = meas.get("grade.low")
    if model.get("ground") and grade is None:
        grade_note = "above the model ground plane at the house centre"
        grade = float(model["ground"][2])
    elif grade is None:
        grade_note, grade = "above the site datum (z = 0, ground at the address point)", 0.0
    else:
        grade_note = "above the lowest finished grade at the walls"
    hi_eave = ft(max(eave_z) - grade) if eave_z else None
    return {"rule": f"walkable <= {WALKABLE_MAX_X12:g}/12, steep <= {STEEP_MAX_X12:g}/12, very steep above",
            "facets": rows, "summary": summ, "highest_eave_ft": hi_eave, "highest_eave_ref": grade_note,
            "height_low_side_ft": (report or {}).get("imperial", {}).get("height_low_side_ft"),
            "height_high_side_ft": (report or {}).get("imperial", {}).get("height_high_side_ft")}


def pitch_summary(facets):
    A = sum(f["area_sqft"] for f in facets) or 1.0
    buckets = {}
    for f in facets:
        k = round(f["pitch_x12"] * 2) / 2
        buckets[k] = buckets.get(k, 0.0) + f["area_sqft"]
    top = max(buckets.items(), key=lambda kv: kv[1]) if buckets else (0.0, 0.0)
    return {"predominant": f"{top[0]:g}/12", "predominant_share": top[1] / A,
            "weighted_x12": sum(f["pitch_x12"] * f["area_sqft"] for f in facets) / A,
            "min_x12": min((f["pitch_x12"] for f in facets), default=0.0),
            "max_x12": max((f["pitch_x12"] for f in facets), default=0.0),
            "buckets": [{"pitch": f"{k:g}/12", "area_sqft": v, "share": v / A} for k, v in sorted(buckets.items())]}


def sigma_imperial(report):
    s = (report or {}).get("measurement_sigma_si", {}) or {}
    out = {}
    if s.get("roof.area"):
        out["roof_area_sqft"] = sqft(float(s["roof.area"]))
        out["roof_squares"] = out["roof_area_sqft"] / 100.0
    for k in REPORT_EDGE_KEYS + ("transition",):
        if s.get(f"edge.{k}"):
            out[f"{k}_ft"] = ft(float(s[f"edge.{k}"]))
    return out


# ---------------------------------------------------------------------------------------------------------------
# label placement

def _rect(cx, cy, w, h, ang_deg):
    a = math.radians(ang_deg)
    u = np.array([math.cos(a), math.sin(a)]) * w / 2
    v = np.array([-math.sin(a), math.cos(a)]) * h / 2
    c = np.array([cx, cy])
    return Polygon([c - u - v, c + u - v, c + u + v, c - u + v])


class LabelPlacer:
    """Collision-free label placement in display pixels (the axes transform must be final before use).

    ``place`` tries candidates in order in two passes: pass 1 also refuses crossing any 'soft' line (another
    edge); pass 2 only refuses overlapping placed labels / obstacles and leaving the frame."""

    def __init__(self, ax, pad_pt=1.6, box_pad=0.22):
        self.ax, self.fig = ax, ax.figure
        self.renderer = self.fig.canvas.get_renderer()
        self.px_pt = self.fig.dpi / 72.0
        self.pad = pad_pt * self.px_pt
        self.box_pad = box_pad
        bb = ax.get_window_extent(self.renderer)
        self.frame = box(bb.x0 + 2, bb.y0 + 2, bb.x1 - 2, bb.y1 - 2)
        self.hard = []          # placed label polygons and obstacles (display px, already padded)
        self.soft = []          # (owner, LineString px)
        self.records = []
        self._sizes = {}

    def px(self, xy):
        return self.ax.transData.transform(np.atleast_2d(np.asarray(xy, float)))

    def data(self, px):
        return self.ax.transData.inverted().transform(np.atleast_2d(np.asarray(px, float)))

    def px_per_data(self):
        a, b = self.px([[0, 0], [1, 0]])
        return float(np.linalg.norm(b - a))

    def measure(self, text, fontsize, weight="normal"):
        key = (text, fontsize, weight)
        if key not in self._sizes:
            t = self.ax.text(0, 0, text, fontsize=fontsize, fontweight=weight, ha="center", va="center")
            bb = t.get_window_extent(self.renderer)
            t.remove()
            p = 2 * self.box_pad * fontsize * self.px_pt
            self._sizes[key] = (bb.width + p, bb.height + p)
        return self._sizes[key]

    def add_obstacle_px(self, geom):
        self.hard.append(geom.buffer(self.pad))

    def add_obstacle_data(self, geom_data_coords):
        g = geom_data_coords
        if g.geom_type == "LineString":
            self.add_obstacle_px(LineString(self.px(np.asarray(g.coords))))
        else:
            self.add_obstacle_px(Polygon(self.px(np.asarray(g.exterior.coords))))

    def add_soft_line(self, owner, p0, p1):
        self.soft.append((owner, LineString(self.px([p0[:2], p1[:2]]))))

    def _free(self, poly, owner, soft):
        if not self.frame.contains(poly):
            return False
        if any(poly.intersects(h) for h in self.hard):
            return False
        if soft and any(o != owner and poly.intersects(l) for o, l in self.soft):
            return False
        return True

    def place(self, label_id, text, anchor_xy, candidates, fontsize=7.0, weight="normal", owner=None,
              color=INK, leader_color=LINE_GREY, zorder=6):
        """candidates: [(xy_data, angle_deg, is_leader[, leader_anchor_xy])]. Returns the record (dict)."""
        w, h = self.measure(text, fontsize, weight)
        default_anchor = self.px(anchor_xy[:2])[0]
        # pass 1: no label / obstacle overlap, no crossing of other edges, leader clear of labels
        # pass 2: edges may be crossed; pass 3: the leader may run under another label (its start is covered)
        for soft, leader_check in ((True, True), (False, True), (False, False)):
            for k, cand in enumerate(candidates):
                xy, ang, leader = cand[:3]
                anchor_px = self.px(cand[3][:2])[0] if len(cand) > 3 else default_anchor
                c = self.px(xy)[0]
                poly = _rect(c[0], c[1], w, h, ang)
                if not self._free(poly, owner, soft):
                    continue
                seg = None
                if leader:
                    q = poly.exterior.interpolate(poly.exterior.project(Point(anchor_px)))
                    seg = LineString([anchor_px, (q.x, q.y)])
                    if leader_check and seg.length > 1e-6 and any(seg.intersects(hh) for hh in self.hard):
                        continue
                return self._commit(label_id, text, xy, ang, poly, seg, k, soft, fontsize, weight, color,
                                    leader_color, zorder, resolved=True)
        xy, ang = candidates[0][:2]
        c = self.px(xy)[0]
        poly = _rect(c[0], c[1], w, h, ang)
        return self._commit(label_id, text, xy, ang, poly, None, 0, False, fontsize, weight, "#c00000",
                            leader_color, zorder, resolved=False)

    def _commit(self, label_id, text, xy, ang, poly, seg, k, soft, fontsize, weight, color, leader_color, zorder,
                resolved):
        ax = self.ax
        if seg is not None and seg.length > 1e-6:
            d = self.data(np.asarray(seg.coords))
            ln, = ax.plot(d[:, 0], d[:, 1], color=leader_color, lw=0.6, zorder=zorder - 1, solid_capstyle="round")
            ln.set_gid(f"{label_id}-leader")
            ax.plot([d[0, 0]], [d[0, 1]], marker="o", ms=1.6, color=leader_color, zorder=zorder - 1)
        t = ax.text(xy[0], xy[1], text, fontsize=fontsize, fontweight=weight, color=color, ha="center",
                    va="center", rotation=ang, rotation_mode="anchor", zorder=zorder,
                    bbox={"boxstyle": f"round,pad={self.box_pad}", "fc": "white", "ec": "none", "alpha": 0.92})
        t.set_gid(label_id)
        self.hard.append(poly.buffer(self.pad))
        rec = {"id": label_id, "text": text, "xy": [float(xy[0]), float(xy[1])], "angle": float(ang),
               "leader": seg is not None, "candidate": int(k), "strict": bool(soft), "resolved": resolved}
        self.records.append(rec)
        return rec


def _norm_angle(dx, dy):
    a = math.degrees(math.atan2(dy, dx))
    if a > 90:
        a -= 180
    elif a <= -90:
        a += 180
    return a


def _dirs(base, n=16):
    """Unit directions starting at ``base`` and fanning out both ways (base, +22.5, -22.5, +45, ...)."""
    b = math.atan2(base[1], base[0])
    out = [base / np.linalg.norm(base)]
    for i in range(1, n // 2 + 1):
        for s in (1, -1):
            a = b + s * i * 2 * math.pi / n
            out.append(np.array([math.cos(a), math.sin(a)]))
    return out[:n]


def edge_candidates(e, centroid, label_h, along=(0.5, 0.32, 0.68, 0.2, 0.8)):
    p0, p1 = e["p0"][:2], e["p1"][:2]
    d = p1 - p0
    ang = _norm_angle(d[0], d[1])
    cands = [(p0 + f * d, ang, False) for f in along]
    mid = (p0 + p1) / 2
    n = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
    if np.dot(n, mid - centroid) < 0:
        n = -n
    for dist in (1.6, 2.6, 3.8, 5.2, 7.0, 9.5, 12.5):
        for f in (0.5, 0.25, 0.75, 0.1, 0.9):            # leaders may start anywhere along the edge
            a = p0 + f * d
            for u in _dirs(n):
                cands.append((a + u * dist * label_h, 0.0, True, a))
    return cands, mid


def facet_candidates(region, centroid, label_h, anchor=None):
    reg = largest(region)
    cands = []
    if not reg.is_empty and reg.area > 1e-6:
        try:
            p = polylabel(reg, tolerance=0.02)
        except Exception:  # noqa: BLE001
            p = reg.representative_point()
        anchor = np.array([p.x, p.y]) if anchor is None else anchor
        cands.append((np.array([p.x, p.y]), 0.0, False))
        rp = reg.representative_point()
        cands.append((np.array([rp.x, rp.y]), 0.0, False))
        if reg.contains(reg.centroid):
            cands.append((np.array([reg.centroid.x, reg.centroid.y]), 0.0, False))
    if anchor is None:
        anchor = np.asarray(centroid, float)
    out = anchor - centroid
    if np.linalg.norm(out) < 1e-6:
        out = np.array([0.0, 1.0])
    for dist in (1.8, 3.0, 4.4, 6.0, 8.0, 10.5, 13.5):
        for u in _dirs(out):
            cands.append((anchor + u * dist * label_h, 0.0, True))
    return cands, anchor


# ---------------------------------------------------------------------------------------------------------------
# pages

PAGE_W, PAGE_H = 8.5, 11.0
PLAN_RECT = (0.06, 0.30, 0.88, 0.60)


def _new_page(dpi, title, subtitle, footer):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(PAGE_W, PAGE_H), dpi=dpi)
    fig.text(0.06, 0.965, title, fontsize=17, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.06, 0.935, subtitle, fontsize=9, color=INK2, va="top")
    fig.add_artist(__import__("matplotlib.lines", fromlist=["Line2D"]).Line2D(
        [0.06, 0.94], [0.918, 0.918], color="#d9d9d9", lw=0.8, transform=fig.transFigure))
    for i, line in enumerate(footer or []):
        fig.text(0.06, 0.035 - i * 0.014, line, fontsize=6.6, color=INK2, va="top")
    return fig


def _plan_axes(fig, bounds, rect=PLAN_RECT, margin=0.22):
    x0, y0, x1, y1 = bounds
    dx, dy = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    m = margin * max(dx, dy)
    x0, x1, y0, y1 = x0 - m, x1 + m, y0 - m, y1 + m
    ax = fig.add_axes(rect)
    w_in, h_in = rect[2] * PAGE_W, rect[3] * PAGE_H
    s = max((x1 - x0) / w_in, (y1 - y0) / h_in)      # data units per inch, equal aspect by construction
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax.set_xlim(cx - s * w_in / 2, cx + s * w_in / 2)
    ax.set_ylim(cy - s * h_in / 2, cy + s * h_in / 2)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    return ax


def _draw_facets(ax, facets, order, hidden_hatch=True, fill=FACET_FILL, edge_lw=0.5, edge_color="#b5b5b0"):
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path
    for i in order:
        f = facets[i]
        geoms = [f["poly"]] if f["poly"].geom_type == "Polygon" else list(getattr(f["poly"], "geoms", []))
        for g in geoms:
            if g.is_empty or g.geom_type != "Polygon":
                continue
            verts, codes = [], []
            for ring in [g.exterior, *g.interiors]:
                c = np.asarray(ring.coords)[:, :2]
                verts += c.tolist()
                codes += [Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY]
            pp = PathPatch(Path(verts, codes), fc=FACET_HIDDEN if (f["hidden"] and hidden_hatch) else fill,
                           ec=edge_color, lw=edge_lw,
                           hatch="////" if (f["hidden"] and hidden_hatch) else None, zorder=1 + 0.001 * i)
            pp.set_gid(f"facet-{f['id']}")
            ax.add_patch(pp)


def _north_arrow(ax, placer, size_in=0.42):
    """North arrow in the top-right corner of the plan axes (+y = north in the model frame)."""
    from matplotlib.patches import FancyArrow
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    s = (x1 - x0) / (PLAN_RECT[2] * PAGE_W)
    L = size_in * s
    cx, cy = x1 - 0.55 * size_in * s, y1 - 1.25 * L
    ar = FancyArrow(cx, cy, 0, L, width=0.10 * L, head_width=0.42 * L, head_length=0.38 * L,
                    length_includes_head=True, color=INK, zorder=8)
    ar.set_gid("north-arrow")
    ax.add_patch(ar)
    ax.text(cx, cy + L * 1.18, "N", ha="center", va="bottom", fontsize=10, fontweight="bold", color=INK, zorder=8)
    if placer is not None:
        placer.add_obstacle_data(box(cx - 0.4 * L, cy - 0.1 * L, cx + 0.4 * L, cy + 1.65 * L))


def _scale_bar(ax, placer, units="ft"):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    span = (x1 - x0) * 0.22
    if units == "m":
        nice = [1, 2, 5, 10, 20, 50]
        L = max([n for n in nice if n <= span] or [1]); Lm = L; lab = f"{L:g} m"
    else:
        nice = [5, 10, 20, 25, 50, 100]
        L = max([n for n in nice if n * M_PER_FT <= span] or [5]); Lm = L * M_PER_FT; lab = f"{L:g} ft"
    bx, by = x0 + 0.03 * (x1 - x0), y0 + 0.035 * (y1 - y0)
    ax.plot([bx, bx + Lm], [by, by], color=INK, lw=1.6, solid_capstyle="butt", zorder=8)
    for xx in (bx, bx + Lm):
        ax.plot([xx, xx], [by - 0.006 * (y1 - y0), by + 0.006 * (y1 - y0)], color=INK, lw=1.0, zorder=8)
    ax.text(bx + Lm / 2, by + 0.012 * (y1 - y0), lab, ha="center", va="bottom", fontsize=7, color=INK, zorder=8)
    if placer is not None:
        placer.add_obstacle_data(box(bx - 0.01 * (x1 - x0), by - 0.012 * (y1 - y0), bx + Lm + 0.01 * (x1 - x0),
                                     by + 0.04 * (y1 - y0)))


def _bounds(facets, edges):
    pts = [np.asarray(f["poly"].bounds).reshape(2, 2) for f in facets if not f["poly"].is_empty]
    pts += [np.vstack([e["p0"][:2], e["p1"][:2]]) for e in edges]
    P = np.vstack(pts) if pts else np.zeros((2, 2))
    return float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())


def _roof_centroid(facets):
    u = unary_union([f["poly"] for f in facets if not f["poly"].is_empty])
    c = u.centroid if not u.is_empty else Point(0, 0)
    return np.array([c.x, c.y])


def _table(fig, x, y, rows, cols, fontsize=8.0, line=0.0175, header=True, bold_rows=(), mark_rows=(), align=None,
           mark_width=None):
    """Plain text table in figure coordinates. rows: list of tuples of strings; cols: x offsets (fraction);
    align: 'l' / 'r' per column (default: first left, the rest right). Returns the y below the table."""
    align = align or ("l" + "r" * (len(cols) - 1))
    for r, row in enumerate(rows):
        hdr = header and r == 0
        weight = "bold" if hdr or r in bold_rows else "normal"
        color = INK2 if hdr else INK
        if r in mark_rows:
            from matplotlib.patches import Rectangle
            fig.add_artist(Rectangle((x - 0.006, y - r * line - 0.45 * line), mark_width or (cols[-1] + 0.012),
                                     line * 0.95,
                                     transform=fig.transFigure, fc="#fff1c9", ec="none", zorder=0))
        for c, cell in enumerate(row):
            ha = "left" if align[c] == "l" else "right"
            fig.text(x + cols[c], y - r * line, cell, fontsize=fontsize, fontweight=weight, color=color, ha=ha,
                     va="center")
        if hdr:
            from matplotlib.lines import Line2D
            fig.add_artist(Line2D([x - 0.004, x + (mark_width or cols[-1] + 0.004)], [y - 0.55 * line] * 2,
                                  color="#cfcfcf", lw=0.6,
                                  transform=fig.transFigure))
    return y - len(rows) * line


def _note(fig, x, y, text, width=118, fontsize=7.0, color=INK2, **kw):
    import textwrap
    return fig.text(x, y, "\n".join(textwrap.wrap(text, width)), fontsize=fontsize, color=color, va="top",
                    linespacing=1.35, **kw)


def _draw_covered(ax, facets, vis, min_area=0.05):
    """Hatch the part of each lower facet that runs on under a higher roof (counted in the area, not seen from above)."""
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path
    n = 0
    for f in facets:
        cov = f["poly"].difference(vis[f["id"]].buffer(1e-6))
        for g in ([cov] if cov.geom_type == "Polygon" else list(getattr(cov, "geoms", []))):
            if g.geom_type != "Polygon" or g.area < min_area:
                continue
            verts, codes = [], []
            for ring in [g.exterior, *g.interiors]:
                c = np.asarray(ring.coords)[:, :2]
                verts += c.tolist()
                codes += [Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY]
            pp = PathPatch(Path(verts, codes), fc="none", ec="#8a8a85", lw=0.6, ls=(0, (3, 2)), hatch="////",
                           zorder=2.5)
            pp.set_gid(f"covered-{f['id']}")
            ax.add_patch(pp)
            n += 1
    return n


def draw_length_page(model, report, ctx, dpi, units="ft"):
    facets, edges = facet_rows(model), edge_rows(model)
    order, vis = visible_regions(facets)
    fig = _new_page(dpi, "Roof length diagram", ctx["subtitle"], ctx["footer"])
    ax = _plan_axes(fig, _bounds(facets, edges))
    _draw_facets(ax, facets, order, edge_lw=0.0, hidden_hatch=False)
    placer = LabelPlacer(ax)
    _north_arrow(ax, placer)
    _scale_bar(ax, placer, units)
    for e in edges:
        st = KIND_STYLE.get(e["kind"], KIND_STYLE["transition"])
        ln, = ax.plot([e["p0"][0], e["p1"][0]], [e["p0"][1], e["p1"][1]], color=st["color"], ls=st["ls"], lw=st["lw"],
                      solid_capstyle="round", zorder=3)
        ln.set_gid(f"edge-{e['index']}")
        placer.add_soft_line(e["index"], e["p0"], e["p1"])
    cen = _roof_centroid(facets)
    fs = 6.6 if len(edges) < 40 else 5.8
    label_h = placer.measure("00.0'", fs)[1] / placer.px_per_data()
    recs = []
    for e in sorted(edges, key=lambda e: -e["length_m"]):          # long edges first: they have the most room
        cands, mid = edge_candidates(e, cen, label_h)
        r = placer.place(f"edge-label-{e['index']}", fmt_len(e["length_m"], units), mid, cands, fontsize=fs,
                         owner=e["index"])
        r.update(index=e["index"], kind=e["kind"], length_ft=e["length_ft"])
        recs.append(r)
    # legend + per-kind totals
    bk = by_kind(model)
    sig = ctx.get("sigma", {})
    rows = [("Edge", "", "Count", "Length (ft)", "Length (m)")]
    kinds = [k for k in KINDS if k in bk]
    for k in kinds:
        s = sig.get(f"{k}_ft")
        rows.append((KIND_LABEL[k], "", str(bk[k]["count"]),
                     f"{bk[k]['length_ft']:.1f}" + (f" ± {s:.1f}" if s else ""), f"{bk[k]['length_m']:.2f}"))
    y = _table(fig, 0.10, 0.27, rows, [0.0, 0.0, 0.40, 0.58, 0.74], fontsize=8.2)
    from matplotlib.lines import Line2D
    for i, k in enumerate(kinds, start=1):
        st = KIND_STYLE[k]
        yy = 0.27 - i * 0.0175
        fig.add_artist(Line2D([0.24, 0.32], [yy, yy], color=st["color"], ls=st["ls"], lw=st["lw"],
                              transform=fig.transFigure))
    _note(fig, 0.10, y - 0.012, "Labels are true lengths along the roof surface (3-D), rounded to 0.1 ft; the drawing "
          "is a plan view, north up. Grey leader lines point to edges too short to carry their own label.", width=125)
    return fig, recs


def draw_pitch_page(model, report, ctx, dpi, units="ft"):
    facets, edges = facet_rows(model), edge_rows(model)
    order, vis = visible_regions(facets)
    fig = _new_page(dpi, "Roof pitch diagram", ctx["subtitle"], ctx["footer"])
    ax = _plan_axes(fig, _bounds(facets, edges))
    _draw_facets(ax, facets, order, hidden_hatch=False)
    _draw_covered(ax, facets, vis)
    placer = LabelPlacer(ax)
    _north_arrow(ax, placer)
    _scale_bar(ax, placer, units)
    for e in edges:
        ax.plot([e["p0"][0], e["p1"][0]], [e["p0"][1], e["p1"][1]], color="#5a5a5a", lw=0.9, zorder=3,
                solid_capstyle="round")
        placer.add_soft_line(("edge", e["index"]), e["p0"], e["p1"])
    cen = _roof_centroid(facets)
    label_h = placer.measure("00.0/12", 8.0, "bold")[1] / placer.px_per_data()
    recs = []
    for f in sorted(facets, key=lambda f: -f["area_m2"]):
        text = "flat" if f["down"] is None else fmt_pitch(f["pitch_x12"])
        cands, anchor = facet_candidates(vis[f["id"]], cen, label_h)
        r = placer.place(f"facet-pitch-{f['id']}", text, anchor, cands, fontsize=8.0, weight="bold")
        r.update(facet=f["id"], pitch_x12=f["pitch_x12"])
        if f["down"] is not None:
            r["arrow"] = _slope_arrow(ax, placer, f, vis[f["id"]], np.asarray(r["xy"]) if not r["leader"] else anchor,
                                      label_h, from_label=not r["leader"], label_id=r["id"])
        recs.append(r)
    _note(fig, 0.10, 0.27, "Pitch = rise in inches per 12 in of run, from the LiDAR-fitted roof planes. Arrows point "
          "down the slope (the way water runs). Hatched: a lower roof that runs on under a higher one.", width=110,
          fontsize=7.4)
    ps = pitch_summary(facets)
    rows = [("Pitch", "Area (ft²)", "Share")] + [(b["pitch"], f"{b['area_sqft']:,.0f}", f"{100 * b['share']:.0f} %")
                                                 for b in ps["buckets"]]
    _table(fig, 0.10, 0.225, rows[:12], [0.0, 0.30, 0.42], fontsize=8.2)
    fig.text(0.62, 0.225, f"Predominant pitch {ps['predominant']} ({100 * ps['predominant_share']:.0f} % of the roof)\n"
             f"Area-weighted {fmt_pitch(ps['weighted_x12'])} · range {fmt_pitch(ps['min_x12'])} – "
             f"{fmt_pitch(ps['max_x12'])}", fontsize=8.2, color=INK, va="center", linespacing=1.6)
    return fig, recs


def _slope_arrow(ax, placer, f, region, start_xy, label_h, from_label=True, label_id=""):
    """Arrow down the slope inside the facet's visible region; registered as an obstacle."""
    reg = largest(region) if not region.is_empty else f["poly"]
    d = f["down"]
    p = np.asarray(start_xy, float)
    gap = (0.95 * label_h) if from_label else 0.0
    s = p + d * gap
    ray = LineString([s, s + d * 1000.0])
    inter = ray.intersection(reg.boundary)
    pts = [np.array(g.coords[0]) for g in getattr(inter, "geoms", [inter]) if not g.is_empty]
    room = min((float(np.linalg.norm(q - s)) for q in pts), default=0.0)
    L = min(room - 0.35 * label_h, 2.2 * label_h + 0.12 * math.sqrt(max(reg.area, 0.0)), 3.0)
    if L < 0.8 * label_h:          # too little room past the label: a short arrow centred on the anchor
        s = p - d * 0.45 * label_h
        L = 0.9 * label_h
    e = s + d * L
    from matplotlib.patches import FancyArrowPatch
    a = FancyArrowPatch(posA=tuple(s), posB=tuple(e), arrowstyle="-|>,head_length=0.5,head_width=0.25",
                        mutation_scale=10, color=INK, lw=1.1, shrinkA=0, shrinkB=0, zorder=5)
    a.set_gid(f"{label_id}-arrow")
    ax.add_patch(a)
    placer.add_obstacle_data(LineString([s, e]))
    return {"from": s.tolist(), "to": e.tolist(), "length": float(L)}


def draw_area_page(model, report, ctx, dpi, units="ft"):
    facets, edges = facet_rows(model), edge_rows(model)
    order, vis = visible_regions(facets)
    fig = _new_page(dpi, "Roof area diagram", ctx["subtitle"], ctx["footer"])
    ax = _plan_axes(fig, _bounds(facets, edges))
    _draw_facets(ax, facets, order, hidden_hatch=False)
    _draw_covered(ax, facets, vis)
    placer = LabelPlacer(ax)
    _north_arrow(ax, placer)
    _scale_bar(ax, placer, units)
    for e in edges:
        ax.plot([e["p0"][0], e["p1"][0]], [e["p0"][1], e["p1"][1]], color="#5a5a5a", lw=0.9, zorder=3)
        placer.add_soft_line(("edge", e["index"]), e["p0"], e["p1"])
    cen = _roof_centroid(facets)
    label_h = placer.measure("F1\n0,000 ft²", 7.6)[1] / placer.px_per_data()
    recs = []
    for f in sorted(facets, key=lambda f: -f["area_m2"]):
        val = f"{f['area_m2']:.1f} m²" if units == "m" else f"{f['area_sqft']:,.0f} ft²"
        cands, anchor = facet_candidates(vis[f["id"]], cen, label_h)
        r = placer.place(f"facet-area-{f['id']}", f"{f['id']}\n{val}", anchor, cands, fontsize=7.6)
        r.update(facet=f["id"], area_sqft=f["area_sqft"])
        recs.append(r)
    tot = ctx["totals"]
    s = ctx.get("sigma", {}).get("roof_area_sqft")
    pm = f" ± {s:,.0f}" if s else ""
    fig.text(0.10, 0.27, f"Total roof area {tot['roof_area_sqft']:,.0f}{pm} ft²  =  {tot['roof_squares']:.2f} squares",
             fontsize=13, fontweight="bold", color=INK, va="top")
    _note(fig, 0.10, 0.235, f"{tot['facets']} facets. Areas are true sloped areas (not plan areas) of the "
          "LiDAR-fitted planes; 1 square = 100 ft². Hatched: a lower roof that runs on under a higher one; its hidden "
          "part is included.", width=110, fontsize=7.6)
    rows = [("Facet", "Pitch", "Area (ft²)", "Area (m²)")]
    for f in sorted(facets, key=lambda f: f["id"])[:14]:
        rows.append((f["id"], fmt_pitch(f["pitch_x12"]), f"{f['area_sqft']:,.0f}", f"{f['area_m2']:.1f}"))
    if len(facets) > 14:
        rows.append((f"+ {len(facets) - 14} more", "", "", ""))
    _table(fig, 0.10, 0.20, rows, [0.0, 0.18, 0.34, 0.47], fontsize=7.8, line=0.0145)
    return fig, recs


def draw_summary_page(model, report, ctx, dpi, units="ft"):
    facets, edges = facet_rows(model), edge_rows(model)
    order, _ = visible_regions(facets)
    fig = _new_page(dpi, "Roof measurement summary", ctx["subtitle"], ctx["footer"])
    tot, sig, ps, acc = ctx["totals"], ctx.get("sigma", {}), ctx["pitch"], ctx["accessories"]
    pm = lambda k, f="{:,.0f}": (" ± " + f.format(sig[k])) if sig.get(k) else ""  # noqa: E731
    rows = [("Roof totals", "Value"),
            ("Total roof area", f"{tot['roof_area_sqft']:,.0f}{pm('roof_area_sqft')} ft²"),
            ("Squares (no waste)", f"{tot['roof_squares']:.2f}{pm('roof_squares', '{:.2f}')}"),
            ("Facets", str(tot["facets"])),
            ("Predominant pitch", f"{ps['predominant']} ({100 * ps['predominant_share']:.0f} %)"),
            ("Area-weighted pitch", fmt_pitch(ps["weighted_x12"])),
            ("Pitch range", f"{fmt_pitch(ps['min_x12'])} – {fmt_pitch(ps['max_x12'])}")]
    y = _table(fig, 0.06, 0.895, rows, [0.0, 0.46], fontsize=8.6, line=0.019)
    bk = by_kind(model)
    rows = [("Lengths by kind", "ft")] + [(KIND_LABEL[k], f"{bk[k]['length_ft']:.1f}") for k in KINDS if k in bk]
    y = _table(fig, 0.06, y - 0.018, rows, [0.0, 0.46], fontsize=8.6, line=0.019)
    rows = [("Accessories", "ft", "From")] + [(lab, f"{acc[k]:.1f}", src) for k, lab, src in ACCESSORY_ROWS]
    y = _table(fig, 0.06, y - 0.018, rows, [0.0, 0.25, 0.27], fontsize=8.2, line=0.018, align="lrl", mark_width=0.46)
    # small plan with the north arrow
    ax = _plan_axes(fig, _bounds(facets, edges), rect=(0.58, 0.60, 0.36, 0.30), margin=0.12)
    _draw_facets(ax, facets, order, hidden_hatch=False)
    _draw_covered(ax, facets, visible_regions(facets)[1])
    for e in edges:
        st = KIND_STYLE.get(e["kind"], KIND_STYLE["transition"])
        ax.plot([e["p0"][0], e["p1"][0]], [e["p0"][1], e["p1"][1]], color=st["color"], ls=st["ls"], lw=1.2, zorder=3)
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    L = 0.09 * (y1 - y0)
    from matplotlib.patches import FancyArrow
    na = FancyArrow(x1 - 0.06 * (x1 - x0), y1 - 1.6 * L, 0, L, width=0.1 * L, head_width=0.45 * L, head_length=0.4 * L,
                    length_includes_head=True, color=INK, zorder=8)
    na.set_gid("north-arrow")
    ax.add_patch(na)
    ax.text(x1 - 0.06 * (x1 - x0), y1 - 0.45 * L, "N", ha="center", va="bottom", fontsize=9, fontweight="bold", zorder=8)
    # waste table
    wt = ctx["waste"]
    rows = [("Waste", "Area (ft²)", "Squares", "Bundles (3/sq)", "")]
    mark = []
    for i, r in enumerate(wt["rows"], start=1):
        note = "suggested" if r["suggested"] else ""
        if r.get("chosen"):
            note = (note + ", " if note else "") + "chosen"
        rows.append((f"{r['pct']} %", f"{r['area_sqft']:,.0f}", f"{r['squares']:.2f}", str(r["bundles"]), note))
        if r["suggested"]:
            mark.append(i)
    yw = min(y, 0.575) - 0.04
    fig.text(0.06, yw + 0.012, f"Waste table (suggested {wt['suggested_pct']} %: {wt['hips_valleys']} hips + valleys, "
             "report.py rule)", fontsize=9, fontweight="bold", color=INK, va="bottom")
    y = _table(fig, 0.06, yw - 0.006, rows, [0.0, 0.25, 0.39, 0.56, 0.60], fontsize=8.4, line=0.0185, mark_rows=mark,
               align="lrrrl", mark_width=0.70)
    # access flags
    ac = ctx["access"]
    fig.text(0.06, y - 0.012, f"Access ({ac['rule']})", fontsize=9, fontweight="bold", color=INK, va="top")
    sm = ac["summary"]
    lines = ["; ".join(f"{c.capitalize()}: {sm[c]['facets']} facet{'s' if sm[c]['facets'] != 1 else ''} "
                       f"({100 * sm[c]['share']:.0f} % of area)" for c in ("walkable", "steep", "very steep"))]
    if ac.get("highest_eave_ft") is not None:
        lines.append(f"Highest eave {ac['highest_eave_ft']:.1f} ft {ac['highest_eave_ref']}.")
    if ac.get("height_low_side_ft"):
        lines.append(f"Top of roof above grade: {ac['height_low_side_ft']:.1f} ft (low side), "
                     f"{ac['height_high_side_ft']:.1f} ft (high side).")
    fig.text(0.06, y - 0.034, "\n".join(lines), fontsize=8.2, color=INK, va="top", linespacing=1.55)
    y -= 0.034 + 0.0175 * len(lines) + 0.012
    rows = [("Facet", "Pitch", "Area (ft²)", "Access")]
    for r in sorted(ac["facets"], key=lambda r: r["id"])[:12]:
        rows.append((r["id"], fmt_pitch(r["pitch_x12"]), f"{r['area_sqft']:,.0f}", r["class"]))
    if len(ac["facets"]) > 12:
        rows.append((f"+ {len(ac['facets']) - 12} more", "", "", ""))
    _table(fig, 0.06, y, rows, [0.0, 0.16, 0.32, 0.36], fontsize=7.8, line=0.0145, align="lrrl", mark_width=0.46)
    _note(fig, 0.58, 0.575, ctx["lidar_line"], width=58, fontsize=8.2, color=INK)
    _note(fig, 0.58, 0.535, "Measured from the fitted 3-D model, not from photos. Accessory lengths are the edge "
          "totals they cover; add laps and local-code widths when ordering.", width=66, fontsize=7.4)
    return fig, []
