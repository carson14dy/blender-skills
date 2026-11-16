"""The measuring pipeline: find -> fetch -> decode -> planes and edges -> checks -> files."""
import json
import math
import os

from . import cityapi, esri, export, planes
from .units import ATTRIBUTION_CITY, ATTRIBUTION_LIDAR, FT_US, m2_to_ft2, m_to_ft

RESIDENTIAL = {110, 121, 122, 130, 140, 150, 190, 210, 220}
SOLID_CAPTURED_MS = 1685577600000   # 2023-06-01
PERMIT_WATCH_MS = 1672531200000     # 2023-01-01: work permitted from here on was probably not finished at the June 2023 capture
LIDAR_FLOWN_MS = 1608336000000   # 2020-12-19 UTC: the GPS times of the lidar points over the benchmark houses are 19 and 20 Dec 2020
SKEW_MAX_DEG = 45.0     # an open edge called rake that runs closer than this to its plane's level line sheds water like an eave
SKEW_FLAG_M = 3.0       # mention such edges from 10 ft ...
SKEW_REVIEW_M = 9.0     # ... and ask for a look from 30 ft: less than that does not change an order of starter or ice barrier
ROOF_STEP_REVIEW_M = 3.0    # plane tops shorter than 10 ft in total are mentioned, not put up for review
REGULARIZE_REVIEW_SHIFT_M = 0.6   # a corner moved 2 ft: one or two lines are off by more than the 1 ft the report promises
SMALL_PLANE_M2 = 20.0   # 215 sq ft, the size from which the 1 degree pitch target applies (a "main plane")
SMALL_PLANES_SHARE = 0.10   # small planes with an unsettled pitch may cover this share of the roof before it is a site check


def skewed_edges_m(model):
    """Length of open edges classed as rake that run less than SKEW_MAX_DEG off the level line of their plane.

    A real rake runs straight up the slope and a real eave is level. An edge in between means the city
    model drew the plane or the edge askew (39 houses in review round 3: 14 have 10 ft or more). Water
    runs off such an edge, so it may need eave treatment; the tool cannot tell and says so.
    """
    total = 0.0
    for e in model.edges:
        if e["type"] != "rake" or len(e["planes"]) != 1:
            continue
        n = model.planes[e["planes"][0]]["normal"]
        vx, vy = e["b"][0] - e["a"][0], e["b"][1] - e["a"][1]
        run, h = math.hypot(vx, vy), math.hypot(n[0], n[1])
        if run > 1e-6 and h > 0.02 and abs(vx * n[0] + vy * n[1]) / (run * h) < math.sin(math.radians(SKEW_MAX_DEG)):
            total += e["lengthM"]
    return total


def unsettled_small_planes_only(model, rows):
    """True when every plane lidar disagrees with is small and the disagreement is only an unsettled pitch.

    Review round 4: 9 of 51 random houses were a site check because of lidar, 3 of them for one plane under
    215 sq ft where lidar sees one clean surface 1.5 to 4 degrees off the city pitch but its fit is not sharp
    enough to supply the pitch. At 4 degrees such a plane moves the roof area by 0.3% at most, a tenth of the
    printed range. That is a pitch to check on site, not a reason to withhold every number of the house.
    Anything else stays a site check: a main plane, more than 4 degrees, or no single surface in lidar.
    """
    from .lidar import MIN_INLIER_FRACTION, OVERRIDE_DEG
    area = 0.0
    for r in rows:
        P = model.planes[r["plane"]]
        clean = r.get("points") and r.get("inliers", 0) >= MIN_INLIER_FRACTION * r["points"]
        if (not clean or abs(r.get("pitchDiffDeg", 99.0)) > OVERRIDE_DEG or P["areaM2"] >= SMALL_PLANE_M2
                or r.get("surfaceKind") == "ground"):
            return False
        area += P["areaM2"]
    return area <= SMALL_PLANES_SHARE * (model.sloped_area or 1.0)


