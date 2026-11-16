# Lab log

Newest first. One entry per session: date, cloud or local, what changed, results, next steps, needs.

---

## 2026-11-16 · cloud (7)

**Changed**
- **blender-suite as a .skill file** for claude.ai and other machines: `python lab/tools/package_skill.py .claude/skills/blender-suite out/skills`.
  - The file is 211 files, 479 KB. It passes skill-creator's validator and the skill's own linter.
  - Unpacked outside the repo, it passes: smoke 0 failures, tests 71 passed, 0 failed, 2 skipped. The file was sent to the user.
- **graphify 0.9.111 installed** (Graphify-Labs/graphify, Apache-2.0 or MIT; no telemetry; code is mapped locally with tree-sitter).
  - `graphify install --project` added: `.claude/skills/graphify/`, `.claude/CLAUDE.md`, a "graphify" section at the end of `CLAUDE.md`, and hooks in `.claude/settings.json`. The hooks are PreToolUse on Read, Glob, Grep and Bash, and SessionStart on compact; they suggest a graph query and never block.
  - `.graphifyignore` skips data and images. `graphify-out/` is git-ignored because it rebuilds in about 5 s.
  - Graph: 2,471 nodes, 4,735 edges, 180 communities.
- Hooks need graphify on PATH, or each file read shows a hook error:
  - **PC:** `lab/NEXT.md` setup now installs it right after the clone, and `doctor.mjs` checks it.
  - **Cloud:** the "Rooftec 1" environment now has a setup script, approved by the user. It installs graphify, EGL and the npm packages, then builds the graph. It is unproven until a fresh session starts.
- Sioux Falls project: both answers recorded in the plan. Swatches are approved (hex colors only, no images), and both stores show side by side.

**Next:** step 016, the product picker with real colors.

**Needs local:**
- Before opening Claude in the repo folder, run `uv tool install graphifyy==0.9.111`, then `graphify update .`.
- Optionally upload `blender-suite.skill` in claude.ai (Settings > Capabilities > Skills).

---

## 2026-11-16 · cloud (6)

**Changed**
- New project **Sioux Falls supplier studio**: plan in `lab/projects/sioux-falls-studio/PLAN.md`, with steps 015–023 in `lab/GOALS.md`. It draws on four handoffs:
  - Menards' 3D-studio package for Sioux Falls West #3064;
  - Home Depot #4301 prices (PR #3);
  - the Menards workbook;
  - the Rooftec design session's product rules: unknown is never zero, only measured values reach the customer, the crew never sees prices.
- Step 015 done:
  - Menards CSVs (no images) are in `lab/data/suppliers/menards-3064-2026-11-15/`;
  - `roof-visualizer/scripts/build-supplier-catalog.mjs` writes `roof-visualizer/viewer/catalog/suppliers/sioux-falls.json`. Details: `lab/experiments/015-supplier-intake/`.
- Studio: the Project tab has a Job section. Sioux Falls (43.54 N) is the default sun location, and a line shows the store prices loaded. `roofStudio.suppliers()` returns the catalog.

**Results:**
- 453 roof products (Menards 89, Home Depot 364), 338 priced, every roof layer covered at both stores.
- Web tests 18/18 (5 new). The studio loads with no console errors.

**Next:** the user's answer on swatch downloads, then step 016 (product picker), 017 (priced list), 018 (project files).

**Needs local:** none new.

**Needs the user:** two open questions in the plan, section 5: swatch downloads, and which store first.

---

## 2026-11-16 · cloud (5)

**Changed**
- New skill **blender-suite** in `.claude/skills/blender-suite/`. It loads by itself in every Claude session opened in this repo. It merges four MIT sources into one skill:
  - EL4CTEO/blender-skills 1.3.1: the newest code for all 43 shared scripts, and the test suite;
  - the user's uploaded blender-master 1.2.1: router, local TRELLIS.2 photo to 3D (the Meshy script is dropped), Poly Haven, camera moves, web viewer;
  - mromidev/claude-blender-skills: the film, car-film and forest pipelines, unedited;
  - the synced blender-master 1.0.0, which nothing was copied from because the upload replaces it.
- Planned by Fable 5.2 and built by Opus 5.5 to the plan. Fable reviewed the build: it matches the plan, and its 4 Windows fixes are applied.
- New in the skill:
  - `scripts/blender_send.py` sends code to the open Blender through the MCP for Blender add-on (port 9876), keeping names between files;
  - `scripts/blend_audit.py` is a safety check for downloaded .blend files;
  - `run_in_blender.py` falls back to pip `bpy` in the cloud;
  - six new references: `blender-film`, `blender-forest`, `long-renders`, `film-sound`, `asset-safety`, `rooftec`.
- `lab/tools/roof_qa.py` now imports the skill's `qa_check.py`. The vendored copy in `lab/tools/vendor/` is removed.
- `.ps1` and `.cmd` files check out with Windows line endings.

**Results (cloud, pip bpy 5.2.4)**
- `check_skill.py --strict`: 211 files, 1.1 MB, 0 errors, 0 warnings.
- `smoke.py`: 6 host tools and 46 bpy scripts load and print `--help`; 92 files compile; 0 failures.
- Test suite: 71 passed, 0 failed, 2 skipped. The two skips need a Blender executable.
- `blender_send.py` against the stand-in add-on: ping and a two-file run sharing a function both work.
- `roof QA passed`; web 13/13; `test_roof_core` passed.

**Next:** run the four local checks below. Then pick the next experiment.

