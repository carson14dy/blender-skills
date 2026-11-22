#!/usr/bin/env python3
"""Build the site (terrain + yard surfaces) around a measured house, for add_site.py in Blender.

    python3 build_site.py PROJECT city_features.json OUT/site_scene.json [--half 34] [--cell 0.5]

Terrain = LiDAR ground returns (class 2) in the model datum, linearly interpolated on a grid
(holes under the house are bridged), lightly median-filtered (LiDAR noise ~5 cm). Each grid
face gets a surface class from planimetric polygons (city "impervious surface" or traced):
street, concrete (driveway / sidewalk / walk / patio), rock bed (a band around the walls and
under decks), lawn; faces inside the house walls are dropped (not under a storey that cantilevers over
open ground: standing_cells). Curbs are emitted along street
edges with heights sampled from the terrain on both sides.

city_features.json (model frame, metres) — as written by the job's GIS step:
  {"impervious": [{"geoms": [[outer, hole...]], "props": {"SurfaceType": "Paved", "SurfaceUse": "Driveway"}}],
   "sidewalk":   [{"geoms": [[x,y],...] (lines), "props": {"WIDTH": 4 (ft)}}],
   "parcels":    [{"geoms": [[outer]], "props": {"ADDRESS": ...}}],
   "hydrants":   [{"geoms": [[x,y]]}]}
   "curbs":      [{"geoms": [[x,y],...] (lines)}]   optional: only these edges get a curb (default: every
                 street edge; a bank meeting the asphalt has none). No curb within --curb-cut of a driveway.
   "rocks":      [{"geoms": [[outer]]}]              optional traced boulder / outcrop outlines (rock faces)
Extra keys in the project's details.json-style file can add rock beds (--beds beds.json).
--cutouts cuts pits (window wells) out of the ground and every surface; the grid cells they touch are
dropped and the draped overlays around them close the hole exactly at the polygon edge.

Hillside terrain (--ground filtered --keep-rocks): ground = morphological filter on the last returns
(median of each ground cell's lowest returns), then max(ground, solid surface) where the solid surface is
the top of single-return, locally planar returns (bare ground, boulders, outcrops; never canopy), so
boulders keep their measured height. The solid surface is masked only on the roof plan (+ --solid-mask-buffer)
and the decks / excludes / paving-like polygons, and tall patches grow back over their edges (the planarity
window fails on every boulder edge, lidar.merge_solid). Inside traced rock outlines ("rocks" features and,
with --boulders yard.json, boulder items) the terrain also takes the --rock-q quantile of the single returns per
cell (capped at the outline's top_z), and raised nodes are despiked (lidar.despike). Faces the merge raises
(or inside rock outlines) get class "rock". --grade yard.json levels grade_pad items (areaways, patios cut
into the slope; never over rock raised > 0.5 m) and --breaklines yard.json makes the terrain step inside
every retaining_wall item instead of ramping through it. A wall item with "line_is": "face" gives its
exposed (downhill) face; it is extruded to the uphill side ("uphill": "left"|"right" of the line direction,
or found from the terrain). Draped overlays are cut out of every wall footprint and lie exactly on the terrain
triangles (drape_on_mesh), so they meet wall faces and rough ground without gaps or flaps; their triangles
are wound counter-clockwise (normals up). Each terrain cell is folded along the diagonal whose nodes differ
less in height (split_diagonals); the quad is written so that its own 0-2 diagonal is that fold, and
add_site.py triangulates along it, so the drapes and the rendered terrain use the same triangles.
Use --cell 0.25 near a house (QL1 LiDAR has ~2 returns per 0.25 m cell).
"""
import argparse
import json
import os
import sys

import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiPolygon
from shapely.ops import unary_union
import shapely

CLASSES = ["ground", "rock_bed", "concrete", "street", "house", "rock"]   # face_class indexes this ("ground": soil / grass)


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


def _wing_poly(w):
    import math
    if w.get("walls"):
        return Polygon(w["walls"]).buffer(0)
    t = math.radians(w["azimuth"])
    u = np.array([math.sin(t), math.cos(t)]); v = np.array([-u[1], u[0]])
    cxy = np.array([w["cx"], w["cy"]])
    L, W = w["length"] / 2, w["width"] / 2
    return Polygon([cxy + s * L * u + r * W * v for s, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def standing_cells(wings, extra_polys, Z, fx, fy, c, raised=(), tol=0.5):
    """Grid cells (centres fx, fy) wholly inside the house where it stands on the ground: inside a wing that
    reaches the ground, or a --house-extra polygon, or inside a `raised` wing (an upper storey whose walls stand
    on another storey: add_site.py keep_wall_bottoms) where the cell's mean terrain height is no more than `tol`
    below that wing's base_z (where it meets the hillside). Ground under a raised storey that overhangs open
    ground stays, so no hole opens between the lower walls and the overhang's wall line."""
    zc = ((Z[:-1, :-1] + Z[:-1, 1:] + Z[1:, :-1] + Z[1:, 1:]) / 4).ravel()
    out = np.zeros(fx.shape, bool)
    for w in wings:
        if w.get("roof_only"):
            continue
        ins = shapely.contains_xy(_wing_poly(w).buffer(-c * 0.75), fx, fy)
        out |= ins & ((zc >= float(w.get("base_z", 0.0)) - tol) if w.get("id") in raised else True)
    for pg in extra_polys:
        out |= shapely.contains_xy(pg.buffer(-c * 0.75), fx, fy)
    return out


def _wing_union(model):
    import math
    polys = []
    for w in model["wings"]:
        if w.get("roof_only"):
            continue
        if w.get("walls"):
            polys.append(_wing_poly(w)); continue
        t = math.radians(w["azimuth"])
        u = np.array([math.sin(t), math.cos(t)]); v = np.array([-u[1], u[0]])
        cxy = np.array([w["cx"], w["cy"]])
        L, W = w["length"] / 2, w["width"] / 2
        polys.append(Polygon([cxy + s * L * u + r * W * v for s, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))]))
    return unary_union(polys)


