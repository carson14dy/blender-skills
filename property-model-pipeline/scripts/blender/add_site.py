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
             {"kind": "box", "name": "...", "xy": [x,y], "size": [w,d,h], "z": 0.0, "rotation": deg, "material": "concrete", "color": [r,g,b]},
             {"kind": "boulder", "polygon": [[x,y],...], "top_z": z, "color": [r,g,b]},          # rock rising from the terrain
             {"kind": "retaining_wall", "line": [[x,y],...], "top_z": z or "height": h, "thickness": 0.3,
              "material": "stone|concrete|drystack|timber", "color": [r,g,b], "line_is": "centre|face", "uphill": "left|right"},
             #   "top_z": [z, z, ...] (one per segment) gives a stepped wall with level tops; the bottom goes
             #   0.3 m under the lower of the two grades beside it (build_site.py --breaklines yard.json
             #   makes the terrain step inside the wall). "line_is": "face": the line is the exposed (downhill)
             #   face as measured from the LiDAR step, the thickness goes to the uphill side ("uphill": left /
             #   right of the line direction, or the higher grade). "drystack" is dry-laid ledgestone: random
             #   course heights (0.05-0.15 m) and stone lengths (0.25-0.75 m, no regular bond), dark 12 mm joints,
             #   per-stone colour jitter around the mean of the two colours and relief; "drystack": {"course": [lo, hi],
             #   "stone": [lo, hi], "joint": m, "joint_dark": 0.35, "jitter": [r, g, b], "bump": m} overrides.
             {"kind": "pier", "xy": [x,y], "size": [w,d], "top_z": z, "rotation": deg, "material": "concrete",
              "plaque": {"text": "...", "face": "-x|+x|-y|+y", "color": [r,g,b], "size": 0.18}},   # numerals on a face
             {"kind": "steps", "line": [[x,y],[x,y]], "width": 1.2, "z0": z_bottom, "z1": z_top, "risers": n,
              "color": [r,g,b]},                                    # landscape steps, each tread grounded
             {"kind": "rock_scatter", "polygon": [[x,y],...], "count": 12, "size": [0.3, 0.7], "height": [0.45, 0.7],
              "seed": 1, "holes": [[[x,y],...]]},                  # height: fraction of each stone's width above grade
             {"kind": "path_light", "xy": [x,y], "height": 0.5},
             {"kind": "grade_pad", "polygon": [[x,y],...], "z": z, "blend": 0.8, "surface": [[r,g,b],[r,g,b]]},
             #   levelled by build_site.py --grade yard.json; here only its optional surface is draped
             {"kind": "box", ..., "top_z": z}   # absolute top: the box stands on the lowest grade under it
             {"kind": "fence", "line": [[x,y],...], "height": 1.2 or "top_z": z, "style": "rail|picket|baluster|chain", "color": [r,g,b]},
             {"kind": "surface", "polygon": [[x,y],...], "color": [[r,g,b],[r,g,b]], "scale": 10, "lift": 0.025, "name": "..."},
             {"kind": "path", "line": [[x,y],...], "width": 0.9, "color": [[r,g,b],[r,g,b]]},    # draped strip
             {"kind": "hot_tub", "xy": [x,y], "size": [2.1, 2.1, 0.9], "rotation": deg, "z": deck_z},
             {"kind": "mailbox" | "light_post", "xy": [x,y], "rotation": deg} ],
  # every item may carry "z" (absolute base, model frame) instead of sitting on the terrain
  "materials": {"rock_bed": [[r,g,b],[r,g,b]], "ground": [...], "rock": [...], "street": [...], "concrete": [...]},
                                      # two-tone overrides ("lawn" is accepted for "ground")
  "show_parcel": true,
  "keep_wall_bottoms": ["M"]          # wing ids whose walls stand on another storey: not extended to the terrain
}

Boulders, the "rock" terrain tone and the rock material carry a sparse joint mask (Voronoi cells ~1.9 m, lines
under 2 cm at 0.82 x the stone value, on about half of the cell edges) and faint horizontal bedding (noise stretched
6:1 in xy:z, +-8 % value), so outcrops read as smooth, jointed and bedded sandstone rather than plaster or a
turtle-shell crack net.

Terrain faces carry build_site.py's surface class: "ground" (soil / grass) or "rock" (boulders and
outcrops the LiDAR rock merge raised, or traced rock outlines). With the scene's per-vertex "vertex_rock"
weight the terrain gets one material that blends the two (soft, noise-broken boulder edges); without
it, rock faces get the rock material slot. The default rock tone is buff sandstone (ROCK_A/ROCK_B).
The terrain is built from explicit triangles along each cell's fold (see build_site.py split_diagonals), so it
renders on exactly the triangles the overlays were draped on; it is smooth-shaded with edges sharper than
SHARP_DEG marked sharp and area-weighted normals (WeightedNormal, keep sharp). Draped overlays are
smooth-shaded and wound counter-clockwise (normals up) for viewers that cull back faces.

Every Site object carries a custom property "site_kind": the yard item kind that made it ("retaining_wall",
"pier", ...), "overlay:<name>" for draped overlays, "curb" or "edging" (render_thumbnail.py --terrain keeps
the hardscape by it).

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

# buff sandstone (linear RGB), the default rock tone: sunlit buff sandstone reads ~(178,169,159) sRGB; warm buff
# (+4 R / -6 B in sRGB over a neutral grey-buff), as the orthos show the rock tops
ROCK_A, ROCK_B = (0.442, 0.38, 0.284), (0.524, 0.45, 0.341)
# stone surface pattern: few long joints (Voronoi cells ~1.9 m, lines < 2 cm, 0.82 x the stone value) and faint
# horizontal bedding (noise stretched 6:1 in xy:z, +-8 % value) -- sandstone, not crazy paving
CRACK_SCALE, CRACK_WIDTH, CRACK_DARK = 0.53, 0.01, 0.82
BEDDING_STRETCH, BEDDING_AMP, BEDDING_SCALE = 6.0, 0.08, 0.8
SHARP_DEG = 50.0      # terrain edges whose two faces differ by more than this are shaded sharp


def ccw_tris(verts, tris):
    """Triangles wound counter-clockwise seen from above (normal +z), so back-face-culling viewers keep them."""
    out = []
    for a, b, c_ in tris:
        (x0, y0), (x1, y1), (x2, y2) = verts[a][:2], verts[b][:2], verts[c_][:2]
        out.append([a, c_, b] if (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) < 0 else [a, b, c_])
    return out


def terrain_triangles(faces, face_class=None):
    """Split every terrain quad along its own 0-2 diagonal (build_site.py writes each quad so that this is the
    cell's more level diagonal) and carry each quad's class to both halves. Triangles and polygons pass through."""
    tris, cls = [], []
    for k, f in enumerate(faces):
        fc_ = face_class[k] if face_class and k < len(face_class) else 0
        if len(f) == 4:
            tris += [[f[0], f[1], f[2]], [f[0], f[2], f[3]]]; cls += [fc_, fc_]
        else:
            tris.append(list(f)); cls.append(fc_)
    return tris, cls


