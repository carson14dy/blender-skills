"""Checks for roof_core.py. Run either way:
    blender -b --factory-startup --python roof-blender/tests/test_roof_core.py
    python roof-blender/tests/test_roof_core.py        (with `pip install bpy`)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import json  # noqa: E402
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
    stored = json.loads(bpy.context.scene.get("rt_measure", "{}"))
    check(stored == {k: res[k] for k in ("planes", "squares", "lengths_m", "pitches_per_12")}, "layers stores its measurements on the scene as rt_measure (for roof_qa.py --expect)")
    pit = res["pitches_per_12"]
    check(len(pit) == 6 and all(p["rise_per_12"] == 6.0 for p in pit) and abs(sum(p["area_m2"] for p in pit) - 254.85) < 0.1,
          f"pitches_per_12: the 6/12 demo reads 6.0 on every plane, areas sum to the roof ({[p['rise_per_12'] for p in pit]})")
    for lid in ("deck", "iceWater", "underlayment", "starter", "nails", "covering", "ridgeVent", "ridgeCap", "dripEdge"):
        ob = bpy.data.objects.get(f"RT_layer_{lid}")
        check(ob is not None and "rt_up" in ob.data.attributes and len(ob.data.polygons) > 0, f"layer {lid} built with build attributes")
    cov = bpy.data.objects["RT_layer_covering"]
    zs = sorted({round(v.co.z, 4) for v in cov.data.vertices})
    check(len(zs) > 100, "shingle courses are stepped geometry, not a flat plane")
    counts = {lid: len(bpy.data.objects[f"RT_layer_{lid}"].data.polygons) for lid in ("covering", "dripEdge", "ridgeVent", "ridgeCap")}
    check(counts == {"covering": 1002, "dripEdge": 27, "ridgeVent": 8, "ridgeCap": 16},
          f"default shingle run unchanged by the metal panels and edge profiles of experiments 019/020 ({counts})")
    # found by blender-master's qa_check (lab experiment 014)
    for lid in ("ridgeCap", "dripEdge"):
        me = bpy.data.objects[f"RT_layer_{lid}"].data
        low = min(p.normal.z for p in me.polygons)
        check(low > -0.3, f"{lid} faces point up or out, none face down into the roof (lowest normal z {low:.2f})")
    old = [bpy.data.objects[f"RT_layer_{lid}"] for lid in ("oldShingles", "oldFelt")]
    check(all(o.hide_render for o in old), "finished roof: the old shingles and felt are torn off (hidden in renders)")
    b = rc.run({"cmd": "build", "orbit": False})
    check(not any(o.hide_render for o in old), "build animation brings the old roof back for the tear-off")
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
    profile_checks()
    new_build_checks()
    print("all roof_core checks passed")


def new_build_checks():
    """A new build (construction kit): no deck repair; ice_rows 0 (unheated building) leaves out the eave membrane."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rc.run({"cmd": "demo", "pitch": 6})
    res = rc.run({"cmd": "layers", "deck_repair": False, "ice_rows": 0, "valleys": False, "old_roof": False})
    check("deckRepair" not in res["layers"] and "iceWater" not in res["layers"] and "deck" in res["layers"],
          f"deck_repair false and ice_rows 0: no deck repair, no ice barrier ({res['layers']})")
    res = rc.run({"cmd": "layers", "deck_repair": False, "ice_rows": 0})
    ice = bpy.data.objects["RT_layer_iceWater"]
    check(max((ice.matrix_world @ v.co).z for v in ice.data.vertices) > 3.0, "ice_rows 0 still lines the valleys")


