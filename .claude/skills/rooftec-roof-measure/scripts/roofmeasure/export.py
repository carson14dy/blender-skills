"""Writers: roof.json (the one roof file every tier shares), roof.glb (studio import) and takeoff.md."""
import datetime
import json
import math
import struct

import numpy as np

from . import __version__, proj
from .units import (ATTRIBUTION_CITY, ATTRIBUTION_LIDAR, CITY_SOLID_CAPTURED, CITY_SRID, FT2_PER_SQUARE,
                    LIDAR_CAPTURED, m2_to_ft2, m_to_ft, pitch_label)

# Until the accuracy study (plan experiment 027) passes, nothing from tier A may be called "verified".
# Change this only together with references/validation.md.
STUDY_PASSED = False
DEFAULT_OVERHANG_M = 0.3048   # 12 in, typed default; the city data does not hold the wall line
# Area range (review round 3, references/accuracy.md). On 38 houses the city outline and the lidar roof edge
# agree within 0.05 m on average, the lidar method itself is good to about 0.08 m, and a gutter adds up
# to 0.12 m at an eave, so the outline is taken as known to 0.10 m (4 in). Pitch: 0.3 degree where lidar
# set it, 1 degree where the city pitch was kept.
OUTLINE_TOLERANCE_M = 0.10
PITCH_TOLERANCE_LIDAR_DEG = 0.3
PITCH_TOLERANCE_CITY_DEG = 1.0

EDGE_LABEL = {"ridge": "Ridge", "hip": "Hip", "valley": "Valley", "eave": "Eave", "rake": "Rake",
              "step_flashing": "Step flashing (roof to wall, sloped)", "headwall": "Headwall flashing (roof to wall, level)",
              "top": "High edge of a single-slope plane"}


def _r(v, nd=3):
    return None if v is None else round(float(v), nd)


def _prov(source, tier, captured, note=None, confidence="estimate"):
    p = {"source": source, "tier": tier, "capturedOn": captured, "confidence": confidence}
    if note:
        p["note"] = note
    return p


