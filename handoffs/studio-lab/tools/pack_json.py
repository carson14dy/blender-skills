#!/usr/bin/env python3
"""Wrap binary files (GLB tiles, SPZ splats) as base64 JSON, because the artifact host serves only
web types (.json, .js, images ...), not .glb or .spz.

    python3 tools/pack_json.py out/lab/tiles/*.glb out/lab/splat/*.spz

`name.glb` becomes `name.glb.json`: {"packed": "base64", "mime": ..., "bytes": n, "sha1": ..., "base64": ...}
and the binary is removed. The Lab decodes it in the browser (js/lab.js, unpackJson).
"""
import base64
import hashlib
import json
import os
import sys

MIME = {".glb": "model/gltf-binary", ".spz": "application/x-spz"}


def pack(path, remove=True):
    data = open(path, "rb").read()
    ext = os.path.splitext(path)[1].lower()
    obj = {"packed": "base64", "mime": MIME.get(ext, "application/octet-stream"), "name": os.path.basename(path),
           "bytes": len(data), "sha1": hashlib.sha1(data).hexdigest(), "base64": base64.b64encode(data).decode("ascii")}
    out = path + ".json"
    with open(out, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    if remove:
        os.remove(path)
    return out, len(data), os.path.getsize(out)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        o, a, b = pack(p)
        print("%s: %d -> %d bytes" % (o, a, b))
