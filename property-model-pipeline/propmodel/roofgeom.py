"""Exact roof / wall geometry engine (pure Python + numpy + shapely).

A building is described as a list of *wings*. Each wing is a rectangular wall
footprint with a parametric roof. A wing roof is the **lower envelope of a few
planes** (each plane passes through a wall line and rises inward at its pitch)
clipped to the roof outline (wall rectangle grown by the overhangs). This one
rule produces exact gable, hip, pyramid, shed, flat, gambrel and mansard roofs,
including overhangs.

Wings are combined like solids: where two wings overlap, the higher surface
wins (valleys, cross-gables, dormers-as-wings and L/T/U plans all fall out
automatically), with one exception: a lower roof that runs *under* the
overhang of a taller wing (lower roof meeting an upper-storey wall) is kept,
because it is real roofing even though it is hidden from above. That holds inside
the lower wing's walls and also outside them wherever the taller roof clears the
lower one by at least ``OVERHUNG_CLEARANCE`` over the whole hidden piece (a porch
roof's rake or a lower eave running in under an upper overhang to the upper wall;
where the two roofs meet, e.g. beyond a valley, the lower one stops). Likewise a
pocket of a roof plane hidden under another wing's roof and enclosed by the
plane's own roof (a lower eave under the corner of an upper roof) is kept: being
overhung never opens a roof. Openings of a wing's own outline (``outline_holes``)
and other wings' walls rising through a roof stay open, and every roof stops at
the faces of solids standing through it (``penetrations``: a chimney, an
exterior chimney chase); the cut edges are flashing (headwall / sidewall).

Everything is computed analytically with polygon clipping, so areas and edge
lengths are exact for the model (no tessellation error). The measurement
accuracy therefore equals the accuracy of the wing parameters, which is what
:mod:`propmodel.fusion` estimates from all evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict, fields
from typing import Dict, List, Optional

import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, GeometryCollection
from shapely.ops import unary_union, linemerge

ROOF_TYPES = ("gable", "hip", "pyramid", "shed", "flat", "gambrel", "mansard")
GEOM_EPS = 1e-7
EDGE_TOL = 2e-3          # m; 2-D tolerance when matching shared boundaries
Z_MATCH_TOL = 0.03       # m; two facets "meet" along an edge if z agrees within this
HORIZ_TOL = 0.03         # rise/run below which an edge counts as horizontal


@dataclass
class Wing:
    """One rectangular building section with a parametric roof.

    Frame: ``cx, cy`` centre of the *wall* rectangle in the site ENU frame (m).
    ``azimuth`` is the compass bearing (deg, 0 = north, 90 = east) of the
    length axis ``u`` (the ridge direction for gable/gambrel/hip).
    ``length`` runs along ``u``, ``width`` across it (wall-to-wall, outside of
    sheathing). ``eave_height`` is the height of the wall plate line (where the
    roof plane meets the outer wall face) above site ground (z=0) — NOT the
    height of the drip edge, which is lower by overhang * pitch.
    Pitches are rise/run (0.5 == 6/12). ``pitch`` is the +v side (left of the azimuth
    direction), ``pitch_b`` the -v side. A shed roof's low eave is on the +v side.
    """

    id: str
    type: str = "gable"
    cx: float = 0.0
    cy: float = 0.0
    azimuth: float = 0.0
    length: float = 10.0
    width: float = 8.0
    eave_height: float = 2.8
    pitch: float = 0.5
    pitch_b: Optional[float] = None         # -v side pitch for asymmetric / saltbox roofs (default = pitch)
    end_pitch: Optional[float] = None       # hip / mansard ends (default = pitch)
    upper_pitch: Optional[float] = None     # gambrel / mansard upper slopes
    break_inset: Optional[float] = None     # gambrel / mansard: plan distance wall -> break line
    eave_overhang: float = 0.45
    rake_overhang: float = 0.30
    base_z: float = 0.0                     # bottom of walls (e.g. split level, wing on a deck)
    shed_high_overhang: Optional[float] = None
    eave_height_b: Optional[float] = None   # -v side plate height (split level / lopsided gable); default = eave_height
    eave_overhang_b: Optional[float] = None # -v side overhang (e.g. roof continued over a porch); default = eave_overhang
    roof_only: bool = False                 # roof patch without walls of its own (porch/junction/carport roofs)
    label: str = ""
    # measured shapes that are not rectangles (site frame, metres). The parametric rectangle still defines
    # the roof PLANES; these only replace where the roof stops and where the walls stand:
    outline: Optional[list] = None          # roof drip-edge polygon [[x,y],...] (prow ends, notches)
    outline_holes: Optional[list] = None    # openings in the roof (an open trellis bay): [[[x,y],...], ...]
    walls: Optional[list] = None            # wall polygon [[x,y],...] (cantilevers, recesses); sides are named w0, w1, ...
    # solids standing through the roof (a masonry chimney, an exterior chimney chase): [{"polygon": [[x,y],...],
    # "z": [z0, z1], "label": "..."}] (site frame; z0 / z1 null = unbounded). EVERY roof facet (any wing) stops at their
    # faces where its plane runs between z0 and z1 inside the polygon: no roof area under the solid, the cut edges
    # are flashing (headwall / sidewall). Roof heights for the fit (surface_z) are not changed.
    penetrations: Optional[list] = None

    NUMERIC = ("cx", "cy", "azimuth", "length", "width", "eave_height", "pitch", "pitch_b", "end_pitch",
               "upper_pitch", "break_inset", "eave_overhang", "rake_overhang", "base_z",
               "shed_high_overhang", "eave_height_b", "eave_overhang_b")

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        w = cls(**{k: v for k, v in d.items() if k in names})
        if w.type not in ROOF_TYPES:
            raise ValueError(f"wing {w.id}: unknown roof type {w.type!r}; use one of {ROOF_TYPES}")
        return w

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None and v != "" and not (k == "roof_only" and not v)}

    # ---- frame helpers -------------------------------------------------
    @property
    def u(self):
        t = math.radians(self.azimuth)
        return np.array([math.sin(t), math.cos(t)])

    @property
    def v(self):
        u = self.u
        return np.array([-u[1], u[0]])

    def to_world(self, uu, vv):
        c = np.array([self.cx, self.cy])
        return c + np.outer(np.atleast_1d(uu), self.u) + np.outer(np.atleast_1d(vv), self.v)

    def rect(self, u0, u1, v0, v1):
        pts = self.to_world([u0, u1, u1, u0], [v0, v0, v1, v1])
        return Polygon(pts)

    # ---- geometry ------------------------------------------------------
    def wall_polygon(self):
        if self.walls:
            return _ccw(Polygon(self.walls))
        L, W = self.length, self.width
        return self.rect(-L / 2, L / 2, -W / 2, W / 2)

    def extents(self):
        """(umax, vlo, vhi) of the roof outline in the wing frame (u symmetric)."""
        L, W, ork = self.length, self.width, self.rake_overhang
        oa = self.eave_overhang
        ob = self.eave_overhang_b if self.eave_overhang_b is not None else oa
        t = self.type
        if t in ("hip", "pyramid", "mansard", "flat"):
            return L / 2 + oa, -W / 2 - ob, W / 2 + oa
        if t == "shed":
            hi = self.shed_high_overhang if self.shed_high_overhang is not None else ob
            return L / 2 + ork, -W / 2 - hi, W / 2 + oa
        return L / 2 + ork, -W / 2 - ob, W / 2 + oa

    def roof_outline(self):
        if self.outline:
            return _ccw(Polygon(self.outline, self.outline_holes or []).buffer(0))
        umax, vlo, vhi = self.extents()
        r = self.rect(-umax, umax, vlo, vhi)
        if self.outline_holes:
            r = r.difference(unary_union([Polygon(h) for h in self.outline_holes]))
        return r

    def solid_polygon(self):
        """Region treated as 'solid building' for visibility (walls, or the outline of a roof-only wing)."""
        return self.roof_outline() if self.roof_only else self.wall_polygon()

    def _plane(self, p0_uv, n_uv, h, s):
        """Plane z = h + s * n.(p - p0) with n an inward unit vector (wing uv)."""
        p0 = self.to_world([p0_uv[0]], [p0_uv[1]])[0]
        n = n_uv[0] * self.u + n_uv[1] * self.v
        a, b = s * n[0], s * n[1]
        return (float(a), float(b), float(h - a * p0[0] - b * p0[1]))

    def planes(self):
        L, W, h, s = self.length, self.width, self.eave_height, self.pitch
        se = self.end_pitch if self.end_pitch is not None else s
        t = self.type
        P = []
        if t == "flat":
            return [(0.0, 0.0, float(h))]
        if t == "shed":
            # low eave on +v wall, rising toward -v
            return [self._plane((0, W / 2), (0, -1), h, s)]
        # side planes (rise from the +v and -v walls); pitch_b makes the -v side asymmetric
        sb = self.pitch_b if self.pitch_b is not None else s
        hb = self.eave_height_b if self.eave_height_b is not None else h
        P.append(self._plane((0, W / 2), (0, -1), h, s))
        P.append(self._plane((0, -W / 2), (0, 1), hb, sb))
        if t in ("hip", "pyramid", "mansard"):
            P.append(self._plane((L / 2, 0), (-1, 0), h, se))
            P.append(self._plane((-L / 2, 0), (1, 0), h, se))
        if t in ("gambrel", "mansard"):
            su = self.upper_pitch if self.upper_pitch is not None else s / 3.0
            b = self.break_inset if self.break_inset is not None else W / 4.0
            hbrk = h + s * b
            hbrk_b = hb + sb * b
            P.append(self._plane((0, W / 2 - b), (0, -1), hbrk, su))
            P.append(self._plane((0, -W / 2 + b), (0, 1), hbrk_b, su))
            if t == "mansard":
                be = self.break_inset if self.break_inset is not None else W / 4.0
                hbe = h + se * be
                P.append(self._plane((L / 2 - be, 0), (-1, 0), hbe, su))
                P.append(self._plane((-L / 2 + be, 0), (1, 0), hbe, su))
        return P

    def surface_z(self, xy):
        """Roof height at points (N,2); NaN outside this wing's roof outline."""
        xy = np.atleast_2d(np.asarray(xy, float))
        P = np.array(self.planes())
        z = (xy[:, :1] * P[:, 0] + xy[:, 1:2] * P[:, 1] + P[:, 2]).min(axis=1)
        if self.outline or self.outline_holes:
            inside = shapely.contains_xy(self.roof_outline().buffer(1e-9), xy[:, 0], xy[:, 1])
        else:
            rel = xy - np.array([self.cx, self.cy])
            uu, vv = rel @ self.u, rel @ self.v
            umax, vlo, vhi = self.extents()
            inside = (np.abs(uu) <= umax + 1e-9) & (vv >= vlo - 1e-9) & (vv <= vhi + 1e-9)
        z[~inside] = np.nan
        return z

    def inside_walls(self, xy, tol=1e-3):
        xy = np.atleast_2d(np.asarray(xy, float))
        if self.roof_only:
            return np.zeros(len(xy), bool)
        if self.walls:
            return shapely.contains_xy(self.wall_polygon().buffer(tol), xy[:, 0], xy[:, 1])
        rel = xy - np.array([self.cx, self.cy])
        return (np.abs(rel @ self.u) <= self.length / 2 + tol) & (np.abs(rel @ self.v) <= self.width / 2 + tol)


