"""add_details.py: "void" openings cut out of the model walls (an open porch recess), eaves without a boxed soffit
(soffits.skip_facets), per-opening frame_color, the default trim material name, and a fence that ends on another fence
(a T-join: cap mitred onto the other cap's face, boards stopped at the shared post).
Runs headless Blender through the `bpy` module in a subprocess."""
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
import bpy, json, re, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {"details": {}, "walls": {}}
for o in bpy.data.collections["Details"].objects:
    if o.type != "MESH":
        continue
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    out["details"].setdefault(re.sub(r"\.\d{3}$", "", o.name), []).append(
        {"min": [min(v[i] for v in vs) for i in range(3)], "max": [max(v[i] for v in vs) for i in range(3)],
         "mat": o.data.materials[0].name if o.data.materials else None})
for o in bpy.data.collections["Walls"].objects:
    mw = o.matrix_world
    out["walls"][o.name] = {"faces": [[list(mw @ o.data.vertices[i].co) for i in p.vertices] for p in o.data.polygons],
                            "area": sum(p.area for p in o.data.polygons), "voids": o.get("voids"),
                            "mats": [m.name for m in o.data.materials]}
out["gutters"] = {o.name: [[list(o.matrix_world @ p.center), o.data.materials[p.material_index].name] for p in o.data.polygons]
                  for o in bpy.data.collections["Details"].objects if o.name.startswith("gutter ")}
out["fnd"] = {o.name: [list(o.matrix_world @ v.co) for v in o.data.vertices]
              for o in bpy.data.collections["Details"].objects if o.name.startswith("foundation")}
