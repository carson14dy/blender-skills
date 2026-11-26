"""add_details.py: exterior chimney chase to grade with procedural stone, rails that end on another rail (shared post),
panel stair sides, door sidelight / storm door, and corner boards cut round a door set at a wall corner.
Runs headless Blender through the `bpy` module in a subprocess."""
import importlib.util
import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

from propmodel.roofgeom import Wing, build, to_mesh_json

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts", "blender")

pytestmark = pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="needs the bpy module")

INSPECT = r"""
import bpy, json, re, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Details"].objects:
    if o.type != "MESH":
        continue
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    out.setdefault(re.sub(r"\.\d{3}$", "", o.name), []).append({"min": [min(v[i] for v in vs) for i in range(3)],
                                       "max": [max(v[i] for v in vs) for i in range(3)], "n": len(vs),
                                       "mat": o.data.materials[0].name if o.data.materials else None,
                                       "label": o.get("label"), "details": o.get("details")})
mats = {}
for m in bpy.data.materials:
    if m.node_tree is None:
        continue
    mats[m.name] = {"diffuse": list(m.diffuse_color)[:3],
                    "nodes": sorted(n.bl_idname for n in m.node_tree.nodes),
                    "ops": sorted(getattr(n, "operation", "") for n in m.node_tree.nodes if hasattr(n, "operation")),
                    "stone_colors": [list(c) for c in m["stone_colors"]] if "stone_colors" in m.keys() else None}
t = bpy.data.texts.get("Details notes")
json.dump({"objects": out, "materials": mats, "notes": t.as_string() if t else ""}, open(sys.argv[2], "w"))
"""


def _run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return r


@pytest.fixture(scope="module")
def house(tmp_path_factory):
    """10 x 8 m gable (walls x -5..5, y -4..4, ridge along x), a level ground grid at z -0.8 (one deep cell far away)."""
    tmp = tmp_path_factory.mktemp("entry_chase")
    w = Wing.from_dict(dict(id="M", type="gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0,
                            pitch=0.5, eave_overhang=0.5, rake_overhang=0.6))
    mj = to_mesh_json(build([w]))
    (tmp / "model.json").write_text(json.dumps(mj))
    (tmp / "data").mkdir()
    Z = np.full((40, 40), -0.8)
    Z[2, 2] = -5.0                                   # (x, y) = (-8.75, -8.75): far from the chase, must not count
    np.savez_compressed(tmp / "data" / "ground_surface.npz", Z=Z, ground=np.ones_like(Z, bool), x0=-10.0, y0=-10.0,
                        cell=0.5)
    _run([os.path.join(SCRIPTS, "build_model.py"), "--model", str(tmp / "model.json"), "--out", str(tmp / "out"),
          "--plain-ground"])
    keys = {round(x["bearing"]) % 360: f'{x["wing"]}:{x["side"]}' for x in mj["walls"]}
    return tmp, mj, keys


def _details(house, extra, tag):
    tmp, mj, _ = house
    D = {"model_json": str(tmp / "model.json"), **extra}
    (tmp / f"{tag}.json").write_text(json.dumps(D))
    r = _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"), str(tmp / f"{tag}.json"),
              str(tmp / f"{tag}.blend")])
    (tmp / "dump_entry.py").write_text(INSPECT)
    _run([str(tmp / "dump_entry.py"), str(tmp / f"{tag}.blend"), str(tmp / f"{tag}_scene.json")])
    return r.stdout, json.loads((tmp / f"{tag}_scene.json").read_text())


