---
name: blender-suite
description: Expert Blender 5.2 LTS and 5.3 workflows with tested scripts - modeling, sculpting, retopology, UVs, PBR materials, texturing, baking, geometry nodes, rigging, animation, mocap retargeting, clothing, hair, environments, lighting, time of day, weather, camera moves, rendering, overnight render queues, video, sound, simulation, add-ons, asset QA, photo to 3D, Poly Haven assets, cinematic short films, car films, realistic forests, and export to Roblox, Unity, Unreal, Godot and the web. Use this skill for anything involving Blender, bpy, .blend files, 3D models, renders or game assets, including RoofTec house and roof renders, even if the user only says "make a 3D model", "render this" or "fix my mesh", and before writing any bpy code, because Blender's Python API changed heavily in 5.x and remembered code often fails.
license: MIT
compatibility: Blender 5.2 LTS or newer, tested on 5.2.4 and with notes for 5.3. Python 3.9+ for host-side scripts. Optional - the MCP for Blender add-on for live sessions, pip bpy for cloud sessions, ffmpeg, ComfyUI with an 8 GB NVIDIA GPU for free local photo to 3D, an OpenAI or ElevenLabs key for the paid routes.
metadata:
  version: "1.0.0"
  based-on: EL4CTEO/blender-skills 1.3.1, blender-master 1.2.1, mromidev/claude-blender-skills 567116b
---

# Blender Suite

Your memory of `bpy` is probably out of date, and a mesh that looks fine in code is often wrong on screen. So use the tested scripts when one fits, check API details here before guessing, and verify with numbers and a look.

## Accuracy first
A build is done when it matches the brief, not when it looks finished. For every build, RoofTec roofs included, follow `build-accuracy`:
1. **First** write `acceptance.json`: each size, count, spacing, material and deliverable in the brief, with its source. Never assume a roof pitch: work it out (`roof-pitch`). Detail is construction grade (`construction-detail`); agree any simplification with the user before building.
2. **After each stage** run `qa_check.py` and `acceptance_check.py`, then look. Fix what fails. Never edit the file to pass.
3. **Log every shortcut** with `build_log.py` (assumed value, skipped check, preview render) and show the user the list.
Speed comes second: faster is fine only if the checks still pass.

## Finding things
- Paths in these documents are relative to this skill's folder, written `<skill_dir>`. When you run a script, give its full path, because the working directory is usually the user's project. In this repo the folder is `.claude/skills/blender-suite`.
- A name in backticks such as `blender-asset-qa` or `long-renders` means `references/<name>.md`. A mention of `SKILL.md` means this file.
- Read only the reference for the task at hand. They hold the procedures, numbers and gotchas.
- `look`, `generate_3d`, `import_asset`, `search_assets` and `world_bounding_box` are tools that some Blender MCP servers offer. Use whatever your server has. Without them, use `review_shots.py` to look, `gpt_model_spec.py` and `build_from_spec.py` to generate, `polyhaven_fetch.py` for assets, and `ob.dimensions` or `ob.bound_box` for size.
- `tests/` is only in the repository copy. A packaged `.skill` carries just `tests/check_skill.py`.
- A bare script name means `scripts/<name>`. Files under `pipelines/` are the real scripts from three finished films. They are tied to those scenes, so read them, copy the folder into the project and adapt it. They are the one exception to the next rule.
- **Run scripts instead of reading them.** Each one documents its flags in its docstring and prints one compact JSON result. They are large.

