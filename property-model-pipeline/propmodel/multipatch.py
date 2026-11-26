"""City LOD2 roofs (Esri multipatch) -> faces, roof planes, a low-weight ``roof_z`` observation.

Some cities publish 3-D building models as ArcGIS multipatch layers. A query with ``returnZ=true&f=json``
returns each geometry either as ``binaryPatches`` (base64 of an Esri shape buffer, usually zlib-compressed
behind a 12-byte header [type | 0x00800000, uncompressed size, compressed size]) or as JSON ``rings``.
The shape buffer is the shapefile MultiPatch layout (type 31 / extended 54 with HasZ / HasM flags)::

    uint32 type; double xmin, ymin, xmax, ymax; int32 nparts, npoints; int32 parts[nparts];
    int32 part_types[nparts]; double xy[2 npoints]; double zmin, zmax; double z[npoints]; [M range + M]

Part types: 0 triangle strip, 1 triangle fan, 2 outer ring, 3 inner ring, 4 first ring, 5 ring, 6 triangles.

Coordinates of state-plane layers are large (2e6..2e7 ft), so every vertex comparison here uses an ABSOLUTE
tolerance (``np.isclose(..., rtol=0, atol=...)``): numpy's default relative tolerance (1e-5) would call
vertices 20 ft apart "the same" at x = 2e6 ft.

Faces are classified in the local frame: vertical (|n_z| < 0.1) = wall, horizontal at the solid's base =
floor, everything else = roof. The roof is registered to the LiDAR roof returns by a horizontal grid search
(city layers sit ~1 m off the 3DEP frame), sampled on a grid inside each roof face (inset from its edges)
and written as one ``roof_z`` observation with a vertical nuisance ``shift.<name>.dz`` and a generous sigma:
a city model is a check on the LiDAR (form, pitch), not a second measurement of equal weight.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

PART_TYPES = {0: "triangle_strip", 1: "triangle_fan", 2: "outer_ring", 3: "inner_ring", 4: "first_ring", 5: "ring",
              6: "triangles"}
Z_UNITS = {"m": 1.0, "meter": 1.0, "metre": 1.0, "ft": 0.3048, "foot": 0.3048, "ftus": 1200.0 / 3937.0,
           "us_ft": 1200.0 / 3937.0, "usft": 1200.0 / 3937.0, "foot_us": 1200.0 / 3937.0}
HAS_Z, HAS_M = 0x80000000, 0x40000000


# ---------------------------------------------------------------------------
# decoding
# ---------------------------------------------------------------------------

def unwrap_binary_patches(b64):
    """base64 binaryPatches -> raw shape buffer (zlib-decompressed when compressed)."""
    b = base64.b64decode(b64)
    if len(b) >= 14:
        t, usz, csz = struct.unpack_from("<III", b, 0)
        if 12 + csz <= len(b) and b[12] == 0x78:       # zlib stream behind the 12-byte header
            raw = zlib.decompress(b[12:12 + csz])
            if usz and len(raw) != usz:
                raise ValueError(f"binaryPatches: {len(raw)} bytes after inflate, header says {usz}")
            return raw
    return b


def decode_shape_buffer(raw):
    """Esri multipatch shape buffer -> {"type", "bbox", "parts": [(part_type, points (n, 3))]}."""
    o = 0
    t, = struct.unpack_from("<I", raw, o); o += 4
    base = t & 0xFF
    if base not in (31, 32, 54):
        raise ValueError(f"not a multipatch shape buffer (type 0x{t:08x})")
    bbox = struct.unpack_from("<4d", raw, o); o += 32
    npart, npt = struct.unpack_from("<2i", raw, o); o += 8
    parts = list(struct.unpack_from(f"<{npart}i", raw, o)); o += 4 * npart
    ptypes = [v & 0xF for v in struct.unpack_from(f"<{npart}i", raw, o)]; o += 4 * npart
    xy = np.frombuffer(raw, "<f8", 2 * npt, o).reshape(npt, 2); o += 16 * npt
    if base == 31 or (t & HAS_Z) or len(raw) >= o + 16 + 8 * npt:
        o += 16
        z = np.frombuffer(raw, "<f8", npt, o); o += 8 * npt
    else:
        z = np.zeros(npt)
    P = np.column_stack([xy, z]).astype(float)
    bounds = parts + [npt]
    out = [(ptypes[k], P[bounds[k]:bounds[k + 1]]) for k in range(npart)]
    return {"type": int(t), "bbox": list(bbox), "parts": out}


def encode_shape_buffer(parts, compress=True):
    """Inverse of decode (tests / fixtures): parts [(part_type, (n, 3) array)] -> base64 binaryPatches."""
    P = np.vstack([p for _, p in parts]).astype(float)
    starts, k = [], 0
    for _, p in parts:
        starts.append(k)
        k += len(p)
    t = HAS_Z | 54
    raw = struct.pack("<I", t) + struct.pack("<4d", P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max())
    raw += struct.pack("<2i", len(parts), len(P)) + struct.pack(f"<{len(parts)}i", *starts)
    raw += struct.pack(f"<{len(parts)}i", *[pt for pt, _ in parts]) + P[:, :2].astype("<f8").tobytes()
    raw += struct.pack("<2d", P[:, 2].min(), P[:, 2].max()) + P[:, 2].astype("<f8").tobytes()
    if not compress:
        return base64.b64encode(raw).decode()
    c = zlib.compress(raw, 9)
    return base64.b64encode(struct.pack("<III", t | 0x00800000, len(raw), len(c)) + c).decode()


def geometry_parts(geom):
    """An ArcGIS / GeoJSON geometry -> [(part_type, (n, 3))] (binaryPatches, Esri JSON rings, GeoJSON polygons)."""
    if not geom:
        return []
    if geom.get("binaryPatches"):
        return decode_shape_buffer(unwrap_binary_patches(geom["binaryPatches"]))["parts"]
    if geom.get("rings"):
        return [(5 if i else 4, np.asarray(r, float)[:, :3]) for i, r in enumerate(geom["rings"])]
    t = geom.get("type")
    if t in ("Polygon", "MultiPolygon"):
        polys = [geom["coordinates"]] if t == "Polygon" else geom["coordinates"]
        out = []
        for poly in polys:
            for i, r in enumerate(poly):
                out.append((2 if i == 0 else 3, np.asarray(r, float)[:, :3]))
        return out
    return []


def _clean_ring(P, atol):
    """Drop the closing vertex and consecutive duplicates (absolute tolerance, rtol=0)."""
    P = np.asarray(P, float)
    keep = [0]
    for i in range(1, len(P)):
        if not np.allclose(P[i], P[keep[-1]], rtol=0, atol=atol):
            keep.append(i)
    P = P[keep]
    if len(P) > 1 and np.allclose(P[0], P[-1], rtol=0, atol=atol):
        P = P[:-1]
    return P


def faces_from_parts(parts, atol):
    """[(part_type, points)] -> faces [{"outer": (n, 3), "holes": [(m, 3)]}]. ``atol`` in the coordinates' units."""
    faces = []
    for pt, P in parts:
        if pt == 0:          # strip
            for i in range(len(P) - 2):
                faces.append({"outer": P[[i, i + 1, i + 2]], "holes": []})
        elif pt == 1:        # fan
            for i in range(1, len(P) - 1):
                faces.append({"outer": P[[0, i, i + 1]], "holes": []})
        elif pt == 6:        # triangles
            for i in range(0, len(P) - 2, 3):
                faces.append({"outer": P[i:i + 3], "holes": []})
        else:
            R = _clean_ring(P, atol)
            if len(R) < 3:
                continue
            if pt in (3, 5) and faces and faces[-1].get("ring") and _inside(R, faces[-1]["outer"]):
                faces[-1]["holes"].append(R)
            else:
                faces.append({"outer": R, "holes": [], "ring": True})
    for f in faces:
        f.pop("ring", None)
    return [f for f in faces if len(_clean_ring(f["outer"], atol)) >= 3]


