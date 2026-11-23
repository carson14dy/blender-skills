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
  "roof": {"exposure": 0.1429, "color": [0.17, 0.17, 0.18], "label": "...",   # shingle course lines
           "underside": true, "underside_color": null},
            # underside: the roof sheet seen from BELOW (under a deep rake / eave overhang) renders as a light soffit
            # (underside_color, default soffit_color) instead of bare dark shingle - a Mix Shader on the roof material
            # switched by the viewer being under the plane (see underside_soffit); false keeps the bare sheet
            # fit "color" to an orthophoto at a few points per slope (sun- and shade-side planes) with a top-down
            # render under the ortho's sun: a grey sky and AgX shift a neutral base colour bluer, so a roof that
            # reads warm brown-grey from above needs a clearly warm base (G-B gap ~20 in 8-bit sRGB)
  "ridge_cap_color": [r,g,b],              # shingle cap folded over every ridge / hip (automatic, 0.30 m wide,
            # 0.03 m proud of both planes); an orthophoto rarely shows the cap darker than the field by more than ~10%
  "trim_color": [0.85, 0.85, 0.82], "deck_color": [0.07, 0.12, 0.09],
  "window_frame_color": [80, 68, 52],                                  # window/slider frames (default: trim)
  "concrete_color": [215, 207, 192],                                   # material "concrete" (walls, boxes, ...)
  "fascia_height": 0.2, "gutters": true, "soffits": true,
            # soffits: true / false, or {"enabled": true, "skip_facets": ["F3"], "label": "..."}: eaves of the facets
            # listed get no horizontal (boxed) soffit at the fascia bottom; the roof sheet's underside (see
            # roof.underside) is then the visible soffit, following the slope (an open / raked eave). Check it on a
            # low street photo: under a boxed soffit the wall is hidden up to well below the fascia, under a raked
            # one it shows right up to the fascia band (the underside is seen nearly edge-on)
            # gutters: true / false, or {"position": "outside" | "inside", "depth": 0.13, "height": 0.12, "trough": null}.
            # "trough": 0..1 - the gutter's top face is the open trough (the inside of the channel, in its own shade
            # and debris), seen from above darker than the paint: that factor x the gutter colour (material "Gutter
            # trough", matte); null keeps one painted box. Check it on an orthophoto: a painted box top reads as a
            # bright line along every eave, brighter than the driveway, where real gutters read darker
            # "outside" (default): the eave line is the shingle drip edge and the gutter hangs outside it. "inside": the
            # eave line was fitted to a LiDAR / ortho outline, whose outermost surface IS the gutter lip (check: no
            # returns at gutter height within ~0.2 m outside the fitted eave), so the gutter's front face lies on the eave
            # line, its top follows the roof plane 8 mm above it (the white band an orthophoto shows along the eave) and
            # the fascia and soffit move in by `depth`; the roof outline (and every measured number) is unchanged
  "foundation": {"default_reveal": 0.25, "walls": {"M:-u": 0.54, "M:+v": 0.62}, "color": [r,g,b],   # siding-bottom z per wall
                 "skip": ["U", "M:+v"]},       # wings / walls with no foundation strip (an upper storey standing on a lower one)
  "openings": [ {"wall": "M:-u", "u": 9.98, "sill_z": 1.55, "width": 1.56, "height": 1.52,
                 "kind": "window|slider|door|garage|egress|void", "label": "...",
                 "leaf_color": [r,g,b], "frame_color": [r,g,b], "mullions": [0.25, 0.75], "mullion_width": 0.04,
                 "panels": [rows, cols], "style": "raised|ribbed", "rib_spacing": 0.1} ],   # u = distance from wall start
                 # leaf_color: door colour; mullions: vertical bars at these width fractions (default: one at 0.5
                 # for a 2-lite slider; a window wall of n units = one opening with n-1 mullions); panels: raised panels
                 # on a door / garage door (default 4x8 garage, 3x2 door); style "ribbed": a garage door with narrow
                 # horizontal grooves every rib_spacing m and no raised panels
                 # "frame": frame bar width (default 0.07). By default sill_z / width / height are the glazed opening
                 # and the frame bars sit OUTSIDE it (the visible unit is 2 x frame wider and taller); "frame_inside":
                 # true makes them the OUTER frame size - what a photo measures from sill to head and jamb to jamb -
                 # with the bars inside it (doors / garage doors: head and jambs only) and mullion fractions taken
                 # of that outer width
                 # doors only: "sidelight": {"side": "start" | "end", "width": 0.36, "color": [r,g,b]} - a fixed panel
                 # beside the leaf (toward the wall start / end) in the same frame (the leaf's jamb is the mullion; an
                 # outer jamb and the head carry on over it); default colour the window glass.
                 # "storm_door": {"color": [r,g,b], "stile": 0.12, "rail": 0.15, "kick": 0.25, "offset": 0.04,
                 # "depth": 0.03} - an open storm-door frame (stiles, top rail, kick panel) standing `offset` m proud
                 # of the wall over the leaf, so the leaf colour shows through its glazing
                 # A corner board that an opening's frame overlaps (a door set hard against a wall corner) is cut
                 # around the opening: the door casing takes over the corner there.
                 # kind "void": a rectangle (u +- width / 2, sill_z .. sill_z + height) CUT OUT of the model wall's face
                 # - an open porch recess or a passage where the wing outline keeps a wall the house does not have
                 # there. No leaf, frame or trim; the wall object ("Wall <wing> <side>") is rebuilt as vertical strips
                 # round the hole, the foundation strip and corner boards are cut exactly to it, and the report deducts
                 # it from the siding like any opening (width x height). The parts of the wall left above / below it
                 # stay (a header over the opening, the foundation under a porch floor). Close the recess with
                 # "extra_walls" (its back / end walls) and a "ceilings" entry. Model walls only (not extra_walls)
  "decks": [ {"polygon": [[x,y],...], "top_z": 0.95, "rail_edges": [[i,j],...], "rail_gaps": [[x0,y0,x1,y1]],
              "rail_height": 0.9, "post_spacing": 2.0, "post_edges": [i,...],   # post_edges: edge i = vertex i -> i+1
              "rail_style": "balusters|screen|panel|none",   # screen = closely spaced vertical boards under a flat cap rail
              "picket_width": 0.11, "picket_gap": 0.025, "rail_post_spacing": 0,
              "skirt": 0.0,                              # screen boards carried this far down over the rim / header
              # rail_edges items may also be {"edge": [i, j], "style": "screen", "skirt": 0.9} (per-edge overrides);
              # "extend_to": [k, l] (another edge of this polygon) or [[x,y],[x,y]] carries the run on along its own
              # line to where it meets that line (the nearer end moves, at most 1.5 m): a fence across an open slot
              # that ends ON the outer fence, the two sharing one post at the junction (no gap, no stub end); its cap
              # is mitred onto the other rail's near cap face and its boards stop at the post face (no overlapping
              # caps: two caps flat on each other z-fight);
              # rail_style "panel": a solid board panel under a flat cap (stair sides closed with boards);
              # a per-edge "label" (e.g. one guard measured +-0.1 m, a skirt whose extent is assumed) goes on that
              # run's rail / skirt / post objects (details key "decks[i].rail_edges[k]") instead of the deck's label,
              # and into the Details notes, flagged like any entry label when it carries a caveat word
              "rail_color": [r,g,b], "board_color": [r,g,b], "rim_depth": 0.24, "rim_color": [r,g,b]} ],
              # rim_depth: depth of the rim joist / header board below the boards on every edge (a deep header
              # over a garage door is a rim of 0.8-0.9 m). A concave polygon (a notch around a light well) is fine.
              # "board_ends": "rim" (default) | "boards": the 0.04 m end faces of the board slab, flush over the rim's
              # outer face, take the rim colour (a fascia covering rim and board ends) - in a contrasting board colour
              # they show as a thin line along every edge, through every picket gap; "boards" keeps the board colour
  "stairs": [ {"top": [x,y], "dir": [dx,dy], "width": 1.0, "top_z": 0.95, "bottom_z": 0.2, "risers": 4,
               "length": 2.1,                             # horizontal run top -> bottom (default run 0.27 per tread)
               "rails": ["left", "right"],                # sloped handrails (left/right looking down the stairs)
               "rail_style": "balusters" | {"left": "screen", "right": "panel"},   # as for decks
               "skirt": 0.0,                              # screen boards / panels carried this far below the sloped
                                                          # rail line (a stair side closed down to the ground); with
                                                          # skirt > 0 a screen / panel side hangs outside the stringer
                                                          # (board inner face 0.01 m out from it), cap centred over it
               "foot_on_deck": null,                      # true / false; null: true when the foot lands on a deck
                                                          # (polygon within 0.15 m, top_z = bottom_z +-0.03): the
                                                          # stringers are then "stair i carriage", which the site
                                                          # grounding step does not snap down to the terrain
               "rail_color": [r,g,b], "tread_color": [r,g,b], "stringer_color": [r,g,b]} ],
  "ceilings": [ {"polygon": [[x,y],...], "z": 3.19, "color": [r,g,b]} ],   # porch ceilings, soffits under cantilevers
              # Wall points: wherever a point lies ON a wall line - ceiling / deck polygon vertices, beam p0 / p1,
              # downspout xy and leader path points - it may be given as {"wall": "M:-v", "u": 2.5, "offset": 0.06,
              # "z": 2.4} instead of [x,y(,z)]: u along the wall from its start ("end" = the wall's far end, negative =
              # back from the far end), offset outward from the wall face, z optional (a 3-D point). The point then
              # follows the wall when model.json moves it (a re-fitted or re-measured wall line), so a soffit edge or a
              # rim beam never floats off its wall. A ceiling whose polygon has (near) zero area is skipped: a soffit
              # strip between an upper wall and the flush wall below it appears only once the upper wall moves out
  "roof_wells": [ {"polygon": [[x,y],...], "color": [r,g,b], "material": "siding", "thickness": 0.1,
                   "bottom_z": null, "label": "..."} ],
              # liner walls round a roof opening (open trellis bay, light well, courtyard): one vertical wall per polygon
              # edge from the roof plane over the opening (the highest facet there, holes ignored) down to the roof
              # surface below it (or bottom_z where no roof lies below), its face on the edge line and `thickness` m
              # deep away from the opening. Without them an opening in an upper roof over a lower roof is open on
              # every side under the upper roof, so low sun lights the lower roof through it, while orthophotos show
              # such a bay as a dark slot
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
              # overrides the tip's distance outside the edge line (0.02: a purlin end flush with the fascia). Check
              # each tip against LiDAR: a projecting end is hit at beam level in a +-0.2 m window beyond the edge about
              # as often as the roof edge itself; ground-only returns there mean it does not project. A ridge beam
              # running out past a prow or hip end (not square to any rake) is a "beams" entry with 3-D p0 / p1 instead
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
                 # are automatic (see ridge_cap_color)
  "skylights": [ {"xy": [x,y], "size": [across, along_slope], "curb": 0.15, "label": "...",   # on the top facet at xy
                  "curb_color": [r,g,b], "glass_color": [r,g,b], "glass_roughness": 0.2, "frame": 0.05, "dome": 0.0} ],
                 # curb: height of the curb top along the roof normal; frame: curb rim left visible around the glazing;
                 # dome > 0: domed / hipped glazing rising this far above the curb top at its centre (read the rim and
                 # crown heights off the LiDAR residuals to the roof plane). Default colours: trim curb, window glass
  "chimneys": [ {"center": [x,y], "size": [a,b], "azimuth": deg_of_a, "top_z": 7.9, "material": "siding|brick|stone",
                 "color": [r,g,b], "label": "...",
                 "shoulder": {"z": 7.25, "size": [a,b]},      # wider lower chase up to z, the stack above it
                 "cap": {"color": [r,g,b], "material": "trim", "overhang": 0.05, "thickness": 0.08},
                 "chase": {"wall": "M:-u", "bottom_z": -1.9 | "grade", "grade_below": 0.3, "projection": null,
                           "u": [u0, u1], "top_z": null, "material": null, "label": "..."}} ],
                 # chimney from below the roof to top_z (cap included); default cap: metal.
                 # chase: an EXTERIOR chase on the outside of a wall (an outside fireplace chimney) from bottom_z up to
                 # 0.02 m under the shoulder top (inside it: no coplanar top faces; no shoulder: the cap's underside),
                 # so the masonry runs from the ground through the eave to the chimney: plan = the wall face (0.05 m
                 # into the wall, no slit) out to `projection` m outside it (default: the shoulder's / stack's
                 # outermost corner + 3 mm), along the wall over u0..u1 (default: the shoulder's / stack's extent
                 # along it, 3 mm in at each end so the end faces are not coplanar with the shoulder's). "wall"
                 # defaults to the model wall nearest the centre.
                 # bottom_z "grade": the lowest ground under the chase footprint (+0.3 m out) from "ground_surface"
                 # (details key, or the chase's own; default <model.json dir>/data/ground_surface.npz) minus
                 # grade_below, so the base is buried, never floating; the site step's terrain covers the rest.
                 # The opaque chase is what the roof overhang wraps around (the roof stops at its faces); openings
                 # on that wall behind the chase are reported (WARNING) - move them off it
  "flashing": true | false | {"color": [r,g,b], "width": 0.1, "height": 0.12, "label": "..."},
            # metal flashing (apron on the roof + upstand on the solid's face) along every model.json roof edge the
            # roof fit tagged "penetration" (a chimney through the roof); default on when such edges exist, metal grey
  "stone": {"colors": [[r,g,b], [r,g,b]], "course": 0.17, "length": 0.55, "joint": 0.01, "joint_color": [r,g,b],
            "label": "..."},
            # procedural coursed stone for material "stone" (chimneys, chases, boxes): each stone a random tone
            # between the two colours, joints recessed (see stone_material); without it "stone" is a flat cast stone
  "extra_walls": [ {"name": "GAR:-v", "bottom": [[x,y,z],[x,y,z]], "top_z": -0.55, "bearing": 214,
                    "material": "concrete", "color": [r,g,b], "thickness": 0.2} ],
                 # presentation-only walls (e.g. a garage under a deck) that openings can name like model walls;
                 # thickness > 0 builds a solid wall extruded inward (away from the bearing)
  "corner_boards": true,     # or {"enabled": true, "skip": ["M:-u:end", "G:+v:start"]}: no board at those wall ends
                             # (a wall carried on flush by an extra wall, so the model wall's end is no real corner)
  "lights": [ {"wall": "M:-v", "u": 5.4, "z": 2.9, "style": "shade|lantern", "color": [r,g,b], "label": "..."} ],
             # "shade" (default): back plate, arm and a flat square shade under it, z = plate centre, colour default
             #   black ("Light fixture (black)"); "lantern": a coach lantern - back plate, short arm and a box body
             #   (cap, corner posts, bottom, glass) with z = body centre: "size": [width, height, depth] (default
             #   0.2, 0.36, 0.18), "arm": body offset from the plate (0.05), "color": body, "glass_color": glass
             #   (default the window glass), "emission": glass Emission Strength (default 0 = unlit; ~0.05-0.2 is a dim
             #   lamp: a sunlit white wall renders ~1), "emission_color" (default warm (255,190,120))
  "text": [ {"wall": "G:+u", "u": 0.5, "z": 0.9, "text": "12", "size": 0.16, "material": "fixture", "color": [r,g,b],
             "plate": [w, h], "plate_color": [r,g,b]} ],  # "\n" stacks lines; or "xy": [x,y] + "azimuth": facing deg
                                                          # instead of wall/u (a plaque on a pier or post)
  "caveats": ["what is not measured, and by how much it may be off", ...],
  "color_labels": {"trim_color": "photo #3 sunlit fascia (220,217,195)", ...}
              # provenance of top-level colours (trim_color, fascia_color, soffit_color, ...): listed in the
              # "Details notes" text like entry labels (and flagged when they carry a caveat word)
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


