"""Answer key: every measurement computed from the generated 3-D roof geometry.

This module is deliberately independent of the roof builder. It only sees:
  * roof facets as 3-D polygons (outer ring + holes, metres),
  * vertical wall faces as 3-D polygons (to find roof-to-wall flashing),
  * the wall footprint rectangles,
  * the placed details and scale markers.
Areas come from Newell's formula, pitch / azimuth from each facet's normal, and every boundary segment is typed
from its neighbourhood alone (which facets share it, which way each facet runs away from it, whether a wall stands
on it). ``compute`` then compares the totals with the builder's own numbers and refuses to write a key that
disagrees (two independent derivations).

Line kinds (EagleView-style names in parentheses):
  ridge     shared, horizontal, both facets fall away from it            (Ridges)
  hip       shared, sloped, both facets fall away from it                (Hips)
  valley    shared, both facets rise away from it                        (Valleys)
  transition shared, one facet rises and one falls (pitch break)        (Transitions)
  eave      free, horizontal, facet rises away from it                   (Eaves)
  rake      free, sloped                                                 (Rakes)
  headwall  roof meets a wall above it, horizontal                       (Flashing)
  step_flashing roof meets a wall above it, sloped                       (Step flashing)
  top_edge  free, horizontal, facet falls away from it (high edge of a shed roof with nothing above it)
"""
from __future__ import annotations

import math

import numpy as np

FT = 0.3048
FT2 = FT * FT
SQ_FT2 = 100.0
TOL = 1e-4                 # m: geometric tolerance for shared vertices / segments
HORIZ = 1e-4               # |dz| / length below this -> horizontal line
ICE_INSIDE_WALL_M = 0.6096   # IRC R905.1.2: ice barrier from the eave to 24 in inside the exterior wall line
ICE_ROLL_FT = 3.0            # 36 in rolls
ICE_LAP_FT = 0.25            # 3 in head lap between courses
VALLEY_ICE_FT = 3.0          # one 36 in roll centred in each valley


# ---------------------------------------------------------------------------------------------------------------
# polygon helpers

def newell(ring):
    """(area, unit normal) of a planar 3-D polygon; the normal follows the ring's winding."""
    p = np.asarray(ring, float)
    q = np.roll(p, -1, axis=0)
    n = np.array([np.sum((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])),
                  np.sum((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])),
                  np.sum((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1]))])
    a = np.linalg.norm(n)
    return a / 2.0, (n / a if a > 0 else n)


def shoelace(ring):
    p = np.asarray(ring, float)[:, :2]
    q = np.roll(p, -1, axis=0)
    return 0.5 * float(np.sum(p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]))


def point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xi > x:
                inside = not inside
    return inside


def point_in_facet(x, y, facet):
    for poly in facet["rings"]:
        if point_in_ring(x, y, poly["outer"]) and not any(point_in_ring(x, y, h) for h in poly["holes"]):
            return True
    return False


def seg_point_dist(p, a, b):
    p, a, b = (np.asarray(v, float) for v in (p, a, b))
    d = b - a
    t = np.clip(np.dot(p - a, d) / max(np.dot(d, d), 1e-18), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * d)))


# ---------------------------------------------------------------------------------------------------------------
# facets

def facet_metrics(facet):
    area, plan = 0.0, 0.0
    normal = None
    for poly in facet["rings"]:
        a, n = newell(poly["outer"])
        if normal is None and a > 1e-9:
            normal = n
        area += a - sum(newell(h)[0] for h in poly["holes"])
        plan += abs(shoelace(poly["outer"])) - sum(abs(shoelace(h)) for h in poly["holes"])
    if normal is None:
        normal = np.array([0.0, 0.0, 1.0])
    if normal[2] < 0:
        normal = -normal
    horiz = math.hypot(normal[0], normal[1])
    slope = horiz / normal[2] if normal[2] > 1e-12 else math.inf
    azimuth = None
    if horiz > 1e-9:
        azimuth = math.degrees(math.atan2(normal[0], normal[1])) % 360.0
        if azimuth > 360.0 - 1e-9:          # -1e-15 deg (cos 90 noise) wraps to 360.0 in float; north is 0
            azimuth = 0.0
    return {
        "area_m2": area, "area_ft2": area / FT2, "plan_area_m2": plan,
        "pitch_x12": slope * 12.0, "pitch_deg": math.degrees(math.atan(slope)),
        "azimuth_deg": azimuth, "normal": normal.tolist(), "slope": slope,
    }


