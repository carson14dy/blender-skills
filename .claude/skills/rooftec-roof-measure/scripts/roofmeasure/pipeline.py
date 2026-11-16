"""The measuring pipeline: find -> fetch -> decode -> planes and edges -> checks -> files."""
import json
import os

from . import cityapi, esri, export, planes
from .units import ATTRIBUTION_CITY, ATTRIBUTION_LIDAR, FT_US, m2_to_ft2, m_to_ft

RESIDENTIAL = {110, 121, 122, 130, 140, 150, 190, 210, 220}
LIDAR_FLOWN_MS = 1608336000000   # 2020-12-19 UTC: the GPS times of the lidar points over the benchmark houses are 19 and 20 Dec 2020


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


def assess(model, footprint, solid_info=None, lookup=None, lidar=None):
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
    if model.stats["regularizeMaxShiftM"] > planes.REGULARIZE_WARN_SHIFT_M or model.stats["regularizeMaxGapM"] > planes.REGULARIZE_WARN_GAP_M:
        flag("regularize", "review", "making the planes flat%s moved a corner %.2f ft (gap left %.2f ft); the city faces do not fit together well"
             % (" and giving them the lidar pitch" if model.stats.get("retiltedPlanes") else "",
                m_to_ft(model.stats["regularizeMaxShiftM"]), m_to_ft(model.stats["regularizeMaxGapM"])))
    if solid_info and solid_info.get("exceededTransferLimit"):
        flag("solid-match", "review", "more solids touch this footprint than one request returns; the right one may be missing")
    elif solid_info and (solid_info.get("candidates", 1) > 1 or solid_info.get("bboxIoU", 1) < 0.8):
        flag("solid-match", "review", "%d solids touched this footprint; picked the best overlap (%.0f%%). Check it is the right building"
             % (solid_info.get("candidates", 1), 100 * solid_info.get("bboxIoU", 0)))
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
        flag("roof-step", "review", "%.1f ft of plane tops end at a wall drop instead of a ridge; the model may hide a ridge or a real step"
             % m_to_ft(tot["top"]["lengthM"]))
    low_wall = sum(e["lengthM"] for e in model.edges if e["type"] == "headwall" and e.get("lowSide"))
    if low_wall > 0.3:
        flag("eave-under-wall", "review", "%.1f ft of eave runs under a wall; the model likely simplified a gable tie-in "
             "(expect valleys there on the real roof)" % m_to_ft(low_wall))
    st = fa.get("STRUCTURE")
    if st is not None and st not in RESIDENTIAL:
        flag("not-residential", "info", "city structure code %s is not a house; flat roofs and parapets are common" % st)
    occ = fa.get("OCCUPIEDDATE")
    yb = (lookup or {}).get("yearBuilt")
    yb = int(yb) if yb and str(yb).isdigit() else None
    if (occ and occ > 1685577600000) or (yb and yb >= 2023):
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
        if sm["siteCheck"]:
            flag("lidar-disagrees", "site-check", "%d plane(s) disagree with lidar by more than the limit" % sm["siteCheck"])
        if sm["override"]:
            flag("lidar-override", "review", "%d plane(s) differ from lidar by 1.5-4 deg; the lidar pitch is used" % sm["override"])
        if sm.get("pitchFromLidar", 0) - sm["override"] > 0:
            flag("lidar-pitch", "info", "%d plane(s) agree with lidar and show the more precise lidar pitch"
                 % (sm["pitchFromLidar"] - sm["override"]))
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
    checks, flags, site = assess(model, footprint, solid_info, lookup, lid)
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
                                            extras={"footprintId": fid, "confidence": doc["summary"]["confidence"]})
    with open(paths["roof"], "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    with open(paths["report"], "w", encoding="utf-8") as f:
        f.write(export.takeoff_markdown(doc))
    return doc, paths
