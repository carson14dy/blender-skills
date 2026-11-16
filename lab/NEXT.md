# Next up

The current to-do list for both sessions. Do the first open item for your kind of session, tick it, and move on. Details live in `lab/LOG.md` and the experiment folders. Keep this file short.

## Local session (Windows PC "Omen")

- [ ] **Setup, once (about 30 minutes):** follow "Set up this PC" below, then run `node lab/tools/doctor.mjs` until it shows no `NO` lines.
- [ ] **Experiment 001, GPU baseline (about 45 minutes, mostly renders running in the background):** follow `lab/experiments/001-local-gpu-baseline/README.md` from top to bottom, including its "Report back" checklist.
- [ ] **Experiment 014, geometry check with real Blender (about 10 minutes):**
  1. Run `blender -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --save out/qa/roof.blend`. Pass = `roof QA passed`.
  2. Open `out/qa/roof.blend` in Blender. Switch the viewport to Rendered (Cycles, GPU) and zoom in on a hip foot and a ridge end. The cap halves should meet with no slit, and the ridge vent should sit on the shingles.
  3. Add the `RT_QA` line and one sentence on how the close-up looks to `lab/LOG.md`.
  4. If Claude lists the `/anthropic-skills:blender-master` skill here, use it for any other Blender check. If not, the same checks are in `lab/tools/vendor/blender-master/`.
- [ ] **Experiment 003, a real RoofTec house:**
  1. Export one house as `.glb` into `lab/experiments/003-real-house/out/` (git-ignored). Name the roof mesh `Roof` if the export tool allows it.
  2. Load it in the viewer (Project tab > Load house model).
  3. Compare squares, pitch and eave/rake/ridge/hip/valley lengths with the house's measurement report.
  4. Run the geometry gate on it: `blender -b --factory-startup --python-exit-code 1 --python lab/tools/roof_qa.py -- --blend <the house .blend>`. Real roofs may show errors the demo does not. Record them; don't add them to ACCEPTED without a reason.
  5. Save two screenshots and write `lab/experiments/003-real-house/README.md` from the template.

## Cloud session

- [ ] After any change to `roof_core.py`, `roof-geometry.js` or the layer heights: run `$LAB_BPY_PYTHON lab/tools/roof_qa.py` and `npm test`.
- [ ] After 001 is pushed: read the results, then pick the next experiment from `lab/GOALS.md` (likely 006, lighter GLB files for phones, or 012, sturdier roof detection for scans).

---

## Set up this PC

Run these in PowerShell. Open a new PowerShell window after installing, so PATH changes apply. Each line is optional if doctor already shows it OK.

1. Install the tools:
   ```
   winget install --id Git.Git -e
   winget install --id OpenJS.NodeJS.LTS -e
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
4. Optional, for scripted screenshots and GPU timings of the web app (`lab/tools/snapshot.mjs`, `capture.mjs`). `--no-save` keeps it out of `package.json`.
   ```
   cd roof-visualizer
   npm i --no-save playwright
   npx playwright install chromium
   cd ..
   ```
5. Start Claude Code in the `blender-skills` folder: the Claude desktop app's Code tab, or `claude` in PowerShell. Then say: **"Do the next local item in lab/NEXT.md"**.
