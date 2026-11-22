"""add_details.py provenance: entry labels travel with the geometry, caveats land in the "Details notes" text."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

from propmodel.roofgeom import Wing, build, to_mesh_json

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts", "blender")

pytestmark = pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="needs the bpy module")

INSPECT = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
objs = {o.name: {k: o[k] for k in ("details", "label") if k in o.keys()} for o in bpy.data.collections["Details"].objects}
t = bpy.data.texts.get("Details notes")
json.dump({"objects": objs, "notes": t.as_string() if t else None}, open(sys.argv[2], "w"))
"""


def _run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return r


def test_labels_on_objects_and_notes_text(tmp_path):
    w = Wing.from_dict(dict(id="M", type="gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0,
                            pitch=0.5, eave_overhang=0.5, rake_overhang=0.3))
    mj = to_mesh_json(build([w]))
    (tmp_path / "model.json").write_text(json.dumps(mj))
    _run([os.path.join(SCRIPTS, "build_model.py"), "--model", str(tmp_path / "model.json"), "--out",
          str(tmp_path / "out"), "--plain-ground"])
    south = next(x for x in mj["walls"] if abs(x["bearing"] - 180) < 1)
    key = f'{south["wing"]}:{south["side"]}'
    long_label = "window wall (photo); SW wall line not measured, may sit up to 1 m further out; +/-1.0 m" * 2
    D = {"model_json": str(tmp_path / "model.json"),
         "openings": [{"wall": key, "u": 3.0, "sill_z": 0.9, "width": 2.0, "height": 1.5, "label": long_label}],
         "decks": [{"polygon": [[-4, -5], [0, -5], [0, -7], [-4, -7]], "top_z": 0.5, "rail_edges": [[1, 2]],
                    "label": "landing (LiDAR 0.5)"}],
         "stairs": [{"top": [-4.0, -6.0], "dir": [-1, 0], "width": 1.0, "top_z": 0.5, "bottom_z": 0.0, "risers": 3,
                     "label": "stair, risers assumed"}],
         "beams": [{"name": "rim beam", "p0": [-4, -4.6, 2.9], "p1": [0, -4.6, 2.9]}],
         "lights": [{"wall": key, "u": 6.0, "z": 2.0}],
         "caveats": ["entry stair rebuilt after the photo"]}
    (tmp_path / "details.json").write_text(json.dumps(D))
    r = _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp_path / "out" / "model.blend"),
              str(tmp_path / "details.json"), str(tmp_path / "detailed.blend")])
    assert "details notes: 4 labelled entries, 3 caveats" in r.stdout
    (tmp_path / "dump_props.py").write_text(INSPECT)
    _run([str(tmp_path / "dump_props.py"), str(tmp_path / "detailed.blend"), str(tmp_path / "out.json")])
    res = json.loads((tmp_path / "out.json").read_text())
    objs = res["objects"]
    win = [v for v in objs.values() if v.get("details") == "openings[0]"]
    assert len(win) >= 5 and all(v["label"] == long_label for v in win)          # full label, not the 40-char name
    deck = [k for k, v in objs.items() if v.get("details") == "decks[0]"]
    assert "deck 0 boards" in deck and all(objs[k]["label"] == "landing (LiDAR 0.5)" for k in deck)
    assert any(k.startswith("stair 0 tread") for k, v in objs.items() if v.get("details") == "stairs[0]")
    assert objs["rim beam"] == {"details": "beams[0]", "label": "rim beam"}           # name stands in for a label
    assert objs["light 0 plate"] == {"details": "lights[0]"}                          # unlabelled entry: key only
    assert all(not v for k, v in objs.items() if k.startswith(("fascia", "gutter", "corner board")))  # not entries
    notes = res["notes"]
    cav = notes.split("Caveats (not fully measured):")[1]
    assert "- entry stair rebuilt after the photo" in cav
    assert "- openings[0]: " + long_label in cav and "- stairs[0]: stair, risers assumed" in cav
    assert "decks[0]" not in cav and "decks[0]: landing (LiDAR 0.5)" in notes          # measured: listed, not flagged
