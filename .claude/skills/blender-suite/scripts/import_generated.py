"""Import a generated GLB into Blender and make it ready to edit: real size, on the ground, and welded along its texture seams.

Works on GLBs from trellis_generate.py or from a web generator. Generators split the mesh at UV seams and
fit it in a 1-unit box around the world origin. This welds the seams, so the mesh is one surface again and
UVs are unchanged, then scales and grounds it with no transforms left over. It all goes in the GEN_<name>
collection, and re-running replaces that collection only. Skeletons aren't supported.
Usage:
  blender -b f.blend -P import_generated.py -- --glb model.glb [--name Helmet] [--height 0.28] [--no-ground] [--no-weld] [--save out.blend]
  MCP: import import_generated as g; print(g.run(glb="C:/work/model.glb", height=0.28))
--height is the real height in meters. Without it the size is arbitrary. Returns the object names (pass them
to qa_check.py), tris, separate parts, dimensions, materials, texture sizes and warnings.
"""
import os
import re
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

WELD_DISTANCE = 1e-5  # relative to the generator's 1-unit box


def _clean(text):
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)).strip("_")[:60]
    return text or "Generated"


def _remove_collection(col):
    for ob in list(col.objects):
        data = ob.data
        bpy.data.objects.remove(ob)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
    bpy.data.collections.remove(col)


def _weld(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD_DISTANCE)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def _parts(me):
    """Count the connected pieces of a mesh."""
    parent = list(range(len(me.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    return len({find(i) for i in range(len(parent))})


def _bounds(obs):
    pts = [v.co for ob in obs for v in ob.data.vertices]
    lo = Vector(min(p[i] for p in pts) for i in range(3))
    hi = Vector(max(p[i] for p in pts) for i in range(3))
    return lo, hi


def run(glb=None, name=None, height=None, no_ground=False, no_weld=False, **_):
    if not glb or not os.path.isfile(bpy.path.abspath(glb)):
        raise ValueError(f"GLB not found: {glb}")
    if height is not None and not 0 < float(height) <= 1000:
        raise ValueError("--height must be above 0, in meters")
    bx.object_mode()
    name = _clean(name or os.path.splitext(os.path.basename(glb))[0])
    old = bpy.data.collections.get(f"GEN_{name}")
    if old:
        _remove_collection(old)
    before = set(bpy.data.objects)
    images_before = set(bpy.data.images)
    bpy.ops.import_scene.gltf(filepath=bpy.path.abspath(glb))
    new = [o for o in bpy.data.objects if o not in before]
    if any(o.type == "ARMATURE" for o in new):
        for ob in new:
            bpy.data.objects.remove(ob)
        raise ValueError("this GLB has a skeleton. Import it with Blender's glTF importer instead")
    obs = [o for o in new if o.type == "MESH" and len(o.data.vertices)]
    if not obs:
        raise ValueError("no mesh found in this GLB")
    col = bpy.data.collections.new(f"GEN_{name}")
    bpy.context.scene.collection.children.link(col)
    bpy.context.view_layer.update()
    for ob in obs:  # flatten any transforms into the mesh
        world = ob.matrix_world.copy()
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        ob.parent = None
        ob.data.transform(world)
        ob.matrix_world = Matrix.Identity(4)
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        col.objects.link(ob)
    for ob in new:
        if ob not in obs:
            bpy.data.objects.remove(ob)
    if not no_weld:
        for ob in obs:
            _weld(ob)
    lo, hi = _bounds(obs)
    warnings = []
    size = hi - lo
    factor = 1.0
    if height is not None and size.z > 1e-9:
        factor = float(height) / size.z
    elif height is None:
        warnings.append("no --height given, so the size is arbitrary")
    # Center on X and Y, and stand it on Z = 0 unless told not to
    offset = Vector(((lo.x + hi.x) / -2, (lo.y + hi.y) / -2, -lo.z if not no_ground else 0))
    move = Matrix.Scale(factor, 4) @ Matrix.Translation(offset)
    for i, ob in enumerate(obs):
        ob.data.transform(move)
        ob.data.update()
        ob.name = name if i == 0 else f"{name}_{i:02d}"
        ob.data.name = ob.name
    for image in set(bpy.data.images) - images_before:
        image.name = f"{name}_{image.name}"
    lo, hi = _bounds(obs)
    parts = sum(_parts(ob.data) for ob in obs)
    if parts > 1:
        warnings.append(f"{parts} separate parts. Check that they belong apart, because qa_check.py reports them as floating")
    mats = sorted({s.material.name for ob in obs for s in ob.material_slots if s.material})
    images = {i.name: list(i.size) for i in set(bpy.data.images) - images_before}
    return {"ok": True, "collection": col.name, "objects": [o.name for o in obs], "tris": sum(bx.mesh_tris(o) for o in obs),
            "verts": sum(len(o.data.vertices) for o in obs), "parts": parts, "dimensions_m": [bx.r(v) for v in hi - lo],
            "materials": mats, "textures": images, "warnings": warnings}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--glb", required=True)
    p.add_argument("--name", default=None)
    p.add_argument("--height", type=float, default=None, help="real height in meters")
    p.add_argument("--no-ground", action="store_true")
    p.add_argument("--no-weld", action="store_true")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
