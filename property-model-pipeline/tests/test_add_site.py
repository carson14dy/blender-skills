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
                              "mat": o.data.materials[0].name if o.data.materials else None, "nverts": len(vs),
                              "smooth": all(p.use_smooth for p in o.data.polygons),
                              "min_nz": min([(o.matrix_world.to_3x3() @ p.normal).z for p in o.data.polygons] or [1.0]),
                              "mats": [m.name for m in o.data.materials],
                              "top_mat": [p.material_index for p in o.data.polygons if (o.matrix_world.to_3x3() @ p.normal).z > 0.99]}
out["fonts"] = {o.name: {"scale": list(o.scale), "size": o.data.size} for o in bpy.data.collections["Site"].objects if o.type == "FONT"}
out["nodes"] = {}
for m in bpy.data.materials:
    if m.use_nodes and m.node_tree:
        out["materials"][m.name] = sorted({n.bl_idname for n in m.node_tree.nodes})
        nd = []
        for n in m.node_tree.nodes:
            e = {"type": n.bl_idname, "label": n.label}
            if n.bl_idname == "ShaderNodeTexVoronoi":
                e.update(dims=n.voronoi_dimensions, feature=n.feature, scale=n.inputs["Scale"].default_value)
            elif n.bl_idname == "ShaderNodeMix" and n.data_type == "RGBA":
                e.update(b=list(n.inputs[7].default_value)[:3])
            elif n.bl_idname == "ShaderNodeVectorMath":
                e.update(v=list(n.inputs[1].default_value))
            elif n.bl_idname == "ShaderNodeMapRange":
                e.update(to=[n.inputs["To Min"].default_value, n.inputs["To Max"].default_value])
            elif n.bl_idname == "ShaderNodeMath":
                e.update(v=n.inputs[1].default_value)
            elif n.bl_idname == "ShaderNodeBump":
                e.update(distance=n.inputs["Distance"].default_value)
            nd.append(e)
        out["nodes"][m.name] = nd