def _inside(R, outer):
    try:
        return Polygon(np.asarray(outer)[:, :2]).buffer(1e-9).contains(Polygon(np.asarray(R)[:, :2]))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# geometry in the local frame
# ---------------------------------------------------------------------------

def newell_normal(P):
    P = np.asarray(P, float)
    Q = np.roll(P, -1, axis=0)
    n = np.array([np.sum((P[:, 1] - Q[:, 1]) * (P[:, 2] + Q[:, 2])),
                  np.sum((P[:, 2] - Q[:, 2]) * (P[:, 0] + Q[:, 0])),
                  np.sum((P[:, 0] - Q[:, 0]) * (P[:, 1] + Q[:, 1]))])
    L = np.linalg.norm(n)
    return n / L if L > 1e-12 else n


def to_local(faces, frame=None, z_unit=1.0, datum=0.0, lonlat=True, xy_unit=1.0):
    """Faces in lon/lat (or projected) + z in ``z_unit`` -> local ENU metres, z above ``datum``."""
    out = []
    for f in faces:
        rings = []
        for R in [f["outer"]] + list(f["holes"]):
            R = np.asarray(R, float)
            if lonlat:
                x, y, _ = frame.from_geodetic(R[:, 1], R[:, 0])
            else:
                x, y = R[:, 0] * xy_unit, R[:, 1] * xy_unit
            rings.append(np.column_stack([x, y, R[:, 2] * z_unit - datum]))
        out.append({"outer": rings[0], "holes": rings[1:]})
    return out


