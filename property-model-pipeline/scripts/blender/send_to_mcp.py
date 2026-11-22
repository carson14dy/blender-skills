#!/usr/bin/env python3
"""Run a Blender script inside a running Blender via the blender-mcp addon socket (default port 9876).

    python3 send_to_mcp.py build_model.py -- --model /abs/model.json --out /abs/out --keep-scene
    python3 send_to_mcp.py measure_mesh.py -- --object "Photogrammetry mesh" --out /abs/measure.json

Arguments after `--` are injected as the PM_ARGS global the scripts read. Use absolute paths:
Blender's working directory is not this shell's. Add --keep-scene to build_model.py so the
user's open scene is not wiped.
"""
import json
import os
import socket
import sys


def send(code, port=9876, host="localhost", timeout=600):
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(json.dumps({"type": "execute_code", "params": {"code": code}}).encode())
    buf = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
        try:
            return json.loads(buf.decode())
        except ValueError:
            continue
    return json.loads(buf.decode() or "{}")


def main():
    argv = sys.argv[1:]
    port = int(os.environ.get("BLENDER_MCP_PORT", "9876"))
    if not argv:
        sys.exit(__doc__)
    script = argv[0]
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    path = script if os.path.exists(script) else os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    code = f"PM_ARGS = {extra!r}\n" + open(path).read()
    print(json.dumps(send(code, port), indent=2)[:4000])


if __name__ == "__main__":
    main()