def profile_checks():
    """Metal panels with real ribs, metal caps, rake trim (lab experiment 019) and drip-edge profiles (020)."""
    from mathutils.bvhtree import BVHTree
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rc.run({"cmd": "demo", "pitch": 6})
    planes, _ = rc.roof_source("Roof")
    segs = rc.analyze_roof(planes)
    for name, want in (("proRib", 0.75), ("proSnap", 0.75), ("corrugated", 0.5)):
        top = area = 0.0
        for P in planes:  # each plane on its own: heights over that plane, area projected onto it
            buf = rc.ribbed_surface([(P, P.region())], rc.H["covering"], name)
            top = max(top, max(P.distance(Vector(p)) for p in buf.verts) - rc.H["covering"])
            for f in buf.faces:
                area += abs(rc.poly_area2([P.from3(Vector(buf.verts[i])) for i in f])) / 2
        flat = sum(P.area for P in planes)
        check(abs(top - want * rc.IN) < 1e-6 and abs(area / flat - 1) < 0.005,
              f"{name}: ribs {top / rc.IN:.3f} in. over the pan, strips cover the planes ({area:.2f} of {flat:.2f} m2, no gaps or overlaps)")

    rc.run({"cmd": "layers", "category": "metal", "panel": "proRib"})
    rib_top = rc.H["covering"] + 0.75 * rc.IN
    check(set(o["rt_layer"] for o in bpy.data.objects if o.get("rt_layer")) <= set(rc.STACK), "metal proRib roof: no new layer ids")
    me = bpy.data.objects["RT_layer_covering"].data

    def near_rake(co, d=0.15):
        for s in segs["rake"]:
            ab = s["B"] - s["A"]
            t = max(0.0, min(1.0, (co - s["A"]).dot(ab) / ab.length_squared))
            if (s["A"] + ab * t - co).length < d:
                return True
        return False
    hmax = 0.0
    for v in me.vertices:
        ds = [P.distance(v.co) for P in planes if P.contains2(*P.from3(v.co), -0.02)]
        if ds and not near_rake(v.co):
            hmax = max(hmax, min(ds, key=abs))
    check(abs(hmax - rib_top) < 0.001, f"metal proRib: the covering's highest point is {(hmax - rc.H['covering']) / rc.IN:.3f} in. over the pan (0.75 in.)")

    cap = bpy.data.objects["RT_layer_ridgeCap"].data
    bvh = BVHTree.FromPolygons([v.co for v in cap.vertices], [tuple(p.vertices) for p in cap.polygons])
    w = 6 * rc.IN  # no cap product: 6 in. each side
    above = below = 0
    for l in segs["hip"] + segs["ridge"]:
        mid = (l["A"] + l["B"]) / 2
        for P in l["planes"]:
            m2 = P.from3(mid)
            inn = rc.inward2(P, P.from3(l["A"]), P.from3(l["B"]))
            for d in (0.01, 0.05, 0.09, w - 0.0127 - 0.002):
                p = P.to3(m2[0] + inn[0] * d, m2[1] + inn[1] * d, rib_top)
                hit_up = bvh.ray_cast(p, P.n, 0.06)[0]
                hit_down = bvh.ray_cast(p, -P.n, 0.03)[0]
                above += hit_up is not None and (hit_up - p).length > 0.001
                below += hit_down is not None
    n_probe = 2 * 4 * len(segs["hip"] + segs["ridge"])
    check(above == n_probe and below == 0, f"metal caps sit above the rib tops on every hip and ridge ({above} of {n_probe} probes, {below} under a rib top)")

    vert = [p for p in me.polygons if abs(p.normal.z) < 0.01]
    hems = [p for p in me.polygons if p.normal.z < -0.8]  # horizontal across the rake, so -cos(slope) along it
    slope = math.atan(6 / 12)
    want = sum((s["A"] - s["B"]).length for s in segs["rake"]) * 3.5 * rc.IN * math.cos(slope)
    got = sum(p.area for p in vert)
    clear = []
    for s in segs["rake"]:
        P = s["planes"][0]
        inn = rc.inward2(P, P.from3(s["A"]), P.from3(s["B"]))
        outw = -(P.h * inn[0] + P.b * inn[1])
        outw.z = 0
        outw.normalize()
        clear += [(p.center - s["A"]).dot(outw) for p in vert if near_rake(p.center, 0.1)]
    check(vert and hems and abs(got / want - 1) < 0.02 and min(clear) > 0.0135,
          f"rake trim in the covering: a 3.5 in. face down every rake ({got:.3f} of {want:.3f} m2), a hem, the face {min(clear) * 1000:.1f} mm out (clear of the drip edge's 13.5 mm kick)")

    prof = {"flange_in": 2.375, "face_in": 1.6875, "kick_out_in": 0.5, "kick_down_in": 0.25, "hem_in": 0}
    rc.run({"cmd": "layers", "edge_profile": prof})
    de = bpy.data.objects["RT_layer_dripEdge"].data
    drops = []
    for p in de.polygons:
        if abs(p.normal.z) < 0.01:
            vs = [de.vertices[i].co for i in p.vertices]
            drops += [abs(a.z - b.z) for i, a in enumerate(vs) for b in vs[i + 1:] if (a.xy - b.xy).length < 1e-6]
    check(drops and all(abs(d - 1.6875 * rc.IN) < 0.001 for d in drops),
          f"edge_profile with a 1.6875 in. face: drip edge drops {min(drops) / rc.IN:.4f}-{max(drops) / rc.IN:.4f} in. at eaves and rakes")
    counts = {lid: len(bpy.data.objects[f"RT_layer_{lid}"].data.polygons) for lid in ("covering", "ridgeVent", "ridgeCap")}
    check(counts == {"covering": 1002, "ridgeVent": 8, "ridgeCap": 16}, f"edge_profile changes only the drip edge ({counts})")


main()