# ---------------------------------------------------------------------------------------------------------------
# lines

def _canonical_vertices(facets):
    """Cluster all ring vertices within TOL -> canonical index per (facet, poly, ring, vertex)."""
    pts, owners = [], []
    for fi, f in enumerate(facets):
        for pi, poly in enumerate(f["rings"]):
            for ri, ring in enumerate([poly["outer"]] + poly["holes"]):
                for vi, v in enumerate(ring):
                    pts.append(v)
                    owners.append((fi, pi, ri, vi))
    pts = np.asarray(pts, float)
    canon = np.full(len(pts), -1)
    reps = []
    for i, p in enumerate(pts):
        for k, r in enumerate(reps):
            if np.linalg.norm(p - r) < TOL:
                canon[i] = k
                break
        else:
            canon[i] = len(reps)
            reps.append(p)
    return np.asarray(reps), {o: int(c) for o, c in zip(owners, canon)}


def _atomic_segments(facets):
    """Split every ring edge at every canonical vertex lying on it; return {(i, j): [(facet, is_hole)]}."""
    reps, cmap = _canonical_vertices(facets)
    segs = {}
    for fi, f in enumerate(facets):
        for pi, poly in enumerate(f["rings"]):
            for ri, ring in enumerate([poly["outer"]] + poly["holes"]):
                n = len(ring)
                for vi in range(n):
                    ia, ib = cmap[(fi, pi, ri, vi)], cmap[(fi, pi, ri, (vi + 1) % n)]
                    if ia == ib:
                        continue
                    a, b = reps[ia], reps[ib]
                    d = b - a
                    L2 = float(np.dot(d, d))
                    on = []
                    for k, p in enumerate(reps):
                        if k in (ia, ib):
                            continue
                        t = float(np.dot(p - a, d)) / L2
                        if 1e-9 < t < 1 - 1e-9 and np.linalg.norm(p - (a + t * d)) < TOL:
                            on.append((t, k))
                    chain = [ia] + [k for _, k in sorted(on)] + [ib]
                    for s, e in zip(chain[:-1], chain[1:]):
                        key = (min(s, e), max(s, e))
                        segs.setdefault(key, []).append((fi, ri > 0))
    return reps, segs


def _away_dz(facet, normal, a, b):
    """Vertical component of the in-plane unit direction pointing from segment ab into the facet."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    e = b - a
    e /= np.linalg.norm(e)
    perp = np.cross(normal, e)
    perp /= np.linalg.norm(perp)
    m = (a + b) / 2.0
    eps = 0.02
    for sign in (1.0, -1.0):
        q = m + sign * eps * perp
        if point_in_facet(q[0], q[1], facet):
            return float(sign * perp[2])
    return 0.0


def _wall_above(walls, a, b):
    """True if segment ab lies in a wall face and that wall rises above it (roof-to-wall junction)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = (a + b) / 2.0
    for w in walls:
        P = np.asarray(w["polygon"], float)
        _, n = newell(P)
        if abs(n[2]) > 1e-3:
            continue
        if abs(np.dot(a - P[0], n)) > 2e-3 or abs(np.dot(b - P[0], n)) > 2e-3:
            continue
        h = np.array([-n[1], n[0], 0.0])                  # horizontal axis of the wall plane
        u = (P - P[0]) @ h
        um = float((m - P[0]) @ h)
        if not (u.min() - 1e-3 <= um <= u.max() + 1e-3):
            continue
        # top of the wall polygon at um (max z of the polygon's boundary crossing that vertical line)
        ztop = -math.inf
        k = len(P)
        for i in range(k):
            u0, u1 = u[i], u[(i + 1) % k]
            z0, z1 = P[i, 2], P[(i + 1) % k, 2]
            if (u0 - um) * (u1 - um) <= 0 and abs(u1 - u0) > 1e-9:
                ztop = max(ztop, z0 + (um - u0) * (z1 - z0) / (u1 - u0))
        if ztop > m[2] + 0.05:
            return True
    return False


