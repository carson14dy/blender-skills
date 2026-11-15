# 001 · GPU baseline on the user's PC

| | |
|---|---|
| Track | T2 |
| Session | local (Omen, Windows) |
| Date | |
| Status | planned |

## Question

How fast and how good are the web app and the Blender pipeline on a real GPU, and does everything work on Windows?

## Method

Run these in a local Claude Code session at the repository root, on branch `rooftec-lab`.

1. `node lab/tools/doctor.mjs`: paste the output under Result.
2. `cd roof-visualizer && npm install && npm test`
3. `blender -b --factory-startup --python roof-blender/tests/test_roof_core.py` (use the full path to blender.exe if it is not on PATH; doctor prints it)
4. `npm start` in `roof-visualizer`. In the browser, note:
   - time until the house appears
   - whether orbiting feels smooth at Quality "High" and "Ultra"
   - Render tab: Snapshot 3840×2160 with Layers view on (time shown in the dialog)
   - Render tab: turn on Path tracing, wait until about 256 samples, and note the time, then take a 1920×1080 snapshot with 128 samples
5. Blender with blender-mcp connected (Blender open, MCP addon connected):
   ```
   node roof-blender/scripts/roof-blender.mjs demo
   node roof-blender/scripts/roof-blender.mjs layers
   node roof-blender/scripts/roof-blender.mjs still --output out/omen-4k.png --samples 256 --resolution 3840x2160
   ```
   Note the render time Blender reports.
6. Headless video, 1080p:
   ```
   node roof-blender/scripts/roof-blender.mjs video --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --plan roof-visualizer/viewer/plans/storm-replacement.json --output out/build-1080p.mp4 --resolution 1920x1080 --samples 64
   ```
7. Save small JPGs, at most 1600 px wide, of the best snapshot and render in `img/`.

## Result

_To fill in: GPU model, Blender version, doctor output, the timings above, anything that failed on Windows._

## Decision

_To fill in._
