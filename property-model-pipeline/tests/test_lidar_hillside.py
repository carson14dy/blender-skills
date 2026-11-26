"""Hillside LiDAR helpers: filtered ground surface, plane patches, canopy removal."""
import numpy as np
from shapely.geometry import Polygon

from propmodel import lidar


def _cloud(rng, xy0, xy1, step, zf, cls=1):
    xs, ys = np.meshgrid(np.arange(xy0[0], xy1[0], step), np.arange(xy0[1], xy1[1], step))
    x, y = xs.ravel() + rng.uniform(-step / 3, step / 3, xs.size), ys.ravel() + rng.uniform(-step / 3, step / 3, xs.size)
    z = zf(x, y) + rng.normal(0, 0.02, x.size)
    one = np.ones_like(x)
    return np.column_stack([x, y, z, cls * one, one, one])   # x, y, z, class, return, n_returns


def test_ground_surface_on_a_slope_with_a_house_cut_in():
    rng = np.random.default_rng(1)
    slope = lambda x, y: 0.3 * y                                      # 30 % grade rising north
    ground = _cloud(rng, (-20, -20), (20, 20), 0.25, slope)
    house = Polygon([(-5, -4), (5, -4), (5, 4), (-5, 4)])
    inside = np.array([house.contains(__import__("shapely").geometry.Point(p)) for p in ground[:, :2]])
    roof = _cloud(rng, (-5, -4), (5, 4), 0.25, lambda x, y: 0.3 * 4 + 0.2)   # flat roof just above uphill grade
    pts = np.vstack([ground[~inside], roof])
    surf = lidar.ground_surface(pts, cell=0.5, exclude=house.buffer(0.5))
    zq = lidar.surface_z(surf, np.array([0.0, 0.0, 10.0]), np.array([0.0, -3.0, 10.0]))
    assert abs(zq[0] - slope(0, 0)) < 0.35 and abs(zq[1] - slope(0, -3)) < 0.5   # bridged under the house
    assert abs(zq[2] - slope(10, 10)) < 0.1


def test_main_patch_drops_thin_strip_and_canopy_keeps_lower_roof():
    rng = np.random.default_rng(2)
    plane = lambda x, y: 5.0 - 0.3 * y
    big = _cloud(rng, (0, 0), (8, 6), 0.2, plane)
    strip = _cloud(rng, (12, 0), (12.3, 6), 0.2, plane)               # 0.3 m wide strip on the same plane
    xyz = np.vstack([big, strip])[:, :3]
    idx = np.arange(len(xyz))
    keep = lidar.main_patch(xyz, idx, cell=0.5, min_area=8.0)
    assert np.all(keep < len(big)) and len(keep) > 0.9 * len(big)
    # an L-shaped plane patch, and another roof in its notch that sits ABOVE the plane's extension:
    # that roof is not canopy (a convex-hull test would delete it)
    leg = _cloud(rng, (0, 6), (3, 12), 0.2, plane)
    Lpts = np.vstack([big, leg])[:, :3]
    other = _cloud(rng, (4, 7.5), (7.5, 11.5), 0.2, lambda x, y: 3.0)[:, :3]   # plane there: 1.6 .. 2.75
    p = {"indices": np.arange(len(Lpts)), "coef": (0.0, -0.3, 5.0)}
    km = lidar.remove_canopy(np.vstack([Lpts, other]), [p])
    assert km[len(Lpts):].mean() > 0.95
    # branches right over the patch are removed
    branch = _cloud(rng, (2, 2), (4, 4), 0.25, lambda x, y: plane(x, y) + 1.5)[:, :3]
    km = lidar.remove_canopy(np.vstack([Lpts, branch]), [p])
    assert not km[len(Lpts):].any()
