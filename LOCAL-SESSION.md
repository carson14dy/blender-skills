# Local session runbook (Windows PC "Omen")

Everything the RoofTec lab needs from a real Windows PC with a GPU, in order, with exact commands. It is written for a **Claude Code session running on that PC**, with a short part for you first.

---

## Part 1: for you (about 10 minutes, once)

1. **Install the tools.** Open PowerShell, run these, then **open a new PowerShell window** so PATH updates:
   ```
   winget install --id Git.Git -e
   winget install --id OpenJS.NodeJS.LTS -e
   winget install --id Python.Python.3.12 -e
   winget install --id BlenderFoundation.Blender -e
   winget install --id Gyan.FFmpeg -e
   winget install --id astral-sh.uv -e
   ```
2. **Get the lab and graphify.** Install graphify **before** opening Claude in the folder: the repo's Claude hooks call it on every file read.
   ```
   git clone https://github.com/carson14dy/blender-skills.git
   cd blender-skills
   git checkout rooftec-lab
   uv tool install graphifyy==0.9.111
   graphify update .
   ```
3. **Install the Blender addon,** then open Blender once. The addon starts its server on port 9876; check the N panel > MCP for Blender tab.
   ```
   uvx mcp-for-blender install-addon
   ```
4. **Start Claude Code** in the `blender-skills` folder and paste:
   > Read LOCAL-SESSION.md and do it from Part 2 onward, top to bottom. Ask me only for things that need my eyes or hands.

Claude will ask you for these:
- keeping Blender open;
- judging colors and close-ups by eye;
- trying the studio on your phone;
- exporting a real house model;
- trying a save inside the claude.ai page.

---

## Part 2: rules for the local Claude session

- **Read first:** `CLAUDE.md`, then the newest entry in `lab/LOG.md`. `lab/NEXT.md` is the checklist this runbook works through: tick each item when done.
- **Shell:** Claude Code on Windows runs commands in Git Bash, so the commands below are bash.
  - Git Bash rewrites arguments that start with `//`. Use `MSYS_NO_PATHCONV=1` before such a command, or use plain relative paths (as below).
- **Blender path:** `node lab/tools/doctor.mjs` prints it. Set it once per shell:
  `B="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"` (use the folder doctor printed).
- **Long commands** (web server, renders, videos) run **in the background**; check on them afterwards.
  - Timings come from the `RT_RESULT {json}` line (`seconds`, `device`, `blender`).
  - The first GPU render loads kernels: run each timed render twice and record the second.
  - A missing `RT_RESULT` is a failure.
- **Ask the user** only for what needs eyes or hands. Never guess how something looks.
- **On a failure:** write the exact error where the step says to record results, try the fix doctor or the error suggests once, then move on.
- **Git:**
  - `git pull origin rooftec-lab` before starting.
  - Commit after each step and push to `rooftec-lab`. Never force-push.
  - Images go in as JPG at most 1600 px wide. Renders, videos and `.blend` files go in `out/`, which is git-ignored.
- **Blender work:** use the `blender-suite` skill (`.claude/skills/blender-suite/`; it loads by itself).
- **Finding code:** use `graphify query "<question>"` before grepping.

---

## Part 3: the steps

| # | Step | Time | Needs the user |
|---|---|---|---|
| 1 | Environment check | 5 min | only if something is missing |
| 2 | Tests on Windows | 10 min | no |
| 3 | Experiment 001: GPU baseline | 45 min | yes (smoothness, looks) |
| 4 | Experiment 014: geometry gate with real Blender | 10 min | a quick look |
| 5 | blender-suite on real Blender | 10 min | Blender open |
| 6 | Steel panels and edge profiles on the GPU (019/020) | 15 min | judge the close-ups |
| 7 | Sioux Falls studio: store renders, colors, phone, saves | 30–45 min | yes |
| 8 | Experiment 003: a real RoofTec house | 30 min | export a house |
| 9 | Wrap up: log, checklist, push | 5 min | no |

### Step 1: environment check (5 min)

