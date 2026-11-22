"""Run a blender-suite script on a saved .blend under pip bpy, which has no Blender executable for
run_in_blender.py --blend. Prints the script's own output (its @@JSON@@ line), so it pipes into build_log.py gate.

Usage: $LAB_BPY_PYTHON run_blend.py out/shed.blend <skill>/scripts/qa_check.py [-- script args]
"""
import runpy
import sys

import bpy

blend, script, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
bpy.ops.wm.open_mainfile(filepath=blend)
sys.argv = [script, "--", *(rest[1:] if rest[:1] == ["--"] else rest)]
runpy.run_path(script, run_name="__main__")
