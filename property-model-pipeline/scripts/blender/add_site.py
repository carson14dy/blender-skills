"""Put a detailed house on its real ground and build the yard around it (no trees).

    python add_site.py MODEL_detailed.blend site_scene.json yard.json OUT.blend
    (bpy module, or blender -b -P add_site.py -- ...)

site_scene.json comes from scripts/build_site.py (LiDAR terrain, draped street / concrete /
rock-bed overlays, curb lines, subject parcel, point features). yard.json (model frame, m):

{
  "items": [ {"kind": "ac_unit", "xy": [x,y], "size": [w,d,h], "rotation": 0},
             {"kind": "fire_pit", "xy": [x,y], "radius": 0.55},
             {"kind": "egress_well", "xy": [x,y] (wall line, centre), "width": 1.8, "depth": 0.9, "facing": [0,-1],
              "corner": 0.25, "rim_z": z or "rim": 0.10 above grade, "floor_z": z or "pit": 0.6 below grade},
             # cut the pit out of the ground with build_site.py --cutouts (well_outline() gives the polygon)
             {"kind": "meter", "xy": [x,y], "z": 1.0},
             {"kind": "box", "name": "...", "xy": [x,y], "size": [w,d,h], "z": 0.0, "material": "concrete", "color": [r,g,b]} ],
  "materials": {"rock_bed": [[r,g,b],[r,g,b]], "lawn": [...], "street": [...], "concrete": [...]},   # two-tone overrides
  "show_parcel": true
}

Grounding: walls and foundation strips are extended to 0.3 m below the terrain under them
(terrain is the LiDAR ground, so the house sits exactly as surveyed), deck posts, stair
stringers, downspouts, piers and stoops are cut to land on the terrain. Everything added goes
to collection "Site"; the measured roof/walls keep their geometry above grade.
"""
import json
import math
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def args():
    a = globals().get("PM_ARGS")
    if a is None:
        a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return a


def coll(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def mat(name, rgb, rough=0.8, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*rgb, 1)
    return m


def textured(name, rgb_a, rgb_b, scale, bump=0.2, rough=0.9):
    """Two-tone noise material (lawn, gravel, concrete) with a little bump."""
    m = mat(name, rgb_a, rough)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = scale
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*rgb_a, 1); ramp.color_ramp.elements[1].color = (*rgb_b, 1)
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = bump
    geo = nt.nodes.new("ShaderNodeNewGeometry")          # world position: `scale` is features per metre
    nt.links.new(geo.outputs["Position"], noise.inputs["Vector"])
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def mesh(name, verts, faces, c, m):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    if m:
        ob.data.materials.append(m)
    return ob


def box(name, lo, hi, c, m):
    x0, y0, z0 = lo; x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return mesh(name, v, f, c, m)


def cylinder(name, xy, r, z0, z1, c, m, seg=24, ring_inner=None):
    x, y = xy
    if ring_inner is None:
        v = [(x + r * math.cos(2 * math.pi * k / seg), y + r * math.sin(2 * math.pi * k / seg), z) for z in (z0, z1) for k in range(seg)]
        f = [list(range(seg))[::-1], list(range(seg, 2 * seg))] + [[k, (k + 1) % seg, seg + (k + 1) % seg, seg + k] for k in range(seg)]
        return mesh(name, v, f, c, m)
    ri = ring_inner
    v = []
    for rr in (r, ri):
        for z in (z0, z1):
            v += [(x + rr * math.cos(2 * math.pi * k / seg), y + rr * math.sin(2 * math.pi * k / seg), z) for k in range(seg)]
    o0, o1, i0, i1 = 0, seg, 2 * seg, 3 * seg
    f = []
    for k in range(seg):
        n = (k + 1) % seg
        f += [[o0 + k, o0 + n, o1 + n, o1 + k], [i0 + n, i0 + k, i1 + k, i1 + n], [o1 + k, o1 + n, i1 + n, i1 + k]]
    return mesh(name, v, f, c, m)