# ---------------------------------------------------------------------------
# polygon helpers
# ---------------------------------------------------------------------------

def _ccw(poly):
    """Polygon with a counter-clockwise exterior (wall sides are walked CCW so outward = right)."""
    from shapely.geometry.polygon import orient
    if poly.geom_type != "Polygon":
        poly = max(_polys(poly), key=lambda p: p.area) if _polys(poly) else Polygon()
    return orient(poly, 1.0) if not poly.is_empty else poly


def _clip_box(bounds, pad=5.0):
    x0, y0, x1, y1 = bounds
    return [(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)]


def halfplane(a, b, c, bounds):
    """Polygon {a x + b y + c <= 0} clipped to a padded bounds box."""
    pts = _clip_box(bounds)
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        fp, fq = a * p[0] + b * p[1] + c, a * q[0] + b * q[1] + c
        if fp <= 0:
            out.append(p)
        if (fp < 0) != (fq < 0) and fp != fq:
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    if len(out) < 3:
        return Polygon()
    return Polygon(out)


def _polys(g):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, (MultiPolygon, GeometryCollection)):
        out = []
        for gg in g.geoms:
            out.extend(_polys(gg))
        return out
    return []


def _clean(g, min_area=1e-6):
    ps = [p for p in _polys(g) if p.area > min_area]
    if not ps:
        return Polygon()
    return unary_union(ps) if len(ps) > 1 else ps[0]


