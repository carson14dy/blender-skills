# Lab log

Newest first. One entry per session: date, cloud or local, what changed, results, next steps, needs.

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
