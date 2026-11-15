# Lab log

Newest first. One entry per session: date, cloud or local, what changed, results, next steps, needs.

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
