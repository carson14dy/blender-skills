#!/usr/bin/env python3
"""Minimal details.json for a DEMO-tier house (no photos): trim, gutters, soffits, a foundation band, and colours.

    python3 details_stub.py JOB [--out JOB/details.json] [--force] [--garage WALL:U:WIDTH]

The demo tier has no photos, so nothing here is measured except the roof colour, which is sampled from the
orthophoto at the facet centroids (``data/ortho.png``; or ``data/hazards.json`` ``roof_colour`` when the hazards
stage wrote one) and labelled an estimate. Doors and windows are not drawn; ``--garage M:-u:4.9`` adds one garage door
on that wall (u = distance along the wall from its start, m), labelled "assumed (no photo)". Every assumed item says
so in its label, and ``caveats`` lists what the model does not show. add_details.py then adds the presentation
geometry in its own collection, so no measured number changes.
"""
import argparse
import json
import os
import sys

import numpy as np

DEFAULTS = {"siding": [214, 210, 198], "trim": [236, 234, 228], "roof": [92, 90, 88], "concrete": [200, 196, 188],
            "foundation": [170, 166, 158]}


def ortho_colour(job, model):
    """Median sRGB of the orthophoto in a 1 m disc round each facet centroid (area-weighted), or None."""
    png, meta_p = os.path.join(job, "data/ortho.png"), os.path.join(job, "data/ortho.png.json")
    if not (os.path.exists(png) and os.path.exists(meta_p)):
        return None
    from PIL import Image
    meta = json.load(open(meta_p))
    x0, y0, x1, y1 = meta["bounds_local"]
    img = np.asarray(Image.open(png).convert("RGB"), float)
    H, W = img.shape[:2]
    cols, wts = [], []
    for f in model.get("facets", []):
        if f.get("hidden_from_above"):
            continue
        pts = np.array([c for q in f["polygons"] for c in q["outer"]])[:, :2]
        cx, cy = pts.mean(axis=0)
        u = (cx - x0) / (x1 - x0) * W
        v = (y1 - cy) / (y1 - y0) * H
        r = max(2, int(1.0 / ((x1 - x0) / W)))
        ys, xs = np.mgrid[max(0, int(v) - r):min(H, int(v) + r), max(0, int(u) - r):min(W, int(u) + r)]
        if not ys.size:
            continue
        cols.append(np.median(img[ys.ravel(), xs.ravel()], axis=0))
        wts.append(f.get("area_m2", 1.0))
    if not cols:
        return None
    c = np.average(np.array(cols), axis=0, weights=np.array(wts))
    return [int(round(v)) for v in c]


def hazards_colour(job):
    hz = os.path.join(job, "data/hazards.json")
    if not os.path.exists(hz):
        return None
    d = json.load(open(hz))
    rc = d.get("roof_colour") or d.get("roof_color") or {}
    for k in ("rgb", "srgb", "color", "colour"):
        if isinstance(rc.get(k), list) and len(rc[k]) >= 3:
            return [int(round(float(v))) for v in rc[k][:3]]
    return None


def stub(job, garage=None):
    model = json.load(open(os.path.join(job, "model.json")))
    rc, src = hazards_colour(job), "hazards.json roof colour (from the aerial)"
    if rc is None:
        rc, src = ortho_colour(job, model), "median orthophoto colour at the facet centroids"
    if rc is None:
        rc, src = DEFAULTS["roof"], "default grey (no orthophoto)"
    d = {
        "model_json": os.path.join(job, "model.json"),
        "note": "demo tier (no photos): presentation detail only; every number in the report comes from the roof model",
        "siding": {"style": "smooth", "color": DEFAULTS["siding"], "label": "siding colour and style assumed (no photo)"},
        "roof": {"exposure": 0.1429, "color": rc, "label": f"asphalt-shingle look; colour = {src}, an estimate"},
        "trim_color": DEFAULTS["trim"], "concrete_color": DEFAULTS["concrete"],
        "fascia_height": 0.2, "gutters": True, "soffits": True,
        "foundation": {"default_reveal": 0.25, "color": DEFAULTS["foundation"]},
        "openings": [],
        "caveats": ["doors and windows are not drawn (no photos in the demo tier)",
                    "wall colours, trim and gutters are assumed",
                    "wall lines follow the roof outline minus the overhang (see the confidence statement)"],
    }
    if garage:
        wall, u, width = garage.split(":")[0] + ":" + garage.split(":")[1], float(garage.split(":")[2]), float(garage.split(":")[3])
        d["openings"].append({"wall": wall, "u": u, "sill_z": 0.0, "width": width, "height": 2.13, "kind": "garage",
                              "label": "garage door, assumed (no photo): position from the driveway in the city paving layer"})
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--garage", help="WING:SIDE:U:WIDTH, e.g. M:-u:2.0:4.9 (assumed garage door)")
    a = ap.parse_args()
    out = a.out or os.path.join(a.job, "details.json")
    if os.path.exists(out) and not a.force:
        sys.exit(f"{out} exists (--force to overwrite)")
    d = stub(a.job, a.garage)
    with open(out, "w") as f:
        json.dump(d, f, indent=1)
    print(f"wrote {out} (roof colour {d['roof']['color']}: {d['roof']['label']})")


if __name__ == "__main__":
    main()
