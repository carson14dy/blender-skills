"""Tiny GLB writer (no dependencies beyond numpy) and an ear-clipping polygon triangulator."""
import json
import struct

import numpy as np


def _pad(b, ch=b"\x00"):
    return b + ch * ((4 - len(b) % 4) % 4)


def write_glb(path, nodes, materials, extras=None, copyright=None):
    """nodes: [{name, extras?, primitives: [{pos Nx3, nrm Nx3?, col Nx3 uint8?, idx Mx3, mat int}]}]
    materials: [{name, color (r,g,b) linear 0..1, roughness, metallic, doubleSided?}]"""
    bin_parts, views, accs = [], [], []

    def add(arr, target, comp, typ, minmax=False, normalized=False):
        data = np.ascontiguousarray(arr).tobytes()
        off = sum(len(p) for p in bin_parts)
        bin_parts.append(_pad(data))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data), "target": target})
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": int(len(arr)), "type": typ}
        if normalized:
            a["normalized"] = True
        if minmax:
            a["min"] = [float(v) for v in arr.min(0)]
            a["max"] = [float(v) for v in arr.max(0)]
        accs.append(a)
        return len(accs) - 1

    gl_nodes, gl_meshes = [], []
    for n in nodes:
        prims = []
        for p in n["primitives"]:
            attrs = {"POSITION": add(p["pos"].astype(np.float32), 34962, 5126, "VEC3", minmax=True)}
            if p.get("nrm") is not None:
                attrs["NORMAL"] = add(p["nrm"].astype(np.float32), 34962, 5126, "VEC3")
            if p.get("col") is not None:
                c = np.concatenate([p["col"].astype(np.uint8), np.full((len(p["col"]), 1), 255, np.uint8)], 1)
                attrs["COLOR_0"] = add(c, 34962, 5121, "VEC4", normalized=True)
            idx = p["idx"].astype(np.uint32).reshape(-1)
            prims.append({"attributes": attrs, "indices": add(idx, 34963, 5125, "SCALAR"), "material": p["mat"]})
        gl_meshes.append({"name": n["name"], "primitives": prims})
        node = {"name": n["name"], "mesh": len(gl_meshes) - 1}
        if n.get("extras"):
            node["extras"] = n["extras"]
        gl_nodes.append(node)
    mats = []
    for m in materials:
        mats.append({"name": m["name"], "doubleSided": bool(m.get("doubleSided", False)), "pbrMetallicRoughness": {
            "baseColorFactor": list(m["color"]) + [1.0], "metallicFactor": m.get("metallic", 0.0),
            "roughnessFactor": m.get("roughness", 0.9)}})
    binary = b"".join(bin_parts)
    gltf = {"asset": {"version": "2.0", "generator": "roof-studio-lab tools/glb.py"},
            "scene": 0, "scenes": [{"nodes": list(range(len(gl_nodes)))}], "nodes": gl_nodes,
            "meshes": gl_meshes, "materials": mats, "accessors": accs, "bufferViews": views,
            "buffers": [{"byteLength": len(binary)}]}
    if copyright:
        gltf["asset"]["copyright"] = copyright
    if extras:
        gltf["asset"]["extras"] = extras
    js = _pad(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


def newell_normal(poly):
    p = np.asarray(poly, float)
    q = np.roll(p, -1, 0)
    n = np.array([((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])).sum(),
                  ((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])).sum(),
                  ((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1])).sum()])
    ln = np.linalg.norm(n)
    return n / ln if ln > 1e-12 else None


def earclip(poly2d):
    """Triangulate a simple polygon (Nx2, any winding). Returns list of index triples, CCW."""
    p = np.asarray(poly2d, float)
    n = len(p)
    if n < 3:
        return []
    area = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    idx = list(range(n)) if area > 0 else list(range(n))[::-1]
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        m = len(idx)
        clipped = False
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            a, b, c = p[i0], p[i1], p[i2]
            if cross(a, b, c) <= 1e-12:
                continue
            ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                q = p[j]
                if cross(a, b, q) >= -1e-12 and cross(b, c, q) >= -1e-12 and cross(c, a, q) >= -1e-12:
                    ok = False
                    break
            if ok:
                tris.append((i0, i1, i2))
                idx.pop(k)
                clipped = True
                break
        if not clipped:  # degenerate: fan the rest
            for k in range(1, len(idx) - 1):
                tris.append((idx[0], idx[k], idx[k + 1]))
            return tris
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris
