"""scripts/blender/export_studio_glb.py: what goes into the studio model. The drop rules are tested without Blender;
the export itself runs headless Blender through the `bpy` module in a subprocess (skipped without bpy)."""
import importlib.util
import json
import os
import struct
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, "..", "scripts", "blender", "export_studio_glb.py")
HAVE_BPY = importlib.util.find_spec("bpy") is not None


@pytest.fixture
def ex(monkeypatch):
    """The exporter module with bpy hidden (pure helpers only)."""
    monkeypatch.setitem(sys.modules, "bpy", None)
    spec = importlib.util.spec_from_file_location("export_studio_glb_pure", EXPORT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.bpy is None
    return mod


def test_drop_rules(ex):
    d = ex.drop_reason
    assert d("Lot line (subject parcel)", ["Site"], hidden=True) == "lot line"
    assert d("Lot line (subject parcel)", ["Site"], hidden=True, keep_lot_line=True) is None
    assert d("Ground (grade)", ["Site"]) == "reference object"
    assert d("Ground ortho 2", ["Site"]) == "reference object"
    assert d("Terrain", ["Site"], reference=True) == "reference object"
    assert d("F1 label", ["Labels"]) == "collection Labels"
    assert d("Label F1", ["Details"]) == "label"
    assert d("Camera", ["Details"], obj_type="CAMERA") == "camera"
    assert d("QA helper", ["Site"], hidden=True) == "hidden from renders"
    assert d("Terrain", ["Site"]) is None
    assert d("pier 0 numerals", ["Site"], obj_type="FONT") is None       # model text stays
    assert d("Roof facet 1", ["Roof facets"]) is None


def test_parse_rgb(ex):
    assert ex.parse_rgb("0.2,0.3,0.4") == (0.2, 0.3, 0.4)
    r, g, b = ex.parse_rgb("#ffffff")
    assert abs(r - 1.0) < 1e-6 and abs(g - 1.0) < 1e-6
    assert ex.parse_rgb("#808080")[0] == pytest.approx(0.2159, abs=1e-3)
    with pytest.raises(ValueError):
        ex.parse_rgb("2,0,0")


def test_parse_args(ex):
    blend, out, o = ex.parse_args(["a.blend", "b.glb", "--with-site", "--keep-lot-line", "--wall-rgb", "#000000"])
    assert (blend, out) == ("a.blend", "b.glb")
    assert o["with_site"] and o["keep_lot_line"] and not o["draco"] and o["wall_rgb"] == (0.0, 0.0, 0.0)
    with pytest.raises(SystemExit):
        ex.parse_args(["a.blend"])


SCENE = r"""
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
def coll(name):
    c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c); return c
def mat(name, rgb):
    m = bpy.data.materials.new(name); m.diffuse_color = (*rgb, 1); return m
def quad(name, c, z, m=None, hide=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, z), (4, 0, z + 1), (4, 3, z + 1), (0, 3, z)], [], [[0, 1, 2, 3]])
    o = bpy.data.objects.new(name, me); c.objects.link(o)
    if m: me.materials.append(m)
    o.hide_render = hide
    return o
roof, walls, site, ref, lab = coll("Roof facets"), coll("Walls"), coll("Site"), coll("Reference data"), coll("Labels")
quad("Roof facet 1", roof, 3, mat("Roof 0", (1, 0, 0)))
quad("Roof facet 2", roof, 3.2, mat("Roof 1", (0, 1, 0)))
quad("Wall A", walls, 0, mat("Wall", (0.5, 0.5, 0.4)))
quad("Wall B", walls, 0.1, mat("Wall", (0.5, 0.5, 0.4)))
quad("Terrain", site, -0.1)
quad("Lot line (subject parcel)", site, 0.04, mat("Lot line", (0.95, 0.2, 0.2)), hide=True)
quad("Ground (grade)", ref, -0.02)
quad("Label F1", lab, 5)
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[1])
"""


def glb_json(path):
    with open(path, "rb") as f:
        b = f.read()
    n, _ = struct.unpack_from("<II", b, 12)
    return json.loads(b[20:20 + n].decode().rstrip(" \x00"))


def export(tmp_path, *args, name="out.glb"):
    out = tmp_path / name
    r = subprocess.run([sys.executable, EXPORT, str(tmp_path / "scene.blend"), str(out), *args],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return glb_json(out), r.stdout


@pytest.mark.skipif(not HAVE_BPY, reason="needs the bpy module")
def test_export_drops_lot_line_and_reference_objects(tmp_path):
    r = subprocess.run([sys.executable, "-c", SCENE, str(tmp_path / "scene.blend")], capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]

    js, log = export(tmp_path, "--with-site")
    names = [n.get("name", "") for n in js["nodes"]]
    assert not any(n.startswith("Lot line") for n in names), names
    assert "Ground (grade)" not in names and "Label F1" not in names
    assert {"Roof F1", "Roof F2", "Walls", "Terrain"} <= set(names)
    mats = {m["name"] for m in js.get("materials", [])}
    assert "Roof shingle" in mats and "Wall" in mats          # QA facet colours replaced, job wall colour kept
    assert not any(m.startswith("Roof 0") for m in mats)
    assert '"lot line": 1' in log

    js, _ = export(tmp_path, "--with-site", "--keep-lot-line", name="lot.glb")
    assert any(n.get("name", "").startswith("Lot line") for n in js["nodes"])

    js, _ = export(tmp_path, name="house.glb")                # without --with-site: house only
    names = {n.get("name", "") for n in js["nodes"]}
    assert "Terrain" not in names and "Walls" in names

    js, log = export(tmp_path, "--draco", "--wall-rgb", "#cccccc", name="draco.glb")
    assert "ok " in log
    assert "Siding" in {m["name"] for m in js.get("materials", [])}
    if "KHR_draco_mesh_compression" not in js.get("extensionsUsed", []):
        assert "no Draco library" in log
