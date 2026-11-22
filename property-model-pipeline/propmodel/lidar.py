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


# ---------------------------------------------------------------------------
# hillside / class-1-only LiDAR: a ground SURFACE, plane acceptance, canopy removal
# ---------------------------------------------------------------------------

def _cell_median_near_min(iy, ix, z, zmin, band):
    """Per-cell median of the values within ``band`` of the cell minimum (nan where a cell has none)."""
    ny, nx = zmin.shape
    keep = z <= zmin[iy, ix] + band
    cid = (iy * nx + ix)[keep]
    zz = z[keep]
    order = np.lexsort((zz, cid))
    cid, zz = cid[order], zz[order]
    cnt = np.bincount(cid, minlength=ny * nx)
    start = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    out = np.full(ny * nx, np.nan)
    has = cnt > 0
    lo = start[has] + (cnt[has] - 1) // 2
    hi = start[has] + cnt[has] // 2
    out[has] = 0.5 * (zz[lo] + zz[hi])
    return out.reshape(ny, nx)


def ground_surface(local, cell=0.5, windows=(1.5, 3.0, 6.0, 12.0), slope=0.6, dh0=0.3, dh_max=3.0, exclude=None,
                   zstat="min", band=0.25, despike=None, despike_cells=2):
    """Progressive morphological ground filter (Zhang et al. 2003) on the lowest LAST return per cell.

    Steep lots break a single ground plane (heights above it tilt with the hill) and many 3DEP sets
    classify little or no ground. Each window opens the minimum grid; a cell is ground while its
    lowest return is within dh(w) = min(dh0 + slope * w, dh_max) of the opened surface. Class 2
    points are always ground. ``exclude`` (shapely polygon) masks cells that cannot be ground
    (a building). Returns {x0, y0, cell, nx, ny, Z (filled), ground (bool grid)}.

    ``zstat="median"``: a ground cell's height is the median of its last returns within ``band`` of
    the cell minimum instead of the minimum itself. The minimum of n noisy returns on a slope sits
    low by ~slope * cell / 2 plus the low tail of the noise (about 0.1 m on a 0.5 m cell of a steep
    lot); the band keeps grass tops and low shrubs out of the median.

    ``despike`` (m, default off): a dense shrub returns only single pulses from its top, which the morphological
    windows (dh >= dh0 + slope * 1.5 m) accept as ground; the TIN then puts a pyramid on the slope. Ground cells
    standing more than ``despike`` above the median of the ground cells in their 3x3 window, in 8-connected groups of
    at most ``despike_cells`` cells (a shrub, not a ridge line or a bank), are dropped from the ground (class 2 cells
    are kept) and bridged from the ground around them.
    """
    from scipy import ndimage
    from scipy.interpolate import griddata
    last = local[(local.shape[1] < 6) | (local[:, 4] >= local[:, 5])] if local.shape[1] >= 6 else local
    x0, y0 = float(local[:, 0].min()), float(local[:, 1].min())
    nx = int((local[:, 0].max() - x0) / cell) + 1
    ny = int((local[:, 1].max() - y0) / cell) + 1
    zmin = np.full((ny, nx), np.inf)
    ix = ((last[:, 0] - x0) / cell).astype(int); iy = ((last[:, 1] - y0) / cell).astype(int)
    np.minimum.at(zmin, (iy, ix), last[:, 2])
    zval = _cell_median_near_min(iy, ix, last[:, 2], zmin, band) if zstat == "median" else None
    has = np.isfinite(zmin)
    if not has.any():
        raise ValueError("no points")
    # fill empty cells with the nearest value so the morphology sees a continuous surface
    filled = zmin.copy()
    if (~has).any():
        idx = ndimage.distance_transform_edt(~has, return_distances=False, return_indices=True)
        filled = zmin[tuple(idx)]
    ground = has.copy()
    surf = filled.copy()
    for w in windows:
        k = max(3, int(round(w / cell)) | 1)
        opened = ndimage.grey_opening(surf, size=(k, k))
        dh = min(dh0 + slope * w, dh_max)
        ground &= (filled - opened) <= dh
        surf = opened
    if exclude is not None and not exclude.is_empty:
        gx = x0 + (np.arange(nx) + 0.5) * cell; gy = y0 + (np.arange(ny) + 0.5) * cell
        X, Y = np.meshgrid(gx, gy)
        ground &= ~shapely.contains_xy(exclude, X, Y)
    cls2 = local[local[:, 3] == 2]
    if len(cls2):
        jx = ((cls2[:, 0] - x0) / cell).astype(int); jy = ((cls2[:, 1] - y0) / cell).astype(int)
        ground[jy, jx] = True
        np.minimum.at(zmin, (jy, jx), cls2[:, 2])
        if zval is not None:
            fresh = np.isnan(zval[jy, jx])
            zval[jy[fresh], jx[fresh]] = zmin[jy[fresh], jx[fresh]]
    if despike is not None and despike > 0:
        v = np.where(ground & np.isfinite(zmin), zmin if zval is None else np.where(np.isnan(zval), zmin, zval), np.nan)
        win = np.stack([np.pad(v, 1, constant_values=np.nan)[1 + dj:1 + dj + ny, 1 + di:1 + di + nx]
                        for dj in (-1, 0, 1) for di in (-1, 0, 1)])
        with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(win, axis=0)
            nval = np.isfinite(win).sum(0)
            high = np.isfinite(v) & (nval >= 5) & (v - med > despike)
        if len(cls2):
            c2 = np.zeros((ny, nx), bool); c2[jy, jx] = True
            high &= ~c2
        if high.any():
            lab, n = ndimage.label(high, np.ones((3, 3)))
            size = ndimage.sum(high, lab, range(1, n + 1))
            ground &= ~np.isin(lab, [k + 1 for k, sz in enumerate(size) if sz <= despike_cells])
    gy_, gx_ = np.nonzero(ground & np.isfinite(zmin))
    pts = np.column_stack([x0 + (gx_ + 0.5) * cell, y0 + (gy_ + 0.5) * cell])
    vals = zmin[gy_, gx_] if zval is None else np.where(np.isnan(zval[gy_, gx_]), zmin[gy_, gx_], zval[gy_, gx_])
    X, Y = np.meshgrid(x0 + (np.arange(nx) + 0.5) * cell, y0 + (np.arange(ny) + 0.5) * cell)
    Z = griddata(pts, vals, (X, Y), method="linear")
    Zn = griddata(pts, vals, (X, Y), method="nearest")
    Z = np.where(np.isnan(Z), Zn, Z)
    return {"x0": x0, "y0": y0, "cell": cell, "nx": nx, "ny": ny, "Z": Z, "ground": ground}


