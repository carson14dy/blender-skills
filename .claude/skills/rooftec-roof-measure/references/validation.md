# Validation results

Read the verdict first: on 2026-11-16 the skill reproduced the research numbers for house 235245, ran live on 7 more buildings, and the lidar check worked on all of them. No roof has been compared with ground truth yet, so nothing is `verified`.

To repeat any row, run `python3 scripts/roof.py measure --oid <footprint id> --out out/roofs --lidar`. Houses are listed by city footprint id only; addresses are kept out of this file on purpose.

## Acceptance: house 235245 (city solid 79199)

| Check | Research note | This skill |
|---|---|---|
| Roof faces and wall faces | 7 and 24 | 7 and 24 |
| Pitch of all 7 faces as delivered | 5.6 to 6.1 in 12 | 5.63 to 6.10 in 12 |
| Sloped area as delivered | 3,269 sq ft | 3,269.2 sq ft |
| Sloped area after cleaning | not done | 3,265 sq ft (0.1% lower); 3,270 sq ft after one lidar pitch override |
| Plan area against footprint | 2,941 and 2,941 sq ft | 2,940.9 as delivered; 2,937.6 after cleaning (0.11% lower) |
| Main ridge | about 53.5 ft, level | 53.5 ft, level within 0.1 m |
| Highest point against footprint top | 0.27 ft lower | 0.28 ft lower |

The line totals differ from the research note on purpose. The note's rough classifier gave ridge 84.9, hip and valley 25.0, eave 116.2 and rake 245.9 ft, and warned that wall steps inflated the rake figure. This skill gives ridge 78.7, hip 2.5, valley 28.6, eave 112.8, rake 191.1, step flashing 25.6, headwall 24.7 and high edges 8.5 ft. Both sets add up to 472 ft, so every edge is counted once; the wall joints are now their own classes.

## Live runs with the lidar check: single-family houses

| Footprint | Planes | Squares | Predominant pitch | Lidar result | Flags |
|---|---|---|---|---|---|
| 235245 | 7 | 32.7 | 5.9/12 | 5 of 7 checked: 4 agree, 1 override | roof-step, eave-under-wall, lidar-override |
| 235246 | 12 | 47.9 | 3.3/12 | 12 of 12 agree | regularize |
| 235247 | 7 | 31.7 | 7.8/12 | 5 of 7 checked: 5 agree | small-planes, eave-under-wall |
| 235248 | 11 | 35.9 | 5.8/12 | 9 of 11 checked: 7 agree, 2 override | roof-step, lidar-override |
| 177261 | 2 | 12.2 | 3.8/12 | 2 of 2 agree | none |

House 218452 (3 planes, 15.4 squares, 4.1/12) was found from a lat/lon 55 ft away and also agreed with lidar on all 3 planes. House 235247 was also found by street address, and house 177261 only by street address; both lookups picked the right footprint.

## Live runs: hard cases that the flags caught

| Footprint | What it is | What happened |
|---|---|---|
| 204065 | A 1911 house, now 3 units | The solid holds a cap polygon under the roof, which doubled the plan area until hidden faces were removed. Plan area is still 10% under the footprint. Result: `site-check`. |
| 250390 | City Hall, flat roofs | Found by address. 14 planes, 150 squares, 8 planes under 2/12, lidar disagrees on 5 planes with rooftop equipment. Result: `site-check`. |

Both are correct outcomes: the tool measured what it could and told the reader not to trust it.

## What the lidar comparison shows

Across the 36 lidar-checked planes on the six single-family houses, comparing lidar with the city pitch as delivered:

- The mean absolute difference is 0.66 degrees, and the largest is 2.3 degrees.
- 75% of planes are within 1 degree and 92% are within 1.5 degrees.
- Lidar reads steeper than the city by 0.6 degrees on average. On house 235245 the lidar pitches cluster at 26.0 to 27.5 degrees around a true 6/12 (26.6 degrees), which suggests the city solid reads slightly low. This is a hint, not a finding, until a roof is measured by hand.
- Lidar plane fits are clean: the fit error is 0.01 to 0.05 m on every checked plane.
- On the four research houses the lidar roof sits 0.09 to 0.24 m from the city solid horizontally, inside the 0.5 m target.

## Studio import check

`scripts/studio_check.mjs` loads `roof.glb` with the studio's own `GLTFLoader` path, `extractRoofPlanes()`, `analyzeRoof()` and `measureRoof()` from branch `rooftec-lab` (three 0.186.1), headless in Node.

- On all six single-family houses the unmodified studio used the mesh named `Roof`, found the same number of planes as `roof.json`, and measured the same area within 0.01%.
- In the unmodified studio, ridge, hip and valley totals matched `roof.json` on four of the six houses. On 235246 and 235248 the studio counted some ridges and eaves as hips and rakes, because it treats any edge that slopes more than 0.6 degrees as not level.
- With the one-line patch in `patches/`, ridge and valley matched on all six and hip on five. On 235246 the studio still missed about 25 ft of hip where two edges only partly overlap.
- The studio has no wall-flashing class, so on three houses its eave or rake total includes the roof-to-wall joints that `roof.json` lists separately.
- City Hall also loaded (14 planes, area within 0.6%). House 204065 loaded with 8 of 9 planes.

The check was not run in a real browser. That takes about 5 minutes with `?glb=roof.glb` on the studio's local server.

## Unit tests

`python3 -m unittest discover -s tests` runs 43 tests in under 2 seconds with no network. They cover the decoder, synthetic gable, hip, lean-to and butterfly roofs with hand-computed answers, the 235245 acceptance numbers, the map projection, the lidar plane fit and reconcile rule (on synthetic points and on 5,308 real lidar points), the three output files, the offline cache and the command line.

## Timing and load

A first run with lidar took 8 seconds for house 235245 and made 21 requests: 2 to the city and 19 to the public lidar bucket, 2.7 MB in total. A repeat run took 0.3 seconds and made no request.

## Not yet validated

1. No comparison with ground truth. This is the accuracy study, step 1 in `references/implementation-plan.md`.
2. Only 8 buildings, and 4 of them are in one neighbourhood.
3. No house built after 2020, no house with heavy tree cover, and no twin home that shares a solid with its neighbour.
4. The reconcile thresholds are the plan's proposal and are not tuned.