json.dump(out, open(sys.argv[2], "w"))
"""


def _run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return r.stdout


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
        {"kind": "fence", "name": "rail", "line": [[-4, 3], [-4, 4]], "top_z": 1.0, "style": "baluster"},
        {"kind": "pier", "name": "pier behind", "xy": [0, 0.8], "size": [0.6, 0.4], "top_z": 0.3,
         "plaque": {"text": "12", "face": "-y"}},                     # numerals below the wall top, wall in front
        {"kind": "pier", "name": "pier inside", "xy": [1.5, 0.5], "size": [0.4, 0.4], "top_z": 1.0,
         "plaque": {"text": "34", "face": "-y"}},                     # face inside the wall solid
        {"kind": "pier", "name": "pier clear", "xy": [-4.5, -2], "size": [0.4, 0.4], "top_z": 0.0,
         "plaque": {"text": "56", "face": "-y"}},
        {"kind": "steps", "name": "st", "line": [[-4, -4], [-4, -2]], "width": 1.0, "z0": -1.0, "z1": -0.5, "risers": 4,
         "tread": {"slab": 0.05, "gap": 0.06}},
        {"kind": "rock_scatter", "name": "stone", "stones": [[4.0, -4.0, 0.5]], "height": [0.4, 0.4]},
        {"kind": "boulder", "name": "notched", "polygon": [[-3, 2], [-1, 2], [-1, 4], [-1.6, 4], [-1.6, 2.6], [-2.4, 2.6],
                                                            [-2.4, 4], [-3, 4]], "top_z": 1.2},    # concave U outline
        {"kind": "boulder", "name": "juniper", "polygon": [[0, 2], [1, 2], [1, 3]], "top_z": 0.8, "surface": "foliage"},
        {"kind": "steps", "name": "buried", "line": [[4.5, -1.0], [4.5, 1.0]], "width": 0.8, "z0": -1.0, "z1": -0.9,
         "risers": 4},                                                # the straight line runs under the upper terrain
        {"kind": "retaining_wall", "name": "capped wall", "line": [[-4.5, -4.5], [-3.0, -4.5]], "top_z": -0.5,
         "thickness": 0.2, "material": "concrete", "color": [[0.16, 0.16, 0.15], [0.21, 0.21, 0.2]],
         "cap_color": [[0.55, 0.55, 0.53], [0.62, 0.62, 0.6]]},
        {"kind": "pier", "name": "pier sx", "xy": [-4.5, 3.0], "size": [1.0, 0.5], "top_z": 1.0,
         "plaque": {"text": "88", "face": "-y", "size": 0.4, "scale_x": 0.6}}],
        "materials": {"rock": [[0.26, 0.19, 0.12], [0.55, 0.42, 0.28]]}}
    sp, yp, out, js = d / "scene.json", d / "yard.json", str(d / "out.blend"), str(d / "inspect.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    log = _run([ADD_SITE, blend, str(sp), str(yp), out])
    (d / "look_site.py").write_text(INSPECT)
    _run([str(d / "look_site.py"), out, js])
    r = json.load(open(js))
    r["log"] = log
    return r


def test_pier_plaque_guard_warns_when_a_wall_hides_the_numerals(site):
    warn = [ln for ln in site["log"].splitlines() if ln.startswith("WARNING") and "plaque" in ln]
    assert any("pier behind" in ln and " behind " in ln for ln in warn)
    assert any("pier inside" in ln and " inside " in ln for ln in warn)
    assert not any("pier clear" in ln for ln in warn)


def test_boulder_is_a_smooth_dome_with_a_rounded_top(site):
    b = site["objects"]["rock"]
    assert b["smooth"] and b["nverts"] == 8 * 8 + 1               # 4 outline points -> 8 segments x 8 rings + centre
    assert abs(b["max"][2] - 1.0) < 1e-6
    rings = add_site_rings()
    hs = [h for _, h in rings]
    assert hs[0] == 0.0 and all(b_ > a_ for a_, b_ in zip(hs, hs[1:]))
    inner = [h for f, h in rings if f >= 0.75]                     # the inner quarter of the radius ...
    assert inner and min(inner) > 0.97                             # ... within 3 % of the top: a broad dome


def test_steps_with_tread_slabs_show_the_fill_between_them(site):
    slab, fill = site["objects"]["st 7 tread 0"], site["objects"]["st 7 tread 0 fill"]
    assert abs((slab["max"][2] - slab["min"][2]) - 0.05) < 1e-6
    assert abs((slab["max"][1] - slab["min"][1]) - (0.5 - 0.06)) < 1e-6    # run 0.5 m, 0.06 m gap
    assert abs(fill["max"][2] - (slab["max"][2] - 0.05)) < 1e-6 and fill["mat"] != slab["mat"]


def test_rock_scatter_places_measured_stones(site):
    """Measured position, angular (icosphere, flat-shaded), flat and partly buried: 30 % of its height under grade."""
    st = site["objects"]["stone 1"]
    assert abs((st["min"][0] + st["max"][0]) / 2 - 4.0) < 0.12 and abs((st["min"][1] + st["max"][1]) / 2 + 4.0) < 0.12
    h = st["max"][2] - st["min"][2]
    assert abs((-1.0 - st["min"][2]) / h - 0.3) < 1e-3                # sunk 30 % below the grade (-1.0)
    w = max(st["max"][0] - st["min"][0], st["max"][1] - st["min"][1])
    assert 0.3 * 0.5 * 0.7 < h < 0.55 * w and w < 0.5 * 1.3           # flat: height 0.35-0.5 x its width (+ noise)
    assert st["nverts"] == 42 and not st["smooth"]                   # icosphere (2 subdivisions), faceted
    assert st["mat"].startswith("Garden stone")


def test_boulder_has_no_undercut_and_foliage_mass(site):
    assert site["objects"]["notched"]["min_nz"] > -1e-6              # no face leans out over the foot
    assert site["objects"]["juniper"]["mat"].startswith("Foliage")


def test_steps_are_never_buried(site):
    tops = [site["objects"][f"buried 11 tread {k}"]["max"][2] for k in range(4)]
    assert all(b_ >= a_ - 1e-9 for a_, b_ in zip(tops, tops[1:]))    # never steps down
    assert tops[-1] >= 0.03 - 1e-6 and tops[0] < -0.5               # upper treads lifted above the upper terrain


def test_wall_cap_colour_and_plaque_scale(site):
    w = site["objects"]["capped wall"]
    assert len(w["mats"]) == 2 and w["mats"][1].startswith("Retaining wall cap") and set(w["top_mat"]) == {1}
    f = [v for k, v in site["fonts"].items() if k.startswith("pier sx")]
    assert f and abs(f[0]["scale"][0] - 0.6) < 1e-6 and abs(f[0]["size"] - 0.4) < 1e-6


def add_site_rings():
    """dome_rings() from add_site.py without importing it (it runs on import): exec just that function."""
    import math
    src = open(ADD_SITE).read()
    ns = {"math": math}
    head = src[src.index("BOULDER_RINGS ="):src.index("def subdivide_ring")]
    exec(head, ns)
    return ns["dome_rings"]()


def test_face_walls_stand_on_the_uphill_side_of_their_line(site):
    w = site["objects"]["face wall"]
    assert abs(w["min"][1] - 0.0) < 1e-4 and abs(w["max"][1] - 0.4) < 1e-4     # exposed face on the line
    a = site["objects"]["auto wall"]                                             # side found from the terrain
    assert abs(a["min"][1] - 0.0) < 1e-4 and abs(a["max"][1] - 0.3) < 1e-4
    assert abs(w["max"][2] - 0.1) < 1e-4 and w["min"][2] < -1.2               # level top, foot under the low side


def test_drystack_is_random_coursed_ledgestone(site):
    """Dry-stack: thin random courses (1-D Voronoi along z, mean 0.08 m -> 0.04-0.12 m), random stone lengths with a
    random stagger (1-D Voronoi along x, mean 0.375 m -> 0.15-0.6 m), dark brown-grey joints (~0.08 linear) recessed
    1-2 cm, no joints on the top faces (side-face mask from the normal); no brick."""
    mat = site["objects"]["face wall"]["mat"]
    assert "ShaderNodeTexBrick" not in site["materials"][mat]
    nodes = site["nodes"][mat]
    vor = [n for n in nodes if n["type"] == "ShaderNodeTexVoronoi"]
    assert all(n["dims"] == "1D" for n in vor)
    courses = {round(n["scale"], 3) for n in vor if n["label"].startswith("courses")}
    stones = {round(n["scale"], 3) for n in vor if n["label"] == "stones"}
    assert courses == {12.5} and stones == {round(1 / 0.375, 3)}       # mean 0.08 m courses, 0.375 m stones
    assert {"F1", "DISTANCE_TO_EDGE"} <= {n["feature"] for n in vor if n["label"] == "stones"}
    jd = [n["b"] for n in nodes if n["label"] == "joint dark"]
    assert jd and 0.05 <= jd[0][0] <= 0.1 and jd[0][2] < jd[0][0]       # dark brown-grey
    bump = [n["distance"] for n in nodes if n["type"] == "ShaderNodeBump"]
    assert bump and 0.01 <= bump[0] <= 0.02
    assert any(n["label"] == "side faces" and abs(n["v"] - 0.5) < 1e-6 for n in nodes)   # caps carry no joints


def test_rocks_have_sparse_joints_and_bedding(site):
    """Rock: joint cells ~1.9 m (Voronoi scale ~0.53), lines < 2 cm (width / scale), joints at >= 0.8 x the stone
    value, horizontal bedding from a noise stretched 6:1 in xy:z at +-8 % -- no dense dark crack net."""
    for mat in (site["objects"]["rock"]["mat"],):
        nodes = site["nodes"][mat]
        cr = [n for n in nodes if n["type"] == "ShaderNodeTexVoronoi" and n["label"] == "cracks"]
        assert cr and all(0.45 <= n["scale"] <= 0.6 for n in cr)
        width = [n["v"] for n in nodes if n["label"] == "crack width"][0]
        assert width / cr[0]["scale"] < 0.02
        dark = [n["b"][0] for n in nodes if n["type"] == "ShaderNodeMix" and n["label"] == "cracks"]
        assert dark and dark[0] >= 0.8
        st = [n["v"] for n in nodes if n["label"] == "bedding stretch"]
        assert st and st[0][2] / st[0][0] == 6.0
        amp = [n["to"] for n in nodes if n["label"] == "bedding amplitude"][0]
        assert abs(amp[1] - 1.08) < 1e-6 and abs(amp[0] - 0.92) < 1e-6


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
    crease with area-weighted normals, a clockwise overlay triangle is flipped normal-up, rock is warm buff."""
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
    assert r["rock"] and all(abs(a - b) < 0.01 for a, b in zip(r["rock"][0], (0.442, 0.38, 0.284)))   # warm buff
    # every Site object is tagged with what made it (render_thumbnail.py --terrain keeps the hardscape by it)
    assert r["kinds"]["concrete (draped)"] == "overlay:concrete" and r["kinds"]["boulder 0"] == "boulder"