out["materials"] = {m.name: list(m.diffuse_color)[:3] for m in bpy.data.materials}
json.dump(out, open(sys.argv[2], "w"))
"""


def _run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return r


@pytest.fixture(scope="module")
def house(tmp_path_factory):
    """10 x 8 m gable (walls x -5..5, y -4..4, ridge along x, plates 3.0, pitch 0.5, gables E / W up to 5.0)."""
    tmp = tmp_path_factory.mktemp("porch")
    w = Wing.from_dict(dict(id="M", type="gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0,
                            pitch=0.5, eave_overhang=0.5, rake_overhang=0.3))
    mj = to_mesh_json(build([w]))
    (tmp / "model.json").write_text(json.dumps(mj))
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
    (tmp / "dump_porch.py").write_text(INSPECT)
    _run([str(tmp / "dump_porch.py"), str(tmp / f"{tag}.blend"), str(tmp / f"{tag}_scene.json")])
    return r.stdout, json.loads((tmp / f"{tag}_scene.json").read_text())


def f_quads(verts):
    """foundation strips are built as separate quads, 4 vertices each"""
    return [verts[k:k + 4] for k in range(0, len(verts), 4)]


def lin(c):
    return [(v / 255 / 12.92) if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]


def _wall(mj, key):
    return next(x for x in mj["walls"] if f'{x["wing"]}:{x["side"]}' == key)


def test_void_openings_cut_the_wall_foundation_and_corner_boards(house):
    """A porch recess at the SW corner: a void on the south wall (u 0..2, z 0..2.4) and one on the west gable wall
    reaching past its sloped top. Both walls lose exactly the hole (no face inside it), keep the header above and the
    strip below, and keep their material; the foundation strip and both corner boards at that corner stop at the
    hole (cut down to its sill, no frame margin); no leaf / frame objects are made; where the hole lies inside the wall
    the area cut is its width x height (what the report deducts)."""
    _, mj, keys = house
    south, west = keys[180], keys[270]
    ws, ww = _wall(mj, south), _wall(mj, west)
    (sx0, sy0, _), (sx1, sy1, _) = ws["bottom"]
    s_start_west = sx0 < sx1                                   # which end of the south wall is the SW corner
    u_sw = 0.0 if s_start_west else math.hypot(sx1 - sx0, sy1 - sy0)
    (wx0, wy0, _), (wx1, wy1, _) = ww["bottom"]
    Lw = math.hypot(wx1 - wx0, wy1 - wy0)
    u_w_sw = 0.0 if wy0 < wy1 else Lw                          # u of the SW corner on the west wall
    voids = [{"wall": south, "u": abs(u_sw - 1.0), "sill_z": 0.0, "width": 2.0, "height": 2.4, "kind": "void",
              "label": "porch recess (assumed)"},
             {"wall": west, "u": abs(u_w_sw - 1.5), "sill_z": 0.0, "width": 3.0, "height": 6.0, "kind": "void",
              "label": "porch side open"}]
    out, sc = _details(house, {"openings": voids, "foundation": {"default_reveal": 0.4}}, "voids")
    assert "void(s) cut" in out
    W = sc["walls"]
    s_ob, w_ob = W[f"Wall {south.replace(':', ' ')}"], W[f"Wall {west.replace(':', ' ')}"]
    assert s_ob["voids"] == "openings[0]" and w_ob["voids"] == "openings[1]"
    assert s_ob["mats"] and s_ob["mats"] == w_ob["mats"]                       # siding kept
    # south wall: 10 x 3 m, minus 2 x 2.4
    assert s_ob["area"] == pytest.approx(10 * 3.0 - 4.8, abs=1e-3)
    for f in s_ob["faces"]:                                                    # nothing inside the hole
        cx = sum(p[0] for p in f) / len(f)
        cz = sum(p[2] for p in f) / len(f)
        assert not (-5.0 + 1e-3 < cx < -3.0 - 1e-3 and 1e-3 < cz < 2.4 - 1e-3)
    header = [f for f in s_ob["faces"] if max(p[0] for p in f) <= -3.0 + 1e-6 and min(p[2] for p in f) >= 2.4 - 1e-6]
    assert header and max(p[2] for f in header for p in f) == pytest.approx(3.0, abs=1e-6)   # header up to the plate
    # west gable (8 m wide, plate 3.0, apex 5.0): area 8*3 + 8*2/2 = 32; the hole is cut up to the sloped top
    gable = 8 * 3.0 + 0.5 * 8 * 2.0
    top_at = [3.0 + 0.5 * u for u in (0.0, 3.0)]                               # roof line over the hole's sides
    cut = 0.5 * 3.0 * (top_at[0] + top_at[1])                                  # whole height over u 0..3
    assert w_ob["area"] == pytest.approx(gable - cut, abs=1e-3)
    assert all(min(p[1] for p in f) >= -4.0 + 3.0 - 1e-6 for f in w_ob["faces"])   # nothing left at y -4..-1
    # no leaf / frame for a void, and the trim stops at the hole
    d = sc["details"]
    assert not any(k.startswith("porch recess") or k.startswith("porch side") for k in d)
    for wall_key, inside in ((south, lambda v: v[0] < -3.0 - 1e-6), (west, lambda v: v[1] < -1.0 - 1e-6)):
        f = sc["fnd"][f"foundation {wall_key}"]
        assert max(v[2] for v in f) == pytest.approx(0.4, abs=1e-6)            # 0.4 reveal elsewhere
        over = [q for q in f_quads(f) if all(inside(v) for v in q)]
        assert over and all(v[2] <= 0.0 + 1e-6 for q in over for v in q)       # cut down to the sill there
    sw_boards = [b for k in (f"corner board {south}", f"corner board {west}") for b in d.get(k, [])
                 if b["min"][0] < -4.8 and b["min"][1] < -3.8]
    assert sw_boards and all(b["min"][2] >= 2.4 - 1e-6 for b in sw_boards)     # only above the south hole
    assert not [b for b in d.get(f"corner board {west}", []) if b["min"][1] < -3.8]   # west hole runs to the top


def test_soffit_skip_facets_frame_color_and_trim_name(house):
    """soffits.skip_facets: that facet's eave keeps fascia and gutter but gets no boxed soffit (its roof underside is
    the soffit); other eaves keep theirs. frame_color paints one opening's frame bars and mullions, leaving the
    window-frame default on the others. The default trim material is "Trim". corner_boards.skip drops one wall end's
    board only."""
    tmp, mj, keys = house
    south = keys[180]
    eaves = [(i, e) for i, e in enumerate(mj["edges"]) if e["kind"] == "eave"]
    assert len(eaves) == 2
    skip_i, skip_e = next((i, e) for i, e in eaves if e["p0"][1] < 0)          # the south eave
    keep_i = next(i for i, e in eaves if i != skip_i)
    ops = [{"wall": south, "u": 3.0, "sill_z": 1.0, "width": 2.0, "height": 1.2, "kind": "window",
            "mullions": [0.5], "frame_color": [221, 212, 176], "label": "khaki frame"},
           {"wall": south, "u": 7.0, "sill_z": 1.0, "width": 1.0, "height": 1.2, "kind": "window", "label": "plain"},
           {"wall": south, "u": 5.0, "sill_z": 0.0, "width": 0.9, "height": 2.0, "kind": "door", "label": "door"}]
    D = {"soffits": {"skip_facets": [skip_e["facets"][0]], "label": "raked soffit (assumed)"},
         "window_frame_color": [80, 68, 52], "openings": ops, "corner_boards": {"skip": [f"{south}:start"]}}
    _, sc = _details(house, D, "soffit_skip")
    d, mats = sc["details"], sc["materials"]
    assert f"soffit {skip_i}" not in d and f"soffit {keep_i}" in d
    assert f"fascia {skip_i}" in d and f"gutter {skip_i}" in d
    k = d["khaki frame head"][0]["mat"]
    assert d["khaki frame mullion"][0]["mat"] == k and d["khaki frame jamb L"][0]["mat"] == k
    assert mats[k] == pytest.approx(lin([221, 212, 176]), abs=1e-4)
    assert d["khaki frame leaf"][0]["mat"] == "Glass"                          # the glazing keeps its own colour
    assert d["plain head"][0]["mat"] == "Window frames"
    assert mats["Window frames"] == pytest.approx(lin([80, 68, 52]), abs=1e-4)
    assert d["door head"][0]["mat"] == "Trim" and "Trim (white)" not in mats
    # corner_boards.skip: the south wall's start end has no board, its far end and the other walls keep theirs
    ws = _wall(mj, south)
    (x0, y0, _), (x1, y1, _) = ws["bottom"]
    ends = [b for b in d[f"corner board {south}"]]
    assert ends and all(min(abs(b["min"][0] - x0), abs(b["max"][0] - x0)) > 0.5 for b in ends)
    assert any(min(abs(b["min"][0] - x1), abs(b["max"][0] - x1)) < 0.05 for b in ends)
    assert len([k for k in d if k.startswith("corner board")]) == 4


@pytest.mark.parametrize("position", ["inside", "outside"])
def test_gutter_trough_darkens_the_top_face_only(house, position):
    """gutters.trough: each eave gutter's upward (top) face takes material "Gutter trough" = trough x the gutter colour,
    every other face keeps "Gutter"; without "trough" the gutter is one material (unchanged default)."""
    D = {"gutters": {"position": position, "trough": 0.5}, "gutter_color": [221, 212, 176]}
    _, sc = _details(house, D, f"trough_{position}")
    g, mats = sc["gutters"], sc["materials"]
    assert g
    for name, faces in g.items():
        top = max(faces, key=lambda f: f[0][2])
        assert top[1] == "Gutter trough"
        assert all(f[1] == "Gutter" for f in faces if f is not top)
    assert mats["Gutter trough"] == pytest.approx([0.5 * v for v in mats["Gutter"]], abs=1e-4)
    _, sc0 = _details(house, {"gutters": {"position": position}}, f"notrough_{position}")
    assert all(f[1] == "Gutter" for faces in sc0["gutters"].values() for f in faces)


FACES = r"""
import bpy, json, re, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[1])
out = {}
for o in bpy.data.collections["Details"].objects:
    if o.type != "MESH" or not o.name.startswith("deck "):
        continue
    mw = o.matrix_world
    vs = [list(mw @ v.co) for v in o.data.vertices]
    fs = [{"v": [vs[i] for i in p.vertices], "n": list((mw.to_3x3() @ p.normal).normalized())} for p in o.data.polygons]
    out.setdefault(re.sub(r"\.\d{3}$", "", o.name), []).append({"verts": vs, "faces": fs})
