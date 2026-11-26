"""A synthetic roof job for the hazards roof part: one 10 x 20 m plane (3/12 pitch, rising north), LiDAR
returns on a 0.4 m grid on the roof, a 4 x 4 m canopy patch 3 m above the roof at the west rake
(x 0..4, y 4..8: 16 m2 = 8.0 % of the 200 m2 plan), a 0.6 m chimney (ignored as a small patch), and an
orthophoto with a known roof colour. Model frame only (no geographic place)."""
import json
import os

import numpy as np

DATUM = 100.0
ROOF_RGB = (92, 74, 60)            # a brown roof in the ortho


def plane_z(x, y):
    return 0.25 * y + 3.0


def model():
    ring = [[0, 0], [10, 0], [10, 20], [0, 20]]
    facet = {"id": "F0", "wings": ["w0"], "plane": [0.0, 0.25, 3.0], "pitch_rise_per_12": 3.0, "azimuth": 180.0,
             "area_m2": 200.0 * (1 + 0.25 ** 2) ** 0.5, "hidden_from_above": False,
             "polygons": [{"outer": [[x, y, plane_z(x, y)] for x, y in ring], "holes": []}]}
    edges = [{"kind": "eave", "facets": ["F0"], "p0": [0, 0, 3.0], "p1": [10, 0, 3.0], "length_m": 10.0},
             {"kind": "rake", "facets": ["F0"], "p0": [0, 0, 3.0], "p1": [0, 20, 8.0], "length_m": 20.6},
             {"kind": "rake", "facets": ["F0"], "p0": [10, 0, 3.0], "p1": [10, 20, 8.0], "length_m": 20.6},
             {"kind": "ridge", "facets": ["F0"], "p0": [0, 20, 8.0], "p1": [10, 20, 8.0], "length_m": 10.0}]
    return {"facets": [facet], "edges": edges, "walls": [], "wings": []}


def points():
    g = np.arange(0.2, 10.0, 0.4)
    h = np.arange(0.2, 20.0, 0.4)
    X, Y = np.meshgrid(g, h)
    roof = np.column_stack([X.ravel(), Y.ravel(), plane_z(X.ravel(), Y.ravel())])
    cx, cy = np.meshgrid(np.arange(0.2, 4.0, 0.4), np.arange(4.2, 8.0, 0.4))
    canopy = np.column_stack([cx.ravel(), cy.ravel(), plane_z(cx.ravel(), cy.ravel()) + 3.0])
    chim = np.array([[7.3, 15.3, plane_z(7.3, 15.3) + 1.2], [7.6, 15.6, plane_z(7.6, 15.6) + 1.2]])
    ground = np.column_stack([np.arange(-5, 15, 0.5), np.full(40, -3.0), np.zeros(40)])
    xyz = np.vstack([roof, canopy, chim, ground])
    cls = np.ones(len(xyz))
    out = np.column_stack([xyz[:, 0], xyz[:, 1], xyz[:, 2] + DATUM, cls, np.ones(len(xyz)), np.ones(len(xyz))])
    return out


def write(job):
    from PIL import Image
    os.makedirs(os.path.join(job, "data"), exist_ok=True)
    with open(os.path.join(job, "model.json"), "w") as f:
        json.dump(model(), f)
    site_p = os.path.join(job, "site.json")
    site = json.load(open(site_p)) if os.path.exists(site_p) else {}
    site.update(datum_m=DATUM, origin=site.get("origin") or {"lat": 10.0, "lon": -140.0, "h": 0.0})
    site.setdefault("geocode", {"lat": 10.0, "lon": -140.0, "source": "user"})
    with open(site_p, "w") as f:
        json.dump(site, f)
    np.save(os.path.join(job, "data", "lidar_points.npy"), points())
    with open(os.path.join(job, "data", "lidar.json"), "w") as f:
        json.dump({"flight_date": "2020-12-20", "leaf_on": False, "year": 2020, "planes": []}, f)
    # ortho: 40 x 40 m around the origin at 0.1 m/px; grass everywhere, the roof brown
    px, half = 400, 20.0
    img = np.zeros((px, px, 3), np.uint8)
    img[:] = (60, 110, 50)
    m = 2 * half / px
    cols = (np.arange(px) + 0.5) * m - half
    rows = half - (np.arange(px) + 0.5) * m
    X, Y = np.meshgrid(cols, rows)
    inside = (X >= 0) & (X <= 10) & (Y >= 0) & (Y <= 20)
    img[inside] = ROOF_RGB
    Image.fromarray(img).save(os.path.join(job, "data", "ortho.png"))
    with open(os.path.join(job, "data", "ortho.png.json"), "w") as f:
        json.dump({"bounds_local": [-half, -half, half, half], "px": px, "m_per_px": m, "provider": "test",
                   "attribution": "Test imagery"}, f)
