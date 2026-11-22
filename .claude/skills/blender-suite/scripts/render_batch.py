"""Render stills/animations with quality presets, per-camera batches, any output format.

Presets: preview (fast look-dev), final (production), product (clean, transparent bg).
Formats: PNG, JPEG, EXR (half float), EXR_MULTI (all passes), MP4 (H.264), WEBM.
Usage:
  blender -b f.blend -P render_batch.py -- [--engine CYCLES|BLENDER_EEVEE|BLENDER_WORKBENCH]
      [--preset preview|final|product] [--res 1920 1080] [--percent 100] [--samples N]
      [--out //render/shot_####] [--format PNG] [--frames 1-120 | 1,12,24] [--cameras CamA CamB]
      [--view AgX|"Khronos PBR Neutral"|Standard] [--look "AgX - Punchy"] [--transparent] [--device GPU|CPU]
  MCP: import render_batch as r; print(r.run(preset="preview", frames="1"))
Returns written files, seconds per image and the quality rendered: preset, samples, percent, "reduced" and
"deliverable" (false for the preview preset or under 100 %: for looking, not for delivery).
"""
import glob
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PRESETS = {
    "preview": {"cycles": dict(samples=64, adaptive_threshold=0.05, use_denoising=True),
                "eevee": dict(taa_render_samples=16, use_raytracing=False), "percent": 50},
    "final": {"cycles": dict(samples=512, adaptive_threshold=0.01, use_denoising=True),
              "eevee": dict(taa_render_samples=128, use_raytracing=True), "percent": 100},
    "product": {"cycles": dict(samples=1024, adaptive_threshold=0.005, use_denoising=True),
                "eevee": dict(taa_render_samples=256, use_raytracing=True), "percent": 100,
                "transparent": True},
}
FORMATS = {"PNG": ("IMAGE", "PNG", ".png"), "JPEG": ("IMAGE", "JPEG", ".jpg"),
           "EXR": ("IMAGE", "OPEN_EXR", ".exr"), "EXR_MULTI": ("MULTI_LAYER_IMAGE", "OPEN_EXR_MULTILAYER", ".exr"),
           "MP4": ("VIDEO", "FFMPEG", ".mp4"), "WEBM": ("VIDEO", "FFMPEG", ".webm")}


