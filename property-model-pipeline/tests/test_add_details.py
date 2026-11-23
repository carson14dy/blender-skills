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
                   "mat": o.data.materials[0].name if o.data.materials else None,
                   "face_mats": [[round(p.normal.z, 3), o.data.materials[p.material_index].name]
                                 for p in o.data.polygons] if o.data.materials and len(o.data.polygons) <= 32 else None}
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


def test_deck_board_ends_take_rim_colour(scene, tmp_path):
    """The end faces of the board slab sit flush over the rim's outer face: by default they take the rim material
    (no thin board-coloured line along the edges / through picket gaps); "board_ends": "boards" keeps them."""
    deck = {"polygon": [[-4, -5], [0, -5], [0, -8], [-4, -8]], "top_z": 0.0, "rail_edges": [[1, 2]],
            "rail_style": "screen", "skirt": 0.5, "rim_depth": 0.6, "post_edges": [],
            "board_color": [170, 110, 95], "rim_color": [45, 38, 30]}
    _, sc, _ = _details_run(scene, tmp_path, {"decks": [deck, {**deck, "board_ends": "boards"}]}, "board_ends")
    o = sc["objects"]
    rim_mat = o["deck 0 rim 0"]["mat"]
    for k, want_side in (("deck 0 boards", rim_mat), ("deck 1 boards", o["deck 1 boards"]["mat"])):
        fm = o[k]["face_mats"]
        assert len(fm) == 6
        caps = {m for nz, m in fm if abs(nz) > 0.9}
        sides = {m for nz, m in fm if abs(nz) < 0.1}
        assert caps == {o[k]["mat"]} and o[k]["mat"].startswith(f"{k} ")       # walking surface: board colour
        assert sides == {want_side}
    assert rim_mat.startswith("deck 0 rim ") and rim_mat != o["deck 0 boards"]["mat"]


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


WALLS_INSPECT = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Walls"].objects:
    m = o.data.materials[0]
    out[o.name] = {"mat": m.name, "nodes": sorted(n.bl_idname for n in m.node_tree.nodes),
                   "ops": sorted(getattr(n, "operation", "") for n in m.node_tree.nodes if hasattr(n, "operation"))}
json.dump(out, open(sys.argv[2], "w"))
"""


def _details_run(scene, tmp_path, extra, tag):
    """Run add_details on the fixture's model with a small details.json; return (stdout, details objects, walls)."""
    mj, D, _ = scene
    base = os.path.dirname(D["model_json"])
    det = {"model_json": D["model_json"], **extra}
    (tmp_path / f"{tag}.json").write_text(json.dumps(det))
    out = tmp_path / f"{tag}.blend"
    r = _run([os.path.join(SCRIPTS, "add_details.py"), os.path.join(base, "out", "model.blend"), str(tmp_path / f"{tag}.json"),
              str(out)])
    (tmp_path / "dump_scene.py").write_text(INSPECT)
    (tmp_path / "dump_walls.py").write_text(WALLS_INSPECT)
    _run([str(tmp_path / "dump_scene.py"), str(out), str(tmp_path / f"{tag}_scene.json")])
    _run([str(tmp_path / "dump_walls.py"), str(out), str(tmp_path / f"{tag}_walls.json")])
    return (r.stdout, json.loads((tmp_path / f"{tag}_scene.json").read_text()),
            json.loads((tmp_path / f"{tag}_walls.json").read_text()))


@pytest.mark.parametrize("style", ["lap", "vertical", "smooth"])
def test_siding_styles(scene, tmp_path, style):
    _, _, walls = _details_run(scene, tmp_path, {"siding": {"style": style, "spacing": 0.2, "color": [225, 215, 180]}},
                               f"siding_{style}")
    assert walls
    mats = {w["mat"] for w in walls.values()}
    assert mats == {f"Siding ({style})"}                       # one material on every wall
    w = next(iter(walls.values()))
    if style == "smooth":
        assert "ShaderNodeBump" not in w["nodes"]                # plain colour, no texture
    else:
        assert "ShaderNodeBump" in w["nodes"]
    if style == "vertical":                                      # grooves spaced along each wall's own tangent
        assert "CROSS_PRODUCT" in w["ops"] and "DOT_PRODUCT" in w["ops"]
    else:
        assert "CROSS_PRODUCT" not in w["ops"]


