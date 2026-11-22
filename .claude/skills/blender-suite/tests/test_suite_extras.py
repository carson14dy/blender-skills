import bpy
import fixtures as fx
from run_all import skill_module


def test_blend_audit_flags_code_in_file():
    audit = skill_module("suite", "blend_audit")
    clean = audit.run()
    assert clean["ok"] and clean["pass"] and not clean["errors"], clean
    ob = fx.cube("Driven")
    drv = ob.driver_add("location", 0).driver
    drv.type, drv.expression = "SCRIPTED", "frame * 0.1"
    txt = bpy.data.texts.new("startup.py")
    txt.write("print('hi')\n")
    txt.use_module = True
    img = bpy.data.images.new("Missing", 4, 4)
    img.source, img.filepath = "FILE", "//no_such_texture.png"
    r = audit.run()
    assert not r["pass"] and len(r["errors"]) == 2, r
    assert r["scripted_drivers"][0]["id"] == "Driven" and r["texts"][0]["runs_on_load"], r
    assert r["images"]["missing"] and any("missing" in w for w in r["warnings"]), r