def well_outline(it, inset=0.0, arc=6):
    """Box window well against a wall, in plan: from the wall out `depth`, `width` wide, rounded front
    corners. `inset` > 0 gives the inner face, < 0 an outline just outside. Also used for the cut-out."""
    x, y = it["xy"]
    w, d = it.get("width", 1.8), it.get("depth", 0.9)
    fx, fy = it.get("facing", [0, -1])
    rx, ry = -fy, fx
    hw, dd = w / 2 - inset, d - inset
    r = max(min(it.get("corner", 0.25), w / 2, d) - inset, 0.02)
    loc = [(-hw, 0.0), (-hw, dd - r)]
    loc += [(-hw + r - r * math.cos(math.pi / 2 * s / arc), dd - r + r * math.sin(math.pi / 2 * s / arc)) for s in range(1, arc)]
    loc += [(-hw + r, dd), (hw - r, dd)]
    loc += [(hw - r + r * math.sin(math.pi / 2 * s / arc), dd - r + r * math.cos(math.pi / 2 * s / arc)) for s in range(1, arc)]
    loc += [(hw, dd - r), (hw, 0.0)]
    return [(x + rx * a + fx * b, y + ry * a + fy * b) for a, b in loc]


class Ground:
    def __init__(self, ob):
        bm = bmesh.new(); bm.from_mesh(ob.data); bm.transform(ob.matrix_world)
        self.bvh = BVHTree.FromBMesh(bm)
        bm.free()

    def z(self, x, y, default=None):
        hit = self.bvh.ray_cast(Vector((x, y, 100.0)), Vector((0, 0, -1)))
        if hit[0] is None:
            hit = self.bvh.find_nearest(Vector((x, y, 0.0)))
        return hit[0].z if hit[0] is not None else default


def snap_bottoms(objs, ground, below=0.0, tol=0.06):
    """Move each object's lowest vertices (within tol of its minimum) to terrain - below."""
    n = 0
    for ob in objs:
        if ob.type != "MESH":
            continue
        me = ob.data
        mw = ob.matrix_world
        zs = [(mw @ v.co).z for v in me.vertices]
        if not zs:
            continue
        zmin = min(zs)
        for v, zw in zip(me.vertices, zs):
            if zw <= zmin + tol:
                w = mw @ v.co
                gz = ground.z(w.x, w.y)
                if gz is not None:
                    w.z = gz - below
                    v.co = mw.inverted() @ w
                    n += 1
        me.update()
    return n


