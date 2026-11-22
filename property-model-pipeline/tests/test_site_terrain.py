"""Hillside site terrain: median ground cells, solid-surface rock merge, breaklines, pads, apron, curbs."""
import importlib.util
import os

import numpy as np
from shapely.geometry import Polygon, LineString
import shapely

from propmodel import lidar

_spec = importlib.util.spec_from_file_location(
    "build_site", os.path.join(os.path.dirname(__file__), "..", "scripts", "build_site.py"))
build_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_site)


def _pts(rng, x0, x1, y0, y1, step, zf, nret=1, noise=0.03):
    xs, ys = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    x = xs.ravel() + rng.uniform(-step / 3, step / 3, xs.size)
    y = ys.ravel() + rng.uniform(-step / 3, step / 3, xs.size)
    z = zf(x, y) + rng.normal(0, noise, x.size)
    one = np.ones_like(x)
    return np.column_stack([x, y, z, one, nret * one, nret * one])     # last return of an n-return pulse


def test_median_ground_cells_remove_the_low_bias_of_the_minimum():
    rng = np.random.default_rng(3)
    slope = lambda x, y: 0.5 * y                                       # steep lot: 50 % grade
    pts = _pts(rng, -10, 10, -10, 10, 0.17, slope, noise=0.04)       # ~35 returns / m2 (QL1-like)
    q = (np.arange(-6, 6.01, 0.5),) * 2
    X, Y = np.meshgrid(*q)
    bias = {}
    for stat in ("min", "median"):
        surf = lidar.ground_surface(pts, cell=0.5, zstat=stat)
        bias[stat] = float(np.median(lidar.surface_z(surf, X.ravel(), Y.ravel()) - slope(X.ravel(), Y.ravel())))
    assert bias["min"] < -0.08                    # the lowest return of a sloping cell sits low
    assert abs(bias["median"]) < 0.04


def test_solid_surface_keeps_a_boulder_and_drops_canopy():
    rng = np.random.default_rng(4)
    ground = lambda x, y: 0.2 * y
    # a 3.5 m tall, ~3 m wide boulder with steep flanks: taller than the filter's height tolerance
    rock = lambda x, y: ground(x, y) + 3.5 * np.clip((1.6 - np.hypot(x - 3, y)) / 0.3, 0, 1)
    pts = [_pts(rng, -8, 8, -8, 8, 0.18, rock)]
    # a tree west of the boulder: canopy first returns + ground last returns of 2-return pulses
    tree = _pts(rng, -6, -3, -2, 1, 0.18, lambda x, y: ground(x, y) + 4.0, nret=2)
    tree[:, 4] = 1
    pts.append(tree)
    pts.append(_pts(rng, -6, -3, -2, 1, 0.18, ground, nret=2))
    P = np.vstack(pts)
    c, x0, y0, n = 0.25, -8.0, -8.0, 64
    sol = lidar.solid_surface(P, x0, y0, n, n, cell=c)
    surf = lidar.ground_surface(P, cell=0.5)
    xs = x0 + c * (np.arange(n) + 0.5)
    X, Y = np.meshgrid(xs, xs)
    Zg = lidar.surface_z(surf, X.ravel(), Y.ravel()).reshape(X.shape)
    Z, acc = lidar.merge_solid(Zg, sol["Z"], c)
    i, j = int((3 - x0) / c), int((0 - y0) / c)
    assert abs(Z[j, i] - rock(3.0, 0.0)) < 0.25                     # boulder top kept at its height
    assert Zg[j, i] < rock(3.0, 0.0) - 2.0                           # (the ground filter alone shaves it)
    ti, tj = int((-4.5 - x0) / c), int((-0.5 - y0) / c)
    assert abs(Z[tj, ti] - ground(-4.5, -0.5)) < 0.2                 # no canopy in the terrain
    # a lone tall solid cell (a post) is not a boulder
    Zs = np.full_like(Zg, np.nan); Zs[5, 5] = Zg[5, 5] + 1.6
    Z2, _ = lidar.merge_solid(Zg, Zs, c)
    assert Z2[5, 5] == Zg[5, 5]


def test_breaklines_step_inside_the_wall_and_pads_level():
    c = 0.25
    xs = np.arange(-5, 5.001, c); ys = np.arange(-5, 5.001, c)
    X, Y = np.meshgrid(xs, ys)
    Z = np.where(Y > 0, 1.0, 0.0) + 0.0 * X                         # 1 m step along y = 0 ...
    Z = Z + np.clip(Y, -0.5, 0.5) * 0                                 # (kept sharp)
    from scipy.ndimage import uniform_filter
    Zs = uniform_filter(Z, 5)                                         # ... smeared over ~1 m like a filtered DEM
    walls = build_site.wall_lines({"items": [{"kind": "retaining_wall", "line": [[-4, 0], [4, 0]], "thickness": 0.3},
                                             {"kind": "boulder", "polygon": [[0, 0], [1, 0], [1, 1]]}]})
    assert len(walls) == 1
    node = [X.copy(), Y.copy()]
    Zb = build_site.apply_breaklines(Zs.copy(), xs, ys, walls, c, snap=node)
    moved = np.hypot(node[0] - X, node[1] - Y) > 1e-9
    assert np.allclose(np.abs(node[1][moved]), 0.15)                 # snapped nodes sit on the two wall faces
    assert not moved[np.abs(Y) > 0.15 + c].any()
    j_up, j_lo = np.searchsorted(ys, 0.25), np.searchsorted(ys, -0.25)
    i = np.searchsorted(xs, 0.0)
    assert Zb[j_up, i] > 0.95 and Zb[j_lo, i] < 0.05               # nodes beside the wall take their own grade
    assert abs(Zb[np.searchsorted(ys, 3.0), i] - Zs[np.searchsorted(ys, 3.0), i]) < 1e-9   # far nodes untouched
    pads = build_site.grade_pads({"items": [{"kind": "grade_pad", "polygon": [[0, 0], [1, 0], [1, 1]], "z": 2.0},
                                            {"kind": "retaining_wall", "line": [[0, 0], [1, 1]]}]})
    assert len(pads) == 1 and pads[0]["z"] == 2.0


def test_apron_meets_the_garage_front():
    drive = Polygon([(0, -10), (4, -10), (4, -1.5), (0, -1.0)])      # traced short of the door
    front = [[-0.5, 0.0], [4.5, 0.0]]
    out = build_site.align_apron(drive, front)
    assert abs(out.bounds[3] - 0.0) < 1e-6                           # top edge now on the front line
    over = build_site.align_apron(Polygon([(0, -10), (4, -10), (4, 1.0), (0, 1.0)]), front)
    assert over.bounds[3] <= 1e-6                                    # nothing under the garage
    assert abs(over.bounds[1] + 10) < 1e-6                           # rest of the driveway untouched


def test_merge_solid_grows_a_box_boulder_back_to_its_edges():
    """A 3 m box boulder: the planar-window test fails within ~radius of its edges, so the accepted patch
    comes out shrunk; the edge growth brings it back to within one cell of the true footprint."""
    rng = np.random.default_rng(7)
    ground = lambda x, y: 0.1 * y
    box = lambda x, y: (np.abs(x - 1.0) <= 1.5) & (np.abs(y) <= 1.5)
    rock = lambda x, y: ground(x, y) + np.where(box(x, y), 2.0, 0.0)
    P = _pts(rng, -8, 8, -8, 8, 0.15, rock, noise=0.02)
    c, x0, y0, n = 0.25, -8.0, -8.0, 64
    sol = lidar.solid_surface(P, x0, y0, n, n, cell=c, radius=0.6)
    xs = x0 + c * (np.arange(n) + 0.5)
    X, Y = np.meshgrid(xs, xs)
    Zg = ground(X, Y)
    truth = box(X, Y)
    inner = (np.abs(X - 1.0) <= 1.5 - c) & (np.abs(Y) <= 1.5 - c)          # one cell inside the edge
    outer = (np.abs(X - 1.0) <= 1.5 + c) & (np.abs(Y) <= 1.5 + c)          # one cell outside
    Z0, _ = lidar.merge_solid(Zg, sol["Z"], c)
    high0 = (Z0 - Zg) > 1.0
    assert (inner & ~high0).sum() > 5                                      # without growth: shrunk
    Z1, acc = lidar.merge_solid(Zg, sol["Z"], c, grow=sol, grow_iter=int(np.ceil(0.6 / c)) + 1)
    high = (Z1 - Zg) > 1.0
    assert not (inner & ~high).any()                                       # every cell a cell inside the edge
    assert not (high & ~outer).any()                                       # nothing more than a cell outside
    assert abs(high.sum() - truth.sum()) <= 0.25 * truth.sum()
    # a masked cell is never grown into
    mask = np.zeros_like(truth); mask[:, : int((0.0 - x0) / c)] = True     # x < 0 masked
    Z2, _ = lidar.merge_solid(Zg, np.where(mask, np.nan, sol["Z"]), c, grow=sol, grow_iter=4, mask=mask)
    assert not (((Z2 - Zg) > 1.0) & mask).any()


def test_despike_caps_single_spikes_and_keeps_cliffs():
    Z = np.zeros((20, 20)); Z[:, 10:] = 3.0                                # a 3 m cliff
    Z[5, 4] = 1.2                                                         # a one-node spike on the low side
    nodes = np.ones_like(Z, bool)
    D = lidar.despike(Z, nodes, 0.25, above=0.3, sigma=0.25, max_change=0.05)
    assert D[5, 4] <= 0.35                                                # spike capped to median + 0.3 (+ blur)
    assert np.allclose(D[:, 12:], 3.0, atol=0.06) and np.allclose(D[:, 10], 3.0, atol=0.06)   # cliff edge kept
    q = lidar.cell_quantile(np.array([0, 0, 0, 0, 1]), np.array([0, 0, 0, 0, 0]), np.array([1.0, 2.0, 3.0, 4.0, 7.0]), 2, 1, 0.9)
    assert abs(q[0, 0] - 3.7) < 1e-9 and q[0, 1] == 7.0


