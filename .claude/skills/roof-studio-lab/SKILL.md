---
name: roof-studio-lab
description: Use, test, rebuild, merge and publish the Roof Studio Lab, a copy of the Roof Layer Studio artifact with a Lab tab that tries four free tools on a measured Sioux Falls house - <model-viewer> AR, the three.js WebGPU renderer, a 3D Tiles neighbourhood (3d-tiles-renderer, City of Sioux Falls 3D solids + USGS 3DEP ground) and Gaussian-splat surroundings (Spark, 3DEP lidar coloured with NAIP 2025). Use it whenever someone asks to run or check the Lab tools, add neighbourhood context or splats for another Sioux Falls house, merge a newer studio build into the lab, republish the lab as a claude.ai artifact, or run its CSP test harness, even if they do not name this skill.
---

# Roof Studio Lab

The lab is a static site (an `index.html` page body plus files) that runs as a claude.ai artifact. The
newest copy is in `handoffs/studio-lab/site/`. The live page is listed in `handoffs/studio-lab/README.md`.
The four tools load only when switched on in the **Lab** tab, so the studio itself starts as before.

## Quick start

Work on a copy of the site in a scratch folder, never in `handoffs/` directly:

```bash
S=.claude/skills/roof-studio-lab/scripts
cp -r handoffs/studio-lab/site "$SCRATCH/lab"            # $SCRATCH: your scratchpad folder
python3 $S/test/serve.py "$SCRATCH/lab" 8765 &            # artifact-like server with the CSP
NODE_PATH=$(npm root -g) LAB_TEST_OUT="$SCRATCH/lab-test" node $S/test/run_all.js
```

`run_all.js` drives headless Chromium through every studio tab and all four Lab tests, under the
artifact CSP and under the CSP plus `'wasm-unsafe-eval'`, at desktop and phone width, light and dark.
It writes JSON results and screenshots into `LAB_TEST_OUT`. A clean run reports `errors: []` for
every part, and `serve.py` prints `UNSERVED <path>` for any request the artifact host would refuse.
Read `references/testing.md` before trusting a number from it: the headless GPU is software.

## What to do for each request

1. **Use or test a Lab tool.** Open the Lab tab, switch the tool on, press **Run test**, and read the
   table. On a phone, Run test is the only way to get real frame rates and AR support.
   `references/tools.md` explains each tool, its verdict and the checks still open on real devices.
2. **Add the neighbourhood and splats for another Sioux Falls house.** Run `align_house.py`, then
   `build_tileset.py` and `build_splat.py`; they write into `$LAB_OUT/lab/`. Commands, dependencies,
   caching and the credit line are in `references/data.md`.
3. **Merge a newer studio build into the lab.** Run `merge_studio.sh BASE NEW LAB`, resolve the
   conflicts by hand, re-run the alignment, then the full test. The procedure and the known conflict
   spots are in `references/merge.md`.
4. **Publish.** Follow `references/publish.md`: served file types only (binaries as base64 JSON via
   `pack_json.py`), no `<html>` skeleton in `index.html`, pinned CDN versions, and the WebAssembly
   note for Spark.

## Rules

- Keep real customer addresses out of git. The studio's test job, 1601 S Discovery Ave, may be named.
  For any other house, keep the output site and `LAB_CACHE` (default `~/.cache/roof-studio-lab`) in a
  scratch or git-ignored folder, and do not write the address into skill or handoff files.
- Show "Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP. Imagery: USDA NAIP
  2025." wherever the tiles or splats appear. The Lab does this on screen; keep it when changing the UI.
- City data "is not intended for use in mapping products for resale": use the context in-house only.
- Be polite to the city service: the scripts ask for 5 records per request, 1 second apart, and cache
  every answer. Never widen the radius past a few hundred metres.
- Do not commit unless the person asks.

## Files

- `scripts/align_house.py`, `build_tileset.py`, `build_splat.py`, `pack_json.py`: data builders.
- `scripts/common.py`, `ept.py`, `naip.py`, `glb.py`, `gltf_read.py`: shared helpers. They import the
  rooftec-roof-measure skill's `scripts/roofmeasure` (found next to this skill, or set `ROOF_MEASURE_SCRIPTS`).
- `scripts/merge_studio.sh`: the 3-way merge of a newer studio build.
- `scripts/test/serve.py`, `skeleton-head.html`, `lib.js`, `run_all.js`: the CSP test harness.
- `references/tools.md`, `data.md`, `merge.md`, `publish.md`, `testing.md`: read the one that matches the task.
