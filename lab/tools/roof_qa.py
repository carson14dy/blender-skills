"""Roof layer QA gate: build (or open) the roof layer stack, then check the finished roof with blender-master's qa_check.

    $LAB_BPY_PYTHON lab/tools/roof_qa.py                       (cloud, pip bpy)
    blender -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py      (local, real Blender)
    ... -- --blend out/house.blend --json out/qa/roof-qa.json --save out/qa/roof.blend

Without --blend it builds the ranch demo house. With --blend it checks the layers already in that file
(run roof-blender.mjs layers on a real RoofTec house first). Pass = "roof QA passed"; prints one RT_QA {json} line.
Any qa_check error not listed in ACCEPTED fails the run: fix the geometry, or add it to ACCEPTED with the reason.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "vendor", "blender-master"))
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
    out = {"blend": None, "json": None, "save": None, "profile": "render"}
    for i, k in enumerate(a):
        if k.startswith("--") and k[2:] in out and i + 1 < len(a):
            out[k[2:]] = a[i + 1]
    return out


def main():
    cfg = args()
    if cfg["blend"]:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(cfg["blend"]))
        if not any(o.get("rt_layer") for o in bpy.data.objects):
            rc.run({"cmd": "layers"})
    else:
        rc.run({"cmd": "ensure", "fresh": True})
    if cfg["save"]:
        os.makedirs(os.path.dirname(os.path.abspath(cfg["save"])), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(cfg["save"]))
    layers = [o.name for o in bpy.data.objects if o.get("rt_layer") and o["rt_layer"] not in OLD_ROOF and o.type == "MESH"]
    res = qa_check.run(objects=layers, profile=cfg["profile"])

    unexpected, accepted = [], []
    for e in res["errors"]:
        for pat, most, why in ACCEPTED:
            m = re.match(pat, e)
            if m and int(m.group(1)) <= most:
                accepted.append(f"{e}: {why}")
                break
        else:
            unexpected.append(e)
    noise = ("UV overlap", "duplicate verts", "zero-area UV faces", "not resting on ground plane", "fully enclosed")
    summary = {
        "pass": not unexpected,
        "blender": bpy.app.version_string,
        "layers": len(layers),
        "tris": sum(m.get("tris", 0) for m in res["objects"].values()),
        "errors": unexpected,
        "accepted": accepted,
        "warnings": [w for w in res["warnings"] if not any(n in w for n in noise)],
        "expected_warnings": sum(1 for w in res["warnings"] if any(n in w for n in noise)),
    }
    if cfg["json"]:
        os.makedirs(os.path.dirname(os.path.abspath(cfg["json"])), exist_ok=True)
        with open(cfg["json"], "w") as f:
            json.dump({"summary": summary, "qa_check": res}, f, indent=1)
    print("RT_QA " + json.dumps(summary))
    for e in unexpected:
        print("FAIL -", e)
    for a in accepted:
        print("accepted -", a)
    for w in summary["warnings"]:
        print("warn -", w)
    if unexpected:
        raise SystemExit(1)
    print("roof QA passed")


main()
