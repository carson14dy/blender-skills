#!/usr/bin/env python3
"""Build one virtual test home: spec -> geometry -> answer key -> cameras -> scene.blend -> renders.

    python3 scripts/make_house.py --seed 1 --out virtual_homes                    # everything, full resolution
    python3 scripts/make_house.py --seed 1 --out vh --long-side 1440 --samples 64 # 1080p-class first pass
    python3 scripts/make_house.py --seed 1 --out vh --no-render                   # files only (no Cycles)
    python3 scripts/make_house.py --seed 1 --out vh --max-per-rig 3 --long-side 480 --samples 8   # smoke test

Needs Python 3.13 with ``pip install bpy==5.3.0 numpy shapely pillow`` (or run the Blender stage under
``blender -b -P`` after installing shapely + pillow into Blender's Python). Output layout:
    <out>/house_NNN/{house.json, answer_key.json, cameras.json, scene.blend, render_log.json, renders/<rig>/*.png}
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vhomes import answer_key, geometry, rigs, spec as spec_mod  # noqa: E402


def _json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--house-id")
    ap.add_argument("--roof-type", default="gable")
    ap.add_argument("--out", default="virtual_homes")
    ap.add_argument("--long-side", type=int, default=None, help="long side of the output images in px (default: device full res)")
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--device", default="auto", choices=["auto", "gpu", "cpu"])
    ap.add_argument("--rigs", default="ground,roof,drone")
    ap.add_argument("--n-ground", type=int, default=40)
    ap.add_argument("--n-roof", type=int, default=60)
    ap.add_argument("--max-per-rig", type=int, default=None, help="render only N evenly spaced cameras per rig")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-blend", action="store_true")
    ap.add_argument("--keep-raw", action="store_true")
    a = ap.parse_args(argv)

    t0 = time.time()
    sp = spec_mod.make_spec(a.seed, a.house_id, a.roof_type)
    root = os.path.join(a.out, sp["house_id"])
    os.makedirs(root, exist_ok=True)
    house = geometry.build_house(sp)
    key = answer_key.compute(house)
    rig_list = tuple(r for r in a.rigs.split(",") if r)
    cams = rigs.make_cameras(house, a.long_side, a.n_ground, a.n_roof, rig_list)
    _json(os.path.join(root, "house.json"), house)
    _json(os.path.join(root, "answer_key.json"), key)
    print(f"{sp['house_id']}: {sp['roof_type']} {key['totals']['squares']:.2f} sq, "
          f"{len(cams['cameras'])} cameras, answer key cross-check: {key['cross_check']['status']}", flush=True)
    if a.no_blend and a.no_render:
        _json(os.path.join(root, "cameras.json"), cams)
        return

    from vhomes import blender_scene, render  # needs bpy
    built = blender_scene.build(house, key)
    used = blender_scene.setup_render(a.samples, a.device, seed=sp["seed"])
    print(f"render device: {used}", flush=True)
    if a.device == "gpu" and used == "CPU":
        raise SystemExit("--device gpu was asked for but Cycles found no GPU; stopping instead of rendering on CPU")
    render.add_rig_cameras(cams)
    if not a.no_blend:
        import bpy
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(root, "scene.blend")), compress=True)
    todo = [] if a.no_render else render.select_cameras(cams, a.max_per_rig)
    chosen = {c["image"] for c in todo}
    for c in cams["cameras"]:
        c["rendered"] = c["image"] in chosen
    _json(os.path.join(root, "cameras.json"), cams)
    log = None
    if todo:
        log = render.render_cameras(cams, root, todo, sp["seed"], a.keep_raw, os.path.join(root, "render_log.json"))
    print(json.dumps({"house": sp["house_id"], "device": used, "roof_area_blender_m2": built["roof_area_blender_m2"],
                      "images": len(todo), "render_total_s": log["total_s"] if log else 0,
                      "mean_render_s": log["mean_render_s"] if log else None,
                      "wall_s": round(time.time() - t0, 1)}), flush=True)


if __name__ == "__main__":
    main()
