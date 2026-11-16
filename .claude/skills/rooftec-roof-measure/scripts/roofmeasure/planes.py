"""Roof planes and roof lines from the faces of a building solid.

Input: polygons (Nx3, source units, usually US survey feet in EPSG 32164).
Output: a `RoofModel` in local metres (x east, y north, z up) with

* planes: merged coplanar roof faces with pitch, azimuth, plan and sloped area;
* edges: ridge, hip, valley, eave, rake, plus `step_flashing` / `headwall`
  (a roof meeting a wall that rises above it) and `top` (the high edge of a shed roof);
* walls: for display only.

"Subtract first, convert second": the local origin is subtracted in float64 feet
before the conversion to metres, so nothing is lost to 32-bit meshes later.
"""
import math

import numpy as np

from .units import FT_US

SNAP_M = 0.02            # vertices closer than this are one vertex
WALL_NZ = 0.087          # faces within 5 degrees of vertical are walls
MERGE_DEG = 3.0          # roof faces closer than this in angle, and touching, are one plane
MERGE_OFFSET_M = 0.10
HORIZONTAL_DEG = 3.0     # an edge flatter than this is "horizontal" (ridge, eave)
LEVEL_PLAN_DEG = 10.0    # ... or one that runs within this angle of its plane's contour line, seen from above
UPDIP_PLAN_DEG = 45.0    # an open edge further than this from the contour line runs up the slope: never "level"
SEAM_SIN = 0.02          # roof-roof folds flatter than about 1 degree are not an edge
REGULARIZE_ITERS = 40
REGULARIZE_WARN_SHIFT_M = 0.30
REGULARIZE_WARN_GAP_M = 0.03
WALL_NEAR_M = 0.08       # a roof edge this close to a wall's plane is at that wall
WALL_PROBE_UP_M = (0.10, 0.25)   # heights above a roof edge at which a wall must exist to count
WALL_WEIGHT = 1e3        # how strongly an outline corner is held on its wall planes during a re-tilt
SPLIT_RIDGE_M = 0.15     # two plane tops closer than this are one ridge that the source drew with a sliver wall
ROOF_TYPES = ("ridge", "hip", "valley", "eave", "rake", "step_flashing", "headwall", "top")


def newell(p):
    """Area vector of a 3D polygon (length = area, direction = normal by the right-hand rule)."""
    q = np.roll(p, -1, axis=0)
    return 0.5 * np.array([
        np.sum((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])),
        np.sum((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])),
        np.sum((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1])),
    ])


