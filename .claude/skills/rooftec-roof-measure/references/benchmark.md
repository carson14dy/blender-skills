# Review benchmark

Use these 13 buildings and 1 missing-data point for every review round, and do not change the list. Review round 2 added building 14, because no building covered a roof changed under a permit after the capture. Review round 3 added none. A round reports its change level from the difference between two runs of this benchmark.

Buildings are listed by city footprint id only. Addresses are kept out of this file on purpose.

## How to run it

```bash
python3 scripts/benchmark.py --out out/benchmark --json out/benchmark/round-N.json --compare out/benchmark/round-N-1.json
```

The first run makes about 180 small requests and takes about 3 minutes. Later runs use the cache and take about 10 seconds. To compare two code versions fairly, copy the `raw/` and `_ept/` cache folders so both read the same city answers and the same lidar points. Run the comparison with `--offline`: the permit answer is asked again once it is 30 days old, and a new permit would change a result for a reason that has nothing to do with the code.

A "main plane" is a plane of 215 sq ft (20 m²) or more. That is the size from which the plan's 1 degree pitch target applies.

## The buildings and why each was chosen

| # | Footprint | Why it is in the set |
|---|---|---|
| 1 | 177261 | Simple gable, 2 planes, 4/12. The smallest possible roof; every edge can be checked by hand. |
| 2 | 218452 | Gable with an attached lower wing, 3 planes, two pitches (4/12 and 6.8/12). Dense lidar (two flight lines). |
| 3 | 175156 | Hip roof, 4 planes, 5/12. One half of a twin home with its own footprint and solid. |
| 4 | 235245 | Cross-gable with valleys, 7 planes, 6/12. The acceptance house from the research note. |
| 5 | 235246 | Low-slope hip, 12 planes, 3.5/12. The city faces fit together poorly here (`regularize` flag). |
| 6 | 235247 | Steep gables with dormer-size planes, 7 planes, 8/12. |
| 7 | 235248 | Complex hip and gable mix, 11 planes, 6/12 with one 4.3/12 plane. |
| 8 | 176864 | Twin home (structure code 121): one footprint and one solid for both units, 6 planes, 5/12. |
| 9 | 204065 | 1911 house, now 3 units. The solid holds extra faces under the roof, and the plan area is 10% under the footprint. Must end as `site-check`. |
| 10 | 250390 | City Hall. Flat roofs, parapets and rooftop equipment. Must end as `site-check`. |
| 11 | 363469 | House occupied September 2023, after the June 2023 capture and after the 2020 lidar. The city has a solid, but lidar has no roof points. Must end as `site-check`. |
| 12 | 363456 | House occupied December 2025. Lidar sees the lot before the house. Must end as `site-check`. |
| 13 | lat/lon 43.4460, -96.8390 | A point outside the city data. Must fail with the "no city footprint within 100 ft" message and write nothing. |
| 14 | 199138 | Added in round 2. A house with an `Addition` permit issued in March 2024, after the June 2023 capture, on a footprint the city has not redrawn. Must end as `site-check` with the `permit-since-capture` flag, with and without `--lidar`. |

Building 14 was found with a permit query for `WORKCLASS = 'Addition'` issued from March to May 2024; it is the first result whose footprint id is older than the permit. Buildings 11 and 12 were found with the query `OCCUPIEDDATE > DATE '2023-09-01' AND STRUCTURE = 110` on the footprint layer, and building 8 with `STRUCTURE = 121`.

## Results by round

Sloped area is in square feet. Pitch is the predominant pitch in inches per 12. "Largest pitch change" is the largest change on any main plane against the round before.

| Footprint | v1 area | Round 1 area | Change | v1 pitch | Round 1 pitch | Largest pitch change | Round 1 result |
|---|---|---|---|---|---|---|---|
| 177261 | 1,215.2 | 1,217.4 | +0.18% | 3.81 | 3.95 | 0.14 | Estimate |
| 218452 | 1,538.5 | 1,540.3 | +0.12% | 4.09 | 4.10 | 0.06 | Estimate |
| 175156 | 1,100.2 | 1,101.9 | +0.15% | 5.27 | 5.29 | 0.22 | Estimate |
| 235245 | 3,270.3 | 3,284.1 | +0.42% | 5.93 | 6.03 | 0.22 | Estimate |
| 235246 | 4,787.0 | 4,796.9 | +0.21% | 3.31 | 3.46 | 0.31 | Estimate |
| 235247 | 3,172.2 | 3,183.1 | +0.34% | 7.83 | 7.99 | 0.16 | Estimate |
| 235248 | 3,588.3 | 3,595.9 | +0.21% | 5.78 | 5.92 | 0.32 | Estimate |
| 176864 | 3,695.8 | 3,702.9 | +0.19% | 4.66 | 4.66 | 0.27 | Estimate (was site-check) |
| 204065 | 1,767.9 | 1,767.4 | -0.03% | 10.24 | 10.24 | 0.08 | Site check |
| 250390 | 14,985.0 | 14,985.8 | +0.01% | 0.02 | 0.02 | 0.36 | Site check |
| 363469 | 4,586.8 | 4,586.8 | 0.00% | 5.94 | 5.94 | 0.00 | Site check |
| 363456 | 3,685.6 | 3,685.6 | 0.00% | 6.01 | 6.01 | 0.00 | Site check |