def surface_z(surf, x, y):
    """Bilinear height of a ground_surface() grid at points x, y."""
    c = surf["cell"]
    fx = np.clip((np.asarray(x) - surf["x0"]) / c - 0.5, 0, surf["nx"] - 1.001)
    fy = np.clip((np.asarray(y) - surf["y0"]) / c - 0.5, 0, surf["ny"] - 1.001)
    i, j = fx.astype(int), fy.astype(int)
    tx, ty = fx - i, fy - j
    Z = surf["Z"]
    return (Z[j, i] * (1 - tx) * (1 - ty) + Z[j, i + 1] * tx * (1 - ty) + Z[j + 1, i] * (1 - tx) * ty + Z[j + 1, i + 1] * tx * ty)


def paving_humps(local, poly, above=0.3, window=3.0, cell=0.5):
    """Returns on paving that are not the pavement: parked cars, trailers, bins standing on a street or driveway.

    Inside ``poly`` (shapely (Multi)Polygon: street / driveway / walk outlines) the local lowest-return surface is
    the grey opening, with a ``window`` m square, of the per-cell (``cell`` m) lowest return -- exact on planes and
    on monotone slopes (a crowned or sloping street, a ramp, a bank the outline laps onto), while anything narrower
    than the window (a car is ~1.8 m wide) is removed. Returns more than ``above`` over the highest envelope of their
    own and the 8 neighbouring cells are flagged (so a steep bank inside the outline is kept).
    Empty cells (under a car roof) take the nearest cell's lowest return before the opening.
    Returns a bool mask over ``local`` (True = not pavement: drop before gridding the ground)."""
    from scipy import ndimage
    out = np.zeros(len(local), bool)
    if poly is None or poly.is_empty or not len(local):
        return out
    inside = shapely.contains_xy(poly, local[:, 0], local[:, 1])
    if not inside.any():
        return out
    # the envelope also sees the ground just outside the outline (a bank top beyond the edge keeps the bank face that
    # the outline laps onto under the envelope); only returns inside the outline are flagged
    near = shapely.contains_xy(poly.buffer(window), local[:, 0], local[:, 1])
    P = local[near]
    x0, y0 = float(P[:, 0].min()), float(P[:, 1].min())
    nx = int((P[:, 0].max() - x0) / cell) + 1
    ny = int((P[:, 1].max() - y0) / cell) + 1
    ix = ((P[:, 0] - x0) / cell).astype(int); iy = ((P[:, 1] - y0) / cell).astype(int)
    zmin = np.full((ny, nx), np.inf)
    np.minimum.at(zmin, (iy, ix), P[:, 2])
    has = np.isfinite(zmin)
    if (~has).any():
        idx = ndimage.distance_transform_edt(~has, return_distances=False, return_indices=True)
        zmin = zmin[tuple(idx)]
    k = max(3, int(round(window / cell)) | 1)
    env = ndimage.grey_opening(zmin, size=(k, k), mode="nearest")
    # compare with the highest envelope of the 3x3 cells around: a return on a steep bank (an outline lapping onto it)
    # may stand more than `above` over the lowest corner of its own cell, never over the envelope uphill of it
    env = ndimage.grey_dilation(env, size=(3, 3), mode="nearest")
    ins = inside[near]
    out[np.nonzero(near)[0][ins]] = P[ins, 2] > env[iy[ins], ix[ins]] + above
    return out