def _pnpoly(poly2, x, y):
    a, b = poly2, np.roll(poly2, -1, axis=0)
    cond = (a[:, 1] > y) != (b[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return bool(np.count_nonzero(cond & (x < xi)) % 2)


def triangulate(poly2):
    """Ear clipping for a simple polygon given as Nx2 (any winding). Returns index triples."""
    n = len(poly2)
    idx = list(range(n))
    area2 = np.sum(poly2[:, 0] * np.roll(poly2[:, 1], -1) - np.roll(poly2[:, 0], -1) * poly2[:, 1])
    if area2 < 0:
        idx.reverse()
    tris = []

    def cross(i, j, k):
        a, b, c = poly2[i], poly2[j], poly2[k]
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        best, clipped = None, False
        m = len(idx)
        for q in range(m):
            i, j, k = idx[q - 1], idx[q], idx[(q + 1) % m]
            c = cross(i, j, k)
            if best is None or abs(c) < best[0]:
                best = (abs(c), q)
            if c <= 1e-12:
                continue
            ok = True
            for r in idx:
                if r in (i, j, k):
                    continue
                if cross(i, j, r) >= -1e-12 and cross(j, k, r) >= -1e-12 and cross(k, i, r) >= -1e-12:
                    ok = False
                    break
            if ok:
                tris.append((i, j, k))
                idx.pop(q)
                clipped = True
                break
        if not clipped:  # numerically stuck: drop the flattest corner
            q = best[1]
            if best[0] > 1e-12:
                tris.append((idx[q - 1], idx[q], idx[(q + 1) % m]))
            idx.pop(q)
    if len(idx) == 3 and abs(cross(*idx)) > 1e-12:
        tris.append(tuple(idx))
    return tris


def simple_loops(p):
    """Split a ring (Nx3) that crosses or touches itself, seen from above, into simple loops. Returns Nx3 arrays.

    About one city roof face in 25 is drawn with a twisted corner: two of its edges cross (review round 5:
    17 of 444 faces, on 12 of 64 houses). Ear clipping cannot triangulate such a ring and covered up to 10 m2 that is
    not roof. The ring is cut at each crossing; the small loop a twist encloses runs the other way round and
    is left out. A ring that does not cross itself comes back unchanged.
    """
    p = np.asarray(p, dtype=np.float64)
    n = len(p)
    if n < 4:
        return [p]
    total = _signed_plan_area(p)
    out = []
    todo = [p]
    while todo:
        q = todo.pop()
        cut = _first_crossing(q)
        if cut is None:
            a = _signed_plan_area(q)
            if len(q) >= 3 and abs(a) > 1e-6 and (a > 0) == (total > 0):
                out.append(q)
            continue
        i, j, x = cut
        todo.append(np.vstack([x[None, :], q[i + 1:j + 1]]))
        todo.append(np.vstack([q[:i + 1], x[None, :], q[j + 1:]]))
    return out if out else [p]


def _signed_plan_area(q):
    return 0.5 * float(np.sum(q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]))


def _first_crossing(q, tol=1e-9, end=1e-6):
    """(i, j, point) for the first pair of edges i < j of the ring that cross seen from above, else None.

    An edge that only touches another with one of its ends counts too (`end`): that is a spike or a pinch.
    """
    n = len(q)
    for i in range(n):
        a, b = q[i], q[(i + 1) % n]
        r = b[:2] - a[:2]
        for j in range(i + 2, n):
            if (j + 1) % n == i:
                continue
            c, d = q[j], q[(j + 1) % n]
            s = d[:2] - c[:2]
            den = r[0] * s[1] - r[1] * s[0]
            if abs(den) < 1e-12:
                continue
            w = c[:2] - a[:2]
            t = (w[0] * s[1] - w[1] * s[0]) / den
            u = (w[0] * r[1] - w[1] * r[0]) / den
            if (tol < t < 1 - tol and -end <= u <= 1 + end) or (tol < u < 1 - tol and -end <= t <= 1 + end):
                t = min(max(t, 0.0), 1.0)
                return i, j, a + t * (b - a)
    return None


class RoofModel:
    """Result of `build_model`. All coordinates are local metres."""

    def __init__(self):
        self.origin_ft = None       # (easting, northing, elevation) of local (0, 0, 0) in source feet
        self.verts = None           # Vx3 regularized vertices
        self.verts_raw = None       # Vx3 as delivered
        self.faces = []             # dicts: kind, loop (vertex ids), plane (index or None)
        self.planes = []            # dicts, see _plane_record
        self.edges = []             # dicts: type, a, b (xyz), lengthM, planes [ids]
        self.stats = {}

    # -- convenience -------------------------------------------------------
    def totals(self):
        out = {t: {"lengthM": 0.0, "count": 0} for t in ROOF_TYPES}
        for e in self.edges:
            out[e["type"]]["lengthM"] += e["lengthM"]
            out[e["type"]]["count"] += 1
        return out

    @property
    def plan_area(self):
        return sum(p["planAreaM2"] for p in self.planes)

    @property
    def sloped_area(self):
        return sum(p["areaM2"] for p in self.planes)

    def roof_triangles(self):
        """[(plane index, 3x3 array)] triangles of the roof, wound counter-clockwise seen from above."""
        out = []
        for f in self.faces:
            if f["kind"] != "roof":
                continue
            for p in simple_loops(self.verts[f["ring"]]):
                for t in triangulate(p[:, :2]):
                    tri = p[list(t)]
                    if newell(tri)[2] < 0:
                        tri = tri[::-1]
                    out.append((f["plane"], tri))
        return out

    def wall_triangles(self, floor_z=None):
        out = []
        for f in self.faces:
            if f["kind"] != "wall":
                continue
            p = self.verts[f["ring"]].copy()
            if floor_z is not None:
                p[:, 2] = np.maximum(p[:, 2], floor_z)
            n = f["n"]
            t = np.array([-n[1], n[0], 0.0])
            t /= np.linalg.norm(t) or 1.0
            p2 = np.column_stack([p @ t, p[:, 2]])
            for tr in triangulate(p2):
                tri = p[list(tr)]
                if np.linalg.norm(newell(tri)) < 1e-6:
                    continue
                if newell(tri) @ n < 0:
                    tri = tri[::-1]
                out.append(tri)
        return out


def _snap(points, tol):
    """Cluster points closer than tol. Returns (representatives Vx3, index of each input point)."""
    reps, ids = [], np.empty(len(points), dtype=int)
    cells = {}
    inv = 1.0 / tol
    for i, p in enumerate(points):
        c = tuple(np.floor(p * inv).astype(int))
        found = -1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in cells.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                        if np.linalg.norm(reps[j] - p) <= tol:
                            found = j
                            break
                    if found >= 0:
                        break
                if found >= 0:
                    break
            if found >= 0:
                break
        if found < 0:
            found = len(reps)
            reps.append(p.copy())
            cells.setdefault(c, []).append(found)
        ids[i] = found
    return np.array(reps), ids


def _dedupe_loop(loop):
    out = []
    for v in loop:
        if not out or out[-1] != v:
            out.append(v)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _split_loop(loop, verts, tol):
    """Insert every vertex that lies on an edge of the loop (T-junctions) so shared edges match exactly."""
    out = []
    n = len(loop)
    for q in range(n):
        i, j = loop[q], loop[(q + 1) % n]
        a, b = verts[i], verts[j]
        d = b - a
        L2 = float(d @ d)
        out.append(i)
        if L2 < 1e-12:
            continue
        t = ((verts - a) @ d) / L2
        dist = np.linalg.norm(verts - (a + np.outer(t, d)), axis=1)
        L = math.sqrt(L2)
        on = np.nonzero((dist <= tol) & (t * L > tol) & ((1 - t) * L > tol))[0]
        for k in sorted(on, key=lambda k: t[k]):
            if k != i and k != j:
                out.append(int(k))
    return _dedupe_loop(out)


class _DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def build_model(faces_src, unit_m=FT_US, origin=None, ground_z=None):
    """Faces of a closed building solid -> RoofModel.

    faces_src : list of Nx3 arrays in source units (feet for the city data).
    unit_m    : metres per source unit.
    origin    : (x, y, z) in source units of the local origin; default = solid min corner,
                with z = ground_z when given.
    ground_z  : ground elevation in source units (the city footprint's GROUNDELEVATION).
    """
    m = RoofModel()
    allp = np.concatenate(faces_src)
    lo = allp.min(axis=0)
    if origin is None:
        origin = (lo[0], lo[1], lo[2] if ground_z is None else ground_z)
    origin = np.array(origin, dtype=np.float64)
    m.origin_ft = tuple(float(v) for v in origin)
    base_z = (lo[2] - origin[2]) * unit_m
    local = [(np.asarray(f, np.float64) - origin) * unit_m for f in faces_src]

    # 1. snap vertices, drop degenerate faces, classify
    verts, ids = _snap(np.concatenate(local), SNAP_M)
    faces, k = [], 0
    seen, duplicates = set(), 0
    for f in local:
        ring = _dedupe_loop([int(v) for v in ids[k:k + len(f)]])
        k += len(f)
        if len(ring) < 3:
            continue
        key = tuple(sorted(ring))
        if key in seen:        # the same face delivered twice would count its area twice
            duplicates += 1
            continue
        seen.add(key)
        A = newell(verts[ring])
        area = float(np.linalg.norm(A))
        if area < 1e-4:
            continue
        n = A / area
        if abs(n[2]) < WALL_NZ:
            kind = "wall"
        elif abs(n[2]) > 0.999 and np.all(np.abs(verts[ring][:, 2] - base_z) < 0.05):
            kind = "floor"  # the bottom of the solid, if the source has one
        else:
            kind = "roof"
            if n[2] < 0:   # winding in the city data is not consistent; make every roof face look up
                ring.reverse()
                n = -n
        faces.append({"kind": kind, "ring": ring, "n": n, "area": area, "plane": None})
    hidden, partly = _mark_hidden(faces, verts)
    for f in faces:
        f["loop"] = _split_loop(f["ring"], verts, SNAP_M)
    m.verts_raw = verts.copy()

    # 2. atomic edges -> faces
    edge_faces = {}
    for fi, f in enumerate(faces):
        lp = f["loop"]
        for q in range(len(lp)):
            a, b = lp[q], lp[(q + 1) % len(lp)]
            edge_faces.setdefault((min(a, b), max(a, b)), []).append((fi, a, b))

    # 3. merge touching, coplanar roof faces into planes
    roof_ids = [i for i, f in enumerate(faces) if f["kind"] == "roof"]
    dsu = _DSU(len(faces))
    cos_merge = math.cos(math.radians(MERGE_DEG))
    for lst in edge_faces.values():
        rf = [x[0] for x in lst if faces[x[0]]["kind"] == "roof"]
        for i in range(len(rf)):
            for j in range(i + 1, len(rf)):
                fa, fb = faces[rf[i]], faces[rf[j]]
                if fa["n"] @ fb["n"] < cos_merge:
                    continue
                ca, cb = verts[fa["ring"]].mean(0), verts[fb["ring"]].mean(0)
                if abs((cb - ca) @ fa["n"]) < MERGE_OFFSET_M and abs((cb - ca) @ fb["n"]) < MERGE_OFFSET_M:
                    dsu.union(rf[i], rf[j])
    groups = {}
    for i in roof_ids:
        groups.setdefault(dsu.find(i), []).append(i)
    plane_faces = sorted(groups.values(), key=lambda g: -sum(faces[i]["area"] for i in g))
    for pi, g in enumerate(plane_faces):
        for i in g:
            faces[i]["plane"] = pi

    # 4. fit planes (area-weighted) to the faces as delivered
    fits = []
    raw_plan = raw_sloped = 0.0
    for g in plane_faces:
        A = sum(newell(verts[faces[i]["ring"]]) for i in g)
        raw_plan += abs(float(A[2]))
        raw_sloped += float(sum(faces[i]["area"] for i in g))
        n = A / np.linalg.norm(A)
        w = np.array([faces[i]["area"] for i in g])
        c = sum(wi * verts[faces[i]["ring"]].mean(0) for wi, i in zip(w, g)) / w.sum()
        used = sorted({v for i in g for v in faces[i]["ring"]})
        planarity = float(np.abs((verts[used] - c) @ n).max())
        fits.append({"n": n, "d": float(n @ c), "planarityM": planarity})
    m.faces = faces
    m._ctx = {"plane_faces": plane_faces, "fits": fits, "edge_faces": edge_faces, "roof_ids": roof_ids,
              "hidden": hidden, "partly": partly, "duplicates": duplicates, "raw_plan": raw_plan,
              "raw_sloped": raw_sloped, "base_z": float(base_z), "points": int(sum(len(f) for f in faces_src))}
    _solve_and_measure(m)
    return m


def retilt(m, pitch_deg_by_plane):
    """Re-tilt planes to a given pitch (degrees) and rebuild the geometry, the plane records and the edges.

    Used when lidar supplies the pitch. Each named plane takes the new pitch and keeps facing the way the
    city face does (it may turn by a fraction of a degree so the corners still meet); the corners are then
    solved again, held on the wall lines. Plane ids do not change. Returns the ids that were re-tilted.
    """
    fixed = {}
    for pid, pitch in pitch_deg_by_plane.items():
        n0 = m._ctx["fits"][pid]["n"]
        if math.hypot(n0[0], n0[1]) < 0.0087 or not 0.5 <= pitch < 85.0:   # a flat face has no direction to tilt along
            continue
        fixed[pid] = float(pitch)
    m._ctx["fixed"] = fixed
    _solve_and_measure(m)
    return sorted(fixed)


def _solve_and_measure(m):
    """Steps 4b to 6 of `build_model`: make the planes flat, then measure planes and classify edges."""
    ctx = m._ctx
    faces, verts = m.faces, m.verts_raw
    plane_faces, fits, edge_faces, roof_ids = ctx["plane_faces"], ctx["fits"], ctx["edge_faces"], ctx["roof_ids"]
    fixed = ctx.get("fixed") or {}
    m.planes, m.edges = [], []
    vplanes, pverts = {}, []
    for pi, g in enumerate(plane_faces):
        used = sorted({v for i in g for v in faces[i]["loop"]})
        pverts.append(used)
        for v in used:
            vplanes.setdefault(v, set()).add(pi)
    # Stage 1: make the delivered faces flat. Alternate between "move each vertex onto its planes" and
    # "refit each plane to its vertices". One pass alone fails on low slopes: three planes that are each
    # a few centimetres off meet far from the delivered corner. Letting the planes move too keeps every
    # shift small.
    reg, cur = _regularize(verts, vplanes, pverts, [(f["n"], f["d"]) for f in fits], refit=True)
    if fixed:
        # Stage 2 (re-tilt): the named planes take their new pitch, and the planes and corners settle
        # again. A corner that touches a wall
        # may slide along that wall or move up and down, but it may not leave the wall's plane: the wall
        # lines come from the city footprint, so the roof keeps its plan area while it is re-tilted.
        vwalls = {}
        for f in faces:
            if f["kind"] != "wall":
                continue
            h = np.array([f["n"][0], f["n"][1], 0.0])
            h /= np.linalg.norm(h)
            for v in f["loop"]:
                vwalls.setdefault(v, []).append(h)
        start, hold = [], {}
        for pi in range(len(fits)):
            n = cur[pi][0]
            # every plane keeps a given pitch: the new one if it is re-tilted, its own from stage 1 if not
            hold[pi] = fixed.get(pi, math.degrees(math.atan2(math.hypot(n[0], n[1]), n[2])))
            n = _with_pitch(n, hold[pi])
            start.append((n, float(n @ reg[pverts[pi]].mean(axis=0))))
        reg, cur = _regularize(reg, vplanes, pverts, start, refit=True, vwalls=vwalls, hold=hold)
    shifts = np.linalg.norm(reg - verts, axis=1)
    max_shift = float(shifts.max()) if len(shifts) else 0.0
    max_shift_xy = float(np.linalg.norm((reg - verts)[:, :2], axis=1).max()) if len(shifts) else 0.0
    max_gap = 0.0
    for v, ps in vplanes.items():
        for p in ps:
            max_gap = max(max_gap, abs(float(cur[p][0] @ reg[v] - cur[p][1])))
    m.verts = reg
    verts = reg

    # 5. plane records (measured on the regularized geometry, so the files, the GLB and the report agree)
    for pi, g in enumerate(plane_faces):
        A = sum(newell(verts[faces[i]["ring"]]) for i in g)
        area = float(np.linalg.norm(A))
        n = A / area
        pitch = math.degrees(math.atan2(math.hypot(n[0], n[1]), n[2]))
        az = (math.degrees(math.atan2(n[0], n[1])) + 360.0) % 360.0 if pitch > 0.5 else None
        loops = _boundary_loops(g, faces, verts)
        zs = verts[sorted({v for i in g for v in faces[i]["ring"]})][:, 2]
        m.planes.append({
            "id": pi, "normal": n, "pitchDeg": pitch, "pitchIn12": 12 * math.tan(math.radians(pitch)),
            "azimuthGridDeg": az, "planAreaM2": float(abs(A[2])), "areaM2": area,
            "planarityM": fits[pi]["planarityM"], "faceCount": len(g),
            "sourcePitchDeg": math.degrees(math.atan2(math.hypot(fits[pi]["n"][0], fits[pi]["n"][1]), fits[pi]["n"][2])),
            "polygon": loops[0] if loops else [], "holes": loops[1:],
            "zMinM": float(zs.min()), "zMaxM": float(zs.max()),
            "centroid": sum(faces[i]["area"] * verts[faces[i]["ring"]].mean(0) for i in g) / sum(faces[i]["area"] for i in g),
        })

    # 6. classify atomic roof edges
    raw = m.verts_raw
    walls = []
    for f in faces:
        if f["kind"] != "wall":
            continue
        n = f["n"]
        t = np.array([-n[1], n[0], 0.0])
        t /= np.linalg.norm(t)
        p = raw[f["ring"]]
        walls.append({"n": n, "d": float(n @ p.mean(0)), "t": t, "poly2": np.column_stack([p @ t, p[:, 2]])})

    def wall_above(mid):
        # Is there a wall rising from this roof edge? A wall shorter than the lower probe is a sliver in the
        # source model, not a wall that needs flashing. The question is asked of the faces as delivered, not
        # of the cleaned or re-tilted corners: lidar supplies a pitch and says nothing about walls. Review
        # round 5: on one house a wall 11 cm tall at the probe became 9.5 cm after the re-tilt, and 22 ft of
        # step flashing turned into rake.
        for w in walls:
            if abs(w["n"] @ mid - w["d"]) >= WALL_NEAR_M:
                continue
            s = mid @ w["t"]
            if any(_pnpoly(w["poly2"], s, mid[2] + up) for up in WALL_PROBE_UP_M):
                return True
        return False

    tan_h = math.tan(math.radians(HORIZONTAL_DEG))
    sin_level = math.sin(math.radians(LEVEL_PLAN_DEG))
    sin_updip = math.sin(math.radians(UPDIP_PLAN_DEG))
    atoms = []
    for (va, vb), lst in edge_faces.items():
        rf = [x for x in lst if faces[x[0]]["kind"] == "roof"]
        if not rf:
            continue
        by_plane = {}
        for x in rf:
            by_plane.setdefault(faces[x[0]]["plane"], []).append(x)
        if len(by_plane) == 1 and len(rf) >= 2:
            continue  # seam inside one plane
        a, b = verts[va], verts[vb]
        vec = b - a
        L = float(np.linalg.norm(vec))
        if L < 1e-6:
            continue
        run = math.hypot(vec[0], vec[1])
        pl = sorted(by_plane)
        # Level means: nearly no rise, or running along the contour of (one of) its plane(s). The second
        # test keeps an eave an eave when the source or a re-tilt leaves it a few degrees out of level;
        # rakes and hips run far from the contour, so they are not affected.
        horizontal = abs(vec[2]) <= max(tan_h * run, 0.02)
        if not horizontal and run > 1e-6:
            for q in pl[:2]:
                nq = m.planes[q]["normal"]
                h = math.hypot(nq[0], nq[1])
                if h > 0.02 and abs(vec[0] * nq[0] + vec[1] * nq[1]) / (run * h) <= sin_level:
                    horizontal = True
        elif len(pl) == 1 and run > 1e-6:
            # On a plane flatter than about 0.9 in 12 every edge rises less than HORIZONTAL_DEG, so the test
            # above would call a rake an eave or a plane top (review round 4: 36 ft on one house). An open
            # edge that runs more up the slope than along it is not level, whatever its rise.
            nq = m.planes[pl[0]]["normal"]
            h = math.hypot(nq[0], nq[1])
            if h > 0.02 and abs(vec[0] * nq[0] + vec[1] * nq[1]) / (run * h) > sin_updip:
                horizontal = False
        if len(pl) >= 2:
            (fa, a1, b1), (fb, a2, b2) = by_plane[pl[0]][0], by_plane[pl[1]][0]
            nA, nB = m.planes[pl[0]]["normal"], m.planes[pl[1]]["normal"]
            in_b = np.cross(nB, verts[b2] - verts[a2])
            in_b /= np.linalg.norm(in_b)
            fold = float(in_b @ nA)
            if abs(fold) < SEAM_SIN:
                continue
            etype = "valley" if fold > 0 else ("ridge" if horizontal else "hip")
            atoms.append({"type": etype, "va": va, "vb": vb, "planes": tuple(pl[:2]), "L": L})
            continue
        fi, a1, b1 = rf[0]
        P = m.planes[pl[0]]
        low_side = False
        if wall_above((raw[va] + raw[vb]) / 2):
            etype = "headwall" if horizontal else "step_flashing"
            # a level roof-to-wall joint at the bottom of its plane cannot drain: the source model
            # most likely simplified a gable tie-in there (pipeline.assess flags it)
            mid_z = (a[2] + b[2]) / 2
            low_side = horizontal and (mid_z - P["zMinM"]) < 0.25 * max(P["zMaxM"] - P["zMinM"], 1e-6)
        elif horizontal:
            n = P["normal"]
            inward = np.cross(n, verts[b1] - verts[a1])
            flat = math.hypot(n[0], n[1]) < 0.02
            etype = "eave" if flat or (inward[0] * -n[0] + inward[1] * -n[1]) > 0 else "top"
        else:
            etype = "rake"
        atoms.append({"type": etype, "va": va, "vb": vb, "planes": (pl[0],), "L": L, "low": low_side})

    m.edges, split_ridge_m = _pair_split_ridges(_merge_lines(atoms, verts))
    for i, e in enumerate(m.edges):
        e["id"] = i
    m.stats = {
        "faces": len(faces), "roofFaces": len(roof_ids), "wallFaces": sum(f["kind"] == "wall" for f in faces),
        "points": ctx["points"], "vertices": int(len(verts)),
        "hiddenFaces": ctx["hidden"], "partlyCoveredFaces": ctx["partly"], "duplicateFaces": ctx["duplicates"],
        "sourcePlanAreaM2": ctx["raw_plan"], "sourceSlopedAreaM2": ctx["raw_sloped"],
        "regularizeMaxShiftM": max_shift, "regularizeMaxShiftXyM": max_shift_xy, "regularizeMaxGapM": max_gap,
        "maxPitchChangeDeg": max((abs(p["pitchDeg"] - p["sourcePitchDeg"]) for i, p in enumerate(m.planes)
                                  if i not in fixed), default=0.0),
        "maxPlanarityM": max((p["planarityM"] for p in m.planes), default=0.0),
        "splitRidgeM": split_ridge_m, "retiltedPlanes": sorted(fixed),
        "baseZM": ctx["base_z"], "topZM": float(verts[:, 2].max()),
        "bboxM": [float(v) for v in (verts[:, 0].max() - verts[:, 0].min(), verts[:, 1].max() - verts[:, 1].min())],
    }


def _with_pitch(n, pitch_deg):
    """The unit normal with the compass direction of `n` and the given pitch."""
    h = math.hypot(n[0], n[1])
    t = math.radians(pitch_deg)
    if h < 1e-6:
        return np.array([0.0, 0.0, 1.0])
    return np.array([n[0] / h * math.sin(t), n[1] / h * math.sin(t), math.cos(t)])


def _regularize(verts, vplanes, pverts, planes0, refit, vwalls=None, hold=None):
    """Move vertices onto their planes. Returns (vertices, [(normal, offset)]).

    refit  : planes are refitted to the moved vertices each round.
    hold   : {plane: pitch in degrees} for planes whose pitch is given (re-tilt); they may still turn
             a little and settle in height.
    vwalls : per vertex, the horizontal normals of the walls it must stay on (re-tilt).
    """
    hold = hold or {}
    reg = verts.copy()
    lam = 1e-3
    cur = list(planes0)
    for _ in range(REGULARIZE_ITERS):
        for v, ps in vplanes.items():
            N = np.array([cur[p][0] for p in ps])
            d = np.array([cur[p][1] for p in ps])
            # least squares on the plane equations, lightly tied to the starting position
            M = N.T @ N + lam * np.eye(3)
            rhs = N.T @ d + lam * verts[v]
            if vwalls and v in vwalls:
                W = np.array(vwalls[v])
                M = M + WALL_WEIGHT * (W.T @ W)
                rhs = rhs + WALL_WEIGHT * (W.T @ (W @ verts[v]))
            reg[v] = np.linalg.solve(M, rhs)
        nxt = []
        for pi, used in enumerate(pverts):
            pts = reg[used]
            c = pts.mean(axis=0)
            if not refit:
                nxt.append((cur[pi][0], float(cur[pi][0] @ c)))
                continue
            _, sv, vt = np.linalg.svd(pts - c, full_matrices=False)
            n = vt[-1] if vt[-1][2] > 0 else -vt[-1]
            if len(used) < 3 or sv[1] < 1e-6 or n @ planes0[pi][0] < 0.99:
                n = cur[pi][0]        # degenerate or drifting: keep the previous direction
                if pi not in hold:
                    nxt.append(cur[pi])
                    continue
            if pi in hold:            # the pitch is given; the compass direction and the height may settle
                n = _with_pitch(n, hold[pi])
            nxt.append((n, float(n @ c)))
        cur = nxt
    return reg, cur


def _mark_hidden(faces, verts):
    """Keep only the top surface: a non-wall face with another non-wall face above it is not roof.

    Some city solids carry extra faces under the real roof (a cap polygon at eave level, the floor
    of a penthouse). Without this step their area is counted twice. Returns (faces hidden, faces
    partly covered); partly covered faces stay and are flagged by the caller.
    """
    roofs = [f for f in faces if f["kind"] == "roof"]
    info = []
    for f in roofs:
        p = verts[f["ring"]]
        c = p.mean(axis=0)
        info.append((p[:, :2], c, f["n"], p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()))
    hidden = partly = 0
    for i, f in enumerate(roofs):
        p = verts[f["ring"]]
        tris = triangulate(p[:, :2])
        tot = cov = 0.0
        for t in tris:
            q = p[list(t)]
            w = abs(newell(q)[2])
            s = q.mean(axis=0)
            tot += w
            for j, (poly, c, n, x0, x1, y0, y1) in enumerate(info):
                if j == i or not (x0 <= s[0] <= x1 and y0 <= s[1] <= y1):
                    continue
                zj = c[2] - (n[0] * (s[0] - c[0]) + n[1] * (s[1] - c[1])) / n[2]
                if zj > s[2] + 0.05 and _pnpoly(poly, s[0], s[1]):
                    cov += w
                    break
        frac = cov / tot if tot > 0 else 0.0
        f["covered"] = frac
        if frac > 0.5:
            f["kind"] = "hidden"
            hidden += 1
        elif frac > 0.05:
            partly += 1
    return hidden, partly


def _boundary_loops(group, faces, verts):
    """Outer loop first, then holes, of a set of faces of one plane. Each loop is a list of xyz."""
    directed = {}
    for i in group:
        lp = faces[i]["loop"]
        for q in range(len(lp)):
            a, b = lp[q], lp[(q + 1) % len(lp)]
            if (b, a) in directed:
                del directed[(b, a)]
            else:
                directed[(a, b)] = True
    nxt = {}
    for a, b in directed:
        nxt.setdefault(a, []).append(b)
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop, cur = [], start
        for _ in range(100000):
            loop.append(cur)
            outs = nxt.get(cur)
            if not outs:
                break
            b = outs.pop()
            if not outs:
                del nxt[cur]
            cur = b
            if cur == start:
                break
        if len(loop) >= 3:
            loops.append(_drop_collinear(loop, verts))
    loops = [lp for lp in loops if len(lp) >= 3]
    loops.sort(key=lambda lp: -float(np.linalg.norm(newell(verts[lp]))))
    return [[[float(c) for c in verts[v]] for v in lp] for lp in loops]


def _drop_collinear(loop, verts):
    out = []
    n = len(loop)
    for q in range(n):
        a, b, c = verts[loop[q - 1]], verts[loop[q]], verts[loop[(q + 1) % n]]
        u, v = b - a, c - b
        if np.linalg.norm(np.cross(u, v)) > 1e-3 * np.linalg.norm(u) * np.linalg.norm(v) or u @ v < 0:
            out.append(loop[q])
    return out


def _merge_lines(atoms, verts):
    """Join collinear, touching pieces of the same type and planes into single lines."""
    groups = {}
    for i, a in enumerate(atoms):
        groups.setdefault((a["type"], a["planes"], bool(a.get("low"))), []).append(i)
    lines = []
    cos_tol = math.cos(math.radians(3.0))
    for (etype, planes, low), members in groups.items():
        dsu = _DSU(len(members))
        dirs = []
        for i in members:
            d = verts[atoms[i]["vb"]] - verts[atoms[i]["va"]]
            dirs.append(d / np.linalg.norm(d))
        at_vertex = {}
        for k, i in enumerate(members):
            for v in (atoms[i]["va"], atoms[i]["vb"]):
                at_vertex.setdefault(v, []).append(k)
        for ks in at_vertex.values():
            for x in range(len(ks)):
                for y in range(x + 1, len(ks)):
                    if abs(dirs[ks[x]] @ dirs[ks[y]]) >= cos_tol:
                        dsu.union(ks[x], ks[y])
        sets = {}
        for k in range(len(members)):
            sets.setdefault(dsu.find(k), []).append(k)
        for ks in sets.values():
            d = dirs[ks[0]]
            pts = np.array([verts[v] for k in ks for v in (atoms[members[k]]["va"], atoms[members[k]]["vb"])])
            t = pts @ d
            a, b = pts[int(np.argmin(t))], pts[int(np.argmax(t))]
            lines.append({"type": etype, "a": [float(c) for c in a], "b": [float(c) for c in b],
                          "lengthM": float(sum(atoms[members[k]]["L"] for k in ks)),
                          "planes": [int(p) for p in planes], "pieces": len(ks)})
            if low:
                lines[-1]["lowSide"] = True
    order = {t: i for i, t in enumerate(ROOF_TYPES)}
    lines.sort(key=lambda e: (order[e["type"]], -e["lengthM"]))
    return lines


def _pair_split_ridges(lines):
    """Turn pairs of `top` lines that lie on each other into one ridge.

    Some city solids put a wall a few centimetres tall between the two sides of a ridge. Each side then
    looks like the high edge of a single-slope plane, the ridge is missing and its length is counted twice
    as `top`. Two tops of different planes that run parallel within SPLIT_RIDGE_M are one ridge over the
    length they share. Returns (lines, metres of ridge recovered).
    """
    tops = [e for e in lines if e["type"] == "top"]
    rest = [e for e in lines if e["type"] != "top"]
    spans = []
    for e in tops:
        a, b = np.array(e["a"]), np.array(e["b"])
        spans.append({"e": e, "a": a, "d": (b - a) / (np.linalg.norm(b - a) or 1.0), "free": [(0.0, float(np.linalg.norm(b - a)))]})
    ridges, recovered = [], 0.0
    cos_tol = math.cos(math.radians(5.0))
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            si, sj = spans[i], spans[j]
            if si["e"]["planes"] == sj["e"]["planes"] or abs(si["d"] @ sj["d"]) < cos_tol:
                continue
            pj = [np.array(sj["e"]["a"]), np.array(sj["e"]["b"])]
            t = [float((p - si["a"]) @ si["d"]) for p in pj]
            off = max(float(np.linalg.norm(p - (si["a"] + tk * si["d"]))) for p, tk in zip(pj, t))
            if off > SPLIT_RIDGE_M:
                continue
            lo_j, hi_j = min(t), max(t)
            for (lo_i, hi_i) in list(si["free"]):
                lo, hi = max(lo_i, lo_j), min(hi_i, hi_j)
                if hi - lo < 0.3:
                    continue
                si["free"].remove((lo_i, hi_i))
                si["free"] += [seg for seg in ((lo_i, lo), (hi, hi_i)) if seg[1] - seg[0] > 0.05]
                # the same stretch measured along j
                u = sorted(float((si["a"] + x * si["d"] - sj["a"]) @ sj["d"]) for x in (lo, hi))
                new_free = []
                for (a0, a1) in sj["free"]:
                    new_free += [seg for seg in ((a0, min(a1, u[0])), (max(a0, u[1]), a1)) if seg[1] - seg[0] > 0.05]
                sj["free"] = new_free
                pa, pb = si["a"] + lo * si["d"], si["a"] + hi * si["d"]
                ridges.append({"type": "ridge", "a": [float(c) for c in pa], "b": [float(c) for c in pb],
                               "lengthM": float(hi - lo), "planes": sorted(si["e"]["planes"] + sj["e"]["planes"]),
                               "pieces": 1, "splitRidge": True})
                recovered += float(hi - lo)
    left = []
    for s in spans:
        for (lo, hi) in s["free"]:
            pa, pb = s["a"] + lo * s["d"], s["a"] + hi * s["d"]
            left.append(dict(s["e"], a=[float(c) for c in pa], b=[float(c) for c in pb], lengthM=float(hi - lo)))
    out = rest + ridges + left
    order = {t: i for i, t in enumerate(ROOF_TYPES)}
    out.sort(key=lambda e: (order[e["type"]], -e["lengthM"]))
    return out, recovered