### Round 2 (2026-11-16)

No number changed on any building: sloped area 0.00%, every main-plane pitch 0.00 in 12, every line total 0.0 ft. Round 2 changed what the tool detects and says, not what it measures.

| Footprint | Area (v2 = round 2) | Pitch | Result | New flags in round 2 |
|---|---|---|---|---|
| 177261 | 1,217.4 | 3.95 | Estimate | `lidar-surface` (a tree over the north plane) |
| 218452 | 1,540.3 | 4.10 | Estimate | none |
| 175156 | 1,101.9 | 5.29 | Estimate | none |
| 235245 | 3,284.1 | 6.03 | Estimate | none |
| 235246 | 4,796.9 | 3.46 | Estimate | none |
| 235247 | 3,183.1 | 7.99 | Estimate | `lidar-surface` (something solid above two planes) |
| 235248 | 3,595.9 | 5.92 | Estimate | none |
| 176864 | 3,702.9 | 4.66 | Estimate | `lidar-surface` (29% of the largest plane lies 0.4 m lower) |
| 204065 | 1,767.4 | 10.24 | Site check | none |
| 250390 | 14,985.8 | 0.02 | Site check | `lidar-surface`, `permit-since-capture` (demolition permits in 2026) |
| 363469 | 4,586.8 | 5.94 | Site check | `lidar-surface` (ground under every plane) |
| 363456 | 3,685.6 | 6.01 | Site check | `lidar-surface` (ground under every plane) |
| 199138 | 2,308.3 | 5.25 | Site check | `permit-since-capture`, `lidar-surface` |

Building 199138 measured with the round 1 code gives the same numbers. With `--lidar` it was already a site check there, because lidar disagrees on two planes; without `--lidar` the round 1 code returned a plain estimate.

### Round 3 (2026-11-16)

Three houses changed, each because one large plane now takes a lidar pitch that another plane of the same house confirms. Largest sloped-area change: +0.28%. Largest main-plane pitch change: 0.39 in 12. No building changed between estimate and site check. Every roof now carries a likely range for its area.

| Footprint | Round 2 area | Round 3 area | Change | Pitch (round 2, round 3) | Largest pitch change | Likely range of the area | Result | Flags added or dropped |
|---|---|---|---|---|---|---|---|---|
| 177261 | 1,217.4 | 1,220.3 | +0.24% | 3.95, 3.95 | 0.20 | 1,173 to 1,268 (3.9%) | Estimate | `tree-over-roof` replaces `lidar-surface` |
| 218452 | 1,540.3 | 1,540.3 | 0.00% | 4.10, 4.10 | 0.00 | 1,479 to 1,602 (4.0%) | Estimate | none |
| 175156 | 1,101.9 | 1,101.9 | 0.00% | 5.29, 5.29 | 0.00 | 1,053 to 1,150 (4.4%) | Estimate | none |
| 235245 | 3,284.1 | 3,284.1 | 0.00% | 6.03, 6.03 | 0.00 | 3,179 to 3,389 (3.2%) | Estimate | none |
| 235246 | 4,796.9 | 4,796.9 | 0.00% | 3.46, 3.46 | 0.00 | 4,687 to 4,907 (2.3%) | Estimate | none |
| 235247 | 3,183.1 | 3,190.1 | +0.22% | 7.99, 7.99 | 0.39 | 3,062 to 3,318 (4.0%) | Estimate | `skewed-edge` (28 ft) |
| 235248 | 3,595.9 | 3,595.9 | 0.00% | 5.92, 5.92 | 0.00 | 3,467 to 3,725 (3.6%) | Estimate | `skewed-edge` (71 ft) |
| 176864 | 3,702.9 | 3,713.4 | +0.28% | 4.66, 4.85 | 0.19 | 3,606 to 3,821 (2.9%) | Estimate | `skewed-edge` (12 ft) |
| 204065 | 1,767.4 | 1,767.4 | 0.00% | 10.24, 10.24 | 0.00 | 1,697 to 1,838 (4.0%) | Site check | `skewed-edge` |
| 250390 | 14,985.8 | 14,985.8 | 0.00% | 0.02, 0.02 | 0.00 | 14,627 to 15,344 (2.4%) | Site check | `tree-over-roof` |
| 363469 | 4,586.8 | 4,586.8 | 0.00% | 5.94, 5.94 | 0.00 | 4,416 to 4,757 (3.7%) | Site check | `skewed-edge` |
| 363456 | 3,685.6 | 3,685.6 | 0.00% | 6.01, 6.01 | 0.00 | 3,528 to 3,843 (4.3%) | Site check | `skewed-edge` |
| 199138 | 2,308.3 | 2,308.3 | 0.00% | 5.25, 5.25 | 0.00 | 2,225 to 2,391 (3.6%) | Site check | none |