def test_face_walls_extrude_to_the_uphill_side():
    item = {"kind": "retaining_wall", "line": [[-4, 0], [4, 0]], "thickness": 0.4, "line_is": "face"}
    up_north = lambda x, y: 1.0 if y > 0 else 0.0
    (line, th), = build_site.wall_lines({"items": [item]}, zfun=up_north)
    assert th == 0.4 and np.allclose(np.array(line)[:, 1], 0.2)           # centre 0.2 m uphill (north) of the face
    (line, _), = build_site.wall_lines({"items": [dict(item, uphill="right")]})
    assert np.allclose(np.array(line)[:, 1], -0.2)                        # explicit side wins (right of +x = south)
    (line, _), = build_site.wall_lines({"items": [dict(item, line_is="centre")]})
    assert np.allclose(np.array(line)[:, 1], 0.0)
    # mitred corner: both legs stay parallel to the face at half a thickness
    bent = build_site.offset_line([[0, 0], [4, 0], [4, 4]], 0.2)
    assert np.allclose(bent[1], [3.8, 0.2]) and np.allclose(bent[2], [3.8, 4.0])
    pads_rock = build_site.rock_outlines({"rocks": [{"geoms": [[[0, 0], [1, 0], [1, 1]]], "props": {"top_z": 2.0}}]},
                                         {"items": [{"kind": "boulder", "polygon": [[2, 2], [3, 2], [3, 3]], "top_z": 1.0},
                                                    {"kind": "retaining_wall", "line": [[0, 0], [1, 1]]}]})
    assert [t for _, t in pads_rock] == [2.0, 1.0]


def test_overlays_lie_on_the_terrain_triangles():
    """A twisted (non-planar) cell: the drape must follow the mesh's own two triangles, not a bilinear patch."""
    xs = np.arange(0, 1.001, 0.5); X, Y = np.meshgrid(xs, xs)
    Z = np.zeros_like(X); Z[1, 1] = 0.4; Z[0, 1] = -0.2                    # rough cell corners
    geom = Polygon([(0.1, 0.1), (0.9, 0.15), (0.8, 0.9), (0.2, 0.7)])
    v, t = build_site.drape_on_mesh(geom, X, Y, Z, 0.02)
    v = np.array(v)
    assert len(t) and abs(sum(Polygon(v[tri, :2]).area for tri in t) - geom.area) < 1e-6
    for x, y, z in v:                                                     # z = the mesh triangle's plane + lift
        i, j = min(int(x / 0.5), 1), min(int(y / 0.5), 1)
        fx, fy = x / 0.5 - i, y / 0.5 - j
        z00, z10, z11, z01 = Z[j, i], Z[j, i + 1], Z[j + 1, i + 1], Z[j + 1, i]
        zt = z00 + fx * (z10 - z00) + fy * (z11 - z10) if fx >= fy else z00 + fy * (z01 - z00) + fx * (z11 - z01)
        assert abs(z - 0.02 - zt) < 1e-3
    for tri in t:                                                         # counter-clockwise: normals up
        (x0, y0), (x1, y1), (x2, y2) = v[tri, :2]
        assert (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) > 0


def test_despike_edge_nodes_take_the_full_blur():
    Z = np.zeros((20, 20)); Z[5:15, 5:15] = 2.0                           # a 2 m block
    nodes = Z > 1.0
    keep = lidar.despike(Z, nodes, 0.25, max_change=0.05)
    assert np.allclose(keep[5:15, 6:14], 2.0, atol=0.051)                  # clamped: the block keeps its edges
    assert keep[5, 5] < 0.5                                                 # (a one-node corner is a spike to the median)
    from scipy.ndimage import binary_dilation
    outline = nodes & binary_dilation(~nodes, np.ones((3, 3)))
    soft = lidar.despike(Z, nodes, 0.25, max_change=0.05, edge_nodes=outline)
    assert soft[5, 10] < 1.6 and abs(soft[10, 10] - 2.0) < 0.06             # only the outline is rounded


def test_cells_fold_along_the_more_level_diagonal_and_drapes_follow():
    """A ridge along the (j,i+1)-(j+1,i) diagonal: the cell is folded along it, the quad is written so its own
    0-2 diagonal is that fold, and a drape over the cell lies on those two triangles, wound normal-up."""
    xs = np.arange(0, 1.001, 0.5); X, Y = np.meshgrid(xs, xs)
    Z = np.zeros_like(X); Z[0, 1] = 0.6; Z[1, 0] = 0.6; Z[1, 1] = 0.6        # cell (0,0): ridge on its 1-3 diagonal
    alt = build_site.split_diagonals(Z)
    assert alt[0, 0]
    nx = X.shape[1]
    f = build_site.quad_face(0, 0, nx, True)
    flat = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    assert {f[0], f[2]} == {1, nx}                                          # the fold is the face's 0-2 diagonal
    q = flat[f, :2]
    assert Polygon(q).exterior.is_ccw                                       # still counter-clockwise from above
    # a node pulled off the grid (snapped onto a wall face) must not flip a triangle
    NX = X.copy(); NX[1, 1] = 0.98
    geom = Polygon([(0.05, 0.05), (0.95, 0.05), (0.95, 0.95), (0.05, 0.95)])
    v, t = build_site.drape_on_mesh(geom, NX, Y, Z, 0.02, alt=alt)
    v = np.array(v)
    assert len(t) and abs(sum(Polygon(v[tri, :2]).area for tri in t) - geom.area) < 1e-6
    for tri in t:                                                           # every overlay triangle: +z winding
        (x0, y0), (x1, y1), (x2, y2) = v[tri, :2]
        assert (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) > 0
    for x, y, z in v:                                                       # cell (0,0) folded on its ridge: plane z
        if x < 0.5 and y < 0.5:
            fx, fy = x / 0.5, y / 0.5
            zt = 0.6 * (fx + fy) if fx + fy <= 1 else 0.6
            assert abs(z - 0.02 - zt) < 1e-3


def test_ground_stays_under_a_cantilevered_storey():
    """Cells inside a raised wing (an upper storey on another one) whose base is far above the grade there keep
    their terrain (the overhang); cells inside a wing standing on the ground are dropped, whatever the fill."""
    xs = np.arange(-4, 4.001, 0.25); X, Y = np.meshgrid(xs, xs)
    Z = np.where(Y < 0, -3.0, 0.0)                                   # ground drops 3 m south of y = 0
    fx = ((X[:-1, :-1] + X[1:, 1:]) / 2).ravel(); fy = ((Y[:-1, :-1] + Y[1:, 1:]) / 2).ravel()
    lower = {"id": "L", "walls": [[-3, 0], [3, 0], [3, 3], [-3, 3]], "base_z": 1.5}     # fill inside it lower: still dropped
    upper = {"id": "M", "walls": [[-3, -2], [3, -2], [3, 3], [-3, 3]], "base_z": 2.3}
    keep = build_site.standing_cells([lower, upper], [], Z, fx, fy, 0.25, raised={"M"})
    assert keep[(fy > 0.3) & (fy < 2.7) & (np.abs(fx) < 2.5)].all()      # inside the lower storey: dropped
    assert not keep[(fy < -0.3) & (fy > -1.7) & (np.abs(fx) < 2.5)].any()   # under the overhang: ground stays
    extra = [Polygon([(-1, -2), (1, -2), (1, -1), (-1, -1)])]          # a --house-extra garage there: dropped
    keep2 = build_site.standing_cells([lower, upper], extra, Z, fx, fy, 0.25, raised={"M"})
    assert build_site.standing_cells([lower, upper], [], Z, fx, fy, 0.25)[(fy < -0.3) & (fy > -1.7) & (np.abs(fx) < 2.5)].all()
    assert keep2[(fy < -1.2) & (fy > -1.8) & (np.abs(fx) < 0.7)].all()


def test_clamp_spikes_removes_a_lone_spike_everywhere_and_keeps_a_box_boulder():
    """The final despike acts on every node (not only rock-raised ones): a +0.8 m single-node spike on a sloping
    lawn is cut to within 0.1 m of its highest neighbour; a 3 m box boulder (rock nodes, measured floor) keeps its
    footprint within one cell and its top height."""
    c = 0.25
    X, Y = np.meshgrid(np.arange(40) * c, np.arange(40) * c)
    slope = 0.3 * Y
    Z = slope.copy(); Z[10, 12] += 0.8                                    # lone spike on the slope (not rock)
    box = (np.abs(X - 6.5) <= 1.5) & (np.abs(Y - 6.5) <= 1.5)
    Z = np.where(box, slope + 2.0, Z)
    rock = box.copy()
    floor = np.where(box, slope + 2.0 - 0.1, np.nan)                       # each cell's measured height - 0.1
    D, rk = lidar.clamp_spikes(Z, c, rock=rock, floor=floor, peak=0.1, bump=0.4, ring=1)
    nb = [D[10 + dj, 12 + di] for dj in (-1, 0, 1) for di in (-1, 0, 1) if dj or di]
    assert D[10, 12] - max(nb) <= 0.1 + 1e-9 and D[10, 12] - slope[10, 12] < 0.2
    from scipy.ndimage import binary_dilation, binary_erosion
    high = (D - slope) > 1.0
    assert not (binary_erosion(box, np.ones((3, 3))) & ~high).any()        # footprint kept to one cell inside ...
    assert not (high & ~binary_dilation(box, np.ones((3, 3)))).any()       # ... and one cell outside
    inner = binary_erosion(box, np.ones((3, 3)), iterations=2)
    assert np.all(D[inner] - slope[inner] >= 1.9 - 1e-9)                   # measured top kept (floor)
    # pits inside rock (a no-return cell at ground level) are lifted to the 3x3 median - 0.3 and smoothed
    Zp = Z.copy(); Zp[26, 26] = slope[26, 26]
    Dp, _ = lidar.clamp_spikes(Zp, c, rock=box & ~((X == X[26, 26]) & (Y == Y[26, 26])), floor=floor)
    assert Dp[26, 26] - slope[26, 26] > 1.5
    # skipped nodes (breakline bands, pads) are never touched
    skip = np.zeros_like(box); skip[10, 12] = True
    Ds, _ = lidar.clamp_spikes(Z, c, skip=skip)
    assert Ds[10, 12] == Z[10, 12]


