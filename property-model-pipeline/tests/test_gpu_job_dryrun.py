"""scripts/gpu: the GPU box job without a GPU (synthetic data only).

* gpu_job.sh: argument checks, DRY_RUN stage order and markers, the FAIL and SPLAT_SKIPPED paths, a re-run
  moving old markers to history, the run lock, a real bundle failure, and a stub end-to-end run (fake
  renderer, fake 3DGRUT, local PUT server; real ffmpeg, holdout ordering, splat compression, results.zip)
  with resume and an upload-only re-run.
* train_splat.sh against a fake 3DGRUT checkout (metrics plumbing, the PSNR gate).
* compress_splat.py: synthetic 1,000-gaussian PLY round trip, size caps, the z-up -> y-up conversion,
  cropping, the JSON form, and the held-out ordering.
* higgsfield_cli.sh against a fake CLI; shellcheck on every script when it is installed.
"""
import base64
import http.server
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import threading
import zipfile

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GPU = os.path.abspath(os.path.join(HERE, "..", "scripts", "gpu"))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
JOB = os.path.join(GPU, "gpu_job.sh")
TRAIN = os.path.join(GPU, "train_splat.sh")
GRUT = os.path.join(GPU, "grut_env.sh")
COMPRESS = os.path.join(GPU, "compress_splat.py")
HFCLI = os.path.join(GPU, "higgsfield_cli.sh")
SCRIPTS = [JOB, TRAIN, GRUT, HFCLI]
sys.path.insert(0, GPU)
import compress_splat as CS  # noqa: E402

DRY_ORDER = ["bundle", "env", "stills", "turntable", "encode", "upload_media", "train_views", "grut_wait", "train",
             "compress", "results"]
HAVE_MEDIA_TOOLS = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def run_job(tmp, job_id="job-test1", dry=True, extra=None, args=()):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PUT_", "BUNDLE_", "DRY_", "SKIP_", "UPLOAD_"))}
    env.update({"RL_ROOT": str(tmp), "POLL_S": "0.1", "DRY_RUN": "1" if dry else "0"})
    env.update(extra or {})
    return subprocess.run(["bash", JOB, job_id, *args], env=env, capture_output=True, text=True, timeout=300)


def status_events(tmp, job_id="job-test1"):
    """-> [(stage, text)] from logs/ID.status ("TIME +Ns STAGE TEXT")."""
    out = []
    for line in open(os.path.join(tmp, "logs", f"{job_id}.status")):
        parts = line.rstrip("\n").split(" ", 3)
        out.append((parts[2], parts[3] if len(parts) > 3 else ""))
    return out


def markers(tmp, job_id="job-test1"):
    d = os.path.join(tmp, "out", job_id)
    return sorted(n for n in os.listdir(d) if n.endswith(".marker"))


def read_kv(path):
    d = {}
    for line in open(path):
        if "=" in line and not line.startswith("---"):
            k, v = line.rstrip("\n").split("=", 1)
            d.setdefault(k, v)
    return d


# ------------------------------------------------------------------------------------------ arguments

