"""Measured drip edges (and wall lines) from LiDAR, per exterior eave / rake of a fitted model.

Why: a fitted rectangle with an overhang PRIOR puts the drip edge where the prior says, not where the
roof ends. On one hillside job that left the roof area 8.6 % low. The LiDAR shows where each roof plane
ends: the outermost returns lying on the plane. This module turns that into numbers and observations.

Method, for every eave / rake edge of ``model.json`` that is on the outside of the roof (no higher roof
beyond it), in the edge frame s (along the edge) / v (outward normal, + = away from the facet):

* returns within ``plane_tol`` (vertical) of the facet plane, extended past the edge, are "on the plane"
  (canopy above the plane and the ground below never count);
* stations every ``step`` m with a ``strip`` m wide window along the edge (0.5 m kept clear of the
  corners); in each, the on-plane returns with v > a0 (a0 = ``band_in`` m inside, or less on a shallow
  facet) are a uniform sample of [a0, edge], so the edge estimate is a0 + (v_max - a0) (n + 1) / n
  (the unbiased endpoint of a uniform sample: the outermost return lies about one point spacing
  inside the drip edge, more on sparse data);
* a station counts only if returns are seen within ``gap_band`` m beyond its outermost roof return (ground,
  wall, gutter): an empty band there is missing data (occlusion), not the end of the roof; stations with
  canopy over the plane at the edge are skipped too;
* a robust line e(s) = e0 + e1 (s - L/2) through the station estimates gives the edge offset e0
  (+ = the LiDAR roof reaches beyond the model edge) and sigma from the station scatter;
* wall line (optional evidence): returns on a vertical face under the overhang (between grade + 0.5 m
  and 0.35 m under the drip) cluster at one v; their median is the wall position, and
  drip - wall is a measured overhang.

``drip_edges`` returns a dict (written to ``data/edges.json`` by ``pm.py edges``);
``edge_observations`` turns measured edges into ``outline`` segment observations (fusion.py) so the next
fit moves the drip edges there; ``overhang_parameters`` says which wing parameter sets each edge's
position (so walls follow from a measured overhang where the wall line is known, else from the prior).
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

EDGE_KINDS = ("eave", "rake")


def facet_polygon(f):
    return unary_union([Polygon(np.asarray(q["outer"])[:, :2], [np.asarray(h)[:, :2] for h in q.get("holes", [])])
                        for q in f["polygons"]]).buffer(0)


def _wing_by_id(model, wid):
    for w in model.get("wings", []):
        if w.get("id") == wid:
            return w
    return None


def edge_parameter(wing, mid_xy):
    """Wing parameter (e.g. ``M.eave_overhang_b``) that places the roof edge at ``mid_xy``, or None
    (measured ``outline`` wings, flat-roof decks: the edge is not an overhang parameter)."""
    if wing is None or wing.get("outline"):
        return None
    t = math.radians(float(wing.get("azimuth", 0.0)))
    u = np.array([math.sin(t), math.cos(t)])
    v = np.array([-u[1], u[0]])
    rel = np.asarray(mid_xy, float) - np.array([float(wing.get("cx", 0.0)), float(wing.get("cy", 0.0))])
    uu, vv = float(rel @ u), float(rel @ v)
    L, W = float(wing.get("length", 10.0)), float(wing.get("width", 8.0))
    typ = wing.get("type", "gable")
    wid = wing["id"]
    # which side: compare the distances to the u-ends and the v-sides of the wall rectangle
    du = abs(abs(uu) - L / 2)
    dv = abs(abs(vv) - W / 2)
    if du < dv:     # an end of the wing
        if typ in ("hip", "pyramid", "mansard", "flat"):
            return f"{wid}.eave_overhang"
        return f"{wid}.rake_overhang"
    if vv >= 0:
        return f"{wid}.eave_overhang"
    if typ == "shed":
        return f"{wid}.shed_high_overhang" if wing.get("shed_high_overhang") is not None else \
            (f"{wid}.eave_overhang_b" if wing.get("eave_overhang_b") is not None else f"{wid}.eave_overhang")
    return f"{wid}.eave_overhang_b" if wing.get("eave_overhang_b") is not None else f"{wid}.eave_overhang"


def _robust_line(s, e, iters=5, k=1.5):
    """Huber IRLS line e = c0 + c1 s; returns (c0, c1, robust residual scale)."""
    A = np.column_stack([np.ones(len(s)), s])
    w = np.ones(len(s))
    c = np.zeros(2)
    for _ in range(iters):
        c, *_ = np.linalg.lstsq(A * w[:, None], e * w, rcond=None)
        r = e - A @ c
        sc = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-3
        w = np.sqrt(np.where(np.abs(r) <= k * sc, 1.0, k * sc / np.maximum(np.abs(r), 1e-12)))
    r = e - A @ c
    return float(c[0]), float(c[1]), float(1.4826 * np.median(np.abs(r - np.median(r))))


def drip_edges(model, pts, min_len=1.0, step=0.5, strip=1.0, band_in=2.0, band_out=2.5, plane_tol=0.25,
               end_skip=0.5, min_points=4, min_stations=3, max_slope=0.12, sigma_floor=0.02,
               wall_faces=True, wall_min_points=8, gap_band=1.0):
    """Per-edge drip-edge (and wall-line) measurement. ``model``: model.json dict; ``pts``: (N, >= 3)
    returns as x, y, z in the model frame and datum (z above model z = 0). See the module docstring."""
    pts = np.asarray(pts, float)
    xy, z = pts[:, :2], pts[:, 2]
    facets = {f["id"]: f for f in model["facets"]}
    fpoly = {k: facet_polygon(f) for k, f in facets.items()}
    roof_all = unary_union(list(fpoly.values()))
    rows = []
    for ei, e in enumerate(model["edges"]):
        if e["kind"] not in EDGE_KINDS or e.get("length_m", 0.0) < min_len or not e.get("facets"):
            continue
        f = facets.get(e["facets"][0])
        if f is None:
            continue
        a, b = np.array(e["p0"][:2], float), np.array(e["p1"][:2], float)
        L = float(np.linalg.norm(b - a))
        if L < min_len:
            continue
        t = (b - a) / L
        nrm = np.array([t[1], -t[0]])
        mid = (a + b) / 2
        fp = fpoly[f["id"]]
        if fp.buffer(1e-6).contains(Point(*(mid + 0.2 * nrm))):
            nrm = -nrm
        pa, pb, pc = f["plane"]
        row = {"index": ei, "facet": f["id"], "kind": e["kind"], "wings": f.get("wings", []),
               "p0": [round(float(a[0]), 3), round(float(a[1]), 3)], "p1": [round(float(b[0]), 3), round(float(b[1]), 3)],
               "length_m": round(L, 3), "outward": [round(float(nrm[0]), 4), round(float(nrm[1]), 4)],
               "hidden_facet": bool(f.get("hidden_from_above"))}
        wing = _wing_by_id(model, (f.get("wings") or [None])[0])
        row["param"] = edge_parameter(wing, mid)
        # beyond the edge: another (higher) roof = an occluded / interior edge; a lower roof = still measurable
        probe = mid + 0.4 * nrm
        z_edge = pa * mid[0] + pb * mid[1] + pc
        beyond = [k for k, q in fpoly.items() if k != f["id"] and q.contains(Point(*probe))]
        higher = [k for k in beyond if (lambda P: P[0] * probe[0] + P[1] * probe[1] + P[2])(facets[k]["plane"]) > z_edge - 0.1]
        if f.get("hidden_from_above") or higher:
            row.update(status="occluded", note="roof beyond the edge (interior / under another roof)")
            rows.append(row)
            continue
        rel = xy - a
        s_, v_ = rel @ t, rel @ nrm
        near = (s_ > -0.5) & (s_ < L + 0.5) & (v_ > -band_in - 2.0) & (v_ < band_out)
        S, V, Z, X = s_[near], v_[near], z[near], xy[near]
        dz = Z - (pa * X[:, 0] + pb * X[:, 1] + pc)
        on = np.abs(dz) < plane_tol
        # usable depth of the facet behind the edge (a shallow facet ends before band_in)
        verts = np.asarray(fp.exterior.coords) if fp.geom_type == "Polygon" else \
            np.vstack([np.asarray(g.exterior.coords) for g in fp.geoms])
        depth = float(max(0.3, np.max(-(verts - a) @ nrm)))
        a0 = -min(band_in, max(0.3, depth - 0.2))
        stations, canopy, gaps = [], 0, 0
        for sk in np.arange(end_skip + strip / 2, L - end_skip - strip / 2 + 1e-9, step):
            m = on & (np.abs(S - sk) < strip / 2) & (V > a0)
            if m.sum() < min_points:
                continue
            over = (np.abs(S - sk) < strip / 2) & (V > -0.5) & (V < 1.0) & (dz > 0.3)
            if over.sum() >= max(3, 0.5 * m.sum()):
                canopy += 1
                continue
            vmax, n = float(V[m].max()), int(m.sum())
            # something must be seen just beyond the outermost roof return (ground, wall, gutter, canopy):
            # an empty band is missing data (occlusion, a dark roof), not the end of the roof
            beyond = (np.abs(S - sk) < strip / 2) & (V > vmax + 0.05) & (V < vmax + gap_band)
            if beyond.sum() < 2:
                gaps += 1
                continue
            stations.append((float(sk), a0 + (vmax - a0) * (n + 1) / n, vmax, n))
        row["stations"] = len(stations)
        row["canopy_stations"] = canopy
        row["gap_stations"] = gaps
        if len(stations) < min_stations:
            row.update(status="too_few_returns", note="trees, occlusion or a short edge: kept where the fit puts it")
            rows.append(row)
            continue
        st = np.array(stations)
        sc = st[:, 0] - L / 2
        c0, c1, scale = _robust_line(sc, st[:, 1])
        if abs(c1) > max_slope:           # a strongly rotated edge is a wrong wing layout: keep the mean offset
            c1 = 0.0
            c0 = float(np.median(st[:, 1]))
        k_eff = max(1.0, len(st) * step / strip)
        sig = max(sigma_floor, scale / math.sqrt(k_eff))
        e_a, e_b = c0 + c1 * (0 - L / 2), c0 + c1 * (L - L / 2)
        A_, B_ = a + nrm * e_a, b + nrm * e_b
        row.update(status="measured", offset_m=round(c0, 3), rotation_m_per_m=round(c1, 4), sigma_m=round(sig, 3),
                   p25_m=round(float(np.percentile(st[:, 1], 25)), 3), p75_m=round(float(np.percentile(st[:, 1], 75)), 3),
                   outermost_median_m=round(float(np.median(st[:, 2])), 3),
                   returns_per_station=round(float(np.median(st[:, 3])), 1),
                   drip_segment=[[round(float(A_[0]), 3), round(float(A_[1]), 3)], [round(float(B_[0]), 3), round(float(B_[1]), 3)]],
                   drip_z_m=round(float(z_edge), 3))
        if wall_faces:
            row.update(_wall_line(S, V, Z, L, end_skip, c0, z_edge, wall_min_points))
        rows.append(row)
    meas = [r for r in rows if r.get("status") == "measured"]
    w = np.array([r["length_m"] for r in meas]) if meas else np.zeros(0)
    summary = {"edges": len(rows), "measured": len(meas),
               "too_few_returns": sum(r.get("status") == "too_few_returns" for r in rows),
               "occluded": sum(r.get("status") == "occluded" for r in rows)}
    if meas:
        off = np.array([r["offset_m"] for r in meas])
        summary.update(mean_offset_m=round(float(np.average(off, weights=w)), 3),
                       max_abs_offset_m=round(float(np.max(np.abs(off))), 3))
    return {"edges": rows, "summary": summary,
            "method": "outermost on-plane returns per eave/rake (uniform-endpoint estimate per station, robust line)"}


def _wall_line(S, V, Z, L, end_skip, drip_off, z_edge, min_points):
    """Wall face under the overhang: returns between grade + 0.5 m and 0.35 m under the drip, inside the drip
    line, clustering at one v. Returns {wall_offset_m, wall_points, overhang_lidar_m} or {}."""
    outside = (V > drip_off + 0.5) & (V < drip_off + 3.0) & (S > 0) & (S < L)
    if outside.sum() < 5:
        return {}
    grade = float(np.percentile(Z[outside], 5))
    band = (S > end_skip) & (S < L - end_skip) & (V < drip_off - 0.05) & (V > drip_off - 3.0) & \
        (Z > grade + 0.5) & (Z < z_edge - 0.35)
    if band.sum() < min_points:
        return {"grade_z_m": round(grade, 3)}
    v = V[band]
    hist, edges_ = np.histogram(v, bins=np.arange(v.min() - 0.1, v.max() + 0.2, 0.1))
    k = int(np.argmax(hist))
    sel = np.abs(v - (edges_[k] + 0.05)) < 0.25
    if sel.sum() < min_points:
        return {"grade_z_m": round(grade, 3)}
    vw = float(np.median(v[sel]))
    mad = float(1.4826 * np.median(np.abs(v[sel] - vw)))
    if mad > 0.15:
        return {"grade_z_m": round(grade, 3)}
    return {"grade_z_m": round(grade, 3), "wall_offset_m": round(vw, 3), "wall_points": int(sel.sum()),
            "overhang_lidar_m": round(drip_off - vw, 3)}


def city_wall_overhangs(result, wall_polygon):
    """Measured overhang per edge against a WALL-LINE outline (a city footprint that traces the walls, already
    moved into the model frame): distance from the measured drip segment's midpoint to the wall line, + = the
    drip edge outside the walls. Adds ``overhang_city_m`` to each measured edge row."""
    P = Polygon(wall_polygon).buffer(0)
    B = P.boundary
    for r in result["edges"]:
        if r.get("status") != "measured":
            continue
        A_, B_ = np.array(r["drip_segment"], float)
        m = (A_ + B_) / 2
        d = B.distance(Point(*m))
        r["overhang_city_m"] = round(float(d if not P.contains(Point(*m)) else -d), 3)
    return result


def overhang_parameters(result, min_edges=1):
    """{param: {value, sigma, n_edges, from}} from edges with a measured overhang (LiDAR wall face first,
    then a wall-line city outline)."""
    acc = {}
    for r in result["edges"]:
        if r.get("status") != "measured" or not r.get("param"):
            continue
        val, src = None, None
        if r.get("overhang_lidar_m") is not None:
            val, src = r["overhang_lidar_m"], "LiDAR drip edge - LiDAR wall face"
        elif r.get("overhang_city_m") is not None:
            val, src = r["overhang_city_m"], "LiDAR drip edge - city wall-line outline"
        if val is None:
            continue
        acc.setdefault(r["param"], []).append((val, r["length_m"], r["sigma_m"], src))
    out = {}
    for p, vals in acc.items():
        if len(vals) < min_edges:
            continue
        v = np.array([x[0] for x in vals]); w = np.array([x[1] for x in vals])
        med = float(np.average(v, weights=w))
        spread = float(np.sqrt(np.average((v - med) ** 2, weights=w))) if len(v) > 1 else 0.0
        sig = max(0.05, spread, float(np.mean([x[2] for x in vals])))
        out[p] = {"value": round(med, 3), "sigma": round(sig, 3), "n_edges": len(vals),
                  "from": sorted({x[3] for x in vals})}
    return out


def edge_observations(result, sigma_floor=0.05, inflate=1.5, source="auto:edges"):
    """outline segment observations (fusion.py) for every measured edge. sigma = max(floor, inflate x the station
    scatter sigma): the scatter of a few stations under-states corner effects, gutters and scan-line spacing."""
    obs = []
    for r in result["edges"]:
        if r.get("status") != "measured":
            continue
        obs.append({"target": "outline", "which": "roof_outline", "segments": [r["drip_segment"]],
                    "sigma": round(max(sigma_floor, inflate * float(r["sigma_m"])), 3),
                    "source": f"{source} LiDAR drip {r['facet']} {r['kind']} e{r['index']}", "kind": "lidar_drip",
                    "offset_m": r["offset_m"], "stations": r["stations"]})
    return obs


def table(result):
    lines = [f"  {'facet':6s} {'kind':5s} {'len':>5s} {'param':<20s} {'st':>3s} {'offset':>7s} {'sigma':>6s} "
             f"{'wall':>6s} {'ovh':>5s} status"]
    for r in result["edges"]:
        ovh = r.get("overhang_lidar_m", r.get("overhang_city_m"))
        lines.append(f"  {r['facet']:6s} {r['kind']:5s} {r['length_m']:5.1f} {str(r.get('param')):<20s} {r.get('stations', 0):3d} "
                     f"{r.get('offset_m', float('nan')):+7.2f} {r.get('sigma_m', float('nan')):6.2f} "
                     f"{r.get('wall_offset_m', float('nan')):+6.2f} {ovh if ovh is not None else float('nan'):5.2f} {r['status']}")
    s = result["summary"]
    lines.append(f"  {s['measured']}/{s['edges']} edges measured" +
                 (f", length-weighted mean offset {s['mean_offset_m']:+.2f} m (+ = LiDAR roof beyond the model)"
                  if "mean_offset_m" in s else ""))
    return "\n".join(lines)


def segment_line(r):
    return LineString(r["drip_segment"]) if r.get("drip_segment") else None
