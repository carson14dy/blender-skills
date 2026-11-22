"""Write acceptance.json for 027 BEFORE building: construction_kit.py --plan (every count, size and spacing its
rules imply) plus the brief's own numbers (024/brief.md) and the hand values below, each with its source.

Usage: $LAB_BPY_PYTHON make_acceptance.py      (pip bpy; writes acceptance.json and roof-expect.json here)
"""
import json
import math
import os
import sys

import bpy  # noqa: F401  (construction_kit is a Blender script)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", ".claude", "skills", "blender-suite", "scripts"))
import construction_kit as ck  # noqa: E402

plan = ck.run(plan=os.path.join(HERE, "building.json"))
checks = plan["checks"]
for c in checks:                       # the brief gives these two; the plan marks every rule "standard"
    if c["type"] == "spacing" or c["id"] == "n-window-frame-head":
        c["source"], c["note"] = "given", "brief: " + ("studs at 16 in. on center" if c["type"] == "spacing" else
                                                      "four windows, two on each long side")
k = math.hypot(1, 0.5)                 # 6/12: slope length per unit run
Dp = 5.5 * k                           # 2x6 rafter, plumb depth
zt = lambda x: 100 + (x - 3.5) * 0.5 + Dp   # noqa: E731  top of rafters: 4 in. pad + 96 in. wall, seat on 3.5 in.
run_ = 60 + 6                          # half width + eave overhang, to the fascia face
std, asm = "standard", "assumed"
extra = [
    {"id": "pad", "type": "size", "objects": "Shed_Pad", "expect": [120, 144, 4], "unit": "in", "source": asm,
     "note": "4 in. thick: not in the brief or the rules (IRC R506.1: at least 3-1/2 in.); flush with the framing: design rule"},
    {"id": "siding-lap", "type": "extent", "objects": ["Shed_Siding_*", "Shed_Starter_*"], "axis": "z", "side": "min",
     "expect": 3, "unit": "in", "source": std, "note": "flush slab: the first course laps 1 in. below the bottom plate (4 in.)"},
    {"id": "roof-area", "type": "area", "objects": "Roof", "hidden": True, "facing": "up", "unit": "sq",
     "expect": round(2 * 156 * run_ * k / 14400, 4), "source": std,
     "note": "2 planes x 156 in. (144 + 2 x 6 rake) x 73.79 in. (66 in. run x 1.1180) = 23,022.6 sq in."},
    {"id": "eave-height", "type": "extent", "objects": "Roof", "hidden": True, "axis": "z", "side": "min",
     "expect": round(zt(-6), 4), "unit": "in", "source": std, "note": "rafter top line at the fascia face"},
    {"id": "roof-ridge", "type": "extent", "objects": "Roof", "hidden": True, "axis": "z", "expect": round(zt(60), 4),
     "unit": "in", "source": std, "note": "100 + (60 - 3.5) x 0.5 + 5.5 x 1.1180 = 134.3992 in."},
    {"id": "pitch-deck", "type": "slope", "objects": "RT_layer_deck", "expect": "6/12", "source": std,
     "note": "pitch.json: 6/12 (design rule approved by the user)"},
    {"id": "roof-layers", "type": "count", "objects": "RT_layer_*", "expect": 7, "source": std,
     "note": "deck, drip edge, underlayment, starter, nails, covering, ridge cap: no ice barrier, no ridge vent "
             "(design rules, R905.1.2 exception), no deck repair (new build)"},
    {"id": "covering-faces", "type": "count", "objects": "RT_layer_covering", "of": "islands", "expect": 110,
     "source": std, "note": "per plane 14 courses (73.79 / 5.625 = 13.1 -> 14) on 2 triangles: 28 course faces + "
                            "27 butt faces (2 per course, 1 on the eave course) = 55; x 2 planes"},
    {"id": "nails", "type": "count", "objects": "RT_layer_nails", "of": "islands", "expect": 3840, "source": std,
     "note": "12 nail rows a plane (rows whose nail line is 1.57 in. inside the plane) x 16 nails (every 9.84 in. = "
             "4 a 39-3/8 in. shingle, R905.2.6) x 2 planes = 384 nails, 10 faces each"},
    {"id": "door", "type": "size", "objects": "Shed_Door_Slab", "sorted": True, "expect": [1.75, 36, 80], "unit": "in",
     "source": std, "note": "door size not in the brief: standard 3 ft 0 in. x 6 ft 8 in. slab"},
    {"id": "door-center", "type": "position", "objects": "Shed_Door_Slab", "at": [60, None, None], "unit": "in",
     "source": "given", "note": "brief: in the middle of the front"},
    {"id": "window-heads", "type": "extent", "objects": "Shed_Window_*_Frame_*", "axis": "z", "expect": 86.25,
     "unit": "in", "source": std, "note": "design rule: window head level with the door head: rough-opening tops at "
     "82.5 in. (80 + 2.5), so the unit's top at 82.25 in. above the slab, 4 in. pad"},
]
for n, (wall, y) in enumerate((("left", 48), ("left", 96), ("right", 48), ("right", 96)), 1):
    extra += [{"id": f"window-{n}-size", "type": "size", "objects": f"Shed_Window_{n}_Frame_*", "sorted": True,
               "expect": [3.9375, 24, 36], "unit": "in", "source": "given", "note": "brief: 2 ft x 3 ft; wall depth"},
              {"id": f"window-{n}-at", "type": "position", "objects": f"Shed_Window_{n}_Frame_*", "at": [None, y, None],
               "unit": "in", "source": std, "note": f"design rule: windows equally spaced along the {wall} wall (12 ft / 3)"}]