def test_veg_floor_cuts_shrub_tops_to_the_ground_envelope():
    c = 0.25
    X, Y = np.meshgrid(np.arange(40) * c, np.arange(40) * c)
    ground = -0.4 * Y
    shrub = (np.abs(X - 5.0) <= 0.5) & (Y > 2) & (Y < 8)                 # 1 m wide, 1.2 m tall juniper row
    Z = ground + np.where(shrub, 1.2, 0.0)
    mask = (X > 3) & (X < 7) & (Y > 1.5) & (Y < 8.5)                        # a bed (away from the grid border)
    V = lidar.veg_floor(Z, mask, c, window=2.0, dh=0.1)
    assert np.all(np.abs(V[shrub] - ground[shrub]) <= 0.1 + 1e-9)        # shrub tops gone, slope kept
    assert np.allclose(V[~mask], Z[~mask])                                 # outside the mask untouched
    assert np.allclose(V[mask & ~shrub], Z[mask & ~shrub])


def test_ground_surface_despike_drops_an_isolated_shrub_cell():
    """A dense shrub returns single pulses from its top; the morphological windows accept a 0.5 m, 1 m tall shrub
    as ground and the TIN puts a pyramid on the slope. despike drops isolated high ground cells."""
    rng = np.random.default_rng(11)
    slope = lambda x, y: 0.5 * y
    pts = _pts(rng, -6, 6, -6, 6, 0.17, slope, noise=0.02)
    x0, y0 = pts[:, 0].min(), pts[:, 1].min()                              # the filter's 0.5 m cells start here
    sx, sy = x0 + 12 * 0.5, y0 + 12 * 0.5
    shrub = (pts[:, 0] >= sx) & (pts[:, 0] < sx + 0.5) & (pts[:, 1] >= sy) & (pts[:, 1] < sy + 0.5)
    pts[shrub, 2] += 1.0                                                   # one cell of dense shrub, 1 m tall
    q = np.array([sx + 0.25]), np.array([sy + 0.25])
    plain = lidar.ground_surface(pts, cell=0.5, zstat="median")
    clean = lidar.ground_surface(pts, cell=0.5, zstat="median", despike=0.3)
    assert lidar.surface_z(plain, *q)[0] - slope(*q)[0] > 0.5             # the shrub is "ground" without it
    assert abs(lidar.surface_z(clean, *q)[0] - slope(*q)[0]) < 0.15
    far = np.array([sx - 3.0, sx + 3.0, sx + 2.0]), np.array([sy - 2.0, sy + 2.5, sy - 4.0])
    assert np.allclose(lidar.surface_z(clean, *far), lidar.surface_z(plain, *far), atol=1e-6)


def test_bed_entries_accept_labelled_no_solid_beds():
    data = [[[0, 0], [1, 0], [1, 1]], {"polygon": [[2, 2], [4, 2], [4, 4], [2, 4]], "label": "bed; shrubs", "no_solid": True},
            {"polygon": [[5, 5], [6, 5], [6, 6]], "label": "mulch"}]
    polys, veg = build_site.bed_entries(data)
    assert len(polys) == 3 and len(veg) == 1 and abs(veg[0].area - 4.0) < 1e-9


def test_bed_entries_overlay_false_is_a_vegetation_mask_only():
    data = [{"polygon": [[0, 0], [2, 0], [2, 2], [0, 2]], "no_solid": True},
            {"polygon": [[0, 0], [3, 0], [3, 3], [0, 3]], "no_solid": True, "overlay": False}]
    polys, veg = build_site.bed_entries(data)
    assert len(polys) == 1 and abs(polys[0].area - 4.0) < 1e-9 and len(veg) == 2


def test_paving_humps_drop_a_parked_car_and_keep_the_street_and_its_bank():
    """A 4.5 x 1.8 m car, 1.3 m tall, parked on a 2 % street: its returns stand on the street, so the morphological
    ground filter (dh >= 0.3 + 0.6 * 1.5 m) takes it as a 1.3 m asphalt mound. paving_humps drops every return on the
    car and keeps the street and a 1 m bank the street outline laps onto; the ground under the car is then bridged
    at the street height."""
    rng = np.random.default_rng(21)
    road = lambda x, y: 0.02 * x
    street = Polygon([(-10, -5), (10, -5), (10, 4), (-10, 4)])
    bank = lambda x, y: road(x, y) + np.clip((y - 2.5) / 2.0, 0, 1) * 1.0       # rises 1 m from y 2.5 to 4.5
    pts = _pts(rng, -12, 12, -7, 6, 0.18, bank, noise=0.02)
    car = (np.abs(pts[:, 0] - 1.0) <= 2.25) & (np.abs(pts[:, 1] + 1.0) <= 0.9)
    pts[car, 2] = road(pts[car, 0], pts[car, 1]) + 1.3                           # a flat car roof (no ground under it)
    drop = lidar.paving_humps(pts, street, above=0.3, window=3.0)
    assert drop[car].all()
    assert drop[~car].sum() == 0                                                  # street and bank all kept
    plain = lidar.ground_surface(pts, cell=0.5, zstat="median")
    clean = lidar.ground_surface(pts[~drop], cell=0.5, zstat="median")
    q = np.array([1.0]), np.array([-1.0])
    assert lidar.surface_z(plain, *q)[0] - road(*q)[0] > 1.0                      # the car is "ground" without it
    assert abs(lidar.surface_z(clean, *q)[0] - road(*q)[0]) < 0.1


def test_street_bank_takes_the_lapped_bank_out_of_the_street():
    c = 0.25
    X, Y = np.meshgrid(np.arange(-10, 10.001, c), np.arange(-6, 6.001, c))
    Z = 0.03 * X + np.clip((Y - 2.0) / 2.0, 0, 1) * 1.5                          # road + a bank from y 2 (1.5 m by y 4)
    street = Polygon([(-8, -4), (8, -4), (8, 4), (-8, 4)])                        # traced 2 m onto the bank
    bank = build_site.street_bank(street, X, Y, Z, c, rise=0.4)
    assert not bank.is_empty
    kept = street.difference(bank)
    assert kept.bounds[3] < 2.0 + 0.4 / 0.75 + c + 1e-6                          # asphalt ends at the bank foot
    assert abs(kept.intersection(Polygon([(-8, -4), (8, -4), (8, 2), (-8, 2)])).area - 16 * 6) < 1e-6   # road kept
    kerb = Polygon([(-8, 1), (8, 1), (8, 5), (-8, 5)])
    assert build_site.street_bank(street, X, Y, Z, c, rise=0.4, keep=kerb).is_empty   # a kerbed edge is left alone


def test_clamp_unsupported_lowers_an_unmeasured_crest_and_keeps_a_measured_one():
    """A one-node crest line is its own 3x3 median, so the median clamp cannot see it. clamp_unsupported lowers it to
    the mean of its 8 neighbours + 0.3 where no LiDAR return supports its height, and keeps a crest the returns show."""
    c = 0.25
    X, Y = np.meshgrid(np.arange(40) * c, np.arange(40) * c)
    Z = 0.2 * Y
    Z[10, 5:30] += 1.0                                                            # unmeasured crest line (TIN fold)
    Z[30, 5:30] += 1.0                                                            # measured crest (a kerb top)
    xs, ys = X[30, 5:30], Y[30, 5:30]
    pxy = np.column_stack([np.r_[X.ravel(), xs], np.r_[Y.ravel(), ys]])
    pz = np.r_[(0.2 * Y).ravel(), Z[30, 5:30]]
    free = np.ones(Z.shape, bool)
    D, n = lidar.clamp_unsupported(Z, c, free, pxy, pz, above=0.3, bump=None)
    assert n >= 20 and np.all(D[10, 6:29] - 0.2 * Y[10, 6:29] < 0.75)            # crest cut down ...
    assert np.allclose(D[30, 5:30], Z[30, 5:30])                                  # ... the measured one kept
    skip = np.zeros(Z.shape, bool); skip[10, :] = True
    D2, _ = lidar.clamp_unsupported(Z, c, ~skip, pxy, pz, above=0.3, bump=None)
    assert np.allclose(D2[10], Z[10])                                             # skipped nodes untouched


def _wall_scene(c=0.25, half=3.0, blend=0.5):
    """A 1 m retaining wall (face along y = 0, uphill north, 0.25 m thick) on a grid whose surface smears the step
    over ~`blend` m (a grade pad's blend reaching across the wall), plus LiDAR last returns of the true two levels."""
    xs = np.arange(-half, half + 1e-9, c); ys = np.arange(-half, half + 1e-9, c)
    X, Y = np.meshgrid(xs, ys)
    true = lambda x, y: np.where(y > 0, 0.0, -1.0)
    Z = np.clip(Y / blend + 0.5, 0, 1) - 1.0                     # 0 north of y = blend/2, -1 south of -blend/2
    rng = np.random.default_rng(5)
    px = rng.uniform(-half - 0.2, half + 0.2, 4000); py = rng.uniform(-half - 0.2, half + 0.2, 4000)
    item = {"kind": "retaining_wall", "line": [[-half - 1, 0.0], [half + 1, 0.0]], "thickness": 0.25, "top_z": 0.1,
            "line_is": "face", "uphill": "left"}
    return xs, ys, X, Y, Z, px, py, true(px, py) + rng.normal(0, 0.02, px.size), item


def test_wall_foot_nodes_drop_to_the_lower_level():
    c = 0.25
    xs, ys, X, Y, Z, px, py, pz, item = _wall_scene(c)
    walls = build_site.wall_lines({"items": [item]})
    faces = build_site.wall_faces({"items": [item]})
    assert faces[0][1] == -1                                      # downhill = right of the +x line (south)
    node = [X.copy(), Y.copy()]
    Zb = build_site.apply_breaklines(Z.copy(), xs, ys, walls, c, snap=node)
    low = build_site.cell_lowest(np.column_stack([px, py]), pz, xs[0], ys[0], c, Z.shape)
    Zf, foot = build_site.wall_foot_lower(Zb, node[0], node[1], faces, low, xs[0], ys[0], c, walls=walls)
    down = (node[1] <= 1e-6) & (node[1] >= -1.0)
    assert foot[down & (node[1] > -0.5)].all() and not foot[node[1] > 1e-6].any()
    assert (Zf[down] - (-1.0)).max() < 0.15                        # no foot node stands up on the lower level
    assert np.all(Zf <= Zb + 1e-12)                                # never raises
    assert np.allclose(Zf[Y > 0.5], Zb[Y > 0.5])                   # the upper level is left alone


