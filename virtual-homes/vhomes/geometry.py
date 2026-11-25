"""Spec -> exact house geometry (roof facets, walls, footprint), placed roof details and scale markers.

The roof is built with property-model-pipeline's exact parametric builder (``propmodel.roofgeom``). The answer key
does NOT reuse that builder's measurements: ``answer_key.compute`` re-derives everything from the 3-D facet
polygons returned here and only *compares* with the builder's own numbers (two independent derivations must agree).
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from shapely.geometry import Point, Polygon

_PMP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "property-model-pipeline")
if _PMP not in sys.path:
    sys.path.insert(0, _PMP)
from propmodel import roofgeom as rg  # noqa: E402

DETAIL_SIZES = {
    # base flashing footprint (m) and height above the roof plane (m)
    "box_vent": {"base": 0.46, "hood": 0.33, "height": 0.16},
    "pipe_boot": {"base": 0.30, "pipe_d": (0.05, 0.10), "height": (0.25, 0.45)},
}


def wing_rectangle(w: dict):
    """Wall rectangle corners of one wing, computed from its parameters (not from the roof builder)."""
    az = math.radians(w["azimuth"])
    u = np.array([math.sin(az), math.cos(az)])
    v = np.array([-u[1], u[0]])                   # left of u (roofgeom's +v side)
    c = np.array([w["cx"], w["cy"]])
    hl, hw = w["length"] / 2.0, w["width"] / 2.0
    return [list(c - u * hl - v * hw), list(c + u * hl - v * hw), list(c + u * hl + v * hw), list(c - u * hl + v * hw)]


def facet_frame(plane):
    """(eave direction, up-slope direction, upward normal) unit vectors of a roof plane z = a x + b y + c."""
    a, b = plane[0], plane[1]
    s = math.hypot(a, b)
    if s < 1e-9:
        e = np.array([1.0, 0.0, 0.0]); up = np.array([0.0, 1.0, 0.0])
    else:
        g = np.array([a, b]) / s
        e = np.array([-g[1], g[0], 0.0])
        up = np.array([g[0], g[1], s]); up /= np.linalg.norm(up)
    n = np.cross(e, up)
    if n[2] < 0:
        e = -e; n = -n
    return e, up, n


def _plane_z(plane, x, y):
    return plane[0] * x + plane[1] * y + plane[2]


def _place_points(rng, poly, n, min_sep, accept, existing, tries=4000):
    """Rejection-sample ``n`` plan points inside ``poly`` that pass ``accept`` and keep ``min_sep`` apart."""
    out = []
    if poly.is_empty or n <= 0:
        return out
    x0, y0, x1, y1 = poly.bounds
    for _ in range(tries):
        if len(out) >= n:
            break
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if not poly.contains(Point(p)) or not accept(p):
            continue
        if any(math.dist(p, q) < min_sep for q in existing + out):
            continue
        out.append(p)
    return out


def build_house(spec: dict) -> dict:
    rng = np.random.default_rng(spec["seed"] + 7919)          # detail placement stream, separate from the spec
    wings = [rg.Wing(**w) for w in spec["wings"]]
    model = rg.build(wings)
    mesh = rg.to_mesh_json(model)

    facets = []
    for f, fm in zip(model.facets, mesh["facets"]):
        e, up, n = facet_frame(f.plane)
        facets.append({
            "id": f.id, "wings": f.wings, "plane": list(f.plane), "hidden_from_above": bool(f.hidden_from_above),
            "rings": [{"outer": p["outer"], "holes": p["holes"]} for p in fm["polygons"]],
            "frame": {"eave": e.tolist(), "up": up.tolist(), "normal": n.tolist()},
        })
    walls = []
    for w in mesh["walls"]:
        prof = [list(p) for p in w["profile"]]
        if len(prof) < 2:
            continue
        a, b = prof[0], prof[-1]
        bottom = w.get("bottom") or [[a[0], a[1], w["base_z"]], [b[0], b[1], w["base_z"]]]
        walls.append({"id": f"{w['wing']}:{w['side']}", "bearing": w["bearing"],
                      "polygon": [list(bottom[0]), list(bottom[1])] + list(reversed(prof))})

    footprint = [wing_rectangle(w) for w in spec["wings"]]
    by_id = {f.id: f for f in model.facets}
    front_dir = None
    w0 = spec["wings"][0]
    az = math.radians(w0["azimuth"])
    v_dir = np.array([-math.cos(az), math.sin(az)])
    front_dir = v_dir if spec["front_side"] == "+v" else -v_dir   # plan direction from the house towards the street

    def facing_front(fid):
        e, up, n = facet_frame(by_id[fid].plane)
        return float(np.dot(n[:2], front_dir)) > 0.0

    # ---- roof details ------------------------------------------------------------------------------------------
    det = spec["details"]
    placed, taken = [], []
    visible = [f for f in model.facets if not f.hidden_from_above and f.slope > 0.05]
    back = [f for f in visible if not facing_front(f.id)] or visible

    def zmax(f):
        return max(_plane_z(f.plane, x, y) for p in rg._polys(f.poly) for x, y in p.exterior.coords)

    def add(kind, f, p, extra):
        e, up, n = facet_frame(f.plane)
        z = _plane_z(f.plane, *p)
        placed.append({"kind": kind, "facet": f.id, "center": [p[0], p[1], z], "normal": n.tolist(),
                       "eave_dir": e.tolist(), "up_dir": up.tolist(), **extra})
        taken.append(p)

    for i in range(det.get("box_vents", 0)):
        f = back[i % len(back)]
        s = f.slope
        top = zmax(f)
        inner = f.poly.buffer(-0.9)
        pts = _place_points(rng, inner, 1, 1.2,
                            lambda p: 0.5 <= (top - _plane_z(f.plane, *p)) * math.sqrt(1 + s * s) / max(s, 1e-6) <= 1.6,
                            taken)
        for p in pts:
            add("box_vent", f, p, {"base_m": DETAIL_SIZES["box_vent"]["base"], "hood_m": DETAIL_SIZES["box_vent"]["hood"],
                                   "height_m": DETAIL_SIZES["box_vent"]["height"]})
    for i in range(det.get("pipe_boots", 0)):
        f = back[int(rng.integers(len(back)))] if rng.random() < 0.75 else visible[int(rng.integers(len(visible)))]
        pts = _place_points(rng, f.poly.buffer(-0.8), 1, 0.9, lambda p: True, taken)
        for p in pts:
            d = float(rng.uniform(*DETAIL_SIZES["pipe_boot"]["pipe_d"]))
            h = float(rng.uniform(*DETAIL_SIZES["pipe_boot"]["height"]))
            add("pipe_boot", f, p, {"base_m": DETAIL_SIZES["pipe_boot"]["base"], "pipe_d_m": round(d, 3),
                                    "height_m": round(h, 3)})

    ridge_vents = []
    if det.get("ridge_vent"):
        cut = w0["rake_overhang"] + 0.15          # the vent stops 6 in short of each gable wall
        for ed in model.edges:
            if ed.kind != "ridge":
                continue
            p0, p1 = np.array(ed.p0), np.array(ed.p1)
            L = np.linalg.norm(p1 - p0)
            if L <= 2 * cut + 0.5:
                continue
            d = (p1 - p0) / L
            ridge_vents.append({"p0": (p0 + d * cut).tolist(), "p1": (p1 - d * cut).tolist(),
                                "length_m": float(L - 2 * cut), "width_m": 0.30, "height_m": 0.07})

    # ---- scale markers -----------------------------------------------------------------------------------------
    size = spec["scale_marker_m"]
    u_dir = np.array([math.sin(az), math.cos(az)])
    dist = w0["width"] / 2 + w0["eave_overhang"] + rng.uniform(1.5, 3.0)
    c = np.array([w0["cx"], w0["cy"]]) + front_dir * dist + u_dir * rng.uniform(-w0["length"] / 4, w0["length"] / 4)
    yaw = rng.uniform(0, 2 * math.pi)
    ex = np.array([math.cos(yaw), math.sin(yaw), 0.0]); ey = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    gz = 0.006                                   # board thickness: the printed face sits 6 mm above grade
    gc = np.array([c[0], c[1], gz])
    markers = [{"id": "ground", "size_m": size, "squares": 8, "center": gc.tolist(), "x_axis": ex.tolist(),
                "y_axis": ey.tolist(), "normal": [0.0, 0.0, 1.0]}]
    rf = min(visible, key=lambda f: (f.slope, f.id))
    inner = rf.poly.buffer(-(size * 0.75 + 0.6))
    pts = _place_points(rng, inner, 1, 1.0, lambda p: True, taken)
    if pts:
        e, up, n = facet_frame(rf.plane)
        yaw = rng.uniform(-math.pi, math.pi)
        ax = math.cos(yaw) * e + math.sin(yaw) * up
        ay = np.cross(n, ax)
        p = pts[0]
        cz = _plane_z(rf.plane, *p)
        center = np.array([p[0], p[1], cz]) + n * 0.006
        markers.append({"id": "roof", "facet": rf.id, "size_m": size, "squares": 8, "center": center.tolist(),
                        "x_axis": ax.tolist(), "y_axis": ay.tolist(), "normal": n.tolist()})
    for m in markers:
        cc, ax, ay = np.array(m["center"]), np.array(m["x_axis"]), np.array(m["y_axis"])
        h = m["size_m"] / 2
        m["corners"] = [(cc - ax * h - ay * h).tolist(), (cc + ax * h - ay * h).tolist(),
                        (cc + ax * h + ay * h).tolist(), (cc - ax * h + ay * h).tolist()]

    meas = model.measurements()
    return {
        "schema": "vhomes.house/1",
        "spec": spec,
        "facets": facets,
        "walls": walls,
        "footprint": footprint,
        "front_dir": front_dir.tolist(),
        "details": placed,
        "ridge_vents": ridge_vents,
        "markers": markers,
        "heights": {"plate_m": w0["eave_height"], "max_m": meas["building.height"]},
        "builder_measurements": {k: float(v) for k, v in meas.items()},
        "builder_edges": [{"kind": e.kind, "facets": list(e.facets), "p0": list(e.p0), "p1": list(e.p1),
                           "length_m": e.length} for e in model.edges],
    }
