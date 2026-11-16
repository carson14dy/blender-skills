# RoofTec lab (branch `rooftec-lab`)

Research and testing sandbox for RoofTec 3D-home features before they go into the app: supplier materials on the roof, render resolution and accuracy, interactive layers, the AI build sequence, and the exploded layers view. Work here may be rough. Anything that proves out moves to `main` (as a skill) or to the app through a small, separate pull request.

**Start every session with `lab/NEXT.md`**: it holds the current to-do list for each kind of session. Then read the newest entry in `lab/LOG.md`, and `lab/GOALS.md` when choosing new work.

**Local session on the user's Windows PC:** follow `LOCAL-SESSION.md`, the full runbook (setup, every local step with exact commands, wrap-up). In short: run `node lab/tools/doctor.mjs`, fix what it lists, then do the first open "Local session" item in `lab/NEXT.md`. Ask the user only for what needs their eyes or hands (opening Blender, judging how something looks, exporting a house model).

## Layout

- `roof-visualizer/`: Roof Layer Studio, the Three.js web app ([SKILL.md](roof-visualizer/SKILL.md))
- `roof-blender/`: the same layer stack in Blender ([SKILL.md](roof-blender/SKILL.md))
- `.claude/skills/blender-suite/`: the one Blender skill (modeling to rendering, films, QA); loads by itself in every session
- `lab/NEXT.md`: what each session does next, plus the Windows setup steps
- `lab/GOALS.md`: research tracks, what "done" means, experiment backlog
- `lab/LOG.md`: running hand-off log between sessions, newest first
- `lab/experiments/NNN-short-name/`: one folder per experiment, started from `lab/experiments/_template/`
- `lab/tools/`: test harness (environment check, screenshots, snapshots, Blender stand-ins)
- `docs/ROOFTEC-OPEN-SOURCE.md`: license-checked tools and supplier image rights

## Two kinds of sessions: pick the right one

| | Cloud session | Local session (the user's Windows PC, "Omen") |
|---|---|---|
| Has | Linux, Node, Chromium with software WebGL, `pip install bpy` (Blender as a Python module, CPU only), ffmpeg | Real GPU, Blender with its UI and the MCP for Blender addon (formerly blender-mcp), real RoofTec house models, the user watching |
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
graphify update .                               # rebuild the code graph (local, about 5 s); then graphify query "<question>"
python lab/tools/package_skill.py .claude/skills/blender-suite out/skills   # blender-suite as a .skill file for claude.ai
cd roof-visualizer && npm install && npm test   # unit tests (Node 18+)
cd roof-visualizer && npm start                 # web app at http://127.0.0.1:8080
$LAB_BPY_PYTHON roof-blender/tests/test_roof_core.py   # Blender core checks with pip bpy (cloud; see setup-cloud.sh)
$LAB_BPY_PYTHON lab/tools/roof_qa.py                    # geometry gate (blender-suite qa_check): z-fighting, flipped faces, floating parts; pass = "roof QA passed"
blender -b --factory-startup --python-exit-code 1 --python roof-blender/tests/test_roof_core.py   # same, real Blender (local); pass = "all roof_core checks passed"
node lab/tools/capture.mjs --url "http://127.0.0.1:8080/?quality=standard" --shots finished,layers,cutaway,midbuild --out lab/experiments/NNN-name/img
node lab/tools/snapshot.mjs --url "http://127.0.0.1:8080/" --size 3840x2160 --explode --out out/roof-4k.png
node lab/tools/closeup.mjs --url "http://127.0.0.1:8080/?quality=standard" --out out/web   # ridge-end and hip-foot close-ups
```

Cloud only: `bash lab/tools/setup-cloud.sh` creates a Python venv with `bpy` (about 430 MB download) and prints the paths to use.

Blender work uses the **blender-suite** skill in `.claude/skills/blender-suite/` (MIT; sources in its `NOTICE.md`). If `blender-master` or separate `blender-*` skills are also listed, they are older copies of the same material: use `blender-suite`. `roof_qa.py` imports its `qa_check.py`. Its rule applies here too: report numbers, then look at the result. Run `roof_qa.py`, then a close-up. Check the skill itself with `python .claude/skills/blender-suite/tests/check_skill.py`. Package it for claude.ai with `python lab/tools/package_skill.py .claude/skills/blender-suite out/skills` (180 files; the test suite stays in the repo).

## Long-running commands

Start the web server, Blender renders and videos in the background and check on them later; they outlast a normal command timeout. `roof-blender.mjs` prints one `RT_RESULT {json}` line per step, with `seconds`, `device` and `blender` for renders. Treat a missing `RT_RESULT` as a failure.

## Conventions

- Units are metres inside the code, inches and feet in anything a contractor reads.
- The web viewer and Blender share the plan JSON format (`roof-visualizer/viewer/plans/`) and the layer ids (`deck`, `dripEdge`, `iceWater`, `underlayment`, `starter`, `nails`, `covering`, `ridgeVent`, `ridgeCap`, `oldShingles`, `oldFelt`, `deckRepair`).
- Pinned web dependencies live in the import map in `roof-visualizer/viewer/index.html`. Bump them deliberately, in their own experiment.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. When the answer is under a Markdown heading, `graphify section "<heading>"` prints that section's text, so the .md need not be opened. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
