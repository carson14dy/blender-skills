# Validation results

Read the verdict first: no roof has been compared with ground truth yet, so nothing is `verified`. What exists is three independent cross-checks that all pass: the decoder and projection against other software, the pitch against lidar, and the outline against lidar.

Review round 1 (2026-11-16) re-derived the numbers below without this skill's code and re-ran everything on the 12 fixed buildings in `references/benchmark.md`. Its findings are in `references/review-log.md`.

To repeat any row, run `python3 scripts/roof.py measure --oid <footprint id> --out out/roofs --lidar`. Houses are listed by city footprint id only; addresses are kept out of this file on purpose.

## Acceptance: house 235245 (city solid 79199)

| Check | Research note | This skill |
|---|---|---|
| Roof faces and wall faces | 7 and 24 | 7 and 24 |
| Pitch of all 7 faces as delivered | 5.6 to 6.1 in 12 | 5.63 to 6.10 in 12 |
| Sloped area as delivered | 3,269 sq ft | 3,269.2 sq ft |
| Sloped area after cleaning | not done | 3,265 sq ft (0.1% lower); 3,284 sq ft with the lidar pitch on the five checked planes |
| Plan area against footprint | 2,941 and 2,941 sq ft | 2,940.9 as delivered; 2,937.6 after cleaning (0.11% lower) |
| Main ridge | about 53.5 ft, level | 53.5 ft, level within 0.1 m |
| Highest point against footprint top | 0.27 ft lower | 0.28 ft lower |

The line totals differ from the research note on purpose. The note's rough classifier gave ridge 84.9, hip and valley 25.0, eave 116.2 and rake 245.9 ft, and warned that wall steps inflated the rake figure. This skill gives ridge 79.2, hip 1.9, valley 28.6, eave 112.8, rake 192.2, step flashing 25.7, headwall 25.0 and high edges 8.5 ft. The sets add up to 472 and 474 ft, so every edge is counted once; the wall joints are now their own classes.

## Live runs on the benchmark

The table of all 12 buildings, with areas, pitches, line totals and results, is in `references/benchmark.md`. In short:

- Eight houses and twin homes measure cleanly: 2 to 12 planes, 11 to 48 squares, pitches from 3.5 to 8 in 12.
- Four hard cases end as `site-check`, as they should: a 1911 house with extra faces in its solid (plan area 10% under the footprint), City Hall (flat roofs and equipment), and two houses occupied after the June 2023 capture.
- A point outside the city data fails with a clear message and writes nothing.
- Address lookup was tested in v1 on houses 235247 and 177261, and lat/lon lookup on 218452 from 55 ft away; all picked the right footprint.

## Independent re-derivation (review round 1)

A separate script with its own multipatch decoder, pyproj for the map conversion and a trimmed least-squares plane fit was run on all 12 buildings.

- Delivered sloped and plan areas match this skill to 0.1 sq ft on the 10 buildings that have no faces under the roof. (The independent script does not remove such faces.)
- Delivered plan area equals the city footprint area to 0.1 sq ft on 10 of 12 buildings. The solid is built on the footprint, so this checks the decoder and nothing more.
- Lidar pitches from the independent fit agree with this skill's fit within 0.05 in 12 on most clean main planes and within 0.12 on all of them.
- `proj.py` agrees with pyproj to 0.0033 ft.
- Edge classes on the simple gable 177261 check by hand: two eaves of 38.3 ft equal the ridge length, and four rakes of 15.1 ft plan length times the slope factor 1.049 give 63.5 ft.

## What the lidar comparison shows

Across 44 lidar-checked planes of 150 sq ft or more on eight houses, comparing lidar with the city pitch:

- Lidar reads steeper than the city by 0.16 in 12 (about 0.6 degree) on average. 92% of planes are within 1.5 degrees.
- Lidar pitches of main planes land on whole-number pitches, which is how roofs are framed: 7.85 to 7.99 on house 235247, 5.82 to 6.07 on 235248, 5.91 to 6.04 on 235245, 3.95 and 4.03 on 177261, and 4.85 to 4.99 on 176864. The city pitches of the same planes are 0.1 to 0.4 lower and scatter about twice as much.
- Lidar plane fits are clean: on the 38 planes the tool calls precise, the fit error is 0.01 to 0.05 m and the pitch standard error is 0.03 to 0.23 degree.
- This is why a precise lidar fit now supplies the pitch. It is indirect evidence until a roof is measured by hand.
- The lidar roof sits 0.09 to 0.24 m from the city solid horizontally, inside the 0.5 m target, and 0.07 to 0.14 m above it.

## What the lidar says about the outline

The roof-edge position was checked on six houses by counting lidar points that lie on the extension of a roof plane, by distance from the city outline.

- Points whose laser pulse hit only the roof stop 0.19 to 0.31 m inside the outline. Points whose pulse hit the roof and then the ground reach 0.16 to 0.39 m outside it. The roof edge is midway between the two.
- That midpoint is within 0.07 m of the city outline on all six houses, with no lean in or out (mean 0.00 m).
- So the city outline is the roof edge and not the wall line, which would sit 0.3 to 0.6 m further in. For a typical house, 0.07 m around the perimeter is about 2% of plan area. That is the resolution of this check, not a measured error.
- On City Hall, where a parapet stands on the outline, the same count stops 0.33 m inside. The method does not push edges outward by itself.

## Studio import check

`scripts/studio_check.mjs` loads `roof.glb` with the studio's own `GLTFLoader` path, `extractRoofPlanes()`, `analyzeRoof()` and `measureRoof()` from branch `rooftec-lab` (three 0.186.1), headless in Node.

- On 11 of the 12 benchmark buildings the unmodified studio used the mesh named `Roof`, found the same number of planes as `roof.json`, and measured the same area within 0.15% (0.6% on City Hall). This now includes planes whose pitch came from lidar, because the GLB is re-tilted with the numbers.
- It fails on 204065, where the studio finds 8 of 9 planes. That building is `site-check`.
- The studio's own ridge, hip and valley totals match `roof.json` on four buildings only (the three simplest roofs and City Hall). It treats any edge that slopes more than 0.6 degrees as not level, and it has no wall-flashing class. The one-line patch in `patches/` closes most of the gap; it was tested in v1 and not re-tested in review round 1.

The check was not run in a real browser. That takes about 5 minutes with `?glb=roof.glb` on the studio's local server.

## Unit tests

`python3 -m unittest discover -s tests` runs 51 tests in under 2 seconds with no network. They cover the decoder, synthetic gable, hip, lean-to and butterfly roofs with hand-computed answers, the 235245 acceptance numbers, both map conversions against PROJ reference values, the lidar plane fit, its standard error and the reconcile rule (on synthetic points and on 5,308 real lidar points), the re-tilt, the three output files, the offline cache and the command line. Eight of them are regression tests for the bugs found in review round 1.

## Timing and load

A first run with lidar took 8 seconds for house 235245 and made 21 requests: 2 to the city and 19 to the public lidar bucket, 2.7 MB in total. A repeat run took 0.3 seconds and made no request.

## Not yet validated

1. No comparison with ground truth. This is the accuracy study, step 1 in `references/implementation-plan.md`. The rule "lidar supplies the pitch" depends on it most.
2. Only 12 buildings, and 4 of them are in one neighbourhood.
3. No house with heavy tree cover, and no check of the lidar flight days (19 and 20 December 2020) for snow.
4. The reconcile thresholds were set on this benchmark and are not tuned against truth.