def test_exterior_chase_from_grade_in_coursed_stone(house):
    """A chimney whose shoulder pokes 0.10 m out of the west wall gets an exterior chase from the grade (lowest ground
    under it - 0.3 m) up to 0.02 m under the shoulder top, outer face on the shoulder's (+3 mm), 0.05 m into the wall,
    over the shoulder's extent along the wall less 3 mm at each end; material "stone" is the procedural coursed stone;
    an opening behind the chase is reported; the chase label reaches the object and the notes."""
    _, mj, keys = house
    west = keys[270]
    wall = next(x for x in mj["walls"] if f'{x["wing"]}:{x["side"]}' == west)
    x_wall = wall["bottom"][0][0]
    assert x_wall == pytest.approx(-5.0)
    dy = 1.0 if wall["bottom"][1][1] > wall["bottom"][0][1] else -1.0
    extra = {"stone": {"colors": [[190, 170, 135], [230, 212, 175]], "course": 0.12, "length": 0.4,
                       "label": "stone tone from a photo, assumed"},
             "chimneys": [{"center": [-4.6, 1.0], "size": [0.6, 1.2], "azimuth": 90, "top_z": 6.5, "material": "stone",
                           "shoulder": {"z": 6.0, "size": [1.0, 1.4]}, "label": "chimney",
                           "chase": {"bottom_z": "grade", "label": "chase projection from the shoulder, assumed"}},
                          {"center": [4.6, -1.0], "size": [0.6, 1.2], "azimuth": 90, "top_z": 6.5, "material": "stone",
                           "label": "east chimney", "chase": {"wall": keys[90], "bottom_z": -1.5, "projection": 0.4,
                                                              "u": [1.0, 2.0]}}],
             "openings": [{"wall": west, "u": (1.0 - wall["bottom"][0][1]) / dy, "sill_z": 1.0, "width": 1.0, "height": 1.0, "kind": "window",
                           "label": "west window"}]}
    out, sc = _details(house, extra, "chase")
    o = sc["objects"]
    ch = o["chimney chase"][0]
    assert ch["min"][2] == pytest.approx(-1.1, abs=1e-4)              # grade -0.8 - 0.3 (the -5.0 cell is far away)
    assert ch["max"][2] == pytest.approx(6.0 - 0.02, abs=1e-4)        # up into the shoulder, 0.02 m under its top
    assert ch["min"][0] == pytest.approx(x_wall - 0.103, abs=1e-4)    # shoulder face 0.10 m out + 3 mm
    assert ch["max"][0] == pytest.approx(x_wall + 0.05, abs=1e-4)     # 0.05 m into the wall: no slit at the face
    assert (ch["min"][1], ch["max"][1]) == pytest.approx((0.303, 1.697), abs=1e-4)   # the shoulder's 1.4 m, 3 mm in
    assert ch["mat"] == "Stone (coursed)" and ch["label"] == "chase projection from the shoulder, assumed"
    assert ch["details"] == "chimneys[0].chase"
    st = sc["materials"]["Stone (coursed)"]
    assert "ShaderNodeTexBrick" in st["nodes"] and "CROSS_PRODUCT" in st["ops"]    # courses along each face's tangent
    lo, hi = np.array(st["stone_colors"])
    assert st["diffuse"] == pytest.approx(list((lo + hi) / 2), abs=1e-4)          # flat preview = mid tone
    assert lo == pytest.approx([0.5149, 0.4020, 0.2423], abs=1e-3)                 # sRGB 190,170,135 -> linear
    assert o["chimney shoulder"][0]["mat"] == "Stone (coursed)"
    east = o["east chimney chase"][0]                                  # explicit wall, bottom, projection and span
    assert east["min"][2] == pytest.approx(-1.5) and east["max"][2] == pytest.approx(6.5 - 0.08, abs=1e-4)
    assert east["max"][0] == pytest.approx(5.4, abs=1e-4) and east["min"][0] == pytest.approx(4.95, abs=1e-4)
    warn = [ln for ln in out.splitlines() if ln.startswith("WARNING: openings[0]")]
    assert len(warn) == 1 and "chimney 0's chase" in warn[0]
    assert "chimneys[0].chase: chase projection from the shoulder, assumed" in sc["notes"]
    assert "stone: stone tone from a photo, assumed" in sc["notes"]


def test_chase_inside_wall_needs_projection(house):
    tmp, _, _ = house
    D = {"model_json": str(tmp / "model.json"),
         "chimneys": [{"center": [-4.0, 1.0], "size": [0.6, 1.2], "azimuth": 90, "top_z": 6.5,
                       "chase": {"bottom_z": -1.0}}]}
    (tmp / "bad.json").write_text(json.dumps(D))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"),
                        str(tmp / "bad.json"), str(tmp / "bad.blend")], capture_output=True, text=True, timeout=300)
    assert r.returncode != 0 and "give chase.projection" in (r.stdout + r.stderr)


