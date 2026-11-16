# Review log

Each review round re-derives the skill's numbers, fixes what is wrong and records the change level here. The fixed test set is in `references/benchmark.md`.

## Round 1 (2026-11-16)

**Change level: MAJOR.** By the numbers alone it would be MODERATE: the largest sloped-area change on the benchmark is +0.42% and the largest main-plane pitch change is 0.36 in 12 (0.32 on a house). It is MAJOR because two rules for MAJOR were met: correctness bugs in the roof-line geometry (ridge lengths changed by 12 to 22 ft on 3 of 12 buildings), and a research finding that changed a decision (lidar now supplies the pitch).

### Findings

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| 1 | High | **The city pitch reads low; lidar is the better pitch source.** v1 kept the city pitch whenever lidar agreed within 1.5 degrees. | Independent fits (own decoder, pyproj, no skill code) reproduce the bias: lidar is 0.16 in 12 steeper on average. Lidar main planes land on whole-number pitches (8, 6, 6, 4 and 5 in 12 on five houses) and the city planes do not. Details in the research note `review-round-1.md`. | A plane with a precise lidar fit now shows the lidar pitch (`PREFER_LIDAR` in `lidar.py`). The city pitch is kept as `cityPitchDeg`. |
| 2 | High | **The "clean lidar fit" test could never fail.** v1 required the RMSE of the inliers to be under 0.10 m, and inliers are within 0.10 m by definition. A plane half covered by a tree could override the city pitch. | Code reading, and test `test_half_covered_plane_cannot_override`: a fit with 45% tree points has an inlier RMSE under 0.10 m. | New test `is_precise`: 80% of the points on the plane and a pitch standard error of 0.25 degree or less. An imprecise fit never supplies a pitch. |
| 3 | High | **A ridge drawn with a sliver wall was counted as two "high edges".** | Benchmark 176864: 12.85 ft of ridge reported as 25.7 ft of `top`. Benchmark 363469: 12.1 ft. The two sides lie 0.05 and 0.08 m apart. | Pairs of `top` lines within 0.15 m become one ridge (`_pair_split_ridges`); new `split-ridge` info flag. |
| 4 | Medium | **A lidar override changed the numbers and left the 3D model alone**, so `roof.json` and `roof.glb` described different roofs, and rake and hip lengths did not follow the new pitch. | v1 `apply_overrides`; the studio check had to compare against `cityAreaM2`. | `planes.retilt` rebuilds the geometry: each plane takes its pitch, outline corners stay on their wall lines, plan area does not change. The studio now measures the same area as `roof.json` (within 0.15%). |
| 5 | Medium | **The roof-to-wall test flipped with 3 cm of movement.** It probed 0.05 m above the edge and needed the wall plane within 0.03 m. | On 235248, 17 ft of an edge under a wall was called rake because it sat 0.05 m from the wall plane. | Probe at 0.10 and 0.25 m, wall plane within 0.08 m. Walls under 0.10 m tall are slivers, not flashing lines. |
| 6 | Medium | **An eave a few degrees out of level was called a rake**, and a near-level ridge a hip. | 363469: 22 ft of outer edge sloping 4.7 degrees, running 8 degrees off the contour of its plane, was a rake. | An edge is level if it rises under 3 degrees or runs within 10 degrees of its plane's contour line. |
| 7 | Medium | **Houses newer than the lidar were only detected for address lookups.** With `--oid` or `--latlon` they got unexplained lidar disagreements. | `assess` used `yearBuilt` from the address point only. | `OCCUPIEDDATE` on or after 2020-12-19 raises `newer-than-lidar`. |
| 8 | Low | **One small imprecise plane could put a whole house on `site-check`.** | 176864: a 168 sq ft plane with 36 of 43 points on the plane; a 389 sq ft plane 1.61 degrees off with a standard error of 0.42. | Fewer than 40 points on the plane means not checked; an imprecise fit is allowed twice its standard error before it disagrees. |
| 9 | Low | **A face delivered twice would count twice.** | Solid 33181 (benchmark 204065) holds one duplicated face; it happened to be hidden, so v1's area was not affected. | Duplicate faces are dropped and reported (`duplicate-faces`). |
| 10 | Low | Lidar capture date was "2020"; the points over Sioux Falls are from 19 and 20 December 2020. More solids than one request returns were not flagged. | GPS times of 2.5 million points; `exceededTransferLimit` was stored and never read. | `capturedOn` is `2020-12`; `solid-match` flag covers the transfer limit. |

### Checked and found correct

- **Units and projection.** `proj.py` agrees with pyproj to 0.0033 ft. US survey feet are used throughout. Grid-to-ground scale changes areas by 0.01%.
- **Decoder.** An independent decoder gives the same delivered areas on all 12 buildings.
- **Elevation datum.** Lidar ground and city ground agree within 0.15 m on level lots.
- **Outline.** The city outline is the roof edge within about 0.07 m (lidar return analysis, 6 houses). This bounds the plan-area error at roughly 2% per house, with no sign of a bias. It is the first independent check of plan area; the footprint comparison in v1 was circular.
- **Tests.** The synthetic roofs use hand-computed answers and the projection test uses PROJ values, so they are not tautological. The 235245 edge totals are regression values, not truth.
- **Studio import.** Run headless against branch `rooftec-lab` at three 0.186.1: 11 of 12 benchmark buildings pass.

### Tried and rejected

- Holding every outline corner in place while the delivered faces are made flat. It kept plan area equal to the footprint, but it changed main-plane pitches by up to 1.3 degrees and moved 17 ft between edge classes. The v1 cleaning step stays; its plan-area drift is 0.33% at most on the benchmark.

### Benchmark before and after

The full table is in `references/benchmark.md`. Summary: sloped area changed by -0.03% to +0.42%; predominant pitch rose on 7 of 12 buildings, by 0.15 in 12 at most; 176864 went from `site-check` to estimate; the four must-fail buildings still end as `site-check`.

Tests: 51, all passing (v1 had 43).

### Open issues for round 2, most important first

1. **No ground truth yet.** Finding 1 rests on indirect evidence. One taped or reported roof would confirm or overturn it. Nothing can become `verified` before that.
2. **Permits are not checked.** The plan promised "permits since capture" in `checks`. The layer is verified (`Data/Community/MapServer/3`, fields `MAINADDRESS`, `WORKCLASS`, `ISSUEDATE`); an `Addition` or `New` permit after June 2023 should raise a flag. About 1 hour.
3. **Faces under the roof are dropped whole or kept whole.** On 204065 the top surface should equal the footprint, and the tool reports 10% less. Clipping faces to the visible surface would fix it. The building is `site-check` today, so no wrong number escapes.
4. **Cleaning moves outline corners.** Plan area drifts up to 0.33% from the footprint (176864), and one corner moves 0.6 m. See "Tried and rejected".
5. **Ridge against hip on low-slope hip roofs is unstable.** On 235246 a 6 ft edge changed class after the re-tilt.
6. **The licence sentence about resale cannot be found any more**, and the Building Wireframe layer has no licence statement of its own. Ask the city in the planned email.
7. **Snow.** The lidar was flown on 19 and 20 December 2020. Check weather records once.
8. **The studio's own ridge, hip and valley totals still differ** from `roof.json` on 8 of 12 buildings without the patch in `patches/`.
9. **A real browser check** of the GLB has still not been run.