def underside_soffit(m, rgb, rough=0.6):
    """Give a roof material a light soffit BSDF on its UNDERSIDE (the bare roof sheet seen from below, under a deep
    rake or eave overhang, reads as a dark slot otherwise; real rakes show pale soffit boards / painted outlookers).

    A Mix Shader picks the soffit BSDF where the viewer is below the roof plane. The factor is the Geometry node's
    True Normal z < 0: Cycles turns the true normal toward the viewer, so it points down exactly when the underside is
    seen, whatever the face winding (the same as Geometry.Backfacing for up-facing facets, which build_model writes).
    Bump and shingle courses stay on the top side only. Idempotent: a material already patched is left alone."""
    nt = m.node_tree
    if nt.nodes.get("Roof underside"):
        return m
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)
    top = out.inputs["Surface"].links[0].from_socket if out and out.inputs["Surface"].links else None
    if top is None:
        return m
    rgb = col(rgb)
    sb = nt.nodes.new("ShaderNodeBsdfPrincipled"); sb.name = sb.label = "Roof underside"
    sb.inputs["Base Color"].default_value = (*rgb, 1)
    sb.inputs["Roughness"].default_value = rough
    geo = nt.nodes.new("ShaderNodeNewGeometry"); geo.name = "Underside geometry"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.inputs[1].default_value = 0.0
    lt.name = lt.label = "Underside factor (backfacing)"
    mix = nt.nodes.new("ShaderNodeMixShader"); mix.name = mix.label = "Roof top / underside"
    nt.links.new(geo.outputs["True Normal"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], lt.inputs[0])
    nt.links.new(lt.outputs[0], mix.inputs["Fac"])
    nt.links.new(top, mix.inputs[1])                      # Fac 0: top side (shingles)
    nt.links.new(sb.outputs["BSDF"], mix.inputs[2])       # Fac 1: underside (soffit)
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
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


STONE_DEFAULT = {"colors": [[196, 176, 140], [228, 210, 172]], "course": 0.17, "length": 0.55, "joint": 0.01}


