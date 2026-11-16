"""Tier B: independent pitch check from USGS 3DEP lidar (public EPT on AWS).

Pipeline: footprint bbox -> walk the EPT octree for that bbox only -> read LAZ
nodes (laspy + lazrs) -> reproject Web Mercator to EPSG 32164 -> local metres
-> keep points above ground inside each city roof plane -> RANSAC + least
squares plane per roof plane -> compare pitch with the city plane -> apply the
reconcile rule (agree / override / site check).

Optional dependencies, imported lazily: `pip install laspy lazrs` (BSD-2, MIT/Apache).
"""
import io
import json
import math
import os

import numpy as np

from . import proj
from .units import FT_US, LIDAR_COLLECTION

EPT_ROOT = "https://s3-us-west-2.amazonaws.com/usgs-lidar-public/%s" % LIDAR_COLLECTION
EPT_HOST = "s3-us-west-2.amazonaws.com"

# Reconcile thresholds from the plan (section 4). Experiment 027 tunes them.
MIN_POINTS = 40
AGREE_DEG = 1.5
OVERRIDE_DEG = 4.0
CLEAN_RMSE_M = 0.10
RANSAC_TOL_M = 0.10
MIN_HEIGHT_M = 2.0       # points lower than this above ground are not roof
EDGE_INSET_M = 0.30      # stay this far inside a plane's outline (lidar footprint + outline uncertainty)
MIN_INLIER_FRACTION = 0.5


class LidarUnavailable(RuntimeError):
    pass


def _need_laspy():
    try:
        import laspy  # noqa: F401
        import lazrs  # noqa: F401
    except ImportError:
        raise LidarUnavailable(
            "the lidar check needs two small packages: pip install laspy lazrs  "
            "(BSD-2-Clause and MIT/Apache-2.0). The city measurement works without them.")
    import laspy
    return laspy


def node_bounds(bounds, d, x, y, z):
    """Cube of EPT node d-x-y-z inside the dataset cube `bounds` (xmin, ymin, zmin, xmax, ymax, zmax)."""
    s = (bounds[3] - bounds[0]) / (2 ** d)
    return (bounds[0] + x * s, bounds[1] + y * s, bounds[2] + z * s,
            bounds[0] + (x + 1) * s, bounds[1] + (y + 1) * s, bounds[2] + (z + 1) * s)


def _overlaps_xy(nb, q):
    return nb[0] <= q[2] and nb[3] >= q[0] and nb[1] <= q[3] and nb[4] >= q[1]


def fetch_points(http, bbox_ft, cache_root, buffer_m=4.0, min_depth=6, log=None, max_nodes=80):
    """Lidar points over a city bbox (x0, y0, x1, y1 in EPSG 32164 feet).

    Returns dict(x_ft, y_ft, z_m, cls, nodes, srs). `min_depth` skips the coarsest octree
    levels: a node at depth d holds about one point per (2000 m / 2^d) cell, so levels
    below 6 add less than one point per house and cost megabytes each.
    """
    laspy = _need_laspy()
    log = log or (lambda m: None)
    http.host_interval.setdefault(EPT_HOST, 0.2)
    cdir = os.path.join(cache_root, "_ept", LIDAR_COLLECTION)
    meta = json.loads(http.get_bytes(EPT_ROOT + "/ept.json", os.path.join(cdir, "ept.json")))
    srs = (meta.get("srs") or {}).get("horizontal")
    if str(srs) != "3857":
        raise LidarUnavailable("EPT is in EPSG %s; this reader handles 3857 only" % srs)
    if meta.get("dataType") != "laszip":
        raise LidarUnavailable("EPT data type %r is not laszip" % meta.get("dataType"))
    b = meta["bounds"]
    x0, y0, x1, y1 = bbox_ft
    buf_ft = buffer_m / FT_US
    cx, cy = proj.city_to_webmerc(np.array([x0 - buf_ft, x1 + buf_ft, x0 - buf_ft, x1 + buf_ft]),
                                  np.array([y0 - buf_ft, y0 - buf_ft, y1 + buf_ft, y1 + buf_ft]))
    q = (float(cx.min()), float(cy.min()), float(cx.max()), float(cy.max()))

    hier = {}

    def load_hier(key):
        d = json.loads(http.get_bytes("%s/ept-hierarchy/%s.json" % (EPT_ROOT, key),
                                      os.path.join(cdir, "ept-hierarchy", key + ".json")))
        hier.update({k: v for k, v in d.items() if not (k in hier and hier[k] > 0)})

    load_hier("0-0-0-0")
    stack, chunks, nodes = [(0, 0, 0, 0)], [], []
    while stack:
        d, x, y, z = stack.pop()
        key = "%d-%d-%d-%d" % (d, x, y, z)
        if key not in hier:
            continue
        if hier[key] == -1:
            load_hier(key)
        if hier.get(key, 0) <= 0:
            continue
        if not _overlaps_xy(node_bounds(b, d, x, y, z), q):
            continue
        if d >= min_depth:
            if len(nodes) >= max_nodes:
                raise LidarUnavailable("more than %d lidar nodes for one house; bbox too large?" % max_nodes)
            raw = http.get_bytes("%s/ept-data/%s.laz" % (EPT_ROOT, key), os.path.join(cdir, "ept-data", key + ".laz"))
            las = laspy.read(io.BytesIO(raw))
            X, Y, Z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
            keep = (X >= q[0]) & (X <= q[2]) & (Y >= q[1]) & (Y <= q[3])
            nodes.append({"key": key, "points": int(len(X)), "kept": int(keep.sum()), "bytes": len(raw)})
            log("lidar node %s: %d points, %d over the house" % (key, len(X), int(keep.sum())))
            if keep.any():
                chunks.append((X[keep], Y[keep], Z[keep], np.asarray(las.classification)[keep]))
        for i in range(8):
            stack.append((d + 1, 2 * x + (i & 1), 2 * y + ((i >> 1) & 1), 2 * z + ((i >> 2) & 1)))
    if chunks:
        X, Y, Z, C = (np.concatenate([c[i] for c in chunks]) for i in range(4))
    else:
        X = Y = Z = np.zeros(0)
        C = np.zeros(0, dtype=np.uint8)
    ex, ny = proj.webmerc_to_city(X, Y)
    return {"x_ft": ex, "y_ft": ny, "z_m": Z, "cls": C.astype(np.uint8), "nodes": nodes, "srs": "EPSG:3857 -> 32164"}