def offset_line(line, dist):
    """Polyline offset by ``dist`` to its left (negative: right), mitred joints (mitre length capped)."""
    P = np.asarray(line, float)
    if len(P) < 2:
        return P.tolist()
    d = np.diff(P, axis=0)
    ln = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
    nrm = np.column_stack([-d[:, 1], d[:, 0]]) / ln[:, None]
    out = []
    for k in range(len(P)):
        if k == 0 or k == len(P) - 1:
            n = nrm[min(k, len(nrm) - 1)]
        else:
            m = nrm[k - 1] + nrm[k]
            mn = np.hypot(*m)
            m = m / mn if mn > 1e-9 else nrm[k]
            n = m / max(float(m @ nrm[k]), 0.35)
        out.append((P[k] + dist * n).tolist())
    return out


def uphill_side(line, thickness, zfun, reach=0.5):
    """+1 when the grade left of the line (direction of travel) is higher than on its right, else -1:
    the length-weighted mean of zfun sampled ``thickness + reach`` either side of each segment midpoint."""
    P = np.asarray(line, float)
    acc = 0.0
    for a_, b_ in zip(P[:-1], P[1:]):
        d = b_ - a_; ln = float(np.hypot(*d))
        if ln < 1e-6:
            continue
        n = np.array([-d[1], d[0]]) / ln; m = (a_ + b_) / 2; off = thickness + reach
        acc += ln * (float(zfun(*(m + off * n))) - float(zfun(*(m - off * n))))
    return 1 if acc >= 0 else -1


def wall_lines(data, zfun=None):
    """Retaining-wall lines for breaklines: a yard.json dict (items of kind retaining_wall) or a list of
    {"line": [[x,y],...], "thickness": t} -> [(centre line, thickness)].

    ``"line_is": "face"``: the line is the wall's exposed (downhill) face, as measured from the LiDAR step;
    the wall is extruded to the uphill side: ``"uphill": "left"|"right"`` (of the line direction) or, when
    absent, the side where ``zfun(x, y)`` (the terrain) is higher. Default: the line is the centre."""
    items = data.get("items", []) if isinstance(data, dict) else data
    out = []
    for it in items:
        if not (isinstance(it, dict) and it.get("line") and it.get("kind", "retaining_wall") == "retaining_wall"):
            continue
        th = float(it.get("thickness", 0.3))
        line = it["line"]
        if it.get("line_is", "centre") == "face":
            side = {"left": 1, "right": -1}.get(it.get("uphill"))
            if side is None:
                if zfun is None:
                    raise ValueError(f"wall {it.get('name')}: line_is face needs 'uphill' or a terrain")
                side = uphill_side(line, th, zfun)
            line = offset_line(line, side * th / 2)
        out.append((line, th))
    return out


def rock_outlines(features, boulders=None):
    """Traced rock outlines: features "rocks" (props top_z optional) and yard boulder items
    ({"kind": "boulder", "polygon", "top_z"}) -> [(Polygon, top_z or None)]."""
    out = []
    for fe in (features or {}).get("rocks", []):
        tz = (fe.get("props") or {}).get("top_z")
        for g in fe["geoms"]:
            ring = g[0] if isinstance(g[0][0], (list, tuple)) else g
            pg = Polygon(ring).buffer(0)
            if not pg.is_empty:
                out.append((pg, None if tz is None else float(tz)))
    items = boulders.get("items", []) if isinstance(boulders, dict) else (boulders or [])
    for it in items:
        if isinstance(it, dict) and it.get("kind") == "boulder" and it.get("polygon"):
            pg = Polygon(it["polygon"]).buffer(0)
            if not pg.is_empty:
                out.append((pg, float(it["top_z"]) if "top_z" in it else None))
    return out


def roof_plan(model, overhang=0.5):
    """Plan outline of the roof (model.json facets), or the wings buffered by ``overhang`` when there are none."""
    polys = []
    for f in model.get("facets", []):
        for p in f.get("polygons", []):
            if isinstance(p, dict):
                polys.append(Polygon(np.array(p["outer"])[:, :2], [np.array(h)[:, :2] for h in p.get("holes", [])]).buffer(0))
            else:
                polys.append(Polygon(np.array(p)[:, :2]).buffer(0))
    if polys:
        return unary_union(polys)
    return _wing_union(model).buffer(overhang)


def grade_pads(data):
    """Flat pads: a list of {polygon, z[, blend]} or a yard.json dict (items of kind grade_pad)."""
    items = data.get("items", []) if isinstance(data, dict) else data
    return [it for it in items if isinstance(it, dict) and it.get("polygon") and "z" in it
            and it.get("kind", "grade_pad") == "grade_pad"]


def align_apron(drive, front, reach=2.5):
    """Make the driveway meet a garage front line exactly: the part of the driveway within `reach` of the
    front is extended up to the line (hull of its near vertices and the line) and anything beyond the
    line (under the garage) is cut off. `drive` is a shapely (Multi)Polygon, `front` [[x,y],[x,y]]."""
    from shapely.geometry import MultiPoint
    (ax_, ay_), (bx_, by_) = front
    F = LineString(front)
    d = np.array([bx_ - ax_, by_ - ay_], float); d /= np.linalg.norm(d); n = np.array([-d[1], d[0]])
    cen = np.array(drive.centroid.coords[0])
    if (cen - [ax_, ay_]) @ n > 0:
        n = -n                                     # n points from the line into the building
    near = [pt for g_ in getattr(drive, "geoms", [drive]) for pt in g_.exterior.coords if F.distance(Point(pt)) < reach]
    if not near:
        return drive
    fill = MultiPoint(near + list(front)).convex_hull
    big = 200.0
    beyond = Polygon([(ax_ - d[0] * big, ay_ - d[1] * big), (bx_ + d[0] * big, by_ + d[1] * big),
                      (bx_ + d[0] * big + n[0] * big, by_ + d[1] * big + n[1] * big),
                      (ax_ - d[0] * big + n[0] * big, ay_ - d[1] * big + n[1] * big)])
    # only clip what lies within the front's own span (+ reach), so the rest of the driveway is untouched
    span = F.buffer(reach, cap_style="flat")
    return unary_union([drive, fill.intersection(span)]).difference(beyond.intersection(span))


def side_grade(zf, ax_, ay_, d, n, s, t, th, band, reach=0.35, run=0.5, max_slope=1.5, blocked=None):
    """Grade at signed offset ``t`` from a wall segment (point a, unit direction d, left normal n, station s),
    from the surface ``zf`` on that side only: sampled ``band + reach`` and ``band + reach + run`` out (beyond
    the smeared step) and extrapolated linearly back to max(|t|, th / 2), so a sloping bed or drive keeps its
    slope up to the wall face instead of being levelled at the far sample.

    ``blocked(x, y)`` -> bool array: sample points there are unusable (inside another wall's band: a narrow
    strip between two walls must not take the grade from beyond the other wall); the sample then moves in
    to ``band`` and then just outside the face (no slope), else the surface at the point itself is kept."""
    s = np.atleast_1d(np.asarray(s, float)); t = np.atleast_1d(np.asarray(t, float))
    sg = np.where(t >= 0, 1.0, -1.0)
    px = lambda dist: ax_ + s * d[0] + sg * dist * n[0]
    py = lambda dist: ay_ + s * d[1] + sg * dist * n[1]
    blk = blocked or (lambda x, y: np.zeros(np.shape(x), bool))
    dn = np.maximum(np.abs(t), th / 2)
    out = np.full(t.shape, np.nan)
    d1, d2 = band + reach, band + reach + run
    ok = ~blk(px(d1), py(d1)) & ~blk(px(d2), py(d2))
    if ok.any():
        z1 = zf(px(d1), py(d1)); z2 = zf(px(d2), py(d2))
        g = np.clip((z2 - z1) / run, -max_slope, max_slope)
        out = np.where(ok, z1 + g * (dn - d1), out)
    for dist in (band, th / 2 + 0.5 * (band - th / 2)):
        todo = np.isnan(out)
        if not todo.any():
            break
        okd = todo & ~blk(px(dist), py(dist))
        if okd.any():
            out = np.where(okd, zf(px(dist), py(dist)), out)
    todo = np.isnan(out)
    if todo.any():
        here_x = ax_ + s * d[0] + t * n[0]; here_y = ay_ + s * d[1] + t * n[1]
        out = np.where(todo, zf(here_x, here_y), out)
    return out


def _band_owner(walls, X, Y, c):
    """Integer grid: index of the wall whose breakline band (half thickness + 1.5 cells) holds each node, -1 for
    none, -2 for nodes in the bands of several walls."""
    own = np.full(X.shape, -1)
    for k, (line, th) in enumerate(walls):
        m = shapely.contains_xy(LineString(line).buffer(th / 2 + 1.5 * c), X, Y)
        own = np.where(m & (own == -1), k, np.where(m & (own != -1) & (own != k), -2, own))
    return own


def _blocker(own, k, x0, y0, c):
    """blocked(x, y) for wall k: the nearest node lies in another wall's band."""
    ny, nx = own.shape

    def f(x, y):
        i = np.clip(np.rint((np.asarray(x) - x0) / c).astype(int), 0, nx - 1)
        j = np.clip(np.rint((np.asarray(y) - y0) / c).astype(int), 0, ny - 1)
        o = own[j, i]
        return (o != -1) & (o != k)
    return f


