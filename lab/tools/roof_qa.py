"""Roof layer QA gate: build (or open) the roof layer stack, then check the finished roof with the blender-suite skill's qa_check.

    $LAB_BPY_PYTHON lab/tools/roof_qa.py                       (cloud, pip bpy)
    blender -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py      (local, real Blender)
    ... -- --blend out/house.blend --json out/qa/roof-qa.json --save out/qa/roof.blend
    ... -- --layers '{"category": "metal", "panel": "proRib"}'      (layers cfg for roof_core, passed to `ensure`)
    ... -- --expect report.json     (or inline JSON: the house's measurement report, compared within tol_pct, default 2)
        {"source": "EagleView report 2026-11-01", "tol_pct": 2, "squares": 27.43, "planes": 6,
         "lengths_ft": {"eave": 191.27, "rake": 29.72, "ridge": 50.69, "hip": 107.28, "valley": 39.86}}

Without --blend it builds the ranch demo house. With --blend it checks the layers already in that file
(run roof-blender.mjs layers on a real RoofTec house first). Pass = "roof QA passed"; prints one RT_QA {json} line.
Any qa_check error not listed in ACCEPTED fails the run: fix the geometry, or add it to ACCEPTED with the reason.
qa_check runs with no triangle limit; a result without "complete": true fails. With --expect, squares and lengths
must be within tol_pct and planes equal, read from the scene's rt_measure (stored by roof_core layers).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FT = 0.3048
sys.path.insert(0, os.path.join(ROOT, ".claude", "skills", "blender-suite", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "roof-blender", "scripts"))

import bpy  # noqa: E402
import qa_check  # noqa: E402
import roof_core as rc  # noqa: E402

# (pattern, most tri pairs allowed, why it is fine)
ACCEPTED = [
    (r"^z-fighting: RT_layer_iceWater \((\d+) overlapping", 4,
     "two valley membranes lap where the valleys meet at a dormer or garage apex (as installed); hidden by the underlayment"),
]
OLD_ROOF = ("oldShingles", "oldFelt")  # torn off before anything new goes on: never on screen with the new layers


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"blend": None, "json": None, "save": None, "profile": "render", "layers": "{}", "expect": None}
    for i, k in enumerate(a):
        if k.startswith("--") and k[2:] in out and i + 1 < len(a):
            out[k[2:]] = a[i + 1]
    return out


def compare(exp, got):
    """Rows of measured vs report numbers. Planes must be equal; squares and lengths within tol_pct."""
    tol = float(exp.get("tol_pct", 2))
    rows = []

    def row(what, want, have, exact=False):
        r = {"what": what, "expect": want, "got": have, "err_pct": None, "pass": False}
        if have is None:
            r["error"] = "not measured"
        elif want == 0:
            r["pass"] = abs(have) < 0.01
        else:
            r["err_pct"] = round(abs(have - want) / abs(want) * 100, 2)
            r["pass"] = have == want if exact else r["err_pct"] <= tol
        rows.append(r)

    L = got.get("lengths_m", {})
    for k, v in exp.items():
        if k == "planes":
            row("planes", v, got.get("planes"), exact=True)
        elif k == "squares":
            row("squares", v, got.get("squares"))
        elif k in ("lengths_ft", "lengths_m"):
            ft = k == "lengths_ft"
            for kind, want in v.items():
                have = L.get(kind)
                row(f"{kind} {'ft' if ft else 'm'}", want, None if have is None else round(have / FT, 2) if ft else have)
        elif k not in ("source", "tol_pct"):
            rows.append({"what": k, "expect": v, "got": None, "pass": False,
                         "error": "unknown key: use planes, squares, lengths_ft, lengths_m"})
    if not rows:
        rows.append({"what": "nothing", "pass": False, "error": "no numbers to compare"})
    return {"pass": all(r["pass"] for r in rows), "tol_pct": tol, "source": exp.get("source", "not given"), "rows": rows}


def main():
    cfg = args()
    layers_cfg = json.loads(cfg["layers"])
    built = None
    if cfg["blend"]:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(cfg["blend"]))
        if not any(o.get("rt_layer") for o in bpy.data.objects):
            built = rc.run({**layers_cfg, "cmd": "layers"})
    else:
        built = rc.run({**layers_cfg, "cmd": "ensure", "fresh": True}).get("layers")
    if cfg["save"]:
        os.makedirs(os.path.dirname(os.path.abspath(cfg["save"])), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(cfg["save"]))
    layers = [o.name for o in bpy.data.objects if o.get("rt_layer") and o["rt_layer"] not in OLD_ROOF and o.type == "MESH"]
    res = qa_check.run(objects=layers, profile=cfg["profile"], max_tris=0)

    unexpected, accepted = [], []
    for e in res["errors"]:
        for pat, most, why in ACCEPTED:
            m = re.match(pat, e)
            if m and int(m.group(1)) <= most:
                accepted.append(f"{e}: {why}")
                break
        else:
            unexpected.append(e)
    if res.get("complete") is not True:
        unexpected.append(f"qa_check incomplete (complete: {res.get('complete')}, skipped: {res.get('skipped')}): not a pass")
    measure = None
    if cfg["expect"]:
        src = cfg["expect"].strip()
        if not src.startswith("{"):
            with open(src, encoding="utf-8") as f:
                src = f.read()
        stored = bpy.context.scene.get("rt_measure")
        got = json.loads(stored) if stored else built if isinstance(built, dict) else None
        if got is None:
            measure = {"pass": False, "rows": [], "error": "no rt_measure in the file: run the layers step again to record measurements"}
        else:
            measure = compare(json.loads(src), got)
    noise = ("UV overlap", "duplicate verts", "zero-area UV faces", "not resting on ground plane", "fully enclosed")
    summary = {
        "pass": not unexpected and (measure is None or measure["pass"]),
        "blender": bpy.app.version_string,
        "cfg": layers_cfg,
        "layers": len(layers),
        "tris": sum(m.get("tris", 0) for m in res["objects"].values()),
        "complete": res.get("complete"),
        "errors": unexpected,
        "accepted": accepted,
        "warnings": [w for w in res["warnings"] if not any(n in w for n in noise)],
        "expected_warnings": sum(1 for w in res["warnings"] if any(n in w for n in noise)),
    }
    if measure is not None:
        summary["measure"] = measure
    if cfg["json"]:
        os.makedirs(os.path.dirname(os.path.abspath(cfg["json"])), exist_ok=True)
        with open(cfg["json"], "w") as f:
            json.dump({"summary": summary, "qa_check": res}, f, indent=1)
    print("RT_QA " + json.dumps(summary))
    for e in unexpected:
        print("FAIL -", e)
    if measure is not None:
        if measure.get("error"):
            print("FAIL - measure:", measure["error"])
        for r in measure["rows"]:
            if not r["pass"]:
                why = r.get("error") or f"{r['err_pct']} % > {measure['tol_pct']} %"
                print(f"FAIL - measure {r['what']}: expected {r.get('expect')}, got {r.get('got')} ({why})")
    for a in accepted:
        print("accepted -", a)
    for w in summary["warnings"]:
        print("warn -", w)
    if not summary["pass"]:
        raise SystemExit(1)
    print("roof QA passed")


main()