def test_downspout_wall_gap_warning_roof_drop_and_pipe_vent(scene, tmp_path):
    mj, _, _ = scene
    south = next(x for x in mj["walls"] if abs(x["bearing"] - 180) < 1)
    (x0, y0, _), (x1, y1, _) = south["bottom"]
    xm, ym = min(x0, x1) + 0.25 * abs(x1 - x0), y0 - 0.06      # 0.06 m off the south wall face, under the eave
    f = next(f for f in mj["facets"] if f["plane"][1] > 0)       # south slope
    a, b, c = f["plane"]
    extra = {"downspouts": [
        {"xy": [xm, ym], "top_z": 2.6, "bottom_z": 0.0, "path": [[xm, ym - 0.6, 2.75]]},    # on the wall
        {"xy": [xm, ym - 1.0], "top_z": 2.6, "bottom_z": 0.0},                                # free-standing pole
        {"xy": [xm, ym], "top_z": 9.0, "bottom_z": 0.0, "to_roof": True}],                    # ends on the roof below
        "roof_vents": [{"xy": [2.0, 2.5], "size": 0.1, "height": 0.3, "shape": "pipe", "label": "vent stack"}]}
    f_n = next(f for f in mj["facets"] if f["plane"][1] < 0)     # north slope for the vent
    stdout, sc, _ = _details_run(scene, tmp_path, extra, "spouts")
    warn = [l for l in stdout.splitlines() if l.startswith("WARNING: downspout")]
    assert len(warn) == 1 and warn[0].startswith("WARNING: downspout 1 ") and "1.06 m" in warn[0]
    o = sc["objects"]
    assert o["downspout 0"]["min"][2] == pytest.approx(0.0) and o["downspout 0"]["max"][2] == pytest.approx(2.6)
    assert "gutter leader 0.0" in o                              # leader from the outlet to the top of the drop
    drop = o["roof drop 2"]                                      # renamed: the site grounding leaves it alone
    assert "downspout 2" not in o
    assert drop["min"][2] == pytest.approx(a * xm + b * ym + c, abs=0.01) and drop["max"][2] == pytest.approx(9.0)
    v = o["vent stack"]
    assert v["n"] == 16                                          # 8-sided round stack
    assert v["max"][0] - v["min"][0] == pytest.approx(0.1, abs=0.002)
    zr = f_n["plane"][0] * 2.0 + f_n["plane"][1] * 2.5 + f_n["plane"][2]
    assert v["max"][2] == pytest.approx(zr + 0.3, abs=0.01)


