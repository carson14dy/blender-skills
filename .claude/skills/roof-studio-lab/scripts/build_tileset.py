#!/usr/bin/env python3
"""Build a small local 3D Tiles 1.1 tileset of the neighbourhood around a measured house.

Inputs: out/lab/data/site.json (from align_house.py), the City of Sioux Falls 3D building solids
(Community/MapServer/66, CC BY 4.0) inside a square of +-radius metres, USGS 3DEP lidar ground
returns for a terrain mesh, and optionally NAIP 2025 colours for the terrain vertices.

Output (out/lab/tiles/):
  tileset.json       3D Tiles 1.1, root.transform = ENU -> ECEF at the site origin (real georeference)
  lod0.glb           every building as a box (oriented min-area rectangle x eave height), LOD 0
  q0..q3.glb         the full city solids, split in four quadrants, LOD 1 (REPLACE refinement)
  subject.glb        the city solid of the measured house itself (for the alignment check)
  ground.glb         3DEP ground mesh with NAIP vertex colours, a hole where the studio's own terrain is

Content is glTF Y-up (x = east, y = up, z = -north); 3D Tiles rotates it to Z-up and applies the
root transform. City requests: 5 records per request, 1 s apart, cached forever (skill rules).

    python3 tools/build_tileset.py --radius 200
"""
import argparse
import hashlib
import math
import os

import numpy as np
from scipy import interpolate

from common import (ATTRIBUTION, CACHE, DATA, FT_US, OUT, Site, cityapi, enu_to_ecef_matrix, esri,
                    geodetic_to_ecef, http, log, proj, write_json)
from glb import earclip, newell_normal, write_glb
import ept

ROOF = {"name": "City roof", "color": (0.32, 0.30, 0.29), "roughness": 0.85}
WALL = {"name": "City wall", "color": (0.78, 0.74, 0.66), "roughness": 0.9}
BOX = {"name": "City block (LOD0)", "color": (0.66, 0.66, 0.68), "roughness": 0.9}
GROUND = {"name": "3DEP ground (NAIP colour)", "color": (1.0, 1.0, 1.0), "roughness": 1.0}
SUBJ = {"name": "City solid of this house", "color": (0.95, 0.35, 0.2), "roughness": 0.6}


def fetch_solids(h, site, radius):
    R = radius / FT_US
    env = "%.2f,%.2f,%.2f,%.2f" % (site.ox - R, site.oy - R, site.ox + R, site.oy + R)
    tag = hashlib.sha1(env.encode()).hexdigest()[:10]
    feats, k = [], 0
    while True:
        d = h.get_json(cityapi.SOLID_LAYER + "/query", {
            "geometry": env, "geometryType": "esriGeometryEnvelope", "inSR": 32164, "outSR": 32164,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "OBJECTID", "returnGeometry": "true",
            "returnZ": "true", "orderByFields": "OBJECTID", "resultOffset": k * cityapi.MAX_RECORDS,
            "resultRecordCount": cityapi.MAX_RECORDS},
            os.path.join(CACHE, "_lab", "solids-%s-p%03d.json" % (tag, k)))
        got = d.get("features", [])
        feats += got
        if len(got) < cityapi.MAX_RECORDS:
            break
        k += 1
    log("city solids: %d in +-%d m (%d requests or cache hits)" % (len(feats), radius, k + 1))
    return feats


class Frame:
    """True ENU at the site origin (WGS84 ellipsoid), from city feet + NAVD88 metres."""

    def __init__(self, site):
        self.site = site
        self.M = enu_to_ecef_matrix(site.lon, site.lat, site.d["originEllipsoidM"])
        self.Minv = np.linalg.inv(self.M)
        self.N = site.d["geoidM"]

    def from_city(self, x_ft, y_ft, z_navd_m):
        lon, lat = proj.city_to_lonlat(np.asarray(x_ft), np.asarray(y_ft))
        ecef = geodetic_to_ecef(lon, lat, np.asarray(z_navd_m) + self.N)
        h = np.concatenate([ecef, np.ones((len(ecef), 1))], 1)
        return (h @ self.Minv.T)[:, :3], lon, lat


def to_yup(p):
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)