def build_roof_json(model, footprint=None, solid=None, solid_info=None, address=None, lidar=None, flags=None,
                    site_check=None, checks=None):
    fa = (footprint or {}).get("attributes", {})
    sa = (solid or {}).get("attributes", {})
    ox, oy, oz = model.origin_ft
    cx = ox + m_to_ft(model.stats["bboxM"][0]) / 2
    cy = oy + m_to_ft(model.stats["bboxM"][1]) / 2
    lon, lat = (float(v) for v in proj.city_to_lonlat(cx, cy))
    conv = proj.grid_convergence_deg(lon, lat)
    # "verified" needs three things: the study passed, this roof has no site-check flag, and (for a
    # plane) lidar agreed with it. Until then everything is an estimate.
    blocked = any(f.get("severity") == "site-check" for f in (flags or []))
    roof_ok = STUDY_PASSED and not blocked and lidar is not None

    def city_prov(note=None, ok=False):
        return _prov("city-solid", "A", CITY_SOLID_CAPTURED, note, "verified" if ok else "estimate")
    planes = []
    lidar_by_plane = {r["plane"]: r for r in (lidar or {}).get("planes", [])}
    for P in model.planes:
        lr = lidar_by_plane.get(P["id"])
        note = None
        if lr:
            note = {"agree": "pitch cross-checked by lidar", "override": "pitch replaced by lidar; review",
                    "site_check": "lidar disagrees; site check required", "not_checked": "not checked by lidar: too few points on this plane"}[lr["status"]]
            if lr["status"] == "agree" and lr.get("action") == "use_lidar":
                note = "pitch from lidar; the city pitch agreed within the limit"
        prov = city_prov(note, roof_ok and bool(lr) and lr["status"] == "agree")
        rec = {
            "id": P["id"],
            "polygon": [[_r(c) for c in p] for p in P["polygon"]],
            "holes": [[[_r(c) for c in p] for p in h] for h in P["holes"]],
            "pitchDeg": _r(P["pitchDeg"], 2), "pitchIn12": _r(P["pitchIn12"], 2),
            "azimuthDeg": None if P["azimuthGridDeg"] is None else _r((P["azimuthGridDeg"] + conv) % 360, 1),
            "planAreaM2": _r(P["planAreaM2"], 2), "areaM2": _r(P["areaM2"], 2), "areaFt2": _r(m2_to_ft2(P["areaM2"]), 1),
            "planarityM": _r(P["planarityM"]), "faceCount": P["faceCount"], "sourcePitchDeg": _r(P["sourcePitchDeg"], 2),
            "provenance": prov,
        }
        if P.get("pitchSource") == "lidar":
            rec["pitchProvenance"] = _prov("usgs-3dep-lidar", "B", LIDAR_CAPTURED, "replaces city pitch %.2f deg" % P["cityPitchDeg"])
            rec["cityPitchDeg"] = _r(P["cityPitchDeg"], 2)
            rec["cityAreaM2"] = _r(P["cityAreaM2"], 2)
        if lr:
            rec["lidar"] = {k: lr[k] for k in ("status", "action", "points", "inliers", "rmseM", "pitchSeDeg", "precise",
                                                    "lidarPitchDeg", "pitchDiffDeg", "azimuthDiffDeg", "siblingPlane",
                                                    "surface", "surfaceKind", "surfaceNote") if k in lr}
        planes.append(rec)
    edges = [{"id": e["id"], "type": e["type"], "a": [_r(c) for c in e["a"]], "b": [_r(c) for c in e["b"]],
              "lengthM": _r(e["lengthM"]), "lengthFt": _r(m_to_ft(e["lengthM"]), 2), "planes": e["planes"],
              "provenance": city_prov(ok=roof_ok), **({"lowSide": True} if e.get("lowSide") else {})} for e in model.edges]
    tot = model.totals()
    sloped = model.sloped_area
    # predominant pitch = area-weighted median
    order = sorted(model.planes, key=lambda p: p["pitchDeg"])
    acc, pred = 0.0, None
    for p in order:
        acc += p["areaM2"]
        if acc >= sloped / 2:
            pred = p["pitchDeg"]
            break
    doc = {
        "format": "rooftec-roof", "version": 1,
        "generator": "rooftec-roof-measure %s" % __version__,
        "createdOn": datetime.date.today().isoformat(),
        "address": address, "footprintId": fa.get("OBJECTID"), "solidId": sa.get("OBJECTID"),
        "units": {"length": "m", "area": "m2", "angle": "deg",
                  "axes": "x east, y north, z up; z = 0 at the city ground elevation",
                  "note": "feet and squares are repeated in summary and in edges for reports"},
        "origin": {"epsg": CITY_SRID, "eastingFtUS": _r(ox, 3), "northingFtUS": _r(oy, 3), "elevationFtUS": _r(oz, 3),
                   "lat": _r(lat, 7), "lon": _r(lon, 7), "gridConvergenceDeg": _r(conv, 3),
                   "verticalDatum": "NAVD88 (inferred, not documented by the city)"},
        "building": {"structure": fa.get("STRUCTURE"), "stories": fa.get("NUMBERSTORIES"),
                     "groundElevationFt": _r(fa.get("GROUNDELEVATION"), 2), "topElevationFt": _r(fa.get("BUILDINGTOPELEVATION"), 2),
                     "occupiedDate": _date(fa.get("OCCUPIEDDATE")), "captureMethod": fa.get("CAPTUREMETH"),
                     "footprintAreaFt2": _r(fa.get("Shape.STArea()"), 1)},
        "summary": {
            "confidence": "verified" if roof_ok and all(p["provenance"]["confidence"] == "verified" for p in planes
                                                         if p["areaFt2"] >= 30) else "estimate",
            "siteCheckRequired": blocked,   # true = do not use the numbers before someone has been on site
            "siteCheck": site_check,
            "planeCount": len(planes),
            "planAreaM2": _r(model.plan_area, 2), "planAreaFt2": _r(m2_to_ft2(model.plan_area), 1),
            "slopedAreaM2": _r(sloped, 2), "slopedAreaFt2": _r(m2_to_ft2(sloped), 1),
            "squares": _r(m2_to_ft2(sloped) / FT2_PER_SQUARE, 2),
            "areaRange": area_range(model),
            "predominantPitchDeg": _r(pred, 2), "predominantPitchIn12": _r(12 * math.tan(math.radians(pred or 0)), 2),
            "edgeTotals": {t: {"lengthM": _r(v["lengthM"]), "lengthFt": _r(m_to_ft(v["lengthM"]), 1), "count": v["count"]}
                           for t, v in tot.items()},
            "provenance": city_prov("waste factor not included", roof_ok),
        },
        "planes": planes, "edges": edges,
        "assumptions": {"overhangM": {"value": DEFAULT_OVERHANG_M,
                                      "provenance": _prov("default", "-", None, "wall line is not in the city data; typed default 12 in. Not added to any area or length here: "
                                                           "the city outline already is the roof edge", "assumed")}},
        "checks": dict(checks or {}, lidar=lidar, solid=dict(solid_info or {}, **{k: _r(v) if isinstance(v, float) else v for k, v in model.stats.items()})),
        "flags": flags or [],
        "attribution": [ATTRIBUTION_CITY] + ([ATTRIBUTION_LIDAR] if lidar else []),
        "license": {"cityData": "CC BY 4.0; not for mapping products for resale", "lidar": "public domain (USGS)"},
    }
    return doc


