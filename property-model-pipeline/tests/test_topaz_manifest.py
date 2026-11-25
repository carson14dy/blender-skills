"""Topaz manifest (scripts/topaz_manifest.py): one entry (the turntable -> upscale_video, provider topaz, 2160p,
aspect auto), the not-sent list, run records, and the 3-frame comparison on synthetic videos (ffmpeg only).
Never calls Higgsfield."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import topaz_manifest as TM  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _video(path, vf=None, size="320x180", seconds=2):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24", "-t", str(seconds)]
    if vf:
        cmd += ["-vf", vf]
    subprocess.run(cmd + ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", str(path)], check=True)


def _upscale(src, dst, vf):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-crf", "16", str(dst)], check=True)


def test_manifest_contents_without_video(tmp_path):
    assert TM.main([str(tmp_path)]) == 0
    d = json.load(open(tmp_path / "topaz_manifest.json"))
    assert len(d["entries"]) == 1
    e = d["entries"][0]
    assert e["file"] == "turntable_1080p.mp4" and e["tool"] == "upscale_video"
    assert e["params"] == {"provider": "topaz", "video_id": None, "resolution": "2160p", "aspect_ratio": "auto"}
    assert e["reason"] == "video only; raises delivery resolution, geometry is not regenerated"
    assert e["label"] == "upscaled with Topaz (video only)" and e["status"] == "video not rendered yet"
    ns = d["not_sent"]
    assert len(ns) == 4 and all(x["reason"] for x in ns)
    text = json.dumps(ns).lower()
    for word in ("stills", "3840x2160", "diagrams", "vector", "splat", "training views", "not deliverables",
                 "real photos", "never sent"):
        assert word in text, word
    assert "no cost preview" in d["cost"]["preflight"] and "first paid run" in d["cost"]["rule"]
    assert any("upscale_video" in s and "'topaz'" in s for s in d["mcp_procedure"])
    assert "topaz_video" in d["cli"] and "NOT verified" in d["cli"]


def test_record_needs_job_id(tmp_path):
    TM.main([str(tmp_path)])
    assert TM.main([str(tmp_path), "--record"]) == 1


def test_record_without_comparison(tmp_path):
    TM.main([str(tmp_path)])
    assert TM.main([str(tmp_path), "--record", "--job-id", "job-1", "--credits", "40", "--seconds", "120",
                    "--video-id", "vid-9"]) == 0
    e = json.load(open(tmp_path / "topaz_manifest.json"))["entries"][0]
    assert e["params"]["video_id"] == "vid-9"
    r = e["runs"][-1]
    assert (r["job_id"], r["credits"], r["seconds"]) == ("job-1", 40.0, 120.0) and "verdict" not in r


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg / ffprobe not installed")
def test_probe_and_three_frame_comparison(tmp_path):
    _video(tmp_path / "turntable_1080p.mp4")
    assert TM.main([str(tmp_path)]) == 0
    e = json.load(open(tmp_path / "topaz_manifest.json"))["entries"][0]
    assert e["status"] == "planned" and e["source"]["width"] == 320 and e["source"]["frames"] == 48
    good, bad = tmp_path / "good.mp4", tmp_path / "bad.mp4"
    _upscale(tmp_path / "turntable_1080p.mp4", good, "scale=640:360:flags=lanczos")
    _upscale(tmp_path / "turntable_1080p.mp4", bad, "scale=640:360,rotate=0.06:fillcolor=black")   # bent geometry
    code = TM.main([str(tmp_path), "--record", "--job-id", "j-good", "--credits", "12", "--seconds", "90",
                    "--upscaled", str(good), "--expect-height", "360", "--result-url", "https://example.invalid/4k.mp4",
                    "--link"])
    assert code == 0
    run = json.load(open(tmp_path / "topaz_manifest.json"))["entries"][0]["runs"][-1]
    cmp_ = run["comparison"]
    assert run["verdict"] == "pass" and len(cmp_["frames"]) == 3
    assert all(c["ok"] for c in cmp_["checks"].values())
    assert all(f["psnr_db"] >= 30 and os.path.exists(tmp_path / f["side_by_side"]) for f in cmp_["frames"])
    media = json.load(open(tmp_path / "media.json"))
    assert media["video4kUrl"] == "https://example.invalid/4k.mp4" and "Topaz" in media["video4kLabel"]
    os.remove(tmp_path / "media.json")
    code = TM.main([str(tmp_path), "--record", "--job-id", "j-bad", "--upscaled", str(bad), "--expect-height", "360",
                    "--result-url", "https://example.invalid/bad.mp4", "--link"])
    assert code == 2
    run = json.load(open(tmp_path / "topaz_manifest.json"))["entries"][0]["runs"][-1]
    assert run["verdict"] == "check" and "1080p" in run["comparison"]["action"]
    assert not (tmp_path / "media.json").exists()                     # a failed check is never linked
    # wrong output size (not 2160p-equivalent here: 360) fails the size check even if the frames match
    small = tmp_path / "small.mp4"
    _upscale(tmp_path / "turntable_1080p.mp4", small, "scale=480:270:flags=lanczos")
    assert TM.main([str(tmp_path), "--record", "--job-id", "j-size", "--upscaled", str(small), "--expect-height",
                    "360"]) == 2
    run = json.load(open(tmp_path / "topaz_manifest.json"))["entries"][0]["runs"][-1]
    assert not run["comparison"]["checks"]["size"]["ok"]
