"""Keyframe a camera move around an asset: push_in, dolly_orbit, crane, speed_ramp.

Distances are derived from the asset's bounding sphere and the lens, so a move frames a ring and a
truck the same way. The asset is untouched; everything lives in the CM_Camera collection and
re-running replaces it. The result reports whether the subject stays in frame on sampled frames.
Framing depends on the aspect ratio, so set the resolution first or pass --res.
Usage:
  blender -b f.blend -P camera_move.py -- --objects Hero --move push_in [--frames 120] [--fps 24]
      [--focus X Y Z | --focus-object Logo] [--tightness 0.45] [--azimuth 0] [--sweep 90]
      [--faces 4] [--hold 0.7] [--tilt 30] [--fill 1.0] [--res 1920 1080] [--save out.blend]
  MCP: import camera_move; print(camera_move.run(objects=["Hero"], move="crane"))
Then render with scripts/render_batch.py (--frames 1-N).
"""
import math
import os
import statistics
import sys

import bpy
from bpy_extras import anim_utils
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX = "CM_"
# start and end of each channel: azimuth deg, elevation deg, distance as a multiple of the fit
# distance for that lens, focal length mm
MOVES = {
    "push_in": {"az": (25, 5), "el": (20, 10), "dist": (1.0, 0.45), "lens": (35, 65)},
    "dolly_orbit": {"az": (0, 90), "el": (25, 15), "dist": (1.25, 1.0), "lens": (40, 50)},
    "crane": {"az": (15, 25), "el": (-5, 55), "dist": (1.0, 1.25), "lens": (45, 35)},
    "speed_ramp": {"az": (0, 360), "el": (15, 15), "dist": (1.1, 1.1), "lens": (45, 45)},
}
MAX_ELEVATION = 75.0  # the Track To up vector flips near the pole


