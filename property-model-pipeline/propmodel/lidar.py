"""LiDAR roof analysis: local conversion, ground, roof points, plane segmentation.

Typical 3DEP quality levels (USGS Lidar Base Specification):
  QL2: >= 2 pts/m^2, vertical RMSEz <= 10 cm     QL1: >= 8 pts/m^2, RMSEz <= 10 cm
  QL0: >= 8 pts/m^2, RMSEz <=  5 cm
A plane fitted to n roof points has pitch uncertainty ~ sigma_z / (extent * sqrt(n/12)),
i.e. a 50 m^2 facet with 100 points pins the pitch to ~0.1/12. LiDAR is usually the single
most accurate remote source for pitch and heights; horizontal edges are limited by point
spacing (edge uncertainty ~ spacing/2), which is why the outline is fused with imagery and
photo measurements instead of being used alone.
"""
from __future__ import annotations

import math
import numpy as np
from shapely.geometry import MultiPoint, Point, Polygon
import shapely

from .geo import mercator_to_lonlat

NON_SURFACE = {2, 3, 4, 5, 7, 9, 18}   # ground, low/medium/high vegetation, low noise, water, high noise


def to_local(pts3857, frame):
    """EPT rows [x3857, y3857, z, cls, ret, nret] -> [e, n, z_abs, cls, ret, nret] (metres)."""
    lon, lat = mercator_to_lonlat(pts3857[:, 0], pts3857[:, 1])
    e, n, _ = frame.from_geodetic(lat, lon, np.full(len(lat), frame.h0))
    out = pts3857.copy()
    out[:, 0], out[:, 1] = e, n
    return out


def fit_ground(local, radius=35.0):
    """Robust ground plane from class-2 points near the origin; returns (a, b, c) with z = ax+by+c."""
    g = local[(local[:, 3] == 2) & (np.hypot(local[:, 0], local[:, 1]) < radius)]
    if len(g) < 10:
        z0 = float(np.percentile(local[:, 2], 2))
        return (0.0, 0.0, z0), 0
    A = np.column_stack([g[:, 0], g[:, 1], np.ones(len(g))])
    w = np.ones(len(g))
    coef = np.zeros(3)
    for _ in range(5):
        coef, *_ = np.linalg.lstsq(A * w[:, None], g[:, 2] * w, rcond=None)
        r = g[:, 2] - A @ coef
        s = 1.4826 * np.median(np.abs(r)) + 1e-3
        w = 1.0 / np.maximum(1.0, np.abs(r) / (2 * s))
    return tuple(float(c) for c in coef), len(g)


def density(local, area_poly=None):
    if area_poly is None:
        x0, y0, x1, y1 = local[:, 0].min(), local[:, 1].min(), local[:, 0].max(), local[:, 1].max()
        a = (x1 - x0) * (y1 - y0)
    else:
        a = area_poly.area
    d = len(local) / max(a, 1e-6)
    return d, 1.0 / math.sqrt(max(d, 1e-9))


def building_points(local, ground, footprint=None, min_hag=1.8, seed_xy=(0.0, 0.0), cell=0.6, single_returns=True):
    """Non-ground points above min_hag belonging to the building — trees kept out.

    Vegetation classes (3-5) are dropped, and with ``single_returns`` every *non-last*
    return of a multi-return pulse is dropped too: those are canopy hits (or pulses split
    on a roof edge), while a roof under bare branches still gives a last return. Many
    3DEP projects leave trees as class 1, so the return test is the one that matters.
    With a footprint polygon (local metres) the points inside it (buffered 1.2 m for
    overhangs) are taken; otherwise the 8-connected raster blob nearest ``seed_xy``.
    Returns rows [x, y, z_abs, cls, ret, nret, hag].
    """
    a, b, c = ground
    hag = local[:, 2] - (a * local[:, 0] + b * local[:, 1] + c)
    m = (~np.isin(local[:, 3], list(NON_SURFACE))) & (hag > min_hag)
    if single_returns and local.shape[1] >= 6:
        m &= ~((local[:, 5] > 1) & (local[:, 4] < local[:, 5]))
    pts = np.column_stack([local[m], hag[m]])
    if len(pts) == 0:
        return pts
    if footprint is not None:
        poly = footprint.buffer(1.2)
        inside = shapely.contains_xy(poly, pts[:, 0], pts[:, 1])
        return pts[inside]
    # raster connected component around the seed
    ix = np.floor((pts[:, 0] - pts[:, 0].min()) / cell).astype(int)
    iy = np.floor((pts[:, 1] - pts[:, 1].min()) / cell).astype(int)
    occ = {}
    for k, (i, j) in enumerate(zip(ix, iy)):
        occ.setdefault((i, j), []).append(k)
    d = np.hypot(pts[:, 0] - seed_xy[0], pts[:, 1] - seed_xy[1])
    start = (ix[np.argmin(d)], iy[np.argmin(d)])
    seen, stack = {start}, [start]
    while stack:
        i, j = stack.pop()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                nb = (i + di, j + dj)
                if nb in occ and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
    idx = [k for cellk in seen for k in occ[cellk]]
    return pts[np.array(idx, int)]


