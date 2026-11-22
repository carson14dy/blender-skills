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

Spikes (lit pyramids): the filtered ground drops isolated shrub-top cells (--ground-despike, lidar.ground_surface), and
every node is despiked twice -- after the rock merge and again after the pads / breaklines (whose own nodes are
skipped) -- by lidar.clamp_spikes: z <= 3x3 median + --spike-clamp and <= highest neighbour + --peak-clamp; rock nodes
(rock_rise > --spike-rock and the pits their closing adds) are also lifted to >= 3x3 median - --pit-clamp and smoothed
with a Gaussian (--rock-smooth, one ring of foot nodes with --rock-smooth-ring) that never goes below the measured
height of the node's own cell (--rock-smooth-floor); small off-rock bumps over the 5x5 median take that median
(--bump-clamp). Shrub / mulch beds: --beds entries may be {"polygon", "label", "no_solid": true} and --veg-mask lists
more; there the single returns are shrub tops, not rock: no solid merge, no rock-outline quantile, and the terrain is
capped at the grey opening of the ground (--veg-window, --veg-dh: lidar.veg_floor). Inside traced rock outlines no node
stays below its cell's lowest last return (--rock-floor-last). A third pass (--spike-third) clamps once more to the 3x3
median + 0.3 everywhere but the breakline bands, pads, cut-outs and tall rock (rock_rise >= --spike-third-rise), and
lowers crest / bump nodes the median cannot see (a node on a one-cell crest is its own median) to the mean of its 8
neighbours + 0.3 / its 5x5 median, unless a LiDAR return supports its height (lidar.clamp_unsupported).

Wall feet and overlays at walls: after the breaklines, nodes within one cell of a retaining-wall face on its downhill side
(also past the face's ends; nodes snapped onto the face count) take min(z, their cell's lowest last return), nodes out to
--wall-foot m min(z, that + --wall-foot-tol), and the later despike passes skip them (wall_foot_lower: a grade pad's blend or
the side grade of a smeared step otherwise leaves pale shards on the lower level). Draped street / paving / bed overlays are cut
back from a --overlay-wall-gap strip on the uphill side of every face (uphill_strips), so a polygon lapping over a face is never
draped on the upper level's triangles. A fourth despike pass (--spike-fourth) clamps the non-rock nodes once more, and nodes of
street cells are kept within --street-clamp of the locally fitted road plane (road_plane).

Vehicles: inside the street / paving outlines, returns more than --paving-hump over the local lowest-return surface (a
3 m grey opening, exact on planes and slopes) are parked cars or trailers; they are dropped before any gridding
(lidar.paving_humps), so the street is bridged under them instead of rising as an asphalt mound. Street cells more
than --street-bank over the locally fitted road plane near the street edge (a street polygon lapping onto a bank) leave
the street overlay and stay ground (street_bank; kerbed edges are kept).
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


def wall_faces(data, zfun=None):
    """Exposed (downhill) faces of the retaining walls of a yard.json dict (or item list) -> [(face line, down, thickness)]:
    ``down`` = +1 when the downhill side is left of the line direction, -1 when it is right. A ``"line_is": "face"`` item
    gives its own line (downhill = the side opposite ``uphill``, or the lower terrain); a centre-line item gives its line
    moved half a thickness to its downhill side (the lower ``zfun`` side; skipped without a terrain)."""
    items = data.get("items", []) if isinstance(data, dict) else data
    out = []
    for it in items:
        if not (isinstance(it, dict) and it.get("line") and len(it["line"]) >= 2
                and it.get("kind", "retaining_wall") == "retaining_wall"):
            continue
        th = float(it.get("thickness", 0.3))
        up = {"left": 1, "right": -1}.get(it.get("uphill"))
        if up is None:
            if zfun is None:
                continue
            up = uphill_side(it["line"], th, zfun)
        line = it["line"] if it.get("line_is", "centre") == "face" else offset_line(it["line"], -up * th / 2)
        out.append(([list(map(float, p[:2])) for p in line], -up, th))
    return out


def uphill_strips(faces, gap=0.15):
    """Plan strips ``gap`` m wide on the uphill side of every wall face (the face line extended by ``gap`` past both
    ends): draped paving / bed overlays are cut back to the face there. A paving polygon that laps a few centimetres over
    a face (or past a wall end) onto the upper level would otherwise be draped on the upper level's terrain triangles and
    stand up as a pale spike on the wall."""
    polys = []
    for line, down, _th in faces:
        P = np.asarray(line, float)
        d0 = P[1] - P[0]; d1 = P[-1] - P[-2]
        n0, n1 = np.hypot(*d0), np.hypot(*d1)
        if n0 < 1e-9 or n1 < 1e-9:
            continue
        P = P.copy(); P[0] = P[0] - gap * d0 / n0; P[-1] = P[-1] + gap * d1 / n1
        # single-sided buffer: positive distance = left of the line direction; the uphill side is -down
        pg = LineString(P).buffer(-down * gap, single_sided=True, join_style="mitre")
        if not pg.is_empty:
            polys.append(pg)
    return unary_union(polys) if polys else Polygon()


