#!/usr/bin/env python3
"""Find where the studio's measured house model sits on the earth.

The studio model (houses/<id>.gltf.json) is in site-local ENU metres, Y up, north = -Z, but it
carries no georeference. This script recovers one from free data and measures how well it fits:

  1. plan position + rotation: the model's roof outline (meshes named "Roof*", projected to plan)
     is fitted to the City of Sioux Falls building footprint (the roof edge incl. overhang) by
     maximising the overlap of the two rasterised shapes (5 cm grid, translation + rotation);
  2. height: model terrain vs USGS 3DEP lidar ground returns (class 2) around the house.

Writes out/lab/data/site.json, which every other lab tool and the Lab tab read.

    python3 tools/align_house.py --address "1601 S Discovery Ave" \
        --model out/houses/1601-s-discovery-ave.gltf.json
"""
import argparse
import math
import os

import numpy as np
from scipy import ndimage, optimize

from common import CACHE, DATA, FT_US, cityapi, esri, http, lidar, log, proj, write_json
from gltf_read import load_meshes

CELL = 0.05  # m


def raster_tris(tris2d, x0, y0, nx, ny, cell=CELL):
    """Rasterise 2D triangles (Kx3x2, metres) into a boolean grid."""
    m = np.zeros((ny, nx), bool)
    for t in tris2d:
        a, b, c = t
        lo = np.floor((t.min(0) - (x0, y0)) / cell).astype(int)
        hi = np.ceil((t.max(0) - (x0, y0)) / cell).astype(int)
        lo = np.clip(lo, 0, (nx - 1, ny - 1)); hi = np.clip(hi, 0, (nx - 1, ny - 1))
        if (hi < lo).any():
            continue
        xs = x0 + (np.arange(lo[0], hi[0] + 1) + 0.5) * cell
        ys = y0 + (np.arange(lo[1], hi[1] + 1) + 0.5) * cell
        X, Y = np.meshgrid(xs, ys)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l1 + l2 <= 1 + 1e-9)
        m[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1] |= inside
    return m


