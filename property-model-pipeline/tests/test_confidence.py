"""Demo gates and the confidence statement helpers (propmodel/confidence.py): synthetic values only."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from propmodel import confidence as C  # noqa: E402
from propmodel.roofgeom import Wing, build, to_mesh_json  # noqa: E402

LIDAR = {"flight_date": "2020-12-05", "year": 2020}


def test_dates():
    assert str(C._date("2021-03-04")) == "2021-03-04"
    assert str(C._date("3/4/2021")) == "2021-03-04"
    assert str(C._date(1614816000000)) == "2021-03-04"       # ArcGIS epoch ms
    assert C._date("n/a") is None and C._date(None) is None


def test_g1_addition_after_the_flight_stops():
    rec = {"permits": [{"PERMITTYPE": "Residential", "WORKCLASS": "Reshingle", "FINALIZEDATE": "2022-06-01"},
                       {"PERMITTYPE": "Residential", "WORKCLASS": "Addition", "ISSUEDATE": "2021-01-10",
                        "FINALIZEDATE": "2021-09-30"}],
           "address_point": {"YEARBUILT": 1998}}
    g = {x["id"]: x for x in C.g1_records(rec, LIDAR)}
    assert g["G1.permits"]["status"] == C.STOP and g["G1.permits"]["overridable"]
    assert g["G1.permits"]["value"] == ["2021-09-30"]
    assert g["G1.year_built"]["status"] == C.PASS


def test_g1_reshingle_only_passes_and_new_house_stops():
    rec = {"permits": [{"WORKCLASS": "Reshingle", "FINALIZEDATE": "2023-05-01"}], "YEARBUILT": 1985}
    assert all(x["status"] == C.PASS for x in C.g1_records(rec, LIDAR))
    new = {"permits": [], "parcel": {"Year_Built": 2021}}
    g = {x["id"]: x for x in C.g1_records(new, LIDAR)}
    assert g["G1.year_built"]["status"] == C.STOP
    assert C.g1_records(None, LIDAR)[0]["status"] == C.WARN       # no records: say so


def test_privacy_scan_finds_owner_like_keys(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"parcel": {"ACREAGE": 0.2, "LANDUSE": "R1"}}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"rows": [{"OWNNAME1": "x"}, {"MRTADR": "y"}, {"contractor_name": "z"}]}))
    assert C.privacy_scan([str(good)]) == []
    keys = sorted(k for _, k in C.privacy_scan([str(bad), str(good)]))
    assert keys == ["MRTADR", "OWNNAME1", "contractor_name"]


def test_address_tokens_and_repo_grep(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "clean.md").write_text("generic notes, 42 S Main pump station\n")
    job = {"address": "42 S Example Rd, Town, ST", "slug": "42-s-example-rd"}
    site = {"geocode": {"lat": 10.123456, "lon": -140.654321}}
    toks = C.address_tokens(job, site, {"parcel": {"TAG": "ABC12345"}})
    assert C.grep_repo(str(repo), toks) == []
    (repo / "notes.md").write_text("job for 42 Example Road\n")      # number + street word, any suffix
    (repo / "data.json").write_text('{"lat": 10.1235}')
    (repo / "x.txt").write_text("tag ABC12345")
    hits = sorted(f for f, _ in C.grep_repo(str(repo), toks))
    assert hits == ["data.json", "notes.md", "x.txt"]


def test_g0_address_variants():
    assert C.g0_address({"source": "address_points", "n": 1})[0]["status"] == C.PASS
    zero = C.g0_address({"source": "address_points", "n": 0})[0]
    assert zero["status"] == C.STOP and not zero["overridable"]
    two = C.g0_address({"source": "address_points", "n": 2})[0]
    assert two["status"] == C.STOP and two["overridable"]
    assert C.g0_address({"source": "census"})[0]["status"] == C.WARN
    g = C.g0_address({"source": "address_points", "n": 1, "county": "Elsewhere", "allowed_counties": ["A", "B"]})
    assert g[1]["id"] == "G0.county" and g[1]["status"] == C.WARN


def test_estimate_shift_recovers_offset():
    from shapely.geometry import Polygon
    roof = Polygon([(0, 0), (14, 0), (14, 10), (0, 10)])
    city = [(x - 0.6, y + 0.8) for x, y in roof.exterior.coords[:-1]]
    sh = C.estimate_shift(city, roof)
    assert sh["dx"] == pytest.approx(0.6, abs=0.06) and sh["dy"] == pytest.approx(-0.8, abs=0.06)
    assert sh["iou"] > 0.98


def test_edge_closure_and_plane_residuals():
    w = Wing(id="M", type="gable", length=12, width=8, eave_height=3, pitch=0.5)
    m = build([w])
    c = C.edge_closure(to_mesh_json(m))
    assert abs(c["diff"]) < 1e-6
    rng = np.random.default_rng(0)
    xy = rng.uniform(-4, 4, (400, 2))         # inside the roof outline (x +-4.45, y +-6.3)
    z = m.surface_z(xy) + rng.normal(0, 0.03, 400)
    rows = np.column_stack([xy, z, (xy[:, 0] > 0).astype(float)])
    r = C.plane_residuals(m, rows, [{"area_cells_m2": 40}, {"area_cells_m2": 40}])
    assert r["covered_rms_m"] < 0.05 and r["outside_frac"] == 0 and r["unassigned_big_planes"] == []
    # a plane the model does not cover (a missing wing) is unassigned
    far = np.column_stack([rng.uniform(20, 25, (80, 2)), np.full(80, 3.0), np.full(80, 2.0)])
    r2 = C.plane_residuals(m, np.vstack([rows, far]), [{"area_cells_m2": 40}, {"area_cells_m2": 40}, {"area_cells_m2": 20}])
    assert r2["unassigned_big_planes"] == ["P3"]


def test_g6_mesh_gate():
    assert C.g6_mesh(200.0, 200.5)[0]["status"] == C.PASS
    assert C.g6_mesh(200.0, 202.0)[0]["status"] == C.STOP
    assert C.g6_mesh(200.0, None)[0]["status"] == C.WARN


def test_g2_hillside_gate_fires_on_a_steep_lot(tmp_path):
    """A 12 % lot: the slope test says re-run in ground-surface mode; a flat one does not."""
    (tmp_path / "data").mkdir()
    rng = np.random.default_rng(1)
    for slope, expect in ((0.12, True), (0.01, False)):
        xy = rng.uniform(-30, 30, (12000, 2))          # 3.3 returns per m2
        roof = (np.abs(xy[:, 0]) < 6) & (np.abs(xy[:, 1]) < 5)
        z = 400 + slope * xy[:, 1] + np.where(roof, 4.0, 0.0)
        pts = np.column_stack([xy, z, np.where(roof, 1, 2), np.ones(len(z)), np.ones(len(z))])
        np.save(tmp_path / "data" / "lidar_points.npy", pts)
        li = {"ground_plane": [0.0, slope, 400.0], "flight_date": "2020-05-28", "leaf_on": True, "year": 2020,
              "roof_outline": [[-6, -5], [6, -5], [6, 5], [-6, 5]], "planes": []}
        (tmp_path / "data" / "lidar.json").write_text(json.dumps(li))
        g, info = C.g2_lidar(str(tmp_path))
        assert info["hillside"] is expect
        gg = {x["id"]: x for x in g}
        assert gg["G2.flight"]["status"] == C.WARN            # late-May flight: leaf-on
        assert gg["G2.density"]["status"] == C.PASS
