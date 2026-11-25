---
name: virtual-homes
description: Generate seeded virtual test houses in Blender with an exact roof-measurement answer key (facet areas, pitch, azimuth, ridge/hip/valley/eave/rake/flashing lengths, squares, counts, drip edge, starter, ridge cap, valley metal, ice-and-water) and realistic phone, on-roof and drone photo sets with ground-truth camera poses, for grading photogrammetry / roof-measurement pipelines and training Gaussian-splat show models (NVIDIA 3DGRUT / 3DGUT).
---

# Virtual test homes (answer-keyed)

Each house is rebuilt exactly from one integer seed. The answer key is computed from the generated 3-D roof
geometry by an independent module and must agree with the roof builder's own numbers before it is written; the
Blender roof mesh is re-measured in Blender and must equal the key (float32, ~1e-8 relative).

## Run

```bash
pip install bpy==5.3.0 numpy shapely pillow          # Python 3.13
python3 virtual-homes/scripts/make_house.py --seed 1 --out virtual_homes                       # full res, all rigs
python3 virtual-homes/scripts/make_house.py --seed 1 --out vh --long-side 1440 --samples 64    # 1080p-class pass
python3 virtual-homes/scripts/make_house.py --seed 1 --out vh --max-per-rig 3 --long-side 480 --samples 8 --device cpu  # smoke test
python3 virtual-homes/scripts/export_colmap.py vh/house_001          # COLMAP text dataset for 3DGRUT / 3DGUT
python3 -m pytest -q virtual-homes/tests
```

Output: `house_NNN/{answer_key.json, cameras.json, house.json, scene.blend, render_log.json, renders/{ground,roof,drone}/*.png}`.

## What is in each file

* `answer_key.json`: per facet area (m², ft²), pitch (x/12, degrees), azimuth; totals (area, squares, plan
  area, footprint, predominant pitch); every roof line with its kind and length (ft); counts (box vents, pipe
  boots, skylights, chimneys, ridge vent ft); materials (drip edge, starter, ridge cap, valley metal, step and
  headwall flashing, ice-and-water per IRC R905.1.2 with 36 in rolls); scale-marker corners; builder cross-check.
* `cameras.json`: per image the true pose (world->camera R, t, quaternion; camera centre; Blender matrix), OPENCV
  intrinsics of the final image (the PNG really carries that distortion), exposure / blur / noise applied, and
  device metadata with realistic GPS / compass error (never ground truth).
* Frame: x east, y north, z up, metres, origin = house centre at grade; `geo_origin` maps it to lat/lon.

## Rigs

* ground: ~40 phone photos walking around the house at eye height, 4-12 m outside the eaves.
* roof: ~60 phone photos standing on every walkable facet (<= 8/12; ladder shots from the eave on steeper ones):
  down-slope, across, up-slope, detail and feet shots.
* drone: nadir lawn-mower grid at 35 m with 75 % overlap plus two oblique orbits (25 m and 12 m).

## Status (step 1-2 of the plan)

Gable roofs with box vents, pipe boots, ridge vents, gutters, downspouts, windows, doors and two 24 in checkerboard
markers. Next: hip, Dutch hip, gambrel, mansard, L/T/multi-wing, dormers, chimneys, skylights, trees for occlusion.
Real customer photos must never be sent to third-party GPU services; virtual homes are fine.