@pytest.mark.parametrize("args, code, needle", [
    ((), 2, "gpu_job.sh ID"),
    (("--help",), 0, "Stage order"),
    (("Job One",), 2, "bad ID"),
    (("12-elm-st",), 2, "house number"),
    (("ab",), 2, "bad ID"),
    (("job-a", "job-b"), 2, "one ID only"),
    (("job-a", "--bogus"), 2, "unknown option"),
])
def test_arguments(tmp_path, args, code, needle):
    env = dict(os.environ, RL_ROOT=str(tmp_path))
    r = subprocess.run(["bash", JOB, *args], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == code, r.stderr
    assert needle in r.stdout + r.stderr


def test_bad_tt_size(tmp_path):
    r = run_job(tmp_path, extra={"TT_SIZE": "huge"})
    assert r.returncode == 2 and "TT_SIZE" in r.stderr


# ------------------------------------------------------------------------------------------ dry run

def test_dry_run_order_and_markers(tmp_path):
    r = run_job(tmp_path, extra={"BUNDLE_URL": "https://example.invalid/b.zip?sig=SECRET1",
                                 "PUT_MP4": "https://up.invalid/m?X-Signature=SECRET2",
                                 "PUT_STILLS": "hero_street.jpg=https://up.invalid/h?s=SECRET3",
                                 "PUT_RESULTS": "https://up.invalid/r?s=SECRET4"})
    assert r.returncode == 0, r.stdout + r.stderr
    ev = status_events(tmp_path)
    starts = [s for s, t in ev if t == "start"]
    assert starts == ["job"] * 0 + DRY_ORDER
    oks = [s for s, t in ev if t.startswith("ok ")]
    assert oks == DRY_ORDER
    assert ev[0][0] == "job" and ev[0][1].startswith("start id=job-test1 dry_run=1")
    assert ev[-1][0] == "job" and "DONE.marker written" in ev[-1][1]
    # encode.marker comes before the splat stages (Topaz starts while the splat trains)
    i_enc = next(i for i, (s, t) in enumerate(ev) if "encode.marker written" in t)
    i_train = next(i for i, (s, t) in enumerate(ev) if s == "train" and t == "start")
    assert i_enc < i_train
    assert markers(tmp_path) == ["DONE.marker", "encode.marker"]
    done = read_kv(tmp_path / "out" / "job-test1" / "DONE.marker")
    assert done["status"] == "done" and done["splat"] == "ok" and done["dry_run"] == "1"
    plan = open(tmp_path / "out" / "job-test1" / "plan.txt").read()
    assert "render_demo.py" in plan and "--only stills" in plan and "--only turntable" in plan and "--only train" in plan
    assert "-crf 18 -pix_fmt yuv420p" in plan and "train_splat.sh" in plan and "compress_splat.py compress" in plan
    assert "SECRET" not in plan and "SECRET" not in r.stdout          # presigned signatures are redacted
    t = json.load(open(tmp_path / "out" / "job-test1" / "timings.json"))
    assert t["dry_run"] is True and list(t["stages"]) == DRY_ORDER
    # a dry run never writes resume markers that would make a real run skip work
    assert not [n for n in os.listdir(tmp_path / "out" / "job-test1" / "stages") if n.endswith(".ok")]


def test_dry_fail_path(tmp_path):
    r = run_job(tmp_path, extra={"DRY_FAIL": "turntable"})
    assert r.returncode == 1
    assert markers(tmp_path) == ["FAIL.marker"]
    fm = read_kv(tmp_path / "out" / "job-test1" / "FAIL.marker")
    assert fm["stage"] == "turntable" and "turntable" in fm["reason"]
    assert "simulated failure" in open(tmp_path / "out" / "job-test1" / "FAIL.marker").read()
    starts = [s for s, t in status_events(tmp_path) if t == "start"]
    assert starts == DRY_ORDER[:4]                     # nothing runs after the failed stage
    assert not os.path.exists(tmp_path / "out" / "job-test1" / ".lock")


@pytest.mark.parametrize("stage", ["train_views", "grut_env", "train", "compress"])
def test_dry_splat_failure_still_done(tmp_path, stage):
    r = run_job(tmp_path, extra={"DRY_FAIL": stage})
    assert r.returncode == 0, r.stdout + r.stderr
    assert markers(tmp_path) == ["DONE.marker", "SPLAT_SKIPPED.marker", "encode.marker"]
    assert read_kv(tmp_path / "out" / "job-test1" / "DONE.marker")["splat"] == "skipped"
    ev = status_events(tmp_path)
    assert [s for s, t in ev if t == "start"][-1] == "results"
    assert any("SPLAT_SKIPPED" in t for s, t in ev)


def test_skip_splat(tmp_path):
    r = run_job(tmp_path, extra={"SKIP_SPLAT": "1"})
    assert r.returncode == 0
    ev = status_events(tmp_path)
    assert [s for s, t in ev if t == "start"] == ["bundle", "env", "stills", "turntable", "encode", "upload_media", "results"]
    sk = read_kv(tmp_path / "out" / "job-test1" / "SPLAT_SKIPPED.marker")
    assert "SKIP_SPLAT" in sk["reason"]
    assert "grut_env" not in open(tmp_path / "out" / "job-test1" / "plan.txt").read()


def test_rerun_moves_old_markers_to_history(tmp_path):
    assert run_job(tmp_path, extra={"DRY_FAIL": "stills"}).returncode == 1
    assert run_job(tmp_path).returncode == 0
    assert markers(tmp_path) == ["DONE.marker", "encode.marker"]
    hist = tmp_path / "out" / "job-test1" / "history"
    assert any((hist / d / "FAIL.marker").exists() for d in os.listdir(hist))


def test_lock_refuses_second_copy(tmp_path):
    lock = tmp_path / "out" / "job-test1" / ".lock"
    lock.mkdir(parents=True)
    boot = open("/proc/sys/kernel/random/boot_id").read().strip() if os.path.exists("/proc/sys/kernel/random/boot_id") \
        else socket.gethostname()
    (lock / "owner").write_text(f"{boot} {os.getpid()}\n")          # a live process on this machine holds it
    r = run_job(tmp_path)
    assert r.returncode == 0 and "already running" in r.stdout
    assert not os.path.exists(tmp_path / "logs" / "job-test1.status")
    (lock / "owner").write_text("another-box 1\n")                    # stale lock from a stopped box
    assert run_job(tmp_path).returncode == 0
    assert markers(tmp_path) == ["DONE.marker", "encode.marker"]


def test_real_bundle_failure_writes_fail_marker(tmp_path):
    r = run_job(tmp_path, dry=False, extra={"BUNDLE_URL": f"file://{tmp_path}/missing.zip", "SKIP_ENV": "1"})
    assert r.returncode == 1
    assert markers(tmp_path) == ["FAIL.marker"]
    fm = read_kv(tmp_path / "out" / "job-test1" / "FAIL.marker")
    assert fm["stage"] == "bundle"
    assert [s for s, t in status_events(tmp_path) if t == "start"] == ["bundle"]


# ------------------------------------------------------------------------------------------ stub end to end

FAKE_RENDER = r'''
import argparse, json, os, sys
from PIL import Image
ap = argparse.ArgumentParser()
ap.add_argument("blend"); ap.add_argument("out"); ap.add_argument("--job"); ap.add_argument("--device")
ap.add_argument("--only"); ap.add_argument("--tt-size")
a = ap.parse_args()
job = json.load(open(a.job))
log = open(os.path.join(a.out, "..", "fake_render.log"), "a") if os.path.isdir(os.path.join(a.out, "..")) else sys.stdout
os.makedirs(a.out, exist_ok=True)
def img(path, i, size=(64, 36)):
    if os.path.exists(path):
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, (40 + (i * 7) % 200, 120, 200 - (i * 5) % 150)).save(path)
    return 1
n = 0
if a.only == "stills":
    for i, s in enumerate(["hero_street", "aerial_34", "top_down"]):
        n += img(os.path.join(a.out, "stills", s + ".png"), i, (96, 54))
elif a.only == "turntable":
    for i in range(job["turntable"]["frames"]):
        n += img(os.path.join(a.out, "turntable", f"frame_{i:04d}.png"), i)
elif a.only == "train":
    root = os.path.join(a.out, "train", "colmap")
    names = [f"ring/ring_{i:03d}.png" for i in range(20)] + [f"holdout/holdout_{i:03d}.png" for i in range(4)]
    for i, nm in enumerate(names):
        n += img(os.path.join(root, "images", nm), i)
    sp = os.path.join(root, "sparse", "0"); os.makedirs(sp, exist_ok=True)
    open(os.path.join(sp, "cameras.txt"), "w").write("1 OPENCV 64 36 50 50 32 18 0 0 0 0\n")
    with open(os.path.join(sp, "images.txt"), "w") as f:
        f.write("# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME\n")
        for i, nm in enumerate(names, 1):
            f.write(f"{i} 1 0 0 0 0 0 {5 + i} 1 {nm}\n\n")
    with open(os.path.join(sp, "points3D.txt"), "w") as f:
        for i, (x, y, z) in enumerate([(-10, -10, 0), (10, 10, 6), (0, 0, 3)], 1):
            f.write(f"{i} {x} {y} {z} 128 128 128 0 1 0 2 0\n")
print(f"fake render {a.only}: {n} new files", file=log)
print(f"fake render {a.only}: {n} new files")
'''

FAKE_TRAIN_PY = r'''
import json, os, subprocess, sys
kv = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
ds = kv["path"]
assert os.path.isfile(os.path.join(ds, "sparse", "0", "images.txt")), ds
assert kv["export_ply.enabled"] == "true" and int(kv["n_iterations"]) > 0
open(os.path.join(os.path.dirname(kv["export_ply.path"]), "train_args.json"), "w").write(json.dumps(kv))
subprocess.check_call([sys.executable, os.environ["FAKE_COMPRESS"], "synth", kv["export_ply.path"], "--n", "1500"])
run = os.path.join(kv["out_dir"], kv["experiment_name"] + "-251125_120000")
os.makedirs(run, exist_ok=True)
json.dump({"mean_psnr": float(os.environ.get("FAKE_PSNR", "31.5")), "mean_ssim": 0.95, "mean_lpips": 0.05},
          open(os.path.join(run, "metrics.json"), "w"))
print("fake 3DGRUT trained", kv["dataset.test_split_interval"])
'''


def make_fake_grut(root):
    venv = root / ".venv" / "bin"
    venv.mkdir(parents=True)
    os.symlink(sys.executable, venv / "python")
    (venv / "activate").write_text(f'export PATH="{venv}:$PATH"\n')
    (root / "train.py").write_text(FAKE_TRAIN_PY)
    return root


class PutStore(http.server.BaseHTTPRequestHandler):
    store = {}

    def do_PUT(self):
        n = int(self.headers.get("Content-Length", 0))
        PutStore.store[self.path.split("?")[0]] = (self.headers.get("Content-Type"), self.rfile.read(n))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def put_server():
    PutStore.store = {}
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PutStore)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", PutStore.store
    srv.shutdown()