def plane_z(plane, x, y):
    return plane[0] * x + plane[1] * y + plane[2]


def same_plane(p, q, tol=1e-6):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol and abs(p[2] - q[2]) < 1e-4


COPLANAR_SLOPE_TOL = 0.004   # rise/run (~0.05/12)
COPLANAR_Z_TOL = 0.03        # m, evaluated where the two pieces meet/overlap


def near_plane(p, q, where):
    """True when planes p and q coincide within tolerance over the polygon ``where``."""
    if abs(p[0] - q[0]) > COPLANAR_SLOPE_TOL or abs(p[1] - q[1]) > COPLANAR_SLOPE_TOL:
        return False
    if where is None or where.is_empty:
        return abs(p[2] - q[2]) < 1e-4
    xs, ys = zip(*where.envelope.exterior.coords) if where.envelope.geom_type == "Polygon" else ((where.centroid.x,), (where.centroid.y,))
    return all(abs(plane_z(p, x, y) - plane_z(q, x, y)) <= COPLANAR_Z_TOL for x, y in zip(xs, ys))


def plane_slope(plane):
    return math.hypot(plane[0], plane[1])


def plane_azimuth(plane):
    """Compass bearing (deg) of the downslope direction; None if flat."""
    a, b = plane[0], plane[1]
    if math.hypot(a, b) < 1e-9:
        return None
    return (math.degrees(math.atan2(-a, -b)) + 360.0) % 360.0


# ---------------------------------------------------------------------------
# main engine
# ---------------------------------------------------------------------------

@dataclass
class Facet:
    id: str
    wings: List[str]
    plane: tuple
    poly: object          # shapely (Multi)Polygon in plan
    hidden_from_above: bool = False

    @property
    def slope(self):
        return plane_slope(self.plane)

    @property
    def area_plan(self):
        return self.poly.area

    @property
    def area_true(self):
        return self.poly.area * math.sqrt(1.0 + self.slope ** 2)

    def z(self, x, y):
        return plane_z(self.plane, x, y)


@dataclass
class Edge:
    kind: str               # ridge hip valley eave rake transition headwall sidewall
    facets: List[str]
    p0: tuple               # 3-D endpoints
    p1: tuple
    penetration: Optional[str] = None   # headwall / sidewall round a solid standing through the roof: "WING:index"
                                        # of that wing's ``penetrations`` (chimney flashing); None otherwise

    @property
    def length(self):
        return float(np.linalg.norm(np.subtract(self.p1, self.p0)))


@dataclass
class Wall:
    wing: str
    side: str
    bearing: float          # outward-normal compass bearing
    length: float
    area_gross: float       # full wing wall incl. gable triangle
    area_exposed: float     # minus parts enclosed by other wings
    profile: list = field(default_factory=list)   # [(x,y,z_top)] along the wall
    bottom: list = field(default_factory=list)    # [(x,y,z)] at the two wall ends (grade or base_z)
    # with finished-grade levels (build(levels=...)): the exposed area split into what is below grade, the
    # exposed foundation / concrete band (grade up to the siding line) and the sided area above it
    area_buried: Optional[float] = None
    area_foundation: Optional[float] = None
    area_siding: Optional[float] = None
    grade_range: Optional[tuple] = None           # (lowest, highest) grade z outside the exposed parts of the wall