def _fit_plane(p):
    """Least-squares z = ax + by + c; returns coef, rms, slope_sigma."""
    A = np.column_stack([p[:, 0], p[:, 1], np.ones(len(p))])
    coef, *_ = np.linalg.lstsq(A, p[:, 2], rcond=None)
    r = p[:, 2] - A @ coef
    rms = float(np.sqrt(np.mean(r ** 2)))
    try:
        cov = np.linalg.inv(A.T @ A) * max(rms, 1e-3) ** 2
        sa, sb = math.sqrt(cov[0, 0]), math.sqrt(cov[1, 1])
    except np.linalg.LinAlgError:
        sa = sb = float("nan")
    a, b = coef[0], coef[1]
    s = math.hypot(a, b)
    s_sig = math.sqrt(((a * sa) ** 2 + (b * sb) ** 2)) / s if s > 1e-9 else math.hypot(sa, sb)
    return coef, rms, s_sig


def _connected(xy, cell):
    """Label 8-connected components of points on a raster of size ``cell``."""
    ij = np.floor(xy / cell).astype(int)
    keys = {}
    for k, t in enumerate(map(tuple, ij)):
        keys.setdefault(t, []).append(k)
    label = -np.ones(len(xy), int)
    cur = 0
    for start in keys:
        if label[keys[start][0]] >= 0:
            continue
        stack = [start]
        for k in keys[start]:
            label[k] = cur
        while stack:
            i, j = stack.pop()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    nb = (i + di, j + dj)
                    if nb in keys and label[keys[nb][0]] < 0:
                        for k in keys[nb]:
                            label[k] = cur
                        stack.append(nb)
        cur += 1
    return label


def segment_planes(pts, thr=0.12, min_pts=25, iters=400, radius=2.5, conn_cell=None, seed=0, max_planes=30):
    """Sequential local-sample RANSAC with connectivity + LS refinement.

    pts: (N,>=3) local xyz (z may be absolute or height-above-ground). Returns list of dicts
    with plane coef (z = ax+by+c), slope, azimuth, inlier indices, rms and slope sigma.
    """
    rng = np.random.default_rng(seed)
    xyz = pts[:, :3]
    remaining = np.arange(len(xyz))
    _, spacing = density(xyz)
    conn_cell = conn_cell or max(1.2 * spacing, 0.6)
    planes = []
    while len(remaining) >= min_pts and len(planes) < max_planes:
        P = xyz[remaining]
        best_idx, best_n = None, 0
        for _ in range(iters):
            i = rng.integers(len(P))
            d = np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1])
            nb = np.flatnonzero((d < radius) & (d > 0.2))
            if len(nb) < 2:
                continue
            j, k = rng.choice(nb, 2, replace=False)
            v1, v2 = P[j] - P[i], P[k] - P[i]
            nrm = np.cross(v1, v2)
            nn = np.linalg.norm(nrm)
            if nn < 1e-6:
                continue
            nrm /= nn
            if abs(nrm[2]) < 0.25:
                continue
            dist = np.abs((P - P[i]) @ nrm)
            inl = np.flatnonzero(dist < thr)
            if len(inl) <= best_n:
                continue
            lab = _connected(P[inl, :2], conn_cell)
            lab_i = lab[np.flatnonzero(inl == i)[0]] if i in inl else np.bincount(lab).argmax()
            comp = inl[lab == lab_i]
            if len(comp) > best_n:
                best_n, best_idx = len(comp), comp
        if best_idx is None or best_n < min_pts:
            break
        # refine: LS fit -> re-collect inliers (vertical distance) -> keep connected component
        idx = best_idx
        for _ in range(3):
            coef, rms, _ = _fit_plane(P[idx])
            vz = np.abs(P[:, 2] - (coef[0] * P[:, 0] + coef[1] * P[:, 1] + coef[2]))
            inl = np.flatnonzero(vz < thr * math.sqrt(1 + coef[0] ** 2 + coef[1] ** 2))
            if len(inl) < min_pts:
                break
            lab = _connected(P[inl, :2], conn_cell)
            common = np.bincount(lab[np.isin(inl, idx)]).argmax() if np.isin(inl, idx).any() else np.bincount(lab).argmax()
            idx = inl[lab == common]
        if len(idx) < min_pts:
            remaining = np.delete(remaining, best_idx)
            continue
        coef, rms, s_sig = _fit_plane(P[idx])
        a, b, c = map(float, coef)
        slope = math.hypot(a, b)
        az = (math.degrees(math.atan2(-a, -b)) + 360) % 360 if slope > 1e-3 else None
        hull = MultiPoint(P[idx, :2]).convex_hull
        planes.append({
            "coef": [a, b, c], "slope": slope, "pitch_rise_per_12": slope * 12, "slope_sigma": s_sig,
            "azimuth": az, "n": int(len(idx)), "rms": rms,
            "centroid": P[idx, :3].mean(axis=0).tolist(),
            "z_min": float(P[idx, 2].min()), "z_max": float(P[idx, 2].max()),
            "area_est_m2": float(hull.area * math.sqrt(1 + slope ** 2)),
            "indices": remaining[idx].tolist(),
        })
        remaining = np.delete(remaining, idx)
    return planes


