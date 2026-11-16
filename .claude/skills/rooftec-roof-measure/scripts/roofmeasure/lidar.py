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

# Reconcile thresholds. The plan (section 4) proposed the first three; review round 1 added the
# "precise fit" test and the rule that a precise lidar pitch is used even when the city agrees
# (see references/accuracy.md for the evidence). Experiment 027 tunes them against ground truth.
MIN_POINTS = 40
AGREE_DEG = 1.5
OVERRIDE_DEG = 4.0
RANSAC_TOL_M = 0.10
MIN_HEIGHT_M = 2.0       # points lower than this above ground are not roof
EDGE_INSET_M = 0.60      # stay this far inside a plane's outline: the laser spot is about 0.5 m wide,
                         # so returns nearer a ridge, valley or eave mix two surfaces
EDGE_INSET_SMALL_M = 0.30  # used when the wide inset leaves fewer than INSET_KEEP_POINTS points
INSET_KEEP_POINTS = 80
MIN_INLIER_FRACTION = 0.5       # below this lidar sees no single plane here
PRECISE_INLIER_FRACTION = 0.8   # a "precise" fit: at least this share of the points on the plane ...
PRECISE_SE_DEG = 0.25           # ... and a pitch standard error no larger than this
PREFER_LIDAR = True      # use a precise lidar pitch even when the city pitch agrees with it
OFF_SURFACE_M = 0.30     # a lidar point this far above or below the fitted plane is not on the roof surface ...
OFF_SURFACE_SHARE = 0.10  # ... and this share of such points on one plane is worth a look (tree, dormer, lower roof)
GROUND_SHARE = 0.25      # this share of ground-level points inside a plane: no roof was there when lidar flew
TREE_MULTI_SHARE = 0.8   # points above a plane are a tree when this share of them come from pulses with several returns,
SOLID_MULTI_SHARE = 0.3  # and a solid surface (dormer, raised roof) when no more than this share do (review round 3)
SIBLING_DEG = 0.5        # a fit that fails "precise" only on its inlier share is trusted when a precise plane of the
SIBLING_MIN_AREA_M2 = 20.0   # same house (this size or larger) has the same pitch within SIBLING_DEG
AZIMUTH_DEG = 8.0        # a plane that faces this far from where lidar sees it is drawn wrong in the city model
AZIMUTH_MIN_PITCH_DEG = 9.5   # ... checked from 2/12 up; the compass direction of a flatter plane is not well defined


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
                chunks.append((X[keep], Y[keep], Z[keep], np.asarray(las.classification)[keep],
                               np.asarray(las.number_of_returns)[keep]))
        for i in range(8):
            stack.append((d + 1, 2 * x + (i & 1), 2 * y + ((i >> 1) & 1), 2 * z + ((i >> 2) & 1)))
    if chunks:
        X, Y, Z, C, NR = (np.concatenate([c[i] for c in chunks]) for i in range(5))
    else:
        X = Y = Z = np.zeros(0)
        C = NR = np.zeros(0, dtype=np.uint8)
    ex, ny = proj.webmerc_to_city(X, Y)
    # nr = how many returns the pulse of each point gave: 1 on a solid surface, 2 or more through branches
    return {"x_ft": ex, "y_ft": ny, "z_m": Z, "cls": C.astype(np.uint8), "nr": NR.astype(np.uint8), "nodes": nodes,
            "srs": "EPSG:3857 -> 32164"}