def solid_surface(local, x0, y0, nx, ny, cell=0.25, radius=0.6, min_single=0.9, max_rms=0.2):
    """Top of hard, smooth surfaces (bare ground, boulders, rock outcrops, paving, roofs) on a grid.

    A cell is *solid* when, in the (2k+1)^2-cell window around it (k = radius / cell), at least
    ``min_single`` of all returns come from single-return pulses (canopy and shrubs split pulses) and a
    plane through the window's last returns fits with RMS < ``max_rms``. Its height is the highest
    single return in the cell, so a boulder keeps its full height where a ground filter shaves it off.
    Cell (i, j) spans x0 + i*cell .. x0 + (i+1)*cell (same for y). Returns {Z (nan = not solid),
    single_frac, rms, count}. Mask buildings, decks and cars yourself (they are solid too).
    """
    from scipy import ndimage
    x, y, z = local[:, 0], local[:, 1], local[:, 2]
    nret = local[:, 5] if local.shape[1] >= 6 else np.ones(len(local))
    last = local[:, 4] >= nret if local.shape[1] >= 6 else np.ones(len(local), bool)
    i = np.floor((x - x0) / cell).astype(int); j = np.floor((y - y0) / cell).astype(int)
    ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    k = max(1, int(round(radius / cell)))
    size = 2 * k + 1

    def acc(w, sel):
        g = np.zeros((ny, nx))
        np.add.at(g, (j[sel], i[sel]), w[sel])
        return ndimage.uniform_filter(g, size, mode="constant") * size * size

    allp = ok
    n_all = acc(np.ones(len(x)), allp)
    n_single = acc((nret == 1).astype(float), allp)
    sel = ok & last
    # plane moments in coordinates relative to the grid origin (keeps the sums well conditioned)
    xr, yr = x - x0, y - y0
    one = np.ones(len(x))
    S = {n: acc(v, sel) for n, v in (("n", one), ("x", xr), ("y", yr), ("z", z), ("xx", xr * xr), ("xy", xr * yr),
                                    ("yy", yr * yr), ("xz", xr * z), ("yz", yr * z), ("zz", z * z))}
    A = np.stack([np.stack([S["xx"], S["xy"], S["x"]], -1), np.stack([S["xy"], S["yy"], S["y"]], -1),
                  np.stack([S["x"], S["y"], S["n"]], -1)], -2)
    b = np.stack([S["xz"], S["yz"], S["z"]], -1)
    good = S["n"] >= 6
    coef = np.zeros(b.shape)
    A_ = A[good] + np.eye(3) * 1e-9
    coef[good] = np.linalg.solve(A_, b[good][..., None])[..., 0]
    sse = S["zz"] - np.einsum("...i,...i->...", coef, b)        # sum r^2 = zz - c . b at the LS optimum
    rms = np.where(good, np.sqrt(np.maximum(sse, 0) / np.maximum(S["n"], 1)), np.inf)
    frac = n_single / np.maximum(n_all, 1)
    top = np.full((ny, nx), -np.inf)
    s1 = ok & (nret == 1)
    np.maximum.at(top, (j[s1], i[s1]), z[s1])
    solid = np.isfinite(top) & good & (frac >= min_single) & (rms < max_rms)
    # per-cell statistics of the cell's own returns (merge_solid's edge growth, rock outlines)
    low = np.full((ny, nx), np.inf)
    np.minimum.at(low, (j[sel], i[sel]), z[sel])
    c_all = np.zeros((ny, nx)); c_one = np.zeros((ny, nx))
    np.add.at(c_all, (j[ok], i[ok]), 1.0); np.add.at(c_one, (j[s1], i[s1]), 1.0)
    return {"Z": np.where(solid, top, np.nan), "single_frac": frac, "rms": rms, "count": n_all,
            "top": np.where(np.isfinite(top), top, np.nan), "low": np.where(np.isfinite(low), low, np.nan),
            "cell_single": np.where(c_all > 0, c_one / np.maximum(c_all, 1), np.nan), "cell_count": c_all,
            "q90_single": cell_quantile(i[s1], j[s1], z[s1], nx, ny, 0.9)}


