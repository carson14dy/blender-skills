# Short Films

From Claude Blender Skills by Mr omi (MIT). Two examples with the scripts that made them: a 10 s night FPV drone shot through a city (`pipelines/film/`) and a 20 s, six-shot story of an old car on a snowy night, 2.39:1, 600 frames at 30 fps (`pipelines/car-film/`). Object names come from the author's scenes.

## Use the pipelines
1. Copy the folder into the project: film to `~/blender-film` or set `FILM_ROOT` (the film scripts load `tools/lib.py` from there); car film to `~/blender-car-film` (hard-coded).
2. Open Blender with the MCP for Blender add-on (port 9876) and send the numbered scripts in order, in one session: from the project folder, `python <skill_dir>/scripts/blender_send.py ./scripts/01_world.py ./scripts/02_car.py`. Names stay defined between calls, so later scripts reuse `pbr()`, `col()`.
3. Work on copies of the .blend: several passes edit materials and break if re-run after a crash.

## Rules
- Storyboard first: camera move, timing and key sound per shot. Wait for approval before touching Blender.
- Find real models (a free CC BY car; Poly Haven CC0 trees, lamps, textures, sky); build only simple things in Python. Read anything you download; bake external assets into the .blend.
- Never render in the live window (it crashes): save, then render headless.
- Ask before long renders. Test at low quality, final quality last.

## Steps
1. **Storyboard**: shots, timings, camera, where the hero is, what the viewer feels; one image sheet kept open. The car film, no people on screen:

| # | s | Shot | Shakify | Key sound |
|---|---|---|---|---|
| 1 | 0–3 | wide low push-in, parked car, streetlight, snow | INVESTIGATION 0.15 | wind, snow hiss, lamp buzz |
| 2 | 3–5 | macro, frosted headlight clicks on | INVESTIGATION 0.1 | key, starter, engine catches |
| 3 | 5–7 | ground cam at the rear wheel, pulls away | engine vibration | tyre crunch, rev |
| 4 | 7–11 | 3/4 front tracking, 45 km/h, school, hospital | OUT_CAR_WINDOW 0.4 | engine, slush; voice 1 at 8.5 |
| 5 | 11–14.5 | inside behind the seats, wipers | OUT_CAR_WINDOW 0.6 | muffled engine, wipers |
| 6 | 14.5–20 | house: stop 16.0, engine off 16.5, porch light 17.5 | INVESTIGATION 0.12 | brakes, silence, ticking; voice 2 at 17.9 |

2. **Layout, motion from physics**: lay the street out from a top-view map along +X, keep the hero's path clear, then dress it. Simulate the move: `01_swing_sim.py` (gravity, drag, a rope that can't stretch) searches anchor timings until the path threads the street; `02_path_empty.py` keys a Follow Path offset per frame, so speed is real. The car drives from a speed profile, wheels rolling by distance / radius.
3. **The hero**: a rigged character on mocap hung like a puppet in the air (mocap is recorded on the ground). If a character with limbs looks wrong, swap the hero and keep set, camera and path. `04_drone_attitude.py` flies a quad: thrust along acceleration + gravity, nose along velocity (it tilts into speed-ups and banks in turns), throttle cut on ballistic stretches for flips and a roll, then a braking flare into a hover.
4. **Realism pass** (`05_realism.py`): AgX `Base Contrast`, exposure 0.55, no grade; thin haze; asphalt with broken repeat, wheel paths, oil lines, patches; dirt at wall feet, run-off streaks.
5. **Night** (`06_night.py`): practicals light the scene, not the sky: 3200 K LED lamps, lit windows, car lights, red signals, blue fog, wet asphalt. The first try gave orange fog and glowing blocks. Glass is smooth, so the facade roughness map is the window mask (`roughness < 0.3`); light random cells warm, cool or off. For other nights: `scripts/scene_mood.py` in `blender-time-of-day`.
6. **Cameras**: Shakify (free add-on, recorded camera motion) on every shot camera. All cameras on one side (180-degree rule). Add close shots: a street-level lens 0.45 m above the wet road, the hero diving at it and stopping in front of it. Planned moves: `blender-camera-moves`.
7. **Snow, fog, steam** (`08_fx.py`): snow pre-rolled to fall at frame 1, a fog volume for light cones, exhaust steam, tyre spray. Looping weather: `blender-weather-fx`. Read the particle lessons.
8. **Lens look, grade**: bloom, slight barrel distortion, dispersion. Grade only where it helps: shadows neutral blue, highlights warm, never green. 24 to 30 fps; `17_fps30.py` remaps 24 → 30 with frame mapping.
9. **Render**: [long-renders.md](long-renders.md). **Sound**: [film-sound.md](film-sound.md).
10. **Clay build-up**: on a fresh copy, `14_clay_build.py` makes everything white clay, freezes camera and traffic, and drops ~500 pieces from the sky (cars, near buildings, far city, props). Cut night, clay, 0.25 s wipe, night on one camera and frame. Clay vs night split stills make thumbnails.

