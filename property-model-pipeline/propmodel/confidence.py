"""Demo-run gates (PASS / WARN / STOP) and the confidence statement that goes with every report.

The gates catch the costly pitfalls of the two finished jobs before anything is published:

* G0 one address match; G1 roof changed after the LiDAR flight (permits / year built); G1p no owner fields;
* G2 LiDAR fit for purpose: density, flight date (leaf-on), plane coverage of the city outline, hillside test
  (-> ground surface mode), footprint convention (drip edge vs wall line), city registration shift, LOD2 pitch;
* G3 the wing spec explains the LiDAR: roof_z RMS, no CONFLICT rows, every plane >= 8 m2 assigned;
* G4 drip edges measured, overhangs plausible, sigma non-zero, fitted city shift in its window;
* G5 report sanity: area vs city LOD2, edge closure, predominant pitch vs the LiDAR plane table;
* G6 Blender mesh roof area equals the report.

Every gate is a dict {id, stage, status, value, limit, message, overridable}. ``overridable`` gates (a human
decision, e.g. "the LiDAR predates an addition: model the old roof?") may be accepted with
``demo_run.py run --yes``; the override is recorded in the confidence statement. Hard gates (privacy,
sigma = 0, an address in the public repo) never are.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import subprocess

import numpy as np

PASS, WARN, STOP = "PASS", "WARN", "STOP"
FORBIDDEN_KEY = re.compile(r"owner|ownname|own_name|taxpayer|mrtnm|mrtadr|buyer|seller|contractor|nameadd|signedby|"
                           r"signed_by|mailing|mail_?addr|occupant|resident", re.I)
LIMITS = {"density": 2.0, "coverage": 0.85, "slope": 0.08, "grade_spread": 1.2, "shift_stop": 1.5, "shift_near": 0.5,
          "lod2_pitch": 1.0, "roof_rms": 0.10, "plane_area": 8.0, "outside_frac": 0.05, "overhang": (0.15, 1.6),
          "overhang_stop": 2.5, "lod2_area": 0.05, "closure": 0.02, "pitch": 0.5, "mesh": 0.005, "city_drip": 0.25}


def gate(gid, status, message, value=None, limit=None, stage=None, overridable=False):
    return {"id": gid, "stage": stage, "status": status, "value": value, "limit": limit, "message": message,
            "overridable": bool(overridable)}


def _load(job, rel, default=None):
    p = os.path.join(job, rel)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def _r(v, n=3):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def plane_cover(roof_rows, cell=0.5, grow=0.25):
    """Plan area covered by accepted roof planes: occupied cells of the inliers (label >= 0), closed, grown."""
    from scipy import ndimage
    from shapely.geometry import box
    from shapely.ops import unary_union
    r = np.asarray(roof_rows)
    r = r[r[:, 3] >= 0] if len(r) else r
    if len(r) < 3:
        return None
    x0, y0 = r[:, 0].min() - 2 * cell, r[:, 1].min() - 2 * cell
    i = ((r[:, 0] - x0) // cell).astype(int); j = ((r[:, 1] - y0) // cell).astype(int)
    occ = np.zeros((i.max() + 3, j.max() + 3), bool)
    occ[i, j] = True
    occ = ndimage.binary_closing(occ, np.ones((3, 3)))
    ii, jj = np.nonzero(occ)
    u = unary_union([box(x0 + a * cell, y0 + b * cell, x0 + (a + 1) * cell, y0 + (b + 1) * cell) for a, b in zip(ii, jj)])
    return u.buffer(grow)


def signed_distances(poly_ring, ref_poly, spacing=0.5):
    """Signed distance of samples along ``poly_ring`` to the boundary of ``ref_poly`` (+ = outside it)."""
    import shapely
    from shapely.geometry import LineString
    ring = LineString(list(poly_ring) + [poly_ring[0]])
    n = max(int(ring.length / spacing), 8)
    pts = np.array([ring.interpolate(k / n, normalized=True).coords[0] for k in range(n)])
    d = shapely.distance(ref_poly.boundary, shapely.points(pts))
    inside = shapely.contains_xy(ref_poly, pts[:, 0], pts[:, 1])
    return np.where(inside, -d, d)


def estimate_shift(city_ring, lidar_poly, search=2.0, step=0.1):
    """(dx, dy) maximising IoU of the city outline moved by (dx, dy) with the LiDAR roof outline."""
    from shapely import affinity
    from shapely.geometry import Polygon
    C = Polygon(city_ring).buffer(0)
    best = (-1.0, 0.0, 0.0)
    for grid, c0 in ((np.arange(-search, search + 1e-9, 4 * step), (0.0, 0.0)), (np.arange(-4 * step, 4 * step + 1e-9, step), None)):
        cx, cy = c0 if c0 is not None else (best[1], best[2])
        for dx in cx + grid:
            for dy in cy + grid:
                M = affinity.translate(C, dx, dy)
                inter = M.intersection(lidar_poly).area
                iou = inter / max(M.union(lidar_poly).area, 1e-9)
                if iou > best[0]:
                    best = (iou, float(dx), float(dy))
    return {"dx": round(best[1], 2), "dy": round(best[2], 2), "iou": round(best[0], 3)}


# ---------------------------------------------------------------------------
# residuals (pm.py resid)
# ---------------------------------------------------------------------------

def plane_residuals(model, roof_rows, planes=(), min_area=8.0):
    """Per LiDAR plane (lidar_roof.npy label): n, points outside the model, median / RMS / p95 of the vertical
    residual LiDAR - model, and whether the plane is explained by the model ("assigned")."""
    r = np.asarray(roof_rows, float)
    z = model.surface_z(r[:, :2])
    d = r[:, 2] - z
    rows = []
    for lab in np.unique(r[:, 3]):
        k = r[:, 3] == lab
        dd = d[k]
        ok = np.isfinite(dd)
        p = planes[int(lab)] if 0 <= int(lab) < len(planes) else {}
        area = float(p.get("area_cells_m2", p.get("area_est_m2", 0.0)) or 0.0)
        row = {"plane": "P%d" % (int(lab) + 1) if lab >= 0 else "unassigned returns", "label": int(lab), "n": int(k.sum()),
               "outside": int((~ok).sum()), "outside_frac": _r((~ok).mean(), 3),
               "median_m": _r(np.median(dd[ok]) if ok.any() else np.nan), "rms_m": _r(np.sqrt(np.mean(dd[ok] ** 2)) if ok.any() else np.nan),
               "p95_abs_m": _r(np.percentile(np.abs(dd[ok]), 95) if ok.any() else np.nan), "area_m2": _r(area, 1),
               "pitch": _r(p.get("pitch_rise_per_12"), 2)}
        if lab >= 0:
            row["assigned"] = bool(ok.mean() >= 0.8 and ok.any() and np.sqrt(np.mean(dd[ok] ** 2)) <= 0.15)
        rows.append(row)
    inl = r[:, 3] >= 0
    okk = inl & np.isfinite(d)
    out = {"planes": rows,
           "covered_rms_m": _r(np.sqrt(np.mean(d[okk] ** 2)) if okk.any() else np.nan),
           "outside_frac": _r((inl & ~np.isfinite(d)).sum() / max(inl.sum(), 1), 4),
           "unassigned_big_planes": [x["plane"] for x in rows if x["label"] >= 0 and not x.get("assigned")
                                     and (x["area_m2"] or 0) >= min_area]}
    return out


def resid_png(model, roof_rows, path):
    """Plan plot of the vertical residuals (needs matplotlib; returns False without it)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    r = np.asarray(roof_rows, float)
    d = r[:, 2] - model.surface_z(r[:, :2])
    k = r[:, 3] >= 0
    fig, ax = plt.subplots(figsize=(8, 7))
    sc = ax.scatter(r[k, 0], r[k, 1], c=np.nan_to_num(d[k], nan=-2), s=3, cmap="RdBu_r", vmin=-0.5, vmax=0.5)
    plt.colorbar(sc, label="LiDAR - model (m); -2 = outside the model")
    for w in model.wings:
        for poly, ls in ((w.wall_polygon(), "k-"), (w.roof_outline(), "g--")):
            xs, ys = poly.exterior.xy
            ax.plot(xs, ys, ls, lw=1)
    ax.set_aspect("equal"); ax.grid(True)
    fig.savefig(path, dpi=70, bbox_inches="tight")
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------
# G0 / G1
# ---------------------------------------------------------------------------

