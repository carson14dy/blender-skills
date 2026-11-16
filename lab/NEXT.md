# Next up

The current to-do list for both sessions. Do the first open item for your kind of session, tick it, and move on. Details live in `lab/LOG.md` and the experiment folders. Keep this file short.

## Local session (Windows PC "Omen")

The full runbook, with commands in order, is `LOCAL-SESSION.md` at the repository root.

- [ ] **Setup, once (about 30 minutes):** follow "Set up this PC" below, then run `node lab/tools/doctor.mjs` until it shows no `NO` lines.
- [ ] **Steel panels and edge profiles on the GPU (about 15 minutes, after 001):**
  1. In the studio (`cd roof-visualizer && npm start`), pick Menards Pro-Rib on the Materials tab and the Style-D drip edge. Copy the command from the **Blender command** button.
  2. Run it, then `node roof-blender/scripts/roof-blender.mjs still --output out/prorib.png --samples 128` on the GPU.
  3. Look at the eave, the gable peak and a hip. Ribs should stand at the eave, caps should ride on the ribs, the trims should meet at the peak, and the drip edge should show a 1-11/16 in. face.
  4. Write one line per view in experiments 019 and 020, add a small JPG, and add the render time to `lab/LOG.md`.
- [ ] **Experiment 001, GPU baseline (about 45 minutes, mostly renders running in the background):** follow `lab/experiments/001-local-gpu-baseline/README.md` from top to bottom, including its "Report back" checklist.
- [ ] **Experiment 014, geometry check with real Blender (about 10 minutes):**
  1. Run `blender -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --save out/qa/roof.blend`. Pass = `roof QA passed`.
  2. Open `out/qa/roof.blend` in Blender. Switch the viewport to Rendered (Cycles, GPU) and zoom in on a hip foot and a ridge end. The cap halves should meet with no slit, and the ridge vent should sit on the shingles.
  3. Add the `RT_QA` line and one sentence on how the close-up looks to `lab/LOG.md`.
  4. For any other Blender check, use the `blender-suite` skill in `.claude/skills/blender-suite/` (it loads by itself).
- [ ] **blender-suite on real Blender (about 10 minutes):** run the four commands under "Needs local" in the newest `lab/LOG.md` entry, and report the last line of each.
- [ ] **Sioux Falls studio, local checks (about 30 minutes):**
  1. Start the studio (`cd roof-visualizer && npm start`). On the Project tab, press **Blender command** with Menards Duration on the roof, then again with Home Depot Timberline HDZ ("On the roof" switch).
  2. With Blender open (MCP for Blender addon), run `node roof-blender/scripts/roof-blender.mjs demo --preset ranch-hip --pitch 6` once. Then, for each store, run its pair of commands and `node roof-blender/scripts/roof-blender.mjs still --output out/sf-<store>.png`. Note the `RT_RESULT` seconds and device.
  3. Compare the two renders and the studio with the store pages. Do this for the 10 best-selling shingles and the 27 name mismatches listed in experiment 016. Write corrections to `roof-visualizer/scripts/data/supplier-color-overrides.json` and rebuild the catalog (command in 016).
  4. Open the studio on a phone: pick a product, open the List tab and the full list, and tap a roof plane. Note anything hard to tap or read.
- [ ] **Experiment 003, a real RoofTec house:**
  1. Export one house as `.glb` into `lab/experiments/003-real-house/out/` (git-ignored). Name the roof mesh `Roof` if the export tool allows it.
  2. Load it in the viewer (Project tab > Load house model).
  3. Compare squares, pitch and eave/rake/ridge/hip/valley lengths with the house's measurement report.
  4. Run the geometry gate on it: `blender -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --blend <the house .blend>`. Real roofs may show errors the demo does not. Record them; don't add them to ACCEPTED without a reason.
  5. Save two screenshots and write `lab/experiments/003-real-house/README.md` from the template.

## Cloud session

- [x] **Sioux Falls studio, steps 016, 017 and 018** (store picker with sampled colors, priced list, project files), plus the texture part of 019 and a read-only 022. See the experiment folders and the newest `lab/LOG.md` entry.
- [x] **Sioux Falls studio, step 019 geometry with 020:** real ribs (Pro-Rib, Pro-Snap, corrugated), metal caps on the ribs, rake trim, edge profiles from the drip-edge product, in both apps with a parity test. See experiments 019 and 020.
- [ ] After any change to `roof_core.py`, `roof-geometry.js` or the layer heights: run `$LAB_BPY_PYTHON lab/tools/roof_qa.py` and `npm test`.
- [ ] After 001 is pushed: read the results, then pick the next experiment from `lab/GOALS.md` (likely 006, lighter GLB files for phones, or 012, sturdier roof detection for scans).

---

## Set up this PC

Run these in PowerShell. Open a new PowerShell window after installing, so PATH changes apply. Each line is optional if doctor already shows it OK.

1. Install the tools:
   ```
   winget install --id Git.Git -e
   winget install --id OpenJS.NodeJS.LTS -e
   winget install --id Python.Python.3.12 -e
   winget install --id BlenderFoundation.Blender -e
   winget install --id Gyan.FFmpeg -e
   winget install --id astral-sh.uv -e
   ```
   Without winget, download them from:
   - https://git-scm.com
   - https://nodejs.org (LTS)
   - https://www.blender.org/download/ (4.2 LTS or 5.x)
   - https://www.gyan.dev/ffmpeg/builds/ (add its `bin` folder to PATH)
   - https://docs.astral.sh/uv/
2. Install the Blender addon. MCP for Blender was formerly called blender-mcp.
   ```
   uvx mcp-for-blender install-addon
   ```
   Open Blender. The addon starts its server on port 9876 when Blender opens; check the N panel > MCP for Blender tab. The roof-blender scripts talk to that server directly, so Claude needs no MCP configuration for this. If you also want Claude to drive Blender by chat, run `uvx mcp-for-blender setup`.
3. Get the lab:
   ```
   git clone https://github.com/carson14dy/blender-skills.git
   cd blender-skills
   git checkout rooftec-lab
   cd roof-visualizer
   npm install
   cd ..
   ```
   The first `git push` opens a browser window to sign in to GitHub.
   Then install graphify. The repo's Claude hooks call it on every file read, so install it **before** opening Claude in this folder, or each read shows a hook error:
   ```
   uv tool install graphifyy==0.9.111
   graphify update .
   ```
   The second line builds the code graph in about 5 seconds, and it is safe to re-run any time.
4. Optional, for scripted screenshots and GPU timings of the web app (`lab/tools/snapshot.mjs`, `capture.mjs`). `--no-save` keeps it out of `package.json`.
   ```
   cd roof-visualizer
   npm i --no-save playwright
   npx playwright install chromium
   cd ..
   ```
5. Start Claude Code in the `blender-skills` folder: the Claude desktop app's Code tab, or `claude` in PowerShell. Then say: **"Do the next local item in lab/NEXT.md"**.
