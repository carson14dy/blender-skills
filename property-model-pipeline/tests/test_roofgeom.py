import math
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from propmodel.roofgeom import Wing, build
from shapely.geometry import Polygon

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
    # porch shed roof dies into the taller wall: headwall flashing along the wall it meets (10 m), no wall-less
    # "headwall" in mid-air at the upper drip line; its 0.3 m rake-overhang corners run on under the upper rake
    # overhang (>= 1.6 m above them) beside the gable walls up to the shed's own high eave: step flashing there
    assert e["headwall"] == pytest.approx(10.0, abs=1e-6)
    assert e["sidewall"] == pytest.approx(2 * 0.4 * math.sqrt(1 + 0.25 ** 2), rel=1e-6)
    # shed roof area includes the strip under the upper overhang (between the walls) and the overhung corners
    shed = [f for f in m.facets if "L" in f.wings][0]
    assert shed.area_plan == pytest.approx(10.6 * 4.0 + 10 * 0.4 + 2 * 0.3 * 0.8, rel=1e-6)
    assert shed.hidden_from_above


def test_lower_roof_runs_in_under_upper_overhang_to_the_wall():
    # two-storey block H (walls y -4..4) with a deep 1.5 m south eave; a porch shed P whose walls stand 2 m off the
    # wall (y -8..-6) and whose outline runs in under the H eave into H (the roof meets the H wall at y = -4)
    hi = Wing("H", "gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=5.5, pitch=0.5,
              eave_overhang=1.5, rake_overhang=0.3)
    po = Wing("P", "shed", cx=0, cy=-7, azimuth=270, length=6, width=2, eave_height=2.6, pitch=0.25,
              outline=[[-3.3, -8.4], [3.3, -8.4], [3.3, -3.0], [-3.3, -3.0]])
    m = build([hi, po])
    p = [f for f in m.facets if f.wings == ["P"]][0]
    # kept to the wall (not stopped at the H drip line y -5.5, which left an open slot over the porch): 6.6 x 4.4
    assert p.area_plan == pytest.approx(6.6 * 4.4, rel=1e-9)
    assert p.hidden_from_above
    e = by_kind(m)
    assert e["headwall"] == pytest.approx(6.6, rel=1e-9)                       # where it meets the H wall
    assert e["rake"] == pytest.approx(2 * 4.4 * math.sqrt(1 + 0.25 ** 2) + 4 * 5.5 * SF, rel=1e-6)
    # the top view (what LiDAR sees) is unchanged: the H eave is on top over the porch roof's upper end
    z = m.surface_z([(0.0, -5.0)])[0]
    assert z == pytest.approx(5.5 - 1.0 * 0.5, abs=1e-9)


def test_cross_gable_overhangs_still_stop_at_the_valleys():
    # same pitch and plates, 0.6 m eaves / 0.4 m rakes: beyond each valley the wing's eave runs under the main eave
    # with no clearance (the roofs meet), so it is NOT kept: the facets tile the outline union exactly
    main = Wing("M", "gable", cx=0, cy=0, azimuth=90, length=12, width=8, pitch=0.5, eave_overhang=0.6, rake_overhang=0.4)
    wing = Wing("W", "gable", cx=0, cy=-5, azimuth=0, length=10, width=6, pitch=0.5, eave_overhang=0.6, rake_overhang=0.4)
    m = build([main, wing])
    from shapely.ops import unary_union
    assert sum(f.area_plan for f in m.facets) == pytest.approx(m.roof_outline().area, rel=1e-9)
    assert unary_union([f.poly for f in m.facets]).area == pytest.approx(m.roof_outline().area, rel=1e-9)
    assert not any(f.hidden_from_above for f in m.facets)
    e = by_kind(m)
    assert e["headwall"] == e["sidewall"] == 0
    assert e["valley"] > 0


def _gable_with_chimney(pens):
    # gable, ridge E-W at y = 0, plates 3.0 at y = +-4, pitch 6/12, 0.7 m rakes (outline x -6.7..6.7) and 0.5 m eaves
    w = Wing("A", "gable", cx=0, cy=0, azimuth=90, length=12, width=8, eave_height=3.0, pitch=0.5,
             eave_overhang=0.5, rake_overhang=0.7, penetrations=pens)
    return build([w])


