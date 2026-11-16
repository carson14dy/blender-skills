# Validation results

Read the verdict first: no roof has been compared with ground truth yet, so nothing is `verified`. What exists is three independent cross-checks that all pass: the decoder and projection against other software, the pitch against lidar, and the outline against lidar.

Review round 1 (2026-11-16) re-derived the numbers below without this skill's code and re-ran everything on the 12 fixed buildings in `references/benchmark.md`. Review round 2 (same day) challenged round 1: it checked the lidar pitch rule on 30 more houses, checked the weather on the flight days, and added one benchmark building. The findings of both are in `references/review-log.md`.

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

## The lidar pitch rule on 30 fresh houses (review round 2)

Round 1 decided that lidar supplies the pitch from 8 benchmark houses. Round 2 measured 30 single-family houses picked at random from the city footprint layer (occupied before 2020, seed and ids in the round 2 scratch folder) and looked at the 94 main planes with a precise lidar fit.

| Question | Lidar | City |
|---|---|---|
| Within 0.15 in 12 of a whole-number pitch (chance is 30%) | 85% | 50% |
| Mean offset from the nearest whole-number pitch | 0.04 below | 0.14 below |
| Spread between the large planes of one house (38 houses with the benchmark) | 0.09 in 12 | 0.15 in 12 |

- The lidar pitches of one house are closer together than its city pitches on 29 of the 33 houses that have two or more large planes.
- Lidar is steeper than the city on 90% of the planes, by 0.12 in 12 on average.
- Two flight lines over house 218452, at scan angles of -13 and +9 degrees, give 4.09 and 4.06, 6.76 and 6.80, and 4.10 and 4.09 in 12 on its three planes.
- Fitting each half of a plane on its own gives pitches that differ by about what the tool's standard error predicts (median 0.8 times, 18 planes). The standard error is honest on clean planes.
- There was no snow. Station `USW00014944` (Sioux Falls airport) recorded no snowfall and zero snow depth from 15 November to 22 December 2020, and the last snow before that (14 cm on 10 November) was gone by 15 November.
- Lidar roof planes sit about 0.1 m above the city roof planes while the ground heights agree. Snow would raise both, so this is not snow. It does not affect pitch.

The same sample showed what the plane fit cannot see: a tree 4 m above the north plane of 177261, something solid 0.7 to 1.5 m above two planes of 235247 (most likely dormers or an upper roof the city model lacks), and 28% of the largest plane of twin home 176864 lying 0.4 m lower than the model (both end thirds of that plane are lower; the city drew three roof sections as one face).

Review round 3 checked every flagged plane on 40 houses. The number of returns per laser pulse tells a tree from a solid surface with a wide gap: points above the roof are 83 to 100% multi-return and 2.4 to 6 m up over trees (6 planes), and 0 to 15% multi-return and 0.5 to 1.3 m up over solid surfaces (6 planes); one plane is mixed. The July 2025 NAIP photo shows the tree over 177261 and no tree at two of the "solid" houses. Trees now raise the `tree-over-roof` info flag, and `lidar-surface` is kept for surfaces the model lacks.

## What the lidar says about the outline

The verdict: the city outline is the roof edge to about 0.10 m (4 in), and nothing free can narrow that. Every area therefore carries a range of 2.3 to 4.4% on the clean benchmark houses.

Review round 3 measured the roof-edge position on 38 houses (the 8 clean benchmark houses and 30 random ones), on 145 straight eaves and rakes with a total length of 817 m. It counted lidar points that lie on the extension of a roof plane, by distance from the city outline, and it also used the strength of each return. "Offset" is lidar roof edge minus city outline; positive is outside the city line.