def classify(faces, vertical=0.1, base_tol=0.3):
    """Adds kind (roof | wall | floor), plane (a, b, c with z = ax + by + c), pitch (rise/12), azimuth, plan
    polygon and 3-D area to every face (local metres). Floor = a horizontal face at the solid's lowest level."""
    if not faces:
        return faces
    zmin = min(float(np.min(f["outer"][:, 2])) for f in faces)
    for f in faces:
        P = f["outer"]
        n = newell_normal(P)
        if n[2] < 0:
            n = -n
        plan = Polygon(P[:, :2], [h[:, :2] for h in f["holes"]]).buffer(0)
        f["normal"] = n.tolist()
        if abs(n[2]) < vertical:
            f.update(kind="wall", plan=plan, area_m2=_area3d(f))
            continue
        a, b = -n[0] / n[2], -n[1] / n[2]
        c = float(np.mean(P[:, 2] - a * P[:, 0] - b * P[:, 1]))
        slope = math.hypot(a, b)
        horiz = slope < 0.02
        kind = "floor" if horiz and float(np.max(P[:, 2])) < zmin + base_tol else "roof"
        f.update(kind=kind, plane=[float(a), float(b), c], plan=plan, slope=slope, pitch=slope * 12,
                 azimuth=(math.degrees(math.atan2(-a, -b)) + 360) % 360 if slope > 1e-3 else None,
                 area_m2=plan.area * math.sqrt(1 + slope ** 2))
    return faces


def _area3d(f):
    n = newell_normal(f["outer"])
    P = f["outer"]
    # area of a planar polygon = |sum cross| / 2 projected on its normal
    s = np.zeros(3)
    for i in range(len(P)):
        s += np.cross(P[i], P[(i + 1) % len(P)])
    return float(abs(np.dot(s, n)) / 2)


def roof_faces(faces):
    return [f for f in faces if f.get("kind") == "roof"]


def surface_z(faces, xy):
    """Top of the roof faces at xy (NaN outside)."""
    xy = np.atleast_2d(np.asarray(xy, float))
    z = np.full(len(xy), -np.inf)
    for f in roof_faces(faces):
        a, b, c = f["plane"]
        inside = shapely.contains_xy(f["plan"], xy[:, 0], xy[:, 1])
        z = np.where(inside, np.maximum(z, a * xy[:, 0] + b * xy[:, 1] + c), z)
    z[~np.isfinite(z)] = np.nan
    return z


def register(faces, pts, search=2.0, step=0.2, refine=0.05, cap=0.5):
    """Horizontal (dx, dy) and vertical dz that move the city roof onto LiDAR roof points ``pts`` (x, y, z in the
    model frame): model = city + (dx, dy), z_model = z_city + dz. Robust cost: mean of min(|r - median r|, cap)
    with points the shifted roof does not cover counted as ``cap``."""
    pts = np.asarray(pts, float)
    if len(pts) > 3000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 3000, replace=False)]

    def cost(dx, dy):
        z = surface_z(faces, pts[:, :2] - [dx, dy])
        r = pts[:, 2] - z
        ok = np.isfinite(r)
        if ok.sum() < 10:
            return 9.9, 0.0
        dz = float(np.median(r[ok]))
        e = np.full(len(r), cap)
        e[ok] = np.minimum(np.abs(r[ok] - dz), cap)
        return float(e.mean()), dz

    best = (9e9, 0.0, 0.0, 0.0)
    for grid, centre in ((np.arange(-search, search + 1e-9, step), (0.0, 0.0)),
                         (np.arange(-2 * step, 2 * step + 1e-9, refine), None)):
        c0 = centre if centre is not None else (best[1], best[2])
        for dx in c0[0] + grid:
            for dy in c0[1] + grid:
                c, dz = cost(dx, dy)
                if c < best[0]:
                    best = (c, float(dx), float(dy), dz)
    c, dx, dy, dz = best
    z = surface_z(faces, pts[:, :2] - [dx, dy])
    r = pts[:, 2] - (z + dz)
    ok = np.isfinite(r)
    return {"dx": round(dx, 3), "dy": round(dy, 3), "dz": round(dz, 3), "cost_m": round(c, 4),
            "robust_sd_m": round(float(1.4826 * np.median(np.abs(r[ok]))) if ok.any() else float("nan"), 4),
            "covered": round(float(ok.mean()), 3), "n": int(len(pts))}