json.dump(out, open(sys.argv[2], "w"))
"""


def _area(p):
    return 0.5 * abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))))


def _clip(subject, clipper):
    """Convex polygon intersection (Sutherland-Hodgman) of plan [x, y] lists, either winding."""
    if sum(clipper[i][0] * clipper[(i + 1) % len(clipper)][1] - clipper[(i + 1) % len(clipper)][0] * clipper[i][1]
           for i in range(len(clipper))) < 0:
        clipper = clipper[::-1]
    out = subject
    for i in range(len(clipper)):
        a, b = clipper[i], clipper[(i + 1) % len(clipper)]
        side = [(b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) for p in out]
        inp, out = out, []
        for j in range(len(inp)):
            p, q, sp, sq = inp[j], inp[(j + 1) % len(inp)], side[j], side[(j + 1) % len(inp)]
            if sp >= -1e-12:
                out.append(p)
            if (sp >= -1e-12) != (sq >= -1e-12):
                t = sp / (sp - sq)
                out.append([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t])
        if len(out) < 3:
            return []
    return out


def test_t_join_cap_mitred_onto_the_outer_cap_with_one_post(house):
    """Two fences across an open slot run on to a slanted outer fence (extend_to; one moved at its end b, one at its
    end a): each cap ends ON the outer cap's near side face (gap <= 5 mm, overlap <= 1 mm, over its whole width), no
    two cap tops / bottoms lie coplanar over a common footprint (the black U at the junction), one post stands at each
    junction and the boards stop at the post face."""
    tmp, _, _ = house
    poly = [[-3.0, -4.0], [1.0, -4.0], [1.0, -6.2], [2.5, -6.6], [2.5, -4.0], [4.0, -4.0], [4.0, -7.2], [-3.0, -5.4]]
    dk = {"polygon": poly, "top_z": 0.0, "rail_style": "screen", "rail_height": 1.0, "post_edges": [],
          "picket_width": 0.09, "picket_gap": 0.042,
          "rail_edges": [{"edge": [1, 2], "extend_to": [6, 7]}, {"edge": [3, 4], "extend_to": [6, 7]}, [6, 7]]}
    D = {"model_json": str(tmp / "model.json"), "decks": [dk]}
    (tmp / "tjoin.json").write_text(json.dumps(D))
    _run([os.path.join(SCRIPTS, "add_details.py"), str(tmp / "out" / "model.blend"), str(tmp / "tjoin.json"),
          str(tmp / "tjoin.blend")])
    (tmp / "dump_tjoin.py").write_text(FACES)
    _run([str(tmp / "dump_tjoin.py"), str(tmp / "tjoin.blend"), str(tmp / "tjoin_faces.json")])
    f = json.loads((tmp / "tjoin_faces.json").read_text())

    def y_fence(x):                                    # outer fence line (4,-7.2) -> (-3,-5.4)
        return -7.2 + (x - 4.0) * (-5.4 + 7.2) / (-3.0 - 4.0)
    caps = f["deck 0 rail cap"]
    assert len(caps) == 3
    cx = lambda o: sum(v[0] for v in o["verts"]) / len(o["verts"])
    outer = max(caps, key=lambda o: max(v[0] for v in o["verts"]) - min(v[0] for v in o["verts"]))
    # its north (slot-side) face: of the two long side faces the one further north, normal taken pointing north
    sides = [fc for fc in outer["faces"] if abs(fc["n"][1]) > 0.9 and abs(fc["n"][2]) < 0.1]
    face = max(sides, key=lambda fc: sum(v[1] for v in fc["v"]))
    n, p0 = [c * (1 if face["n"][1] > 0 else -1) for c in face["n"]], face["v"][0]
    for x_run in (1.0, 2.5):
        cap = next(o for o in caps if o is not outer and abs(cx(o) - x_run) < 0.05)
        ends = [v for v in cap["verts"] if v[1] < y_fence(x_run) + 0.3]
        assert len(ends) == 4                                            # both bottom and both top corners
        for v in ends:
            s_ = sum((v[i] - p0[i]) * n[i] for i in range(3))          # + = gap in front of the face, - = overlap
            assert -0.001 <= s_ <= 0.005
            assert 1.0 - 0.04 - 1e-6 <= v[2] <= 1.0 + 1e-6               # a cap corner (z 0.96..1.0)
        posts = [o for o in f["deck 0 rail post"]
                 if abs(cx(o) - x_run) < 1e-3
                 and abs(sum(v[1] for v in o["verts"]) / len(o["verts"]) - y_fence(x_run)) < 1e-3]
        assert len(posts) == 1                                           # one shared post at the junction
        pk = next(o for o in f["deck 0 rail pickets"] if abs(cx(o) - x_run) < 0.05)
        assert min(v[1] for v in pk["verts"]) == pytest.approx(y_fence(x_run) + 0.045, abs=1e-4)   # at the post face
    for i, a in enumerate(caps):                                         # no coplanar horizontal faces over an overlap
        for b in caps[i + 1:]:
            for fa in a["faces"]:
                for fb in b["faces"]:
                    if abs(fa["n"][2]) > 0.99 and abs(fb["n"][2]) > 0.99 and abs(fa["v"][0][2] - fb["v"][0][2]) < 1e-3:
                        assert _area(_clip([v[:2] for v in fa["v"]], [v[:2] for v in fb["v"]]) or [[0, 0]] * 3) < 1e-6
