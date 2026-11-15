"""Checks for roof_core.py. Run either way:
    blender -b --factory-startup --python roof-blender/tests/test_roof_core.py
    python roof-blender/tests/test_roof_core.py        (with `pip install bpy`)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import bpy  # noqa: E402
import roof_core as rc  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rc.run({"cmd": "demo", "pitch": 6})
    res = rc.run({"cmd": "layers"})
    L = res["lengths_m"]
    check(res["planes"] == 6, "ranch demo has 6 roof planes (4 hip + 2 garage gable)")
    check(28.0 < res["squares"] < 30.0, f"roof area is about 29 squares ({res['squares']})")
    check(abs(L["valley"] - 12.0) < 0.5, f"two garage valleys found ({L['valley']} m)")
    check(abs(L["ridge"] - 15.4) < 0.2 and abs(L["hip"] - 32.4) < 0.5, "ridges and hips classified")
    for lid in ("deck", "iceWater", "underlayment", "starter", "nails", "covering", "ridgeVent", "ridgeCap", "dripEdge"):
        ob = bpy.data.objects.get(f"RT_layer_{lid}")
        check(ob is not None and "rt_up" in ob.data.attributes and len(ob.data.polygons) > 0, f"layer {lid} built with build attributes")
    cov = bpy.data.objects["RT_layer_covering"]
    zs = sorted({round(v.co.z, 4) for v in cov.data.vertices})
    check(len(zs) > 100, "shingle courses are stepped geometry, not a flat plane")
    b = rc.run({"cmd": "build", "orbit": False})
    check(b["frame_end"] > b["frame_start"], "build sequence keyframed")
    node = cov.data.materials[0].node_tree.nodes["RT_Reveal"]
    bpy.context.scene.frame_set(b["frame_start"])
    start_val = node.outputs[0].default_value
    bpy.context.scene.frame_set(b["frame_end"])
    end_val = node.outputs[0].default_value
    check(start_val < 0 < end_val, f"shingles hidden at the start and shown at the end ({start_val:.2f} -> {end_val:.2f})")
    e = rc.run({"cmd": "explode", "gap": 0.8, "animate": False, "labels": False})
    check(bpy.data.objects["RT_layer_ridgeCap"].location.z > bpy.data.objects["RT_layer_deck"].location.z, "exploded view stacks layers upward")
    print("all roof_core checks passed")


main()