def building_mesh(faces_enu, centroid):
    """Faces (list of Nx3 ENU) -> roof and wall primitives (Y-up positions, flat normals, CCW)."""
    out = {"roof": ([], [], []), "wall": ([], [], [])}
    for f in faces_enu:
        n = newell_normal(f)
        if n is None:
            continue
        if n[2] < -0.3:  # floor / base under ground
            if (f[:, 2].mean() - centroid[2]) < 0:
                continue
            n = -n
        kind = "roof" if abs(n[2]) >= 0.3 else "wall"
        if kind == "roof" and n[2] < 0:
            n = -n
        if kind == "wall" and np.dot(n[:2], f[:, :2].mean(0) - centroid[:2]) < 0:
            n = -n
        u = np.cross([0, 0, 1.0], n) if abs(n[2]) < 0.9 else np.cross([1.0, 0, 0], n)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        p2 = np.stack([(f - f[0]) @ u, (f - f[0]) @ v], 1)
        tris = earclip(p2)
        if not tris:
            continue
        P, Nn, I = out[kind]
        base = sum(len(x) for x in P)
        P.append(f)
        Nn.append(np.repeat(n[None], len(f), 0))
        I.append(np.asarray(tris) + base)
    prims = {}
    for kind, (P, Nn, I) in out.items():
        if P:
            pos = np.concatenate(P)
            prims[kind] = (to_yup(pos), to_yup(np.concatenate(Nn)), np.concatenate(I))
    return prims


def box_mesh(pts_enu, z0, z1):
    """Oriented minimum-area rectangle of the plan points, extruded z0..z1 (no floor)."""
    from scipy.spatial import ConvexHull
    xy = pts_enu[:, :2]
    hull = xy[ConvexHull(xy).vertices]
    best = None
    for i in range(len(hull)):
        e = hull[(i + 1) % len(hull)] - hull[i]
        a = math.atan2(e[1], e[0])
        R = np.array([[math.cos(a), math.sin(a)], [-math.sin(a), math.cos(a)]])
        r = hull @ R.T
        lo, hi = r.min(0), r.max(0)
        area = np.prod(hi - lo)
        if best is None or area < best[0]:
            best = (area, R, lo, hi)
    _, R, lo, hi = best
    corners = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]]) @ R  # back to ENU
    P, N, I = [], [], []
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        d = b - a
        n = np.array([d[1], -d[0], 0.0]); n /= np.linalg.norm(n)
        q = np.array([[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]])
        base = len(P) * 4
        P.append(q); N.append(np.repeat(n[None], 4, 0)); I.append(np.array([[0, 1, 2], [0, 2, 3]]) + base)
    top = np.array([[c[0], c[1], z1] for c in corners])
    base = len(P) * 4
    P.append(top); N.append(np.repeat(np.array([[0, 0, 1.0]]), 4, 0)); I.append(np.array([[0, 1, 2], [0, 2, 3]]) + base)
    pos = np.concatenate(P)
    return to_yup(pos), to_yup(np.concatenate(N)), np.concatenate(I)


def bvol(pos_yup, pad=0.5):
    """3D Tiles box (tile frame is Z-up ENU) around Y-up positions."""
    p = np.stack([pos_yup[:, 0], -pos_yup[:, 2], pos_yup[:, 1]], 1)
    lo, hi = p.min(0) - pad, p.max(0) + pad
    c, hlf = (lo + hi) / 2, (hi - lo) / 2
    return {"box": [round(float(v), 3) for v in [*c, hlf[0], 0, 0, 0, hlf[1], 0, 0, 0, hlf[2]]]}