**Needs local (Windows, from the repo folder, about 10 minutes)**
```
python .claude\skills\blender-suite\tests\check_skill.py --strict
python .claude\skills\blender-suite\tests\run_tests.py
blender -b --factory-startup --python-exit-code 1 -P .claude\skills\blender-suite\tests\smoke.py
python .claude\skills\blender-suite\scripts\blender_send.py --ping
```
- Expect `OK`, then `73 passed, 0 failed` (GPU), then `"failures": 0`.
- The last command needs Blender open with the MCP for Blender add-on running, and should print the Blender version.
- Report the last line of each in this log.

**For the user:** 31 separate `blender-*` skills and the synced `blender-master` also still load, wherever they were installed. They are older copies of the same material; `CLAUDE.md` says to use `blender-suite`. Removing them is the user's call.

---

## 2026-11-16 · cloud (4)

**Changed**
- Added the **blender-master** skill to the lab. Its MIT-licensed `qa_check` found 9 geometry errors in the roof layers; all fixed in both apps or accepted with a reason. Details and before/after images: `lab/experiments/014-blender-master-qa/`.
- Visible bugs fixed in the web app:
  - half of every hip cap did not render;
  - the ridge cap and drip edge were lit inside-out;
  - a slit showed along hips and ridges.
- Visible bugs fixed in Blender:
  - old shingles stayed under the finished roof;
  - the ridge vent and cap floated.
- New geometry gate: `lab/tools/roof_qa.py`, with blender-master's checks vendored in `lab/tools/vendor/blender-master/`.
- New tool: `lab/tools/closeup.mjs`, close-up screenshots of hips and ridge ends in the web app.

**Results:**
- Gate: 0 unexpected errors in 6.6 s; it fails on the old code with 4.
- Node tests: 13/13.
- Blender core checks pass, with 3 new ones.

**Next:** local experiment 014 step (10 minutes, in `lab/NEXT.md`), then 001.

**Needs local:** run `roof_qa.py` with real Blender, and look at a Cycles close-up of a hip.

**Needs cloud:** none open.

---

## 2026-11-15 · cloud (3)

**Changed**
- Ran an independent review on Claude Fable 5.2 (46 findings across web, Blender, lab and docs) and fixed the verified ones. Details and evidence: `lab/experiments/010-fable-review/`.
- Measurements corrected: the ranch demo is 27.4 squares, not 29.4. Hand-calculation tests now cover 3 houses in the web app and the ranch in Blender.
- Blender videos: no black bands, the sun matches the sky, frame-step previews work, failures fail, renders report seconds and device.
- Local-session guide: `lab/NEXT.md` (setup with winget and MCP for Blender), experiment 001 rewritten as a runbook, README "start here", `CLAUDE.md` points at NEXT.md.

**Results:** 12/12 Node tests; Blender core checks pass on 5.2.4 and 4.2.0; scan and image proxy work live; path-traced snapshots are no longer blank.

**Next:** experiment 001 on the local PC. New backlog items 011-013.

**Needs local:** follow `lab/NEXT.md`, Local session.

**Needs cloud:** none open.

---

## 2026-11-15 · cloud (2)

**Changed**
- Fixed backlog 009: layers-view labels now pick a size by view width (full, mid, or title-only on phones), stay between the top bar and the toolbar, and the camera keeps a strip free for them. Files: `roof-visualizer/viewer/js/labels.js`, `js/app.js` (`frameView`), `index.html` (callout styles).
- Experiment write-up with before and after images: `lab/experiments/009-narrow-labels/`.
- Same code change applied to PR #1's branch; demo artifact republished.

**Results:** labels readable and clear of the house at 1000, 1400 and 1920 px windows and at phone width; snapshots still burn labels in; 8/8 unit tests pass.

**Next:** waiting on experiment 001 from the local PC.

**Needs local:** unchanged from the entry below (run experiment 001). While you are in the layers view, check the labels on your real screen sizes and write down anything that looks off.

**Needs cloud:** none open.

---

## 2026-11-15 · cloud

**Changed**
- Created branch `rooftec-lab` from `claude/nice-gauss-v0itms` (PR #1: roof-visualizer, roof-blender, open-source guide).
- Added `CLAUDE.md` (lab rules for every session), `lab/GOALS.md` (tracks T1-T6, backlog 001-009), the experiment template, and the test harness in `lab/tools/`.
- Recorded the baseline: `lab/experiments/000-baseline/`.

**Results:** everything in 000 works on Linux without a GPU. Timings there are worst case. The lab tools are tested here: doctor, setup-cloud plus blender-shim (headless still), capture (3 shots), snapshot (1080p exploded, 3.9 s).

**Found:** the layers-view labels break at medium widths (backlog 009, image in 000).

**Next:** experiment 001 on the user's PC; then 003 (a real RoofTec house) and 002 (color accuracy).

**Needs local**
1. Clone and check out this branch:
   ```
   git clone https://github.com/carson14dy/blender-skills.git
   cd blender-skills
   git checkout rooftec-lab
   ```
2. Install Node 18+, Blender 4.2 or 5.x, ffmpeg, and the blender-mcp addon (https://github.com/ahujasid/blender-mcp).
3. Start Claude Code in the folder and ask it to run experiment 001.
4. Export one real RoofTec house as `.glb` and put it in `lab/experiments/003-real-house/out/` (git-ignored). Note the units and whether the roof mesh is named.

**Needs cloud:** fix 009 (layers-view labels on narrow screens).