def test_penetrations_cut_the_roof_at_a_chimney_and_its_exterior_chase():
    # an outside fireplace on the west gable wall (x = -6): shoulder x -7.2..-6.0 (a chase 0.13 m out of the wall
    # wrapped in the 0.7 m rake overhang) x y -2.5..-1.0 on the south slope, standing through the roof to z 5.5
    plain = _gable_with_chimney(None)
    stone = [[-6.13, -2.5], [-4.9, -2.5], [-4.9, -1.0], [-6.13, -1.0]]
    m = _gable_with_chimney([{"polygon": stone, "z": [-2.0, 5.5], "label": "stone chimney"}])
    hole_plan = 1.23 * 1.5
    assert m.roof_area() == pytest.approx(plain.roof_area() - hole_plan * SF, rel=1e-9)
    south = [f for f in m.facets if f.plane[1] > 0][0]                # z rises toward the ridge (+y)
    rings = [r for p in (south.poly.geoms if hasattr(south.poly, "geoms") else [south.poly]) for r in p.interiors]
    assert len(rings) == 1 and Polygon(rings[0]).area == pytest.approx(hole_plan, rel=1e-9)
    # the rake overhang outside the chase is still roof: no notch in the drip edge, eaves/rakes unchanged
    e, e0 = by_kind(m), by_kind(plain)
    for k in ("ridge", "eave", "rake", "valley", "hip"):
        assert e[k] == pytest.approx(e0[k], rel=1e-9)
    # the edges round the stone are chimney flashing: 2 horizontal (headwall) + 2 sloped (sidewall)
    assert e["headwall"] == pytest.approx(2 * 1.23, rel=1e-9)
    assert e["sidewall"] == pytest.approx(2 * 1.5 * SF, rel=1e-9)
    # nothing of the roof is left inside the stone footprint; roof heights for the fit are unchanged
    assert south.poly.intersection(Polygon(stone)).area == pytest.approx(0, abs=1e-9)
    assert m.surface_z([(-5.5, -1.7)])[0] == pytest.approx(plain.surface_z([(-5.5, -1.7)])[0])
    # serialised for Blender as a hole ring of the facet polygon
    from propmodel.roofgeom import to_mesh_json
    mj = to_mesh_json(m)
    assert sum(len(p["holes"]) for f in mj["facets"] for p in f["polygons"]) == 1
    assert mj["wings"][0]["penetrations"][0]["label"] == "stone chimney"


def test_penetration_flashing_edges_are_tagged_with_their_solid():
    # the headwall / sidewall pieces round the stone carry "WING:index" of the penetration (so the Blender side can
    # dress exactly those edges as chimney flashing); roof-to-wall junctions elsewhere stay untagged
    stone = [[-6.13, -2.5], [-4.9, -2.5], [-4.9, -1.0], [-6.13, -1.0]]
    m = _gable_with_chimney([{"polygon": stone, "z": [-2.0, 5.5], "label": "stone chimney"}])
    tagged = [e for e in m.edges if e.penetration]
    assert {e.penetration for e in tagged} == {"A:0"}
    assert {e.kind for e in tagged} == {"headwall", "sidewall"}
    assert sum(e.length for e in tagged) == pytest.approx(2 * 1.23 + 2 * 1.5 * SF, rel=1e-9)
    assert all(e.penetration is None for e in m.edges if e.kind not in ("headwall", "sidewall"))
    from propmodel.roofgeom import to_mesh_json
    mj = to_mesh_json(m)
    assert sum(1 for e in mj["edges"] if e.get("penetration") == "A:0") == len(tagged) == 4
    assert all("penetration" not in e for e in mj["edges"] if e["kind"] in ("eave", "rake", "ridge"))
    # a lower roof meeting an upper wall (no penetration) gives untagged sidewall / headwall edges
    hi = Wing("H", "gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=5.5, pitch=0.5,
              eave_overhang=0.4, rake_overhang=0.3)
    lo = Wing("L", "shed", cx=0, cy=-6, azimuth=270, length=10, width=4, eave_height=2.6, pitch=0.25,
              eave_overhang=0.4, rake_overhang=0.3)
    walls = [e for e in build([hi, lo]).edges if e.kind in ("headwall", "sidewall")]
    assert sum(e.length for e in walls) > 10 and all(e.penetration is None for e in walls)


