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
             #   a smooth-shaded dome: the outline (+ 4-point midpoints) in 8 cos-spaced rings, h = (1 - rho^2.5)^(1/2),
             #   built of explicit triangles (each side quad folded along its closest-z, then shorter, diagonal: split_quad)
             #   ("rings", "dome": [a, b], "subdivide" override), broad rounded top at top_z; rings never lean out over
             #   the ring below (no undercut at concave outline corners); "surface": "foliage" gives a leafy two-tone
             #   material without joints or bedding (a mass the LiDAR cannot tell from rock, e.g. dense juniper);
             #   "foot": "terrain" starts the dome at the terrain under each outline point (default: every ring from the
             #   outline's lowest grade - 0.15, which on a slope meets the upper ground as a steep sheet); "max_over_terrain":
             #   m clamps every dome vertex to min(dome z, terrain z + m) (terrain from the site_scene grid, bilinear), so an
             #   assumed dome profile never stands far over a flank the LiDAR terrain already follows;
             #   "max_over_terrain_local": [{"xy": [x,y], "radius": r, "max": m}] uses m within r of xy (a flank whose
             #   terrain grid sits under the measured rock side at the outline edge)
             {"kind": "retaining_wall", "line": [[x,y],...], "top_z": z or "height": h, "thickness": 0.3,
              "material": "stone|concrete|drystack|timber|rock", "color": [r,g,b], "line_is": "centre|face", "uphill": "left|right",
              "cap_color": [[r,g,b],[r,g,b]]},          # optional: a separate (e.g. lighter) material on the top faces
             #   "top_z": [z, z, ...] (one per segment) gives a stepped wall with level tops; the bottom goes
             #   0.3 m under the lower of the two grades beside it (build_site.py --breaklines yard.json
             #   makes the terrain step inside the wall). "line_is": "face": the line is the exposed (downhill)
             #   face as measured from the LiDAR step, the thickness goes to the uphill side ("uphill": left /
             #   right of the line direction, or the higher grade). "rock": a natural rock face (boulder or ledge edge
             #   the terrain steps at) in the boulder sandstone material. "drystack" is dry-laid thin flat stone:
             #   independent random course heights (0.04-0.12 m, U-shaped: thin and thick courses side by side, every 1 m
             #   of wall >= 7 courses with a height CoV >= 0.32; a packed 1-D course texture along z) and stone lengths
             #   (0.15-0.6 m, mean stretched +-15 % per course, random stagger), per-stone colour drawn from the item's
             #   colour range (default buff sandstone), 12 % of the stones x1.2 brighter, dark brown-grey 12 mm joints
             #   recessed 1.5 cm, a 5 cm shadow under every bed joint, plain stone colour on the top faces;
             #   "drystack": {"course": [lo, hi], "stone": [lo, hi], "joint": m, "joint_color": [r, g, b], "bump": m,
             #   "shadow": m, "lift": share, "lift_k": x, "seed": n, ...} overrides (see drystack()).
             {"kind": "pier", "xy": [x,y], "size": [w,d], "top_z": z, "rotation": deg, "material": "concrete",
              "plaque": {"text": "...", "face": "-x|+x|-y|+y", "color": [r,g,b], "size": 0.18, "below_top": 0.35,
                         "scale_x": 1.0, "offset": 0.0}},   # numerals on a face; size = font size (digit height ~0.7 x
             #   size), scale_x squeezes them horizontally (the default font's digits are ~0.44 x size wide), offset moves
             #   them along the face (m, + = to the right seen from the front)
             #   prints a WARNING when the plaque face lies inside a retaining wall's solid or behind one taller than it
             {"kind": "steps", "line": [[x,y],[x,y]], "width": 1.2, "z0": z_bottom, "z1": z_top, "risers": n,
              "color": [r,g,b], "tread": {"slab": 0.05, "gap": 0.06, "fill": [[r,g,b],[r,g,b]]}},
             #   landscape steps, each tread grounded; "tread": slabs of the step colour on a fill block (default the
             #   rock-bed material) that shows as a `gap` m strip between treads; every tread top stays >= "clearance"
             #   (default 0.03 m; negative = off) above the terrain under the middle of its run (LiDAR ground over a stair
             #   is a ramp through the tread middles) and never below the tread before it; build_site.py --step-caps keeps
             #   the terrain under the treads below the line z0 -> z1
             {"kind": "rock_scatter", "polygon": [[x,y],...], "count": 12, "size": [0.3, 0.7], "seed": 1,
              "holes": [[[x,y],...]], "color": [[r,g,b],[r,g,b]]},
             #   angular, partly buried flat stones (5-7-sided outlines, +-25 % radius jitter, 0.6-0.9 across, height
             #   0.35-0.5 x the width, bevelled tilted flat top, random yaw, 30 % below grade), each coloured from the
             #   colour range; "stones": [[x, y, diameter], ...] places measured stones instead of `count` random ones;
             #   "shape": "ico" (older noisy icospheres) or "dome" + "height" (fraction of the width above grade)
             {"kind": "path_light", "xy": [x,y], "height": 0.5},
             {"kind": "grade_pad", "polygon": [[x,y],...], "z": z, "blend": 0.8, "surface": [[r,g,b],[r,g,b]]},
             #   levelled by build_site.py --grade yard.json; here only its optional surface is draped
             {"kind": "box", ..., "top_z": z}   # absolute top: the box stands on the lowest grade under it
             {"kind": "fence", "line": [[x,y],...], "height": 1.2 or "top_z": z, "style": "rail|picket|baluster|chain", "color": [r,g,b]},
             {"kind": "surface", "polygon": [[x,y],...], "color": [[r,g,b],[r,g,b]], "scale": 10, "lift": 0.025, "name": "..."},
             {"kind": "path", "line": [[x,y],...], "width": 0.9, "color": [[r,g,b],[r,g,b]]},    # draped strip
             #   surfaces and paths are draped exactly on the terrain triangles (drape_exact) + lift
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
it, rock faces get the rock material slot. The default rock tone is buff sandstone (ROCK_A/ROCK_B). Terrain vertices
within 0.1 m of a yard "boulder" outline carry that boulder's colour range in two point colour attributes (rock_tone_lo /
rock_tone_hi; boulder_tones) that the blended material's rock tone reads, so terrain the LiDAR raised inside a boulder
renders as the same stone where it pokes through the dome ("boulder_tones": false in yard.json turns it off).
The terrain is built from explicit triangles along each cell's fold (see build_site.py split_diagonals), so it
renders on exactly the triangles the overlays were draped on; it is smooth-shaded with edges sharper than
SHARP_DEG marked sharp and area-weighted normals (WeightedNormal, keep sharp). Draped overlays are
smooth-shaded and wound counter-clockwise (normals up) for viewers that cull back faces.

Materials: every material add_site makes carries the custom property "propmodel_site" (SITE_TAG). A material of the
same name that the house blend already uses (e.g. add_details' 'Concrete' on concrete walls, coloured from the photos) is
never taken over or recoloured: the site builds 'Site <name>' instead (the draped driveway / walk concrete is then
'Site Concrete'; look it up through the 'concrete (draped)' object, not by the bare name).

Every Site object carries a custom property "site_kind": the yard item kind that made it ("retaining_wall",
"pier", ...), "overlay:<name>" for draped overlays, "curb" or "edging" (render_thumbnail.py --terrain keeps
the hardscape by it).

Reference geometry: once the scene has a terrain, build_model.py's flat reference ground planes ("Ground (grade)",
"Ground ortho*") are hidden in renders and viewports (hide_reference) -- the LiDAR terrain is the only ground, and a
flat plane at the model datum would cover everything below it on a hillside lot -- and the QA collections "Labels",
"Roof edges", "LiDAR points" and "Reference data" are excluded from renders (their viewport visibility is kept).