def find_house(http, out_root, oid=None, latlon=None, address=None):
    """Resolve one of the three selectors to a city footprint. Returns (footprint feature, lookup info)."""
    info = {}
    if oid is not None:
        return cityapi.footprint_by_oid(http, oid, out_root), {"by": "oid"}
    if latlon is not None:
        lat, lon = latlon
        fp, dist = cityapi.footprint_by_point(http, lon, lat, out_root, in_sr=4326)
        return fp, {"by": "latlon", "distanceFt": round(dist, 1)}
    if address:
        cands = cityapi.find_address(http, address, out_root)
        if not cands:
            raise cityapi.LookupError_(
                "no city address point matches %r. Check the spelling, or pass --latlon or --oid. "
                "Houses outside city limits are not in this layer." % address)
        spots = {(round(c["x"], 0), round(c["y"], 0)) for c in cands}
        exact = [c for c in cands if c["match"] == "exact"]
        if len(spots) > 1 and not exact:
            raise cityapi.LookupError_("address is ambiguous; candidates: %s" % ", ".join(sorted({c["address"] for c in cands})))
        c = (exact or cands)[0]
        fp, dist = cityapi.footprint_by_point(http, c["x"], c["y"], out_root)
        info = {"by": "address", "matched": c["address"], "match": c["match"], "yearBuilt": c.get("yearBuilt"),
                "distanceFt": round(dist, 1), "candidates": len(cands)}
        return fp, info
    raise cityapi.LookupError_("give one of --oid, --latlon or --address")


def model_from_features(footprint, solid):
    faces, shape = esri.decode_feature(solid)
    ground = (footprint or {}).get("attributes", {}).get("GROUNDELEVATION")
    return planes.build_model(faces, unit_m=FT_US, ground_z=ground), shape