def test_skylight_colours_curb_and_dome(scene, tmp_path):
    mj, _, _ = scene
    f_n = next(f for f in mj["facets"] if f["plane"][1] < 0)     # north slope
    a, b, c = f_n["plane"]
    nz = 1 / math.sqrt(1 + a * a + b * b)                        # vertical -> roof-normal distance

    def above(p):                                                # height above the roof plane, along its normal
        return (p[2] - (a * p[0] + b * p[1] + c)) * nz

    extra = {"skylights": [
        {"xy": [2.5, 2.0], "size": [1.0, 1.4], "curb": 0.15, "curb_color": [235, 232, 222],
         "glass_color": [55, 48, 40], "label": "flat unit"},
        {"xy": [-0.5, 2.2], "size": [1.2, 0.8], "curb": 0.2, "dome": 0.3, "frame": 0.04,
         "curb_color": [70, 60, 50], "glass_color": [55, 48, 40], "label": "dome unit"},
        {"xy": [0.5, 3.0], "size": [0.6, 0.6], "label": "plain unit"}]}
    _, sc, _ = _details_run(scene, tmp_path, extra, "skylights")
    o, mats = sc["objects"], sc["materials"]
    flat_c, flat_g = o["flat unit curb"], o["flat unit glass"]
    assert max(above(p) for p in flat_c["verts"]) == pytest.approx(0.15, abs=0.005)
    assert min(above(p) for p in flat_g["verts"]) == pytest.approx(0.15, abs=0.005)
    assert mats[flat_c["mat"]] == pytest.approx([0.831, 0.807, 0.730], abs=0.005)   # sRGB 235,232,222 -> linear
    assert mats[flat_g["mat"]] == pytest.approx([0.038, 0.030, 0.021], abs=0.003)   # sRGB 55,48,40 -> linear
    dome = o["dome unit glass"]
    assert dome["n"] == 16                                       # 4 rings, flat crown
    assert max(above(p) for p in dome["verts"]) == pytest.approx(0.5, abs=0.005)     # curb 0.2 + dome 0.3
    assert min(above(p) for p in dome["verts"]) == pytest.approx(0.2, abs=0.005)
    assert mats[o["dome unit curb"]["mat"]] != mats[flat_c["mat"]]                     # per-unit curb colour
    assert o["plain unit curb"]["mat"] == "Trim" and o["plain unit glass"]["mat"] == "Glass"   # defaults


def test_ridge_cap_follows_both_roof_planes(scene):
    mj, _, sc = scene
    caps = _objs(sc, "ridge cap")
    ridges = [e for e in mj["edges"] if e["kind"] in ("ridge", "hip") and e["length_m"] >= 0.3]
    assert len(caps) == len(ridges) >= 1
    e = next(e for e in mj["edges"] if e["kind"] == "ridge")
    zr = e["p0"][2]                                              # level ridge along x at y = 0
    cap = next(v for v in caps.values() if v["n"] == 10)         # folded strip: 5 vertices per end, no flat board
    top = max(p[2] for p in cap["verts"])
    assert top == pytest.approx(zr + 0.03, abs=0.002)            # apex 0.03 m over the ridge line
    for f in mj["facets"]:                                       # each half lies 0.03 m above its own plane
        a, b, c = f["plane"]
        s = -1 if b > 0 else 1                                    # south slope rises north: its half is at y < 0
        edge = [p for p in cap["verts"] if abs(p[1] - s * 0.15) < 1e-3]
        assert edge and max(p[2] for p in edge) == pytest.approx(a * edge[0][0] + b * s * 0.15 + c + 0.03, abs=0.002)
    assert cap["max"][2] - cap["min"][2] < 0.15                  # follows the 6/12 slopes, about 0.11 m tall


def test_ridge_cap_mesh_normals_and_one_sided_edge():
    import ast
    src = open(os.path.join(SCRIPTS, "add_details.py")).read()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "ridge_cap_mesh")
    import bpy  # noqa: F401                                     # bpy ships mathutils
    from mathutils import Vector
    ns = {"Vector": Vector}
    exec(compile(ast.Module([node], []), "ridge_cap_mesh", "exec"), ns)
    planes = {"S": {"plane": [0.0, 0.5, 5.0]}, "N": {"plane": [0.0, -0.5, 5.0]}}
    v, f = ns["ridge_cap_mesh"]({"p0": [0, 0, 5], "p1": [4, 0, 5], "facets": ["S", "N"]}, planes)
    tops = [f[0], f[1]]
    for face in tops:                                            # top faces point up (outward winding)
        a, b, c = (v[i] for i in face[:3])
        assert (b - a).cross(c - b).z > 0
    v1, _ = ns["ridge_cap_mesh"]({"p0": [0, 0, 5], "p1": [4, 0, 5], "facets": ["S"]}, planes)
    assert max(p.z for p in v1 if p.y > 0.1) == pytest.approx(5.03)          # no facet named: that side stays level
    assert ns["ridge_cap_mesh"]({"p0": [0, 0, 5], "p1": [0, 0, 6], "facets": []}, planes) is None


