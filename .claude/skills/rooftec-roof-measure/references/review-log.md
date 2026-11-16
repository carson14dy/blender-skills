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

## Round 2 (2026-11-16)

**Change level: MODERATE.** No benchmark number moved: sloped area changed by 0.00% and main-plane pitch by 0.00 in 12 on all 13 buildings. It is not MINOR, because two failure modes are now detected that were silent before (a roof changed under a permit after the capture, and lidar points off the roof surface) and two real bugs were fixed. It is not MAJOR: no bug was found in geometry, units or reprojection, and the one decision that was challenged hardest, `PREFER_LIDAR`, was kept as it is.

**Verdict on round 1's main claim.** Keep `PREFER_LIDAR`. Round 1 decided it on 8 houses and an argument that could have been cherry-picked. Round 2 tested it on 30 fresh houses and it held more clearly than on the benchmark. There was no snow.

### Round 1's claims, checked

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | The city pitch reads low and lidar should set the pitch | **Confirmed, kept unchanged.** The bias is 0.12 to 0.15 in 12, a little less than the 0.16 round 1 gave. | 30 random houses, 94 precise main planes: lidar is within 0.15 of a whole-number pitch on 85%, the city on 50% (chance 30%). Lidar pitches of one house are closer together than its city pitches on 29 of 33 houses. Two flight lines 22 degrees apart agree within 0.04 in 12. Edge insets from 0.3 to 1.0 m move large planes by 0.1 at most. |
| 1a | Snow on 19 and 20 December 2020 | **No snow.** | NOAA daily summaries, station `USW00014944`: snowfall 0 and snow depth 0 every day from 15 November to 22 December 2020. Lidar ground heights match the city's; only roofs sit 0.1 m higher, which snow would not do. |
| 1b | The re-tilt is consistent | **Confirmed.** | On all 12 buildings the GLB area equals `roof.json` within 0.003% (0.6% on City Hall), each plane's area equals plan area over cos(pitch), edge lengths match their end points to 1 mm, and the re-tilt starts from the delivered corners each time, so nothing is adjusted twice. |
| 2 | The fit-quality test is calibrated and can fail | **Confirmed.** | Pitches fitted to the two halves of a plane differ by 0.8 times the predicted standard error (median, 18 planes). The test refuses the plane that needs it (235248 plane 0, a bump 0.6 to 0.9 m high on it). |
| 3 | Edge classes after the fixes | **Confirmed on 218452 and 176864, with one doubtful edge.** | Every edge of both was read by hand. On 176864 a 9.2 ft outer edge of a small skewed plane is called rake and is more likely eave (open issue 5). |
| 4 | The outline is the roof edge within about 0.07 m | **Right in kind, too tight in number.** | Round 1's script re-run on 8 houses: mean 0.02 m inside, scatter 0.07 m, worst 0.14 m. And 0.1 m is 2 to 4% of plan area, so this check cannot confirm the 2% area target. The docs said "roughly 2%, no bias" as if that settled plan area. |
| 5 | The resale sentence cannot be found | **Overturned.** | `<layer>/metadata?f=xml` on layers 66, 5, 0 and 3 holds the full use limitation, with CC BY 4.0 and "This data is not intended for use in mapping products for resale". Round 1 tried `format=default`, which is switched off. |

