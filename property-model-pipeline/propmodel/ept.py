"""Minimal Entwine Point Tile (EPT) reader for the public USGS 3DEP LiDAR bucket.

No API key needed. Data: s3://usgs-lidar-public (AWS Open Data), index at
https://usgs.entwine.io/boundaries/resources.geojson.

Points come back in EPSG:3857 (Web Mercator) with Z in metres (usually NAVD88).
Use :func:`propmodel.lidar.to_local` to convert — never measure in 3857 directly
(horizontal scale error of 1/cos(lat), ~30 % at 40 deg N).
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


def _cached_get(url, cache_dir, binary=False, timeout=120):
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:20] + os.path.splitext(url.split("?")[0])[1]
    path = os.path.join(cache_dir, key)
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
    else:
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

    def read(self, bbox, max_depth=None, progress=None):
        import laspy
        keys = self.nodes_in(bbox, max_depth)
        chunks = []
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
        if not chunks:
            return np.zeros((0, 6))
        return np.vstack(chunks)
