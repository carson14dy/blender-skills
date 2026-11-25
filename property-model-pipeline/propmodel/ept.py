"""Minimal Entwine Point Tile (EPT) reader for the public USGS 3DEP LiDAR bucket.

No API key needed. Data: s3://usgs-lidar-public (AWS Open Data), index at
https://usgs.entwine.io/boundaries/resources.geojson.

Points come back in EPSG:3857 (Web Mercator) with Z in metres (usually NAVD88).
Use :func:`propmodel.lidar.to_local` to convert — never measure in 3857 directly
(horizontal scale error of 1/cos(lat), ~30 % at 40 deg N).

Offline / cached mode: with ``PROPMODEL_OFFLINE=1`` every request is answered from the cache
only and a miss raises :class:`OfflineMiss` (no network). :func:`install_offline_guard` makes
the same true for every other ``requests`` call in the process (the other fetchers check their
cache first, so a guarded run reads cached responses and fails fast on a miss).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
from typing import List

import numpy as np
import requests

INDEX_URL = "https://usgs.entwine.io/boundaries/resources.geojson"
UA = {"User-Agent": "propmodel/0.1 (property measurement toolkit)"}
# LAS dimension names for --extra-dims (case-insensitive aliases -> laspy attribute)
EXTRA_DIMS = {"gpstime": "gps_time", "gps_time": "gps_time", "intensity": "intensity",
              "scananglerank": "scan_angle_rank", "scan_angle_rank": "scan_angle_rank", "scanangle": "scan_angle",
              "scan_angle": "scan_angle", "pointsourceid": "point_source_id", "point_source_id": "point_source_id",
              "userdata": "user_data", "user_data": "user_data"}


class OfflineMiss(RuntimeError):
    """PROPMODEL_OFFLINE=1 and the response is not in the cache."""


def offline():
    return os.environ.get("PROPMODEL_OFFLINE", "") not in ("", "0", "false", "no")


def install_offline_guard():
    """Make every ``requests`` call in this process raise OfflineMiss (cache-only run).

    Not a RequestException subclass on purpose: retry loops that catch request errors must not
    sleep and retry on a cache miss. Returns True when the guard is (now) active."""
    if not offline():
        return False
    from requests import sessions
    if getattr(sessions.Session.request, "_propmodel_offline", False):
        return True

    def _blocked(self, method, url, *a, **k):
        raise OfflineMiss(f"offline (PROPMODEL_OFFLINE=1): {method} {url} is not in the cache")
    _blocked._propmodel_offline = True
    sessions.Session.request = _blocked
    return True


def cache_path(url, cache_dir):
    """Cache file for ``url`` (the key every EPT request uses; fixtures build caches with it)."""
    key = hashlib.sha1(url.encode()).hexdigest()[:20] + os.path.splitext(url.split("?")[0])[1]
    return os.path.join(cache_dir, key)


def _cached_get(url, cache_dir, binary=False, timeout=120):
    os.makedirs(cache_dir, exist_ok=True)
    path = cache_path(url, cache_dir)
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
    else:
        if offline():
            raise OfflineMiss(f"offline (PROPMODEL_OFFLINE=1): {url} is not in the cache ({path})")
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()
        data = r.content
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return data if binary else json.loads(data)


def find_resources(lon, lat, cache_dir):
    """All 3DEP EPT datasets covering (lon, lat), newest acquisition first."""
    from shapely.geometry import shape, Point
    idx = _cached_get(INDEX_URL, cache_dir)
    p = Point(lon, lat)
    hits = []
    for f in idx["features"]:
        g = shape(f["geometry"])
        if g.bounds[0] <= lon <= g.bounds[2] and g.bounds[1] <= lat <= g.bounds[3] and g.contains(p):
            props = dict(f["properties"])
            years = [int(y) for y in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", props["name"])]
            props["year"] = max(years) if years else None
            hits.append(props)
    # newest first; mosaics without a year ("FullState") last
    hits.sort(key=lambda h: (h["year"] is None, -(h["year"] or 0)))
    return hits


class EPT:
    def __init__(self, url, cache_dir):
        self.url = url
        self.base = url.rsplit("/", 1)[0]
        self.cache = os.path.join(cache_dir, re.sub(r"\W+", "_", self.base.split("/")[-1]))
        self.meta = _cached_get(url, self.cache)
        self.bounds = np.array(self.meta["bounds"], float)
        self._hier = {}

    def _hierarchy(self, key):
        return _cached_get(f"{self.base}/ept-hierarchy/{key}.json", self.cache)

    def _node_bounds(self, d, x, y, z):
        b = self.bounds
        size = (b[3:] - b[:3]) / (2 ** d)
        lo = b[:3] + size * np.array([x, y, z])
        return lo, lo + size

    def nodes_in(self, bbox, max_depth=None):
        """Keys of non-empty nodes whose XY bounds intersect bbox=(xmin,ymin,xmax,ymax) in 3857."""
        out = []
        stack = [("0-0-0-0", self._hierarchy("0-0-0-0"))]
        visited = set()
        while stack:
            key, hier = stack.pop()
            if (key, id(hier)) in visited:
                continue
            visited.add((key, id(hier)))
            count = hier.get(key)
            if count is None or count == 0:
                continue
            if count == -1:
                sub = self._hierarchy(key)
                stack.append((key, sub))
                continue
            d, x, y, z = map(int, key.split("-"))
            lo, hi = self._node_bounds(d, x, y, z)
            if hi[0] < bbox[0] or lo[0] > bbox[2] or hi[1] < bbox[1] or lo[1] > bbox[3]:
                continue
            out.append(key)
            if max_depth is not None and d >= max_depth:
                continue
            for dx in (0, 1):
                for dy in (0, 1):
                    for dz in (0, 1):
                        ck = f"{d + 1}-{2 * x + dx}-{2 * y + dy}-{2 * z + dz}"
                        if ck in hier:
                            stack.append((ck, hier))
        return out

    def read(self, bbox, max_depth=None, progress=None, extra=None):
        """Points in bbox (3857) as rows [x, y, z, class, return, n_returns].

        ``extra``: LAS dimension names (``GpsTime``, ``Intensity``, ``ScanAngleRank``...); then returns
        (rows, extra_rows) with one extra column per name in the same row order (NaN where a chunk lacks it)."""
        import laspy
        keys = self.nodes_in(bbox, max_depth)
        names = [EXTRA_DIMS.get(str(n).lower().replace("-", "_"), str(n)) for n in (extra or [])]
        chunks, xchunks = [], []
        self.gps_time_type = None
        for i, k in enumerate(keys):
            if progress:
                progress(i, len(keys), k)
            raw = _cached_get(f"{self.base}/ept-data/{k}.laz", self.cache, binary=True)
            las = laspy.read(io.BytesIO(raw))
            x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
            m = (x >= bbox[0]) & (x <= bbox[2]) & (y >= bbox[1]) & (y <= bbox[3])
            if not m.any():
                continue
            cls = np.asarray(las.classification)[m]
            ret = np.asarray(las.return_number)[m]
            nret = np.asarray(las.number_of_returns)[m]
            chunks.append(np.column_stack([x[m], y[m], z[m], cls, ret, nret]))
            if names:
                cols = []
                for nm in names:
                    try:
                        cols.append(np.asarray(getattr(las, nm), float)[m])
                    except (AttributeError, ValueError, KeyError):
                        cols.append(np.full(int(m.sum()), np.nan))
                xchunks.append(np.column_stack(cols))
                try:   # LAS global encoding bit 0: 1 = adjusted standard GPS time, 0 = GPS week seconds
                    self.gps_time_type = "adjusted_standard" if int(las.header.global_encoding.gps_time_type) else "week"
                except Exception:  # noqa: BLE001
                    pass
        pts = np.vstack(chunks) if chunks else np.zeros((0, 6))
        if not names:
            return pts
        return pts, (np.vstack(xchunks) if xchunks else np.zeros((0, len(names))))
