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
SEAM_SIN = 0.02          # roof-roof folds flatter than about 1 degree are not an edge
REGULARIZE_ITERS = 40
REGULARIZE_WARN_SHIFT_M = 0.30
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
            p = self.verts[f["ring"]]
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
    for f in local:
        ring = _dedupe_loop([int(v) for v in ids[k:k + len(f)]])
        k += len(f)
        if len(ring) < 3:
            continue
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

    # 4. fit planes (area-weighted) and regularize vertices so planes are flat and meet exactly
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
    vplanes, pverts = {}, []
    for pi, g in enumerate(plane_faces):
        used = sorted({v for i in g for v in faces[i]["loop"]})
        pverts.append(used)
        for v in used:
            vplanes.setdefault(v, set()).add(pi)
    # Alternate between "move each vertex onto its planes" and "refit each plane to its vertices".
    # One pass alone fails on low slopes: three planes that are each a few centimetres off meet
    # far from the delivered corner. Letting the planes move too keeps every shift small.
    reg = verts.copy()
    lam = 1e-3
    cur = [(f["n"], f["d"]) for f in fits]
    for _ in range(REGULARIZE_ITERS):
        for v, ps in vplanes.items():
            N = np.array([cur[p][0] for p in ps])
            d = np.array([cur[p][1] for p in ps])
            # least squares on the plane equations, lightly tied to the delivered position
            reg[v] = np.linalg.solve(N.T @ N + lam * np.eye(3), N.T @ d + lam * verts[v])
        nxt = []
        for pi, used in enumerate(pverts):
            pts = reg[used]
            c = pts.mean(axis=0)
            _, sv, vt = np.linalg.svd(pts - c, full_matrices=False)
            n = vt[-1] if vt[-1][2] > 0 else -vt[-1]
            if len(used) < 3 or sv[1] < 1e-6 or n @ fits[pi]["n"] < 0.99:
                nxt.append(cur[pi])   # degenerate or drifting: keep the previous plane
            else:
                nxt.append((n, float(n @ c)))
        cur = nxt
    shifts = np.linalg.norm(reg - verts, axis=1)
    max_shift = float(shifts.max()) if len(shifts) else 0.0
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
    m.faces = faces

    # 6. classify atomic roof edges
    walls = []
    for f in faces:
        if f["kind"] != "wall":
            continue
        n = f["n"]
        t = np.array([-n[1], n[0], 0.0])
        t /= np.linalg.norm(t)
        p = verts[f["ring"]]
        walls.append({"n": n, "d": float(n @ p.mean(0)), "t": t, "poly2": np.column_stack([p @ t, p[:, 2]])})

    def wall_above(mid):
        probe = mid + np.array([0, 0, 0.05])
        for w in walls:
            if abs(w["n"] @ probe - w["d"]) < 0.03 and _pnpoly(w["poly2"], probe @ w["t"], probe[2]):
                return True
        return False

    tan_h = math.tan(math.radians(HORIZONTAL_DEG))
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
        horizontal = abs(vec[2]) <= max(tan_h * run, 0.02)
        pl = sorted(by_plane)
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
        if wall_above((a + b) / 2):
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

    m.edges = _merge_lines(atoms, verts)
    for i, e in enumerate(m.edges):
        e["id"] = i
    m.stats = {
        "faces": len(faces), "roofFaces": len(roof_ids), "wallFaces": sum(f["kind"] == "wall" for f in faces),
        "points": int(sum(len(f) for f in faces_src)), "vertices": int(len(verts)),
        "hiddenFaces": hidden, "partlyCoveredFaces": partly,
        "sourcePlanAreaM2": raw_plan, "sourceSlopedAreaM2": raw_sloped,
        "regularizeMaxShiftM": max_shift, "regularizeMaxGapM": max_gap,
        "maxPitchChangeDeg": max((abs(p["pitchDeg"] - p["sourcePitchDeg"]) for p in m.planes), default=0.0),
        "maxPlanarityM": max((p["planarityM"] for p in m.planes), default=0.0),
        "baseZM": float(base_z), "topZM": float(verts[:, 2].max()),
        "bboxM": [float(v) for v in (verts[:, 0].max() - verts[:, 0].min(), verts[:, 1].max() - verts[:, 1].min())],
    }
    return m


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