Grounding: walls and foundation strips are extended to 0.3 m below the terrain under them
(terrain is the LiDAR ground, so the house sits exactly as surveyed), deck posts, stair
stringers, downspouts, piers and stoops are cut to land on the terrain. Everything added goes
to collection "Site"; the measured roof/walls keep their geometry above grade.
"""
import json
import math
import random
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
# build_model.py reference ground the LiDAR terrain replaces (flat grade plane, ortho plane) and its QA collections
REFERENCE_GROUND = ("Ground (grade)", "Ground ortho")
QA_COLLECTIONS = ("Labels", "Roof edges", "LiDAR points", "Reference data")


def reference_ground(names, prefixes=REFERENCE_GROUND):
    """The names among `names` that are build_model reference ground planes (replaced by the terrain)."""
    return [n for n in names if n.startswith(tuple(prefixes))]


def hide_reference(objects, collections, terrain=True):
    """With a terrain: hide the reference ground planes in renders and viewports (so neither a render nor a ray cast
    meets a flat plane at the model datum) and exclude the QA collections from renders, keeping them in the viewport.
    `objects` / `collections`: bpy.data.objects / bpy.data.collections (or anything with .name / .hide_render /
    .hide_viewport). Returns (plane names, collection names) changed."""
    if not terrain:
        return [], []
    planes = set(reference_ground([o.name for o in objects]))
    for o in objects:
        if o.name in planes:
            o.hide_render = True
            o.hide_viewport = True
    cols = [c for c in collections if c.name in QA_COLLECTIONS]
    for c in cols:
        c.hide_render = True
    return sorted(planes), [c.name for c in cols]


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


def overlay_nodes(grid, pts_xy=(), polys=(), pad=0.75):
    """Bool mask (ny * nx, grid order) of the terrain grid nodes that carry draped overlays: the four corners of every
    cell holding an overlay vertex (``pts_xy``: the scene's street / concrete / bed overlay vertices, draped on the
    terrain triangles by build_site) or meeting a polygon (``polys``: yard surfaces / paths draped here, grown by
    ``pad`` cells)."""
    import numpy as np
    nx, ny, c = int(grid["nx"]), int(grid["ny"]), float(grid["cell"])
    x0, y0 = float(grid["x0"]), float(grid["y0"])
    cells = np.zeros((ny - 1, nx - 1), bool)
    P = np.asarray(pts_xy, float).reshape(-1, 2)
    if len(P):
        i = np.clip(np.floor((P[:, 0] - x0) / c).astype(int), 0, nx - 2)
        j = np.clip(np.floor((P[:, 1] - y0) / c).astype(int), 0, ny - 2)
        cells[j, i] = True
    if polys:
        import shapely
        from shapely.geometry import Polygon
        cx, cy = np.meshgrid(x0 + c * (np.arange(nx - 1) + 0.5), y0 + c * (np.arange(ny - 1) + 0.5))
        for ring in polys:
            if len(ring) < 3:
                continue
            pg = Polygon([q[:2] for q in ring]).buffer(0)
            if pg.is_empty:
                continue
            bx0, by0, bx1, by1 = pg.bounds
            m = (cx >= bx0 - c) & (cx <= bx1 + c) & (cy >= by0 - c) & (cy <= by1 + c)
            if m.any():
                cells[m] |= shapely.contains_xy(pg.buffer(pad * c), cx[m], cy[m])
    out = np.zeros((ny, nx), bool)
    out[:-1, :-1] |= cells; out[:-1, 1:] |= cells; out[1:, :-1] |= cells; out[1:, 1:] |= cells
    return out.ravel()


def LineStringBuffer(line, half_width):
    """Outline ring of a path centre line buffered by half its width (for overlay_nodes)."""
    from shapely.geometry import LineString
    g = LineString([q[:2] for q in line]).buffer(half_width, cap_style="flat")
    return list(g.exterior.coords) if not g.is_empty and g.geom_type == "Polygon" else None


def smooth_face_normals(ob, grid, range_min=1.0, rings=2, laplace=0.5, max_dz=0.3, fixed=None):
    """Shading of steep rock faces: a cliff running obliquely across the terrain grid is a staircase of cell-wide
    steps, whose triangles face alternately left and right of the cliff -- smooth shading then shows vertical flutes and
    dark triangular 'fangs' along the crest and foot. The terrain's normals are first baked (the WeightedNormal modifier
    is applied into custom normals), then every corner of a vertex whose 8-neighbour height range exceeds `range_min` m
    (the 'rock face' vertex group, also written) gets the area-weighted normal averaged over (2 `rings` + 1)^2 grid
    vertices: the face is shaded as the face, the geometry (measured heights) is untouched. `grid` = the scene's
    {"nx", "ny", "z"[, "x0", "y0", "cell"]} (terrain vertices in grid order; with the origin and cell, vertices off the
    regular grid -- breakline nodes snapped onto a retaining-wall face -- are not moved). `fixed` (bool per vertex,
    overlay_nodes()): vertices under a draped overlay are not moved either -- the overlays lie on the unsmoothed
    triangles, and a vertex the pass lifts pokes the terrain through them. Returns the number of face vertices."""
    import numpy as np
    nx, ny = int(grid["nx"]), int(grid["ny"])
    me = ob.data
    if len(me.vertices) != nx * ny:
        return 0
    Z = np.asarray(grid["z"], float).reshape(ny, nx)
    from scipy import ndimage
    rng_ = ndimage.maximum_filter(Z, size=3, mode="nearest") - ndimage.minimum_filter(Z, size=3, mode="nearest")
    face = (rng_ > range_min).ravel()
    if not face.any():
        return 0
    if laplace and laplace > 0:
        # one Laplacian pass (factor `laplace`) over the rock-face vertices: the staircase a grid makes of an oblique cliff
        # is pulled towards its neighbours (in plan mostly; height change limited to +-`max_dz` m so measured crests stay).
        # Breakline vertices (build_site snapped them off the regular grid onto a retaining-wall face) stay put: they
        # carry the wall's step exactly on its faces, and the overlays were draped on them
        movable = face.copy()
        if fixed is not None and len(fixed) == len(movable):
            movable &= ~np.asarray(fixed, bool)
        if "x0" in grid and "cell" in grid:
            co = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
            jj, ii = np.divmod(np.arange(nx * ny), nx)
            reg = np.column_stack([grid["x0"] + ii * grid["cell"], grid["y0"] + jj * grid["cell"]])
            movable &= np.hypot(*(co[:, :2] - reg).T) < 1e-4
        bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
        sel = [bm.verts[int(k)] for k in np.nonzero(movable)[0]]
        z0 = {v.index: v.co.z for v in sel}
        bmesh.ops.smooth_vert(bm, verts=sel, factor=float(laplace), use_axis_x=True, use_axis_y=True, use_axis_z=True)
        for v in sel:
            v.co.z = min(max(v.co.z, z0[v.index] - max_dz), z0[v.index] + max_dz)
        bm.to_mesh(me); bm.free(); me.update()
    # bake the modifier stack (weighted normals, sharp creases) into the mesh's custom normals
    dg = bpy.context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = new
    new.name = old.name
    bpy.data.meshes.remove(old)
    me = ob.data
    nl = len(me.loops)
    cn = np.zeros(nl * 3); me.corner_normals.foreach_get("vector", cn); cn = cn.reshape(-1, 3)
    lv = np.zeros(nl, int); me.loops.foreach_get("vertex_index", lv)
    npoly = len(me.polygons)
    pn = np.zeros(npoly * 3); me.polygons.foreach_get("normal", pn); pn = pn.reshape(-1, 3)
    pa = np.zeros(npoly); me.polygons.foreach_get("area", pa)
    lt = np.zeros(npoly, int); me.polygons.foreach_get("loop_total", lt)
    lp = np.repeat(np.arange(npoly), lt)
    vn = np.zeros((len(me.vertices), 3))
    np.add.at(vn, lv, pn[lp] * pa[lp, None])
    k = 2 * int(rings) + 1
    G = np.stack([ndimage.uniform_filter(vn[:, d].reshape(ny, nx), size=k, mode="nearest").ravel() for d in range(3)], 1)
    G /= np.maximum(np.linalg.norm(G, axis=1, keepdims=True), 1e-12)
    sel = face[lv]
    cn[sel] = G[lv[sel]]
    me.normals_split_custom_set([tuple(v) for v in cn])
    vg = ob.vertex_groups.new(name="rock face")
    vg.add([int(v) for v in np.nonzero(face)[0]], 1.0, "REPLACE")
    me.update()
    return int(face.sum())


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


SITE_TAG = "propmodel_site"          # custom property on every material add_site creates


def site_material(name):
    """The material add_site builds as ``name``, never one of the house's: a material add_site made before (tagged
    SITE_TAG, e.g. when the site is rebuilt on a site blend) or an untagged one nobody uses is taken over; an untagged
    material of that name WITH users (build_model / add_details made it, e.g. the house walls' 'Concrete') is left alone
    and a new material 'Site ' + name is used instead (deterministic, so presentation scripts can find it). Its node
    tree is reset to a bare Principled BSDF -> Material Output, so a re-used material is rebuilt from scratch and never
    keeps old noise / ramp nodes. The result carries SITE_TAG."""
    def own(m_):
        return m_ is None or bool(m_.get(SITE_TAG)) or m_.users == 0
    m = bpy.data.materials.get(name)
    if not own(m):
        alt = "Site " + name
        m = bpy.data.materials.get(alt)
        if not own(m):
            m = bpy.data.materials.new(alt)          # an unrelated 'Site ...' material with users: Blender adds .001
    if m is None:
        m = bpy.data.materials.new(name if bpy.data.materials.get(name) is None else "Site " + name)
    m[SITE_TAG] = True
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.name = "Principled BSDF"
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat(name, rgb, rough=0.8, metal=0.0):
    """Plain Principled material add_site owns (site_material: a house material of the same name is never taken)."""
    m = site_material(name)
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*rgb, 1)
    return m


def textured(name, rgb_a, rgb_b, scale, bump=0.2, rough=0.9):
    """Two-tone noise material (lawn, gravel, concrete) with a little bump. Built on a fresh node tree (mat ->
    site_material clears the nodes of a re-used site material first)."""
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


def blend_by_attribute(name, ground, rock, attr, edge=0.5, soft=0.18, tone_attrs=None):
    """Terrain material: two-tone noise `ground` (rgb_a, rgb_b, scale) where the point attribute `attr` is
    low, `rock` where it is high, with a noise-broken transition around `edge`. ``tone_attrs`` = (lo, hi): names of
    two point colour attributes that replace the rock tone's two colours per vertex (boulder_tones: the terrain the
    LiDAR raised inside a yard boulder outline takes that boulder's colour range); the rock noise still mixes them."""
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
    rock_col = rp_r.outputs["Color"]
    if tone_attrs:
        # per-vertex rock colours: mix(lo, hi, noise) -- the same linear two-stop ramp, its stops read per vertex
        lo_, hi_ = (nt.nodes.new("ShaderNodeAttribute") for _ in range(2))
        for nd_, nm_ in ((lo_, tone_attrs[0]), (hi_, tone_attrs[1])):
            nd_.attribute_type = "GEOMETRY"; nd_.attribute_name = nm_; nd_.label = "rock tone " + nm_
        mt = nt.nodes.new("ShaderNodeMix"); mt.data_type = "RGBA"; mt.label = "rock tone per vertex"
        nt.links.new(nz_r.outputs["Fac"], mt.inputs["Factor"])
        nt.links.new(lo_.outputs["Color"], mt.inputs[6]); nt.links.new(hi_.outputs["Color"], mt.inputs[7])
        nt.nodes.remove(rp_r)
        rock_col = mt.outputs[2]
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
    nt.links.new(add_cracks(nt, add_bedding(nt, rock_col)), mix.inputs[7])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.4
    nt.links.new(nz_r.outputs["Fac"], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    m.diffuse_color = (*[0.5 * (x + y) for x, y in zip(ground[0], rock[0])], 1)
    return m


def boulder_tones(items, verts, rock, pad=0.1):
    """Per-vertex rock colours of the terrain: vertices within ``pad`` m of a yard "boulder" outline (not a "foliage"
    mass) take that boulder's colour range (_two: its "color", else ``rock``), all others ``rock`` (lo, hi linear RGB).
    The LiDAR rock merge raises the terrain inside a traced boulder to its returns, so where the terrain pokes through
    the dome it shows in the boulder's own colour and the boulder reads as one stone. Returns (lo list, hi list, number
    of vertices inside a boulder) or None when no vertex lies in a boulder (later outlines win where they overlap)."""
    import shapely
    from shapely.geometry import Polygon
    import numpy as _np
    bl = [it for it in items if isinstance(it, dict) and it.get("kind") == "boulder" and it.get("polygon")
          and it.get("surface") != "foliage"]
    if not bl or not len(verts):
        return None
    V = _np.asarray(verts, float)
    lo = _np.tile(_np.asarray(rock[0], float), (len(V), 1)); hi = _np.tile(_np.asarray(rock[1], float), (len(V), 1))
    inside = _np.zeros(len(V), bool)
    for it in bl:
        pg = Polygon(it["polygon"]).buffer(0)
        if pg.is_empty:
            continue
        m = shapely.contains_xy(pg.buffer(pad), V[:, 0], V[:, 1])
        a_, b_ = _two(it, tuple(rock[0]), tuple(rock[1]))
        lo[m] = a_; hi[m] = b_; inside |= m
    if not inside.any():
        return None
    return [tuple(r) for r in lo], [tuple(r) for r in hi], int(inside.sum())


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


BOULDER_RINGS = 8                 # rings from the foot to the top (cos-spaced: dense at the foot)
BOULDER_DOME = (2.5, 2.0)         # height fraction h = (1 - rho^a)^(1/b) at radius fraction rho: steep foot, the top
                                  # ~25 % of the radius within 2 % of top_z (a broad rounded dome, no peaked crest)


def dome_rings(rings=BOULDER_RINGS, dome=BOULDER_DOME):
    """(inset fraction towards the centre, height fraction) of each ring of a boulder, foot first; the centre vertex
    (1, 1) closes the top."""
    a, b = dome
    out = []
    for k in range(int(rings)):
        rho = math.cos(k / rings * math.pi / 2)
        out.append((1.0 - rho, max(0.0, 1.0 - rho ** a) ** (1.0 / b)))
    return out


def subdivide_ring(ring, times=1):
    """Double the vertex count of a closed outline `times` times with the 4-point interpolating scheme: every measured
    vertex stays where it is, the new midpoints round the corners between them (no polygonal facets)."""
    P = [tuple(p) for p in ring]
    for _ in range(int(times)):
        n = len(P)
        if n < 4:
            P = [q for k in range(n) for q in (P[k], tuple((P[k][j] + P[(k + 1) % n][j]) / 2 for j in range(2)))]
            continue
        Q = []
        for k in range(n):
            p0, p1, p2, p3 = P[k - 1], P[k], P[(k + 1) % n], P[(k + 2) % n]
            Q += [p1, tuple(9 / 16 * (p1[j] + p2[j]) - 1 / 16 * (p0[j] + p3[j]) for j in range(2))]
        P = Q
    return P


def no_overhang(ring, prev):
    """Ring of a dome (plan points) kept inside the ring below it: a vertex that the inset towards the centroid moves
    outside the lower ring (at a concave corner of the outline) is pulled back onto the lower ring's boundary, so no
    side face of the dome leans out over its foot (no undercut notch; its normal never points down)."""
    from shapely.geometry import Polygon, Point
    from shapely.ops import nearest_points
    lower = Polygon(prev)
    if not lower.is_valid:
        lower = lower.buffer(0)
    if lower.is_empty:
        return ring
    out = []
    for x, y in ring:
        p = Point(x, y)
        if lower.covers(p):
            out.append((x, y))
        else:
            q = nearest_points(lower, p)[0]
            out.append((q.x, q.y))
    return out


def split_quad(verts, q):
    """Two triangles of the quad q (vertex indices into verts, counter-clockwise), split along the diagonal whose two
    vertices differ less in height (the terrain rule of build_site.py split_diagonals), ties along the shorter diagonal:
    a twisted quad split the other way renders as a dark folded shard (Blender would split every quad along 0-2)."""
    a, b, c_, d = q
    P = [verts[j] for j in q]
    dz02, dz13 = abs(P[0][2] - P[2][2]), abs(P[1][2] - P[3][2])
    if abs(dz02 - dz13) < 1e-6:
        l02 = sum((P[0][j] - P[2][j]) ** 2 for j in range(3)); l13 = sum((P[1][j] - P[3][j]) ** 2 for j in range(3))
        use13 = l13 < l02 - 1e-12
    else:
        use13 = dz13 < dz02
    return [[a, b, d], [b, c_, d]] if use13 else [[a, b, c_], [a, c_, d]]


def grid_z(grid, x, y):
    """Bilinear height of a site-scene terrain grid (build_site.py "grid": x0, y0, nx, ny, cell, z row-major by y) at
    (x, y); None outside the grid or next to a missing node."""
    if not grid:
        return None
    nx, ny, c = int(grid["nx"]), int(grid["ny"]), float(grid["cell"])
    fi, fj = (x - grid["x0"]) / c, (y - grid["y0"]) / c
    if fi < -1e-9 or fj < -1e-9 or fi > nx - 1 + 1e-9 or fj > ny - 1 + 1e-9:
        return None
    i, j = min(max(int(math.floor(fi)), 0), nx - 2), min(max(int(math.floor(fj)), 0), ny - 2)
    tx, ty = fi - i, fj - j
    z = grid["z"]
    q = [z[j * nx + i], z[j * nx + i + 1], z[(j + 1) * nx + i], z[(j + 1) * nx + i + 1]]
    if any(v is None or v != v for v in q):
        return None
    return (q[0] * (1 - tx) * (1 - ty) + q[1] * tx * (1 - ty) + q[2] * (1 - tx) * ty + q[3] * tx * ty)


def clamp_over_terrain(verts, zfun, max_over, local=None):
    """Vertices (x, y, z) with z = min(z, zfun(x, y) + max_over) wherever zfun gives a height (None = no terrain: kept).
    ``local``: [{"xy": [x, y], "radius": r, "max": m}, ...]: vertices within r (plan) of xy use m instead (the largest of
    the entries that reach them), e.g. where the terrain grid at an outline edge sits under the measured flank.
    Only heights change, so no face of a dome built on a consistent plan winding turns over. Returns (verts, n clamped)."""
    out, n = [], 0
    for x, y, z in verts:
        t = zfun(x, y)
        loc = [float(e["max"]) for e in (local or [])
               if math.hypot(x - e["xy"][0], y - e["xy"][1]) <= float(e.get("radius", 0.0))]
        mo = max(loc) if loc else max_over
        if t is not None and z > t + mo:
            z = t + mo
            n += 1
        out.append((x, y, z))
    return out, n


def k_boulder(it, G, c, M, i):
    """Rock: the outline at grade (+ 4-point midpoints: 2x the segments, measured vertices kept), rising in
    `rings` cos-spaced rings with a dome profile (`dome` [a, b]: h = (1 - rho^a)^(1/b)) to a broad rounded top at
    top_z (the LiDAR height), closed by a centre vertex and smooth-shaded.
    "max_over_terrain" (m): every dome vertex is clamped to min(dome z, terrain z at its xy + that), the terrain from the
    site-scene grid (bilinear; the terrain mesh where there is no grid), so an assumed dome profile never stands far
    over the measured surface on a flank the LiDAR terrain already follows (the terrain faces inside the outline that
    then show through keep the boulder's colour: boulder_tones)."""
    from shapely.geometry import Polygon
    P = Polygon(it["polygon"]).buffer(0)
    if P.is_empty:
        return
    if not P.exterior.is_ccw:
        P = Polygon(list(P.exterior.coords)[::-1])
    cx, cy = P.centroid.x, P.centroid.y
    if not P.buffer(-0.05 * math.sqrt(P.area)).contains(P.centroid):
        from shapely.ops import polylabel           # concave outline: dome towards its pole of inaccessibility
        pl = polylabel(P, tolerance=0.01)
        cx, cy = pl.x, pl.y
    ring0 = list(P.exterior.coords)[:-1]
    zg = min(G.z(x, y, 0) for x, y in ring0) - 0.15
    ring0 = subdivide_ring(ring0, it.get("subdivide", 1))
    top = it.get("top_z", zg + it.get("height", 1.0))
    if it.get("foot") == "terrain":
        # the dome rises from the terrain under each outline point (a boulder on a slope stands taller on its downhill
        # side), instead of every ring starting at the outline's lowest grade: on a slope that profile meets the upper
        # ground as a near-vertical sheet along the outline
        zb = [min(G.z(x, y, zg + 0.15) - 0.15, top - 0.05) for x, y in ring0]
    else:
        zb = [zg] * len(ring0)
    fr = dome_rings(it.get("rings", BOULDER_RINGS), tuple(it.get("dome", BOULDER_DOME)))
    verts, faces, n = [], [], len(ring0)
    prev = None
    for f, hz in fr:
        ring = [(x + (cx - x) * f, y + (cy - y) * f) for x, y in ring0]
        if prev is not None:
            ring = no_overhang(ring, prev)
        for k, (x, y) in enumerate(ring):
            verts.append((x, y, zb[k] + (top - zb[k]) * hz))
        prev = ring
    # a side quad whose normal still points down (inset rings of a strongly concave outline cross) is made vertical:
    # its upper vertices move straight above the lower ones (repeated up the rings)
    for r in range(len(fr) - 1):
        for _ in range(3):
            bad = False
            for k in range(n):
                a, b = r * n + k, r * n + (k + 1) % n
                q = [verts[a], verts[b], verts[b + n], verts[a + n]]
                nz = sum((q[j][0] - q[(j + 1) % 4][0]) * (q[j][1] + q[(j + 1) % 4][1]) for j in range(4))
                if nz < -1e-9:
                    for lo_, up_ in ((a, a + n), (b, b + n)):
                        verts[up_] = (verts[lo_][0], verts[lo_][1], verts[up_][2])
                    bad = True
            if not bad:
                break
    for r in range(len(fr) - 1):
        for k in range(n):
            a, b = r * n + k, r * n + (k + 1) % n
            faces += split_quad(verts, [a, b, b + n, a + n])
    ctr = len(verts)
    verts.append((cx, cy, top))
    r0 = (len(fr) - 1) * n
    fan = [[r0 + k, r0 + (k + 1) % n, ctr] for k in range(n)]

    def _up(t):
        (x0, y0, _), (x1, y1, _), (x2, y2, _) = (verts[j] for j in t)
        return (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0) > -1e-12
    if all(_up(t) for t in fan):
        faces += fan
    else:
        # the top ring of a strongly concave outline does not see the centre: close it with its own (constrained
        # Delaunay) triangulation at top_z instead of a fan, so no top triangle faces down
        import shapely
        from shapely.geometry import Polygon as _SP
        key = {(round(verts[r0 + k][0], 6), round(verts[r0 + k][1], 6)): r0 + k for k in range(n)}
        tris = []
        tp = _SP([verts[r0 + k][:2] for k in range(n)])
        if tp.is_valid:
            for t in shapely.constrained_delaunay_triangles(tp).geoms:
                ids = [key.get((round(x, 6), round(y, 6))) for x, y in list(t.exterior.coords)[:3]]
                if None in ids:
                    tris = None
                    break
                tris.append(ids if _up(ids) else ids[::-1])
        if tris:
            for k in range(n):
                verts[r0 + k] = (verts[r0 + k][0], verts[r0 + k][1], top)
            faces += tris
        else:
            faces += [t for t in fan if _up(t)]
    if it.get("max_over_terrain") is not None:
        grid = (M or {}).get("_grid")

        def _tz(x, y):
            z_ = grid_z(grid, x, y) if grid else None
            return G.z(x, y) if z_ is None else z_
        verts, ncl = clamp_over_terrain(verts, _tz, float(it["max_over_terrain"]), it.get("max_over_terrain_local"))
        print(f"boulder {it.get('name', i)!s:.40}: {ncl} of {len(verts)} dome vertices clamped to the terrain + "
              f"{float(it['max_over_terrain']):.2f} m" + (f" ({len(it['max_over_terrain_local'])} local overrides)"
                                                          if it.get("max_over_terrain_local") else ""))
    dflt = (M or {}).get("_tones", {}).get("rock", (ROCK_A, ROCK_B))[:2]
    if it.get("surface") == "foliage":
        # a mass the LiDAR cannot tell from rock (dense juniper): leafy two-tone noise, no joints or bedding
        rock = textured(f"Foliage mass {i}", *_two(it, (0.035, 0.045, 0.022), (0.075, 0.085, 0.04)), 9.0, 1.0, rough=0.95)
    else:
        rock = stone(f"Rock {i}", *_two(it, *dflt), 3.0, 0.6)
    ob = mesh(it.get("name", f"boulder {i}"), verts, faces, c, rock)
    ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    ob.data.update()
    return ob


def _srgb(v):
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


# shadow: 5 cm under the joint above (the round-5..9 Voronoi mask shaded within 2 cm of whichever joint was nearer, above the
# course's random feature point, i.e. part of many courses' feet too; 5 cm under the top joint alone gives the same face tone)
DRYSTACK = {"course": (0.04, 0.12), "stone": (0.15, 0.6), "joint": 0.012, "joint_color": (0.08, 0.072, 0.062),
            "weathered": 0.85, "bump": 0.015, "shadow": 0.05, "shadow_dark": 0.6, "step": 0.015, "tilt": 0.08,
            "ragged": 0.004,
            "course_shape": 0.55, "course_cov": 0.32, "period": 4.096, "stone_random": 0.6, "stone_course": 0.15,
            "lift": 0.12, "lift_k": 1.2}
DRYSTACK_TEX_RES = 0.001          # m per pixel of the course texture (1-D, along z)
DRYSTACK_TEX_RANGE = 0.25         # m: distances to the bed joints are stored as value x this (8 bit: 1 mm steps)


def drystack_courses(seed, course=(0.04, 0.12), shape=0.55, period=4.096, window=1.0, min_cov=0.32, min_n=7, tries=2000,
                     mean_tol=0.05):
    """Course heights (m, bottom to top) of a dry-stack tile ``period`` m tall that repeats up the wall: each drawn
    independently from lo + (hi - lo) Beta(shape, shape) (``course`` = (lo, hi); shape < 1 is U-shaped: thin and thick
    courses side by side, as hand-laid ledgestone, coefficient of variation ~0.34 for 0.55), then all scaled to close
    the period exactly. The first seed from ``seed`` on whose every ``window`` m stretch (starting at any course joint,
    wrapping round the period) holds >= ``min_n`` whole courses with a height CoV >= ``min_cov`` and whose mean course is
    within ``mean_tol`` of 0.5 (lo + hi) (the joint share of the face, i.e. its tone, stays that of the nominal mean)
    is used. Returns (heights, the seed used)."""
    lo, hi = float(course[0]), float(course[1])
    best = None
    for k in range(tries):
        rnd = random.Random(seed + 7919 * k)
        hs = []
        while sum(hs) < period:
            hs.append(lo + (hi - lo) * rnd.betavariate(shape, shape))
        if sum(hs) - period > 0.5 * hs[-1]:
            hs.pop()                                   # closer to the period without the last course
        f = period / sum(hs)
        hs = [h * f for h in hs]
        worst = 9.0
        n = len(hs)
        for i in range(n):
            acc, win = 0.0, []
            for j in range(n):
                h = hs[(i + j) % n]
                if acc + h > window + 1e-9:
                    break
                acc += h
                win.append(h)
            m_ = sum(win) / max(len(win), 1)
            cov = (sum((h - m_) ** 2 for h in win) / max(len(win) - 1, 1)) ** 0.5 / m_ if len(win) >= 2 else 0.0
            worst = min(worst, cov if len(win) >= min_n else 0.0)
        mean_ok = abs(period / len(hs) / (0.5 * (lo + hi)) - 1.0) <= mean_tol
        if worst >= min_cov and mean_ok:
            return hs, seed + 7919 * k
        worst = worst if mean_ok else worst - 1.0
        if best is None or worst > best[0]:
            best = (worst, hs, seed + 7919 * k)
    return best[1], best[2]


def drystack_course_pixels(heights, res=0.001, rng_range=0.25, seed=0):
    """RGBA rows of the 1-D course texture of drystack_courses() heights: per pixel (res m, bottom up) R = distance to
    the course's top joint, G = distance to its bottom joint (both / rng_range, clamped to 1), B = the course's random
    value (0..1), A = 1. Returns (width, flat list of floats)."""
    rnd = random.Random(seed * 31 + 5)
    vals = [rnd.random() for _ in heights]
    period = sum(heights)
    w = max(1, int(round(period / res)))
    out = []
    k, z0 = 0, 0.0
    for p in range(w):
        z = (p + 0.5) * period / w
        while k < len(heights) - 1 and z >= z0 + heights[k]:
            z0 += heights[k]; k += 1
        top, bot = z0 + heights[k] - z, z - z0
        out += [min(1.0, max(0.0, top / rng_range)), min(1.0, max(0.0, bot / rng_range)), vals[k], 1.0]
    return w, out


def drystack(name, rgb_a, rgb_b, course=None, stone=None, joint=None, joint_color=None, weathered=None, bump=None,
             shadow=None, shadow_dark=None, step=None, seed=None, lift=None, lift_k=None, course_shape=None,
             course_cov=None, period=None, stone_random=None, stone_course=None, tilt=None, ragged=None, **_old):
    """Dry-stacked thin flat stone (sandstone ledgestone), in wall coordinates (object x along the wall, z up;
    k_retaining_wall builds each segment in such a frame):

    * courses of independent random height between ``course`` = (lo, hi) m (default 4-12 cm), drawn U-shaped
      (Beta(``course_shape``, same), thin and thick courses side by side; every 1 m of wall holds >= 7 courses with a
      height coefficient of variation >= ``course_cov``: drystack_courses) and stored in a 1-D course texture along z
      (1 mm pixels, repeating every ``period`` m: distances to the course's top and bottom joints and a random value
      per course; the heights are kept in m["drystack_courses"]);
    * stones of random length along each course: a 1-D Voronoi along x (mean 0.5 (lo + hi) of ``stone`` = (lo, hi) m,
      default 0.15-0.6 m; randomness ``stone_random`` gives 1 -+ that x the mean), its mean stretched by up to
      +-``stone_course`` per course and its phase shifted by a random number per course, so head joints are staggered
      at random (no regular bond);
    * per-stone colour drawn between the two tones ``rgb_a`` .. ``rgb_b`` (the yard item's colour range, linear; buff
      sandstone by default), one stone in eight a little darker (``weathered`` x rgb_a), with a faint grain; a random
      ``lift`` share of the stones (by stone id; default 12 %) ``lift_k`` x brighter (default 1.2, clamped at 1.0
      linear): the sunlit pale stones of a ledgestone face;
    * joints ``joint`` m wide in ``joint_color`` (dark brown-grey, linear ~0.08), recessed by ``bump`` m (1-2 cm);
    * a light shadow band ``shadow`` m deep under every bed joint (x ``shadow_dark`` of the sRGB value; default 5 cm);
    * each stone up to +-``step`` / 2 m higher or lower than its neighbours, so bed joints step at the head joints, and
      its bed joints tilted by up to +-``tilt`` / 2 (m per m) about its middle (tapered flagstones, not parallel bricks);
      a fine noise of +-``ragged`` m roughens every joint edge;
    * TOP faces (normal z > 0.5: the tier's cap) are plain stone colour: no joint or shadow lines, so a tier seen from
      above reads as a light cap line, as the orthos show it.
    Joint edges are noise-distorted by a centimetre or two, so the courses wander like hand-laid stone. Node labels
    "joint" (map ranges fed by a node labelled "courses..." = bed-joint distance / mean course, or "stones..." = head-joint
    distance / mean stone), "overhang shadow", "joint dark" and "stone jitter" are the presentation hooks (widths,
    joint colour, tone range) that a presentation script may retune. Old keyword arguments (joint_dark, jitter) are
    accepted and ignored."""
    P = dict(DRYSTACK)
    for k, v in (("course", course), ("stone", stone), ("joint", joint), ("joint_color", joint_color),
                 ("weathered", weathered), ("bump", bump), ("shadow", shadow), ("shadow_dark", shadow_dark), ("step", step),
                 ("lift", lift), ("lift_k", lift_k), ("course_shape", course_shape), ("course_cov", course_cov),
                 ("period", period), ("stone_random", stone_random), ("stone_course", stone_course), ("tilt", tilt),
                 ("ragged", ragged)):
        if v is not None:
            P[k] = v
    seed = int(seed) if seed is not None else sum(ord(ch) for ch in name)
    mean = [0.5 * (a + b) for a, b in zip(rgb_a, rgb_b)]
    darkest = tuple(P["weathered"] * v for v in rgb_a)
    m = mat(name, tuple(mean), 0.9)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    N = nt.nodes.new
    c_mean = 0.5 * (P["course"][0] + P["course"][1]); s_mean = 0.5 * (P["stone"][0] + P["stone"][1])
    # course texture (1-D, along z)
    heights, used = drystack_courses(seed, P["course"], P["course_shape"], P["period"], min_cov=P["course_cov"])
    w, px = drystack_course_pixels(heights, DRYSTACK_TEX_RES, DRYSTACK_TEX_RANGE, seed=used)
    period = sum(heights)
    iname = f"{name} courses"
    img = bpy.data.images.get(iname)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(iname, width=w, height=1, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(px)
    img.pack()
    tc = N("ShaderNodeTexCoord")
    # wander: a centimetre-scale distortion of the coordinates
    wz = N("ShaderNodeTexNoise"); wz.inputs["Scale"].default_value = 4.0; wz.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Object"], wz.inputs["Vector"])
    dv = N("ShaderNodeVectorMath"); dv.operation = "MULTIPLY_ADD"; dv.inputs[1].default_value = (0.03, 0.03, 0.008)
    nt.links.new(wz.outputs["Color"], dv.inputs[0]); nt.links.new(tc.outputs["Object"], dv.inputs[2])
    sep = N("ShaderNodeSeparateXYZ"); nt.links.new(dv.outputs[0], sep.inputs[0])
    # ragged joint edges: a fine noise on z only
    rg = N("ShaderNodeTexNoise"); rg.inputs["Scale"].default_value = 25.0; rg.inputs["Detail"].default_value = 2.0
    rg.label = "ragged joints"
    nt.links.new(tc.outputs["Object"], rg.inputs["Vector"])

    def course_tex(z_socket, label):
        u = N("ShaderNodeMath"); u.operation = "DIVIDE"; u.inputs[1].default_value = period
        nt.links.new(z_socket, u.inputs[0])
        cv = N("ShaderNodeCombineXYZ"); cv.inputs["Y"].default_value = 0.5
        nt.links.new(u.outputs[0], cv.inputs["X"])
        t = N("ShaderNodeTexImage"); t.image = img; t.interpolation = "Closest"; t.extension = "REPEAT"; t.label = label
        nt.links.new(cv.outputs[0], t.inputs["Vector"])
        sc = N("ShaderNodeSeparateColor"); nt.links.new(t.outputs["Color"], sc.inputs[0])
        return sc

    def math(op, a_, b_=None, label="", v=None):
        n_ = N("ShaderNodeMath"); n_.operation = op; n_.label = label
        for k_, x_ in enumerate((a_, b_)):
            if x_ is None:
                continue
            if isinstance(x_, (int, float)):
                n_.inputs[k_].default_value = x_
            else:
                nt.links.new(x_, n_.inputs[k_])
        return n_
    c1 = course_tex(sep.outputs["Z"], "courses (stone ids)")              # course random value: c1 Blue
    # stones along x: mean stretched per course (1 +- stone_course), phase shifted per course
    r2 = math("FRACT", math("MULTIPLY", c1.outputs[2], 7.31).outputs[0])
    stretch = math("MULTIPLY_ADD", r2.outputs[0], 2.0 * P["stone_course"], label="stone stretch per course")
    stretch.inputs[2].default_value = 1.0 - P["stone_course"]
    wx = math("DIVIDE", sep.outputs["X"], stretch.outputs[0])
    sh = math("MULTIPLY_ADD", c1.outputs[2], 37.0); nt.links.new(wx.outputs[0], sh.inputs[2])

    def vor1(w_socket, mean_len, feature, label):
        v = N("ShaderNodeTexVoronoi"); v.voronoi_dimensions = "1D"; v.feature = feature; v.label = label
        v.inputs["Scale"].default_value = 1.0 / mean_len; v.inputs["Randomness"].default_value = P["stone_random"]
        nt.links.new(w_socket, v.inputs["W"])
        return v
    sid = vor1(sh.outputs[0], s_mean, "F1", "stones")                     # random colour per stone
    sedge = vor1(sh.outputs[0], s_mean, "DISTANCE_TO_EDGE", "stones")     # head joints
    sdist = math("MULTIPLY", sedge.outputs["Distance"], stretch.outputs[0], label="stones: head-joint distance / mean")
    rs = N("ShaderNodeSeparateColor"); nt.links.new(sid.outputs["Color"], rs.inputs[0])
    zo = math("MULTIPLY_ADD", rs.outputs[2], P["step"]); zo.inputs[2].default_value = -0.5 * P["step"]
    # tilt about the stone's middle: (W - feature W) x slope, slope from another random value of the stone
    rt = math("FRACT", math("MULTIPLY", rs.outputs[0], 13.7).outputs[0])
    slope = math("MULTIPLY_ADD", rt.outputs[0], P["tilt"], label="stone tilt"); slope.inputs[2].default_value = -0.5 * P["tilt"]
    dxw = math("SUBTRACT", sh.outputs[0], sid.outputs["W"])
    tz = math("MULTIPLY", dxw.outputs[0], slope.outputs[0])
    rz = math("MULTIPLY_ADD", rg.outputs["Fac"], 2.0 * P["ragged"]); rz.inputs[2].default_value = -P["ragged"]
    zo2 = math("ADD", zo.outputs[0], tz.outputs[0])
    zo3 = math("ADD", zo2.outputs[0], rz.outputs[0])
    zs = math("ADD", sep.outputs["Z"], zo3.outputs[0])
    c2 = course_tex(zs.outputs[0], "courses (stepped joints)")
    bed = math("MINIMUM", c2.outputs[0], c2.outputs[1])
    bdist = math("MULTIPLY", bed.outputs[0], DRYSTACK_TEX_RANGE / c_mean, label="courses: bed-joint distance / mean")
    topd = math("MULTIPLY", c2.outputs[0], DRYSTACK_TEX_RANGE / c_mean, label="courses: depth under the joint above / mean")

    def jmask(dist_socket, scale_):
        mr = N("ShaderNodeMapRange"); mr.clamp = True; mr.label = "joint"
        mr.inputs["From Min"].default_value = 0.5 * P["joint"] * scale_
        mr.inputs["From Max"].default_value = 0.9 * P["joint"] * scale_
        mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
        nt.links.new(dist_socket, mr.inputs["Value"])
        return mr
    jc, js = jmask(bdist.outputs[0], 1.0 / c_mean), jmask(sdist.outputs[0], 1.0 / s_mean)
    jm0 = math("MAXIMUM", jc.outputs["Result"], js.outputs["Result"])
    # no joints on the top faces (the cap of the tier): world normal z > 0.5
    geo = N("ShaderNodeNewGeometry"); gsep = N("ShaderNodeSeparateXYZ"); nt.links.new(geo.outputs["Normal"], gsep.inputs[0])
    side = math("LESS_THAN", gsep.outputs["Z"], 0.5, label="side faces")
    jm = math("MULTIPLY", jm0.outputs[0], side.outputs[0], label="joints")
    # stone colour: rgb_a .. rgb_b by the stone's random value (one in eight weathered darker), faint grain
    ramp = N("ShaderNodeValToRGB"); ramp.label = "stone jitter"
    ramp.color_ramp.elements[0].color = (*darkest, 1); ramp.color_ramp.elements[1].color = (*rgb_b, 1)
    e = ramp.color_ramp.elements.new(0.12); e.color = (*rgb_a, 1)
    nt.links.new(rs.outputs[0], ramp.inputs["Fac"])
    gr = N("ShaderNodeTexNoise"); gr.inputs["Scale"].default_value = 40.0; gr.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], gr.inputs["Vector"])
    grm = N("ShaderNodeMapRange"); grm.inputs["To Min"].default_value = 0.94; grm.inputs["To Max"].default_value = 1.06
    nt.links.new(gr.outputs["Fac"], grm.inputs["Value"])
    grain = N("ShaderNodeMix"); grain.data_type = "RGBA"; grain.blend_type = "MULTIPLY"; grain.inputs["Factor"].default_value = 1.0
    gv = N("ShaderNodeCombineXYZ")
    for k in ("X", "Y", "Z"):
        nt.links.new(grm.outputs["Result"], gv.inputs[k])
    nt.links.new(ramp.outputs["Color"], grain.inputs[6]); nt.links.new(gv.outputs[0], grain.inputs[7])
    # lifted stones: a random `lift` share of the stones (their green random value) `lift_k` x brighter, clamped at 1
    lsel = math("GREATER_THAN", rs.outputs[1], 1.0 - P["lift"], label="lifted stones")
    lift_ = N("ShaderNodeMix"); lift_.data_type = "RGBA"; lift_.blend_type = "MULTIPLY"; lift_.label = "lifted stones"
    lift_.clamp_result = True
    lift_.inputs[7].default_value = (P["lift_k"], P["lift_k"], P["lift_k"], 1)
    nt.links.new(lsel.outputs[0], lift_.inputs["Factor"]); nt.links.new(grain.outputs[2], lift_.inputs[6])
    # joints: a dark brown-grey mortar-less gap colour
    dark = N("ShaderNodeMix"); dark.data_type = "RGBA"; dark.blend_type = "MIX"; dark.label = "joint dark"
    dark.inputs[7].default_value = (*P["joint_color"], 1)
    nt.links.new(jm.outputs[0], dark.inputs["Factor"]); nt.links.new(lift_.outputs[2], dark.inputs[6])
    # overhang shadow: within `shadow` under the bed joint above (side faces only)
    shd = N("ShaderNodeMapRange"); shd.clamp = True; shd.label = "overhang shadow"
    shd.inputs["From Min"].default_value = 0.5 * P["joint"] / c_mean
    shd.inputs["From Max"].default_value = (0.5 * P["joint"] + P["shadow"]) / c_mean
    shd.inputs["To Min"].default_value = 1.0; shd.inputs["To Max"].default_value = 0.0
    nt.links.new(topd.outputs[0], shd.inputs["Value"])
    sh3 = math("MULTIPLY", shd.outputs["Result"], side.outputs[0])
    sdk = P["shadow_dark"] ** 2.2
    shade = N("ShaderNodeMix"); shade.data_type = "RGBA"; shade.blend_type = "MULTIPLY"; shade.label = "overhang shadow"
    shade.inputs[7].default_value = (sdk, sdk, sdk, 1)
    nt.links.new(sh3.outputs[0], shade.inputs["Factor"]); nt.links.new(dark.outputs[2], shade.inputs[6])
    nt.links.new(shade.outputs[2], b.inputs["Base Color"])
    # relief: each stone proud by half to all of `bump` (its random value), joints recessed by `bump`, a little grain
    h = math("MULTIPLY_ADD", rs.outputs[2], 0.5); h.inputs[2].default_value = 0.5
    inv = math("SUBTRACT", 1.0, jm.outputs[0])
    hh = math("MULTIPLY", h.outputs[0], inv.outputs[0])
    hg = math("MULTIPLY_ADD", gr.outputs["Fac"], 0.1); nt.links.new(hh.outputs[0], hg.inputs[2])
    bp = N("ShaderNodeBump"); bp.label = "stone relief"
    bp.inputs["Strength"].default_value = 1.0; bp.inputs["Distance"].default_value = P["bump"]
    nt.links.new(hg.outputs[0], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    m.diffuse_color = (*mean, 1)
    m["drystack"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in P.items()}
    m["drystack_courses"] = [round(v, 5) for v in heights]
    return m


def _wall_material(it, i, M=None):
    kind = it.get("material", "stone")
    if kind == "rock":
        # a natural rock face carried as a breakline (a boulder or ledge edge the terrain steps at): the boulder / outcrop
        # sandstone (joints and bedding), in the item's colour or the scene's rock tone
        dflt = (M or {}).get("_tones", {}).get("rock", (ROCK_A, ROCK_B))[:2]
        return stone(f"Retaining wall (rock face) {i}", *_two(it, *dflt), 3.0, 0.6)
    if kind == "drystack":
        return drystack(f"Dry-stack stone {i}", *_two(it, (0.45, 0.40, 0.32), (0.75, 0.68, 0.56)), **it.get("drystack", {}))
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


def wall_centre_line(it, G):
    """Centre line (Vectors) of a retaining_wall item: its line, or, with "line_is": "face", the line moved half a
    thickness to the uphill side ("uphill": left / right of the line direction, else the higher terrain)."""
    line = [Vector((p[0], p[1], 0)) for p in it["line"]]
    th = it.get("thickness", 0.3)
    if len(line) >= 2 and it.get("line_is", "centre") == "face":
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
    return line


def wall_solids(items, G):
    """Plan footprint (shapely) and highest top of every retaining_wall item: [(polygon, top or None, name)]."""
    from shapely.geometry import LineString
    out = []
    for it in items:
        if it.get("kind") != "retaining_wall" or len(it.get("line", [])) < 2:
            continue
        line = wall_centre_line(it, G)
        th = it.get("thickness", 0.3)
        tops = it.get("top_z")
        top = max(tops) if isinstance(tops, (list, tuple)) else tops
        out.append((LineString([(p.x, p.y) for p in line]).buffer(th / 2, cap_style="flat", join_style="mitre"),
                    top, it.get("name", "retaining wall")))
    return out


def plaque_blocked(face_xy, nrm_xy, z, walls, reach=1.5):
    """Why a plaque on a face centred at face_xy (outward normal nrm_xy, plaque centre height z) cannot be seen: the
    face lies inside a retaining wall's solid, or a wall standing higher than the plaque is in front of it within
    `reach` m. Returns a list of (reason, wall name); empty when the face is clear."""
    from shapely.geometry import Point, LineString
    fx, fy = face_xy; nx_, ny_ = nrm_xy
    p_in = Point(fx + 0.02 * nx_, fy + 0.02 * ny_)
    ray = LineString([(fx + 0.02 * nx_, fy + 0.02 * ny_), (fx + reach * nx_, fy + reach * ny_)])
    out = []
    for poly, top, name in walls:
        if poly.contains(p_in):
            out.append(("inside", name))
        elif ray.intersects(poly) and (top is None or top > z):
            out.append(("behind", name))
    return out


def k_retaining_wall(it, G, c, M, i):
    """Wall along a polyline: mitred joints (no overlapping boxes), one level top per segment when
    top_z is a list (a stepped wall), foot 0.3 m under the lower of the two grades beside it."""
    th = it.get("thickness", 0.3)
    m_ = _wall_material(it, i, M)
    cap = None
    if it.get("cap_color"):
        # sunlit / weathered-light cap on a darker face (photo: dark poured faces, pale caps)
        cap = textured(f"Retaining wall cap {i}", *_two({"color": it["cap_color"]}, None, None), 3.0, 0.08)
    tops = it.get("top_z")
    line = wall_centre_line(it, G)
    nseg = len(line) - 1
    if nseg < 1:
        return
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
        if cap is not None:
            ob.data.materials.append(cap)
            ob.data.polygons[1].material_index = 1          # the top face
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
        right = Vector((-nrm.y, nrm.x, 0))               # the viewer's right, facing the plaque face
        ob.location = Vector((x, y, zc)) + nrm * (half + 0.01) + right * float(pl.get("offset", 0.0))
        # text lies in its local XY plane: stand it up and turn it to face along nrm
        ob.rotation_euler = (math.radians(90), 0, math.atan2(nrm.y, nrm.x) + math.radians(90))
        ob.scale.x = float(pl.get("scale_x", 1.0))      # narrower numerals than the default font (photo width / height)
        ob.data.materials.append(mat(f"Pier numerals {i}", tuple(pl.get("color", (0.75, 0.22, 0.06))), 0.5))
        fc = Vector((x, y, 0)) + nrm * half
        for why, wall in plaque_blocked((fc.x, fc.y), (nrm.x, nrm.y), zc, (M or {}).get("_walls", [])):
            print(f"WARNING: {it.get('name', f'pier {i}')}: plaque face ({fc.x:.2f}, {fc.y:.2f}) lies {why} "
                  f"retaining wall '{wall[:60]}' -- the numerals are hidden; move the pier proud of the wall")


def k_steps(it, G, c, M, i):
    """Landscape steps from line[0] (z0) up to line[1] (z1): `risers` treads, each a block from the grade
    under it (or a little below its own nose) to its tread height. "tread": {"slab": 0.05, "gap": 0.06,
    "fill": [[r,g,b],[r,g,b]]} makes each tread a slab of the step colour, `gap` m shorter than the run, on a block
    of the fill (default: the rock-bed material), so the fill shows as a strip between the treads (pale treads on a
    red rock bed, as an ortho shows them)."""
    (ax_, ay_), (bx_, by_) = it["line"][:2]
    n = int(it.get("risers", 6)); w = it.get("width", 1.2)
    z0, z1 = it["z0"], it["z1"]
    L = math.hypot(bx_ - ax_, by_ - ay_)
    rot = math.degrees(math.atan2(by_ - ay_, bx_ - ax_))
    m_ = textured(f"Steps {i}", *_two(it, (0.42, 0.30, 0.22), (0.52, 0.40, 0.30)), 6.0, 0.3)
    tr = it.get("tread")
    if tr:
        slab, gap = float(tr.get("slab", 0.05)), float(tr.get("gap", 0.06))
        fill = (textured(f"Steps fill {i}", *_two({"color": tr["fill"]}, None, None), 10.0, 0.6) if tr.get("fill")
                else (M or {}).get("rock_bed") or m_)
    ux, uy = (bx_ - ax_) / max(L, 1e-9), (by_ - ay_) / max(L, 1e-9)
    clear = float(it.get("clearance", 0.03))
    last = -1e9
    for k in range(n):
        s0, s1 = k / n, (k + 1) / n
        cx, cy = ax_ + (bx_ - ax_) * (s0 + s1) / 2, ay_ + (by_ - ay_) * (s0 + s1) / 2
        top = z0 + (z1 - z0) * (k + 1) / n
        if clear >= 0:
            # never buried: the tread stands at least `clearance` above the terrain under the middle of its run (at 0 and
            # +-w/4 across: a stair whose slope steepens near the top otherwise sinks into the ground along the straight
            # z0-z1 line; on a cross slope the outer edge of the uphill side may stay cut into the bank); treads never step
            # down. Only the middle of the run is sampled: LiDAR ground over a stair is a smooth ramp through the tread
            # middles, which stands half a riser above the tread at its back (build_site.py --step-caps lowers it there)
            pts_ = [(cx - sb * uy * w, cy + sb * ux * w) for sb in (-0.25, 0.0, 0.25)]
            top = max(top, max(G.z(px_, py_, top) for px_, py_ in pts_) + clear, last)
        last = top
        base = min(G.z(cx, cy, top), top - 0.15) - 0.1
        nm = f"{it.get('name', 'steps')} {i} tread {k}"
        if not tr:
            obox(nm, (cx, cy), (L / n + 0.03, w), base, top, rot, c, m_)
            continue
        obox(nm + " fill", (cx, cy), (L / n + 0.03, w), base, top - slab, rot, c, fill)
        obox(nm, (cx, cy), (max(L / n - gap, 0.05), w - 0.02), top - slab, top, rot, c, m_)


def rock_stone(rnd, x, y, r, zg, noise=0.25, yscale=(0.6, 0.9), zscale=(0.35, 0.5), sink=0.3, subdiv=2):
    """One angular landscape stone: an icosphere (``subdiv``) of radius ``r`` whose vertices are pushed in or out by a
    smooth random field of +-``noise`` x r (a few low-order lumps, so faces stay planar-ish and edges angular), scaled
    1 x U(yscale) x U(zscale) (flat, bedded), turned to a random yaw and sunk ``sink`` of its height below ``zg``.
    Returns (verts, faces) in world coordinates."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=int(subdiv), radius=1.0)
    lumps = [(Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))).normalized(), rnd.uniform(-1, 1),
              rnd.uniform(1.5, 3.5)) for _ in range(6)]
    sy, sz = rnd.uniform(*yscale), rnd.uniform(*zscale)
    yaw = rnd.uniform(0, 2 * math.pi)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    pts = []
    for v in bm.verts:
        d = v.co.normalized()
        f = sum(a * max(0.0, d.dot(u)) ** k for u, a, k in lumps) / 2.0
        f += 0.35 * rnd.uniform(-1, 1) / (1 + int(subdiv))          # small facet jitter
        rr = r * (1.0 + noise * max(-1.0, min(1.0, f)))
        pts.append((d.x * rr, d.y * rr * sy, d.z * rr * sz))
    zmin = min(p_[2] for p_ in pts); zmax = max(p_[2] for p_ in pts)
    dz = zg - (zmin + sink * (zmax - zmin))
    verts = [(x + px * cy_ - py * sy_, y + px * sy_ + py * cy_, pz + dz) for px, py, pz in pts]
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return verts, faces


def stone_outline(rnd, r, sides=(5, 7), jitter=0.25, yscale=(1.0, 1.0), corners=4, corner_deg=30.0, tries=50):
    """Plan outline of an angular flat stone (a slab, not an ellipse): `sides` (an int or a [lo, hi] range) vertices
    at evenly spread angles (each moved by up to +-a quarter of the angular step) and radii r x (1 +- `jitter`), y
    squeezed by U(yscale) (elongated slabs), counter-clockwise around (0, 0). Redrawn (up to `tries` times) until at
    least `corners` corners turn by more than `corner_deg` degrees and the outline is convex enough not to fold (every
    turn positive), so the stone reads as an angular slab from above. Pure Python (math + the given random.Random)."""
    def turns(P):
        out = []
        for k in range(len(P)):
            (ax, ay), (bx, by), (cx_, cy_) = P[k - 1], P[k], P[(k + 1) % len(P)]
            a1, a2 = math.atan2(by - ay, bx - ax), math.atan2(cy_ - by, cx_ - bx)
            out.append(math.degrees((a2 - a1 + math.pi) % (2 * math.pi) - math.pi))
        return out
    lo, hi = (sides, sides) if isinstance(sides, int) else (int(sides[0]), int(sides[-1]))
    best = None
    for _ in range(int(tries)):
        n = rnd.randint(lo, hi)
        ph = rnd.uniform(0, 2 * math.pi)
        sy = rnd.uniform(*yscale)
        P = []
        for q in range(n):
            a = ph + 2 * math.pi * (q + rnd.uniform(-0.25, 0.25)) / n
            rr = r * (1.0 + rnd.uniform(-jitter, jitter))
            P.append((rr * math.cos(a), rr * sy * math.sin(a)))
        tr = turns(P)
        ok = all(t > 0 for t in tr)
        score = sum(t > corner_deg for t in tr)
        if ok and score >= corners:
            return P
        if ok and (best is None or score > best[0]):
            best = (score, P)
    return best[1] if best else P


def slab_stone(rnd, x, y, r, zg, sides=(5, 7), jitter=0.25, yscale=(0.6, 0.9), zscale=(0.35, 0.5), sink=0.3,
               bevel=(0.88, 0.62), tilt=0.15):
    """One angular flat landscape stone (default rock_scatter shape): a stone_outline() prism of height
    h = 2 r U(zscale) (the icosphere stones' height range), sunk `sink` of h below `zg`: the buried foot ring, a
    shoulder ring at 0.7 h inset to bevel[0] and a flat top at bevel[1] of the outline, tilted by up to `tilt` x h
    across the stone; random yaw. Returns (verts, faces) in world coordinates (faces: sides, bevel, one n-gon top)."""
    P = stone_outline(rnd, r, sides=sides, jitter=jitter, yscale=yscale)
    n = len(P)
    h = 2 * r * rnd.uniform(*zscale)
    zb = zg - sink * h
    yaw = rnd.uniform(0, 2 * math.pi)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    ua = rnd.uniform(0, 2 * math.pi); ux, uy = math.cos(ua), math.sin(ua)
    dd = [px * ux + py * uy for px, py in P]
    d0, d1 = min(dd), max(dd)
    verts = []
    for k_, (sc, zz) in enumerate(((1.0, None), (bevel[0], 0.7 * h), (bevel[1], None))):
        for (px, py), d_ in zip(P, dd):
            qx, qy = px * sc, py * sc
            if k_ == 0:
                z = zb
            elif k_ == 1:
                z = zb + zz
            else:                                    # planar tilted top: its highest corner at zb + h
                z = zb + h - tilt * h * (d1 - d_) / max(d1 - d0, 1e-9)
            verts.append((x + qx * cy_ - qy * sy_, y + qx * sy_ + qy * cy_, z))
    faces = []
    for ring in (0, 1):
        for k in range(n):
            a, b = ring * n + k, ring * n + (k + 1) % n
            faces.append([a, b, b + n, a + n])
    faces.append([2 * n + k for k in range(n)])
    return verts, faces


def k_rock_scatter(it, G, c, M, i):
    """Loose landscape rocks in a bed (seeded, so rebuilds are identical): angular, partly buried flat stones
    (slab_stone: a 5-7-sided outline with +-25 % radius jitter -- at least 4 corners turning > 30 deg -- squeezed to
    0.6-0.9 across, height 0.35-0.5 x the width with a bevelled, slightly tilted flat top, random yaw, 30 % of the height
    below grade), each with its own colour drawn from the item's colour range. "stones": [[x, y, diameter], ...] places
    measured stones, else `count` random ones in `polygon` (minus `holes`); "sides", "jitter", "yscale", "zscale",
    "sink" override the shape; "shape": "ico" gives the older noisy icosphere (rock_stone; "noise"), "dome" the older
    smooth dome (k_boulder) with "height" = fraction of the width above grade."""
    import random
    from shapely.geometry import Polygon, Point
    P = Polygon(it["polygon"]).buffer(0) if it.get("polygon") else Polygon()
    for h in it.get("holes", []):                  # keep clear of boulders / features inside the bed
        P = P.difference(Polygon(h).buffer(0.1))
    P = P.buffer(-0.2)
    if P.is_empty and not it.get("stones"):
        return
    rnd = random.Random(it.get("seed", 1))
    lo, hi = it.get("size", [0.3, 0.7])
    x0, y0, x1, y1 = P.bounds if not P.is_empty else (0, 0, 0, 0)
    ca, cb = _two(it, (0.31, 0.29, 0.25), (0.58, 0.55, 0.48))
    placed = []
    todo = [(float(x), float(y), float(d_) / 2) for x, y, d_ in it.get("stones", [])]     # measured positions
    for _ in range(len(todo) if todo else int(it.get("count", 10)) * 30):
        if todo:
            x, y, r = todo.pop(0)
        else:
            if len(placed) >= int(it.get("count", 10)):
                break
            x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
            r = rnd.uniform(lo, hi) / 2
            if not P.contains(Point(x, y)) or any(math.hypot(x - px, y - py) < r + pr + 0.1 for px, py, pr in placed):
                continue
        placed.append((x, y, r))
        zg = G.z(x, y, 0)
        nm = f"{it.get('name', 'rock')} {len(placed)}"
        if it.get("shape") == "dome":
            nv = 9; ph = rnd.uniform(0, math.pi)
            poly = [(x + r * rnd.uniform(0.75, 1.15) * math.cos(ph + 2 * math.pi * q / nv) * (1.0 if q % 2 else 1.15),
                     y + r * rnd.uniform(0.75, 1.15) * math.sin(ph + 2 * math.pi * q / nv)) for q in range(nv)]
            hlo, hhi = it.get("height", [0.45, 0.7])
            k_boulder({"polygon": poly, "top_z": zg + 2 * r * rnd.uniform(hlo, hhi), "color": it.get("color"),
                       "name": nm}, G, c, M, f"{i}.{len(placed)}")
            continue
        if it.get("shape") == "ico":
            v, f = rock_stone(rnd, x, y, r, zg, noise=it.get("noise", 0.25), yscale=it.get("yscale", (0.6, 0.9)),
                              zscale=it.get("zscale", (0.35, 0.5)), sink=it.get("sink", 0.3))
        else:
            v, f = slab_stone(rnd, x, y, r, zg, sides=it.get("sides", (5, 7)), jitter=it.get("jitter", 0.25),
                              yscale=it.get("yscale", (0.6, 0.9)), zscale=it.get("zscale", (0.35, 0.5)),
                              sink=it.get("sink", 0.3))
        t = rnd.random()
        col = tuple(a + (b - a) * t for a, b in zip(ca, cb))
        m_ = stone(f"Garden stone {i}.{len(placed)}", col, tuple(min(1.0, 1.12 * v_) for v_ in col), 6.0, 0.5)
        ob = mesh(nm, v, f, c, m_)
        ob.data.polygons.foreach_set("use_smooth", [False] * len(ob.data.polygons))
        ob.data.update()


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


_TERRAIN = {}     # main(): "tris" = terrain triangle corners [n, 3, 3] (the same triangles the terrain mesh is built of)


def drape_exact(P, tris, lift):
    """Drape the polygon ``P`` exactly on the terrain triangles ``tris`` ([n, 3, 3] corner coordinates): every piece of
    ``P`` inside a triangle gets that triangle's plane + ``lift`` (as build_site.py drapes its overlays), so no terrain
    pokes through a draped surface on rough ground. Returns (verts, tris) wound counter-clockwise (normals up)."""
    import numpy as np
    import shapely
    verts, out = [], []
    T = np.asarray(tris, float)
    if P.is_empty or not len(T):
        return verts, out
    bx0, by0, bx1, by1 = P.bounds
    mn, mx = T[:, :, :2].min(1), T[:, :, :2].max(1)
    T = T[(mx[:, 0] >= bx0) & (mn[:, 0] <= bx1) & (mx[:, 1] >= by0) & (mn[:, 1] <= by1)]
    if not len(T):
        return verts, out
    polys = shapely.polygons(T[:, :, :2])
    good = shapely.area(polys) > 1e-9
    shapely.prepare(P)
    inside = good & shapely.contains(P, polys)
    part = good & ~inside & shapely.intersects(P, polys)
    A = np.concatenate([T[:, :, :2], np.ones((len(T), 3, 1))], 2)
    coef = np.full((len(T), 3), np.nan)
    ok = inside | part
    coef[ok] = np.linalg.solve(A[ok], T[ok, :, 2][..., None])[..., 0]
    for k in np.nonzero(inside)[0]:
        b0 = len(verts)
        verts += [(float(x), float(y), float(z) + lift) for x, y, z in T[k]]
        out.append([b0, b0 + 1, b0 + 2])
    kp = np.nonzero(part)[0]
    for k, pc in zip(kp, shapely.intersection(P, polys[kp])):
        if pc.is_empty or pc.area < 1e-6:
            continue
        a_, b_, c_ = coef[k]
        for t in shapely.constrained_delaunay_triangles(pc).geoms:
            if t.area < 1e-7:
                continue
            b0 = len(verts)
            verts += [(x, y, float(a_ * x + b_ * y + c_) + lift) for x, y in list(t.exterior.coords)[:3]]
            out.append([b0, b0 + 1, b0 + 2])
    return verts, ccw_tris(verts, out)


def _drape(P, G, lift, step=0.5):
    if _TERRAIN.get("tris") is not None:
        # exact: on the terrain's own triangles (a coarser drape cuts under the 0.25 m terrain relief and the ground or
        # a bed overlay shows through it in patches)
        return drape_exact(P, _TERRAIN["tris"], lift)
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
    M["_grid"] = S.get("grid")             # terrain grid (bilinear heights: boulder max_over_terrain)
    # terrain (ground / rock faces) + draped overlays
    # explicit triangles along each cell's chosen fold (the same triangles the overlays were draped on); smooth
    # shading with creases kept sharp (> SHARP_DEG) and area-weighted normals: no dark folded shards on slopes
    ttris, fc = terrain_triangles(S["faces"], S.get("face_class") or [])
    terrain = mesh("Terrain (LiDAR ground)", S["verts"], ttris, c, M["ground"])
    import numpy as _np
    _vt = _np.asarray(S["verts"], float)
    _TERRAIN["tris"] = _vt[_np.asarray([t for t in ttris if len(t) == 3], int)] if len(_vt) and ttris else None
    nsharp = sharpen(terrain)
    print(f"terrain: {len(ttris)} triangles, {nsharp} sharp edges (> {SHARP_DEG:.0f} deg)")
    hp, hc = hide_reference(bpy.data.objects, bpy.data.collections, terrain=bool(len(_vt) and ttris))
    if hp or hc:
        print(f"terrain: reference ground hidden {hp}; not rendered: collections {hc}")
    if S.get("grid") and Y.get("face_normals", True):
        fixed = None
        if all(k in S["grid"] for k in ("x0", "y0", "cell")):
            ovxy = [v[:2] for o in (S.get("overlays") or {}).values() for v in o.get("verts", [])]
            dr = [it.get("polygon") for it in Y.get("items", []) if it.get("kind") in ("surface", "grade_pad")
                  and it.get("polygon") and (it.get("kind") == "surface" or it.get("surface"))]
            dr += [LineStringBuffer(it["line"], float(it.get("width", 0.9)) / 2) for it in Y.get("items", [])
                   if it.get("kind") == "path" and len(it.get("line", [])) >= 2]
            fixed = overlay_nodes(S["grid"], ovxy, [r for r in dr if r])
        nf = smooth_face_normals(terrain, S["grid"], fixed=fixed)
        print(f"terrain: {nf} steep-face vertices shaded with smoothed normals (vertex group 'rock face')"
              + (f"; {int(fixed.sum())} vertices under draped overlays kept in place" if fixed is not None else ""))
    classes = S.get("classes", [])
    if S.get("vertex_rock") and len(S["vertex_rock"]) == len(S["verts"]) and any(v > 0 for v in S["vertex_rock"]):
        # one material blending ground and rock by the per-vertex rock weight (soft boulder edges)
        at = terrain.data.attributes.new("rock", "FLOAT", "POINT")
        at.data.foreach_set("value", S["vertex_rock"])
        bt = boulder_tones(Y.get("items", []), S["verts"], M["_tones"]["rock"][:2]) if Y.get("boulder_tones", True) else None
        if bt:
            for nm_, cols in (("rock_tone_lo", bt[0]), ("rock_tone_hi", bt[1])):
                ca = terrain.data.color_attributes.new(nm_, "FLOAT_COLOR", "POINT")
                ca.data.foreach_set("color", [v for col in cols for v in (*col, 1.0)])
            print(f"terrain: {bt[2]} vertices inside yard boulder outlines take the boulder colours")
        terrain.data.materials.clear()
        terrain.data.materials.append(blend_by_attribute("Terrain (ground / rock)", M["_tones"]["ground"],
                                                         M["_tones"]["rock"], "rock",
                                                         tone_attrs=("rock_tone_lo", "rock_tone_hi") if bt else None))
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
    M["_walls"] = wall_solids(Y.get("items", []), G)          # pier plaque guard (k_pier)
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