@pytest.mark.skipif(not (HAVE_MEDIA_TOOLS and HAVE_PIL), reason="needs ffmpeg, ffprobe and Pillow")
def test_stub_end_to_end_resume_and_upload_only(tmp_path, put_server):
    base, store = put_server
    work = tmp_path / "work"
    work.mkdir()
    (work / "render_demo.py").write_text(FAKE_RENDER)
    grut = make_fake_grut(tmp_path / "fake3dgrut")
    (work / "grut_env.sh").write_text("#!/bin/bash\necho fake grut env ready\n")
    bdir = work / "bundle"
    bdir.mkdir()
    (bdir / "model_site.blend").write_bytes(b"BLENDER-fake")
    (bdir / "render_job.json").write_text(json.dumps({"id": "job-test1", "turntable": {"frames": 30, "fps": 24}}))
    with zipfile.ZipFile(work / "render_bundle.zip", "w") as z:
        for p in bdir.iterdir():
            z.write(p, p.name)
    rl = tmp_path / "rl"
    put_json = work / "put.json"
    put_json.write_text(json.dumps({"turntable.mp4": f"{base}/mp4?sig=x", "hero_street.jpg": f"{base}/hero?sig=x",
                                    "aerial_34.jpg": f"{base}/aerial?sig=x", "top_down.jpg": f"{base}/top?sig=x",
                                    "results.zip": f"{base}/results?sig=x"}))
    extra = {"BUNDLE_URL": f"file://{work}/render_bundle.zip", "SKIP_ENV": "1", "DEVICE": "cpu",
             "PY_BLENDER": sys.executable, "RENDER_DEMO": str(work / "render_demo.py"), "GRUT_ENV": str(work / "grut_env.sh"),
             "GRUT_DIR": str(grut), "FAKE_COMPRESS": COMPRESS, "PUT_JSON": str(put_json), "HELPER_PY": sys.executable}
    r = run_job(rl, dry=False, extra=extra)
    out = rl / "out" / "job-test1"
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert markers(rl) == ["DONE.marker", "encode.marker"], r.stdout[-3000:]
    done = read_kv(out / "DONE.marker")
    assert done["splat"] == "ok" and done["uploads_failed"] == "none" and done["results_upload"] == "ok"
    enc = read_kv(out / "encode.marker")
    assert enc["mp4_upload"] == "ok" and "hero_street.jpg:ok" in enc["stills_upload"]
    e = json.load(open(out / "encode.json"))
    assert e["frames"] == 30 and e["fps"] == 24 and e["height"] == 36
    assert set(store) == {"/mp4", "/hero", "/aerial", "/top", "/results"}
    assert store["/mp4"][0] == "video/mp4" and store["/hero"][0] == "image/jpeg" and store["/results"][0] == "application/octet-stream"
    assert store["/mp4"][1][4:8] == b"ftyp"
    # the held-out views sit on 3DGRUT's test slots
    split = json.load(open(out / "splat" / "dataset" / "split.json"))
    assert split["k"] == 6 and split["n_test"] == 4 and all(n.startswith("holdout/") for n in split["test"])
    args = json.load(open(out / "splat" / "train_args.json"))
    assert args["dataset.test_split_interval"] == "6"
    train = json.load(open(out / "splat" / "train.json"))
    assert train["psnr"] == 31.5 and train["psnr_ok"] is True
    info = json.load(open(out / "splat" / "compress.json"))
    assert info["written"] > 0 and info["raw_bytes"] == info["written"] * 32 and info["format"] == "splat.json"
    assert (out / "media" / "splat.splat.json").stat().st_size == info["bytes"] <= 11_000_000
    with zipfile.ZipFile(out / "results.zip") as z:
        names = set(z.namelist())
        assert {"media/turntable_36p.mp4", "media/hero_street.jpg", "media/splat.splat.json", "media/media.json",
                "timings.json", "qa.json", "status.txt", "encode.marker"} <= names
        assert not [n for n in names if n.endswith((".blend", ".ply", ".png"))]
        mj = json.loads(z.read("media/media.json"))
        assert mj["labels"]["splat"].startswith("visual layer") and mj["splat"]["state"] == "ok"
    assert store["/results"][1] == open(out / "results.zip", "rb").read()
    t = json.load(open(out / "timings.json"))
    assert [k for k in t["stages"]] == DRY_ORDER
    assert all(v["status"] == "ok" for v in t["stages"].values())

    # resume: a second run skips every finished stage (env, grut_wait and results always run)
    store.clear()
    r2 = run_job(rl, dry=False, extra=extra)
    assert r2.returncode == 0, r2.stdout[-2000:]
    ev = [(s, x) for s, x in status_events(rl) if x.startswith(("skip", "start"))]
    last_run = ev[max(i for i, (s, x) in enumerate(ev) if s == "bundle"):]
    skipped = [s for s, x in last_run if x.startswith("skip")]
    assert skipped == ["bundle", "stills", "turntable", "encode", "upload_media", "train_views", "grut_wait", "train",
                       "compress"]
    assert not any(s == "grut_env" for s, x in status_events(rl)[-12:])  # no 3DGRUT start when the splat is done
    assert markers(rl) == ["DONE.marker", "encode.marker"]          # encode.marker restored for the poll
    assert set(store) == {"/results"}

    # upload-only with fresh URLs (e.g. the first ones expired)
    store.clear()
    r3 = run_job(rl, dry=False, extra=extra, args=("--upload-only",))
    assert r3.returncode == 0, r3.stdout[-2000:]
    assert set(store) == {"/mp4", "/hero", "/aerial", "/top", "/results"}