## Files: `pipelines/film/`
| File | Does |
|---|---|
| `pipelines/film/scripts/01_swing_sim.py` | plain Python (numpy, Pillow): swing sim, `research/sim_out.json` |
| `pipelines/film/scripts/02_path_empty.py` | path + hero empty keyed per frame |
| `pipelines/film/scripts/03_camera.py` | chase camera, lens per panel |
| `pipelines/film/scripts/03b_camera_noise.py` | sway + micro-shake, DOF |
| `pipelines/film/scripts/04_drone_attitude.py` | quad attitude, tricks, `research/drone_path.json` |
| `pipelines/film/scripts/05_realism.py` | haze, asphalt wear, wall dirt |
| `pipelines/film/scripts/06_night.py` | night lights, windows, wet road |
| `pipelines/film/scripts/07_shakify_cams.py` | Shakify + street-level `CAM_LOW` |
| `pipelines/film/scripts/08_lens_look.py` | bloom, lens distortion |
| `pipelines/film/scripts/09_render_opt.py` | no duplicate trees, LOD1 beyond 30 m |
| `pipelines/film/scripts/10_render_edit.py` | headless edit render, `status.json` |
| `pipelines/film/scripts/11_motion_data.py` | motion → `audio/motion.json` |
| `pipelines/film/scripts/12_build_sfx.py` | plain Python (numpy, scipy): the mix |
| `pipelines/film/scripts/13_aerial_cam.py` | aerial camera for the clay shot |
| `pipelines/film/scripts/14_clay_build.py` | clay drop-in build |
| `pipelines/film/tools/lib.py` | `coll()`, `save()`, `snap()` |
| `pipelines/film/tools/render_window.ps1` | Windows progress panel |
| `pipelines/film/tools/clay_assemble.sh` | ffmpeg clay cut |

## Files: `pipelines/car-film/`
| File | Does |
|---|---|
| `pipelines/car-film/scripts/01_world.py` | fresh scene, PBR helper |
| `pipelines/car-film/scripts/02_car.py` | car import, 4.5 m |
| `pipelines/car-film/scripts/03_rig.py` | wheel origins |
| `pipelines/car-film/scripts/04_set.py` | street, lamps, school, hospital |
| `pipelines/car-film/scripts/05_house.py` | the house |
| `pipelines/car-film/scripts/06_light_viewport.py` | autosave, light viewport |
| `pipelines/car-film/scripts/07_anim.py` | drive, wheels, lights |
| `pipelines/car-film/scripts/08_fx.py` | snow, fog, steam, spray |
| `pipelines/car-film/scripts/09_cams.py` | 6 Shakify cameras |
| `pipelines/car-film/scripts/10_fix.py` | headlight spots, lamp discs |
| `pipelines/car-film/scripts/11_fast_render.py` | render speed-up |
| `pipelines/car-film/scripts/12_fixes.py` | snow, fog banding, dark interior |
| `pipelines/car-film/scripts/13_speed_cine.py` | culling, 2560x1072, 180-degree rule |
| `pipelines/car-film/scripts/14_comp.py` | lens look |
| `pipelines/car-film/scripts/15_grade_speed.py` | grade, particle bake |
| `pipelines/car-film/scripts/16_grade_shot2.py` | grade for shot 2 |
| `pipelines/car-film/scripts/17_fps30.py` | 24 → 30 fps |
| `pipelines/car-film/scripts/dl_ph.py` | Poly Haven download |
| `pipelines/car-film/scripts/gen_sfx.py` | ElevenLabs effects, music |
| `pipelines/car-film/scripts/render_clay.py` | EEVEE clay setup |
| `pipelines/car-film/scripts/render_frames.py` | resumable PNG frames |
| `pipelines/car-film/scripts/render_stills.py` | a still per shot |
| `pipelines/car-film/tools/mix.sh` | ffmpeg mix, ducking |
| `pipelines/car-film/tools/preview.py` | quick still (`PREVIEW` dict) |
| `pipelines/car-film/tools/progress.ps1` | progress per shot |
| `pipelines/car-film/tools/render_all.sh` | render queue + encode |
| `pipelines/car-film/tools/stay_awake.ps1` | keeps Windows awake |

## When adapting
- Find nodes by type (`n.type == "BSDF_PRINCIPLED"`): names like `"Principled BSDF"` break in a translated UI.
- Drop `use_nodes = True` (deprecated in 5.0).
- Rename hard-coded objects and collections (`Drone Empty`, `CarRig`, `STREET`, `FX`).
- Film shot lists (camera + frame range) repeat in `09_render_opt.py`, `10_render_edit.py`, `11_motion_data.py`. Scripts 02–04 read `research/sim_shift.json`, which 01 does not write.
- `15_grade_speed.py` and `16_grade_shot2.py` expect a `Grade` node that `14_comp.py` no longer adds.

## Lessons
- A Cycles emitter with `visible_camera = False` hides its particles too; use `show_instancer_for_render = False`.
- Bake particle caches to disk, or every frame re-simulates.
- Green and purple casts look wrong at once; a pinkish grade was removed.
- Fog banding: finer volume steps plus film dither.
- Relative output paths in `blender -b` resolve to the drive root.
- Screen recorders can capture black: check the first frame.
- Viewport recordings: Material Preview needs motion blur off and volumes unlinked; Cycles viewport needs a denoiser.
- Cost: about 20% of a weekly Claude limit (Opus, high effort) for the car film.
