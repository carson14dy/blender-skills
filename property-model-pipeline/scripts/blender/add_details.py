"""Add the rest of the house to a measured model: openings, trim, gutters, decks, stairs, railings.

    python add_details.py MODEL.blend details.json OUT.blend   (bpy module, or blender -b -P ... --)

Works on a scene built by build_model.py (collections "Roof facets", "Walls", "Roof edges") and
the project's model.json (walls with bottom/profile; edges with kind/p0/p1). Everything added
lives in collection "Details" so measurements are untouched: these objects are presentation
geometry, placed from photo measurements. details.json (metres, model frame):

{
  "model_json": "path/to/model.json",
  "siding": {"style": "lap", "exposure": 0.1803, "color": [0.42, 0.42, 0.30]},
            # style "lap": horizontal shadow lines every `exposure` m (material "Siding (lap)");
            # "vertical": grooves every `spacing` m (default 0.203, T1-11 / board siding) running up each wall,
            #   spaced along that wall's own tangent ("Siding (vertical)"); "groove": groove width (default 0.012);
            # "smooth": plain colour, no texture ("Siding (smooth)") - use it when a photo shows no lines
  "roof": {"exposure": 0.1429, "color": [0.17, 0.17, 0.18]},          # shingle course lines
  "trim_color": [0.85, 0.85, 0.82], "deck_color": [0.07, 0.12, 0.09],
  "window_frame_color": [80, 68, 52],                                  # window/slider frames (default: trim)
  "concrete_color": [215, 207, 192],                                   # material "concrete" (walls, boxes, ...)
  "fascia_height": 0.2, "gutters": true, "soffits": true,
  "foundation": {"default_reveal": 0.25, "walls": {"M:-u": 0.54, "M:+v": 0.62}, "color": [r,g,b],   # siding-bottom z per wall
                 "skip": ["U", "M:+v"]},       # wings / walls with no foundation strip (an upper storey standing on a lower one)
  "openings": [ {"wall": "M:-u", "u": 9.98, "sill_z": 1.55, "width": 1.56, "height": 1.52,
                 "kind": "window|slider|door|garage|egress", "label": "...",
                 "leaf_color": [r,g,b], "frame_color": [r,g,b], "mullions": [0.25, 0.75], "mullion_width": 0.04,
                 "panels": [rows, cols], "style": "raised|ribbed", "rib_spacing": 0.1} ],   # u = distance from wall start
                 # leaf_color: door colour; mullions: vertical bars at these width fractions (default: one at 0.5
                 # for a 2-lite slider; a window wall of n units = one opening with n-1 mullions); panels: raised panels
                 # on a door / garage door (default 4x8 garage, 3x2 door); style "ribbed": a garage door with narrow
                 # horizontal grooves every rib_spacing m and no raised panels
  "decks": [ {"polygon": [[x,y],...], "top_z": 0.95, "rail_edges": [[i,j],...], "rail_gaps": [[x0,y0,x1,y1]],
              "rail_height": 0.9, "post_spacing": 2.0, "post_edges": [i,...],   # post_edges: edge i = vertex i -> i+1
              "rail_style": "balusters|screen|none",     # screen = closely spaced vertical boards under a flat cap rail
              "picket_width": 0.11, "picket_gap": 0.025, "rail_post_spacing": 0,
              "skirt": 0.0,                              # screen boards carried this far down over the rim / header
              # rail_edges items may also be {"edge": [i, j], "style": "screen", "skirt": 0.9} (per-edge overrides)
              "rail_color": [r,g,b], "board_color": [r,g,b], "rim_depth": 0.24, "rim_color": [r,g,b]} ],
              # rim_depth: depth of the rim joist / header board below the boards on every edge (a deep header
              # over a garage door is a rim of 0.8-0.9 m). A concave polygon (a notch around a light well) is fine.
  "stairs": [ {"top": [x,y], "dir": [dx,dy], "width": 1.0, "top_z": 0.95, "bottom_z": 0.2, "risers": 4,
               "length": 2.1,                             # horizontal run top -> bottom (default run 0.27 per tread)
               "rails": ["left", "right"],                # sloped handrails (left/right looking down the stairs)
               "rail_style": "balusters" | {"left": "screen", "right": "balusters"},
               "rail_color": [r,g,b], "tread_color": [r,g,b], "stringer_color": [r,g,b]} ],
  "ceilings": [ {"polygon": [[x,y],...], "z": 3.19, "color": [r,g,b]} ],   # porch ceilings, soffits under cantilevers
  "boxes": [ {"name": "...", "min": [x,y,z], "max": [x,y,z], "material": "brick|concrete|trim|deck|wood|stone|siding|vinyl",
              "color": [r,g,b]} ],
  "panels": [ {"name": "...", "polygon": [[x,y,z],...], "material": "siding"} ],    # flat infill (e.g. gable end over a porch)
  "beams": [ {"name": "...", "p0": [x,y,z], "p1": [x,y,z], "size": [width, depth], "material": "trim", "color": [r,g,b],
              "facet": "F2", "z_offset": 0.03} ],
              # a beam whose TOP face runs along p0 -> p1 (rim/porch beams, headers, trellis rafters). Give p0/p1 as
              # [x,y] to lay the beam IN the roof plane (the facet named, else the top facet at the midpoint; also over
              # an outline hole): its top sits z_offset above the plane and its depth hangs along the roof normal
  "beam_ends": [ {"xy": [x,y], "size": [width, depth], "length": 1.0, "proud": null, "drop": 0.06, "color": [r,g,b]} ],
              # rafter tails / outlooker ends under the nearest eave or rake: xy is the visible tip (as traced on an
              # orthophoto); the beam runs back square to that edge, its top `drop` under the roof edge. "proud"
              # overrides the tip's distance outside the edge line
  "wall_boxes": [ {"wall": "M:+u", "u": 1.5, "z": 0.4, "size": [w, h, depth], "color": [r,g,b], "name": "AC sleeve"} ],
              # wall-mounted boxes (through-wall AC, vents, meters); z = bottom
  "downspouts": [ {"xy": [x,y], "top_z": 3.5, "bottom_z": 0.2, "label": "...",
                   "path": [[x,y,z],...],         # optional leader from the gutter outlet to the top of the drop
                   "to_roof": false} ],           # true: the drop ends on the roof surface below top_z at xy (an
                   # upper gutter discharging onto a lower roof); it is then named "roof drop i", not "downspout i",
                   # so the site grounding step does not drag it down to the terrain
                   # A downspout runs ON a wall: xy = pipe centre ~0.06 m off a wall face (model or extra wall).
                   # The script prints a WARNING for any xy farther than "downspout_max_gap" (default 0.15 m) from
                   # every wall face (a free-standing pole). Bring the gutter outlet to it with "path": drop below
                   # the soffit first (soffit z = eave z - fascia_height), then run back under it to the wall.
  "corner_board_color": [r,g,b], "fascia_color": [r,g,b], "soffit_color": [r,g,b],   # default: trim / soffit white
  "roof_vents": [ {"xy": [x,y], "size": 0.32, "height": 0.16,
                   "shape": "box|pipe", "color": [r,g,b], "label": "..."} ],
                 # placed on the roof surface; "pipe" = round stack of diameter `size` (plumbing vent); ridge caps
                 # are automatic
  "skylights": [ {"xy": [x,y], "size": [across, along_slope], "curb": 0.15, "label": "...",   # on the top facet at xy
                  "curb_color": [r,g,b], "glass_color": [r,g,b], "glass_roughness": 0.2, "frame": 0.05, "dome": 0.0} ],
                 # curb: height of the curb top along the roof normal; frame: curb rim left visible around the glazing;
                 # dome > 0: domed / hipped glazing rising this far above the curb top at its centre (read the rim and
                 # crown heights off the LiDAR residuals to the roof plane). Default colours: trim curb, window glass
  "chimneys": [ {"center": [x,y], "size": [a,b], "azimuth": deg_of_a, "top_z": 7.9, "material": "siding|brick|stone",
                 "color": [r,g,b], "label": "...",
                 "shoulder": {"z": 7.25, "size": [a,b]},      # wider lower chase up to z, the stack above it
                 "cap": {"color": [r,g,b], "material": "trim", "overhang": 0.05, "thickness": 0.08}} ],
                 # chase from below the roof to top_z (cap included); default cap: metal
  "extra_walls": [ {"name": "GAR:-v", "bottom": [[x,y,z],[x,y,z]], "top_z": -0.55, "bearing": 214,
                    "material": "concrete", "color": [r,g,b], "thickness": 0.2} ],
                 # presentation-only walls (e.g. a garage under a deck) that openings can name like model walls;
                 # thickness > 0 builds a solid wall extruded inward (away from the bearing)
  "corner_boards": true,
  "lights": [ {"wall": "M:-v", "u": 5.4, "z": 2.9} ],
  "text": [ {"wall": "G:+u", "u": 0.5, "z": 0.9, "text": "12", "size": 0.16, "material": "fixture", "color": [r,g,b],
             "plate": [w, h], "plate_color": [r,g,b]} ],  # "\n" stacks lines; or "xy": [x,y] + "azimuth": facing deg
                                                          # instead of wall/u (a plaque on a pier or post)
  "caveats": ["what is not measured, and by how much it may be off", ...]
}
Walls are named "<wing>:<side>" as in model.json (e.g. "M:-u"); u runs from bottom[0] to bottom[1].
Provenance: every object built from a list entry carries custom properties "details" (e.g. "stairs[1]") and "label"
(the entry's full "label", else its "name"), so the measured / assumed status written in a label travels with the
geometry. The text block "Details notes" in the .blend lists every labelled entry, repeats the ones whose label has a
caveat word (assumed, extrapolated, not measured, +/-, ...) and the top-level "caveats" strings.
Colours: [r,g,b] in 0..1 are linear; any component > 1 means 8-bit sRGB (e.g. [225,215,180] read off a photo)
and is converted to linear.
"""
import json
import math
import sys

