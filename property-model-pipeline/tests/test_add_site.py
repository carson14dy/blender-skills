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
                              "nsides": max([len(p.vertices) for p in o.data.polygons] or [0]),
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
         "plaque": {"text": "88", "face": "-y", "size": 0.4, "scale_x": 0.6}},
        {"kind": "discs", "name": "dots", "points": [[4.0, 4.0], [4.0, -4.5]], "diameter": 0.25, "proud": 0.03,
         "color": [0.7, 0.66, 0.6]},
        {"kind": "retaining_wall", "name": "rubble wall", "line": [[1.0, -3.0], [2.0, -3.0]], "top_z": -0.6, "thickness": 0.3,
         "material": "drystack", "line_is": "face", "uphill": "left",
         "drystack": {"corner": 0.03, "pillow": 0.012, "lift": 0.5, "lift_k": 1.7, "lift_range": 0.3}},
        {"kind": "rock_scatter", "name": "round stone", "stones": [[3.0, -2.0, 0.6]], "shape": "dome", "chaikin": 2,
         "height": [0.3, 0.3], "tint_spread": 0.5, "color": [[0.40, 0.355, 0.20], [0.94, 0.83, 0.47]]},
        {"kind": "box", "name": "deck slab", "xy": [-2.0, 1.0], "size": [0.8, 0.5, 0.08], "base_z": 2.5,
         "color": [0.145, 0.1, 0.088]},
        {"kind": "surface", "name": "shrub bed", "polygon": [[-1, -4], [0, -4], [0, -3], [-1, -3]],
         "color": [[0.05, 0.05, 0.02], [0.1, 0.1, 0.04]], "foliage": {"side": 0.2, "power": 2.0}}],
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
    """Measured position, angular flat slab (5-7-sided prism, flat-shaded), partly buried: 30 % of its height under
    grade; height 0.35-0.5 x the measured diameter."""
    st = site["objects"]["stone 1"]
    assert abs((st["min"][0] + st["max"][0]) / 2 - 4.0) < 0.15 and abs((st["min"][1] + st["max"][1]) / 2 + 4.0) < 0.15
    h = st["max"][2] - st["min"][2]
    assert abs((-1.0 - st["min"][2]) / h - 0.3) < 1e-3                # sunk 30 % below the grade (-1.0)
    w = max(st["max"][0] - st["min"][0], st["max"][1] - st["min"][1])
    assert 0.5 * 0.35 - 1e-6 <= h <= 0.5 * 0.5 + 1e-6                # 0.35-0.5 x the 0.5 m diameter
    assert 0.5 * 0.6 < w < 0.5 * 1.3
    assert st["nverts"] in (15, 18, 21) and not st["smooth"]         # 3 rings of a 5-7-sided outline, faceted
    assert st["mat"].startswith("Garden stone")


def test_discs_sit_proud_of_the_terrain_at_their_points(site):
    """discs: one flat round object per point, `diameter` across, its top `proud` m over the terrain (0 north, -1 south)
    and its bottom under it, so none is buried and none floats."""
    for k, (x, y, g) in enumerate(((4.0, 4.0, 0.0), (4.0, -4.5, -1.0))):
        d = site["objects"][f"dots 14 disc {k}"]
        assert abs((d["min"][0] + d["max"][0]) / 2 - x) < 1e-3 and abs((d["min"][1] + d["max"][1]) / 2 - y) < 1e-3
        assert abs((d["max"][0] - d["min"][0]) - 0.25) < 0.01
        assert abs(d["max"][2] - (g + 0.03)) < 1e-3 and d["min"][2] < g - 0.02
        assert d["mat"].startswith("Discs")


def test_disc_span_takes_the_highest_terrain_under_the_rim():
    """On a slope the disc top stands `proud` over the HIGHEST terrain under its rim (never buried at the uphill edge)
    and its bottom `embed` under the lowest."""
    ds = _pure({"disc_span"})["disc_span"]
    z0, z1 = ds(lambda x, y: 0.5 * y, 0.0, 0.0, 0.125, proud=0.03, embed=0.05)
    assert abs(z1 - (0.5 * 0.125 + 0.03)) < 1e-9 and abs(z0 - (-0.5 * 0.125 - 0.05)) < 1e-9
    z0, z1 = ds(lambda x, y: None, 0.0, 0.0, 0.1)                     # no terrain: around z 0
    assert z0 < 0.0 < z1


def _pure(names):
    """Top-level functions of add_site.py compiled without bpy (they use only math / random)."""
    import ast
    import math
    import random
    src = open(ADD_SITE).read()
    fns = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {"math": math, "random": random}
    exec(compile(ast.Module(fns, []), ADD_SITE, "exec"), ns)
    return ns


def test_stone_outlines_are_angular_polygons_not_ellipses():
    """rock_scatter stones from above: 5-7 corners, radii within +-25 % of the stone radius, at least 4 corners turning
    by more than 30 deg (an ellipse or a noisy sphere has none), convex (every turn positive)."""
    import math
    import random
    so = _pure({"stone_outline"})["stone_outline"]
    for seed in range(200):
        rnd = random.Random(seed)
        P = so(rnd, 0.3)
        assert 5 <= len(P) <= 7
        assert all(0.75 * 0.3 - 1e-9 <= math.hypot(x, y) <= 1.25 * 0.3 + 1e-9 for x, y in P)
        turns = []
        for k in range(len(P)):
            (ax, ay), (bx, by), (cx, cy) = P[k - 1], P[k], P[(k + 1) % len(P)]
            a1, a2 = math.atan2(by - ay, bx - ax), math.atan2(cy - by, cx - bx)
            turns.append(math.degrees((a2 - a1 + math.pi) % (2 * math.pi) - math.pi))
        assert all(t > 0 for t in turns) and sum(t > 30 for t in turns) >= 4, (seed, turns)


