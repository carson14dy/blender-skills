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