### Findings

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| 1 | High | **A roof changed under a permit after June 2023 gave a clean estimate.** Only new houses were caught, through the occupied date. | The city issued 350 residential `Addition` permits since June 2023. House 199138 has one from March 2024 on an unchanged footprint; without `--lidar` the round 1 code called it an estimate. | New permit lookup (one cached request) and the `permit-since-capture` site check. Benchmark building 14. |
| 2 | High | **A blocked roof was labelled "Status: ESTIMATE".** `summary.confidence` was `estimate` for clean and blocked roofs alike, and the report headline and the CLI printed it. | `takeoff.md` of 363456 in the round 1 output. | New `summary.siteCheckRequired`; the report and the CLI say "SITE CHECK REQUIRED"; the GLB carries the field. |
| 3 | Medium | **A plane could "agree" with lidar while lidar showed something else on it.** The fit ignores points off the plane, and nothing reported them. | 177261: a tree 4 m above the north plane (30% of its points). 235247: solid returns 0.7 to 1.5 m above two planes, most likely dormers the model lacks. 176864: 29% of the largest plane lies 0.4 m lower. Sample house 243577: 63% ground points under a 400 sq ft plane that "agreed". | Each plane records the share of points above, below and at ground level; the `lidar-surface` review flag names the planes. |
| 4 | Medium | **A download cut off half way crashed the run.** `IncompleteRead` skipped the retry loop. | 1 of 32 live runs in this round. | Retried like a timeout. |
| 5 | Low | A plane with no lidar points was described as "too small for a lidar check", also on new houses with 780 sq ft planes. | 363469 in the round 1 output. | Now "not checked: too few points". |
| 6 | Low | The report said overhangs "are already included" with no hint of how well the outline is known. | Claim 4 above. | The report gives the 4 in figure and asks for a taped eave. The error budget names the outline as the largest unknown. |
| 7 | Low | The licence pages said the resale sentence could not be found and that CC BY for the solids was an inference. | Claim 5 above. | `licenses.md`, `data-sources.md` and `SKILL.md` now quote the text and its address. |

### Tried and rejected

- **Refusing a lidar fit whose two halves disagree.** It would have refused 6 precise planes in 43 houses. On 3 of them lidar was right and the city wrong by 0.4 to 0.7 in 12, and on the other 3 the two sources were within 0.1 of each other. It also would have turned benchmark house 175156 into a site check for no gain.
- **Loosening the "precise" test.** Imprecise lidar fits are still closer to their house's common pitch than the city is (0.17 against 0.40 in 12, 26 planes). That argues for a "one house, one pitch" rule, which is more than a threshold change and should wait for a taped roof.

### Benchmark before and after

The table is in `references/benchmark.md`. Largest sloped-area change: 0.00%. Largest main-plane pitch change: 0.00 in 12. Line totals: unchanged. New flags: `lidar-surface` on 3 of the 8 clean houses, `permit-since-capture` on City Hall and on building 14. The baseline was the round 1 code run on the same cached city answers and lidar points.

Tests: 60, all passing (round 1 had 51). The studio check was not run again, because the roof geometry in the GLB did not change.

### Open issues for round 3, most important first

1. **No ground truth, and the outline is the part that needs it.** Pitch is worth 0.2 to 0.4% of area; the outline is uncertain by 2 to 4%. Tape one eave and one rake per study roof.
2. **`lidar-surface` cannot tell a tree from a dormer.** The return number can: the tree points on 177261 are 100% multiple returns, the points above 235247 are 6 to 14%. The cached points do not keep the return number. About 1 hour, and it would let a likely dormer become a stronger warning about missing area.
3. **"One house, one pitch" for small planes.** City pitches of imprecise planes are 0.40 in 12 from the house's common pitch.
4. **Additions without a permit.** NAIP 2025 photos (0.3 m, July 2025) are free and newer than the solid.
5. **Open edges on skewed planes.** An outer edge 11 to 35 degrees off its plane's contour is called a rake. On 235248 that is 55 ft on one plane, and on 176864 a 9 ft eave. The city model is the cause; the tool could at least flag such edges.
6. **Faces partly under the roof** (204065), and the GLB of City Hall holding 0.6% more area than `roof.json`. Both buildings are site checks.
7. **The permit rule is a first guess.** The 1 January 2023 cut-off is not tested, commercial `Demolition` permits may be interior work, and `Remodel/Renovation` is ignored.
8. **`OCCUPIEDDATE` can be years after the build.** 363456 is "occupied December 2025" and has a new-house permit from February 2021, so its `newer-than-solid` flag may be a false alarm.
9. Cleaning still moves outline corners (plan area up to 0.33% off the footprint).
10. The studio's own line totals, and the check in a real browser, are where round 1 left them.
