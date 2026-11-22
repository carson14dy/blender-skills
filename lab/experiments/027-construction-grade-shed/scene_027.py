"""Light and cameras for 027, on the built .blend: lawn, the pilot's hero camera (front left corner, 28 mm),
an afternoon sun (scene_mood), 1920x1080; and Cam_Gable, square-ish on the front gable for the pitch photo check
(about 25 degrees off square, the whole gable and the door in view).

Usage: $LAB_BPY_PYTHON scene_027.py out/shed.blend      (saves the same file)
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", ".claude", "skills", "blender-suite", "scripts"))
blend = os.path.abspath(sys.argv[1])
bpy.ops.wm.open_mainfile(filepath=blend)
import scene_mood  # noqa: E402

for name in ("Ground_Lawn", "Cam_Hero", "Cam_Gable"):
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name])
me = bpy.data.meshes.new("Ground_Lawn")
me.from_pydata([(-300, -300, 0), (300, -300, 0), (300, 300, 0), (-300, 300, 0)], [], [(0, 1, 2, 3)])
lawn = bpy.data.objects.new("Ground_Lawn", me)
bpy.context.scene.collection.objects.link(lawn)
m = bpy.data.materials.get("M_Lawn") or bpy.data.materials.new("M_Lawn")
nt = m.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
noise, ramp = nt.nodes.new("ShaderNodeTexNoise"), nt.nodes.new("ShaderNodeValToRGB")
noise.inputs["Scale"].default_value = 40.0
ramp.color_ramp.elements[0].color = (0.12, 0.24, 0.07, 1)
ramp.color_ramp.elements[1].color = (0.22, 0.36, 0.12, 1)
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.9
me.materials.append(m)


def camera(name, loc, target, lens):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = lens
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    return cam


hero = camera("Cam_Hero", (-3.9, -5.6, 1.75), (1.45, 1.75, 1.45), 28)
a = math.radians(25)                     # 25 degrees off square to the front gable, from the left
c = Vector((1.524, 0, 1.55))             # the gable's centre, metres
camera("Cam_Gable", c + Vector((-math.sin(a), -math.cos(a), 0)) * 8.0 + Vector((0, 0, 0.1)), c, 35)
bpy.context.scene.camera = hero
res = scene_mood.run(time="afternoon")
r = bpy.context.scene.render
r.resolution_x, r.resolution_y = 1920, 1080
print("scene_mood:", {k: res[k] for k in res if k in ("ok", "time", "sun", "elevation", "heading", "warning")})
bpy.ops.wm.save_as_mainfile(filepath=blend)
