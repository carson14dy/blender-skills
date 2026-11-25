#!/usr/bin/env python3
"""roof_diagrams — EagleView-style roof report pages from the fitted model (CPU, matplotlib, no AI).

    python3 roof_diagrams.py JOB [--out JOB/out/diagrams] [--dpi 300] [--units ft|m] [--waste PCT]
                             [--lidar-date TEXT] [--title TEXT] [--no-section]

Reads JOB/model.json and JOB/report.json (as written by pm.py fit) and JOB/data/lidar.json (flight year / date,
optional). Writes into --out:
    length.svg / length.png     every edge labelled with its true length, coloured by kind, legend + per-kind totals
    pitch.svg  / pitch.png      each facet x/12 with an arrow down the slope
    area.svg   / area.png       each facet's ft2 and the total in squares
    summary.svg / summary.png   totals, predominant pitch, facet count, waste table (suggested row = report.py rule),
                                cap / starter / drip edge / valley / step flashing / headwall / ice-barrier lengths,
                                walkable / steep flags, north arrow, LiDAR flight line
    diagrams.json               every total drawn (keys as report.json "imperial"), labels, checks
and JOB/out/sections/20_diagrams.md (takeoff tables for the studio report / PDF; --no-section skips it).
Pages are US letter; PNG at --dpi (300 = print), SVG with text kept as text.

Exit codes: 0 ok; 1 input error; 2 a drawn total differs from report.json (lengths > 0.1 ft, areas > 1 ft2,
squares > 0.01) - the model and the report are out of step: refit / rebuild, never hand-edit; 3 a label overlap
could not be resolved by the leader-line fallback (the page is still written; the label is drawn in red).
No address, owner or parcel text is ever drawn: --title sets a neutral page subtitle (default none).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from propmodel import diagrams as D  # noqa: E402

PAGES = (("length", D.draw_length_page), ("pitch", D.draw_pitch_page), ("area", D.draw_area_page),
         ("summary", D.draw_summary_page))


def jload(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def sha(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def lidar_line(job, override=None):
    li = jload(os.path.join(job, "data", "lidar.json"), {}) or {}
    flown = override or li.get("flight_date") or li.get("acquired") or li.get("year")
    ds = li.get("dataset")
    if flown:
        line = f"Measured from public LiDAR{f' ({ds})' if ds else ''}, flown {flown}."
    else:
        line = "Measured from public LiDAR; flight date not recorded in data/lidar.json."
    return line, {"dataset": ds, "flown": flown}


def section_md(ctx, tot, bk, wt, acc, ac, ps):
    L = ["## Roof diagrams: takeoff", "",
         f"{ctx['lidar_line']} Drawn from the fitted model (model.json); every total below equals report.json "
         "(lengths to 0.1 ft, areas to 1 ft²). Plan views are north up.", "",
         "| Edge | Count | Length (ft) |", "|---|---|---|"]
    for k in D.KINDS:
        if k in bk:
            L.append(f"| {D.KIND_LABEL[k]} | {bk[k]['count']} | {bk[k]['length_ft']:.1f} |")
    L += ["", f"Total roof area **{tot['roof_area_sqft']:,.0f} ft²** = **{tot['roof_squares']:.2f} squares** on "
              f"{tot['facets']} facets; predominant pitch {ps['predominant']} ({100 * ps['predominant_share']:.0f} %).",
          "", "| Waste | Area (ft²) | Squares | Bundles (3/sq) | |", "|---|---|---|---|---|"]
    for r in wt["rows"]:
        note = ("**suggested**" if r["suggested"] else "") + (" chosen" if r.get("chosen") else "")
        cells = [f"{r['pct']} %", f"{r['area_sqft']:,.0f}", f"{r['squares']:.2f}", str(r["bundles"])]
        if r["suggested"]:
            cells = [f"**{c}**" for c in cells]
        L.append("| " + " | ".join(cells + [note.strip()]) + " |")
    L += ["", f"_Suggested waste {wt['suggested_pct']} % from {wt['hips_valleys']} hips + valleys (report.py rule)._", "",
          "| Accessory | Length (ft) | From |", "|---|---|---|"]
    for k, lab, src in D.ACCESSORY_ROWS:
        L.append(f"| {lab} | {acc[k]:.1f} | {src} |")
    sm = ac["summary"]
    L += ["", f"Access ({ac['rule']}): " + "; ".join(
        f"{c} {sm[c]['facets']} facets ({100 * sm[c]['share']:.0f} % of area)" for c in ("walkable", "steep", "very steep"))
        + "."]
    if ac.get("highest_eave_ft") is not None:
        L.append(f"Highest eave {ac['highest_eave_ft']:.1f} ft {ac['highest_eave_ref']}.")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--out")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--units", choices=("ft", "m"), default="ft")
    ap.add_argument("--waste", type=float, help="the waste %% chosen for this job (marked 'chosen'; job.json waste)")
    ap.add_argument("--lidar-date", help="flight date text when data/lidar.json has none")
    ap.add_argument("--title", default="", help="neutral subtitle (never an address)")
    ap.add_argument("--no-section", action="store_true")
    a = ap.parse_args(argv)

    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams.update({"svg.fonttype": "none", "svg.hashsalt": "roof-diagrams",
                                "font.family": "sans-serif",
                                "hatch.linewidth": 0.5, "hatch.color": "#a9a9a4"})
    import matplotlib.pyplot as plt

    job = os.path.abspath(a.job)
    out = os.path.abspath(a.out or os.path.join(job, "out", "diagrams"))
    mp, rp = os.path.join(job, "model.json"), os.path.join(job, "report.json")
    model, report = jload(mp), jload(rp)
    if not model or not model.get("facets"):
        print(f"roof_diagrams: no facets in {mp}", file=sys.stderr)
        return 1
    if report is None:
        print(f"roof_diagrams: {rp} missing or unreadable", file=sys.stderr)
        return 1
    cfg = jload(os.path.join(job, "job.json"), {}) or {}
    chosen = a.waste if a.waste is not None else cfg.get("waste")
    chosen = None if chosen is None else int(round(float(chosen)))

    facets = D.facet_rows(model)
    tot = D.totals(model)
    diffs = D.check_totals(tot, report, facets)
    sug, nhv = D.suggested_waste(model)
    wt = {"suggested_pct": sug, "hips_valleys": nhv, "chosen_pct": chosen,
          "rows": D.waste_table(tot["roof_area_sqft"], sug, chosen)}
    acc = D.accessories(tot)
    ac = D.access_summary(facets, model, report)
    ps = D.pitch_summary(facets)
    line, li = lidar_line(job, a.lidar_date)
    gen = dt.date.today().isoformat()
    sub = " · ".join(x for x in (a.title.strip(), f"generated {gen}", line) if x)
    ctx = {"subtitle": sub, "lidar_line": line, "totals": tot, "sigma": D.sigma_imperial(report), "pitch": ps,
           "accessories": acc, "access": ac, "waste": wt,
           "footer": ["Drawn by roof_diagrams.py from the fitted model (model.json, report.json): measured geometry, "
                      "no AI, no photos. Plan view, north up.",
                      "The model and report are the source of truth; drawings are to scale but read numbers from the "
                      "labels, not with a ruler."]}

    os.makedirs(out, exist_ok=True)
    pages, labels, unresolved = [], {}, []
    for name, fn in PAGES:
        fig, recs = fn(model, report, ctx, a.dpi, a.units)
        svg, png = os.path.join(out, f"{name}.svg"), os.path.join(out, f"{name}.png")
        fig.savefig(svg, format="svg", metadata={"Date": None})
        fig.savefig(png, format="png", dpi=a.dpi, metadata={"Software": "roof_diagrams.py"})
        plt.close(fig)
        labels[name] = recs
        unresolved += [f"{name}:{r['id']}" for r in recs if not r["resolved"]]
        pages.append({"name": name, "svg": os.path.basename(svg), "png": os.path.basename(png),
                      "labels": len(recs), "leaders": sum(1 for r in recs if r["leader"])})

    bk = D.by_kind(model)
    edge_recs = {r["index"]: r for r in labels["length"]}
    doc = {
        "schema": "roof_diagrams/1", "generated": dt.datetime.now().isoformat(timespec="seconds"), "units": a.units,
        "dpi": a.dpi, "source": {"model": "model.json", "report": "report.json", "model_sha256": sha(mp),
                                 "report_sha256": sha(rp)},
        "lidar": {**li, "line": line},
        "totals": {k: v for k, v in tot.items() if not (k == "transition_ft" and v == 0)},
        "sigma": ctx["sigma"],
        "by_kind": bk,
        "accessories_ft": acc,
        "waste": wt,
        "pitch": ps,
        "access": ac,
        "facets": [{"id": f["id"], "pitch_x12": f["pitch_x12"], "area_sqft": f["area_sqft"], "area_m2": f["area_m2"],
                    "hidden": f["hidden"]} for f in facets],
        "edges": [{"index": e["index"], "kind": e["kind"], "length_ft": e["length_ft"], "length_m": e["length_m"],
                   "label": edge_recs.get(e["index"], {}).get("text"),
                   "leader": edge_recs.get(e["index"], {}).get("leader"),
                   "resolved": edge_recs.get(e["index"], {}).get("resolved")} for e in D.edge_rows(model)],
        "labels": {"edge": len(labels["length"]), "facet_pitch": len(labels["pitch"]), "facet_area": len(labels["area"]),
                   "leaders": sum(p["leaders"] for p in pages), "unresolved": unresolved},
        "pages": pages,
        "check": {"ok": not diffs and not unresolved, "tolerance": D.TOL,
                  "diffs": [{"key": k, "drawn": v, "report": r} for k, v, r in diffs]},
    }
    with open(os.path.join(out, "diagrams.json"), "w") as f:
        json.dump(doc, f, indent=1)
    if not a.no_section:
        sd = os.path.join(job, "out", "sections")
        os.makedirs(sd, exist_ok=True)
        with open(os.path.join(sd, "20_diagrams.md"), "w") as f:
            f.write(section_md(ctx, tot, bk, wt, acc, ac, ps))
    print(json.dumps({"out": out, "pages": [p["name"] for p in pages], "roof_area_sqft": round(tot["roof_area_sqft"], 1),
                      "roof_squares": round(tot["roof_squares"], 2), "leaders": doc["labels"]["leaders"],
                      "unresolved": unresolved, "diffs": doc["check"]["diffs"]}))
    if diffs:
        print("roof_diagrams: drawn totals differ from report.json: "
              + "; ".join(f"{k} {v:.2f} vs {r:.2f}" for k, v, r in diffs), file=sys.stderr)
        return 2
    if unresolved:
        print("roof_diagrams: label overlap not resolved: " + ", ".join(unresolved), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
