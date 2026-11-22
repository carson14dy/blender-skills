import math
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from propmodel.roofgeom import Wing, build

SF = math.sqrt(1 + 0.25)  # 6/12 slope factor


def by_kind(m):
    return {k: m.edge_total(k) for k in ("ridge", "hip", "valley", "eave", "rake", "headwall", "sidewall", "transition")}


def test_gable_no_overhang():
    m = build([Wing("A", "gable", length=10, width=8, pitch=0.5, eave_overhang=0, rake_overhang=0, eave_height=3)])
    assert len(m.facets) == 2
    assert m.roof_area() == pytest.approx(80 * SF, rel=1e-9)
    e = by_kind(m)
    assert e["ridge"] == pytest.approx(10)
    assert e["eave"] == pytest.approx(20)
    assert e["rake"] == pytest.approx(4 * 4 * SF)
    assert e["hip"] == e["valley"] == 0
    assert m.max_height() == pytest.approx(3 + 2)
    # walls: 2 eave walls 10x3, 2 gable walls 8x3 + triangle 0.5*8*2
    assert m.wall_area() == pytest.approx(2 * 30 + 2 * (24 + 8), rel=1e-4)


def test_gable_with_overhangs_area_is_outline_times_slope_factor():
    m = build([Wing("A", "gable", length=10, width=8, pitch=0.5, eave_overhang=0.5, rake_overhang=0.3)])
    assert m.roof_area() == pytest.approx(10.6 * 9 * SF, rel=1e-9)
    assert by_kind(m)["ridge"] == pytest.approx(10.6)


def test_hip_equal_pitch():
    m = build([Wing("A", "hip", length=10, width=8, pitch=0.5, eave_overhang=0, rake_overhang=0)])
    assert len(m.facets) == 4
    assert m.roof_area() == pytest.approx(80 * SF, rel=1e-9)
    e = by_kind(m)
    assert e["ridge"] == pytest.approx(2.0)
    assert e["hip"] == pytest.approx(4 * 6.0)
    assert e["eave"] == pytest.approx(36)
    assert e["rake"] == 0


def test_pyramid():
    m = build([Wing("A", "pyramid", length=8, width=8, pitch=0.5, eave_overhang=0)])
    e = by_kind(m)
    assert e["ridge"] == pytest.approx(0, abs=1e-6)
    assert e["hip"] == pytest.approx(4 * 6.0)


def test_shed_and_flat():
    m = build([Wing("A", "shed", length=6, width=4, pitch=0.25, eave_overhang=0, rake_overhang=0)])
    assert m.roof_area() == pytest.approx(24 * math.sqrt(1 + 0.0625))
    e = by_kind(m)
    assert e["eave"] == pytest.approx(12) and e["rake"] == pytest.approx(2 * 4 * math.sqrt(1 + 0.0625))
    f = build([Wing("A", "flat", length=6, width=4, pitch=0, eave_overhang=0)])
    assert f.roof_area() == pytest.approx(24)


def test_t_shape_cross_gable_valleys():
    main = Wing("M", "gable", cx=0, cy=0, azimuth=90, length=12, width=8, pitch=0.5, eave_overhang=0, rake_overhang=0)
    # wing extends south from the middle; ridge runs N-S and dies into the main roof at y=-1
    wing = Wing("W", "gable", cx=0, cy=-5, azimuth=0, length=10, width=6, pitch=0.5, eave_overhang=0, rake_overhang=0)
    m = build([main, wing])
    fp = m.footprint()
    # same pitch & plate height: roof area = plan area * slope factor (exact invariant)
    assert m.roof_area() == pytest.approx(fp.area * SF, rel=1e-6)
    e = by_kind(m)
    hv = math.sqrt(2 * 3 ** 2 + (0.5 * 3) ** 2)
    assert e["valley"] == pytest.approx(2 * hv, rel=1e-4)
    assert e["ridge"] == pytest.approx(12 + 9, rel=1e-4)  # main ridge + wing ridge (y=-10..-1)
    assert e["headwall"] == e["sidewall"] == 0