ROOF_INSPECT = r"""
import bpy, json, sys
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {"mats": {}}
for o in bpy.data.collections["Roof facets"].objects:
    m = o.data.materials[0]
    nt = m.node_tree
    res = {"name": m.name}
    surf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial").inputs["Surface"].links[0].from_node
    res["out"] = surf.bl_idname
    if surf.bl_idname == "ShaderNodeMixShader":
        fac = surf.inputs["Fac"].links[0].from_node
        res["fac"] = [fac.bl_idname, getattr(fac, "operation", "")]
        res["fac_src"] = fac.inputs[0].links[0].from_node.inputs[0].links[0].from_socket.name
        res["top"] = surf.inputs[1].links[0].from_node.bl_idname
        und = surf.inputs[2].links[0].from_node
        res["under_rgb"] = list(und.inputs["Base Color"].default_value)[:3]
        res["under_has_bump"] = bool(und.inputs["Normal"].links)
    out["mats"][o.name] = res
# functional check of the underside switch in Cycles: emission red on top, green underneath, seen from above and below
m = bpy.data.collections["Roof facets"].objects[0].data.materials[0]
mix = m.node_tree.nodes.get("Roof top / underside")
if mix is not None:
    nt = m.node_tree
    for k, c in ((1, (1, 0, 0, 1)), (2, (0, 1, 0, 1))):
        e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = c; e.inputs["Strength"].default_value = 1
        nt.links.new(e.outputs[0], mix.inputs[k])
    sc = bpy.context.scene
    keep = set(bpy.data.collections["Roof facets"].objects[:1])
    for o in sc.objects:
        o.hide_render = o not in keep and o.type not in ("LIGHT", "CAMERA")   # the facet alone (no labels / curves)
    roof = bpy.data.collections["Roof facets"].objects[0]
    big = max(roof.data.polygons, key=lambda p: p.area)                # a point on the sheet (not in a roof opening)
    ctr = roof.matrix_world @ big.center
    cd = bpy.data.cameras.new("t"); cam = bpy.data.objects.new("t", cd); sc.collection.objects.link(cam); sc.camera = cam
    cd.lens = 400
    sc.render.engine = "CYCLES"; sc.cycles.samples = 1; sc.render.resolution_x = sc.render.resolution_y = 8
    sc.view_settings.view_transform = "Standard"
    for tag, dz in (("above", 6.0), ("below", -6.0)):
        cam.location = ctr + Vector((0.3, 0.2, dz))
        cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = sys.argv[2] + f".{tag}.png"
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(sc.render.filepath)
        px = list(im.pixels[:]); n = len(px) // 4
        out[tag] = [sum(px[i * 4 + c] for i in range(n)) / n for c in range(3)]
json.dump(out, open(sys.argv[2], "w"))
"""


