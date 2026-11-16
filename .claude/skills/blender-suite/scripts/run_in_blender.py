#!/usr/bin/env python3
"""Run a skill script in headless Blender and print only its JSON result.

Host-side (system Python 3.9+, no bpy). Finds Blender automatically:
$BLENDER_EXE > PATH > standard install dirs (newest version wins).

Usage:
  python run_in_blender.py [--blend FILE] [--user-prefs] SCRIPT.py [-- script args]
  python run_in_blender.py --expr "import bpy; print(bpy.app.version_string)"
  python run_in_blender.py --which          # print the Blender path it would use
Exit code: 0 ok, 1 script error, 2 Blender not found.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

MARK = "@@JSON@@"


def _ver(path):
    m = re.search(r"(\d+)\.(\d+)", path)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blender():
    env = os.environ.get("BLENDER_EXE")
    if env and os.path.isfile(env):
        return env
    hit = shutil.which("blender")
    if hit:
        return hit
    pats = {
        "win32": [r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender *\blender.exe"),
                  r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"],
        "darwin": ["/Applications/Blender*.app/Contents/MacOS/Blender",
                   os.path.expanduser("~/Applications/Blender*.app/Contents/MacOS/Blender")],
    }.get(sys.platform, ["/usr/bin/blender", "/opt/blender*/blender", "/snap/bin/blender",
                         os.path.expanduser("~/blender*/blender")])
    found = [p for pat in pats for p in glob.glob(pat) if os.path.isfile(p)]
    return max(found, key=_ver) if found else None


# No Blender executable (cloud sessions): run the script in a Python that has the pip `bpy` module.
# bpy is imported first because bmesh, mathutils and addon_utils only resolve after it.
BPY_BOOT = (
    "import bpy, sys, runpy\n"
    "blend, mode, target = sys.argv[1:4]\n"
    "if blend: bpy.ops.wm.open_mainfile(filepath=blend)\n"
    "sys.argv = [target if mode == 'file' else '-c'] + sys.argv[4:]\n"
    "exec(compile(target, '<expr>', 'exec'), {'__name__': '__main__'}) if mode == 'expr' "
    "else runpy.run_path(target, run_name='__main__')\n"
)


def find_bpy_python():
    """A Python that has `bpy`: $BLENDER_BPY_PYTHON, else $LAB_BPY_PYTHON, else this one if it imports bpy."""
    for env in ("BLENDER_BPY_PYTHON", "LAB_BPY_PYTHON"):
        p = os.environ.get(env)
        if p and os.path.isfile(p):
            return p
    import importlib.util
    return sys.executable if importlib.util.find_spec("bpy") else None


def main():
    a = sys.argv[1:]
    rest = []
    if "--" in a:
        i = a.index("--")
        a, rest = a[:i], a[i + 1:]
    exe = find_blender()
    py = None if exe else find_bpy_python()
    if not exe and not py:
        print(json.dumps({"ok": False, "error": "Blender not found; set BLENDER_EXE (or BLENDER_BPY_PYTHON "
                                                 "to a Python that has the bpy module)"}))
        return 2
    if "--which" in a:
        print(exe or py)
        return 0
    blend = a[a.index("--blend") + 1] if "--blend" in a else ""
    scripts = [x for x in a if x.endswith(".py") and x != blend]
    if "--expr" not in a and not scripts:
        print(__doc__)
        return 1
    if exe:
        cmd = [exe, "-b"] + ([blend] if blend else [])
        if "--user-prefs" not in a:
            cmd.append("--factory-startup")
        cmd += ["--python-exit-code", "1"]
        cmd += ["--python-expr", a[a.index("--expr") + 1]] if "--expr" in a else ["-P", scripts[0]]
    elif "--expr" in a:
        cmd = [py, "-c", BPY_BOOT, blend, "expr", a[a.index("--expr") + 1]]
    else:
        cmd = [py, "-c", BPY_BOOT, blend, "file", scripts[0]]
    cmd += ["--"] + rest
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = [ln[len(MARK):] for ln in p.stdout.splitlines() if ln.startswith(MARK)]
    if out:
        print("\n".join(out))
    elif "--expr" in a:
        # free-form expression: show stdout minus Blender banner noise
        noise = ("Blender ", "Read prefs", "Read blend", "Blender quit", "Color management")
        print("\n".join(ln for ln in p.stdout.splitlines() if ln and not ln.startswith(noise)))
    if p.returncode != 0 and not out:
        tail = (p.stderr or p.stdout).strip().splitlines()[-15:]
        print(json.dumps({"ok": False, "returncode": p.returncode, "log_tail": tail}))
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