def outline(pts_xy, spacing, ratio=0.15, simplify=0.25, grow=None):
    """Concave hull of roof points, grown outward because the last roof return lies inside
    the drip edge. Default growth 0.65 x point spacing (measured: hull 0.32 m inside the
    drip edge at 0.45 m spacing on a 3DEP QL2 house)."""
    mp = MultiPoint([tuple(p) for p in pts_xy])
    hull = shapely.concave_hull(mp, ratio=ratio)
    if hull.geom_type != "Polygon":
        hull = mp.convex_hull
    g = 0.65 * spacing if grow is None else grow
    return hull.buffer(g, join_style="mitre").simplify(simplify)


def dominant_azimuth(planes):
    """Building orientation (deg, mod 90) from plane downslope azimuths, weighted by points."""
    num = 0j
    for p in planes:
        if p["azimuth"] is None or p["slope"] < 0.05:
            continue
        num += p["n"] * np.exp(1j * math.radians(p["azimuth"] * 4))
    if abs(num) < 1e-9:
        return None
    return (math.degrees(np.angle(num)) / 4) % 90


def suggest_wing(planes, roof_outline, ground_eave_hint=None, wing_id="M"):
    """Single-wing starting guess (orientation, rectangle, pitch, type) from LiDAR planes."""
    from shapely import affinity
    az90 = dominant_azimuth(planes) or 0.0
    # rectangle aligned with dominant orientation
    c = roof_outline.centroid
    rot = affinity.rotate(roof_outline, az90, origin=c)  # bearing -> rotate CCW by az to axis-align
    x0, y0, x1, y1 = rot.bounds
    dx, dy = x1 - x0, y1 - y0
    big = sorted([p for p in planes if p["slope"] > 0.05], key=lambda p: -p["n"])
    pitch = float(np.average([p["slope"] for p in big[:4]], weights=[p["n"] for p in big[:4]])) if big else 0.0
    # long axis bearing: dx is along bearing az90+90, dy along az90
    if dx >= dy:
        azimuth, L, W = (az90 + 90) % 180, dx, dy
    else:
        azimuth, L, W = az90 % 180, dy, dx
    # roof type: a hip has big facets sloping along the length axis as well
    along = [p for p in big[:6] if p["azimuth"] is not None and
             min(abs(((p["azimuth"] - azimuth + 180) % 360) - 180), abs(((p["azimuth"] - azimuth) % 360) - 180)) < 25]
    rtype = "hip" if len(along) >= 2 else ("flat" if pitch < 0.08 else "gable")
    ov = 0.45
    rid = max(p["z_max"] for p in big) if big else None
    eave = min(p["z_min"] for p in big) if big else None
    wing = {"id": wing_id, "type": rtype, "cx": c.x, "cy": c.y, "azimuth": azimuth,
            "length": max(L - 2 * ov, 1.0), "width": max(W - 2 * ov, 1.0), "pitch": pitch,
            "eave_overhang": ov, "rake_overhang": ov if rtype != "gable" else 0.3}
    if eave is not None:
        wing["eave_height"] = eave + ov * pitch  # drip edge -> plate line
    return wing, {"ridge_hag": rid, "drip_hag": eave}