def save_points(path, pts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    extra = {"nr": pts["nr"]} if pts.get("nr") is not None else {}
    np.savez_compressed(path, x_ft=pts["x_ft"], y_ft=pts["y_ft"], z_m=pts["z_m"], cls=pts["cls"],
                        nodes=json.dumps(pts.get("nodes", [])), **extra)


def load_points(path):
    d = np.load(path, allow_pickle=False)
    # files cached before review round 3 hold no return counts; the tree-or-dormer test is then skipped
    return {"x_ft": d["x_ft"], "y_ft": d["y_ft"], "z_m": d["z_m"], "cls": d["cls"], "nodes": json.loads(str(d["nodes"])),
            "nr": d["nr"] if "nr" in d.files else None}


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
    # standard error of the pitch from the least-squares covariance (points treated as independent,
    # so it is a lower bound; it grows quickly when the points span little of the slope)
    k = int(inl.sum())
    se = float("inf")
    if k > 3:
        zres = p[inl, 2] - A @ coef
        cov = float(zres @ zres) / (k - 3) * np.linalg.pinv(A.T @ A)[:2, :2]
        g = np.array([a, b]) / math.hypot(a, b) if math.hypot(a, b) > 1e-9 else None
        var = float(g @ cov @ g) if g is not None else float(np.linalg.eigvalsh(cov).max())
        se = math.degrees(math.sqrt(max(var, 0.0)) * math.cos(math.radians(pitch)) ** 2)
    az = (math.degrees(math.atan2(-a, -b)) + 360) % 360 if pitch > 0.5 else None
    return {"a": a, "b": b, "c": float(coef[2] + c0[2] - a * c0[0] - b * c0[1]),
            "pitchDeg": pitch, "azimuthGridDeg": az, "inliers": int(inl.sum()), "points": n,
            "rmseM": float(math.sqrt(np.mean(res ** 2))), "seDeg": se}


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


def _surface_shares(x, y, z, sel, low, fit, nr=None):
    """What lidar sees inside a plane besides the roof surface: shares of points above it, below it and at ground level.

    The plane fit ignores these points, so a plane can "agree" while a tree hangs over it, a dormer the
    city model does not show sits on it, or half of it was not built yet. `sel` are the points used for
    the fit, `low` the points inside the same outline that are too low to be roof.
    """
    n_all = int(sel.sum() + low.sum())
    if n_all < MIN_POINTS:
        return None
    out = {"groundShare": round(float(low.sum()) / n_all, 3)}
    if fit and sel.sum():
        res = (z[sel] - (fit["a"] * x[sel] + fit["b"] * y[sel] + fit["c"])) / math.sqrt(1 + fit["a"] ** 2 + fit["b"] ** 2)
        above = res > OFF_SURFACE_M
        out["aboveShare"] = round(float(above.mean()), 3)
        out["belowShare"] = round(float((res < -OFF_SURFACE_M).mean()), 3)
        if nr is not None and above.any():
            # a pulse through branches gives several returns, a pulse on a dormer gives one
            out["aboveMultiShare"] = round(float((nr[sel][above] > 1).mean()), 3)
    return out


def surface_kind(surface):
    """What the shares from `_surface_shares` say: (kind, one short reason), or (None, None) when the plane is clean.

    kind: ground | tree | solid-above | above | below. Only `tree` leaves the roof itself in no doubt.
    """
    if not surface:
        return None, None
    if surface["groundShare"] >= GROUND_SHARE:
        return "ground", "%.0f%% of the lidar points are at ground level (built after the lidar flight, or a deck or porch under 2 m)" % (100 * surface["groundShare"])
    if surface.get("aboveShare", 0) >= OFF_SURFACE_SHARE:
        pct, multi = 100 * surface["aboveShare"], surface.get("aboveMultiShare")
        if multi is not None and multi >= TREE_MULTI_SHARE:
            return "tree", "%.0f%% of the lidar points are in a tree above the roof" % pct
        if multi is not None and multi <= SOLID_MULTI_SHARE:
            return "solid-above", "%.0f%% of the lidar points are on a solid surface above this plane (a dormer or raised roof part the model does not show)" % pct
        return "above", "%.0f%% of the lidar points are above the roof surface (a tree over the roof, or a dormer the model does not show)" % pct
    if surface.get("belowShare", 0) >= OFF_SURFACE_SHARE:
        return "below", "%.0f%% of the lidar points are below the roof surface (a lower roof part, a step or an opening the model does not show)" % (100 * surface["belowShare"])
    return None, None


def surface_note(surface):
    """One short reason when the shares from `_surface_shares` are worth a look, else None."""
    return surface_kind(surface)[1]


def _azimuth_diff(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def is_precise(fit):
    """True when a lidar fit is good enough to supply the pitch: most points on one plane, small standard error.

    Version 1 tested the inlier RMSE against 0.10 m. Inliers are within 0.10 m by construction, so that
    test could never fail and a half-covered plane could override the city pitch.
    """
    return (fit["inliers"] >= PRECISE_INLIER_FRACTION * fit["points"]
            and fit.get("seDeg", float("inf")) <= PRECISE_SE_DEG)


def reconcile(city_pitch_deg, fit, min_points=MIN_POINTS):
    """The reconcile rule for one plane. Returns (status, action, note).

    status: agree | override | site_check | not_checked;  action: keep_city | use_lidar
    """
    if fit is None or fit["points"] < min_points:
        return "not_checked", "keep_city", "fewer than %d lidar points on this plane" % min_points
    if fit["inliers"] < MIN_INLIER_FRACTION * fit["points"]:
        return "site_check", "keep_city", "lidar finds no clean plane here (trees, or the roof changed)"
    if fit["inliers"] < min_points:
        return "not_checked", "keep_city", "fewer than %d lidar points lie on this plane" % min_points
    diff = abs(fit["pitchDeg"] - city_pitch_deg)
    precise = is_precise(fit)
    if not precise and math.isfinite(fit.get("seDeg", float("inf"))):
        # an imprecise fit cannot tell a small difference from none: allow it twice its own standard error
        diff = max(0.0, diff - 2.0 * fit["seDeg"])
    if diff <= AGREE_DEG:
        if precise and PREFER_LIDAR:
            return "agree", "use_lidar", "city and lidar agree within %.1f deg; the precise lidar pitch is used" % AGREE_DEG
        return "agree", "keep_city", "city and lidar pitch agree within %.1f deg" % AGREE_DEG
    if diff <= OVERRIDE_DEG:
        if precise:
            return "override", "use_lidar", "pitch differs %.1f deg; precise lidar fit overrides; review" % diff
        return "site_check", "keep_city", "pitch differs %.1f deg and the lidar fit is not precise enough to override" % diff
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
                          "ransacTolM": RANSAC_TOL_M, "edgeInsetM": EDGE_INSET_M, "edgeInsetSmallM": EDGE_INSET_SMALL_M,
                          "preciseInlierFraction": PRECISE_INLIER_FRACTION, "preciseSeDeg": PRECISE_SE_DEG,
                          "preferLidar": PREFER_LIDAR, "offSurfaceM": OFF_SURFACE_M,
                          "offSurfaceShare": OFF_SURFACE_SHARE, "groundShare": GROUND_SHARE,
                          "treeMultiShare": TREE_MULTI_SHARE, "solidMultiShare": SOLID_MULTI_SHARE,
                          "siblingDeg": SIBLING_DEG, "azimuthDeg": AZIMUTH_DEG},
           "planes": []}
    high = z > ground_z_m + MIN_HEIGHT_M
    nr = pts.get("nr")
    if nr is not None and len(nr) != len(x):
        nr = None
    out["returnCounts"] = nr is not None
    rows, dz_rows = [], []
    for P in model.planes:
        poly = np.array(P["polygon"])[:, :2] if P["polygon"] else np.zeros((0, 2))
        rec = {"plane": P["id"], "cityPitchDeg": round(P["pitchDeg"], 2)}
        fit = None
        if len(poly) >= 3:
            holes = np.zeros(len(x), dtype=bool)
            for hole in P["holes"]:
                holes |= _inside_with_inset(np.array(hole)[:, :2], x, y, 0.0)
            for inset in (EDGE_INSET_M, EDGE_INSET_SMALL_M):
                sel = _inside_with_inset(poly, x, y, inset) & high & ~holes
                if sel.sum() >= INSET_KEEP_POINTS:
                    break
            rec["insetM"] = inset
            if sel.sum() >= 3:
                fit = fit_plane(np.column_stack([x[sel], y[sel], z[sel]]))
            rec["points"] = int(sel.sum())
            rec["surface"] = _surface_shares(x, y, z, sel, _inside_with_inset(poly, x, y, inset) & ~high & ~holes, fit, nr)
        status, action, note = reconcile(P["pitchDeg"], fit)
        if fit:
            n = P["normal"]
            c = P["centroid"]
            z_lidar = fit["a"] * c[0] + fit["b"] * c[1] + fit["c"]
            rec.update({"inliers": fit["inliers"], "rmseM": round(fit["rmseM"], 3),
                        "pitchSeDeg": round(fit["seDeg"], 3) if math.isfinite(fit["seDeg"]) else None,
                        "precise": is_precise(fit),
                        "lidarPitchDeg": round(fit["pitchDeg"], 2),
                        "lidarPitchIn12": round(12 * math.tan(math.radians(fit["pitchDeg"])), 2),
                        "pitchDiffDeg": round(fit["pitchDeg"] - P["pitchDeg"], 2),
                        "lidarAzimuthGridDeg": None if fit["azimuthGridDeg"] is None else round(fit["azimuthGridDeg"], 1),
                        "heightDiffM": round(float(z_lidar - c[2]), 3)})
            if (fit["azimuthGridDeg"] is not None and P.get("azimuthGridDeg") is not None
                    and min(P["pitchDeg"], fit["pitchDeg"]) >= AZIMUTH_MIN_PITCH_DEG):
                rec["azimuthDiffDeg"] = round(_azimuth_diff(fit["azimuthGridDeg"], P["azimuthGridDeg"]), 1)
            if status in ("agree", "override") and 8.0 <= P["pitchDeg"] <= 70.0:
                # city plane as z = a x + b y + c; used to estimate the shift between the two datasets
                dz_rows.append((-n[0] / n[2], -n[1] / n[2], float(z_lidar - c[2]), fit["inliers"]))
        rec.update({"status": status, "action": action, "note": note})
        kind, why = surface_kind(rec.get("surface"))
        if kind:
            rec["surfaceKind"], rec["surfaceNote"] = kind, why
        out["planes"].append(rec)
        rows.append(rec)
    _confirm_by_sibling(rows, {P["id"]: P["areaM2"] for P in model.planes})
    out["registration"] = _registration(dz_rows)
    checked = [r for r in rows if r["status"] != "not_checked"]
    area = {P["id"]: P["areaM2"] for P in model.planes}
    tot = sum(area.values()) or 1.0
    out["summary"] = {
        "planesChecked": len(checked), "planes": len(rows),
        "areaCheckedPct": round(100 * sum(area[r["plane"]] for r in checked) / tot, 1),
        "agree": sum(r["status"] == "agree" for r in rows),
        "override": sum(r["status"] == "override" for r in rows),
        "pitchFromLidar": sum(r["action"] == "use_lidar" for r in rows),
        "siteCheck": sum(r["status"] == "site_check" for r in rows),
        "notChecked": sum(r["status"] == "not_checked" for r in rows),
        "surfaceNotes": sum("surfaceNote" in r for r in rows),
        "confirmedBySibling": sum(bool(r.get("siblingPlane") is not None) for r in rows),
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


def _confirm_by_sibling(rows, area_m2):
    """Trust a fit that failed the "precise" test only on its inlier share when another plane confirms its pitch.

    The 80% inlier rule guards against a fit pulled off the roof by a tree or a second surface. A fit with
    a small standard error whose pitch equals the precise pitch of another main plane of the same house
    within SIBLING_DEG was not pulled anywhere: houses are framed at one or two pitches. Review round 3:
    4 of 4 such planes on 38 houses moved to a whole-number pitch (city 0.29 in 12 away, lidar 0.09).
    Only planes that already agree with the city within the limit are touched. "Within the limit" allows an
    imprecise fit twice its standard error, so the lidar pitch can be up to 2 degrees from the city pitch.
    Review round 4: from AGREE_DEG on, the plane is reported as an override, the same as a precise fit that
    far from the city would be (2 of 11 such planes on 64 houses; one went from 16.3 to 18.1 degrees with no word).
    """
    sibs = [r for r in rows if r.get("precise") and r["status"] in ("agree", "override")
            and area_m2.get(r["plane"], 0) >= SIBLING_MIN_AREA_M2]
    for r in rows:
        if r["status"] != "agree" or r["action"] != "keep_city" or r.get("precise") is not False:
            continue
        if r.get("pitchSeDeg") is None or r["pitchSeDeg"] > PRECISE_SE_DEG:
            continue
        near = [s for s in sibs if s["plane"] != r["plane"] and abs(s["lidarPitchDeg"] - r["lidarPitchDeg"]) <= SIBLING_DEG]
        if near and PREFER_LIDAR:
            s = min(near, key=lambda q: abs(q["lidarPitchDeg"] - r["lidarPitchDeg"]))
            r["action"], r["siblingPlane"] = "use_lidar", s["plane"]
            if abs(r["pitchDiffDeg"]) > AGREE_DEG:
                r["status"] = "override"
                r["note"] = ("pitch differs %.1f deg; the lidar pitch is used because plane %d has the same pitch within "
                             "%.1f deg; review" % (abs(r["pitchDiffDeg"]), s["plane"], SIBLING_DEG))
            else:
                r["note"] = ("city and lidar agree within %.1f deg; the lidar pitch is used because plane %d has the same "
                             "pitch within %.1f deg" % (AGREE_DEG, s["plane"], SIBLING_DEG))


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
    """Give every plane whose reconcile action is `use_lidar` the lidar pitch, and rebuild the geometry.

    The plane keeps its compass direction and its outline; `planes.retilt` solves the corners again, so
    roof.json, the GLB and the report keep describing one and the same roof. Returns the plane ids changed.
    """
    from . import planes as _planes
    want = {r["plane"]: r["lidarPitchDeg"] for r in check["planes"] if r.get("action") == "use_lidar"}
    if not want:
        return []
    before = {P["id"]: (P["pitchDeg"], P["areaM2"]) for P in model.planes}
    changed = _planes.retilt(model, want)
    for pid in changed:
        P = model.planes[pid]
        P["cityPitchDeg"], P["cityAreaM2"] = before[pid]
        P["lidarPitchDeg"] = want[pid]
        P["pitchSource"] = "lidar"
    return changed