def test_rail_ends_on_outer_rail_with_one_shared_post_and_panel_stair_sides(house):
    """A fence along a notch edge carried on to the outer fence line (extend_to): its cap runs to the junction, where
    exactly one rail post stands; the open notch keeps no boards. Stair sides in "panel" style are solid boards under a
    cap, running down over the stringer."""
    # deck south of the house: outer fence on the slanted south edge (6 -> 7), a slot x 1..2 open from the wall down to
    # 0.1 m short of the fence, fenced on x 1 (edge 2 -> 3) and x 2 (edge 4 -> 5)
    poly = [[-3.0, -4.0], [1.0, -4.0], [1.0, -6.3], [2.0, -6.5], [2.0, -4.0], [4.0, -4.0], [4.0, -7.0], [-3.0, -5.6]]
    dk = {"polygon": poly, "top_z": 0.0, "rail_style": "screen", "rail_height": 1.0, "post_edges": [],
          "rail_edges": [{"edge": [1, 2], "extend_to": [6, 7]}, {"edge": [3, 4], "extend_to": [6, 7]}, [6, 7]]}
    st = {"top": [-3.0, -4.6], "dir": [-1, 0], "width": 1.2, "length": 2.0, "top_z": 0.0, "bottom_z": -1.4,
          "risers": 8, "rails": ["left", "right"], "rail_style": "panel", "rail_height": 0.95}
    _, sc = _details(house, {"decks": [dk], "stairs": [st]}, "rails")
    o = sc["objects"]

    def y_fence(x):                                    # the outer fence line (4,-7) -> (-3,-5.6)
        return -7.0 + (x - 4.0) * (-5.6 + 7.0) / (-3.0 - 4.0)
    caps = o["deck 0 rail cap"]
    assert len(caps) == 3
    for x_run in (1.0, 2.0):
        cap = next(cp for cp in caps if abs((cp["min"][0] + cp["max"][0]) / 2 - x_run) < 0.1)
        # runs on to the outer fence's cap and stops on its near face (0.07 m off the line, mitred: lower corner at x+0.07)
        assert cap["min"][1] == pytest.approx(y_fence(x_run + 0.07) + 0.07 / math.cos(math.atan(0.2)), abs=1e-3)
        posts = [p for p in o["deck 0 rail post"]
                 if abs((p["min"][0] + p["max"][0]) / 2 - x_run) < 1e-3
                 and abs((p["min"][1] + p["max"][1]) / 2 - y_fence(x_run)) < 1e-3]
        assert len(posts) == 1                                               # one shared post at the junction
    assert len(o["deck 0 rail post"]) == 6            # 2 x (wall end + junction) + the outer fence's two ends
    pan = o["stair 0 rail panel"]
    assert len(pan) == 2 and not o.get("stair 0 rail balusters") and not o.get("stair 0 rail pickets")
    for p in pan:
        assert p["max"][1] - p["min"][1] == pytest.approx(0.03, abs=1e-4)  # a 3 cm board panel
        assert p["min"][2] < -1.4 + 0.2 and p["max"][2] == pytest.approx(0.95 - 0.04, abs=1e-3)
    assert len(o["stair 0 rail cap"]) == 2


def test_door_sidelight_storm_door_and_corner_board_cut(house):
    """A door hard against the end of a wall, with a sidelight toward the wall start and a storm door: the sidelight
    and its jamb lie beside the leaf, the storm frame stands proud over the leaf, and the corner board at that wall end
    keeps only the piece above the door head (none beside the door)."""
    _, mj, keys = house
    west = keys[270]
    wall = next(x for x in mj["walls"] if f'{x["wing"]}:{x["side"]}' == west)
    (x0, y0, _), (x1, y1, _) = wall["bottom"]
    L = math.hypot(x1 - x0, y1 - y0)
    dy = (y1 - y0) / L
    door = {"wall": west, "u": L - 0.07 - 0.455, "sill_z": 0.0, "width": 0.91, "height": 2.03, "kind": "door",
            "leaf_color": [110, 30, 32], "label": "entry door",
            "sidelight": {"side": "start", "width": 0.3, "color": [30, 30, 32]},
            "storm_door": {"color": [240, 240, 235]}}
    _, sc = _details(house, {"openings": [door], "foundation": {"skip": ["M"]}}, "door")
    o = sc["objects"]

    def u_of(y):
        return (y - y0) / dy
    sl = o["entry door sidelight"][0]
    us = sorted(u_of(v) for v in (sl["min"][1], sl["max"][1]))
    assert us == pytest.approx([L - 0.07 - 0.91 - 0.07 - 0.3, L - 0.07 - 0.91 - 0.07], abs=1e-4)
    sj = o["entry door sidelight jamb"][0]
    assert sorted(u_of(v) for v in (sj["min"][1], sj["max"][1])) == pytest.approx([L - 1.42, L - 1.35], abs=1e-4)
    storm = o["entry door storm door"][0]
    assert storm["min"][0] == pytest.approx(x0 - 0.07, abs=1e-4)          # 0.04 + 0.03 proud of the west wall face
    assert storm["max"][2] == pytest.approx(2.03, abs=1e-4)
    leaf = o["entry door leaf"][0]
    assert sc["materials"][leaf["mat"]]["diffuse"][0] > 3 * sc["materials"][leaf["mat"]]["diffuse"][2]   # red leaf
    end_boards = [b for b in o["corner board " + west] if max(u_of(b["min"][1]), u_of(b["max"][1])) > L - 0.2]
    assert len(end_boards) == 1 and end_boards[0]["min"][2] == pytest.approx(2.03 + 0.07, abs=1e-4)   # above the head
    start_boards = [b for b in o["corner board " + west] if min(u_of(b["min"][1]), u_of(b["max"][1])) < 0.2]
    assert len(start_boards) == 1 and start_boards[0]["min"][2] == pytest.approx(0.0, abs=1e-4)      # untouched


