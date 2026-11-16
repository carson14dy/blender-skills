#!/usr/bin/env python3
"""Smoke-run every script in the skill: --help for tools, import for Blender scripts, compile for pipelines.

Usage:
  <python with bpy> tests/smoke.py                 (cloud: the pip bpy venv)
  blender -b --factory-startup --python-exit-code 1 -P tests/smoke.py      (local: real Blender)
Host tools (no bpy) run as `python X --help`. Blender scripts are imported with bpy loaded first and must
expose run(); their `-- --help` must print usage. Pipeline files are scene-specific, so they are only compiled.
Prints one line per failure, then one JSON line. Exit code: 0 ok, 1 failed.
"""
import ast
import json
import pathlib
import shutil
import subprocess
import sys

import bpy  # first: bmesh, mathutils and addon_utils only resolve after it under pip bpy

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOST_PY = shutil.which("python3") or shutil.which("python") or sys.executable
HELP_BOOT = ("import bpy, runpy, sys; p = sys.argv[1]; sys.argv = [p, '--', '--help']; "
             "runpy.run_path(p, run_name='__main__')")
NO_USAGE_OK = {"track_camera.py"}        # needs a window: answers with a JSON error instead of usage
fails, counts = [], {"host_help": 0, "bpy_import": 0, "bpy_help": 0, "compiled": 0, "shell_checked": 0}


def is_bpy_script(path):
    tree = ast.parse(path.read_text("utf-8"))
    return any(isinstance(n, ast.Import) and any(a.name == "bpy" for a in n.names) for n in tree.body)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    return p.returncode, p.stdout + p.stderr


for f in sorted((ROOT / "scripts").glob("*.py")):
    if f.name == "_bpyx.py":
        continue
    if not is_bpy_script(f):
        rc, out = run([HOST_PY, str(f), "--which" if f.name == "run_in_blender.py" else "--help"])
        ok = rc in (0, 2) if f.name == "run_in_blender.py" else rc == 0 and "usage" in out.lower()
        counts["host_help"] += 1
        if not ok:
            fails.append(f"host --help failed: scripts/{f.name}: rc={rc} {out[-300:]!r}")
        continue
    try:                                            # import in this process
        sys.path.insert(0, str(f.parent))
        ns = {"__name__": f"smoke_{f.stem}", "__file__": str(f)}
        exec(compile(f.read_text("utf-8"), str(f), "exec"), ns)
        assert callable(ns.get("run")), "no run()"
        counts["bpy_import"] += 1
    except Exception as e:
        fails.append(f"import failed: scripts/{f.name}: {type(e).__name__}: {e}")
        continue
    if bpy.app.binary_path:                         # real Blender
        cmd = [bpy.app.binary_path, "-b", "--factory-startup", "-P", str(f), "--", "--help"]
    else:                                           # pip bpy
        cmd = [sys.executable, "-c", HELP_BOOT, str(f)]
    rc, out = run(cmd)
    counts["bpy_help"] += 1
    if "usage:" not in out.lower() and not (f.name in NO_USAGE_OK and "@@JSON@@" in out):
        fails.append(f"-- --help printed no usage: scripts/{f.name}: rc={rc} {out[-300:]!r}")

for f in sorted([*ROOT.glob("pipelines/**/*.py"), *ROOT.glob("tests/*.py"), *ROOT.glob("assets/**/*.py")]):
    try:
        compile(f.read_text("utf-8"), str(f), "exec")
        counts["compiled"] += 1
    except SyntaxError as e:
        fails.append(f"syntax error: {f.relative_to(ROOT).as_posix()}: {e}")
for f in sorted(ROOT.glob("pipelines/**/*.json")):
    try:
        json.loads(f.read_text("utf-8"))
        counts["compiled"] += 1
    except ValueError as e:
        fails.append(f"bad JSON: {f.relative_to(ROOT).as_posix()}: {e}")
bash = shutil.which("bash")
for f in sorted(ROOT.glob("pipelines/**/*.sh")):
    if bash and sys.platform != "win32":
        rc, out = run([bash, "-n", str(f)])
        counts["shell_checked"] += 1
        if rc:
            fails.append(f"bash -n failed: {f.relative_to(ROOT).as_posix()}: {out[-200:]!r}")

for line in fails:
    print("FAIL", line)
print(json.dumps({"ok": not fails, "blender": bpy.app.version_string, **counts, "failures": len(fails)}))
sys.exit(1 if fails else 0)
