# Camera Moves

The execution model is in `SKILL.md`. A constant-speed looping orbit is `turntable.py` in `blender-lighting-lookdev`. This skill covers every other move. Rendering and video encoding are in `blender-rendering`.

## One call each
```
scripts/camera_move.py -- --objects Hero --move push_in --focus-object Logo --frames 120
scripts/camera_move.py -- --objects Hero --move dolly_orbit --sweep 120
scripts/camera_move.py -- --objects Hero --move crane --frames 96
scripts/camera_move.py -- --objects Hero --move speed_ramp --frames 240 --faces 4 --tilt 30
```

## Pick the move
| Move | Reads as | Motion |
|---|---|---|
| `push_in` | reveal, "look at this detail" | wide 35 mm to tight 65 mm while closing in. `--focus X Y Z` or `--focus-object` picks the detail |
| `dolly_orbit` | energy, showing form | 90° sweep (`--sweep`) while moving closer and lowering |
| `crane` | scale, unveiling | starts low looking up, rises and pulls back to look down. Stays above the asset's floor |
| `speed_ramp` | social and marketing hero, every side shown | slow drift on each of `--faces` stops, fast whip between them. Loops seamlessly |

## Procedure
1. **Fix the aspect ratio first,** because framing depends on it. Pass `--res 1920 1080`.
2. **Find the front.** Imported and AI-generated meshes rarely face -Y. Render `review_shots.py -- --objects Hero --views front right back left` (`blender-asset-qa`), ask the user if it isn't obvious, then pass `--azimuth` (90 starts from +X, 180 from +Y).
3. **Find the detail for a push-in.** `--focus-object` needs a separate object. A scanned or generated model is usually one mesh, so use `--focus X Y Z`. Estimate the point from the review shots and the object's bounds, render the last frame as a preview, then adjust. Ask the user where the detail is if you can't see it.
4. **Light it.** This skill adds no lights. `turntable.py --objects Hero --rig studio --frames 1` gives a static light rig. Run it **before** the move, because it sets its own scene camera.
5. Run the move and read the result: `warnings` must be empty. `frames_subject_in_frame` should equal `frames_checked`, except on a push-in, which leaves the frame on purpose after its opening.
6. Preview before a full render: `render_batch.py -- --preset preview --frames 1,60,120`. Then render the range. For a transparent background, skip `--backdrop` and any floor, render PNG frames with `--transparent`, and encode them (`blender-rendering`).

## How the rig works
- `CM_Pivot` is an empty at the subject's center. `CM_Cam` is parented to it and aims at it with Track To. Orbit lives on the pivot's rotation, and distance and height live on the camera's local position, so a sweep follows an arc. Interpolating world positions directly would cut a chord and dip toward the asset.
- Distances are multiples of the fit distance for each lens, so moves work at any scale. Hard-coded meters break on anything not about 1 m wide.
- The default fit is safe rather than snug, because it keeps the asset's whole bounding sphere in frame. For a tighter hero framing, try `--fill 1.3`. The result warns if the subject clips.
- Interpolation is BEZIER with auto-clamped handles: a natural ease at both ends with no overshoot.

## speed_ramp numbers
- The speed comes from uneven key spacing. Each stop spends `--hold` (0.7) of its time on a small drift, then whips in the rest. The result reports `peak_deg_per_frame` against `hold_deg_per_frame`. Aim for a ratio of at least 5. Use 240 frames or more, because whips strobe if they get too short.
- Elevation swings by `--tilt` along a sine, so the second stop sees the top and the fourth sees the underside. Positive tilt means above. `--tilt 0` keeps it level. Total elevation is limited to 75° because Track To flips at the pole.
- The last key is one full turn on frame N+1, which isn't rendered, so frames 1..N loop. `seam_error_deg` must be 0. Speed drops to zero at the seam on both sides, which reads as part of the first hold.
- A floor or backdrop blocks the underside. Render with a transparent film and no floor, or use `--tilt 0`.

## Rules
- Keep one move per clip. Chain clips in `blender-video-editing` rather than stacking moves in one action.
- Long lenses flatter products. If a wide opening looks distorted on a small object, edit the `CM_Cam` lens keys rather than the distance.
- Let the asset breathe: 4–5 seconds for `push_in`, `dolly_orbit` and `crane`, about 10 seconds for `speed_ramp`.

## Gotchas
- Re-running replaces `CM_*` and resets the scene frame range. Running `turntable.py` afterward takes back the scene camera.
- Each MCP call has a fresh namespace, so object references don't survive between calls. Look the rig up by name: `bpy.data.objects["CM_Cam"]`.
- Long animation renders outlive an MCP call. Run them headless with `run_in_blender.py` and check the output folder for the frames.
