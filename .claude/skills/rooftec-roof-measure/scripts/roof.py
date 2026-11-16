#!/usr/bin/env python3
"""Measure a Sioux Falls roof from free public data and hand it to the Rooftec roof studio.

    python3 roof.py measure --address "224 W 9th St" --out out/roofs --lidar
    python3 roof.py measure --oid 235245 --out out/roofs
    python3 roof.py measure --latlon 43.4809,-96.7424 --out out/roofs
    python3 roof.py find    --address "224 W 9th St"
    python3 roof.py fetch   --oid 235245              # download and cache only
    python3 roof.py decode  --oid 235245              # solid faces as JSON (feet)
    python3 roof.py lidar   --oid 235245              # add the lidar check to a measured house
    python3 roof.py compare --roof out/roofs/235245/roof.json --truth truth.json   # accuracy study

Outputs land in <out>/<footprintId>/: roof.json, roof.glb, takeoff.md and raw/ (cached answers).
Needs Python 3.9+ and numpy. `--lidar` also needs: pip install laspy lazrs
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import numpy  # noqa: F401
except ImportError:
    sys.exit("numpy is required: pip install numpy")

from roofmeasure import cityapi, esri, pipeline  # noqa: E402


def _selectors(p):
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--address", help='street address inside Sioux Falls, e.g. "224 W 9th St"')
    g.add_argument("--oid", type=int, help="city Building Footprints OBJECTID")
    g.add_argument("--latlon", help='"lat,lon" in decimal degrees, e.g. 43.4809,-96.7424')
    p.add_argument("--out", default="out/roofs", help="root folder for results and cache (default out/roofs; keep it git-ignored)")
    p.add_argument("--offline", action="store_true", help="use cached answers only; fail instead of calling a service")
    p.add_argument("--quiet", action="store_true")


def _latlon(text):
    if not text:
        return None
    try:
        lat, lon = (float(v) for v in text.replace(" ", "").split(","))
    except ValueError:
        sys.exit('--latlon wants "lat,lon", for example 43.4809,-96.7424')
    if lat < 0 and lon > 0:
        lat, lon = lon, lat
    return lat, lon


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, hlp in (("measure", "find, fetch, measure and write roof.json, roof.glb, takeoff.md"),
                      ("find", "show which city footprint a selector resolves to"),
                      ("fetch", "download and cache the footprint and the 3D solid"),
                      ("decode", "print the solid's faces as JSON (feet, EPSG 32164)"),
                      ("lidar", "same as measure --lidar (reuses cached city data)")):
        p = sub.add_parser(name, help=hlp)
        _selectors(p)
        if name == "measure":
            p.add_argument("--lidar", action="store_true", help="cross-check each plane's pitch against USGS 3DEP lidar")
        if name in ("measure", "lidar"):
            p.add_argument("--json", action="store_true", help="print the summary as JSON instead of text")
    p = sub.add_parser("compare", help="accuracy study: compare a measured roof.json with a truth file")
    p.add_argument("--roof", required=True, help="path to roof.json")
    p.add_argument("--truth", required=True, help="path to the truth JSON (see roofmeasure/study.py)")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        from roofmeasure import study
        with open(a.roof, encoding="utf-8") as f:
            doc = json.load(f)
        with open(a.truth, encoding="utf-8") as f:
            truth = json.load(f)
        rows, passed = study.compare(doc, truth)
        text = study.markdown(doc, truth, rows, passed)
        out = os.path.join(os.path.dirname(os.path.abspath(a.roof)), "accuracy.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(text + "\nWrote " + out)
        return 0 if passed else 1
    log = (lambda m: None) if a.quiet else (lambda m: print("  " + m, file=sys.stderr))
    http = cityapi.Http(offline=a.offline, log=log)
    sel = dict(oid=a.oid, latlon=_latlon(a.latlon), address=a.address)
    try:
        if a.cmd == "find":
            fp, info = pipeline.find_house(http, a.out, **sel)
            at = fp["attributes"]
            print(json.dumps({"footprintId": at["OBJECTID"], "structure": at.get("STRUCTURE"), "stories": at.get("NUMBERSTORIES"),
                              "areaFt2": round(at.get("Shape.STArea()") or 0, 1), "bboxFt": [round(v, 2) for v in cityapi.footprint_bbox(fp)],
                              "lookup": info}, indent=1))
            return 0
        if a.cmd in ("fetch", "decode"):
            fp, info = pipeline.find_house(http, a.out, **sel)
            solid, sinfo = cityapi.solid_for_footprint(http, fp, a.out)
            if a.cmd == "fetch":
                print(json.dumps({"footprintId": fp["attributes"]["OBJECTID"], "solidId": solid["attributes"]["OBJECTID"],
                                  "solid": sinfo, "cache": os.path.join(a.out, str(fp["attributes"]["OBJECTID"]), "raw")}, indent=1))
                return 0
            faces, shape = esri.decode_feature(solid)
            print(json.dumps({"solidId": solid["attributes"]["OBJECTID"], "epsg": 32164, "units": "US survey feet",
                              "bbox": shape["bbox"], "zRange": shape["zrange"],
                              "partTypes": sorted({esri.PART_NAMES.get(t, str(t)) for t, _, _ in shape["parts"]}),
                              "faces": [f.round(4).tolist() for f in faces]}))
            return 0
        doc, paths = pipeline.run(http, a.out, with_lidar=(a.cmd == "lidar" or getattr(a, "lidar", False)), log=log, **sel)
    except cityapi.LookupError_ as e:
        print("Could not measure: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # lidar extras missing, etc.
        if type(e).__name__ == "LidarUnavailable":
            print("Lidar check unavailable: %s" % e, file=sys.stderr)
            return 3
        raise
    s = doc["summary"]
    if getattr(a, "json", False):
        print(json.dumps({"summary": s, "flags": doc["flags"], "paths": paths}, indent=1))
        return 0
    print("Footprint %s, solid %s: %d planes, %.0f sq ft sloped = %.1f squares, predominant pitch %.1f/12  [%s]"
          % (doc["footprintId"], doc["solidId"], s["planeCount"], s["slopedAreaFt2"], s["squares"], s["predominantPitchIn12"],
             "site check required" if s.get("siteCheckRequired") else s["confidence"]))
    if s.get("areaRange"):
        print("Likely range of the sloped area: %.0f to %.0f sq ft (plus or minus %.1f%%; the outline is known to about 4 in)"
              % (s["areaRange"]["lowFt2"], s["areaRange"]["highFt2"], s["areaRange"]["plusMinusPct"]))
    print("Lines (ft): " + ", ".join("%s %.1f" % (t, v["lengthFt"]) for t, v in s["edgeTotals"].items() if v["count"]))
    lid = doc["checks"].get("lidar")
    if lid:
        sm = lid["summary"]
        print("Lidar: %d/%d planes checked (%.0f%% of area): %d agree, %d override, %d site check, %d not checked; mean |pitch diff| %s deg"
              % (sm["planesChecked"], sm["planes"], sm["areaCheckedPct"], sm["agree"], sm["override"], sm["siteCheck"], sm["notChecked"], sm["meanAbsPitchDiffDeg"]))
    for f in doc["flags"]:
        print("FLAG %-11s %s: %s" % (f["severity"], f["code"], f["message"]))
    print(s["siteCheck"])
    print("Wrote %s, %s, %s (%d requests)" % (paths["roof"], paths["glb"], paths["report"], http.requests_made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
