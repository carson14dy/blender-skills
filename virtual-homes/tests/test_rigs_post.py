"""Camera rigs and post-processing: pose / intrinsics conventions and the lens-distortion warp."""
import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from vhomes import geometry as G, post, rigs, spec as S  # noqa: E402


@pytest.fixture(scope="module")
def cams():
    return rigs.make_cameras(G.build_house(S.make_spec(3)), long_side=1440)


def _qvec_to_R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def test_rig_counts_and_determinism(cams):
    by = {}
    for c in cams["cameras"]:
        by[c["rig"]] = by.get(c["rig"], 0) + 1
    assert by["ground"] == 40 and by["roof"] == 60 and 50 <= by["drone"] <= 100
    again = rigs.make_cameras(G.build_house(S.make_spec(3)), long_side=1440)
    assert json.dumps(cams, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_pose_conventions(cams):
    for c in cams["cameras"]:
        R = np.array(c["pose"]["R"]); t = np.array(c["pose"]["t"]); C = np.array(c["pose"]["center"])
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-12) and np.linalg.det(R) == pytest.approx(1.0)
        assert np.allclose(-R.T @ t, C, atol=1e-9)
        assert np.allclose(_qvec_to_R(c["pose"]["qvec"]), R, atol=1e-9)
        B = np.array(c["pose"]["blender_matrix_world"])
        assert np.allclose(B[:3, 2], -R[2], atol=1e-12)          # Blender camera looks down its -Z
        assert np.allclose(B[:3, 1], -R[1], atol=1e-12)          # Blender +Y = image up
        k = dict(c["intrinsics"], k1=0.0, k2=0.0, p1=0.0, p2=0.0)
        uv, z = rigs.project(np.array([c["look_at"]]), {**c, "intrinsics": k})
        assert z[0] > 0
        if abs(c["roll_deg"]) < 1e-12:
            assert uv[0] == pytest.approx([k["cx"], k["cy"]], abs=1e-6)


def test_phone_intrinsics_are_realistic(cams):
    d = [v for v in cams["devices"].values() if v["kind"] == "phone"][0]
    assert 60 < d["hfov_deg"] < 75
    assert d["cx"] == d["width"] / 2 and d["cy"] == d["height"] / 2


def test_nadir_images_are_north_up(cams):
    nadir = [c for c in cams["cameras"] if c.get("shot") == "nadir"]
    assert nadir
    for c in nadir:
        R = np.array(c["pose"]["R"])
        assert R[2] @ [0, 0, -1] > 0.999                      # looking straight down
        assert R[1] @ [0, -1, 0] > 0.99                        # image down = south


def test_roof_cameras_stand_above_the_roof(cams):
    house = G.build_house(S.make_spec(3))
    planes = {f["id"]: f["plane"] for f in house["facets"]}
    for c in cams["cameras"]:
        if c["rig"] == "roof" and c.get("standing_on_roof"):
            a, b, cc = planes[c["facet"]]
            x, y, z = c["pose"]["center"]
            assert 1.4 < z - (a * x + b * y + cc) < 1.75


def test_distortion_inverse_and_overscan(cams):
    for name, d in cams["devices"].items():
        rng = np.random.default_rng(0)
        x = rng.uniform(-0.6, 0.6, 2000); y = rng.uniform(-0.45, 0.45, 2000)
        r2 = x * x + y * y
        rad = 1 + d["k1"] * r2 + d["k2"] * r2 * r2
        xd = x * rad + 2 * d["p1"] * x * y + d["p2"] * (r2 + 2 * x * x)
        yd = y * rad + d["p1"] * (r2 + 2 * y * y) + 2 * d["p2"] * x * y
        xu, yu = post._undistort_norm(xd, yd, d)
        assert np.max(np.abs(xu - x)) < 1e-9 and np.max(np.abs(yu - y)) < 1e-9
        pad = post.overscan_pad(d)
        su, sv = post._source_map(d, pad)
        assert su.min() >= 0 and sv.min() >= 0
        assert su.max() <= d["width"] + 2 * pad[0] - 1 and sv.max() <= d["height"] + 2 * pad[1] - 1


def test_colmap_export(tmp_path):
    out = tmp_path / "vh"
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_house.py"), "--seed", "4", "--out", str(out),
                    "--no-render", "--no-blend"], check=True, capture_output=True)
    hd = out / "house_004"
    # pretend two images were rendered
    cams = json.load(open(hd / "cameras.json"))
    for c in cams["cameras"][:2]:
        p = hd / c["image"]; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"png")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "export_colmap.py"), str(hd), "--points", "500"],
                   check=True, capture_output=True)
    sp = hd / "colmap" / "sparse" / "0"
    lines = [l for l in open(sp / "images.txt") if l.strip() and not l.startswith("#")]
    assert len(lines) == 2
    first = lines[0].split()
    c0 = cams["cameras"][0]
    assert [float(v) for v in first[1:5]] == pytest.approx(c0["pose"]["qvec"], abs=1e-9)
    assert first[9] == c0["image"].split("renders/", 1)[1]
    cams_txt = [l for l in open(sp / "cameras.txt") if not l.startswith("#")]
    assert all(l.split()[1] == "OPENCV" for l in cams_txt)
    assert sum(1 for l in open(sp / "points3D.txt") if not l.startswith("#")) >= 450   # allocation rounds per face