def save_points(path, pts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, x_ft=pts["x_ft"], y_ft=pts["y_ft"], z_m=pts["z_m"], cls=pts["cls"],
                        nodes=json.dumps(pts.get("nodes", [])))


def load_points(path):
    d = np.load(path, allow_pickle=False)
    return {"x_ft": d["x_ft"], "y_ft": d["y_ft"], "z_m": d["z_m"], "cls": d["cls"], "nodes": json.loads(str(d["nodes"]))}


# --------------------------------------------------------------------------- plane fitting

def fit_plane(pts, tol=RANSAC_TOL_M, iters=300, seed=0):
    """Robust plane z = a x + b y + c through Nx3 points. Returns dict or None.

    RANSAC picks the plane with most points within `tol`, then least squares refits on those.
    """
    n = len(pts)
    if n < 3:
        return None
    rng = np.random.default_rng(seed)
    c0 = pts.mean(axis=0)
    p = pts - c0
    best = None
    for _ in range(iters):
        i = rng.choice(n, 3, replace=False)
        nrm = np.cross(p[i[1]] - p[i[0]], p[i[2]] - p[i[0]])
        ln = np.linalg.norm(nrm)
        if ln < 1e-9 or abs(nrm[2]) / ln < 0.1:
            continue
        nrm /= ln
        inl = np.abs((p - p[i[0]]) @ nrm) < tol
        k = int(inl.sum())
        if best is None or k > best[0]:
            best = (k, inl)
    if best is None or best[0] < 3:
        return None
    inl = best[1]
    for _ in range(2):  # refit and re-pick inliers
        A = np.column_stack([p[inl, 0], p[inl, 1], np.ones(int(inl.sum()))])
        coef, *_ = np.linalg.lstsq(A, p[inl, 2], rcond=None)
        res = p[:, 2] - (p[:, 0] * coef[0] + p[:, 1] * coef[1] + coef[2])
        nz = 1.0 / math.sqrt(1 + coef[0] ** 2 + coef[1] ** 2)
        new = np.abs(res * nz) < tol
        if new.sum() < 3:
            break
        inl = new
    A = np.column_stack([p[inl, 0], p[inl, 1], np.ones(int(inl.sum()))])
    coef, *_ = np.linalg.lstsq(A, p[inl, 2], rcond=None)
    res = (p[inl, 2] - A @ coef) * (1.0 / math.sqrt(1 + coef[0] ** 2 + coef[1] ** 2))
    a, b = float(coef[0]), float(coef[1])
    pitch = math.degrees(math.atan(math.hypot(a, b)))
    az = (math.degrees(math.atan2(-a, -b)) + 360) % 360 if pitch > 0.5 else None
    return {"a": a, "b": b, "c": float(coef[2] + c0[2] - a * c0[0] - b * c0[1]),
            "pitchDeg": pitch, "azimuthGridDeg": az, "inliers": int(inl.sum()), "points": n,
            "rmseM": float(math.sqrt(np.mean(res ** 2)))}


