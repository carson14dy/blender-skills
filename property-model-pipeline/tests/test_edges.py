"""Drip-edge measurement (propmodel/edges.py) and segment outline observations (fusion.py) on the synthetic
gable of tests/fixtures/demo_job: 1.3 m true eave overhang, 0.6 m rake, a model built with the 0.45 / 0.30 m priors."""
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "fixtures", "demo_job"))

import make_fixture as FX  # noqa: E402
from propmodel import edges as E, fusion  # noqa: E402
from propmodel.roofgeom import Wing, build, to_mesh_json  # noqa: E402


def _points_model_frame(h):
    """Fixture returns with z above the ground at the house centre (the wing heights' datum)."""
    w = Wing.from_dict(h["truth"])
    P = FX.points(h)
    sx, sy = h["ground_slope"]
    g0 = float(h["elevation_m"]) + sx * w.cx + sy * w.cy
    return np.column_stack([P[:, 0], P[:, 1], P[:, 2] - g0])


@pytest.fixture(scope="module")
def setup():
    h = FX.house()
    truth = dict(h["truth"])
    prior = dict(truth, eave_overhang=0.45, rake_overhang=0.30)     # walls right, overhangs from the priors
    return h, truth, prior, _points_model_frame(h)


def test_drip_edges_report_the_prior_error(setup):
    h, truth, prior, pts = setup
    mj = to_mesh_json(build([Wing.from_dict(prior)]))
    res = E.drip_edges(mj, pts)
    rows = {(r["kind"], r["param"]): r for r in res["edges"]}
    eaves = [r for r in res["edges"] if r["kind"] == "eave"]
    rakes = [r for r in res["edges"] if r["kind"] == "rake"]
    assert len(eaves) == 2 and len(rakes) == 4 and all(r["status"] == "measured" for r in res["edges"])
    for r in eaves:               # true drip edge is 1.30 - 0.45 = 0.85 m beyond the model's
        assert r["offset_m"] == pytest.approx(0.85, abs=0.12), r
        assert r["param"] == "M.eave_overhang"
    for r in rakes:               # 0.60 - 0.30
        assert r["offset_m"] == pytest.approx(0.30, abs=0.12), r
        assert r["param"] == "M.rake_overhang"
    # the wall-face returns under the eaves give the wall line, so the overhang itself is measured
    ov = E.overhang_parameters(res)
    assert ov["M.eave_overhang"]["value"] == pytest.approx(1.3, abs=0.1)
    assert ov["M.rake_overhang"]["value"] == pytest.approx(0.6, abs=0.1)
    assert rows and res["summary"]["measured"] == 6


def test_drip_observations_fix_the_area(setup):
    """Fit with LiDAR roof_z + the measured drip segments + a wall-line outline: area within 1 % of the truth."""
    h, truth, prior, pts = setup
    true_area = build([Wing.from_dict(truth)]).roof_area()
    mj = to_mesh_json(build([Wing.from_dict(prior)]))
    res = E.drip_edges(mj, pts)
    walls = list(Wing.from_dict(truth).wall_polygon().exterior.coords)[:-1]
    E.city_wall_overhangs(res, walls)
    obs = E.edge_observations(res)
    assert all(o["kind"] == "lidar_drip" and len(o["segments"]) == 1 for o in obs)
    roof = pts[pts[:, 2] > 1.8]
    obs += [{"target": "roof_z", "points": roof[::3].tolist(), "sigma": 0.1, "source": "lidar"},
            {"target": "outline", "which": "footprint", "polygon": walls, "sigma": 0.25, "source": "city walls"}]
    free = ["M.cx", "M.cy", "M.azimuth", "M.length", "M.width", "M.eave_height", "M.pitch", "M.eave_overhang", "M.rake_overhang"]
    ov = E.overhang_parameters(res)
    spec = {"wings": [prior], "free": free,
            "priors": {k: {"value": v["value"], "sigma": 0.25} for k, v in ov.items()}}
    fit = fusion.fit(spec, obs)
    area = fit["measurements"]["roof.area"]
    assert area == pytest.approx(true_area, rel=0.01)
    assert fit["params"]["M.eave_overhang"]["value"] == pytest.approx(1.3, abs=0.15)
    assert fit["measurement_sigma"]["roof.area"] > 0
    # with the priors alone (no drip edges) the same walls give a roof far too small
    assert build([Wing.from_dict(prior)]).roof_area() < 0.93 * true_area