mats = [("siding", ["Shed_Siding_*", "Shed_Starter_*"], "M_Siding", "given"), ("trim", ["Shed_Trim_*",
         "Shed_Window_*_Casing_*", "Shed_Door_Casing_*"], "M_Trim", "given"), ("shingles", "RT_layer_covering",
         "RT_covering*", "given"), ("pad-material", "Shed_Pad", "M_Concrete", "given"),
        ("lumber", ["Shed_Stud_*", "Shed_Rafter_*"], "M_Lumber", std), ("glass", "Shed_Window_*_Glass", "M_Glass", std),
        ("door-material", "Shed_Door_Slab", "M_Door", std)]
extra += [{"id": i, "type": "material", "objects": o, "expect": e, "source": s} for i, o, e, s in mats]
extra[-1]["note"] = "design rule: the door colour matches the trim (#FFFFFF)"
extra.append({"id": "hero", "type": "image", "file": "//render/hero_0001.png", "res": [1920, 1080], "source": "given"})
spec = {"name": "Garden shed (027, construction grade)", "units": "in", "checks": checks + extra,
        "forbid": {"scope": "Shed_*"}}
with open(os.path.join(HERE, "acceptance.json"), "w", encoding="utf-8") as f:
    f.write('{"name": %s, "units": "in",\n "checks": [\n' % json.dumps(spec["name"]))
    f.write(",\n".join("  " + json.dumps(c) for c in spec["checks"]))
    f.write('],\n "forbid": {"scope": "Shed_*"}}\n')
with open(os.path.join(HERE, "roof-expect.json"), "w", encoding="utf-8") as f:
    json.dump({"source": "hand values (accuracy plan 2, D1): two 13 ft eaves, four 73.79 in. rakes, one 13 ft ridge",
               "tol_pct": 2, "planes": 2, "squares": round(2 * 156 * run_ * k / 14400, 3),
               "lengths_ft": {"eave": 26, "rake": round(4 * run_ * k / 12, 3), "ridge": 13}}, f, indent=1)
print(f"acceptance.json: {len(spec['checks'])} checks ({len(checks)} from --plan); roof-expect.json")