def test_overlay_lapping_over_a_wall_face_stays_on_the_lower_level():
    c = 0.25
    xs, ys, X, Y, Z, px, py, pz, item = _wall_scene(c, blend=0.75)
    item = dict(item, thickness=0.06)                              # a thin edge: the 0.1 m lap reaches past its back
    walls = build_site.wall_lines({"items": [item]})
    faces = build_site.wall_faces({"items": [item]})
    node = [X.copy(), Y.copy()]
    Zb = build_site.apply_breaklines(Z.copy(), xs, ys, walls, c, snap=node)
    # a paving polygon traced 0.1 m over the face (and running past the wall's end region)
    pave = Polygon([(-2.0, -1.5), (2.0, -1.5), (2.0, 0.1), (-2.0, 0.1)])
    wallpoly = shapely.unary_union([LineString(l_).buffer(th / 2, cap_style="flat") for l_, th in walls])
    trimmed = pave.difference(shapely.unary_union([wallpoly, build_site.uphill_strips(faces, 0.15)]))
    assert trimmed.bounds[3] <= 1e-9                               # cut back to the face
    v, t = build_site.drape_on_mesh(trimmed, node[0], node[1], Zb, 0.0, alt=build_site.split_diagonals(Zb))
    v = np.array(v)
    assert len(t) and v[:, 2].max() < -1.0 + 0.1                    # nothing climbs the wall
    # (untrimmed, the lap is draped on the upper level's triangles)
    v0, _ = build_site.drape_on_mesh(pave.difference(wallpoly), node[0], node[1], Zb, 0.0)
    assert np.array(v0)[:, 2].max() > -0.5


def test_deck_cap_keeps_the_terrain_under_the_boards():
    """A deck excluded from the ground filter is bridged from the hill around it: on a 30 % slope the bridge runs through
    the boards. The cap leaves no node inside the deck above top - 0.3, only lowers, and fades out within the blend."""
    c = 0.25
    xs = ys = np.arange(-6, 6.001, c)
    X, Y = np.meshgrid(xs, ys)
    Z = 0.3 * Y + 1.0                                              # 30 % slope rising north, z 1.0 at y 0
    deck = {"decks": [{"polygon": [[-2, -1], [2, -1], [2, 2], [-2, 2]], "top_z": 0.9}]}
    caps = build_site.deck_caps(deck)
    Zc, low = build_site.cap_terrain(Z, X, Y, caps, blend=0.3)
    inside = shapely.contains_xy(Polygon(deck["decks"][0]["polygon"]), X, Y) | (
        (np.abs(X) <= 2 + 1e-9) & (Y >= -1 - 1e-9) & (Y <= 2 + 1e-9))
    assert Zc[inside].max() <= 0.9 - 0.3 + 1e-9                   # nothing within 0.3 m of the boards
    assert np.all(Zc <= Z + 1e-12)                                 # never raises
    far = shapely.distance(Polygon(deck["decks"][0]["polygon"]), shapely.points(X.ravel(), Y.ravel())).reshape(X.shape) > 0.3
    assert np.allclose(Zc[far], Z[far])                            # untouched beyond the blend
    assert low[inside & (Z > 0.65)].all() and not low[far].any()
    # nodes in `skip` (e.g. a wall's breakline band) are capped inside the polygon only, never by the outside blend
    skip = np.ones(X.shape, bool)
    Zs, _ = build_site.cap_terrain(Z, X, Y, caps, blend=0.3, skip=skip)
    assert Zs[inside].max() <= 0.6 + 1e-9 and np.allclose(Zs[~inside], Z[~inside])


def test_stair_cap_runs_under_every_tread():
    """A details.json stair (add_details: tread k at top_z - k rise over s = run (k-1) .. run k) over a ramp that the LiDAR
    ground filter smoothed through the treads: after the cap, no node of the footprint stands within stair_clear of the
    tread above it; a yard 'steps' item (k_steps treads) is capped the same way."""
    c = 0.1
    xs = np.arange(-1, 4.001, c); ys = np.arange(-2, 2.001, c)
    X, Y = np.meshgrid(xs, ys)
    st = {"top": [0.0, 0.0], "dir": [1, 0], "width": 1.0, "length": 2.0, "top_z": 2.0, "bottom_z": 0.4, "risers": 8}
    Z = 2.0 - 0.8 * X + 0.05                                       # a ramp through the tread middles, a little high
    caps = build_site.deck_caps({"stairs": [st]})
    assert len(caps) == 1
    Zc, _ = build_site.cap_terrain(Z, X, Y, caps, blend=0.3)
    rise, run = 1.6 / 8, 2.0 / 7
    for k in range(1, 8):                                          # treads 1..7
        m = (X >= run * (k - 1) + 1e-6) & (X <= run * k - 1e-6) & (np.abs(Y) <= 0.5)
        assert Zc[m].max() <= 2.0 - k * rise - 0.05 + 1e-9
    steps = {"items": [{"kind": "steps", "line": [[0.0, 0.0], [2.0, 0.0]], "width": 1.0, "z0": 0.0, "z1": 1.0, "risers": 5}]}
    Z2 = 0.5 * X + 0.1                                             # ramp through the yard treads' middles
    Zs, _ = build_site.cap_terrain(Z2, X, Y, build_site.steps_caps(steps), blend=0.3)
    for k in range(5):                                             # k_steps: tread k top z0 + (k + 1) rise over k..k+1 runs
        m = (X >= 0.4 * k + 1e-6) & (X <= 0.4 * (k + 1) - 1e-6) & (np.abs(Y) <= 0.5)
        assert Zs[m].max() <= 0.2 * (k + 1) - 0.05 + 1e-9


def test_wall_top_clamp_lowers_an_unsupported_node_on_the_cap():
    """A side grade extrapolated from a cliff behind a wall puts a node 3 m over the wall top: with no LiDAR return near
    that height it takes the top + tol; a node over the top that a return supports (a bed rising behind an edging) stays."""
    c = 0.25
    xs = ys = np.arange(-2, 2.001, c)
    X, Y = np.meshgrid(xs, ys)
    Z = np.where(Y > 0, 1.0, 0.0)
    j1, i1 = int(np.argmin(np.abs(ys - 0.25))), int(np.argmin(np.abs(xs - 0.5)))
    j2, i2 = j1, int(np.argmin(np.abs(xs + 0.5)))
    Z[j1, i1] = 4.0                                                # unsupported spike on the cap
    Z[j2, i2] = 1.5                                                # supported by a return at 1.45
    walls = [([[-2.0, 0.0], [2.0, 0.0]], 0.3)]
    pxy = np.array([[-0.5, 0.25], [0.5, 0.25]]); pz = np.array([1.45, 1.0])
    Zt, low = build_site.wall_top_clamp(Z, X, Y, walls, [[1.0]], pxy, pz, c, tol=0.2)
    assert abs(Zt[j1, i1] - 1.2) < 1e-9 and low[j1, i1]
    assert Zt[j2, i2] == 1.5 and low.sum() == 1
    assert build_site.wall_tops({"items": [{"kind": "retaining_wall", "line": [[0, 0], [1, 0], [2, 0]],
                                            "top_z": [1.0]}]}) == [[1.0, 1.0]]


def test_clamp_mean_trims_crest_tips_by_a_bounded_amount():
    c = 0.25
    Z = np.zeros((9, 9))
    Z[4, 4] = 0.5                                                  # a tip 0.5 over its 8 neighbours (its own 3x3 median: 0)
    Zn, n = build_site.clamp_mean(Z, np.ones(Z.shape, bool), above=0.3, max_drop=0.15)
    assert n == 1 and abs(Zn[4, 4] - 0.35) < 1e-9                  # lowered by max_drop only
    Zn2, _ = build_site.clamp_mean(Z, np.ones(Z.shape, bool), above=0.3, max_drop=1.0)
    assert abs(Zn2[4, 4] - 0.3) < 1e-9
    Zn3, n3 = build_site.clamp_mean(Z, np.zeros(Z.shape, bool))
    assert n3 == 0 and np.array_equal(Zn3, Z)


def test_wall_back_floor_lifts_retained_ground_to_the_measured_ledge():
    """Behind a face the side grade is extrapolated along the slope beyond the band; on a level ledge that runs to the
    face it lands under the measured surface. Nodes behind the face rise to the lowest last return within one cell behind
    the wall body (never over top + tol, never more than 1 m: a deck over the bank), are never lowered, and the downhill
    side is left alone."""
    c = 0.25
    xs, ys, X, Y, Z, px, py, pz, item = _wall_scene(c, blend=0.75)
    item = dict(item, top_z=0.05)
    walls = build_site.wall_lines({"items": [item]})
    faces = build_site.wall_faces({"items": [item]})
    node = [X.copy(), Y.copy()]
    Zb = build_site.apply_breaklines(Z.copy(), xs, ys, walls, c, snap=node)
    Zb[(Y > 0) & (Y < 0.6)] -= 0.4                                 # the side grade dropped behind the face
    tops = build_site.face_tops({"items": [item]})
    assert tops == [[0.05]]
    Zr, up = build_site.wall_back_floor(Zb, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2)
    behind = (node[1] > 1e-6) & (node[1] <= 0.25 + 1.5 * c)
    assert up[behind & (np.abs(X) < 2.5)].all() and not up[node[1] <= 1e-6].any()
    assert np.abs(Zr[behind & (np.abs(X) < 2.5)]).max() < 0.1      # back on the 0.0 ledge
    assert np.all(Zr >= Zb - 1e-12) and Zr.max() <= 0.05 + 0.2 + 1e-9
    # a return 1.5 m over the node (a deck over the bank) is not ground
    Zd, upd = build_site.wall_back_floor(Zb, node[0], node[1], faces, tops, np.column_stack([px, py]), pz + 1.9, c, tol=5.0)
    assert not upd.any()


