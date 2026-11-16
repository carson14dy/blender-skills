#!/usr/bin/env python3
"""Build a Gaussian-splat "surroundings" file from free data: USGS 3DEP lidar points coloured from
USDA NAIP 2025 imagery, for Spark (sparkjs.dev) to draw around the studio's measured house.

Every lidar return within --radius metres of the house becomes one splat:
  * position: the return, in the studio's model frame (x = east, y = up from model y=0, z = -north);
  * shape: a flat disc along the local surface (PCA of the 12 nearest returns) where the points are
    planar (ground, roofs), a round blob where they are not (leaf-off branches);
  * colour: the NAIP pixel straight below (3 x 3 mean, 0.9 m), so roof edges and tree crowns pick up
    the photo's lean (NAIP is not a true orthophoto);
  * returns on the measured house itself and ground inside the studio's own terrain square are left out.

Output: out/lab/splat/surroundings.spz (Niantic SPZ v2, gzip) and out/lab/data/splat.json.

    python3 tools/build_splat.py --radius 70
"""
import argparse
import gzip
import math
import os
import struct

import numpy as np
from scipy.spatial import cKDTree

from common import ATTRIBUTION, CACHE, DATA, FT_US, OUT, Site, cityapi, http, log, write_json
import ept
from naip import naip_window

SH_C0 = 0.28209479177387814


def write_spz(path, pos, rgb, alpha, log_scale, quat_xyzw, frac_bits=12):
    """Niantic SPZ v2: header, then positions (24-bit fixed), alphas, colours, scales, rotations; gzip."""
    n = len(pos)
    hdr = struct.pack("<IIIBBBB", 0x5053474E, 2, n, 0, frac_bits, 0, 0)
    fx = np.round(pos * (1 << frac_bits)).astype(np.int64)
    if np.abs(fx).max() >= (1 << 23):
        raise ValueError("positions out of range for %d fractional bits" % frac_bits)
    fx &= 0xFFFFFF
    p24 = np.stack([(fx >> 0) & 0xFF, (fx >> 8) & 0xFF, (fx >> 16) & 0xFF], -1).astype(np.uint8).reshape(-1)
    a8 = np.clip(np.round(alpha * 255.0), 0, 255).astype(np.uint8)
    f_dc = (rgb - 0.5) / SH_C0
    c8 = np.clip(np.round(f_dc * (0.15 * 255.0) + 0.5 * 255.0), 0, 255).astype(np.uint8).reshape(-1)
    s8 = np.clip(np.round((log_scale + 10.0) * 16.0), 0, 255).astype(np.uint8).reshape(-1)
    q = quat_xyzw / np.linalg.norm(quat_xyzw, axis=1, keepdims=True)
    q = np.where(q[:, 3:4] < 0, -q, q)
    r8 = np.clip(np.round(q[:, :3] * 127.5 + 127.5), 0, 255).astype(np.uint8).reshape(-1)
    raw = hdr + p24.tobytes() + a8.tobytes() + c8.tobytes() + s8.tobytes() + r8.tobytes()
    data = gzip.compress(raw, 9, mtime=0)
    with open(path, "wb") as f:
        f.write(data)
    return len(data), len(raw)


def quat_from_matrix(R):
    """Rotation matrices (N x 3 x 3, columns = local axes) -> quaternions (x, y, z, w)."""
    m = R
    t = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    q = np.zeros((len(m), 4))
    w = np.sqrt(np.maximum(0, 1 + t)) / 2
    x = np.sqrt(np.maximum(0, 1 + m[:, 0, 0] - m[:, 1, 1] - m[:, 2, 2])) / 2
    y = np.sqrt(np.maximum(0, 1 - m[:, 0, 0] + m[:, 1, 1] - m[:, 2, 2])) / 2
    z = np.sqrt(np.maximum(0, 1 - m[:, 0, 0] - m[:, 1, 1] + m[:, 2, 2])) / 2
    x = np.copysign(x, m[:, 2, 1] - m[:, 1, 2])
    y = np.copysign(y, m[:, 0, 2] - m[:, 2, 0])
    z = np.copysign(z, m[:, 1, 0] - m[:, 0, 1])
    q[:, 0], q[:, 1], q[:, 2], q[:, 3] = x, y, z, w
    return q


