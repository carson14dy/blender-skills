"""Accuracy-first builds: acceptance_check.py, the qa_check skip error, render_batch quality fields, _bpyx seconds."""
import contextlib
import io
import json
import math
import sys

import bmesh
import bpy
import fixtures as fx
from run_all import TMP, skill_module

FT, IN = 0.3048, 0.0254


def _ac():
    return skill_module("blender-suite", "acceptance_check")


def _box(name, size, at):
    """Box of `size` (m) with its lowest corner at `at`."""
    def build(bm):
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co = [(c + 0.5) * s for c, s in zip(v.co, size)]
    return fx.mesh_object(name, build, location=at)


def _mat(ob, name, rgb=(0.4, 0.3, 0.2), image=False):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (*rgb, 1)
    if image and not any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes):
        m.node_tree.nodes.new("ShaderNodeTexImage").image = bpy.data.images.new("T_" + name, 8, 8)
    ob.data.materials.append(m)
    return ob


def shed(windows=4, short=0.0, stud_shift=0.0):
    """10 x 12 x 8 ft walls, a 6/12 gable roof on top, 16 in. studs, windows. Lengths in metres."""
    _mat(_box("Shed_Wall", (10 * FT - short, 12 * FT, 8 * FT), (0, 0, 0)), "M_Siding", image=True)
    for i in range(windows):
        _mat(_box(f"Shed_Window_{i + 1}", (0.6, 0.05, 0.6), (1 + i * 0.7, -0.05, 1)), "M_Glass", (0.1, 0.2, 0.3))
    for i in range(5):
        x = i * 16 * IN + (stud_shift if i == 2 else 0)
        _mat(_box(f"Shed_Stud_{i + 1}", (1.5 * IN, 3.5 * IN, 8 * FT), (x + 0.1, 0.1, 0)), "M_Wood")
    w, d, h, rise = 10 * FT, 12 * FT, 8 * FT, 2.5 * FT

    def roof(bm):
        v = [bm.verts.new(p) for p in ((0, 0, h), (w / 2, 0, h + rise), (w, 0, h), (0, d, h), (w / 2, d, h + rise),
                                       (w, d, h))]
        bm.faces.new((v[0], v[1], v[4], v[3]))  # normals up: slope reads only faces that face up
        bm.faces.new((v[1], v[2], v[5], v[4]))
    _mat(fx.mesh_object("Shed_Roof", roof), "M_Shingle", (0.2, 0.2, 0.2))


def _write(name, checks, **top):
    path = TMP / name
    path.write_text(json.dumps({"name": "Garden shed", "units": "ft", **top, "checks": checks}))
    return str(path)


CHECKS = [
    {"id": "footprint", "type": "size", "objects": "Shed_Wall*", "expect": [10, 12, 8], "source": "given"},
    {"id": "windows", "type": "count", "objects": "Shed_Window_*", "expect": 4, "source": "given"},
    {"id": "stud-spacing", "type": "spacing", "objects": "Shed_Stud_*", "axis": "x", "expect": 16, "unit": "in",
     "source": "standard"},
    {"id": "roof-on-walls", "type": "gap", "a": "Shed_Wall*", "b": "Shed_Roof*", "source": "given"},
    {"id": "ridge", "type": "extent", "objects": "Shed_Roof", "expect": 10.5, "source": "assumed", "note": "6/12"},
    {"id": "pitch", "type": "slope", "objects": "Shed_Roof", "expect": "6/12", "source": "assumed", "note": "no answer"},
    {"id": "siding", "type": "material", "objects": "Shed_Wall*", "expect": "M_Siding*", "textured": True,
     "source": "given"}]


def test_acceptance_passes_on_a_matching_scene():
    shed()
    r = _ac().run(accept=_write("ok.json", CHECKS, forbid={"scope": "Shed_*"}))
    assert r["pass"] and r["checked"] == r["passed"] == 7 and not r["failed"] and not r["warnings"], r
    assert r["sources"] == {"given": 4, "standard": 1, "assumed": 2}, r["sources"]
    assert r["assumed"] == ["ridge: 6/12", "pitch: no answer"] and len(r["spec_sha"]) == 12, r
    fp = r["results"][0]
    assert fp["got"] == [10.0, 12.0, 8.0] and type(fp["got"][0]) is float and type(r["pass"]) is bool, fp


def test_acceptance_fails_on_count_size_spacing():
    shed(windows=3, short=0.005, stud_shift=IN)
    r = _ac().run(accept=_write("bad.json", CHECKS))
    assert not r["pass"] and set(r["failed"]) == {"footprint", "windows", "stud-spacing"}, r["failed"]
    res = {x["id"]: x for x in r["results"]}
    assert res["windows"]["expect"] == 4 and res["windows"]["got"] == 3
    assert res["footprint"]["got"][0] == round(10 - 0.005 / FT, 4) and res["footprint"]["expect"] == [10, 12, 8]
    assert res["stud-spacing"]["got"] in (15.0, 17.0) and res["stud-spacing"]["expect"] == 16, res["stud-spacing"]


