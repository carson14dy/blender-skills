# Studio patches

The measured `roof.glb` loads in the roof studio with no code change. Apply the patch below only if you want the studio's own eave and rake totals to match `roof.json` on real houses. It takes about 2 minutes.

## 0001-studio-level-edge-tolerance.patch

**What it changes.** One line in `roof-visualizer/viewer/js/roof-geometry.js`, inside `analyzeRoof()`. The studio calls an edge "level" only when it slopes less than about 0.6 degrees. Roofs from city solids and lidar are not that level, so real eaves were counted as rakes. The patch raises the tolerance to 3 degrees, the same value this skill uses.

**How to apply it** on branch `rooftec-lab`, from the repository root:

```bash
git apply .claude/skills/rooftec-roof-measure/patches/0001-studio-level-edge-tolerance.patch
cd roof-visualizer && npm test
```

If the skill folder is on a different branch, copy the patch file across first.

**What was tested.** On 2026-11-16 the patch was applied to a scratch copy of the studio. The studio's `tests/geometry.test.mjs` still passed (4 of 4), and on house 235248 the studio's ridge, hip, valley and eave totals then matched `roof.json` to 0.1 ft. Its rake total matched the sum of rake and step flashing in `roof.json`.

**What still differs after the patch.** The studio has no wall-flashing class. It counts a roof-to-wall joint as a rake or an eave, and it misses some hips where two edges only partly overlap. Fixing that is step 3 in `references/implementation-plan.md`. Until then, `roof.json` is the reference for line lengths.