def in_ring(ring, x, y):
    inside = np.zeros(len(x), bool)
    for (ax, ay), (bx, by) in zip(ring, np.roll(ring, -1, 0)):
        cond = (ay > y) != (by > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = ax + (y - ay) * (bx - ax) / (by - ay)
        inside ^= cond & (x < xi)
    return inside


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radius", type=float, default=70.0)
    ap.add_argument("--hole", type=float, default=33.5, help="drop ground returns inside this half-size square")
    ap.add_argument("--max-splats", type=int, default=260000)
    ap.add_argument("--keep-house", action="store_true", help="keep the lidar returns on the measured house")
    ap.add_argument("--ground-grid", type=float, default=0.35,
                    help="replace ground returns by a regular grid of splats on the lidar ground (metres; 0 = off)."
                         " Grid points more than 1 m from any ground return (under buildings) are left out")
    a = ap.parse_args()
    site = Site.load()
    h = http(log)
    R = (a.radius + 2) / FT_US
    pts = ept.fetch(h, (site.ox - R, site.oy - R, site.ox + R, site.oy + R))
    e, n, u = site.city_to_enu(pts["x_ft"], pts["y_ft"], pts["z_m"])
    keep = np.hypot(e, n) <= a.radius
    ground = pts["cls"] == 2
    # the house: city footprint (roof edge incl. overhang) + 0.4 m, above 0.6 m (cached by align_house.py)
    ring_ft = None
    try:
        import json
        cache_fp = os.path.join(CACHE, str(site.d["footprintOid"]), "raw", "footprint.json")
        ring_ft = np.asarray(json.load(open(cache_fp))["features"][0]["geometry"]["rings"][0], float)[:, :2]
    except OSError:
        log("footprint not cached; run align_house.py first to leave the house out")
    dropped_house = 0
    if ring_ft is not None and not a.keep_house:
        re_, rn_ = site.city_to_enu(ring_ft[:, 0], ring_ft[:, 1])
        ring = np.column_stack([re_, rn_])
        c = ring.mean(0)
        ring = c + (ring - c) * (1 + 0.4 / np.linalg.norm(ring - c, axis=1, keepdims=True))
        house = in_ring(ring, e, n) & (u > 0.6)
        dropped_house = int((house & keep).sum())
        keep &= ~house
    hole = ground & (np.abs(e) < a.hole) & (np.abs(n) < a.hole)
    keep &= ~hole
    e, n, u = e[keep], n[keep], u[keep]
    cls, nr = pts["cls"][keep], pts["nr"][keep]
    if len(e) > a.max_splats:  # thin ground first
        rng = np.random.default_rng(0)
        g = np.where(cls == 2)[0]
        drop = rng.choice(g, min(len(g), len(e) - a.max_splats), replace=False)
        m = np.ones(len(e), bool); m[drop] = False
        e, n, u, cls, nr = e[m], n[m], u[m], cls[m], nr[m]
    grid_added = 0
    if a.ground_grid > 0:
        from scipy.interpolate import griddata
        g = cls == 2
        gx = np.arange(-a.radius, a.radius + 1e-6, a.ground_grid)
        X, Y = np.meshgrid(gx, gx)
        X, Y = X.ravel(), Y.ravel()
        m = (np.hypot(X, Y) <= a.radius) & ~((np.abs(X) < a.hole) & (np.abs(Y) < a.hole))
        X, Y = X[m], Y[m]
        dist, _ = cKDTree(np.column_stack([e[g], n[g]])).query(np.column_stack([X, Y]))
        X, Y = X[dist < 1.0], Y[dist < 1.0]
        Z = griddata(np.column_stack([e[g], n[g]]), u[g], (X, Y), "linear")
        ok = ~np.isnan(Z)
        X, Y, Z = X[ok], Y[ok], Z[ok]
        grid_added = len(X)
        e = np.concatenate([e[~g], X]); n = np.concatenate([n[~g], Y]); u = np.concatenate([u[~g], Z])
        cls = np.concatenate([cls[~g], np.full(len(X), 2, np.uint8)]); nr = np.concatenate([nr[~g], np.ones(len(X), np.uint8)])
    P = np.column_stack([e, n, u])
    tree = cKDTree(P)
    d, idx = tree.query(P, k=12)
    spacing = np.median(d[:, 1:4], axis=1)
    nb = P[idx] - P[idx].mean(1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / 12
    w, V = np.linalg.eigh(cov)  # ascending: V[:, :, 0] = normal
    planarity = (w[:, 1] - w[:, 0]) / np.maximum(w[:, 2], 1e-9)
    flat = (cls == 2) | ((planarity > 0.35) & (nr == 1))
    # local axes in scene frame (x = e, y = u, z = -n): columns t1, t2, normal
    def to_scene(v):
        return np.stack([v[..., 0], v[..., 2], -v[..., 1]], -1)
    normal = to_scene(V[:, :, 0]); t1 = to_scene(V[:, :, 2]); t2 = np.cross(normal, t1)
    Rm = np.stack([t1, t2, normal], -1)
    q = quat_from_matrix(Rm)
    sig = np.clip(spacing * 0.6, 0.08, 0.45)
    if grid_added:
        sig = np.where(cls == 2, a.ground_grid * 0.6, sig)
    scale = np.where(flat[:, None], np.column_stack([sig, sig, np.full(len(sig), 0.025)]),
                     np.column_stack([sig * 0.8, sig * 0.8, sig * 0.8]))
    q = np.where(flat[:, None], q, np.array([[0, 0, 0, 1.0]]))
    info, smp = naip_window(site, half_m=a.radius + 10)
    acc = np.zeros((len(e), 3))
    for dx in (-0.3, 0, 0.3):
        for dy in (-0.3, 0, 0.3):
            acc += smp(e + dx, n + dy)
    rgb = (acc / 9.0) / 255.0
    alpha = np.where(flat, 0.92, 0.55)
    pos = to_scene(P)
    os.makedirs(os.path.join(OUT, "lab", "splat"), exist_ok=True)
    path = os.path.join(OUT, "lab", "splat", "surroundings.spz")
    size, raw = write_spz(path, pos, rgb, alpha, np.log(scale), q)
    area = math.pi * a.radius ** 2
    summary = {
        "file": "lab/splat/surroundings.spz", "format": "SPZ v2 (gzip), SH degree 0", "bytes": size, "rawBytes": raw,
        "splats": int(len(pos)), "radiusM": a.radius, "groundSplats": int((cls == 2).sum()),
        "aboveGroundSplats": int((cls != 2).sum()), "flatSplats": int(flat.sum()),
        "droppedHouseReturns": dropped_house, "groundGridM": a.ground_grid, "groundGridSplats": grid_added, "droppedGroundInStudioTerrain": int(hole.sum()),
        "splatsPerM2": round(float(len(pos) / area), 2),
        "lidarAboveGroundMedianSpacingM": round(float(np.median(spacing[cls != 2])), 3),
        "lidar": "USGS 3DEP SD_EasternSD_3_2020 (flown Dec 2020, leaf-off), classes: 1 unclassified, 2 ground",
        "imagery": "USDA NAIP %s (%s, %.1f m)" % (info["item"], info["date"][:10], info["pixelM"]),
        "frame": "studio model frame (x east, y up from model y=0, z = -north); add the studio's model offset",
        "attribution": ATTRIBUTION,
    }
    write_json(os.path.join(DATA, "splat.json"), summary, indent=1)
    # the artifact host serves no .glb/.spz: ship each binary as base64 JSON (<name>.glb.json)
    from pack_json import pack
    _, _, packed = pack(path)
    summary["file"] = "lab/splat/surroundings.spz.json"
    summary["packedBytes"] = packed
    write_json(os.path.join(DATA, "splat.json"), summary, indent=1)
    log("splat: %d splats (%d ground, %d flat), %.2f MB gz (%.2f MB raw)" % (
        len(pos), summary["groundSplats"], summary["flatSplats"], size / 1e6, raw / 1e6))


if __name__ == "__main__":
    main()