def test_roof_underside_renders_as_soffit(scene, tmp_path):
    """The roof sheet seen from below (deep rake / eave overhang) gets a light soffit BSDF, the top keeps shingles."""
    mj, D, _ = scene
    det = os.path.join(os.path.dirname(D["model_json"]), "detailed.blend")
    (tmp_path / "roof.py").write_text(ROOF_INSPECT)
    _run([str(tmp_path / "roof.py"), det, str(tmp_path / "roof.json")])
    r = json.loads((tmp_path / "roof.json").read_text())
    assert r["mats"]
    for res in r["mats"].values():
        assert res["out"] == "ShaderNodeMixShader"                     # top / underside branch on every roof facet
        assert res["fac"] == ["ShaderNodeMath", "LESS_THAN"] and res["fac_src"] == "True Normal"
        assert res["top"] == "ShaderNodeBsdfPrincipled" and not res["under_has_bump"]
        assert res["under_rgb"] == pytest.approx([0.8, 0.8, 0.77], abs=0.005)   # default soffit colour
    assert r["above"][0] > 0.9 and r["above"][1] < 0.1                  # seen from above: the shingle (top) branch
    assert r["below"][1] > 0.9 and r["below"][0] < 0.1                  # seen from below: the soffit branch
    # opt out: "roof": {"underside": false} leaves the bare sheet
    _, _, _ = _details_run(scene, tmp_path, {"roof": {"underside": False}}, "no_under")
    _run([str(tmp_path / "roof.py"), str(tmp_path / "no_under.blend"), str(tmp_path / "roof2.json")])
    r2 = json.loads((tmp_path / "roof2.json").read_text())
    assert all(res["out"] == "ShaderNodeBsdfPrincipled" for res in r2["mats"].values())


def test_wall_points_follow_the_wall(scene, tmp_path):
    """Beam ends, ceiling / deck vertices and downspout points given as wall points land on the wall line in model.json."""
    mj, _, _ = scene
    south = next(x for x in mj["walls"] if abs(x["bearing"] - 180) < 1)
    key = f'{south["wing"]}:{south["side"]}'
    (x0, y0, _), (x1, y1, _) = south["bottom"]
    L = math.hypot(x1 - x0, y1 - y0)
    dx, dy = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = math.sin(math.radians(south["bearing"])), math.cos(math.radians(south["bearing"]))

    def on(u, off=0.0):
        return x0 + dx * u + nx * off, y0 + dy * u + ny * off
    extra = {
        "beams": [{"name": "rim on wall", "p0": {"wall": key, "u": 1.0, "offset": 0.06, "z": 2.4},
                   "p1": {"wall": key, "u": -1.0, "offset": 0.06, "z": 2.4}, "size": [0.12, 0.3]}],
        "ceilings": [{"polygon": [{"wall": key, "u": 0.0}, {"wall": key, "u": "end"}, [x1 + nx * 1.0, y1 + ny * 1.0],
                                  [x0 + nx * 1.0, y0 + ny * 1.0]], "z": 2.2}],
        "downspouts": [{"xy": {"wall": key, "u": 2.0, "offset": 0.06}, "top_z": 2.5, "bottom_z": 0.0,
                        "path": [{"wall": key, "u": 2.0, "offset": 0.5, "z": 2.7}]}],
    }
    stdout, sc, _ = _details_run(scene, tmp_path, extra, "wallpts")
    assert "WARNING: downspout" not in stdout                    # the wall point sits on the wall face
    o = sc["objects"]
    rim = o["rim on wall"]
    ends = sorted({(round(p[0], 3), round(p[1], 3)) for p in rim["verts"] if abs(p[2] - 2.4) < 1e-4})
    mid = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in (ends[:2], ends[2:])]
    want = sorted([on(1.0, 0.06), on(L - 1.0, 0.06)])
    for m_, w_ in zip(sorted(mid), want):
        assert m_ == pytest.approx(w_, abs=0.01)                 # beam axis on the wall line, 0.06 m proud, 1 m in
    ce = o["porch ceiling 0"]
    got = sorted((round(p[0], 3), round(p[1], 3)) for p in ce["verts"])
    for w_ in (on(0.0), on(L)):
        assert any(math.hypot(g[0] - w_[0], g[1] - w_[1]) < 1e-3 for g in got)
    ds = o["downspout 0"]
    cx, cy = (ds["min"][0] + ds["max"][0]) / 2, (ds["min"][1] + ds["max"][1]) / 2
    assert (cx, cy) == pytest.approx(on(2.0, 0.06), abs=1e-3)
    assert "gutter leader 0.0" in o