def sharpen(ob, deg=SHARP_DEG):
    """Smooth-shade a terrain mesh but keep creases: edges whose two faces' normals differ by more than `deg`
    are marked sharp, and a WeightedNormal modifier (face area, keep sharp) stops a steep boulder flank or a
    folded cell from darkening its smooth neighbours. Returns the number of sharp edges."""
    import numpy as np
    me = ob.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    npoly = len(me.polygons)
    nrm = np.zeros(npoly * 3); me.polygons.foreach_get("normal", nrm); nrm = nrm.reshape(-1, 3)
    ls = np.zeros(npoly, int); me.polygons.foreach_get("loop_start", ls)
    lt = np.zeros(npoly, int); me.polygons.foreach_get("loop_total", lt)
    le = np.zeros(len(me.loops), int); me.loops.foreach_get("edge_index", le)
    lp = np.repeat(np.arange(npoly), lt)                     # polygon of every loop
    order = np.argsort(le, kind="stable")
    e_sorted, p_sorted = le[order], lp[order]
    pair = np.nonzero(e_sorted[1:] == e_sorted[:-1])[0]       # edges shared by two faces
    cosang = (nrm[p_sorted[pair]] * nrm[p_sorted[pair + 1]]).sum(1)
    sharp = np.zeros(len(me.edges), bool)
    sharp[e_sorted[pair][cosang < math.cos(math.radians(deg))]] = True
    at = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    at.data.foreach_set("value", sharp.tolist())
    md = ob.modifiers.new("Weighted normals (keep sharp)", "WEIGHTED_NORMAL")
    md.keep_sharp = True
    md.mode = "FACE_AREA"
    me.update()
    return int(sharp.sum())


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