def test_two_storey_lower_roof_meets_wall():
    hi = Wing("H", "gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=5.5, pitch=0.5,
              eave_overhang=0.4, rake_overhang=0.3)
    lo = Wing("L", "shed", cx=0, cy=-6, azimuth=270, length=10, width=4, eave_height=2.6, pitch=0.25,
              eave_overhang=0.4, rake_overhang=0.3)
    m = build([hi, lo])
    e = by_kind(m)
    # porch shed roof dies into the taller wall: headwall flashing ~ shed length + rake overhangs
    assert e["headwall"] == pytest.approx(10.6, abs=0.05)
    # shed roof area includes the strip under the upper overhang (between the walls)
    shed = [f for f in m.facets if "L" in f.wings][0]
    assert shed.area_plan == pytest.approx(10.6 * 4.0 + 10 * 0.4, rel=1e-6)
    assert shed.hidden_from_above


def test_collinear_wings_merge_into_single_facets():
    a = Wing("A", "gable", cx=-5, azimuth=90, length=10, width=8, pitch=0.5, eave_overhang=0, rake_overhang=0)
    b = Wing("B", "gable", cx=5, azimuth=90, length=10, width=8, pitch=0.5, eave_overhang=0, rake_overhang=0)
    m = build([a, b])
    assert len(m.facets) == 2
    assert by_kind(m)["ridge"] == pytest.approx(20)
    assert m.roof_area() == pytest.approx(160 * SF)


def test_gambrel():
    w = Wing("G", "gambrel", length=10, width=8, pitch=2.0, upper_pitch=0.5, break_inset=1.0, eave_overhang=0, rake_overhang=0)
    m = build([w])
    assert len(m.facets) == 4
    expected = 10 * (2 * 1.0 * math.sqrt(1 + 4) + 2 * 3.0 * math.sqrt(1 + 0.25))
    assert m.roof_area() == pytest.approx(expected, rel=1e-6)
    assert by_kind(m)["transition"] == pytest.approx(20)


def test_walls_follow_sloped_grade():
    w = Wing("A", "gable", azimuth=90, length=10, width=8, pitch=0.5, eave_overhang=0, rake_overhang=0, eave_height=3)
    flat = build([w])
    # grade falls 1 m over the 10 m length (x from -5 to 5): linear, so the long walls keep
    # the same mean height; the low gable end gains 0.5 m x 8 m, the high end loses the same
    sl = build([w], ground=(-0.1, 0.0, 0.0))
    long_wall = [x for x in sl.walls if x.side == "-v"][0]
    assert long_wall.area_exposed == pytest.approx(30.0, rel=1e-3)
    low_end = [x for x in sl.walls if x.side == "+u"][0]   # x = +5, grade -0.5
    assert low_end.area_exposed == pytest.approx(8 * 3.5 + 8, rel=1e-3)
    assert sl.wall_area() == pytest.approx(flat.wall_area(), rel=1e-3)
    assert sl.roof_area() == pytest.approx(flat.roof_area())


def test_lopsided_gable_with_porch_overhang():
    # equal pitch, plates at different heights: ridge shifts toward the lower side's opposite
    w = Wing("M", "gable", azimuth=0, length=8, width=11, eave_height=5.0, eave_height_b=4.4, pitch=0.5,
             eave_overhang=0, eave_overhang_b=2.0, rake_overhang=0)
    m = build([w])
    assert len(m.facets) == 2
    # +v (west) plate 5.0 at v=+5.5, -v (east) plate 4.4 at v=-5.5: ridge where 5.0+0.5(5.5-v) = 4.4+0.5(v+5.5)
    ridge_v = 0.6
    z_ridge = 5.0 + 0.5 * (5.5 - ridge_v)
    assert m.max_height() == pytest.approx(z_ridge)
    plan = 8 * (11 + 2.0)
    assert m.roof_area() == pytest.approx(plan * SF, rel=1e-9)
    assert m.footprint().area == pytest.approx(88)


def test_roof_only_patch_coplanar_is_merged_not_double_counted():
    main = Wing("M", "shed", azimuth=180, cx=0, cy=0, length=10, width=6, eave_height=3.0, pitch=0.5,
                eave_overhang=0, rake_overhang=0)
    # roof-only patch continuing the same plane 4 m further north (tiny height mismatch, 1 cm)
    patch = Wing("J", "shed", azimuth=180, cx=0, cy=7, length=4, width=6, eave_height=3.01, pitch=0.5,
                 eave_overhang=0, rake_overhang=0, roof_only=True)
    m = build([main, patch])
    assert len(m.facets) == 1
    assert m.roof_area() == pytest.approx(6 * 14 * SF, rel=2e-3)
    assert len(m.walls) == 4 and m.footprint().area == pytest.approx(60)