def test_units_and_tolerance():
    shed()
    sizes = [{"id": u, "type": "size", "objects": "Shed_Wall", "unit": u, "expect": e, "source": "given"}
             for u, e in (("ft", [10, 12, 8]), ("in", [120, 144, 96]), ("mm", [3048, 3657.6, 2438.4]))]
    assert _ac().run(accept=_write("units.json", sizes))["pass"]
    bpy.data.objects["Shed_Wall"].scale.x = (10 * FT - 0.005) / (10 * FT)           # 5 mm short
    mm = {"id": "mm", "type": "size", "objects": "Shed_Wall", "unit": "mm", "expect": [3048, None, None],
          "source": "given"}
    r = _ac().run(accept=_write("tol.json", [mm]))
    assert not r["pass"] and abs(r["results"][0]["err"][0] + 5) < 0.01 and r["results"][0]["tol"][0] > 3, r
    r = _ac().run(accept=_write("tol2.json", [{**mm, "tol": 6, "why": "site-built, 1/4 in. is fine"}]))
    assert r["pass"] and not r["warnings"], r
    r = _ac().run(accept=_write("tol3.json", [{**mm, "tol": 6}]))
    assert r["pass"] and any("without 'why'" in w for w in r["warnings"]), r


def test_nothing_passes_by_default():
    shed()
    ac = _ac()
    for c in ({"type": "count", "objects": "Nope_*", "expect": 0}, {"type": "volume", "objects": "Shed_Wall"},
              {"type": "size", "objects": "Shed_Wall", "expect": 10}, {"type": "spacing", "objects": "Shed_Stud_*"}):
        r = ac.run(accept=_write("one.json", [{"id": "c", "source": "given", **c}]))
        assert not r["pass"] and r["failed"] == ["c"] and r["results"][0]["error"], (c, r)
    assert "matched 0 objects" in ac.run(accept=_write("z.json", [{"id": "z", "type": "count", "objects": "No*",
                                                                    "expect": 1, "source": "given"}]))["results"][0]["error"]
    r = ac.run(accept=_write("empty.json", []))
    assert not r["pass"] and r["checked"] == 0 and r["warnings"], r
    r = ac.run(accept=_write("nosrc.json", [{"id": "w", "type": "count", "objects": "Shed_Wall", "expect": 1}]))
    assert r["sources"] == {"assumed": 1} and r["assumed"] == ["w: no note"] and "source" in r["warnings"][0], r


def test_slope_and_area():
    shed()
    area_ft2 = 2 * 12 * math.hypot(5, 2.5)
    r = _ac().run(accept=_write("roof.json", [
        {"id": "pitch", "type": "slope", "objects": "Shed_Roof", "expect": "6/12", "source": "given"},
        {"id": "area", "type": "area", "objects": "Shed_Roof", "expect": round(area_ft2, 2), "source": "measured"},
        {"id": "sq", "type": "area", "objects": "Shed_Roof", "unit": "sq", "facing": "up",
         "expect": round(area_ft2 / 100, 4), "source": "measured"},
        {"id": "deg", "type": "slope", "objects": "Shed_Roof", "expect": 30, "source": "given"}]))
    res = {x["id"]: x for x in r["results"]}
    assert res["pitch"]["pass"] and res["pitch"]["got"] == 26.565 and res["pitch"]["got_rise_per_12"] == 6.0, res
    assert res["area"]["pass"] and res["area"]["unit"] == "ft2" and abs(res["area"]["got"] - area_ft2) < 0.01, res
    assert res["sq"]["pass"] and res["sq"]["unit"] == "sq" and abs(res["sq"]["got"] - 1.3416) < 1e-3, res
    assert r["failed"] == ["deg"], r["failed"]


def test_material_and_forbid():
    shed()
    _mat(_box("Shed_Trim", (0.1, 0.1, 0.1), (5, 5, 0)), "M_Brick")
    _mat(_box("Shed_Panel", (0.1, 0.1, 0.1), (6, 5, 0)), "M_Siding_Plain")
    fx.cube("Cube.001", size=0.2, location=(8, 0, 0)).data.materials.append(bpy.data.materials.new("M_Untouched"))
    _box("Shed_Door", (0.1, 0.1, 0.1), (7, 5, 0)).data.materials.append(None)
    _mat(_box("Wall_placeholder", (0.1, 0.1, 0.1), (9, 5, 0)), "M_Other")
    acc = [{"id": "siding", "type": "material", "objects": ["Shed_Wall", "Shed_Trim", "Shed_Panel"],
            "expect": "M_Siding*", "textured": True, "source": "given"}]
    r = _ac().run(accept=_write("mat.json", acc))
    fails = r["results"][0]["failing"]
    assert "Shed_Trim: M_Brick" in fails and "Shed_Panel: M_Siding_Plain has no image texture" in fails, fails
    forb = {f["rule"]: f["items"] for f in r["forbidden"]}
    assert forb == {"name_patterns": ["Wall_placeholder"], "default_names": ["Cube.001"], "empty_slots": ["Shed_Door"],
                    "default_materials": ["M_Untouched"]}, forb
    r = _ac().run(accept=_write("mat2.json", acc, forbid={"scope": "Shed_*"}))
    assert [f["rule"] for f in r["forbidden"]] == ["empty_slots"] and not r["pass"], r["forbidden"]


