#!/usr/bin/env python3
"""Run the fixed review benchmark (references/benchmark.md) and print one row per building.

    python3 scripts/benchmark.py --out out/benchmark [--json results.json] [--compare old.json]

It measures the 13 benchmark footprints with --lidar (cached after the first run) and prints sloped
area, predominant pitch, the pitch of every plane of 215 sq ft or more, the line totals and the flags.
With --compare it adds the change against an earlier --json file, which is what a review round reports.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roofmeasure import cityapi, pipeline  # noqa: E402

BENCHMARK = [177261, 218452, 175156, 235245, 235246, 235247, 235248, 176864, 204065, 250390, 363469, 363456,
             199138]   # added in review round 2: an Addition permit issued after the June 2023 capture
MAIN_PLANE_FT2 = 215.0


def summarize(doc):
    s = doc["summary"]
    lid = (doc["checks"].get("lidar") or {}).get("summary") or {}
    return {"slopedFt2": s["slopedAreaFt2"], "planFt2": s["planAreaFt2"], "predominantIn12": s["predominantPitchIn12"],
            "mainPlanesIn12": {str(p["id"]): p["pitchIn12"] for p in doc["planes"] if p["areaFt2"] >= MAIN_PLANE_FT2},
            "edgesFt": {k: v["lengthFt"] for k, v in s["edgeTotals"].items()},
            "lidar": {k: lid.get(k) for k in ("planesChecked", "agree", "override", "siteCheck", "pitchFromLidar")},
            "flags": sorted(f["code"] for f in doc["flags"]),
            "siteCheck": any(f["severity"] == "site-check" for f in doc["flags"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="out/benchmark")
    ap.add_argument("--json", help="write the results to this file")
    ap.add_argument("--compare", help="an earlier --json file to compare with")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    http = cityapi.Http(offline=a.offline)
    old = json.load(open(a.compare)) if a.compare else {}
    res = {}
    for oid in BENCHMARK:
        doc, _ = pipeline.run(http, a.out, oid=oid, with_lidar=True)
        r = res[str(oid)] = summarize(doc)
        line = "%d: %.1f sq ft, %.2f/12, ridge %.1f hip %.1f valley %.1f eave %.1f rake %.1f ft" % (
            oid, r["slopedFt2"], r["predominantIn12"], *(r["edgesFt"][k] for k in ("ridge", "hip", "valley", "eave", "rake")))
        o = old.get(str(oid))
        if o:
            dp = max((abs(v - o["mainPlanesIn12"].get(k, v)) for k, v in r["mainPlanesIn12"].items()), default=0.0)
            line += " | area %+.2f%%, largest main-plane pitch change %.2f/12" % (100 * (r["slopedFt2"] / o["slopedFt2"] - 1), dp)
        print(line + (" | SITE CHECK" if r["siteCheck"] else ""))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