def area_range(model):
    """How far the sloped area may be off, from the two things that set it: the outline and the pitch.

    Outline: every open edge (eave or rake) may sit OUTLINE_TOLERANCE_M further in or out, which changes
    the plan area by that distance times the length of those edges seen from above. Pitch: a plane's area
    changes by tan(pitch) times the pitch error. The two are combined as independent errors. This is a
    likely range from public data, not a guarantee, and it does not cover a roof that was changed or a
    model that misses a part of the roof; the flags cover those.
    """
    plan, sloped = model.plan_area, model.sloped_area
    if plan <= 0 or sloped <= 0:
        return None
    open_m = sum(math.hypot(e["b"][0] - e["a"][0], e["b"][1] - e["a"][1]) for e in model.edges if e["type"] in ("eave", "rake"))
    outline_pct = 100.0 * open_m * OUTLINE_TOLERANCE_M / plan
    pitch_pct = 100.0 * sum(p["areaM2"] * math.tan(math.radians(p["pitchDeg"])) * math.radians(
        PITCH_TOLERANCE_LIDAR_DEG if p.get("pitchSource") == "lidar" else PITCH_TOLERANCE_CITY_DEG) for p in model.planes) / sloped
    pct = math.hypot(outline_pct, pitch_pct)
    ft2 = m2_to_ft2(sloped)
    return {"plusMinusPct": _r(pct, 1), "plusMinusFt2": _r(ft2 * pct / 100, 0),
            "lowFt2": _r(ft2 * (1 - pct / 100), 0), "highFt2": _r(ft2 * (1 + pct / 100), 0),
            "outlinePct": _r(outline_pct, 1), "pitchPct": _r(pitch_pct, 1),
            "outlineToleranceM": OUTLINE_TOLERANCE_M, "openEdgePlanM": _r(open_m, 1),
            "note": "likely range from the outline (known to about 4 in) and the pitch; not a guarantee, and it does not "
                    "cover a changed roof or a roof part the model misses"}


def _date(ms):
    if not ms:
        return None
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=ms)).date().isoformat()


def validate_roof_json(doc):
    """Return a list of problems (empty = valid). Every measured value must carry source and confidence."""
    bad = []
    for key in ("format", "version", "planes", "edges", "summary", "attribution", "origin"):
        if key not in doc:
            bad.append("missing %s" % key)
    if doc.get("format") != "rooftec-roof":
        bad.append("format must be rooftec-roof")
    if not doc.get("attribution"):
        bad.append("attribution is empty")
    for kind in ("planes", "edges"):
        for item in doc.get(kind, []):
            p = item.get("provenance") or {}
            for k in ("source", "tier", "capturedOn", "confidence"):
                if k not in p:
                    bad.append("%s %s: provenance.%s missing" % (kind, item.get("id"), k))
            if p.get("confidence") not in ("verified", "estimate", "assumed"):
                bad.append("%s %s: bad confidence %r" % (kind, item.get("id"), p.get("confidence")))
    if (doc.get("summary", {}).get("provenance") or {}).get("confidence") is None:
        bad.append("summary.provenance.confidence missing")
    return bad


# --------------------------------------------------------------------------- GLB