def test_roof_well_liners_and_colour_labels(scene, tmp_path):
    """Liner walls round a roof opening run from just under the roof plane down to bottom_z (no roof below), outside
    the opening; top-level colour provenance lands in the notes text."""
    mj, _, _ = scene
    f = next(f for f in mj["facets"] if f["plane"][1] > 0)       # south slope (holds the opening)
    a, b, c = f["plane"]
    hole = [[1.0, -2.6], [2.2, -2.6], [2.2, -1.2], [1.0, -1.2]]
    extra = {"roof_wells": [{"polygon": hole, "bottom_z": 0.5, "thickness": 0.1, "color": [40, 35, 30],
                             "label": "bay liner, assumed"}],
             "trim_color": [232, 228, 205], "color_labels": {"trim_color": "photo cream, measured"}}
    stdout, sc, _ = _details_run(scene, tmp_path, extra, "wells")
    w = sc["objects"]["roof well 0"]
    assert w["n"] == 32                                          # 4 slabs x 8 corners
    assert w["min"][2] == pytest.approx(0.48, abs=1e-4)          # bottom_z - 0.02 (into the floor)
    assert w["min"][0] == pytest.approx(1.0 - 0.105, abs=1e-3) and w["max"][0] == pytest.approx(2.2 + 0.105, abs=1e-3)
    assert w["min"][1] == pytest.approx(-2.6 - 0.105, abs=1e-3) and w["max"][1] == pytest.approx(-1.2 + 0.105, abs=1e-3)
    top = max(a * 2.305 + b * -1.095 + c, a * 0.895 + b * -1.095 + c) - 0.01
    assert w["max"][2] == pytest.approx(top, abs=1e-3)          # follows the roof plane over the opening
    assert sc["materials"][w["mat"]] == pytest.approx([0.021, 0.017, 0.015], abs=0.003)
    assert "details notes: 2 labelled entries, 1 caveats" in stdout     # colour label listed, not flagged


def test_opening_frame_inside_uses_the_outer_frame_size(scene, tmp_path):
    """frame_inside: sill_z / width / height are the outer frame (as a photo measures them); the default keeps the
    frame bars outside the glazed opening. Mullion fractions are of the outer width; a door has no sill bar."""
    mj, _, _ = scene
    south = next(x for x in mj["walls"] if abs(x["bearing"] - 180) < 1)
    key = f'{south["wing"]}:{south["side"]}'
    (x0, y0, _), (x1, y1, _) = south["bottom"]
    L = math.hypot(x1 - x0, y1 - y0)
    dx, dy = (x1 - x0) / L, (y1 - y0) / L

    def along(p):
        return (p[0] - x0) * dx + (p[1] - y0) * dy
    extra = {"openings": [
        {"wall": key, "u": 3.0, "sill_z": 0.5, "width": 3.0, "height": 1.75, "frame": 0.08, "kind": "window",
         "mullions": [0.5], "frame_inside": True, "label": "inside win"},
        {"wall": key, "u": 7.0, "sill_z": 0.5, "width": 1.0, "height": 1.0, "frame": 0.08, "kind": "window",
         "label": "outside win"},
        {"wall": key, "u": 5.2, "sill_z": 0.0, "width": 0.9, "height": 2.0, "frame": 0.08, "kind": "door",
         "frame_inside": True, "label": "inside door"}]}
    _, sc, _ = _details_run(scene, tmp_path, extra, "frame_inside")
    o = sc["objects"]

    def span(prefix):
        parts = [v for k, v in o.items() if k.startswith(prefix)]
        vs = [p for v in parts for p in v["verts"]]
        return (min(p[2] for p in vs), max(p[2] for p in vs), min(along(p) for p in vs), max(along(p) for p in vs))
    z0, z1, u0, u1 = span("inside win")
    assert (z0, z1) == pytest.approx((0.5, 2.25), abs=1e-4)      # sill bottom .. head top = the given outer size
    assert (u0, u1) == pytest.approx((1.5, 4.5), abs=1e-4)
    leaf = o["inside win leaf"]
    assert (leaf["min"][2], leaf["max"][2]) == pytest.approx((0.58, 2.17), abs=1e-4)
    mu = o["inside win mullion"]
    assert sum(along(p) for p in mu["verts"]) / len(mu["verts"]) == pytest.approx(3.0, abs=1e-4)   # 0.5 of the outer width
    z0, z1, u0, u1 = span("outside win")
    assert (z0, z1) == pytest.approx((0.42, 1.58), abs=1e-4)     # default: frame outside the opening
    assert (u0, u1) == pytest.approx((6.42, 7.58), abs=1e-4)
    z0, z1, u0, u1 = span("inside door")
    assert (z0, z1) == pytest.approx((0.0, 2.0), abs=1e-4) and (u0, u1) == pytest.approx((4.75, 5.65), abs=1e-4)
    assert "inside door sill" not in o


