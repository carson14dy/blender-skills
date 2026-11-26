#!/usr/bin/env python3
"""topaz_manifest — what goes to the Topaz upscaler (Higgsfield upscale_video), what never does, and what came back.

    python3 topaz_manifest.py OUTDIR [--video turntable_1080p.mp4] [--resolution 2160p]
        writes OUTDIR/topaz_manifest.json: ONE entry (the turntable video -> upscale_video, provider topaz, 2160p,
        aspect_ratio auto) and the not_sent list with reasons. Probes the video with ffprobe when it exists.
    python3 topaz_manifest.py OUTDIR --record --job-id ID [--credits N] [--seconds S] [--video-id ID]
                              [--result-url URL] [--upscaled FILE.mp4] [--expect-height 2160] [--link]
        records the run on the entry; with --upscaled runs the 3-frame comparison (ffmpeg): output size, frame
        count +/- 1 and duration +/- 0.1 s, then three timestamps (15 / 50 / 85 %): the upscaled frame is scaled back
        to the source size and compared (luma PSNR, gradient correlation, edge overlap) - side-by-side crops go to
        OUTDIR/topaz_compare/. --link (verdict pass only) merges video4kUrl into OUTDIR/media.json for the studio.

Nothing here calls Higgsfield or spends credits: the session runs the MCP calls (procedure in the manifest).
upscale_video has NO cost preview: before the FIRST paid run ask the client, then read `transactions` and record the
credits here and in the runbook's "Measured so far" table. Topaz raises delivery resolution; it does not regenerate
geometry, but it can sharpen or smear fine detail, so the measured Blender model and report stay the source of truth
and the 4K file is labelled "upscaled with Topaz (video only)".
Exit codes: 0 ok (or comparison pass), 1 input error, 2 comparison says check (deliver the 1080p file and say so).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys

import numpy as np

LABEL = "upscaled with Topaz (video only)"
REASON = "video only; raises delivery resolution, geometry is not regenerated"
NOT_SENT = [
    {"what": "stills (hero_street, aerial_34, top_down)",
     "reason": "rendered natively at 3840x2160 in Blender from the measured model: exact, no upscaler needed"},
    {"what": "roof diagrams (length, pitch, area, summary)",
     "reason": "vector SVG + 300 dpi PNG drawn from model.json / report.json: no raster to upscale"},
    {"what": "3DGRUT splat and its training views",
     "reason": "not deliverables: the splat is a visual layer trained on renders, never a measurement source"},
    {"what": "real photos (listing, owner, street-level, inspection)",
     "reason": "never sent to a third-party service; they stay in the job folder"},
]
THRESH = {"psnr_db": 30.0, "grad_corr": 0.90, "edge_iou": 0.60, "frames_tol": 1, "duration_tol_s": 0.1}
MCP_PROCEDURE = [
    "First run only: ask the client before spending (upscale_video has no cost preview); read `balance` first.",
    "media_upload {filename: 'turntable_1080p.mp4', content_type: 'video/mp4'} -> PUT the bytes to upload_url "
    "(curl -T, expect HTTP 200; on the GPU box the MP4 is PUT straight from the box) -> "
    "media_confirm {type: 'video', media_id} -> that media_id is the video_id.",
    "upscale_video {params: {provider: 'topaz', video_id: <media_id>, resolution: '2160p', aspect_ratio: 'auto'}} "
    "-> job id (no width / height / fps for topaz; those are bytedance-only).",
    "jobs_wait {jobs: [{index: 0, job_id}], timeout_seconds: 15}, repeated while all_terminal is false; download "
    "the result URL into OUTDIR/turntable_2160p_topaz.mp4.",
    "transactions -> the credits of this job; then: topaz_manifest.py OUTDIR --record --job-id ... --credits ... "
    "--seconds ... --video-id ... --upscaled OUTDIR/turntable_2160p_topaz.mp4 --result-url <url> --link",
]
CLI_NOTE = ("Higgsfield CLI (npm @higgsfield/cli 1.2.2 installs the `hf` Go binary; login is browser OAuth with a "
            "localhost callback, so it works on the client's own computer, not in a cloud container). A static read "
            "of the linux binary's strings (it was not run) shows `upload create <file>`, `generate create <job_type> "
            "[--param value]` (local files auto-uploaded), `generate cost`, `generate wait <job_id>`, `generate get "
            "<job_id> --json`, `model list --video`, `model get <job_type> --json`; job types compiled in include "
            "topaz_video, bytedance_video_upscale, flux_video_upscale and sora2_video_upscale. topaz_video's "
            "parameter names are NOT verified: run `higgsfield model get topaz_video --json` first and stop if it is "
            "missing; never guess parameters. No GPU-rental commands: the box is MCP-only.")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def probe(path):
    """ffprobe -> {width, height, frames, duration_s, fps, codec, bytes, sha256}; None fields when unavailable."""
    info = {"file": os.path.basename(path), "bytes": os.path.getsize(path), "sha256": sha256(path)}
    if not shutil.which("ffprobe"):
        info["probe"] = "ffprobe not installed"
        return info
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=width,height,codec_name,r_frame_rate,nb_read_packets:format=duration", "-of", "json",
                        path], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        s = d["streams"][0]
        num, den = (float(v) for v in s.get("r_frame_rate", "0/1").split("/"))
        info.update(width=int(s["width"]), height=int(s["height"]), codec=s.get("codec_name"),
                    frames=int(s.get("nb_read_packets", 0)), fps=num / den if den else None,
                    duration_s=float(d.get("format", {}).get("duration", 0.0)))
    except (ValueError, KeyError, IndexError):
        info["probe"] = f"ffprobe failed: {r.stderr[-200:]}"
    return info


def frame_at(path, t):
    from PIL import Image
    import io
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-f", "image2pipe",
                        "-vcodec", "png", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"ffmpeg could not read a frame at {t:.2f} s of {path}: {r.stderr[-200:]!r}")
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def _luma(im):
    a = np.asarray(im, float) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _grad(y):
    gx = np.zeros_like(y); gy = np.zeros_like(y)
    gx[:, 1:-1] = y[:, 2:] - y[:, :-2]
    gy[1:-1, :] = y[2:, :] - y[:-2, :]
    return np.hypot(gx, gy)


def _dilate(m, r=1):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def compare_frames(src_im, up_im):
    """Metrics of the upscaled frame scaled back to the source size against the source frame."""
    from PIL import Image
    down = up_im.resize(src_im.size, Image.LANCZOS)
    a, b = _luma(src_im), _luma(down)
    mse = float(np.mean((a - b) ** 2))
    psnr = 99.0 if mse <= 1e-12 else float(10 * np.log10(1.0 / mse))
    ga, gb = _grad(a), _grad(b)
    gc = float(np.corrcoef(ga.ravel(), gb.ravel())[0, 1]) if ga.std() > 1e-9 and gb.std() > 1e-9 else 1.0
    ta, tb = np.quantile(ga, 0.9), np.quantile(gb, 0.9)
    ea, eb = ga > max(ta, 1e-6), gb > max(tb, 1e-6)
    inter = np.sum(ea & _dilate(eb)) + np.sum(eb & _dilate(ea))
    iou = float(inter / max(np.sum(ea) + np.sum(eb), 1))
    ok = psnr >= THRESH["psnr_db"] and gc >= THRESH["grad_corr"] and iou >= THRESH["edge_iou"]
    return {"psnr_db": round(psnr, 2), "grad_corr": round(gc, 4), "edge_iou": round(iou, 4), "pass": bool(ok)}


def side_by_side(src_im, up_im, out_png, crop=0.3):
    """Centre crop of the source (scaled up to the upscaled size, nearest) next to the same crop of the 4K frame."""
    from PIL import Image
    W, H = up_im.size
    cw, ch = int(W * crop), int(H * crop)
    x0, y0 = (W - cw) // 2, (H - ch) // 2
    big = src_im.resize((W, H), Image.NEAREST).crop((x0, y0, x0 + cw, y0 + ch))
    ups = up_im.crop((x0, y0, x0 + cw, y0 + ch))
    sheet = Image.new("RGB", (2 * cw + 8, ch), "white")
    sheet.paste(big, (0, 0)); sheet.paste(ups, (cw + 8, 0))
    sheet.save(out_png)


def compare_videos(src, up, outdir, expect_height=2160):
    ps, pu = probe(src), probe(up)
    res = {"source": ps, "upscaled": pu, "checks": {}, "frames": []}
    if "width" not in ps or "width" not in pu:
        res["verdict"] = "check"
        res["reason"] = "ffprobe could not read one of the videos"
        return res
    exp_w = int(round(ps["width"] * expect_height / ps["height"] / 2) * 2)
    c = res["checks"]
    c["size"] = {"expected": [exp_w, expect_height], "got": [pu["width"], pu["height"]],
                 "ok": abs(pu["width"] - exp_w) <= 2 and pu["height"] == expect_height}
    c["frames"] = {"source": ps.get("frames"), "upscaled": pu.get("frames"),
                   "ok": abs((pu.get("frames") or 0) - (ps.get("frames") or 0)) <= THRESH["frames_tol"]}
    c["duration"] = {"source": ps.get("duration_s"), "upscaled": pu.get("duration_s"),
                     "ok": abs((pu.get("duration_s") or 0) - (ps.get("duration_s") or 0)) <= THRESH["duration_tol_s"]}
    os.makedirs(os.path.join(outdir, "topaz_compare"), exist_ok=True)
    dur = ps.get("duration_s") or 0.0
    for k, f in enumerate((0.15, 0.50, 0.85), start=1):
        t = dur * f
        a, b = frame_at(src, t), frame_at(up, t)
        m = compare_frames(a, b)
        png = os.path.join(outdir, "topaz_compare", f"t{k}.png")
        side_by_side(a, b, png)
        res["frames"].append({"t_s": round(t, 3), **m, "side_by_side": os.path.relpath(png, outdir)})
    ok = all(v["ok"] for v in c.values()) and all(f["pass"] for f in res["frames"])
    res["verdict"] = "pass" if ok else "check"
    res["thresholds"] = THRESH
    if not ok:
        res["action"] = "deliver the 1080p turntable and say the 4K upscale did not pass the geometry check"
    return res


def plan(outdir, video, resolution):
    p = os.path.join(outdir, video)
    entry = {"file": video, "tool": "upscale_video",
             "params": {"provider": "topaz", "video_id": None, "resolution": resolution, "aspect_ratio": "auto"},
             "reason": REASON, "label": LABEL, "status": "planned" if os.path.exists(p) else "video not rendered yet",
             "result_file": f"turntable_{resolution}_topaz.mp4"}
    if os.path.exists(p):
        entry["source"] = probe(p)
    return {"schema": "topaz_manifest/1", "written": dt.datetime.now().isoformat(timespec="seconds"),
            "entries": [entry], "not_sent": NOT_SENT,
            "cost": {"preflight": "none: upscale_video has no cost preview",
                     "rule": "ask the client before the first paid run; record credits from `transactions` after "
                             "each run (here and in the runbook's 'Measured so far' table)"},
            "truth": "the measured Blender model and report are the source of truth; upscaled media are labelled "
                     f"'{LABEL}' and no measurement is taken from them",
            "mcp_procedure": MCP_PROCEDURE, "cli": CLI_NOTE}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--video", default="turntable_1080p.mp4")
    ap.add_argument("--resolution", default="2160p")
    ap.add_argument("--out")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--job-id")
    ap.add_argument("--video-id")
    ap.add_argument("--credits", type=float)
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--result-url")
    ap.add_argument("--upscaled")
    ap.add_argument("--expect-height", type=int)
    ap.add_argument("--link", action="store_true", help="on pass: put video4kUrl into OUTDIR/media.json")
    a = ap.parse_args(argv)
    outdir = os.path.abspath(a.outdir)
    if not os.path.isdir(outdir):
        print(f"topaz_manifest: no folder {outdir}", file=sys.stderr)
        return 1
    mp = a.out or os.path.join(outdir, "topaz_manifest.json")
    if not a.record:
        doc = plan(outdir, a.video, a.resolution)
        with open(mp, "w") as f:
            json.dump(doc, f, indent=1)
        print(json.dumps({"manifest": mp, "entries": len(doc["entries"]), "status": doc["entries"][0]["status"],
                          "not_sent": len(doc["not_sent"])}))
        return 0
    if not a.job_id:
        print("topaz_manifest: --record needs --job-id", file=sys.stderr)
        return 1
    try:
        with open(mp) as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = plan(outdir, a.video, a.resolution)
    e = doc["entries"][0]
    if a.video_id:
        e["params"]["video_id"] = a.video_id
    run = {"job_id": a.job_id, "credits": a.credits, "seconds": a.seconds, "result_url": a.result_url,
           "recorded": dt.datetime.now().isoformat(timespec="seconds")}
    code = 0
    if a.upscaled:
        src = os.path.join(outdir, e["file"])
        if not (os.path.exists(src) and os.path.exists(a.upscaled)):
            print("topaz_manifest: --upscaled needs both the source video and the upscaled file", file=sys.stderr)
            return 1
        if not shutil.which("ffmpeg"):
            print("topaz_manifest: ffmpeg is needed for the comparison", file=sys.stderr)
            return 1
        eh = a.expect_height or int(str(e["params"]["resolution"]).rstrip("p"))
        run["comparison"] = compare_videos(src, a.upscaled, outdir, eh)
        run["verdict"] = run["comparison"]["verdict"]
        code = 0 if run["verdict"] == "pass" else 2
        if run["verdict"] == "pass" and a.link and a.result_url:
            mj = os.path.join(outdir, "media.json")
            try:
                with open(mj) as f:
                    media = json.load(f)
            except (OSError, ValueError):
                media = {}
            media.update(video4kUrl=a.result_url, video4kLabel=LABEL)
            with open(mj, "w") as f:
                json.dump(media, f, indent=1)
            run["linked"] = os.path.relpath(mj, outdir)
    e.setdefault("runs", []).append(run)
    e["status"] = "upscaled" + (f" ({run['verdict']})" if "verdict" in run else "")
    with open(mp, "w") as f:
        json.dump(doc, f, indent=1)
    print(json.dumps({"manifest": mp, "job_id": a.job_id, "credits": a.credits, "seconds": a.seconds,
                      "verdict": run.get("verdict")}))
    if a.credits is not None:
        print(f"runbook 'Measured so far' row: Topaz 2160p | {e.get('source', {}).get('duration_s', '?')} s source | "
              f"{a.credits:g} credits | {a.seconds if a.seconds is not None else '?'} s | job {a.job_id}")
    return code


if __name__ == "__main__":
    sys.exit(main())
