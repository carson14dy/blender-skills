"""Stand-in for the blender-mcp addon, for sessions without Blender's UI.

Listens on 127.0.0.1:9876 (or the port given) and answers
{"type": "execute_code", "params": {"code": ...}} the way the addon does,
running the code with real bpy (pip install bpy) and returning stdout.
Lets roof-blender.mjs run through its MCP path in a cloud session:

    $LAB_BPY_PYTHON lab/tools/mock_blender_mcp.py [port] &
    node roof-blender/scripts/roof-blender.mjs demo
"""
import contextlib
import io
import json
import socket
import sys
import traceback

import bpy

port = int(sys.argv[1]) if len(sys.argv) > 1 else 9876
bpy.ops.wm.read_factory_settings(use_empty=True)
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(1)
print(f"mock blender-mcp listening on {port} (Blender {bpy.app.version_string})", flush=True)
while True:
    conn, _ = srv.accept()
    buf = b""
    req = None
    while True:
        chunk = conn.recv(1 << 20)
        if not chunk:
            break
        buf += chunk
        try:
            req = json.loads(buf.decode())
            break
        except ValueError:
            continue
    out = io.StringIO()
    try:
        if not req or req.get("type") != "execute_code":
            raise ValueError("only execute_code is supported by this stand-in")
        with contextlib.redirect_stdout(out):
            exec(req["params"]["code"], {"bpy": bpy, "__name__": "mcp"})
        resp = {"status": "success", "result": {"executed": True, "result": out.getvalue()}}
    except Exception as e:  # report like the addon does
        resp = {"status": "error", "message": f"{e}\n{traceback.format_exc()[-800:]}"}
    conn.sendall(json.dumps(resp).encode())
    conn.close()