def test_wall_back_floor_fills_the_wedge_behind_a_convex_joint():
    """An L-shaped face (east, then turning south; uphill on the left = outside of the turn): the retained ground behind the
    joint lies outside both segments' spans. The ground filter shaves that narrow corner (here 0.5 m low); with corners
    on, the wedge nodes within the reach of the joint rise to the measured upper level like the band behind each
    segment; with corners off (the round-8 rule) they stay low. The lower level inside the L is left alone."""
    c = 0.25
    xs = np.arange(-3, 3 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    item = {"kind": "retaining_wall", "line": [[-3.5, 0.0], [0.0, 0.0], [0.0, -3.5]], "thickness": 0.25, "top_z": 0.1,
            "line_is": "face", "uphill": "left"}
    faces = build_site.wall_faces({"items": [item]}); tops = build_site.face_tops({"items": [item]})
    upper = (X > 0) | (Y > 0)
    rng = np.random.default_rng(3)
    px = rng.uniform(-3.2, 3.2, 6000); py = rng.uniform(-3.2, 3.2, 6000)
    pz = np.where((px > 0) | (py > 0), 0.0, -1.0) + rng.normal(0, 0.02, px.size)
    Z = np.where(upper, 0.0, -1.0)
    wedge = (X > 1e-6) & (Y > 1e-6) & (np.hypot(X, Y) <= 0.25 + 1.5 * c)
    Z[wedge] = -0.5                                                # the filter's notch at the corner
    node = [X.copy(), Y.copy()]
    Zr, up = build_site.wall_back_floor(Z, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2, q=0.5)
    assert wedge.sum() >= 3 and up[wedge].all() and np.abs(Zr[wedge]).max() < 0.06
    assert np.allclose(Zr[~upper], Z[~upper]) and np.all(Zr >= Z - 1e-12)
    Zo, upo = build_site.wall_back_floor(Z, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2, q=0.5,
                                         corners=False)
    assert not upo[wedge].any()
    # a wider band reaches nodes the default (thickness + 1.5 cells) leaves
    far = (Y > 0.25 + 1.5 * c + 1e-6) & (Y <= 0.25 + 3.0 * c) & (X < -0.5)
    Zf = Z.copy(); Zf[far] = -0.5
    _, up15 = build_site.wall_back_floor(Zf, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2, q=0.5)
    _, up30 = build_site.wall_back_floor(Zf, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2, q=0.5,
                                         reach_cells=3.0)
    assert not up15[far].any() and up30[far].all()


def test_wall_back_floor_quantile_takes_the_median_of_a_rough_top():
    """q = 0.5 raises the retained ground to the median of the last returns behind the wall body (a rough rock top with
    +-0.1 m noise); q = 0 to their lowest, a noise sigma or two under the surface. Neither lowers a node."""
    c = 0.25
    xs, ys, X, Y, Z, px, py, pz, item = _wall_scene(c, blend=0.75)
    item = dict(item, top_z=0.4)
    rng = np.random.default_rng(5)
    pz = np.where(py > 0, 0.2 + rng.normal(0, 0.1, pz.size), pz)      # a rough top at 0.2 behind the face
    walls = build_site.wall_lines({"items": [item]})
    faces = build_site.wall_faces({"items": [item]})
    node = [X.copy(), Y.copy()]
    Zb = build_site.apply_breaklines(Z.copy(), xs, ys, walls, c, snap=node)
    Zb[(Y > 0) & (Y < 0.6)] = -0.4                                 # the side grade dropped behind the face
    tops = build_site.face_tops({"items": [item]})
    behind = (node[1] > 1e-6) & (node[1] <= 0.25 + 1.5 * c) & (np.abs(X) < 2.5)
    Zm, upm = build_site.wall_back_floor(Zb, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2, q=0.5)
    Zl, upl = build_site.wall_back_floor(Zb, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c, tol=0.2)
    assert upm[behind].all() and upl[behind].all()
    assert abs(np.median(Zm[behind]) - 0.2) < 0.05                 # the median top
    assert np.median(Zl[behind]) < 0.1                             # the lowest return: well under it
    assert np.all(Zm >= Zb - 1e-12) and np.all(Zm >= Zl - 1e-12) and Zm.max() <= 0.4 + 0.2 + 1e-9
    # node 0.9 m under the lowest return but 1.1 m under the median: q = 0 raises it (within the 1 m overhead), so q = 0.5
    # must too (the overhead test is on the lowest return, not on the quantile)
    Zd = Zb.copy(); Zd[behind] = 0.2 - 1.1
    pz2 = np.where(py > 0, np.where(rng.random(pz.size) < 0.3, 0.2 - 0.2, 0.2), pz)
    Zm2, upm2 = build_site.wall_back_floor(Zd, node[0], node[1], faces, tops, np.column_stack([px, py]), pz2, c, tol=0.2, q=0.5)
    Zl2, upl2 = build_site.wall_back_floor(Zd, node[0], node[1], faces, tops, np.column_stack([px, py]), pz2, c, tol=0.2)
    assert np.array_equal(upm2, upl2) and upl2[behind].mean() > 0.8 and np.all(Zm2 >= Zl2 - 1e-12)
    assert np.any(upm2 & (np.abs(Zm2 - 0.2) < 1e-9))               # raised to the median 1.1 m over the node


def test_flat_window_median_finds_a_shelf_and_skips_a_step_edge():
    """A node over a flat shelf (>= 5 last returns within 0.1 m, the window's majority) gets the shelf's median; a node
    whose window straddles a 2 m step has no dominant flat cluster and is left alone."""
    rng = np.random.default_rng(3)
    px = rng.uniform(-2, 2, 4000); py = rng.uniform(-2, 2, 4000)
    pz = np.where(px > 0.5, 2.0, 0.0) + rng.normal(0, 0.02, px.size)    # shelf at 0, cliff top at 2 east of x 0.5
    c = 0.25
    xs = ys = np.arange(-1.5, 1.501, c)
    nodes = np.ones((len(ys), len(xs)), bool)
    med, cnt = lidar.flat_window_median(nodes, c, np.column_stack([px, py]), pz, x0=xs[0], y0=ys[0], window=0.5)
    i_shelf, i_edge = int(np.argmin(np.abs(xs + 1.0))), int(np.argmin(np.abs(xs - 0.5)))
    j = len(ys) // 2
    assert abs(med[j, i_shelf]) < 0.05 and cnt[j, i_shelf] >= 5
    assert abs(med[j, int(np.argmin(np.abs(xs - 1.25)))] - 2.0) < 0.05 # the cliff top is a shelf too
    med6, _ = lidar.flat_window_median(nodes, c, np.column_stack([px, py]), pz, x0=xs[0], y0=ys[0], window=0.5, share=0.6)
    assert np.isnan(med6[j, i_edge])                                 # half shelf, half cliff top: no 60 % cluster


def test_flat_lower_no_dents_lowers_a_shelf_and_skips_a_lone_node():
    """A lowered shelf (a block of nodes) is kept; a lone node dropped 0.3 m into an otherwise level rock top is not."""
    Z = np.ones((9, 9))
    target = np.full(Z.shape, np.nan)
    target[1:5, 1:5] = 0.6                                           # a 4 x 4 shelf
    target[7, 7] = 0.7                                               # one node of the rough top
    out = build_site.flat_lower_no_dents(Z, target, np.isfinite(target))
    assert np.allclose(out[1:5, 1:5], 0.6) and out[7, 7] == 1.0
    assert np.all(out <= Z)


def _corner_pad_scene(c=0.25):
    """A patio pad (z 0) retained by two walls meeting at a corner: an east-west face at y = -0.11 (uphill north, 0.35 m
    thick: the grid rows y 0 and y -0.25 both snap onto it) and a north-south face at x = 1.13 from its east end (uphill
    west), lower level -0.9 in front of both. LiDAR last returns: -0.9 in front; on the patio a few 0.0 returns through a
    deck whose boards (+2.0) give most of the returns there."""
    xs = np.arange(-3, 3 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    yard = {"items": [
        {"kind": "grade_pad", "polygon": [[-2.5, -0.11], [1.13, -0.11], [1.13, 2.5], [-2.5, 2.5]], "z": 0.0, "blend": 0.3},
        {"kind": "retaining_wall", "line": [[-2.5, -0.11], [1.13, -0.11]], "thickness": 0.35, "top_z": 0.03,
         "line_is": "face", "uphill": "left"},
        {"kind": "retaining_wall", "line": [[1.13, -0.11], [1.13, 2.5]], "thickness": 0.25, "top_z": 0.05,
         "line_is": "face", "uphill": "left"}]}
    upper = (X < 1.13) & (Y > -0.11)
    from scipy.ndimage import uniform_filter
    Z = uniform_filter(np.where(upper, 0.0, -0.9), 3, mode="nearest")      # the filtered ground smears the step
    rng = np.random.default_rng(11)
    px = rng.uniform(-3.1, 3.1, 9000); py = rng.uniform(-3.1, 3.1, 9000)
    up_p = (px < 1.13) & (py > -0.11)
    deck = up_p & (rng.random(px.size) < 0.7)
    pz = np.where(up_p, np.where(deck, 2.0, 0.0), -0.9) + rng.normal(0, 0.02, px.size)
    return xs, X, Y, Z, px, py, pz, yard


def test_corner_wall_feet_stay_on_the_lower_level_and_the_pad_is_not_raised_to_the_deck():
    """Grid rows on both sides of a face snap onto it; at the corner with a second wall the snapped feet sit a few
    millimetres inside that wall's span, so the retained-ground floor used to lift them (and the wall-body node snapped next
    to them) to the patio returns: a terrain tent in front of the face. Snapped feet now belong to their own face, move
    0.02 m downhill and keep the lower level; face-line nodes are lifted only on a terrace; the pad blend stops at the face;
    no pad node rises above pad z + 0.02 to the deck returns over it."""
    c = 0.25
    xs, X, Y, Z, px, py, pz, yard = _corner_pad_scene(c)
    zfun = lambda x, y: 0.0
    pads = build_site.grade_pads(yard)
    faces = build_site.wall_faces(yard, zfun=zfun)
    walls = build_site.wall_lines(yard, zfun=zfun)
    tops = build_site.face_tops(yard, zfun=zfun)
    last = np.column_stack([px, py])
    low = build_site.cell_lowest(last, pz, xs[0], xs[0], c, Z.shape)
    front_low = pz[~((px < 1.13) & (py > -0.11))].min()
    tol = 0.3

    def run(new):
        rr = np.zeros(Z.shape)
        Zp, padmask, nblk = build_site.pad_blend(Z, X, Y, pads, faces if new else None, rr)
        node = [X.copy(), Y.copy()]
        Zb = build_site.apply_breaklines(Zp.copy(), xs, xs, walls, c, snap=node)
        Zf, foot = build_site.wall_foot_lower(Zb, node[0], node[1], faces, low, xs[0], xs[0], c, walls=walls, tol=tol,
                                              shift=0.02 if new else 0.0)
        ceil_ = build_site.pad_ceiling(pads, node[0], node[1]) if new else None
        Zr, _ = build_site.wall_back_floor(Zf, node[0], node[1], faces, tops, last, pz, c, q=0.5, reach_cells=2.0,
                                           ceiling=ceil_, front_probe=0.05 if new else 0.0)
        return Zr, node, nblk

    def downhill_near(node):
        NX, NY = node
        # in front of the east-west face (y <= -0.11, x <= 1.13) or of the north-south face (x >= 1.13), within 0.3 m
        d1 = np.where(NX <= 1.13 + 1e-9, -0.11 - NY, np.hypot(NX - 1.13, NY + 0.11))
        d2 = np.where(NY >= -0.11 - 1e-9, NX - 1.13, np.hypot(NX - 1.13, NY + 0.11))
        return ((d1 >= -1e-3) & (d1 <= 0.3) & (NY <= -0.11 + 1e-3)) | ((d2 >= -1e-3) & (d2 <= 0.3) & (NX >= 1.13 - 1e-3))

    def pad_nodes(node):
        return shapely.contains_xy(Polygon(pads[0]["polygon"]), node[0], node[1])

    Zo, nodeo, _ = run(False)
    m_o = downhill_near(nodeo) & (np.abs(nodeo[0]) < 2.2) & (nodeo[1] < 2.2)
    assert (Zo[m_o] > front_low + tol).sum() >= 3                      # round 9: the tent at the corner
    assert Zo[pad_nodes(nodeo)].max() > 0.0 + 0.1                      # and the pad raised towards the deck
    Zr, node, nblk = run(True)
    m = downhill_near(node) & (np.abs(node[0]) < 2.2) & (node[1] < 2.2)     # (away from the faces' far ends)
    assert m.sum() >= 15 and Zr[m].max() <= front_low + tol + 1e-9
    assert Zr[pad_nodes(node)].max() <= 0.0 + 0.02 + 1e-9
    assert nblk > 0                                                    # the blend stopped at the faces
    # snapped feet sit 0.02 m in front of the face, never on top of the wall-body node snapped onto it
    feet = (np.abs(node[1] + 0.13) < 1e-6) & (node[0] < 1.13)
    assert feet.sum() >= 10
    on_face = (np.abs(node[1] + 0.11) < 1e-6) & (node[0] < 1.13)
    pairs = [(j, i) for j, i in zip(*np.nonzero(on_face)) if j > 0 and feet[j - 1, i]]
    assert pairs and all(Zr[j, i] <= Zr[j - 1, i] + 1e-9 for j, i in pairs)   # no curtain in front of the face


def test_face_line_nodes_rise_only_on_a_terrace_not_round_a_corner():
    """wall_back_floor and nodes on a downhill face line: (a) a chamfered corner -- face A runs east, turns south-east
    for 0.28 m and east again to meet face B, which runs north (both retain the same patio): the band behind B reaches
    round the corner onto the walk in front of A's chamfer; a node on the chamfer is not raised to the patio returns.
    (b) a terrace -- an upper wall's face stands 0.5 m behind a lower wall's face: the node on the upper face IS the
    lower wall's retained ground and rises to the terrace returns."""
    c = 0.25
    xs = np.arange(-3, 3 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    rng = np.random.default_rng(7)
    px = rng.uniform(-3, 3, 12000); py = rng.uniform(-3, 3, 12000)
    # (a) the corner
    A = {"kind": "retaining_wall", "line": [[-3.0, 0.0], [0.4, 0.0], [0.6, -0.2], [1.2, -0.2]], "thickness": 0.35,
         "top_z": 0.05, "line_is": "face", "uphill": "left"}
    Bw = {"kind": "retaining_wall", "line": [[1.2, -0.2], [1.2, 3.0]], "thickness": 0.25, "top_z": 0.05,
          "line_is": "face", "uphill": "left"}
    faces = build_site.wall_faces({"items": [A, Bw]}); tops = build_site.face_tops({"items": [A, Bw]})
    # the patio-level returns reach 0.12 m past the modelled faces (cap and top returns, registration), as on the lot
    patio = shapely.contains_xy(Polygon([(-3, 0), (0.4, 0), (0.6, -0.2), (1.2, -0.2), (1.2, 3), (-3, 3)])
                                .buffer(0.12, join_style="mitre"), px, py)
    pz = np.where(patio, 0.0, -0.9) + rng.normal(0, 0.02, px.size)
    NX, NY = X.copy(), Y.copy()
    # a node on the chamfer's face line (as apply_breaklines snaps one there), at the walk level
    j0, i0 = int(np.argmin(np.abs(xs + 0.0))), int(np.argmin(np.abs(xs - 0.5)))
    NX[j0, i0], NY[j0, i0] = 0.5, -0.1
    Z = np.where(shapely.contains_xy(Polygon([(-3, 0), (0.4, 0), (0.6, -0.2), (1.2, -0.2), (1.2, 3), (-3, 3)]), NX, NY),
                 0.0, -0.9)
    Z[j0, i0] = -0.9
    pxy = np.column_stack([px, py])
    Zr, up = build_site.wall_back_floor(Z, NX, NY, faces, tops, pxy, pz, c, q=0.5, reach_cells=2.0)
    assert not up[j0, i0] and Zr[j0, i0] == -0.9
    Zo, upo = build_site.wall_back_floor(Z, NX, NY, faces, tops, pxy, pz, c, q=0.5, reach_cells=2.0, front_probe=0.0)
    assert upo[j0, i0] and Zo[j0, i0] > -0.2                         # (without the probe: the round-9 tent)
    # (b) the terrace: lower wall face along y = -1 (top -0.5), upper wall face along y = -0.5 (top 0.4)
    lo_w = {"kind": "retaining_wall", "line": [[-3.0, -1.0], [3.0, -1.0]], "thickness": 0.25, "top_z": -0.45,
            "line_is": "face", "uphill": "left"}
    up_w = {"kind": "retaining_wall", "line": [[-3.0, -0.5], [3.0, -0.5]], "thickness": 0.3, "top_z": 0.4,
            "line_is": "face", "uphill": "left"}
    faces2 = build_site.wall_faces({"items": [lo_w, up_w]}); tops2 = build_site.face_tops({"items": [lo_w, up_w]})
    pz2 = np.where(py > -0.5, 0.4, np.where(py > -1.0, -0.5, -1.5)) + rng.normal(0, 0.02, px.size)
    NX2, NY2 = X.copy(), Y.copy()
    j1 = int(np.argmin(np.abs(xs + 0.5)))                              # the row on the upper face line
    Z2 = np.where(NY2 > -0.5, 0.4, np.where(NY2 > -1.0, -0.5, -1.5)).astype(float)
    Z2[j1, :] = -0.9                                                   # a side grade dropped under the terrace
    Zt, upt = build_site.wall_back_floor(Z2, NX2, NY2, faces2, tops2, pxy, pz2, c, q=0.5, reach_cells=2.0)
    inner = np.abs(xs) < 2.0
    # raised onto the terrace (its returns at -0.5; mixed with the upper level's within one cell, capped at the lower wall's
    # top + 0.2 as any retained ground)
    assert upt[j1, inner].all() and Zt[j1, inner].min() >= -0.55 and Zt[j1, inner].max() <= -0.45 + 0.2 + 1e-9


def test_wall_back_cap_lowers_retained_ground_to_flat_measured_ground_and_keeps_the_cap_clear():
    """A side grade extrapolated from a ramp behind a wall stands 0.3 m over the level ground the LiDAR measured right
    behind it (and over the wall cap). wall_back_cap: nodes from the back line out to `reach` behind the wall body over
    flat returns take min(z, lowest + dz); back-line nodes stand no higher than the top where the ground there meets it;
    nodes further back, on the downhill side or over a sloping bank are left alone; never raises."""
    c = 0.25
    xs, ys, X, Y, Z, px, py, pz, item = _wall_scene(c)
    item = dict(item, top_z=-0.06)                                 # level ground 0.0 just over the cap (-0.06)
    walls = build_site.wall_lines({"items": [item]})
    faces = build_site.wall_faces({"items": [item]})
    tops = build_site.face_tops({"items": [item]})
    node = [X.copy(), Y.copy()]
    Zb = build_site.apply_breaklines(Z.copy(), xs, ys, walls, c, snap=node)
    Zb[Y > 0.1] += 0.3                                             # the side grade stands over the measured level
    Zc, low = build_site.wall_back_cap(Zb, node[0], node[1], faces, tops, np.column_stack([px, py]), pz, c)
    mid = np.abs(X) < 2.5
    back = mid & (np.abs(node[1] - 0.25) < 1e-3)
    near = mid & (node[1] > 0.26) & (node[1] <= 0.75 + 1e-6)
    far = node[1] > 0.75 + 1e-6
    assert back.any() and near.any()
    assert np.allclose(Zc[back], -0.06)                            # back line at the wall top: the cap stays clear
    assert low[near].all() and Zc[near].max() < 0.05 + 0.05        # lowest flat return + 0.05 (noise 0.02)
    assert Zc[near].min() > -0.1
    assert np.allclose(Zc[far], Zb[far]) and np.allclose(Zc[node[1] < -1e-6], Zb[node[1] < -1e-6])
    assert np.all(Zc <= Zb + 1e-12)
    # a bank rising 0.6 m/m behind the wall is not flat, and its ground stands well over the top: left alone
    pz2 = np.where(py > 0, 0.6 * py + 0.3, pz)
    Zs, lows = build_site.wall_back_cap(Zb, node[0], node[1], faces, tops, np.column_stack([px, py]), pz2, c)
    assert not lows[mid].any()
    # off (no tops): nothing happens
    Zn, lown = build_site.wall_back_cap(Zb, node[0], node[1], faces, [None], np.column_stack([px, py]), pz, c)
    assert not lown.any()


def test_lone_wall_feet_stay_on_the_face_twinned_feet_move_off_it():
    """--wall-foot-shift separates a snapped foot from its twin (a node snapped onto the same point of the face from inside
    the wall body). A foot with no twin -- here every grid row of the body lies uphill of the wall's centre line and snaps to
    the back line -- stays ON the face: moved 0.02 m downhill, its triangles to the back line would cross the face in front
    of it as a steep terrain curtain (the khaki sliver at a patio wall's inside corner)."""
    c = 0.25
    xs = np.arange(-2, 2 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    Z = np.where(Y > 0.2, 0.0, -1.0)
    rng = np.random.default_rng(11)
    px = rng.uniform(-2, 2, 3000); py = rng.uniform(-2, 2, 3000); pz = np.where(py > 0.1, 0.0, -1.0)
    for face_y, twin in ((0.1, False), (-0.11, True)):
        item = {"kind": "retaining_wall", "line": [[-3, face_y], [3, face_y]], "thickness": 0.25, "top_z": 0.05,
                "line_is": "face", "uphill": "left"}
        walls = build_site.wall_lines({"items": [item]}); faces = build_site.wall_faces({"items": [item]})
        node = [X.copy(), Y.copy()]
        Zb = build_site.apply_breaklines(Z.copy(), xs, xs, walls, c, snap=node)
        feet = build_site.snapped_feet(node[0], node[1], faces, xs[0], xs[0], c)[0]
        assert feet.sum() >= 10
        low = build_site.cell_lowest(np.column_stack([px, py]), pz, xs[0], xs[0], c, Z.shape)
        n2 = [node[0].copy(), node[1].copy()]
        build_site.wall_foot_lower(Zb, n2[0], n2[1], faces, low, xs[0], xs[0], c, walls=walls, shift=0.02)
        want = face_y - (0.02 if twin else 0.0)
        assert np.allclose(n2[1][feet], want)
        n3 = [node[0].copy(), node[1].copy()]
        build_site.wall_foot_lower(Zb, n3[0], n3[1], faces, low, xs[0], xs[0], c, walls=walls, shift=0.02, shift_lone=True)
        assert np.allclose(n3[1][feet], face_y - 0.02)                    # the old behaviour, on request


def test_wall_back_cap_keeps_unsnapped_nodes_inside_the_wall_body_under_the_cap():
    """At a joint of a face line the breakline snap (per segment span) can leave a node inside the wall body at its own
    cell's grade, poking through the cap: wall_back_cap lowers every node inside the body to the top of the nearest
    segment (the higher one at a joint); nodes on the downhill side are left alone."""
    c = 0.25
    xs = np.arange(-2, 2 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    # a face with a joint at x = 0 (two segments meeting at an angle), uphill north, 0.3 m thick, tops -0.1 / 0.0
    item = {"kind": "retaining_wall", "line": [[-3, 0.1], [0.0, 0.1], [3, -0.2]], "thickness": 0.3, "top_z": [-0.1, 0.0],
            "line_is": "face", "uphill": "left"}
    faces = build_site.wall_faces({"items": [item]}); tops = build_site.face_tops({"items": [item]})
    Z = np.where(Y > 0.05, 0.15, -1.0)                      # the upper grade carried into the body, unsnapped
    rng = np.random.default_rng(3)
    px = rng.uniform(-2, 2, 2000); py = rng.uniform(-2, 2, 2000); pz = np.where(py > 0.1, 0.15, -1.0)
    Zc, low = build_site.wall_back_cap(Z, X, Y, faces, tops, np.column_stack([px, py]), pz, c, flat=-1.0, over=-9.0)
    inside = (np.abs(Y - 0.25) < 1e-9) & (X < -0.3)          # 0.15 m behind the west face: inside the body (top -0.1)
    assert inside.any() and np.allclose(Zc[inside], -0.1) and low[inside].all()
    joint = (np.abs(Y - 0.25) < 1e-9) & (np.abs(X) < 1e-9)  # at the joint: the higher top of the two segments
    assert np.allclose(Zc[joint], 0.0)
    assert np.allclose(Zc[Y < 0.0], Z[Y < 0.0]) and np.all(Zc <= Z + 1e-12)


def test_wall_back_shift_keeps_the_terrain_under_the_cap_back_edge():
    """Back-line nodes (snapped onto a wall's back line) at or over the wall top: the terrain triangles from them to the
    face nodes run through the body and reach the cap's back edge at (or over) the cap -- coincident with it or lapping
    over it. wall_back_shift moves them uphill off the back line by max(shift, th (z - top + margin) / (top - margin -
    zf)), so the triangles cross the back edge under the cap; Z is untouched, nodes under the top stay, a buried wall
    (face nodes over the top) is left alone; a node inside the body at a convex joint is pushed out past the mitre."""
    c = 0.25
    xs = np.arange(-2, 2 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    for top, want in ((0.0, 0.02), (-0.06, 0.02), (-0.2, 0.25 * 0.21 / 0.79)):
        item = {"kind": "retaining_wall", "line": [[-3, 0.1], [3, 0.1]], "thickness": 0.25, "top_z": top,
                "line_is": "face", "uphill": "left"}
        walls = build_site.wall_lines({"items": [item]}); faces = build_site.wall_faces({"items": [item]})
        tops = build_site.face_tops({"items": [item]})
        node = [X.copy(), Y.copy()]
        Z = build_site.apply_breaklines(np.where(Y > 0.2, 0.0, -1.0), xs, xs, walls, c, snap=node)
        Z = np.where(node[1] >= 0.1 + 0.25 - 1e-6, max(Z.max(), 0.0), Z)       # back line at the retained grade 0
        Z = np.where(np.abs(node[1] - 0.1) < 1e-6, -1.0, Z)                     # face nodes at the lower level
        back = np.abs(node[1] - 0.35) < 1e-6
        assert back.sum() >= 10
        n2 = [node[0].copy(), node[1].copy()]
        mv, amt = build_site.wall_back_shift(Z, n2[0], n2[1], faces, tops, c, shift=0.02)
        assert mv[back].all() and not mv[~back].any()
        assert np.allclose(amt[back], want, atol=1e-6) and np.allclose(n2[1][back], 0.35 + want)
        assert np.allclose(n2[0], node[0])
        # the triangle edge from a moved node down to the face node crosses the back line under the cap
        zb = Z[back] - (Z[back] - (-1.0)) * want / (0.25 + want)
        assert np.all(zb <= top - 0.01 + 1e-9)
    # nodes under the top stay; a buried wall (face nodes over the top) is left alone
    n3 = [node[0].copy(), node[1].copy()]
    mv, _ = build_site.wall_back_shift(Z - 0.5, n3[0], n3[1], faces, tops, c)
    assert not mv.any()
    mv, _ = build_site.wall_back_shift(np.full(Z.shape, 0.5), n3[0], n3[1], faces, tops, c)
    assert not mv.any()
    # convex joint on the uphill side: a node inside the body outside both spans (no snap) goes out past the mitre
    item = {"kind": "retaining_wall", "line": [[-3, 0.0], [0.0, 0.0], [3, -1.0]], "thickness": 0.3, "top_z": -0.1,
            "line_is": "face", "uphill": "left"}
    faces = build_site.wall_faces({"items": [item]}); tops = build_site.face_tops({"items": [item]})
    NX, NY = X.copy(), Y.copy()
    j0, i0 = int(np.argmin(np.abs(xs - 0.25))), int(np.argmin(np.abs(xs - 0.0)))   # (0.0, 0.25): inside the body
    body = LineString(item["line"]).buffer(0.3, single_sided=True, join_style="mitre")
    assert body.contains(shapely.Point(NX[j0, i0], NY[j0, i0]))
    Z = np.where(Y > 0.0, 0.2, -1.0); Z[j0, i0] = -0.1
    mv, amt = build_site.wall_back_shift(Z, NX, NY, faces, tops, c)
    assert mv[j0, i0] and not body.contains(shapely.Point(NX[j0, i0], NY[j0, i0]))
    assert body.distance(shapely.Point(NX[j0, i0], NY[j0, i0])) >= 0.02 - 1e-6


def _tri_z_max_over(NX, NY, Z, poly, step=0.02):
    """Highest terrain z (grid quads split along both diagonals' worst case: max of the two triangulations) sampled on a
    step grid inside ``poly`` -- what a ray cast down onto the cap would meet first."""
    ny, nx = Z.shape
    bx0, by0, bx1, by1 = poly.bounds
    best = -np.inf
    tris = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            q = [(j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)]
            for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]), (q[0], q[1], q[3]), (q[1], q[2], q[3])):
                P = np.array([[NX[a], NY[a], Z[a]] for a in t])
                if P[:, 0].max() < bx0 or P[:, 0].min() > bx1 or P[:, 1].max() < by0 or P[:, 1].min() > by1:
                    continue
                tris.append(P)
    xs = np.arange(bx0 + step / 2, bx1, step); ys = np.arange(by0 + step / 2, by1, step)
    for x in xs:
        for y in ys:
            if not poly.contains(shapely.Point(x, y)):
                continue
            for P in tris:
                (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = P
                den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
                if abs(den) < 1e-12:
                    continue
                l1 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / den
                l2 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / den
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) >= -1e-9:
                    best = max(best, l1 * z1 + l2 * z2 + l3 * z3)
    return best


def test_wall_back_cap_holds_the_back_line_and_a_free_end_at_the_cap_where_the_lidar_sees_it():
    """A 0.4 m-thick tier (face y = 0, uphill north, top 0.0) with a steep bank rising behind it (+0.35 m 0.25 m back) and
    a raised toe beyond its west end: the side grade leaves the back-line nodes 0.3 m over the cap, and no snap reaches
    past the end, so terrain covers the back and the end of the cap -- though the LiDAR returns ON the cap are at the top.
    wall_back_cap (cap_seen, ends): back-boundary nodes and the beyond-end nodes (one onto the back corner, the others onto
    the end line) stand at top - cap_drop; then no terrain point over the cap is above the top. With the cap returns 0.3 m
    over the top (soil lapping onto the cap) nothing moves; off, the old behaviour."""
    c = 0.25
    xs = np.arange(-2, 2 + 1e-9, c); X, Y = np.meshgrid(xs, xs)
    item = {"kind": "retaining_wall", "line": [[-0.9, 0.02], [3.0, 0.02]], "thickness": 0.4, "top_z": 0.0,
            "line_is": "face", "uphill": "left"}
    walls = build_site.wall_lines({"items": [item]}); faces = build_site.wall_faces({"items": [item]})
    tops = build_site.face_tops({"items": [item]})
    ground = lambda x, y: np.where(y < 0.02, -0.6, np.where(y < 0.42, 0.3, 0.3 + 0.5 * (y - 0.42)))
    Z0 = np.where(X < -0.9, np.where(Y < 0.0, -0.3, 0.25 + 0.3 * Y), ground(X, Y))   # raised toe west of the end
    node = [X.copy(), Y.copy()]
    Z = build_site.apply_breaklines(Z0.copy(), xs, xs, walls, c, snap=node)
    rng = np.random.default_rng(2)
    px = rng.uniform(-2, 2, 6000); py = rng.uniform(-2, 2, 6000)
    on_cap = (px > -0.9) & (py > 0.02) & (py < 0.42)
    pz = np.where(on_cap, rng.normal(0.0, 0.02, px.size), np.where(py >= 0.42, 0.35 + 0.5 * (py - 0.42), -0.6))
    body = LineString(item["line"]).buffer(0.4, single_sided=True, join_style="mitre").intersection(
        shapely.box(-2, -2, 2, 2))
    cap = body.buffer(-0.03)
    assert _tri_z_max_over(node[0], node[1], Z, cap) > 0.1            # the old terrain covers the cap
    n2 = [node[0].copy(), node[1].copy()]; st = {}
    Zc, low = build_site.wall_back_cap(Z, n2[0], n2[1], faces, tops, np.column_stack([px, py]), pz, c, stats=st)
    assert st["cap_seen"] >= 10 and st["ends"] >= 2
    assert _tri_z_max_over(n2[0], n2[1], Zc, cap) <= 0.0 + 1e-9       # nothing over the cap now
    cb = np.array([-0.9, 0.42])                                          # the end's back corner holds a node
    assert np.min(np.hypot(n2[0] - cb[0], n2[1] - cb[1])) < 1e-9
    assert np.all(Zc <= Z + 1e-12)
    far = (X < -1.3) | (Y > 0.8)
    assert np.allclose(Zc[far], Z[far]) and np.allclose(n2[0][far], node[0][far])
    # soil on the cap (its returns 0.3 m over the top): nothing moves
    pz_soil = np.where(on_cap, 0.3 + rng.normal(0.0, 0.02, px.size), pz)
    n3 = [node[0].copy(), node[1].copy()]
    Zs, _ = build_site.wall_back_cap(Z, n3[0], n3[1], faces, tops, np.column_stack([px, py]), pz_soil, c)
    on_back = np.abs(n3[1] - 0.42) < 1e-6
    assert np.allclose(Zs[on_back], Z[on_back]) and np.allclose(n3[0], node[0])
    # both rules off: as before
    n4 = [node[0].copy(), node[1].copy()]
    Zo, _ = build_site.wall_back_cap(Z, n4[0], n4[1], faces, tops, np.column_stack([px, py]), pz, c, cap_seen=False,
                                     ends=False)
    assert np.allclose(n4[0], node[0]) and np.allclose(n4[1], node[1])


def test_cap_nodes_mark_the_stair_footprint_and_its_blend():
    st = {"stairs": [{"top": [0.0, 0.0], "dir": [1, 0], "width": 1.0, "length": 1.5, "top_z": 1.0, "bottom_z": 0.0,
                      "risers": 6}]}
    caps = build_site.deck_caps(st)
    xs = np.arange(-2, 3 + 1e-9, 0.25); X, Y = np.meshgrid(xs, xs)
    m = build_site.cap_nodes(X, Y, caps, 0.55)
    assert m[(X > 0.1) & (X < 1.4) & (np.abs(Y) < 0.4)].all()
    assert m[(np.abs(X - 0.75) < 1e-9) & (np.abs(Y - 1.0) < 1e-9)].all()        # 0.5 m off the side: kept
    assert not m[(X < -0.6) | (X > 2.1) | (np.abs(Y) > 1.1)].any()


def test_stair_foot_ground_takes_the_measured_landing_past_the_foot():
    """Past a stair's foot the bridged ground (here 0.2 m over the measured landing) drops to the lower quartile of the
    last returns within the radius; nodes under the treads, beside the stair, beyond the reach or protected keep their
    height, and a node with fewer than min_n returns near it is left alone. Never raises."""
    c = 0.25
    xs = np.arange(-1, 4.001, c); ys = np.arange(-2, 2.001, c)
    X, Y = np.meshgrid(xs, ys)
    st = {"stairs": [{"top": [0.0, 0.0], "dir": [1, 0], "width": 1.0, "length": 2.0, "top_z": 2.0, "bottom_z": 0.4,
                      "risers": 8}]}
    land = 0.2
    Z = np.full(X.shape, land + 0.2)                                # bridge 0.2 m over the measured landing
    rng = np.random.default_rng(3)
    px = rng.uniform(-1, 4, 4000); py = rng.uniform(-2, 2, 4000)
    keep = np.hypot(px - 2.75, py - 0.5) > 0.3                     # a hole in the returns round the node (2.75, 0.5)
    px, py = px[keep], py[keep]
    pz = np.full(px.shape, land) + rng.normal(0, 0.01, px.shape)
    prot = (np.abs(X - 2.25) < 1e-9) & (np.abs(Y) < 1e-9)
    Zf, low, stats = build_site.stair_foot_ground(Z, X, Y, st, np.column_stack([px, py]), pz, reach=0.75, radius=0.25,
                                                  protect=prot)
    past = (X > 2.0 + 1e-6) & (X <= 2.75 + 1e-6) & (np.abs(Y) <= 0.75 + 1e-9) & ~prot
    hole = (np.abs(X - 2.75) < 1e-9) & (np.abs(Y - 0.5) < 1e-9)
    assert np.all(np.abs(Zf[past & ~hole] - land) < 0.03)          # on the measured landing
    assert np.allclose(Zf[hole], Z[hole])                           # no returns near it: kept
    assert np.all(Zf <= Z + 1e-12)                                  # never raises
    assert np.allclose(Zf[~past], Z[~past])                         # treads, sides, beyond the reach, protected: untouched
    assert np.allclose(Zf[prot], Z[prot])
    assert low[past & ~hole].all() and stats[0][1] == int((low).sum())


def test_overlay_gap_per_wall_keeps_an_uphill_walk_up_to_a_thin_edge_and_past_its_end():
    """A wall item's "overlay_gap" overrides --overlay-wall-gap: 0 for a walk's 12 cm concrete edge leaves no strip on its
    uphill side (the walk overlay meets the edge's back and runs on past its end), while the default wall keeps its
    0.15 m strip and the 0.15 m extension past its ends."""
    edge = {"kind": "retaining_wall", "line": [[0.0, 0.0], [-2.0, 0.0]], "top_z": 0.0, "thickness": 0.12,
            "line_is": "face", "uphill": "right", "overlay_gap": 0.0}
    other = {"kind": "retaining_wall", "line": [[0.0, 5.0], [-2.0, 5.0]], "top_z": 0.0, "thickness": 0.12,
             "line_is": "face", "uphill": "right"}
    data = {"items": [edge, other]}
    faces = build_site.wall_faces(data)
    gaps = build_site.face_overlay_gaps(data, 0.15)
    assert gaps == [0.0, 0.15]
    strips = build_site.uphill_strips(faces, gaps)
    assert not strips.intersects(Polygon([(-2.2, -0.1), (0.3, -0.1), (0.3, 0.3), (-2.2, 0.3)]))   # no strip at the edge
    assert abs(strips.area - (2.0 + 0.3) * 0.15) < 1e-6                                              # the other wall's
    walls = build_site.wall_lines(data)
    wallpoly = shapely.unary_union([LineString(l_).buffer(th / 2, cap_style="flat") for l_, th in walls] + [strips])
    walk = Polygon([(-2.5, 0.0), (0.6, 0.0), (0.6, 1.0), (-2.5, 1.0)]).difference(wallpoly)
    assert walk.contains(shapely.Point(-1.0, 0.13))                 # meets the edge's back (0.12)
    assert walk.contains(shapely.Point(0.08, 0.05))                 # and runs on past its end


def test_split_diagonals_never_turns_a_snapped_cell_over():
    """A cell whose nodes were snapped onto a diagonal wall face is skewed in plan: the diagonal the height rule picks
    would give a triangle of negative plan area (facing down, folded over its neighbours). With the node positions the
    other diagonal is taken; without them (or on a regular cell) the height rule stands."""
    # one cell (local coordinates) whose two lower nodes were snapped onto a wall face running at 45 deg to the grid
    NX = np.array([[0.082, 0.195], [0.0, 0.33]]); NY = np.array([[-0.035, -0.16], [0.0, 0.212]])
    Z = np.array([[-3.72, -3.755], [-3.608, -2.93]])
    assert bool(build_site.split_diagonals(Z)[0, 0])                       # height rule: (j,i+1)-(j+1,i)
    alt = build_site.split_diagonals(Z, NX, NY)
    assert not bool(alt[0, 0])                                             # that one turns over: the other is used
    tri = lambda a, b, c: 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))
    P = {k: (NX[j, i], NY[j, i]) for k, (j, i) in {"00": (0, 0), "01": (0, 1), "11": (1, 1), "10": (1, 0)}.items()}
    assert tri(P["01"], P["10"], P["00"]) < 0 < min(tri(P["00"], P["01"], P["11"]), tri(P["00"], P["11"], P["10"]))
    xs = np.arange(0, 1.01, 0.25); X, Y = np.meshgrid(xs, xs); Zr = np.random.default_rng(1).normal(0, 0.2, X.shape)
    assert np.array_equal(build_site.split_diagonals(Zr, X, Y), build_site.split_diagonals(Zr))   # regular grid: unchanged