def test_penetration_z_range_limits_the_cut():
    stone = [[-6.13, -2.5], [-4.9, -2.5], [-4.9, -1.0], [-6.13, -1.0]]
    plain = _gable_with_chimney(None)
    # a solid entirely above the roof there (z 5.5..6.0 > roof 3.75-4.5) cuts nothing
    above = _gable_with_chimney([{"polygon": stone, "z": [5.5, 6.0]}])
    assert above.roof_area() == pytest.approx(plain.roof_area(), rel=1e-12)
    # a solid topping out at z 4.0 cuts only where the roof is below 4.0 (y < -2 on the south slope)
    low = _gable_with_chimney([{"polygon": stone, "z": [None, 4.0]}])
    assert low.roof_area() == pytest.approx(plain.roof_area() - 1.23 * 0.5 * SF, rel=1e-9)
    with pytest.raises(ValueError):
        _gable_with_chimney([{"polygon": [[0, 0], [1, 0]]}])


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


def _upper_over_lower(lower_holes=None):
    # flat lower roof: walls x -5..5, y -4..4, eave overhang 1 m all round (outline x -6..6, y -5..5); an upper
    # storey (walls x -2..2, y -2..2, standing through the lower roof) whose gable rakes overhang 2.5 m north and
    # south, i.e. 0.5 m past the lower walls over the lower eave strip, and stop 0.5 m short of the lower drip edge
    lower = Wing("L", "flat", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0, pitch=0,
                 eave_overhang=1.0, outline_holes=lower_holes)
    upper = Wing("U", "gable", cx=0, cy=0, azimuth=0, length=4, width=4, eave_height=6.0, pitch=0.5,
                 eave_overhang=0.45, rake_overhang=2.5)
    m = build([lower, upper])
    return m, [f for f in m.facets if f.wings == ["L"]][0]


def test_lower_eave_under_upper_roof_is_not_opened():
    m, lo = _upper_over_lower()
    # the lower eave strips under the upper rakes (2 x 4.9 m x 0.5 m, outside every wall) are kept as roofing
    # hidden from above, not punched out as openings; the upper storey's walls still pass through the lower roof
    assert lo.area_plan == pytest.approx(12 * 10 - 16, rel=1e-9)
    assert lo.hidden_from_above
    rings = [r for p in (lo.poly.geoms if hasattr(lo.poly, "geoms") else [lo.poly]) for r in p.interiors]
    assert len(rings) == 1 and Polygon(rings[0]).area == pytest.approx(16, rel=1e-9)
    # flashing only where the lower roof meets the upper walls (no wall-less "headwall" round the eave strips)
    e = by_kind(m)
    assert e["headwall"] + e["sidewall"] == pytest.approx(16, rel=1e-6)


def test_own_outline_opening_under_upper_roof_stays_open():
    hole = [[-1.0, -4.4], [1.0, -4.4], [1.0, -4.1], [-1.0, -4.1]]     # inside the overhung eave strip
    m, lo = _upper_over_lower([hole])
    assert lo.area_plan == pytest.approx(12 * 10 - 16 - 0.6, rel=1e-9)
    rings = sorted(Polygon(r).area for p in (lo.poly.geoms if hasattr(lo.poly, "geoms") else [lo.poly]) for r in p.interiors)
    assert rings == pytest.approx([0.6, 16], rel=1e-9)
    # its edges are open roof edges of the lower roof (flat: all level -> eave), tagged with the opening
    tagged = [e for e in m.edges if e.opening]
    assert {e.opening for e in tagged} == {"L:0"} and {e.kind for e in tagged} == {"eave"}
    assert sum(e.length for e in tagged) == pytest.approx(2 * (2.0 + 0.3), rel=1e-9)