def _png(name, w, h, flat=False):
    im = bpy.data.images.new(name, w, h)
    im.pixels.foreach_set([1.0, 0.0, 0.0, 1.0] * w * h if flat else
                          [v for i in range(w * h) for v in ((i % w) / w, 0.5, (i // w) / h, 1.0)])
    im.filepath_raw, im.file_format = str(TMP / f"{name}.png"), "PNG"
    im.save()
    return im.filepath_raw


def test_image_check():
    fx.cube("Shed_Wall")
    ok, flat = _png("hero", 64, 32), _png("flat", 64, 32, flat=True)
    acc = [{"id": "a", "type": "image", "file": ok, "res": [64, 32], "source": "given"},
           {"id": "b", "type": "image", "file": ok, "res": [128, 64], "source": "given"},
           {"id": "c", "type": "image", "file": flat, "res": [64, 32], "source": "given"},
           {"id": "d", "type": "image", "file": "flat.png", "source": "given"},               # next to the file
           {"id": "e", "type": "image", "file": str(TMP / "missing.png"), "source": "given"}]
    r = _ac().run(accept=_write("img.json", acc, forbid={"scope": "none"}))
    res = {x["id"]: x for x in r["results"]}
    assert res["a"]["pass"] and res["a"]["range"] > 0.5, res["a"]
    assert r["failed"] == ["b", "c", "d", "e"] and res["b"]["got"] == [64, 32], r
    assert res["c"]["range"] < 0.02 and "missing" in res["e"]["error"], res
    assert not any(i.name.startswith(("hero.", "flat.")) for i in bpy.data.images if i.filepath), "loaded copy kept"


def test_only_is_partial():
    shed()
    fx.cube("Cube.001", location=(9, 9, 0))
    acc = _write("only.json", CHECKS)
    r = _ac().run(accept=acc, only=["footprint", "windows"])
    assert r["pass"] and r["partial"] and r["checked"] == 2 and r["forbidden"] == [], r
    full = _ac().run(accept=acc)
    assert not full["pass"] and not full["partial"] and full["forbidden"], full["forbidden"]
    assert any("no such check" in w for w in _ac().run(accept=acc, only=["nope"])["warnings"])


def test_qa_skip_is_an_error():
    fx.cube("SM_Box", location=(0, 0, 1)).data.materials.append(bpy.data.materials.new("M_Box"))
    qa = skill_module("blender-asset-qa", "qa_check")
    r = qa.run(objects=["SM_Box"], max_tris=5, uv=False)
    assert not r["pass"] and r["complete"] is False and r["skipped"] == ["zfighting", "floating"], r
    assert any("did not run" in e and "--max-tris 0" in e for e in r["errors"]), r["errors"]
    r = qa.run(objects=["SM_Box"], max_tris=0, uv=False)
    assert r["pass"] and r["complete"] is True and r["skipped"] == [], r


def test_render_reports_quality():
    fx.cube("Box")
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location, cam.rotation_euler = (0, -6, 1), (1.5708, 0, 0)
    bpy.context.scene.camera = cam
    rb = skill_module("blender-rendering", "render_batch")
    kw = dict(engine="CYCLES", res=(64, 64), samples=1, device="CPU", frames="1")
    r = rb.run(preset="preview", out=str(TMP / "q" / "p_####"), **kw)
    assert r["ok"] and r["deliverable"] is False and r["percent"] == 50 and r["res"] == [32, 32], r
    assert r["quality"] == "preview" and r["warning"].startswith("preview quality (1 samples, 50% = 32x32)"), r
    assert "resolution 50%" in r["reduced"] and r["preset"] == "preview" and r["seconds_total"] > 0, r
    r = rb.run(preset="final", out=str(TMP / "q" / "f_####"), **kw)
    assert r["ok"] and r["deliverable"] is True and r["samples"] == 1 and "quality" not in r, r
    assert r["reduced"] == ["samples 1 < final preset 512"] and "warning" not in r, r


def test_cli_adds_seconds():
    bx = skill_module("blender-suite", "_bpyx")
    old, out = sys.argv, io.StringIO()
    sys.argv = ["x.py", "--"]
    try:
        with contextlib.redirect_stdout(out):
            res = bx.cli(lambda **_: {"ok": True}, bx.parser("Demo.\nUsage: x"))
    finally:
        sys.argv = old
    line = [ln for ln in out.getvalue().splitlines() if ln.startswith(bx.MARK)][-1]
    emitted = json.loads(line[len(bx.MARK):])
    assert emitted["ok"] and isinstance(emitted["seconds"], float) and res["seconds"] == emitted["seconds"], emitted
