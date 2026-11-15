# RoofTec lab (branch `rooftec-lab`)

Research and testing sandbox for RoofTec 3D-home features before they go into the app: supplier materials on the roof, render resolution and accuracy, interactive layers, the AI build sequence, and the exploded layers view. Work here may be rough. Anything that proves out moves to `main` (as a skill) or to the app through a small, separate pull request.

Start every session by reading `lab/LOG.md` (newest entry first) and `lab/GOALS.md`.

## Layout

- `roof-visualizer/`: Roof Layer Studio, the Three.js web app ([SKILL.md](roof-visualizer/SKILL.md))
- `roof-blender/`: the same layer stack in Blender ([SKILL.md](roof-blender/SKILL.md))
- `lab/GOALS.md`: research tracks, what "done" means, experiment backlog
- `lab/LOG.md`: running hand-off log between sessions, newest first
- `lab/experiments/NNN-short-name/`: one folder per experiment, started from `lab/experiments/_template/`
- `lab/tools/`: test harness (environment check, screenshots, snapshots, Blender stand-ins)
- `docs/ROOFTEC-OPEN-SOURCE.md`: license-checked tools and supplier image rights

## Two kinds of sessions: pick the right one

| | Cloud session | Local session (the user's Windows PC, "Omen") |
|---|---|---|
| Has | Linux, Node, Chromium with software WebGL, `pip install bpy` (Blender as a Python module, CPU only), ffmpeg | Real GPU, Blender with its UI and the blender-mcp addon, real RoofTec house models, the user watching |
| Good for | code, research, unit tests, headless Blender checks, documentation | GPU timings, path tracing at real speed, Cycles renders, testing on real houses, judging how things look |
| Slow or impossible | anything GPU-bound; WebGL renders take seconds per frame | nothing in particular |

When a task needs the other kind of session, write it under **Needs local** or **Needs cloud** in `lab/LOG.md` with exact steps.

## Working rules

1. `git pull origin rooftec-lab` before starting; commit small, push often. Never force-push this branch.
2. One experiment per folder. Its README states the question, method, result (numbers, small images) and decision. Fill in the result even when the experiment fails.
3. Keep images small: JPG, at most 1600 px wide. Full renders, videos and `.blend` files go in an `out/` folder (git-ignored) or are attached elsewhere.
4. End every session with a `lab/LOG.md` entry: date, cloud or local, what changed, results, next steps, needs.
5. Do not commit supplier images unless their rights are recorded (see roof-visualizer/SKILL.md, "Supplier images: rights").
6. To promote a change: branch from `main`, copy only that change, open a pull request. Do not merge `rooftec-lab` into `main`.

## Commands

```bash
node lab/tools/doctor.mjs                       # what this machine can run, and what is missing
cd roof-visualizer && npm install && npm test   # unit tests (Node 18+)
cd roof-visualizer && npm start                 # web app at http://127.0.0.1:8080
python roof-blender/tests/test_roof_core.py     # Blender core checks with pip bpy (cloud)
blender -b --factory-startup --python roof-blender/tests/test_roof_core.py   # same, with real Blender (local)
node lab/tools/capture.mjs --url "http://127.0.0.1:8080/?quality=standard" --shots finished,layers,cutaway,midbuild --out lab/experiments/NNN-name/img
node lab/tools/snapshot.mjs --url "http://127.0.0.1:8080/" --size 3840x2160 --explode --out out/roof-4k.png
```

Cloud only: `bash lab/tools/setup-cloud.sh` creates a Python venv with `bpy` (about 430 MB download) and prints the paths to use.

## Conventions

- Units are metres inside the code, inches and feet in anything a contractor reads.
- The web viewer and Blender share the plan JSON format (`roof-visualizer/viewer/plans/`) and the layer ids (`deck`, `dripEdge`, `iceWater`, `underlayment`, `starter`, `nails`, `covering`, `ridgeVent`, `ridgeCap`, `oldShingles`, `oldFelt`, `deckRepair`).
- Pinned web dependencies live in the import map in `roof-visualizer/viewer/index.html`. Bump them deliberately, in their own experiment.