- The planes that changed: 177261 plane 1 (3.83 to 4.03 in 12), 235247 plane 3 (7.45 to 7.85) and 176864 plane 0 (4.66 to 4.86). All three moved towards a whole-number pitch.
- Line totals moved by 0.2 ft at most (rakes and hips follow the new pitch).
- `lidar-surface` now fires on 2 of the 8 clean houses (235247 and 176864), both real differences between model and roof. The tree on 177261 is an info flag.
- The range on a site-check building is printed too, but it means nothing there: the numbers must not be used.
- Both runs read the same cached city answers and the same lidar nodes. The point files were rebuilt from those nodes, because round 3 also stores the return count of each point.

### Line totals in feet, round 1 (v1 in brackets where it changed by more than 1 ft)

| Footprint | Ridge | Hip | Valley | Eave | Rake | Step flashing | Headwall | High edge |
|---|---|---|---|---|---|---|---|---|
| 177261 | 38.3 | 0 | 0 | 76.6 | 63.6 | 0 | 0 | 0 |
| 218452 | 33.4 | 0 | 0 | 70.9 | 110.1 | 25.4 | 2.1 | 2.1 |
| 175156 | 2.5 (1.0) | 85.5 (87.6) | 0 | 120.5 | 16.1 | 0 | 0 | 0 |
| 235245 | 79.2 | 1.9 | 28.6 | 112.8 | 192.2 (191.1) | 25.7 | 25.0 | 8.5 |
| 235246 | 60.6 (66.5) | 242.6 (232.9) | 100.2 | 316.5 | 7.0 | 0 | 0 | 0 |
| 235247 | 67.0 | 8.7 | 0 | 112.8 | 247.1 | 63.2 | 20.5 | 0 |
| 235248 | 37.7 (26.1) | 165.9 (175.2) | 14.2 | 222.0 | 138.8 (156.4) | 72.4 (55.8) | 0 | 2.0 |
| 176864 | 116.3 (94.6) | 32.8 (42.2) | 15.5 | 221.6 | 85.7 | 0 | 0 | 0 (25.7) |
| 204065 | 40.4 | 3.6 | 31.4 | 77.6 (57.3) | 117.4 (142.0) | 74.7 | 72.6 | 23.8 (19.5) |
| 250390 | 0 | 0 | 8.3 | 1,009.2 | 80.3 | 80.1 (94.5) | 509.0 (494.6) | 220.3 |
| 363469 | 62.6 (50.6) | 89.6 | 0.5 | 186.5 (164.0) | 279.4 (297.9) | 148.2 (152.1) | 0 | 8.9 (33.1) |
| 363456 | 56.6 | 30.6 | 15.6 | 200.7 (179.8) | 237.7 (244.8) | 63.7 (77.6) | 10.5 | 11.5 |

### Studio hand-off, round 1

`scripts/studio_check.mjs` passed on 11 of 12 buildings (same plane count, area within 0.6%). It failed on 204065, where the studio finds 8 of 9 planes; that building is `site-check` anyway. In v1 it passed on 10 of 12 and failed on 176864 as well.

## What must stay true in every round

1. Buildings 9 to 12 and 14 end as `site-check`, and point 13 fails cleanly. Building 14 does so without `--lidar` too.
2. Buildings 1 to 8 keep a plan area within 0.5% of the city footprint area.
3. On buildings 1 to 8, every main plane with a precise lidar fit shows a pitch within 0.25 degree of that lidar pitch.
4. All unit tests pass with no network.
5. Every roof has `summary.areaRange`, and the GLB holds the same sloped area as `roof.json` within 0.01% on buildings 1 to 8.