## Route the task
| Task | Read | Main scripts |
|---|---|---|
| Complete asset, start to finish | `blender-workflow-recipes` | chains the others |
| Units, naming, collections, asset libraries | `blender-scene-setup` | `scene_audit.py` |
| Hard-surface modeling, bevels, booleans | `blender-hardsurface-modeling` | `apply_stack.py` |
| Sculpting, remesh, multires | `blender-sculpting` | `sculpt_ops.py` |
| Retopology, UVs, texel density | `blender-retopology-uv` | `auto_retopo.py`, `uv_pack.py`, `texel_density.py` |
| PBR materials, color spaces, texture sets | `blender-pbr-materials` | `build_pbr_material.py` |
| Wear, grime, decals, trim sheets, painting | `blender-texturing` | `smart_material.py`, `decal.py` |
| Baking normal, AO, curvature, ORM | `blender-texture-baking` | `bake_maps.py` |
| Geometry Nodes, procedural modeling | `blender-geometry-nodes` | `gn_builder.py` |
| Body rigging, Rigify, weights | `blender-character-rigging` | `rigify_build.py`, `bind_mesh.py`, `stress_poses.py`, `rig_check.py` |
| Face rig, shape keys, ARKit, visemes | `blender-facial-shapekeys` | `shapekeys.py` |
| Keyframes, NLA, mocap, Mixamo, loops, root motion | `blender-animation` | `retarget.py`, `bake_action.py`, `loop_check.py` |
| Garments, layered clothing, poke-through | `blender-clothing` | `garment.py` |
| Hair, fur, hair cards | `blender-hair-grooming` | `groom.py` |
| Poly budgets, LODs, draw calls | `blender-game-optimization` | `mesh_stats.py`, `make_lods.py` |
| Export to engines and the web | `blender-export-pipelines` | `export_asset.py`, `web_viewer.py` |
| Cycles and EEVEE settings, batch render, video encoding | `blender-rendering` | `render_batch.py` |
| Studio light, HDRI, looping turntable | `blender-lighting-lookdev` | `turntable.py` |
| Push-in, dolly, crane, speed-ramp shots | `blender-camera-moves` | `camera_move.py` |
| Poly Haven assets, HDRI or material comparison grids | `blender-polyhaven` | `polyhaven_fetch.py`, `variant_renders.py` |
| Photo to 3D model, free and local | `blender-image-to-3d` | `trellis_generate.py`, `import_generated.py` |
| Toon, anime, outlines, Grease Pencil | `blender-stylized-npr` | `toon_setup.py` |
| Terrain, biome scatter, modular kits | `blender-environment-kits` | `terrain.py`, `scatter.py`, `kit_check.py` |
| Video editing, motion tracking | `blender-video-editing` | `vse_edit.py`, `track_camera.py` |
| Short film, multi-shot story, car film, clay build-up reveal | `blender-film` | `pipelines/film/`, `pipelines/car-film/` |
| Realistic forest or environment rebuilt from a tutorial, car in nature | `blender-forest` | `pipelines/forest/` |
| Overnight renders, render benchmarks, resumable queues, progress windows | `long-renders` | `render_batch.py`, pipeline tools |
| Sound effects, sound driven by the motion, final mix | `film-sound` | `vse_edit.py`, pipeline tools |
| Checking a downloaded .blend or asset pack before use | `asset-safety` | `blend_audit.py` |
| RoofTec houses and roofs in this repo | `rooftec` | `qa_check.py`, `scene_mood.py`, `export_asset.py` |
| Time of day, night, fog, moods | `blender-time-of-day` | `scene_mood.py` |
| Rain, snow, wet surfaces, lightning | `blender-weather-fx` | `precipitation.py`, `surface_weather.py`, `lightning.py` |
| Rigid body, cloth, fluids | `blender-simulation` | `sim_setup.py` |
| Writing add-ons and extensions | `blender-addon-development` | `assets/addon_template/` |
| Batch jobs, file conversion, CI | `blender-pipeline-automation` | `batch_process.py` |
| Checking any asset before delivery | `blender-asset-qa` | `qa_check.py`, `review_shots.py` |

AttributeError or KeyError: read `references/api-changes-5x.md`. Verified bmesh, attribute, numpy, driver and keyframe snippets: `references/bpy-patterns.md`.