def main():
    blend, scene_path, yard_path, out = args()[:4]
    bpy.ops.wm.open_mainfile(filepath=blend)
    S = json.load(open(scene_path))
    Y = json.load(open(yard_path)) if yard_path and yard_path != "-" else {}
    c = coll("Site")
    ov = Y.get("materials", {})

    def two(key, a_, b_):
        v = ov.get(key)
        return (tuple(v[0]), tuple(v[1])) if v else (a_, b_)
    M = {
        "lawn": textured("Lawn", *two("lawn", (0.10, 0.22, 0.05), (0.18, 0.30, 0.08)), 6.0, 0.15),
        "street": textured("Street (red concrete)", *two("street", (0.33, 0.20, 0.17), (0.40, 0.26, 0.22)), 3.0, 0.05),
        "concrete": textured("Concrete", *two("concrete", (0.55, 0.55, 0.52), (0.62, 0.62, 0.59)), 2.0, 0.05),
        "rock_bed": textured("Rock mulch", *two("rock_bed", (0.30, 0.27, 0.23), (0.48, 0.44, 0.38)), 14.0, 0.8),
        "curb": mat("Curb", (0.5, 0.48, 0.45), 0.9),
        "hydrant": mat("Hydrant (yellow)", (0.85, 0.65, 0.05), 0.5),
        "metal": mat("Metal (grey)", (0.45, 0.46, 0.47), 0.5, 0.6),
        "stone": textured("Fire-pit stone", (0.38, 0.36, 0.33), (0.55, 0.52, 0.48), 8.0, 0.4),
        "ac": mat("AC unit", (0.75, 0.75, 0.73), 0.5, 0.3),
        "parcel": mat("Lot line", (0.95, 0.2, 0.2), 0.5),
    }
    # terrain (lawn) + draped overlays
    terrain = mesh("Terrain (LiDAR ground, lawn)", S["verts"], S["faces"], c, M["lawn"])
    for k, ovl in S.get("overlays", {}).items():
        if ovl["tris"]:
            mesh(f"{k.replace('_', ' ')} (draped)", ovl["verts"], ovl["tris"], c, M.get(k, M["concrete"]))
    G = Ground(terrain)
    # landscape edging: 0.1 m wide, 0.07 m tall strip along rock-bed / lawn boundaries
    for i, line in enumerate(S.get("edging", [])):
        verts, faces = [], []
        for k, (x, y) in enumerate(line):
            nx_, ny_ = line[min(k + 1, len(line) - 1)][0] - line[max(k - 1, 0)][0], line[min(k + 1, len(line) - 1)][1] - line[max(k - 1, 0)][1]
            ln = math.hypot(nx_, ny_) or 1
            px, py = -ny_ / ln * 0.05, nx_ / ln * 0.05
            z = G.z(x, y, 0)
            verts += [(x + px, y + py, z - 0.05), (x + px, y + py, z + 0.07), (x - px, y - py, z + 0.07), (x - px, y - py, z - 0.05)]
            if k:
                b0, b1 = 4 * (k - 1), 4 * k
                faces += [[b0, b1, b1 + 1, b0 + 1], [b0 + 1, b1 + 1, b1 + 2, b0 + 2], [b0 + 2, b1 + 2, b1 + 3, b0 + 3]]
        mesh(f"bed edging {i}", verts, faces, c, M["curb"])
    # curbs: 0.15 m wide, 0.15 m tall strip centred on the street edge
    for i, line in enumerate(S.get("curbs", [])):
        verts, faces = [], []
        for k, (x, y) in enumerate(line):
            nx_, ny_ = line[min(k + 1, len(line) - 1)][0] - line[max(k - 1, 0)][0], line[min(k + 1, len(line) - 1)][1] - line[max(k - 1, 0)][1]
            ln = math.hypot(nx_, ny_) or 1
            px, py = -ny_ / ln * 0.075, nx_ / ln * 0.075
            za, zb = G.z(x + px * 4, y + py * 4, 0), G.z(x - px * 4, y - py * 4, 0)
            top = max(za, zb) + 0.02
            verts += [(x + px, y + py, top - 0.25), (x + px, y + py, top), (x - px, y - py, top), (x - px, y - py, top - 0.25)]
            if k:
                b0, b1 = 4 * (k - 1), 4 * k
                faces += [[b0, b1, b1 + 1, b0 + 1], [b0 + 1, b1 + 1, b1 + 2, b0 + 2], [b0 + 2, b1 + 2, b1 + 3, b0 + 3]]
        mesh(f"curb {i}", verts, faces, c, M["curb"])
    # subject lot line (QA; hidden in renders)
    if S.get("parcel"):
        ring = S["parcel"]
        verts, faces = [], []
        for k, (x, y) in enumerate(ring):
            z = G.z(x, y, 0) + 0.04
            verts += [(x - 0.03, y - 0.03, z), (x + 0.03, y + 0.03, z)]
        n = len(ring)
        for k in range(n):
            a0, a1 = 2 * k, 2 * ((k + 1) % n)
            faces.append([a0, a1, a1 + 1, a0 + 1])
        lot = mesh("Lot line (parcel 74475)", verts, faces, c, M["parcel"])
        lot.hide_render = not Y.get("show_parcel", False)
    # point features
    for p in S.get("points", []):
        if p["kind"] == "hydrant":
            x, y = p["xy"]; z = G.z(x, y, 0)
            cylinder("fire hydrant body", (x, y), 0.11, z, z + 0.62, c, M["hydrant"])
            cylinder("fire hydrant bonnet", (x, y), 0.13, z + 0.62, z + 0.72, c, M["hydrant"])
            box("fire hydrant nozzle", (x - 0.2, y - 0.05, z + 0.42), (x + 0.2, y + 0.05, z + 0.52), c, M["hydrant"])
    for i, it in enumerate(Y.get("items", [])):
        x, y = it["xy"]; z = G.z(x, y, 0)
        k = it["kind"]
        if k == "ac_unit":
            w, d, h = it.get("size", [0.75, 0.75, 0.8])
            box("pad (AC)", (x - w / 2 - 0.08, y - d / 2 - 0.08, z - 0.05), (x + w / 2 + 0.08, y + d / 2 + 0.08, z + 0.06), c, M["concrete"])
            acm = mat("AC unit (custom)", tuple(it["color"]), 0.5, 0.3) if it.get("color") else M["ac"]
            box("AC condenser", (x - w / 2, y - d / 2, z + 0.06), (x + w / 2, y + d / 2, z + 0.06 + h), c, acm)
            cylinder("AC fan grille", (x, y), min(w, d) * 0.38, z + 0.06 + h, z + 0.08 + h, c, M["metal"])
        elif k == "fire_pit":
            r = it.get("radius", 0.55)
            cylinder("fire pit (stone)", (x, y), r, z - 0.05, z + 0.33, c, M["stone"], ring_inner=r - 0.2)
            cylinder("fire pit (ash)", (x, y), r - 0.2, z - 0.05, z + 0.05, c, mat("Ash", (0.08, 0.08, 0.08)))
        elif k == "egress_well":
            pts = well_outline(it)
            inner = well_outline(it, inset=it.get("thickness", 0.04))
            gz = max(G.z(px_, py_, z) for px_, py_ in well_outline(it, inset=-0.15)[1:-1])   # grade just outside
            ztop = it.get("rim_z", gz + it.get("rim", 0.10))
            zbot = it.get("floor_z", gz - it.get("pit", 0.6))
            plastic = mat("Window well (white plastic)", tuple(it.get("color", (0.80, 0.80, 0.77))), 0.45)
            n = len(pts)
            verts = [(px_, py_, zz) for px_, py_ in pts for zz in (zbot - 0.03, ztop)] + [(px_, py_, zz) for px_, py_ in inner for zz in (zbot - 0.03, ztop)]
            faces = []
            for s_ in range(n - 1):
                o0, o1, i0, i1 = 2 * s_, 2 * s_ + 2, 2 * n + 2 * s_, 2 * n + 2 * s_ + 2
                faces += [[o0, o1, o1 + 1, o0 + 1], [i1, i0, i0 + 1, i1 + 1], [o0 + 1, o1 + 1, i1 + 1, i0 + 1]]
            faces += [[0, 1, 2 * n + 1, 2 * n], [2 * n - 2, 4 * n - 2, 4 * n - 1, 2 * n - 1]]   # wall ends
            mesh("egress window well", verts, faces, c, plastic)
            # gravel floor down in the pit (build_site.py --cutouts removed the ground here)
            mesh("egress well floor (gravel)", [(px_, py_, zbot) for px_, py_ in inner], [list(range(len(inner)))], c, M["rock_bed"])
            # foundation face behind the well, from the floor up under the window
            fnd = bpy.data.materials.get("Foundation") or M["concrete"]
            (ax, ay), (bx, by) = inner[0], inner[-1]
            mesh("egress well back (foundation)", [(ax, ay, zbot), (bx, by, zbot), (bx, by, it.get("back_top", gz - 0.28)), (ax, ay, it.get("back_top", gz - 0.28))],
                 [[0, 1, 2, 3]], c, fnd)
        elif k == "meter":
            zz = it.get("z", 1.0)
            box("utility meter", (x - 0.15, y - 0.08, z + zz), (x + 0.15, y + 0.08, z + zz + 0.35), c, M["metal"])
        else:
            w, d, h = it.get("size", [0.5, 0.5, 0.5])
            z += it.get("z", 0.0)
            m_ = mat(f"{it.get('name', 'item')} colour", tuple(it["color"]), 0.6) if it.get("color") else M.get(it.get("material", "concrete"), M["concrete"])
            box(it.get("name", f"item {i}"), (x - w / 2, y - d / 2, z), (x + w / 2, y + d / 2, z + h), c, m_)
    # ---- ground the house -----------------------------------------------------
    walls = list(bpy.data.collections["Walls"].objects)
    n = snap_bottoms(walls, G, below=0.3, tol=0.6)
    det = bpy.data.collections.get("Details")
    if det:
        fnd = [o for o in det.objects if o.name.startswith("foundation")]
        n += snap_bottoms(fnd, G, below=0.3, tol=0.12)
        land = [o for o in det.objects if "rail" not in o.name and any(p in o.name for p in
                ("post", "stringer", "downspout", "brick pier", "garage stoop"))]
        n += snap_bottoms(land, G, below=0.02, tol=0.06)
    print("snapped vertices:", n)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("site added ->", out)


main()
