# Realistic forest from a tutorial

From Claude Blender Skills by Mr omi (MIT). The workflow behind a 13-second shot of a Porsche driving through a sunlit forest (2560x1440, 390 frames). The idea: don't ask Claude for a scene. Give it a long tutorial and let it follow the tutorial step by step. Claude writes the code and places the cameras; the tutorial's free assets and open-source tools make the models. Every script in `pipelines/forest/scripts/` ran for that shot; rename the scene, material and collection names inside them for yours.

## Rules for Claude
- Don't build 3D models or animation from scratch. Use the tutorial's free assets or open-source ones.
- Do what Claude is good at: scripts, scatter systems, camera moves, render settings.
- Write your own code. Don't install add-ons or run scripts you haven't read (a paid scatter add-on and a car-rig add-on were both replaced by our own code).
- After every stage, render a small test still next to the reference frame. Fix what is off before moving on.
- Hand render-and-compare loops to a cheaper sub-agent (Sonnet) with a tight brief; read only its short report.
- Say how long a render will take before starting it. Keep the PC usable: below-normal priority, 8 threads, texture limit 2048 for tests.

## Steps
| # | Step | What happens |
|---|---|---|
| 0 | Setup | Blender 5.x (made on 5.2), an NVIDIA GPU (OptiX), Python 3, `ffmpeg`. Project `~/blender-forest` with `scene/`, `assets/`, `research/`, `render/`. Copy `pipelines/forest/scripts/` there as `scripts/` (`build_car.py` and `build_shots.py` find `assets/` and `quarantine/` beside it). Run from the project: `blender -b scene/forest.blend --python ./scripts/build_path.py`; live, use `scripts/blender_send.py` |
| 1 | Pick the tutorial | A long (1 h+) Blender environment tutorial that gives its assets away. "Go watch his video. We are going to recreate his scene exactly as he did." |
| 2 | Claude watches it | Download the transcript and read all of it. Capture the first 30 s at 30 fps, build contact sheets, detect the cuts. Write the shot plan: every shot, its camera move and length, plus the build stages. If YouTube blocks command-line downloaders with a bot check, grab frames and the transcript through the browser |
| 3 | Assets and safety | `asset-safety`: one folder per archive, list and virus-scan, open headless with `--disable-autoexec`, `scripts/blend_audit.py` must report `"pass": true` and 0 linked libraries; results in the project's `SECURITY.md` |
| 4 | Build in stages | One resumable script per stage, the .blend saved after each. Rebuild order: `build_world.py` -> `pipelines/forest/scripts/scatter.py` -> `build_path.py`. Look-dev: `camset.py` + `test_still.py` (960x540). 32 samples is fine for layout, but the denoiser smears gravel: judge textures at 128 |
| 5 | Pivot when it looks dull | The tutorial's cabins looked dull in our build, so we dropped them and switched to its car clip (19-32 s, 390 frames, 4 shots). Don't polish something that doesn't work |
| 6 | The car | `build_car.py`: the tutorial's Porsche + our own rig. It follows the path, wheels spin with distance travelled, front wheels steer into the curve, the body bounces slightly. `car.json` holds path and speed |
| 7 | Camera shots | Capture every frame of the target clip; a sub-agent measures each shot (camera height, lens, fisheye, speed, cut times). `build_shots.py` builds them from `shots.json`: a slow truck through leaves, a locked wide with the car crossing, a camera rigid on the car's rear corner with a fisheye, a top-down follow |
| 8 | Look pass | `look.py` reads everything from `look_params.json` (haze, sun dapples, DOF, motion blur, colour, denser ground cover). Change the JSON, not the script |
| 9 | Render | Benchmark, then render overnight (table below, method in `long-renders`) |
| 10 | Sound | The render is silent. Real recorded CC0 effects (BigSoundBank) sounded better than generated ones: ambience, the car passing, onboard, whooshes. Mix in `film-sound` |

## Scatter: which script
`scripts/scatter.py` (see `blender-environment-kits`) is the general scatter tool, one layer per call. `pipelines/forest/scripts/scatter.py` is the layered example that replaced the paid add-on: one layer table with the tutorial's densities and scales, a density attribute per layer, 560k to 730k instances built in about 15 s, because everything stays an instance.