@dataclass
class BuildingModel:
    wings: List[Wing]
    facets: List[Facet]
    edges: List[Edge]
    walls: List[Wall]
    ground: Optional[tuple] = None   # (a, b, c): finished grade z = a x + b y + c in the model datum
    grade_extra: Optional[list] = None   # grade z seen at structures outside the wings (e.g. a garage under a deck)

    # ---- aggregate measurements (SI) -------------------------------------
    def edge_total(self, kind):
        return sum(e.length for e in self.edges if e.kind == kind)

    def roof_area(self):
        return sum(f.area_true for f in self.facets)

    def roof_area_plan(self):
        return sum(f.area_plan for f in self.facets)

    def footprint(self):
        return unary_union([w.wall_polygon() for w in self.wings if not w.roof_only])

    def roof_outline(self):
        return unary_union([w.roof_outline() for w in self.wings])

    def wall_area(self):
        return sum(w.area_exposed for w in self.walls)

    def surface_z(self, xy):
        """Top visible roof surface (what LiDAR / aerial photos see); NaN = no roof."""
        xy = np.atleast_2d(np.asarray(xy, float))
        zs = np.stack([w.surface_z(xy) for w in self.wings], axis=0)
        with np.errstate(all="ignore"):
            allnan = np.all(np.isnan(zs), axis=0)
            z = np.nanmax(np.where(np.isnan(zs), -np.inf, zs), axis=0)
        z[allnan] = np.nan
        return z

    def facet_at(self, x, y):
        p = Point(x, y)
        best, bz = None, -np.inf
        for f in self.facets:
            if f.poly.buffer(1e-6).contains(p):
                z = f.z(x, y)
                if z > bz:
                    best, bz = f, z
        return best

    def grade_range(self):
        """(lowest, highest) finished grade at the walls: the grade levels seen outside the exposed walls, else
        the wall bottoms (walls standing on grade; a wing whose walls all start above another storey counts
        too, so give levels for hillside houses); None when the model has a ground plane (heights are above it)."""
        if self.ground is not None or not self.walls:
            return None
        gr = [w.grade_range for w in self.walls if w.grade_range] + [(z, z) for z in (self.grade_extra or [])]
        if gr:
            return min(g[0] for g in gr), max(g[1] for g in gr)
        zs = [p[2] for w in self.walls if w.area_exposed > 1e-6 for p in w.bottom]
        return (min(zs), max(zs)) if zs else None

    def max_height(self):
        best = 0.0
        for f in self.facets:
            for poly in _polys(f.poly):
                for x, y in poly.exterior.coords:
                    best = max(best, f.z(x, y))
        return best

    def measurements(self):
        """Flat dict of every scalar the fusion / report layer can reference."""
        fp = self.footprint()
        ro = self.roof_outline()
        m = {
            "roof.area": self.roof_area(),
            "roof.area_plan": self.roof_area_plan(),
            "roof.facets": float(len(self.facets)),
            "footprint.area": fp.area,
            "footprint.perimeter": fp.length,
            "roof_outline.area": ro.area,
            "roof_outline.perimeter": ro.length,
            "wall.area": self.wall_area(),
            "building.height": self.max_height(),
        }
        if any(w.area_siding is not None for w in self.walls):
            m["wall.area_siding"] = sum(w.area_siding or 0.0 for w in self.walls)
            m["wall.area_foundation"] = sum(w.area_foundation or 0.0 for w in self.walls)
            m["wall.area_buried"] = sum(w.area_buried or 0.0 for w in self.walls)
        lo_hi = self.grade_range()
        if lo_hi is not None:
            m["grade.low"], m["grade.high"] = lo_hi
            m["building.height_low_side"] = m["building.height"] - lo_hi[0]
            m["building.height_high_side"] = m["building.height"] - lo_hi[1]
        for k in ("ridge", "hip", "valley", "eave", "rake", "transition", "headwall", "sidewall"):
            m[f"edge.{k}"] = self.edge_total(k)
        if self.facets:
            tot = self.roof_area()
            m["roof.pitch_weighted"] = sum(f.slope * f.area_true for f in self.facets) / max(tot, 1e-9)
            m["roof.pitch_max"] = max(f.slope for f in self.facets)
        for w in self.wings:
            m[f"wing.{w.id}.ridge_height"] = w.eave_height + _ridge_rise(w)
        return m


def _ridge_rise(w: Wing):
    """Rise from plate line to highest point of the wing roof."""
    P = w.planes()
    corners = w.wall_polygon()
    # sample a fine grid inside the walls; exact for lower-envelope maxima at grid nodes
    n = 41
    uu, vv = np.meshgrid(np.linspace(-w.length / 2, w.length / 2, n), np.linspace(-w.width / 2, w.width / 2, n))
    xy = w.to_world(uu.ravel(), vv.ravel())
    z = np.min(np.array([plane_z(p, xy[:, 0], xy[:, 1]) for p in P]), axis=0)
    return float(z.max() - w.eave_height)


def _wing_regions(w: Wing):
    """[(plane, polygon)] lower-envelope regions of a single wing."""
    outline = w.roof_outline()
    P = w.planes()
    bounds = outline.bounds
    regs = []
    for i, pi in enumerate(P):
        r = outline
        for j, pj in enumerate(P):
            if i == j:
                continue
            if same_plane(pi, pj):
                if j < i:
                    r = Polygon()
                    break
                continue
            # keep where plane_i <= plane_j
            r = r.intersection(halfplane(pi[0] - pj[0], pi[1] - pj[1], pi[2] - pj[2], bounds))
            if r.is_empty:
                break
        r = _clean(r)
        if not r.is_empty:
            regs.append((pi, r))
    return regs