def _gpu(sc, device):
    if device == "CPU":
        sc.cycles.device = "CPU"
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.refresh_devices()
        if any(d.type != "CPU" for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type != "CPU"
            sc.cycles.device = "GPU"
            return backend
    sc.cycles.device = "CPU"
    return "CPU"


def _frames(spec, sc):
    if not spec:
        return [sc.frame_current]
    out = []
    for part in str(spec).split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def run(engine=None, preset="preview", res=None, percent=None, samples=None, out="//render/####",
        format="PNG", frames=None, cameras=None, view=None, look=None, transparent=None,  # noqa: A002
        device="GPU", **_):
    t0 = time.time()
    sc = bpy.context.scene
    r = sc.render
    if engine:
        bx.set_enum(r, "engine", engine)
    pr = PRESETS[preset]
    info = {"engine": r.engine}
    if r.engine == "CYCLES":
        info["device"] = _gpu(sc, device)
        for k, v in pr["cycles"].items():
            setattr(sc.cycles, k, v)
        sc.cycles.use_adaptive_sampling = True
        if samples:
            sc.cycles.samples = samples
        if info["device"] == "OPTIX":
            sc.cycles.denoiser = "OPTIX"
        else:
            sc.cycles.denoiser = "OPENIMAGEDENOISE"
    elif r.engine == "BLENDER_EEVEE":
        for k, v in pr["eevee"].items():
            setattr(sc.eevee, k, v)
        if samples:
            sc.eevee.taa_render_samples = samples
    if res:
        r.resolution_x, r.resolution_y = res
    r.resolution_percentage = percent or pr["percent"]
    r.film_transparent = pr.get("transparent", False) if transparent is None else transparent
    if view:
        bx.set_enum(sc.view_settings, "view_transform", view)
    if look:
        bx.set_enum(sc.view_settings, "look", look)
    media, fmt, ext = FORMATS[format]
    s = r.image_settings
    s.media_type = media  # 5.0+: must precede file_format
    s.file_format = fmt
    if fmt in ("OPEN_EXR", "OPEN_EXR_MULTILAYER"):
        s.color_depth, s.exr_codec = "16", "DWAA"
    elif fmt == "PNG":
        s.color_mode = "RGBA" if r.film_transparent else "RGB"
    if media == "VIDEO":
        r.ffmpeg.format = "MPEG4" if format == "MP4" else "WEBM"
        r.ffmpeg.codec = "H264" if format == "MP4" else "AV1"
        r.ffmpeg.constant_rate_factor = "HIGH"
    warn = ["JPEG has no alpha; use PNG/EXR for transparent renders"] if r.film_transparent and fmt == "JPEG" else []
    cams = [bpy.data.objects[c] for c in cameras] if cameras else [sc.camera]
    if cams[0] is None:
        raise ValueError("scene has no camera (see blender-lighting-lookdev)")
    base = bpy.path.abspath(out)
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    files, times = [], []
    for cam in cams:
        sc.camera = cam
        stem = base.replace("####", "") if len(cams) == 1 else f"{base.replace('####', '')}{cam.name}_"
        if media == "VIDEO":
            fr = _frames(frames, sc)
            sc.frame_start, sc.frame_end = fr[0], fr[-1]
            r.filepath = stem
            t = time.time()
            bpy.ops.render.render(animation=True)
            times.append(time.time() - t)
            files += sorted(f for f in glob.glob(glob.escape(stem) + "*" + ext)  # Blender adds the frame range
                            if os.path.getsize(f) > 0 and os.path.getmtime(f) >= t - 1)
            continue
        for f in _frames(frames, sc):
            sc.frame_set(f)
            path = f"{stem}{f:04d}{ext}"
            r.filepath = path
            t = time.time()
            bpy.ops.render.render(write_still=True)
            times.append(time.time() - t)
            files.append(path)
    eng = {"CYCLES": (sc.cycles, "samples", "cycles"), "BLENDER_EEVEE": (sc.eevee, "taa_render_samples", "eevee")}
    pct, size = r.resolution_percentage, [r.resolution_x * r.resolution_percentage // 100,
                                          r.resolution_y * r.resolution_percentage // 100]
    spp, reduced = None, []
    if r.engine in eng:
        owner, key, group = eng[r.engine]
        ref = preset if preset != "preview" else "final"
        spp, want = getattr(owner, key), PRESETS[ref][group][key]
        if spp < want:
            reduced.append(f"samples {spp} < {ref} preset {want}")
    if pct < 100:
        reduced.append(f"resolution {pct}%")
    deliverable = preset != "preview" and pct >= 100
    if not deliverable:
        info["quality"] = "preview"
        warn.insert(0, f"preview quality ({f'{spp} samples, ' if spp else ''}{pct}% = {size[0]}x{size[1]}): "
                       "for looking, not for delivery. Use --preset final or product.")
    if warn:
        info["warning"] = "; ".join(warn)
    info.update({"ok": bool(files) and all(os.path.exists(f) and os.path.getsize(f) > 0 for f in files),
                 "files": files, "sec_per_image": round(sum(times) / max(len(times), 1), 2), "res": size,
                 "view": sc.view_settings.view_transform, "preset": preset, "samples": spp, "percent": pct,
                 "deliverable": deliverable, "reduced": reduced, "seconds_total": round(time.time() - t0, 2)})
    return info


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--engine", default=None)
    p.add_argument("--preset", default="preview", choices=list(PRESETS))
    p.add_argument("--res", nargs=2, type=int, default=None)
    p.add_argument("--percent", type=int, default=None)
    p.add_argument("--samples", type=int, default=None)
    p.add_argument("--out", default="//render/####")
    p.add_argument("--format", default="PNG", choices=list(FORMATS))
    p.add_argument("--frames", default=None)
    p.add_argument("--cameras", nargs="*", default=None)
    p.add_argument("--view", default=None)
    p.add_argument("--look", default=None)
    p.add_argument("--transparent", action="store_true", default=None)
    p.add_argument("--device", default="GPU", choices=["GPU", "CPU"])
    bx.cli(run, p)