def raster_poly(ring, x0, y0, nx, ny, cell=CELL):
    xs = x0 + (np.arange(nx) + 0.5) * cell
    ys = y0 + (np.arange(ny) + 0.5) * cell
    X, Y = np.meshgrid(xs, ys)
    inside = np.zeros_like(X, bool)
    r = np.asarray(ring)
    for (ax, ay), (bx, by) in zip(r, np.roll(r, -1, 0)):
        cond = (ay > Y) != (by > Y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = ax + (Y - ay) * (bx - ax) / (by - ay)
        inside ^= cond & (X < xi)
    return inside


def outline_distance(mask_a, mask_b, cell=CELL):
    """Symmetric boundary distance stats (m) between two masks on the same grid."""
    ea = mask_a ^ ndimage.binary_erosion(mask_a)
    eb = mask_b ^ ndimage.binary_erosion(mask_b)
    db = ndimage.distance_transform_edt(~eb) * cell
    da = ndimage.distance_transform_edt(~ea) * cell
    d = np.concatenate([db[ea], da[eb]])
    return {"meanM": round(float(d.mean()), 3), "p95M": round(float(np.percentile(d, 95)), 3),
            "maxM": round(float(d.max()), 3)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address", default="1601 S Discovery Ave")
    ap.add_argument("--model", required=True)
    ap.add_argument("--geoid", type=float, default=-26.9,
                    help="geoid undulation N in metres (GEOID18 near Sioux Falls is about -26.9); only used "
                         "to turn NAVD88 into an ellipsoid height for the ECEF tileset, and it cancels on load")
    a = ap.parse_args()
    h = http(log)
    cand = cityapi.find_address(h, a.address, CACHE)
    if not cand:
        raise SystemExit("address not found")
    addr = cand[0]
    fp, _ = cityapi.footprint_by_point(h, addr["x"], addr["y"], CACHE)
    sol, _ = cityapi.solid_for_footprint(h, fp, CACHE)
    faces, shape = esri.decode_feature(sol)
    ring = np.asarray(fp["geometry"]["rings"][0], float)[:-1, :2]

    # ---- model roof plan + terrain
    meshes = load_meshes(a.model)
    roof = [(p, i) for n, mat, p, i in meshes if n.startswith("Roof")]
    tris = np.concatenate([p[i][:, :, [0, 2]] for p, i in roof])  # (x, z)
    tris[:, :, 1] *= -1.0  # z -> north
    terr = [(p, i) for n, mat, p, i in meshes if n.startswith("Terrain")]

    # ---- 1. plan fit, in a local frame around the footprint centroid (grid feet -> metres)
    c0 = ring.mean(0)
    ring_m = (ring - c0) * FT_US
    span = 13.0
    x0 = y0 = -span
    nx = ny = int(2 * span / CELL)
    model_c = tris.reshape(-1, 2).mean(0)

    def model_mask(dx, dy, th):
        c, s = math.cos(th), math.sin(th)
        R = np.array([[c, -s], [s, c]])
        t = (tris - model_c) @ R.T + model_c + (dx, dy)
        return raster_tris(t, x0, y0, nx, ny)

    city = raster_poly(ring_m, x0, y0, nx, ny)

    def cost(v):
        m = model_mask(v[0], v[1], math.radians(v[2]))
        return -(m & city).sum() / (m | city).sum()

    start = (-model_c[0] + (ring_m.mean(0)[0]), -model_c[1] + ring_m.mean(0)[1])
    best = None
    for th in np.arange(-3.0, 3.01, 0.25):  # degrees: grid vs true north is about 1.6 deg here
        for ddx in (-0.3, 0, 0.3):
            for ddy in (-0.3, 0, 0.3):
                v = (start[0] + ddx, start[1] + ddy, th)
                cv = cost(v)
                if best is None or cv < best[0]:
                    best = (cv, v)
    res = optimize.minimize(cost, best[1], method="Nelder-Mead",
                            options={"xatol": 0.005, "fatol": 1e-5, "initial_simplex": np.array(
                                [best[1], np.add(best[1], (0.1, 0, 0)), np.add(best[1], (0, 0.1, 0)),
                                 np.add(best[1], (0, 0, 0.2))])})
    dx, dy, th_deg = res.x
    iou = -res.fun
    mm = model_mask(dx, dy, math.radians(th_deg))
    dist = outline_distance(mm, city)
    # model point (0,0) lands at: R*(0 - model_c) + model_c + (dx,dy) in the grid-metre frame
    th = math.radians(th_deg)
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    o_local = R @ (-model_c) + model_c + (dx, dy)
    origin_city = c0 + o_local / FT_US
    lon, lat = (float(v) for v in proj.city_to_lonlat(origin_city[0], origin_city[1]))
    conv = proj.grid_convergence_deg(lon, lat)
    # a model rotation of th (counter-clockwise, grid frame) means model "north" = grid north rotated by th.
    # True north is grid north rotated clockwise by conv, i.e. by -conv counter-clockwise ... so the model is
    # true-north aligned when th == -conv (within the fit's noise).
    log("plan fit: IoU %.4f, rotation %.3f deg (grid convergence %.3f deg), outline distance %s"
        % (iou, th_deg, conv, dist))

    # ---- 2. height from lidar ground near the house (within 30 m, outside the footprint)
    x0f, y0f, x1f, y1f = cityapi.footprint_bbox(fp)
    pts = lidar.fetch_points(h, (x0f, y0f, x1f, y1f), CACHE, buffer_m=30.0, log=log, max_nodes=200)
    g = pts["cls"] == 2
    # ground points into the model frame (inverse of the plan fit)
    gl = (np.column_stack([pts["x_ft"][g], pts["y_ft"][g]]) - c0) * FT_US
    mod = (gl - model_c - (dx, dy)) @ R + model_c  # R^-1 = R^T, applied as row @ R
    mx, mz = mod[:, 0], -mod[:, 1]
    # model terrain heights: sample the terrain triangles by barycentric lookup on a 0.5 m grid
    T = np.concatenate([p[i] for p, i in terr])
    grid = {}
    for t in T:
        lo = np.floor(t[:, [0, 2]].min(0) / 0.5).astype(int)
        hi = np.floor(t[:, [0, 2]].max(0) / 0.5).astype(int)
        for gx in range(lo[0], hi[0] + 1):
            for gz in range(lo[1], hi[1] + 1):
                grid.setdefault((gx, gz), []).append(t)
    diffs, used = [], []
    for k in range(len(mx)):
        cand_t = grid.get((int(math.floor(mx[k] / 0.5)), int(math.floor(mz[k] / 0.5))), [])
        for t in cand_t:
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
            d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(d) < 1e-12:
                continue
            l1 = ((bz - cz) * (mx[k] - cx) + (cx - bx) * (mz[k] - cz)) / d
            l2 = ((cz - az) * (mx[k] - cx) + (ax - cx) * (mz[k] - cz)) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) >= -1e-6:
                diffs.append(pts["z_m"][g][k] - (l1 * ay + l2 * by + l3 * cy))
                used.append(k)
                break
    diffs = np.array(diffs)
    med = float(np.median(diffs))
    mad = float(np.median(np.abs(diffs - med)) * 1.4826)
    log("height fit: %d lidar ground points on the model terrain, model y=0 is %.3f m NAVD88 (robust sd %.3f m)"
        % (len(diffs), med, mad))

    # roof check: lidar points above 2 m inside the footprint vs the model roof surface height
    roof_tris3 = np.concatenate([p[i] for p, i in roof])
    inside_fp = raster_poly(ring_m, x0, y0, nx, ny)
    allp = (np.column_stack([pts["x_ft"], pts["y_ft"]]) - c0) * FT_US
    ix = ((allp[:, 0] - x0) / CELL).astype(int); iy = ((allp[:, 1] - y0) / CELL).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    on = np.zeros(len(allp), bool); on[ok] = inside_fp[iy[ok], ix[ok]]
    on &= pts["z_m"] > med + 2.5
    rm = (allp[on] - model_c - (dx, dy)) @ R + model_c
    rx, rz = rm[:, 0], -rm[:, 1]
    rd = []
    for k in range(len(rx)):
        best_y = None
        for t in roof_tris3:
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
            d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(d) < 1e-12:
                continue
            l1 = ((bz - cz) * (rx[k] - cx) + (cx - bx) * (rz[k] - cz)) / d
            l2 = ((cz - az) * (rx[k] - cx) + (ax - cx) * (rz[k] - cz)) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) >= -1e-6:
                y = l1 * ay + l2 * by + l3 * cy
                best_y = y if best_y is None else max(best_y, y)
        if best_y is not None:
            rd.append(pts["z_m"][on][k] - med - best_y)
    rd = np.array(rd)
    log("roof check: %d lidar roof returns, lidar minus model roof: median %.3f m, robust sd %.3f m"
        % (len(rd), np.median(rd), np.median(np.abs(rd - np.median(rd))) * 1.4826))

    # the city solid's top vs the model roof top
    solid_top_m = shape["zrange"][1] * FT_US
    model_top = max(p[:, 1].max() for p, i in roof)
    site = {
        "address": addr["address"],
        "footprintOid": fp["attributes"]["OBJECTID"],
        "solidOid": sol["attributes"]["OBJECTID"],
        "originCityFt": [round(float(origin_city[0]), 4), round(float(origin_city[1]), 4)],
        "originLonLat": [round(lon, 9), round(lat, 9)],
        "originElevM": round(med, 3),
        "geoidM": a.geoid,
        "originEllipsoidM": round(med + a.geoid, 3),
        "gridConvergenceDeg": round(conv, 4),
        "modelRotationDeg": round(float(th_deg), 3),
        "modelTrueNorth": bool(abs(th_deg - conv) < abs(th_deg)),
        "modelHeadingDeg": round(float(th_deg - conv), 4),
        "fit": {
            "planIoU": round(float(iou), 4),
            "outlineDistance": dist,
            "groundPoints": int(len(diffs)), "groundRobustSdM": round(mad, 3),
            "roofPoints": int(len(rd)), "roofMedianM": round(float(np.median(rd)), 3),
            "roofRobustSdM": round(float(np.median(np.abs(rd - np.median(rd))) * 1.4826), 3),
            "cityTopMinusModelTopM": round(float(solid_top_m - (med + model_top)), 3),
        },
        "frames": "scene x = east, y = up (NAVD88 - originElevM), z = -north; the studio then shifts "
                  "the model by its bounding box (read glbRoot.position at runtime)",
        "attribution": "Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP.",
    }
    # the model frame is the fitted one: rotation th from grid. Other tools convert city -> model with this.
    site["gridToModelDeg"] = round(float(-th_deg), 4)
    write_json(os.path.join(DATA, "site.json"), site, indent=1)
    log("wrote", os.path.join(DATA, "site.json"))


if __name__ == "__main__":
    main()
