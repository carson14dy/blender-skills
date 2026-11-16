#!/usr/bin/env python3
"""Build the site (terrain + yard surfaces) around a measured house, for add_site.py in Blender.

    python3 build_site.py PROJECT city_features.json OUT/site_scene.json [--half 34] [--cell 0.5]

Terrain = LiDAR ground returns (class 2) in the model datum, linearly interpolated on a grid
(holes under the house are bridged), lightly median-filtered (LiDAR noise ~5 cm). Each grid
face gets a surface class from planimetric polygons (city "impervious surface" or traced):
street, concrete (driveway / sidewalk / walk / patio), rock bed (a band around the walls and
under decks), lawn; faces inside the house walls are dropped. Curbs are emitted along street
edges with heights sampled from the terrain on both sides.

city_features.json (model frame, metres) — as written by the job's GIS step:
  {"impervious": [{"geoms": [[outer, hole...]], "props": {"SurfaceType": "Paved", "SurfaceUse": "Driveway"}}],
   "sidewalk":   [{"geoms": [[x,y],...] (lines), "props": {"WIDTH": 4 (ft)}}],
   "parcels":    [{"geoms": [[outer]], "props": {"ADDRESS": ...}}],
   "hydrants":   [{"geoms": [[x,y]]}]}
Extra keys in the project's details.json-style file can add rock beds (--beds beds.json).
"""
import argparse
import json
import os
import sys

import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiPolygon
from shapely.ops import unary_union
import shapely

CLASSES = ["lawn", "rock_bed", "concrete", "street", "house"]


