#!/usr/bin/env python3
"""render_demo — presentation stills, a turntable and 3DGRUT training views of the measured model (Cycles).

    python3 render_demo.py BLEND OUTDIR --job render_job.json [--device gpu|cpu] [--only stills,turntable,train]
                           [--dry-run] [--plan-from-job] [--tt-size 1280x720] [--max-size PX] [--samples N]
                           [--limit N] [--encode]
    (or: blender -b -P render_demo.py -- BLEND OUTDIR --job ...)

Sets (counts, sizes and samples from render_job.json, written by scripts/render_bundle.py; defaults in
propmodel/rigs_demo.py):
  stills     hero_street (eye height 1.7 m, front_az side), aerial_34, top_down (orthographic, north up): 3840x2160,
             PNG + JPG -> OUTDIR/stills/
  turntable  240 frames, 24 fps, 1920x1080 (--tt-size 1280x720), constant-radius orbit from the house bbox, constant
             sun -> OUTDIR/turntable/frames/tt_NNNN.png; --encode writes OUTDIR/turntable_<H>p.mp4 (ffmpeg, H.264
             crf 18, yuv420p, +faststart; the exact command is in plan.json either way)
  train      ~200 pinhole views at 1440 px: ground ring, aerial orbit at two heights, nadir grid (train) + 20 held-out
             views -> ONE COLMAP text dataset OUTDIR/train/colmap/: images/<rig>/<name>.png (train) and
             images/holdout/<name>.png (held out, also listed in holdout.txt for scripts/gpu/compress_splat.py
             holdout), sparse/0/{cameras,images,points3D}.txt: OPENCV pinhole cameras, world->camera quaternions,
             points seeded on the true roof / walls (render_job seed_points) and the terrain
Cameras come from the house bbox (Walls + Roof facets collections) and front_az: never fixed coordinates. The ground
under a camera is ray-cast on the Terrain object (else the grade plane, else the walls' bottom).

Presentation only (never saved back): labels, roof-edge curves, LiDAR points and reference planes hidden; the grade
plane is removed when a LiDAR terrain exists; a neutral apron disc under the terrain; constant sun (render_job sun,
default 35 deg right of the front, 45 deg up); AgX. Cycles: GPU (OptiX, else CUDA / HIP / oneAPI / Metal) with
denoising_use_gpu=True, or CPU with --device cpu. With --device gpu and no GPU the script exits 4 at once.
Frame-level resume: a frame whose final file exists is skipped (renders go to *.part.png and are renamed).
OUTDIR/timings.json is rewritten after every frame (per-set and per-frame seconds, mean luminance; frames darker
than 0.02 are listed as black). --dry-run writes only plan.json and cameras.json (with --plan-from-job, or without
bpy, the plan comes from render_job.json's bbox and ground_z and the blend is not opened).
Exit codes: 0 done, 1 input error, 3 black frames found, 4 no GPU.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, TOOL)

import numpy as np  # noqa: E402

from propmodel import rigs_demo as RD  # noqa: E402

HIDE_COLLECTIONS = ("Labels", "Roof edges", "LiDAR points", "Reference data")
SETS = ("stills", "turntable", "train")
BLACK_LUMA = 0.02


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("blend")
    ap.add_argument("outdir")
    ap.add_argument("--job", required=True, help="render_job.json")
    ap.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    ap.add_argument("--only", default=",".join(SETS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--plan-from-job", action="store_true", help="plan from render_job.json bbox (no blend opened)")
    ap.add_argument("--tt-size", help="turntable size WxH (default from render_job, 1920x1080)")
    ap.add_argument("--max-size", type=int, help="cap every image's long side (previews / tests)")
    ap.add_argument("--samples", type=int, help="override every set's samples")
    ap.add_argument("--limit", type=int, help="render at most N frames per set")
    ap.add_argument("--encode", action="store_true", help="encode the turntable MP4 with ffmpeg when its frames are done")
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    a = ap.parse_args(argv)
    a.only = [s.strip() for s in a.only.split(",") if s.strip()]
    bad = [s for s in a.only if s not in SETS]
    if bad:
        ap.error(f"--only: unknown set(s) {bad}; choose from {SETS}")
    return a


def jdump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    os.replace(tmp, path)


def load_job(path):
    with open(path) as f:
        job = json.load(f)
    job.setdefault("front_az", 180.0)
    return job


def apply_overrides(job, a):
    job = json.loads(json.dumps(job))
    if a.tt_size:
        w, h = (int(v) for v in a.tt_size.lower().split("x"))
        job.setdefault("turntable", {})["size"] = [w, h]
    if a.samples:
        for k in SETS:
            job.setdefault(k, {})["samples"] = a.samples
    return job


# ---------------------------------------------------------------------------------------------------------------
# plan

def plan_from_job(job, a):
    bb = job.get("bbox") or {}
    walls, roof = bb.get("walls"), bb.get("roof")
    if not walls and not roof:
        raise SystemExit("render_demo: render_job.json has no bbox (walls / roof); open the blend instead")
    house = RD.union_bbox(walls, roof)
    gz = job.get("ground_z")
    gz = float(house[0][2]) if gz is None else float(gz)
    plan = RD.plan_cameras(house, float(job["front_az"]), lambda x, y: gz, job=job, walls_bbox=walls or house,
                           clear_bbox=bb.get("clear") or house, scale=a.max_size)
    plan["source"] = "render_job.json bbox (blend not opened)"
    plan["ground_model"] = {"kind": "plane", "z": gz}
    return plan, (lambda x, y: gz)


def output_paths(plan, out):
    """{camera name: absolute output path} for every camera of the plan."""
    p = {}
    for c in plan["stills"]:
        p[c["name"]] = os.path.join(out, "stills", f"{c['name']}.png")
    for c in plan["turntable"]:
        p[c["name"]] = os.path.join(out, "turntable", "frames", f"{c['name']}.png")
    for c in plan["train"]:
        p[c["name"]] = os.path.join(out, "train", "colmap", "images", c["rig"], f"{c['name']}.png")
    for c in plan["holdout"]:
        p[c["name"]] = os.path.join(out, "train", "colmap", "images", "holdout", f"{c['name']}.png")
    return p


def encode_cmd(out, plan):
    tt = plan["turntable"]
    if not tt:
        return None
    h = tt[0]["intrinsics"]["height"]
    fps = int(plan["config"]["turntable"]["fps"])
    return ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
            os.path.join(out, "turntable", "frames", "tt_%04d.png"), "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", os.path.join(out, f"turntable_{h}p.mp4")]


def write_plan(plan, out, a, job):
    paths = output_paths(plan, out)
    os.makedirs(out, exist_ok=True)
    cams = []
    for key in ("stills", "turntable", "train", "holdout"):
        for c in plan[key]:
            d = dict(c)
            d["image"] = os.path.relpath(paths[c["name"]], out)
            cams.append(d)
    counts = {k: len(plan[k]) for k in ("stills", "turntable", "train", "holdout")}
    cfg = plan["config"]
    doc = {"schema": "render_demo.plan/1", "written": dt.datetime.now().isoformat(timespec="seconds"),
           "job_id": job.get("id"), "front_az": plan["front_az"], "source": plan.get("source"),
           "ground_model": plan.get("ground_model"), "target": plan["target"], "house_bbox": plan["house_bbox"],
           "walls_bbox": plan["walls_bbox"], "radii": plan["radii"], "sun": plan["sun"], "counts": counts,
           "sets": a.only, "device": a.device, "max_size": a.max_size,
           "sizes": {"stills": [plan["stills"][0]["intrinsics"]["width"], plan["stills"][0]["intrinsics"]["height"]],
                     "turntable": [plan["turntable"][0]["intrinsics"]["width"], plan["turntable"][0]["intrinsics"]["height"]]
                     if plan["turntable"] else None,
                     "train": [plan["train"][0]["intrinsics"]["width"], plan["train"][0]["intrinsics"]["height"]]
                     if plan["train"] else None},
           "samples": {k: int(cfg[k]["samples"]) for k in SETS},
           "fps": int(cfg["turntable"]["fps"]), "encode": encode_cmd(out, plan), "notes": plan["notes"],
           "outputs": {"stills": "stills/<name>.png + .jpg", "turntable": "turntable/frames/tt_NNNN.png",
                       "train": "train/colmap (COLMAP text, images/<rig>/)",
                       "holdout": "train/colmap/images/holdout/ + train/colmap/holdout.txt"}}
    jdump(os.path.join(out, "plan.json"), doc)
    jdump(os.path.join(out, "cameras.json"), {
        "schema": "render_demo.cameras/1", "conventions": RD.__doc__.split("Conventions", 1)[1].strip(),
        "front_az": plan["front_az"], "target": plan["target"], "cameras": cams})
    return doc, paths


# ---------------------------------------------------------------------------------------------------------------
# Blender side

def open_scene(bpy, blend):
    bpy.ops.wm.open_mainfile(filepath=blend)
    sc = bpy.context.scene
    for n in HIDE_COLLECTIONS:
        c = bpy.data.collections.get(n)
        if c:
            c.hide_render = True
            for o in list(c.all_objects):       # copy: hide_render invalidates the cached all_objects list
                if o is not None:
                    o.hide_render = True
    terrain = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Terrain")]
    if terrain:
        for o in list(bpy.data.objects):
            if o.name.startswith("Ground (grade)") or o.name.startswith("Ground ortho"):
                bpy.data.objects.remove(o, do_unlink=True)
    for o in list(bpy.data.objects):
        if o.type == "FONT":
            o.hide_render = True
    return sc, terrain


def world_bbox(objs):
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        return None
    return ([min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)],
            [max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)])


def scene_bboxes(bpy):
    def coll_meshes(name):
        c = bpy.data.collections.get(name)
        return [o for o in (c.all_objects if c else []) if o.type == "MESH" and not o.hide_render]
    walls, roof = coll_meshes("Walls"), coll_meshes("Roof facets")
    house_objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render
                  and not o.name.startswith(("Terrain", "Ground", "RenderDemo"))
                  and "Site" not in [c.name for c in o.users_collection]]
    wb, rb = world_bbox(walls), world_bbox(roof)
    if wb is None and rb is None:
        wb = world_bbox(house_objs)
    return wb, rb, world_bbox(house_objs)


def make_ground_fn(bpy, terrain, fallback_z):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    trees = []
    for o in terrain:
        me = o.data
        verts = [o.matrix_world @ v.co for v in me.vertices]
        polys = [tuple(p.vertices) for p in me.polygons]
        if polys:
            trees.append(BVHTree.FromPolygons(verts, polys))
    zmin = min((min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in terrain if o.data.vertices),
               default=fallback_z)

    def fn(x, y):
        best = None
        for t in trees:
            hit = t.ray_cast(Vector((x, y, 1e4)), Vector((0, 0, -1)))
            if hit[0] is not None:
                best = hit[0].z if best is None else max(best, hit[0].z)
        return float(best) if best is not None else float(zmin if trees else fallback_z)
    return fn, zmin


def setup_look(bpy, sc, plan, terrain, zmin):
    import bmesh  # noqa: F401
    from mathutils import Vector
    sc.render.engine = "CYCLES"
    vt = [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items]
    sc.view_settings.view_transform = "AgX" if "AgX" in vt else "Filmic"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.view_settings.exposure = 0.0
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("RenderDemo World")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.62, 0.72, 0.86, 1.0)
    bg.inputs[1].default_value = 0.65
    nt.links.new(bg.outputs[0], nt.nodes.new("ShaderNodeOutputWorld").inputs[0])
    for o in [o for o in bpy.data.objects if o.type == "LIGHT" and o.data.type == "SUN"]:
        o.hide_render = True
    sd = bpy.data.lights.new("RenderDemo Sun", "SUN")
    sd.energy = float(plan["sun"]["energy"])
    sd.angle = math.radians(1.5)
    sun = bpy.data.objects.new("RenderDemo Sun", sd)
    sc.collection.objects.link(sun)
    to_sun = Vector(plan["sun"]["to_sun"])
    sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    if terrain:      # neutral apron under the LiDAR terrain tile (presentation only)
        t = plan["target"]
        bpy.ops.mesh.primitive_circle_add(vertices=96, radius=1500.0, fill_type="NGON", location=(t[0], t[1], zmin - 0.08))
        ap = bpy.context.active_object
        ap.name = "RenderDemo apron"
        m = bpy.data.materials.new("RenderDemo apron")
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.20, 0.21, 0.17, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.95
        ap.data.materials.append(m)
    sc.render.use_persistent_data = True
    sc.render.use_motion_blur = False
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1.0
    sc.render.use_file_extension = False
    im = sc.render.image_settings
    im.file_format, im.color_mode, im.color_depth, im.compression = "PNG", "RGB", "8", 15
    sc.cycles.max_bounces = 8
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True


def setup_device(bpy, sc, device):
    """-> description string; raises SystemExit(4) when a GPU was asked for and none exists."""
    if device == "cpu":
        sc.cycles.device = "CPU"
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        try:
            prefs.refresh_devices()
        except AttributeError:
            prefs.get_devices()
        devs = [d for d in prefs.devices if d.type == kind]
        if devs:
            for d in prefs.devices:
                d.use = d.type == kind
            sc.cycles.device = "GPU"
            try:
                sc.cycles.denoising_use_gpu = True
            except AttributeError:
                pass
            return f"GPU {kind}: " + ", ".join(sorted({d.name for d in devs}))
    print("render_demo: --device gpu but Cycles finds no GPU (OptiX / CUDA / HIP / oneAPI / Metal); "
          "use --device cpu for a CPU run", file=sys.stderr)
    raise SystemExit(4)


def set_camera(bpy, cam_ob, c):
    from mathutils import Matrix
    cd = cam_ob.data
    k = c["intrinsics"]
    if c.get("projection") == "orthographic":
        cd.type = "ORTHO"
        cd.ortho_scale = float(c["ortho_scale"])
    else:
        cd.type = "PERSP"
        cd.lens = 50.0
        cd.sensor_fit = "HORIZONTAL"
        cd.sensor_width = 50.0 * k["width"] / k["fx"]
    cd.shift_x = cd.shift_y = 0.0
    cd.clip_start, cd.clip_end = 0.05, 6000.0
    cam_ob.matrix_world = Matrix(c["pose"]["blender_matrix_world"])


def mean_luma(path):
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((64, 36))
        return float(np.asarray(im, float).mean() / 255.0)
    except Exception:  # noqa: BLE001
        return None


def to_jpg(bpy, sc, png, jpg, quality=90):
    try:
        from PIL import Image
        Image.open(png).convert("RGB").save(jpg, quality=quality, optimize=True, progressive=True)
        return
    except ImportError:
        pass
    img = bpy.data.images.load(png)
    im = sc.render.image_settings
    old = (im.file_format, im.quality)
    im.file_format, im.quality = "JPEG", quality
    img.save_render(jpg, scene=sc)
    im.file_format, im.quality = old
    bpy.data.images.remove(img)


def render_sets(bpy, sc, plan, paths, a, out, timings, device_desc):
    cam_ob = bpy.data.objects.new("RenderDemo camera", bpy.data.cameras.new("RenderDemo camera"))
    sc.collection.objects.link(cam_ob)
    sc.camera = cam_ob
    cfg = plan["config"]
    order = [("stills", plan["stills"]), ("turntable", plan["turntable"]),
             ("train", plan["train"] + plan["holdout"])]
    t_all = time.time()
    for set_name, cams in order:
        if set_name not in a.only:
            continue
        if a.limit is not None:
            cams = cams[:a.limit]
        st = timings["sets"].setdefault(set_name, {"frames": len(cams), "rendered": 0, "skipped": 0, "seconds": 0.0})
        st["frames"] = len(cams)
        sc.cycles.samples = int(cfg[set_name]["samples"])
        t_set = time.time()
        for c in cams:
            path = paths[c["name"]]
            if os.path.exists(path) and os.path.getsize(path) > 0:
                st["skipped"] += 1
                if set_name == "stills" and not os.path.exists(path[:-4] + ".jpg"):
                    to_jpg(bpy, sc, path, path[:-4] + ".jpg")
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            k = c["intrinsics"]
            sc.render.resolution_x, sc.render.resolution_y = int(k["width"]), int(k["height"])
            set_camera(bpy, cam_ob, c)
            part = path[:-4] + ".part.png"
            sc.render.filepath = part
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            os.replace(part, path)
            dt_ = time.time() - t0
            luma = mean_luma(path)
            if set_name == "stills":
                to_jpg(bpy, sc, path, path[:-4] + ".jpg")
            st["rendered"] += 1
            timings["frames"].append({"name": c["name"], "set": set_name, "seconds": round(dt_, 3),
                                      "size": [k["width"], k["height"]], "mean_luma": luma})
            if luma is not None and luma < BLACK_LUMA:
                timings["black_frames"].append(c["name"])
            st["seconds"] = round(time.time() - t_set, 2)
            done = [f["seconds"] for f in timings["frames"] if f["set"] == set_name]
            st["mean_s"] = round(sum(done) / len(done), 3)
            timings["total_s"] = round(time.time() - t_all + timings.get("_prev_total", 0.0), 2)
            jdump(os.path.join(out, "timings.json"), {k_: v for k_, v in timings.items() if not k_.startswith("_")})
            print(f"[{set_name} {st['rendered'] + st['skipped']}/{len(cams)}] {c['name']} {dt_:.1f}s", flush=True)
        st["seconds"] = round(time.time() - t_set, 2)
    timings["total_s"] = round(time.time() - t_all + timings.get("_prev_total", 0.0), 2)


def colmap_points(bpy, job, job_dir, terrain, target, radius, z_fallback, n_ground=15000, seed=11):
    """Seed points: render_job seed_points (true roof + walls from model.json) + points on the terrain triangles
    within ``radius`` of the target (a flat disc at the grade when there is no terrain)."""
    pts = []
    sp = job.get("seed_points")
    if sp:
        p = sp if os.path.isabs(sp) else os.path.join(job_dir, sp)
        if os.path.exists(p):
            pts.append(np.load(p).reshape(-1, 3).astype(float))
    rng = np.random.default_rng(seed)
    tri = []
    for o in terrain:
        me = o.data
        me.calc_loop_triangles()
        mw = o.matrix_world
        V = np.array([tuple(mw @ v.co) for v in me.vertices], float)
        T = np.array([tuple(t.vertices) for t in me.loop_triangles], int).reshape(-1, 3)
        if len(V) and len(T):
            tri.append(V[T])
    tri = np.concatenate(tri) if tri else None
    pts.append(RD.sample_ground(tri, target, radius, n_ground, rng, z_fallback=z_fallback))
    return np.vstack(pts) if pts else np.zeros((0, 3))


def write_colmap_sets(plan, paths, out, points, a):
    """One COLMAP text dataset with the train views and the held-out views (images/holdout/, holdout.txt)."""
    train = plan["train"][:a.limit] if a.limit is not None else plan["train"]
    hold = plan["holdout"][:a.limit] if a.limit is not None else plan["holdout"]
    cams = [c for c in train + hold if os.path.exists(paths[c["name"]])]
    if not cams:
        return {}
    root = os.path.join(out, "train", "colmap")
    names = {c["name"]: os.path.relpath(paths[c["name"]], os.path.join(root, "images")) for c in cams}
    res = RD.write_colmap(root, [dict(c) for c in cams], points, names)
    held = [names[c["name"]] for c in cams if c.get("split") == "holdout"]
    with open(os.path.join(root, "holdout.txt"), "w") as f:
        f.write("# held-out views (never trained on; scored for PSNR), names relative to images/\n")
        f.writelines(n + "\n" for n in held)
    res["holdout"] = len(held)
    return res


def main(argv=None):
    a = parse(sys.argv[1:] if argv is None else argv)
    if not os.path.exists(a.job):
        print(f"render_demo: no render job {a.job}", file=sys.stderr)
        return 1
    job = apply_overrides(load_job(a.job), a)
    job_dir = os.path.dirname(os.path.abspath(a.job))
    out = os.path.abspath(a.outdir)
    os.makedirs(out, exist_ok=True)
    try:
        import bpy  # noqa: F401
        have_bpy = True
    except ImportError:
        have_bpy = False
    if a.dry_run and (a.plan_from_job or not have_bpy):
        plan, _ = plan_from_job(job, a)
        doc, _ = write_plan(plan, out, a, job)
        print(json.dumps({"dry_run": True, "plan": os.path.join(out, "plan.json"), "counts": doc["counts"],
                          "source": doc["source"]}))
        return 0
    if not have_bpy:
        print("render_demo: bpy is not importable here (pip install bpy, or run inside Blender)", file=sys.stderr)
        return 1
    if not os.path.exists(a.blend):
        print(f"render_demo: no blend {a.blend}", file=sys.stderr)
        return 1
    import bpy
    t_open = time.time()
    sc, terrain = open_scene(bpy, a.blend)
    wb, rb, cb = scene_bboxes(bpy)
    house = RD.union_bbox(wb, rb)
    fallback_z = house[0][2]
    grade = bpy.data.objects.get("Ground (grade)")
    if grade is not None and not terrain:
        fallback_z = world_bbox([grade])[1][2]
    ground_fn, zmin = make_ground_fn(bpy, terrain, fallback_z)
    plan = RD.plan_cameras(house, float(job["front_az"]), ground_fn, job=job, walls_bbox=wb or house,
                           clear_bbox=cb or house, scale=a.max_size)
    plan["source"] = "blend (Walls + Roof facets bbox, terrain ray-cast)"
    plan["ground_model"] = {"kind": "terrain ray-cast" if terrain else "plane", "z_fallback": float(fallback_z)}
    jb = (job.get("bbox") or {})
    if jb.get("walls") and wb:
        dev = float(np.max(np.abs(np.asarray(jb["walls"]) - np.asarray(wb))))
        if dev > 0.5:
            plan["notes"].append(f"render_job walls bbox differs from the blend by {dev:.2f} m (blend used)")
    doc, paths = write_plan(plan, out, a, job)
    if a.dry_run:
        print(json.dumps({"dry_run": True, "plan": os.path.join(out, "plan.json"), "counts": doc["counts"],
                          "source": doc["source"]}))
        return 0
    setup_look(bpy, sc, plan, terrain, zmin)
    device_desc = setup_device(bpy, sc, a.device)
    tp = os.path.join(out, "timings.json")
    prev = {}
    if os.path.exists(tp):
        try:
            with open(tp) as f:
                prev = json.load(f)
        except ValueError:
            prev = {}
    timings = {"schema": "render_demo.timings/1", "started": dt.datetime.now().isoformat(timespec="seconds"),
               "device": device_desc, "blend_open_s": round(time.time() - t_open, 2),
               "sets": {}, "frames": prev.get("frames", []) if prev else [], "black_frames": [],
               "_prev_total": float(prev.get("total_s", 0.0)) if prev else 0.0}
    render_sets(bpy, sc, plan, paths, a, out, timings, device_desc)
    if "train" in a.only:
        pts = colmap_points(bpy, job, job_dir, terrain, plan["target"], max(plan["radii"]["clear"] * 2.5, 25.0),
                            fallback_z)
        timings["colmap"] = write_colmap_sets(plan, paths, out, pts, a)
    if a.encode and "turntable" in a.only:
        frames = [paths[c["name"]] for c in plan["turntable"]]
        if a.limit is None and all(os.path.exists(p) for p in frames) and shutil.which("ffmpeg"):
            t0 = time.time()
            r = subprocess.run(encode_cmd(out, plan), capture_output=True, text=True)
            timings["encode"] = {"exit": r.returncode, "seconds": round(time.time() - t0, 2), "stderr": r.stderr[-400:]}
        else:
            timings["encode"] = {"skipped": "frames incomplete (or --limit) or ffmpeg missing"}
    timings["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    jdump(tp, {k: v for k, v in timings.items() if not k.startswith("_")})
    print(json.dumps({"out": out, "device": device_desc, "sets": {k: v for k, v in timings["sets"].items()},
                      "black_frames": timings["black_frames"], "total_s": timings.get("total_s")}))
    return 3 if timings["black_frames"] else 0


if __name__ == "__main__":
    sys.exit(main())