MIN_FACET_AREA = 0.1   # m2: slivers smaller than this (numerical leftovers of hidden roofs) are not facets
OVERHUNG_CLEARANCE = 0.3   # m: an upper roof at least this far above a hidden lower roof piece never meets it there


def _overhung_clear(cand, plane, upper, clearance=OVERHUNG_CLEARANCE):
    """The pieces of ``cand`` (roof of ``plane`` hidden under wing ``upper``'s roof, outside the walls of both wings)
    that the upper roof clears by at least ``clearance`` everywhere: a lower roof running in under an upper overhang
    (real roofing, hidden from above). A piece where the roofs meet (min clearance ~0, e.g. the far side of a valley)
    stays hidden. The upper roof is the lower envelope of its planes (concave) and ``plane`` is linear, so the minimum
    clearance over a piece is reached at one of its vertices."""
    P = np.array(upper.planes())
    keep = []
    for piece in _polys(_clean(cand)):
        xy = np.array([c[:2] for ring in [piece.exterior, *piece.interiors] for c in ring.coords])
        zu = (xy[:, :1] * P[:, 0] + xy[:, 1:2] * P[:, 1] + P[:, 2]).min(axis=1)
        if float(np.min(zu - plane_z(plane, xy[:, 0], xy[:, 1]))) >= clearance:
            keep.append(piece)
    return unary_union(keep) if keep else Polygon()


def _penetration_cut(plane, poly, pens):
    """``poly`` (a facet of ``plane``) minus every penetration's plan polygon where the plane lies within its [z0, z1]."""
    a, b, c = plane
    cuts = []
    for pen in pens:
        ring = pen.get("polygon") if isinstance(pen, dict) else None
        if not ring or len(ring) < 3:
            raise ValueError(f"penetration needs a 'polygon' of >= 3 [x, y] points: {pen!r}")
        r = Polygon([p[:2] for p in ring]).buffer(0)
        if r.is_empty or not r.intersects(poly):
            continue
        z0, z1 = (list(pen.get("z") or []) + [None, None])[:2]
        if z1 is not None:
            r = r.intersection(halfplane(a, b, c - float(z1), r.bounds))     # plane z <= z1
        if z0 is not None and not r.is_empty:
            r = r.intersection(halfplane(-a, -b, float(z0) - c, r.bounds))  # plane z >= z0
        if not r.is_empty:
            cuts.append(r)
    return _clean(poly.difference(unary_union(cuts))) if cuts else poly


def _enclosed_pockets(vis, reg, solids):
    """Holes of a plane's kept roof ``vis`` that only the visibility test made: inside the plane's own region
    ``reg`` (so not an opening of the wing's own outline) and outside every other wing's walls / roof-only
    outline ``solids`` (so not where another wing stands on or rises through the roof)."""
    holes = [Polygon(r) for p in _polys(vis) for r in p.interiors]
    if not holes:
        return Polygon()
    pockets = unary_union(holes).intersection(reg)
    if solids:
        pockets = pockets.difference(unary_union(solids))
    return _clean(pockets)