def cell_lowest(pxy, pz, x0, y0, c, shape):
    """Lowest return of every grid node's cell (node (j, i) at (x0 + i c, y0 + j c), cell +-c/2); nan where empty."""
    ny, nx = shape
    i = np.floor((pxy[:, 0] - (x0 - c / 2)) / c).astype(int)
    j = np.floor((pxy[:, 1] - (y0 - c / 2)) / c).astype(int)
    ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    low = np.full(shape, np.inf)
    np.minimum.at(low, (j[ok], i[ok]), pz[ok])
    low[~np.isfinite(low)] = np.nan
    return low


def wall_foot_lower(Z, NX, NY, faces, low, x0, y0, c, reach=0.5, tol=0.3, walls=None):
    """Foot of every retaining-wall face: grid nodes (at their mesh positions NX, NY: nodes snapped onto a face count)
    within one cell of the face on its downhill side -- also past the face's ends -- take min(z, lowest last return of
    their own cell; with none, of the nearest cell down the face normal, up to 3 cells); nodes one cell to ``reach`` m
    out take min(z, that return + ``tol``). Grade-pad blends reach across a wall and the side grade of a smeared step can
    leave the foot standing up as a pale terrain shard on the lower level. Nodes on the uphill side of another wall's
    face (inside its band, ``walls`` = wall_lines output) are left to that wall. Never raises a node.
    Returns (new grid, bool mask of the lowered foot nodes)."""
    Z = np.array(Z, float, copy=True)
    ny, nx = Z.shape
    near = np.full(Z.shape, np.inf); tdn = np.zeros(Z.shape); ndir = np.zeros(Z.shape + (2,))
    owner = np.full(Z.shape, -1)
    uph = [np.zeros(Z.shape, bool) for _ in faces]
    for k, (line, down, th) in enumerate(faces):
        P = np.asarray(line, float)
        bx0, by0 = P.min(0) - reach - c; bx1, by1 = P.max(0) + reach + c
        cand = (NX >= bx0) & (NX <= bx1) & (NY >= by0) & (NY <= by1)
        if not cand.any():
            continue
        dk = np.full(Z.shape, np.inf); tk = np.zeros(Z.shape); nk = np.zeros(Z.shape + (2,))
        for a_, b_ in zip(P[:-1], P[1:]):
            d = b_ - a_; ln = float(np.hypot(*d))
            if ln < 1e-9:
                continue
            d = d / ln; n = down * np.array([-d[1], d[0]])         # n points downhill
            s = (NX - a_[0]) * d[0] + (NY - a_[1]) * d[1]
            t = (NX - a_[0]) * n[0] + (NY - a_[1]) * n[1]
            dist = np.hypot(s - np.clip(s, 0, ln), t)
            better = cand & (dist < dk)
            dk = np.where(better, dist, dk); tk = np.where(better, t, tk)
            nk[better] = n
        uph[k] = cand & (tk < -1e-6) & (dk <= th + 1.5 * c)
        mine = cand & (tk >= -1e-6) & (dk <= reach + 1e-6) & (dk < near)
        near = np.where(mine, dk, near); tdn = np.where(mine, tk, tdn); ndir[mine] = nk[mine]
        owner[mine] = k
    foot = owner >= 0
    for k in range(len(faces)):
        others = np.zeros(Z.shape, bool)
        for j in range(len(faces)):
            if j != k:
                others |= uph[j]
        foot &= ~((owner == k) & others)
    jj, ii = np.nonzero(foot)
    lowered = np.zeros(Z.shape, bool)
    for j_, i_ in zip(jj, ii):
        lo = low[j_, i_]
        step = 1
        while not np.isfinite(lo) and step <= 3:
            px = x0 + i_ * c + step * c * ndir[j_, i_, 0]; py = y0 + j_ * c + step * c * ndir[j_, i_, 1]
            i2, j2 = int(round((px - x0) / c)), int(round((py - y0) / c))
            if 0 <= i2 < nx and 0 <= j2 < ny:
                lo = low[j2, i2]
            step += 1
        if not np.isfinite(lo):
            continue
        cap = lo if near[j_, i_] <= c + 1e-6 else lo + tol
        if Z[j_, i_] > cap:
            Z[j_, i_] = cap
            lowered[j_, i_] = True
    return Z, foot


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


