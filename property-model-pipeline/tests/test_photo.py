import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pytest
from propmodel import photo


def _look_at(C, target, up=(0, 0, 1)):
    f = np.subtract(target, C); f = f / np.linalg.norm(f)
    r = np.cross(f, up); r /= np.linalg.norm(r)
    d = np.cross(f, r)
    R = np.stack([r, d, f])  # world->cam rows: x right, y down, z forward
    return R, -R @ np.asarray(C, float)


def test_rectifier_measures_wall_and_pitch():
    K = np.array([[3000, 0, 2000], [0, 3000, 1500], [0, 0, 1.0]])
    R, t = _look_at([4, -12, 1.6], [4, 0, 3])
    # gable wall in plane y=0: door 0.914 x 2.032 at x=1..1.914; gable 8 m wide, eave 2.7, ridge 4.7 (6/12)
    door = np.array([[1, 0, 0], [1.914, 0, 0], [1.914, 0, 2.032], [1, 0, 2.032]])
    uv, _ = photo.project(K, R, t, door)
    rect = photo.Rectifier(uv, door[:, [0, 2]], px_sigma=0.5)
    pts, _ = photo.project(K, R, t, np.array([[0, 0, 0], [8, 0, 0], [0, 0, 2.7], [4, 0, 4.7]]))
    d, s = rect.distance(pts[0], pts[1])
    assert d == pytest.approx(8.0, abs=0.01)
    assert 0 < s < 0.3
    slope, ss = rect.rise_run(pts[2], pts[3])
    assert slope == pytest.approx(0.5, abs=1e-3)


def test_solve_camera_recovers_pose():
    K = np.array([[2800, 0, 2000], [0, 2800, 1500], [0, 0, 1.0]])
    C = np.array([15.0, -20.0, 8.0])
    R, t = _look_at(C, [0, 0, 3])
    X = np.array([[-5, -4, 0], [5, -4, 0], [5, 4, 0], [-5, 4, 0], [-5, -4, 2.8], [5, -4, 2.8],
                  [5, 4, 2.8], [-5, 4, 2.8], [-5, 0, 4.8], [5, 0, 4.8]], float)
    uv, _ = photo.project(K, R, t, X)
    uv += np.random.default_rng(0).normal(0, 0.7, uv.shape)
    cam = photo.solve_camera(uv, X, K=K)
    assert np.allclose(cam["centre"], C, atol=0.15)
    assert cam["rms_px"] < 1.5
    cam2 = photo.solve_camera(uv, X)  # no intrinsics: DLT path
    assert np.allclose(cam2["centre"], C, atol=0.6)
    bc = photo.blender_camera(cam, 4000, 3000)
    assert bc["lens"] == pytest.approx(2800 / 4000 * 36, rel=1e-6)


def test_blender_camera_matches_the_pinhole_for_portrait_and_off_centre_images():
    """The Blender camera made by blender_camera() puts a 3-D point where K, R, t project it, also for a portrait
    image whose principal point lies outside the frame (a crop of a larger photo)."""
    import importlib.util
    import json
    import subprocess
    import sys
    import numpy as np
    import pytest
    from propmodel import photo
    if importlib.util.find_spec("bpy") is None:
        pytest.skip("needs the bpy module")
    W, H = 180, 240
    K = np.array([[850.0, 0, 225.0], [0, 850.0, 140.0], [0, 0, 1]])
    C = np.array([30.0, -15.0, 2.0]); T = np.array([10.0, -3.0, 3.0])
    f = (T - C) / np.linalg.norm(T - C); r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r); u = np.cross(f, r)
    R = np.vstack([r, u, f]); t = -R @ C
    X = np.array([[12.0, -4.0, 4.0], [14.0, -6.0, 1.0], [9.0, -1.0, 6.5]])
    q, _ = photo.project(K, R, t, X)
    b = photo.blender_camera({"K": K.tolist(), "R": R.tolist(), "t": t.tolist()}, W, H)
    script = r"""
import bpy, json, sys
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view
b, X, W, H = json.loads(sys.argv[1])
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
cd = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cd); sc.collection.objects.link(co)
co.matrix_world = Matrix.Translation(b["location"]) @ Matrix(b["matrix_rotation"]).to_4x4()
cd.lens, cd.sensor_width, cd.sensor_fit = b["lens"], b["sensor_width"], b["sensor_fit"]
cd.shift_x, cd.shift_y = b["shift_x"], b["shift_y"]
sc.render.resolution_x, sc.render.resolution_y = W, H
out = []
for x in X:
    v = world_to_camera_view(sc, co, Vector(x)); out.append([v.x * W, (1 - v.y) * H])
print("UV" + json.dumps(out))
"""
    r = subprocess.run([sys.executable, "-c", script, json.dumps([b, X.tolist(), W, H])], capture_output=True, text=True,
                       timeout=120)
    uv = np.array(json.loads(r.stdout.split("UV", 1)[1].splitlines()[0]))
    assert np.abs(uv - q).max() < 0.5, (uv, q)