def write_glb(path, model, attribution, floor_z=0.0, extras=None):
    """Binary glTF 2.0, metres, Y up (X east, Y up, Z = -north), one mesh named `Roof` and one named `Walls`.

    The studio (`roof-visualizer`, `extractRoofPlanes`) and `roof-blender` both pick up the mesh named
    `Roof`; walls stay as the visible house. Triangles are not indexed and are flat shaded.
    """
    def yup(tris):
        a = np.asarray(tris, dtype=np.float64).reshape(-1, 3)
        return np.column_stack([a[:, 0], a[:, 2], -a[:, 1]]).astype("<f4")

    def normals(pos):
        t = pos.reshape(-1, 3, 3).astype(np.float64)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        return np.repeat(n, 3, axis=0).astype("<f4")

    roof = yup([t for _, t in model.roof_triangles()])
    walls = yup(model.wall_triangles(floor_z=floor_z))
    cx, cz = (roof[:, 0].min() + roof[:, 0].max()) / 2, (roof[:, 2].min() + roof[:, 2].max()) / 2
    blob, views, accessors, meshes, nodes = b"", [], [], [], []
    mats = [{"name": "Roof", "pbrMetallicRoughness": {"baseColorFactor": [0.25, 0.25, 0.27, 1], "metallicFactor": 0, "roughnessFactor": 0.9}},
            {"name": "Wall", "pbrMetallicRoughness": {"baseColorFactor": [0.82, 0.8, 0.76, 1], "metallicFactor": 0, "roughnessFactor": 0.95},
             "doubleSided": True}]
    for name, pos, mat in (("Roof", roof, 0), ("Walls", walls, 1)):
        if not len(pos):
            continue
        pos = pos.copy()
        pos[:, 0] -= cx
        pos[:, 2] -= cz
        attrs = {}
        for sem, arr in (("POSITION", pos), ("NORMAL", normals(pos))):
            data = arr.tobytes()
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": 34962})
            blob += data
            acc = {"bufferView": len(views) - 1, "componentType": 5126, "count": len(arr), "type": "VEC3"}
            if sem == "POSITION":
                acc["min"] = [float(v) for v in arr.min(axis=0)]
                acc["max"] = [float(v) for v in arr.max(axis=0)]
            accessors.append(acc)
            attrs[sem] = len(accessors) - 1
        meshes.append({"name": name, "primitives": [{"attributes": attrs, "material": mat, "mode": 4}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
    gltf = {
        "asset": {"version": "2.0", "generator": "rooftec-roof-measure %s" % __version__, "copyright": attribution},
        "scene": 0, "scenes": [{"name": "House", "nodes": list(range(len(nodes))), "extras": dict(extras or {}, attribution=attribution)}],
        "nodes": nodes, "meshes": meshes, "materials": mats, "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob)))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0") + blob)
    return {"roofTriangles": len(roof) // 3, "wallTriangles": len(walls) // 3}


def read_glb_json(path):
    with open(path, "rb") as f:
        magic, ver, _ = struct.unpack("<4sII", f.read(12))
        n, kind = struct.unpack("<I4s", f.read(8))
        if magic != b"glTF" or kind != b"JSON":
            raise ValueError("not a GLB file")
        return json.loads(f.read(n))


# --------------------------------------------------------------------------- report

def takeoff_markdown(doc):
    s = doc["summary"]
    L = []
    title = doc.get("address") or "footprint %s" % doc.get("footprintId")
    L.append("# Roof takeoff: %s" % title)
    L.append("")
    status = "SITE CHECK REQUIRED" if s.get("siteCheckRequired") else s["confidence"].upper()
    L.append("**Status: %s.** %s" % (status, s.get("siteCheck") or ""))
    L.append("")
    L.append("| Measure | Value |")
    L.append("|---|---|")
    L.append("| Sloped roof area | %s sq ft = **%.1f squares** (no waste added) |" % ("{:,.0f}".format(s["slopedAreaFt2"]), s["squares"]))
    ar = s.get("areaRange")
    if ar:
        L.append("| Likely range of the sloped area | %s to %s sq ft (plus or minus %.1f%%) |"
                 % ("{:,.0f}".format(ar["lowFt2"]), "{:,.0f}".format(ar["highFt2"]), ar["plusMinusPct"]))
    L.append("| Plan (flat) area | %s sq ft |" % "{:,.0f}".format(s["planAreaFt2"]))
    L.append("| Predominant pitch | **%s** (%.1f deg) |" % (pitch_label(s["predominantPitchDeg"]), s["predominantPitchDeg"]))
    L.append("| Roof planes | %d |" % s["planeCount"])
    L.append("| City footprint / solid | %s / %s, solid captured %s |" % (doc.get("footprintId"), doc.get("solidId"), CITY_SOLID_CAPTURED))
    L.append("")
    L.append("## Lines")
    L.append("")
    L.append("| Line | Feet | Pieces |")
    L.append("|---|---|---|")
    for t, v in s["edgeTotals"].items():
        if v["count"]:
            L.append("| %s | %.0f | %d |" % (EDGE_LABEL[t], v["lengthFt"], v["count"]))
    L.append("")
    L.append("## Planes")
    L.append("")
    has_lidar = any("lidar" in p for p in doc["planes"])
    L.append("| # | Pitch | Faces (compass) | Sloped sq ft |%s" % (" Lidar pitch (difference from city, points) | Lidar check |" if has_lidar else ""))
    L.append("|---|---|---|---|%s" % ("---|---|" if has_lidar else ""))
    for p in doc["planes"]:
        row = "| %d | %s (%.1f deg) | %s | %.0f |" % (p["id"], pitch_label(p["pitchDeg"]), p["pitchDeg"], _compass(p["azimuthDeg"]), p["areaFt2"])
        if has_lidar:
            lr = p.get("lidar") or {}
            # a fit on a handful of points is not a measurement: show a lidar pitch only for a plane that was checked
            lp = lr.get("lidarPitchDeg") if lr.get("status") not in (None, "not_checked") else None
            row += " %s | %s |" % ("%s (%+.1f deg, %d pts)" % (pitch_label(lp), lr.get("pitchDiffDeg", 0), lr.get("inliers", 0)) if lp is not None else "-",
                                   (lr.get("status") or "-").replace("_", " "))
        L.append(row)
    L.append("")
    L.append("## Flags")
    L.append("")
    if doc["flags"]:
        for f in doc["flags"]:
            L.append("- **%s** (%s): %s" % (f["code"], f["severity"], f["message"]))
    else:
        L.append("- None.")
    lid = (doc.get("checks") or {}).get("lidar")
    if lid:
        sm = lid["summary"]
        L.append("")
        L.append("## Lidar cross-check (USGS 3DEP 2020)")
        L.append("")
        L.append("%d of %d planes checked (%.0f%% of the area): %d agree, %d overridden by lidar, %d need a site check, %d not checked (too few points)."
                 % (sm["planesChecked"], sm["planes"], sm["areaCheckedPct"], sm["agree"], sm["override"], sm["siteCheck"], sm["notChecked"]))
        if sm.get("pitchFromLidar"):
            L.append("%d plane(s) show the lidar pitch, because the lidar fit was precise; the city pitch is kept in roof.json as `cityPitchDeg`."
                     % sm["pitchFromLidar"])
        reg = lid.get("registration")
        if reg and "eastM" in reg:
            L.append("Lidar sits %.1f ft east, %.1f ft north and %.1f ft above the city solid (negative means west, south or below)."
                     % (m_to_ft(reg["eastM"]), m_to_ft(reg["northM"]), m_to_ft(reg["verticalM"])))
    L.append("")
    L.append("## How to read this")
    L.append("")
    L.append("- Every number is an **estimate** from public data until the accuracy study passes. Do not put it on a customer document.")
    L.append("- Areas and eaves are measured at the city's roof outline (the drip line), so overhangs are already included. "
             "Lidar confirms that outline to about 4 in%s. Tape one eave to eave width on site to narrow it."
             % (", which is the largest part of the %.1f%% range above" % ar["plusMinusPct"] if ar else ""))
    L.append("- Line lengths are rounded to the foot. A single edge can be off by about 1 ft, because each end follows the city outline.")
    L.append("- The model does not show chimneys, pipe boots, skylights or small dormers.")
    L.append("")
    for a in doc["attribution"]:
        L.append("_%s_" % a)
    L.append("")
    return "\n".join(L)


def _compass(az):
    if az is None:
        return "flat"
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return "%s (%d deg)" % (names[int((az + 22.5) // 45) % 8], round(az))