def test_occluded_and_sparse_edges_are_not_measured(setup):
    h, truth, prior, pts = setup
    mj = to_mesh_json(build([Wing.from_dict(prior)]))
    w = Wing.from_dict(prior)
    # drop every return near one eave (a tree hides it): that edge keeps the fitted position
    rel = pts[:, :2] - [w.cx, w.cy]
    vv = rel @ w.v
    keep = ~((vv > w.width / 2 - 0.5) & (pts[:, 2] > 0.5))
    res = E.drip_edges(mj, pts[keep])
    st = sorted(r["status"] for r in res["edges"] if r["kind"] == "eave")
    assert st == ["measured", "too_few_returns"]
    assert len(E.edge_observations(res)) == 5


def test_edge_parameter_mapping():
    # azimuth 0: the length axis u points north, v points west; +v = west wall, -v = east wall, u ends = N / S
    g = {"id": "G", "type": "gable", "cx": 0, "cy": 0, "azimuth": 0, "length": 10, "width": 8}
    assert E.edge_parameter(g, (-4.5, 0)) == "G.eave_overhang"         # +v eave
    assert E.edge_parameter(g, (4.5, 0)) == "G.eave_overhang"          # -v eave without its own overhang
    assert E.edge_parameter(g, (0, 5.5)) == "G.rake_overhang"          # gable end
    assert E.edge_parameter(dict(g, type="hip"), (0, 5.5)) == "G.eave_overhang"   # a hip end is an eave
    assert E.edge_parameter(dict(g, eave_overhang_b=1.0), (4.5, 0)) == "G.eave_overhang_b"
    assert E.edge_parameter(dict(g, outline=[[0, 0], [1, 0], [1, 1]]), (-4.5, 0)) is None


def test_segment_outline_observation_pulls_only_its_edge():
    w = dict(id="M", type="gable", cx=0, cy=0, azimuth=0, length=10, width=8, eave_height=3, pitch=0.5,
             eave_overhang=0.4, rake_overhang=0.3)
    m = build([Wing.from_dict(w)])
    umax, vlo, vhi = Wing.from_dict(w).extents()
    # azimuth 0: u = north, v = west (-x). One measured drip segment 0.5 m further west than the model's +v eave.
    seg = [[-(vhi + 0.5), -umax + 1], [-(vhi + 0.5), umax - 1]]
    spec = {"wings": [w], "free": ["M.eave_overhang", "M.eave_overhang_b"]}
    fit = fusion.fit(spec, [{"target": "outline", "which": "roof_outline", "segments": [seg], "sigma": 0.05,
                             "source": "drip"}])
    assert fit["params"]["M.eave_overhang"]["value"] == pytest.approx(0.9, abs=0.02)
    assert fit["params"]["M.eave_overhang_b"]["value"] == pytest.approx(0.4, abs=0.02)   # untouched side
    assert m.roof_area() < fit["measurements"]["roof.area"]


def test_disabled_observations_are_ignored():
    w = dict(id="M", type="gable", cx=0, cy=0, azimuth=0, length=10, width=8, eave_height=3, pitch=0.5)
    ring = list(Wing.from_dict(dict(w, length=12)).roof_outline().exterior.coords)[:-1]
    spec = {"wings": [w], "free": ["M.length"]}
    on = fusion.fit(spec, [{"target": "outline", "polygon": ring, "sigma": 0.1, "source": "a"}])
    off = fusion.fit(spec, [{"target": "outline", "polygon": ring, "sigma": 0.1, "source": "a", "disabled": True},
                            {"target": "M.length", "value": 10.0, "sigma": 0.01, "source": "tape"}])
    assert on["params"]["M.length"]["value"] == pytest.approx(12.0, abs=0.05)
    assert off["params"]["M.length"]["value"] == pytest.approx(10.0, abs=0.01)
    assert [r["source"] for r in off["residuals"]] == ["tape"]