@pytest.mark.skipif(not (HAVE_MEDIA_TOOLS and HAVE_PIL), reason="needs ffmpeg, ffprobe and Pillow")
def test_stub_low_psnr_ships_without_splat(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "render_demo.py").write_text(FAKE_RENDER)
    grut = make_fake_grut(tmp_path / "fake3dgrut")
    (work / "grut_env.sh").write_text("#!/bin/bash\nexit 0\n")
    bdir = work / "bundle"
    bdir.mkdir()
    (bdir / "model_site.blend").write_bytes(b"BLENDER-fake")
    (bdir / "render_job.json").write_text(json.dumps({"turntable": {"frames": 12}}))
    with zipfile.ZipFile(work / "b.zip", "w") as z:
        for p in bdir.iterdir():
            z.write(p, p.name)
    rl = tmp_path / "rl"
    extra = {"BUNDLE_URL": f"file://{work}/b.zip", "SKIP_ENV": "1", "DEVICE": "cpu", "PY_BLENDER": sys.executable,
             "RENDER_DEMO": str(work / "render_demo.py"), "GRUT_ENV": str(work / "grut_env.sh"), "GRUT_DIR": str(grut),
             "FAKE_COMPRESS": COMPRESS, "FAKE_PSNR": "21.0", "HELPER_PY": sys.executable}
    r = run_job(rl, dry=False, extra=extra)
    assert r.returncode == 0, r.stdout[-3000:]
    out = rl / "out" / "job-test1"
    assert markers(rl) == ["DONE.marker", "SPLAT_SKIPPED.marker", "encode.marker"]
    assert "PSNR below 28" in read_kv(out / "SPLAT_SKIPPED.marker")["reason"]
    assert not [n for n in os.listdir(out / "media") if n.startswith("splat.")]
    done = read_kv(out / "DONE.marker")
    assert done["splat"] == "skipped" and done["results_upload"] == "skipped"      # no PUT URL given


