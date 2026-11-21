"""add_details.py presentation features (runs headless Blender through the `bpy` module in a subprocess)."""
import importlib.util
import json
import math
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
out = {}
for o in bpy.data.collections["Details"].objects:
    if o.type != "MESH":
        out[o.name] = {"type": o.type, "loc": list(o.location)}
        continue
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    out[o.name] = {"n": len(vs), "min": [min(v[i] for v in vs) for i in range(3)],
                   "max": [max(v[i] for v in vs) for i in range(3)],
                   "verts": [list(v) for v in vs] if len(vs) <= 16 else None,
                   "mat": o.data.materials[0].name if o.data.materials else None}
mats = {m.name: list(m.diffuse_color)[:3] for m in bpy.data.materials}
json.dump({"objects": out, "materials": mats}, open(sys.argv[2], "w"))
"""


def _run(args, cwd=None):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=cwd, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return r


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("details")
    # gable along x (ridge y = 0), a roof opening on the south slope, a notched (concave) south outline
    hole = [[1.0, -2.6], [2.2, -2.6], [2.2, -1.2], [1.0, -1.2]]
    outline = [[-5.3, -4.5], [0.0, -4.5], [0.0, -3.5], [5.3, -3.5], [5.3, 4.5], [-5.3, 4.5]]
    w = Wing.from_dict(dict(id="M", type="gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0,
                            pitch=0.5, eave_overhang=0.5, rake_overhang=0.3, outline=outline, outline_holes=[hole]))
    m = build([w])
    mj = to_mesh_json(m)
    (tmp / "model.json").write_text(json.dumps(mj))
    _run([os.path.join(SCRIPTS, "build_model.py"), "--model", str(tmp / "model.json"), "--out", str(tmp / "out"),
          "--plain-ground"])
    south = next(x for x in mj["walls"] if abs(x["bearing"] - 180) < 1)
    key = f'{south["wing"]}:{south["side"]}'
    D = {
        "model_json": str(tmp / "model.json"),
        "siding": {"color": [225, 215, 180]},                       # 8-bit sRGB -> linear
        "foundation": {"skip": ["M"]},
        "window_frame_color": [80, 68, 52],
        "openings": [{"wall": key, "u": 3.0, "sill_z": 0.9, "width": 3.0, "height": 1.5, "kind": "window",
                      "mullions": [0.2, 0.8], "label": "window wall"},
                     {"wall": "GAR:front", "u": 2.0, "sill_z": -3.0, "width": 2.5, "height": 2.1, "kind": "garage",
                      "style": "ribbed", "label": "garage door"}],
        "extra_walls": [{"name": "GAR:front", "bottom": [[-4, -8, -3.0], [0, -8, -3.0]], "top_z": -0.2,
                         "bearing": 180, "material": "concrete", "thickness": 0.2}],
        "decks": [{"polygon": [[-4, -4], [0, -4], [0, -8], [-2, -8], [-2, -6], [-3, -6], [-3, -8], [-4, -8]],
                   "top_z": 0.0, "rail_edges": [[1, 2], [2, 3]], "rail_style": "screen", "rail_height": 1.0,
                   "picket_width": 0.11, "picket_gap": 0.025, "rim_depth": 0.8, "post_edges": []}],
        "stairs": [{"top": [-4.0, -5.0], "dir": [-1, 0], "width": 1.2, "length": 2.0, "top_z": 0.0,
                    "bottom_z": -1.4, "risers": 8, "rails": ["left", "right"],
                    "rail_style": {"left": "screen", "right": "balusters"}}],
        "beams": [{"name": "trellis beam", "p0": [0.8, -1.9], "p1": [2.4, -1.9], "size": [0.15, 0.2],
                   "z_offset": 0.03},
                  {"name": "porch beam", "p0": [-4, -4.1, 2.9], "p1": [0, -4.1, 2.9], "size": [0.14, 0.3]}],
        "beam_ends": [{"xy": [5.6, -1.0], "name": "rake beam end"}],
        "chimneys": [{"center": [-3.0, 1.5], "size": [0.6, 1.0], "azimuth": 90, "top_z": 6.5,
                      "shoulder": {"z": 6.0, "size": [1.0, 1.4]}, "cap": {"color": [232, 230, 224]},
                      "label": "chimney"}],
        "wall_boxes": [{"wall": key, "u": 7.0, "z": 1.0, "size": [0.6, 0.4, 0.25], "name": "AC sleeve"}],
        "text": [{"xy": [2.0, -9.0], "azimuth": 180, "z": 0.5, "text": "7", "plate": [0.3, 0.2]}],
    }
    (tmp / "details.json").write_text(json.dumps(D))
    _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"), str(tmp / "details.json"),
          str(tmp / "detailed.blend")])
    (tmp / "dump_scene.py").write_text(INSPECT)
    _run([str(tmp / "dump_scene.py"), str(tmp / "detailed.blend"), str(tmp / "scene.json")])
    return mj, D, json.loads((tmp / "scene.json").read_text())


def _objs(sc, prefix):
    return {k: v for k, v in sc["objects"].items() if k.startswith(prefix)}


def test_screen_rail_and_deep_rim(scene):
    _, D, sc = scene
    pk = _objs(sc, "deck 0 rail pickets")
    assert pk, "screen railing builds picket boards"
    n_boards = sum(v["n"] for v in pk.values()) // 8
    run = 4.0 + 2.0                                     # the two rail edges
    assert abs(n_boards - run / 0.135) < 4             # ~0.135 m board pitch
    assert not _objs(sc, "deck 0 rail balusters")
    rim = _objs(sc, "deck 0 rim")
    assert min(v["min"][2] for v in rim.values()) == pytest.approx(-0.84, abs=0.01)   # 0.8 m header under the boards


def test_stairs_length_styles_and_sloped_stringers(scene):
    _, D, sc = scene
    treads = _objs(sc, "stair 0 tread")
    assert len(treads) == 7
    xs = [v["min"][0] for v in treads.values()]
    assert min(xs) == pytest.approx(-6.0, abs=0.01)            # run = length / (risers - 1)
    st = _objs(sc, "stair 0 stringer")
    assert len(st) == 2
    for v in st.values():
        top = [p for p in v["verts"] if p[0] > -4.01]
        low = [p for p in v["verts"] if p[0] < -5.99]
        assert max(p[2] for p in top) > -0.05 and min(p[2] for p in low) == pytest.approx(-1.4, abs=0.01)
    assert _objs(sc, "stair 0 rail pickets") and _objs(sc, "stair 0 rail balusters")


def test_roof_plane_beam_hole_trim_and_beam_end(scene):
    mj, D, sc = scene
    f = next(f for f in mj["facets"] if f["plane"][1] > 0)       # south slope rises to the north
    a, b, c = f["plane"]
    bm = sc["objects"]["trellis beam"]
    ztop = max(p[2] for p in bm["verts"])
    assert ztop == pytest.approx(a * 2.4 + b * -1.9 + c + 0.03 + 0.15 / 2 * math.sin(math.atan(b)), abs=0.02)
    # no gutters inside the roof opening: gutters only on the outer eaves
    hole_y = {-2.6, -1.2}
    for k, v in _objs(sc, "gutter").items():
        assert not any(abs(v["min"][1] - y) < 0.2 and v["min"][0] > 0.8 and v["max"][0] < 2.4 for y in hole_y)
    # concave outline: the fascia of the notch eave (y = -3.5, x 0..5.3) sits on the roof side (north of the edge)
    notch = [v for k, v in _objs(sc, "fascia").items() if v["min"][0] > -0.1 and abs(v["max"][1] + 3.5) < 0.05
             and v["max"][0] > 5.0]
    assert notch and all(v["min"][1] > -3.51 for v in notch)
    be = sc["objects"]["rake beam end"]
    assert be["max"][0] == pytest.approx(5.6, abs=0.02) and be["min"][0] < 5.3   # tip outside, runs back under the rake


def test_chimney_shoulder_cap_walls_and_colours(scene):
    _, D, sc = scene
    o = sc["objects"]
    assert o["chimney shoulder"]["max"][2] == pytest.approx(6.0, abs=0.01)
    assert o["chimney cap"]["max"][2] == pytest.approx(6.5, abs=0.01)
    assert o["chimney"]["max"][0] - o["chimney"]["min"][0] == pytest.approx(0.6, abs=0.01)
    w = o["wall GAR:front"]
    assert w["n"] == 8 and w["min"][1] == pytest.approx(-8.0, abs=0.01)       # outer face on the given line
    assert w["max"][1] == pytest.approx(-7.8, abs=0.01)                        # solid, extruded inward (north)
    assert _objs(sc, "garage door ribs")
    assert "AC sleeve" in o and "plaque 0" in o and any(k.startswith("text") for k in o)
    assert not _objs(sc, "foundation M")                                        # skipped wing
    lin = sc["materials"]["Siding (lap)"]
    assert lin == pytest.approx([0.753, 0.680, 0.457], abs=0.005)               # sRGB 225,215,180 -> linear
