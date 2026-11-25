"""Offline inputs for the synthetic demo job (tests/test_demo_run.py, tests/test_edges.py).

    python3 make_fixture.py OUT_DIR

writes, from house.json (an invented gable house in the open Pacific: no real place):
  OUT_DIR/cache/                 a PROPMODEL_CACHE holding a tiny USGS-style EPT dataset (index, ept.json,
                                 hierarchy, one uncompressed LAS chunk with GpsTime), keyed exactly as
                                 propmodel.ept reads it, so `pm.py lidar` runs with PROPMODEL_OFFLINE=1
  OUT_DIR/footprint.geojson      the fake "city" footprint (traces the walls, off by a datum shift)
  OUT_DIR/profile.json           the region profile (no real services)
and returns the truth (wing, roof area) for the assertions. Points: class-2 ground on a gently tilted plane
(none under the roof), class-1 single returns on the true roof including the overhangs, and a few returns on
the wall faces under the eaves. Deterministic (seeded).
"""
import datetime as dt
import io
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from propmodel import ept  # noqa: E402
from propmodel.geo import LocalFrame, lonlat_to_mercator  # noqa: E402
from propmodel.roofgeom import Wing, build  # noqa: E402

GPS_EPOCH = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)


def house():
    with open(os.path.join(HERE, "house.json")) as f:
        return json.load(f)


def truth_model(h=None):
    h = h or house()
    return build([Wing.from_dict(h["truth"])])


def _uniform_in(poly, density, rng):
    x0, y0, x1, y1 = poly.bounds
    n = rng.poisson(density * (x1 - x0) * (y1 - y0))
    xy = np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)])
    import shapely
    return xy[shapely.contains_xy(poly, xy[:, 0], xy[:, 1])]


def points(h=None):
    """Synthetic returns in the house frame: rows x, y, z_abs, class, return, n_returns."""
    import shapely
    from shapely.geometry import box
    h = h or house()
    li = h["lidar"]
    rng = np.random.default_rng(li["seed"])
    w = Wing.from_dict(h["truth"])
    m = build([w])
    roof = m.roof_outline()
    sx, sy = h["ground_slope"]
    z0 = float(h["elevation_m"])

    def ground(x, y):
        return z0 + sx * np.asarray(x) + sy * np.asarray(y)
    g0 = float(ground(w.cx, w.cy))
    half = li["half"]
    gxy = _uniform_in(box(-half, -half, half, half), li["ground_density"], rng)
    gxy = gxy[~shapely.contains_xy(roof, gxy[:, 0], gxy[:, 1])]
    gz = ground(gxy[:, 0], gxy[:, 1]) + rng.normal(0, li["noise_m"], len(gxy))
    rxy = _uniform_in(roof, li["roof_density"], rng)
    rz = g0 + m.surface_z(rxy) + rng.normal(0, li["noise_m"], len(rxy))
    # wall faces under the eaves (scan angle): between 0.3 m above grade and 0.4 m under the soffit
    wp = []
    ring = np.asarray(w.wall_polygon().exterior.coords)
    drip = w.eave_height - w.eave_overhang * w.pitch
    for a, b in zip(ring[:-1], ring[1:]):
        L = float(np.linalg.norm(b - a))
        n = int(L * li["wall_points_per_m"])
        t = rng.uniform(0.05, 0.95, n)
        p = a + np.outer(t, b - a)
        zz = g0 + rng.uniform(0.3, drip - 0.4, n)
        wp.append(np.column_stack([p, zz]))
    wp = np.vstack(wp)
    rows = [np.column_stack([gxy, gz, np.full(len(gz), 2), np.ones(len(gz)), np.ones(len(gz))]),
            np.column_stack([rxy, rz, np.ones(len(rz)), np.ones(len(rz)), np.ones(len(rz))]),
            np.column_stack([wp, np.ones(len(wp)), np.ones(len(wp)), np.ones(len(wp))])]
    return np.vstack(rows)


def _gps_seconds(date_str, n, rng):
    d = dt.datetime.fromisoformat(date_str).replace(hour=18, tzinfo=dt.timezone.utc)
    t = (d - GPS_EPOCH).total_seconds() - 1e9          # adjusted standard GPS time
    return t + np.sort(rng.uniform(0, 600, n))