def add_bedding(nt, color_socket, stretch=None, amp=None, scale=None):
    """Horizontal bedding on stone: the colour times 1 +- `amp` from a low-frequency noise of the world position
    stretched `stretch`:1 in xy:z (layers run level across a boulder). Returns the new colour socket."""
    stretch = BEDDING_STRETCH if stretch is None else stretch
    amp = BEDDING_AMP if amp is None else amp
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sq = nt.nodes.new("ShaderNodeVectorMath"); sq.operation = "MULTIPLY"; sq.label = "bedding stretch"
    sq.inputs[1].default_value = (1.0, 1.0, stretch)
    nt.links.new(geo.outputs["Position"], sq.inputs[0])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.label = "bedding"
    nz.inputs["Scale"].default_value = BEDDING_SCALE if scale is None else scale
    nz.inputs["Detail"].default_value = 2.0
    nt.links.new(sq.outputs[0], nz.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.clamp = True; mr.label = "bedding amplitude"
    mr.inputs["From Min"].default_value = 0.3; mr.inputs["From Max"].default_value = 0.7
    mr.inputs["To Min"].default_value = 1.0 - amp; mr.inputs["To Max"].default_value = 1.0 + amp
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.label = "bedding"
    mix.inputs["Factor"].default_value = 1.0
    cv = nt.nodes.new("ShaderNodeCombineXYZ")
    for k in ("X", "Y", "Z"):
        nt.links.new(mr.outputs["Result"], cv.inputs[k])
    nt.links.new(color_socket, mix.inputs[6]); nt.links.new(cv.outputs[0], mix.inputs[7])
    return mix.outputs[2]


def add_cracks(nt, color_socket, scale=None, width=None, dark=None, coverage=0.5):
    """Joint lines on stone: where Voronoi F2 - F1 (world position, `scale` cells per metre, slightly
    noise-distorted) is below `width` the colour is multiplied by `dark` -- on about `coverage` of the cell
    edges (a large noise switches joints on and off, so the stone reads as jointed, not as crazy paving).
    Defaults: CRACK_SCALE (cells ~1.9 m), CRACK_WIDTH (lines width / scale < 2 cm wide), CRACK_DARK (0.82).
    Returns the new colour socket."""
    scale = CRACK_SCALE if scale is None else scale
    width = CRACK_WIDTH if width is None else width
    dark = CRACK_DARK if dark is None else dark
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.5
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    dist = nt.nodes.new("ShaderNodeVectorMath"); dist.operation = "MULTIPLY_ADD"
    dist.inputs[1].default_value = (0.08 * 1.6 / scale,) * 3          # wiggle in proportion to the cell size
    nt.links.new(nz.outputs["Color"], dist.inputs[0]); nt.links.new(geo.outputs["Position"], dist.inputs[2])
    f = []
    for feat in ("F1", "F2"):
        v = nt.nodes.new("ShaderNodeTexVoronoi"); v.feature = feat; v.inputs["Scale"].default_value = scale
        v.label = "cracks"
        nt.links.new(dist.outputs[0], v.inputs["Vector"]); f.append(v)
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"
    nt.links.new(f[1].outputs["Distance"], sub.inputs[0]); nt.links.new(f[0].outputs["Distance"], sub.inputs[1])
    lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.inputs[1].default_value = width; lt.label = "crack width"
    nt.links.new(sub.outputs[0], lt.inputs[0])
    on = nt.nodes.new("ShaderNodeTexNoise"); on.inputs["Scale"].default_value = 0.8 * scale / 1.6; on.inputs["Detail"].default_value = 1.0
    nt.links.new(geo.outputs["Position"], on.inputs["Vector"])
    gate = nt.nodes.new("ShaderNodeMath"); gate.operation = "GREATER_THAN"; gate.inputs[1].default_value = 1.0 - coverage
    nt.links.new(on.outputs["Fac"], gate.inputs[0])
    both = nt.nodes.new("ShaderNodeMath"); both.operation = "MULTIPLY"
    nt.links.new(lt.outputs[0], both.inputs[0]); nt.links.new(gate.outputs[0], both.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.label = "cracks"
    mix.inputs[7].default_value = (dark, dark, dark, 1)
    nt.links.new(both.outputs[0], mix.inputs["Factor"]); nt.links.new(color_socket, mix.inputs[6])
    return mix.outputs[2]


def stone(name, rgb_a, rgb_b, scale, bump=0.6):
    """Two-tone noise stone with bedding and sparse joints (boulders, outcrops)."""
    m = textured(name, rgb_a, rgb_b, scale, bump)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    col = b.inputs["Base Color"].links[0].from_socket
    nt.links.new(add_cracks(nt, add_bedding(nt, col)), b.inputs["Base Color"])
    return m


def blend_by_attribute(name, ground, rock, attr, edge=0.5, soft=0.18):
    """Terrain material: two-tone noise `ground` (rgb_a, rgb_b, scale) where the point attribute `attr` is
    low, `rock` where it is high, with a noise-broken transition around `edge`."""
    m = mat(name, ground[0], 0.9)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")

    def tone(rgb_a, rgb_b, scale):
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 4.0
        nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
        rp = nt.nodes.new("ShaderNodeValToRGB")
        rp.color_ramp.elements[0].color = (*rgb_a, 1); rp.color_ramp.elements[1].color = (*rgb_b, 1)
        nt.links.new(nz.outputs["Fac"], rp.inputs["Fac"])
        return nz, rp
    nz_g, rp_g = tone(*ground)
    nz_r, rp_r = tone(*rock)
    att = nt.nodes.new("ShaderNodeAttribute"); att.attribute_type = "GEOMETRY"; att.attribute_name = attr
    brk = nt.nodes.new("ShaderNodeTexNoise"); brk.inputs["Scale"].default_value = 1.5
    nt.links.new(geo.outputs["Position"], brk.inputs["Vector"])
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = 0.5
    nt.links.new(brk.outputs["Fac"], sub.inputs[0])
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "MULTIPLY_ADD"; add.inputs[1].default_value = 0.35
    nt.links.new(sub.outputs[0], add.inputs[0]); nt.links.new(att.outputs["Fac"], add.inputs[2])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.clamp = True
    mr.inputs["From Min"].default_value = edge - soft; mr.inputs["From Max"].default_value = edge + soft
    nt.links.new(add.outputs[0], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    nt.links.new(mr.outputs["Result"], mix.inputs["Factor"])
    nt.links.new(rp_g.outputs["Color"], mix.inputs[6])
    nt.links.new(add_cracks(nt, add_bedding(nt, rp_r.outputs["Color"])), mix.inputs[7])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.4
    nt.links.new(nz_r.outputs["Fac"], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    m.diffuse_color = (*[0.5 * (x + y) for x, y in zip(ground[0], rock[0])], 1)
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


def obox(name, xy, wd, z0, z1, rot, c, m):
    """Box centred on xy, w along the rotated x axis (rot: degrees counter-clockwise)."""
    t = math.radians(rot)
    ex, ey = Vector((math.cos(t), math.sin(t), 0)), Vector((-math.sin(t), math.cos(t), 0))
    o = Vector((xy[0], xy[1], 0))
    w, d = wd
    ring = [o + ex * (sx * w / 2) + ey * (sy * d / 2) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    v = [(p.x, p.y, z0) for p in ring] + [(p.x, p.y, z1) for p in ring]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return mesh(name, v, f, c, m)


def _base(it, G, x, y):
    return it["z"] if "z" in it else G.z(x, y, 0)


def _two(it, a, b):
    col = it.get("color")
    if col and isinstance(col[0], (list, tuple)):
        return tuple(col[0]), tuple(col[1])
    if col:
        return tuple(col), tuple(min(1.0, v * 1.25) for v in col)
    return a, b


def k_boulder(it, G, c, M, i):
    """Rock: the outline at grade, shrinking in rings to a rounded top at top_z (the LiDAR height)."""
    from shapely.geometry import Polygon
    P = Polygon(it["polygon"]).buffer(0)
    if P.is_empty:
        return
    cx, cy = P.centroid.x, P.centroid.y
    ring0 = list(P.exterior.coords)[:-1]
    zg = min(G.z(x, y, 0) for x, y in ring0) - 0.15
    top = it.get("top_z", zg + it.get("height", 1.0))
    fr = [(0.0, 0.0), (0.15, 0.55), (0.45, 0.88), (0.75, 1.0)]    # (inset fraction, height fraction): a domed rock
    verts, faces, n = [], [], len(ring0)
    for f, hz in fr:
        for x, y in ring0:
            verts.append((x + (cx - x) * f, y + (cy - y) * f, zg + (top - zg) * hz))
    for r in range(len(fr) - 1):
        for k in range(n):
            a, b = r * n + k, r * n + (k + 1) % n
            faces.append([a, b, b + n, a + n])
    faces.append(list(range((len(fr) - 1) * n, len(fr) * n)))
    dflt = (M or {}).get("_tones", {}).get("rock", (ROCK_A, ROCK_B))[:2]
    rock = stone(f"Rock {i}", *_two(it, *dflt), 3.0, 0.6)
    mesh(it.get("name", f"boulder {i}"), verts, faces, c, rock)


def _srgb(v):
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


DRYSTACK = {"course": (0.05, 0.15), "stone": (0.25, 0.75), "joint": 0.015, "joint_dark": 0.3,
            "jitter": (25, 22, 22), "bump": 0.008, "shadow": 0.035, "shadow_dark": 0.3, "step": 0.02}


def drystack(name, rgb_a, rgb_b, course=None, stone=None, joint=None, joint_dark=None, jitter=None, bump=None,
             shadow=None, shadow_dark=None, step=None):
    """Dry-stacked flat stone (ledgestone), in wall coordinates (object x along the wall, z up; k_retaining_wall
    builds each segment in such a frame):

    * courses of random height between ``course`` = (lo, hi) m: a 1-D Voronoi along z (randomness 1 gives cell
      lengths from 0.5 to 1.5 x the mean);
    * stones of random length ``stone`` = (lo, hi) m along each course: a 1-D Voronoi along x whose phase is shifted
      by a random number per course, so head joints never line up (no regular bond);
    * joint / shadow lines ``joint`` m wide (10-15 mm), darkened to ``joint_dark`` x the stone's sRGB value;
    * per-stone colour: the mean of the two tones (the yard item's colours) jittered by up to +-``jitter`` sRGB levels
      (r, g, b; one stone in eight down to -1.7 x ``jitter``, weathered), with a little warm / cool shift per stone and a
      faint grain;
    * per-stone relief of up to ``bump`` m (5-10 mm), joints recessed;
    * the shadow each course's overhanging stones cast on the top of the course below: a band ``shadow`` m deep
      under every bed joint, fading from ``shadow_dark`` x the stone's sRGB value (a 12 mm joint alone is under a pixel
      from the street, and dry-laid walls read by these shadow lines);
    * each stone sits up to +-``step`` / 2 m higher or lower than its neighbours, so bed joints step at every head joint.
    Joint edges are noise-distorted by a centimetre or two, so the courses wander like hand-laid stone."""
    P = dict(DRYSTACK)
    for k, v in (("course", course), ("stone", stone), ("joint", joint), ("joint_dark", joint_dark),
                 ("jitter", jitter), ("bump", bump), ("shadow", shadow), ("shadow_dark", shadow_dark), ("step", step)):
        if v is not None:
            P[k] = v
    mean = [0.5 * (a + b) for a, b in zip(rgb_a, rgb_b)]
    sm = [_srgb(v) * 255 for v in mean]
    lo = tuple(_lin(max(0.0, c - j) / 255) for c, j in zip(sm, P["jitter"]))
    hi = tuple(_lin(min(255.0, c + j) / 255) for c, j in zip(sm, P["jitter"]))
    darkest = tuple(_lin(max(0.0, c - 1.7 * j) / 255) for c, j in zip(sm, P["jitter"]))   # a few weathered stones
    m = mat(name, tuple(mean), 0.9)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    N = nt.nodes.new
    tc = N("ShaderNodeTexCoord")
    # wander: a centimetre-scale distortion of the coordinates
    wz = N("ShaderNodeTexNoise"); wz.inputs["Scale"].default_value = 4.0; wz.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Object"], wz.inputs["Vector"])
    dv = N("ShaderNodeVectorMath"); dv.operation = "MULTIPLY_ADD"; dv.inputs[1].default_value = (0.03, 0.03, 0.012)
    nt.links.new(wz.outputs["Color"], dv.inputs[0]); nt.links.new(tc.outputs["Object"], dv.inputs[2])
    sep = N("ShaderNodeSeparateXYZ"); nt.links.new(dv.outputs[0], sep.inputs[0])

    def vor1(w_socket, mean_len, feature, label):
        v = N("ShaderNodeTexVoronoi"); v.voronoi_dimensions = "1D"; v.feature = feature; v.label = label
        v.inputs["Scale"].default_value = 1.0 / mean_len; v.inputs["Randomness"].default_value = 1.0
        nt.links.new(w_socket, v.inputs["W"])
        return v
    c_mean = 0.5 * (P["course"][0] + P["course"][1]); s_mean = 0.5 * (P["stone"][0] + P["stone"][1])
    cid = vor1(sep.outputs["Z"], c_mean, "F1", "courses")                  # random number per course
    sh = N("ShaderNodeMath"); sh.operation = "MULTIPLY_ADD"; sh.inputs[1].default_value = 37.0
    nt.links.new(cid.outputs["Color"], sh.inputs[0]); nt.links.new(sep.outputs["X"], sh.inputs[2])
    sid = vor1(sh.outputs[0], s_mean, "F1", "stones")                     # random colour per stone
    sedge = vor1(sh.outputs[0], s_mean, "DISTANCE_TO_EDGE", "stones")     # head joints
    # bed joints again, with each stone's own vertical offset (joints step at the head joints)
    rs = N("ShaderNodeSeparateColor"); nt.links.new(sid.outputs["Color"], rs.inputs[0])
    zo = N("ShaderNodeMath"); zo.operation = "MULTIPLY_ADD"; zo.inputs[1].default_value = P["step"]
    zo.inputs[2].default_value = -0.5 * P["step"]
    nt.links.new(rs.outputs[2], zo.inputs[0])
    zs = N("ShaderNodeMath"); zs.operation = "ADD"
    nt.links.new(sep.outputs["Z"], zs.inputs[0]); nt.links.new(zo.outputs[0], zs.inputs[1])
    cedge = vor1(zs.outputs[0], c_mean, "DISTANCE_TO_EDGE", "courses (stepped)")
    cid2 = vor1(zs.outputs[0], c_mean, "F1", "courses (stepped)")
    # joint masks (1 in the joint): distance to the cell edge (scaled units) below half the joint width
    def jmask(edge, scale_):
        mr = N("ShaderNodeMapRange"); mr.clamp = True; mr.label = "joint"
        mr.inputs["From Min"].default_value = 0.5 * P["joint"] * scale_
        mr.inputs["From Max"].default_value = 0.9 * P["joint"] * scale_
        mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
        nt.links.new(edge.outputs["Distance"], mr.inputs["Value"])
        return mr
    jc, js = jmask(cedge, 1.0 / c_mean), jmask(sedge, 1.0 / s_mean)
    jm = N("ShaderNodeMath"); jm.operation = "MAXIMUM"; jm.label = "joints"
    nt.links.new(jc.outputs["Result"], jm.inputs[0]); nt.links.new(js.outputs["Result"], jm.inputs[1])
    # stone colour: lo..hi by the stone's random value, a warm / cool shift by a second random channel, faint grain
    rnd = N("ShaderNodeSeparateColor"); nt.links.new(sid.outputs["Color"], rnd.inputs[0])
    ramp = N("ShaderNodeValToRGB"); ramp.label = "stone jitter"
    ramp.color_ramp.elements[0].color = (*darkest, 1); ramp.color_ramp.elements[1].color = (*hi, 1)
    e = ramp.color_ramp.elements.new(0.12); e.color = (*lo, 1)
    nt.links.new(rnd.outputs[0], ramp.inputs["Fac"])
    warm = N("ShaderNodeMapRange"); warm.inputs["To Min"].default_value = -0.05; warm.inputs["To Max"].default_value = 0.05
    nt.links.new(rnd.outputs[1], warm.inputs["Value"])
    wv = N("ShaderNodeCombineXYZ")
    a1 = N("ShaderNodeMath"); a1.operation = "ADD"; a1.inputs[0].default_value = 1.0
    s1 = N("ShaderNodeMath"); s1.operation = "SUBTRACT"; s1.inputs[0].default_value = 1.0
    nt.links.new(warm.outputs["Result"], a1.inputs[1]); nt.links.new(warm.outputs["Result"], s1.inputs[1])
    nt.links.new(a1.outputs[0], wv.inputs["X"]); wv.inputs["Y"].default_value = 1.0; nt.links.new(s1.outputs[0], wv.inputs["Z"])
    tint = N("ShaderNodeMix"); tint.data_type = "RGBA"; tint.blend_type = "MULTIPLY"; tint.inputs["Factor"].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], tint.inputs[6]); nt.links.new(wv.outputs[0], tint.inputs[7])
    gr = N("ShaderNodeTexNoise"); gr.inputs["Scale"].default_value = 40.0; gr.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], gr.inputs["Vector"])
    grm = N("ShaderNodeMapRange"); grm.inputs["To Min"].default_value = 0.93; grm.inputs["To Max"].default_value = 1.07
    nt.links.new(gr.outputs["Fac"], grm.inputs["Value"])
    grain = N("ShaderNodeMix"); grain.data_type = "RGBA"; grain.blend_type = "MULTIPLY"; grain.inputs["Factor"].default_value = 1.0
    gv = N("ShaderNodeCombineXYZ")
    for k in ("X", "Y", "Z"):
        nt.links.new(grm.outputs["Result"], gv.inputs[k])
    nt.links.new(tint.outputs[2], grain.inputs[6]); nt.links.new(gv.outputs[0], grain.inputs[7])
    # joints: the stone colour at joint_dark x its sRGB value (linear factor joint_dark ** 2.2)
    jdk = P["joint_dark"] ** 2.2
    dark = N("ShaderNodeMix"); dark.data_type = "RGBA"; dark.blend_type = "MULTIPLY"; dark.label = "joint dark"
    dark.inputs[7].default_value = (jdk, jdk, jdk, 1)
    nt.links.new(jm.outputs[0], dark.inputs["Factor"]); nt.links.new(grain.outputs[2], dark.inputs[6])
    # overhang shadow: in the upper half of a course (above the course's feature point), within `shadow` of its edge
    above = N("ShaderNodeMath"); above.operation = "GREATER_THAN"
    nt.links.new(zs.outputs[0], above.inputs[0])
    nt.links.new(cid2.outputs["W"], above.inputs[1])                   # the course's feature point (metres)
    sdist = N("ShaderNodeMapRange"); sdist.clamp = True; sdist.label = "overhang shadow"
    sdist.inputs["From Min"].default_value = 0.5 * P["joint"] / c_mean
    sdist.inputs["From Max"].default_value = (0.5 * P["joint"] + P["shadow"]) / c_mean
    sdist.inputs["To Min"].default_value = 1.0; sdist.inputs["To Max"].default_value = 0.0
    nt.links.new(cedge.outputs["Distance"], sdist.inputs["Value"])
    sh2 = N("ShaderNodeMath"); sh2.operation = "MULTIPLY"
    nt.links.new(sdist.outputs["Result"], sh2.inputs[0]); nt.links.new(above.outputs[0], sh2.inputs[1])
    sdk = P["shadow_dark"] ** 2.2
    shade = N("ShaderNodeMix"); shade.data_type = "RGBA"; shade.blend_type = "MULTIPLY"; shade.label = "overhang shadow"
    shade.inputs[7].default_value = (sdk, sdk, sdk, 1)
    nt.links.new(sh2.outputs[0], shade.inputs["Factor"]); nt.links.new(dark.outputs[2], shade.inputs[6])
    nt.links.new(shade.outputs[2], b.inputs["Base Color"])
    # relief: each stone proud by up to `bump` (its random value), joints recessed, a little grain
    h = N("ShaderNodeMath"); h.operation = "MULTIPLY_ADD"; h.inputs[1].default_value = 0.5; h.inputs[2].default_value = 0.5
    nt.links.new(rnd.outputs[2], h.inputs[0])
    inv = N("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    nt.links.new(jm.outputs[0], inv.inputs[1])
    hh = N("ShaderNodeMath"); hh.operation = "MULTIPLY"
    nt.links.new(h.outputs[0], hh.inputs[0]); nt.links.new(inv.outputs[0], hh.inputs[1])
    hg = N("ShaderNodeMath"); hg.operation = "MULTIPLY_ADD"; hg.inputs[1].default_value = 0.15
    nt.links.new(gr.outputs["Fac"], hg.inputs[0]); nt.links.new(hh.outputs[0], hg.inputs[2])
    bp = N("ShaderNodeBump"); bp.label = "stone relief"
    bp.inputs["Strength"].default_value = 1.0; bp.inputs["Distance"].default_value = P["bump"]
    nt.links.new(hg.outputs[0], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    m.diffuse_color = (*mean, 1)
    m["drystack"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in P.items()}
    return m


def _wall_material(it, i):
    kind = it.get("material", "stone")
    if kind == "drystack":
        return drystack(f"Dry-stack stone {i}", *_two(it, (0.40, 0.35, 0.27), (0.66, 0.60, 0.50)), **it.get("drystack", {}))
    if kind == "concrete":
        return textured(f"Retaining wall (concrete) {i}", *_two(it, (0.40, 0.39, 0.36), (0.47, 0.46, 0.43)), 3.0, 0.08)
    if kind == "timber":
        return textured(f"Retaining wall (timber) {i}", *_two(it, (0.25, 0.18, 0.12), (0.33, 0.25, 0.17)), 5.0, 0.3)
    return textured(f"Retaining wall {i}", *_two(it, (0.45, 0.43, 0.40), (0.58, 0.56, 0.52)), 4.0, 0.5)


def _offset_line(line, dist):
    """Polyline offset by `dist` to its left (negative: right), mitred (same as build_site.offset_line)."""
    P = [Vector((x, y, 0)) for x, y in line]
    nrm = []
    for a, b in zip(P[:-1], P[1:]):
        d = b - a
        d = d.normalized() if d.length > 1e-9 else Vector((1, 0, 0))
        nrm.append(Vector((-d.y, d.x, 0)))
    out = []
    for k, p in enumerate(P):
        if k == 0 or k == len(P) - 1:
            n = nrm[min(k, len(nrm) - 1)]
        else:
            m = nrm[k - 1] + nrm[k]
            m = m.normalized() if m.length > 1e-9 else nrm[k]
            n = m / max(m.dot(nrm[k]), 0.35)
        out.append((p.x + dist * n.x, p.y + dist * n.y, 0.0))
    return out


def k_retaining_wall(it, G, c, M, i):
    """Wall along a polyline: mitred joints (no overlapping boxes), one level top per segment when
    top_z is a list (a stepped wall), foot 0.3 m under the lower of the two grades beside it."""
    line = [Vector((p[0], p[1], 0)) for p in it["line"]]
    th = it.get("thickness", 0.3)
    m_ = _wall_material(it, i)
    tops = it.get("top_z")
    nseg = len(line) - 1
    if nseg < 1:
        return
    if it.get("line_is", "centre") == "face":
        # the line is the exposed (downhill) face: move it half a thickness to the uphill side
        side = {"left": 1, "right": -1}.get(it.get("uphill"))
        if side is None:
            acc = 0.0
            for a, b in zip(line[:-1], line[1:]):
                d = b - a; d.z = 0
                if d.length < 1e-6:
                    continue
                n = Vector((-d.y, d.x, 0)).normalized(); mm = (a + b) / 2; off_ = th + 0.5
                acc += d.length * (G.z(mm.x + off_ * n.x, mm.y + off_ * n.y, 0) - G.z(mm.x - off_ * n.x, mm.y - off_ * n.y, 0))
            side = 1 if acc >= 0 else -1
        line = [Vector(p) for p in _offset_line([(p.x, p.y) for p in line], side * th / 2)]
    nrm = []
    for a, b in zip(line[:-1], line[1:]):
        d = (b - a); d.z = 0
        d = d.normalized() if d.length > 1e-6 else Vector((1, 0, 0))
        nrm.append(Vector((-d.y, d.x, 0)))
    off = []
    for k in range(len(line)):
        if k == 0 or k == nseg:
            off.append(nrm[min(k, nseg - 1)] * (th / 2))
        else:
            m = nrm[k - 1] + nrm[k]
            m = m.normalized() if m.length > 1e-6 else nrm[k]
            off.append(m * ((th / 2) / max(m.dot(nrm[k]), 0.35)))
    side = [o * (1 + 0.1 / max(th / 2, 1e-3)) for o in off]
    foot = [min(G.z(p.x + sx * o.x, p.y + sx * o.y, 0) for sx in (-1, 1)) - 0.3 for p, o in zip(line, side)]
    high = [max(G.z(p.x + sx * o.x, p.y + sx * o.y, 0) for sx in (-1, 1)) for p, o in zip(line, side)]
    for k in range(nseg):
        A, B = line[k], line[k + 1]
        if (B - A).length < 1e-3:
            continue
        if isinstance(tops, (list, tuple)):
            ta = tb = tops[min(k, len(tops) - 1)]
        elif tops is not None:
            ta = tops; tb = it.get("top_z_end", tops) if k == nseg - 1 else tops
        else:
            ta, tb = high[k] + it.get("height", 0.6), high[k + 1] + it.get("height", 0.6)
        za, zb = foot[k], foot[k + 1]
        ring = [A - off[k], B - off[k + 1], B + off[k + 1], A + off[k]]
        v = [(p.x, p.y, z) for p, z in zip(ring, (za, zb, zb, za))] + [(p.x, p.y, z) for p, z in zip(ring, (ta, tb, tb, ta))]
        ob = mesh(it.get("name", f"retaining wall {i}"), v, [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]], c, m_)
        # object frame: origin at A, local x along the segment, z up (textures that follow the wall use it)
        d = (B - A); d.z = 0; d.normalize()
        from mathutils import Matrix
        R = Matrix(((d.x, -d.y, 0, A.x), (d.y, d.x, 0, A.y), (0, 0, 1, 0), (0, 0, 0, 1)))
        ob.data.transform(R.inverted()); ob.matrix_world = R


def k_pier(it, G, c, M, i):
    """Square pier (gate / address pier) standing on the lowest grade under it, with an optional plaque
    of raised numerals on one face."""
    x, y = it["xy"]; w, d = it.get("size", [0.6, 0.6]); rot = it.get("rotation", 0.0)
    t = math.radians(rot)
    ex, ey = Vector((math.cos(t), math.sin(t), 0)), Vector((-math.sin(t), math.cos(t), 0))
    corners = [Vector((x, y, 0)) + ex * (sx * w / 2) + ey * (sy * d / 2) for sx in (-1, 1) for sy in (-1, 1)]
    zb = min(G.z(p.x, p.y, 0) for p in corners) - 0.1
    top = it.get("top_z", zb + 0.1 + it.get("height", 1.2))
    m_ = _wall_material(dict(it, material=it.get("material", "concrete")), i)
    obox(it.get("name", f"pier {i}"), (x, y), (w, d), zb, top, rot, c, m_)
    pl = it.get("plaque")
    if pl and pl.get("text"):
        face = pl.get("face", "-y")
        nrm = {"+x": ex, "-x": -ex, "+y": ey, "-y": -ey}[face]
        half = (w if face[1] == "x" else d) / 2
        cur = bpy.data.curves.new(f"pier {i} numerals", type="FONT")
        cur.body = str(pl["text"]); cur.size = pl.get("size", 0.18); cur.extrude = 0.008
        cur.align_x = "CENTER"; cur.align_y = "CENTER"
        ob = bpy.data.objects.new(it.get("name", f"pier {i}") + " numerals", cur)
        c.objects.link(ob)
        zc = pl.get("z", top - pl.get("below_top", 0.35))
        ob.location = Vector((x, y, zc)) + nrm * (half + 0.01)
        # text lies in its local XY plane: stand it up and turn it to face along nrm
        ob.rotation_euler = (math.radians(90), 0, math.atan2(nrm.y, nrm.x) + math.radians(90))
        ob.data.materials.append(mat(f"Pier numerals {i}", tuple(pl.get("color", (0.75, 0.22, 0.06))), 0.5))


def k_steps(it, G, c, M, i):
    """Landscape steps from line[0] (z0) up to line[1] (z1): `risers` treads, each a block from the grade
    under it (or a little below its own nose) to its tread height."""
    (ax_, ay_), (bx_, by_) = it["line"][:2]
    n = int(it.get("risers", 6)); w = it.get("width", 1.2)
    z0, z1 = it["z0"], it["z1"]
    L = math.hypot(bx_ - ax_, by_ - ay_)
    rot = math.degrees(math.atan2(by_ - ay_, bx_ - ax_))
    m_ = textured(f"Steps {i}", *_two(it, (0.42, 0.30, 0.22), (0.52, 0.40, 0.30)), 6.0, 0.3)
    for k in range(n):
        s0, s1 = k / n, (k + 1) / n
        cx, cy = ax_ + (bx_ - ax_) * (s0 + s1) / 2, ay_ + (by_ - ay_) * (s0 + s1) / 2
        top = z0 + (z1 - z0) * (k + 1) / n
        base = min(G.z(cx, cy, top), top - 0.15) - 0.1
        obox(f"{it.get('name', 'steps')} {i} tread {k}", (cx, cy), (L / n + 0.03, w), base, top, rot, c, m_)


def k_rock_scatter(it, G, c, M, i):
    """Loose landscape rocks scattered in a bed (seeded, so rebuilds are identical)."""
    import random
    from shapely.geometry import Polygon, Point
    P = Polygon(it["polygon"]).buffer(0)
    for h in it.get("holes", []):                  # keep clear of boulders / features inside the bed
        P = P.difference(Polygon(h).buffer(0.1))
    P = P.buffer(-0.2)
    if P.is_empty:
        return
    rnd = random.Random(it.get("seed", 1))
    lo, hi = it.get("size", [0.3, 0.7])
    x0, y0, x1, y1 = P.bounds
    placed = []
    for _ in range(int(it.get("count", 10)) * 30):
        if len(placed) >= int(it.get("count", 10)):
            break
        x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        r = rnd.uniform(lo, hi) / 2
        if not P.contains(Point(x, y)) or any(math.hypot(x - px, y - py) < r + pr + 0.1 for px, py, pr in placed):
            continue
        placed.append((x, y, r))
        nv = 9; ph = rnd.uniform(0, math.pi)
        poly = [(x + r * rnd.uniform(0.75, 1.15) * math.cos(ph + 2 * math.pi * q / nv) * (1.0 if q % 2 else 1.15),
                 y + r * rnd.uniform(0.75, 1.15) * math.sin(ph + 2 * math.pi * q / nv)) for q in range(nv)]
        zg = G.z(x, y, 0)
        hlo, hhi = it.get("height", [0.45, 0.7])          # height as a fraction of the stone's width (bedded stones: low)
        k_boulder({"polygon": poly, "top_z": zg + 2 * r * rnd.uniform(hlo, hhi), "color": it.get("color"),
                   "name": f"{it.get('name', 'rock')} {len(placed)}"}, G, c, M, f"{i}.{len(placed)}")


def k_path_light(it, G, c, M, i):
    x, y = it["xy"]; z = _base(it, G, x, y)
    h = it.get("height", 0.5)
    m_ = mat("Path light (black)", tuple(it.get("color", (0.03, 0.03, 0.03))), 0.4, 0.3)
    cylinder(f"path light {i} post", (x, y), 0.025, z - 0.1, z + h, c, m_, seg=12)
    cylinder(f"path light {i} lens", (x, y), 0.05, z + h, z + h + 0.06, c, mat("Path light lens", (0.85, 0.82, 0.70), 0.3), seg=16)
    # mushroom cap: flat cone
    seg = 20; r = it.get("cap", 0.13)
    v = [(x + r * math.cos(2 * math.pi * k / seg), y + r * math.sin(2 * math.pi * k / seg), z + h + 0.06) for k in range(seg)]
    v.append((x, y, z + h + 0.13))
    f = [[k, (k + 1) % seg, seg] for k in range(seg)] + [list(range(seg))[::-1]]
    mesh(f"path light {i} cap", v, f, c, m_)


def k_grade_pad(it, G, c, M, i):
    if it.get("surface"):
        k_surface(dict(it, color=it["surface"], name=it.get("name", "graded pad")), G, c, M, i)


def k_fence(it, G, c, M, i):
    H0 = it.get("height", 1.2)
    m_ = mat(f"Fence {i}", tuple(it.get("color", (0.35, 0.27, 0.2))), 0.8)
    style = it.get("style", "rail")
    line = it["line"]
    top_z = it.get("top_z")
    zg = (lambda x, y: G.z(x, y, 0)) if "z" not in it else (lambda x, y: it["z"])
    H = H0 if top_z is None else max(top_z - min(zg(p[0], p[1]) for p in line), 0.3)
    for a, b in zip(line[:-1], line[1:]):
        d = Vector((b[0] - a[0], b[1] - a[1], 0)); L = d.length
        if L < 1e-3:
            continue
        npost = max(1, int(math.ceil(L / 2.4)))
        for k in range(npost + 1):
            p = Vector((a[0], a[1], 0)) + d * (k / npost)
            z = zg(p.x, p.y)
            box(f"fence {i} post", (p.x - 0.045, p.y - 0.045, z - 0.1), (p.x + 0.045, p.y + 0.045, (top_z if top_z is not None else z + H)), c, m_)
        za, zb = zg(a[0], a[1]), zg(b[0], b[1])
        if top_z is not None:                       # level top rail: measured from the top down
            za = zb = top_z - H
        dn = d.normalized(); side = Vector((-dn.y, dn.x, 0)) * 0.02
        for hz in ((0.25, H - 0.08) if style not in ("picket", "baluster") else (0.1, H - 0.07)):
            A, B = Vector((a[0], a[1], za + hz)), Vector((b[0], b[1], zb + hz))
            v = [A - side, B - side, B + side, A + side]
            vv = [(p.x, p.y, p.z) for p in v] + [(p.x, p.y, p.z + 0.07) for p in v]
            mesh(f"fence {i} rail", vv, [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]], c, m_)
        if style in ("picket", "baluster"):
            gap, w2 = (0.14, 0.03) if style == "picket" else (0.12, 0.02)
            np_ = max(int(L / gap), 1)
            for k in range(np_):
                p = Vector((a[0], a[1], 0)) + d * ((k + 0.5) / np_)
                z = za + (zb - za) * (k + 0.5) / np_
                z0 = z + 0.05 if top_z is None else max(zg(p.x, p.y), z + 0.05)
                box(f"fence {i} picket", (p.x - w2, p.y - w2, z0), (p.x + w2, p.y + w2, z + H - 0.05), c, m_)


def _drape(P, G, lift, step=0.5):
    import shapely
    from shapely.geometry import Polygon as SP
    verts, tris = [], []
    bx0, by0, bx1, by1 = P.bounds
    gx = math.floor(bx0 / step) * step
    while gx < bx1:
        gy = math.floor(by0 / step) * step
        while gy < by1:
            cp = P.intersection(SP([(gx, gy), (gx + step, gy), (gx + step, gy + step), (gx, gy + step)]))
            if not cp.is_empty and cp.area > 1e-4:
                for t in shapely.constrained_delaunay_triangles(cp).geoms:
                    if t.area < 1e-6:
                        continue
                    b0 = len(verts)
                    for x, y in list(t.exterior.coords)[:3]:
                        verts.append((x, y, G.z(x, y, 0) + lift))
                    tris.append([b0, b0 + 1, b0 + 2])
            gy += step
        gx += step
    return verts, ccw_tris(verts, tris)


def k_surface(it, G, c, M, i):
    from shapely.geometry import Polygon
    P = Polygon(it["polygon"]).buffer(0)
    v, t = _drape(P, G, it.get("lift", 0.025))
    m_ = textured(f"{it.get('name', 'surface')} {i}", *_two(it, (0.30, 0.27, 0.23), (0.48, 0.44, 0.38)), it.get("scale", 10.0), 0.6)
    if t:
        mesh(it.get("name", f"surface {i}"), v, t, c, m_)


def k_path(it, G, c, M, i):
    from shapely.geometry import LineString
    P = LineString(it["line"]).buffer(it.get("width", 0.9) / 2, cap_style="flat")
    v, t = _drape(P, G, it.get("lift", 0.03))
    m_ = textured(f"{it.get('name', 'path')} {i}", *_two(it, (0.55, 0.55, 0.52), (0.62, 0.62, 0.59)), it.get("scale", 4.0), 0.3)
    if t:
        mesh(it.get("name", f"path {i}"), v, t, c, m_)


def k_hot_tub(it, G, c, M, i):
    x, y = it["xy"]; z = _base(it, G, x, y)
    w, d, h = it.get("size", [2.1, 2.1, 0.9])
    obox("hot tub cabinet", (x, y), (w, d), z, z + h - 0.08, it.get("rotation", 0), c, mat("Hot tub cabinet", tuple(it.get("color", (0.30, 0.22, 0.16))), 0.7))
    obox("hot tub cover", (x, y), (w - 0.04, d - 0.04), z + h - 0.08, z + h, it.get("rotation", 0), c, mat("Hot tub cover", tuple(it.get("cover_color", (0.22, 0.24, 0.25))), 0.6))


def k_mailbox(it, G, c, M, i):
    x, y = it["xy"]; z = _base(it, G, x, y)
    m_ = mat("Mailbox", tuple(it.get("color", (0.08, 0.08, 0.08))), 0.4, 0.4)
    box("mailbox post", (x - 0.05, y - 0.05, z), (x + 0.05, y + 0.05, z + 1.05), c, mat("Mailbox post", (0.25, 0.2, 0.15), 0.8))
    obox("mailbox", (x, y), (0.48, 0.2), z + 1.05, z + 1.28, it.get("rotation", 0), c, m_)


def k_light_post(it, G, c, M, i):
    x, y = it["xy"]; z = _base(it, G, x, y)
    m_ = mat("Lamp post", (0.05, 0.05, 0.05), 0.4, 0.5)
    cylinder("lamp post", (x, y), 0.05, z, z + it.get("height", 1.8), c, m_, seg=12)
    box("lamp head", (x - 0.13, y - 0.13, z + it.get("height", 1.8)), (x + 0.13, y + 0.13, z + it.get("height", 1.8) + 0.3), c,
        mat("Lamp glass", (0.85, 0.82, 0.7), 0.3))


EXTRA_KINDS = {"boulder": k_boulder, "retaining_wall": k_retaining_wall, "fence": k_fence, "surface": k_surface,
               "path": k_path, "hot_tub": k_hot_tub, "mailbox": k_mailbox, "light_post": k_light_post,
               "pier": k_pier, "steps": k_steps, "rock_scatter": k_rock_scatter, "path_light": k_path_light,
               "grade_pad": k_grade_pad}


def main():
    blend, scene_path, yard_path, out = args()[:4]
    bpy.ops.wm.open_mainfile(filepath=blend)
    S = json.load(open(scene_path))
    Y = json.load(open(yard_path)) if yard_path and yard_path != "-" else {}
    c = coll("Site")
    ov = Y.get("materials", {})

    def two(key, a_, b_, alias=None):
        v = ov.get(key) or (ov.get(alias) if alias else None)
        return (tuple(v[0]), tuple(v[1])) if v else (a_, b_)
    M = {
        "ground": textured("Ground (LiDAR terrain)", *two("ground", (0.10, 0.22, 0.05), (0.18, 0.30, 0.08), "lawn"), 6.0, 0.15),
        "rock": stone("Rock (boulders, outcrops)", *two("rock", ROCK_A, ROCK_B), 2.5, 0.7),
        "_tones": {"ground": (*two("ground", (0.10, 0.22, 0.05), (0.18, 0.30, 0.08), "lawn"), 6.0),
                   "rock": (*two("rock", ROCK_A, ROCK_B), 2.5)},
        "street": textured("Street (asphalt)", *two("street", (0.27, 0.27, 0.25), (0.33, 0.33, 0.31)), 3.0, 0.05),
        "concrete": textured("Concrete", *two("concrete", (0.55, 0.55, 0.52), (0.62, 0.62, 0.59)), 2.0, 0.05),
        "rock_bed": textured("Rock mulch", *two("rock_bed", (0.30, 0.27, 0.23), (0.48, 0.44, 0.38)), 14.0, 0.8),
        "curb": mat("Curb", (0.5, 0.48, 0.45), 0.9),
        "hydrant": mat("Hydrant (yellow)", (0.85, 0.65, 0.05), 0.5),
        "metal": mat("Metal (grey)", (0.45, 0.46, 0.47), 0.5, 0.6),
        "stone": textured("Fire-pit stone", (0.38, 0.36, 0.33), (0.55, 0.52, 0.48), 8.0, 0.4),
        "ac": mat("AC unit", (0.75, 0.75, 0.73), 0.5, 0.3),
        "parcel": mat("Lot line", (0.95, 0.2, 0.2), 0.5),
    }
    M["lawn"] = M["ground"]
    # terrain (ground / rock faces) + draped overlays
    # explicit triangles along each cell's chosen fold (the same triangles the overlays were draped on); smooth
    # shading with creases kept sharp (> SHARP_DEG) and area-weighted normals: no dark folded shards on slopes
    ttris, fc = terrain_triangles(S["faces"], S.get("face_class") or [])
    terrain = mesh("Terrain (LiDAR ground)", S["verts"], ttris, c, M["ground"])
    nsharp = sharpen(terrain)
    print(f"terrain: {len(ttris)} triangles, {nsharp} sharp edges (> {SHARP_DEG:.0f} deg)")
    classes = S.get("classes", [])
    if S.get("vertex_rock") and len(S["vertex_rock"]) == len(S["verts"]) and any(v > 0 for v in S["vertex_rock"]):
        # one material blending ground and rock by the per-vertex rock weight (soft boulder edges)
        at = terrain.data.attributes.new("rock", "FLOAT", "POINT")
        at.data.foreach_set("value", S["vertex_rock"])
        terrain.data.materials.clear()
        terrain.data.materials.append(blend_by_attribute("Terrain (ground / rock)", M["_tones"]["ground"],
                                                         M["_tones"]["rock"], "rock"))
    elif "rock" in classes and any(v == classes.index("rock") for v in fc):
        terrain.data.materials.append(M["rock"])
        rk = classes.index("rock")
        terrain.data.polygons.foreach_set("material_index", [1 if v == rk else 0 for v in fc])
        terrain.data.update()
    for k, ovl in S.get("overlays", {}).items():
        if ovl["tris"]:
            ob_ = mesh(f"{k.replace('_', ' ')} (draped)", ovl["verts"], ccw_tris(ovl["verts"], ovl["tris"]), c,
                       M.get(k, M["concrete"]))
            # the drape is a triangle soup: weld it so smooth shading follows the ground instead of facets
            bm = bmesh.new(); bm.from_mesh(ob_.data)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
            bm.to_mesh(ob_.data); bm.free()
            ob_.data.polygons.foreach_set("use_smooth", [True] * len(ob_.data.polygons))
            ob_["site_kind"] = "overlay:" + k
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
        mesh(f"bed edging {i}", verts, faces, c, M["curb"])["site_kind"] = "edging"
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
        mesh(f"curb {i}", verts, faces, c, M["curb"])["site_kind"] = "curb"
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
        lot = mesh("Lot line (subject parcel)", verts, faces, c, M["parcel"])
        lot.hide_render = not Y.get("show_parcel", False)
    # point features
    for p in S.get("points", []):
        if p["kind"] == "hydrant":
            x, y = p["xy"]; z = G.z(x, y, 0)
            cylinder("fire hydrant body", (x, y), 0.11, z, z + 0.62, c, M["hydrant"])
            cylinder("fire hydrant bonnet", (x, y), 0.13, z + 0.62, z + 0.72, c, M["hydrant"])
            box("fire hydrant nozzle", (x - 0.2, y - 0.05, z + 0.42), (x + 0.2, y + 0.05, z + 0.52), c, M["hydrant"])
    seen, prev = {o.name for o in c.objects}, None
    for i, it in enumerate(Y.get("items", []) + [None]):
        for o in c.objects:     # tag what the previous item made with its kind (render_thumbnail keeps hardscape)
            if o.name not in seen:
                o["site_kind"] = prev; seen.add(o.name)
        if it is None:
            break
        k = prev = it["kind"]
        if k in EXTRA_KINDS:
            EXTRA_KINDS[k](it, G, c, M, i)
            continue
        x, y = it["xy"]; z = G.z(x, y, 0)
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
            if "top_z" in it:      # absolute top: stand on the lowest grade under the footprint
                t_ = math.radians(it.get("rotation", 0.0))
                z = min(G.z(x + sx * w / 2 * math.cos(t_) - sy * d / 2 * math.sin(t_),
                            y + sx * w / 2 * math.sin(t_) + sy * d / 2 * math.cos(t_), z)
                        for sx in (-1, 1) for sy in (-1, 1)) - 0.05
                h = it["top_z"] - z
            else:
                z += it.get("z", 0.0)
            m_ = mat(f"{it.get('name', 'item')} colour", tuple(it["color"]), 0.6) if it.get("color") else M.get(it.get("material", "concrete"), M["concrete"])
            obox(it.get("name", f"item {i}"), (x, y), (w, d), z, z + h, it.get("rotation", 0.0), c, m_)
    # ---- ground the house -----------------------------------------------------
    # walls of an upper storey that stands on a lower one (or cantilevers over it) keep their bottoms
    keep = set(Y.get("keep_wall_bottoms", []))
    wc = bpy.data.collections.get("Walls")
    walls = [o for o in (wc.objects if wc else []) if not (len(o.name.split()) > 1 and o.name.split()[1] in keep)]
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