def assess(model, footprint, solid_info=None, lookup=None, lidar=None, permits=None):
    """Checks and flags. Returns (checks dict, flags list, site check sentence)."""
    fa = (footprint or {}).get("attributes", {})
    flags, checks = [], {}

    def flag(code, severity, message):
        flags.append({"code": code, "severity": severity, "message": message})

    fp_area = fa.get("Shape.STArea()")
    if fp_area:
        diff = 100 * (m2_to_ft2(model.plan_area) - fp_area) / fp_area
        checks["planAreaVsFootprint"] = {"roofPlanFt2": round(m2_to_ft2(model.plan_area), 1), "footprintFt2": round(fp_area, 1),
                                         "diffPct": round(diff, 2), "pass": abs(diff) <= 1.0}
        if abs(diff) > 1.0:
            flag("plan-area-mismatch", "site-check", "roof plan area differs from the city footprint by %.1f%% (limit 1%%); "
                 "the solid may not match this footprint" % diff)
    top = fa.get("BUILDINGTOPELEVATION")
    if top is not None:
        d = model.origin_ft[2] + m_to_ft(model.stats["topZM"]) - top
        checks["topVsBuildingTop"] = {"diffFt": round(d, 2), "pass": abs(d) <= 1.5}
        if abs(d) > 1.5:
            flag("top-height-mismatch", "review", "highest roof point is %.1f ft from the footprint's top elevation" % d)
    if model.stats["maxPlanarityM"] > 0.1524:
        flag("non-planar-face", "review", "a city roof face is %.2f ft out of flat (limit 0.5 ft)" % m_to_ft(model.stats["maxPlanarityM"]))
    shift, gap = model.stats["regularizeMaxShiftM"], model.stats["regularizeMaxGapM"]
    if shift > planes.REGULARIZE_WARN_SHIFT_M or gap > planes.REGULARIZE_WARN_GAP_M:
        # Review round 4: 25 of 64 houses moved a corner more than 1 ft, most of them only because the lidar pitch
        # moved the point where three planes meet. Under 2 ft that is inside the 1 ft per line end the report states.
        bad = shift >= REGULARIZE_REVIEW_SHIFT_M or gap > planes.REGULARIZE_WARN_GAP_M
        flag("regularize", "review" if bad else "info",
             "making the planes flat%s moved a corner %.1f ft (gap left %.2f ft); the ridge, hip and valley lines that meet "
             "there can be off by about that much" % (" and giving them the lidar pitch" if model.stats.get("retiltedPlanes") else "",
                                                      m_to_ft(shift), m_to_ft(gap)))
    if solid_info and solid_info.get("exceededTransferLimit"):
        flag("solid-match", "review", "more solids touch this footprint than one request returns; the right one may be missing")
    elif solid_info and (solid_info.get("candidates", 1) > 1 or solid_info.get("bboxIoU", 1) < 0.8):
        # a neighbour's solid touching the search box is normal (twin homes, tight lots). When the chosen solid
        # overlaps well and its plan area equals the footprint's, it is the right one: say so, ask for nothing.
        sure = solid_info.get("bboxIoU", 1) >= 0.8 and (checks.get("planAreaVsFootprint") or {}).get("pass") is True
        flag("solid-match", "info" if sure else "review", "%d solids touched this footprint; picked the best overlap (%.0f%%)%s"
             % (solid_info.get("candidates", 1), 100 * solid_info.get("bboxIoU", 0),
                " and its plan area matches the footprint" if sure else ". Check it is the right building"))
    if model.stats.get("hiddenFaces"):
        flag("hidden-faces", "info", "%d face(s) under the roof surface were ignored (extra faces in the city solid)" % model.stats["hiddenFaces"])
    if model.stats.get("duplicateFaces"):
        flag("duplicate-faces", "info", "%d face(s) were delivered twice and counted once" % model.stats["duplicateFaces"])
    if model.stats.get("splitRidgeM", 0) > 0.3:
        flag("split-ridge", "info", "%.1f ft of ridge was drawn in the city model as two plane tops with a sliver wall between; "
             "counted as ridge" % m_to_ft(model.stats["splitRidgeM"]))
    if model.stats.get("partlyCoveredFaces"):
        flag("overlapping-faces", "review", "%d roof face(s) partly lie under another face; area may be overstated" % model.stats["partlyCoveredFaces"])
    low = [p for p in model.planes if p["pitchIn12"] < 2.0 and m2_to_ft2(p["areaM2"]) >= 30]
    if low:
        flag("low-slope", "review", "%d plane(s) under 2/12 (%.0f sq ft): not a shingle slope; confirm material on site"
             % (len(low), sum(m2_to_ft2(p["areaM2"]) for p in low)))
    small = [p for p in model.planes if m2_to_ft2(p["areaM2"]) < 30]
    if small:
        flag("small-planes", "info", "%d plane(s) under 30 sq ft; dormer-size detail is unreliable in this data" % len(small))
    tot = model.totals()
    if tot["top"]["lengthM"] > 0.3:
        flag("roof-step", "review" if tot["top"]["lengthM"] >= ROOF_STEP_REVIEW_M else "info",
             "%.0f ft of plane tops end at a wall drop instead of a ridge; the model may hide a ridge or a real step"
             % m_to_ft(tot["top"]["lengthM"]))
    low_wall = sum(e["lengthM"] for e in model.edges if e["type"] == "headwall" and e.get("lowSide"))
    if low_wall > 0.3:
        flag("eave-under-wall", "review", "%.1f ft of eave runs under a wall; the model likely simplified a gable tie-in "
             "(expect valleys there on the real roof)" % m_to_ft(low_wall))
    skew = skewed_edges_m(model)
    if skew >= SKEW_FLAG_M:
        flag("skewed-edge", "review" if skew >= SKEW_REVIEW_M else "info",
             "%.0f ft of open edge is counted as rake but runs at a slant across its plane, so water runs "
             "off it like an eave; check on a photo whether it is an eave" % m_to_ft(skew))
    st = fa.get("STRUCTURE")
    if st is not None and st not in RESIDENTIAL:
        flag("not-residential", "info", "city structure code %s is not a house; flat roofs and parapets are common" % st)
    occ = fa.get("OCCUPIEDDATE")
    yb = (lookup or {}).get("yearBuilt")
    yb = int(yb) if yb and str(yb).isdigit() else None
    if permits is None:
        checks["permits"] = {"checked": False}
        flag("permits-not-checked", "info", "building permits were not looked up (offline, or the service did not answer); "
             "an addition after June 2023 would not show")
    else:
        shape = [p for p in permits if p["workClass"] != "Reshingle" and p["workClass"] not in cityapi.PERMIT_OTHER]
        recent = [p for p in shape if (p["issuedMs"] or 0) >= PERMIT_WATCH_MS]
        other = [p for p in permits if p["workClass"] in cityapi.PERMIT_OTHER and (p["issuedMs"] or 0) >= PERMIT_WATCH_MS]
        resh = [p for p in permits if p["workClass"] == "Reshingle" and p["issuedMs"]]
        checks["permits"] = {"checked": True, "roofShapePermits": len(shape),
                             "sinceCapture": [{"workClass": p["workClass"], "issued": export._date(p["issuedMs"])} for p in recent],
                             "otherSinceCapture": [{"workClass": p["workClass"], "issued": export._date(p["issuedMs"])} for p in other],
                             "lastReshingle": export._date(resh[0]["issuedMs"]) if resh else None}
        if other and not recent:
            flag("permit-other", "info", "a %s permit was issued %s; such work seldom changes the roof shape, ask the owner"
                 % (other[0]["workClass"], export._date(other[0]["issuedMs"])))
        if recent:
            flag("permit-since-capture", "site-check", "a building permit (%s, issued %s) is newer than the city model or was "
                 "open when it was captured in June 2023; the roof may have changed"
                 % (recent[0]["workClass"], export._date(recent[0]["issuedMs"])))
    if (occ and occ > SOLID_CAPTURED_MS) or (yb and yb >= 2023):
        flag("newer-than-solid", "site-check", "built or occupied after the June 2023 capture; the solid may be wrong")
    elif (yb and yb >= 2020) or (occ and occ >= LIDAR_FLOWN_MS):
        flag("newer-than-lidar", "review" if lidar else "info",
             "built or occupied after the December 2020 lidar flight; lidar may show the lot before the house was finished, "
             "so the lidar check does not apply")
    if st in cityapi.ACCESSORY_STRUCTURES:
        flag("accessory-structure", "review", "this footprint is an accessory structure (garage or shed), not the main building")
    if (lookup or {}).get("distanceFt", 0) > 0:
        flag("point-off-building", "review", "the %s is %.0f ft from the chosen building; confirm it is the right one"
             % ("address point" if lookup.get("by") == "address" else "given point", lookup["distanceFt"]))
    if lidar:
        sm = lidar["summary"]
        def named(rows):
            return ", ".join("plane %d" % r["plane"] for r in rows[:4]) + (" and %d more" % (len(rows) - 4) if len(rows) > 4 else "")
        bad = [r for r in lidar["planes"] if r["status"] == "site_check"]
        if bad:
            if unsettled_small_planes_only(model, bad):
                flag("lidar-disagrees", "review", "%s: lidar and the city differ by 1.5 to 4 deg and lidar cannot settle it. "
                     "Each is under 215 sq ft, so the total area moves by under 0.5%%; check that pitch on site" % named(bad))
            else:
                flag("lidar-disagrees", "site-check", "%d plane(s) disagree with lidar by more than the limit (%s)" % (len(bad), named(bad)))
        over = [r for r in lidar["planes"] if r["status"] == "override"]
        if over:
            flag("lidar-override", "review", "%d plane(s) differ from lidar by 1.5-4 deg; the lidar pitch is used (%s)" % (len(over), named(over)))
        def listed(rows):
            return ("; ".join("plane %d, %s" % (r["plane"], r["surfaceNote"]) for r in rows[:3])
                    + ("; and %d more" % (len(rows) - 3) if len(rows) > 3 else ""))
        trees = [r for r in lidar["planes"] if r.get("surfaceKind") == "tree"]
        noted = [r for r in lidar["planes"] if r.get("surfaceNote") and r.get("surfaceKind") != "tree"]
        if noted:
            flag("lidar-surface", "review", "lidar does not see the modelled roof surface on %d plane(s): %s. Area and lines there may be off"
                 % (len(noted), listed(noted)))
        if trees:
            flag("tree-over-roof", "info", "a tree hangs over %d plane(s): %s. The roof under it is measured from the city model; "
                 "lidar checked only the open part" % (len(trees), listed(trees)))
        from .lidar import AZIMUTH_DEG, MIN_POINTS
        turned = [r for r in lidar["planes"] if abs(r.get("azimuthDiffDeg") or 0) >= AZIMUTH_DEG and r.get("inliers", 0) >= MIN_POINTS]
        if turned:
            flag("lidar-azimuth", "review", "%d plane(s) face a different way in lidar than in the city model (%s); their edges "
                 "may be drawn askew" % (len(turned), ", ".join("plane %d by %.0f deg" % (r["plane"], abs(r["azimuthDiffDeg"])) for r in turned[:3])))
        if sm["planesChecked"] == 0:
            flag("lidar-no-check", "review", "no plane had enough lidar points; the city numbers are unchecked")
        reg = lidar.get("registration") or {}
        if "eastM" in reg:
            shift = (reg["eastM"] ** 2 + reg["northM"] ** 2) ** 0.5
            checks["outlinePosition"] = {"shiftM": round(shift, 3), "pass": shift <= 0.5}
            if shift > 0.5:
                flag("outline-shift", "review", "city outline and lidar differ by %.2f m (limit 0.5 m)" % shift)
    else:
        flag("no-lidar-check", "review", "run with --lidar: the city numbers have no independent check yet")
    if any(f["severity"] == "site-check" for f in flags):
        site = "Site check required before any use: see flags."
    else:
        site = "Office estimate only. Confirm one eave length and one pitch on site before a contract."
    return checks, flags, site


