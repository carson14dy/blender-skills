"""Minimal reader for the studio's embedded .gltf.json house models (one base64 buffer)."""
import base64
import json

import numpy as np

_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
_T = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}


def _quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def load_meshes(path):
    """Return a list of (node name, material name, positions Nx3 world, triangle indices Mx3)."""
    d = json.load(open(path))
    buf = base64.b64decode(d["buffers"][0]["uri"].split(",", 1)[1])

    def acc(i):
        a = d["accessors"][i]
        bv = d["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        n = _N[a["type"]]
        arr = np.frombuffer(buf, _T[a["componentType"]], a["count"] * n, off)
        return arr.reshape(-1, n) if n > 1 else arr

    out = []
    for node in d["nodes"]:
        if "mesh" not in node:
            continue
        m = np.eye(4)
        if "rotation" in node:
            m[:3, :3] = _quat_mat(node["rotation"])
        if "scale" in node:
            m[:3, :3] = m[:3, :3] @ np.diag(node["scale"])
        if "translation" in node:
            m[:3, 3] = node["translation"]
        for p in d["meshes"][node["mesh"]]["primitives"]:
            pos = acc(p["attributes"]["POSITION"]).astype(np.float64)
            pos = pos @ m[:3, :3].T + m[:3, 3]
            idx = acc(p["indices"]).astype(np.int64).reshape(-1, 3) if "indices" in p else \
                np.arange(len(pos)).reshape(-1, 3)
            mat = d["materials"][p["material"]]["name"] if "material" in p else ""
            out.append((node.get("name", ""), mat, pos, idx))
    return out