def apply_breaklines(Z, xs, ys, walls, c, reach=0.35, snap=None):
    """Grid nodes within half a wall thickness + 1.5 cells of a wall segment take the grade of their own side
    (side_grade: sampled ``reach`` m beyond that band from the unmodified surface and extrapolated back along its
    slope): the step happens inside the wall instead of as a ramp poking out of its faces.

    ``snap`` (a pair of node-coordinate arrays [X, Y], modified in place): nodes within half a thickness
    + one cell of the wall line are also moved onto the wall face on their side, so every terrain
    triangle that crosses the wall runs from one face to the other, inside the wall (a grid cell is as
    wide as a wall is thick, so without it a ramp would stand out of the face)."""
    Z0 = Z.copy()
    X, Y = np.meshgrid(xs, ys)
    x0, y0 = xs[0], ys[0]
    ny, nx = Z.shape

    def zb(x, y):
        fi = np.clip((x - x0) / c, 0, nx - 1.001); fj = np.clip((y - y0) / c, 0, ny - 1.001)
        i, j = fi.astype(int), fj.astype(int); tx, ty = fi - i, fj - j
        return (Z0[j, i] * (1 - tx) * (1 - ty) + Z0[j, i + 1] * tx * (1 - ty)
                + Z0[j + 1, i] * (1 - tx) * ty + Z0[j + 1, i + 1] * tx * ty)
    own = _band_owner(walls, X, Y, c)
    for k, (line, th) in enumerate(walls):
        band = th / 2 + 1.5 * c
        blocked = _blocker(own, k, x0, y0, c)
        for (ax_, ay_), (bx_, by_) in zip(line[:-1], line[1:]):
            d = np.array([bx_ - ax_, by_ - ay_], float); ln = float(np.hypot(*d))
            if ln < 1e-6:
                continue
            d /= ln; n = np.array([-d[1], d[0]])
            s = (X - ax_) * d[0] + (Y - ay_) * d[1]
            t = (X - ax_) * n[0] + (Y - ay_) * n[1]
            m = (s >= 0) & (s <= ln) & (np.abs(t) <= band)
            if not m.any():
                continue
            Z[m] = side_grade(zb, ax_, ay_, d, n, s[m], t[m], th, band, reach, blocked=blocked)
            if snap is not None:
                ms = (s >= 0) & (s <= ln) & (np.abs(t) < th / 2 + c)
                sg = np.sign(t[ms]); sg[sg == 0] = 1
                snap[0][ms] = ax_ + s[ms] * d[0] + sg * (th / 2) * n[0]
                snap[1][ms] = ay_ + s[ms] * d[1] + sg * (th / 2) * n[1]
    return Z


def split_diagonals(Z):
    """Per grid cell, the diagonal the terrain quad is folded along: True = (j,i+1)-(j+1,i), False =
    (j,i)-(j+1,i+1). Each cell takes the diagonal whose two nodes differ less in height, so ridges and
    valleys run along the fold instead of across it (a warped cell split the other way renders as a dark
    folded shard on a slope or a boulder flank)."""
    d02 = np.abs(Z[1:, 1:] - Z[:-1, :-1])
    d13 = np.abs(Z[:-1, 1:] - Z[1:, :-1])
    return d13 < d02 - 1e-9


def quad_face(j, i, nx, alt):
    """Vertex indices of grid cell (j, i), counter-clockwise from above, ordered so that the face's own
    0-2 diagonal is the fold chosen by split_diagonals (add_site.py splits every quad along 0-2)."""
    a0 = j * nx + i
    return [a0 + 1, a0 + nx + 1, a0 + nx, a0] if alt else [a0, a0 + 1, a0 + nx + 1, a0 + nx]


def _ccw(cs):
    """Triangle corner list in counter-clockwise (normal up) order."""
    (x0_, y0_), (x1_, y1_), (x2_, y2_) = [c_[:2] for c_ in cs]
    return cs[::-1] if (x1_ - x0_) * (y2_ - y0_) - (x2_ - x0_) * (y1_ - y0_) < 0 else cs