CLIFF_LOOK = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
t = bpy.data.objects["Terrain (LiDAR ground)"]
me = t.data
out = {"z": [v.co.z for v in me.vertices], "xy": [[v.co.x, v.co.y] for v in me.vertices],
       "tris": [list(p.vertices) for p in me.polygons], "n": [list(p.normal) for p in me.polygons],
       "groups": [g.name for g in t.vertex_groups], "custom": me.has_custom_normals, "mods": [m.type for m in t.modifiers]}
json.dump(out, open(sys.argv[2], "w"))
"""


def test_oblique_cliff_faces_are_smoothed_without_back_facing_fangs(tmp_path):
    """A 3 m cliff running at 30 deg to a 0.25 m grid, with a ragged crest, is a notched staircase: some of its steep
    triangles face away from the cliff (they self-shadow as dark 'fangs'). The rock-face vertices (8-neighbour range > 1 m) get one Laplacian pass
    (heights kept within 0.3 m of the measured grid) and smoothed shading normals: fewer back-facing steep triangles,
    no vertex more than 0.3 m off its measured height, flat ground away from the cliff untouched."""
    import math
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    c, n = 0.25, 17
    a = math.radians(30.0); N = (math.cos(a), math.sin(a))          # uphill direction (the cliff faces -N)
    xy = [(i * c - 2.0, j * c - 2.0) for j in range(n) for i in range(n)]
    import random
    rnd = random.Random(4)                                          # a ragged crest: +-0.3 m along the face normal
    z = [3.0 if x * N[0] + y * N[1] > 0.05 + rnd.uniform(-0.3, 0.3) else 0.0 for x, y in xy]
    verts = [[x, y, zz] for (x, y), zz in zip(xy, z)]
    faces = [[j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i] for j in range(n - 1) for i in range(n - 1)]
    scene = {"verts": verts, "faces": faces, "face_class": [0] * len(faces), "classes": ["ground"], "overlays": {},
             "curbs": [], "edging": [], "parcel": None, "points": [], "grid": {"nx": n, "ny": n, "z": z}}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "c.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps({"items": []}))
    log = _run([ADD_SITE, blend, str(sp), str(yp), out])
    assert "steep-face vertices" in log
    (tmp_path / "look.py").write_text(CLIFF_LOOK)
    _run([str(tmp_path / "look.py"), out, js])
    r = json.load(open(js))
    assert "rock face" in r["groups"] and r["custom"] and "WEIGHTED_NORMAL" not in r["mods"]   # baked + overridden

    def off_angles(P, tris):
        """Angle (deg) between each steep triangle's horizontal normal and the cliff's outward normal -N."""
        out = []
        for t in tris:
            p0, p1, p2 = (P[k] for k in t)
            u = [p1[d] - p0[d] for d in range(3)]; v = [p2[d] - p0[d] for d in range(3)]
            nx_, ny_, nz_ = u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]
            ln = math.sqrt(nx_ * nx_ + ny_ * ny_ + nz_ * nz_) or 1.0
            if abs(nz_ / ln) < 0.7:
                h = math.hypot(nx_, ny_)
                out.append(math.degrees(math.acos(max(-1.0, min(1.0, -(nx_ * N[0] + ny_ * N[1]) / h)))))
        return sorted(out)
    before = off_angles(verts, [[f[0], f[1], f[2]] for f in faces] + [[f[0], f[2], f[3]] for f in faces])
    after = off_angles([[x, y, zz] for (x, y), zz in zip(r["xy"], r["z"])], r["tris"])
    med = lambda v: v[len(v) // 2]
    assert med(after) <= med(before) - 15                                   # the face reads as one face (no flutes)
    assert sum(x > 60 for x in after) < sum(x > 60 for x in before)         # fewer slivers turned away from it
    assert max(abs(a_ - b_) for a_, b_ in zip(r["z"], z)) <= 0.3 + 1e-6      # measured heights kept within 0.3 m
    far = [k for k, (x, y) in enumerate(xy) if abs(x * N[0] + y * N[1]) > 1.0]
    assert all(abs(r["z"][k] - z[k]) < 1e-9 and abs(r["xy"][k][0] - xy[k][0]) < 1e-9 for k in far)