def polys_of(feats, pred=lambda p: True):
    out = []
    for fe in feats or []:
        if not pred(fe.get("props") or {}):
            continue
        for g in fe["geoms"]:
            try:
                poly = Polygon(g[0], g[1:]) if isinstance(g[0][0], (list, tuple)) else Polygon(g)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                out.append(poly)
            except Exception:
                continue
    return unary_union(out) if out else Polygon()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("features"); ap.add_argument("out")
    ap.add_argument("--half", type=float, default=34.0); ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--bed-width", type=float, default=0.9, help="rock bed band around the walls (m)")
    ap.add_argument("--beds", help="json list of extra bed polygons [[x,y],...] (e.g. under decks)")
    ap.add_argument("--address", help="parcel ADDRESS to outline as the subject lot")
    a = ap.parse_args()

    site = json.load(open(os.path.join(a.project, "site.json")))
    datum = float(site.get("datum_m"))
    model = json.load(open(os.path.join(a.project, "model.json")))
    F = json.load(open(a.features))
    pts = np.load(os.path.join(a.project, "data/lidar_points.npy"))
    g = pts[pts[:, 3] == 2]
    gx, gy, gz = g[:, 0], g[:, 1], g[:, 2] - datum

    # ---- terrain grid -----------------------------------------------------
    from scipy.interpolate import griddata
    from scipy.ndimage import median_filter
    h, c = a.half, a.cell
    xs = np.arange(-h, h + 1e-9, c)
    ys = np.arange(-h, h + 1e-9, c)
    X, Y = np.meshgrid(xs, ys)
    Z = griddata((gx, gy), gz, (X, Y), method="linear")
    Zn = griddata((gx, gy), gz, (X, Y), method="nearest")
    Z = np.where(np.isnan(Z), Zn, Z)
    Z = median_filter(Z, size=3, mode="nearest")

    # ---- surface classes --------------------------------------------------
    wing_polys = []
    for w in model["wings"]:
        if w.get("roof_only"):
            continue
        import math
        t = math.radians(w["azimuth"])
        u = np.array([math.sin(t), math.cos(t)]); v = np.array([-u[1], u[0]])
        cxy = np.array([w["cx"], w["cy"]])
        L, W = w["length"] / 2, w["width"] / 2
        wing_polys.append(Polygon([cxy + s * L * u + r * W * v for s, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
    house = unary_union(wing_polys)
    imp = F.get("impervious", [])
    street = polys_of(imp, lambda p: p.get("SurfaceUse") == "Street" or p.get("SurfaceType") == "Paved Street")
    concrete = polys_of(imp, lambda p: not (p.get("SurfaceUse") == "Street" or p.get("SurfaceType") == "Paved Street"))
    sw_lines = []
    for fe in F.get("sidewalk", []):
        wid = float((fe.get("props") or {}).get("WIDTH") or 4) * 0.3048
        for gl in fe["geoms"]:
            if len(gl) >= 2:
                sw_lines.append(LineString(gl).buffer(wid / 2, cap_style="flat"))
    if sw_lines:
        concrete = unary_union([concrete, unary_union(sw_lines).difference(street)])
    window = Polygon([(-h, -h), (h, -h), (h, h), (-h, h)])
    street, concrete = street.intersection(window), concrete.intersection(window)
    beds = house.buffer(a.bed_width, join_style="mitre").difference(house)
    if a.beds:
        beds = unary_union([beds] + [Polygon(p) for p in json.load(open(a.beds))])
    beds = beds.difference(concrete).difference(street)

    # face centres
    cx = (X[:-1, :-1] + X[1:, 1:]) / 2
    cy = (Y[:-1, :-1] + Y[1:, 1:]) / 2
    fx, fy = cx.ravel(), cy.ravel()
    cls = np.zeros(fx.shape, int)
    for k, geom in ((1, beds), (2, concrete), (3, street), (4, house)):
        if not geom.is_empty:
            cls[shapely.contains_xy(geom, fx, fy)] = k
    # paved surfaces are planar-ish: smooth them more (curb faces come separately)
    ny, nx = Z.shape
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    faces, fcls = [], []
    for j in range(ny - 1):
        for i in range(nx - 1):
            k = j * (nx - 1) + i
            if cls[k] == 4:
                continue
            a0 = j * nx + i
            faces.append([a0, a0 + 1, a0 + nx + 1, a0 + nx])
            fcls.append(0)   # lawn everywhere; paving and beds are crisp draped overlays

    # ---- crisp draped overlays (exact polygon edges, z from the terrain) -----------
    x0g, y0g = xs[0], ys[0]

    def zbil(x, y):
        fi = np.clip((np.asarray(x) - x0g) / c, 0, nx - 1.001)
        fj = np.clip((np.asarray(y) - y0g) / c, 0, ny - 1.001)
        i, j = fi.astype(int), fj.astype(int)
        tx, ty = fi - i, fj - j
        return (Z[j, i] * (1 - tx) * (1 - ty) + Z[j, i + 1] * tx * (1 - ty)
                + Z[j + 1, i] * (1 - tx) * ty + Z[j + 1, i + 1] * tx * ty)

    def drape(geom, lift, step=1.0):
        """Triangulate geom cell by cell (so it follows the terrain) -> verts, tris."""
        verts, tris = [], []
        if geom.is_empty:
            return verts, tris
        bx0, by0, bx1, by1 = geom.bounds
        for gx0 in np.arange(np.floor(bx0 / step) * step, bx1, step):
            for gy0 in np.arange(np.floor(by0 / step) * step, by1, step):
                cellp = geom.intersection(Polygon([(gx0, gy0), (gx0 + step, gy0), (gx0 + step, gy0 + step), (gx0, gy0 + step)]))
                if cellp.is_empty or cellp.area < 1e-4:
                    continue
                for t in shapely.constrained_delaunay_triangles(cellp).geoms:
                    if t.area < 1e-6:
                        continue
                    cs = list(t.exterior.coords)[:3]
                    base = len(verts)
                    for x, y in cs:
                        verts.append([round(x, 4), round(y, 4), round(float(zbil(x, y)) + lift, 4)])
                    tris.append([base, base + 1, base + 2])
        return verts, tris

    overlays = {}
    for name, geom, lift in (("street", street, 0.015), ("concrete", concrete.difference(house), 0.03),
                             ("rock_bed", beds.difference(house), 0.02)):
        v, t = drape(geom.buffer(0), lift)
        overlays[name] = {"verts": v, "tris": t}

    def zat(x, y):
        return float(griddata((X.ravel(), Y.ravel()), Z.ravel(), [(x, y)], method="linear")[0])

    # ---- curbs along street edges -------------------------------------------
    curbs = []
    if not street.is_empty:
        edge = street.boundary.intersection(window.buffer(-0.5))
        lines = list(edge.geoms) if hasattr(edge, "geoms") else [edge]
        for ln in lines:
            if ln.length < 1:
                continue
            n = max(int(ln.length / 1.0), 1)
            poly = []
            for s in range(n + 1):
                p = ln.interpolate(s / n, normalized=True)
                poly.append([p.x, p.y])
            curbs.append(poly)
    parcel = None
    for fe in F.get("parcels", []):
        if a.address and (fe.get("props") or {}).get("ADDRESS") == a.address:
            ring = fe["geoms"][0][0]
            parcel = [[x, y] for x, y in ring]
    points = [{"kind": "hydrant", "xy": fe["geoms"][0]} for fe in F.get("hydrants", [])]

    out = {"cell": c, "classes": CLASSES, "verts": np.round(verts, 4).tolist(), "faces": faces, "face_class": fcls,
           "grid": {"x0": float(xs[0]), "y0": float(ys[0]), "nx": int(nx), "ny": int(ny), "cell": c,
                    "z": np.round(Z, 4).ravel().tolist()},
           "overlays": overlays, "curbs": curbs, "parcel": parcel, "points": points,
           "stats": {"ground_points": int(len(g)), "z_min": float(np.nanmin(Z)), "z_max": float(np.nanmax(Z)),
                     "street_m2": street.area, "concrete_m2": concrete.area, "bed_m2": beds.area}}
    json.dump(out, open(a.out, "w"))
    print(json.dumps(out["stats"], indent=1), len(faces), "faces")


if __name__ == "__main__":
    main()
