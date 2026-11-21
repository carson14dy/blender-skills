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
--cutouts cuts pits (window wells) out of the ground and every surface; the grid cells they touch are
dropped and the draped overlays around them close the hole exactly at the polygon edge.
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


def _wing_union(model):
    import math
    polys = []
    for w in model["wings"]:
        if w.get("roof_only"):
            continue
        t = math.radians(w["azimuth"])
        u = np.array([math.sin(t), math.cos(t)]); v = np.array([-u[1], u[0]])
        cxy = np.array([w["cx"], w["cy"]])
        L, W = w["length"] / 2, w["width"] / 2
        polys.append(Polygon([cxy + s * L * u + r * W * v for s, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
    return unary_union(polys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ground", default="auto", choices=["auto", "class2", "filtered"],
                    help="terrain from class-2 returns, or a filtered ground surface (auto: filtered when <10%% are class 2)")
    ap.add_argument("--ground-exclude", help="json list of polygons that are never ground (decks, a garage under a deck)")
    ap.add_argument("--keep-rocks", action="store_true", help="filtered terrain: keep boulders/outcrops from no-canopy last returns")
    ap.add_argument("--rock-max", type=float, default=4.5, help="max height of a kept rock above the filtered ground (m)")
    ap.add_argument("--canopy-frac", type=float, default=0.2, help="cells with more multi-return pulses than this are canopy")
    ap.add_argument("--paving-like", help="json polygons where returns are not terrain (street with cars, driveways)")
    ap.add_argument("--house-extra", help="json list of polygons treated as building (no lawn/beds; e.g. a garage under a deck)")
    ap.add_argument("project"); ap.add_argument("features"); ap.add_argument("out")
    ap.add_argument("--half", type=float, default=34.0); ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--bed-width", type=float, default=0.9, help="rock bed band around the walls (m)")
    ap.add_argument("--beds", help="json list of extra bed polygons [[x,y],...] (e.g. under decks)")
    ap.add_argument("--paving", help="json list of extra concrete polygons [[x,y],...] (aprons, stoops the GIS misses)")
    ap.add_argument("--cutouts", help="json list of polygons [[x,y],...] cut out of the ground and every surface "
                                      "(window-well pits, stair wells); add_site.py builds what goes in the hole")
    ap.add_argument("--address", help="parcel ADDRESS to outline as the subject lot")
    ap.add_argument("--subject-only", action="store_true",
                    help="drop private paving (driveways, patios, walks) that does not touch the subject parcel "
                         "(needs --address); streets and public sidewalk centre-lines are kept")
    ap.add_argument("--edging", type=float, default=0.0,
                    help="emit landscape edging lines along rock-bed/lawn boundaries longer than this many metres (0 = off)")
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
    if a.ground == "filtered" or (a.ground == "auto" and len(g) < 0.1 * len(pts)):
        # LiDAR delivered with few class-2 points (e.g. Montana statewide QL1): find the ground with the
        # progressive morphological filter on last returns; the house, decks and anything listed in
        # --ground-exclude can never be ground (they are bridged from the grade around them)
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from propmodel import lidar as L
        ex = [_wing_union(model).buffer(1.0)]
        if a.ground_exclude:
            ex += [Polygon(q).buffer(0) for q in json.load(open(a.ground_exclude))]
        exu = unary_union(ex)
        surf = L.ground_surface(pts, cell=c, exclude=exu)
        Z = L.surface_z(surf, X.ravel(), Y.ravel()).reshape(X.shape) - datum
        print(f"terrain: filtered ground surface ({int(surf['ground'].sum())} ground cells)")
        if a.keep_rocks:
            # the morphological filter shaves boulders and rock outcrops (real terrain). Where no pulse split
            # (no canopy), take the lowest last return of each cell instead, unless the cell is building, deck,
            # paving/street (cars) or rises implausibly high above the filtered ground.
            last = pts[:, 4] >= pts[:, 5]
            ii = np.floor((pts[:, 0] - (xs[0] - c / 2)) / c).astype(int)
            jj = np.floor((pts[:, 1] - (ys[0] - c / 2)) / c).astype(int)
            ok = (ii >= 0) & (ii < len(xs)) & (jj >= 0) & (jj < len(ys))
            zmin = np.full(X.shape, np.inf); cnt = np.zeros(X.shape); multi = np.zeros(X.shape)
            np.minimum.at(zmin, (jj[ok & last], ii[ok & last]), pts[ok & last, 2] - datum)
            np.add.at(cnt, (jj[ok], ii[ok]), 1.0)
            np.add.at(multi, (jj[ok], ii[ok]), (pts[ok, 5] > 1).astype(float))
            canopy = multi / np.maximum(cnt, 1) > a.canopy_frac
            from scipy.ndimage import binary_dilation
            canopy = binary_dilation(canopy, iterations=1)       # trunks and branch edges next to canopy cells
            keep = np.isfinite(zmin) & ~canopy & (zmin - Z < a.rock_max) & (zmin - Z > -0.5)
            nog = unary_union([exu.buffer(0.5)] + [Polygon(q).buffer(0) for q in (json.load(open(a.paving_like)) if a.paving_like else [])])
            keep &= ~shapely.contains_xy(nog, X, Y)
            Z = np.where(keep, zmin, Z)
            print(f"terrain: {int(keep.sum())} cells keep their rock/grade returns ({100 * keep.mean():.0f} %)")
    else:
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
    if a.house_extra:
        house = unary_union([house] + [Polygon(q).buffer(0) for q in json.load(open(a.house_extra))])
    imp = F.get("impervious", [])
    street = polys_of(imp, lambda p: p.get("SurfaceUse") == "Street" or p.get("SurfaceType") == "Paved Street")
    concrete = polys_of(imp, lambda p: not (p.get("SurfaceUse") == "Street" or p.get("SurfaceType") == "Paved Street"))
    if a.subject_only and a.address:
        subj = polys_of([fe for fe in F.get("parcels", []) if (fe.get("props") or {}).get("ADDRESS") == a.address])
        if not subj.is_empty:
            keep = subj.buffer(0.5)
            private = [fe for fe in imp if not (fe.get("props", {}).get("SurfaceUse") == "Street"
                                               or fe.get("props", {}).get("SurfaceType") == "Paved Street")]
            concrete = unary_union([g_ for g_ in (polys_of([fe]) for fe in private) if not g_.is_empty and g_.intersects(keep)]
                                   or [Polygon()])
    sw_lines = []
    for fe in F.get("sidewalk", []):
        wid = float((fe.get("props") or {}).get("WIDTH") or 4) * 0.3048
        for gl in fe["geoms"]:
            if len(gl) >= 2:
                sw_lines.append(LineString(gl).buffer(wid / 2, cap_style="flat"))
    if sw_lines:
        concrete = unary_union([concrete, unary_union(sw_lines).difference(street)])
    if a.paving:
        concrete = unary_union([concrete] + [Polygon(p).buffer(0) for p in json.load(open(a.paving))])
    window = Polygon([(-h, -h), (h, -h), (h, h), (-h, h)])
    street, concrete = street.intersection(window), concrete.intersection(window)
    beds = house.buffer(a.bed_width, join_style="mitre").difference(house) if a.bed_width > 0 else Polygon()
    if a.beds:
        beds = unary_union([beds] + [Polygon(p).buffer(0) for p in json.load(open(a.beds))])
    beds = beds.difference(concrete).difference(street)
    cut = unary_union([Polygon(p).buffer(0) for p in json.load(open(a.cutouts))]) if a.cutouts else Polygon()
    if not cut.is_empty:
        street, concrete, beds = street.difference(cut), concrete.difference(cut), beds.difference(cut)
        # LiDAR returns from inside an existing pit drag the ground down around it: level the grid near each
        # cut-out to the median grade of a ring 0.6-1.5 m outside it
        # (full levelling within 0.6 m, blending back to the LiDAR surface by 1.5 m so no cell is left with a step)
        for pc in getattr(cut, "geoms", [cut]):
            dist = shapely.distance(pc, shapely.points(X.ravel(), Y.ravel())).reshape(X.shape)
            ring = (dist > 1.5) & (dist < 2.5) & ~shapely.contains_xy(house, X, Y)
            if ring.sum() >= 4:
                w = np.clip((1.5 - dist) / 0.9, 0.0, 1.0)
                Z = w * float(np.median(Z[ring])) + (1 - w) * Z

    # face centres
    cx = (X[:-1, :-1] + X[1:, 1:]) / 2
    cy = (Y[:-1, :-1] + Y[1:, 1:]) / 2
    fx, fy = cx.ravel(), cy.ravel()
    cls = np.zeros(fx.shape, int)
    # only grid cells wholly inside the walls are dropped (a cell straddling a wall stays, under the wall),
    # so no gap opens round the house where no overlay covers the ground
    for k, geom in ((1, beds), (2, concrete), (3, street), (4, house.buffer(-c * 0.75))):
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
            if not cut.is_empty and cut.intersects(Polygon([(X[j, i], Y[j, i]), (X[j, i + 1], Y[j, i + 1]),
                                                            (X[j + 1, i + 1], Y[j + 1, i + 1]), (X[j + 1, i], Y[j + 1, i])])):
                continue   # the hole is closed by the overlays around it and by what add_site.py puts in it
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

    def drape(geom, lift, step=None):
        step = step or max(c, 0.25)     # same cells as the terrain grid, so the lawn never pokes through
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
    # landscape edging: bed boundary that faces lawn (not the house, paving or the street)
    edging = []
    if a.edging > 0 and not beds.is_empty:
        hard = unary_union([house.buffer(0.05), concrete.buffer(0.05), street.buffer(0.05)] + ([cut.buffer(0.05)] if not cut.is_empty else []))
        edge = beds.difference(house).boundary.difference(hard.buffer(0.1)).intersection(window.buffer(-0.5))
        for ln in (list(edge.geoms) if hasattr(edge, "geoms") else [edge]):
            if ln.is_empty or ln.length < a.edging:
                continue
            n = max(int(ln.length / 0.4), 1)
            edging.append([[round(ln.interpolate(s / n, normalized=True).x, 3), round(ln.interpolate(s / n, normalized=True).y, 3)]
                           for s in range(n + 1)])
    parcel = None
    for fe in F.get("parcels", []):
        if a.address and (fe.get("props") or {}).get("ADDRESS") == a.address:
            ring = fe["geoms"][0][0]
            parcel = [[x, y] for x, y in ring]
    points = [{"kind": "hydrant", "xy": fe["geoms"][0]} for fe in F.get("hydrants", [])]

    out = {"cell": c, "classes": CLASSES, "verts": np.round(verts, 4).tolist(), "faces": faces, "face_class": fcls,
           "grid": {"x0": float(xs[0]), "y0": float(ys[0]), "nx": int(nx), "ny": int(ny), "cell": c,
                    "z": np.round(Z, 4).ravel().tolist()},
           "overlays": overlays, "curbs": curbs, "edging": edging, "parcel": parcel, "points": points,
           "cutouts": [[[round(x, 3), round(y, 3)] for x, y in g_.exterior.coords] for g_ in getattr(cut, "geoms", [cut]) if not g_.is_empty],
           "stats": {"ground_points": int(len(g)), "z_min": float(np.nanmin(Z)), "z_max": float(np.nanmax(Z)),
                     "street_m2": street.area, "concrete_m2": concrete.area, "bed_m2": beds.area}}
    json.dump(out, open(a.out, "w"))
    print(json.dumps(out["stats"], indent=1), len(faces), "faces")


if __name__ == "__main__":
    main()