def bed_entries(data):
    """Bed polygons from a beds json: each entry is a ring [[x,y],...] or a dict {"polygon": ring, "label": "...",
    "no_solid": true}. Returns (all bed polygons, the no_solid ones). A no_solid bed (shrubs / mulch: dense evergreen
    shrubs return single, planar-looking pulses that pass the solid-surface test) is also a vegetation mask: no
    solid-surface merge, no rock-outline quantile and no rock edge growth inside it, so the terrain there is the
    filtered ground (lowest last returns), not the shrub tops. ``"overlay": false`` makes an entry a vegetation mask
    only (no bed overlay): e.g. the shrub area round a bed whose drawn outline is kept clear of a boulder or a wall."""
    polys, veg = [], []
    for e in data or []:
        ring = e.get("polygon") if isinstance(e, dict) else e
        if not ring or len(ring) < 3:
            continue
        pg = Polygon(ring).buffer(0)
        if pg.is_empty:
            continue
        if not (isinstance(e, dict) and e.get("overlay") is False):
            polys.append(pg)
        if isinstance(e, dict) and e.get("no_solid"):
            veg.append(pg)
    return polys, veg


def paving_outlines(F, paving=None):
    """Street + private paving outlines of a features dict (every "impervious" polygon, sidewalk lines buffered by
    their width, extra --paving polygons): where returns standing on the pavement are vehicles, not ground."""
    parts = [polys_of(F.get("impervious", []))]
    for fe in F.get("sidewalk", []):
        wid = float((fe.get("props") or {}).get("WIDTH") or 4) * 0.3048
        parts += [LineString(gl).buffer(wid / 2, cap_style="flat") for gl in fe["geoms"] if len(gl) >= 2]
    parts += [Polygon(p).buffer(0) for p in (paving or [])]
    parts = [g_ for g_ in parts if not g_.is_empty]
    return unary_union(parts) if parts else Polygon()


def road_plane(street, X, Y, Z, radius=5.0, step=1.0, trim=0.15):
    """Local road surface under a street outline: at every ``step`` m sample a plane through the street nodes within
    ``radius`` m, started level at their median (the road is most of the disc) and refitted four times to the nodes within
    ``trim`` of it (a bank strip along the edge neither lifts nor tilts it). Returns road_z(qx, qy) (nearest sample's
    plane) or None when the street has too few nodes."""
    from scipy.spatial import cKDTree
    m = shapely.contains_xy(street, X, Y) if not street.is_empty else np.zeros(X.shape, bool)
    if m.sum() < 10:
        return None
    P = np.column_stack([X[m], Y[m], Z[m]])
    tree = cKDTree(P[:, :2])
    bx0, by0, bx1, by1 = street.bounds
    sx, sy = np.meshgrid(np.arange(bx0, bx1 + step, step), np.arange(by0, by1 + step, step))
    S = np.column_stack([sx.ravel(), sy.ravel()])
    near, _ = tree.query(S, distance_upper_bound=step)
    S = S[np.isfinite(near)]
    coef = np.full((len(S), 3), np.nan)
    for k, idx in enumerate(tree.query_ball_point(S, radius)):
        if len(idx) < 10:
            continue
        Q = P[idx]
        A = np.column_stack([Q[:, 0] - S[k, 0], Q[:, 1] - S[k, 1], np.ones(len(Q))])
        cf = np.array([0.0, 0.0, float(np.median(Q[:, 2]))])
        for _ in range(4):
            sel = np.abs(Q[:, 2] - A @ cf) <= trim
            if sel.sum() < 6:
                break
            cf = np.linalg.lstsq(A[sel], Q[sel, 2], rcond=None)[0]
        coef[k] = cf
    ok = np.isfinite(coef[:, 0])
    if not ok.any():
        return None
    S, coef = S[ok], coef[ok]
    kd = cKDTree(S)

    def road_z(qx, qy):
        q = np.column_stack([np.ravel(qx), np.ravel(qy)])
        _, si = kd.query(q)
        z = coef[si, 2] + coef[si, 0] * (q[:, 0] - S[si, 0]) + coef[si, 1] * (q[:, 1] - S[si, 1])
        return z.reshape(np.shape(qx))
    return road_z