TINY_SCENE = r'''
import bpy, sys
out = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
def coll(name):
    c = bpy.data.collections.new(name); sc.collection.children.link(c); return c
def box(name, c, loc, size, color):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    for cc in list(o.users_collection): cc.objects.unlink(o)
    c.objects.link(o)
    m = bpy.data.materials.new(name); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    o.data.materials.append(m)
box("Wall box", coll("Walls"), (0, 0, 1.5), (8, 6, 3), (0.8, 0.8, 0.78, 1))
box("Roof slab", coll("Roof facets"), (0, 0, 3.2), (8.8, 6.8, 0.4), (0.25, 0.25, 0.27, 1))
box("Terrain (LiDAR ground)", coll("Site"), (0, 0, -0.05), (60, 60, 0.1), (0.30, 0.36, 0.26, 1))
bpy.ops.wm.save_as_mainfile(filepath=out, compress=False)
'''
RENDER_DEMO = os.path.join(HERE, "..", "scripts", "blender", "render_demo.py")
try:
    import importlib.util
    HAVE_BPY = importlib.util.find_spec("bpy") is not None
except Exception:
    HAVE_BPY = False


@pytest.mark.skipif(not (HAVE_BPY and os.path.isfile(RENDER_DEMO) and HAVE_MEDIA_TOOLS),
                    reason="needs bpy, scripts/blender/render_demo.py and ffmpeg")
def test_real_renderer_contract_cpu(tmp_path):
    """render_demo.py (owner D) on CPU at 96 px -> this job: stills, frames, encode, D's holdout.txt, crop."""
    bdir = tmp_path / "b" / "house-int01"
    bdir.mkdir(parents=True)
    (tmp_path / "scene.py").write_text(TINY_SCENE)
    r = subprocess.run([sys.executable, str(tmp_path / "scene.py"), str(bdir / "model_site.blend")], capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-1500:]
    job = {"schema": "render_job/1", "id": "house-int01", "front_az": 200.0,
           "bbox": {"walls": [[-4, -3, 0], [4, 3, 3]], "roof": [[-4.4, -3.4, 3.0], [4.4, 3.4, 3.4]]}, "ground_z": 0.0,
           "turntable": {"frames": 8, "fps": 24}, "train": {"n_ground": 6, "n_orbit": 6, "n_nadir": 4, "n_holdout": 3}}
    (bdir / "render_job.json").write_text(json.dumps(job))
    with zipfile.ZipFile(tmp_path / "bundle.zip", "w") as z:
        for p in bdir.iterdir():
            z.write(p, "house-int01/" + p.name)
    grut = make_fake_grut(tmp_path / "fake3dgrut")
    (tmp_path / "grut_env.sh").write_text("#!/bin/bash\nexit 0\n")
    rl = tmp_path / "rl"
    r = run_job(rl, job_id="house-int01", dry=False, extra={
        "BUNDLE_URL": f"file://{tmp_path}/bundle.zip", "SKIP_ENV": "1", "DEVICE": "cpu", "PY_BLENDER": sys.executable,
        "RENDER_ARGS": "--max-size 96 --samples 2", "GRUT_DIR": str(grut), "GRUT_ENV": str(tmp_path / "grut_env.sh"),
        "FAKE_COMPRESS": COMPRESS, "HELPER_PY": sys.executable})
    out = rl / "out" / "house-int01"
    assert r.returncode == 0, r.stdout[-3000:]
    assert markers(rl, "house-int01") == ["DONE.marker", "encode.marker"]
    assert json.load(open(out / "encode.json"))["frames"] == 8
    qa = json.load(open(out / "qa.json"))
    assert set(qa["stills"]) == {"hero_street.jpg", "aerial_34.jpg", "top_down.jpg"} and qa["black"] == []
    split = json.load(open(out / "splat" / "dataset" / "split.json"))
    assert split["held_out_source"] == "names file holdout.txt" and split["n_test"] == 3
    assert all(n.startswith("holdout/") for n in split["test"])
    assert json.load(open(out / "splat" / "compress.json"))["crop"] is not None


# ------------------------------------------------------------------------------------------ train_splat.sh

def make_dataset(root, n_train=20, n_hold=4, holdout_dir=True):
    names = [f"ring/r_{i:03d}.png" for i in range(n_train)]
    names += [(f"holdout/h_{i:03d}.png" if holdout_dir else f"ring/h_{i:03d}.png") for i in range(n_hold)]
    for nm in names:
        p = root / "images" / nm
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
    sp = root / "sparse" / "0"
    sp.mkdir(parents=True)
    (sp / "cameras.txt").write_text("1 OPENCV 64 36 50 50 32 18 0 0 0 0\n")
    with open(sp / "images.txt", "w") as f:
        f.write("# header\n")
        for i, nm in enumerate(names, 1):
            f.write(f"{i} 1 0 0 0 {i} 0 0 1 {nm}\n{i}.5 2.5 {i}\n")
    with open(sp / "points3D.txt", "w") as f:
        f.write("# POINT3D_ID X Y Z R G B ERROR TRACK[]\n")
        f.write(f"1 0 0 0 128 128 128 0 1 0 {len(names)} 3\n")
    return names


