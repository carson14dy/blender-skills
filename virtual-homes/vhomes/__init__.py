"""Virtual test homes: seeded houses with an exact answer key and realistic photo sets.

Pipeline (each stage is deterministic in the house seed):

1. ``spec.make_spec(seed)``            -> house parameters (pure Python)
2. ``geometry.build_house(spec)``      -> exact roof/wall geometry, placed details, scale markers
3. ``answer_key.compute(house)``       -> measurements computed from that geometry (independent of the builder)
4. ``rigs.make_cameras(house)``        -> ground / roof / drone camera poses + intrinsics (ground truth)
5. ``blender_scene.build(house)``      -> scene.blend (needs bpy + numpy only)
6. ``render.render_cameras(...)``      -> raw Cycles renders (needs bpy)
7. ``post.finish(...)``                -> lens distortion, blur, noise -> renders/<rig>/*.png (numpy + Pillow)

Units: metres inside, feet / squares in the report. Frame: x east, y north, z up, origin at the house centre on
the ground (z = 0 is finished grade).
"""

GENERATOR_VERSION = "0.1.0"
