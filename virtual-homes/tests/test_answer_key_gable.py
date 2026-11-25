"""Gable houses: the answer key must equal the closed-form hand calculation, for many seeds.

Hand formulas for a gable wing (L = wall length along the ridge, W = wall width, p = rise/run,
e = eave overhang, r = rake overhang, all horizontal):
    slope length   s = (W/2 + e) * sqrt(1 + p^2)
    each facet     (L + 2r) * s                       (a rectangle)
    ridge          L + 2r
    eaves          2 (L + 2r)
    rakes          4 s
    footprint      L * W
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vhomes import answer_key as A, geometry as G, spec as S  # noqa: E402

FT, FT2 = 0.3048, 0.3048 ** 2


def hand(w):
    L, W, p, e, r = w["length"], w["width"], w["pitch"], w["eave_overhang"], w["rake_overhang"]
    s = (W / 2 + e) * math.sqrt(1 + p * p)
    return {"area_ft2": 2 * (L + 2 * r) * s / FT2, "ridge": (L + 2 * r) / FT, "eave": 2 * (L + 2 * r) / FT,
            "rake": 4 * s / FT, "footprint_ft2": L * W / FT2, "pitch_x12": 12 * p,
            "plan_ft2": (L + 2 * r) * (W + 2 * e) / FT2}


@pytest.mark.parametrize("seed", range(1, 41))
def test_gable_matches_hand_calculation(seed):
    spec = S.make_spec(seed)
    key = A.compute(G.build_house(spec))
    h = hand(spec["wings"][0])
    t, lf = key["totals"], key["lines_ft"]
    assert t["roof_area_ft2"] == pytest.approx(h["area_ft2"], rel=1e-9)
    assert t["squares"] == pytest.approx(h["area_ft2"] / 100, rel=1e-9)
    assert t["roof_plan_area_ft2"] == pytest.approx(h["plan_ft2"], rel=1e-9)
    assert t["footprint_area_ft2"] == pytest.approx(h["footprint_ft2"], rel=1e-9)
    assert lf["ridge"] == pytest.approx(h["ridge"], rel=1e-9)
    assert lf["eave"] == pytest.approx(h["eave"], rel=1e-9)
    assert lf["rake"] == pytest.approx(h["rake"], rel=1e-9)
    for k in ("hip", "valley", "transition", "step_flashing", "headwall", "top_edge", "penetration"):
        assert lf[k] == 0.0
    assert len(key["facets"]) == 2
    for f in key["facets"]:
        assert f["pitch_x12"] == pytest.approx(h["pitch_x12"], abs=1e-9)
        assert f["area_ft2"] == pytest.approx(h["area_ft2"] / 2, rel=1e-9)
    az = sorted(f["azimuth_deg"] for f in key["facets"])
    assert (az[1] - az[0]) == pytest.approx(180.0, abs=1e-9)          # the two planes face opposite ways
    ridge_bearing = spec["wings"][0]["azimuth"]
    assert math.cos(math.radians(az[0] - ridge_bearing)) == pytest.approx(0.0, abs=1e-9)   # and face off the ridge
    m = key["materials"]
    assert m["drip_edge_ft"] == pytest.approx(h["eave"] + h["rake"], rel=1e-9)
    assert m["ridge_cap_ft"] == pytest.approx(h["ridge"], rel=1e-9)
    assert m["valley_metal_ft"] == 0.0
    assert key["cross_check"]["status"].startswith("agree")
    json.dumps(key)                                                    # serialisable


def test_azimuth_stays_in_0_360():
    for seed in range(1, 61):
        for f in A.compute(G.build_house(S.make_spec(seed)))["facets"]:
            assert 0.0 <= f["azimuth_deg"] < 360.0


def test_line_counts_and_lengths_gable():
    key = A.compute(G.build_house(S.make_spec(5)))
    kinds = sorted(l["kind"] for l in key["lines"])
    assert kinds == ["eave", "eave", "rake", "rake", "rake", "rake", "ridge"]


def test_ice_and_water_hand_check():
    spec = S.make_spec(1)
    w = spec["wings"][0]
    key = A.compute(G.build_house(spec))
    iw = key["materials"]["ice_and_water"]
    reach_ft = (w["eave_overhang"] + 0.6096) * math.sqrt(1 + w["pitch"] ** 2) / FT
    courses = 1 + max(0, math.ceil((reach_ft - 3.0) / 2.75))
    eave_len_ft = (w["length"] + 2 * w["rake_overhang"]) / FT
    assert iw["eave_required_area_ft2"] == pytest.approx(2 * eave_len_ft * reach_ft, rel=1e-9)
    assert all(e["courses"] == courses for e in iw["eaves"])
    assert all(e["overhang_m"] == pytest.approx(w["eave_overhang"], abs=1e-9) for e in iw["eaves"])


def test_spec_is_deterministic():
    assert S.make_spec(11) == S.make_spec(11)
    a = G.build_house(S.make_spec(11))
    b = G.build_house(S.make_spec(11))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert S.make_spec(11) != S.make_spec(12)


def test_details_and_markers_sit_on_their_planes():
    for seed in range(1, 21):
        h = G.build_house(S.make_spec(seed))
        planes = {f["id"]: f["plane"] for f in h["facets"]}
        for d in h["details"]:
            a, b, c = planes[d["facet"]]
            x, y, z = d["center"]
            assert z == pytest.approx(a * x + b * y + c, abs=1e-9)
        roof = [m for m in h["markers"] if m["id"] == "roof"]
        for m in roof:
            a, b, c = planes[m["facet"]]
            for x, y, z in m["corners"]:
                # the printed face lies 6 mm above the roof plane, measured along the plane normal
                assert z - (a * x + b * y + c) == pytest.approx(0.006 * math.sqrt(1 + a * a + b * b), abs=1e-9)
            side = [math.dist(m["corners"][i], m["corners"][(i + 1) % 4]) for i in range(4)]
            assert side == pytest.approx([m["size_m"]] * 4, abs=1e-9)
        counts = A.compute(h)["counts"]
        spec = h["spec"]["details"]
        assert counts["box_vents"] == spec["box_vents"]
        assert counts["pipe_boots"] == spec["pipe_boots"]
