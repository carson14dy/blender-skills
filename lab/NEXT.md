# Next up

The current to-do list for both sessions. Do the first open item for your kind of session, tick it, and move on. Details live in `lab/LOG.md` and the experiment folders. Keep this file short.

## Local session (Windows PC "Omen")

- [ ] **Setup, once (about 30 minutes):** follow "Set up this PC" below, then run `node lab/tools/doctor.mjs`. Every line except `bpy` should say OK.
- [ ] **Experiment 001, GPU baseline (about 45 minutes, mostly waiting on renders):** follow `lab/experiments/001-local-gpu-baseline/README.md` step by step and fill in its Result section.
- [ ] **Report back:** add a `lab/LOG.md` entry (newest first), tick the boxes here, then commit and push:
  ```
  git add -A
  git commit -m "Lab: experiment 001 results (local)"
  git push
  ```
- [ ] **Experiment 003, a real RoofTec house:** export one house as `.glb` into `lab/experiments/003-real-house/out/` (git-ignored). Open it in the viewer (Project tab > Load house model), write down squares, pitch and LF next to the house's measurement report, and save two screenshots.

## Cloud session

- [ ] Wait for 001 results, then pick the next experiment from `lab/GOALS.md` (likely 004: baked textures in Blender, or 006: lighter GLB files).

---

## Set up this PC

Run these in PowerShell. Install anything doctor reports missing, then open a new PowerShell window so PATH changes apply.

1. **Git** from https://git-scm.com/download/win. The first `git push` asks you to sign in to GitHub in the browser.
2. **Node.js LTS** (18 or newer) from https://nodejs.org
3. **Blender 4.2 LTS or 5.x** from https://www.blender.org/download/. The default folder is `C:\Program Files\Blender Foundation\Blender <version>\blender.exe`. Doctor finds it there, or set `BLENDER` to the full path.
4. **ffmpeg** from https://www.gyan.dev/ffmpeg/builds/ (the "release essentials" zip). Unzip it, add its `bin` folder to PATH, and check with `ffmpeg -version`.
5. **blender-mcp addon:**
   1. Download `addon.py` from https://github.com/ahujasid/blender-mcp
   2. In Blender: Edit > Preferences > Add-ons > Install from Disk, pick `addon.py`, and enable "Blender MCP".
   3. In the 3D view press N, open the BlenderMCP tab, and click Connect.

   The roof-blender scripts talk to the addon on port 9876 directly, so Claude does not need an MCP server entry for this.
6. **Get the lab:**
   ```
   git clone https://github.com/carson14dy/blender-skills.git
   cd blender-skills
   git checkout rooftec-lab
   cd roof-visualizer
   npm install
   cd ..
   ```
7. **Optional, for scripted screenshots** (`lab/tools/capture.mjs`):
   ```
   cd roof-visualizer
   npm i --no-save playwright
   npx playwright install chromium
   cd ..
   ```
8. Open the `blender-skills` folder in Claude Code (the Claude desktop app's Code tab, or `claude` in that folder) and say: **"Do the next local item in lab/NEXT.md"**.