def classify_lines(facets, metrics, walls):
    reps, segs = _atomic_segments(facets)
    lines = []
    for (i, j), owners in segs.items():
        a, b = reps[i], reps[j]
        L = float(np.linalg.norm(b - a))
        if L < 1e-6:
            continue
        horizontal = abs(b[2] - a[2]) / L < HORIZ
        fids = sorted({fi for fi, _ in owners})
        hole = any(h for _, h in owners)
        if len(fids) >= 2:
            if len(fids) > 2:
                kind = "ambiguous"
            else:
                n0, n1 = (np.asarray(metrics[k]["normal"]) for k in fids)
                if np.linalg.norm(n0 - n1) < 1e-6:
                    continue                                   # coplanar split of one roof plane: not a line
                d0 = _away_dz(facets[fids[0]], n0, a, b)
                d1 = _away_dz(facets[fids[1]], n1, a, b)
                if d0 < -1e-9 and d1 < -1e-9:
                    kind = "ridge" if horizontal else "hip"
                elif d0 > 1e-9 and d1 > 1e-9:
                    kind = "valley"
                else:
                    kind = "transition"
        else:
            fi = fids[0]
            n0 = np.asarray(metrics[fi]["normal"])
            if hole:
                kind = "penetration"
            elif _wall_above(walls, a, b):
                kind = "headwall" if horizontal else "step_flashing"
            elif horizontal:
                kind = "eave" if _away_dz(facets[fi], n0, a, b) > 0 else "top_edge"
            else:
                kind = "rake"
        lines.append({"kind": kind, "facets": [facets[k]["id"] for k in fids], "p0": a.tolist(), "p1": b.tolist(),
                      "length_m": L})
    return _merge_collinear(lines)


def _merge_collinear(lines):
    """Join consecutive collinear atomic segments of the same kind and facets into one line item."""
    out = []
    pool = sorted(lines, key=lambda l: (l["kind"], l["facets"], l["p0"], l["p1"]))
    used = [False] * len(pool)
    for i, l in enumerate(pool):
        if used[i]:
            continue
        used[i] = True
        p0, p1 = np.array(l["p0"]), np.array(l["p1"])
        grown = True
        while grown:
            grown = False
            d = (p1 - p0) / np.linalg.norm(p1 - p0)
            for j, m in enumerate(pool):
                if used[j] or m["kind"] != l["kind"] or m["facets"] != l["facets"]:
                    continue
                q0, q1 = np.array(m["p0"]), np.array(m["p1"])
                dm = (q1 - q0) / np.linalg.norm(q1 - q0)
                if abs(abs(float(np.dot(d, dm))) - 1.0) > 1e-9:
                    continue
                if seg_point_dist(q0, p0 - d * 1e3, p1 + d * 1e3) > TOL:
                    continue
                for s, e in ((q0, q1), (q1, q0)):
                    if np.linalg.norm(s - p1) < TOL:
                        p1 = e; used[j] = grown = True; break
                    if np.linalg.norm(e - p0) < TOL:
                        p0 = s; used[j] = grown = True; break
        L = float(np.linalg.norm(p1 - p0))
        out.append({"kind": l["kind"], "facets": l["facets"], "p0": p0.tolist(), "p1": p1.tolist(),
                    "length_m": L, "length_ft": L / FT})
    return out


