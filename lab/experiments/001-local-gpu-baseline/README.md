# 001 · GPU baseline on the user's PC

| | |
|---|---|
| Track | T2 |
| Session | local (Omen, Windows) |
| Date | _fill in_ |
| Status | planned |

## Question

How fast and how good are the web app and the Blender pipeline on a real GPU, and does everything work on Windows?

## Before you start (local Claude session, read this)

- Work from the repository root (`blender-skills`) unless a step says otherwise.
- Long commands (the web server, Blender renders, the video) must run **in the background**, or they will outlast your command timeout. Check on them afterwards.
- Timings come from the `RT_RESULT` lines that `roof-blender.mjs` prints (`seconds`, `device`, `blender`). The first GPU render loads kernels, so run each Blender render twice and record the second.
- Some steps need the user's eyes (how smooth orbiting feels, how the roof looks). Ask the user those questions directly; do not guess.
- If a step fails, write down the exact error under Result, try the fix doctor or the error suggests once, and move on.

## Method

1. **Environment check**
   ```
   node lab/tools/doctor.mjs
   ```
   Paste the output under Result. Every line marked `NO` has its fix printed under "To fix". Do those first (see `lab/NEXT.md`, "Set up this PC").

2. **Unit tests** (about 1 minute)
   ```
   cd roof-visualizer
   npm install
   npm test
   cd ..
   ```
   Pass when the output ends with `# fail 0`.

3. **Blender core checks** (about 1 minute). Use the Blender path doctor printed:
   ```
   & "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 --python roof-blender/tests/test_roof_core.py
   ```
   Pass when it prints `all roof_core checks passed`.

4. **Web app on the GPU**
   1. Start the server in the background:
      ```
      node roof-visualizer/scripts/serve.mjs --port 8080
      ```
   2. Check that the browser uses the GPU, not software WebGL. This needs Playwright, which is optional (see NEXT.md step 7):
      ```
      node lab/tools/snapshot.mjs --url http://127.0.0.1:8080/ --size 3840x2160 --explode --out out/omen-web-4k.png
      ```
      ```
      node lab/tools/snapshot.mjs --url http://127.0.0.1:8080/ --size 1920x1080 --pt 128 --out out/omen-web-pt.png
      ```
      Each prints the WebGL renderer and the time. Run both twice and record the second time.
   3. Ask the user to open http://127.0.0.1:8080 and answer:
      - How long until the house appears?
      - Is orbiting smooth at Render > Quality "High" and "Ultra"?
      - Does Layers view (key E) look right at their usual window size?
      - With path tracing on, about how many seconds until the image looks clean?

5. **Blender with MCP for Blender**
   1. Ask the user to open Blender on an empty General scene; the addon starts its server.
   2. Run:
      ```
      node roof-blender/scripts/roof-blender.mjs demo
      ```
      ```
      node roof-blender/scripts/roof-blender.mjs layers
      ```
   3. Run this one twice and record the second `seconds`:
      ```
      node roof-blender/scripts/roof-blender.mjs still --output out/omen-4k.png --samples 256 --resolution 3840x2160
      ```

6. **Headless build video**, in the background. This renders about 155 frames (13 s of video), so expect minutes, not seconds:
   ```
   node roof-blender/scripts/roof-blender.mjs video --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --plan roof-visualizer/viewer/plans/storm-replacement.json --output out/build-1080p.mp4 --resolution 1920x1080 --samples 64 --speed 4 --frame-step 2
   ```
   Record `seconds_per_frame` and the device from its result line, and check the video plays.

7. **Small images for the write-up** (at most 1600 px wide):
   ```
   ffmpeg -y -i out/omen-4k.png -vf scale=1600:-2 -q:v 3 lab/experiments/001-local-gpu-baseline/img/omen-blender-4k.jpg
   ```
   ```
   ffmpeg -y -i out/omen-web-4k.png -vf scale=1600:-2 -q:v 3 lab/experiments/001-local-gpu-baseline/img/omen-web-4k.jpg
   ```

## Result

_To fill in._ Include:
- the GPU and Blender version
- the doctor output
- a table of each step's timing (web 4K, web path tracing, Blender 4K still, video seconds per frame)
- the user's answers from step 4
- anything that failed on Windows, with the exact error

## Decision

_To fill in:_ what is fast enough for live sales use, and what needs work.

## Report back (checklist)

1. Set Date and Status (`done`) above, and fill in Result and Decision.
2. Add a `lab/LOG.md` entry at the top: date, `local`, what changed, results, next, needs.
3. Tick the item in `lab/NEXT.md`.
4. Commit only text and the small images. Renders, videos and `.blend` files stay in `out/`, which git ignores.
   ```
   git add lab
   git commit -m "Lab: experiment 001 results (local)"
   git push origin rooftec-lab
   ```
5. Tell the user it is pushed, so they can ask the cloud session to "check the lab log".