## Car rig part names
The rig expects 9 objects: `mycar_body`, `mycar_wheel.Ft.R`, `mycar_wheel.Ft.L`, `mycar_wheel.Bk.R`, `mycar_wheel.Bk.L`, `mycar_wheelbrake.Ft.R`, `mycar_wheelbrake.Ft.L`, `mycar_wheelbrake.Bk.R`, `mycar_wheelbrake.Bk.L`.

## Render result
| Measure | Result |
|---|---|
| `bench.py`, 128 samples + OpenImageDenoise vs 256 samples | looks the same, about 45% faster (51 s -> 28 s a frame) |
| Persistent data | on: the forest is built once and stays in GPU memory between frames |
| Final, 390 frames at 2560x1440 | about 3 hours overnight, resumes after a power cut |
| Clay preview (Workbench), whole clip | about 4 minutes |

## Paid sound
`gen_sfx.py` generates effects through ElevenLabs, which costs money: confirm with the user first. The key comes only from `ELEVENLABS_API_KEY`.

## Files
| File | What it does |
|---|---|
| `pipelines/forest/scripts/build_world.py` | terrain, ground material, HDRI world with a light-path split, sun, colour management |
| `pipelines/forest/scripts/layout.py` | shared layout every stage reads: road spline (3.5 m gravel), clearing, sun angle |
| `pipelines/forest/scripts/scatter.py` | layered GN scatter from the plant library, everything instanced |
| `pipelines/forest/scripts/build_path.py` | gravel ribbon + pad on the terrain, wobbly middle band, transparent edge fade, leaf litter |
| `pipelines/forest/scripts/build_car.py` | appends the car's 9 parts, drops its armature, bakes the drive per frame |
| `pipelines/forest/scripts/car.json` | start distance, direction, lateral offset, speed keys (frame, m/s) |
| `pipelines/forest/scripts/build_shots.py` | one animated camera per shot, lens, DOF, per-shot sun, hero props, cut markers |
| `pipelines/forest/scripts/shots.json` | 30 fps, 390 frames, 4 shots: start/end pose, lens or fisheye, f-stop, focus, shake, sun |
| `pipelines/forest/scripts/look.py` | look pass: sun, world, haze from the mist pass, glare, grade, vignette, DOF |
| `pipelines/forest/scripts/look_params.json` | the look numbers, scatter density multipliers, materials |
| `pipelines/forest/scripts/camset.py` | look-dev camera from `CAM="x,y,height,yaw,pitch,lens"` |
| `pipelines/forest/scripts/test_still.py` | cheap still (32 samples, 960 px default); doesn't save |
| `pipelines/forest/scripts/render_frames.py` | chosen frames at given samples and width; doesn't save |
| `pipelines/forest/scripts/bench.py` | same frames, Cycles settings from `BENCH` JSON, seconds per frame |
| `pipelines/forest/scripts/preview.py` | fast 4-sample animation to check timing and cuts, resumable |
| `pipelines/forest/scripts/render_clay.py` | grey Workbench clay of the clip, 1280x720, resumable; `--test` times one frame |
| `pipelines/forest/scripts/render_final.py` | 2560x1440 PNGs, 128 samples + OIDN, motion blur, skips frames on disk |
| `pipelines/forest/scripts/render_final.cmd` | Windows launcher: deletes empty placeholder frames, runs `look.py` + `render_final.py` |
| `pipelines/forest/scripts/watch_render.ps1` | frames done, speed, time left |
| `pipelines/forest/scripts/stay_awake_encode.ps1` | keeps the PC awake (no settings changed), then makes the MP4 |
| `pipelines/forest/scripts/gen_sfx.py` | paid ElevenLabs sound effects, standard library only |

## Start prompt
"Go watch this video: [tutorial link]. We're going to recreate his scene exactly on my GPU. Capture the transcript and the first 30 seconds at 30 fps, write the shot plan, then tell me which assets to download. Follow the blender-forest rules in the blender-suite skill."
