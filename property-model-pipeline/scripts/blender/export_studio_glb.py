"""Export a measured model for web viewers / Roof Layer Studio: roof facets as meshes named "Roof F1..", walls
joined into "Walls"; glTF is Y-up with north = -Z.

    python export_studio_glb.py OUT/model_site.blend house.glb [--with-site] [--keep-lot-line] [--draco]
        [--roof-rgb R,G,B|#hex] [--wall-rgb R,G,B|#hex]              (bpy module, or blender -b -P ... -- args)

Kept: collections "Roof facets", "Walls", "Details" (add_details.py) and, with --with-site, "Site" (add_site.py).
Dropped by default (the studio must show the house, not QA geometry): the lot line ("Lot line*"), reference
ground ("Ground (grade)", "Ground ortho*"), labels (collection "Labels", objects named "Label*"), reference /
QA collections ("Reference data", "Roof edges", "LiDAR points", "Cameras"), objects flagged reference=True and
objects hidden from renders. --keep-lot-line keeps the lot line. Text that is part of the model (house numerals
on a plaque or pier) stays.

Materials: build_model's per-facet QA colours on the roof become a neutral shingle (--roof-rgb sets it); walls
keep the job's siding material (add_details.py colour) unless --wall-rgb is given; procedural colours are baked to
flat glTF colours. --draco asks the exporter for Draco mesh compression and checks that it happened (some bpy builds
have no Draco library: then the GLB is written uncompressed with a warning). Hosts that cannot serve .glb take the
same model as embedded glTF JSON (scripts/studio/glb_to_gltf_json.py, package_house.py).
"""
import json
import sys

try:
    import bpy
except ImportError:          # the pure helpers below are importable without Blender (tests)
    bpy = None

KEEP_COLLECTIONS = ("Roof facets", "Walls", "Details")
SITE_COLLECTION = "Site"
LOT_LINE_PREFIX = ("Lot line",)
REFERENCE_PREFIX = ("Ground (grade)", "Ground ortho", "LiDAR points", "Reference ")
LABEL_PREFIX = ("Label", "label ")
DROP_COLLECTIONS = ("Labels", "Reference data", "Roof edges", "LiDAR points", "Cameras")
QA_ROOF_MATERIAL = "Roof "        # build_model.py: "Roof 0", "Roof 1", ... (facet debug colours)
DEFAULT_ROOF_RGB = (0.2, 0.2, 0.21)


def drop_reason(name, collections, obj_type="MESH", keep_lot_line=False, hidden=False, reference=False):
    """Why an object is left out of the studio model (None = keep). Pure function of the object's name, the names
    of the collections it is linked to, its type, its hide_render flag and a 'reference' custom property."""
    if name.startswith(LOT_LINE_PREFIX):
        return None if keep_lot_line else "lot line"
    for c in collections:
        if c in DROP_COLLECTIONS:
            return f"collection {c}"
    if name.startswith(REFERENCE_PREFIX) or reference:
        return "reference object"
    if name.startswith(LABEL_PREFIX):
        return "label"
    if obj_type in ("CAMERA", "LIGHT", "EMPTY", "LIGHT_PROBE", "SPEAKER"):
        return obj_type.lower()
    if hidden:
        return "hidden from renders"
    return None


def parse_rgb(text):
    """'0.2,0.2,0.21' (linear) or '#7f7a6e' (sRGB hex) -> linear (r, g, b)."""
    t = text.strip()
    if t.startswith("#") and len(t) == 7:
        def lin(c):
            c = int(c, 16) / 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return tuple(round(lin(t[i:i + 2]), 4) for i in (1, 3, 5))
    v = tuple(float(x) for x in t.split(","))
    if len(v) != 3 or not all(0.0 <= x <= 1.0 for x in v):
        raise ValueError(f"colour {text!r}: expected R,G,B in 0..1 or #rrggbb")
    return v


def parse_args(argv):
    opts = {"with_site": False, "keep_lot_line": False, "draco": False, "roof_rgb": None, "wall_rgb": None}
    pos, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--with-site":
            opts["with_site"] = True
        elif a == "--keep-lot-line":
            opts["keep_lot_line"] = True
        elif a == "--draco":
            opts["draco"] = True
        elif a in ("--roof-rgb", "--wall-rgb"):
            opts[a[2:].replace("-", "_")] = parse_rgb(argv[i + 1])
            i += 1
        elif a.startswith("--"):
            raise SystemExit(f"unknown option {a}")
        else:
            pos.append(a)
        i += 1
    if len(pos) != 2:
        raise SystemExit("usage: export_studio_glb.py MODEL.blend OUT.glb [--with-site] [--keep-lot-line] [--draco]")
    return pos[0], pos[1], opts