```bash
git pull origin rooftec-lab
node lab/tools/doctor.mjs
```
- Fix every line marked `NO` using the fix it prints, then run doctor again until there are none.
- If `graphify` is missing, every file read shows a hook error: `uv tool install graphifyy==0.9.111`, then `graphify update .`.
- Optional, for screenshot tools: `cd roof-visualizer && npm i --no-save playwright && npx playwright install chromium && cd ..`.

### Step 2: tests on Windows (10 min)

```bash
cd roof-visualizer && npm install && npm test && cd ..
"$B" -b --factory-startup --python-exit-code 1 --python roof-blender/tests/test_roof_core.py
```
Pass:
- the web tests end with `# fail 0` (87 tests);
- Blender ends with `all roof_core checks passed`.

### Step 3: experiment 001, GPU baseline (45 min, mostly renders in the background)

Follow `lab/experiments/001-local-gpu-baseline/README.md` top to bottom, including its "Report back" checklist. Record the results in that README.

### Step 4: experiment 014, geometry gate with real Blender (10 min)

```bash
"$B" -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --save out/qa/roof.blend
"$B" -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --layers '{"category":"metal","panel":"proRib"}'
"$B" -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --layers '{"category":"metal","panel":"corrugated"}'
```
1. Each run must print `roof QA passed`.
2. Ask the user to open `out/qa/roof.blend`, switch the viewport to Rendered (Cycles, GPU) and zoom in on a hip foot and a ridge end. The two halves of each cap should meet with no slit, and the ridge vent should sit on the shingles.
3. Record the `RT_QA` lines and the user's one-line verdict in `lab/experiments/014-blender-master-qa/README.md`, under a "Local check" heading.

### Step 5: blender-suite on real Blender (10 min; Blender open with the addon)

```bash
python .claude/skills/blender-suite/tests/check_skill.py --strict
python .claude/skills/blender-suite/tests/run_tests.py
"$B" -b --factory-startup --python-exit-code 1 -P .claude/skills/blender-suite/tests/smoke.py
python .claude/skills/blender-suite/scripts/blender_send.py --ping
```
Expect, in order:
- `OK`;
- `73 passed, 0 failed` (with a GPU);
- a JSON line with `"failures": 0`;
- the Blender version.

If `python` opens the Microsoft Store, Python is not installed: run `winget install --id Python.Python.3.12 -e` and open a new terminal.

### Step 6: steel panels and edge profiles on the GPU (019/020, 15 min)

1. Start the studio in the background: `cd roof-visualizer && npm start`. It serves http://127.0.0.1:8080.
2. Ask the user to open it:
   - pick **Menards Pro-Rib** on the Materials tab ("Choosing for: Shingles / panels");
   - pick the **Style-D** drip edge ("Choosing for: Drip edge");
   - press **Blender command** on the Project tab and paste the commands to you.
3. With Blender open, run those commands. Then render twice in the background, and record the second time:
   ```bash
   node roof-blender/scripts/roof-blender.mjs still --output out/prorib.png --samples 128
   ```
4. Ask the user to look at the render, or the Blender viewport in Rendered mode, at three places:
   - **eave:** the ribs stand up at the edge;
   - **gable peak:** the two rake trims meet in a clean point;
   - **hip:** the cap rides on the rib tops.

   Also check that the Style-D drip edge shows a 1-11/16 in. face.
5. Save a JPG at most 1600 px wide of each view into `lab/experiments/019-steel-profiles/img/` and `lab/experiments/020-edge-profiles/img/`. Add a "Local GPU check" section to both READMEs with one line per view and the render seconds.

### Step 7: Sioux Falls studio checks (30–45 min)