def street_bank(street, X, Y, Z, c, rise=0.4, radius=5.0, step=1.0, trim=0.15, edge=3.0, keep=None):
    """Parts of a street outline that lap onto a bank (the polygon traced a little wide of the asphalt): grid cells
    the outline covers (centre or a corner inside), within ``edge`` m of its outline and outside ``keep`` (e.g. the kerb lines,
    buffered: a kerbed edge keeps its asphalt up to the kerb), with any corner node more than ``rise`` over the road
    surface. The road surface at each ``step`` m sample is a plane through the street nodes within ``radius`` m: it
    starts level at their median (the road is most of the disc) and is refitted (least squares) four times to the
    nodes within ``trim`` of it, so a bank strip along the edge neither lifts nor tilts it.
    Returns the union of those cells (shapely), to take out of the street overlay (they stay ground)."""
    from scipy.spatial import cKDTree
    m = shapely.contains_xy(street, X, Y) if not street.is_empty else np.zeros(X.shape, bool)
    if m.sum() < 10:
        return Polygon()
    P = np.column_stack([X[m], Y[m], Z[m]])
    tree = cKDTree(P[:, :2])
    bx0, by0, bx1, by1 = street.bounds
    sx, sy = np.meshgrid(np.arange(bx0, bx1 + step, step), np.arange(by0, by1 + step, step))
    S = np.column_stack([sx.ravel(), sy.ravel()])
    near, _ = tree.query(S, distance_upper_bound=step)
    S = S[np.isfinite(near)]
    coef = np.full((len(S), 3), np.nan)
    for k, idx in enumerate(tree.query_ball_point(S, radius)):
        if len(idx) < 10:
            continue
        Q = P[idx]
        A = np.column_stack([Q[:, 0] - S[k, 0], Q[:, 1] - S[k, 1], np.ones(len(Q))])
        cf = np.array([0.0, 0.0, float(np.median(Q[:, 2]))])      # start level at the median: the road is most of it
        for _ in range(4):
            sel = np.abs(Q[:, 2] - A @ cf) <= trim
            if sel.sum() < 6:
                break
            cf = np.linalg.lstsq(A[sel], Q[sel, 2], rcond=None)[0]
        coef[k] = cf
    ok = np.isfinite(coef[:, 0])
    if not ok.any():
        return Polygon()
    S, coef = S[ok], coef[ok]
    cx = (X[:-1, :-1] + X[1:, 1:]) / 2; cy = (Y[:-1, :-1] + Y[1:, 1:]) / 2
    zmax = np.maximum.reduce([Z[:-1, :-1], Z[:-1, 1:], Z[1:, :-1], Z[1:, 1:]])
    cand = shapely.contains_xy(street, cx, cy) | m[:-1, :-1] | m[:-1, 1:] | m[1:, :-1] | m[1:, 1:]   # cells it touches
    cand &= shapely.distance(street.boundary, shapely.points(cx.ravel(), cy.ravel())).reshape(cx.shape) <= edge
    if keep is not None and not keep.is_empty:
        cand &= ~shapely.contains_xy(keep, cx, cy)
    if not cand.any():
        return Polygon()
    q = np.column_stack([cx[cand], cy[cand]])
    _, si = cKDTree(S).query(q)
    road = coef[si, 2] + coef[si, 0] * (q[:, 0] - S[si, 0]) + coef[si, 1] * (q[:, 1] - S[si, 1])
    bank = zmax[cand] - road > rise
    if not bank.any():
        return Polygon()
    h_ = c / 2
    cells = unary_union([Polygon([(x - h_, y - h_), (x + h_, y - h_), (x + h_, y + h_), (x - h_, y + h_)]) for x, y in q[bank]])
    return cells.buffer(0.05, join_style="mitre").buffer(-0.05, join_style="mitre")


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
    ap.add_argument("--rock-floor-last", type=int, default=1,
                    help="inside traced rock outlines no node stays below its cell's lowest last return (1 = on, 0 = off)")
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
    ap.add_argument("--veg-mask", help="json list of polygons (rings or {polygon} dicts): shrub / bed areas whose single returns "
                                       "are vegetation, not rock: kept out of the --keep-rocks solid merge, the rock-outline "
                                       "quantile and the edge growth (terrain = filtered ground). --beds entries with "
                                       "\"no_solid\": true are added to it")
    ap.add_argument("--spike-clamp", type=float, default=0.3,
                    help="despike of every terrain node, after the rock merge and again after the pads and breaklines: "
                         "z = min(z, 3x3 median + this), --spike-passes times; in the second stage breakline bands, grade "
                         "pads and cut-out rings are skipped (0 = off)")
    ap.add_argument("--spike-passes", type=int, default=2, help="passes of the final despike")
    ap.add_argument("--spike-floor", type=int, default=1, choices=[0, 1, 2],
                    help="where the --rock-smooth-floor also protects measured rock points from the 3x3 clamp: 1 = inside "
                         "traced rock outlines (default), 2 = on every rock node, 0 = nowhere (every peak is cut to the "
                         "3x3 median + --spike-clamp)")
    ap.add_argument("--spike-rock", type=float, default=0.2,
                    help="final despike: nodes the rock merge raised more than this (m; + the pits their 3x3 closing adds) "
                         "are also clamped from below (--pit-clamp) and smoothed (--rock-smooth)")
    ap.add_argument("--peak-clamp", type=float, default=0.1,
                    help="despike: z = min(z, highest of the 8 neighbours + this) (lone peaks; 0 = off)")
    ap.add_argument("--pit-ceiling", type=float, default=0.3,
                    help="despike: the pit lift and the rock Gaussian never raise a node more than this above its own "
                         "cell's lowest last return (measured ground at a rock foot stays; negative = no ceiling)")
    ap.add_argument("--pit-clamp", type=float, default=0.3, help="final despike, rock nodes: z = max(z, 3x3 median - this) (0 = off)")
    ap.add_argument("--rock-smooth", type=float, default=0.25,
                    help="final despike: Gaussian sigma (m) over the rock nodes only (0 = off)")
    ap.add_argument("--rock-smooth-clamp", type=float, default=0.0,
                    help="final despike: the rock Gaussian moves no node by more than this (m; 0 = no limit)")
    ap.add_argument("--rock-smooth-floor", type=float, default=0.1,
                    help="despike: on rock nodes neither the clamp nor the Gaussian takes a node more than this below the "
                         "measured height of its own cell (max of its lowest last return and q90 single return), so measured "
                         "rock keeps its height (negative = no floor)")
    ap.add_argument("--rock-smooth-ring", type=int, default=1,
                    help="final despike: the rock Gaussian also covers this many rings of nodes round the rock (its foot)")
    ap.add_argument("--bump-clamp", type=float, default=0.4,
                    help="final despike: off-rock nodes more than this above the 5x5 median, in groups of <= 4 nodes, take "
                         "that median (0 = off)")
    ap.add_argument("--ground-despike", type=float, default=0.3,
                    help="filtered ground: isolated ground cells (<= 2) more than this above the median of their 3x3 ground "
                         "cells are shrub tops, not ground (0 = off)")
    ap.add_argument("--veg-window", type=float, default=2.0,
                    help="inside --veg-mask / no_solid beds the terrain is capped at the grey opening of this window (m) + "
                         "--veg-dh: shrub tops the ground filter kept are cut to the envelope of the ground around them")
    ap.add_argument("--veg-dh", type=float, default=0.1, help="see --veg-window")
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
    ap.add_argument("--paving-hump", type=float, default=0.3,
                    help="inside the street / paving outlines, returns more than this over the local lowest-return surface "
                         "(--paving-hump-window m grey opening: parked cars, trailers) are dropped before any gridding "
                         "(filtered ground, solid merge, class-2 terrain); 0 = off")
    ap.add_argument("--paving-hump-window", type=float, default=3.0, help="see --paving-hump (m; wider than a car)")
    ap.add_argument("--street-bank", type=float, default=0.4,
                    help="street nodes more than this above the locally fitted road plane, within 3 m of the street outline, "
                         "are bank under a too-wide street polygon: they leave the street overlay (0 = off)")
    ap.add_argument("--spike-third", type=float, default=0.3,
                    help="third despike pass after the second stage: z = min(z, 3x3 median + this) on non-rock nodes outside "
                         "breakline bands, pads and cut-outs, and on rock nodes the merge raised less than --spike-third-rise "
                         "(0 = off)")
    ap.add_argument("--spike-third-rise", type=float, default=1.0, help="see --spike-third (m)")
    ap.add_argument("--support-radius", type=float, default=0.3,
                    help="third despike pass: a non-rock node more than --spike-third over the mean of its 8 neighbours (or "
                         "--bump-clamp over its 5x5 median) is lowered to that level unless a LiDAR return within this many m "
                         "(plan) lies within --support-dz of its height")
    ap.add_argument("--support-dz", type=float, default=0.25, help="see --support-radius (m)")
    ap.add_argument("--wall-foot", type=float, default=0.5,
                    help="after the breaklines, nodes within one cell of a retaining-wall face on its downhill side (past its "
                         "ends too) take min(z, their cell's lowest last return), nodes up to this many m out min(z, that + "
                         "--wall-foot-tol); they are skipped by the later despike passes (0 = off)")
    ap.add_argument("--wall-foot-tol", type=float, default=0.3, help="see --wall-foot (m)")
    ap.add_argument("--overlay-wall-gap", type=float, default=0.15,
                    help="draped street / paving / bed overlays are cut back from a strip this wide on the uphill side of "
                         "every wall face (and past its ends), so a polygon lapping over a face is not draped on the upper "
                         "level (0 = off)")
    ap.add_argument("--spike-fourth", type=float, default=0.3,
                    help="fourth despike pass after the third: z = min(z, 3x3 median + this) on non-rock nodes outside the "
                         "breakline bands, wall feet, pads and cut-outs (0 = off)")
    ap.add_argument("--street-clamp", type=float, default=0.25,
                    help="street-overlay nodes: z = min(z, locally fitted road plane + this) (0 = off)")
    ap.add_argument("--house-extra", help="json list of polygons treated as building (no lawn/beds; e.g. a garage under a deck)")
    ap.add_argument("project"); ap.add_argument("features"); ap.add_argument("out")
    ap.add_argument("--half", type=float, default=34.0); ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--bed-width", type=float, default=0.9, help="rock bed band around the walls (m)")
    ap.add_argument("--beds", help="json list of extra bed polygons [[x,y],...] or {polygon, label, no_solid} dicts (e.g. under "
                                   "decks; no_solid: a shrub / mulch bed that is also a --veg-mask)")
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
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from propmodel import lidar as L
    if a.paving_hump > 0:
        # parked cars / trailers on the street or a driveway: not ground, and not "rock" for the solid merge
        pav = paving_outlines(F, json.load(open(a.paving)) if a.paving else None)
        hump = L.paving_humps(pts, pav, above=a.paving_hump, window=a.paving_hump_window)
        if hump.any():
            hp = pts[hump]
            print(f"terrain: {int(hump.sum())} returns on paving more than {a.paving_hump} m over the local lowest-return "
                  f"surface dropped (vehicles; x {hp[:, 0].min():.1f}..{hp[:, 0].max():.1f}, y {hp[:, 1].min():.1f}..{hp[:, 1].max():.1f})")
        pts = pts[~hump]
    g = pts[pts[:, 3] == 2]
    gx, gy, gz = g[:, 0], g[:, 1], g[:, 2] - datum

    bed_polys, veg_polys = bed_entries(json.load(open(a.beds))) if a.beds else ([], [])
    if a.veg_mask:
        veg_polys += bed_entries(json.load(open(a.veg_mask)))[0]
    veg = unary_union(veg_polys) if veg_polys else Polygon()

    # ---- terrain grid -----------------------------------------------------
    from scipy.interpolate import griddata
    from scipy.ndimage import median_filter
    h, c = a.half, a.cell
    xs = np.arange(-h, h + 1e-9, c)
    ys = np.arange(-h, h + 1e-9, c)
    X, Y = np.meshgrid(xs, ys)
    rock_rise = np.zeros(X.shape)          # how far the rock merge raised each node above the filtered ground
    rock_low = None                        # measured height of each node's cell (solid merge): floor of the rock smoothing
    in_outlines = np.zeros(X.shape, bool)  # nodes inside traced rock outlines
    cell_low = None                        # lowest last return of each node's cell (ceiling of the pit lift / smoothing)
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
        surf = L.ground_surface(pts, cell=a.ground_cell or max(c, 0.5), exclude=exu, zstat=a.ground_stat,
                                despike=a.ground_despike if a.ground_despike > 0 else None)
        Z = L.surface_z(surf, X.ravel(), Y.ravel()).reshape(X.shape) - datum
        if not veg.is_empty and a.veg_window > 0:
            vm = shapely.contains_xy(veg, X, Y)
            Zv = L.veg_floor(Z, vm, c, window=a.veg_window, dh=a.veg_dh)
            print(f"terrain: vegetation mask lowers {int((Z - Zv > 0.05).sum())} nodes to the ground envelope "
                  f"(max {(Z - Zv).max():.2f} m)")
            Z = Zv
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
            cell_low = sol["low"]
            # measured rock height of each node cell: the higher of its lowest last return and its q90 single return
            with np.errstate(invalid="ignore"):
                rock_low = np.fmax(sol["low"], sol["q90_single"])
            # never solid: the roof plan and decks / excludes (+ a small margin; a boulder can stand right at the
            # drip line) and paving with cars. The ground filter above keeps its wider exclusion.
            mb = a.solid_mask_buffer
            nog = unary_union([roof_plan(model).buffer(mb)]
                              + [Polygon(q).buffer(0).buffer(mb) for q in (json.load(open(a.ground_exclude)) if a.ground_exclude else [])]
                              + [Polygon(q).buffer(0) for q in (json.load(open(a.paving_like)) if a.paving_like else [])]
                              + [veg])
            nogm = shapely.contains_xy(nog, X, Y)
            if not veg.is_empty:
                print(f"terrain: vegetation mask (no solid / rock merge) {veg.area:.1f} m2, "
                      f"{int(shapely.contains_xy(veg, X, Y).sum())} nodes")
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
                in_outlines = inside & ~nogm
                with np.errstate(invalid="ignore"):
                    take = inside & ~nogm & np.isfinite(q) & (q > Z) & (q <= cap) & (q - Zg < a.rock_max)
                Z = np.where(take, q, Z)
                print(f"terrain: {len(outl)} rock outlines, {int(take.sum())} nodes raised to the q{a.rock_q:g} single return")
                if a.rock_floor_last:
                    # a traced outline is rock by inspection (vegetation was excluded when it was traced): no node in it
                    # stays below the lowest last return of its own cell (cells with mixed pulses have no q90 single return)
                    low = sol["low"]
                    with np.errstate(invalid="ignore"):
                        tk2 = inside & ~nogm & np.isfinite(low) & (low > Z) & (low <= cap) & (low - Zg < a.rock_max)
                    Z = np.where(tk2, low, Z)
                    print(f"terrain: rock outlines, {int(tk2.sum())} more nodes raised to their cell's lowest last return")
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
            nog = unary_union([exu.buffer(0.5), veg] + [Polygon(q).buffer(0) for q in (json.load(open(a.paving_like)) if a.paving_like else [])])
            keep &= ~shapely.contains_xy(nog, X, Y)
            Z = np.where(keep, zmin, Z)
            print(f"terrain: {int(keep.sum())} cells keep their rock/grade returns ({100 * keep.mean():.0f} %)")
    else:
        Z = griddata((gx, gy), gz, (X, Y), method="linear")
        Zn = griddata((gx, gy), gz, (X, Y), method="nearest")
        Z = np.where(np.isnan(Z), Zn, Z)
    if not (a.keep_rocks and a.rocks == "solid"):
        Z = median_filter(Z, size=3, mode="nearest")      # (the solid merge filtered its ground part already)

    # ---- final despike of every node (lit pyramids: shrub tops the ground filter kept, single solid cells,
    # sampling holes in boulder tops, a 2x2 block on a slope), first stage: before the pads and breaklines, so the
    # wall bands take their side grades from a clean surface
    def _despike(Z, rock_rise, skip, stage, smooth=True):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from propmodel import lidar as L
        floor = (rock_low - a.rock_smooth_floor) if (rock_low is not None and a.rock_smooth_floor >= 0) else None
        Zn, rk_n = L.clamp_spikes(Z, c, skip=skip, rock=rock_rise > a.spike_rock, above=a.spike_clamp,
                                  below=a.pit_clamp if (a.pit_clamp > 0 and smooth) else None, passes=a.spike_passes,
                                  sigma=a.rock_smooth if smooth else 0,
                                  max_change=a.rock_smooth_clamp if a.rock_smooth_clamp > 0 else None,
                                  floor=floor, bump=a.bump_clamp if a.bump_clamp > 0 else None, ring=a.rock_smooth_ring,
                                  ring_exclude=shapely.contains_xy(veg, X, Y) if not veg.is_empty else None,
                                  floor_clamp={0: False, 1: in_outlines, 2: True}[a.spike_floor],
                                  peak=a.peak_clamp if a.peak_clamp > 0 else None,
                                  ceiling=(cell_low + a.pit_ceiling) if (cell_low is not None and a.pit_ceiling >= 0) else None)
        dz = Zn - Z
        print(f"terrain: despike ({stage}) lowered {int((dz < -0.01).sum())} nodes (max {-dz.min():.2f} m), raised "
              f"{int((dz > 0.01).sum())} (max {dz.max():.2f} m)" + (f"; {int(rk_n.sum())} rock nodes smoothed" if smooth else "")
              + (f", {int(skip.sum())} skipped" if skip is not None else ""))
        return Zn, rock_rise + dz
    if a.spike_clamp > 0:
        Z, rock_rise = _despike(Z, rock_rise, None, "after the rock merge")

    # ---- grade pads and retaining-wall breaklines ------------------------------
    pads = grade_pads(json.load(open(a.grade))) if a.grade else []
    padmask = np.zeros(X.shape, bool)       # pad + blend nodes (the final despike leaves them alone)
    if pads:
        for pad in pads:
            pp = Polygon(pad["polygon"]).buffer(0)
            bl = float(pad.get("blend", 0.0))
            dist = shapely.distance(pp, shapely.points(X.ravel(), Y.ravel())).reshape(X.shape)
            w = np.clip(1.0 - dist / bl, 0.0, 1.0) if bl > 0 else (dist <= 0).astype(float)
            w[(rock_rise > 0.5) & (dist > 0)] = 0.0        # the blend never drags a boulder / outcrop down
            Z = w * float(pad["z"]) + (1 - w) * Z
            padmask |= w > 0
            print(f"terrain: grade pad z={pad['z']} over {pp.area:.1f} m2")
    _Zw = Z.copy()

    def _zw(x, y):
        fi = np.clip((x - xs[0]) / c, 0, len(xs) - 1.001); fj = np.clip((y - ys[0]) / c, 0, len(ys) - 1.001)
        i_, j_ = int(fi), int(fj); tx, ty = fi - i_, fj - j_
        return (_Zw[j_, i_] * (1 - tx) * (1 - ty) + _Zw[j_, i_ + 1] * tx * (1 - ty)
                + _Zw[j_ + 1, i_] * (1 - tx) * ty + _Zw[j_ + 1, i_ + 1] * tx * ty)
    walls = wall_lines(json.load(open(a.breaklines)), zfun=_zw) if a.breaklines else []
    wfaces = wall_faces(json.load(open(a.breaklines)), zfun=_zw) if a.breaklines else []
    node_xy = [X.copy(), Y.copy()]          # mesh vertex positions (nodes next to walls move onto the faces)
    lastm = pts[:, 4] >= pts[:, 5]
    low_last = cell_lowest(pts[lastm, :2], pts[lastm, 2] - datum, xs[0], ys[0], c, X.shape)
    foot = np.zeros(X.shape, bool)
    if walls:
        Z = apply_breaklines(Z, xs, ys, walls, c, snap=node_xy)
        print(f"terrain: {len(walls)} retaining-wall breaklines")
        if a.wall_foot > 0 and wfaces:
            Zf, foot = wall_foot_lower(Z, node_xy[0], node_xy[1], wfaces, low_last, xs[0], ys[0], c, reach=a.wall_foot,
                                       tol=a.wall_foot_tol, walls=walls)
            dzf = Z - Zf
            print(f"terrain: wall feet: {int(foot.sum())} nodes within {a.wall_foot} m downhill of a face, "
                  f"{int((dzf > 0.01).sum())} lowered to their cell's lowest last return (max {dzf.max():.2f} m)")
            Z = Zf

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
    if a.street_bank > 0 and not street.is_empty:
        kerb = unary_union([LineString(gl).buffer(1.0) for fe in (F.get("curbs") or []) for gl in fe["geoms"] if len(gl) >= 2]
                           or [Polygon()])
        bank = street_bank(street, X, Y, Z, c, rise=a.street_bank, keep=kerb)
        if not bank.is_empty:
            before = street.area
            street = street.difference(bank.intersection(street))
            street = unary_union([g_ for g_ in getattr(street, "geoms", [street]) if g_.area > 0.05] or [Polygon()])
            print(f"paving: street outline laps onto a bank (> {a.street_bank} m over the road plane): "
                  f"{before - street.area:.1f} m2 left as ground")
    beds = house.buffer(a.bed_width, join_style="mitre").difference(house) if a.bed_width > 0 else Polygon()
    if bed_polys:
        beds = unary_union([beds] + bed_polys)
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

    # ---- final despike, second stage: what the pads, breaklines and cut-outs left (their own nodes keep their steps)
    skip = padmask.copy() | foot
    if walls:
        skip |= _band_owner(walls, X, Y, c) != -1
    if not cut.is_empty:
        skip |= shapely.distance(cut, shapely.points(X.ravel(), Y.ravel())).reshape(X.shape) < 1.5
    if a.spike_clamp > 0:
        Z, rock_rise = _despike(Z, rock_rise, skip, "after pads / breaklines")
    # third pass: a plain 3x3-median clamp (no rock floor, no smoothing) on everything but the breakline bands, pads,
    # cut-outs and the tall rock (cliffs and boulders the merge raised >= --spike-third-rise keep their measured edges)
    if a.spike_third > 0:
        sk3 = skip | (rock_rise >= a.spike_third_rise)
        Zn, _ = L.clamp_spikes(Z, c, skip=sk3, rock=None, above=a.spike_third, below=None, passes=1, sigma=0,
                               peak=a.peak_clamp if a.peak_clamp > 0 else None)
        # crest and bump nodes the median clamp cannot see (a node on a crest line IS its 3x3 median) are lowered only
        # where no LiDAR return supports their height (measured terrain breaks stay)
        free3 = ~sk3 & ~(rock_rise > a.spike_rock)
        Zn, nun = L.clamp_unsupported(Zn, c, free3, pts[:, :2], pts[:, 2] - datum, x0=xs[0], y0=ys[0], above=a.spike_third,
                                      bump=a.bump_clamp if a.bump_clamp > 0 else None, radius=a.support_radius,
                                      dz=a.support_dz)
        dz = Zn - Z
        print(f"terrain: despike (third pass) lowered {int((dz < -0.01).sum())} nodes (max {-dz.min():.2f} m; "
              f"{nun} unsupported crest / bump nodes), {int(sk3.sum())} skipped")
        Z, rock_rise = Zn, rock_rise + dz
        if a.spike_fourth > 0:
            # once more on the non-rock nodes: lowering the crests can leave the next node standing over its new median
            Zn, _ = L.clamp_spikes(Z, c, skip=sk3 | (rock_rise > a.spike_rock), rock=None, above=a.spike_fourth, below=None,
                                   passes=1, sigma=0, peak=a.peak_clamp if a.peak_clamp > 0 else None)
            dz = Zn - Z
            print(f"terrain: despike (fourth pass, non-rock) lowered {int((dz < -0.01).sum())} nodes (max {-dz.min():.2f} m)")
            Z, rock_rise = Zn, rock_rise + dz
    # street nodes: never more than --street-clamp over the locally fitted road plane (bank cells already left the street)
    if a.street_clamp > 0 and not street.is_empty:
        road_z = road_plane(street, X, Y, Z)
        if road_z is not None:
            # street-class nodes: every corner of a cell whose centre is on the street (the overlay's edge triangles
            # reach the first node outside the outline; a bank node there would lift the overlay's edge)
            scell = shapely.contains_xy(street, (X[:-1, :-1] + X[1:, 1:]) / 2, (Y[:-1, :-1] + Y[1:, 1:]) / 2)
            sm_ = np.zeros(X.shape, bool)
            sm_[:-1, :-1] |= scell; sm_[:-1, 1:] |= scell; sm_[1:, :-1] |= scell; sm_[1:, 1:] |= scell
            sm_ &= ~skip
            Zr = np.where(sm_, np.minimum(Z, road_z(X, Y) + a.street_clamp), Z)
            dz = Zr - Z
            print(f"terrain: street nodes clamped to the road plane + {a.street_clamp} m: {int((dz < -0.01).sum())} lowered "
                  f"(max {-dz.min():.2f} m)")
            Z = Zr

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
    if a.overlay_wall_gap > 0 and wfaces:
        # nothing draped on the uphill side within --overlay-wall-gap of a face (or past its ends): it would take the
        # upper level's triangles and stand up as a spike on the wall
        wallpoly = unary_union([wallpoly, uphill_strips(wfaces, a.overlay_wall_gap)])
    for name, geom, lift in (("street", street.difference(wallpoly), 0.015),
                             ("concrete", concrete.difference(house).difference(wallpoly), 0.03),
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