def drape_on_mesh(geom, NX, NY, Z, lift, faces_ok=None, alt=None):
    """Drape polygon(s) ``geom`` exactly on the terrain mesh: grid nodes at (NX, NY, Z) (2-D arrays; nodes may
    be moved off the regular grid, e.g. snapped onto wall faces), each quad (j,i)-(j,i+1)-(j+1,i+1)-(j+1,i) split
    along its (j,i)-(j+1,i+1) diagonal as the mesh faces are, or along (j,i+1)-(j+1,i) where ``alt`` (bool
    [ny-1, nx-1], from split_diagonals) is set. Every piece of ``geom`` inside a terrain triangle
    gets that triangle's plane + ``lift``, so the overlay coincides with the terrain (no terrain poking through
    on rough ground, no overlay floating over a twisted cell, clean meeting with wall faces).
    ``faces_ok`` (bool [ny-1, nx-1]): quads that exist in the terrain mesh. Returns (verts, tris); every
    triangle is wound counter-clockwise seen from above (normal +z), so viewers that cull back faces keep it."""
    verts, tris = [], []
    if geom is None or geom.is_empty:
        return verts, tris
    ny, nx = Z.shape
    bx0, by0, bx1, by1 = geom.bounds
    # candidate quads: node bounding boxes overlapping the geometry bounds (nodes move less than a cell)
    qx0 = np.minimum.reduce([NX[:-1, :-1], NX[:-1, 1:], NX[1:, :-1], NX[1:, 1:]])
    qx1 = np.maximum.reduce([NX[:-1, :-1], NX[:-1, 1:], NX[1:, :-1], NX[1:, 1:]])
    qy0 = np.minimum.reduce([NY[:-1, :-1], NY[:-1, 1:], NY[1:, :-1], NY[1:, 1:]])
    qy1 = np.maximum.reduce([NY[:-1, :-1], NY[:-1, 1:], NY[1:, :-1], NY[1:, 1:]])
    cand = (qx1 >= bx0) & (qx0 <= bx1) & (qy1 >= by0) & (qy0 <= by1)
    if faces_ok is not None:
        cand &= faces_ok
    if alt is None:
        alt = np.zeros(cand.shape, bool)
    if not cand.any():
        return verts, tris
    shapely.prepare(geom)
    for corners, flag in ((((0, 0), (0, 1), (1, 1)), False), (((0, 0), (1, 1), (1, 0)), False),
                          (((0, 0), (0, 1), (1, 0)), True), (((0, 1), (1, 1), (1, 0)), True)):
        jj, ii = np.nonzero(cand & (alt == flag))
        if not len(jj):
            continue
        P = np.stack([np.column_stack([NX[jj + dj, ii + di], NY[jj + dj, ii + di], Z[jj + dj, ii + di]])
                      for dj, di in corners], 1)                         # [n, 3 corners, xyz]
        polys = shapely.polygons(P[:, :, :2])
        good = shapely.area(polys) > 1e-9
        inside = good & shapely.contains(geom, polys)
        part = good & ~inside & shapely.intersects(geom, polys)
        # plane z = a x + b y + c of every triangle
        A = np.concatenate([P[:, :, :2], np.ones((len(P), 3, 1))], 2)
        coef = np.full((len(P), 3), np.nan)
        ok = good & (inside | part)
        coef[ok] = np.linalg.solve(A[ok], P[ok, :, 2][..., None])[..., 0]
        for k in np.nonzero(inside)[0]:
            b0 = len(verts)
            verts += [[round(float(x), 4), round(float(y), 4), round(float(z) + lift, 4)] for x, y, z in _ccw(list(P[k]))]
            tris.append([b0, b0 + 1, b0 + 2])
        kp = np.nonzero(part)[0]
        if len(kp):
            pieces = shapely.intersection(geom, polys[kp])
            for k, pc in zip(kp, pieces):
                if pc.is_empty or pc.area < 1e-6:
                    continue
                a_, b_, c_ = coef[k]
                for t in shapely.constrained_delaunay_triangles(pc).geoms:
                    if t.area < 1e-7:
                        continue
                    cs = _ccw(list(t.exterior.coords)[:3])              # counter-clockwise: normals up
                    b0 = len(verts)
                    for x, y in cs:
                        verts.append([round(x, 4), round(y, 4), round(float(a_ * x + b_ * y + c_) + lift, 4)])
                    tris.append([b0, b0 + 1, b0 + 2])
    return verts, tris


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ground", default="auto", choices=["auto", "class2", "filtered"],
                    help="terrain from class-2 returns, or a filtered ground surface (auto: filtered when <10%% are class 2)")
    ap.add_argument("--ground-exclude", help="json list of polygons that are never ground (decks, a garage under a deck)")
    ap.add_argument("--keep-rocks", action="store_true", help="filtered terrain: keep boulders/outcrops from no-canopy last returns")
    ap.add_argument("--rocks", default="solid", choices=["solid", "lowest"],
                    help="--keep-rocks method. solid (default): terrain = max(ground, solid surface) where solid = cells whose "
                         "neighbourhood is single-return and planar (lidar.solid_surface); lowest: lowest last return of "
                         "every no-canopy cell (older, noisier: shrub tops become ground)")
    ap.add_argument("--rock-max", type=float, default=4.5, help="max height of a kept rock above the filtered ground (m)")
    ap.add_argument("--canopy-frac", type=float, default=0.2, help="cells with more multi-return pulses than this are canopy")
    ap.add_argument("--solid-single", type=float, default=0.9, help="solid surface: min single-return fraction within --solid-radius")
    ap.add_argument("--solid-rms", type=float, default=0.2, help="solid surface: max plane-fit RMS within --solid-radius (m)")
    ap.add_argument("--solid-radius", type=float, default=0.6, help="solid surface: neighbourhood half-size (m)")
    ap.add_argument("--solid-rise", type=float, default=1.0,
                    help="solid cells more than this above the ground surface must form a patch of --solid-patch m^2")
    ap.add_argument("--solid-patch", type=float, default=0.75, help="min area (m^2) of a tall solid patch (boulder)")
    ap.add_argument("--solid-mask-buffer", type=float, default=0.3,
                    help="solid surface: never on the roof plan, decks or --ground-exclude polygons grown by this (m)")
    ap.add_argument("--solid-grow", type=int, default=-1,
                    help="rounds of edge growth of tall solid patches (-1: ceil(radius / cell) + 1; 0 = off)")
    ap.add_argument("--boulders", help="yard.json whose boulder items (polygon, top_z) count as traced rock outlines")
    ap.add_argument("--rock-q", type=float, default=0.9,
                    help="inside traced rock outlines the terrain takes this quantile of the single returns per cell "
                         "(not above the outline's top_z + 0.1; 0 = off)")
    ap.add_argument("--despike", type=float, default=0.3,
                    help="rock-raised nodes: z = min(z, 3x3 median + this), then a Gaussian of --despike-sigma (0 = off)")
    ap.add_argument("--despike-sigma", type=float, default=0.25, help="Gaussian sigma (m) of the despike pass")
    ap.add_argument("--despike-edge", type=float, default=0.0,
                    help="presentation option: nodes raised more than this next to unraised ground (the outline teeth of a "
                         "boulder patch, which cast shard shadows) take the full Gaussian, unclamped. Off by default: it "
                         "rounds small boulders well below their LiDAR tops (0 = off)")
    ap.add_argument("--despike-passes", type=int, default=2, help="passes of the edge smoothing")
    ap.add_argument("--despike-clamp", type=float, default=0.05,
                    help="the despike Gaussian moves no node by more than this (m), so measured cliff edges stay (0 = no limit)")
    ap.add_argument("--wall-gap", type=float, default=0.0,
                    help="draped overlays stop this far short of every retaining wall's faces (m; they are draped on the "
                         "terrain triangles themselves, which step inside the wall, so 0 meets the face cleanly)")
    ap.add_argument("--rock-face", type=float, default=0.3,
                    help="terrain faces raised more than this by the rock merge get surface class 'rock' (0 = off)")
    ap.add_argument("--ground-cell", type=float, help="cell of the morphological ground filter (default max(--cell, 0.5))")
    ap.add_argument("--ground-stat", default="median", choices=["min", "median"],
                    help="height of a filtered ground cell: lowest return, or median of returns within 0.25 m of it")
    ap.add_argument("--breaklines", help="json with retaining walls (a yard.json: items of kind retaining_wall, or a list of "
                                         "{line, thickness}): grid nodes next to a wall take the grade of their own side, so "
                                         "the terrain steps inside the wall instead of ramping across it")
    ap.add_argument("--raised", help="comma list of wing ids standing on another storey (no ground contact; also read "
                                     "from keep_wall_bottoms in the --grade / --breaklines / --boulders yard.json): "
                                     "ground under their overhangs is kept")
    ap.add_argument("--grade", help="json list of flat pads {polygon, z[, blend]}: terrain inside set to z (areaways, patios "
                                    "cut into a slope), blended back to the surface over `blend` m outside")
    ap.add_argument("--curb-cut", type=float, default=0.6,
                    help="no curb within this distance of a driveway polygon (curb cut at the driveway mouth); 0 = off")
    ap.add_argument("--curb-cut-uses", default="Driveway", help="comma list of SurfaceUse values that cut the curb")
    ap.add_argument("--garage-front", help='json {"front": [[x,y],[x,y]]}: the driveway apron is extended to / cut at this '
                                           "garage-door line (the measured wall face)")
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
    rock_rise = np.zeros(X.shape)          # how far the rock merge raised each node above the filtered ground
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
        surf = L.ground_surface(pts, cell=a.ground_cell or max(c, 0.5), exclude=exu, zstat=a.ground_stat)
        Z = L.surface_z(surf, X.ravel(), Y.ravel()).reshape(X.shape) - datum
        print(f"terrain: filtered ground surface ({int(surf['ground'].sum())} ground cells, {a.ground_stat} per cell)")
        if a.keep_rocks and a.rocks == "solid":
            # boulders and outcrops are real terrain the morphological filter shaves off: take the max of the
            # ground and the solid surface (single-return, planar neighbourhood), never on the building, decks,
            # paving with cars (--paving-like) or rising more than --rock-max
            Zg = median_filter(Z, size=3, mode="nearest")
            loc = np.column_stack([pts[:, :2], pts[:, 2] - datum, pts[:, 3:]])
            sol = L.solid_surface(loc, xs[0] - c / 2, ys[0] - c / 2, len(xs), len(ys), cell=c, radius=a.solid_radius,
                                  min_single=a.solid_single, max_rms=a.solid_rms)
            Zs = sol["Z"]
            # never solid: the roof plan and decks / excludes (+ a small margin; a boulder can stand right at the
            # drip line) and paving with cars. The ground filter above keeps its wider exclusion.
            mb = a.solid_mask_buffer
            nog = unary_union([roof_plan(model).buffer(mb)]
                              + [Polygon(q).buffer(0).buffer(mb) for q in (json.load(open(a.ground_exclude)) if a.ground_exclude else [])]
                              + [Polygon(q).buffer(0) for q in (json.load(open(a.paving_like)) if a.paving_like else [])])
            nogm = shapely.contains_xy(nog, X, Y)
            Zs[nogm] = np.nan
            ngrow = int(np.ceil(a.solid_radius / c)) + 1 if a.solid_grow < 0 else a.solid_grow
            Z, acc = L.merge_solid(Zg, Zs, c, rise=a.solid_rise, min_patch=a.solid_patch, max_rise=a.rock_max,
                                   grow=sol, grow_iter=ngrow, mask=nogm)
            print(f"terrain: solid surface raises {int((Z - Zg > 0.05).sum())} nodes "
                  f"({int((Z - Zg > a.rock_face).sum())} by > {a.rock_face} m, max {(Z - Zg).max():.2f} m; edge growth {ngrow} rounds)")
            # traced rock outlines: the planarity test fails on domed and fractured rock, so take a high quantile
            # of the cell's single returns there (canopy above the outline's top is not rock)
            outl = rock_outlines(F, json.load(open(a.boulders)) if a.boulders else None)
            if outl and a.rock_q > 0:
                s1 = loc[:, 5] == 1
                ii = np.floor((loc[:, 0] - (xs[0] - c / 2)) / c).astype(int)
                jj = np.floor((loc[:, 1] - (ys[0] - c / 2)) / c).astype(int)
                okq = s1 & (ii >= 0) & (ii < len(xs)) & (jj >= 0) & (jj < len(ys))
                q = L.cell_quantile(ii[okq], jj[okq], loc[okq, 2], len(xs), len(ys), a.rock_q)
                cap = np.full(X.shape, -np.inf); inside = np.zeros(X.shape, bool)
                for pg, tz in outl:
                    m_ = shapely.contains_xy(pg, X, Y)
                    inside |= m_
                    cap[m_] = np.maximum(cap[m_], (tz + 0.1) if tz is not None else np.inf)
                with np.errstate(invalid="ignore"):
                    take = inside & ~nogm & np.isfinite(q) & (q > Z) & (q <= cap) & (q - Zg < a.rock_max)
                Z = np.where(take, q, Z)
                print(f"terrain: {len(outl)} rock outlines, {int(take.sum())} nodes raised to the q{a.rock_q:g} single return")
            rock_rise = Z - Zg
            if a.despike > 0:
                from scipy.ndimage import binary_dilation
                raised = rock_rise > 0.05
                # outline of the raised patches: tall nodes next to unraised ground (cell-sized teeth)
                outline = (rock_rise > a.despike_edge) & binary_dilation(~raised, np.ones((3, 3))) if a.despike_edge > 0 else None
                Z = L.despike(Z, raised, c, above=a.despike, sigma=a.despike_sigma,
                              max_change=a.despike_clamp if a.despike_clamp > 0 else None,
                              edge_nodes=outline, passes=a.despike_passes)
                rock_rise = Z - Zg
            print(f"terrain: rock-raised nodes {int((rock_rise > 0.05).sum())} "
                  f"({int((rock_rise > a.rock_face).sum())} by > {a.rock_face} m, max {rock_rise.max():.2f} m)")
        elif a.keep_rocks:
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
    if not (a.keep_rocks and a.rocks == "solid"):
        Z = median_filter(Z, size=3, mode="nearest")      # (the solid merge filtered its ground part already)

    # ---- grade pads and retaining-wall breaklines ------------------------------
    pads = grade_pads(json.load(open(a.grade))) if a.grade else []
    if pads:
        for pad in pads:
            pp = Polygon(pad["polygon"]).buffer(0)
            bl = float(pad.get("blend", 0.0))
            dist = shapely.distance(pp, shapely.points(X.ravel(), Y.ravel())).reshape(X.shape)
            w = np.clip(1.0 - dist / bl, 0.0, 1.0) if bl > 0 else (dist <= 0).astype(float)
            w[(rock_rise > 0.5) & (dist > 0)] = 0.0        # the blend never drags a boulder / outcrop down
            Z = w * float(pad["z"]) + (1 - w) * Z
            print(f"terrain: grade pad z={pad['z']} over {pp.area:.1f} m2")
    _Zw = Z.copy()

    def _zw(x, y):
        fi = np.clip((x - xs[0]) / c, 0, len(xs) - 1.001); fj = np.clip((y - ys[0]) / c, 0, len(ys) - 1.001)
        i_, j_ = int(fi), int(fj); tx, ty = fi - i_, fj - j_
        return (_Zw[j_, i_] * (1 - tx) * (1 - ty) + _Zw[j_, i_ + 1] * tx * (1 - ty)
                + _Zw[j_ + 1, i_] * (1 - tx) * ty + _Zw[j_ + 1, i_ + 1] * tx * ty)
    walls = wall_lines(json.load(open(a.breaklines)), zfun=_zw) if a.breaklines else []
    node_xy = [X.copy(), Y.copy()]          # mesh vertex positions (nodes next to walls move onto the faces)
    if walls:
        Z = apply_breaklines(Z, xs, ys, walls, c, snap=node_xy)
        print(f"terrain: {len(walls)} retaining-wall breaklines")

    # ---- surface classes --------------------------------------------------
    house = unary_union([_wing_poly(w) for w in model["wings"] if not w.get("roof_only")])
    extra_polys = [Polygon(q).buffer(0) for q in json.load(open(a.house_extra))] if a.house_extra else []
    if extra_polys:
        house = unary_union([house] + extra_polys)
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
    if a.garage_front and os.path.exists(a.garage_front):
        gf = json.load(open(a.garage_front))
        gf = gf.get("front", gf) if isinstance(gf, dict) else gf
        before = concrete.area
        concrete = align_apron(concrete, gf[:2])
        print(f"paving: apron aligned to the garage front {gf[:2]} ({concrete.area - before:+.1f} m2)")
    # traced boulder / outcrop outlines (faces inside get the rock class)
    rocks = unary_union([pg for pg, _ in rock_outlines(F, json.load(open(a.boulders)) if a.boulders else None)] or [Polygon()])
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
    raised = set(a.raised.split(",")) if a.raised else set()
    for yj in {a.grade, a.breaklines, a.boulders} - {None}:
        yd = json.load(open(yj))
        if isinstance(yd, dict):
            raised |= set(yd.get("keep_wall_bottoms", []))
    if raised:   # ground stays under a raised storey that overhangs open ground
        cls[(cls == 4) & ~standing_cells(model["wings"], extra_polys, Z, fx, fy, c, raised)] = 0
    in_rock = shapely.contains_xy(rocks, fx, fy) if not rocks.is_empty else np.zeros(fx.shape, bool)
    # rock faces: raised by the rock merge, or inside a traced rock outline; plus the steep flanks next to them
    # (> 45 deg within two faces), so a boulder is stone down to its foot instead of only on its top
    nyf, nxf = Z.shape[0] - 1, Z.shape[1] - 1
    rrf = rock_rise[:-1, :-1] + rock_rise[:-1, 1:] + rock_rise[1:, :-1] + rock_rise[1:, 1:]
    rockf = (rrf > 4 * a.rock_face) if a.rock_face > 0 else np.zeros((nyf, nxf), bool)
    rockf |= (in_rock & (cls == 0)).reshape(nyf, nxf)
    if rockf.any():
        from scipy.ndimage import binary_dilation as _bd
        gzx = (Z[:-1, 1:] + Z[1:, 1:] - Z[:-1, :-1] - Z[1:, :-1]) / (2 * c)
        gzy = (Z[1:, :-1] + Z[1:, 1:] - Z[:-1, :-1] - Z[:-1, 1:]) / (2 * c)
        rockf |= _bd(rockf, iterations=2) & (np.hypot(gzx, gzy) > 1.0)
    rockf = rockf.ravel()
    # paved surfaces are planar-ish: smooth them more (curb faces come separately)
    ny, nx = Z.shape
    verts = np.column_stack([node_xy[0].ravel(), node_xy[1].ravel(), Z.ravel()])
    faces, fcls = [], []
    alt = split_diagonals(Z)                       # per-cell fold along the more level diagonal
    faces_ok = np.zeros((ny - 1, nx - 1), bool)
    for j in range(ny - 1):
        for i in range(nx - 1):
            k = j * (nx - 1) + i
            if cls[k] == 4:
                continue
            if not cut.is_empty and cut.intersects(Polygon([(X[j, i], Y[j, i]), (X[j, i + 1], Y[j, i + 1]),
                                                            (X[j + 1, i + 1], Y[j + 1, i + 1]), (X[j + 1, i], Y[j + 1, i])])):
                continue   # the hole is closed by the overlays around it and by what add_site.py puts in it
            faces.append(quad_face(j, i, nx, alt[j, i]))
            faces_ok[j, i] = True
            # ground everywhere (paving and beds are crisp draped overlays), except boulders / outcrops the
            # rock merge raised: those get the rock class (add_site gives them a lighter stone material)
            fcls.append(5 if rockf[k] else 0)

    # ---- crisp draped overlays (exact polygon edges, z from the terrain triangles themselves) -----------
    def drape(geom, lift):
        return drape_on_mesh(geom, node_xy[0], node_xy[1], Z, lift, faces_ok, alt)

    overlays = {}
    # overlays end at the wall faces (+ --wall-gap): the terrain under the wall is the hidden step
    wallpoly = unary_union([LineString(l_).buffer(th / 2 + a.wall_gap, cap_style="flat") for l_, th in walls]) if walls else Polygon()
    for name, geom, lift in (("street", street, 0.015), ("concrete", concrete.difference(house).difference(wallpoly), 0.03),
                             ("rock_bed", beds.difference(house).difference(wallpoly), 0.02)):
        v, t = drape(geom.buffer(0), lift)
        overlays[name] = {"verts": v, "tris": t}

    def zat(x, y):
        return float(griddata((X.ravel(), Y.ravel()), Z.ravel(), [(x, y)], method="linear")[0])

    # ---- curbs along street edges -------------------------------------------
    curbs = []
    if F.get("curbs") is not None:
        # explicit curb lines (a street edge with no raised curb, e.g. a bank meeting the asphalt, gets none)
        lines_ = [LineString(gl) for fe in F["curbs"] for gl in fe["geoms"] if len(gl) >= 2]
        edge = unary_union(lines_).intersection(window.buffer(-0.5)) if lines_ else LineString()
    elif not street.is_empty:
        edge = street.boundary.intersection(window.buffer(-0.5))
    else:
        edge = LineString()
    if not edge.is_empty:
        if a.curb_cut > 0:
            # curb cut: no curb across a driveway mouth (the driveway meets the street flush)
            uses = {u.strip() for u in a.curb_cut_uses.split(",") if u.strip()}
            mouths = polys_of(imp, lambda p: p.get("SurfaceUse") in uses)
            if not mouths.is_empty:
                edge = edge.difference(mouths.buffer(a.curb_cut))
        edge = shapely.line_merge(edge) if edge.geom_type == "MultiLineString" else edge
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

    # per-vertex rock weight (share of the rock faces around each vertex, smoothed once): add_site blends the
    # ground and rock materials with it, so a boulder's edge is a soft transition rather than a sawtooth
    from scipy.ndimage import uniform_filter as _uf
    rk = rockf.reshape(nyf, nxf).astype(float)
    vw = np.zeros((ny, nx)); vn = np.zeros((ny, nx))
    for dj in (0, 1):
        for di in (0, 1):
            vw[dj:dj + nyf, di:di + nxf] += rk; vn[dj:dj + nyf, di:di + nxf] += 1
    vrock = _uf(vw / np.maximum(vn, 1), 5, mode="nearest")
    out = {"cell": c, "classes": CLASSES, "verts": np.round(verts, 4).tolist(), "faces": faces, "face_class": fcls,
           "face_split": "0-2",            # each quad is folded along its own 0-2 diagonal (chosen per cell)
           "vertex_rock": np.round(vrock.ravel(), 2).tolist(),
           "grid": {"x0": float(xs[0]), "y0": float(ys[0]), "nx": int(nx), "ny": int(ny), "cell": c,
                    "z": np.round(Z, 4).ravel().tolist(), "rock_rise": np.round(rock_rise, 2).ravel().tolist()},
           "overlays": overlays, "curbs": curbs, "edging": edging, "parcel": parcel, "points": points,
           "cutouts": [[[round(x, 3), round(y, 3)] for x, y in g_.exterior.coords] for g_ in getattr(cut, "geoms", [cut]) if not g_.is_empty],
           "stats": {"ground_points": int(len(g)), "z_min": float(np.nanmin(Z)), "z_max": float(np.nanmax(Z)),
                     "cell": c, "nodes": int(Z.size), "rock_faces": int(sum(1 for v in fcls if v == 5)),
                     "cells_folded_13": int(alt[faces_ok].sum()),
                     "rock_raised_nodes": int((rock_rise > 0.05).sum()), "curb_lines": len(curbs),
                     "street_m2": street.area, "concrete_m2": concrete.area, "bed_m2": beds.area}}
    json.dump(out, open(a.out, "w"))
    print(json.dumps(out["stats"], indent=1), len(faces), "faces")


if __name__ == "__main__":
    main()