GLASS_INSPECT = r"""
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Details"].objects:
    if o.name.endswith(" glass") and o.data.materials:
        b = o.data.materials[0].node_tree.nodes.get("Principled BSDF")
        out[o.name] = [b.inputs["Emission Strength"].default_value, list(b.inputs["Emission Color"].default_value)[:3]]
json.dump(out, open(sys.argv[2], "w"))
"""


def test_lantern_light_style(scene, tmp_path):
    """lights "style": "lantern": back plate, arm, body (cap, corner posts, bottom) and glass, the body centred at z and
    `arm` m off the plate, body / glass in their own colours, optional glass emission; the default style is unchanged."""
    mj, _, _ = scene
    south = next(x for x in mj["walls"] if abs(x["bearing"] - 180) < 1)
    key = f'{south["wing"]}:{south["side"]}'
    (x0, y0, _), (x1, y1, _) = south["bottom"]
    L = math.hypot(x1 - x0, y1 - y0)
    extra = {"lights": [
        {"wall": key, "u": 2.0, "z": 1.8, "style": "lantern", "size": [0.2, 0.4, 0.18], "arm": 0.05,
         "color": [45, 40, 35], "glass_color": [45, 40, 35], "label": "garage lantern"},
        {"wall": key, "u": 4.0, "z": 1.8, "style": "lantern", "glass_color": [200, 190, 170], "emission": 0.1},
        {"wall": key, "u": 6.0, "z": 1.8}]}
    _, sc, _ = _details_run(scene, tmp_path, extra, "lanterns")
    o, mats = sc["objects"], sc["materials"]
    assert {"light 0 plate", "light 0 arm", "light 0 body", "light 0 glass"} <= set(o)
    assert "light 0 shade" not in o
    body, glass = o["light 0 body"], o["light 0 glass"]
    assert (body["min"][2], body["max"][2]) == pytest.approx((1.6, 2.0), abs=1e-4)          # centred at z, 0.4 tall
    out = [-(p - y0) for p in (body["min"][1], body["max"][1])]                         # outward = -y on a south wall
    assert sorted(out) == pytest.approx([0.07, 0.27], abs=1e-4)      # plate 0.02 + arm 0.05, depth 0.18 + cap lip 0.02
    xc = x0 + (x1 - x0) * 2.0 / L
    assert (body["min"][0], body["max"][0]) == pytest.approx((xc - 0.12, xc + 0.12), abs=1e-4)   # 0.2 wide + cap lips
    assert glass["min"][2] > 1.6 and glass["max"][2] < 2.0                              # glass between bottom and cap
    assert mats[body["mat"]] == pytest.approx([0.0262, 0.0212, 0.0168], abs=0.0005)     # sRGB 45,40,35 -> linear
    assert mats[glass["mat"]] == pytest.approx([0.0262, 0.0212, 0.0168], abs=0.0005)
    assert o["light 1 body"]["mat"] == "Light fixture (black)"                          # default body colour
    (tmp_path / "glass.py").write_text(GLASS_INSPECT)
    _run([str(tmp_path / "glass.py"), str(tmp_path / "lanterns.blend"), str(tmp_path / "glass.json")])
    g = json.loads((tmp_path / "glass.json").read_text())
    assert g["light 1 glass"][0] == pytest.approx(0.1) and g["light 1 glass"][1][0] > g["light 1 glass"][1][2]  # warm
    assert g["light 0 glass"][0] == pytest.approx(0.0)                                  # unlit by default
    assert {"light 2 plate", "light 2 arm", "light 2 shade"} <= set(o)                  # default style: plate/arm/shade
    assert o["light 2 shade"]["mat"] == "Light fixture (black)"


