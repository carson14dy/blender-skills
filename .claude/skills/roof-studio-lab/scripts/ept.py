"""USGS 3DEP EPT reader with a depth limit, sharing the skill's node cache (cache/_ept/...).

The skill's lidar.fetch_points always walks to the deepest node, which is right for one roof but
pulls far too much for a 400 m ground model. `max_depth` stops early: in this collection a node
at depth d holds about one point per (265106 / 2^d / 128) Web-Mercator metres, i.e. depth 10 is
about 1.5 m ground spacing and depth 11 about 0.75 m.
"""
import io
import json
import os

import numpy as np

from common import CACHE, FT_US, lidar, log, proj


def fetch(http, bbox_ft, min_depth=6, max_depth=30, max_nodes=400):
    laspy = lidar._need_laspy()
    http.host_interval.setdefault(lidar.EPT_HOST, 0.2)
    cdir = os.path.join(CACHE, "_ept", lidar.LIDAR_COLLECTION)
    root = lidar.EPT_ROOT
    meta = json.loads(http.get_bytes(root + "/ept.json", os.path.join(cdir, "ept.json")))
    b = meta["bounds"]
    x0, y0, x1, y1 = bbox_ft
    cx, cy = proj.city_to_webmerc(np.array([x0, x1, x0, x1]), np.array([y0, y0, y1, y1]))
    q = (float(cx.min()), float(cy.min()), float(cx.max()), float(cy.max()))
    hier = {}

    def load_hier(key):
        d = json.loads(http.get_bytes("%s/ept-hierarchy/%s.json" % (root, key),
                                      os.path.join(cdir, "ept-hierarchy", key + ".json")))
        hier.update({k: v for k, v in d.items() if not (k in hier and hier[k] > 0)})

    load_hier("0-0-0-0")
    stack, chunks, nodes = [(0, 0, 0, 0)], [], 0
    while stack:
        d, x, y, z = stack.pop()
        key = "%d-%d-%d-%d" % (d, x, y, z)
        if key not in hier:
            continue
        if hier[key] == -1:
            load_hier(key)
        if hier.get(key, 0) <= 0 or not lidar._overlaps_xy(lidar.node_bounds(b, d, x, y, z), q):
            continue
        if d >= min_depth:
            nodes += 1
            if nodes > max_nodes:
                raise RuntimeError("more than %d lidar nodes" % max_nodes)
            raw = http.get_bytes("%s/ept-data/%s.laz" % (root, key), os.path.join(cdir, "ept-data", key + ".laz"))
            las = laspy.read(io.BytesIO(raw))
            X, Y = np.asarray(las.x), np.asarray(las.y)
            keep = (X >= q[0]) & (X <= q[2]) & (Y >= q[1]) & (Y <= q[3])
            if keep.any():
                chunks.append((X[keep], Y[keep], np.asarray(las.z)[keep], np.asarray(las.classification)[keep],
                               np.asarray(las.number_of_returns)[keep], np.asarray(las.return_number)[keep],
                               np.asarray(las.intensity)[keep], np.full(int(keep.sum()), d, np.uint8)))
        if d < max_depth:
            for i in range(8):
                stack.append((d + 1, 2 * x + (i & 1), 2 * y + ((i >> 1) & 1), 2 * z + ((i >> 2) & 1)))
    cols = [np.concatenate([c[i] for c in chunks]) for i in range(8)]
    ex, ny = proj.webmerc_to_city(cols[0], cols[1])
    log("lidar: %d nodes, %d points in the box (depth %d..%d)" % (nodes, len(ex), min_depth, max_depth))
    return {"x_ft": ex, "y_ft": ny, "z_m": cols[2], "cls": cols[3].astype(np.uint8), "nr": cols[4].astype(np.uint8),
            "rn": cols[5].astype(np.uint8), "intensity": cols[6], "depth": cols[7], "nodes": nodes}
