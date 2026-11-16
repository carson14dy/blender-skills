import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
import pytest
from propmodel.roofgeom import Wing, build
from propmodel import fusion

TRUE = dict(id="M", type="hip", cx=1.0, cy=-0.5, azimuth=12.0, length=14.0, width=9.0,
            eave_height=2.9, pitch=0.5, eave_overhang=0.45, rake_overhang=0.45)


def synth_lidar(w, n=400, noise=0.08, seed=1):
    rng = np.random.default_rng(seed)
    m = build([w])
    minx, miny, maxx, maxy = m.roof_outline().bounds
    pts = []
    while len(pts) < n:
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        z = m.surface_z([[x, y]])[0]
        if not np.isnan(z):
            pts.append([x, y, z + rng.normal(0, noise)])
    return np.array(pts)


def test_fit_recovers_truth_from_lidar_and_outline():
    truth = Wing(**TRUE)
    pts = synth_lidar(truth)
    outline = list(truth.roof_outline().exterior.coords)[:-1]
    start = dict(TRUE, cx=0, cy=0, azimuth=8.0, length=13.0, width=9.8, eave_height=3.3, pitch=0.42)
    spec = {"wings": [start], "free": ["M.cx", "M.cy", "M.azimuth", "M.length", "M.width", "M.eave_height", "M.pitch"]}
    obs = [{"target": "roof_z", "points": pts.tolist(), "sigma": 0.08, "source": "lidar"},
           {"target": "outline", "polygon": outline, "sigma": 0.1, "source": "trace"}]
    res = fusion.fit(spec, obs)
    # every estimate must be within 3 reported sigma of the truth (honest uncertainty)
    for name, true in (("M.length", 14.0), ("M.width", 9.0), ("M.pitch", 0.5), ("M.azimuth", 12.0),
                       ("M.eave_height", 2.9), ("M.cx", 1.0), ("M.cy", -0.5)):
        est = res["params"][name]
        assert abs(est["value"] - true) < 3 * est["sigma"] + 1e-3, (name, est, true)
    assert res["params"]["M.pitch"]["sigma"] < 0.01
    true_area = build([truth]).roof_area()
    assert res["measurements"]["roof.area"] == pytest.approx(true_area, rel=0.01)
    assert 0 < res["measurement_sigma"]["roof.area"] < 0.02 * true_area


def test_conflicting_past_report_is_flagged():
    truth = Wing(**TRUE)
    true_area = build([truth]).roof_area()
    pts = synth_lidar(truth)
    spec = {"wings": [TRUE], "free": ["M.length", "M.width", "M.pitch", "M.eave_height"]}
    obs = [{"target": "roof_z", "points": pts.tolist(), "sigma": 0.08, "source": "lidar"},
           {"target": "M.length", "value": "45.93ft", "sigma": "1in", "source": "tape"},
           {"target": "roof.area", "value": f"{true_area * 0.8 * 10.7639:.0f} sqft", "sigma": "1%",
            "source": "2009 report", "kind": "past_report"}]
    res = fusion.fit(spec, obs)
    flags = {r["source"]: r["flag"] for r in res["residuals"]}
    assert flags["2009 report"] == "EXCLUDED"
    assert flags["tape"] == "ok"
    # robust fit is not dragged far by the blunder
    assert res["measurements"]["roof.area"] == pytest.approx(true_area, rel=0.03)


def test_units_parsing():
    assert fusion.parse_value("roof.area", "25.5 squares") == pytest.approx(2550 / 10.7639104, rel=1e-6)
    assert fusion.parse_value("M.pitch", "6/12") == pytest.approx(0.5)
    assert fusion.parse_value("M.length", "42' 6\"") == pytest.approx(12.954, abs=1e-6)
    assert fusion.parse_sigma("roof.area", "2%", 100.0) == pytest.approx(2.0)


def test_snooping_excludes_blunder_and_keeps_answer():
    truth = Wing(**TRUE)
    true_area = build([truth]).roof_area()
    pts = synth_lidar(truth)
    spec = {"wings": [TRUE], "free": ["M.length", "M.width", "M.pitch", "M.eave_height"]}
    obs = [{"target": "roof_z", "points": pts.tolist(), "sigma": 0.08, "source": "lidar"},
           {"target": "roof.area", "value": true_area * 0.75, "sigma": "1%", "source": "old"}]
    res = fusion.fit(spec, obs)
    assert [o["source"] for o in res["excluded"]] == ["old"]
    assert res["measurements"]["roof.area"] == pytest.approx(true_area, rel=0.005)


def test_chained_ties_form_one_group():
    ps = fusion.ParamSpace([dict(id="A"), dict(id="B"), dict(id="C")], ["A.pitch", "B.pitch", "C.pitch"],
                           ties=[["A.pitch", "B.pitch"], ["B.pitch", "C.pitch"]])
    assert len(ps.groups) == 1 and sorted(ps.groups[0]) == ["A.pitch", "B.pitch", "C.pitch"]
