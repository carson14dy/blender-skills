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
