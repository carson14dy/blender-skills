"""Render the rig cameras in Cycles (needs bpy). Raw over-scanned pinhole frames -> post.finish() -> final PNGs.

Every image's wall-clock time is logged so a GPU benchmark gives seconds (and credits) per finished house.
"""
from __future__ import annotations

import json
import os
import time

import bpy
import numpy as np
from mathutils import Matrix

from . import post

LENS_MM = 26.0


def add_rig_cameras(cams_doc, coll_name="Rig cameras"):
    """Create one Blender camera per rig camera (pinhole, no overscan) so scene.blend contains the rig."""
    coll = bpy.data.collections.new(coll_name)
    bpy.context.scene.collection.children.link(coll)
    objs = {}
    for cam in cams_doc["cameras"]:
        intr = cam["intrinsics"]
        cd = bpy.data.cameras.new(os.path.basename(cam["image"]))
        cd.lens = LENS_MM
        cd.sensor_fit = "HORIZONTAL"
        cd.sensor_width = LENS_MM * intr["width"] / intr["fx"]
        cd.clip_start, cd.clip_end = 0.05, 2000.0
        ob = bpy.data.objects.new(cd.name, cd)
        ob.matrix_world = Matrix(cam["pose"]["blender_matrix_world"])
        coll.objects.link(ob)
        objs[cam["image"]] = ob
    return objs


def select_cameras(cams_doc, max_per_rig=None, rigs=None):
    picked = []
    for rig in ("ground", "roof", "drone"):
        if rigs and rig not in rigs:
            continue
        cs = [c for c in cams_doc["cameras"] if c["rig"] == rig]
        if max_per_rig is not None and len(cs) > max_per_rig:
            idx = np.unique(np.round(np.linspace(0, len(cs) - 1, max_per_rig)).astype(int))
            cs = [cs[i] for i in idx]
        picked += cs
    return picked


def render_cameras(cams_doc, out_root, cams, seed, keep_raw=False, log_path=None):
    sc = bpy.context.scene
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1.0
    sc.render.use_motion_blur = False
    sc.render.use_persistent_data = True          # keep the scene's BVH between frames (only the camera moves)
    raw_dir = os.path.join(out_root, "renders", "_raw")
    os.makedirs(raw_dir, exist_ok=True)
    cam_ob = bpy.data.objects.get("_render_camera")
    if cam_ob is None:
        cam_ob = bpy.data.objects.new("_render_camera", bpy.data.cameras.new("_render_camera"))
        sc.collection.objects.link(cam_ob)
    sc.camera = cam_ob
    log = []
    t_all = time.time()
    for k, cam in enumerate(cams):
        intr = cam["intrinsics"]
        pad = post.overscan_pad(intr)
        Wr, Hr = intr["width"] + 2 * pad[0], intr["height"] + 2 * pad[1]
        cd = cam_ob.data
        cd.lens = LENS_MM
        cd.sensor_fit = "HORIZONTAL"
        cd.sensor_width = LENS_MM * Wr / intr["fx"]          # same focal length in pixels, wider frame
        cd.clip_start, cd.clip_end = 0.05, 2000.0
        cam_ob.matrix_world = Matrix(cam["pose"]["blender_matrix_world"])
        sc.render.resolution_x, sc.render.resolution_y = Wr, Hr
        sc.view_settings.exposure = cam["exposure_ev"]
        raw = os.path.join(raw_dir, os.path.basename(cam["image"]))
        sc.render.filepath = raw
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        t1 = time.time()
        out = os.path.join(out_root, cam["image"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        post.finish(raw, out, cam, pad, seed * 100003 + k)
        t2 = time.time()
        if not keep_raw:
            os.remove(raw)
        log.append({"image": cam["image"], "render_s": round(t1 - t0, 3), "post_s": round(t2 - t1, 3),
                    "raw_size": [Wr, Hr]})
        print(f"[{k + 1}/{len(cams)}] {cam['image']} render {t1 - t0:.1f}s post {t2 - t1:.1f}s", flush=True)
    summary = {"images": len(cams), "total_s": round(time.time() - t_all, 2),
               "mean_render_s": round(float(np.mean([l["render_s"] for l in log])), 3) if log else None,
               "per_image": log}
    if log_path:
        with open(log_path, "w") as f:
            json.dump(summary, f, indent=1)
    if not keep_raw and os.path.isdir(raw_dir) and not os.listdir(raw_dir):
        os.rmdir(raw_dir)
    return summary