def test_train_splat_usage_and_dry_run(tmp_path):
    assert subprocess.run(["bash", TRAIN], capture_output=True).returncode == 2
    r = subprocess.run(["bash", TRAIN, str(tmp_path / "ds"), str(tmp_path / "run"), "--dry-run", "--iters", "15000"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "--config-name apps/colmap_3dgut.yaml" in r.stdout and "n_iterations=15000" in r.stdout
    assert "export_ply.enabled=true" in r.stdout and "test_last=true" in r.stdout
    r = subprocess.run(["bash", TRAIN, str(tmp_path / "nope"), str(tmp_path / "run")], capture_output=True, text=True,
                       env=dict(os.environ, GRUT_DIR=str(tmp_path / "g")))
    assert r.returncode == 1 and "no COLMAP" in r.stderr


@pytest.mark.parametrize("psnr, code", [("30.2", 0), ("24.0", 3)])
def test_train_splat_with_fake_3dgrut(tmp_path, psnr, code):
    make_dataset(tmp_path / "ds")
    grut = make_fake_grut(tmp_path / "g")
    env = dict(os.environ, GRUT_DIR=str(grut), FAKE_COMPRESS=COMPRESS, FAKE_PSNR=psnr, HELPER_PY=sys.executable,
               TORCH_EXTENSIONS_DIR=str(tmp_path / "ext"))
    r = subprocess.run(["bash", TRAIN, str(tmp_path / "ds"), str(tmp_path / "run"), "--iters", "100"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == code, r.stdout + r.stderr
    t = json.load(open(tmp_path / "run" / "train.json"))
    assert t["psnr"] == round(float(psnr), 2) and t["k"] == 6 and t["n_test"] == 4 and t["iterations"] == 100
    assert (tmp_path / "run" / "splat.ply").stat().st_size > 0


# ------------------------------------------------------------------------------------------ compress_splat.py

def synth(path, n=1000, seed=0):
    assert CS.main(["synth", str(path), "--n", str(n), "--seed", str(seed)]) == 0


def test_compress_round_trip_counts(tmp_path):
    synth(tmp_path / "a.ply")
    data, names = CS.read_ply(str(tmp_path / "a.ply"))
    assert len(data) == 1000 and "f_rest_44" in names
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "a.splat"), "--axis", "none",
                    "--meta", str(tmp_path / "m.json")]) == 0
    raw = open(tmp_path / "a.splat", "rb").read()
    assert len(raw) == 1000 * 32
    back = CS.decode_splat(raw)
    m = json.load(open(tmp_path / "m.json"))
    assert m["input_count"] == 1000 and m["written"] == 1000
    # same set of positions, colours from SH DC, alpha from the opacity logit
    src = np.stack([data["x"], data["y"], data["z"]], 1)
    order = np.lexsort(src.T)
    order_b = np.lexsort(back["p"].T)
    assert np.allclose(src[order], back["p"][order_b], atol=1e-6)
    i = int(np.argmax(data["opacity"]))
    j = int(np.argmin(np.linalg.norm(back["p"] - src[i], axis=1)))
    alpha = 1 / (1 + math.exp(-float(data["opacity"][i])))
    assert abs(back["c"][j][3] - round(alpha * 255)) <= 1
    assert abs(back["c"][j][0] - np.clip(round((0.5 + CS.SH_C0 * float(data["f_dc_0"][i])) * 255), 0, 255)) <= 1
    assert np.allclose(back["s"][j], np.exp([data["scale_0"][i], data["scale_1"][i], data["scale_2"][i]]), rtol=1e-5)


@pytest.mark.parametrize("args, n_expect", [
    (["--max-bytes", "3200"], 100),                     # the byte cap lowers the gaussian cap
    (["--max-gaussians", "250"], 250),
    (["--max-gaussians", "250", "--max-bytes", "4000"], 125),
])
def test_compress_respects_caps(tmp_path, args, n_expect):
    synth(tmp_path / "a.ply")
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "a.splat"), *args]) == 0
    size = os.path.getsize(tmp_path / "a.splat")
    assert size == n_expect * 32
    cap = dict(zip(args[::2], args[1::2])).get("--max-bytes")
    assert cap is None or size <= int(cap)


def test_compress_json_form_caps_the_file(tmp_path):
    synth(tmp_path / "a.ply")
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "a.splat.json"), "--format", "splat.json",
                    "--max-bytes", "20000"]) == 0
    size = os.path.getsize(tmp_path / "a.splat.json")
    doc = json.load(open(tmp_path / "a.splat.json"))
    assert size <= 20000 and doc["count"] == ((20000 - CS.JSON_HEADER_BYTES) // 4 * 3) // 32
    # the default cap keeps a full-size splat JSON inside the studio's per-file limit
    assert (11_000_000 - CS.JSON_HEADER_BYTES) // 4 * 3 // 32 > 250_000


def test_compress_keeps_most_important(tmp_path):
    synth(tmp_path / "a.ply")
    data, _ = CS.read_ply(str(tmp_path / "a.ply"))
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "a.splat"), "--max-gaussians", "50",
                    "--axis", "none"]) == 0
    back = CS.decode_splat(open(tmp_path / "a.splat", "rb").read())
    imp = np.exp(np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], 1).astype(float)).prod(1) \
        / (1 + np.exp(-data["opacity"].astype(float)))
    top = np.stack([data["x"], data["y"], data["z"]], 1)[np.argsort(-imp)[:50]]
    assert np.allclose(np.sort(top, axis=0), np.sort(back["p"], axis=0), atol=1e-6)