def _inside_with_inset(poly, x, y, inset):
    """Points inside polygon (Nx2) and at least `inset` from its outline."""
    a, b = poly, np.roll(poly, -1, axis=0)
    inside = np.zeros(len(x), dtype=bool)
    dmin = np.full(len(x), np.inf)
    for (ax, ay), (bx, by) in zip(a, b):
        if (ay > by) != (by > ay) or ay != by:
            cond = (ay > y) != (by > y)
            with np.errstate(divide="ignore", invalid="ignore"):
                xi = ax + (y - ay) * (bx - ax) / (by - ay)
            inside ^= cond & (x < xi)
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1e-12
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / L2, 0, 1)
        dmin = np.minimum(dmin, np.hypot(ax + t * dx - x, ay + t * dy - y))
    return inside & (dmin >= inset)


def reconcile(city_pitch_deg, fit, min_points=MIN_POINTS):
    """The plan's rule for one plane. Returns (status, action, note).

    status: agree | override | site_check | not_checked
    """
    if fit is None or fit["points"] < min_points:
        return "not_checked", "keep_city", "fewer than %d lidar points on this plane" % min_points
    if fit["inliers"] < min_points or fit["inliers"] < MIN_INLIER_FRACTION * fit["points"]:
        return "site_check", "keep_city", "lidar finds no clean plane here (trees, or the roof changed)"
    diff = abs(fit["pitchDeg"] - city_pitch_deg)
    if diff <= AGREE_DEG:
        return "agree", "keep_city", "city and lidar pitch agree within %.1f deg" % AGREE_DEG
    if diff <= OVERRIDE_DEG:
        if fit["rmseM"] <= CLEAN_RMSE_M:
            return "override", "use_lidar", "pitch differs %.1f deg; clean lidar fit overrides; review" % diff
        return "site_check", "keep_city", "pitch differs %.1f deg and the lidar fit is noisy" % diff
    return "site_check", "keep_city", "pitch differs %.1f deg: changed or wrong, site check required" % diff


def cross_check(model, pts, ground_z_m=None):
    """Compare every roof plane of `model` (planes.RoofModel) with lidar points.

    pts: dict from fetch_points. Returns the `checks.lidar` block and updates nothing;
    `apply_overrides` changes the model.
    """
    ox, oy, oz = model.origin_ft
    x = (pts["x_ft"] - ox) * FT_US
    y = (pts["y_ft"] - oy) * FT_US
    z = pts["z_m"] - oz * FT_US          # heights are NAVD88 in both sources (feet vs metres)
    if ground_z_m is None:
        ground_z_m = 0.0
    out = {"source": "USGS 3DEP %s (EPT)" % LIDAR_COLLECTION, "pointsFetched": int(len(x)),
           "thresholds": {"minPoints": MIN_POINTS, "agreeDeg": AGREE_DEG, "overrideDeg": OVERRIDE_DEG,
                          "cleanRmseM": CLEAN_RMSE_M, "ransacTolM": RANSAC_TOL_M, "edgeInsetM": EDGE_INSET_M},
           "planes": []}
    high = z > ground_z_m + MIN_HEIGHT_M
    rows, dz_rows = [], []
    for P in model.planes:
        poly = np.array(P["polygon"])[:, :2] if P["polygon"] else np.zeros((0, 2))
        rec = {"plane": P["id"], "cityPitchDeg": round(P["pitchDeg"], 2)}
        fit = None
        if len(poly) >= 3:
            sel = _inside_with_inset(poly, x, y, EDGE_INSET_M) & high
            for hole in P["holes"]:
                sel &= ~_inside_with_inset(np.array(hole)[:, :2], x, y, 0.0)
            if sel.sum() >= 3:
                fit = fit_plane(np.column_stack([x[sel], y[sel], z[sel]]))
            rec["points"] = int(sel.sum())
        status, action, note = reconcile(P["pitchDeg"], fit)
        if fit:
            n = P["normal"]
            c = P["centroid"]
            z_lidar = fit["a"] * c[0] + fit["b"] * c[1] + fit["c"]
            rec.update({"inliers": fit["inliers"], "rmseM": round(fit["rmseM"], 3),
                        "lidarPitchDeg": round(fit["pitchDeg"], 2),
                        "lidarPitchIn12": round(12 * math.tan(math.radians(fit["pitchDeg"])), 2),
                        "pitchDiffDeg": round(fit["pitchDeg"] - P["pitchDeg"], 2),
                        "lidarAzimuthGridDeg": None if fit["azimuthGridDeg"] is None else round(fit["azimuthGridDeg"], 1),
                        "heightDiffM": round(float(z_lidar - c[2]), 3)})
            if status in ("agree", "override") and 8.0 <= P["pitchDeg"] <= 70.0:
                # city plane as z = a x + b y + c; used to estimate the shift between the two datasets
                dz_rows.append((-n[0] / n[2], -n[1] / n[2], float(z_lidar - c[2]), fit["inliers"]))
        rec.update({"status": status, "action": action, "note": note})
        out["planes"].append(rec)
        rows.append(rec)
    out["registration"] = _registration(dz_rows)
    checked = [r for r in rows if r["status"] != "not_checked"]
    area = {P["id"]: P["areaM2"] for P in model.planes}
    tot = sum(area.values()) or 1.0
    out["summary"] = {
        "planesChecked": len(checked), "planes": len(rows),
        "areaCheckedPct": round(100 * sum(area[r["plane"]] for r in checked) / tot, 1),
        "agree": sum(r["status"] == "agree" for r in rows),
        "override": sum(r["status"] == "override" for r in rows),
        "siteCheck": sum(r["status"] == "site_check" for r in rows),
        "notChecked": sum(r["status"] == "not_checked" for r in rows),
        "meanAbsPitchDiffDeg": round(float(np.mean([abs(r["pitchDiffDeg"]) for r in checked if "pitchDiffDeg" in r])), 2)
        if any("pitchDiffDeg" in r for r in checked) else None,
    }
    # coverage: share of above-ground points over the footprint bbox that fall on some roof plane (no inset)
    on_roof = np.zeros(len(x), dtype=bool)
    for P in model.planes:
        if P["polygon"]:
            on_roof |= _inside_with_inset(np.array(P["polygon"])[:, :2], x, y, 0.0)
    out["pointsAboveGround"] = int(high.sum())
    out["pointsOnRoofOutline"] = int((on_roof & high).sum())
    return out