def _light_well(holes=None, lower_walls_under=True):
    # upper storey U (walls x -6..0, y -3..3, gable ridge along x at y = 0, plates 6.0, 6/12) whose 3 m east rake
    # overhang (to x = 3) reaches over a flat lower wing L (roof z 3.0, x .. 8, y -3..3) that runs in under it to the
    # U wall at x = 0: with ``lower_walls_under`` L's walls (x -2..8) stand under the overhang; otherwise they stop at
    # x 2.5 and only L's roof (outline from x -0.5) runs in under the overhang. ``holes`` = openings of U's own
    # outline (a light well in the overhang over L)
    up = Wing("U", "gable", cx=-3, cy=0, azimuth=90, length=6, width=6, eave_height=6.0, pitch=0.5,
              eave_overhang=0.5, rake_overhang=3.0, outline_holes=holes)
    if lower_walls_under:
        lo = Wing("L", "flat", cx=3, cy=0, azimuth=90, length=10, width=6, eave_height=3.0, pitch=0,
                  eave_overhang=0, rake_overhang=0)
    else:
        lo = Wing("L", "flat", cx=5.25, cy=0, azimuth=90, length=5.5, width=6, eave_height=3.0, pitch=0,
                  outline=[[-0.5, -3.0], [8.0, -3.0], [8.0, 3.0], [-0.5, 3.0]])
    return build([up, lo])


@pytest.mark.parametrize("lower_walls_under", [True, False])
def test_opening_in_an_upper_overhang_over_a_lower_roof_stays_open(lower_walls_under):
    # an open bay in the upper roof's overhang, 2.25-3.25 m above the lower roof that runs on under the overhang:
    # being over a kept (hidden) lower roof must not refill it (the overhung-pocket rule only refills holes made by
    # the visibility test, inside or outside the lower walls), and the lower roof under it stays whole (now partly
    # seen from above, not double counted)
    well = [[1.0, 0.5], [2.0, 0.5], [2.0, 1.5], [1.0, 1.5]]          # north slope, 1 x 1 m plan
    plain, m = _light_well(None, lower_walls_under), _light_well([well], lower_walls_under)
    assert m.roof_area() == pytest.approx(plain.roof_area() - 1.0 * SF, rel=1e-9)
    north = [f for f in m.facets if f.wings == ["U"] and f.plane[1] < 0][0]      # z falls toward +y
    rings = [r for p in (north.poly.geoms if hasattr(north.poly, "geoms") else [north.poly]) for r in p.interiors]
    assert len(rings) == 1 and Polygon(rings[0]).area == pytest.approx(1.0, rel=1e-9)
    lo, lo0 = ([f for f in x.facets if f.wings == ["L"]][0] for x in (m, plain))
    assert lo.area_plan == pytest.approx(lo0.area_plan, rel=1e-12) == pytest.approx(8 * 6, rel=1e-9)
    assert lo.hidden_from_above and lo.poly.equals(lo0.poly)
    # the opening's edges are open roof edges (drip edge): 2 level ones (eave) + 2 sloped ones (rake); no flashing
    e, e0 = by_kind(m), by_kind(plain)
    assert e["eave"] - e0["eave"] == pytest.approx(2 * 1.0, rel=1e-9)
    assert e["rake"] - e0["rake"] == pytest.approx(2 * 1.0 * SF, rel=1e-9)
    for k in ("ridge", "hip", "valley", "headwall", "sidewall", "transition"):
        assert e[k] == pytest.approx(e0[k], rel=1e-9, abs=1e-12)
    assert e["headwall"] == pytest.approx(6.0, rel=1e-9)                # L meets the U wall at x = 0, as before
    # ... tagged with the opening, so a takeoff can list them apart; every other edge is untagged
    tagged = [x for x in m.edges if x.opening]
    assert {x.opening for x in tagged} == {"U:0"} and {x.kind for x in tagged} == {"eave", "rake"}
    assert sum(x.length for x in tagged) == pytest.approx(2 * 1.0 + 2 * 1.0 * SF, rel=1e-9)
    assert all(x.opening is None for x in plain.edges)
    # the top surface there is the lower roof; elsewhere under the overhang it is still the upper roof
    assert m.surface_z([(1.5, 1.0)])[0] == pytest.approx(3.0, abs=1e-9)
    assert m.surface_z([(1.5, 2.0)])[0] == pytest.approx(plain.surface_z([(1.5, 2.0)])[0], abs=1e-9)
    from propmodel.roofgeom import to_mesh_json
    mj = to_mesh_json(m)
    assert sum(1 for x in mj["edges"] if x.get("opening") == "U:0") == len(tagged) == 4
    assert all("opening" not in x for x in to_mesh_json(plain)["edges"])
