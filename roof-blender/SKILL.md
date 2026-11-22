---
name: roof-blender
description: Rebuild a house's roof in Blender as real roofing layers (deck, drip edge, ice & water, underlayment, starter, nails, stepped shingle courses, ridge vent, caps), put a supplier photo or color on the shingles at true scale, and render high-resolution Cycles stills, a tear-off-to-finish build video, or an exploded layers animation. Trigger when asked for a photoreal or 4K roof render, a roof replacement video, an installation animation, an exploded roof diagram in Blender, or to apply a supplier shingle image to a house model in Blender.
---

# Roof layers in Blender (roof-blender)

Cycles companion to [roof-visualizer](../roof-visualizer/SKILL.md). Same geometry rules and the same build-plan JSON, but rendered with path tracing, real nail and course-step geometry, and Blender's physical sky, at any resolution.

## Prerequisites

- Blender 4.2 LTS or 5.x. The core checks pass on Blender 5.2.4 LTS and 4.2.0, as the pip `bpy` module; not yet run on a desktop install with a GPU (lab experiment 001).
- Either the [MCP for Blender](https://github.com/ahujasid/blender-mcp) addon (formerly blender-mcp) with Blender open, or `--blender <path to blender>` to run headless.
  - Install the addon with `uvx mcp-for-blender install-addon`. It starts its server on port 9876 when Blender opens.
  - This CLI talks to that port directly, so Claude needs no MCP server entry for it.
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
| `--nails` | nails per shingle (4 standard, 6 high wind) | 4 |
| `--category` | `shingle` or `metal` (flat panels, concealed clips, no starter) | shingle |
| `--panel` | metal panel profile with real ribs: `proRib`, `proSnap`, `corrugated` or `flat` (cfg `panel`) | flat |
| `--cap-width-in` | metal hip and ridge cap product width; each side gets half (cfg `cap_width_in`) | 12 |
| `--edge "flange,face,kickOut,kickDown,hem"` | drip-edge profile in inches, from the drip-edge product (cfg `edge_profile`) | today's shape |
| `--no-vent`, `--no-old-roof` | skip ridge vent / skip the existing roof layers | |
| `--image`, `--width-in`, `--height-in`, `--rotation`, `--relief` | supplier photo and its real size | |
| `--palette "#hex,#hex,..."` | procedural shingle colors instead of a photo | charcoal blend |
| `--samples`, `--resolution`, `--percentage` | Cycles quality | 192, 3840x2160, 100 |
| `--sun-elevation`, `--sun-azimuth` | sun position (degrees) | 38, 215 |
| `--view-azimuth`, `--view-elevation`, `--distance`, `--lens` | camera (distance 1.0 fits the whole scene) | -35, 24, 0.85, 35 |
| `--plan`, `--speed`, `--fps`, `--no-orbit` | build animation (`--speed 4` plays the plan 4x faster) | built-in plan, 1, 24, orbit on |
| `--frame-step` | render every Nth frame for previews; the MP4 keeps real time | 1 |
| `--save out.blend` | save the result (headless) | |

Headless runs that start without `--file` clear the startup scene and build the demo house; with `--file` they build the layer stack if it is missing. Headless Blender runs with `--python-exit-code 1`, so a Python error fails the command.

Every step prints one `RT_RESULT {json}` line. Renders include:
- `seconds` (and `seconds_per_frame` for videos)
- `device`, for example `OPTIX: NVIDIA ...`
- `blender` version, sample count and resolution

A run that ends without `RT_RESULT` failed.

Plan render time before you start. A full-length build at 1080p and 64 samples is over a thousand frames; use `--speed 4 --frame-step 2` for previews, and run long renders in the background.

## How it works

`scripts/roof_core.py` runs inside Blender (sent through blender-mcp, or with `blender -b -P roof_core.py -- cfg.json`):

- Roof faces are clustered into planes; each plane gets an eave-aligned (u, v) frame; edges are classified into eaves, rakes, ridges, hips and valleys by adjacency and convexity.
- Each layer is a mesh `RT_layer_<id>` in collection `RT_Layers` with a `UVMeters` UV map (metres, so image textures are true size) and two point attributes, `rt_up` and `rt_along`.
- Each material has a `RT_Reveal` value node: a face shows while `floor(rt_up / row) + rt_along < RT_Reveal`. Keyframing that value lays shingles course by course, left to right, and tears off from the ridge down, matching the web viewer.
- `explode` keyframes layer heights (closed, open, hold, close) and adds text labels that face the camera.
- Scene:
  - Cycles: GPU devices only when one is found, and 64 transparent bounces so hidden layers never render as black bands.
  - AgX colour management.
  - Physical sky (`MULTIPLE_SCATTERING` on Blender 5, `NISHITA` on 4.x) plus a sun lamp aimed where the sky draws its sun.
  - Ground plane, and a camera fitted to the vertical view (including an exploded stack and its labels) on a pivot that orbits during builds.
- The demo house uses the web viewer's 0.45 m overhang and matches its measurements: 27.4 squares on the ranch preset. The main roof is notched under the garage, so hidden roof is not counted.
- Roofs found only by slope leave the house meshes visible; name the roof object `Roof` so it can be replaced cleanly.
- Running `material` after `build` keeps the build animation.
- `layers` stores its measurements on the scene as `rt_measure`, for `roof_qa.py --expect`. They include `pitches_per_12`: each plane's rise per 12 (from its normal) and its area in m2.
- A new building hands over a mesh object named exactly `Roof`: two planes on the top of the rafters, out to the fascia and rake faces. The blender-suite `construction_kit.py` makes it and runs `{"cmd": "layers", "roof": "Roof", "old_roof": false, "deck_repair": false, "ridge_vent": ..., "ice_rows": ...}` on it. No other part of the building may have "roof" or "shingle" in its name.
- `Plane.contains2(u, v, margin)` keeps a positive margin from the plane's outer edges only, as the web studio does (it used to drop nails near the diagonals between a plane's triangles: the ranch demo has 6925 nails in both apps), and `clip_half` keeps a corner on the clip line once (no zero-area slivers).
- `deck_repair` (default true) builds the re-roof deck patches; a new build passes false. `ice_rows` 0 leaves out the eave membrane (valleys keep theirs), for an unheated building under the code exception.
- Metal panels and edge profiles (lab experiments 019 and 020):
  - `panel` picks a profile from `PANEL_PROFILES`, the same JSON text as the web studio's `profiles.js`. `ribbed_surface` slices each plane into planar strips between the profile's breakpoints, repeated from the plane's left end, so the ribs run up the slope and stand up at the eave.
  - On a metal roof the hip and ridge caps take the metal cap profile, 3 mm over the rib tops; the ridge vent and the cap over it stand on the rib tops.
  - With a profile other than `flat`, a rake trim (1.5 in. top leg, 3.5 in. face, 0.5 in. hem) is merged into the covering. Its bend sits 1/8 in. outside the drip edge's kick, and the two trims are mitered at a gable peak.
  - `edge_profile` is `{"flange_in", "face_in", "kick_out_in", "kick_down_in", "hem_in"}`. A missing key keeps today's value; without it the drip edge is unchanged.
  - Check a variant with `roof_qa.py -- --layers '{"category": "metal", "panel": "proRib"}'`.

Results are printed as `RT_RESULT {json}` lines.

## Tests

```bash
blender -b --factory-startup --python roof-blender/tests/test_roof_core.py
# or: pip install bpy && python roof-blender/tests/test_roof_core.py
$LAB_BPY_PYTHON lab/tools/roof_qa.py -- --expect report.json   # squares, planes and edge lengths against the house's measurement report (2 %)
```

Builds follow `build-accuracy` in the blender-suite skill: acceptance file first, shortcuts logged.