def test_compress_zup_to_yup(tmp_path):
    synth(tmp_path / "a.ply", n=200)
    data, _ = CS.read_ply(str(tmp_path / "a.ply"))
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "a.splat"), "--min-opacity", "0"]) == 0
    back = CS.decode_splat(open(tmp_path / "a.splat", "rb").read())
    src = np.stack([data["x"], data["y"], data["z"]], 1)
    want = np.stack([src[:, 0], src[:, 2], -src[:, 1]], 1)                # glTF y up: (x, z, -y)
    assert np.allclose(np.sort(want, axis=0), np.sort(back["p"], axis=0), atol=1e-5)
    # the rotation turns with the frame: R' = R_axis @ R
    i = 0
    j = int(np.argmin(np.linalg.norm(back["p"] - want[i], axis=1)))
    def rot(q):
        w, x, y, z = q / np.linalg.norm(q)
        return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                         [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                         [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
    q_src = np.array([data[f"rot_{k}"][i] for k in range(4)], float)
    q_out = (back["r"][j].astype(float) - 128) / 128
    axis = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    assert np.allclose(rot(q_out), axis @ rot(q_src), atol=0.05)


def test_compress_crop_and_json_form(tmp_path):
    synth(tmp_path / "a.ply")
    pts = tmp_path / "points3D.txt"
    pts.write_text("# id x y z r g b err\n1 -4 -5 0 1 1 1 0\n2 4 5 5.5 1 1 1 0\n")
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "c.splat"), "--crop-points", str(pts),
                    "--margin", "0.5", "--axis", "none", "--meta", str(tmp_path / "m.json")]) == 0
    back = CS.decode_splat(open(tmp_path / "c.splat", "rb").read())
    assert back["p"][:, 0].min() >= -4.5 - 1e-5 and back["p"][:, 1].max() <= 5.5 + 1e-5
    m = json.load(open(tmp_path / "m.json"))
    assert m["dropped"]["outside_crop"] > 0 and m["written"] == len(back)
    assert CS.main(["compress", str(tmp_path / "a.ply"), str(tmp_path / "c.splat.json"), "--crop-points", str(pts),
                    "--margin", "0.5", "--axis", "none", "--format", "splat.json"]) == 0
    doc = json.load(open(tmp_path / "c.splat.json"))
    assert doc["format"] == "splat" and doc["count"] == len(back)
    assert base64.b64decode(doc["base64"]) == open(tmp_path / "c.splat", "rb").read()
    assert "not used for measurements" in doc["label"]


def test_compress_rejects_bad_input(tmp_path):
    (tmp_path / "x.ply").write_text("ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nend_header\n0\n")
    assert CS.main(["compress", str(tmp_path / "x.ply"), str(tmp_path / "x.splat")]) == 1
    assert CS.main(["compress", str(tmp_path / "missing.ply"), str(tmp_path / "x.splat")]) == 1


@pytest.mark.parametrize("n_train, n_hold", [(20, 4), (200, 20), (180, 20), (7, 3), (30, 0)])
def test_holdout_order_puts_holdouts_on_test_slots(n_train, n_hold):
    k, kept, order = CS.holdout_order(n_train, n_hold)
    assert len(order) == n_train + kept
    assert [i for i, o in enumerate(order) if o == "h"] == ([i for i in range(len(order)) if i % k == 0] if kept else [])
    assert kept <= n_hold and (n_hold == 0 or kept >= n_hold - 2)


def test_holdout_dataset_view(tmp_path):
    names = make_dataset(tmp_path / "src", n_train=20, n_hold=4)
    assert CS.main(["holdout", str(tmp_path / "src"), str(tmp_path / "dst")]) == 0
    split = json.load(open(tmp_path / "dst" / "split.json"))
    assert split["k"] == 6 and split["n"] == 24 and sorted(split["test"]) == sorted(names[20:])
    ent = CS.read_images_txt(str(tmp_path / "dst" / "sparse" / "0" / "images.txt"))
    assert [int(f[0]) for f, _ in ent] == list(range(1, 25))
    test_rows = [f for i, (f, _) in enumerate(ent) if i % 6 == 0]
    assert all("holdout__" in f[9] for f in test_rows)
    assert all(os.path.islink(tmp_path / "dst" / "images" / f[9]) for f, _ in ent)
    assert sorted(f[9] for f, _ in ent) == [f[9] for f, _ in ent]       # name order = id order = split order
    # points2D lines travel with their image; points3D tracks follow the new image ids
    by_name = {f[9].split("_", 1)[1].replace("__", "/"): (f, p) for f, p in ent}
    f, p = by_name["holdout/h_003.png"]
    assert p.endswith(" 24")
    track = open(tmp_path / "dst" / "sparse" / "0" / "points3D.txt").read().split("\n")[1].split()[8:]
    assert track[2] == f[0]                                  # old image id 24 -> its new id