def write_cache(cache_dir, h=None):
    """EPT index + dataset for the synthetic points, cached under the keys propmodel.ept uses."""
    import laspy
    h = h or house()
    li = h["lidar"]
    lat0, lon0 = h["location"]["lat"], h["location"]["lon"]
    frame = LocalFrame(lat0, lon0, 0.0)
    P = points(h)
    lat, lon, _ = frame.to_geodetic(P[:, 0], P[:, 1], 0.0)
    X, Y = lonlat_to_mercator(lon, lat)
    name = li["dataset"]
    base = f"https://synthetic.invalid/{name}"
    url = f"{base}/ept.json"
    # index (resources.geojson) with one polygon round the site
    d = 0.01
    index = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"name": name, "url": url, "count": int(len(P))},
        "geometry": {"type": "Polygon", "coordinates": [[[lon0 - d, lat0 - d], [lon0 + d, lat0 - d], [lon0 + d, lat0 + d],
                                                          [lon0 - d, lat0 + d], [lon0 - d, lat0 - d]]]}}]}
    os.makedirs(cache_dir, exist_ok=True)
    with open(ept.cache_path(ept.INDEX_URL, cache_dir), "w") as f:
        json.dump(index, f)
    lo = np.array([X.min(), Y.min(), P[:, 2].min()]) - 1.0
    span = float(max(X.max() - X.min(), Y.max() - Y.min(), P[:, 2].max() - P[:, 2].min()) + 2.0)
    meta = {"bounds": [*lo.tolist(), *(lo + span).tolist()], "dataType": "laszip", "hierarchyType": "json",
            "points": int(len(P)), "span": 128, "version": "1.0.0", "srs": {"authority": "EPSG", "horizontal": "3857"}}
    ds_cache = os.path.join(cache_dir, "ept", name)   # EPT(url, CACHE/ept) caches under the dataset folder name
    os.makedirs(ds_cache, exist_ok=True)
    with open(ept.cache_path(url, ds_cache), "w") as f:
        json.dump(meta, f)
    with open(ept.cache_path(f"{base}/ept-hierarchy/0-0-0-0.json", ds_cache), "w") as f:
        json.dump({"0-0-0-0": int(len(P))}, f)
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.offsets = lo.tolist()
    hdr.scales = [0.001, 0.001, 0.001]
    hdr.global_encoding.gps_time_type = laspy.header.GpsTimeType.STANDARD
    las = laspy.LasData(hdr)
    las.x, las.y, las.z = X, Y, P[:, 2]
    las.classification = P[:, 3].astype(np.uint8)
    las.return_number = P[:, 4].astype(np.uint8)
    las.number_of_returns = P[:, 5].astype(np.uint8)
    las.gps_time = _gps_seconds(li["flight_date"], len(P), np.random.default_rng(li["seed"] + 1))
    buf = io.BytesIO()
    las.write(buf, do_compress=False)
    with open(ept.cache_path(f"{base}/ept-data/0-0-0-0.laz", ds_cache), "wb") as f:
        f.write(buf.getvalue())
    return {"points": int(len(P)), "dataset": name}


def footprint_geojson(path, h=None):
    """The fake city footprint: the true WALL rectangle in the city's datum (model = city + shift)."""
    h = h or house()
    cf = h["city_footprint"]
    w = Wing.from_dict(h["truth"])
    poly = w.wall_polygon() if cf["traces"] == "walls" else w.roof_outline()
    ring = np.asarray(poly.exterior.coords)[:-1]
    rng = np.random.default_rng(h["lidar"]["seed"] + 2)
    ring = ring - np.asarray(cf["shift_to_lidar"]) + rng.normal(0, cf["noise_m"], ring.shape)
    frame = LocalFrame(h["location"]["lat"], h["location"]["lon"], 0.0)
    ll = frame.ring_to_lonlat(np.vstack([ring, ring[:1]]))
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "id": 1, "properties": {"OBJECTID": 1},
                                                     "geometry": {"type": "Polygon", "coordinates": [ll]}}]}
    with open(path, "w") as f:
        json.dump(fc, f)
    return path