def build(wings: List[Wing], wall_step=0.02, ground=None, levels=None) -> BuildingModel:
    """Build the exact model. ``levels(key, pts, outward, bottom) -> (grade_z, siding_from_z)`` (per wall
    "WING:side", sample points [n, 2] along it, outward unit normal, wall bottom z; NaN = unknown grade /
    siding from grade) splits each wall's
    exposed area into buried / foundation / siding (Wall.area_*). Facets under MIN_FACET_AREA are dropped.
    ``ground`` = (a, b, c) makes wall bottoms follow a planar
    grade z = a x + b y + c (same datum as eave heights); ``base_z`` is then an offset
    above that grade. Without ``ground`` walls start at z = base_z."""
    wings = [w if isinstance(w, Wing) else Wing.from_dict(w) for w in wings]
    regions = {w.id: _wing_regions(w) for w in wings}
    wall_polys = {w.id: w.solid_polygon() for w in wings}
    allb = unary_union([w.roof_outline() for w in wings]).bounds

    # ---- visibility between wings -------------------------------------------
    raw = []  # (wing_id, plane, poly, hidden_flag)
    for wi, W in enumerate(wings):
        for plane, reg in regions[W.id]:
            vis = reg
            under = Polygon()
            for vi, V in enumerate(wings):
                if V.id == W.id:
                    continue
                hide_parts = []
                for gplane, greg in regions[V.id]:
                    ov = greg.intersection(reg)
                    if same_plane(plane, gplane) or (not ov.is_empty and near_plane(plane, gplane, ov)):
                        if vi < wi:
                            hide_parts.append(greg)
                        continue
                    # where plane_g > plane_f  <=>  (f - g) < 0
                    hp = halfplane(plane[0] - gplane[0], plane[1] - gplane[1], plane[2] - gplane[2], allb)
                    hide_parts.append(greg.intersection(hp))
                if not hide_parts:
                    continue
                hide = unary_union(hide_parts)
                # exception: lower roof under a taller wing's overhang is kept: inside its own walls, and outside them
                # where the taller roof clears it everywhere (it runs in under the overhang, the roofs never meet)
                keep = wall_polys[W.id].difference(wall_polys[V.id])
                kept_under = hide.intersection(keep)
                hide = hide.difference(keep)
                clear = _overhung_clear(hide.intersection(reg).difference(wall_polys[V.id]), plane, V)
                if not clear.is_empty:
                    kept_under = unary_union([kept_under, clear])
                    hide = hide.difference(clear)
                vis = vis.difference(hide)
                under = unary_union([under, kept_under.intersection(vis)])
            vis = _clean(vis)
            # a roof is not opened by being overhung: a pocket of this plane hidden under another wing's roof and
            # enclosed by the plane's own kept roof (e.g. a lower eave under the corner of an upper roof) is real
            # roofing, hidden from above; openings of the wing's own outline and other wings' walls stay open
            pockets = _enclosed_pockets(vis, reg, [wall_polys[V.id] for V in wings if V.id != W.id])
            if not pockets.is_empty:
                vis = _clean(unary_union([vis, pockets]))
                under = unary_union([under, pockets])
            if not vis.is_empty:
                raw.append((W.id, plane, vis, under.area > 1e-4))

    # ---- merge coplanar facets across wings --------------------------------
    merged = []
    for wid, plane, poly, hid in raw:
        for m in merged:
            touch = m["poly"].buffer(EDGE_TOL).intersection(poly.buffer(EDGE_TOL))
            if not touch.is_empty and (same_plane(m["plane"], plane, tol=1e-6) or near_plane(m["plane"], plane, touch)):
                m["poly"] = _clean(unary_union([m["poly"], poly]).buffer(0))
                if wid not in m["wings"]:
                    m["wings"].append(wid)
                m["hid"] = m["hid"] or hid
                break
        else:
            merged.append({"plane": plane, "poly": poly, "wings": [wid], "hid": hid})
    # solids standing through the roof (chimneys, exterior chases): every facet stops at their faces
    pens = [p for w in wings for p in (w.penetrations or [])]
    if pens:
        for m in merged:
            m["poly"] = _penetration_cut(m["plane"], m["poly"], pens)
    merged = [m for m in merged if m["poly"].area * math.sqrt(1.0 + plane_slope(m["plane"]) ** 2) >= MIN_FACET_AREA]
    facets = [Facet(id=f"F{i + 1}", wings=m["wings"], plane=m["plane"], poly=m["poly"], hidden_from_above=m["hid"])
              for i, m in enumerate(merged)]

    edges = _classify_edges(facets, wings)
    walls = _walls(wings, wall_step, ground, levels)
    return BuildingModel(wings=wings, facets=facets, edges=edges, walls=walls,
                         ground=tuple(ground) if ground is not None else None)


def _ring_edges(poly):
    for p in _polys(poly):
        for ring in [p.exterior, *p.interiors]:
            c = list(ring.coords)
            for i in range(len(c) - 1):
                if math.dist(c[i], c[i + 1]) > 1e-9:
                    yield c[i][:2], c[i + 1][:2]


def _all_vertices(geoms):
    pts = []
    for g in geoms:
        for p in _polys(g):
            for ring in [p.exterior, *p.interiors]:
                pts.extend(c[:2] for c in ring.coords)
    return np.array(pts) if pts else np.zeros((0, 2))


def _split_edge(a, b, verts, tol=EDGE_TOL):
    """Split segment a-b at every vertex in ``verts`` lying on it (T-junctions)."""
    a, b = np.asarray(a), np.asarray(b)
    d = b - a
    L2 = float(d @ d)
    ts = {0.0, 1.0}
    if len(verts):
        t = ((verts - a) @ d) / L2
        proj = a + np.outer(t, d)
        dist = np.linalg.norm(verts - proj, axis=1)
        ok = (dist < tol) & (t > 1e-6) & (t < 1 - 1e-6)
        ts.update(float(x) for x in t[ok])
    ts = sorted(ts)
    out = []
    for t0, t1 in zip(ts[:-1], ts[1:]):
        if (t1 - t0) * math.sqrt(L2) > 1e-6:
            out.append((tuple(a + t0 * d), tuple(a + t1 * d)))
    return out


def _seg3d(plane, a, b):
    return (a[0], a[1], plane_z(plane, *a)), (b[0], b[1], plane_z(plane, *b))


def _is_horizontal(plane, a, b):
    L = math.dist(a, b)
    dz = abs(plane_z(plane, *a) - plane_z(plane, *b))
    return dz <= HORIZ_TOL * max(L, 1e-9)


def _merge_collinear(edges):
    """Join consecutive collinear edges of the same kind/facets (cosmetic, lengths unchanged)."""
    out = []
    for e in edges:
        if out:
            p = out[-1]
            if p.kind == e.kind and p.facets == e.facets and p.penetration == e.penetration \
                    and np.allclose(p.p1, e.p0, atol=1e-6):
                d0 = np.subtract(p.p1, p.p0)
                d1 = np.subtract(e.p1, e.p0)
                if np.linalg.norm(np.cross(d0, d1)) < 1e-9 * (np.linalg.norm(d0) * np.linalg.norm(d1) + 1e-12) + 1e-9:
                    out[-1] = Edge(p.kind, p.facets, p.p0, e.p1, p.penetration)
                    continue
        out.append(e)
    return out