def test_holdout_from_cameras_json_and_default(tmp_path):
    make_dataset(tmp_path / "src", n_train=16, n_hold=0)
    json.dump({"cameras": [{"image": "ring/r_003.png", "split": "test"}, {"image": "ring/r_010.png", "holdout": True}]},
              open(tmp_path / "src" / "cameras.json", "w"))
    assert CS.main(["holdout", str(tmp_path / "src"), str(tmp_path / "dst")]) == 0
    split = json.load(open(tmp_path / "dst" / "split.json"))
    assert sorted(split["test"]) == ["ring/r_003.png", "ring/r_010.png"] and split["k"] == 8
    os.remove(tmp_path / "src" / "cameras.json")
    assert CS.main(["holdout", str(tmp_path / "src"), str(tmp_path / "dst2")]) == 0
    split = json.load(open(tmp_path / "dst2" / "split.json"))
    assert split["k"] == 8 and split["n_test"] == 2 and split["test"] == []      # every 8th view, unnamed


# ------------------------------------------------------------------------------------------ CLI script, env script

FAKE_HF = """#!/bin/bash
echo "$*" >> "$(dirname "$0")/calls.log"
case "$1 $2" in
  "upload create") echo "Uploaded: 3f2a9c1e-1b2c-4d5e-8f90-123456789abc";;
  "model list") [ -n "$HF_TOPAZ" ] && echo "topaz_video  Topaz Video"; echo "bytedance_video_upscale"; echo "kling3_0";;
  "model get") echo "params";;
  "generate cost") echo "cost 40";;
  "generate create") echo "done";;
esac
"""


@pytest.fixture
def fake_hf(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "higgsfield").write_text(FAKE_HF)
    (b / "higgsfield").chmod(0o755)
    (tmp_path / "turntable_1080p.mp4").write_bytes(b"\0" * 64)
    (tmp_path / "IMG_0001.jpg").write_bytes(b"\xff\xd8")
    return tmp_path


def hf(tmp, *args, topaz=False):
    env = dict(os.environ, PATH=f"{tmp}/bin:" + os.environ["PATH"])
    if topaz:
        env["HF_TOPAZ"] = "1"
    return subprocess.run(["bash", HFCLI, *args], env=env, capture_output=True, text=True, cwd=tmp, timeout=60)


def calls(tmp):
    p = tmp / "bin" / "calls.log"
    return open(p).read().splitlines() if p.exists() else []


def test_hf_cli_upload_only_when_no_topaz(fake_hf):
    r = hf(fake_hf, "turntable_1080p.mp4")
    assert r.returncode == 0
    assert "upload done, run the upscale from a Claude session" in r.stdout
    assert "client chose Topaz" in r.stdout                          # other upscalers are not used
    assert calls(fake_hf) == ["upload create turntable_1080p.mp4", "model list --video"]


def test_hf_cli_needs_yes_before_paid_upscale(fake_hf):
    r = hf(fake_hf, "turntable_1080p.mp4", topaz=True)
    assert r.returncode == 0 and "Not upscaling without --yes" in r.stdout
    assert not [c for c in calls(fake_hf) if c.startswith("generate create")]
    r = hf(fake_hf, "turntable_1080p.mp4", "--yes", topaz=True)
    assert r.returncode == 0
    assert "generate create topaz_video --video 3f2a9c1e-1b2c-4d5e-8f90-123456789abc --resolution 2160p --wait" in calls(fake_hf)


def test_hf_cli_refuses_photo_names_and_missing_cli(fake_hf):
    r = hf(fake_hf, "IMG_0001.jpg")
    assert r.returncode == 3 and "Real photos never go to Higgsfield" in r.stderr
    assert calls(fake_hf) == []
    r = subprocess.run(["bash", HFCLI, "turntable_1080p.mp4"], cwd=fake_hf, capture_output=True, text=True,
                       env=dict(os.environ, PATH="/usr/bin:/bin"))
    assert r.returncode == 4 and "npm install -g @higgsfield/cli" in r.stderr


def test_grut_env_dry_run_calls_virtual_homes_installer():
    r = subprocess.run(["bash", GRUT, "--dry-run"], capture_output=True, text=True)
    assert r.returncode == 0
    inst = os.path.join(REPO, "virtual-homes", "gpu", "grut_install.sh")
    assert os.path.isfile(inst) and inst in r.stdout
    assert "build-essential" in r.stdout and "TORCH_EXTENSIONS_DIR=/workspace/vh/torch_extensions" in r.stdout
    assert "UV_PYTHON_INSTALL_DIR=/workspace/rl/uv/python" in r.stdout


def test_mcp_sequence_doc_has_the_stop_rules():
    doc = open(os.path.join(GPU, "MCP_SEQUENCE.md")).read()
    for needle in ("gpu_rental_stop", "gpu_my", "max_credits_per_hour", "auto_pause_minutes", "idempotency_key",
                   "encode.marker", "DONE.marker", "FAIL.marker", "upscale_video", "\"topaz\"", "2160p", "jobs_wait",
                   "transactions", "balance", "media_confirm"):
        assert needle in doc, needle
    assert doc.index("gpu_rental_stop") < doc.rindex("download")


def _shellcheck():
    return os.environ.get("SHELLCHECK") or shutil.which("shellcheck")


@pytest.mark.skipif(not _shellcheck(), reason="shellcheck not installed (pip install shellcheck-py)")
@pytest.mark.parametrize("script", SCRIPTS, ids=os.path.basename)
def test_shellcheck_clean(script):
    r = subprocess.run([_shellcheck(), "-S", "info", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("script", SCRIPTS, ids=os.path.basename)
def test_bash_syntax(script):
    assert subprocess.run(["bash", "-n", script]).returncode == 0
