# RoofTec houses and roofs

How this skill fits the RoofTec lab in this repository. The roof itself is built elsewhere: this page says where, and what this skill adds around it. Repo rules and session roles are in the repo's `CLAUDE.md`.

## The roof is not built here
Roof geometry, the layer stack (deck to ridge cap), supplier materials at true scale, the build video and the exploded layers view live in `roof-blender/SKILL.md` and `roof-blender/scripts/roof-blender.mjs`. Use them to build or change a roof. The web viewer is `roof-visualizer/`. Both share the plan JSON format and the layer ids.

## What this skill adds

| Roof task | Use |
|---|---|
| Geometry gate after any change to the layers | `lab/tools/roof_qa.py`, which calls this skill's `qa_check.py`; then a close-up with `review_shots.py` |
| Check a house model or supplier asset that came from outside | `asset-safety`, `blend_audit.py` |
| Marketing light: golden hour, overcast, dusk with lit windows | `blender-time-of-day`, `scene_mood.py --time golden` (or `sunset`, `blue_hour`) |
| Storm, rain-wet or snow-covered roof | `blender-weather-fx`, `surface_weather.py`, `precipitation.py` |
| Shingle and metal materials at true scale | `blender-pbr-materials`, `build_pbr_material.py`, `texel_density.py` |
| Hero clip of a finished roof | `blender-camera-moves`, `camera_move.py`; orbit with `turntable.py` |
| House to the web viewer or a phone | `blender-export-pipelines`, `export_asset.py --preset web`, then open `roof-visualizer` with `?glb=<url>`; `web_viewer.py` for a one-file preview |
| GPU timings and overnight build videos on the Windows PC | `long-renders` |
| HDRI skies with clear rights | `blender-polyhaven` (CC0) |

## Repo rules for anything made here
- Metres inside code; inches and feet in anything a contractor reads.
- Images committed to the repo are JPG, at most 1600 px wide. Full renders, video and `.blend` files go in `out/` (git-ignored).
- No supplier image without recorded rights (`roof-visualizer/SKILL.md`, "Supplier images: rights").
- GPU work belongs to the local session on the Windows PC. From a cloud session, write it under "Needs local" in `lab/LOG.md` with exact steps.

## Cloud command for any script
Cloud sessions have pip `bpy`, not a Blender install. `LAB_BPY_PYTHON` is not set by default: `bash lab/tools/setup-cloud.sh` creates the Python and prints the path to export.
```
BLENDER_BPY_PYTHON=$LAB_BPY_PYTHON python .claude/skills/blender-suite/scripts/run_in_blender.py --blend out/qa/roof.blend .claude/skills/blender-suite/scripts/qa_check.py -- --profile render
```
On the local PC, `run_in_blender.py` finds the installed Blender by itself.
