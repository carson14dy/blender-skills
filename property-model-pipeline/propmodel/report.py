"""Measurement report (Markdown + JSON) in roofing/siding trade units with 1-sigma."""
from __future__ import annotations

import datetime as dt
import json
import math

from . import units as U
from .roofgeom import plane_azimuth, _polys

WASTE_BY_COMPLEXITY = [(0, 10), (2, 12), (6, 15), (12, 17), (20, 20)]  # (hip+valley count, waste %)
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(b):
    return COMPASS[int(((b + 22.5) % 360) // 45)] if b is not None else "flat"


def _pm(v, s, fmt="{:.1f}"):
    if s is None or s == 0 or not math.isfinite(s):
        return fmt.format(v)
    return f"{fmt.format(v)} ± {fmt.format(s)}"


def suggested_waste(model):
    n = sum(1 for e in model.edges if e.kind in ("hip", "valley"))
    w = 10
    for k, pct in WASTE_BY_COMPLEXITY:
        if n >= k:
            w = pct
    return w, n


def openings_by_facade(openings, zone="siding"):
    """spec 'openings': [{"facade": "N", "width": "36in", "height": "80in", "count": 1, "label": "door"}], or
    entries with "area_m2" and "zone" ("siding" | "foundation", default siding) as pm.py reads them from
    details.json. Returns {facade: m2} for the openings in ``zone``."""
    from .units import parse_length
    out = {}
    for o in openings or []:
        if o.get("zone", "siding") != zone:
            continue
        if "area_m2" in o:
            a = float(o["area_m2"])
        else:
            a = parse_length(o["width"]) * parse_length(o["height"]) * float(o.get("count", 1))
        out[o["facade"].upper()] = out.get(o["facade"].upper(), 0.0) + a
    return out


def _facade_table(rows_m2, op, total_sigma=0.0):
    """Markdown rows: facade | gross | openings | net | net m2, plus the total row."""
    lines = []
    for k in COMPASS:
        if rows_m2.get(k, 0) > 0.05 or op.get(k, 0) > 0.05:
            g, o = rows_m2.get(k, 0.0), op.get(k, 0.0)
            lines.append(f"| {k} | {U.sqft(g):.0f} | {U.sqft(o):.0f} | {U.sqft(g - o):.0f} | {g - o:.1f} |")
    W, O = sum(rows_m2.values()), sum(op.values())
    lines.append(f"| **Total** | **{_pm(U.sqft(W), U.sqft(total_sigma), '{:.0f}')}** | {U.sqft(O):.0f} | **{U.sqft(W - O):.0f}** | {W - O:.1f} |")
    return lines


def build_report(model, fit=None, site=None, title="Property measurement report", openings=None, extra_walls=None):
    """``extra_walls``: [{"name", "facade", "area_m2", "material", "openings_m2"}] walls modelled outside the
    wings (details.json extra_walls, e.g. a concrete garage front under a deck): concrete ones are listed with
    the foundation, others with the siding."""
    meas = model.measurements()
    sig = (fit or {}).get("measurement_sigma", {})
    lines = [f"# {title}", ""]
    if site:
        lines += [f"- **Site**: {site.get('address', '')} ({site['origin']['lat']:.6f}, {site['origin']['lon']:.6f})"]
    lines += [f"- **Generated**: {dt.datetime.now().isoformat(timespec='minutes')}",
              "- **Method**: parametric model fitted to all evidence by robust weighted least squares; "
              "± values are 1-sigma (68 %) uncertainties propagated from the evidence.", ""]

    A, As = meas["roof.area"], sig.get("roof.area", 0)
    waste, nhv = suggested_waste(model)
    lines += ["## Roof summary", "",
              "| Quantity | Value | Metric |", "|---|---|---|",
              f"| Total roof area | {_pm(U.sqft(A), U.sqft(As), '{:.0f}')} ft² ({_pm(U.squares(A), U.squares(As), '{:.2f}')} sq) | {_pm(A, As)} m² |",
              f"| Plan (footprint-projected) roof area | {U.sqft(meas['roof.area_plan']):.0f} ft² | {meas['roof.area_plan']:.1f} m² |",
              f"| Facets | {len(model.facets)} | |",
              f"| Predominant pitch (area-weighted) | {U.fmt_pitch(meas.get('roof.pitch_weighted', 0))} | {U.slope_to_deg(meas.get('roof.pitch_weighted', 0)):.1f}° |",
              f"| Suggested waste | {waste} % ({nhv} hips+valleys) → order {U.squares(A) * (1 + waste / 100):.2f} sq | |",
              *([f"| Max height above grade, low side (grade {meas['grade.low']:+.2f} m) | "
                 f"{_pm(U.ft(meas['building.height_low_side']), U.ft(sig.get('building.height', 0)))} ft | {meas['building.height_low_side']:.2f} m |",
                 f"| Max height above grade, high side (grade {meas['grade.high']:+.2f} m) | "
                 f"{_pm(U.ft(meas['building.height_high_side']), U.ft(sig.get('building.height', 0)))} ft | {meas['building.height_high_side']:.2f} m |"]
                if "building.height_low_side" in meas else
                [f"| Max height above grade | {_pm(U.ft(meas['building.height']), U.ft(sig.get('building.height', 0)))} ft | {meas['building.height']:.2f} m |"]),
              ""]
    lines += ["## Lengths", "", "| Edge | Length (ft) | Length (m) |", "|---|---|---|"]
    for k in ("ridge", "hip", "valley", "rake", "eave", "transition", "headwall", "sidewall"):
        v = meas.get(f"edge.{k}", 0)
        if v > 0:
            s = sig.get(f"edge.{k}", 0)
            lines.append(f"| {k.capitalize()} | {_pm(U.ft(v), U.ft(s))} | {_pm(v, s, '{:.2f}')} |")
    drip = meas.get("edge.eave", 0) + meas.get("edge.rake", 0)
    cap = meas.get("edge.ridge", 0) + meas.get("edge.hip", 0)
    lines += [f"| Drip edge (eaves+rakes) | {U.ft(drip):.1f} | {drip:.2f} |",
              f"| Ridge cap (ridges+hips) | {U.ft(cap):.1f} | {cap:.2f} |",
              f"| Step flashing (sidewalls) / headwall | {U.ft(meas.get('edge.sidewall', 0)):.1f} / {U.ft(meas.get('edge.headwall', 0)):.1f} | |", ""]

    lines += ["## Facets", "", "| Facet | Pitch | Faces | Area (ft²) | Area (m²) | Note |", "|---|---|---|---|---|---|"]
    for f in model.facets:
        az = plane_azimuth(f.plane)
        note = "partly under upper overhang" if f.hidden_from_above else ""
        lines.append(f"| {f.id} | {U.fmt_pitch(f.slope)} | {compass(az)} | {U.sqft(f.area_true):.0f} | {f.area_true:.1f} | {note} |")
    by_pitch = {}
    for f in model.facets:
        key = round(f.slope * 12 * 2) / 2
        by_pitch[key] = by_pitch.get(key, 0) + f.area_true
    lines += ["", "| Pitch | Area (ft²) | Share |", "|---|---|---|"]
    for k in sorted(by_pitch):
        lines.append(f"| {k:g}/12 | {U.sqft(by_pitch[k]):.0f} | {100 * by_pitch[k] / max(A, 1e-9):.0f} % |")

    op = openings_by_facade(openings)
    extra_walls = extra_walls or []
    lines += ["", "## Walls (siding)", "", "| Facade | Gross (ft²) | Openings (ft²) | Net (ft²) | Net (m²) |", "|---|---|---|---|---|"]
    graded = "wall.area_siding" in meas
    fac = {}
    for w in model.walls:
        fac[compass(w.bearing)] = fac.get(compass(w.bearing), 0) + (w.area_siding if graded else w.area_exposed)
    for e in extra_walls:
        if e.get("material") != "concrete":
            fac[e["facade"]] = fac.get(e["facade"], 0) + e["area_m2"]
            op[e["facade"]] = op.get(e["facade"], 0) + e.get("openings_m2", 0.0)
    lines += _facade_table(fac, op, 0.0 if graded else sig.get("wall.area", 0))
    n_open = len(openings or [])
    if graded:
        lines += ["", f"_Siding = exposed wall above the finished grade and above the foundation / concrete line; "
                      f"{n_open} openings deducted. The concrete band and the wall below grade are listed apart._"]
    lines += ["" if openings else "_No openings listed (spec.json / details.json) → net = gross. Add `openings` to deduct "
                                  "doors/windows/garage doors._"]
    if graded or any(e.get("material") == "concrete" for e in extra_walls):
        cf, co = {}, openings_by_facade(openings, zone="foundation")
        for w in model.walls:
            if w.area_foundation:
                cf[compass(w.bearing)] = cf.get(compass(w.bearing), 0) + w.area_foundation
        names = []
        for e in extra_walls:
            if e.get("material") == "concrete":
                cf[e["facade"]] = cf.get(e["facade"], 0) + e["area_m2"]
                co[e["facade"]] = co.get(e["facade"], 0) + e.get("openings_m2", 0.0)
                names.append(e["name"])
        lines += ["### Foundation / concrete (exposed, not sided)", "",
                  "| Facade | Gross (ft²) | Openings (ft²) | Net (ft²) | Net (m²) |", "|---|---|---|---|---|"]
        lines += _facade_table(cf, co)
        if names:
            lines += ["", f"_Includes the concrete walls modelled outside the wings: {', '.join(names)}._"]
        if graded:
            lines += ["", f"Below grade (buried, not sided): {U.sqft(meas['wall.area_buried']):.0f} ft² "
                          f"({meas['wall.area_buried']:.1f} m²). All wing walls from their bottoms (siding + concrete + "
                          f"buried): {U.sqft(meas['wall.area']):.0f} ft² ({meas['wall.area']:.1f} m²)."]
        lines += [""]
    lines += [f"Footprint (outside of walls): {U.sqft(meas['footprint.area']):.0f} ft² ({meas['footprint.area']:.1f} m²), "
              f"perimeter {U.ft(meas['footprint.perimeter']):.1f} ft.", ""]

    if fit:
        lines += ["## Evidence reconciliation", "",
                  f"Fit: χ² = {fit['chi2']:.1f} on {fit['dof']} dof (variance factor {fit['variance_factor']:.2f}; "
                  "≈1 means the stated source uncertainties are realistic).", "",
                  "| Source | Target | Observed | Model | Residual (σ) | Flag |", "|---|---|---|---|---|---|"]
        for r in fit["residuals"]:
            if "observed" in r:
                lines.append(f"| {r['source']} | {r['target']} | {r['observed']:.3f} | {r['predicted']:.3f} | {r['residual_sigma']:+.1f} | {r['flag']} |")
            else:
                lines.append(f"| {r['source']} | {r['target']} ({r['n']} samples) | | RMS {r['rms_m']:.3f} m | {r['rms_sigma']:.1f} | {r['flag']} |")
        excl = [r for r in fit["residuals"] if r["flag"] == "EXCLUDED"]
        if excl:
            lines += ["", "**Excluded as blunders** (> 4σ from all other evidence; not used in the result): " + "; ".join(
                f"{r['source']} → {r['target']} ({r['residual_sigma']:+.1f}σ)" for r in excl) + "."]
        conflicts = [r for r in fit["residuals"] if r["flag"] == "CONFLICT"]
        if conflicts:
            lines += ["", "**Conflicts to resolve** (|residual| > 3σ): " + "; ".join(
                f"{r['source']} → {r['target']}" for r in conflicts) +
                ". Typical causes: renovation/addition after an old report, footprint traced at the roof edge "
                "instead of the wall, wrong structure, wrong units, or an over-optimistic σ."]
        lines += ["", "## Fitted parameters", "", "| Parameter | Value | 1σ |", "|---|---|---|"]
        for k, p in fit["params"].items():
            fld = k.split(".", 1)[1]
            if "pitch" in fld:
                lines.append(f"| {k} | {U.fmt_pitch(p['value'])} | {p['sigma'] * 12:.2f}/12 |")
            elif fld in ("azimuth",):
                lines.append(f"| {k} | {p['value']:.2f}° | {p['sigma']:.2f}° |")
            else:
                lines.append(f"| {k} | {p['value']:.3f} m ({U.ft(p['value']):.2f} ft) | {p['sigma']:.3f} m |")
    lines += ["", "_Model geometry is exact for the fitted parameters; uncertainty comes only from the evidence._", ""]
    return "\n".join(lines)


def report_json(model, fit=None, site=None):
    meas = model.measurements()
    return {
        "site": site, "measurements_si": meas,
        "measurement_sigma_si": (fit or {}).get("measurement_sigma", {}),
        "imperial": {"roof_area_sqft": U.sqft(meas["roof.area"]), "roof_squares": U.squares(meas["roof.area"]),
                     **{f"{k}_ft": U.ft(meas[f'edge.{k}']) for k in ("ridge", "hip", "valley", "rake", "eave", "headwall", "sidewall")},
                     "wall_area_sqft": U.sqft(meas["wall.area"]),
                     **({"siding_area_sqft": U.sqft(meas["wall.area_siding"]),
                         "foundation_area_wing_walls_sqft": U.sqft(meas["wall.area_foundation"]),
                         "below_grade_wall_sqft": U.sqft(meas["wall.area_buried"])} if "wall.area_siding" in meas else {}),
                     **({"height_low_side_ft": U.ft(meas["building.height_low_side"]),
                         "height_high_side_ft": U.ft(meas["building.height_high_side"])}
                        if "building.height_low_side" in meas else {})},
        "facets": [{"id": f.id, "pitch": f.slope * 12, "azimuth": plane_azimuth(f.plane),
                    "area_m2": f.area_true, "area_sqft": U.sqft(f.area_true), "wings": f.wings} for f in model.facets],
        "fit": {k: v for k, v in (fit or {}).items() if k in ("params", "residuals", "chi2", "dof", "variance_factor")},
    }