def cell_quantile(i, j, z, nx, ny, q):
    """Per-cell quantile ``q`` (0..1, linear between order statistics) of values z at cells (i, j);
    nan where a cell has no value."""
    out = np.full((ny, nx), np.nan)
    if len(z) == 0:
        return out
    k = j.astype(np.int64) * nx + i
    o = np.lexsort((z, k))
    k, zs = k[o], z[o]
    starts = np.r_[0, np.nonzero(np.diff(k))[0] + 1]
    ends = np.r_[starts[1:], len(k)]
    pos = starts + q * (ends - starts - 1)
    lo = np.floor(pos).astype(int); hi = np.minimum(lo + 1, ends - 1); t = pos - lo
    out.ravel()[k[starts]] = zs[lo] * (1 - t) + zs[hi] * t
    return out


def merge_solid(Zg, Zs, cell, rise=1.0, min_patch=0.75, max_rise=None, grow=None, grow_iter=0, grow_single=0.9,
                grow_above=0.3, mask=None):
    """Terrain = max(ground surface, solid surface). Solid cells that stand more than ``rise`` above the
    ground are kept only in 8-connected patches of at least ``min_patch`` m^2 (a lone tall cell is a
    post, a sign or a bird, a boulder is a patch); ``max_rise`` drops anything taller.

    Edge growth (``grow`` = the solid_surface() dict, ``grow_iter`` > 0): the planarity window of the solid
    surface fails on every boulder / outcrop edge, so tall patches come out shrunk by about the window
    radius. For ``grow_iter`` rounds (use ceil(radius / cell) + 1), 8-neighbours of an accepted tall patch
    are accepted too when the cell's own returns are at least ``grow_single`` single-return pulses, its
    lowest last return stands more than ``grow_above`` above the ground (and less than ``max_rise``) and it
    is not in ``mask`` (bool grid: never solid). A grown cell takes its highest single return.
    Returns (Z, accepted mask)."""
    from scipy import ndimage
    d = Zs - Zg
    acc = np.isfinite(d) & (d > 0)
    if max_rise is not None:
        acc &= d < max_rise
    if mask is not None:
        acc &= ~mask
    tall = acc & (d > rise)
    lab, n = ndimage.label(tall, np.ones((3, 3)))
    if n:
        area = ndimage.sum(tall, lab, range(1, n + 1)) * cell * cell
        small = np.isin(lab, [q + 1 for q, a in enumerate(area) if a < min_patch])
        acc &= ~small
        tall &= ~small
    Zm = np.where(acc, Zs, Zg)
    if grow is not None and grow_iter > 0 and tall.any():
        top, low, frac = grow["top"], grow["low"], grow["cell_single"]
        with np.errstate(invalid="ignore"):
            up = low - Zg
            ok = np.isfinite(top) & np.isfinite(up) & (np.nan_to_num(frac) >= grow_single) & (up > grow_above)
            if max_rise is not None:
                ok &= up < max_rise
        if mask is not None:
            ok &= ~mask
        region = tall.copy(); grown = np.zeros_like(tall)
        for _ in range(int(grow_iter)):
            ring = ndimage.binary_dilation(region, np.ones((3, 3))) & ~region & ok
            if not ring.any():
                break
            region |= ring; grown |= ring
        Zm = np.where(grown, np.maximum(top, Zg), Zm)
        acc = acc | grown
    # sampling holes inside a raised patch (an empty cell, one rough window on a boulder top) would drop to
    # the ground below as a pit: fill cells the closing of the raised patch covers from their raised
    # neighbours -- but not a cell whose own lowest return is at ground level (the foot around a boulder)
    raised = acc & ((Zm - Zg) > 0.3)
    holes = ndimage.binary_closing(raised, np.ones((3, 3)), iterations=2) & ~raised
    if mask is not None:
        holes &= ~mask
    if grow is not None:
        with np.errstate(invalid="ignore"):
            holes &= ~(np.isfinite(grow["low"]) & ((grow["low"] - Zg) <= grow_above))
    if holes.any():
        w = ndimage.uniform_filter(raised.astype(float), 3)
        v = ndimage.uniform_filter(np.where(raised, Zm, 0.0), 3) / np.maximum(w, 1e-9)
        fill = holes & (w > 0.3) & (v > Zg)
        Zm = np.where(fill, v, Zm)
        acc = acc | fill
    return Zm, acc


