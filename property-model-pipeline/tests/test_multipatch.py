"""City LOD2 multipatch decoding (propmodel/multipatch.py): binaryPatches round trip, absolute-tolerance vertex
handling at state-plane coordinates, face classes, roof area / pitch / sampled heights, registration to LiDAR."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from propmodel import multipatch as MP  # noqa: E402

FTUS = MP.Z_UNITS["ftus"]
X0, Y0 = 2_217_500.0, 15_820_500.0       # state-plane-like feet (synthetic, no real place)


def gable_parts(x0=X0, y0=Y0, L=40.0, W=30.0, ov=1.5, pitch=0.5, eave=10.0, base=-2.0, closed=True):
    """A gable solid in feet: 2 roof faces (to the drip edge), 4 walls, a floor. Ridge along x."""
    ridge = eave + pitch * W / 2
    drip = eave - pitch * ov
    def ring(pts):
        a = np.asarray(pts, float)
        return np.vstack([a, a[:1]]) if closed else a
    roof_s = ring([[x0 - ov, y0 - ov, drip], [x0 + L + ov, y0 - ov, drip], [x0 + L + ov, y0 + W / 2, ridge], [x0 - ov, y0 + W / 2, ridge]])
    roof_n = ring([[x0 - ov, y0 + W / 2, ridge], [x0 + L + ov, y0 + W / 2, ridge], [x0 + L + ov, y0 + W + ov, drip], [x0 - ov, y0 + W + ov, drip]])
    walls = [ring([[x0, y0, base], [x0 + L, y0, base], [x0 + L, y0, eave], [x0, y0, eave]]),
             ring([[x0, y0 + W, base], [x0 + L, y0 + W, base], [x0 + L, y0 + W, eave], [x0, y0 + W, eave]]),
             ring([[x0, y0, base], [x0, y0 + W, base], [x0, y0 + W, eave], [x0, y0 + W / 2, ridge], [x0, y0, eave]]),
             ring([[x0 + L, y0, base], [x0 + L, y0 + W, base], [x0 + L, y0 + W, eave], [x0 + L, y0 + W / 2, ridge], [x0 + L, y0, eave]])]
    floor = ring([[x0, y0, base], [x0 + L, y0, base], [x0 + L, y0 + W, base], [x0, y0 + W, base]])
    return [(4, r) for r in [roof_s, roof_n] + walls + [floor]]


def local_faces(parts, compress=True):
    b64 = MP.encode_shape_buffer(parts, compress=compress)
    dec = MP.geometry_parts({"binaryPatches": b64})
    faces = MP.faces_from_parts(dec, atol=1e-3)
    # projected feet -> metres about the first vertex (a stand-in for the local frame)
    fx = []
    for f in faces:
        def m(R):
            R = np.asarray(R, float)
            return np.column_stack([(R[:, 0] - X0) * FTUS, (R[:, 1] - Y0) * FTUS, R[:, 2] * FTUS])
        fx.append({"outer": m(f["outer"]), "holes": [m(h) for h in f["holes"]]})
    return MP.classify(fx)


@pytest.mark.parametrize("compress", [True, False])
def test_binary_patches_round_trip(compress):
    parts = gable_parts()
    dec = MP.geometry_parts({"binaryPatches": MP.encode_shape_buffer(parts, compress=compress)})
    assert len(dec) == len(parts) == 7
    for (t0, p0), (t1, p1) in zip(parts, dec):
        assert t0 == t1 and np.array_equal(p0, p1)


def test_absolute_tolerance_at_state_plane_coordinates():
    # two vertices 0.5 ft apart at x = 2.2e6 ft: numpy's default rtol (1e-5 -> 22 ft here) would merge them
    R = np.array([[X0, Y0, 0], [X0 + 0.5, Y0, 0], [X0 + 0.5, Y0 + 10, 0], [X0, Y0 + 10, 0], [X0, Y0, 0]])
    assert np.allclose(R[0], R[1])                     # the trap
    clean = MP._clean_ring(R, atol=1e-3)
    assert len(clean) == 4                             # closing vertex dropped, the 0.5 ft step kept
    dup = np.vstack([R[:1], R])                        # a repeated vertex IS dropped
    assert len(MP._clean_ring(dup, atol=1e-3)) == 4


def test_faces_classes_area_pitch_and_samples():
    faces = local_faces(gable_parts())
    kinds = sorted(f["kind"] for f in faces)
    assert kinds == ["floor", "roof", "roof", "wall", "wall", "wall", "wall"]
    roof = MP.roof_faces(faces)
    L, W, ov, p = 40 * FTUS, 30 * FTUS, 1.5 * FTUS, 0.5
    true_area = (L + 2 * ov) * (W + 2 * ov) * math.sqrt(1 + p * p)
    s = MP.summary(faces)
    assert s["roof_area_m2"] == pytest.approx(true_area, abs=0.002)
    assert all(f["pitch"] == pytest.approx(6.0, abs=1e-6) for f in roof)
    assert sorted(round(f["azimuth"]) for f in roof) == [0, 180]
    pts = MP.sample_roof(faces, spacing=0.5, inset=0.35, max_points=10_000)
    assert len(pts) > 200
    z = MP.surface_z(faces, pts[:, :2])
    assert np.max(np.abs(z - pts[:, 2])) < 1e-9


def test_registration_recovers_a_known_shift():
    faces = local_faces(gable_parts())
    rng = np.random.default_rng(3)
    # LiDAR reaches the drip edge on every side (an inset sample would leave the along-ridge shift free)
    pts = MP.sample_roof(faces, spacing=0.3, inset=0.01, max_points=5000)
    true = np.array([0.6, -0.8, 0.09])
    lidar = np.column_stack([pts[:, 0] + true[0], pts[:, 1] + true[1], pts[:, 2] + true[2] + rng.normal(0, 0.03, len(pts))])
    reg = MP.register(faces, lidar)
    assert reg["dx"] == pytest.approx(true[0], abs=0.1)
    assert reg["dy"] == pytest.approx(true[1], abs=0.1)
    assert reg["dz"] == pytest.approx(true[2], abs=0.03)
    assert reg["robust_sd_m"] < 0.06


def test_triangle_parts_and_rings_json():
    # a triangle strip and Esri-JSON rings decode to faces too
    strip = (0, np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float))
    assert len(MP.faces_from_parts([strip], atol=1e-6)) == 2
    rings = {"rings": [[[0, 0, 3], [4, 0, 3], [4, 4, 5], [0, 4, 5], [0, 0, 3]]]}
    f = MP.classify(MP.to_local(MP.faces_from_parts(MP.geometry_parts(rings), atol=1e-6), lonlat=False))
    assert f[0]["kind"] == "roof" and f[0]["pitch"] == pytest.approx(6.0)