def _registration(rows):
    """Shift between city solid and lidar, from the height differences of planes facing different ways.

    A horizontal shift (dx, dy) of the roof shows up as a height difference a*dx + b*dy on a plane with
    slopes (a, b), so three or more planes with different aspects give dx, dy and a vertical offset.
    """
    if len(rows) < 3:
        return None
    A = np.array([[-r[0], -r[1], 1.0] for r in rows])
    d = np.array([r[2] for r in rows])
    w = np.sqrt(np.array([r[3] for r in rows], float))
    sv = np.linalg.svd((A[:, :2] - np.average(A[:, :2], axis=0, weights=w ** 2)) * w[:, None], compute_uv=False)
    if len(sv) < 2 or sv[1] < 0.3 * sv[0]:   # e.g. a plain gable: its two planes only see a shift across the ridge
        return {"verticalM": round(float(np.average(d, weights=w ** 2)), 3), "note": "planes face too few directions for a horizontal estimate"}
    sol, *_ = np.linalg.lstsq(A * w[:, None], d * w, rcond=None)
    res = d - A @ sol
    if math.hypot(sol[0], sol[1]) > 3.0:   # not believable for two surveyed datasets: the fit is unstable
        return {"verticalM": round(float(np.average(d, weights=w ** 2)), 3), "note": "horizontal estimate unstable; ignored"}
    return {"eastM": round(float(sol[0]), 3), "northM": round(float(sol[1]), 3), "verticalM": round(float(sol[2]), 3),
            "residualRmsM": round(float(np.sqrt(np.mean(res ** 2))), 3), "planesUsed": len(rows),
            "note": "lidar position minus city-solid position (positive = lidar roof is further east / north / higher)"}


def apply_overrides(model, check):
    """Re-tilt planes whose reconcile action is `use_lidar`: pitch from lidar, sloped area from plan area."""
    changed = []
    for r in check["planes"]:
        if r.get("action") != "use_lidar":
            continue
        P = model.planes[r["plane"]]
        P["cityPitchDeg"] = P["pitchDeg"]
        P["cityAreaM2"] = P["areaM2"]
        P["pitchDeg"] = r["lidarPitchDeg"]
        P["pitchIn12"] = 12 * math.tan(math.radians(P["pitchDeg"]))
        P["areaM2"] = P["planAreaM2"] / math.cos(math.radians(P["pitchDeg"]))
        P["pitchSource"] = "lidar"
        changed.append(P["id"])
    return changed
