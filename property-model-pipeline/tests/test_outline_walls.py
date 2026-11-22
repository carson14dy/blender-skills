"""Measured (non-rectangular) roof outlines, roof openings and wall polygons on a parametric wing."""
import math

from propmodel.roofgeom import Wing, build


def _gable(**kw):
    d = dict(id="M", type="gable", cx=0, cy=0, azimuth=90, length=10, width=8, eave_height=3.0, pitch=0.5,
             eave_overhang=0.5, rake_overhang=0.3)
    d.update(kw)
    return Wing.from_dict(d)


def test_prow_outline_keeps_planes_and_classifies_edges():
    # ridge along x (y = 0); the east end is a prow: north plane stops at x = 6, south plane at a 45-degree edge
    outline = [[-5.3, -4.5], [1.5, -4.5], [6.0, 0.0], [6.0, 4.5], [-5.3, 4.5]]
    m = build([_gable(outline=outline)])
    plain = build([_gable()])
    assert len(m.facets) == 2
    assert {f.plane for f in m.facets} == {f.plane for f in plain.facets}          # same planes
    ridge = m.edge_total("ridge")
    assert abs(ridge - 11.3) < 1e-6                                                 # ridge runs to the prow tip
    kinds = {e.kind for e in m.edges}
    assert "rake" in kinds and "eave" in kinds and "hip" not in kinds
    diag = [e for e in m.edges if e.kind == "rake" and abs(e.p0[0] - e.p1[0]) > 1 and abs(e.p0[1] - e.p1[1]) > 1]
    assert len(diag) == 1                                                            # the 45-degree prow edge
    # surface_z follows the outline, not the rectangle
    assert math.isnan(m.surface_z([[4.0, -3.5]])[0]) and not math.isnan(m.surface_z([[4.0, 3.5]])[0])


def test_roof_hole_and_wall_polygon():
    hole = [[0, -2.5], [1.0, -2.5], [1.0, -1.0], [0, -1.0]]
    walls = [[-5, -4], [3, -4], [3, -1], [5, -1], [5, 4], [-5, 4]]                # notched plan
    m = build([_gable(outline_holes=[hole], walls=walls)])
    plain = build([_gable()])
    assert abs((plain.roof_area_plan() - m.roof_area_plan()) - 1.5) < 1e-6
    names = sorted(w.side for w in m.walls)
    assert names == [f"w{k}" for k in range(6)]
    assert abs(m.footprint().area - (80 - 6)) < 1e-6
    south = [w for w in m.walls if abs(w.bearing - 180) < 1 and w.length > 7]
    assert south and abs(south[0].profile[0][2] - 3.0) < 1e-6                      # plate on the -v wall line
