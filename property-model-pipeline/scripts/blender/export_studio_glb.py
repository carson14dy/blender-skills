"""Export a measured model for web viewers / Roof Layer Studio: roof facets as meshes named
"Roof F1..", walls joined into "Walls" with PBR siding/shingle materials; labels, edge curves,
ground, cameras and LiDAR points are dropped. glTF is Y-up with north = -Z.

    python export_studio_glb.py OUT/model.blend house.glb      (bpy module or blender -b -P ... --)

Hosts that cannot serve .glb can take the same model as embedded glTF JSON (see SKILL.md).
"""
import sys, bpy
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
blend, out = argv[0], argv[1]
bpy.ops.wm.open_mainfile(filepath=blend)
keep = set()
for cname in ("Roof facets", "Walls", "Details"):   # Details = add_details.py (openings, trim, decks)
    c = bpy.data.collections.get(cname)
    if c is None:
        continue
    for o in c.objects:
        keep.add(o.name)
for o in list(bpy.data.objects):
    if o.name not in keep:
        bpy.data.objects.remove(o, do_unlink=True)
def pbr(name, rgb, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*rgb, 1)
    return m
roof_mat = pbr("Roof shingle", (0.2, 0.2, 0.21), 0.9)
wall_mat = pbr("Siding", (0.42, 0.42, 0.30), 0.85)   # sage lap siding from the photos (linear RGB)
roofs = sorted([o for o in bpy.data.objects if o.users_collection[0].name == "Roof facets"], key=lambda o: o.name)
for i, o in enumerate(roofs):
    o["facet"] = o.name
    o.name = f"Roof F{i + 1}"
for o in bpy.data.objects:
    if o.users_collection[0].name == "Details":
        continue   # keep their own materials
    if o.users_collection[0].name == "Roof facets":
        o.data.materials.clear(); o.data.materials.append(roof_mat)
    else:
        o.data.materials.clear(); o.data.materials.append(wall_mat)
# join walls into one mesh
walls = [o for o in bpy.data.objects if o.users_collection[0].name == "Walls"]
bpy.ops.object.select_all(action="DESELECT")
for o in walls: o.select_set(True)
bpy.context.view_layer.objects.active = walls[0]
bpy.ops.object.join(); bpy.context.view_layer.objects.active.name = "Walls"
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
print("ok", [o.name for o in bpy.data.objects])
