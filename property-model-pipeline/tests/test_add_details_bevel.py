"""add_details.py: bevelled (slanted) ends on beams and beam ends ("bevel", "bevel_end"). Synthetic scene only."""
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

DUMP = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Details"].objects:
    if o.type == "MESH" and len(o.data.vertices) == 8:
        me = o.data
        out[o.name] = {"verts": [list(o.matrix_world @ v.co) for v in me.vertices],
                       "faces": [[list(o.matrix_world @ me.vertices[i].co) for i in p.vertices] for p in me.polygons]}
json.dump(out, open(sys.argv[2], "w"))
"""


def _run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return r


@pytest.fixture(scope="module")
def beams(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("bevel")
    # gable along x (ridge y = 0), rakes at x = +-5.3 (rake overhang 0.3), eaves at y = +-4.5
    w = Wing.from_dict(dict(id="M", type="gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0,
                            pitch=0.5, eave_overhang=0.5, rake_overhang=0.3))
    mj = to_mesh_json(build([w]))
    (tmp / "model.json").write_text(json.dumps(mj))
    _run([os.path.join(SCRIPTS, "build_model.py"), "--model", str(tmp / "model.json"), "--out", str(tmp / "out"),
          "--plain-ground"])
    D = {"model_json": str(tmp / "model.json"),
         "beams": [{"name": "header bevel p0", "p0": [-6.0, -4.0, 2.5], "p1": [-2.0, -4.0, 2.5], "size": [0.15, 0.3],
                    "bevel": 0.25},
                   {"name": "header bevel both", "p0": [0.0, -6.0, 2.5], "p1": [3.0, -6.0, 2.5], "size": [0.15, 0.3],
                    "bevel": 0.2, "bevel_end": "both"},
                   {"name": "header square", "p0": [0.0, -7.0, 2.5], "p1": [3.0, -7.0, 2.5], "size": [0.15, 0.3]}],
         "beam_ends": [{"xy": [5.7, -1.0], "name": "tail bevelled", "size": [0.25, 0.35], "bevel": 0.2},
                       {"xy": [5.7, 1.0], "name": "tail square", "size": [0.25, 0.35]}]}
    (tmp / "details.json").write_text(json.dumps(D))
    _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"), str(tmp / "details.json"),
          str(tmp / "detailed.blend")])
    (tmp / "dump.py").write_text(DUMP)
    _run([str(tmp / "dump.py"), str(tmp / "detailed.blend"), str(tmp / "beams.json")])
    return json.loads((tmp / "beams.json").read_text())


def _split(verts):
    zs = sorted(v[2] for v in verts)
    zmid = (zs[0] + zs[-1]) / 2
    return [v for v in verts if v[2] < zmid], [v for v in verts if v[2] > zmid]


def _planar(face, tol=1e-4):
    import numpy as np
    P = np.array(face)
    c = P.mean(axis=0)
    n = np.linalg.svd(P - c)[2][-1]
    return float(np.abs((P - c) @ n).max()) < tol


def test_beam_bevel_sets_back_the_bottom_edge_at_p0_only(beams):
    bot, top = _split(beams["header bevel p0"]["verts"])
    assert min(v[0] for v in top) == pytest.approx(-6.0, abs=1e-4)          # the top runs out to p0
    assert min(v[0] for v in bot) == pytest.approx(-5.75, abs=1e-4)         # the bottom stops 0.25 m short
    assert max(v[0] for v in top) == pytest.approx(-2.0, abs=1e-4)          # p1 end square
    assert max(v[0] for v in bot) == pytest.approx(-2.0, abs=1e-4)
    assert all(_planar(f) for f in beams["header bevel p0"]["faces"])


def test_beam_bevel_both_ends_and_square_default(beams):
    bot, top = _split(beams["header bevel both"]["verts"])
    assert (min(v[0] for v in bot), max(v[0] for v in bot)) == (pytest.approx(0.2, abs=1e-4), pytest.approx(2.8, abs=1e-4))
    assert (min(v[0] for v in top), max(v[0] for v in top)) == (pytest.approx(0.0, abs=1e-4), pytest.approx(3.0, abs=1e-4))
    bot, top = _split(beams["header square"]["verts"])
    assert sorted(round(v[0], 4) for v in bot) == sorted(round(v[0], 4) for v in top)


def test_beam_end_bevel_cuts_the_tip_bottom_back_toward_the_wall(beams):
    sq_bot, sq_top = _split(beams["tail square"]["verts"])
    bv_bot, bv_top = _split(beams["tail bevelled"]["verts"])
    tip = max(v[0] for v in sq_top)
    assert max(v[0] for v in bv_top) == pytest.approx(tip, abs=1e-4)          # same tip at the top
    assert max(v[0] for v in bv_bot) == pytest.approx(tip - 0.2, abs=1e-4)    # bottom set back 0.2 m
    assert max(v[0] for v in sq_bot) == pytest.approx(tip, abs=1e-4)
    assert all(_planar(f) for f in beams["tail bevelled"]["faces"])


def test_bevel_end_rejects_unknown_names():
    src = open(os.path.join(SCRIPTS, "add_details.py")).read()
    start = src.index("def bevel_ends(")
    ns = {}
    exec(src[start:src.index("\n\n\n", start)], ns)
    assert ns["bevel_ends"]({"bevel": 0.2, "bevel_end": "p1"}) == (0.0, 0.2)
    assert ns["bevel_ends"]({}) == (0.0, 0.0)
    with pytest.raises(ValueError):
        ns["bevel_ends"]({"bevel": 0.2, "bevel_end": "tip"})
