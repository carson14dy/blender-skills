#!/usr/bin/env python3
"""Property records for one job: parcel, permits, assessed value, sales, from public city / county GIS layers.

    python3 records.py JOB --profile NAME [--offline] [--refresh] [--street "1 TEST AVE"]

Reads JOB/site.json (geocode), JOB/job.json (address), JOB/data/address_point.json (if the wrapper's init
stage wrote it) and JOB/data/lidar.json (flight date, if the LiDAR stage has run). Writes
    JOB/data/records.json              every source, the fields used, the match method, the derived facts
    JOB/out/sections/40_records.md     the "Property records" report section
    JOB/out/detail_extra/records.json  the studio detail block (no ids, addresses or coordinates)
Matching: the parcel containing the geocoded point, then intersection with that parcel, then a parcel key,
then the address string; a fallback is flagged. Explicit outFields only; names / postal addresses of people
are never requested, and the written files are privacy-scanned (a hit deletes them: exit 3).
Exit codes: 0 done (unreachable sources are written as such), 1 bad input / profile, 3 privacy hit.
--offline (or PROPMODEL_OFFLINE=1): cache only (PROPMODEL_CACHE); a miss is "source not reachable".
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from propmodel import records as R  # noqa: E402
from propmodel.sources import Http  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("job")
    ap.add_argument("--profile", required=True, help="region profile name (references/regions/<name>.json) or path")
    ap.add_argument("--offline", action="store_true", help="cache only (PROPMODEL_OFFLINE=1)")
    ap.add_argument("--refresh", action="store_true", help="ignore cached replies (re-query every source)")
    ap.add_argument("--street", help="street line override for the address fallback, e.g. '1 TEST AVE'")
    a = ap.parse_args(argv)
    if a.offline:
        os.environ["PROPMODEL_OFFLINE"] = "1"
        from propmodel import ept
        ept.install_offline_guard()
    try:
        rec, paths = R.run(os.path.abspath(a.job), a.profile, http=Http(refresh=a.refresh), street=a.street)
    except R.PrivacyError as e:
        print(f"G1p STOP: {e} - files deleted")
        return 3
    except (FileNotFoundError, ValueError) as e:
        print(f"records: {e}")
        return 1
    d = rec["derived"]
    print(f"records: county {rec.get('county') or '?'}; {len(rec['permits'])} permit(s); {len(rec['sales'])} sale(s)")
    print(f"  roof age: {d.get('roof_age_text')}")
    print(f"  year built {d.get('year_built') or '?'}; storeys {d.get('storeys') or '?'}; "
          f"assessed total {((d.get('assessed') or {}).get('total')) or '?'}")
    if d["changes_after_lidar"]["flag"]:
        print("  G1: " + "; ".join(d["changes_after_lidar"]["reasons"]))
    for s in rec["sources"]:
        if s.get("status") != "ok":
            print(f"  {s.get('status')}: {s.get('message')}")
        elif s.get("fallback"):
            print(f"  fallback: {s['label']} matched by {s['method']}")
    for p in paths.values():
        print("  wrote", os.path.relpath(p, os.path.abspath(a.job)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