def lod2_faces(h=None):
    """The truth house as a city LOD2 solid in the house frame: 2 roof planes, 4 walls (gable ends to the ridge),
    a floor at grade - 0.5 m. Rings of (x, y, z_rel) with z above the ground at the house centre."""
    h = h or house()
    w = Wing.from_dict(h["truth"])
    umax, vlo, vhi = w.extents()
    hr = w.eave_height + w.pitch * w.width / 2          # ridge height above the plate's datum
    drip_hi = w.eave_height - w.pitch * (vhi - w.width / 2)
    drip_lo = w.eave_height - w.pitch * (-w.width / 2 - vlo)

    def P(u, v, z):
        x, y = w.to_world([u], [v])[0]
        return [float(x), float(y), float(z)]
    roof_a = [P(-umax, vhi, drip_hi), P(umax, vhi, drip_hi), P(umax, 0, hr), P(-umax, 0, hr)]
    roof_b = [P(-umax, 0, hr), P(umax, 0, hr), P(umax, vlo, drip_lo), P(-umax, vlo, drip_lo)]
    L, W = w.length / 2, w.width / 2
    base = -0.5
    walls = [[P(-L, -W, base), P(L, -W, base), P(L, -W, w.eave_height), P(-L, -W, w.eave_height)],
             [P(-L, W, base), P(L, W, base), P(L, W, w.eave_height), P(-L, W, w.eave_height)],
             [P(L, -W, base), P(L, W, base), P(L, W, w.eave_height), P(L, 0, w.eave_height + w.pitch * W), P(L, -W, w.eave_height)],
             [P(-L, -W, base), P(-L, W, base), P(-L, W, w.eave_height), P(-L, 0, w.eave_height + w.pitch * W), P(-L, -W, w.eave_height)]]
    floor = [P(-L, -W, base), P(L, -W, base), P(L, W, base), P(-L, W, base)]
    return [roof_a, roof_b] + walls + [floor]


def lod2_json(path, h=None, dz=-0.09):
    """Esri JSON FeatureSet (lon/lat, Z in US survey feet, binaryPatches) of the city LOD2 house, in the city datum
    (off by the same horizontal shift as the footprint, and ``dz`` m vertically)."""
    from propmodel import multipatch as MP
    h = h or house()
    w = Wing.from_dict(h["truth"])
    sx, sy = h["ground_slope"]
    g0 = float(h["elevation_m"]) + sx * w.cx + sy * w.cy
    frame = LocalFrame(h["location"]["lat"], h["location"]["lon"], 0.0)
    shift = np.asarray(h["city_footprint"]["shift_to_lidar"])
    parts = []
    for ring in lod2_faces(h):
        R = np.asarray(ring, float)
        lat, lon, _ = frame.to_geodetic(R[:, 0] - shift[0], R[:, 1] - shift[1], 0.0)
        z_ft = (R[:, 2] + g0 + dz) / MP.Z_UNITS["ftus"]
        R2 = np.column_stack([lon, lat, z_ft])
        parts.append((4, np.vstack([R2, R2[:1]])))       # FirstRing, closed
    fs = {"geometryType": "esriGeometryMultiPatch", "spatialReference": {"wkid": 4326}, "hasZ": True,
          "features": [{"attributes": {"OBJECTID": 1}, "geometry": {"hasZ": True, "binaryPatches": MP.encode_shape_buffer(parts)}}]}
    with open(path, "w") as f:
        json.dump(fs, f)
    return path


def build_all(out_dir):
    h = house()
    os.makedirs(out_dir, exist_ok=True)
    info = write_cache(os.path.join(out_dir, "cache"), h)
    footprint_geojson(os.path.join(out_dir, "footprint.geojson"), h)
    lod2_json(os.path.join(out_dir, "lod2.json"), h)
    shutil.copy(os.path.join(HERE, "profile.json"), os.path.join(out_dir, "profile.json"))
    m = truth_model(h)
    info.update(cache=os.path.join(out_dir, "cache"), profile=os.path.join(out_dir, "profile.json"),
                latlon=f"{h['location']['lat']},{h['location']['lon']}", truth=h["truth"],
                roof_area_m2=float(m.roof_area()), footprint_area_m2=float(m.footprint().area))
    return info


if __name__ == "__main__":
    print(json.dumps(build_all(sys.argv[1]), indent=1))