def _classify_edges(facets: List[Facet], wings: List[Wing]):
    """Split every facet boundary at all T-junctions, then classify each piece.

    Shared piece with another facet at the same height -> ridge / hip / valley /
    transition (by convexity and slope directions). Unshared piece on the facet's
    own roof outline -> eave (horizontal) / rake (sloped). Anything else is a
    roof-to-wall junction -> headwall (horizontal) / sidewall (sloped, step flashing); a junction lying on
    the face of a solid standing through the roof (``Wing.penetrations``) is tagged with it (chimney flashing).
    """
    edges: List[Edge] = []
    outline = {w.id: w.roof_outline() for w in wings}
    verts = _all_vertices([f.poly for f in facets] + list(outline.values()))
    bnd = {f.id: f.poly.boundary for f in facets}
    obnd = {w: g.boundary for w, g in outline.items()}
    idx = {f.id: i for i, f in enumerate(facets)}
    pen_rings = [(f"{w.id}:{k}", Polygon([q[:2] for q in pen["polygon"]]).buffer(0).boundary)
                 for w in wings for k, pen in enumerate(w.penetrations or [])
                 if isinstance(pen, dict) and len(pen.get("polygon") or []) >= 3]

    for F in facets:
        pieces = []
        for a, b in _ring_edges(F.poly):
            pieces.extend(_split_edge(a, b, verts))
        for a, b in pieces:
            mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            mx, my = mid.x, mid.y
            partner = None
            for G in facets:
                if G.id == F.id or bnd[G.id].distance(mid) > EDGE_TOL:
                    continue
                if abs(F.z(mx, my) - G.z(mx, my)) <= Z_MATCH_TOL and abs(F.z(*a) - G.z(*a)) <= Z_MATCH_TOL:
                    partner = G
                    break
            if partner is not None:
                if idx[partner.id] < idx[F.id]:
                    continue  # already emitted from the partner's side
                G = partner
                d = np.subtract(b, a)
                nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-12)
                convex = True
                for sgn in (1, -1):
                    q = (mx + sgn * 0.05 * nrm[0], my + sgn * 0.05 * nrm[1])
                    if G.poly.contains(Point(q)):
                        convex = F.z(*q) > G.z(*q) + 1e-6
                        break
                horiz = _is_horizontal(F.plane, a, b)
                azf, azg = plane_azimuth(F.plane), plane_azimuth(G.plane)
                opposite = azf is not None and azg is not None and abs(((azf - azg + 180) % 360) - 180) > 135
                if horiz:
                    kind = ("ridge" if opposite else "transition") if convex else ("valley" if opposite else "transition")
                else:
                    kind = "hip" if convex else "valley"
                p0, p1 = _seg3d(F.plane, a, b)
                edges.append(Edge(kind, [F.id, G.id], p0, p1))
                continue
            on_outline = any(obnd[w].distance(mid) <= EDGE_TOL for w in F.wings)
            horiz = _is_horizontal(F.plane, a, b)
            if on_outline:
                kind = "eave" if horiz else "rake"
            else:
                kind = "headwall" if horiz else "sidewall"
            pen = None
            if not on_outline:
                pen = next((key for key, ring in pen_rings if ring.distance(mid) <= EDGE_TOL), None)
            p0, p1 = _seg3d(F.plane, a, b)
            edges.append(Edge(kind, [F.id], p0, p1, pen))
    return _merge_collinear(edges)


def _interval_cover(iv, lo, hi):
    """Length of [lo, hi] covered by the merged, sorted intervals iv."""
    if hi <= lo:
        return 0.0
    return sum(max(min(b_, hi) - max(a_, lo), 0.0) for a_, b_ in iv)