def run(http, out_root, oid=None, latlon=None, address=None, with_lidar=False, footprint=None, solid=None,
        house_dir=None, log=None):
    """Measure one house and write roof.json, roof.glb and takeoff.md. Returns (doc, paths)."""
    log = log or (lambda m: None)
    lookup, solid_info = {"by": "files"}, {}
    if footprint is None:
        footprint, lookup = find_house(http, out_root, oid=oid, latlon=latlon, address=address)
    fid = footprint["attributes"]["OBJECTID"]
    if solid is None:
        solid, solid_info = cityapi.solid_for_footprint(http, footprint, out_root)
    house_dir = house_dir or os.path.join(out_root, str(fid))
    os.makedirs(house_dir, exist_ok=True)
    model, shape = model_from_features(footprint, solid)
    if not model.planes:
        raise cityapi.LookupError_("the city solid for footprint %s has no roof faces (walls only); nothing can be measured. "
                                   "Use a site capture for this building." % fid)
    lid = None
    npz = os.path.join(house_dir, "raw", "lidar_points.npz")
    if with_lidar or os.path.exists(npz):   # points fetched once are reused on every later run
        from . import lidar as L
        if os.path.exists(npz):
            pts = L.load_points(npz)
        else:
            pts = L.fetch_points(http, cityapi.footprint_bbox(footprint), out_root, log=log)
            L.save_points(npz, pts)
        lid = L.cross_check(model, pts)
        lid["nodes"] = len(pts.get("nodes", []))
        lid["overridden"] = L.apply_overrides(model, lid)
    try:
        permits = cityapi.permits_for_footprint(http, footprint, out_root)
    except (cityapi.LookupError_, KeyError, ValueError) as e:
        log("permit lookup failed: %s" % e)
        permits = None
    checks, flags, site = assess(model, footprint, solid_info, lookup, lid, permits)
    checks["lookup"] = lookup
    doc = export.build_roof_json(model, footprint, solid, solid_info, address=address, lidar=lid, flags=flags,
                                 site_check=site, checks=checks)
    problems = export.validate_roof_json(doc)
    if problems:
        raise RuntimeError("roof.json failed its own provenance check: %s" % "; ".join(problems[:5]))
    paths = {"dir": house_dir, "roof": os.path.join(house_dir, "roof.json"), "glb": os.path.join(house_dir, "roof.glb"),
             "report": os.path.join(house_dir, "takeoff.md")}
    with open(paths["roof"], "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    attribution = ATTRIBUTION_CITY + (" " + ATTRIBUTION_LIDAR if lid else "")
    doc["checks"]["glb"] = export.write_glb(paths["glb"], model, attribution, floor_z=0.0,
                                            extras={"footprintId": fid, "confidence": doc["summary"]["confidence"],
                                                    "siteCheckRequired": doc["summary"]["siteCheckRequired"]})
    with open(paths["roof"], "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    with open(paths["report"], "w", encoding="utf-8") as f:
        f.write(export.takeoff_markdown(doc))
    return doc, paths