def g0_address(match):
    """``match``: {"n": matches, "source": ..., "county": ...} from the wrapper's address-point lookup."""
    n = match.get("n")
    if match.get("source") == "latlon":
        return [gate("G0.address", PASS, "coordinates given in job.json (no address lookup)", stage="init")]
    if match.get("source") == "census":
        return [gate("G0.address", WARN, "no city address-point layer in the profile: Census geocode used (+/- 10-50 m;"
                     " the footprint pick decides the building)", stage="init")]
    if n == 1:
        g = [gate("G0.address", PASS, "address matched exactly one city address point", value=1, limit="== 1", stage="init")]
    elif not n:
        return [gate("G0.address", STOP, "address not in the city address-point layer: please confirm the spelling",
                     value=0, limit="== 1", stage="init")]
    else:
        return [gate("G0.address", STOP, f"address matched {n} address points (units / duplicates): give the unit or "
                     "the coordinates in job.json", value=n, limit="== 1", stage="init", overridable=True)]
    allowed = match.get("allowed_counties")
    if allowed and match.get("county") and str(match["county"]).lower() not in [c.lower() for c in allowed]:
        g.append(gate("G0.county", WARN, f"county {match['county']!r} is not one this profile covers ({', '.join(allowed)})",
                      value=match["county"], stage="init"))
    elif match.get("county"):
        g.append(gate("G0.county", PASS, f"county {match['county']}", value=match["county"], stage="init"))
    return g


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _date(v):
    """A date from an ArcGIS epoch-ms number, a year, or an ISO / US date string; None when it is not one."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if v > 1e11:
            return dt.datetime.fromtimestamp(v / 1000.0, dt.timezone.utc).date()
        if 1800 < v < 2200:
            return dt.date(int(v), 12, 31)
        return None
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s) or re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if not m:
            return None
        mo, d, y = map(int, m.groups())
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


ADDITION = re.compile(r"addition|new\s*(construction|building|dwelling|house|home|res|single)|new sfd|new sfr", re.I)
TYPE_KEY = re.compile(r"workclass|work_class|permittype|permit_type|projecttype|project_type|^type$|projdesc|description|class", re.I)
DATE_KEY = re.compile(r"final|issue|approv|complet|date", re.I)
YEAR_KEY = re.compile(r"^year_?built$|^yr_?built$|^yearbuilt$|^year_built$", re.I)


def permits_and_year(records):
    """Tolerant reader of records.json (schema owned by records.py): permit-like rows {text, date} and the
    year built values found anywhere in it."""
    permits, years = [], []
    for d in _walk(records or {}):
        for k, v in d.items():
            if YEAR_KEY.match(str(k)) and isinstance(v, (int, float, str)) and str(v).strip()[:4].isdigit():
                y = int(str(v).strip()[:4])
                if 1700 < y < 2200:
                    years.append(y)
        texts = [str(v) for k, v in d.items() if TYPE_KEY.search(str(k)) and isinstance(v, str)]
        dates = [(k, _date(v)) for k, v in d.items() if DATE_KEY.search(str(k))]
        dates = [(k, x) for k, x in dates if x is not None]
        if texts and dates:
            fin = [x for k, x in dates if re.search(r"final|complet", k, re.I)]
            permits.append({"text": " / ".join(texts), "date": max(fin or [x for _, x in dates]).isoformat()})
    return permits, sorted(set(years))


def g1_records(records, lidar_json):
    """LiDAR older than the roof: an addition / new-construction permit after the flight, or a house built in or
    after the LiDAR year -> STOP (ask the owner: model the old roof and flag it, use a newer city roof model, skip)."""
    if records is None:
        return [gate("G1.records", WARN, "no property records (records stage skipped or not installed): roof age and "
                     "changes since the LiDAR flight are unknown", stage="lidar")]
    li = lidar_json or {}
    fd = _date(li.get("flight_date")) if li.get("flight_date") else None
    year = li.get("year") or (fd.year if fd else None)
    permits, years = permits_and_year(records)
    out = []
    late = []
    for p in permits:
        if not ADDITION.search(p["text"]):
            continue
        d = dt.date.fromisoformat(p["date"])
        if (fd and d > fd) or (not fd and year and d.year > int(year)):
            late.append(p)
    yb = max(years) if years else None
    msg_opts = "Options: (a) model the LiDAR-year roof and flag it, (b) use the city's newer roof model with lower " \
               "confidence, (c) skip this house."
    if late:
        out.append(gate("G1.permits", STOP, f"{len(late)} addition / new-construction permit(s) after the LiDAR flight "
                        f"({fd or year}): the LiDAR does not show today's roof. " + msg_opts,
                        value=[p["date"] for p in late], limit=f"none after {fd or year}", stage="lidar", overridable=True))
    else:
        out.append(gate("G1.permits", PASS, f"no addition / new-construction permit after the LiDAR flight ({fd or year})",
                        value=len(permits), stage="lidar"))
    if yb and year and yb >= int(year):
        out.append(gate("G1.year_built", STOP, f"year built {yb} >= LiDAR year {year}: the house may be missing or "
                        "unfinished in the LiDAR. " + msg_opts, value=yb, limit=f"< {year}", stage="lidar", overridable=True))
    elif yb:
        out.append(gate("G1.year_built", PASS, f"year built {yb}, LiDAR {year}", value=yb, stage="lidar"))
    return out


def privacy_scan(paths):
    """Keys in JSON files (and words in markdown) that look like owner / taxpayer / contractor fields.
    Returns [(path, key)]. Uses propmodel.privacy (owner F) when present."""
    try:
        from . import privacy  # noqa: F401
        scan = getattr(privacy, "scan_file", None)
    except ImportError:
        scan = None
    hits = []
    for p in paths:
        if not os.path.exists(p):
            continue
        if scan is not None:
            try:
                hits += [(p, h) for h in (scan(p) or [])]
                continue
            except Exception:  # noqa: BLE001
                pass
        if p.endswith(".json"):
            try:
                with open(p) as f:
                    d = json.load(f)
            except (ValueError, OSError):
                continue
            for o in _walk(d):
                for k in o:
                    if FORBIDDEN_KEY.search(str(k)):
                        hits.append((p, str(k)))
    return hits


# ---------------------------------------------------------------------------
# G2 LiDAR
# ---------------------------------------------------------------------------

def g2_lidar(job, profile=None):
    """Gates on the LiDAR stage outputs. Returns (gates, info) where info["hillside"] says to re-run in
    ground-surface mode."""
    from shapely.geometry import Polygon
    import shapely
    li = _load(job, "data/lidar.json") or {}
    fps = (_load(job, "data/footprints.json") or {}).get("chosen", {})
    info = {}
    G = []
    pts_path = os.path.join(job, "data/lidar_points.npy")
    roof_path = os.path.join(job, "data/lidar_roof.npy")
    if not li or not os.path.exists(pts_path):
        return [gate("G2.lidar", STOP, "no LiDAR results (data/lidar.json)", stage="lidar")], info
    pts = np.load(pts_path)
    outline = Polygon(li["roof_outline"]).buffer(0) if li.get("roof_outline") else None
    # density on the roof
    if outline is not None and outline.area > 1:
        inside = shapely.contains_xy(outline, pts[:, 0], pts[:, 1])
        dens = float(inside.sum() / outline.area)
        G.append(gate("G2.density", PASS if dens >= LIMITS["density"] else STOP,
                      f"{dens:.1f} returns/m2 on the roof", value=_r(dens, 2), limit=">= 2 pts/m2", stage="lidar"))
        info["density_roof"] = dens
    # flight date
    fd = li.get("flight_date")
    if fd:
        G.append(gate("G2.flight", WARN if li.get("leaf_on") else PASS,
                      f"flown {fd}" + (" (leaf-on: trees may hide eaves; check the edges table)" if li.get("leaf_on") else " (leaf-off)"),
                      value=fd, stage="lidar"))
    else:
        G.append(gate("G2.flight", WARN, f"flight date unknown ({li.get('gps_time', 'no GpsTime')}); LiDAR year "
                      f"{li.get('year')}", value=li.get("year"), stage="lidar"))
    # hillside test: lot slope and the spread of the grade along the drip line
    a, b, _ = li.get("ground_plane", [0, 0, 0])
    slope = math.hypot(a, b)
    spread = None
    if outline is not None:
        ring = outline.buffer(3.0).difference(outline.buffer(0.5))
        g = pts[(pts[:, 3] == 2) & shapely.contains_xy(ring, pts[:, 0], pts[:, 1])]
        if len(g) < 30:
            near = pts[shapely.contains_xy(ring, pts[:, 0], pts[:, 1])]
            if len(near):
                key = np.floor(near[:, :2]).astype(int)
                order = np.lexsort((near[:, 2], key[:, 1], key[:, 0]))
                k2 = key[order]
                first = np.r_[True, np.any(k2[1:] != k2[:-1], axis=1)]
                g = near[order][first]
        if len(g) >= 10:
            spread = float(np.percentile(g[:, 2], 95) - np.percentile(g[:, 2], 5))
    hill = slope > LIMITS["slope"] or (spread is not None and spread > LIMITS["grade_spread"])
    info.update(hillside=bool(hill), lot_slope=slope, grade_spread=spread)
    G.append(gate("G2.hillside", WARN if hill else PASS,
                  (f"lot slope {100 * slope:.1f} %, grade spread along the eaves "
                   f"{'n/a' if spread is None else f'{spread:.2f} m'}")
                  + (": hillside -> LiDAR re-run with --ground-mode surface" if hill else ""),
                  value={"slope_pct": _r(100 * slope, 1), "grade_spread_m": _r(spread, 2)},
                  limit="slope <= 8 % and spread <= 1.2 m", stage="lidar"))
    # city outline: coverage by accepted planes, convention, registration
    city = next(((k, v) for k, v in fps.items() if k not in ("osm", "ms")), None)
    reg = (profile or {}).get("registration") or {}
    exp = reg.get("expected_shift")
    stop_above = float(reg.get("stop_above_m", LIMITS["shift_stop"]))
    if city and outline is not None:
        name, c = city
        which = c.get("which", "roof_outline")
        ring = c["ring"]
        if which == "roof_outline":
            sh = estimate_shift(ring, outline)
        else:
            C = Polygon(ring).buffer(0)
            sh = {"dx": round(outline.centroid.x - C.centroid.x, 2), "dy": round(outline.centroid.y - C.centroid.y, 2),
                  "iou": None, "method": "centroid (wall-line layer)"}
        info["shift_prefit"] = sh
        mag = math.hypot(sh["dx"], sh["dy"])
        st = STOP if mag > stop_above else PASS
        msg = f"city outline -> LiDAR shift (pre-fit) ({sh['dx']:+.2f}, {sh['dy']:+.2f}) m"
        if exp is not None and st == PASS and math.hypot(sh["dx"] - exp[0], sh["dy"] - exp[1]) > LIMITS["shift_near"]:
            st, msg = WARN, msg + f", expected about ({exp[0]:+.2f}, {exp[1]:+.2f})"
        if mag > stop_above:
            msg += f": above {stop_above} m = wrong building or wrong datum. Look at overview.png"
        G.append(gate("G2.shift", st, msg, value=[sh["dx"], sh["dy"]], limit=f"|shift| <= {stop_above} m",
                      stage="lidar", overridable=True))
        from shapely import affinity
        moved = affinity.translate(Polygon(ring).buffer(0), sh["dx"], sh["dy"])
        cover = plane_cover(np.load(roof_path)) if os.path.exists(roof_path) else None
        if cover is not None and moved.area > 1:
            cov = float(moved.intersection(cover).area / moved.area)
            G.append(gate("G2.coverage", PASS if cov >= LIMITS["coverage"] else WARN,
                          f"accepted roof planes cover {100 * cov:.0f} % of the city outline"
                          + ("" if cov >= LIMITS["coverage"] else ": a tree-hidden corner, or the outline includes a deck /"
                             " carport: look at overview.png"), value=_r(cov, 3), limit=">= 85 %", stage="lidar"))
        d = signed_distances(list(moved.exterior.coords)[:-1], outline)
        frac_in = float(np.mean(d < -0.25))
        looks = "walls" if frac_in > 0.8 else "drip edge"
        ok = (looks == "walls") == (which == "footprint")
        G.append(gate("G2.convention", PASS if ok else WARN,
                      f"city outline lies inside the LiDAR roof by > 0.25 m on {100 * frac_in:.0f} % of its length: looks "
                      f"like the {looks}; profile says {'walls' if which == 'footprint' else 'drip edge'}",
                      value=_r(frac_in, 3), limit="> 80 % inside = wall line", stage="lidar"))
    elif not city:
        G.append(gate("G2.city", WARN, "no city footprint: outline from LiDAR and imagery footprints only", stage="lidar"))
    return G, info


def g2_lod2(job):
    lod = _load(job, "data/lod2.json")
    if not lod:
        return []
    G = []
    diffs = [f for f in lod.get("summary", {}).get("faces", []) if f.get("pitch_diff") is not None]
    big = [f for f in diffs if abs(f["pitch_diff"]) > LIMITS["lod2_pitch"]]
    if big:
        G.append(gate("G2.lod2_pitch", WARN, "city LOD2 and LiDAR pitch differ by more than 1/12 on "
                      + ", ".join(f"face {f['face']} ({f['pitch']:.1f} vs {f['pitch_lidar']:.1f}/12)" for f in big)
                      + ": roof changed since the LiDAR, or a dormer", value=[f["pitch_diff"] for f in big],
                      limit="<= 1/12", stage="city3d"))
    elif diffs:
        G.append(gate("G2.lod2_pitch", PASS, f"city LOD2 pitch agrees with the LiDAR on {len(diffs)} face(s)",
                      value=max(abs(f["pitch_diff"]) for f in diffs), limit="<= 1/12", stage="city3d"))
    reg = lod.get("registration") or {}
    if reg:
        G.append(gate("G2.lod2_reg", PASS if (reg.get("robust_sd_m") or 9) < 0.15 else WARN,
                      f"city LOD2 registered to the LiDAR: shift ({reg.get('dx'):+.2f}, {reg.get('dy'):+.2f}, {reg.get('dz'):+.2f}) m, "
                      f"robust SD {reg.get('robust_sd_m')} m", value=reg.get("robust_sd_m"), limit="< 0.15 m", stage="city3d"))
    return G


# ---------------------------------------------------------------------------
# G3 fit, G4 edges, G5 report, G6 mesh
# ---------------------------------------------------------------------------

def g3_fit(job):
    fit = _load(job, "fit.json")
    res = _load(job, "data/resid.json")
    if not fit:
        return [gate("G3.fit", STOP, "no fit.json", stage="fit")]
    G = []
    if res:
        rms = res.get("covered_rms_m")
        G.append(gate("G3.roof_rms", PASS if rms is not None and rms <= LIMITS["roof_rms"] else STOP,
                      f"LiDAR roof returns vs the model: RMS {rms} m" + ("" if rms is not None and rms <= LIMITS["roof_rms"]
                                                                        else ": the wing layout does not explain the roof; edit spec.json"),
                      value=rms, limit="<= 0.10 m", stage="fit"))
        un = res.get("unassigned_big_planes") or []
        G.append(gate("G3.planes", STOP if un else PASS,
                      ("LiDAR planes >= 8 m2 the model does not explain: " + ", ".join(un) + " (add or fix a wing)") if un
                      else "every LiDAR plane >= 8 m2 is explained by a wing", value=un, limit="none", stage="fit"))
        of = res.get("outside_frac") or 0.0
        G.append(gate("G3.outside", WARN if of > LIMITS["outside_frac"] else PASS,
                      f"{100 * of:.1f} % of the roof returns lie outside the model roof"
                      + (" (drip edges inside the LiDAR roof: the edges stage measures them)" if of > LIMITS["outside_frac"] else ""),
                      value=of, limit="<= 5 %", stage="fit"))
    conf = [r for r in fit.get("residuals", []) if r.get("flag") == "CONFLICT"]
    G.append(gate("G3.conflict", STOP if conf else PASS,
                  ("CONFLICT: " + "; ".join(f"{r['source']} ({r['target']})" for r in conf) + " - explain each in the report or fix the spec")
                  if conf else "no CONFLICT rows", value=len(conf), limit="0", stage="fit", overridable=True))
    return G


def _overhangs(wings):
    out = {}
    for w in wings:
        if w.get("outline"):
            continue
        for k in ("eave_overhang", "eave_overhang_b", "rake_overhang", "shed_high_overhang"):
            if w.get(k) is not None:
                if k == "rake_overhang" and w.get("type") in ("hip", "pyramid", "mansard", "flat"):
                    continue
                out[f"{w['id']}.{k}"] = float(w[k])
    return out


def g4_edges(job, profile=None):
    ed = _load(job, "data/edges.json")
    fit = _load(job, "fit.json") or {}
    rep = _load(job, "report.json") or {}
    G = []
    if not ed:
        return [gate("G4.edges", STOP, "drip edges not measured (run pm.py edges --write-obs)", stage="edges")]
    rows = ed.get("edges", [])
    ext = [r for r in rows if r.get("status") != "occluded"]
    meas = [r for r in ext if r.get("status") == "measured"]
    Lm, Lt = sum(r["length_m"] for r in meas), sum(r["length_m"] for r in ext) or 1.0
    few = [f"{r['facet']} {r['kind']}" for r in ext if r.get("status") == "too_few_returns"]
    G.append(gate("G4.edges", PASS if Lm / Lt >= 0.7 else WARN,
                  f"drip edge measured from LiDAR on {len(meas)}/{len(ext)} exterior edges ({100 * Lm / Lt:.0f} % of their length)"
                  + (f"; kept as fitted (too few returns, e.g. trees): {', '.join(few)}" if few else ""),
                  value=_r(Lm / Lt, 3), limit=">= 70 % of the length", stage="edges"))
    lo, hi = LIMITS["overhang"]
    ov = _overhangs(fit.get("wings", []))
    measured = ed.get("overhangs") or {}
    bad = {k: v for k, v in ov.items() if not lo <= v <= hi}
    absurd = {k: v for k, v in ov.items() if v > LIMITS["overhang_stop"]}
    msg = ", ".join(f"{k} {v:.2f} m ({'measured' if k in measured else 'prior'})" for k, v in ov.items())
    G.append(gate("G4.overhang", STOP if absurd else (WARN if bad else PASS),
                  ("overhangs " + msg) + (": outside 0.15-1.6 m, check the wing layout" if bad else ""),
                  value={k: _r(v) for k, v in ov.items()}, limit="0.15-1.6 m", stage="edges"))
    sig = rep.get("measurement_sigma_si") or {}
    meas_si = rep.get("measurements_si") or {}
    zero = [k for k in ["roof.area"] + [f"edge.{e}" for e in ("ridge", "hip", "valley", "eave", "rake")]
            if (meas_si.get(k) or 0) > 0.05 and not (sig.get(k) or 0) > 0]
    G.append(gate("G4.sigma", STOP if zero else PASS,
                  ("sigma is zero for " + ", ".join(zero) + " (no free parameters: fit --sigma-free)") if zero
                  else f"area +/- {sig.get('roof.area', 0):.2f} m2; every edge total has a sigma",
                  value=_r(sig.get("roof.area")), limit="> 0", stage="edges"))
    # fitted city shift
    reg = (profile or {}).get("registration") or {}
    nu = fit.get("nuisance") or {}
    for name in sorted({k.split(".")[1] for k in nu if k.startswith("shift.") and k.endswith(".dx")}):
        dx, dy = nu.get(f"shift.{name}.dx", 0.0), nu.get(f"shift.{name}.dy", 0.0)
        mag = math.hypot(dx, dy)
        stop_above = float(reg.get("stop_above_m", LIMITS["shift_stop"]))
        exp = reg.get("expected_shift") if name == "city" else None
        st, msg = (STOP, ": wrong building or wrong datum") if mag > stop_above else (PASS, "")
        if st == PASS and exp is not None and math.hypot(dx - exp[0], dy - exp[1]) > LIMITS["shift_near"]:
            st, msg = WARN, f" (expected about ({exp[0]:+.2f}, {exp[1]:+.2f}))"
        G.append(gate(f"G4.shift_{name}", st, f"fitted shift.{name} ({dx:+.2f}, {dy:+.2f}) m" + msg,
                      value=[_r(dx), _r(dy)], limit=f"|shift| <= {stop_above} m", stage="edges", overridable=True))
    for r in fit.get("residuals", []):
        if r.get("kind") == "footprint" and r.get("target") == "outline" and "rms_m" in r:
            src = r["source"]
            obs = next((o for o in (_load(job, "observations.json") or []) if o.get("source") == src), {})
            if obs.get("which", "roof_outline") != "roof_outline":
                continue
            G.append(gate("G4.city_drip", PASS if r["rms_m"] <= LIMITS["city_drip"] else WARN,
                          f"{src} vs the fitted drip edge after the shift: RMS {r['rms_m']:.2f} m"
                          + ("" if r["rms_m"] <= LIMITS["city_drip"] else " (the LiDAR drip edge wins)"),
                          value=_r(r["rms_m"]), limit="<= 0.25 m", stage="edges"))
    res = _load(job, "data/resid.json")
    if res and res.get("covered_rms_m") is not None:
        rms = res["covered_rms_m"]
        G.append(gate("G4.roof_rms", PASS if rms <= LIMITS["roof_rms"] else STOP,
                      f"after the drip edges: LiDAR roof returns vs the model RMS {rms} m, "
                      f"{100 * (res.get('outside_frac') or 0):.1f} % outside the model roof",
                      value=rms, limit="<= 0.10 m", stage="edges"))
    s3 = _load(job, "data/report_s3.json")
    if s3 and meas_si.get("roof.area"):
        a3 = (s3.get("measurements_si") or {}).get("roof.area")
        if a3:
            ch = meas_si["roof.area"] / a3 - 1
            G.append(gate("G4.area_change", PASS, f"roof area {a3:.1f} -> {meas_si['roof.area']:.1f} m2 ({100 * ch:+.1f} %) "
                          "from the measured drip edges", value=_r(100 * ch, 2), stage="edges"))
    return G


def edge_closure(model_json):
    """Plan length of exterior eaves + rakes against the roof-outline perimeter (fraction difference)."""
    from shapely.geometry import LineString
    from .edges import facet_polygon
    from shapely.ops import unary_union
    roof = unary_union([facet_polygon(f) for f in model_json["facets"]])
    per = roof.length
    if per <= 0:
        return None
    bnd = roof.boundary.buffer(0.02)
    tot = 0.0
    for e in model_json["edges"]:
        if e["kind"] in ("eave", "rake"):
            seg = LineString([e["p0"][:2], e["p1"][:2]])
            tot += seg.intersection(bnd).length
    return {"exterior_eave_rake_plan_m": round(tot, 3), "outline_perimeter_m": round(per, 3), "diff": round(tot / per - 1, 4)}


def g5_report(job):
    rep = _load(job, "report.json") or {}
    mj = _load(job, "model.json")
    li = _load(job, "data/lidar.json") or {}
    lod = _load(job, "data/lod2.json")
    meas = rep.get("measurements_si") or {}
    G = []
    area = meas.get("roof.area")
    if lod and area:
        la = (lod.get("summary") or {}).get("roof_area_m2")
        if la:
            d = area / la - 1
            G.append(gate("G5.lod2_area", PASS if abs(d) <= LIMITS["lod2_area"] else WARN,
                          f"roof area {area:.1f} m2 vs city LOD2 {la:.1f} m2 ({100 * d:+.1f} %; the city model is a check, "
                          "not a second measurement)", value=_r(100 * d, 2), limit="within 5 %", stage="checks"))
    if mj:
        c = edge_closure(mj)
        if c:
            G.append(gate("G5.closure", PASS if abs(c["diff"]) <= LIMITS["closure"] else WARN,
                          f"exterior eaves + rakes {c['exterior_eave_rake_plan_m']:.1f} m vs outline perimeter "
                          f"{c['outline_perimeter_m']:.1f} m ({100 * c['diff']:+.1f} %)", value=_r(100 * c["diff"], 2),
                          limit="within 2 %", stage="checks"))
        facets = sorted(rep.get("facets", []), key=lambda f: -f.get("area_m2", 0))
        planes = li.get("planes", [])
        if facets and planes:
            f = facets[0]
            cand = [p for p in planes if p.get("azimuth") is not None and f.get("azimuth") is not None
                    and abs(((p["azimuth"] - f["azimuth"] + 180) % 360) - 180) < 30]
            if cand:
                p = max(cand, key=lambda q: q["n"])
                d = f["pitch"] - p["pitch_rise_per_12"]
                G.append(gate("G5.pitch", PASS if abs(d) <= LIMITS["pitch"] else WARN,
                              f"largest facet {f['id']} {f['pitch']:.2f}/12 vs LiDAR plane {p['pitch_rise_per_12']:.2f}/12",
                              value=_r(d, 2), limit="within 0.5/12", stage="checks"))
    return G


def g6_mesh(report_area, mesh_area):
    if mesh_area is None:
        return [gate("G6.mesh", WARN, "Blender mesh roof area not measured", stage="blender")]
    d = mesh_area / report_area - 1 if report_area else float("nan")
    return [gate("G6.mesh", PASS if abs(d) <= LIMITS["mesh"] else STOP,
                 f"Blender roof mesh {mesh_area:.2f} m2 vs report {report_area:.2f} m2 ({100 * d:+.2f} %)",
                 value=_r(100 * d, 3), limit="within 0.5 %", stage="blender")]


# ---------------------------------------------------------------------------
# public-repo address check
# ---------------------------------------------------------------------------

def address_tokens(job_cfg, site=None, records=None):
    """Strings that identify the house: the slug, '<number> <street>' and the coordinates (4 decimals)."""
    toks = []
    if job_cfg.get("slug"):
        toks.append(re.escape(job_cfg["slug"]))
    addr = (job_cfg.get("address") or "").split(",")[0].strip()
    m = re.match(r"^\s*(\d+[A-Za-z]?)\s+(.+)$", addr)
    if m:
        num, street = m.groups()
        words = [w for w in re.split(r"\s+", street) if w]
        core = [w for w in words if w.upper().strip(".") not in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")]
        if core:
            toks.append(rf"\b{re.escape(num)}\s+(?:[NSEW]{{1,2}}\.?\s+)?{re.escape(core[0])}\b")
    geo = (site or {}).get("geocode") or {}
    for k in ("lat", "lon"):
        if geo.get(k) is not None:
            toks.append(re.escape(f"{float(geo[k]):.4f}"))
    for d in _walk(records or {}):
        for k, v in d.items():
            if re.search(r"^(tag|countyid|pid|parcel_?id|parcel_number|apn)$", str(k), re.I) and v and len(str(v)) >= 5:
                toks.append(re.escape(str(v)))
    return sorted(set(toks))


def grep_repo(repo_root, tokens):
    """Files of the repo working tree (tracked + untracked, not ignored) that contain any token (case-insensitive)."""
    if not tokens:
        return []
    try:
        files = subprocess.run(["git", "-C", repo_root, "ls-files", "-co", "--exclude-standard"], capture_output=True,
                               text=True, check=True).stdout.split("\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = []
        for dp, dn, fn in os.walk(repo_root):
            dn[:] = [d for d in dn if not d.startswith(".") and d != "__pycache__"]
            files += [os.path.relpath(os.path.join(dp, f), repo_root) for f in fn]
    rx = re.compile("|".join(tokens), re.I)
    hits = []
    for f in files:
        if not f:
            continue
        p = os.path.join(repo_root, f)
        try:
            if os.path.getsize(p) > 5_000_000:
                continue
            with open(p, "rb") as fh:
                txt = fh.read().decode("utf-8", "ignore")
        except OSError:
            continue
        m = rx.search(txt)
        if m:
            hits.append((f, m.group(0)))
    return hits


# ---------------------------------------------------------------------------
# confidence statement
# ---------------------------------------------------------------------------

def _ft(m):
    return m / 0.3048


def confidence(job, gates, job_cfg=None, overrides=()):
    """(markdown, json) confidence statement from report.json, fit.json, lidar.json, edges.json, lod2.json and
    the gate table."""
    rep = _load(job, "report.json") or {}
    fit = _load(job, "fit.json") or {}
    li = _load(job, "data/lidar.json") or {}
    ed = _load(job, "data/edges.json") or {}
    lod = _load(job, "data/lod2.json")
    det = _load(job, "details.json")
    rec = _load(job, "data/records.json")
    m, s = rep.get("measurements_si") or {}, rep.get("measurement_sigma_si") or {}
    area, sa = m.get("roof.area", 0.0), s.get("roof.area", 0.0)
    sq, ssq = area * 10.7639 / 100, sa * 10.7639 / 100
    facets = sorted(rep.get("facets", []), key=lambda f: -f.get("area_m2", 0))
    pw, spw = m.get("roof.pitch_weighted", 0.0) * 12, s.get("roof.pitch_weighted", 0.0) * 12
    rows = [("Roof area", f"{area * 10.7639:,.0f} sq ft ({sq:.2f} squares)", f"{sa * 10.7639:,.0f} sq ft ({ssq:.2f} sq)",
             "model fitted to the LiDAR roof planes and the measured drip edges")]
    rows.append(("Predominant pitch", f"{facets[0]['pitch']:.1f}/12" if facets else "-", f"{spw:.2f}/12",
                 f"LiDAR plane fit (area-weighted pitch {pw:.1f}/12)"))
    for k in ("eave", "rake", "ridge", "hip", "valley", "headwall", "sidewall"):
        v = m.get(f"edge.{k}", 0.0)
        if v > 0.05:
            rows.append((f"{k.capitalize()}s", f"{_ft(v):.1f} ft", f"{_ft(s.get(f'edge.{k}', 0.0)):.1f} ft",
                         "measured drip edges" if k in ("eave", "rake") else "intersection of the fitted planes"))
    meas_edges = [r for r in ed.get("edges", []) if r.get("status") == "measured"]
    ext_edges = [r for r in ed.get("edges", []) if r.get("status") != "occluded"]
    summ = ed.get("summary", {})
    overh = ed.get("overhangs") or {}
    ovs = _overhangs(fit.get("wings", []))
    src = [f"LiDAR: USGS 3DEP {li.get('dataset', '?')}, flown {li.get('flight_date') or li.get('year')}"
           f"{' (leaf-on)' if li.get('leaf_on') else ''}; {len(li.get('planes', []))} roof planes."]
    if meas_edges:
        src.append(f"Drip edges: measured from the outermost LiDAR returns on {len(meas_edges)} of {len(ext_edges)} exterior "
                   f"edges (length-weighted change against the first fit {summ.get('mean_offset_m', 0):+.2f} m).")
    reg = [r for r in fit.get("residuals", []) if r.get("kind") == "footprint"]
    for r in reg:
        src.append(f"Outline check: {r['source'].replace('auto:', '')} (RMS {r.get('rms_m', 0):.2f} m after its registration shift).")
    nu = fit.get("nuisance") or {}
    if "shift.city.dx" in nu:
        src.append(f"City layers sit ({nu['shift.city.dx']:+.2f}, {nu.get('shift.city.dy', 0):+.2f}) m off the LiDAR; every "
                   "city feature was moved by that.")
    if lod:
        la = (lod.get("summary") or {}).get("roof_area_m2")
        if la:
            src.append(f"City 3-D roof model (LOD2): {la * 10.7639:,.0f} sq ft, used as a low-weight check.")
    if rec is not None:
        src.append("Property records and permits: public city / county services (see the property records section).")
    measured = ["roof planes and pitches (LiDAR)", "roof outline at the drip edge (LiDAR returns)" if meas_edges else
                "roof outline (city outline + LiDAR hull; drip edges not measured)",
                "roof area, squares and edge lengths (from the fitted model)"]
    assumed = []
    if overh:
        measured.append("overhangs " + ", ".join(f"{k} {ovs.get(k, v['value']):.2f} m" for k, v in overh.items())
                        + " (fitted to the LiDAR drip edge and the wall line), so the walls are measured too")
        rest = {k: v for k, v in ovs.items() if k not in overh}
        if rest:
            assumed.append("overhangs without a wall-line measurement: " + ", ".join(f"{k} {v:.2f} m" for k, v in rest.items()))
    else:
        assumed.append("wall lines = roof outline minus an assumed overhang ("
                       + ", ".join(f"{k} {v:.2f} m" for k, v in ovs.items()) + "): no wall-line evidence from above")
    assumed.append("eave / plate heights and storeys follow the LiDAR roof and the county class, not a survey")
    if not det or not (det.get("openings") or []):
        assumed.append("doors and windows: not modelled (no photos in the demo tier)")
    else:
        assumed.append("doors and windows: placed without photos (marked 'assumed')")
    assumed.append("yard: LiDAR terrain and city paving outlines; no plants or fences")
    over = [g for g in gates if g["status"] == STOP and g["id"] in set(overrides)]
    md = ["## Confidence statement", "",
          f"**Roof area {area * 10.7639:,.0f} ± {sa * 10.7639:,.0f} sq ft ({sq:.2f} ± {ssq:.2f} squares).** "
          "The ± values are one standard deviation from the fit of the model to the evidence; about two in three "
          "independent re-measurements would land inside them.", "",
          "| Quantity | Value | ± (1σ) | From |", "|---|---|---|---|",
          *[f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows], "",
          "### Where the numbers come from", "", *[f"- {x}" for x in src], "",
          "### Measured", "", *[f"- {x}" for x in measured], "",
          "### Assumed (not measured)", "", *[f"- {x}" for x in assumed], ""]
    if over:
        md += ["### Accepted with a known limitation", "",
               *[f"- {g['id']}: {g['message']} (accepted by the operator)" for g in over], ""]
    md += ["### Checks", "", "| Check | Result | Note |", "|---|---|---|",
           *[f"| {g['id']} | {g['status']} | {str(g['message']).replace('|', '/')} |" for g in gates], ""]
    js = {"roof_area_m2": _r(area), "roof_area_sigma_m2": _r(sa), "squares": _r(sq, 2), "squares_sigma": _r(ssq, 2),
          "predominant_pitch": _r(facets[0]["pitch"], 2) if facets else None, "pitch_sigma": _r(spw, 3),
          "edges_ft": {k: {"value": _r(_ft(m.get(f"edge.{k}", 0.0)), 1), "sigma": _r(_ft(s.get(f"edge.{k}", 0.0)), 1)}
                       for k in ("eave", "rake", "ridge", "hip", "valley", "headwall", "sidewall") if m.get(f"edge.{k}", 0) > 0.05},
          "sources": src, "measured": measured, "assumed": assumed,
          "lidar": {"dataset": li.get("dataset"), "flight_date": li.get("flight_date"), "year": li.get("year"),
                    "leaf_on": li.get("leaf_on")},
          "drip_edges": {"measured": len(meas_edges), "exterior": len(ext_edges)},
          "overhangs_measured": overh, "overrides": [g["id"] for g in over],
          "gates": [{k: g[k] for k in ("id", "status", "message")} for g in gates],
          "go": not any(g["status"] == STOP and g["id"] not in set(overrides) for g in gates)}
    return "\n".join(md), js