def despike(Z, nodes, cell, above=0.3, sigma=0.25, max_change=None, edge_nodes=None, passes=1):
    """Knock down single-node spikes on rough raised terrain (boulder fields, outcrop tops): on ``nodes``
    (bool grid) z = min(z, median of the 3x3 neighbourhood + ``above``), then a Gaussian of ``sigma`` m
    over those nodes only (the rest of the grid is untouched). ``max_change`` (m) limits how far the
    Gaussian may move a node, so measured rough rock tops keep their relief (spikes are already capped by
    the median step) -- except on ``edge_nodes`` (bool grid; e.g. the outline of the raised patches, whose
    cell-sized teeth render as dark shards): they take the full Gaussian, ``passes`` times.
    Returns the new grid."""
    from scipy import ndimage
    if not nodes.any():
        return Z
    med = ndimage.median_filter(Z, size=3, mode="nearest")
    Z1 = np.where(nodes, np.minimum(Z, med + above), Z)
    if sigma <= 0:
        return Z1
    G = ndimage.gaussian_filter(Z1, sigma / cell, mode="nearest")
    Gc = np.clip(G, Z1 - max_change, Z1 + max_change) if max_change is not None else G
    out = np.where(nodes, Gc, Z1)
    if edge_nodes is not None and edge_nodes.any():
        e = edge_nodes & nodes
        for _ in range(max(1, int(passes))):
            G = ndimage.gaussian_filter(out, sigma / cell, mode="nearest")
            out = np.where(e, G, out)
    return out


def veg_floor(Z, mask, cell, window=2.0, dh=0.1):
    """Ground under dense shrubs: inside ``mask`` (bool grid: a shrub / mulch bed) z = min(z, grey opening of the grid
    with a ``window`` m square + ``dh``). Evergreen shrubs return single pulses from their tops, which the ground
    filter keeps; the opening removes bumps narrower than the window (shrubs) and keeps planes, slopes and hollows,
    so the bed follows the envelope of the ground around the shrubs. Nodes outside the mask are untouched."""
    from scipy import ndimage
    m = np.asarray(mask, bool)
    if not m.any():
        return np.array(Z, float, copy=True)
    k = max(3, int(round(window / cell)) | 1)
    op = ndimage.grey_opening(np.asarray(Z, float), size=(k, k), mode="nearest")
    return np.where(m, np.minimum(Z, op + dh), Z)


