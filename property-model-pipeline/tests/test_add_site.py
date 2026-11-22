"""add_site.py yard items (runs headless Blender through the `bpy` module in a subprocess)."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ADD_SITE = os.path.join(HERE, "..", "scripts", "blender", "add_site.py")

pytestmark = pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="needs the bpy module")

EMPTY = r"""
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[1])
"""

INSPECT = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {"objects": {}, "materials": {}}
for o in bpy.data.collections["Site"].objects:
    if o.type != "MESH":
        continue
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    out["objects"][o.name] = {"min": [min(v[i] for v in vs) for i in range(3)], "max": [max(v[i] for v in vs) for i in range(3)],
                              "mat": o.data.materials[0].name if o.data.materials else None}
for m in bpy.data.materials:
    if m.use_nodes and m.node_tree:
        out["materials"][m.name] = sorted({n.bl_idname for n in m.node_tree.nodes})
json.dump(out, open(sys.argv[2], "w"))
"""


def _run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("site")
    blend = str(d / "empty.blend")
    (d / "empty.py").write_text(EMPTY)
    _run([str(d / "empty.py"), blend])
    # flat 10 x 10 m terrain at z 0 (north half) / -1 (south half), as two quads
    verts = [[-5, -5, -1], [5, -5, -1], [5, 0, -1], [-5, 0, -1], [-5, 0, 0], [5, 0, 0], [5, 5, 0], [-5, 5, 0]]
    scene = {"verts": verts, "faces": [[0, 1, 2, 3], [4, 5, 6, 7]], "face_class": [0, 0], "classes": ["ground"],
             "overlays": {}, "curbs": [], "edging": [], "parcel": None, "points": []}
    yard = {"items": [
        {"kind": "retaining_wall", "name": "face wall", "line": [[-3, 0], [3, 0]], "top_z": 0.1, "thickness": 0.4,
         "material": "drystack", "line_is": "face", "uphill": "left"},
        {"kind": "retaining_wall", "name": "auto wall", "line": [[3, 0.0], [-3, 0.0]], "top_z": 0.1, "thickness": 0.3,
         "line_is": "face"},
        {"kind": "boulder", "name": "rock", "polygon": [[2, 2], [3, 2], [3, 3], [2, 3]], "top_z": 1.0},
        {"kind": "fence", "name": "rail", "line": [[-4, 3], [-4, 4]], "top_z": 1.0, "style": "baluster"}],
        "materials": {"rock": [[0.26, 0.19, 0.12], [0.55, 0.42, 0.28]]}}
    sp, yp, out, js = d / "scene.json", d / "yard.json", str(d / "out.blend"), str(d / "inspect.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    _run([ADD_SITE, blend, str(sp), str(yp), out])
    (d / "look_site.py").write_text(INSPECT)
    _run([str(d / "look_site.py"), out, js])
    return json.load(open(js))


def test_face_walls_stand_on_the_uphill_side_of_their_line(site):
    w = site["objects"]["face wall"]
    assert abs(w["min"][1] - 0.0) < 1e-4 and abs(w["max"][1] - 0.4) < 1e-4     # exposed face on the line
    a = site["objects"]["auto wall"]                                             # side found from the terrain
    assert abs(a["min"][1] - 0.0) < 1e-4 and abs(a["max"][1] - 0.3) < 1e-4
    assert abs(w["max"][2] - 0.1) < 1e-4 and w["min"][2] < -1.2               # level top, foot under the low side


def test_drystack_is_a_brick_coursed_stone_and_rocks_are_fractured(site):
    mat = site["objects"]["face wall"]["mat"]
    assert "ShaderNodeTexBrick" in site["materials"][mat]
    assert "ShaderNodeBump" in site["materials"][mat]
    rock = site["materials"][site["objects"]["rock"]["mat"]]
    assert "ShaderNodeTexVoronoi" in rock                                        # crack mask on boulders


def test_level_rail_top(site):
    posts = [v for k, v in site["objects"].items() if k.startswith("fence") and "post" in k]
    assert posts and all(abs(p["max"][2] - 1.0) < 1e-4 for p in posts)


TERRAIN_LOOK = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
t = bpy.data.objects["Terrain (LiDAR ground)"]
out = {"sizes": sorted({len(p.vertices) for p in t.data.polygons}),
       "sharp": sum(t.data.attributes["sharp_edge"].data[i].value for i in range(len(t.data.edges)))
                if "sharp_edge" in t.data.attributes else 0,
       "mods": [m.type for m in t.modifiers], "keep_sharp": [m.keep_sharp for m in t.modifiers if m.type == "WEIGHTED_NORMAL"],
       "overlay_nz": [p.normal.z for p in bpy.data.objects["concrete (draped)"].data.polygons],
       "kinds": {o.name: o.get("site_kind") for o in bpy.data.collections["Site"].objects},
       "rock": [list(e.color[:3]) for m in bpy.data.materials if m.name.startswith("Rock") and m.node_tree
                for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeValToRGB" for e in n.color_ramp.elements]}
json.dump(out, open(sys.argv[2], "w"))
"""


def test_terrain_is_folded_creased_and_overlays_face_up(tmp_path):
    """Quads become the two triangles of their 0-2 fold, a 3 m step between neighbouring cells is a sharp
    crease with area-weighted normals, a clockwise overlay triangle is flipped normal-up, rock is buff."""
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    # 3 x 1 strip of 1 m cells: flat, a 3 m cliff cell, flat on top
    verts = [[x, y, (0.0 if x <= 1 else 3.0)] for y in (0, 1) for x in (0, 1, 2, 3)]
    faces = [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6]]
    scene = {"verts": verts, "faces": faces, "face_class": [0, 0, 0], "classes": ["ground"],
             "overlays": {"concrete": {"verts": [[0.1, 0.1, 0.03], [0.1, 0.9, 0.03], [0.9, 0.1, 0.03]], "tris": [[0, 1, 2]]}},
             "curbs": [], "edging": [], "parcel": None, "points": []}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "t.json")
    yard = {"items": [{"kind": "boulder", "polygon": [[0.2, 0.2], [0.6, 0.2], [0.6, 0.6]], "top_z": 0.5}]}   # default tone
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    _run([ADD_SITE, blend, str(sp), str(yp), out])
    (tmp_path / "look.py").write_text(TERRAIN_LOOK)
    _run([str(tmp_path / "look.py"), out, js])
    r = json.load(open(js))
    assert r["sizes"] == [3]                                    # explicit triangles
    assert r["sharp"] >= 2                                      # the cliff's top and foot are creases
    assert "WEIGHTED_NORMAL" in r["mods"] and r["keep_sharp"] == [True]
    assert r["overlay_nz"] and min(r["overlay_nz"]) > 0.99     # flipped to face up
    assert r["rock"] and all(abs(a - b) < 0.01 for a, b in zip(r["rock"][0], (0.42, 0.38, 0.31)))
    # every Site object is tagged with what made it (render_thumbnail.py --terrain keeps the hardscape by it)
    assert r["kinds"]["concrete (draped)"] == "overlay:concrete" and r["kinds"]["boulder 0"] == "boulder"