# ---------------------------------------------------------------------------------------------------------------
# footprint and materials

def footprint_metrics(rects):
    """Union area / perimeter of the wall rectangles (shapely only for the union of several wings)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    u = unary_union([Polygon(r) for r in rects])
    return {"area_m2": u.area, "area_ft2": u.area / FT2, "perimeter_m": u.length, "perimeter_ft": u.length / FT}, u


def _ice_water(lines, metrics, facets, footprint_geom):
    from shapely.geometry import LineString
    fac_by_id = {f["id"]: k for k, f in enumerate(facets)}
    eave_items, area_exact, area_rolls, lf = [], 0.0, 0.0, 0.0
    for l in lines:
        if l["kind"] != "eave":
            continue
        k = fac_by_id[l["facets"][0]]
        slope = metrics[k]["slope"]
        seg = LineString([l["p0"][:2], l["p1"][:2]])
        overhang = seg.distance(footprint_geom.exterior) if not footprint_geom.contains(seg) else 0.0
        reach = (overhang + ICE_INSIDE_WALL_M) * math.sqrt(1.0 + slope * slope) / FT
        rows = 1 + max(0, math.ceil((reach - ICE_ROLL_FT) / (ICE_ROLL_FT - ICE_LAP_FT) - 1e-9))
        area_exact += l["length_ft"] * reach
        area_rolls += l["length_ft"] * rows * ICE_ROLL_FT
        lf += l["length_ft"] * rows
        eave_items.append({"facet": l["facets"][0], "length_ft": l["length_ft"], "overhang_m": overhang,
                           "required_width_ft": reach, "courses": rows})
    valley_ft = sum(l["length_ft"] for l in lines if l["kind"] == "valley")
    return {
        "rule": "IRC R905.1.2: from the eave edge to 24 in inside the exterior wall line, measured up the slope; "
                "36 in rolls with 3 in head laps; one 36 in roll centred in every valley",
        "eaves": eave_items,
        "eave_required_area_ft2": area_exact,
        "eave_roll_area_ft2": area_rolls,
        "eave_roll_lf": lf,
        "valley_lf": valley_ft,
        "valley_area_ft2": valley_ft * VALLEY_ICE_FT,
        "total_roll_area_ft2": area_rolls + valley_ft * VALLEY_ICE_FT,
    }


def compute(house: dict, check_builder: bool = True) -> dict:
    facets = house["facets"]
    metrics = [facet_metrics(f) for f in facets]
    lines = classify_lines(facets, metrics, house["walls"])
    fp, fp_geom = footprint_metrics(house["footprint"])
    if fp_geom.geom_type != "Polygon":
        raise ValueError("footprint is not one connected polygon")

    tot = {k: sum(l["length_ft"] for l in lines if l["kind"] == k)
           for k in ("ridge", "hip", "valley", "eave", "rake", "transition", "step_flashing", "headwall", "top_edge",
                     "penetration", "ambiguous")}
    if tot["ambiguous"] > 0:
        raise ValueError("a roof line is shared by more than two facets")
    area_m2 = sum(m["area_m2"] for m in metrics)
    plan_m2 = sum(m["plan_area_m2"] for m in metrics)
    by_pitch = {}
    for m in metrics:
        key = round(m["pitch_x12"], 2)
        by_pitch[key] = by_pitch.get(key, 0.0) + m["area_ft2"]
    predominant = max(by_pitch.items(), key=lambda kv: kv[1])[0] if by_pitch else None

    det = house["details"]
    counts = {
        "box_vents": sum(1 for d in det if d["kind"] == "box_vent"),
        "pipe_boots": sum(1 for d in det if d["kind"] == "pipe_boot"),
        "skylights": sum(1 for d in det if d["kind"] == "skylight"),
        "chimneys": sum(1 for d in det if d["kind"] == "chimney"),
        "ridge_vent_ft": sum(r["length_m"] for r in house.get("ridge_vents", [])) / FT,
    }
    key = {
        "schema": "vhomes.answer_key/1",
        "house_id": house["spec"]["house_id"],
        "seed": house["spec"]["seed"],
        "roof_type": house["spec"]["roof_type"],
        "generator_version": house["spec"]["generator_version"],
        "units": {"length": "ft (metres also given)", "area": "ft2 (m2 also given)", "square": "100 ft2",
                  "pitch": "rise per 12 run", "azimuth": "compass bearing the facet faces (0 = N, 90 = E)",
                  "frame": "x east, y north, z up, metres; origin = house centre at grade"},
        "facets": [{
            "id": f["id"], "area_m2": m["area_m2"], "area_ft2": m["area_ft2"], "plan_area_m2": m["plan_area_m2"],
            "pitch_x12": m["pitch_x12"], "pitch_deg": m["pitch_deg"], "azimuth_deg": m["azimuth_deg"],
            "hidden_from_above": f["hidden_from_above"], "polygon_m": f["rings"],
        } for f, m in zip(facets, metrics)],
        "totals": {
            "roof_area_m2": area_m2, "roof_area_ft2": area_m2 / FT2, "squares": area_m2 / FT2 / SQ_FT2,
            "roof_plan_area_m2": plan_m2, "roof_plan_area_ft2": plan_m2 / FT2,
            "footprint_area_m2": fp["area_m2"], "footprint_area_ft2": fp["area_ft2"],
            "footprint_perimeter_ft": fp["perimeter_ft"],
            "facet_count": len(facets), "predominant_pitch_x12": predominant,
            "area_by_pitch_ft2": {f"{k:g}/12": v for k, v in sorted(by_pitch.items())},
            "building_height_m": house["heights"]["max_m"],
        },
        "lines_ft": {k: v for k, v in tot.items() if k not in ("ambiguous",)},
        "lines": lines,
        "counts": counts,
        "materials": {
            "drip_edge_ft": tot["eave"] + tot["rake"],
            "starter_eaves_ft": tot["eave"],
            "starter_eaves_and_rakes_ft": tot["eave"] + tot["rake"],
            "ridge_cap_ft": tot["ridge"] + tot["hip"],
            "valley_metal_ft": tot["valley"],
            "step_flashing_ft": tot["step_flashing"],
            "headwall_flashing_ft": tot["headwall"],
            "ice_and_water": _ice_water(lines, metrics, facets, fp_geom),
        },
        "details": det,
        "ridge_vents": house.get("ridge_vents", []),
        "scale_markers": house["markers"],
    }
    if check_builder:
        key["cross_check"] = cross_check(key, house["builder_measurements"])
    return key


def cross_check(key, builder):
    """Compare with the roof builder's own measurements; raise if two independent derivations disagree."""
    pairs = {
        "roof_area_m2": (key["totals"]["roof_area_m2"], builder["roof.area"]),
        "roof_plan_area_m2": (key["totals"]["roof_plan_area_m2"], builder["roof.area_plan"]),
        "footprint_area_m2": (key["totals"]["footprint_area_m2"], builder["footprint.area"]),
    }
    name = {"step_flashing": "sidewall"}
    for k in ("ridge", "hip", "valley", "eave", "rake", "transition", "step_flashing", "headwall"):
        pairs[f"{k}_m"] = (key["lines_ft"][k] * FT, builder[f"edge.{name.get(k, k)}"])
    out, bad = {}, []
    for k, (ours, theirs) in pairs.items():
        diff = ours - theirs
        out[k] = {"answer_key": ours, "builder": theirs, "diff": diff}
        if abs(diff) > 1e-6 * max(1.0, abs(theirs)):
            bad.append(k)
    if bad:
        raise AssertionError(f"answer key disagrees with the roof builder on {bad}: {out}")
    return {"status": "agree (|diff| <= 1e-6 relative)", "values": out}