def clamp_spikes(Z, cell, skip=None, rock=None, above=0.3, below=0.3, passes=2, sigma=0.25, max_change=None,
                 fill_rock=True, floor=None, bump=None, bump_nodes=4, ring=0, bump_passes=3, ring_exclude=None,
                 floor_clamp=True, peak=None, ceiling=None):
    """Final terrain despike on EVERY grid node (not only rock-raised ones): spikes left by shrub tops the ground
    filter kept, single solid cells, sampling holes, render as lit pyramids.

    ``passes`` times: z = min(z, 3x3 median + ``above``) on every node not in ``skip`` (bool grid: breakline bands,
    grade pads -- their steps are measured and intended). On ``rock`` nodes (bool grid, e.g. rock_rise > 0.2; with
    ``fill_rock`` also the nodes its 3x3 closing adds: no-return pits inside a boulder top) also
    z = max(z, 3x3 median - ``below``), which lifts one-node pits where a boulder's sampling hole let the ground
    through. Then a Gaussian of ``sigma`` m over those rock nodes only (``max_change`` m limits how far it moves a
    node; None = free). A straight cliff edge keeps its height (its 3x3 median is the high side); a 2x2 bump is
    clamped (only 4 of 9 nodes are high), and one-cell-wide fins are cut down.

    ``floor`` (grid, nan = none; e.g. each node cell's measured height - 0.1): on rock nodes the Gaussian never takes a
    node below it, nor does the clamp where ``floor_clamp`` is True or a bool grid that holds the node (e.g. traced
    rock outlines: there a measured point is rock, elsewhere it may be a shrub top), so measured rock points keep their height while the artefacts around them
    (unsupported spikes, sawtooth outline teeth over empty cells) are clamped and smoothed.
    ``ceiling`` (grid, nan = none; e.g. each node cell's lowest last return + 0.3): the pit lift and the Gaussian never
    raise a node above it -- a node with a ground return at the foot of a rock face is measured ground, not a pit.
    ``peak`` (m): also z = min(z, highest of the 8 neighbours + peak) (a lone node a little over the clamp still
    renders as a lit pyramid; a rounded rock top is only centimetres above its highest neighbour).
    ``bump`` (m): afterwards, nodes off the rock that stand more than this above the 5x5 median in 8-connected
    groups of at most ``bump_nodes`` (a 2x2 block on a slope passes the 3x3 test because its window holds the block
    and the slope above it) are set to that median, up to ``bump_passes`` times (lowering one bump can leave the next
    node standing out). ``ring`` > 0 extends the rock Gaussian over that many rings of nodes around the rock (the
    foot of a boulder), so a one-cell cliff at the rock outline becomes a short ramp instead of a cell-sized tooth
    (``ring_exclude``: nodes the ring must not lift, e.g. a shrub bed levelled to its ground envelope).
    Returns (new grid, rock nodes used)."""
    from scipy import ndimage
    Z = np.array(Z, float, copy=True)
    free = np.ones(Z.shape, bool) if skip is None else ~np.asarray(skip, bool)
    rk = np.zeros(Z.shape, bool) if rock is None else np.asarray(rock, bool).copy()
    if fill_rock and rk.any():
        rk |= ndimage.binary_closing(rk, np.ones((3, 3)), border_value=0)
    rk &= free
    if floor is None or floor_clamp is False or floor_clamp is None:
        fl = None
    else:
        fc = rk if floor_clamp is True else (rk & np.asarray(floor_clamp, bool))
        fl = np.where(fc, np.asarray(floor, float), np.nan)
    ring8 = np.ones((3, 3), bool); ring8[1, 1] = False
    for _ in range(max(1, int(passes))):
        med = ndimage.median_filter(Z, size=3, mode="nearest")
        Zc = np.minimum(Z, med + above)
        if peak is not None:          # a lone peak (higher than all 8 neighbours) renders as a lit pyramid
            Zc = np.minimum(Zc, ndimage.maximum_filter(Z, footprint=ring8, mode="nearest") + peak)
        if fl is not None:            # a measured rock point (its own cell's lowest last return) is not a spike
            Zc = np.where(np.isfinite(fl), np.maximum(Zc, np.minimum(Z, fl)), Zc)
        Z = np.where(free, Zc, Z)
        if rk.any() and below is not None:
            up = np.maximum(Z, med - below)
            if ceiling is not None:
                up = np.where(np.isfinite(ceiling), np.minimum(up, np.maximum(Z, ceiling)), up)
            Z = np.where(rk, up, Z)
    if sigma and sigma > 0 and rk.any():
        G = ndimage.gaussian_filter(Z, sigma / cell, mode="nearest")
        if max_change is not None:
            G = np.clip(G, Z - max_change, Z + max_change)
        if floor is not None:
            fl2 = np.asarray(floor, float)
            G = np.where(np.isfinite(fl2), np.maximum(G, np.minimum(Z, fl2)), G)
        if ceiling is not None:
            G = np.where(np.isfinite(ceiling), np.minimum(G, np.maximum(Z, ceiling)), G)
        sm = rk
        if ring and ring > 0:
            sm = (ndimage.binary_dilation(rk, np.ones((3, 3)), iterations=int(ring)) & free) | rk
            if ring_exclude is not None:
                sm &= ~(np.asarray(ring_exclude, bool) & ~rk)
        Z = np.where(sm, G, Z)
    if bump is not None and bump > 0:
        for _ in range(max(1, int(bump_passes))):
            m5 = ndimage.median_filter(Z, size=5, mode="nearest")
            high = (Z - m5 > bump) & free & ~rk
            if not high.any():
                break
            lab, n = ndimage.label(high, np.ones((3, 3)))
            size = ndimage.sum(high, lab, range(1, n + 1))
            sel = np.isin(lab, [k + 1 for k, sz in enumerate(size) if sz <= bump_nodes])
            if not sel.any():
                break
            Z = np.where(sel, m5, Z)
    return Z, rk