- Points whose pulse hit only the roof stop about 0.32 m inside the outline. Points whose pulse also hit the ground reach about 0.25 to 0.4 m outside it. The edge is taken to be midway, which assumes the laser spot is symmetric.
- That midpoint is +0.04 m at eaves and -0.05 m at rakes. With the tighter height band of rounds 1 and 2 the eaves read -0.04 m. The choice of band alone moves the answer by 0.08 m, and that is the limit of the method.
- The return strength gives -0.07 m at rakes. At eaves it is not usable: gutters reflect far more than shingles, and lidar sees them as roof.
- House averages scatter by 0.09 m, of which 0.08 m is lidar noise. The real spread between houses is about 0.05 m.
- A single edge scatters by 0.15 m. Edge lengths are therefore good to about 1 ft, even where the area is fine.
- So the city outline is the roof edge and not the wall line, which would sit 0.3 to 0.6 m further in. Lidar cannot say whether the line follows the shingle edge or the gutter lip, which are 4 to 5 in apart.
- On City Hall, where a parapet stands on the outline, the count stops 0.33 m inside. The method does not push edges outward by itself.
- NAIP 2025 photos (0.3 m) were tried as a second source. Roofs are shifted 0.3 to 1.5 m in them because the photo is not a true orthophoto, and one clean eave-to-eave length agreed with the city within 0.15 m. They cannot narrow the outline.

The details are in the research note `review-round-3.md`. The range the tool prints is explained in `references/accuracy.md`.

## Studio import check

`scripts/studio_check.mjs` loads `roof.glb` with the studio's own `GLTFLoader` path, `extractRoofPlanes()`, `analyzeRoof()` and `measureRoof()` from branch `rooftec-lab` (three 0.186.1), headless in Node.

- On 11 of the 12 benchmark buildings the unmodified studio used the mesh named `Roof`, found the same number of planes as `roof.json`, and measured the same area within 0.15% (0.6% on City Hall). This now includes planes whose pitch came from lidar, because the GLB is re-tilted with the numbers.
- It fails on 204065, where the studio finds 8 of 9 planes. That building is `site-check`.
- The studio's own ridge, hip and valley totals match `roof.json` on four buildings only (the three simplest roofs and City Hall). It treats any edge that slopes more than 0.6 degrees as not level, and it has no wall-flashing class. The one-line patch in `patches/` closes most of the gap; it was tested in v1 and not re-tested in review round 1.

The check was not run in a real browser. That takes about 5 minutes with `?glb=roof.glb` on the studio's local server.

## Unit tests

`python3 -m unittest discover -s tests` runs 69 tests in under 2 seconds with no network. They cover the decoder, synthetic gable, hip, lean-to and butterfly roofs with hand-computed answers, the 235245 acceptance numbers, both map conversions against PROJ reference values, the lidar plane fit, its standard error and the reconcile rule (on synthetic points and on 5,308 real lidar points), the re-tilt, the three output files, the offline cache and the command line. Eight of them are regression tests for the bugs found in review round 1, nine cover the fixes and new checks of review round 2 (points off the roof surface, permits, the site-check status, and a download that is cut off), and nine cover review round 3 (tree or dormer, a pitch confirmed by another plane, the area range, slanted edges, a plane that faces another way in lidar, the permit cache, repair permits, and two report fixes).

## Timing and load

A first run with lidar took 8 seconds for house 235245 and made 21 requests: 2 to the city and 19 to the public lidar bucket, 2.7 MB in total. A repeat run took 0.3 seconds and made no request.

## Not yet validated

1. No comparison with ground truth. This is the accuracy study, step 1 in `references/implementation-plan.md`. The rule "lidar supplies the pitch" depends on it most.
2. Only 13 benchmark buildings, and 4 of them are in one neighbourhood. The 30 extra houses of review round 2 were used for the pitch rule only; nobody looked at their line totals.
3. The plan area. Lidar confirms the outline only to 4 in, which is 2.3 to 5.4% of the area depending on the house (see above). Whether the city line follows the shingle edge or the gutter lip is not known.
4. The `lidar-surface` thresholds (10% of points 0.3 m off the surface, 25% at ground level) were set on 43 houses. Round 3 checked the tree calls against photos; a 0.3 m photo cannot show a dormer, so the "solid surface" calls rest on lidar alone.
5. The reconcile thresholds were set on this benchmark and are not tuned against truth.