def sample_roof(faces, spacing=0.5, inset=0.35, max_points=300, seed=0):
    """Grid samples (x, y, z) inside every roof face, ``inset`` m from its edges (local frame)."""
    out = []
    for f in roof_faces(faces):
        P = f["plan"].buffer(-inset)
        if P.is_empty:
            continue
        x0, y0, x1, y1 = P.bounds
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1e-9, spacing), np.arange(y0, y1 + 1e-9, spacing))
        q = np.column_stack([gx.ravel(), gy.ravel()])
        q = q[shapely.contains_xy(P, q[:, 0], q[:, 1])]
        a, b, c = f["plane"]
        out.append(np.column_stack([q, a * q[:, 0] + b * q[:, 1] + c]))
    pts = np.vstack(out) if out else np.zeros((0, 3))
    # the top surface only (a face hidden under another roof is not what the LiDAR sees)
    if len(pts):
        top = surface_z(faces, pts[:, :2])
        pts = pts[np.abs(pts[:, 2] - top) < 0.05]
    if len(pts) > max_points:
        pts = pts[np.sort(np.random.default_rng(seed).choice(len(pts), max_points, replace=False))]
    return pts


def pick_building(features_faces, xy=(0.0, 0.0)):
    """Index of the multipatch whose roof plan contains ``xy`` (else the nearest)."""
    from shapely.geometry import Point
    best, bd = None, 1e18
    for i, faces in enumerate(features_faces):
        rf = roof_faces(faces)
        if not rf:
            continue
        u = unary_union([f["plan"] for f in rf])
        d = u.distance(Point(xy))
        if d < bd:
            best, bd = i, d
    return best, bd


def summary(faces, planes=None, shift=(0.0, 0.0)):
    """Roof area (sloped), plan area, per-face pitch, and a pitch check against LiDAR planes (lidar.json)."""
    rf = roof_faces(faces)
    out = {"faces": [], "roof_area_m2": round(float(sum(f["area_m2"] for f in rf)), 3),
           "plan_area_m2": round(float(unary_union([f["plan"] for f in rf]).area), 3) if rf else 0.0,
           "walls": sum(f.get("kind") == "wall" for f in faces)}
    from shapely import affinity
    for k, f in enumerate(rf):
        row = {"face": k, "area_m2": round(f["area_m2"], 2), "pitch": round(f["pitch"], 2),
               "azimuth": None if f["azimuth"] is None else round(f["azimuth"], 1)}
        if planes and f["azimuth"] is not None and f["area_m2"] >= 8.0:
            poly = affinity.translate(f["plan"], *shift).buffer(1.0)
            cand = []
            for j, p in enumerate(planes):
                if p.get("azimuth") is None:
                    continue
                daz = abs(((p["azimuth"] - f["azimuth"] + 180) % 360) - 180)
                cx, cy = p["centroid"][:2]
                if daz < 30 and poly.contains(shapely.geometry.Point(cx, cy)):
                    cand.append((p["n"], j, p))
            if cand:
                _, j, p = max(cand)
                row.update(lidar_plane=f"P{j + 1}", pitch_lidar=round(p["pitch_rise_per_12"], 2),
                           pitch_diff=round(f["pitch"] - p["pitch_rise_per_12"], 2))
        out["faces"].append(row)
    return out


def local_faces_json(faces):
    """JSON-safe copy (drops shapely objects)."""
    out = []
    for f in faces:
        out.append({"kind": f.get("kind"), "outer": np.round(f["outer"], 3).tolist(),
                    "holes": [np.round(h, 3).tolist() for h in f["holes"]],
                    **({"plane": f["plane"], "pitch": round(f["pitch"], 3), "azimuth": f["azimuth"],
                        "area_m2": round(f["area_m2"], 3)} if f.get("kind") in ("roof", "floor") else
                       {"area_m2": round(f.get("area_m2", 0.0), 3)})})
    return out