def clamp_unsupported(Z, cell, free, pxy, pz, x0=0.0, y0=0.0, above=0.3, bump=0.4, radius=0.3, dz=0.25, passes=2):
    """Lower spikes no LiDAR return supports. On ``free`` nodes (bool grid; e.g. off the rock and the breakline bands)
    a node more than ``above`` over the mean of its 8 neighbours (a crest-line node, which is its own 3x3 median, or a
    pyramid tip), or more than ``bump`` over its 5x5 median, is set to that level unless a return within ``radius`` m
    in plan (``pxy`` [n, 2], heights ``pz``, the grid's frame) lies within ``dz`` of its height: measured terrain breaks
    and crests keep their height, interpolation artefacts (a TIN fold over a sampling gap) go.
    Grid node (j, i) is at (x0 + i * cell, y0 + j * cell). Returns (new grid, number of nodes lowered)."""
    from scipy import ndimage
    from scipy.spatial import cKDTree
    Z = np.array(Z, float, copy=True)
    free = np.asarray(free, bool).copy()
    free[[0, -1], :] = False; free[:, [0, -1]] = False
    tree = cKDTree(np.asarray(pxy, float))
    k8 = np.ones((3, 3)); k8[1, 1] = 0
    lowered = np.zeros(Z.shape, bool)
    for _ in range(max(1, int(passes))):
        mean8 = ndimage.convolve(Z, k8 / 8.0, mode="nearest")
        target = np.where(free & (Z - mean8 > above), mean8 + above, np.inf)
        if bump:
            m5 = ndimage.median_filter(Z, size=5, mode="nearest")
            target = np.where(free & (Z - m5 > bump), np.minimum(target, m5), target)
        jj, ii = np.nonzero(np.isfinite(target))
        if not len(jj):
            break
        q = np.column_stack([x0 + ii * cell, y0 + jj * cell])
        hits = tree.query_ball_point(q, radius)
        cut = np.array([not (len(h) and np.any(np.abs(np.asarray(pz)[h] - Z[j_, i_]) < dz))
                        for h, j_, i_ in zip(hits, jj, ii)], bool)
        if not cut.any():
            break
        Z[jj[cut], ii[cut]] = target[jj[cut], ii[cut]]
        lowered[jj[cut], ii[cut]] = True
    return Z, int(lowered.sum())


