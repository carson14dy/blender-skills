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
    assert o["plain unit curb"]["mat"] == "Trim (white)" and o["plain unit glass"]["mat"] == "Glass"   # defaults


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