import bpy
from mathutils import Vector


def args():
    a = globals().get("PM_ARGS")
    if a is None:
        a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    return a


def col(c):
    """Colour from details.json: linear 0..1, or 8-bit sRGB when any component exceeds 1."""
    c = tuple(float(v) for v in c[:3])
    if max(c) <= 1.0:
        return c
    out = []
    for v in c:
        s = min(max(v / 255.0, 0.0), 1.0)
        out.append(s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def coll(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    return c


def mat(name, rgb, rough=0.7, metal=0.0, alpha=1.0, emission=0.0):
    rgb = col(rgb)
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        try:
            m.blend_method = "BLEND"
        except AttributeError:
            pass
    m.diffuse_color = (*rgb, alpha)
    return m


def pick(spec, mats, default, name, rough=0.7, key="color", mkey="material"):
    """Material for a details entry: its own colour, else a named material, else the default."""
    if spec.get(key) is not None:
        rgb = col(spec[key])     # one material per colour, so entries sharing a name never repaint each other
        return mat(f"{name[:32]} {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f}", rgb, rough)
    return mats.get(spec.get(mkey, default), mats[default])


SIDING_STYLES = ("lap", "vertical", "smooth")


def siding_material(rgb, exposure=0.1803, style="lap", spacing=0.203, groove=0.012):
    """Wall cladding material.

    lap:      horizontal shadow lines every `exposure` m (bump from world Z).
    vertical: grooves every `spacing` m running up the wall (T1-11 / board siding). The coordinate along each
              wall is computed per face from its normal (tangent = normalize(N x Z), dot world position), so
              walls at any bearing get grooves without UVs or one material per wall.
    smooth:   plain colour (stucco, panel, or a wall a photo shows without lines)."""
    if style not in SIDING_STYLES:
        raise ValueError(f"siding style {style!r}: expected one of {SIDING_STYLES}")
    rgb = col(rgb)
    if style == "smooth":
        return mat("Siding (smooth)", rgb, rough=0.85)
    if style == "vertical":
        m = mat("Siding (vertical)", rgb, rough=0.85)
        nt = m.node_tree
        b = nt.nodes.get("Principled BSDF")
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        cr = nt.nodes.new("ShaderNodeVectorMath"); cr.operation = "CROSS_PRODUCT"
        cr.inputs[1].default_value = (0.0, 0.0, 1.0)
        nz = nt.nodes.new("ShaderNodeVectorMath"); nz.operation = "NORMALIZE"
        dot = nt.nodes.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"
        div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = spacing
        fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "FRACT"
        lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"
        lt.inputs[1].default_value = min(max(groove / spacing, 0.0), 0.5)
        inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
        bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25
        nt.links.new(geo.outputs["Normal"], cr.inputs[0])
        nt.links.new(cr.outputs["Vector"], nz.inputs[0])
        nt.links.new(nz.outputs["Vector"], dot.inputs[0])
        nt.links.new(geo.outputs["Position"], dot.inputs[1])
        nt.links.new(dot.outputs["Value"], div.inputs[0])
        nt.links.new(div.outputs[0], fr.inputs[0])
        nt.links.new(fr.outputs[0], lt.inputs[0])
        nt.links.new(lt.outputs[0], inv.inputs[1])
        nt.links.new(inv.outputs[0], bump.inputs["Height"])          # groove = recessed
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        mx = nt.nodes.new("ShaderNodeMixRGB")                         # faint shadow in the groove
        mx.inputs["Color1"].default_value = (*rgb, 1)
        mx.inputs["Color2"].default_value = (rgb[0] * 0.7, rgb[1] * 0.7, rgb[2] * 0.7, 1)
        nt.links.new(lt.outputs[0], mx.inputs["Fac"])
        nt.links.new(mx.outputs["Color"], b.inputs["Base Color"])
        return m
    m = mat("Siding (lap)", rgb, rough=0.85)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = exposure
    fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "FRACT"
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.35
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], div.inputs[0])
    nt.links.new(div.outputs[0], fr.inputs[0])
    nt.links.new(fr.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    # shadow line under each lap (the top ~8% of a course sits under the butt of the board above)
    gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; gt.inputs[1].default_value = 0.92
    mx = nt.nodes.new("ShaderNodeMixRGB")
    mx.inputs["Color1"].default_value = (*rgb, 1)
    mx.inputs["Color2"].default_value = (rgb[0] * 0.45, rgb[1] * 0.45, rgb[2] * 0.45, 1)
    nt.links.new(fr.outputs[0], gt.inputs[0])
    nt.links.new(gt.outputs[0], mx.inputs["Fac"])
    nt.links.new(mx.outputs["Color"], b.inputs["Base Color"])
    return m


def shingle_material(rgb, exposure, slope):
    """Asphalt shingles: course shadow lines every `exposure` metres up the slope (bump from world Z)."""
    m = mat("Roof shingle (courses)", rgb, rough=0.9)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"
    div.inputs[1].default_value = exposure * slope / math.sqrt(1 + slope * slope)   # vertical spacing
    fr = nt.nodes.new("ShaderNodeMath"); fr.operation = "FRACT"
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.5
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], div.inputs[0])
    nt.links.new(div.outputs[0], fr.inputs[0])
    nt.links.new(fr.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def brick_material(rgb=(0.20, 0.055, 0.04), mortar=(0.55, 0.52, 0.47)):
    """Running-bond brick, mapped on world position (u = x + y, v = z) so axis-aligned faces need no UVs."""
    rgb = col(rgb)
    m = mat("Brick", rgb, rough=0.9)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "ADD"
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Color1"].default_value = (*rgb, 1)
    br.inputs["Color2"].default_value = (rgb[0] * 0.55, rgb[1] * 0.6, rgb[2] * 0.7, 1)
    br.inputs["Mortar"].default_value = (*mortar, 1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.006
    br.inputs["Brick Width"].default_value = 0.203
    br.inputs["Row Height"].default_value = 0.068
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["X"], add.inputs[0]); nt.links.new(sep.outputs["Y"], add.inputs[1])
    nt.links.new(add.outputs[0], comb.inputs["X"]); nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
    nt.links.new(comb.outputs[0], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    return m


def raised_panels(name, base, d, n, w, h, rows, cols, c, m, margin=0.06, gap=0.05, proud=0.012):
    """rows x cols raised rectangles on a door leaf (base = lower-left corner on the wall, d along, n outward)."""
    pw = (w - 2 * margin - (cols - 1) * gap) / cols
    ph = (h - 2 * margin - (rows - 1) * gap) / rows
    if pw <= 0.02 or ph <= 0.02:
        return
    for r in range(rows):
        for k in range(cols):
            p = base + d * (margin + k * (pw + gap)) + Vector((0, 0, margin + r * (ph + gap))) + n * 0.015
            oriented_box(f"{name} panel", p, d * pw, n * proud, Vector((0, 0, ph)), c, m)


_TAG = {}          # provenance stamped on every object made while it is set (see tag())


def tag(key=None, entry=None):
    """Objects created from now on carry custom properties details=key and label=entry's label (or name);
    tag() with no key stops tagging (trim, foundation, ... are not built from one entry)."""
    _TAG.clear()
    if key:
        _TAG["details"] = key
        lab = (entry or {}).get("label") or (entry or {}).get("name")
        if lab:
            _TAG["label"] = str(lab)


def stamp(ob):
    for k, v in _TAG.items():
        ob[k] = v
    return ob


CAVEAT_WORDS = ("assumed", "extrapolated", "estimated", "approximate", "approx", "unverified", "not measured",
                "by eye", "±", "+/-")
LIST_KEYS = ("openings", "extra_walls", "decks", "stairs", "ceilings", "boxes", "panels", "beams", "beam_ends",
             "wall_boxes", "downspouts", "roof_vents", "skylights", "chimneys", "lights", "text")


def details_notes(D):
    """(text, n_labelled, n_flagged): every labelled entry of details.json, the ones not fully measured (a caveat
    word in the label) repeated, and the top-level "caveats" strings."""
    rows, flagged = [], []
    for k, v in D.items():
        if isinstance(v, dict) and v.get("label"):
            rows.append((k, str(v["label"])))
    for k in LIST_KEYS:
        for i, e in enumerate(D.get(k, []) or []):
            lab = (e.get("label") or e.get("name")) if isinstance(e, dict) else None
            if lab:
                rows.append((f"{k}[{i}]", str(lab)))
    for key, lab in rows:
        if any(w in lab.lower() for w in CAVEAT_WORDS):
            flagged.append(f"- {key}: {lab}")
    cav = [f"- {c}" for c in D.get("caveats", []) or []]
    lines = ["Details: labelled entries", *[f"{k}: {lab}" for k, lab in rows]]
    if flagged or cav:
        lines += ["", "Caveats (not fully measured):", *cav, *flagged]
    return "\n".join(lines) + "\n", len(rows), len(flagged) + len(cav)


def mesh(name, verts, faces, c, m):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    ob.data.materials.append(m)
    return stamp(ob)


BOX_FACES = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]


def box(name, lo, hi, c, m):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return mesh(name, v, BOX_FACES, c, m)


def box_verts(origin, ex, ey, ez):
    o = Vector(origin)
    ex, ey, ez = Vector(ex), Vector(ey), Vector(ez)
    return [o, o + ex, o + ex + ey, o + ey, o + ez, o + ex + ez, o + ex + ey + ez, o + ey + ez]


def oriented_box(name, origin, ex, ey, ez, c, m):
    """Box spanned by vectors ex, ey, ez from origin."""
    return mesh(name, box_verts(origin, ex, ey, ez), BOX_FACES, c, m)


def boxes_mesh(name, boxes, c, m):
    """Many oriented boxes [(origin, ex, ey, ez), ...] as ONE object (pickets, balusters, ribs)."""
    if not boxes:
        return None
    verts, faces = [], []
    for b in boxes:
        k = len(verts)
        verts += box_verts(*b)
        faces += [[k + i for i in f] for f in BOX_FACES]
    return mesh(name, verts, faces, c, m)


def wall_frames(model):
    """{'M:-u': (start, along_unit, outward_unit, length, bottom_z(u))}"""
    out = {}
    for w in model["walls"]:
        a, b = Vector(w["bottom"][0]), Vector(w["bottom"][1])
        d = Vector((b.x - a.x, b.y - a.y, 0))
        L = d.length
        d.normalize()
        t = math.radians(w["bearing"])
        n = Vector((math.sin(t), math.cos(t), 0))
        za, zb = a.z, b.z
        out[f'{w["wing"]}:{w["side"]}'] = (Vector((a.x, a.y, 0)), d, n, L, lambda u, za=za, zb=zb, L=L: za + (zb - za) * u / max(L, 1e-9))
    return out


def add_opening(o, frames, c, mats):
    a, d, n, L, _ = frames[o["wall"]]
    w, h = o["width"], o["height"]
    u0 = o["u"] - w / 2
    base = a + d * u0 + Vector((0, 0, o["sill_z"]))
    kind = o.get("kind", "window")
    T, D = o.get("frame", 0.07), 0.04          # frame width, frame projection
    name = o.get("label", kind)[:40]
    # recessed glass / door leaf, slightly proud of the wall so it never z-fights
    leaf = mats["glass"] if kind in ("window", "slider", "egress") else (mats["garage"] if kind == "garage" else mats["door"])
    if kind == "slider" and h > 1.6:   # patio door: glass leaf
        leaf = mats["glass"]
    if o.get("leaf_color"):
        leaf = mat(f"Door ({name})", o["leaf_color"], 0.45)
    oriented_box(f"{name} leaf", base + n * 0.005, d * w, n * 0.01, Vector((0, 0, h)), c, leaf)
    # frame (4 bars): glazed units take the window-frame colour, doors the trim
    fm = mats["frame"] if kind in ("window", "slider", "egress") else mats["trim"]
    if o.get("frame_color"):
        fm = mat(f"Frame ({name})", o["frame_color"], 0.5)
    oriented_box(f"{name} head", base + d * (-T) + Vector((0, 0, h)), d * (w + 2 * T), n * D, Vector((0, 0, T)), c, fm)
    if kind not in ("door", "garage"):
        oriented_box(f"{name} sill", base + d * (-T) + Vector((0, 0, -T)), d * (w + 2 * T), n * (D + 0.02), Vector((0, 0, T)), c, fm)
    oriented_box(f"{name} jamb L", base + d * (-T), d * T, n * D, Vector((0, 0, h)), c, fm)
    oriented_box(f"{name} jamb R", base + d * w, d * T, n * D, Vector((0, 0, h)), c, fm)
    mull = o.get("mullions")
    if mull is None:
        mull = [0.5] if (kind in ("window", "slider") and (h <= 1.6 or kind == "slider") and w > 0.6) else []
    mw = o.get("mullion_width", 0.04)
    for fr in mull:   # meeting rails / mullions
        oriented_box(f"{name} mullion", base + d * (w * fr - mw / 2), d * mw, n * 0.02, Vector((0, 0, h)), c, fm)
    if kind == "garage":
        rows, cols = o.get("panels", [4, 8])
        if o.get("style") == "ribbed":   # lap-look steel door: narrow horizontal grooves, no raised panels
            sp = o.get("rib_spacing", 0.1)
            ribs = [(base + n * 0.016 + Vector((0, 0, z - 0.004)), d * w, n * 0.003, Vector((0, 0, 0.008)))
                    for z in [sp * k for k in range(1, int(h / sp))]]
            boxes_mesh(f"{name} ribs", ribs, c, mats["shadow"])
        else:                            # horizontal section joints + raised panels
            for k in range(1, rows):
                oriented_box(f"{name} joint {k}", base + n * 0.016 + Vector((0, 0, h * k / rows - 0.006)), d * w, n * 0.004, Vector((0, 0, 0.012)), c, mats["shadow"])
            for r in range(rows):
                raised_panels(name, base + Vector((0, 0, h * r / rows)), d, n, w, h / rows, 1, cols, c, leaf, margin=0.07, gap=0.09)
    elif kind == "door":
        rows, cols = o.get("panels", [3, 2])
        raised_panels(name, base, d, n, w, h, rows, cols, c, leaf, margin=0.12, gap=0.1)
        # lever handle on the side given by "handle" (0 = start side, 1 = end side of the wall direction)
        hs = o.get("handle", 1)
        oriented_box(f"{name} handle", base + d * (w * (0.92 if hs else 0.08) - 0.03) + n * 0.015 + Vector((0, 0, 0.95)), d * 0.06, n * 0.05, Vector((0, 0, 0.06)), c, mats["metal"])


def in_ring(ring, x, y):
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i][:2]; x2, y2 = ring[(i + 1) % len(ring)][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


def in_facet(f, x, y):
    """Point inside a facet's plan polygon (outer rings minus holes)."""
    return any(in_ring(p["outer"], x, y) and not any(in_ring(h, x, y) for h in p.get("holes", []))
               for p in f["polygons"])


def is_hole_edge(f, e, tol=0.02):
    """True when an edge runs along one of the facet's hole rings (a roof opening, e.g. an open trellis bay)."""
    for p in f["polygons"]:
        for h in p.get("holes", []):
            for i in range(len(h)):
                a, b = Vector((*h[i][:2], 0)), Vector((*h[(i + 1) % len(h)][:2], 0))
                ab = b - a
                if ab.length < 1e-6:
                    continue
                ok = True
                for q in (e["p0"], e["p1"]):
                    q = Vector((q[0], q[1], 0))
                    t = (q - a).dot(ab) / ab.length_squared
                    if not (-0.01 <= t <= 1.01) or (q - (a + ab * t)).length > tol:
                        ok = False
                if ok:
                    return True
    return False


def edge_outward(model, e):
    """Horizontal unit vector pointing away from the facet an eave/rake edge belongs to (the side where the
    facet's plan polygon is NOT: robust for concave outlines and hole edges, unlike a centroid test)."""
    p0, p1 = Vector(e["p0"]), Vector(e["p1"])
    dh = Vector((p1.x - p0.x, p1.y - p0.y, 0))
    f = next(f for f in model["facets"] if f["id"] == e["facets"][0])
    nrm = Vector((dh.y, -dh.x, 0)).normalized()
    mid = (p0 + p1) / 2
    a_in = in_facet(f, mid.x + nrm.x * 0.05, mid.y + nrm.y * 0.05)
    b_in = in_facet(f, mid.x - nrm.x * 0.05, mid.y - nrm.y * 0.05)
    if a_in != b_in:
        return -nrm if a_in else nrm
    pts = [v for p in f["polygons"] for v in p["outer"]]          # fallback: centroid side
    cx = sum(v[0] for v in pts) / len(pts)
    cy = sum(v[1] for v in pts) / len(pts)
    if (Vector((cx, cy, 0)) - Vector((mid.x, mid.y, 0))).dot(nrm) > 0:
        nrm = -nrm
    return nrm


def add_trim(model, frames, c, mats, fascia_h, gutters, soffits):
    for i, e in enumerate(model["edges"]):
        if e["kind"] not in ("eave", "rake") or e["length_m"] < 0.15:
            continue
        p0, p1 = Vector(e["p0"]), Vector(e["p1"])
        d = (p1 - p0)
        dh = Vector((d.x, d.y, 0))
        if dh.length < 1e-6:
            continue
        f = next(f for f in model["facets"] if f["id"] == e["facets"][0])
        if f.get("area_m2", 1.0) < 0.05:
            continue      # sliver facet (e.g. a flat roof left over under an upper storey): no trim
        nrm = edge_outward(model, e)
        mid = (p0 + p1) / 2
        down = Vector((0, 0, -fascia_h))
        # fascia: a thin board just inside the roof edge (also trims the edges of a roof opening)
        oriented_box(f"fascia {i}", p0 - nrm * 0.03, d, nrm * 0.03, down, c, mats["fascia"])
        if e["kind"] == "eave" and not is_hole_edge(f, e):     # no gutter / soffit inside a roof opening
            if gutters:
                g0 = p0 + nrm * 0.005 + Vector((0, 0, -0.03))
                oriented_box(f"gutter {i}", g0, d, nrm * 0.13, Vector((0, 0, -0.12)), c, mats["gutter"])
            if soffits:
                # horizontal soffit from the fascia back to the nearest parallel wall face (<= 2.5 m)
                best = None
                for k, (a, wd, wn, L, _) in frames.items():
                    if abs(wd.dot(dh.normalized())) < 0.99:
                        continue
                    dist = (Vector((mid.x, mid.y, 0)) - a).dot(wn)
                    along = (Vector((mid.x, mid.y, 0)) - a).dot(wd)
                    if 0.05 < dist < 2.5 and -0.5 < along < L + 0.5 and (best is None or dist < best):
                        best = dist
                if best:
                    z = min(p0.z, p1.z) - fascia_h
                    s0 = Vector((p0.x, p0.y, z)) - nrm * 0.03
                    oriented_box(f"soffit {i}", s0, Vector((d.x, d.y, 0)), -nrm * (best - 0.03), Vector((0, 0, -0.012)), c, mats["soffit"])


def skipped(key, skip):
    return key in skip or key.split(":")[0] in skip


def add_foundation(frames, fnd, c, mats, openings=()):
    """Foundation reveal strips per wall. Doors cut the strip down to their sill and windows set in the
    foundation (egress) leave a hole, so nothing is coplanar with a door leaf or glass. A per-wall top
    (foundation.walls) well above the bottom makes a concrete-faced lower storey; foundation.skip lists
    wings or walls without a strip (an upper storey standing on a lower one)."""
    skip = set(fnd.get("skip", []))
    for k, (a, d, n, L, zb) in frames.items():
        if skipped(k, skip):
            continue
        top = fnd.get("walls", {}).get(k)

        def ztop(u):
            return max(top if top is not None else zb(u) + fnd.get("default_reveal", 0.25), zb(u))
        cuts = []   # (u0, u1, sill, head)
        for o in openings:
            if o.get("wall") != k:
                continue
            T = o.get("frame", 0.07)
            cuts.append((o["u"] - o["width"] / 2 - T, o["u"] + o["width"] / 2 + T, o["sill_z"] - (0 if o.get("kind") in ("door", "garage") else T),
                         o["sill_z"] + o["height"] + T))
        us = sorted({0.0, L, *[L * s_ / 12 for s_ in range(13)], *[min(max(u, 0.0), L) for cu in cuts for u in cu[:2]]})
        verts, faces = [], []

        def quad(u0, u1, zl0, zl1, zh0, zh1):
            if zh0 - zl0 < 1e-3 and zh1 - zl1 < 1e-3:
                return
            p0, p1 = a + d * u0 + n * 0.015, a + d * u1 + n * 0.015
            i = len(verts)
            verts.extend([(p0.x, p0.y, zl0), (p1.x, p1.y, zl1), (p1.x, p1.y, zh1), (p0.x, p0.y, zh0)])
            faces.append([i, i + 1, i + 2, i + 3])
        for u0, u1 in zip(us[:-1], us[1:]):
            if u1 - u0 < 1e-4:
                continue
            um = (u0 + u1) / 2
            lo0, lo1, hi0, hi1 = zb(u0) - 0.15, zb(u1) - 0.15, ztop(u0), ztop(u1)
            cut = next((cu for cu in cuts if cu[0] - 1e-6 <= um <= cu[1] + 1e-6 and cu[2] < ztop(um)), None)
            if cut is None:
                quad(u0, u1, lo0, lo1, hi0, hi1)
            else:
                quad(u0, u1, lo0, lo1, min(hi0, cut[2]), min(hi1, cut[2]))       # below the sill
                if cut[3] < min(hi0, hi1):                                           # above the head
                    quad(u0, u1, cut[3], cut[3], hi0, hi1)
        if faces:
            mesh(f"foundation {k}", verts, faces, c, mats["foundation"])


def rail_run(name, pa, pb, H, style, c, m, opts, slope_floor=False):
    """Railing infill between two points at walking-surface level (pa.z, pb.z; sloped on stairs).

    style "balusters": 0.07 top rail, bottom rail, 40 mm balusters at 0.13 m.
    style "screen":   closely spaced vertical boards (picket_width / picket_gap) under a flat cap rail,
                      reaching down to the walking surface (a privacy-screen railing)."""
    run = pb - pa
    L = Vector((run.x, run.y, 0)).length
    if L < 0.05:
        return
    u = Vector((run.x, run.y, 0)).normalized()
    side = u.cross(Vector((0, 0, 1))).normalized()
    up = Vector((0, 0, 1))
    if style == "screen":
        cap_w = opts.get("cap_width", 0.14)
        oriented_box(f"{name} rail cap", pa + up * (H - 0.04) - side * (cap_w / 2), run, side * cap_w, up * 0.04, c, m)
        pw, gap = opts.get("picket_width", 0.11), opts.get("picket_gap", 0.025)
        k_n = max(int((L - 0.05) / (pw + gap)), 1)
        pitch = (L - pw) / max(k_n, 1)
        pickets = []
        skirt = opts.get("skirt", 0.0)                     # boards carried down over the rim / header
        for k in range(k_n + 1):
            t = (k * pitch + pw / 2) / L
            q = pa + run * t
            z0 = q.z - (0.12 if slope_floor else 0.0) - skirt   # on stairs the boards run down over the stringer
            pickets.append((Vector((q.x, q.y, z0)) - u * (pw / 2) - side * 0.0125, u * pw, side * 0.025, up * (q.z + H - 0.04 - z0)))
        boxes_mesh(f"{name} rail pickets", pickets, c, m)
    elif style != "none":
        w2 = side * 0.07
        oriented_box(f"{name} rail top", pa + up * (H - 0.07) - w2 / 2, run, w2, up * 0.07, c, m)
        lo = 0.12 if slope_floor else 0.08
        oriented_box(f"{name} rail bottom", pa + up * lo - w2 * 0.3, run, w2 * 0.6, up * 0.05, c, m)
        nb = max(int(L / 0.13), 1)
        bal = []
        for k in range(1, nb):
            q = pa + run * (k / nb)
            bal.append((q + Vector((-0.02, -0.02, lo)), Vector((0.04, 0, 0)), Vector((0, 0.04, 0)), up * (H - 0.07 - lo)))
        boxes_mesh(f"{name} rail balusters", bal, c, m)


def add_deck(dk, c, mats, idx):
    poly = [Vector((x, y, 0)) for x, y in dk["polygon"]]
    z = dk["top_z"]
    t = 0.04
    board = pick(dk, mats, "deck", f"deck {idx} boards", 0.75, key="board_color")
    rim_m = pick(dk, mats, "deck", f"deck {idx} rim", 0.75, key="rim_color")
    rail_m = pick(dk, mats, "deck", f"deck {idx} rail", 0.8, key="rail_color")
    top = [(p.x, p.y, z) for p in poly]
    bot = [(p.x, p.y, z - t) for p in poly]
    n = len(poly)
    faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    mesh(f"deck {idx} boards", top + bot, faces, c, board)
    # rim joist / header (rim_depth), always just inside the outline (either winding) + support posts
    rd = dk.get("rim_depth", 0.24)
    ccw = sum(poly[i].x * poly[(i + 1) % n].y - poly[(i + 1) % n].x * poly[i].y for i in range(n)) > 0
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        inward = (b - a).cross(Vector((0, 0, 1))).normalized() * (-0.04 if ccw else 0.04)
        oriented_box(f"deck {idx} rim {i}", a + Vector((0, 0, z - t - rd)), b - a, inward, Vector((0, 0, rd)), c, rim_m)
    sp = dk.get("post_spacing", 2.0)
    ps = dk.get("post_size", 0.09) / 2
    seen = set()
    for i in dk.get("post_edges", range(n)):      # edges carried by walls below (a garage) need no posts
        a, b = poly[i], poly[(i + 1) % n]
        L = (b - a).length
        for s in range(int(L // sp) + 1):
            p = a + (b - a) * (s * sp / max(L, 1e-9))
            key = (round(p.x, 1), round(p.y, 1))
            if key in seen:
                continue
            seen.add(key)
            box(f"deck {idx} post", (p.x - ps, p.y - ps, dk.get("grade_z", 0.2)), (p.x + ps, p.y + ps, z - t - rd + 0.01), c, rim_m)
    # railings
    H = dk.get("rail_height", 0.9)
    style = dk.get("rail_style", "balusters")
    gaps = dk.get("rail_gaps", [])
    seen_posts = set()
    for re_ in dk.get("rail_edges", []):
        if isinstance(re_, dict):      # per-edge overrides: {"edge": [i, j], "style": "screen", "skirt": 0.9}
            (i, j), estyle = re_["edge"], re_.get("style", style)
            eopts = {**dk, "skirt": re_.get("skirt", dk.get("skirt", 0.0))}
        else:
            (i, j), estyle, eopts = re_, style, dk
        a, b = poly[i], poly[j]
        L = (b - a).length
        u = (b - a) / max(L, 1e-9)
        segs = [(0.0, L)]
        for g in gaps:
            g0, g1 = Vector((g[0], g[1], 0)), Vector((g[2], g[3], 0))
            t0, t1 = sorted([(g0 - a).dot(u), (g1 - a).dot(u)])
            if (g0 - a).cross(u).length < 0.3 and t1 > 0 and t0 < L:
                segs = [s for seg in segs for s in ((seg[0], min(seg[1], t0)), (max(seg[0], t1), seg[1])) if s[1] - s[0] > 0.05]
        for s0, s1 in segs:
            pa = a + u * s0 + Vector((0, 0, z))
            pb = a + u * s1 + Vector((0, 0, z))
            rail_run(f"deck {idx}", pa, pb, H, estyle, c, rail_m, eopts)
            rs = dk.get("rail_post_spacing", 0)
            ends = [pa, pb]
            if rs and (s1 - s0) > rs * 1.3:
                k_n = int(round((s1 - s0) / rs))
                ends += [pa + (pb - pa) * (k / k_n) for k in range(1, k_n)]
            for pend in ends:
                key = (round(pend.x, 2), round(pend.y, 2))
                if key in seen_posts:      # corner shared by two rail runs: one post, no coincident faces
                    continue
                seen_posts.add(key)
                box(f"deck {idx} rail post", (pend.x - 0.045, pend.y - 0.045, z), (pend.x + 0.045, pend.y + 0.045, z + H + 0.05), c, rail_m)


def add_stairs(st, c, mats, idx):
    top = Vector((*st["top"], 0))
    dvec = Vector((*st["dir"], 0)).normalized()
    side = dvec.cross(Vector((0, 0, 1))).normalized()
    W, r = st["width"], st["risers"]
    rise = (st["top_z"] - st["bottom_z"]) / r
    run = st["length"] / max(r - 1, 1) if st.get("length") else st.get("run", 0.27)
    tread_m = pick(st, mats, "deck", f"stair {idx} treads", 0.8, key="tread_color")
    str_m = pick(st, mats, "deck", f"stair {idx} stringers", 0.8, key="stringer_color") if st.get("stringer_color") else tread_m
    rail_m = pick(st, mats, "deck", f"stair {idx} rail", 0.8, key="rail_color")
    for k in range(1, r):
        z = st["top_z"] - k * rise
        p0 = top + dvec * (run * (k - 1)) - side * (W / 2) + Vector((0, 0, z - 0.04))
        oriented_box(f"stair {idx} tread {k}", p0, dvec * run, side * W, Vector((0, 0, 0.04)), c, tread_m)
    length = run * (r - 1)
    for sgn in (-1, 1):   # sloped stringers under the tread ends, toe on the ground
        o = top - side * (sgn * W / 2)
        tz, bz = st["top_z"], st["bottom_z"]
        quad = [o + Vector((0, 0, tz - 0.04)), o + dvec * length + Vector((0, 0, bz + rise - 0.04)),
                o + dvec * length + Vector((0, 0, bz)), o + Vector((0, 0, tz - 0.04 - 0.3))]
        th = side * 0.05 * sgn
        verts = quad + [p + th for p in quad]
        mesh(f"stair {idx} stringer", verts, [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]], c, str_m)
    # sloped handrails: "left"/"right" looking down the stairs
    H = st.get("rail_height", 0.9)
    drop = rise * (r - 1)
    styles = st.get("rail_style", "balusters")
    for which in st.get("rails", []):
        style = styles.get(which, "balusters") if isinstance(styles, dict) else styles
        sgn = 1 if which == "left" else -1          # side = dvec x up points to the right-hand side looking down
        off = -side * (sgn * (W / 2 - 0.045))
        t0 = top + off + Vector((0, 0, st["top_z"]))
        t1 = top + off + dvec * length + Vector((0, 0, st["top_z"] - drop))
        for q, zb, hw in ((t0, st["top_z"], 0.04), (t1, st["bottom_z"], 0.045)):   # top post slimmer: it meets the deck rail post
            box(f"stair {idx} rail post", (q.x - hw, q.y - hw, zb), (q.x + hw, q.y + hw, q.z + H + 0.05), c, rail_m)
        rail_run(f"stair {idx}", t0, t1, H, style, c, rail_m, st, slope_floor=True)


def facet_z(model, x, y):
    """Top roof surface z at (x, y) from the facet planes (point-in-polygon on the outer rings)."""
    best = None
    for f in model["facets"]:
        a, b, c0 = f["plane"]
        for poly in f["polygons"]:
            ring = poly["outer"]
            inside = False
            for i in range(len(ring)):
                x1, y1 = ring[i][:2]; x2, y2 = ring[(i + 1) % len(ring)][:2]
                if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
                    inside = not inside
            if inside:
                z = a * x + b * y + c0
                best = z if best is None else max(best, z)
    return best


def add_roof_extras(model, D, c, mats):
    up = Vector((0, 0, 1))
    tag()
    for i, e in enumerate(model["edges"]):
        if e["kind"] not in ("ridge", "hip") or e["length_m"] < 0.3:
            continue
        p0, p1 = Vector(e["p0"]), Vector(e["p1"])
        side = (p1 - p0).cross(up).normalized()
        oriented_box(f"ridge cap {i}", p0 - side * 0.15 + up * 0.005, p1 - p0, side * 0.30, up * 0.05, c, mats["cap"])
    for i, v in enumerate(D.get("roof_vents", [])):
        tag(f"roof_vents[{i}]", v)
        x, y = v["xy"]
        z = facet_z(model, x, y)
        if z is None:
            print(f"roof vent {i} at ({x:.2f}, {y:.2f}) is off the roof, skipped")
            continue
        w = v.get("size", 0.32)
        h = v.get("height", 0.16)
        nm = v.get("label", f"roof vent {i}")[:40]
        m = pick(v, mats, "vent", nm, 0.6)
        if v.get("shape", "box") == "pipe":       # round stack (plumbing vent): 8-sided prism of diameter w
            k = 8
            ring = [(x + w / 2 * math.cos(2 * math.pi * j / k), y + w / 2 * math.sin(2 * math.pi * j / k)) for j in range(k)]
            verts = [(px, py, z - 0.05) for px, py in ring] + [(px, py, z + h) for px, py in ring]
            faces = [list(range(k - 1, -1, -1)), list(range(k, 2 * k))] + \
                    [[j, (j + 1) % k, k + (j + 1) % k, k + j] for j in range(k)]
            mesh(nm, verts, faces, c, m)
        else:
            box(nm, (x - w / 2, y - w / 2, z - 0.05), (x + w / 2, y + w / 2, z + h), c, m)


def facet_plane(model, x, y):
    """(a, b, c) of the top facet at (x, y), or None."""
    best, top = None, None
    for f in model["facets"]:
        a, b, c0 = f["plane"]
        z = a * x + b * y + c0
        if facet_z_one(f, x, y) and (top is None or z > top):
            best, top = (a, b, c0), z
    return best


def facet_z_one(f, x, y):
    for poly in f["polygons"]:
        ring, inside = poly["outer"], False
        for i in range(len(ring)):
            x1, y1 = ring[i][:2]; x2, y2 = ring[(i + 1) % len(ring)][:2]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
                inside = not inside
        if inside:
            return True
    return False


def add_skylights_chimneys(model, D, c, mats):
    for i, s in enumerate(D.get("skylights", [])):
        tag(f"skylights[{i}]", s)
        x, y = s["xy"]
        pl = facet_plane(model, x, y)
        if pl is None:
            continue
        a, b, c0 = pl
        g = math.hypot(a, b)
        down = Vector((-a / g, -b / g, 0)) if g > 1e-6 else Vector((0, -1, 0))
        across = Vector((-down.y, down.x, 0))
        along = Vector((down.x, down.y, -g)).normalized()          # down the slope, in the roof plane
        nrm = across.cross(along).normalized()
        if nrm.z < 0:
            nrm = -nrm
        w, l = s.get("size", (0.6, 1.2))
        h = s.get("curb", 0.15)
        fw = min(s.get("frame", 0.05), 0.45 * min(w, l))        # curb rim left visible around the glazing
        dome = max(float(s.get("dome", 0.0)), 0.0)
        ctr = Vector((x, y, a * x + b * y + c0))
        o = ctr - across * (w / 2) - along * (l / 2)
        nm = s.get("label", f"skylight {i}")[:40]
        curb_m = pick(s, mats, "trim", f"skylight {i} curb", 0.5, key="curb_color", mkey="curb_material")
        glass_m = pick(s, mats, "glass", f"skylight {i} glass", s.get("glass_roughness", 0.2), key="glass_color",
                       mkey="glass_material")
        oriented_box(f"{nm} curb", o - nrm * 0.03, across * w, along * l, nrm * (h + 0.03), c, curb_m)
        g0, gw, gl = o + across * fw + along * fw + nrm * h, w - 2 * fw, l - 2 * fw
        if dome <= 0:
            oriented_box(f"{nm} glass", g0, across * gw, along * gl, nrm * 0.02, c, glass_m)
            continue
        # domed / hipped glazing: 4 rings from the curb top to a flat crown `dome` above it (quarter-sine profile)
        inset = 0.4 * min(gw, gl)
        ccw = across.cross(along).dot(nrm) > 0
        verts, faces = [], []
        for k in range(4):
            t = k / 3
            d, e = inset * t, dome * math.sin(t * math.pi / 2)
            ring = [(d, d), (gw - d, d), (gw - d, gl - d), (d, gl - d)]
            if not ccw:
                ring.reverse()
            verts += [g0 + across * p + along * q + nrm * e for p, q in ring]
        for k in range(3):
            faces += [[4 * k + j, 4 * k + (j + 1) % 4, 4 * (k + 1) + (j + 1) % 4, 4 * (k + 1) + j] for j in range(4)]
        faces.append([12, 13, 14, 15])
        mesh(f"{nm} glass", verts, faces, c, glass_m)
    for i, ch in enumerate(D.get("chimneys", [])):
        tag(f"chimneys[{i}]", ch)
        x, y = ch["center"]
        A, B = ch.get("size", (0.9, 0.9))
        t = math.radians(ch.get("azimuth", 0.0))
        ea = Vector((math.sin(t), math.cos(t), 0))
        eb = Vector((-ea.y, ea.x, 0))
        sh = ch.get("shoulder")
        SA, SB = sh.get("size", (A, B)) if sh else (A, B)
        corners = [Vector((x, y, 0)) + ea * (sa * max(A, SA) / 2) + eb * (sb * max(B, SB) / 2) for sa in (-1, 1) for sb in (-1, 1)]
        zs = [facet_z(model, p.x, p.y) for p in corners]
        zs = [z for z in zs if z is not None]
        z0 = (min(zs) if zs else ch["top_z"] - 1.5) - 0.3
        ctr = Vector((x, y, 0))
        m = pick(ch, mats, "siding", f"chimney {i}", 0.85)
        nm = ch.get("label", f"chimney {i}")[:40]
        cp = ch.get("cap", {})
        ct, co = cp.get("thickness", 0.08), cp.get("overhang", 0.05)
        cap_m = pick(cp, mats, "metal", f"chimney {i} cap", 0.6) if cp else mats["metal"]
        zs_ = z0
        if sh:   # wider lower chase up to the shoulder, the stack above it
            oriented_box(f"{nm} shoulder", Vector((x, y, z0)) - ea * (SA / 2) - eb * (SB / 2), ea * SA, eb * SB,
                         Vector((0, 0, sh["z"] - z0)), c, m)
            zs_ = sh["z"] - 0.02
        o = Vector((x, y, zs_)) - ea * (A / 2) - eb * (B / 2)
        oriented_box(nm, o, ea * A, eb * B, Vector((0, 0, ch["top_z"] - ct - zs_)), c, m)
        oriented_box(f"{nm} cap", ctr + Vector((0, 0, ch["top_z"] - ct)) - ea * (A / 2 + co) - eb * (B / 2 + co),
                     ea * (A + 2 * co), eb * (B + 2 * co), Vector((0, 0, ct)), c, cap_m)


def add_beams(model, D, c, mats):
    """Straight beams (rim/porch beams, headers, trellis rafters lying in a roof plane)."""
    for i, bm in enumerate(D.get("beams", [])):
        tag(f"beams[{i}]", bm)
        p0, p1 = list(bm["p0"]), list(bm["p1"])
        w, h = bm.get("size", (0.15, 0.2))
        nm = bm.get("name", f"beam {i}")[:40]
        m = pick(bm, mats, "trim", nm, 0.6)
        if len(p0) == 2 or len(p1) == 2:
            if bm.get("facet"):
                pl = next(f["plane"] for f in model["facets"] if f["id"] == bm["facet"])
            else:
                pl = facet_plane(model, (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            if pl is None:
                print("beam off the roof, skipped:", nm)
                continue
            a, b, c0 = pl
            off = bm.get("z_offset", 0.0)
            P0 = Vector((p0[0], p0[1], a * p0[0] + b * p0[1] + c0 + off))
            P1 = Vector((p1[0], p1[1], a * p1[0] + b * p1[1] + c0 + off))
            nrm = Vector((-a, -b, 1.0)).normalized()
        else:
            P0, P1, nrm = Vector(p0), Vector(p1), Vector((0, 0, 1))
        dv = P1 - P0
        sd = dv.cross(nrm).normalized() * w
        oriented_box(nm, P0 - sd / 2 - nrm * h, dv, sd, nrm * h, c, m)


def add_beam_ends(model, D, c, mats):
    """Rafter tails / outlooker ends showing under eaves and rakes, placed from their traced tips."""
    edges = [e for e in model["edges"] if e["kind"] in ("eave", "rake") and e["length_m"] > 0.3]
    for i, be in enumerate(D.get("beam_ends", [])):
        tag(f"beam_ends[{i}]", be)
        q = Vector((be["xy"][0], be["xy"][1], 0))
        best = None
        for e in edges:
            p0, p1 = Vector(e["p0"]), Vector(e["p1"])
            a2, b2 = Vector((p0.x, p0.y, 0)), Vector((p1.x, p1.y, 0))
            ab = b2 - a2
            t = max(0.0, min(1.0, (q - a2).dot(ab) / max(ab.length_squared, 1e-12)))
            dist = (q - (a2 + ab * t)).length
            if best is None or dist < best[0]:
                best = (dist, e, t, a2 + ab * t, p0.z + (p1.z - p0.z) * t)
        if best is None:
            continue
        _, e, t, foot, ze = best
        nrm = edge_outward(model, e)
        proud = be.get("proud")
        if proud is None:
            proud = max((q - foot).dot(nrm), 0.05)
        tip = foot + nrm * proud
        L = be.get("length", proud + 0.8)
        w, h = be.get("size", (0.15, 0.2))
        sd = nrm.cross(Vector((0, 0, 1))).normalized()
        topz = ze - be.get("drop", 0.06)
        o = tip - nrm * L - sd * (w / 2) + Vector((0, 0, topz - h))
        nm = be.get("name", f"beam end {i}")[:40]
        oriented_box(nm, o, nrm * L, sd * w, Vector((0, 0, h)), c, pick(be, mats, "trim", "beam ends", 0.6))


def add_extra_walls(D, frames, c, mats):
    for i, w in enumerate(D.get("extra_walls", [])):
        tag(f"extra_walls[{i}]", w)
        (x0, y0, z0), (x1, y1, z1) = w["bottom"]
        top = w["top_z"]
        m = pick(w, mats, "siding", f"wall {w['name']}", 0.85)
        d = Vector((x1 - x0, y1 - y0, 0))
        L = d.length
        d.normalize()
        n = Vector((math.sin(math.radians(w["bearing"])), math.cos(math.radians(w["bearing"])), 0)) if "bearing" in w \
            else Vector((d.y, -d.x, 0))                   # outward = right of travel by default
        th = w.get("thickness", 0.0)
        face = [(x0, y0, z0), (x1, y1, z1), (x1, y1, top), (x0, y0, top)]
        if th > 0:   # solid wall: outer face on the given line, extruded inward
            back = [(p[0] - n.x * th, p[1] - n.y * th, p[2]) for p in face]
            mesh(f"wall {w['name']}", face + back, [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]], c, m)
        else:
            mesh(f"wall {w['name']}", face, [[0, 1, 2, 3]], c, m)
        frames[w["name"]] = (Vector((x0, y0, 0)), d, n, L, lambda u, za=z0, zb=z1, L=L: za + (zb - za) * u / max(L, 1e-9))


def add_corner_boards(model, frames, fnd, c, mats, width=0.1):
    skip = set(fnd.get("skip", []))
    for w in model["walls"]:
        key = f'{w["wing"]}:{w["side"]}'
        a, d, n, L, zb = frames[key]
        top0, top1 = w["profile"][0][2], w["profile"][-1][2]
        sb = fnd.get("walls", {}).get(key)
        for u, zt, sgn in ((0.0, top0, 1), (L, top1, -1)):
            z0 = zb(u) if skipped(key, skip) else (sb if sb is not None else zb(u) + fnd.get("default_reveal", 0.25))
            p = a + d * u + n * 0.012 + Vector((0, 0, z0))
            oriented_box(f"corner board {key}", p, d * (width * sgn), n * 0.02, Vector((0, 0, zt - z0 - 0.05)), c, mats["corner"])


def add_wall_boxes(D, frames, c, mats):
    for i, wb in enumerate(D.get("wall_boxes", [])):
        tag(f"wall_boxes[{i}]", wb)
        a, d, n, L, _ = frames[wb["wall"]]
        w, h, dep = wb.get("size", (0.6, 0.4, 0.25))
        p = a + d * (wb["u"] - w / 2) + Vector((0, 0, wb["z"]))
        nm = wb.get("name", f"wall box {i}")[:40]
        oriented_box(nm, p + n * 0.005, d * w, n * dep, Vector((0, 0, h)), c, pick(wb, mats, "vinyl", nm, 0.5))


def wall_gap(xy, frames):
    """Horizontal distance from a point to the nearest wall face (segment, clamped at its ends) of any frame."""
    q = Vector((xy[0], xy[1], 0))
    best = math.inf
    for a, d, n, L, _ in frames.values():
        rel = q - a
        u, v = rel.dot(d), rel.dot(n)
        best = min(best, math.hypot(v, max(0.0, -u, u - L)))
    return best


def roof_below(model, x, y, zmax):
    """Highest roof surface z at (x, y) that lies below zmax (None when no facet covers the point)."""
    best = None
    for f in model["facets"]:
        if not facet_z_one(f, x, y):
            continue
        a, b, c0 = f["plane"]
        z = a * x + b * y + c0
        if z < zmax and (best is None or z > best):
            best = z
    return best


def add_downspouts(model, D, frames, c, mats):
    """Downspouts on wall faces, with optional leaders from the gutter outlet (see the docstring)."""
    tol = D.get("downspout_max_gap", 0.15)
    for i, ds in enumerate(D.get("downspouts", [])):
        tag(f"downspouts[{i}]", ds)
        x, y = ds["xy"]
        gap = wall_gap((x, y), frames)
        if gap > tol:
            print(f"WARNING: downspout {i} at ({x:.2f}, {y:.2f}) is {gap:.2f} m from the nearest wall face "
                  f"(> {tol:.2f} m): a free-standing pipe. Put it on a wall and bring the gutter outlet to it with 'path'.")
        bottom, name = ds.get("bottom_z", 0.2), f"downspout {i}"
        if ds.get("to_roof"):
            zr = roof_below(model, x, y, ds["top_z"])
            if zr is None:
                print(f"WARNING: downspout {i} has to_roof but no roof below ({x:.2f}, {y:.2f}); using bottom_z")
            else:
                bottom, name = zr, f"roof drop {i}"
        box(name, (x - 0.04, y - 0.04, bottom), (x + 0.04, y + 0.04, ds["top_z"]), c, mats["gutter"])
        path = [Vector(p) for p in ds.get("path", [])]
        if path:
            path.append(Vector((x, y, ds["top_z"] - 0.04)))
        for k in range(len(path) - 1):      # leader pipes (named so the grounding step leaves them alone)
            p0, p1 = path[k], path[k + 1]
            dv = p1 - p0
            if dv.length < 1e-3:
                continue
            sx = dv.cross(Vector((0, 0, 1)))
            sx = (sx.normalized() if sx.length > 1e-6 else Vector((1, 0, 0))) * 0.08
            sz = sx.cross(dv).normalized() * 0.08
            oriented_box(f"gutter leader {i}.{k}", p0 - sx / 2 - sz / 2, dv, sx, sz, c, mats["gutter"])


def add_lights_and_text(D, frames, c, mats):
    import mathutils
    for i, l in enumerate(D.get("lights", [])):
        tag(f"lights[{i}]", l)
        a, d, n, L, _ = frames[l["wall"]]
        p = a + d * l["u"] + Vector((0, 0, l["z"]))
        oriented_box(f"light {i} plate", p - d * 0.06 - Vector((0, 0, 0.08)), d * 0.12, n * 0.03, Vector((0, 0, 0.16)), c, mats["fixture"])
        oriented_box(f"light {i} arm", p - d * 0.015 + Vector((0, 0, 0.04)), d * 0.03, n * 0.22, Vector((0, 0, 0.03)), c, mats["fixture"])
        oriented_box(f"light {i} shade", p - d * 0.12 + n * 0.12 - Vector((0, 0, 0.1)), d * 0.24, n * 0.24, Vector((0, 0, 0.12)), c, mats["fixture"])
    for i, t in enumerate(D.get("text", [])):
        tag(f"text[{i}]", t)
        if "wall" in t:
            a, d, n, L, _ = frames[t["wall"]]
            p = a + d * t["u"] + Vector((0, 0, t["z"]))
        else:                                  # free-standing: a plaque on a pier, post or gate
            az = math.radians(t.get("azimuth", 180.0))
            n = Vector((math.sin(az), math.cos(az), 0))
            d = Vector((-n.y, n.x, 0))           # reading direction: left-to-right seen from the front
            p = Vector((t["xy"][0], t["xy"][1], t["z"]))
        off = t.get("offset", 0.12 if "wall" in t else 0.01)
        if t.get("plate"):
            pw, ph = t["plate"]
            oriented_box(f"plaque {i}", p + n * (off - 0.02) - d * (pw / 2) - Vector((0, 0, ph / 2)), d * pw, n * 0.02,
                         Vector((0, 0, ph)), c, pick(t, mats, "trim", f"plaque {i}", 0.5, key="plate_color"))
        cu = bpy.data.curves.new(f"text {i}", "FONT")
        cu.body = t["text"]; cu.size = t.get("size", 0.15); cu.align_x = "CENTER"; cu.extrude = 0.004
        if t.get("plate"):
            cu.align_y = "CENTER"
        ob = bpy.data.objects.new(f"text {t['text']}", cu)
        ob.location = p + n * off
        # text faces +Z by default: rotate to stand up and face outward
        ob.rotation_euler = mathutils.Matrix((d, Vector((0, 0, 1)), n)).transposed().to_euler()
        cu.materials.append(pick(t, mats, "trim", f"text {i}", 0.5))
        c.objects.link(ob)
        stamp(ob)


def main():
    blend, details, out = args()[:3]
    bpy.ops.wm.open_mainfile(filepath=blend)
    D = json.load(open(details))
    model = json.load(open(D["model_json"]))
    frames = wall_frames(model)
    c = coll("Details")
    sid = D.get("siding", {})
    trim = D.get("trim_color", (0.85, 0.85, 0.82))
    mats = {
        "trim": mat("Trim (white)", trim, 0.5),
        "frame": mat("Window frames", D.get("window_frame_color", trim), 0.5),
        "soffit": mat("Soffit", D.get("soffit_color", (0.8, 0.8, 0.77)), 0.6),
        "fascia": mat("Fascia", D.get("fascia_color", trim), 0.5),
        "corner": mat("Corner boards", D.get("corner_board_color", trim), 0.6),
        "gutter": mat("Gutter", D.get("gutter_color", (0.88, 0.88, 0.86)), 0.35, 0.2),
        "glass": mat("Glass", (0.03, 0.05, 0.07), 0.05, 0.0),
        "door": mat("Door", D.get("door_color", (0.82, 0.82, 0.8)), 0.45),
        "garage": mat("Garage door", D.get("garage_door_color", (0.9, 0.9, 0.88)), 0.4),
        "shadow": mat("Joint shadow", (0.25, 0.25, 0.25), 0.8),
        "deck": mat("Deck (painted)", D.get("deck_color", (0.07, 0.12, 0.09)), 0.75),
        "concrete": mat("Concrete", D.get("concrete_color", (0.55, 0.55, 0.53)), 0.95),
        "foundation": mat("Foundation", D.get("foundation", {}).get("color", (0.55, 0.55, 0.53)), 0.95),
        "brick": brick_material(D.get("brick_color", (0.20, 0.055, 0.04))),
        "wood": mat("Weathered wood", (0.28, 0.21, 0.15), 0.9),
        "stone": mat("Cast stone", (0.62, 0.60, 0.55), 0.8),
        "vinyl": mat("Vinyl (white)", (0.80, 0.80, 0.78), 0.5),
        "metal": mat("Hardware (nickel)", (0.55, 0.55, 0.55), 0.35, 0.8),
        "cap": mat("Ridge cap", D.get("ridge_cap_color", (0.12, 0.12, 0.13)), 0.9),
        "vent": mat("Roof vent", (0.1, 0.1, 0.11), 0.6, 0.3),
        "fixture": mat("Light fixture (black)", (0.02, 0.02, 0.02), 0.4, 0.5),
    }
    # siding on the existing walls
    sm = siding_material(sid.get("color", (0.42, 0.42, 0.30)), sid.get("exposure", 0.1803), sid.get("style", "lap"),
                         sid.get("spacing", 0.203), sid.get("groove", 0.012))
    for ob in bpy.data.collections["Walls"].objects:
        ob.data.materials.clear()
        ob.data.materials.append(sm)
    mats["siding"] = sm
    rf = D.get("roof", {})
    if rf.get("courses", True):
        slope = rf.get("slope") or max(f["pitch_rise_per_12"] for f in model["facets"]) / 12.0
        rm = shingle_material(rf.get("color", (0.17, 0.17, 0.18)), rf.get("exposure", 0.1429), slope)
        for ob in bpy.data.collections["Roof facets"].objects:
            ob.data.materials.clear()
            ob.data.materials.append(rm)
    tag()
    add_foundation(frames, D.get("foundation", {}), c, mats, D.get("openings", []))
    add_trim(model, frames, c, mats, D.get("fascia_height", 0.2), D.get("gutters", True), D.get("soffits", True))
    add_extra_walls(D, frames, c, mats)
    for i, o in enumerate(D.get("openings", [])):
        tag(f"openings[{i}]", o)
        add_opening(o, frames, c, mats)
    add_roof_extras(model, D, c, mats)
    add_skylights_chimneys(model, D, c, mats)
    add_beams(model, D, c, mats)
    add_beam_ends(model, D, c, mats)
    tag()
    if D.get("corner_boards", True):
        add_corner_boards(model, frames, D.get("foundation", {}), c, mats)
    add_wall_boxes(D, frames, c, mats)
    add_lights_and_text(D, frames, c, mats)
    for i, dk in enumerate(D.get("decks", [])):
        tag(f"decks[{i}]", dk)
        add_deck(dk, c, mats, i)
    for i, st in enumerate(D.get("stairs", [])):
        tag(f"stairs[{i}]", st)
        add_stairs(st, c, mats, i)
    for i, ce in enumerate(D.get("ceilings", [])):
        tag(f"ceilings[{i}]", ce)
        pts = [(x, y, ce["z"]) for x, y in ce["polygon"]]
        mesh(f"porch ceiling {i}", pts, [list(range(len(pts)))], c, pick(ce, mats, "soffit", f"ceiling {i}", 0.6))
    for i, b in enumerate(D.get("boxes", [])):
        tag(f"boxes[{i}]", b)
        box(b["name"], b["min"], b["max"], c, pick(b, mats, "trim", b["name"], 0.7))
    for i, pn in enumerate(D.get("panels", [])):
        tag(f"panels[{i}]", pn)
        pts = [tuple(p) for p in pn["polygon"]]
        mesh(pn.get("name", "panel"), pts, [list(range(len(pts)))], c, pick(pn, mats, "siding", pn.get("name", "panel"), 0.8))
    add_downspouts(model, D, frames, c, mats)
    tag()
    notes, n_lab, n_cav = details_notes(D)
    txt = bpy.data.texts.get("Details notes") or bpy.data.texts.new("Details notes")
    txt.clear()
    txt.write(notes)
    txt.use_fake_user = True                    # kept in the saved file with no other user
    print(f"details notes: {n_lab} labelled entries, {n_cav} caveats (not fully measured) -> text 'Details notes'")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("details added:", len(c.objects), "objects ->", out)


main()
