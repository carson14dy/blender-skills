#!/usr/bin/env python3
"""Send Python to the open Blender through the MCP for Blender add-on and print what it printed.

Host-side (plain Python 3.9+, no bpy). The add-on (formerly blender-mcp) listens on 127.0.0.1:9876
while Blender is open; no MCP server entry is needed for this script.

Usage:
  python blender_send.py FILE.py [MORE.py ...]     # run files in order, stop at the first error
  python blender_send.py -c "print(bpy.data.filepath)"
  python blender_send.py --ping                    # is Blender listening? prints its version
  options: [--port 9876] [--host 127.0.0.1] [--timeout 1800] [--fresh]
Names defined by one call stay defined for the next one (same Blender session), so a numbered
pipeline can be sent file by file. --fresh runs in an empty namespace instead.
Prints the code's output, then one JSON line. Exit code: 0 ok, 1 the code raised, 2 no connection.
"""
import argparse
import json
import os
import socket
import sys

# The add-on runs each request in a new namespace. Keep ours in a module so helpers survive
# between calls and across file loads.
WRAP = (
    "import bpy, sys, types\n"
    "_m = sys.modules.setdefault('_blender_send_ns', types.ModuleType('_blender_send_ns'))\n"
    "if {fresh!r}: _m.__dict__.clear()\n"
    "_m.__dict__.update(bpy=bpy, __name__='__main__', __file__={name!r})\n"
    "exec(compile({code!r}, {name!r}, 'exec'), _m.__dict__)\n"
)


def send(code, name="<send>", host="127.0.0.1", port=9876, timeout=1800, fresh=False):
    """Run `code` in Blender. Returns {"ok": bool, "out": str, "error": str}."""
    req = {"type": "execute_code", "params": {"code": WRAP.format(fresh=fresh, name=name, code=code)}}
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(json.dumps(req).encode("utf-8"))
        buf = b""
        while True:
            chunk = s.recv(1 << 16)
            if not chunk:
                break
            buf += chunk
            try:
                resp = json.loads(buf.decode("utf-8"))
                break
            except ValueError:
                continue
        else:
            resp = None
    if not buf:
        return {"ok": False, "out": "", "error": "Blender closed the connection without answering"}
    if resp is None:
        resp = json.loads(buf.decode("utf-8"))
    if resp.get("status") == "success":
        result = resp.get("result")
        return {"ok": True, "out": result.get("result", "") if isinstance(result, dict) else str(result or ""),
                "error": ""}
    return {"ok": False, "out": "", "error": str(resp.get("message", resp))}


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("files", nargs="*", help="Python files to run in Blender, in order")
    p.add_argument("-c", dest="code", help="one line of Python instead of files")
    p.add_argument("--ping", action="store_true", help="check the connection and print Blender's version")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9876)
    p.add_argument("--timeout", type=float, default=1800, help="seconds to wait for each answer")
    p.add_argument("--fresh", action="store_true", help="forget names from earlier calls first")
    a = p.parse_args()
    if a.ping:
        jobs = [("<ping>", "print(bpy.app.version_string)")]
    elif a.code:
        jobs = [("<send>", a.code)]
    elif a.files:
        jobs = [(os.path.abspath(f), open(f, encoding="utf-8").read()) for f in a.files]  # __file__ for Blender
    else:
        p.print_usage()
        return 1
    done = []
    for i, (name, code) in enumerate(jobs):
        try:
            r = send(code, name, a.host, a.port, a.timeout, a.fresh and i == 0)
        except OSError as e:
            print(json.dumps({"ok": False, "error": f"no Blender on {a.host}:{a.port} ({e}). Open Blender and "
                              "start the MCP for Blender add-on (N panel > MCP for Blender)."}))
            return 2
        if r["out"]:
            print(r["out"], end="" if r["out"].endswith("\n") else "\n")
        if not r["ok"]:
            print(json.dumps({"ok": False, "failed": name, "ran": done, "error": r["error"][-3000:]}))
            return 1
        done.append(name)
    print(json.dumps({"ok": True, "ran": done}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
