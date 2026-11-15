---
name: roof-blender
description: Rebuild a house's roof in Blender as real roofing layers (deck, drip edge, ice & water, underlayment, starter, nails, stepped shingle courses, ridge vent, caps), put a supplier photo or color on the shingles at true scale, and render high-resolution Cycles stills, a tear-off-to-finish build video, or an exploded layers animation. Trigger when asked for a photoreal or 4K roof render, a roof replacement video, an installation animation, an exploded roof diagram in Blender, or to apply a supplier shingle image to a house model in Blender.
---

# Roof layers in Blender (roof-blender)

Cycles companion to [roof-visualizer](../roof-visualizer/SKILL.md). Same geometry rules and the same build-plan JSON, but rendered with path tracing, real nail and course-step geometry, and Blender's physical sky, at any resolution.

## Prerequisites

- Blender 4.2 LTS or 5.x (tested headless with Blender 5.2.4 LTS)
- Either the [blender-mcp](https://github.com/ahujasid/blender-mcp) addon connected on port 9876 (Blender open), or `--blender <path to blender>` to run headless
- ffmpeg for `video` / `exploded-video`
- The house in Blender with its roof object named `Roof` (or pass `--roof <name>`). Without one, `demo` builds a ranch with a hip roof and a front-gable garage.

## Commands

```bash
# in the open Blender (blender-mcp)
node roof-blender/scripts/roof-blender.mjs demo --pitch 6                # only if there is no house yet
node roof-blender/scripts/roof-blender.mjs layers --ice-rows 2 --nails 6
node roof-blender/scripts/roof-blender.mjs material --image ~/swatches/pewter.jpg --width-in 36
node roof-blender/scripts/roof-blender.mjs still --output ~/Desktop/roof-4k.png --samples 256 --resolution 3840x2160

# headless (best for long renders; leaves the UI free or runs on a render box)
node roof-blender/scripts/roof-blender.mjs video --blender /Applications/Blender.app/Contents/MacOS/Blender \
  --file house.blend --plan roof-visualizer/viewer/plans/storm-replacement.json \
  --output ~/Desktop/build.mp4 --resolution 1920x1080 --samples 64
node roof-blender/scripts/roof-blender.mjs exploded-video --blender blender --file house.blend --output ~/Desktop/layers.mp4 --gap 0.8
node roof-blender/scripts/roof-blender.mjs export --output roof-visualizer/viewer/house.glb   # open in the web viewer with ?glb=house.glb
```

`node roof-blender/scripts/roof-blender.mjs --help` lists every option. The main ones:

| Option | Meaning | Default |
|---|---|---|
| `--roof` | roof object name | `Roof`, else any object named roof/shingle, else slope detection |
| `--ice-rows` / `--no-valleys` | ice & water rows at eaves / skip valley strips | 2 / valleys on |
| `--nails` | nails per shingle (4 or 6) | 6 |
| `--no-vent`, `--no-old-roof` | skip ridge vent / skip the existing roof layers | |
| `--image`, `--width-in`, `--height-in`, `--rotation`, `--relief` | supplier photo and its real size | |
| `--palette "#hex,#hex,..."` | procedural shingle colors instead of a photo | charcoal blend |
| `--samples`, `--resolution`, `--percentage` | Cycles quality | 192, 3840x2160, 100 |
| `--sun-elevation`, `--sun-azimuth` | sun position (degrees) | 38, 215 |
| `--view-azimuth`, `--view-elevation`, `--distance`, `--lens` | camera | -35, 24, 1.0, 35 |
| `--plan`, `--speed`, `--fps`, `--no-orbit` | build animation | built-in plan, 1, 24, orbit on |
| `--save out.blend` | save the result (headless) | |

Headless runs that start without `--file` clear the startup scene and build the demo house; with `--file` they build the layer stack if it is missing.

## How it works

`scripts/roof_core.py` runs inside Blender (sent through blender-mcp, or with `blender -b -P roof_core.py -- cfg.json`):

- Roof faces are clustered into planes; each plane gets an eave-aligned (u, v) frame; edges are classified into eaves, rakes, ridges, hips and valleys by adjacency and convexity.
- Each layer is a mesh `RT_layer_<id>` in collection `RT_Layers` with a `UVMeters` UV map (metres, so image textures are true size) and two point attributes, `rt_up` and `rt_along`.
- Each material has a `RT_Reveal` value node: a face shows while `floor(rt_up / row) + rt_along < RT_Reveal`. Keyframing that value lays shingles course by course, left to right, and tears off from the ridge down, matching the web viewer.
- `explode` keyframes layer heights (closed, open, hold, close) and adds text labels that face the camera.
- Scene: Cycles (GPU if available), AgX, physical sky (`MULTIPLE_SCATTERING` on Blender 5, `NISHITA` on 4.x) plus a sun lamp, ground plane, camera on a pivot that orbits during builds.

Results are printed as `RT_RESULT {json}` lines.

## Tests

```bash
blender -b --factory-startup --python roof-blender/tests/test_roof_core.py
# or: pip install bpy && python roof-blender/tests/test_roof_core.py
```