def _bounds(obs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _fit(radius, lens, sensor, aspect, margin=1.1):
    """Distance at which a sphere of `radius` fits the narrower frame axis (sensor fit AUTO)."""
    half_tan = (sensor / 2) / lens * min(aspect, 1 / aspect)
    return radius / math.sin(math.atan(half_tan)) * margin


def _clear():
    for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:
            bpy.data.cameras.remove(data)


def _smooth(id_block):
    """BEZIER with auto-clamped handles: eases at the ends and never overshoots a key."""
    ad = id_block.animation_data
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    for fc in cb.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
        fc.update()
    return list(cb.fcurves)


def _local(dist, elevation_deg, pivot_z, floor_z):
    """Camera offset in pivot space at azimuth 0 (Blender front, -Y), kept above the floor."""
    e = math.radians(elevation_deg)
    z = max(dist * math.sin(e), floor_z - pivot_z)
    return Vector((0.0, -dist * math.cos(e), z))


def _ramp_keys(frames, faces, hold, drift, azimuth, tilt):
    """Slow drift across each face, then a whip to the next. Ends one full turn on frame N+1."""
    seg = frames / faces
    step = 360.0 / faces
    az, tl = [], []
    for i in range(faces):
        f0 = 1 + round(i * seg)
        f1 = 1 + round(i * seg + hold * seg)
        a = azimuth + i * step
        t = tilt * math.sin(2 * math.pi * i / faces)
        az += [(f0, a), (f1, a + drift)]
        tl += [(f0, t), (f1, t)]
    az.append((frames + 1, azimuth + 360.0))
    tl.append((frames + 1, 0.0))
    return az, tl


def _in_frame(sc, cam, lo, hi):
    for x in (lo.x, hi.x):
        for y in (lo.y, hi.y):
            for z in (lo.z, hi.z):
                c = world_to_camera_view(sc, cam, Vector((x, y, z)))
                if c.z <= 0 or not (0 <= c.x <= 1 and 0 <= c.y <= 1):
                    return False
    return True


def run(objects=None, move="push_in", frames=120, fps=None, focus=None, focus_object=None,
        tightness=0.45, azimuth=0.0, sweep=None, faces=4, hold=0.7, tilt=30.0, fill=1.0, res=None, **_):
    bx.object_mode()
    if move not in MOVES:
        raise ValueError(f"move must be one of {sorted(MOVES)}")
    if frames < 2:
        raise ValueError("frames must be at least 2")
    if fill <= 0:
        raise ValueError("fill must be above 0")
    obs = bx.objects(objects, types=("MESH", "CURVE", "FONT", "CURVES", "ARMATURE"))
    if not objects:  # a default selection must not frame a look-dev backdrop
        obs = [o for o in obs if not o.name.startswith((PREFIX, "LD_"))]
    if not obs:
        raise ValueError("no objects to frame")
    _clear()
    sc = bpy.context.scene
    if res:
        sc.render.resolution_x, sc.render.resolution_y = res
    col = bpy.data.collections.get(PREFIX + "Camera") or bpy.data.collections.new(PREFIX + "Camera")
    if col.name not in sc.collection.children:
        sc.collection.children.link(col)
    lo, hi = _bounds(obs)
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-3)
    floor_z = lo.z + (hi.z - lo.z) * 0.02
    aspect = sc.render.resolution_x / sc.render.resolution_y
    spec = MOVES[move]
    warnings = []

    cam_d = bpy.data.cameras.new(PREFIX + "Cam")
    sensor = cam_d.sensor_width
    lens0, lens1 = spec["lens"]
    d0 = spec["dist"][0] * _fit(radius, lens0, sensor, aspect) / fill
    d1 = spec["dist"][1] * _fit(radius, lens1, sensor, aspect) / fill
    pivot0, pivot1 = center.copy(), center.copy()
    if move == "push_in":
        d1 = tightness * _fit(radius, lens1, sensor, aspect) / fill
        if focus_object:
            lo_f, hi_f = _bounds([bpy.data.objects[focus_object]])
            pivot1 = (lo_f + hi_f) / 2
            d1 = 1.5 * _fit(max((hi_f - lo_f).length / 2, 1e-3), lens1, sensor, aspect)
        elif focus:
            pivot1 = Vector(focus)
    cam_d.clip_start = min(d0, d1) / 100
    cam_d.clip_end = max(d0, d1) * 20
    cam = bpy.data.objects.new(PREFIX + "Cam", cam_d)
    pivot = bpy.data.objects.new(PREFIX + "Pivot", None)
    col.objects.link(pivot)
    col.objects.link(cam)
    cam.parent = pivot
    track = cam.constraints.new("TRACK_TO")
    track.target, track.track_axis, track.up_axis = pivot, "TRACK_NEGATIVE_Z", "UP_Y"
    sc.camera = cam
    sc.frame_start, sc.frame_end = 1, frames
    if fps:
        sc.render.fps = fps
    pivot.location = pivot0
    res = {}

    if move == "speed_ramp":
        if frames / faces < 4:
            raise ValueError("speed_ramp needs at least 4 frames per face")
        hold = min(max(hold, 0.1), 0.9)
        el = spec["el"][0]
        limit = MAX_ELEVATION - abs(el)
        if abs(tilt) > limit:
            warnings.append(f"tilt reduced from {tilt} to {limit} deg to stay clear of the pole")
            tilt = math.copysign(limit, tilt)
        if tilt and "LD_Backdrop" in bpy.data.objects:
            warnings.append("tilt moves the camera below the floor, so the backdrop will block it")
        cam.location = _local(d0, el, center.z, -math.inf)
        cam_d.lens = lens0
        az_keys, tilt_keys = _ramp_keys(frames, faces, hold, min(10.0, 180.0 / faces), azimuth, tilt)
        for f, a in az_keys:
            pivot.rotation_euler[2] = math.radians(a)
            pivot.keyframe_insert("rotation_euler", index=2, frame=f)
        for f, t in tilt_keys:
            pivot.rotation_euler[0] = math.radians(-t)  # elevation rises as the X rotation falls
            pivot.keyframe_insert("rotation_euler", index=0, frame=f)
        curves = _smooth(pivot)
        fz = next(fc for fc in curves if fc.array_index == 2)
        steps = [abs(math.degrees(fz.evaluate(f + 1) - fz.evaluate(f))) for f in range(1, frames + 1)]
        res.update(peak_deg_per_frame=round(max(steps), 2),
                   hold_deg_per_frame=round(statistics.median(steps), 2),
                   seam_error_deg=round(abs(math.degrees(fz.evaluate(frames + 1) - fz.evaluate(1)) - 360), 4),
                   note="frame N+1 == frame 1, so 1..N loops seamlessly")
    else:
        az0 = spec["az"][0] + azimuth
        az1 = az0 + sweep if (sweep is not None and move == "dolly_orbit") else spec["az"][1] + azimuth
        for f, az, d, el, ln, pv in ((1, az0, d0, spec["el"][0], lens0, pivot0),
                                     (frames, az1, d1, spec["el"][1], lens1, pivot1)):
            pivot.location = pv
            pivot.keyframe_insert("location", frame=f)
            pivot.rotation_euler = (0, 0, math.radians(az))
            pivot.keyframe_insert("rotation_euler", index=2, frame=f)
            cam.location = _local(d, el, pv.z, floor_z)
            cam.keyframe_insert("location", frame=f)
            cam_d.lens = ln
            cam_d.keyframe_insert("lens", frame=f)
        _smooth(pivot)
        _smooth(cam)
        _smooth(cam_d)

    samples = sorted({1 + round(i * (frames - 1) / 8) for i in range(9)})
    in_frame, cam_z = {}, math.inf
    for f in samples:
        sc.frame_set(f)
        in_frame[f] = _in_frame(sc, cam, lo, hi)
        cam_z = min(cam_z, cam.matrix_world.translation.z)
    sc.frame_set(frames)
    end_ndc = world_to_camera_view(sc, cam, pivot1 if move == "push_in" else center)
    sc.frame_set(1)
    # a push-in ends on a detail by design, so only its opening frame must show the whole subject
    must_fit = [1] if move == "push_in" else samples
    missing = [f for f in must_fit if not in_frame[f]]
    if missing:
        warnings.append(f"subject leaves the frame on {missing}: check the aspect ratio and bounds")
    res.update(ok=True, move=move, camera=cam.name, pivot=pivot.name, collection=col.name, frames=frames,
               lens=[lens0, lens1], distance=[round(d0, 3), round(d1, 3)], radius=round(radius, 3),
               frames_checked=len(samples), frames_subject_in_frame=sum(in_frame.values()),
               end_focus_ndc=[round(end_ndc.x, 3), round(end_ndc.y, 3)],
               camera_min_z=round(cam_z, 3), warnings=warnings)
    return res


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--move", default="push_in", choices=sorted(MOVES))
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--fps", type=int, default=None)
    p.add_argument("--focus", type=float, nargs=3, default=None, help="push_in end point, world XYZ")
    p.add_argument("--focus-object", default=None, help="push_in ends close on this object")
    p.add_argument("--tightness", type=float, default=0.45, help="push_in end distance as a fraction of the fit")
    p.add_argument("--azimuth", type=float, default=0.0, help="offset from the Blender front (-Y), deg")
    p.add_argument("--sweep", type=float, default=None, help="dolly_orbit rotation, deg (default 90)")
    p.add_argument("--faces", type=int, default=4, help="speed_ramp stops per turn")
    p.add_argument("--hold", type=float, default=0.7, help="speed_ramp share of each stop spent drifting")
    p.add_argument("--tilt", type=float, default=30.0, help="speed_ramp elevation swing, deg (0 = level)")
    p.add_argument("--res", type=int, nargs=2, default=None, help="render resolution, set before framing")
    p.add_argument("--fill", type=float, default=1.0, help="above 1 frames tighter; the result warns if it clips")
    bx.cli(run, p)
