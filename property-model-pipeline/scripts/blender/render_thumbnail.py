"""Project-card thumbnail: the house alone on a light backdrop with a soft contact shadow,
seen from a front corner (3/4 view, ~23 deg down), auto-cropped to 4:3.

    python3 render_thumbnail.py SITE.blend OUT.jpg [--front-az 90] [--swing -16] [--samples 128]

--front-az  compass bearing the front of the house faces (0 = N, 90 = E, 180 = S, 270 = W)
--swing     degrees to swing the camera off square-on toward a corner (negative = to the right of the front)
Yard surfaces (Site collection), labels, LiDAR and reference geometry are hidden; Details stay.
With --terrain the LiDAR terrain stays and so does the hardscape that meets the house: draped paving
(concrete, street, rock beds), curbs, retaining walls, piers, landscape steps and paths (Site objects
tagged by add_site.py's "site_kind"), so a garage opens onto its driveway. The crop follows the house alone.
The blend is not saved back.
"""
import argparse, math, sys
import bpy
from mathutils import Vector

ap = argparse.ArgumentParser()
ap.add_argument("blend"); ap.add_argument("out")
ap.add_argument("--front-az", type=float, default=90.0)
ap.add_argument("--swing", type=float, default=-16.0)
ap.add_argument("--elev", type=float, default=23.0)
ap.add_argument("--samples", type=int, default=128)
ap.add_argument("--size", default="800x600")
ap.add_argument("--terrain", action="store_true", help="keep the LiDAR terrain in the shot (hillside lots); crop to the house")
ap.add_argument("--grade", default="median", choices=["median", "low"],
                help="floor height: median grade under the house, or its low side (hillside / walk-out lots)")
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

bpy.ops.wm.open_mainfile(filepath=a.blend)
sc = bpy.context.scene
HIDE = ("Labels", "Roof edges", "LiDAR points", "Reference data")
KEEP_SITE = ("AC", "pad (AC)", "gas meter", "egress window well")
# with the terrain shown: the paving and walls the house meets (add_site.py "site_kind" tags)
KEEP_KINDS_TERRAIN = ("overlay:concrete", "overlay:street", "overlay:rock_bed", "curb", "edging", "retaining_wall",
                      "pier", "steps", "path", "surface")


def keep_with_terrain(o):
    return o.name.startswith("Terrain") or o.get("site_kind") in KEEP_KINDS_TERRAIN or o.name.endswith("(draped)")


for o in bpy.data.objects:
    names = [c.name for c in o.users_collection]
    if o.name.startswith("Ground") or any(n in HIDE for n in names) or ("Site" in names and not o.name.startswith(KEEP_SITE)):
        o.hide_render = not (a.terrain and "Site" in names and keep_with_terrain(o))
# the crop / framing follows the house (and its small fittings), not the yard kept with --terrain
house = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render and not o.name.startswith("Terrain")
         and not ("Site" in [c.name for c in o.users_collection] and keep_with_terrain(o) and not o.name.startswith(KEEP_SITE))]
pts = [o.matrix_world @ Vector(c) for o in house for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
# grade at the house: median terrain height near the building, else the lowest house point
z0 = lo.z
ter = next((o for o in bpy.data.objects if o.name.startswith("Terrain")), None)
if ter:
    c = (lo + hi) / 2; r = max(hi.x - lo.x, hi.y - lo.y) / 2
    zs = sorted(p.z for p in (ter.matrix_world @ v.co for v in ter.data.vertices) if abs(p.x - c.x) < r and abs(p.y - c.y) < r)
    if zs: z0 = zs[len(zs) // 2] if a.grade == "median" else zs[len(zs) // 10]

sc.render.engine = "CYCLES"; sc.cycles.samples = a.samples; sc.cycles.device = "CPU"
try: sc.cycles.use_denoising = True
except Exception: pass
vt = [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items]
sc.view_settings.view_transform = "AgX" if "AgX" in vt else "Filmic"
sc.render.film_transparent = not a.terrain
w = sc.world or bpy.data.worlds.new("World"); sc.world = w
w.use_nodes = True; nt = w.node_tree; nt.nodes.clear()
bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs[0].default_value = (0.9, 0.92, 0.95, 1); bg.inputs[1].default_value = 1.1
nt.links.new(bg.outputs[0], nt.nodes.new("ShaderNodeOutputWorld").inputs[0])
sun = next((o for o in bpy.data.objects if o.type == "LIGHT" and o.data.type == "SUN"), None)
if sun is None:
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); sc.collection.objects.link(sun)
# camera bearing (ENU: x east, y north), math angle from +x
cam_bearing = a.front_az - a.swing
th = math.radians(90 - cam_bearing)
# sun high and a little to the camera's right, so the front is lit and the shadow falls behind the house
sth = th - math.radians(30)
sun.rotation_euler = (math.radians(35), 0, sth + math.pi / 2); sun.data.energy = 3.0; sun.data.angle = math.radians(8)
if not a.terrain:
    bpy.ops.mesh.primitive_plane_add(size=400, location=((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, z0 + 0.02))
    bpy.context.active_object.is_shadow_catcher = True
cd = bpy.data.cameras.new("Thumb"); cam = bpy.data.objects.new("Thumb", cd); sc.collection.objects.link(cam)
cd.lens = 55
tgt = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, z0 + (hi.z - z0) * 0.35))
dist = 2.4 * max(hi.x - lo.x, hi.y - lo.y, hi.z - z0)
el = math.radians(a.elev)
cam.location = tgt + dist * Vector((math.cos(el) * math.cos(th), math.cos(el) * math.sin(th), math.sin(el)))
cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 1200, 100
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
import os, tempfile
tmp = os.path.join(tempfile.mkdtemp(), "thumb_rgba.png"); sc.render.filepath = tmp
bpy.ops.render.render(write_still=True)

from PIL import Image
im = Image.open(tmp).convert("RGBA")
if a.terrain:   # crop to the house's projected box (the terrain fills the frame)
    from bpy_extras.object_utils import world_to_camera_view
    cs = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    uv = [world_to_camera_view(sc, cam, c) for c in cs]
    W_, H_ = im.size
    x0, x1 = min(p.x for p in uv) * W_, max(p.x for p in uv) * W_
    y0, y1 = (1 - max(p.y for p in uv)) * H_, (1 - min(p.y for p in uv)) * H_
else:
    x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
W = max((x1 - x0) * 1.12, (y1 - y0) * 1.12 * 4 / 3); H = W * 3 / 4
if a.terrain:   # keep the crop on the render (no backdrop to pad with)
    W, H = min(W, im.width), min(H, im.height)
    cx = min(max(cx, W / 2), im.width - W / 2); cy = min(max(cy, H / 2), im.height - H / 2)
pad = int(max(W, H))                                   # crop may run past the render: pad with backdrop
flat = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (242, 242, 240, 255)); flat.alpha_composite(im, (pad, pad))
cx, cy = cx + pad, cy + pad
ow, oh = (int(v) for v in a.size.split("x"))
flat.crop((int(cx - W / 2), int(cy - H / 2), int(cx + W / 2), int(cy + H / 2))).convert("RGB").resize((ow, oh), Image.LANCZOS) \
    .save(a.out, quality=86, optimize=True, progressive=True)
print("thumbnail", a.out, "grade z", round(z0, 2))