def stone_material(colors=STONE_DEFAULT["colors"], course=0.17, length=0.55, joint=0.01, joint_color=None,
                   rough=0.9, warp=0.012, mottle=0.12, name="Stone (coursed)"):
    """Coursed stone (sandstone ashlar / ledgestone) for chimneys, chases and piers, with no UVs.

    Stones about `length` m long in courses about `course` m high; each stone takes a random tone between colors[0]
    and colors[1] (8-bit sRGB or linear); mortar joints `joint` m wide in joint_color (default 0.72 x the darker
    stone, 40 % greyed) are recessed by a bump. So the bond does not read as brick: course heights swell and shrink
    by +-25 % (a smooth monotonic warp of the height), and every course gets its own random stone length
    (0.75-1.25 x) and joint offset; joints wobble by up to `warp` m (low-frequency noise) and a fine noise mottles
    each stone by +-mottle.
    Mapping: vertical faces use (distance along the face's own tangent N x Z, z), so a chase at any bearing gets
    level courses; faces within 60 deg of horizontal (caps, washes, shoulders) use (x, y)."""
    c0, c1 = col(colors[0]), col(colors[1])
    if joint_color is not None:
        jc = col(joint_color)
    else:                       # sandstone mortar: a little darker and greyer than the stone, not a dark brick joint
        dk = [0.72 * min(a, b) for a, b in zip(c0, c1)]
        g = sum(dk) / 3
        jc = tuple(0.6 * v + 0.4 * g for v in dk)
    mid = tuple((a + b) / 2 for a, b in zip(c0, c1))
    m = mat(name, mid, rough)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")

    def node(kind, op=None, **inputs):
        n_ = nt.nodes.new(kind)
        if op:
            n_.operation = op
        for k, v in inputs.items():
            n_.inputs[k].default_value = v
        return n_
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sp, sn = nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sp.inputs[0])
    nt.links.new(geo.outputs["Normal"], sn.inputs[0])
    cr = node("ShaderNodeVectorMath", "CROSS_PRODUCT")
    cr.inputs[1].default_value = (0.0, 0.0, 1.0)
    nz = node("ShaderNodeVectorMath", "NORMALIZE")
    dot = node("ShaderNodeVectorMath", "DOT_PRODUCT")
    nt.links.new(geo.outputs["Normal"], cr.inputs[0])
    nt.links.new(cr.outputs["Vector"], nz.inputs[0])
    nt.links.new(nz.outputs["Vector"], dot.inputs[0])
    nt.links.new(geo.outputs["Position"], dot.inputs[1])
    vert, flat = nt.nodes.new("ShaderNodeCombineXYZ"), nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dot.outputs["Value"], vert.inputs["X"])
    nt.links.new(sp.outputs["Z"], vert.inputs["Y"])
    nt.links.new(sp.outputs["X"], flat.inputs["X"])
    nt.links.new(sp.outputs["Y"], flat.inputs["Y"])
    ab = node("ShaderNodeMath", "ABSOLUTE")
    nt.links.new(sn.outputs["Z"], ab.inputs[0])
    fl = node("ShaderNodeMath", "GREATER_THAN")
    fl.inputs[1].default_value = 0.5                                  # |N.z| > 0.5: within 60 deg of horizontal
    nt.links.new(ab.outputs[0], fl.inputs[0])
    inv = node("ShaderNodeMath", "SUBTRACT")
    inv.inputs[0].default_value = 1.0
    nt.links.new(fl.outputs[0], inv.inputs[1])
    s_v, s_f = node("ShaderNodeVectorMath", "SCALE"), node("ShaderNodeVectorMath", "SCALE")
    nt.links.new(vert.outputs[0], s_v.inputs[0]); nt.links.new(inv.outputs[0], s_v.inputs["Scale"])
    nt.links.new(flat.outputs[0], s_f.inputs[0]); nt.links.new(fl.outputs[0], s_f.inputs["Scale"])
    uv = node("ShaderNodeVectorMath", "ADD")
    nt.links.new(s_v.outputs["Vector"], uv.inputs[0]); nt.links.new(s_f.outputs["Vector"], uv.inputs[1])
    # joint wobble: low-frequency noise (centred) x warp
    wn = node("ShaderNodeTexNoise", Scale=1.5, Detail=2.0)
    nt.links.new(geo.outputs["Position"], wn.inputs["Vector"])
    wc = node("ShaderNodeVectorMath", "SUBTRACT")
    wc.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(wn.outputs["Color"], wc.inputs[0])
    ws = node("ShaderNodeVectorMath", "SCALE")
    ws.inputs["Scale"].default_value = 2.0 * warp
    nt.links.new(wc.outputs["Vector"], ws.inputs[0])
    uvw = node("ShaderNodeVectorMath", "ADD")
    nt.links.new(uv.outputs["Vector"], uvw.inputs[0]); nt.links.new(ws.outputs["Vector"], uvw.inputs[1])
    sw_ = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uvw.outputs["Vector"], sw_.inputs[0])
    # course heights: t' = t + a sin(2 pi t / P), a 2 pi / P = 0.25 (monotonic: courses 0.75-1.25 x `course`)
    period = 6.0 * course
    ph = node("ShaderNodeMath", "MULTIPLY")
    ph.inputs[1].default_value = 2 * math.pi / period
    nt.links.new(sw_.outputs["Y"], ph.inputs[0])
    sn_ = node("ShaderNodeMath", "SINE")
    nt.links.new(ph.outputs[0], sn_.inputs[0])
    am = node("ShaderNodeMath", "MULTIPLY")
    am.inputs[1].default_value = 0.25 * period / (2 * math.pi)
    nt.links.new(sn_.outputs[0], am.inputs[0])
    tw = node("ShaderNodeMath", "ADD")
    nt.links.new(sw_.outputs["Y"], tw.inputs[0]); nt.links.new(am.outputs[0], tw.inputs[1])
    # per-course random joint offset and stone length (white noise of the course index)
    rq = node("ShaderNodeMath", "DIVIDE")
    rq.inputs[1].default_value = course
    nt.links.new(tw.outputs[0], rq.inputs[0])
    row = node("ShaderNodeMath", "FLOOR")
    nt.links.new(rq.outputs[0], row.inputs[0])
    r1, r2 = nt.nodes.new("ShaderNodeTexWhiteNoise"), nt.nodes.new("ShaderNodeTexWhiteNoise")
    r1.noise_dimensions = r2.noise_dimensions = "1D"
    r2o = node("ShaderNodeMath", "ADD")
    r2o.inputs[1].default_value = 17.31
    nt.links.new(row.outputs[0], r1.inputs["W"])
    nt.links.new(row.outputs[0], r2o.inputs[0]); nt.links.new(r2o.outputs[0], r2.inputs["W"])
    lf = node("ShaderNodeMapRange")
    lf.inputs["To Min"].default_value, lf.inputs["To Max"].default_value = 0.75, 1.25
    nt.links.new(r2.outputs["Value"], lf.inputs["Value"])
    sl_ = node("ShaderNodeMath", "MULTIPLY")
    nt.links.new(sw_.outputs["X"], sl_.inputs[0]); nt.links.new(lf.outputs["Result"], sl_.inputs[1])
    so = node("ShaderNodeMath", "MULTIPLY_ADD")
    so.inputs[1].default_value = length
    nt.links.new(r1.outputs["Value"], so.inputs[0]); nt.links.new(sl_.outputs[0], so.inputs[2])
    st_ = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(so.outputs[0], st_.inputs["X"]); nt.links.new(tw.outputs[0], st_.inputs["Y"])
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset, br.offset_frequency, br.squash, br.squash_frequency = 0.0, 2, 1.0, 2
    br.inputs["Color1"].default_value = (*c0, 1)
    br.inputs["Color2"].default_value = (*c1, 1)
    br.inputs["Mortar"].default_value = (*jc, 1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = joint
    br.inputs["Mortar Smooth"].default_value = 0.15
    br.inputs["Bias"].default_value = 0.0
    br.inputs["Brick Width"].default_value = length
    br.inputs["Row Height"].default_value = course
    nt.links.new(st_.outputs["Vector"], br.inputs["Vector"])
    # mottling inside each stone: fine noise mapped to 1 +- mottle, multiplied into the colour
    mn = node("ShaderNodeTexNoise", Scale=9.0, Detail=6.0)
    nt.links.new(geo.outputs["Position"], mn.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 1.0 - mottle
    mr.inputs["To Max"].default_value = 1.0 + mottle
    nt.links.new(mn.outputs["Fac"], mr.inputs["Value"])
    mo = node("ShaderNodeVectorMath", "SCALE")
    nt.links.new(br.outputs["Color"], mo.inputs[0]); nt.links.new(mr.outputs["Result"], mo.inputs["Scale"])
    nt.links.new(mo.outputs["Vector"], b.inputs["Base Color"])
    jinv = node("ShaderNodeMath", "SUBTRACT")                          # mortar (Fac 1) recessed
    jinv.inputs[0].default_value = 1.0
    nt.links.new(br.outputs["Fac"], jinv.inputs[1])
    bump = node("ShaderNodeBump", Strength=0.6)
    nt.links.new(jinv.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    m["stone_colors"] = [list(c0), list(c1)]                           # linear range, for checks and exports
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
             "wall_boxes", "downspouts", "roof_vents", "skylights", "chimneys", "lights", "text", "roof_wells")


def details_notes(D):
    """(text, n_labelled, n_flagged): every labelled entry of details.json, the ones not fully measured (a caveat
    word in the label) repeated, and the top-level "caveats" strings."""
    rows, flagged = [], []
    for k, v in D.items():
        if isinstance(v, dict) and v.get("label"):
            rows.append((k, str(v["label"])))
    for k, lab in (D.get("color_labels") or {}).items():
        rows.append((k, str(lab)))
    for k in LIST_KEYS:
        for i, e in enumerate(D.get(k, []) or []):
            lab = (e.get("label") or e.get("name")) if isinstance(e, dict) else None
            if lab:
                rows.append((f"{k}[{i}]", str(lab)))
            if k == "decks" and isinstance(e, dict):        # per-edge rail labels (see "rail_edges")
                for j, re_ in enumerate(e.get("rail_edges", []) or []):
                    if isinstance(re_, dict) and re_.get("label"):
                        rows.append((f"decks[{i}].rail_edges[{j}]", str(re_["label"])))
            if k == "chimneys" and isinstance(e, dict) and isinstance(e.get("chase"), dict) and e["chase"].get("label"):
                rows.append((f"chimneys[{i}].chase", str(e["chase"]["label"])))
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


def wall_point(p, frames):
    """A point from details.json: [x, y] / [x, y, z] as given, or a wall point {"wall", "u", "offset", "z"} resolved
    on the current wall line (u from the wall start; "end" or a negative u counts from the far end; offset outward
    from the face). Returns a list of 2 or 3 floats (3 when the wall point carries "z")."""
    if not isinstance(p, dict):
        return [float(v) for v in p]
    if p.get("wall") not in frames:
        raise KeyError(f"wall point names an unknown wall {p.get('wall')!r} (known: {sorted(frames)})")
    a, d, n, L, _ = frames[p["wall"]]
    u = p.get("u", 0.0)
    u = L if u == "end" else (L + float(u) if float(u) < 0 else float(u))
    q = a + d * u + n * float(p.get("offset", 0.0))
    return [q.x, q.y] + ([float(p["z"])] if p.get("z") is not None else [])


def wall_points(pts, frames):
    return [wall_point(p, frames) for p in pts]


def add_opening(o, frames, c, mats):
    kind = o.get("kind", "window")
    if kind == "void":           # cut out of the wall's face by cut_wall_voids: nothing to add
        return
    a, d, n, L, _ = frames[o["wall"]]
    w, h = o["width"], o["height"]
    u0 = o["u"] - w / 2
    sill = o["sill_z"]
    T, D = o.get("frame", 0.07), 0.04          # frame width, frame projection
    W_out = w                                  # outer width the mullion fractions refer to (frame_inside)
    if o.get("frame_inside"):
        # sill_z / width / height are the OUTER frame (what a photo measures: sill to head, jamb to jamb), so the
        # frame bars sit inside that rectangle and the glazing / leaf shrinks by the frame width on each side.
        # A door or garage door has no sill bar: only the head and jambs come off its height and width.
        u0 += T
        w -= 2 * T
        if kind in ("door", "garage"):
            h -= T
        else:
            sill += T
            h -= 2 * T
        if w <= 0 or h <= 0:
            raise ValueError(f"opening {o.get('label', kind)!r}: frame {T} m leaves no glazing with frame_inside")
    base = a + d * u0 + Vector((0, 0, sill))
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
    for fr in mull:   # meeting rails / mullions (fractions of the outer width with frame_inside)
        x = W_out * fr - T if o.get("frame_inside") else w * fr
        oriented_box(f"{name} mullion", base + d * (x - mw / 2), d * mw, n * 0.02, Vector((0, 0, h)), c, fm)
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
        sl = o.get("sidelight")
        if sl:    # fixed panel beside the leaf in the same frame: the leaf's jamb is the mullion
            sw = float(sl.get("width", 0.36))
            s0 = -T - sw if sl.get("side", "end") == "start" else w + T        # u of the panel from the leaf start
            pm = mat(f"Sidelight ({name})", sl["color"], 0.3) if sl.get("color") else mats["glass"]
            oriented_box(f"{name} sidelight", base + d * s0 + n * 0.005, d * sw, n * 0.01, Vector((0, 0, h)), c, pm)
            jo = s0 - T if s0 < 0 else s0 + sw                                  # outer jamb beyond the panel
            oriented_box(f"{name} sidelight jamb", base + d * jo, d * T, n * D, Vector((0, 0, h)), c, fm)
            hd0 = min(jo, s0)
            oriented_box(f"{name} sidelight head", base + d * hd0 + Vector((0, 0, h)), d * (sw + T), n * D,
                         Vector((0, 0, T)), c, fm)
        sd = o.get("storm_door")
        if sd:    # open storm-door frame standing proud over the leaf (its glazing left open: the leaf shows through)
            sm = mat(f"Storm door ({name})", sd.get("color", (235, 235, 230)), 0.45)
            st, rl, kk = float(sd.get("stile", 0.12)), float(sd.get("rail", 0.15)), float(sd.get("kick", 0.25))
            off, dp = float(sd.get("offset", 0.04)), float(sd.get("depth", 0.03))
            q = base + n * off
            parts = [(q, d * st, n * dp, Vector((0, 0, h))),                                   # stiles
                     (q + d * (w - st), d * st, n * dp, Vector((0, 0, h))),
                     (q + d * st + Vector((0, 0, h - rl)), d * (w - 2 * st), n * dp, Vector((0, 0, rl))),   # top rail
                     (q + d * st, d * (w - 2 * st), n * dp, Vector((0, 0, kk)))]                # kick panel
            boxes_mesh(f"{name} storm door", parts, c, sm)
            oriented_box(f"{name} storm handle", q + d * (w * (0.9 if hs else 0.1) - 0.02) + n * dp + Vector((0, 0, 0.95)),
                         d * 0.04, n * 0.04, Vector((0, 0, 0.12)), c, mats["metal"])


def opening_extent(o):
    """(u_lo, u_hi, z_lo, z_hi) of an opening's visible unit on its wall: glazing / leaf plus frame bars (outside it by
    default, inside with frame_inside; doors and garage doors have no sill bar) plus a door's sidelight and its jamb."""
    T, w, h, sill = o.get("frame", 0.07), o["width"], o["height"], o["sill_z"]
    door = o.get("kind", "window") in ("door", "garage")
    if o.get("kind") == "void":                       # a hole in the wall: exactly its rectangle, no frame
        return o["u"] - w / 2, o["u"] + w / 2, sill, sill + h
    if o.get("frame_inside"):
        u_lo, u_hi, z_lo, z_hi = o["u"] - w / 2, o["u"] + w / 2, sill, sill + h
    else:
        u_lo, u_hi = o["u"] - w / 2 - T, o["u"] + w / 2 + T
        z_lo, z_hi = sill - (0 if door else T), sill + h + T
    sl = o.get("sidelight") if o.get("kind") == "door" else None
    if sl:
        extra = float(sl.get("width", 0.36)) + T
        if sl.get("side", "end") == "start":
            u_lo -= extra
        else:
            u_hi += extra
    return u_lo, u_hi, z_lo, z_hi


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


def gutter_options(gutters):
    """(enabled, inside, depth, height) from details.json "gutters" (bool or dict, see the docstring)."""
    if isinstance(gutters, dict):
        pos = gutters.get("position", "outside")
        if pos not in ("outside", "inside"):
            raise ValueError(f"gutters.position {pos!r}: expected 'outside' or 'inside'")
        return (bool(gutters.get("enabled", True)), pos == "inside", float(gutters.get("depth", 0.13)),
                float(gutters.get("height", 0.12)))
    return bool(gutters), False, 0.13, 0.12


def gutter_inside_mesh(p0, p1, nrm, plane, depth, height, lift=0.008):
    """(verts, faces) of a gutter lying INSIDE an eave line p0 -> p1 (nrm = outward horizontal unit): front face on the
    eave line, back face `depth` inside it, top following the roof plane (a, b, c) `lift` above it, bottom `height`
    under the eave. Windings give outward normals."""
    a, b, c0 = plane

    def zp(q):
        return a * q.x + b * q.y + c0
    zb = min(p0.z, p1.z) - height
    rows = []
    for p in (p0, p1):
        fo = Vector((p.x, p.y, 0))
        bi = fo - nrm * depth
        rows += [Vector((fo.x, fo.y, zb)), Vector((fo.x, fo.y, zp(fo) + lift)),
                 Vector((bi.x, bi.y, zp(bi) + lift)), Vector((bi.x, bi.y, zb))]
    # 0..3 at p0 (front bottom, front top, back top, back bottom), 4..7 at p1
    faces = [[0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0], [0, 1, 2, 3], [4, 7, 6, 5]]
    d = p1 - p0
    if Vector((d.x, d.y, 0)).cross(nrm).z > 0:          # keep the front face pointing outward whatever the edge direction
        faces = [list(reversed(f)) for f in faces]
    return rows, faces


def soffit_options(soffits):
    """(enabled, skip_facets) from details.json "soffits" (bool, or {"enabled", "skip_facets"}; see the docstring)."""
    if isinstance(soffits, dict):
        return bool(soffits.get("enabled", True)), {str(f) for f in soffits.get("skip_facets", []) or []}
    return bool(soffits), set()


def add_trim(model, frames, c, mats, fascia_h, gutters, soffits):
    g_on, g_in, g_depth, g_h = gutter_options(gutters)
    s_on, s_skip = soffit_options(soffits)
    trough = gutters.get("trough") if isinstance(gutters, dict) else None
    trough_m = None
    if trough is not None and g_on:
        base = mats["gutter"].diffuse_color
        trough_m = mat("Gutter trough", tuple(float(trough) * v for v in base[:3]), 0.8)
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
        eave = e["kind"] == "eave" and not is_hole_edge(f, e)     # no gutter / soffit inside a roof opening
        gut = g_on and eave
        inset = g_depth if (gut and g_in) else 0.0      # "inside" gutters: fascia and soffit sit behind the gutter
        # fascia: a thin board just inside the roof edge (also trims the edges of a roof opening)
        oriented_box(f"fascia {i}", p0 - nrm * (0.03 + inset), d, nrm * 0.03, down, c, mats["fascia"])
        if gut:
            if g_in:
                gv, gf = gutter_inside_mesh(p0, p1, nrm, f["plane"], g_depth, g_h)
                gob = mesh(f"gutter {i}", gv, gf, c, mats["gutter"])
            else:
                g0 = p0 + nrm * 0.005 + Vector((0, 0, -0.03))
                gob = oriented_box(f"gutter {i}", g0, d, nrm * g_depth, Vector((0, 0, -g_h)), c, mats["gutter"])
            if trough_m is not None:              # the open trough: the upward face takes the trough material
                gob.data.materials.append(trough_m)
                flat = [p_ for p_ in gob.data.polygons if abs(p_.normal.z) > 0.5]     # top and bottom (either winding)
                if flat:
                    max(flat, key=lambda p_: p_.center.z).material_index = 1
        if eave and s_on and f["id"] not in s_skip:
            # horizontal soffit from the fascia back to the nearest parallel wall face (<= 2.5 m)
            best = None
            for k, (a, wd, wn, L, _) in frames.items():
                if abs(wd.dot(dh.normalized())) < 0.99:
                    continue
                dist = (Vector((mid.x, mid.y, 0)) - a).dot(wn)
                along = (Vector((mid.x, mid.y, 0)) - a).dot(wd)
                if 0.05 < dist < 2.5 and -0.5 < along < L + 0.5 and (best is None or dist < best):
                    best = dist
            if best and best - 0.03 - inset > 0.02:
                z = min(p0.z, p1.z) - fascia_h
                s0 = Vector((p0.x, p0.y, z)) - nrm * (0.03 + inset)
                oriented_box(f"soffit {i}", s0, Vector((d.x, d.y, 0)), -nrm * (best - 0.03 - inset), Vector((0, 0, -0.012)), c, mats["soffit"])


def skipped(key, skip):
    return key in skip or key.split(":")[0] in skip


def void_strips(w, rects):
    """Face of model wall `w` (model.json: bottom line + top profile) with the rectangles `rects` [(u0, u1, z0, z1)]
    (u along the wall from bottom[0]) cut out, as vertical strips: (verts, quads, area before, area after). Strips
    break at the profile vertices, the hole sides and wherever the top / bottom line crosses a hole's top or bottom,
    so every quad is exact; the parts of the wall above and below each hole stay."""
    (ax, ay, za), (bx, by, zb) = w["bottom"][0][:3], w["bottom"][1][:3]
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    prof = sorted(((p[0] - ax) * ux + (p[1] - ay) * uy, p[2]) for p in w["profile"])

    def bot(u):
        return za + (zb - za) * u / L

    def top(u):
        if u <= prof[0][0]:
            return prof[0][1]
        for (u0, z0), (u1, z1) in zip(prof[:-1], prof[1:]):
            if u <= u1:
                return z0 if u1 - u0 < 1e-12 else z0 + (z1 - z0) * (u - u0) / (u1 - u0)
        return prof[-1][1]
    cuts = {0.0, L, *[min(max(pu, 0.0), L) for pu, _ in prof], *[min(max(v, 0.0), L) for r in rects for v in r[:2]]}
    lines = [(0.0, za, L, zb)] + [(u0, z0, u1, z1) for (u0, z0), (u1, z1) in zip(prof[:-1], prof[1:])]
    for r in rects:                          # where a top / bottom line crosses a hole's bottom or top
        for zz in r[2:4]:
            for u0, z0, u1, z1 in lines:
                if (z0 - zz) * (z1 - zz) < 0:
                    cuts.add(u0 + (u1 - u0) * (zz - z0) / (z1 - z0))
    cuts = sorted(c_ for c_ in cuts if 0.0 <= c_ <= L)
    verts, quads, area0, area1 = [], [], 0.0, 0.0

    def P(u, z):
        return (ax + ux * u, ay + uy * u, z)
    for ua, ub in zip(cuts[:-1], cuts[1:]):
        if ub - ua < 1e-6:
            continue
        um = 0.5 * (ua + ub)
        area0 += 0.5 * (ub - ua) * (max(top(ua) - bot(ua), 0) + max(top(ub) - bot(ub), 0))
        holes = sorted((r[2], r[3]) for r in rects if r[0] - 1e-9 <= um <= r[1] + 1e-9)
        for lo, hi in zip([None] + [h[1] for h in holes], [h[0] for h in holes] + [None]):
            zl = [bot(u) if lo is None else max(lo, bot(u)) for u in (ua, ub)]
            zh = [top(u) if hi is None else min(hi, top(u)) for u in (ua, ub)]
            if zh[0] - zl[0] < 1e-6 and zh[1] - zl[1] < 1e-6:
                continue
            zh = [max(h_, l_) for h_, l_ in zip(zh, zl)]
            k = len(verts)
            verts += [P(ua, zl[0]), P(ub, zl[1]), P(ub, zh[1]), P(ua, zh[0])]
            quads.append([k, k + 1, k + 2, k + 3])
            area1 += 0.5 * (ub - ua) * ((zh[0] - zl[0]) + (zh[1] - zl[1]))
    return verts, quads, area0, area1


def cut_wall_voids(model, openings):
    """Cut every kind "void" opening out of its model wall's face (object "Wall <wing> <side>" from build_model.py),
    keeping the wall's materials; the object gets custom property "voids" (the openings' details keys). Returns
    {wall key: m2 removed}. A void on a wall with no such object (an extra wall) is reported and skipped."""
    by = {}
    for k, o in enumerate(openings or []):
        if o.get("kind") == "void":
            by.setdefault(o["wall"], []).append((k, o))
    walls = {f'{w["wing"]}:{w["side"]}': w for w in model["walls"]}
    out = {}
    for key, items in by.items():
        w = walls.get(key)
        ob = bpy.data.objects.get(f'Wall {w["wing"]} {w["side"]}') if w else None
        if w is None or ob is None or not w.get("bottom"):
            print(f"WARNING: void opening(s) {[f'openings[{k}]' for k, _ in items]} on {key}: no model wall object "
                  f"to cut (voids cut model walls only)")
            continue
        rects = [(o["u"] - o["width"] / 2, o["u"] + o["width"] / 2, o["sill_z"], o["sill_z"] + o["height"])
                 for _, o in items]
        verts, quads, a0, a1 = void_strips(w, rects)
        inv = ob.matrix_world.inverted()
        me = bpy.data.meshes.new(f"{ob.data.name} (voids)")
        me.from_pydata([tuple(inv @ Vector(v)) for v in verts], [], quads)
        me.update()
        for m in ob.data.materials:
            me.materials.append(m)
        ob.data = me
        ob["voids"] = ", ".join(f"openings[{k}]" for k, _ in items)
        out[key] = a0 - a1
        print(f"wall {key}: {len(items)} void(s) cut, {a0 - a1:.2f} m2 of {a0:.2f} removed")
    return out


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
            if o.get("kind") == "void":               # the hole itself: no frame round it
                lo, hi, zlo, zhi = opening_extent(o)
                cuts.append((lo, hi, zlo, zhi))
                continue
            T = o.get("frame", 0.07)
            sw = (float(o["sidelight"].get("width", 0.36)) + T) if (o.get("kind") == "door" and o.get("sidelight")) else 0.0
            s_start = o.get("sidelight", {}).get("side", "end") == "start" if sw else False
            cuts.append((o["u"] - o["width"] / 2 - T - (sw if s_start else 0.0),
                         o["u"] + o["width"] / 2 + T + (0.0 if s_start else sw),
                         o["sill_z"] - (0 if o.get("kind") in ("door", "garage") else T), o["sill_z"] + o["height"] + T))
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


def rail_bar(name, pa, pb, half, z_lo, h, c, m, cut_a=None, cut_b=None):
    """A rail member (cap, top / bottom rail) of half-width `half` centred on the plan line pa -> pb, from z_lo to
    z_lo + h above that line (sloped with it on stairs). An end with a cut line (P, D) (plan point, plan direction) is
    mitred onto that line: its two corners lie ON it, so a cap that ends against another rail's cap side face touches
    it over the whole width (no gap, no overlap, no coplanar top faces). Without cuts it is the plain oriented box."""
    run = pb - pa
    L = Vector((run.x, run.y, 0)).length
    u = Vector((run.x, run.y, 0)) / L
    side = u.cross(Vector((0, 0, 1))).normalized()

    def corner(end, s, cut):
        q = Vector(((pa if end == 0 else pb).x, (pa if end == 0 else pb).y, 0)) + side * (s * half)
        if cut is not None:
            hit = line_hit(q, q + u, Vector((cut[0].x, cut[0].y, 0)), Vector((cut[0].x + cut[1].x, cut[0].y + cut[1].y, 0)))
            if hit is not None:
                q = hit
        t = (q - Vector((pa.x, pa.y, 0))).dot(u) / L
        return Vector((q.x, q.y, pa.z + run.z * t + z_lo))
    bottom = [corner(0, -1, cut_a), corner(1, -1, cut_b), corner(1, 1, cut_b), corner(0, 1, cut_a)]
    verts = bottom + [v + Vector((0, 0, h)) for v in bottom]
    return mesh(name, verts, BOX_FACES, c, m)


def rail_run(name, pa, pb, H, style, c, m, opts, slope_floor=False, cuts=None):
    """Railing infill between two points at walking-surface level (pa.z, pb.z; sloped on stairs).

    style "balusters": 0.07 top rail, bottom rail, 40 mm balusters at 0.13 m.
    style "screen":   closely spaced vertical boards (picket_width / picket_gap) under a flat cap rail,
                      reaching down to the walking surface (a privacy-screen railing).
    style "panel":    a solid board panel (panel_thickness, default 0.03 m) under the same flat cap, from the walking
                      surface (on stairs 0.12 m lower, over the stringer; minus any skirt) up to the cap: a stair side
                      closed with boards.
    cuts: {"a" | "b": {"cap_line": (P, D), "board": d}} for a run that ends ON another rail (a T-join): at that end the
    cap / top rail is mitred onto cap_line (the other rail's near cap face) and the boards, panel, bottom rail and
    balusters stop d m short of the end point (the shared post's face), so nothing overlaps the other rail."""
    run = pb - pa
    L = Vector((run.x, run.y, 0)).length
    if L < 0.05:
        return
    u = Vector((run.x, run.y, 0)).normalized()
    side = u.cross(Vector((0, 0, 1))).normalized()
    up = Vector((0, 0, 1))
    cuts = cuts or {}
    ca, cb = (cuts.get(k, {}).get("cap_line") for k in ("a", "b"))
    ba, bb = (min(float(cuts.get(k, {}).get("board", 0.0)), 0.45 * L) for k in ("a", "b"))
    qa, qb = pa + run * (ba / L), pb - run * (bb / L)          # board span (the whole run unless cut)
    brun, BL = qb - qa, L - ba - bb
    if style == "screen":
        cap_w = opts.get("cap_width", 0.14)
        rail_bar(f"{name} rail cap", pa, pb, cap_w / 2, H - 0.04, 0.04, c, m, ca, cb)
        pw, gap = opts.get("picket_width", 0.11), opts.get("picket_gap", 0.025)
        k_n = max(int((BL - 0.05) / (pw + gap)), 1)
        pitch = (BL - pw) / max(k_n, 1)
        pickets = []
        skirt = opts.get("skirt", 0.0)                     # boards carried down over the rim / header
        for k in range(k_n + 1):
            t = (k * pitch + pw / 2) / BL
            q = qa + brun * t
            z0 = q.z - (0.12 if slope_floor else 0.0) - skirt   # on stairs the boards run down over the stringer
            pickets.append((Vector((q.x, q.y, z0)) - u * (pw / 2) - side * 0.0125, u * pw, side * 0.025, up * (q.z + H - 0.04 - z0)))
        boxes_mesh(f"{name} rail pickets", pickets, c, m)
    elif style == "panel":
        cap_w, t = opts.get("cap_width", 0.14), opts.get("panel_thickness", 0.03)
        rail_bar(f"{name} rail cap", pa, pb, cap_w / 2, H - 0.04, 0.04, c, m, ca, cb)
        drop = (0.12 if slope_floor else 0.0) + opts.get("skirt", 0.0)
        oriented_box(f"{name} rail panel", qa - up * drop - side * (t / 2), brun, side * t, up * (H - 0.04 + drop), c, m)
    elif style != "none":
        w2 = side * 0.07
        rail_bar(f"{name} rail top", pa, pb, 0.035, H - 0.07, 0.07, c, m, ca, cb)
        lo = 0.12 if slope_floor else 0.08
        oriented_box(f"{name} rail bottom", qa + up * lo - w2 * 0.3, brun, w2 * 0.6, up * 0.05, c, m)
        nb = max(int(BL / 0.13), 1)
        bal = []
        for k in range(1, nb):
            q = qa + brun * (k / nb)
            bal.append((q + Vector((-0.02, -0.02, lo)), Vector((0.04, 0, 0)), Vector((0, 0.04, 0)), up * (H - 0.07 - lo)))
        boxes_mesh(f"{name} rail balusters", bal, c, m)


def top_member_half(style, opts):
    """Half-width of a rail's top member: the flat cap of a screen / panel rail, the 0.07 m top rail of balusters."""
    if style in ("screen", "panel"):
        return opts.get("cap_width", 0.14) / 2
    return 0.035 if style != "none" else 0.0


def board_half(style, opts):
    """Half-thickness of a rail's infill across its line (screen boards 0.025, panel, 40 mm balusters)."""
    return {"screen": 0.0125, "panel": opts.get("panel_thickness", 0.03) / 2, "none": 0.0}.get(style, 0.02)


def line_hit(a, b, p, q):
    """Plan intersection of the infinite lines a-b and p-q (Vectors, z ignored); None when (nearly) parallel."""
    r, s_ = Vector((b.x - a.x, b.y - a.y, 0)), Vector((q.x - p.x, q.y - p.y, 0))
    den = r.x * s_.y - r.y * s_.x
    if abs(den) < 1e-9 * max(r.length * s_.length, 1e-12):
        return None
    t = ((p.x - a.x) * s_.y - (p.y - a.y) * s_.x) / den
    return Vector((a.x + r.x * t, a.y + r.y * t, 0))


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
    ob = mesh(f"deck {idx} boards", top + bot, faces, c, board)
    # board ends: the side faces of the board slab sit flush over the rim's outer face, so by default they take the
    # rim material (a fascia over rim + board ends); in board colour they read as a thin coloured line along every
    # edge, worst through a railing's picket gaps. "board_ends": "boards" keeps them in the board colour.
    if dk.get("board_ends", "rim") == "rim" and rim_m is not board:
        ob.data.materials.append(rim_m)
        for p in ob.data.polygons[2:]:
            p.material_index = 1
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
    deck_tag = dict(_TAG)
    for k_re, re_ in enumerate(dk.get("rail_edges", [])):
        _TAG.clear()
        _TAG.update(deck_tag)
        if isinstance(re_, dict):      # per-edge overrides: {"edge": [i, j], "style": "screen", "skirt": 0.9}
            (i, j), estyle = re_["edge"], re_.get("style", style)
            eopts = {**dk, "skirt": re_.get("skirt", dk.get("skirt", 0.0))}
            if re_.get("label"):       # this run's own provenance (a guard measured apart, a skirt of assumed extent)
                _TAG["details"] = f"{deck_tag.get('details', f'decks[{idx}]')}.rail_edges[{k_re}]"
                _TAG["label"] = str(re_["label"])
        else:
            (i, j), estyle, eopts = re_, style, dk
        a, b = poly[i], poly[j]
        ext = re_.get("extend_to") if isinstance(re_, dict) else None
        join = None
        if ext is not None:            # carry the run on along its line until it meets another rail line (shared post)
            p_, q_ = ((poly[ext[0]], poly[ext[1]]) if isinstance(ext[0], int)
                      else (Vector((ext[0][0], ext[0][1], 0)), Vector((ext[1][0], ext[1][1], 0))))
            hit = line_hit(a, b, p_, q_)
            moved = None
            if hit is not None:
                if (hit - b).length <= (hit - a).length:
                    moved, b, end, other = (hit - b).length, hit, "b", a
                else:
                    moved, a, end, other = (hit - a).length, hit, "a", b
            if moved is None or moved > 1.5:
                raise ValueError(f"decks[{idx}].rail_edges[{k_re}]: extend_to {ext} does not meet the run's line within "
                                 f"1.5 m of an end (parallel, or a wrong edge)")
            # T-join: the post stands at the junction; the cap stops ON the target rail's near cap face (mitred to it,
            # no overlap: two caps lying flat on each other at the same height z-fight, black in renders) and the
            # boards stop at the post face
            tstyle, topts = style, dk
            if isinstance(ext[0], int):
                for r2 in dk.get("rail_edges", []):
                    e2 = r2["edge"] if isinstance(r2, dict) else r2
                    if sorted(e2) == sorted(ext):
                        tstyle = r2.get("style", style) if isinstance(r2, dict) else style
            td = (q_ - p_).normalized()
            nt = Vector((-td.y, td.x, 0))
            if (other - hit).dot(nt) < 0:
                nt = -nt
            ui = (other - hit).normalized()                      # from the junction back along the run
            sin_t, cos_t = abs(ui.x * td.y - ui.y * td.x), abs(ui.dot(td))
            ps_ = 0.045                                          # rail post half size (axis-aligned box below)
            board = max(ps_ / max(abs(ui.x), abs(ui.y)),
                        (board_half(tstyle, topts) + board_half(estyle, eopts) * cos_t) / max(sin_t, 1e-6))
            join = (end, {"cap_line": (hit + nt * top_member_half(tstyle, topts), td), "board": board})
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
            cuts = {}
            if join and ((join[0] == "a" and s0 < 1e-6) or (join[0] == "b" and s1 > L - 1e-6)):
                cuts[join[0]] = join[1]
            rail_run(f"deck {idx}", pa, pb, H, estyle, c, rail_m, eopts, cuts=cuts)
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
    _TAG.clear()
    _TAG.update(deck_tag)


def foot_deck(st, decks, tol=0.15, dz=0.03):
    """Index of the deck the stair's foot stands on (its foot centre inside, or within `tol` m of, a deck polygon whose
    top_z is within `dz` of the stair's bottom_z: a flight down onto a raised landing), else None. decks: details
    "decks" with plan polygons resolved."""
    top = Vector((*st["top"], 0))
    dvec = Vector((*st["dir"], 0)).normalized()
    r = st["risers"]
    run = st["length"] / max(r - 1, 1) if st.get("length") else st.get("run", 0.27)
    q = top + dvec * (run * (r - 1))
    for k, dk in enumerate(decks or []):
        if abs(float(dk["top_z"]) - float(st["bottom_z"])) > dz:
            continue
        ring = [Vector((p[0], p[1], 0)) for p in dk["polygon"]]
        if in_ring([(p.x, p.y) for p in ring], q.x, q.y):
            return k
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            t = max(0.0, min(1.0, (q - a).dot(b - a) / max((b - a).length_squared, 1e-12)))
            if (a + (b - a) * t - q).length <= tol:
                return k
    return None


def add_stairs(st, c, mats, idx, decks=None):
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
    # a flight whose foot stands on a raised landing / deck ("foot_on_deck", default: found from the decks) gets
    # "carriage" stringers: the site grounding step snaps every "stringer" toe to the terrain (it would drag this one
    # down to the ground under the landing), as it leaves a "roof drop" where a "downspout" would be grounded
    on = st.get("foot_on_deck")
    on = foot_deck(st, decks) is not None if on is None else bool(on)
    sname = f"stair {idx} carriage" if on else f"stair {idx} stringer"
    if on:
        print(f"stair {idx}: foot on a deck at {st['bottom_z']:.2f} - stringers named '{sname}' (not grounded)")
    for sgn in (-1, 1):   # sloped stringers under the tread ends, toe on the ground (or on the landing)
        o = top - side * (sgn * W / 2)
        tz, bz = st["top_z"], st["bottom_z"]
        quad = [o + Vector((0, 0, tz - 0.04)), o + dvec * length + Vector((0, 0, bz + rise - 0.04)),
                o + dvec * length + Vector((0, 0, bz)), o + Vector((0, 0, tz - 0.04 - 0.3))]
        th = side * 0.05 * sgn
        verts = quad + [p + th for p in quad]
        mesh(sname, verts, [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]], c, str_m)
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
        if style in ("screen", "panel") and st.get("skirt", 0.0) > 0:
            # boards / panel carried down below the rail line: hung on the OUTSIDE of the stringer (inner face 0.01 m
            # out from its outer face at W / 2), with the cap centred over them, so the stringer cannot cover them
            ob_ = -side * (sgn * (W / 2 + 0.01 + board_half(style, st)))
            t0, t1 = t0 - off + ob_, t1 - off + ob_
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


def ridge_cap_mesh(e, facets, half=0.15, t=0.03):
    """(verts, faces) of a shingle cap folded over a ridge / hip edge: a strip `half` m wide (in plan, square to the
    edge) down each adjacent facet, its top `t` m above that facet's plane, apex `t` above the edge. Following the
    two planes it casts no false shadow strip (a flat board at ridge height shades a band of the lower-lit slope,
    which reads as a dark ridge line that orthophotos do not show). A side with no facet named in e["facets"]
    stays level with the edge. None for a vertical edge."""
    up = Vector((0, 0, 1))
    p0, p1 = Vector(e["p0"]), Vector(e["p1"])
    d = p1 - p0
    side = Vector((d.x, d.y, 0)).cross(up)                  # right of p0 -> p1, seen from above
    if side.length < 1e-6:
        return None
    side.normalize()
    planes = {}
    for fid in e.get("facets", []) or []:
        f = facets.get(fid)
        if not f:
            continue
        a, b, c0 = f["plane"]
        s = 1 if (-a * side.x - b * side.y) > 0 else -1      # the facet lies on the side its slope falls towards
        planes.setdefault(s, (a, b, c0))
    verts = []
    for p in (p0, p1):
        row = {}
        for s in (-1, 1):
            q = p + side * (s * half)
            pl = planes.get(s)
            zq = pl[0] * q.x + pl[1] * q.y + pl[2] if pl else p.z
            row[s] = (Vector((q.x, q.y, zq - 0.005)), Vector((q.x, q.y, zq + t)))
        verts += [row[-1][0], row[-1][1], p + up * t, row[1][1], row[1][0]]   # L bottom, L top, apex, R top, R bottom
    # 0..4 at p0, 5..9 at p1; windings give outward normals (top faces up)
    faces = [[1, 2, 7, 6], [2, 3, 8, 7], [1, 6, 5, 0], [3, 4, 9, 8], [0, 4, 3, 2, 1], [5, 6, 7, 8, 9]]
    return verts, faces


def add_roof_extras(model, D, c, mats):
    tag()
    facets = {f["id"]: f for f in model["facets"]}
    for i, e in enumerate(model["edges"]):
        if e["kind"] not in ("ridge", "hip") or e["length_m"] < 0.3:
            continue
        rc = ridge_cap_mesh(e, facets)
        if rc:
            mesh(f"ridge cap {i}", rc[0], rc[1], c, mats["cap"])
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


def add_flashing(model, D, c, mats):
    """Metal flashing round every solid that passes through the roof (a chimney): built along the model.json roof edges
    that the roof fit tags with "penetration" (headwall / sidewall edges on the solid's faces, grouped by that tag): an
    apron `width` m out over the roof (0.004..0.010 m above the facet plane) and an upstand `height` m up the solid's
    face (0.004..0.007 m proud of it). Neighbouring edges of one solid are mitred (offset lines intersected), so the
    pieces meet at the corners without overlapping (no coplanar faces). D["flashing"]: true (default) | false |
    {"color": [r,g,b], "width": 0.1, "height": 0.12, "label": "..."}."""
    fl = D.get("flashing", True)
    if fl is False or (isinstance(fl, dict) and not fl.get("enabled", True)):
        return
    fl = fl if isinstance(fl, dict) else {}
    groups = {}
    for e in model["edges"]:
        if e.get("penetration") and e["kind"] in ("headwall", "sidewall"):
            groups.setdefault(str(e["penetration"]), []).append(e)
    if not groups:
        return
    tag("flashing", fl)
    w, h = float(fl.get("width", 0.10)), float(fl.get("height", 0.12))
    m = pick(fl, mats, "metal", "Flashing", 0.45) if fl.get("color") else mats["metal"]
    planes = {f["id"]: f["plane"] for f in model["facets"]}
    up = Vector((0, 0, 1))
    for key, es in groups.items():
        pts = [Vector((p[0], p[1], 0)) for e in es for p in (e["p0"], e["p1"])]
        ctr = sum(pts, Vector()) / len(pts)
        lines = []
        for e in es:
            p0, p1 = Vector((e["p0"][0], e["p0"][1], 0)), Vector((e["p1"][0], e["p1"][1], 0))
            t = (p1 - p0).normalized()
            o = Vector((-t.y, t.x, 0))
            if ((p0 + p1) / 2 - ctr).dot(o) < 0:              # o: away from the solid
                o = -o
            lines.append((p0, p1, t, o, planes[e["facets"][0]]))

        def corner(k, end, d):
            """plan corner of edge k's offset line (d m out) at its end 0 / 1, mitred onto a neighbour sharing it"""
            p0, p1, t, o, _ = lines[k]
            q = p0 if end == 0 else p1
            for j, (r0, r1, tj, oj, _) in enumerate(lines):
                if j != k and min((q - r0).length, (q - r1).length) < 1e-3:
                    hit = line_hit(p0 + o * d, p1 + o * d, r0 + oj * d, r1 + oj * d)
                    if hit is not None and (hit - q).length < 5 * d + 0.05:
                        return hit
            return q + o * d

        def zp(pl, q, dz):
            return Vector((q.x, q.y, pl[0] * q.x + pl[1] * q.y + pl[2] + dz))
        aprons, ups = [], []
        for k, (p0, p1, t, o, pl) in enumerate(lines):
            ring = [p0, p1, corner(k, 1, w), corner(k, 0, w)]
            aprons.append(([zp(pl, q, 0.004) for q in ring], up * 0.006))
            ring = [corner(k, 0, 0.004), corner(k, 1, 0.004), corner(k, 1, 0.007), corner(k, 0, 0.007)]
            ups.append(([zp(pl, q, 0.007) for q in ring], up * h))
        for nm, pieces in (("apron", aprons), ("upstand", ups)):
            verts, faces = [], []
            for bot, dz in pieces:
                k0 = len(verts)
                verts += bot + [v + dz for v in bot]
                faces += [[k0 + i for i in f] for f in BOX_FACES]
            mesh(f"flashing {key} {nm}", verts, faces, c, m)
        print(f"flashing {key}: {len(es)} edges, {sum((l[1] - l[0]).length for l in lines):.2f} m")
    tag()


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


def add_skylights_chimneys(model, D, c, mats, frames=None):
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
        if ch.get("chase"):
            body = [Vector((x, y, 0)) + ea * (sa * SA / 2) + eb * (sb * SB / 2) for sa in (-1, 1) for sb in (-1, 1)]
            # with a shoulder the chase ends 0.02 m inside it (as the stack does): a chase top flush with the shoulder
            # top is a coplanar face pair over the overlap, rendered as a black slot in the stone; without one it runs
            # to the cap's underside, which covers the stack top
            add_chase(i, ch, body, sh["z"] - 0.02 if sh else ch["top_z"] - ct, D, frames or {}, c, mats, m, nm)


def chase_wall(ch, frames):
    """Key of the wall a chimney's exterior chase stands against: ch["chase"]["wall"], else the wall line nearest the
    chimney centre among walls whose span covers it."""
    key = ch["chase"].get("wall")
    if key:
        if key not in frames:
            raise KeyError(f"chimney chase names an unknown wall {key!r} (known: {sorted(frames)})")
        return key
    q = Vector((ch["center"][0], ch["center"][1], 0))
    best = None
    for k, (a, d, n, L, _) in frames.items():
        u, v = (q - a).dot(d), (q - a).dot(n)
        if -0.5 <= u <= L + 0.5 and (best is None or abs(v) < best[0]):
            best = (abs(v), k)
    if best is None:
        raise ValueError("chimney chase: no wall near the chimney; give chase.wall")
    return best[1]


def grade_under(D, pts, margin=0.3, path=None):
    """Lowest ground z (model datum) under a plan footprint `pts` grown by `margin`, from a ground_surface.npz grid
    (Z[j, i] at x0 + (i + 0.5) cell, y0 + (j + 0.5) cell; pm.py lidar --ground-mode surface): path, else
    D["ground_surface"], else <model.json dir>/data/ground_surface.npz. None when no grid is found or none of its
    cells lies under the footprint."""
    import os
    import numpy as np
    path = path or D.get("ground_surface") or os.path.join(os.path.dirname(os.path.abspath(D["model_json"])), "data",
                                                           "ground_surface.npz")
    if not os.path.exists(path):
        return None
    g = np.load(path)
    Z, x0, y0, cell = g["Z"], float(g["x0"]), float(g["y0"]), float(g["cell"])
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    i0 = max(int(math.floor((min(xs) - margin - x0) / cell - 0.5)), 0)
    i1 = min(int(math.ceil((max(xs) + margin - x0) / cell - 0.5)), Z.shape[1] - 1)
    j0 = max(int(math.floor((min(ys) - margin - y0) / cell - 0.5)), 0)
    j1 = min(int(math.ceil((max(ys) + margin - y0) / cell - 0.5)), Z.shape[0] - 1)
    if i1 < i0 or j1 < j0:
        return None
    sub = Z[j0:j1 + 1, i0:i1 + 1]
    sub = sub[np.isfinite(sub)]
    return float(sub.min()) if sub.size else None


def add_chase(i, ch, body, top, D, frames, c, mats, m, nm):
    """Exterior chimney chase (see the "chimneys" docstring): from bottom_z (or the grade) up to `top` (0.02 m under
    the shoulder top; no shoulder: the cap's underside), on the outside of its wall from 0.05 m inside the face out to
    `projection`, along the wall over the chimney body's extent (`body`: plan corners of the shoulder / stack) inset
    3 mm at each end, so its end faces never lie in the shoulder's / stack's end planes, unless "u" is given."""
    chs = ch["chase"]
    key = chase_wall(ch, frames)
    a, d, n, L, _ = frames[key]
    us = [(p - a).dot(d) for p in body]
    outs = [(p - a).dot(n) for p in body]
    proj = float(chs["projection"]) if chs.get("projection") is not None else max(outs) + 0.003
    if chs.get("u") is not None:
        u0, u1 = (float(v) for v in chs["u"])
    else:   # 3 mm inside the body's end faces where the chase meets them (a body a hair off the wall's square too)
        pu = sorted(zip(us, outs))

        def end_u(p, q, pick):
            if abs(q[1] - p[1]) < 1e-6:
                return pick(p[0], q[0])
            return pick(p[0] + (v - p[1]) * (q[0] - p[0]) / (q[1] - p[1]) for v in (-0.05, proj))
        u0, u1 = end_u(pu[0], pu[1], max) + 0.003, end_u(pu[2], pu[3], min) - 0.003
    if proj <= 0.0:
        raise ValueError(f"chimney {i} chase: projection {proj:.3f} m - the chimney lies inside wall {key}; "
                         f"give chase.projection")
    foot = [a + d * u + n * v for u in (u0, u1) for v in (-0.05, proj)]
    zb = chs.get("bottom_z", "grade")
    if zb == "grade":
        g = grade_under(D, foot, path=chs.get("ground_surface"))
        if g is None:
            raise ValueError(f"chimney {i} chase: bottom_z 'grade' but no ground_surface grid covers it; give bottom_z")
        zb = g - float(chs.get("grade_below", 0.3))
    zb, zt = float(zb), float(chs["top_z"] if chs.get("top_z") is not None else top)
    cm = pick(chs, mats, "siding", f"chimney {i} chase", 0.85) if (chs.get("color") or chs.get("material")) else m
    if chs.get("label"):
        tag(f"chimneys[{i}].chase", chs)
    oriented_box(f"{nm} chase", a + d * u0 - n * 0.05 + Vector((0, 0, zb)), d * (u1 - u0), n * (proj + 0.05),
                 Vector((0, 0, zt - zb)), c, cm)
    tag(f"chimneys[{i}]", ch)
    print(f"chimney {i} chase on {key}: u {u0:.2f}..{u1:.2f}, {proj:.2f} m out, z {zb:.2f}..{zt:.2f}")
    for k_, o in enumerate(D.get("openings", []) or []):      # openings on this wall line (any storey) behind it
        fo = frames.get(o.get("wall"))
        if fo is None or abs(fo[1].dot(d)) < 0.999 or abs((fo[0] - a).dot(n)) > 0.02:
            continue
        lo, hi, zlo, zhi = opening_extent(o)
        shift = (fo[0] - a).dot(d)                                # the opening's u in this wall's frame
        lo, hi = sorted((shift + lo * fo[1].dot(d), shift + hi * fo[1].dot(d)))
        if hi > u0 and lo < u1 and zlo < zt and zhi > zb:
            print(f"WARNING: openings[{k_}] ({o.get('label', o.get('kind', ''))[:40]}) on {o['wall']} lies behind "
                  f"chimney {i}'s chase (u {lo:.2f}..{hi:.2f} against {u0:.2f}..{u1:.2f}): move it off the chase")


def add_beams(model, D, c, mats, frames=None):
    """Straight beams (rim/porch beams, headers, trellis rafters lying in a roof plane); p0 / p1 may be wall points."""
    for i, bm in enumerate(D.get("beams", [])):
        tag(f"beams[{i}]", bm)
        p0, p1 = wall_point(bm["p0"], frames or {}), wall_point(bm["p1"], frames or {})
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


def add_roof_wells(model, D, c, mats):
    """Liner walls round roof openings ("roof_wells"): per polygon edge a slab from just under the roof plane over the
    opening (the top facet just inside the opening at mid-edge, holes ignored) down into the roof (or bottom_z) below
    it, its face 5 mm behind the edge line (the hole-edge fascia stays proud of it) and `thickness` deep away from the
    opening. Edges with no roof over them are skipped."""
    for i, rw in enumerate(D.get("roof_wells", [])):
        tag(f"roof_wells[{i}]", rw)
        ring = [Vector((float(p[0]), float(p[1]), 0)) for p in rw["polygon"]]
        n = len(ring)
        if n < 3:
            continue
        ccw = sum(ring[k].x * ring[(k + 1) % n].y - ring[(k + 1) % n].x * ring[k].y for k in range(n)) > 0
        th = float(rw.get("thickness", 0.1))
        verts, faces, skipped_edges = [], [], 0
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            e = b - a
            if e.length < 1e-6:
                continue
            away = Vector((e.y, -e.x, 0)).normalized() * (1 if ccw else -1)     # away from the opening
            if e.cross(away).z < 0:                                                 # right-handed slab: outward normals
                a, b, e = b, a, -e
            corners = [a + away * 0.005, b + away * 0.005, b + away * (0.005 + th), a + away * (0.005 + th)]
            mid = (a + b) / 2 - away * 0.05                       # just inside the opening, mid-edge
            pl = facet_plane(model, mid.x, mid.y)                 # the roof the opening is cut in (holes ignored)
            top, bot = [], []
            for q in corners if pl else []:
                zt = pl[0] * q.x + pl[1] * q.y + pl[2]
                zb = roof_below(model, q.x, q.y, zt - 0.05)
                if zb is None:                                    # slab corner past the lower roof's edge
                    qi = q - away * (away.dot(q - a) + 0.05)
                    zb = roof_below(model, qi.x, qi.y, zt - 0.05)
                zb = rw.get("bottom_z") if zb is None else zb
                if zb is None or zb >= zt - 0.05:
                    break
                top.append(zt - 0.01)
                bot.append(zb - 0.02)
            if len(top) < 4:
                skipped_edges += 1
                continue
            j = len(verts)
            verts += [(q.x, q.y, z) for q, z in zip(corners, bot)] + [(q.x, q.y, z) for q, z in zip(corners, top)]
            faces += [[j + v for v in f] for f in BOX_FACES]
        if skipped_edges:
            print(f"roof well {i}: {skipped_edges} edge(s) with no roof above or below, skipped")
        if faces:
            mesh(f"roof well {i}", verts, faces, c, pick(rw, mats, "siding", f"roof well {i}", 0.85))


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


def board_spans(z0, z1, u_lo, u_hi, cuts):
    """z intervals of a vertical board over u_lo..u_hi from z0 to z1 left after removing every opening extent
    (u_lo, u_hi, z_lo, z_hi) that overlaps it in u (a door frame set against the wall corner takes over the board)."""
    spans = [(z0, z1)]
    for cu0, cu1, cz0, cz1 in cuts:
        if cu1 <= u_lo + 1e-6 or cu0 >= u_hi - 1e-6:
            continue
        spans = [p for s0, s1 in spans for p in ((s0, min(s1, cz0)), (max(s0, cz1), s1)) if p[1] - p[0] > 0.02]
    return spans


def add_corner_boards(model, frames, fnd, c, mats, width=0.1, openings=(), skip_ends=()):
    """Boards at both ends of every model wall, from the foundation line to the top, cut round openings; skip_ends
    lists "<wall>:start" / "<wall>:end" ends that get none."""
    skip = set(fnd.get("skip", []))
    skip_ends = set(skip_ends)
    for w in model["walls"]:
        key = f'{w["wing"]}:{w["side"]}'
        a, d, n, L, zb = frames[key]
        top0, top1 = w["profile"][0][2], w["profile"][-1][2]
        sb = fnd.get("walls", {}).get(key)
        cuts = [opening_extent(o) for o in openings if o.get("wall") == key]
        for u, zt, sgn, end in ((0.0, top0, 1, "start"), (L, top1, -1, "end")):
            if f"{key}:{end}" in skip_ends:
                continue
            z0 = zb(u) if skipped(key, skip) else (sb if sb is not None else zb(u) + fnd.get("default_reveal", 0.25))
            for s0, s1 in board_spans(z0, zt - 0.05, min(u, u + width * sgn), max(u, u + width * sgn), cuts):
                p = a + d * u + n * 0.012 + Vector((0, 0, s0))
                oriented_box(f"corner board {key}", p, d * (width * sgn), n * 0.02, Vector((0, 0, s1 - s0)), c,
                             mats["corner"])


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
        x, y = wall_point(ds["xy"], frames)[:2]
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
        path = [Vector(p) for p in wall_points(ds.get("path", []), frames)]
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


LANTERN_SIZE = (0.2, 0.36, 0.18)       # default coach-lantern body: width along the wall, height, depth out from it


def glass_material(name, rgb, rough=0.15, emission=0.0, emission_color=(255, 190, 120)):
    """Lamp glass: a Principled BSDF of colour rgb, optionally glowing (emission = Emission Strength, ~radiance in the
    sun's units: a sunlit white wall is ~1, so 0.05-0.2 reads as a dim lamp at dusk and disappears in daylight)."""
    rgb, e = col(rgb), float(emission or 0.0)
    ec = col(emission_color)
    m = mat(f"{name[:28]} {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} e{e:.2f}", rgb, rough)
    b = m.node_tree.nodes.get("Principled BSDF")
    if e > 0:
        for k in ("Emission Color", "Emission"):            # Blender 4+ / 3.x socket names
            if k in b.inputs:
                b.inputs[k].default_value = (*ec, 1)
                break
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = e
    return m


def add_lantern(i, l, p, d, n, c, mats):
    """Coach lantern on a wall: back plate, a short arm and a box body (cap, corner posts, bottom, glass) whose centre
    is l["z"] high, `arm` m out from the plate. Body / glass colours from l["color"] / l["glass_color"]."""
    w, h, dp = (float(v) for v in l.get("size", LANTERN_SIZE))
    arm = float(l.get("arm", 0.05))
    up = Vector((0, 0, 1))
    body_m = pick(l, mats, "fixture", f"light {i} body", 0.45)
    glass_m = (glass_material(f"light {i} glass", l["glass_color"], 0.15, l.get("emission", 0.0),
                              l.get("emission_color", (255, 190, 120)))
               if l.get("glass_color") is not None else mats["glass"])
    plate_t = 0.02
    oriented_box(f"light {i} plate", p - d * 0.05 - up * (h * 0.3), d * 0.1, n * plate_t, up * (h * 0.6), c, body_m)
    oriented_box(f"light {i} arm", p - d * 0.015 + n * plate_t + up * (h * 0.15), d * 0.03, n * arm, up * 0.03, c, body_m)
    o = p - d * (w / 2) + n * (plate_t + arm)               # body back-left-bottom corner (bottom at z - h / 2)
    o = o - up * (h / 2)
    cap_t, bot_t, post, ov = min(0.05, h * 0.15), min(0.035, h * 0.1), min(0.025, w * 0.15), 0.02
    gh = h - cap_t - bot_t
    parts = [(o - d * ov - n * 0.0 + up * gh + up * bot_t, d * (w + 2 * ov), n * (dp + ov), up * cap_t),   # cap
             (o, d * w, n * dp, up * bot_t)]                                                              # bottom
    for a_ in (0.0, w - post):                              # four corner posts
        for b_ in (0.0, dp - post):
            parts.append((o + d * a_ + n * b_ + up * bot_t, d * post, n * post, up * gh))
    boxes_mesh(f"light {i} body", parts, c, body_m)
    gi = 0.006                                              # glass set just inside the posts' outer faces
    oriented_box(f"light {i} glass", o + d * gi + n * gi + up * bot_t, d * (w - 2 * gi), n * (dp - 2 * gi), up * gh,
                 c, glass_m)


def add_lights_and_text(D, frames, c, mats):
    import mathutils
    for i, l in enumerate(D.get("lights", [])):
        tag(f"lights[{i}]", l)
        a, d, n, L, _ = frames[l["wall"]]
        p = a + d * l["u"] + Vector((0, 0, l["z"]))
        if l.get("style", "shade") == "lantern":
            add_lantern(i, l, p, d, n, c, mats)
            continue
        fx = pick(l, mats, "fixture", f"light {i}", 0.4)
        oriented_box(f"light {i} plate", p - d * 0.06 - Vector((0, 0, 0.08)), d * 0.12, n * 0.03, Vector((0, 0, 0.16)), c, fx)
        oriented_box(f"light {i} arm", p - d * 0.015 + Vector((0, 0, 0.04)), d * 0.03, n * 0.22, Vector((0, 0, 0.03)), c, fx)
        oriented_box(f"light {i} shade", p - d * 0.12 + n * 0.12 - Vector((0, 0, 0.1)), d * 0.24, n * 0.24, Vector((0, 0, 0.12)), c, fx)
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
        "trim": mat("Trim", trim, 0.5),
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
        "stone": (stone_material(**{k: v for k, v in D["stone"].items() if k in ("colors", "course", "length", "joint",
                                                                                 "joint_color", "warp", "mottle")})
                  if D.get("stone") else mat("Cast stone", (0.62, 0.60, 0.55), 0.8)),
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
    if rf.get("underside", True):         # light soffit on the roof sheet seen from below (rakes, eaves, overhangs)
        und = rf.get("underside_color") or D.get("soffit_color", (0.8, 0.8, 0.77))
        for m in {s.material for ob in bpy.data.collections["Roof facets"].objects for s in ob.material_slots
                  if s.material and s.material.node_tree is not None}:
            underside_soffit(m, und)
    tag()
    cut_wall_voids(model, D.get("openings", []) or [])          # kind "void" openings: holes in the model walls
    add_foundation(frames, D.get("foundation", {}), c, mats, D.get("openings", []))
    add_trim(model, frames, c, mats, D.get("fascia_height", 0.2), D.get("gutters", True), D.get("soffits", True))
    add_extra_walls(D, frames, c, mats)
    for i, o in enumerate(D.get("openings", [])):
        tag(f"openings[{i}]", o)
        add_opening(o, frames, c, mats)
    add_roof_extras(model, D, c, mats)
    add_skylights_chimneys(model, D, c, mats, frames)
    add_flashing(model, D, c, mats)
    add_beams(model, D, c, mats, frames)
    add_beam_ends(model, D, c, mats)
    add_roof_wells(model, D, c, mats)
    tag()
    cb = D.get("corner_boards", True)
    if (cb.get("enabled", True) if isinstance(cb, dict) else cb):
        add_corner_boards(model, frames, D.get("foundation", {}), c, mats, openings=D.get("openings", []) or [],
                          skip_ends=cb.get("skip", []) if isinstance(cb, dict) else ())
    add_wall_boxes(D, frames, c, mats)
    add_lights_and_text(D, frames, c, mats)
    for i, dk in enumerate(D.get("decks", [])):
        tag(f"decks[{i}]", dk)
        add_deck({**dk, "polygon": [p[:2] for p in wall_points(dk["polygon"], frames)]}, c, mats, i)
    for i, st in enumerate(D.get("stairs", [])):
        tag(f"stairs[{i}]", st)
        add_stairs(st, c, mats, i, [{**dk, "polygon": [p[:2] for p in wall_points(dk["polygon"], frames)]}
                                    for dk in D.get("decks", [])])
    for i, ce in enumerate(D.get("ceilings", [])):
        tag(f"ceilings[{i}]", ce)
        pts = [(p[0], p[1], ce["z"]) for p in wall_points(ce["polygon"], frames)]
        area = 0.5 * abs(sum(pts[k][0] * pts[k - 1][1] - pts[k - 1][0] * pts[k][1] for k in range(len(pts))))
        if area < 0.01:          # wall points that coincide until a wall moves (a soffit strip over a flush wall)
            print(f"ceiling {i}: zero area ({area:.4f} m2), skipped")
            continue
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