def test_gutters_inside_the_fitted_eave_line(scene, tmp_path):
    """gutters.position "inside": an eave line fitted to LiDAR is the gutter lip, so the gutter's front face lies on the
    eave line (nothing beyond it), its top follows the roof plane 8 mm above it, and fascia / soffit move in by depth.
    The default ("outside") hangs the gutter outside the line, as before."""
    mj, _, _ = scene
    eaves = {i: e for i, e in enumerate(mj["edges"]) if e["kind"] == "eave" and e["length_m"] >= 1.0
             and abs(e["p0"][0] - e["p1"][0]) > 1.0}                   # level eaves along x
    assert eaves
    facets = {f["id"]: f for f in mj["facets"]}

    def out_dist(i, p):                                                # metres outside eave i (+ = away from its facet)
        e = eaves[i]
        a, b, _ = facets[e["facets"][0]]["plane"]
        s = -1 if b > 0 else 1                                         # a slope rising north drains south (-y)
        return (p[1] - e["p0"][1]) * s

    _, out_sc, _ = _details_run(scene, tmp_path, {}, "gut_out")
    _, in_sc, _ = _details_run(scene, tmp_path, {"gutters": {"position": "inside", "depth": 0.13, "height": 0.12}},
                               "gut_in")
    seen = 0
    for i, e in eaves.items():
        go, gi = out_sc["objects"].get(f"gutter {i}"), in_sc["objects"].get(f"gutter {i}")
        if go is None:                                                 # hole edges carry no gutter
            assert gi is None
            continue
        seen += 1
        assert max(out_dist(i, p) for p in go["verts"]) == pytest.approx(0.135, abs=0.002)
        assert max(out_dist(i, p) for p in gi["verts"]) == pytest.approx(0.0, abs=1e-4)
        assert min(out_dist(i, p) for p in gi["verts"]) == pytest.approx(-0.13, abs=1e-4)
        a, b, c = facets[e["facets"][0]]["plane"]
        tops = [p for p in gi["verts"] if p[2] > e["p0"][2] - 0.05]
        assert len(tops) == 4 and all(p[2] - (a * p[0] + b * p[1] + c) == pytest.approx(0.008, abs=1e-4) for p in tops)
        assert gi["min"][2] == pytest.approx(e["p0"][2] - 0.12, abs=1e-4)
        fo, fi = out_sc["objects"][f"fascia {i}"], in_sc["objects"][f"fascia {i}"]
        assert max(out_dist(i, p) for p in fi["verts"]) == pytest.approx(max(out_dist(i, p) for p in fo["verts"]) - 0.13,
                                                                          abs=1e-4)
        so, si = out_sc["objects"].get(f"soffit {i}"), in_sc["objects"].get(f"soffit {i}")
        if so:
            assert max(out_dist(i, p) for p in si["verts"]) == pytest.approx(-0.16, abs=1e-4)
            assert min(out_dist(i, p) for p in si["verts"]) == pytest.approx(min(out_dist(i, p) for p in so["verts"]),
                                                                              abs=1e-4)   # still ends on the wall face
    assert seen >= 1
    with pytest.raises(AssertionError, match="gutters.position"):     # a typo fails loudly, no silent default
        _details_run(scene, tmp_path, {"gutters": {"position": "under"}}, "gut_bad")