## Run code
**Live, in the user's open Blender.** With a Blender MCP server, use `execute_blender_code`. Without one, the MCP for Blender add-on still listens on `127.0.0.1:9876` while Blender is open, and this sends to it:
```
python <skill_dir>/scripts/blender_send.py -c "print(bpy.data.filepath)"
python <skill_dir>/scripts/blender_send.py step1.py step2.py     # in order; names from step1 stay defined
```
Work in small steps and print only what you need. To call a skill script, import it by absolute path:
```python
import sys, importlib; sys.path.insert(0, r"<skill_dir>/scripts")
import qa_check; importlib.reload(qa_check); print(qa_check.run(objects=["Chair"]))
```
An MCP call starts with a fresh namespace, so import again each time. Never render inside the live window: save, then render headless.
**Headless, from any shell.** The wrapper finds Blender and prints only the script's JSON:
```
python <skill_dir>/scripts/run_in_blender.py --blend in.blend <skill_dir>/scripts/qa_check.py -- --objects Chair
python <skill_dir>/scripts/run_in_blender.py --blend in.blend --expr "import bpy; bpy.data.objects['X_high_low'].name='SM_X'; bpy.ops.wm.save_mainfile()"
```
`--blend` paths resolve from the working directory. Scripts that change the scene take `--save out.blend`; read-only checks don't. Each headless run starts from the saved file, so save between steps. Use `--expr` for small jobs with no script (rename an object, set the resolution), and save inside the expression.
Set `BLENDER_EXE` if Blender isn't found. Documents write commands as `scripts/x.py -- --flags`, which means either form above. `build_log.py`, `trellis_generate.py`, `gpt_model_spec.py`, `polyhaven_fetch.py`, `web_viewer.py` and `blender_send.py` are plain Python and run without Blender.
**Cloud sessions have no Blender.** Set `BLENDER_BPY_PYTHON` (or this repo's `LAB_BPY_PYTHON`) to a Python that has the pip `bpy` module and the same commands work. When you start such a Python yourself, `import bpy` first, because `bmesh`, `mathutils` and `addon_utils` only resolve after it.
**Windows with Git Bash:** MSYS rewrites `//out.png` to `/out.png`. Prefix the command with `MSYS_NO_PATHCONV=1`, or use PowerShell.

**First call in a session:** run `scripts/env_report.py` (Blender version, engines, GPU, add-ons, units, color management, scene counts). Below 5.2, tell the user, because these scripts target 5.2.

## Writing bpy yourself
- **Prefer the data API to operators.** Use `bpy.data`, `bmesh`, `mesh.attributes`, and `foreach_get`/`foreach_set` with numpy. Operators depend on context and selection, and many need a 3D View that background mode doesn't have.
- **If an operator is unavoidable**, wrap it: `with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):` and check that it returned `{'FINISHED'}`.
- **Find nodes by type** (`n.type == "BSDF_PRINCIPLED"`), never by name, because names are localized.
- **Edit Mode:** `ob.data` isn't updated while editing. Use `bmesh.from_edit_mesh` and `bmesh.update_edit_mesh`, or switch to Object Mode before reading.
- **Evaluated data:** `ob.evaluated_get(depsgraph)`, then `.to_mesh()`, and always `.to_mesh_clear()`. Call `view_layer.update()` before reading `matrix_world` after a change.
- **Freed data:** removing a modifier, object or ID frees it. Old Python references then return garbage or crash, so collect names first.
- **Default names lie** ("Cube.001"). Keep object references or rename explicitly.
- **Enums:** read valid values with `[i.identifier for i in T.bl_rna.properties[p].enum_items]`. Dynamic enums such as `render.engine` under-report, so assign inside `try/except TypeError`.
- **Paths:** `bpy.path.abspath("//textures/x.png")` is relative to the .blend. In headless batches, use absolute paths.
- **Sculpt Mode operators crash in background mode.** Use `sculpt_ops.py` instead.

## Common 5.x changes
| Old code or memory | Now |
|---|---|
| `action.fcurves` | `from bpy_extras import anim_utils`. To read, use `action_get_channelbag_for_slot(action, slot)`, which can return None. To write, use `action_ensure_channelbag_for_slot(action, slot)`. Then `.fcurves`, with `slot = ob.animation_data.action_slot` |
| `scene.node_tree`, `scene.use_nodes` | `scene.compositing_node_group` |
| `material.use_nodes = True` | deprecated, new materials already have nodes |
| `mod["Socket_2"]` | `mod.properties.inputs.Socket_2.value` (5.2) |
| `BLENDER_EEVEE_NEXT` | `BLENDER_EEVEE` |
| Boolean solver `FAST` | `FLOAT`, plus `EXACT` and `MANIFOLD` |
| `mesh.use_auto_smooth` | Smooth by Angle (`shade_auto_smooth`) |
| Bone layers | bone collections |
| `bl_info` add-ons | extensions with `blender_manifest.toml` |
| `file_format = "FFMPEG"` alone | set `image_settings.media_type` first |
| `bgl` | `gpu`. Call `gpu.init()` first in background mode (5.2) |
| Principled `Specular`, `Transmission`, `Coat` | `Specular IOR Level`, `Transmission Weight`, `Coat Weight` |
| 5.3 compositor, glTF WebP flag, VSE `EXPAND` | changed: `references/api-changes-5x.md` |

## What makes results look professional
- **Real scale.** 1 unit = 1 m. Check `ob.dimensions`. Apply rotation and scale before bevels, rigging, physics, baking and export. Wrong scale breaks modifiers, light falloff, depth of field and texel density.
- **Materials** (`blender-pbr-materials`): metallic is 0 or 1, base color has no lighting in it, roughness varies. Base color and emission are sRGB, other maps Non-Color. Unreal normals are DirectX: flip green. Game engines only get image textures, so bake procedural nodes.
- **Silhouette and proportions first,** then secondary forms, then small details. A blockout is a stage, not a result.

## Respect the user's work and accounts
- A live Blender session is the user's work. Don't reset to factory settings or delete data you didn't create, and save a backup copy before destructive batch edits.
- Photo to 3D starts with `trellis_generate.py`, which is free and keeps the photo on this PC. A run can use nearly all the graphics memory, so ask the user to save their work first, and never close their programs for them.
- `gpt_model_spec.py` is the last resort. It uploads the user's photos to OpenAI and is billed to their API account, so confirm first and show a `--dry-run`. Say up front that the result is a part-based model, not a textured scan. The key comes only from the `OPENAI_API_KEY` environment variable. Never write it into a command, file or message.
- Ask before any long render, and say how long it will take. Test at low quality first, then deliver at final quality (`long-renders`).
- `gen_sfx.py` in `pipelines/car-film/scripts/` and `pipelines/forest/scripts/` calls ElevenLabs, a paid service, so confirm first. The key comes only from `ELEVENLABS_API_KEY`.

## Before saying "done"
1. **Report numbers, not adjectives:** triangles, objects, materials, dimensions, and files written.
2. **If geometry changed,** run `qa_check.py`. Fix every error, and fix or explain each warning.
3. **Look at it.** Use the MCP's viewport or screenshot tool from several angles, in material and wireframe shading. Without one, run `review_shots.py` and open the PNG it returns. Numbers miss proportion and shading problems.
4. **Check the output exists:** confirm exported files are there with a non-zero size, then re-import or read the summary.
5. **Say what you didn't verify, simplified or assumed.** A build also needs `"done": true` from `build_log.py close`; paste its report.