def ground_mesh(h, frame, site, radius, cell, hole, naip):
    R = (radius + 2 * cell) / FT_US
    pts = ept.fetch(h, (site.ox - R, site.oy - R, site.ox + R, site.oy + R), max_depth=10)
    g = pts["cls"] == 2
    enu, _, _ = frame.from_city(pts["x_ft"][g], pts["y_ft"][g], pts["z_m"][g])
    n = int(round(2 * radius / cell)) + 1
    xs = np.linspace(-radius, radius, n)
    ix = np.clip(np.round((enu[:, 0] + radius) / cell).astype(int), 0, n - 1)
    iy = np.clip(np.round((enu[:, 1] + radius) / cell).astype(int), 0, n - 1)
    s = np.zeros((n, n)); c = np.zeros((n, n))
    np.add.at(s, (iy, ix), enu[:, 2]); np.add.at(c, (iy, ix), 1)
    have = c > 0
    Z = np.where(have, s / np.maximum(c, 1), np.nan)
    X, Y = np.meshgrid(xs, xs)
    if (~have).any():  # under buildings: interpolate from the cells around
        fill = interpolate.griddata(np.column_stack([X[have], Y[have]]), Z[have], (X[~have], Y[~have]), "linear")
        near = interpolate.griddata(np.column_stack([X[have], Y[have]]), Z[have], (X[~have], Y[~have]), "nearest")
        Z[~have] = np.where(np.isnan(fill), near, fill)
    Z -= 0.03  # sit just under the studio's own terrain where they meet
    pos = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    gy, gx = np.gradient(Z, cell)
    nrm = np.column_stack([-gx.ravel(), -gy.ravel(), np.ones(n * n)])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    col = None
    if naip is not None:
        # vertex colour = NAIP pixel at the vertex (mean of a 3 x 3 block, about 1 m)
        cx, cy = site.enu_to_city(X.ravel(), Y.ravel())
        lon, lat = proj.city_to_lonlat(cx, cy)
        acc = np.zeros((n * n, 3))
        for dx in (-0.3, 0, 0.3):
            for dy in (-0.3, 0, 0.3):
                acc += naip(lon + dx / 80000.0, lat + dy / 111000.0)
        # glTF vertex colours are linear: NAIP pixels are sRGB-encoded
        c = acc / 9.0 / 255.0
        lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        col = np.clip(np.round(lin * 255.0), 0, 255).astype(np.uint8)
    tris = []
    for j in range(n - 1):
        for i in range(n - 1):
            cxm, cym = (xs[i] + xs[i + 1]) / 2, (xs[j] + xs[j + 1]) / 2
            if abs(cxm) < hole and abs(cym) < hole:
                continue
            a = j * n + i
            tris += [(a, a + 1, a + n + 1), (a, a + n + 1, a + n)]
    return to_yup(pos), to_yup(nrm), np.array(tris), col, int(g.sum())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radius", type=float, default=200.0, help="half-size of the square, metres")
    ap.add_argument("--ground-cell", type=float, default=3.0)
    ap.add_argument("--hole", type=float, default=33.5, help="half-size of the studio terrain square to leave open")
    ap.add_argument("--no-naip", action="store_true")
    a = ap.parse_args()
    site = Site.load()
    frame = Frame(site)
    h = http(log)
    feats = fetch_solids(h, site, a.radius)
    tdir = os.path.join(OUT, "lab", "tiles")
    os.makedirs(tdir, exist_ok=True)
    quads = {k: [] for k in range(4)}
    boxes, subject, stats = [], None, {"buildings": 0, "faces": 0}
    for f in feats:
        oid = f["attributes"]["OBJECTID"]
        try:
            faces, shape = esri.decode_feature(f)
        except esri.MultipatchError:
            continue
        allp = np.concatenate(faces)
        enu_all, _, _ = frame.from_city(allp[:, 0], allp[:, 1], allp[:, 2] * FT_US)
        cuts = np.cumsum([len(x) for x in faces])[:-1]
        faces_enu = np.split(enu_all, cuts)
        cen = enu_all.mean(0)
        prims = building_mesh(faces_enu, cen)
        if not prims:
            continue
        stats["buildings"] += 1
        stats["faces"] += len(faces)
        roofz = prims["roof"][0][:, 1] if "roof" in prims else enu_all[:, 2]
        node = {"name": "bldg-%d" % oid, "extras": {"oid": oid, "topM": round(float(enu_all[:, 2].max()), 2)}, "prims": prims}
        if oid == site.d["solidOid"]:
            subject = node
            continue
        quads[(1 if cen[0] >= 0 else 0) + (2 if cen[1] >= 0 else 0)].append(node)
        z0 = float(np.percentile(enu_all[:, 2], 2))
        z1 = float(np.median(roofz))
        boxes.append(box_mesh(enu_all, z0, max(z1, z0 + 2.5)))
    mats = [ROOF, WALL, BOX, GROUND, SUBJ]
    files, children = {}, []

    def emit(name, nodes_):
        n_out, allpos, tris = [], [], 0
        for nd in nodes_:
            pr = []
            for kind, (pos, nrm, idx) in nd["prims"].items():
                m = 4 if nd is subject else (0 if kind == "roof" else 1)
                pr.append({"pos": pos, "nrm": nrm, "idx": idx, "mat": m})
                allpos.append(pos); tris += len(idx)
            n_out.append({"name": nd["name"], "extras": nd["extras"], "primitives": pr})
        size = write_glb(os.path.join(tdir, name), n_out, mats, copyright=ATTRIBUTION)
        files[name] = {"bytes": size, "triangles": tris, "meshes": len(n_out)}
        return np.concatenate(allpos)

    for q in range(4):
        if not quads[q]:
            continue
        pos = emit("q%d.glb" % q, quads[q])
        children.append({"boundingVolume": bvol(pos), "geometricError": 0, "content": {"uri": "q%d.glb" % q}})
    # LOD0: one mesh of boxes
    bp = np.concatenate([b[0] for b in boxes]); bn = np.concatenate([b[1] for b in boxes])
    off = np.cumsum([0] + [len(b[0]) for b in boxes[:-1]])
    bi = np.concatenate([b[2] + o for b, o in zip(boxes, off)])
    size = write_glb(os.path.join(tdir, "lod0.glb"), [{"name": "city-blocks-lod0", "primitives": [
        {"pos": bp, "nrm": bn, "idx": bi, "mat": 2}]}], mats, copyright=ATTRIBUTION)
    files["lod0.glb"] = {"bytes": size, "triangles": int(len(bi)), "meshes": 1}
    root_children = [{"boundingVolume": bvol(bp), "geometricError": 4.0, "refine": "REPLACE",
                      "content": {"uri": "lod0.glb"}, "children": children}]
    if subject:
        pos = emit("subject.glb", [subject])
        root_children.append({"boundingVolume": bvol(pos), "geometricError": 0, "content": {"uri": "subject.glb"}})
    naip = None
    if not a.no_naip:
        from naip import naip_window
        _, smp = naip_window(site, half_m=a.radius + 10)
        naip = smp.lonlat
    gp, gn, gi, gc, npts = ground_mesh(h, frame, site, a.radius, a.ground_cell, a.hole, naip)
    size = write_glb(os.path.join(tdir, "ground.glb"), [{"name": "ground-3dep", "primitives": [
        {"pos": gp, "nrm": gn, "col": gc, "idx": gi, "mat": 3}]}], mats, copyright=ATTRIBUTION)
    files["ground.glb"] = {"bytes": size, "triangles": int(len(gi)), "meshes": 1, "lidarGroundPoints": npts}
    root_children.insert(0, {"boundingVolume": bvol(gp), "geometricError": 0, "content": {"uri": "ground.glb"}})
    allb = np.concatenate([gp, bp])
    M = frame.M
    tileset = {
        "asset": {"version": "1.1", "tilesetVersion": "lab-1",
                  "extras": {"attribution": ATTRIBUTION, "site": site.d["address"]}},
        "geometricError": 60.0,
        "root": {"transform": [round(float(v), 6) for v in M.T.reshape(-1)],  # column-major
                 "boundingVolume": bvol(allb, pad=2.0), "geometricError": 30.0, "refine": "ADD",
                 "children": root_children},
    }
    write_json(os.path.join(tdir, "tileset.json"), tileset, indent=1)
    files["tileset.json"] = {"bytes": os.path.getsize(os.path.join(tdir, "tileset.json"))}
    summary = {"radiusM": a.radius, "buildings": stats["buildings"], "cityFaces": stats["faces"],
               "tiles": len([c for c in root_children]) + len(children), "files": files,
               "totalBytes": sum(v["bytes"] for v in files.values()),
               "subjectOid": site.d["solidOid"], "lod": "LOD0 boxes (geometricError 4 m) -> LOD1 city solids (0)",
               "attribution": ATTRIBUTION}
    write_json(os.path.join(DATA, "tiles.json"), summary, indent=1)
    # the artifact host serves no .glb/.spz: ship each binary as base64 JSON (<name>.glb.json)
    from pack_json import pack
    for name in [k for k in files if k.endswith(".glb")]:
        _, _, packed = pack(os.path.join(tdir, name))
        files[name]["packedBytes"] = packed
    summary["totalPackedBytes"] = sum(v.get("packedBytes", v["bytes"]) for v in files.values())
    write_json(os.path.join(DATA, "tiles.json"), summary, indent=1)
    log("tileset: %d buildings, %s, total %.0f KB" % (stats["buildings"],
        {k: (v["bytes"] // 1024, v.get("triangles")) for k, v in files.items()}, summary["totalBytes"] / 1024))


if __name__ == "__main__":
    main()