1. **One render per store.**
   - With **Menards Duration** on the roof (the studio's default), press **Blender command**.
   - Run `node roof-blender/scripts/roof-blender.mjs demo --preset ranch-hip --pitch 6` once, then the copied commands, then `node roof-blender/scripts/roof-blender.mjs still --output out/sf-menards.png`.
   - Switch "On the roof" to **Home Depot** (Timberline HDZ) and repeat with `out/sf-homedepot.png`.
   - Record the seconds and device from `RT_RESULT`.
2. **Colors by eye** (the user).
   - Compare the renders and the studio swatches with the store pages for the 10 best-selling shingles and the 27 name mismatches listed in `lab/experiments/016-store-picker-colors/README.md`.
   - For each color that's wrong, add an entry to `roof-visualizer/scripts/data/supplier-color-overrides.json`: key `"<product id>|<color name>"`, value `{ "hex": "#rrggbb", "note": "why" }`.
   - Then rebuild:
     ```bash
     mkdir -p out && git show origin/claude/stoic-keller-boixwx:handoffs/sioux-falls-material-prices/homedepot/materials.json > out/hd.json
     node roof-visualizer/scripts/build-supplier-catalog.mjs --menards lab/data/suppliers/menards-3064-2026-11-15 --homedepot out/hd.json
     cd roof-visualizer && npm test && cd ..
     ```
3. **Phone** (the user).
   - On the same Wi-Fi, start the server reachable from the phone: `node roof-visualizer/scripts/serve.mjs --host 0.0.0.0 --allow-host <PC's LAN IP>`.
   - The user opens `http://<PC's LAN IP>:8080` on the phone, picks a product, opens the List tab and the full list, and taps a roof plane.
   - Note anything hard to tap or read.
4. **Saves inside claude.ai** (the user).
   - Open the Roof Layer Studio page (https://claude.ai/artifact/VYuREoj6UhHXQ5G5Mst7Du).
   - On the List tab, download the CSV. On the Project tab, Save a project, then Open it again.
   - Note whether each save worked or showed a message.
5. Record everything in `lab/experiments/017-priced-list/README.md` under "Local check": render seconds, color fixes made, the phone notes and the save results.

### Step 8: experiment 003, a real RoofTec house (30 min)

1. Ask the user for one real house as `.glb` (or `.blend`), saved in `lab/experiments/003-real-house/out/` (git-ignored). The roof mesh should be named `Roof` if possible.
   - If the user's **property-model-pipeline** work (branch `claude/upbeat-franklin-at23bw`) has produced a house model, use that.
2. Load it in the studio: Project tab > Load house model. Compare squares, pitch, and eave, rake, ridge, hip and valley lengths with the house's measurement report.
3. Run the gate on it:
   ```bash
   "$B" -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --blend lab/experiments/003-real-house/out/house.blend
   ```
   Real roofs may show errors the demo does not. Record them; do not add them to ACCEPTED without a written reason.
4. Write `lab/experiments/003-real-house/README.md` from `lab/experiments/_template/README.md`, with two screenshots (JPG, at most 1600 px wide).

### Step 9: wrap up (5 min)

1. Tick the finished items in `lab/NEXT.md`.
2. Add a `lab/LOG.md` entry at the top:
   ```
   ## <date> · local

   **Changed** ...
   **Results** (numbers: test counts, RT_QA lines, render seconds and device, color fixes, phone notes, save results) ...
   **Next** ...
   **Needs cloud** (exact steps for anything a cloud session should do with these results) ...
   ```
3. Commit, and push to `rooftec-lab`.
4. Tell the user what passed, what failed, and what the cloud session should do next.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| A hook error on every file read | graphify is not installed or not on PATH: `uv tool install graphifyy==0.9.111`, open a new terminal, then `graphify update .` |
| `blender_send.py --ping` can't connect, or the roof-blender commands hang | Blender is not open, or the addon's server is off: open Blender and check N panel > MCP for Blender (port 9876) |
| `blender: command not found` | use `"$B"` with the full path from doctor |
| `python` opens the Microsoft Store | install Python 3.12 with winget, then open a new terminal |
| The first render is very slow | GPU kernels compile on the first run; record the second run |
| A command stops at the timeout | run it in the background and check its output later |
| A path like `//render/x.png` becomes `/render/x.png` | prefix the command with `MSYS_NO_PATHCONV=1`, or run it in PowerShell |