def _pbr(name, rgb, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*rgb, 1)
    return m


def _bake_flat_colours():
    """glTF cannot carry procedural shading: each linked base colour becomes its mean / viewport colour."""
    for m in bpy.data.materials:
        if not m.use_nodes or not m.node_tree:
            continue
        b = m.node_tree.nodes.get("Principled BSDF")
        if not b or not b.inputs["Base Color"].is_linked:
            continue
        src = b.inputs["Base Color"].links[0].from_node
        if src.type == "VALTORGB":
            els = src.color_ramp.elements
            col = [sum(e.color[i] for e in els) / len(els) for i in range(4)]
        else:
            col = list(m.diffuse_color)
        m.node_tree.links.remove(b.inputs["Base Color"].links[0])
        b.inputs["Base Color"].default_value = col


def export(blend, out, with_site=False, keep_lot_line=False, draco=False, roof_rgb=None, wall_rgb=None):
    bpy.ops.wm.open_mainfile(filepath=blend)
    keep_cols = KEEP_COLLECTIONS + ((SITE_COLLECTION,) if with_site else ())
    keep, dropped = set(), {}
    for o in list(bpy.data.objects):
        cols = [c.name for c in o.users_collection]
        if not any(c in keep_cols for c in cols):
            continue
        why = drop_reason(o.name, cols, o.type, keep_lot_line, bool(o.hide_render), bool(o.get("reference", False)))
        if why:
            dropped.setdefault(why, []).append(o.name)
        else:
            keep.add(o.name)
    for o in list(bpy.data.objects):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)

    def coll(o):
        return o.users_collection[0].name if o.users_collection else ""

    roofs = sorted([o for o in bpy.data.objects if coll(o) == "Roof facets"], key=lambda o: o.name)
    roof_mat = _pbr("Roof shingle", roof_rgb or DEFAULT_ROOF_RGB, 0.9)
    for i, o in enumerate(roofs):
        o["facet"] = o.name
        o.name = f"Roof F{i + 1}"
        if o.type != "MESH":
            continue
        mats = [m for m in o.data.materials if m]
        if roof_rgb or not mats or all(m.name.startswith(QA_ROOF_MATERIAL) for m in mats):
            o.data.materials.clear()
            o.data.materials.append(roof_mat)
    walls = [o for o in bpy.data.objects if coll(o) == "Walls" and o.type == "MESH"]
    if wall_rgb:
        wall_mat = _pbr("Siding", wall_rgb, 0.85)
        for o in walls:
            o.data.materials.clear()
            o.data.materials.append(wall_mat)
    if walls:
        bpy.ops.object.select_all(action="DESELECT")
        for o in walls:
            o.select_set(True)
        bpy.context.view_layer.objects.active = walls[0]
        if len(walls) > 1:
            bpy.ops.object.join()
        bpy.context.view_layer.objects.active.name = "Walls"
    _bake_flat_colours()
    bpy.ops.object.select_all(action="SELECT")
    kw = dict(filepath=out, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
    if draco:
        kw.update(export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
    bpy.ops.export_scene.gltf(**kw)
    compressed = None
    if draco:
        with open(out, "rb") as f:
            compressed = b"KHR_draco_mesh_compression" in f.read(1 << 20)
        if not compressed:
            print("WARNING: --draco requested but this Blender build wrote no Draco extension (no Draco library); "
                  "the GLB is uncompressed")
    names = sorted(o.name for o in bpy.data.objects)
    print("dropped " + json.dumps({k: len(v) for k, v in dropped.items()}))
    print("ok " + json.dumps({"objects": len(names), "roof_facets": len(roofs), "draco": compressed,
                              "lot_line": any(n.startswith(LOT_LINE_PREFIX) for n in names)}))
    return names, dropped


if __name__ == "__main__":
    if bpy is None:
        raise SystemExit("needs Blender: the bpy module or blender -b -P export_studio_glb.py -- ARGS")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    blend_, out_, o_ = parse_args(argv)
    export(blend_, out_, **o_)