FACES = r"""
import bpy, json, re, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Details"].objects:
    if o.type != "MESH":
        continue
    mw = o.matrix_world
    vs = [list(mw @ v.co) for v in o.data.vertices]
    fs = [{"v": [vs[i] for i in p.vertices], "n": list((mw.to_3x3() @ p.normal).normalized())} for p in o.data.polygons]
    out.setdefault(re.sub(r"\.\d{3}$", "", o.name), []).append({"verts": vs, "faces": fs})
json.dump(out, open(sys.argv[2], "w"))
"""


def _faces(house, extra, tag):
    tmp, _, _ = house
    D = {"model_json": str(tmp / "model.json"), **extra}
    (tmp / f"{tag}.json").write_text(json.dumps(D))
    _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"), str(tmp / f"{tag}.json"),
          str(tmp / f"{tag}.blend")])
    (tmp / "dump_faces.py").write_text(FACES)
    _run([str(tmp / "dump_faces.py"), str(tmp / f"{tag}.blend"), str(tmp / f"{tag}_faces.json")])
    return json.loads((tmp / f"{tag}_faces.json").read_text())


def _poly_area(p):
    return 0.5 * abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))))


def _clip(subject, clipper):
    """Sutherland-Hodgman: convex `subject` clipped by convex `clipper` (plan [x, y] lists, either winding)."""
    if sum(clipper[i][0] * clipper[(i + 1) % len(clipper)][1] - clipper[(i + 1) % len(clipper)][0] * clipper[i][1]
           for i in range(len(clipper))) < 0:
        clipper = clipper[::-1]
    out = subject
    for i in range(len(clipper)):
        a, b = clipper[i], clipper[(i + 1) % len(clipper)]
        inside = lambda p: (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-12
        inp, out = out, []
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            if inside(q):
                if not inside(p):
                    out.append(_seg_x(p, q, a, b))
                out.append(q)
            elif inside(p):
                out.append(_seg_x(p, q, a, b))
        if not out:
            return []
    return out


def _seg_x(p, q, a, b):
    d1, d2 = (q[0] - p[0], q[1] - p[1]), (b[0] - a[0], b[1] - a[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((a[0] - p[0]) * d2[1] - (a[1] - p[1]) * d2[0]) / den
    return [p[0] + d1[0] * t, p[1] + d1[1] * t]


def _coplanar_overlaps(objs_a, objs_b, tol=0.001):
    """Area of horizontal faces of objs_a lying within tol (z) of a horizontal face of objs_b over a common footprint."""
    area = 0.0
    for oa in objs_a:
        for fa in oa["faces"]:
            if abs(fa["n"][2]) < 0.99:
                continue
            for ob in objs_b:
                for fb in ob["faces"]:
                    if abs(fb["n"][2]) < 0.99 or abs(fa["v"][0][2] - fb["v"][0][2]) > tol:
                        continue
                    area += _poly_area(_clip([v[:2] for v in fa["v"]], [v[:2] for v in fb["v"]]) or [[0, 0]])
    return area


def test_chase_top_and_ends_lie_inside_the_shoulder(house):
    """A chimney with a shoulder and an exterior chase (shoulder a hair off the wall's square, as a LiDAR-fitted
    azimuth is): the chase stops 0.02 m inside the shoulder, so no horizontal chase face is coplanar with a shoulder
    one over a common footprint (rendered as a black slot), and its end faces stand >= 2 mm inside the shoulder's."""
    extra = {"chimneys": [{"center": [-4.6, 1.0], "size": [0.6, 1.2], "azimuth": 90.06, "top_z": 6.5,
                           "material": "stone", "shoulder": {"z": 6.0, "size": [1.0, 1.4]},
                           "chase": {"bottom_z": -1.0}}]}
    f = _faces(house, extra, "chase_inside")
    chase, sh = f["chimney 0 chase"], f["chimney 0 shoulder"]
    ztop = lambda objs: max(v[2] for o in objs for v in o["verts"])
    assert ztop(chase) <= ztop(sh) - 0.01
    assert _coplanar_overlaps(chase, sh) < 1e-6
    # end planes: the shoulder's faces whose normals run along the wall (+-y here), distance of every chase vertex on
    # the matching chase end face to that plane, inside the shoulder's height range
    for sgn in (1, -1):
        sf = next(fc for fc in sh[0]["faces"] if fc["n"][1] * sgn > 0.99)
        cf = next(fc for fc in chase[0]["faces"] if fc["n"][1] * sgn > 0.99)
        n, p0 = np.array(sf["n"]), np.array(sf["v"][0])
        for v in cf["v"]:
            assert (p0 - np.array(v)) @ n >= 0.002          # inside the shoulder's end plane by >= 2 mm


def test_stair_screen_with_skirt_hangs_outside_the_stringer(house):
    """A stair side in "screen" style with a skirt: the boards hang outside the stringer (inner face 0.01 m out from
    its outer face), so it cannot cover them, and still reach nosing line - 0.12 - skirt."""
    st = {"top": [-6.0, -6.0], "dir": [-1, 0], "width": 1.2, "length": 1.5, "top_z": 0.0, "bottom_z": -1.4,
          "risers": 7, "rails": ["left"], "rail_style": {"left": "screen"}, "rail_height": 1.0, "skirt": 0.5,
          "picket_width": 0.09, "picket_gap": 0.042}
    f = _faces(house, {"stairs": [st]}, "stair_skirt")
    W, y_c = 1.2, -6.0
    # "left" looking down the stairs (west) is the south side; its stringer is the one at y_c - W / 2
    stringer = min(f["stair 0 stringer"], key=lambda o: min(v[1] for v in o["verts"]))
    str_out = y_c - min(v[1] for v in stringer["verts"])
    assert str_out == pytest.approx(W / 2, abs=1e-4)
    pk = f["stair 0 rail pickets"][0]["verts"]
    out_face = y_c - min(v[1] for v in pk)
    in_face = y_c - max(v[1] for v in pk)
    assert out_face > str_out and in_face == pytest.approx(W / 2 + 0.01, abs=1e-4)
    rise = 1.4 / 7
    drop, L = rise * 6, 1.5
    for k in range(0, len(pk), 8):                     # one 8-vertex box per board
        b = pk[k:k + 8]
        xc = sum(v[0] for v in b) / 8
        nosing = 0.0 - drop * (-6.0 - xc) / L          # rail line z over the board's centre
        assert min(v[2] for v in b) == pytest.approx(nosing - 0.12 - 0.5, abs=1e-3)
    cap = f["stair 0 rail cap"][0]["verts"]               # the cap sits centred over the boards
    assert (y_c - min(v[1] for v in cap) + y_c - max(v[1] for v in cap)) / 2 == pytest.approx((out_face + in_face) / 2, abs=1e-4)



def test_flashing_round_a_penetration_mitred_at_the_corners(house):
    """Roof edges tagged "penetration" (a chimney's headwall / sidewall edges on the roof plane) get an apron 0.10 m out
    over the roof, 4..10 mm above the facet plane, and an upstand 0.12 m up the solid's face, 4..7 mm proud of it;
    the four aprons are mitred at the corners (they tile the 0.10 m ring exactly, no horizontal face overlaps another),
    and the flashing label reaches the objects."""
    tmp, mj, _ = house
    f = max(mj["facets"], key=lambda f: abs(f["plane"][1]))       # a facet sloping in y (the gable's ridge runs along x)
    a, b, c0 = f["plane"]
    z = lambda x, y: a * x + b * y + c0
    sq = [(-1.0, 1.0), (0.0, 1.0), (0.0, 2.0), (-1.0, 2.0)]       # a 1 x 1 m solid on that facet
    sq = [(x, y if b > 0 else -y) for x, y in sq]
    mp = json.loads(json.dumps(mj))
    for k in range(4):
        p0, p1 = sq[k], sq[(k + 1) % 4]
        kind = "headwall" if abs(p0[1] - p1[1]) < 1e-9 else "sidewall"
        mp["edges"].append({"kind": kind, "facets": [f["id"]], "p0": [*p0, z(*p0)], "p1": [*p1, z(*p1)],
                            "length_m": 1.0, "penetration": "M:0"})
    (tmp / "model_pen.json").write_text(json.dumps(mp))
    D = {"model_json": str(tmp / "model_pen.json"),
         "flashing": {"color": [110, 100, 88], "label": "flashing, size and colour assumed"}}
    (tmp / "flash.json").write_text(json.dumps(D))
    _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"), str(tmp / "flash.json"),
          str(tmp / "flash.blend")])
    (tmp / "dump_faces.py").write_text(FACES)
    _run([str(tmp / "dump_faces.py"), str(tmp / "flash.blend"), str(tmp / "flash_faces.json")])
    fc = json.loads((tmp / "flash_faces.json").read_text())
    ap, upst = fc["flashing M:0 apron"][0], fc["flashing M:0 upstand"][0]
    xs, ys = [v[0] for v in ap["verts"]], [v[1] for v in ap["verts"]]
    assert (min(xs), max(xs)) == pytest.approx((-1.1, 0.1), abs=1e-4)          # 0.10 m out on every side
    assert max(ys) - min(ys) == pytest.approx(1.2, abs=1e-4)
    for v in ap["verts"]:
        assert 0.004 - 1e-4 <= v[2] - z(v[0], v[1]) <= 0.010 + 1e-4             # just above the roof plane
    tops = [fa for fa in ap["faces"] if abs(fa["n"][2]) > 0.5]                  # top and bottom faces (on the slope)
    top_area = sum(_poly_area([v[:2] for v in fa["v"]]) for fa in tops) / 2       # 4 aprons, top + bottom each
    assert len(tops) == 8 and top_area == pytest.approx(1.2 * 1.2 - 1.0, abs=1e-4)   # they tile the ring exactly
    for i, fa in enumerate(tops):                                                # no two aprons overlap in plan
        for fb in tops[i + 1:]:
            if abs(fa["n"][2] - fb["n"][2]) < 1e-6:
                assert _poly_area(_clip([v[:2] for v in fa["v"]], [v[:2] for v in fb["v"]]) or [[0, 0]]) < 1e-6
    uxs = [v[0] for v in upst["verts"]]
    assert (min(uxs), max(uxs)) == pytest.approx((-1.007, 0.007), abs=1e-4)      # 4..7 mm proud of the faces
    for v in upst["verts"]:
        assert -1e-4 <= v[2] - z(v[0], v[1]) - 0.007 <= 0.12 + 1e-4
    sc = _details(house, {}, "noflash")[1]                                         # untagged model: no flashing
    assert not any(k.startswith("flashing") for k in sc["objects"])


def test_flight_onto_a_landing_gets_carriages_not_grounded_stringers(house):
    """A flight whose foot lands on a raised landing deck (foot within 0.15 m of its polygon, top_z = bottom_z) gets
    stringers named "stair i carriage", which the site grounding step leaves alone (it snaps every "stringer" toe to the
    terrain); a flight down to the ground keeps "stair i stringer"; "foot_on_deck": false overrides the detection."""
    landing = {"polygon": [[-9.0, -7.5], [-7.4, -7.5], [-7.4, -5.5], [-9.0, -5.5]], "top_z": -1.0, "rail_edges": []}
    up = {"top": [-6.0, -6.5], "dir": [-1, 0], "width": 1.0, "length": 1.5, "top_z": 0.0, "bottom_z": -1.0,
          "risers": 6}                                   # foot at x -7.5: 0.1 m short of the landing's east edge
    down = {"top": [-8.5, -7.5], "dir": [0, -1], "width": 1.0, "length": 1.2, "top_z": -1.0, "bottom_z": -1.8,
            "risers": 5}
    _, sc = _details(house, {"decks": [landing], "stairs": [up, down]}, "landing")
    o = sc["objects"]
    assert len(o["stair 0 carriage"]) == 2 and "stair 0 stringer" not in o
    assert len(o["stair 1 stringer"]) == 2 and "stair 1 carriage" not in o
    _, sc = _details(house, {"decks": [landing], "stairs": [{**up, "foot_on_deck": False}]}, "landing_off")
    assert len(sc["objects"]["stair 0 stringer"]) == 2
