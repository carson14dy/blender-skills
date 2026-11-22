"""Hillside site terrain: median ground cells, solid-surface rock merge, breaklines, pads, apron, curbs."""
import importlib.util
import os

import numpy as np
from shapely.geometry import Polygon

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
