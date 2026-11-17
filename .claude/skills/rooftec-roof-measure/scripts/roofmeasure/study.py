"""Accuracy study helper (plan experiment 027): compare a measured roof.json with ground truth.

Truth file (JSON, any subset of the keys):
    {"source": "tape and pitch gauge, 2026-11-20",
     "slopedAreaFt2": 3300, "predominantPitchIn12": 6,
     "edgesFt": {"ridge": 79, "hip": 0, "valley": 29, "eave": 135, "rake": 190}}

Targets are the plan's: area within 2 %, pitch within 1 degree, each line total within 3 % or 2 ft.
"""
import math

AREA_PCT = 2.0
PITCH_DEG = 1.0
EDGE_PCT = 3.0
EDGE_FT = 2.0


def compare(doc, truth):
    """Return (rows, passed). Each row: dict(what, measured, truth, diff, limit, ok)."""
    rows = []
    s = doc["summary"]
    if truth.get("slopedAreaFt2"):
        t = float(truth["slopedAreaFt2"])
        d = 100 * (s["slopedAreaFt2"] - t) / t
        rows.append({"what": "Sloped area (sq ft)", "measured": s["slopedAreaFt2"], "truth": t, "diff": "%+.1f%%" % d,
                     "limit": "2%", "ok": abs(d) <= AREA_PCT})
    if truth.get("predominantPitchIn12") is not None:
        t = float(truth["predominantPitchIn12"])
        d = s["predominantPitchDeg"] - math.degrees(math.atan(t / 12))
        rows.append({"what": "Predominant pitch (x/12)", "measured": s["predominantPitchIn12"], "truth": t,
                     "diff": "%+.1f deg" % d, "limit": "1 deg", "ok": abs(d) <= PITCH_DEG})
    for k, t in (truth.get("edgesFt") or {}).items():
        if k not in s["edgeTotals"]:
            raise ValueError("unknown line type %r in truth file" % k)
        m = s["edgeTotals"][k]["lengthFt"]
        d = m - float(t)
        lim = max(EDGE_FT, EDGE_PCT / 100 * float(t))
        rows.append({"what": "%s (ft)" % k.capitalize(), "measured": m, "truth": float(t), "diff": "%+.1f ft" % d,
                     "limit": "%.1f ft" % lim, "ok": abs(d) <= lim})
    return rows, bool(rows) and all(r["ok"] for r in rows)


def markdown(doc, truth, rows, passed):
    L = ["# Accuracy check: footprint %s" % doc.get("footprintId"), "",
         "Truth source: %s. Result: **%s**." % (truth.get("source", "not stated"), "PASS" if passed else "FAIL"), "",
         "| What | Measured | Truth | Difference | Limit | OK |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s |" % (r["what"], r["measured"], r["truth"], r["diff"], r["limit"], "yes" if r["ok"] else "NO"))
    L.append("")
    return "\n".join(L)
