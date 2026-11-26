"""Demo render tools: camera rigs (propmodel/rigs_demo.py), COLMAP text output, render_demo.py --dry-run frame
counts, one small CPU frame + a pose check against a rendered marker (bpy only), and render_bundle.py refusals
(address tokens, JOB/data files). Synthetic houses and places only."""
import importlib.util
import json
import os
import subprocess
import sys
import zipfile

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from propmodel import report, rigs_demo as RD, roofgeom as R  # noqa: E402

RENDER = os.path.join(ROOT, "scripts", "blender", "render_demo.py")
BUNDLE = os.path.join(ROOT, "scripts", "render_bundle.py")
HAVE_BPY = importlib.util.find_spec("bpy") is not None
FAKE_ADDRESS = "4321 Nonesuch Lane, Faketown, ZZ 00000"
FAKE_GEO = {"lat": 0.512345, "lon": -140.532109}        # open Pacific: no real place

HOUSE = ([-5.0, -4.0, 0.0], [5.0, 4.0, 6.0])


def RB_TOKENS(job):
    """render_bundle.address_tokens(job), loaded from the script by path."""
    spec = importlib.util.spec_from_file_location("render_bundle_under_test", BUNDLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.address_tokens(str(job))


def slope_ground(x, y):
    return 0.08 * x - 0.05 * y


def _plan(**kw):
    return RD.plan_cameras(HOUSE, 135.0, slope_ground, **kw)


# ------------------------------------------------------------------------------------------------- rigs

def test_counts_and_sizes():
    p = _plan()
    assert len(p["stills"]) == 3 and len(p["turntable"]) == 240
    assert len(p["train"]) == 180 and len(p["holdout"]) == 20
    rigs = [c["rig"] for c in p["train"]]
    assert rigs.count("ground") == 48 and rigs.count("orbit") == 72 and rigs.count("nadir") == 60
    assert {c["split"] for c in p["holdout"]} == {"holdout"}
    k = p["stills"][0]["intrinsics"]
    assert (k["width"], k["height"]) == (3840, 2160)
    assert (p["turntable"][0]["intrinsics"]["width"], p["turntable"][0]["intrinsics"]["height"]) == (1920, 1080)
    assert max(p["train"][0]["intrinsics"]["width"], p["train"][0]["intrinsics"]["height"]) == 1440
    small = _plan(scale=64)
    assert max(small["stills"][0]["intrinsics"]["width"], small["stills"][0]["intrinsics"]["height"]) == 64


def test_cameras_look_at_centre_above_ground_rotations_valid():
    p = _plan()
    cams = p["stills"][:2] + p["turntable"] + p["train"] + p["holdout"]
    assert RD.check_cameras(cams, p["target"], slope_ground) == []
    assert np.allclose(p["target"], [0.0, 0.0, 3.0])
    # nadir views look straight down with north up
    for c in [c for c in p["train"] if c["rig"] == "nadir"]:
        R_ = np.asarray(c["pose"]["R"])
        assert np.allclose(R_[2], [0, 0, -1]) and np.allclose(R_[1], [0, -1, 0])
    # the ground cameras stand at eye height on the (sloped) ground, outside the house
    for c in p["stills"][:1] + [c for c in p["train"] if c["rig"] == "ground"]:
        x, y, z = c["pose"]["center"]
        assert abs(z - (slope_ground(x, y) + RD.EYE_HEIGHT)) < 1e-9
        assert np.hypot(x, y) > np.hypot(5, 4)


def test_front_az_drives_the_hero_and_turntable():
    for az in (0.0, 90.0, 222.0):
        p = RD.plan_cameras(HOUSE, az, slope_ground)
        hero = p["stills"][0]
        b = np.degrees(np.arctan2(hero["pose"]["center"][0], hero["pose"]["center"][1])) % 360
        assert abs(((b - (az - 18.0)) + 180) % 360 - 180) < 1e-6           # front side, swung 18 deg
        t0 = p["turntable"][0]["pose"]["center"]
        assert abs(((np.degrees(np.arctan2(t0[0], t0[1])) - az) + 180) % 360 - 180) < 1e-6
        r = [np.hypot(*c["pose"]["center"][:2]) for c in p["turntable"]]
        assert max(r) - min(r) < 1e-6                                        # constant radius
        top = p["stills"][2]
        assert top["projection"] == "orthographic" and top["ortho_scale"] > 10.0


def test_colmap_roundtrip_and_projection(tmp_path):
    p = _plan(scale=320)
    cams = p["train"][:12] + p["holdout"][:3]
    names = {c["name"]: f"{c['rig']}/{c['name']}.png" for c in cams}
    model = R.to_mesh_json(R.build([R.Wing(id="A", type="gable", length=10, width=8, eave_height=3, pitch=0.5)]))
    pts = RD.seed_points_from_model(model, n=2000)
    assert pts.shape[1] == 3 and 1500 < len(pts) <= 2000
    info = RD.write_colmap(str(tmp_path), [dict(c) for c in cams], pts, names)
    assert info == {"dir": str(tmp_path), "images": 15, "cameras": 1, "points": len(pts)}
    rd = RD.read_colmap(str(tmp_path / "sparse" / "0"))
    assert len(rd["images"]) == 15 and rd["points"] == len(pts) and rd["cameras"][1]["model"] == "OPENCV"
    fx, fy, cx, cy = rd["cameras"][1]["params"][:4]
    for img, c in zip(rd["images"], cams):
        assert img["name"] == names[c["name"]]
        Rq = RD.qvec_to_rot(img["qvec"])
        assert np.abs(Rq - np.asarray(c["pose"]["R"])).max() < 1e-8
        assert abs(np.linalg.norm(img["qvec"]) - 1) < 1e-8
        # the target projects to the principal point of every non-nadir view
        if c["rig"] != "nadir":
            Xc = Rq @ np.asarray(p["target"]) + np.asarray(img["t"])
            assert abs(fx * Xc[0] / Xc[2] + cx - cx) < 1e-6 and abs(fy * Xc[1] / Xc[2]) < 1e-6
    # roof seed points lie on their facet planes
    f = model["facets"][0]
    a, b, c0 = f["plane"]
    on = np.abs(pts[:, 2] - (a * pts[:, 0] + b * pts[:, 1] + c0)) < 1e-3
    assert on.sum() > 100


def _job_file(tmp_path, **extra):
    walls, roof = [[-5, -4, 0], [5, 4, 3]], [[-5.5, -4.5, 2.5], [5.5, 4.5, 6]]
    j = {"schema": "render_job/1", "id": "house-test", "front_az": 200.0, "bbox": {"walls": walls, "roof": roof},
         "ground_z": 0.0, **extra}
    p = tmp_path / "render_job.json"
    p.write_text(json.dumps(j))
    return str(p)


def test_dry_run_frame_counts_from_job(tmp_path):
    job = _job_file(tmp_path)
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, RENDER, str(tmp_path / "none.blend"), str(out), "--job", job, "--dry-run",
                        "--plan-from-job", "--tt-size", "1280x720"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    plan = json.load(open(out / "plan.json"))
    assert plan["counts"] == {"stills": 3, "turntable": 240, "train": 180, "holdout": 20}
    assert plan["sizes"]["turntable"] == [1280, 720] and plan["sizes"]["stills"] == [3840, 2160]
    assert plan["fps"] == 24 and plan["encode"][-1].endswith("turntable_720p.mp4")
    cams = json.load(open(out / "cameras.json"))["cameras"]
    assert len(cams) == 443
    assert sum(c["image"].startswith("train/colmap/images/") and "/holdout/" not in c["image"] for c in cams) == 180
    assert sum(c["image"].startswith("train/colmap/images/holdout/") for c in cams) == 20
    assert not (out / "stills").exists() and not (out / "timings.json").exists()     # nothing rendered


def test_dry_run_counts_follow_the_job(tmp_path):
    job = _job_file(tmp_path, turntable={"frames": 96}, train={"n_ground": 24, "n_orbit": 36, "n_nadir": 30,
                                                               "n_holdout": 10})
    out = tmp_path / "o"
    r = subprocess.run([sys.executable, RENDER, "x.blend", str(out), "--job", job, "--dry-run", "--plan-from-job"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert json.load(open(out / "plan.json"))["counts"] == {"stills": 3, "turntable": 96, "train": 90, "holdout": 10}


# ------------------------------------------------------------------------------------------------- Blender

SCENE = r'''
import bpy, sys
out = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
def coll(name):
    c = bpy.data.collections.new(name); sc.collection.children.link(c); return c
def box(name, c, loc, size, color, emit=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    for cc in list(o.users_collection): cc.objects.unlink(o)
    c.objects.link(o)
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = color
    if emit:
        b.inputs["Emission Color"].default_value = color; b.inputs["Emission Strength"].default_value = emit
    o.data.materials.append(m)
    return o
walls, roof, site, det, lab = coll("Walls"), coll("Roof facets"), coll("Site"), coll("Details"), coll("Labels")
box("Wall box", walls, (0, 0, 1.5), (8, 6, 3), (0.8, 0.8, 0.78, 1))
box("Roof slab", roof, (0, 0, 3.2), (8.8, 6.8, 0.4), (0.25, 0.25, 0.27, 1))
box("Terrain (LiDAR ground)", site, (0, 0, -0.05), (90, 90, 0.1), (0.30, 0.36, 0.26, 1))
box("Marker by 4321 Nonesuch Lane", det, (1.5, -3.35, 1.5), (0.7, 0.7, 0.7), (1.0, 0.0, 0.0, 1), emit=1.5)
cu = bpy.data.curves.new("sign", "FONT"); cu.body = "4321 Nonesuch"
t = bpy.data.objects.new("4321 Nonesuch Lane sign", cu); det.objects.link(t); t.location = (0, -3.2, 2.5)
lt = bpy.data.curves.new("lab", "FONT"); lt.body = "F1 Nonesuch"; lab.objects.link(bpy.data.objects.new("label", lt))
sc["note"] = "4321 Nonesuch Lane"
bpy.data.texts.new("notes").write("4321 Nonesuch Lane")
bpy.ops.wm.save_as_mainfile(filepath=out, compress=False)
'''


@pytest.fixture(scope="module")
def tiny_blend(tmp_path_factory):
    if not HAVE_BPY:
        pytest.skip("bpy not installed")
    d = tmp_path_factory.mktemp("scene")
    script = d / "make.py"
    script.write_text(SCENE)
    blend = d / "tiny.blend"
    r = subprocess.run([sys.executable, str(script), str(blend)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and blend.exists(), r.stderr[-2000:]
    return str(blend)


@pytest.mark.skipif(not HAVE_BPY, reason="bpy not installed")
def test_one_64px_cpu_frame_and_resume(tmp_path, tiny_blend):
    job = _job_file(tmp_path, front_az=180.0)
    out = tmp_path / "r"
    cmd = [sys.executable, RENDER, tiny_blend, str(out), "--job", job, "--device", "cpu", "--max-size", "64",
           "--samples", "2", "--only", "stills", "--limit", "1"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    from PIL import Image
    im = Image.open(out / "stills" / "hero_street.png")
    assert im.size[0] == 64 and (out / "stills" / "hero_street.jpg").exists()
    t = json.load(open(out / "timings.json"))
    assert t["device"] == "CPU" and t["sets"]["stills"]["rendered"] == 1 and not t["black_frames"]
    plan = json.load(open(out / "plan.json"))
    assert plan["source"].startswith("blend") and plan["ground_model"]["kind"] == "terrain ray-cast"
    r2 = subprocess.run(cmd, capture_output=True, text=True, timeout=600)            # resume: nothing re-rendered
    assert r2.returncode == 0
    assert json.load(open(out / "timings.json"))["sets"]["stills"] == {"frames": 1, "rendered": 0, "skipped": 1,
                                                                       "seconds": 0.0}


@pytest.mark.skipif(not HAVE_BPY, reason="bpy not installed")
def test_training_pose_matches_the_render(tmp_path, tiny_blend):
    """The COLMAP / OpenCV pose written for a view projects the marker where Blender actually drew it."""
    job = _job_file(tmp_path, front_az=180.0)
    out = tmp_path / "t"
    r = subprocess.run([sys.executable, RENDER, tiny_blend, str(out), "--job", job, "--device", "cpu", "--max-size",
                        "192", "--samples", "4", "--only", "train", "--limit", "1"], capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    cams = {c["name"]: c for c in json.load(open(out / "cameras.json"))["cameras"]}
    cam = cams["ground_000"]
    from PIL import Image
    a = np.asarray(Image.open(out / cam["image"]).convert("RGB"), float) / 255
    red = (a[..., 0] > a[..., 1] + 0.25) & (a[..., 0] > a[..., 2] + 0.25)
    assert red.sum() >= 4, "marker not visible"
    ys, xs = np.nonzero(red)
    uv, z = RD.project([[1.5, -3.35 - 0.35, 1.5]], cam)          # centre of the marker's front face
    assert z[0] > 0
    assert abs(xs.mean() + 0.5 - uv[0, 0]) < 3.0 and abs(ys.mean() + 0.5 - uv[0, 1]) < 3.0
    rd = RD.read_colmap(str(out / "train" / "colmap" / "sparse" / "0"))
    assert rd["images"][0]["name"] == "ground/ground_000.png" and rd["points"] > 0
    assert np.abs(RD.qvec_to_rot(rd["images"][0]["qvec"]) - np.asarray(cam["pose"]["R"])).max() < 1e-8


# ------------------------------------------------------------------------------------------------- bundle

def _bundle_job(tmp_path, blend_bytes=b"BLENDER-v500 synthetic test file, no house text\n"):
    j = tmp_path / "jobs" / "nonesuch-4321"
    (j / "out").mkdir(parents=True)
    (j / "data").mkdir()
    m = R.build([R.Wing(id="A", type="hip", length=12, width=9, eave_height=3, pitch=0.45)])
    site = {"address": FAKE_ADDRESS, "geocode": dict(FAKE_GEO), "origin": {**FAKE_GEO, "h": 0.0}}
    (j / "model.json").write_text(json.dumps({**R.to_mesh_json(m), "site": site}))
    (j / "report.json").write_text(json.dumps(report.report_json(m, site=site)))
    (j / "site.json").write_text(json.dumps(site))
    (j / "job.json").write_text(json.dumps({"slug": "nonesuch-4321", "address": FAKE_ADDRESS, "front_az": 135}))
    (j / "data" / "records.json").write_text(json.dumps({"parcel": {"parcel_id": "ZZ99887766"}}))
    (j / "out" / "model_site.blend").write_bytes(blend_bytes)
    return j


def _run_bundle(j, *args):
    out = j / "out" / "render_bundle.zip"
    r = subprocess.run([sys.executable, BUNDLE, str(j), "--out", str(out), "--seed-points", "500", *args],
                       capture_output=True, text=True, timeout=600)
    return r, out


def test_bundle_clean_job(tmp_path):
    j = _bundle_job(tmp_path)
    r, out = _run_bundle(j, "--no-pack")
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)
    assert rec["id"].startswith("house-") and rec["front_az"] == 135.0 and rec["tokens_checked"] >= 4
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert sorted(n.split("/", 1)[1] for n in names) == ["bundle.json", "model_site.blend", "render_job.json",
                                                             "seed_points.npy"]
        assert all(n.startswith(rec["id"] + "/") for n in names) and not any("data/" in n for n in names)
        blob = b"".join(z.read(n) for n in names).decode("latin-1")
        jb = json.loads(z.read(f"{rec['id']}/render_job.json"))
    for bad in ("Nonesuch", "nonesuch", "4321", "Faketown", "0.5123", "140.5321", "ZZ99887766", str(tmp_path)):
        assert bad not in blob, bad
    assert any("4321" in t and "Nonesuch" not in t for t in RB_TOKENS(j)), "the bare house number is a bundle token"
    assert jb["front_az"] == 135.0 and jb["bbox"]["walls"] and jb["bbox"]["roof"] and jb["turntable"]["frames"] == 240
    assert json.load(open(j / "out" / "render_bundle.json"))["id"] == rec["id"]


@pytest.mark.parametrize("planted", [b"... 4321 Nonesuch Lane ...", b"slug nonesuch-4321", b"lat 0.5123 x",
                                     b"pid ZZ99887766", b"numerals block '4321' on the wall"])
def test_bundle_refuses_a_planted_address_token(tmp_path, planted):
    j = _bundle_job(tmp_path, blend_bytes=b"BLENDER-v500 " + planted + b" end")
    (j / "out" / "render_bundle.zip").write_bytes(b"old bundle")             # an older bundle must not survive
    r, out = _run_bundle(j, "--no-pack")
    assert r.returncode == 3 and "REFUSED" in r.stderr
    assert not out.exists()


def test_bundle_refuses_data_files_and_tokens_in_extras(tmp_path):
    j = _bundle_job(tmp_path)
    r, out = _run_bundle(j, "--no-pack", "--extra", str(j / "data" / "records.json"))
    assert r.returncode == 3 and "JOB/data" in r.stderr and not out.exists()
    note = tmp_path / "note.txt"
    note.write_text("render the house at 4321 Nonesuch Lane")
    r, out = _run_bundle(j, "--no-pack", "--extra", str(note))
    assert r.returncode == 3 and not out.exists()
    note.write_text("lighting preset: overcast")
    r, out = _run_bundle(j, "--no-pack", "--extra", str(note))
    assert r.returncode == 0 and out.exists()


@pytest.mark.skipif(not HAVE_BPY, reason="bpy not installed")
def test_bundle_scrubs_text_objects_and_names_in_the_blend(tmp_path, tiny_blend):
    j = _bundle_job(tmp_path, blend_bytes=open(tiny_blend, "rb").read())
    raw = open(tiny_blend, "rb").read().decode("latin-1")
    assert "Nonesuch" in raw                                                  # planted in the source blend
    r, out = _run_bundle(j)
    assert r.returncode == 0, r.stderr[-1500:]
    rec = json.loads(r.stdout)
    with zipfile.ZipFile(out) as z:
        blend = z.read(f"{rec['id']}/model_site.blend").decode("latin-1")
    assert "Nonesuch" not in blend and "nonesuch-4321" not in blend and str(tmp_path) not in blend
    pack = json.load(open(j / "out" / "render_bundle.json"))["pack"]
    assert pack["packed"] and pack["fonts_to_mesh"] >= 1 and pack["texts_removed"] >= 1
    assert pack["renamed"] >= 2 and pack["props_dropped"] >= 1        # object + material names, the scene note
