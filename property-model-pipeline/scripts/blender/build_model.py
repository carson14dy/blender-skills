"""Build the measured property model inside Blender from model.json.

Runs three ways:
  blender -b --factory-startup -P build_model.py -- --model model.json --out OUTDIR [--ortho ortho.png]
          [--points pts.xyz] [--cameras cameras.json] [--glb] [--render] [--imperial] [--keep-scene]
  python build_model.py ...            (with the `bpy` pip module)
  via Blender MCP: scripts/blender/send_to_mcp.py prepends `PM_ARGS = [...]` to this file.

Only bpy / bmesh / mathutils / json are used, so it runs on any Blender >= 3.6 (tested 5.x).
Scene unit = metre, 1 Blender unit = 1 m, X = East, Y = North, Z = Up (site-local ENU),
so measurements taken in Blender (MeasureIt, N-panel) are real-world values.
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon

EDGE_COLORS = {"ridge": (1, 0.1, 0.1), "hip": (1, 0.5, 0), "valley": (0.1, 0.4, 1), "eave": (0, 0.85, 0),
               "rake": (0, 0.8, 0.8), "transition": (0.8, 0, 0.8), "headwall": (1, 1, 0), "sidewall": (1, 0.85, 0.4)}
FACET_COLORS = [(0.62, 0.32, 0.25), (0.45, 0.42, 0.40), (0.55, 0.38, 0.30), (0.40, 0.36, 0.34),
                (0.58, 0.45, 0.36), (0.50, 0.30, 0.28)]


def parse_args():
    argv = globals().get("PM_ARGS")
    if argv is None:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ortho")
    ap.add_argument("--points")
    ap.add_argument("--cameras")
    ap.add_argument("--glb", action="store_true")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--imperial", action="store_true")
    ap.add_argument("--keep-scene", action="store_true")
    ap.add_argument("--labels", action="store_true", default=True)
    return ap.parse_args(argv)


def collection(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def material(name, color, emission=0.0, alpha=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Roughness"].default_value = 0.8
        if emission:
            key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
            bsdf.inputs[key].default_value = (*color, 1)
            bsdf.inputs["Emission Strength"].default_value = emission
        if alpha < 1:
            bsdf.inputs["Alpha"].default_value = alpha
    m.diffuse_color = (*color, alpha)
    return m


def mesh_object(name, verts, faces, coll, mat=None, edges=()):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, list(edges), faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def polygon_faces(outer, holes):
    """Vertices + faces for a planar polygon with holes (ngon when there are no holes)."""
    if not holes:
        return [tuple(v) for v in outer], [list(range(len(outer)))]
    loops = [outer] + holes
    verts = [tuple(v) for loop in loops for v in loop]
    tris = tessellate_polygon([[Vector(v) for v in loop] for loop in loops])
    return verts, [list(t) for t in tris]


def build_roof(model, coll, labels, label_coll):
    objs = []
    for i, f in enumerate(model["facets"]):
        mat = material(f"Roof {i % len(FACET_COLORS)}", FACET_COLORS[i % len(FACET_COLORS)])
        verts, faces = [], []
        for poly in f["polygons"]:
            v, fc = polygon_faces(poly["outer"], poly["holes"])
            off = len(verts)
            verts += v
            faces += [[k + off for k in face] for face in fc]
        pitch = f["pitch_rise_per_12"]
        ob = mesh_object(f"{f['id']} {pitch:.1f}-12", verts, faces, coll, mat)
        # make normals point up
        me = ob.data
        for p in me.polygons:
            if p.normal.z < 0:
                p.flip()
        ob["area_m2"] = f["area_m2"]
        ob["area_sqft"] = f["area_m2"] * 10.7639104
        ob["pitch_rise_per_12"] = pitch
        ob["azimuth"] = f["azimuth"] if f["azimuth"] is not None else -1
        ob["wings"] = ",".join(f["wings"])
        objs.append(ob)
        if labels and verts:
            c = Vector((0, 0, 0))
            for v in verts:
                c += Vector(v)
            c /= len(verts)
            txt = bpy.data.curves.new(f"lbl {f['id']}", "FONT")
            txt.body = f"{f['id']} {pitch:.1f}/12\n{f['area_m2'] * 10.7639:.0f} ft²"
            txt.size = 0.45
            txt.align_x = "CENTER"
            to = bpy.data.objects.new(f"label {f['id']}", txt)
            to.location = c + Vector((0, 0, 0.6))
            to.data.materials.append(material("Label", (1, 1, 1), emission=2.0))
            label_coll.objects.link(to)
    return objs


def build_walls(model, coll):
    mat = material("Wall", (0.85, 0.83, 0.78))
    for w in model["walls"]:
        prof = w["profile"]
        if len(prof) < 2:
            continue
        a, b = prof[0], prof[-1]
        if w.get("bottom"):
            verts = [tuple(w["bottom"][0]), tuple(w["bottom"][1])] + [tuple(p) for p in reversed(prof)]
        else:
            verts = [(a[0], a[1], w["base_z"]), (b[0], b[1], w["base_z"])] + [tuple(p) for p in reversed(prof)]
        mesh_object(f"Wall {w['wing']} {w['side']}", verts, [list(range(len(verts)))], coll, mat)


def build_edges(model, coll):
    by_kind = {}
    for e in model["edges"]:
        by_kind.setdefault(e["kind"], []).append(e)
    for kind, es in by_kind.items():
        cu = bpy.data.curves.new(f"{kind} lines", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.035
        for e in es:
            sp = cu.splines.new("POLY")
            sp.points.add(1)
            sp.points[0].co = (*e["p0"], 1)
            sp.points[1].co = (*e["p1"], 1)
        ob = bpy.data.objects.new(f"{kind} ({sum(x['length_m'] for x in es) * 3.28084:.1f} ft)", cu)
        ob["length_m"] = sum(x["length_m"] for x in es)
        cu.materials.append(material(f"Edge {kind}", EDGE_COLORS.get(kind, (1, 1, 1)), emission=3.0))
        coll.objects.link(ob)


def build_ground(ortho, coll):
    meta = json.load(open(ortho + ".json"))
    x0, y0, x1, y1 = meta["bounds_local"]
    ob = mesh_object("Ground ortho", [(x0, y0, -0.02), (x1, y0, -0.02), (x1, y1, -0.02), (x0, y1, -0.02)], [[0, 1, 2, 3]], coll)
    me = ob.data
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[li].uv = (u, v)
    m = bpy.data.materials.new("Ortho")
    m.use_nodes = True
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.abspath(ortho))
    bsdf = nt.nodes.get("Principled BSDF")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    me.materials.append(m)
    ob["attribution"] = meta.get("attribution", "")
    return ob


def build_points(path, coll):
    pts = []
    with open(path) as f:
        for line in f:
            x, y, z = map(float, line.split()[:3])
            pts.append((x, y, z))
    ob = mesh_object("LiDAR points (height above ground)", pts, [], coll)
    try:  # render the cloud as small spheres via geometry nodes
        ng = bpy.data.node_groups.new("PM points", "GeometryNodeTree")
        if hasattr(ng, "interface"):
            ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
            ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
        m2p = ng.nodes.new("GeometryNodeMeshToPoints")
        m2p.inputs["Radius"].default_value = 0.04
        sm = ng.nodes.new("GeometryNodeSetMaterial")
        sm.inputs["Material"].default_value = material("LiDAR", (1.0, 0.75, 0.1), emission=1.5)
        ng.links.new(gi.outputs[0], m2p.inputs["Mesh"])
        ng.links.new(m2p.outputs["Points"], sm.inputs["Geometry"])
        ng.links.new(sm.outputs["Geometry"], go.inputs[0])
        mod = ob.modifiers.new("points", "NODES")
        mod.node_group = ng
    except Exception as e:  # older Blender: vertices only
        print("point rendering setup skipped:", e)
    return ob


def build_cameras(path, coll):
    cams = json.load(open(path))
    out = []
    for name, c in cams.items():
        b = c["blender"]
        cd = bpy.data.cameras.new(f"cam {name}")
        cd.lens = b["lens"]
        cd.sensor_width = b["sensor_width"]
        cd.sensor_fit = b["sensor_fit"]
        cd.shift_x, cd.shift_y = b["shift_x"], b["shift_y"]
        cd.clip_start, cd.clip_end = 0.1, 2000
        ob = bpy.data.objects.new(f"Photo {name}", cd)
        R = Matrix(b["matrix_rotation"])
        ob.matrix_world = Matrix.Translation(Vector(b["location"])) @ R.to_4x4()
        if os.path.exists(c["image"]):
            img = bpy.data.images.load(c["image"])
            cd.show_background_images = True
            bg = cd.background_images.new()
            bg.image = img
            bg.alpha = 0.7
        ob["rms_px"] = c["rms_px"]
        ob["image"] = c["image"]
        ob["resolution"] = b["resolution"]
        coll.objects.link(ob)
        out.append(ob)
    return out


def setup_scene(imperial):
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system = "IMPERIAL" if imperial else "METRIC"
    us.scale_length = 1.0
    us.length_unit = "FEET" if imperial else "METERS"
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.7, 0.78, 0.9, 1)
        bg.inputs["Strength"].default_value = 0.8
    sun_d = bpy.data.lights.new("Sun", "SUN")
    sun_d.energy = 3.5
    sun = bpy.data.objects.new("Sun", sun_d)
    sun.rotation_euler = (math.radians(40), math.radians(10), math.radians(35))
    sc.collection.objects.link(sun)


def bounds_of(model):
    xs, ys, zs = [], [], []
    for f in model["facets"]:
        for p in f["polygons"]:
            for v in p["outer"]:
                xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
    return min(xs), min(ys), max(xs), max(ys), max(zs)


def add_view_cameras(model, coll):
    x0, y0, x1, y1, zmax = bounds_of(model)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    span = max(x1 - x0, y1 - y0) + 6
    top = bpy.data.cameras.new("Plan (orthographic)")
    top.type = "ORTHO"
    top.ortho_scale = span
    to = bpy.data.objects.new("Plan view", top)
    to.location = (cx, cy, zmax + 50)
    coll.objects.link(to)
    per = bpy.data.cameras.new("Perspective")
    per.lens = 35
    po = bpy.data.objects.new("Hero view", per)
    d = span * 1.1
    po.location = (cx + d * 0.8, cy - d, zmax + d * 0.6)
    direction = Vector((cx, cy, zmax * 0.4)) - po.location
    po.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(po)
    return to, po


def render(cam, path, res=(1600, 1200), transparent=False):
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 24
    sc.cycles.device = "CPU"
    try:
        sc.cycles.use_denoising = False
    except AttributeError:
        pass
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def overlay_on_photo(render_path, photo_path, out_path, alpha=0.55):
    """Alpha-blend a transparent model render over the inspection photo (numpy, no PIL needed)."""
    import numpy as np
    r = bpy.data.images.load(render_path)
    p = bpy.data.images.load(photo_path)
    if tuple(p.size) != tuple(r.size):
        p.scale(*r.size)
    w, h = r.size
    rp = np.array(r.pixels[:]).reshape(h, w, 4)
    pp = np.array(p.pixels[:]).reshape(h, w, 4)
    a = rp[:, :, 3:4] * alpha
    out = pp.copy()
    out[:, :, :3] = pp[:, :, :3] * (1 - a) + rp[:, :, :3] * a
    o = bpy.data.images.new("overlay", w, h, alpha=False)
    o.pixels[:] = out.ravel()
    o.filepath_raw = out_path
    o.file_format = "PNG"
    o.save()
    return out_path


def main():
    a = parse_args()
    model = json.load(open(a.model))
    os.makedirs(a.out, exist_ok=True)
    if not a.keep_scene:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_scene(a.imperial)
    roof_c, wall_c, edge_c = collection("Roof facets"), collection("Walls"), collection("Roof edges")
    lab_c, ref_c, cam_c = collection("Labels"), collection("Reference data"), collection("Cameras")
    build_roof(model, roof_c, a.labels, lab_c)
    build_walls(model, wall_c)
    build_edges(model, edge_c)
    if a.ortho and os.path.exists(a.ortho):
        build_ground(a.ortho, ref_c)
    if a.points and os.path.exists(a.points):
        pts_c = collection("LiDAR points")
        build_points(a.points, pts_c)
        pts_c.hide_render = True  # visible in the viewport for QA, kept out of presentation renders
    photo_cams = build_cameras(a.cameras, cam_c) if a.cameras and os.path.exists(a.cameras) else []
    plan, hero = add_view_cameras(model, cam_c)
    bpy.context.scene.camera = hero
    site = model.get("site") or {}
    bpy.context.scene["pm_origin"] = json.dumps(site.get("origin", {}))
    bpy.context.scene["pm_address"] = site.get("address", "")
    blend = os.path.join(os.path.abspath(a.out), "model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("saved", blend)
    if a.glb:
        glb = os.path.join(os.path.abspath(a.out), "model.glb")
        for ob in bpy.context.scene.objects:
            ob.select_set(ob.users_collection[0].name in ("Roof facets", "Walls"))
        bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True)
        print("exported", glb)
    if a.render:
        render(plan, os.path.join(a.out, "plan.png"), (1400, 1400))
        render(hero, os.path.join(a.out, "hero.png"))
        ref_c.hide_render = True
        lab_c.hide_render = True
        for cam in photo_cams:
            w, h = cam["resolution"]
            scale = 1600 / max(w, h)
            rp = render(cam, os.path.join(a.out, f"{cam.name}_model.png"), (int(w * scale), int(h * scale)), True)
            overlay_on_photo(rp, cam["image"], os.path.join(a.out, f"{cam.name}_overlay.png"))
        print("renders in", a.out)


main()