def accept_planes(planes, xyz, min_pts=150, max_rms=0.06, max_slope=1.0, min_area=8.0, cell=0.5):
    """Keep roof planes only: enough points, flat enough fit, not steeper than 12/12, real area.
    Area is the occupied-cell area of the inliers (trees and rocks give small or rough patches).
    Rejected planes come back separately (chimney tops, skylight curbs, canopy, boulders)."""
    keep, reject = [], []
    for p in planes:
        idx = main_patch(xyz, np.asarray(p["indices"], int), cell=cell, min_area=min_area)
        if len(idx) < len(p["indices"]):
            # thin strips that happen to lie on the plane (hillside grade, a fence line) are cut off
            a, b, c = p["coef"]
            r = xyz[idx, 2] - (a * xyz[idx, 0] + b * xyz[idx, 1] + c)
            p.update(indices=idx, n=int(len(idx)), rms=float(np.sqrt(np.mean(r ** 2))) if len(idx) else 9.9,
                     z_min=float(xyz[idx, 2].min()) if len(idx) else 0.0, z_max=float(xyz[idx, 2].max()) if len(idx) else 0.0)
        cells = {(int(x // cell), int(y // cell)) for x, y in xyz[idx, :2]}
        area = len(cells) * cell * cell
        p["area_cells_m2"] = area
        ok = p["n"] >= min_pts and p["rms"] <= max_rms and p["slope"] <= max_slope and area >= min_area
        (keep if ok else reject).append(p)
    return keep, reject


def _cells(xy, x0, y0, cell, shape):
    i = np.clip(((xy[:, 0] - x0) // cell).astype(int), 0, shape[0] - 1)
    j = np.clip(((xy[:, 1] - y0) // cell).astype(int), 0, shape[1] - 1)
    return i, j


def main_patch(xyz, idx, cell=0.5, min_area=8.0):
    """Plane inliers that form real patches: occupancy raster, opened by one cell (drops 1-2 cell
    wide strips), components of at least ``min_area`` (and 20 % of the largest) kept, grown back
    by one cell. Returns the surviving inlier indices."""
    from scipy import ndimage
    if len(idx) == 0:
        return idx
    xy = xyz[idx, :2]
    x0, y0 = xy.min(axis=0) - 2 * cell
    shape = (int((xy[:, 0].max() - x0) // cell) + 3, int((xy[:, 1].max() - y0) // cell) + 3)
    i, j = _cells(xy, x0, y0, cell, shape)
    occ = np.zeros(shape, bool)
    occ[i, j] = True
    occ = ndimage.binary_closing(occ, np.ones((3, 3)))          # fill sampling holes first
    core = ndimage.binary_opening(occ, np.ones((3, 3)))
    lab, n = ndimage.label(core, np.ones((3, 3)))
    if n == 0:
        return idx[:0]
    areas = ndimage.sum(core, lab, range(1, n + 1)) * cell * cell
    good = [k + 1 for k, a in enumerate(areas) if a >= min(min_area, areas.max()) and a >= 0.2 * areas.max()]
    mask = ndimage.binary_dilation(np.isin(lab, good), np.ones((3, 3))) & occ
    return idx[mask[i, j]]


def remove_canopy(xyz, planes, near=0.6, above=0.15, cell=0.5):
    """Points over / just outside a kept roof plane that sit more than ``above`` m over it are
    branches overhanging the eaves: drop them. "Over the plane" means within ``near`` of the
    plane's own inlier cells (not its convex hull, which would also swallow a lower roof that
    sits in a notch of the plane). Returns a boolean keep-mask."""
    from scipy import ndimage
    keep = np.ones(len(xyz), bool)
    for p in planes:
        idx = np.asarray(p["indices"], int)
        xy = xyz[idx, :2]
        x0, y0 = xy.min(axis=0) - near - cell
        shape = (int((xy[:, 0].max() + near - x0) // cell) + 2, int((xy[:, 1].max() + near - y0) // cell) + 2)
        occ = np.zeros(shape, bool)
        occ[_cells(xy, x0, y0, cell, shape)] = True
        occ = ndimage.binary_dilation(ndimage.binary_closing(occ, np.ones((3, 3))), np.ones((3, 3)),
                                      iterations=max(1, int(round(near / cell))))
        a, b, c = p["coef"]
        inb = (xyz[:, 0] >= x0) & (xyz[:, 1] >= y0) & (xyz[:, 0] < x0 + shape[0] * cell) & (xyz[:, 1] < y0 + shape[1] * cell)
        inside = np.zeros(len(xyz), bool)
        ii, jj = _cells(xyz[inb, :2], x0, y0, cell, shape)
        inside[inb] = occ[ii, jj]
        dz = xyz[:, 2] - (a * xyz[:, 0] + b * xyz[:, 1] + c)
        keep &= ~(inside & (dz > above))
    return keep


def flat_clusters(xyz, z_lo, z_hi, max_slope=0.05, min_area=4.0, cell=0.5, thr=0.06):
    """Level surfaces (decks, slabs, flat roofs) between two heights: plane segmentation restricted
    to near-horizontal fits. Returns [{z, area_m2, outline, n}]."""
    m = (xyz[:, 2] > z_lo) & (xyz[:, 2] < z_hi)
    pts = xyz[m]
    if len(pts) < 20:
        return []
    out = []
    for p in segment_planes(pts, thr=thr, min_pts=20, max_planes=12):
        if p["slope"] > max_slope:
            continue
        q = pts[np.asarray(p["indices"], int)]
        cells = {(int(x // cell), int(y // cell)) for x, y in q[:, :2]}
        area = len(cells) * cell * cell
        if area < min_area:
            continue
        hull = shapely.concave_hull(MultiPoint([tuple(v) for v in q[:, :2]]), ratio=0.3)
        out.append({"z": float(np.median(q[:, 2])), "area_m2": area, "n": len(q),
                    "outline": [list(map(float, c)) for c in getattr(hull, "exterior", hull.convex_hull.exterior).coords]})
    return out