def _walls(wings: List[Wing], step, ground=None, levels=None):
    out = []

    def bottom_at(W, pts):
        b = np.full(len(pts), float(W.base_z))
        if ground is not None:  # base_z becomes an offset above grade (e.g. a wing on a raised deck)
            b = b + ground[0] * pts[:, 0] + ground[1] * pts[:, 1] + ground[2]
        return b

    for W in wings:
        if W.roof_only:
            continue
        L, Wd = W.length, W.width
        if W.walls:
            corners = np.array(list(W.wall_polygon().exterior.coords)[:-1])
            names = [f"w{k}" for k in range(len(corners))]
        else:
            corners = W.to_world([-L / 2, L / 2, L / 2, -L / 2], [-Wd / 2, -Wd / 2, Wd / 2, Wd / 2])
            names = ["-v", "+u", "+v", "-u"]
        P = np.array(W.planes())
        nc = len(corners)
        for k in range(nc):
            a, b = corners[k], corners[(k + 1) % nc]
            seg = np.subtract(b, a)
            length = float(np.linalg.norm(seg))
            n = max(int(math.ceil(length / step)), 1)
            t = (np.arange(n) + 0.5) / n
            pts = a + np.outer(t, seg)
            top = (pts[:, :1] * P[:, 0] + pts[:, 1:2] * P[:, 1] + P[:, 2]).min(axis=1)
            bot = bottom_at(W, pts)
            gross = float(np.sum(np.maximum(top - bot, 0)) * length / n)
            # hidden = the parts of [bot, top] that lie inside another wing's walls AND within that wing's own
            # height range [its wall bottom, its roof]: a stacked storey (a main floor over a lower level on the
            # same wall line) hides nothing, an interior wall is hidden completely
            hidden = np.zeros(len(pts))
            merged_iv = [[] for _ in range(len(pts))]
            spans = []
            for V in wings:
                if V.id == W.id or V.roof_only:
                    continue
                inside = V.inside_walls(pts)
                if inside.any():
                    PV = np.array(V.planes())
                    zv = (pts[:, :1] * PV[:, 0] + pts[:, 1:2] * PV[:, 1] + PV[:, 2]).min(axis=1)
                    vb = bottom_at(V, pts)
                    lo = np.where(inside, np.maximum(vb, bot), np.inf)
                    hi = np.where(inside, np.minimum(zv, top), -np.inf)
                    spans.append((lo, hi))
            if spans:
                for i_ in range(len(pts)):
                    iv = sorted((lo[i_], hi[i_]) for lo, hi in spans if hi[i_] > lo[i_])
                    tot, cur_lo, cur_hi = 0.0, None, None
                    for a_, b_ in iv:
                        if cur_hi is None or a_ > cur_hi:
                            if cur_hi is not None:
                                tot += cur_hi - cur_lo
                                merged_iv[i_].append((cur_lo, cur_hi))
                            cur_lo, cur_hi = a_, b_
                        else:
                            cur_hi = max(cur_hi, b_)
                    if cur_hi is not None:
                        tot += cur_hi - cur_lo
                        merged_iv[i_].append((cur_lo, cur_hi))
                    hidden[i_] = tot
            exposed = float(np.sum(np.maximum(np.maximum(top - bot, 0) - hidden, 0)) * length / n)
            outward = np.array([seg[1], -seg[0]]) / (length + 1e-12)  # corners are CCW
            split = None
            if levels is not None:
                g, s_ = (np.asarray(v, float) for v in levels(f"{W.id}:{names[k]}", pts, outward, bot))
                gg = np.where(np.isfinite(g), g, bot)                   # unknown grade: the wall bottom
                ss = np.maximum(np.where(np.isfinite(s_), s_, gg), gg)  # siding starts at or above grade
                bur = fnd = sid = 0.0
                seen_g = []
                for i_ in range(len(pts)):
                    lo_, hi_ = bot[i_], top[i_]
                    if hi_ <= lo_:
                        continue
                    iv = merged_iv[i_]

                    def vis(a_, b_):
                        a_, b_ = max(a_, lo_), min(b_, hi_)
                        return max(b_ - a_, 0.0) - _interval_cover(iv, a_, b_)
                    bur += vis(lo_, gg[i_]); fnd += vis(gg[i_], ss[i_]); sid += vis(ss[i_], hi_)
                    if np.isfinite(g[i_]) and vis(lo_, hi_) > 1e-6:
                        seen_g.append(g[i_])
                f_ = length / n
                split = (bur * f_, fnd * f_, sid * f_, (float(min(seen_g)), float(max(seen_g))) if seen_g else None)
            bearing = (math.degrees(math.atan2(outward[0], outward[1])) + 360) % 360
            # exact top profile: wall endpoints + every place the envelope changes plane
            prof_t = {0.0, 1.0}
            for i in range(len(P)):
                for j in range(i + 1, len(P)):
                    da = P[i] - P[j]
                    fa = da[0] * a[0] + da[1] * a[1] + da[2]
                    fb = da[0] * b[0] + da[1] * b[1] + da[2]
                    if fa != fb and (fa <= 0) != (fb <= 0):
                        prof_t.add(fa / (fa - fb))
            prof = []
            for tt in sorted(prof_t):
                p = a + tt * seg
                prof.append((float(p[0]), float(p[1]), float(np.min(P[:, 0] * p[0] + P[:, 1] * p[1] + P[:, 2]))))
            ends = np.array([a, b])
            wall = Wall(W.id, names[k], bearing, length, gross, exposed, prof)
            wall.bottom = [(float(x), float(y), float(z)) for (x, y), z in zip(ends, bottom_at(W, ends))]
            if split is not None:
                wall.area_buried, wall.area_foundation, wall.area_siding, wall.grade_range = split
            out.append(wall)
    return out


# ---------------------------------------------------------------------------
# serialisation for Blender / reports
# ---------------------------------------------------------------------------

def _ring3d(plane, coords):
    return [[float(x), float(y), float(plane_z(plane, x, y))] for x, y in list(coords)[:-1]]


def to_mesh_json(model: BuildingModel):
    """Plain-JSON geometry consumed by scripts/blender/build_model.py (no shapely needed there)."""
    facets = []
    for f in model.facets:
        polys = []
        for p in _polys(f.poly):
            p = p.simplify(1e-5)
            polys.append({"outer": _ring3d(f.plane, p.exterior.coords),
                          "holes": [_ring3d(f.plane, r.coords) for r in p.interiors]})
        facets.append({
            "id": f.id, "wings": f.wings, "plane": list(f.plane), "polygons": polys,
            "pitch_rise_per_12": f.slope * 12, "azimuth": plane_azimuth(f.plane),
            "area_m2": f.area_true, "hidden_from_above": f.hidden_from_above,
        })
    walls = [{"wing": w.wing, "side": w.side, "bearing": w.bearing, "base_z": next(x.base_z for x in model.wings if x.id == w.wing),
              "profile": w.profile, "bottom": w.bottom, "area_exposed_m2": w.area_exposed,
              **({"area_buried_m2": w.area_buried, "area_foundation_m2": w.area_foundation, "area_siding_m2": w.area_siding,
                  "grade_range": list(w.grade_range) if w.grade_range else None} if w.area_siding is not None else {})}
             for w in model.walls]
    edges = [{"kind": e.kind, "facets": e.facets, "p0": list(e.p0), "p1": list(e.p1), "length_m": e.length,
              **({"penetration": e.penetration} if e.penetration else {})} for e in model.edges]
    return {"facets": facets, "walls": walls, "edges": edges, "wings": [w.to_dict() for w in model.wings],
            "ground": list(model.ground) if model.ground is not None else None}
