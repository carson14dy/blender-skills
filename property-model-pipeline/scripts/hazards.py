#!/usr/bin/env python3
"""Hail / wind / flood history and roof-condition facts for one job, from public sources only.

    python3 hazards.py JOB --profile NAME [--years 10] [--only reports|flood|roof|permits[,...]] [--offline]

Parts (default: all; roof is "pending" until the fit has written model.json):
    reports  NOAA NCEI Storm Events (final) + IEM local storm reports and SPC daily reports (preliminary) within
             1 / 5 / 10 miles; events after the last re-roof permit flagged; NEXRAD hail signatures (NCEI SWDI)
             on the reported hail dates, labelled radar-estimated
    flood    FEMA NFHL flood zone on the parcel polygon (worst zone touching the parcel, and at the house)
    roof     after the fit: tree overhang from the LiDAR, roof access / steepness per facet, eave heights,
             roof colour from the ortho (an estimate)
    permits  re-roof permits within 300 m per year (counts only)
Writes JOB/data/hazards.json (parts merged: --only updates just that part), JOB/out/sections/50_hazards.md
and JOB/out/detail_extra/hazards.json. A failing source is written as "source not reachable on <date>"; no
hazard result stops a run (exit 0), except a privacy hit in the written files (exit 3).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from propmodel import hazards as H  # noqa: E402
from propmodel.sources import Http  # noqa: E402

PARTS = ("reports", "flood", "roof", "permits")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("job")
    ap.add_argument("--profile", help="region profile name or path (wfo, flood layer, permit layer, ortho date)")
    ap.add_argument("--years", type=int, default=10, help="storm history window (default 10)")
    ap.add_argument("--only", action="append", help="reports | flood | roof | permits (repeat or comma-separate)")
    ap.add_argument("--offline", action="store_true", help="cache only (PROPMODEL_OFFLINE=1)")
    ap.add_argument("--refresh", action="store_true", help="ignore cached replies of live sources")
    a = ap.parse_args(argv)
    parts = None
    if a.only:
        parts = [p.strip() for x in a.only for p in x.split(",") if p.strip()]
        bad = [p for p in parts if p not in PARTS]
        if bad:
            ap.error(f"--only: unknown part(s) {', '.join(bad)} (one of {', '.join(PARTS)})")
    if a.offline:
        os.environ["PROPMODEL_OFFLINE"] = "1"
        from propmodel import ept
        ept.install_offline_guard()
    try:
        hz, paths = H.run(os.path.abspath(a.job), a.profile, http=Http(refresh=a.refresh), parts=parts, years=a.years)
    except RuntimeError as e:
        if "privacy" in str(e):
            print(f"G1p STOP: {e} - files deleted")
            return 3
        raise
    except (FileNotFoundError, ValueError) as e:
        print(f"hazards: {e}")
        return 1
    st = hz.get("storms") or {}
    if st:
        print("hazards:", st.get("sentence"))
    fl = (hz.get("flood") or {})
    if fl.get("worst"):
        print(f"  flood zone {fl['worst']['zone']} ({fl['worst']['description']})")
    elif fl.get("message"):
        print("  " + fl["message"])
    rf = hz.get("roof") or {}
    if rf.get("tree_overhang", {}).get("pct") is not None:
        print(f"  tree overhang {rf['tree_overhang']['pct']} % of the roof plan")
    if hz.get("roof_colour"):
        print(f"  roof colour {hz['roof_colour']['name']} {hz['roof_colour']['hex']} (estimate)")
    for s in (st.get("sources") or []) + [x for x in (fl, hz.get("neighbourhood") or {}) if x]:
        if s.get("status") == "unreachable":
            print("  " + s.get("message", ""))
    for p in paths.values():
        print("  wrote", os.path.relpath(p, os.path.abspath(a.job)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
