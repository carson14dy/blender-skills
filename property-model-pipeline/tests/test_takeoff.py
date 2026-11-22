"""Report takeoff: sliver facets dropped, height above grade on both sides, siding vs concrete vs buried wall."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from propmodel import report, roofgeom as R  # noqa: E402


def _stack(d):
    """A gable storey on a flat lower storey that is 2*d wider: its roof shows only as two d-wide strips."""
    M = R.Wing(id="M", type="gable", length=10, width=8, eave_height=5, pitch=0.33, base_z=2.3,
               eave_overhang=0.0, rake_overhang=0.0)
    L = R.Wing(id="L", type="flat", length=10, width=8 + 2 * d, eave_height=2.3, pitch=0.0,
               eave_overhang=0.0, rake_overhang=0.0)
    return [M, L]


def test_sliver_facets_are_not_facets_and_bring_no_edges():
    m = R.build(_stack(0.002))                       # 2 x (0.002 x 10 m) = 0.04 m2 of hidden flat roof
    assert [f.id for f in m.facets] == ["F1", "F2"]
    assert abs(m.edge_total("eave") - 20.0) < 1e-6    # the strips' 20 m of "eave" are gone too
    assert m.measurements()["roof.facets"] == 2
    assert "| F3 |" not in report.build_report(m)
    wide = R.build(_stack(0.5))                       # a real 10 m2 lower roof stays
    assert len(wide.facets) == 3


def test_height_above_grade_low_and_high_side():
    wings = [R.Wing(id="A", type="gable", length=10, width=8, eave_height=3, pitch=0.5, base_z=-2.0,
                    eave_overhang=0.0, rake_overhang=0.0)]

    def levels(key, pts, outward, bottom):           # grade rises 0.3 m per m to the north (walls at y = +-5)
        return 0.3 * pts[:, 1], np.full(len(pts), np.nan)
    m = R.build(wings, levels=levels)
    meas = m.measurements()
    top = meas["building.height"]                     # ridge z = 3 + 0.5 * 4 = 5
    assert abs(top - 5.0) < 1e-6
    assert abs(meas["grade.low"] + 1.5) < 0.01 and abs(meas["grade.high"] - 1.5) < 0.01
    assert abs(meas["building.height_low_side"] - 6.5) < 0.01
    assert abs(meas["building.height_high_side"] - 3.5) < 0.01
    md = report.build_report(m)
    assert "low side" in md and "high side" in md
    # no levels, no ground plane: the wall bottoms give the two sides (walk-out on a lower storey)
    m2 = R.build(_stack(0.5))
    meas2 = m2.measurements()
    assert abs(meas2["building.height_low_side"] - (meas2["building.height"] - 0.0)) < 1e-6
    assert abs(meas2["building.height_high_side"] - (meas2["building.height"] - 2.3)) < 1e-6


def test_siding_is_above_grade_and_the_concrete_line_openings_deducted():
    wings = [R.Wing(id="A", type="flat", length=10, width=8, eave_height=3, pitch=0.0, base_z=0.0,
                    eave_overhang=0.0, rake_overhang=0.0)]

    def levels(key, pts, outward, bottom):
        g = np.full(len(pts), 1.0 if outward[1] > 0.5 else 0.0)        # north wall buried 1 m
        return g, np.full(len(pts), 1.5) if outward[1] > 0.5 else bottom + 0.2
    m = R.build(wings, levels=levels)
    north = next(w for w in m.walls if w.bearing < 1 or w.bearing > 359)        # 8 m long (the wing runs N-S)
    assert abs(north.area_buried - 8.0) < 0.05 and abs(north.area_foundation - 4.0) < 0.05
    assert abs(north.area_siding - 12.0) < 0.05
    meas = m.measurements()
    assert abs(meas["wall.area"] - 108.0) < 0.1                         # bottom to roof, all four walls
    assert abs(meas["wall.area_buried"] - 8.0) < 0.1
    assert abs(meas["wall.area_foundation"] - (4.0 + 0.2 * 28)) < 0.1
    assert abs(meas["wall.area_siding"] - (12.0 + 2.8 * 28)) < 0.1
    ops = [{"facade": "S", "area_m2": 2.0, "zone": "siding"}, {"facade": "N", "area_m2": 0.5, "zone": "foundation"}]
    extra = [{"name": "garage front", "facade": "S", "area_m2": 12.0, "material": "concrete", "openings_m2": 9.0}]
    md = report.build_report(m, openings=ops, extra_walls=extra)
    walls_md = md.split("## Walls (siding)", 1)[1]
    siding_md, concrete_md = walls_md.split("### Foundation / concrete", 1)
    tot_sid = meas["wall.area_siding"]
    assert f"**{report.U.sqft(tot_sid):.0f}**" in siding_md and f"**{report.U.sqft(tot_sid - 2.0):.0f}**" in siding_md
    tot_con = meas["wall.area_foundation"] + 12.0
    assert f"**{report.U.sqft(tot_con):.0f}**" in concrete_md and f"**{report.U.sqft(tot_con - 9.5):.0f}**" in concrete_md
    assert "garage front" in concrete_md and "Below grade (buried, not sided)" in concrete_md


def test_pm_reads_grade_surface_and_details_for_the_takeoff(tmp_path):
    import importlib.util
    import json
    spec_ = importlib.util.spec_from_file_location(
        "pm_cli_t", os.path.join(os.path.dirname(__file__), "..", "scripts", "pm.py"))
    pm = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(pm)
    (tmp_path / "data").mkdir()
    Z = np.full((60, 60), -1.0)                                                 # grade -1 everywhere (0.5 m cells)
    np.savez_compressed(tmp_path / "data" / "ground_surface.npz", Z=Z, ground=np.ones_like(Z, bool),
                        x0=-15.0, y0=-15.0, cell=0.5)
    det = {"foundation": {"default_reveal": 0.2, "walls": {"A:-v": 0.5}},
           "openings": [{"wall": "A:-v", "u": 2, "sill_z": 1.0, "width": 1.0, "height": 1.0},
                        {"wall": "GF", "u": 1, "sill_z": -1.0, "width": 2.0, "height": 2.0}],
           "extra_walls": [{"name": "GF", "bottom": [[-3, -9, -1.0], [3, -9, -1.0]], "top_z": 1.0, "bearing": 180,
                            "material": "concrete"}]}
    (tmp_path / "details.json").write_text(json.dumps(det))
    wd = [{"id": "A", "type": "flat", "length": 10, "width": 8, "eave_height": 3, "pitch": 0.0, "base_z": -2.0,
           "eave_overhang": 0.0, "rake_overhang": 0.0, "azimuth": 90}]
    m = pm._build_for_report(str(tmp_path), {}, wd)
    meas = m.measurements()
    assert abs(meas["grade.low"] + 1.0) < 1e-6 and abs(meas["building.height_low_side"] - 4.0) < 1e-6
    assert abs(meas["wall.area_buried"] - 36.0) < 0.1                         # 1 m under grade all round
    south = next(w for w in m.walls if abs(w.bearing - 180) < 1)
    assert south.side == "-v" and abs(south.area_foundation - 10 * 1.5) < 0.05   # grade -1 up to the 0.5 line
    ops, extra = pm._details_openings(str(tmp_path), m)
    assert ops == [{"facade": "S", "area_m2": 1.0, "zone": "siding", "label": ""}]
    assert extra[0]["name"] == "GF" and abs(extra[0]["area_m2"] - 12.0) < 1e-6 and extra[0]["openings_m2"] == 4.0
