"""Checks for roof_core.py. Run either way:
    blender -b --factory-startup --python roof-blender/tests/test_roof_core.py
    python roof-blender/tests/test_roof_core.py        (with `pip install bpy`)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import math  # noqa: E402

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
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
    # hand-computed for 16 x 10 m hip + 7.2 m garage, 6/12, 0.45 m overhang (same as tests/geometry.test.mjs):
    # area 254.85 m2 = 27.43 squares, eaves 58.3, rakes 9.06, ridges 15.45, hips 32.70, valleys 12.15 m
    check(res["planes"] == 6, "ranch demo has 6 roof planes (4 hip + 2 garage gable)")
    check(abs(res["squares"] - 27.43) < 0.05, f"roof area 27.43 squares; nothing hidden under the garage roof counted ({res['squares']})")
    check(abs(L["eave"] - 58.3) < 0.1, f"eaves 58.3 m ({L['eave']} m)")
    check(abs(L["rake"] - 9.06) < 0.1, f"rakes 9.06 m ({L['rake']} m)")
    check(abs(L["valley"] - 12.15) < 0.1, f"two garage valleys 12.15 m ({L['valley']} m)")
    check(abs(L["ridge"] - 15.45) < 0.1 and abs(L["hip"] - 32.70) < 0.1, f"ridges 15.45 m and hips 32.70 m, each counted once ({L['ridge']}, {L['hip']})")
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
    sc = rc.run({"cmd": "scene", "samples": 4, "resolution": [64, 36]})
    check(bpy.context.scene.cycles.transparent_max_bounces >= 32, "enough transparent bounces for hidden layers (no black bands)")
    sun = bpy.data.objects["RT_Sun"].rotation_euler.to_matrix() @ Vector((0, 0, 1))  # toward the sun
    sky = next(n for n in bpy.data.worlds["RT_Sky"].node_tree.nodes if n.type == "TEX_SKY")
    el, rot = sky.sun_elevation, sky.sun_rotation
    sky_dir = Vector((math.sin(rot) * math.cos(el), math.cos(rot) * math.cos(el), math.sin(el)))  # calibrated on a rendered sky panorama
    check((sun - sky_dir).length < 0.05, f"sun lamp points where the sky draws its sun ({tuple(round(x, 2) for x in sun)})")
    print("all roof_core checks passed")


main()