def test_boulder_dome_clamped_to_the_terrain(tmp_path):
    """"max_over_terrain": no dome vertex stands more than that over the terrain (site-scene grid, bilinear) under it,
    on a terrain sloping 0.4 m/m across the outline; without it the assumed dome profile stands up to ~1 m over the
    downhill flank. Pure helpers: grid_z is bilinear, clamp_over_terrain only lowers."""
    ns = _pure({"grid_z", "clamp_over_terrain"})
    g = {"x0": 0.0, "y0": 0.0, "nx": 3, "ny": 2, "cell": 1.0, "z": [0.0, 1.0, 3.0, 0.0, 1.0, 3.0]}
    assert abs(ns["grid_z"](g, 0.5, 0.3) - 0.5) < 1e-9 and abs(ns["grid_z"](g, 1.5, 1.0) - 2.0) < 1e-9
    assert ns["grid_z"](g, -0.1, 0.5) is None
    v, n = ns["clamp_over_terrain"]([(0.5, 0.5, 2.0), (1.5, 0.5, 1.0)], lambda x, y: ns["grid_z"](g, x, y), 0.15)
    assert n == 1 and abs(v[0][2] - 0.65) < 1e-9 and v[1][2] == 1.0
    # a local override (max_over_terrain_local) within its radius only
    v, n = ns["clamp_over_terrain"]([(0.5, 0.5, 2.0), (0.5, 1.5, 3.0)], lambda x, y: 0.5, 0.15,
                                    [{"xy": [0.5, 0.4], "radius": 0.2, "max": 0.6}])
    assert n == 2 and abs(v[0][2] - 1.1) < 1e-9 and abs(v[1][2] - 0.65) < 1e-9
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    nx_ = ny_ = 17
    xs = [-4 + 0.5 * k for k in range(nx_)]
    zf = lambda x, y: 0.4 * y                                      # downhill to the south
    verts = [[x, y, zf(x, y)] for y in xs for x in xs]
    faces = [[j * nx_ + i, j * nx_ + i + 1, (j + 1) * nx_ + i + 1, (j + 1) * nx_ + i] for j in range(ny_ - 1) for i in range(nx_ - 1)]
    grid = {"x0": -4.0, "y0": -4.0, "nx": nx_, "ny": ny_, "cell": 0.5, "z": [v_[2] for v_ in verts]}
    scene = {"verts": verts, "faces": faces, "face_class": [0] * len(faces), "classes": ["ground"], "grid": grid,
             "overlays": {}, "curbs": [], "edging": [], "parcel": None, "points": []}
    ring = [[-1.5, -1.5], [1.5, -1.5], [1.5, 1.5], [-1.5, 1.5]]
    yard = {"items": [{"kind": "boulder", "name": "clamped", "polygon": ring, "top_z": 1.2, "max_over_terrain": 0.15},
                      {"kind": "boulder", "name": "free", "polygon": [[x_ + 0.0, y_] for x_, y_ in ring], "top_z": 1.2}],
            "face_normals": False}
    sp, yp, out = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    log = _run([ADD_SITE, blend, str(sp), str(yp), out])
    assert "dome vertices clamped to the terrain + 0.15 m" in log
    look = tmp_path / "look.py"
    look.write_text(r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Site"].objects:
    if o.type == "MESH" and o.name in ("clamped", "free"):
        out[o.name] = [list(o.matrix_world @ v.co) for v in o.data.vertices]
        out[o.name + " min_nz"] = min((o.matrix_world.to_3x3() @ p.normal).z for p in o.data.polygons)
json.dump(out, open(sys.argv[2], "w"))
""")
    _run([str(look), out, str(tmp_path / "v.json")])
    r = json.load(open(tmp_path / "v.json"))
    over_c = max(z - zf(x, y) for x, y, z in r["clamped"])
    over_f = max(z - zf(x, y) for x, y, z in r["free"])
    assert over_c <= 0.15 + 1e-5 and over_f > 0.6
    assert r["clamped min_nz"] > -1e-6                              # heights only: no face turned over


def test_boulder_has_no_undercut_and_foliage_mass(site):
    assert site["objects"]["notched"]["min_nz"] > -1e-6              # no face leans out over the foot
    assert site["objects"]["juniper"]["mat"].startswith("Foliage")
    # explicit triangles (each side quad split along its closest-z / shorter diagonal), never Blender's fixed 0-2 split
    assert site["objects"]["notched"]["nsides"] == 3 and site["objects"]["rock"]["nsides"] == 3


def test_split_quad_folds_along_the_level_diagonal():
    import ast
    src = open(ADD_SITE).read()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "split_quad")
    ns = {}
    exec(compile(ast.Module([fn], []), ADD_SITE, "exec"), ns)
    sq = ns["split_quad"]
    v = [(0, 0, 0.0), (1, 0, 1.0), (1, 1, 0.1), (0, 1, 1.0)]       # 0-2 nearly level, 1-3 level: fold along 1-3
    assert sorted(map(sorted, sq(v, [0, 1, 2, 3]))) == [[0, 1, 3], [1, 2, 3]]
    v = [(0, 0, 0.0), (1, 0, 1.0), (1, 1, 0.0), (0, 1, 0.5)]       # 0-2 level: fold along 0-2
    assert sorted(map(sorted, sq(v, [0, 1, 2, 3]))) == [[0, 1, 2], [0, 2, 3]]
    v = [(0, 0, 0.0), (2, 0, 0.0), (2.5, 1, 1.0), (0.5, 1, 1.0)]   # equal dz: the shorter diagonal (1-3)
    assert sorted(map(sorted, sq(v, [0, 1, 2, 3]))) == [[0, 1, 3], [1, 2, 3]]


def test_tread_clearance_uses_the_middle_of_the_run(tmp_path):
    """LiDAR ground over a stair is a ramp through the tread middles: a tread lifted for clearance stands `clearance` over
    the ramp at the middle of its run, not over the ramp at its back (half a riser higher)."""
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    verts = [[-2, -2, 0.0], [2, -2, 0.0], [2, 2, 2.0], [-2, 2, 2.0]]          # ramp z = 0.5 (y + 2)
    scene = {"verts": verts, "faces": [[0, 1, 2, 3]], "face_class": [0], "classes": ["ground"],
             "overlays": {}, "curbs": [], "edging": [], "parcel": None, "points": []}
    yard = {"items": [{"kind": "steps", "name": "ramp st", "line": [[0, -2], [0, 2]], "width": 1.0, "z0": -1.0,
                       "z1": -0.5, "risers": 4}]}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "i.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    _run([ADD_SITE, blend, str(sp), str(yp), out])
    (tmp_path / "look.py").write_text(INSPECT)
    _run([str(tmp_path / "look.py"), out, js])
    r = json.load(open(js))
    tops = [r["objects"][f"ramp st 0 tread {k}"]["max"][2] for k in range(4)]
    for k, t in enumerate(tops):                                  # middle of tread k at y = -1.5 + k: ramp 0.25 + 0.5 k
        assert abs(t - (0.25 + 0.5 * k + 0.03)) < 1e-3


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
    """Dry-stack: independent random course heights from a 1-D course texture along z (no regular courses), random stone
    lengths with a random stagger (1-D Voronoi along x, mean 0.375 m, randomness 0.6 -> 0.15-0.6 m), dark brown-grey
    joints (~0.08 linear) recessed 1-2 cm, no joints on the top faces (side-face mask from the normal), 12 % of the
    stones lifted x1.2 (clamped); the presentation hooks (map ranges labelled "joint" fed by "courses..." / "stones..."
    distances, "overhang shadow", "joint dark", "stone jitter") are in place; no brick."""
    mat = site["objects"]["face wall"]["mat"]
    assert "ShaderNodeTexBrick" not in site["materials"][mat]
    nodes = site["nodes"][mat]
    vor = [n for n in nodes if n["type"] == "ShaderNodeTexVoronoi"]
    assert vor and all(n["dims"] == "1D" for n in vor)
    stones = {round(n["scale"], 3) for n in vor if n["label"] == "stones"}
    assert stones == {round(1 / 0.375, 3)}                             # 0.375 m mean stones
    assert {"F1", "DISTANCE_TO_EDGE"} <= {n["feature"] for n in vor if n["label"] == "stones"}
    assert not any(n["label"].startswith("courses") for n in vor)       # courses from the texture, not a Voronoi
    assert sum(1 for n in nodes if n["type"] == "ShaderNodeTexImage" and n["label"].startswith("courses")) == 2
    assert {"joint", "overhang shadow", "joint dark", "stone jitter", "lifted stones"} <= {n["label"] for n in nodes}
    lift = [n for n in nodes if n["type"] == "ShaderNodeMix" and n["label"] == "lifted stones"]
    assert lift and abs(lift[0]["b"][0] - 1.2) < 1e-6
    assert any(n["label"] == "lifted stones" and n["type"] == "ShaderNodeMath" and abs(n["v"] - 0.88) < 1e-6 for n in nodes)
    jd = [n["b"] for n in nodes if n["label"] == "joint dark"]
    assert jd and 0.05 <= jd[0][0] <= 0.1 and jd[0][2] < jd[0][0]       # dark brown-grey
    bump = [n["distance"] for n in nodes if n["type"] == "ShaderNodeBump"]
    assert bump and 0.01 <= bump[0] <= 0.02
    assert any(n["label"] == "side faces" and abs(n["v"] - 0.5) < 1e-6 for n in nodes)   # caps carry no joints


def test_drystack_courses_are_irregular_ledgestone():
    """drystack_courses: heights within 0.04-0.12 m, mean within 5 % of 0.08, the tile closes its period exactly, and every
    1 m stretch of wall holds >= 7 courses with a height coefficient of variation >= 0.3 (a uniform draw on 0.04-0.12
    gives 0.29; equal courses 0); the course texture codes each pixel's distances to the course's joints."""
    ns = _pure({"drystack_courses", "drystack_course_pixels"})
    for seed in (0, 1, 1552, 1553, 2024):
        hs, used = ns["drystack_courses"](seed)
        assert abs(sum(hs) - 4.096) < 1e-9
        assert min(hs) >= 0.04 * 0.97 and max(hs) <= 0.12 * 1.03
        assert abs(sum(hs) / len(hs) / 0.08 - 1) <= 0.05 + 1e-9
        n = len(hs)
        for i in range(n):                                            # every 1 m window starting at a joint
            acc, win = 0.0, []
            for j in range(n):
                h = hs[(i + j) % n]
                if acc + h > 1.0:
                    break
                acc += h; win.append(h)
            m = sum(win) / len(win)
            cov = (sum((h - m) ** 2 for h in win) / (len(win) - 1)) ** 0.5 / m
            assert len(win) >= 7 and cov >= 0.3
        w, px = ns["drystack_course_pixels"](hs, 0.001, 0.25, seed=used)
        assert w == 4096 and len(px) == 4 * w
        top0, bot0 = px[0] * 0.25, px[1] * 0.25                       # first pixel: 0.5 mm above the first joint
        assert abs(bot0 - 0.0005) < 1e-6 and abs(top0 + bot0 - hs[0]) < 1e-6


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
       "overlay_faces": [{"nz": p.normal.z, "n": list(p.normal), "c": list(p.center), "smooth": p.use_smooth,
                          "z": [bpy.data.objects["concrete (draped)"].data.vertices[i].co.z for i in p.vertices]}
                         for p in bpy.data.objects["concrete (draped)"].data.polygons],
       "kinds": {o.name: o.get("site_kind") for o in bpy.data.collections["Site"].objects},
       "rock": [list(e.color[:3]) for m in bpy.data.materials if m.name.startswith("Rock") and m.node_tree
                for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeValToRGB" for e in n.color_ramp.elements]}
json.dump(out, open(sys.argv[2], "w"))
"""


def test_terrain_is_folded_creased_and_overlays_face_up(tmp_path):
    """Quads become the two triangles of their 0-2 fold, a 3 m step between neighbouring cells is a sharp
    crease with area-weighted normals, a clockwise overlay triangle is flipped normal-up and skirted (one flat-shaded
    vertical quad per outer edge, facing out, 0.10 m deep, 2 mm inside the edge), rock is warm buff."""
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
    top = [f for f in r["overlay_faces"] if abs(f["nz"]) > 0.5]
    skirt = [f for f in r["overlay_faces"] if abs(f["nz"]) < 0.01]
    assert len(top) == 1 and top[0]["nz"] > 0.99 and top[0]["smooth"]      # flipped to face up
    assert len(skirt) == 3 and not any(f["smooth"] for f in skirt)          # one skirt quad per outer edge
    for f in skirt:
        assert abs(max(f["z"]) - 0.03) < 1e-6 and abs(min(f["z"]) - (0.03 - 0.10)) < 1e-6
        out = (f["c"][0] - 0.3667) * f["n"][0] + (f["c"][1] - 0.3667) * f["n"][1]
        assert out > 0                                                         # faces away from the overlay's centre
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


DUMP = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Site"].objects:
    if o.type == "MESH":
        out[o.name] = {"v": [list(o.matrix_world @ v.co) for v in o.data.vertices],
                       "mats": [m.name for m in o.data.materials]}
json.dump(out, open(sys.argv[2], "w"))
"""


def test_rock_face_wall_exact_drape_terrain_foot_and_fixed_breakline_nodes(tmp_path):
    """Round-7 additions: a "rock" retaining wall gets the boulder sandstone; surfaces are draped on the terrain's own
    triangles (no vertex of the south half leaves its plane); a boulder with "foot": "terrain" starts at the terrain
    under each outline point; breakline nodes snapped off the regular grid are not moved by the rock-face smoothing."""
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    # 9 x 9 grid, 1 m cells, z -1.5 south of y 0 and 0 from y 0 north (the step between rows y -1 and y 0); the row y = 0
    # nodes are snapped 0.1 m north (a breakline face), so they sit off the regular grid
    n, c = 9, 1.0
    verts, z = [], []
    for j in range(n):
        for i in range(n):
            x, y = -4 + i * c, -4 + j * c
            zz = 0.0 if y >= 0 else -1.5
            verts.append([x, y + (0.1 if y == 0 else 0.0), zz]); z.append(zz)
    faces = [[j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i] for j in range(n - 1) for i in range(n - 1)]
    scene = {"verts": verts, "faces": faces, "face_class": [0] * len(faces), "classes": ["ground"], "overlays": {},
             "curbs": [], "edging": [], "parcel": None, "points": [],
             "grid": {"x0": -4.0, "y0": -4.0, "nx": n, "ny": n, "cell": c, "z": z}}
    yard = {"items": [
        {"kind": "retaining_wall", "name": "ledge", "line": [[-3, 0.1], [-1, 0.1]], "top_z": 0.05, "thickness": 0.3,
         "material": "rock", "line_is": "face", "uphill": "left"},
        {"kind": "surface", "name": "bed", "polygon": [[-3.7, -3.6], [-0.3, -3.6], [-0.3, -2.4], [-3.7, -2.4]], "lift": 0.03},
        {"kind": "boulder", "name": "slope rock", "polygon": [[1.0, -2.5], [3.0, -2.5], [3.0, 1.5], [1.0, 1.5]],
         "top_z": 0.8, "foot": "terrain"}]}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "d.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    _run([ADD_SITE, blend, str(sp), str(yp), out])
    (tmp_path / "dump.py").write_text(DUMP)
    _run([str(tmp_path / "dump.py"), out, js])
    d = json.load(open(js))
    led = [k for k in d if k.startswith("ledge")]
    assert led and all(any(m.startswith("Retaining wall (rock face)") for m in d[k]["mats"]) for k in led)
    bed = d["bed"]["v"]
    assert bed and max(abs(v[2] - (-1.47)) for v in bed) < 1e-4            # on the south plane + lift everywhere
    ring0 = d["slope rock"]["v"][:8]                                        # the outline ring (4 points + midpoints)
    foot_n = [v[2] for v in ring0 if v[1] > 1.4]                           # outline points on the upper level
    foot_s = [v[2] for v in ring0 if v[1] < -2.4]
    assert foot_n and foot_s and all(abs(z + 0.15) < 1e-4 for z in foot_n) and all(abs(z + 1.65) < 1e-4 for z in foot_s)
    # terrain: the snapped row y = 0.1 kept its place and height ('rock face' vertices: 8-neighbour range 1.5 m)
    ter = d["Terrain (LiDAR ground)"]["v"]
    row = [v for v in ter if abs(v[1] - 0.1) < 1e-4]
    assert len(row) == n and all(abs(v[2]) < 1e-6 for v in row)


TONE_LOOK = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
t = bpy.data.objects["Terrain (LiDAR ground)"]
me = t.data
out = {"attrs": {a.name: [list(d.color)[:3] for d in a.data] for a in me.color_attributes},
       "xy": [[v.co.x, v.co.y] for v in me.vertices], "mats": [m.name for m in me.materials]}
nt = me.materials[0].node_tree
mix = [n for n in nt.nodes if n.label == "rock tone per vertex"]
out["mix_inputs"] = sorted(l.from_node.attribute_name for n in mix for l in nt.links if l.to_node == n and l.from_node.bl_idname == "ShaderNodeAttribute")
out["mix_used"] = bool(mix) and any(l.from_node == mix[0] for l in nt.links)
out["ramps"] = [[list(e.color)[:3] for e in n.color_ramp.elements] for n in nt.nodes if n.bl_idname == "ShaderNodeValToRGB"]
json.dump(out, open(sys.argv[2], "w"))
"""


def test_terrain_inside_a_boulder_outline_takes_the_boulder_colours(tmp_path):
    """The LiDAR rock merge raises the terrain inside a traced boulder; where it pokes through the dome it must show the
    boulder's own colour range, not the terrain rock tone (a two-tone boulder). Vertices within 0.1 m of the outline get
    the boulder colours in rock_tone_lo / rock_tone_hi, all others the yard 'rock' tone; the rock ramp reads them."""
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    xs = [0, 1, 2, 3, 4]
    verts = [[x, y, 0.0] for y in xs for x in xs]
    faces = [[j * 5 + i, j * 5 + i + 1, (j + 1) * 5 + i + 1, (j + 1) * 5 + i] for j in range(4) for i in range(4)]
    scene = {"verts": verts, "faces": faces, "face_class": [1] * 16, "classes": ["ground", "rock"],
             "vertex_rock": [1.0] * 25, "overlays": {}, "curbs": [], "edging": [], "parcel": None, "points": []}
    rock = [[0.30, 0.225, 0.145], [0.60, 0.475, 0.34]]
    bcol = [[0.48, 0.42, 0.28], [0.76, 0.69, 0.50]]
    yard = {"items": [{"kind": "boulder", "polygon": [[0.9, 0.9], [2.1, 0.9], [2.1, 2.1], [0.9, 2.1]], "top_z": 0.6,
                       "color": bcol},
                      {"kind": "boulder", "polygon": [[2.9, 2.9], [4, 2.9], [4, 4], [2.9, 4]], "top_z": 0.5,
                       "surface": "foliage"}],                       # a foliage mass keeps the terrain rock tone
            "materials": {"rock": rock}}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "t.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps(yard))
    log = _run([ADD_SITE, blend, str(sp), str(yp), out])
    assert "4 vertices inside yard boulder outlines" in log
    (tmp_path / "look.py").write_text(TONE_LOOK)
    _run([str(tmp_path / "look.py"), out, js])
    r = json.load(open(js))
    lo, hi = r["attrs"]["rock_tone_lo"], r["attrs"]["rock_tone_hi"]
    for (x, y), a, b in zip(r["xy"], lo, hi):
        want = bcol if 0.8 <= x <= 2.2 and 0.8 <= y <= 2.2 else rock
        assert all(abs(u - v) < 1e-4 for u, v in zip(a, want[0])) and all(abs(u - v) < 1e-4 for u, v in zip(b, want[1]))
    assert r["mix_inputs"] == ["rock_tone_hi", "rock_tone_lo"] and r["mix_used"]
    assert len(r["ramps"]) == 1                                      # the ground ramp; the rock ramp is per vertex now


REF_BLEND = r"""
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
def plane(name, coll, z, half=30.0):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-half, -half, z), (half, -half, z), (half, half, z), (-half, half, z)], [], [[0, 1, 2, 3]])
    o = bpy.data.objects.new(name, me); coll.objects.link(o); return o
ref = bpy.data.collections.new("Reference data"); bpy.context.scene.collection.children.link(ref)
lab = bpy.data.collections.new("Labels"); bpy.context.scene.collection.children.link(lab)
plane("Ground (grade)", ref, -0.01)                  # build_model's plane at the model datum, above a downhill terrain
plane("Ground ortho", ref, -0.02)
t = bpy.data.curves.new("roof label", "FONT"); t.body = "F1"; lab.objects.link(bpy.data.objects.new("roof label", t))
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[1])
"""

REF_LOOK = r"""
import bpy, json, sys
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
dg = bpy.context.evaluated_depsgraph_get()
hit = bpy.context.scene.ray_cast(dg, Vector((1.0, -1.0, 60.0)), Vector((0, 0, -1)))
out = {"objs": {o.name: [o.hide_render, o.hide_viewport] for o in bpy.data.objects if o.name.startswith("Ground")},
       "colls": {c.name: [c.hide_render, c.hide_viewport] for c in bpy.data.collections},
       "hit": [hit[4].name, hit[1].z] if hit[0] else None}
json.dump(out, open(sys.argv[2], "w"))
"""


def test_terrain_hides_the_reference_grade_plane_and_qa_collections(tmp_path):
    """build_model's flat 'Ground (grade)' plane (z = model 'ground' or -0.01) covers a hillside terrain that runs below
    the datum: once add_site has built the terrain, the grade and ortho planes are hidden in renders and viewports (a
    ray cast from above meets the terrain, not the plane) and Labels / Reference data are not rendered but stay in the
    viewport."""
    blend = str(tmp_path / "ref.blend")
    (tmp_path / "ref.py").write_text(REF_BLEND)
    _run([str(tmp_path / "ref.py"), blend])
    verts = [[-5, -5, -3], [5, -5, -3], [5, 5, -1], [-5, 5, -1]]          # downhill terrain, all below z -0.01
    scene = {"verts": verts, "faces": [[0, 1, 2, 3]], "face_class": [0], "classes": ["ground"],
             "overlays": {}, "curbs": [], "edging": [], "parcel": None, "points": []}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "r.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps({"items": []}))
    log = _run([ADD_SITE, blend, str(sp), str(yp), out])
    assert "reference ground hidden ['Ground (grade)', 'Ground ortho']" in log
    (tmp_path / "look.py").write_text(REF_LOOK)
    _run([str(tmp_path / "look.py"), out, js])
    r = json.load(open(js))
    assert r["objs"] == {"Ground (grade)": [True, True], "Ground ortho": [True, True]}
    assert r["colls"]["Labels"] == [True, False] and r["colls"]["Reference data"] == [True, False]
    assert r["colls"]["Site"] == [False, False]
    assert r["hit"][0] == "Terrain (LiDAR ground)" and abs(r["hit"][1] - -2.2) < 0.05


def test_overlay_nodes_keep_draped_ground_out_of_the_cliff_smoothing():
    """overlay_nodes: the corners of every grid cell holding an overlay vertex or meeting a draped polygon are fixed (the
    Laplacian pass of smooth_face_normals must not lift a vertex whose triangles carry a draped overlay: the overlay was
    draped on the unsmoothed triangles and the terrain would poke through it); nodes away from them stay movable."""
    ns = _pure({"overlay_nodes"})
    g = {"x0": 0.0, "y0": 0.0, "nx": 6, "ny": 5, "cell": 1.0}
    m = ns["overlay_nodes"](g, [[1.5, 1.5]], [])
    M = m.reshape(5, 6)
    assert M[1, 1] and M[1, 2] and M[2, 1] and M[2, 2] and M.sum() == 4
    m2 = ns["overlay_nodes"](g, [], [[[3.2, 2.2], [3.8, 2.2], [3.8, 2.8], [3.2, 2.8]]], pad=0.0)
    M2 = m2.reshape(5, 6)
    assert M2[2, 3] and M2[3, 4] and not M2[0, 0] and M2.sum() == 4


HOUSE_CONCRETE = r"""
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
m = bpy.data.materials.new("Concrete")               # add_details' photo-measured house concrete (unlinked base)
b = m.node_tree.nodes.get("Principled BSDF"); b.inputs["Base Color"].default_value = (0.68, 0.624, 0.527, 1)
walls = bpy.data.collections.new("Walls"); bpy.context.scene.collection.children.link(walls)
me = bpy.data.meshes.new("wall GAR:front")
me.from_pydata([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)], [], [[0, 1, 2, 3]]); me.materials.append(m)
walls.objects.link(bpy.data.objects.new("wall GAR:front", me))
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[1])
"""

MAT_LOOK = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
def info(m):
    b = m.node_tree.nodes.get("Principled BSDF")
    return {"base": list(b.inputs["Base Color"].default_value)[:3], "linked": b.inputs["Base Color"].is_linked,
            "users": m.users, "tag": bool(m.get("propmodel_site")), "nodes": len(m.node_tree.nodes)}
out = {"mats": {m.name: info(m) for m in bpy.data.materials},
       "wall": bpy.data.objects["wall GAR:front"].data.materials[0].name,
       "drive": bpy.data.objects["concrete (draped)"].data.materials[0].name}
json.dump(out, open(sys.argv[2], "w"))
"""


def test_site_materials_never_take_over_a_house_material(tmp_path):
    """add_details' 'Concrete' (photo-measured house walls, unlinked base colour) shares its name with the site's
    driveway concrete: add_site must leave it untouched (same base, no links, same users) and drape the driveway in its
    own tagged 'Site Concrete'. Re-running add_site on the site blend re-uses its own material (no '.001' copy) and
    rebuilds it on a cleared node tree (same node count)."""
    blend = str(tmp_path / "house.blend")
    (tmp_path / "house.py").write_text(HOUSE_CONCRETE)
    _run([str(tmp_path / "house.py"), blend])
    verts = [[-5, -5, 0], [5, -5, 0], [5, 5, 0], [-5, 5, 0]]
    drive = {"verts": [[1, -4, 0.02], [4, -4, 0.02], [4, -1, 0.02], [1, -1, 0.02]], "tris": [[0, 1, 2], [0, 2, 3]]}
    scene = {"verts": verts, "faces": [[0, 1, 2, 3]], "face_class": [0], "classes": ["ground"],
             "overlays": {"concrete": drive}, "curbs": [], "edging": [], "parcel": None, "points": []}
    sp, yp = tmp_path / "scene.json", tmp_path / "yard.json"
    sp.write_text(json.dumps(scene))
    yp.write_text(json.dumps({"items": [], "materials": {"concrete": [[0.68, 0.55, 0.41], [0.82, 0.67, 0.51]]}}))
    (tmp_path / "look.py").write_text(MAT_LOOK)
    out1, out2 = str(tmp_path / "site1.blend"), str(tmp_path / "site2.blend")
    _run([ADD_SITE, blend, str(sp), str(yp), out1])
    _run([ADD_SITE, out1, str(sp), str(yp), out2])
    for out in (out1, out2):
        js = str(tmp_path / "m.json")
        _run([str(tmp_path / "look.py"), out, js])
        r = json.load(open(js))
        house = r["mats"]["Concrete"]
        assert all(abs(u - v) < 1e-4 for u, v in zip(house["base"], (0.68, 0.624, 0.527)))
        assert not house["linked"] and house["users"] == 1 and not house["tag"]
        assert r["wall"] == "Concrete"
        assert r["drive"] == "Site Concrete" and r["mats"]["Site Concrete"]["tag"] and r["mats"]["Site Concrete"]["linked"]
        assert not any(n.startswith("Site Concrete.") for n in r["mats"])
        if out == out1:
            n1 = r["mats"]["Site Concrete"]["nodes"]
        else:
            assert r["mats"]["Site Concrete"]["nodes"] == n1


def test_face_smoothing_leaves_the_scene_fixed_nodes_in_place(tmp_path):
    """build_site lists the nodes it capped under decks / stairs as "fixed_nodes": the steep-face Laplacian (which lifts a
    stair foot next to a boulder face by up to 0.3 m, back over the bottom tread) must not move them; the other cliff
    vertices are still smoothed."""
    blend = str(tmp_path / "empty.blend")
    (tmp_path / "empty.py").write_text(EMPTY)
    _run([str(tmp_path / "empty.py"), blend])
    c, n = 0.25, 13
    xy = [(i * c - 1.5, j * c - 1.5) for j in range(n) for i in range(n)]
    z = [2.0 if y > 0.1 else 0.0 for x, y in xy]                  # a 2 m face along y = 0.1
    verts = [[x, y, zz] for (x, y), zz in zip(xy, z)]
    faces = [[j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i] for j in range(n - 1) for i in range(n - 1)]
    fixed = [k for k, (x, y) in enumerate(xy) if x < 0.0]          # the west half: a stair foot capped by build_site
    scene = {"verts": verts, "faces": faces, "face_class": [0] * len(faces), "classes": ["ground"], "overlays": {},
             "curbs": [], "edging": [], "parcel": None, "points": [], "fixed_nodes": fixed,
             "grid": {"nx": n, "ny": n, "z": z, "x0": -1.5, "y0": -1.5, "cell": c}}
    sp, yp, out, js = tmp_path / "scene.json", tmp_path / "yard.json", str(tmp_path / "out.blend"), str(tmp_path / "c.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps({"items": []}))
    _run([ADD_SITE, blend, str(sp), str(yp), out])
    (tmp_path / "look.py").write_text(CLIFF_LOOK)
    _run([str(tmp_path / "look.py"), out, js])
    r = json.load(open(js))
    face = [k for k, (x, y) in enumerate(xy) if abs(y - 0.1) < 0.4]
    moved = lambda k: abs(r["z"][k] - z[k]) > 1e-6 or abs(r["xy"][k][0] - xy[k][0]) > 1e-6 or abs(r["xy"][k][1] - xy[k][1]) > 1e-6
    assert not any(moved(k) for k in fixed)
    assert any(moved(k) for k in face if k not in set(fixed))


def test_rubble_drystack_rounded_pillowed_graded_lift(site):
    """drystack "corner" > 0: one joint map range fed by the rounded-box distance (labelled "courses: rounded ...", so a
    presentation script rescales it by the course), "pillow" > 0 rounds every stone face towards its joints (a "pillow"
    node), "lift_range" grades the lift over the lifted share; the default wall keeps the two square joint masks."""
    nodes = site["nodes"][site["objects"]["rubble wall"]["mat"]]
    labels = [n["label"] for n in nodes]
    assert "rounded corner distance" in labels and "courses: rounded stone joint distance / mean course" in labels
    assert labels.count("joint") == 1 and "pillow" in labels and "lifted stones: grade" in labels
    stones = {round(n["scale"], 3) for n in nodes if n["type"] == "ShaderNodeTexVoronoi" and n["label"] == "stones"}
    assert stones == {round(1 / 0.375, 3)}
    plain = [n["label"] for n in site["nodes"][site["objects"]["face wall"]["mat"]]]
    assert plain.count("joint") == 2 and "pillow" not in plain and "rounded corner distance" not in plain


def test_rock_scatter_dome_stones_are_rounded(site):
    """rock_scatter "shape": "dome" + "chaikin": 2 -- a smooth-shaded dome on a corner-cut (rounded) outline, in the
    boulder stone material (not a 'Garden stone'), centred on the measured stone, 0.3 x its width above grade."""
    st = site["objects"]["round stone 1"]
    assert st["smooth"] and st["nverts"] > 100 and not st["mat"].startswith("Garden stone")
    assert abs((st["min"][0] + st["max"][0]) / 2 - 3.0) < 0.2 and abs((st["min"][1] + st["max"][1]) / 2 + 2.0) < 0.2
    assert abs(st["max"][2] - (-1.0 + 0.6 * 0.3)) < 0.02


def test_chaikin_rounds_a_polygon():
    import math
    ch = _pure({"chaikin"})["chaikin"]
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    r1 = ch(sq)
    assert len(r1) == 8 and (0.25, 0) in r1 and (0.75, 0) in r1
    r2 = ch(r1)
    assert len(r2) == 16
    turns = []
    for k in range(len(r2)):
        (ax, ay), (bx, by), (cx, cy) = r2[k - 1], r2[k], r2[(k + 1) % len(r2)]
        a1, a2 = math.atan2(by - ay, bx - ax), math.atan2(cy - by, cx - bx)
        turns.append(abs(math.degrees((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)))
    assert max(turns) < 46                                       # no 90-degree corner left


def test_foliage_bed_darkens_seen_obliquely(site):
    """surface "foliage": the bed colour x a clump mottle x a view factor mapped to [side, 1] ("foliage view")."""
    nodes = site["nodes"][site["objects"]["shrub bed"]["mat"]]
    fv = [n for n in nodes if n["label"] == "foliage view" and n["type"] == "ShaderNodeMapRange"]
    assert fv and abs(fv[0]["to"][0] - 0.2) < 1e-6 and abs(fv[0]["to"][1] - 1.0) < 1e-6
    assert any(n["label"] == "foliage clumps" and n["type"] == "ShaderNodeTexNoise" for n in nodes)
    assert any(n["type"] == "ShaderNodeMath" and abs(n.get("v", 0) - 2.0) < 1e-6 for n in nodes)   # |N.V| ^ 2


def test_box_base_z_is_absolute(site):
    """A box with "base_z" stands at that absolute height (on a deck), not on the terrain under it (z 0 here)."""
    b = site["objects"]["deck slab"]
    assert abs(b["min"][2] - 2.5) < 1e-6 and abs(b["max"][2] - 2.58) < 1e-6


TUB_LOOK = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for nm in ("Hot tub cover", "Hot tub cabinet"):
    b = bpy.data.materials[nm].node_tree.nodes["Principled BSDF"]
    key = "Specular IOR Level" if "Specular IOR Level" in b.inputs else "Specular"
    out[nm] = {"rough": b.inputs["Roughness"].default_value, "spec": b.inputs[key].default_value,
               "rgb": list(b.inputs["Base Color"].default_value)[:3]}
json.dump(out, open(sys.argv[2], "w"))
"""


def _tub_materials(tmp_path, tub, tag):
    blend = str(tmp_path / "empty.blend")
    if not os.path.exists(blend):
        (tmp_path / "empty.py").write_text(EMPTY)
        _run([str(tmp_path / "empty.py"), blend])
    scene = {"verts": [[-3, -3, 0], [3, -3, 0], [3, 3, 0], [-3, 3, 0]], "faces": [[0, 1, 2, 3]], "face_class": [0],
             "classes": ["ground"], "overlays": {}, "curbs": [], "edging": [], "parcel": None, "points": []}
    sp, yp, out, js = tmp_path / f"s{tag}.json", tmp_path / f"y{tag}.json", str(tmp_path / f"o{tag}.blend"), str(tmp_path / f"m{tag}.json")
    sp.write_text(json.dumps(scene)); yp.write_text(json.dumps({"items": [tub]}))
    _run([ADD_SITE, blend, str(sp), str(yp), out])
    (tmp_path / "tub_look.py").write_text(TUB_LOOK)
    _run([str(tmp_path / "tub_look.py"), out, js])
    return json.load(open(js))


def test_hot_tub_cover_roughness_and_specular(tmp_path):
    """hot_tub "cover_roughness" / "cover_specular" (and "roughness" / "specular" for the cabinet) set the Principled
    Roughness and Specular IOR Level of the 'Hot tub cover' / 'Hot tub cabinet' materials; without them the cover stays
    at roughness 0.6, the cabinet at 0.7, and the specular level at the Principled default."""
    base = {"kind": "hot_tub", "xy": [0, 0], "size": [1.5, 1.2, 0.9], "color": [0.01, 0.008, 0.006],
            "cover_color": [0.01, 0.008, 0.006]}
    m = _tub_materials(tmp_path, dict(base, cover_roughness=0.9, cover_specular=0.1, roughness=0.85, specular=0.2), "a")
    assert abs(m["Hot tub cover"]["rough"] - 0.9) < 1e-6 and abs(m["Hot tub cover"]["spec"] - 0.1) < 1e-6
    assert abs(m["Hot tub cabinet"]["rough"] - 0.85) < 1e-6 and abs(m["Hot tub cabinet"]["spec"] - 0.2) < 1e-6
    assert all(abs(a - b) < 1e-6 for a, b in zip(m["Hot tub cover"]["rgb"], (0.01, 0.008, 0.006)))
    d = _tub_materials(tmp_path, base, "b")
    assert abs(d["Hot tub cover"]["rough"] - 0.6) < 1e-6 and abs(d["Hot tub cabinet"]["rough"] - 0.7) < 1e-6
    assert abs(d["Hot tub cover"]["spec"] - 0.5) < 1e-6 and abs(d["Hot tub cabinet"]["spec"] - 0.5) < 1e-6   # Principled default
