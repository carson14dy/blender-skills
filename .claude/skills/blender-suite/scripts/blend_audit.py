"""Audit a .blend you did not make before trusting it: embedded scripts, scripted drivers, OSL nodes,
linked libraries, and missing or unpacked images.

Usage:
  blender -b --disable-autoexec FILE.blend -P blend_audit.py
  MCP: import blend_audit; print(blend_audit.run())
Read-only. `pass` is false when the file carries code that could run on load (text blocks registered as
modules, scripted drivers, OSL script nodes). Libraries and missing images are reported as warnings.
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _trees():
    """Every node tree: node groups plus the trees embedded in materials, worlds, lights and scenes."""
    for ng in bpy.data.node_groups:
        yield ng.name, ng
    for coll in (bpy.data.materials, bpy.data.worlds, bpy.data.lights):
        for d in coll:
            if getattr(d, "node_tree", None):
                yield d.name, d.node_tree


def run(limit=20):
    texts = [{"name": t.name, "chars": len(t.as_string()), "runs_on_load": bool(t.use_module)}
             for t in bpy.data.texts]
    drivers = []
    for d in bpy.data.all_ids:
        ad = getattr(d, "animation_data", None)
        for fc in (ad.drivers if ad else []):
            if fc.driver and fc.driver.type == "SCRIPTED":
                drivers.append({"id": d.name, "path": fc.data_path, "expression": fc.driver.expression[:80]})
    osl = [{"tree": name, "node": n.name} for name, tree in _trees() for n in tree.nodes
           if n.bl_idname == "ShaderNodeScript"]
    libs = sorted(lib.filepath for lib in bpy.data.libraries)
    files = [i for i in bpy.data.images if i.source in {"FILE", "SEQUENCE", "MOVIE", "TILED"}]
    missing = sorted({i.filepath for i in files
                      if not i.packed_file and not os.path.exists(bpy.path.abspath(i.filepath, library=i.library))})
    errors, warnings = [], []
    if any(t["runs_on_load"] for t in texts):
        errors.append("text blocks registered to run on load: "
                      f"{[t['name'] for t in texts if t['runs_on_load']][:limit]}")
    if drivers:
        errors.append(f"{len(drivers)} scripted drivers (Python expressions)")
    if osl:
        errors.append(f"{len(osl)} OSL script nodes")
    if texts and not errors:
        warnings.append(f"{len(texts)} text blocks: read them before running any")
    if libs:
        warnings.append(f"{len(libs)} linked libraries: audit each one too")
    if missing:
        warnings.append(f"{len(missing)} image files missing")
    return {"ok": True, "pass": not errors, "errors": errors, "warnings": warnings,
            "file": bpy.data.filepath or None,
            "autoexec_enabled": bool(bpy.context.preferences.filepaths.use_scripts_auto_execute),
            "texts": texts[:limit], "scripted_drivers": drivers[:limit], "osl_nodes": osl[:limit],
            "libraries": libs[:limit],
            "images": {"total": len(bpy.data.images), "packed": sum(1 for i in bpy.data.images if i.packed_file),
                       "missing": missing[:limit]},
            "counts": {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes),
                       "materials": len(bpy.data.materials), "collections": len(bpy.data.collections)}}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--limit", type=int, default=20, help="most entries listed per category")
    bx.cli(run, p)
