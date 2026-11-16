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

## Round 3 (2026-11-16)

**Change level: MODERATE.** The largest sloped-area change on the benchmark is +0.28% and the largest main-plane pitch change is 0.39 in 12, which is inside the MODERATE band (pitch between 0.1 and 0.5 in 12). Three failure modes are also detected now that were silent before: an open edge that is neither eave nor rake, a plane that faces the wrong way, and a permit answer that was cached for ever. It is not MAJOR: no bug was found in geometry, units or reprojection, no area moved by more than 2%, and no decision was reversed. It is not MINOR: three benchmark houses changed a main-plane pitch by 0.19 to 0.39 in 12.

**Verdict on the outline.** It cannot be measured better than about 4 in (0.10 m) for $0. Lidar agrees with the city outline within 0.05 m on average over 38 houses, but the method itself is only good to 0.08 m, and the 2025 aerial photos are worse. No area was moved. Every roof now carries a likely range: 2.3 to 4.4% on the clean benchmark houses.

**Verdict on `lidar-surface`.** Keep it, and split it. All three benchmark hits were real, but one was a tree, which does not put the roof in doubt. The lidar return count separates trees from solid surfaces with a wide gap, so trees now raise an info flag and the review flag is kept for surfaces the model lacks.

### Round 2's claims, checked

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | 0.1 m of outline is 2 to 4% of plan area | **Right on the benchmark, low for small roofs.** | Open-edge length times 0.1 m over plan area: 2.3 to 4.4% on the 8 clean houses, 2.5 to 5.3% on 30 random ones. |
| 2 | City outline against lidar edge: mean 0.02 m inside, scatter 0.07 m, worst 0.14 m | **The mean holds; the scatter was mostly lidar noise.** | 38 houses, 145 edges, 817 m. Mean -0.04 to +0.03 m depending on one setting of the method. House averages scatter by 0.09 m, of which 0.08 m is measurement noise. Round 2's worst house (235247, 8 in 12) is still the worst at 0.21 m inside (standard error 0.10); part of its offset came from a height band that is too tight on steep roofs. |
| 3 | The return number would separate trees from dormers | **Confirmed.** | 13 planes with points above the surface on 40 houses: 6 with 83 to 100% multi-return points (trees), 6 with 0 to 15% (solid), 1 mixed. The July 2025 photo shows the tree on 177261. |
| 4 | The permit point sits on the building | **Confirmed, and explained.** | On 30 houses every permit point is exactly on a city address point; the address point lies on the footprint on 8 of 8 houses. No neighbour's permit was matched, and none of the 30 houses raised a false site check. |
| 5 | `summary.siteCheckRequired` and the `IncompleteRead` retry | **Confirmed.** | Set on all five must-fail buildings, in the report headline and in the GLB. `IncompleteRead` is an `HTTPException`, which the retry loop catches. |
| 6 | `PREFER_LIDAR` held on 30 random houses | **Confirmed on a spot check.** | 5 of the 30 houses (seed 3), my own reader and fit: 14 of 16 precise main planes within 0.15 in 12 of a whole number against 9 for the city; lidar 0.14 steeper; my fit within 0.11 of the skill's. |
| 7 | City pitches of imprecise planes are 0.40 in 12 from the house's common pitch, lidar 0.17 | **Not reproduced.** | 71 imprecise planes with a precise plane of similar pitch on the same house: city 0.26, own lidar 0.22. Under 215 sq ft: 0.29 against 0.26. No case for a general "one house, one pitch" rule. |

### Findings

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| 1 | High | **An area was printed with no hint of how far off it can be.** The outline is the largest error and the report gave one number to the square foot. | Section 1 of the research note `review-round-3.md`. | `summary.areaRange` and a "likely range" line in the report and the CLI: outline 0.10 m along the open edges, plus pitch (0.3 degree from lidar, 1 degree from the city). |
| 2 | Medium | **A sharp lidar fit was thrown away when a second surface lay beside it.** The largest plane of 176864 kept a city pitch 0.2 in 12 low, although lidar fits it to 0.09 degree and the other side of the ridge has the same pitch. | 4 planes on 38 houses; on all 4 the lidar pitch is near a whole number (0.09 in 12 away) and the city pitch is not (0.29). | A fit that fails "precise" only on the 80% rule supplies the pitch when a precise main plane of the same house agrees within 0.5 degree (`_confirm_by_sibling`). |
| 3 | Medium | **The permit answer was cached for ever.** A permit issued after the first run was never seen on a repeat run. | `Http.get_json` returned any cached file. | The permit answer is asked again after 30 days; the old answer is used when the service does not respond. |
| 4 | Medium | **`lidar-surface` treated a tree like a missing dormer.** | 177261 (tree) and 235247 (solid) got the same review flag. | Cached points keep the return count. `tree-over-roof` (info) for trees; `lidar-surface` (review) says "solid surface" when it is one. |
| 5 | Medium | **Open edges that are neither eave nor rake were silently counted as rake.** | 14 of 39 houses have 10 ft or more of them (71 ft on 235248). On 4 edges lidar shows the plane is drawn 11 to 16 degrees askew and the edge is really level. | `skewed-edge` and `lidar-azimuth` review flags. No edge was re-classed: there is no ground truth for it. |
| 6 | Low | **The report showed a lidar pitch fitted to 6 points.** "16.6/12 (+24.5 deg, 6 pts)" beside a 36 sq ft plane on 235247. | `takeoff.md` of 235247 in the round 2 output. | A lidar pitch is shown only for a plane that was checked. |
| 7 | Low | **One pitch printed two ways in one row** (7.8/12 and 7.9/12 for 33.2 degrees), lines to a tenth of a foot, areas with and without thousands separators, lidar shift in metres in a report in feet. | Same file. | One pitch formatter, whole feet for lines with a note that an edge is good to about 1 ft, commas, feet. |
| 8 | Low | **The 12 in overhang default could be read as something to add.** | `assumptions.overhangM` in `roof.json`. | Its note now says it is not added to any area or length. |
| 9 | Low | Repair and remodel permits were invisible. | 5 of 30 random houses have one since 2023. | `permit-other` info flag. They stay out of the site check: about 7,100 were issued since 2023. |
| 10 | Low | The docs gave the laser spot as 0.5 m wide and the outline check as "8 houses". | The strength of a roof return fades over 0.9 m across a rake. | Docs corrected. |

### Checked and found correct

- **Re-tilt consistency after the new rule.** On all 12 buildings but City Hall the GLB holds the same sloped area as `roof.json` within 0.004%; each plane's area is its plan area over cos(pitch) within 0.13%; edge lengths match their end points to 1.4 mm.
- **Benchmark rules.** Buildings 9 to 12 and 14 are site checks, building 14 also without `--lidar`; point 13 fails cleanly; plan area is within 0.33% of the footprint on buildings 1 to 8; precise main planes show their lidar pitch within 0.19 degree.
- **Permit classes.** `New%` matches new houses, town homes and duplexes only. Sheds and accessory buildings have their own classes.

### Tried and rejected

- **A physical model of the lidar pulse at a roof edge** (spot size, detection threshold, bright gutter). The fitted eave position moved between 0.22 m outside and 0.40 m inside the city line depending on which parameters were free. The data does not hold the answer.
- **NAIP 2025 for the outline.** Roofs are shifted 0.3 to 1.5 m in the photo; one clean eave-to-eave length agreed with the city within 0.15 m; the rest were blocked by trees or shadow.
- **A per-house "outline is off" flag from lidar.** The lidar noise per house (0.08 m) is as large as the tolerance. It would have fired on 1 house in 38, at two standard errors.
- **A general "one house, one pitch" rule for small planes.** See claim 7.
- **Re-classing slanted open edges as eaves.** Physically likely, but it would move up to 71 ft between eave and rake on a benchmark house with nothing to check it against.

### Benchmark before and after

The table is in `references/benchmark.md`. Largest sloped-area change: +0.28% (176864). Largest main-plane pitch change: 0.39 in 12 (235247 plane 3). Predominant pitch changed on one house (176864, 4.66 to 4.85). Line totals moved by 0.2 ft at most. No building changed between estimate and site check. The baseline was the round 2 code (tag `roof-measure-v3`) on the same cached city answers and lidar nodes.

Tests: 69, all passing (round 2 had 60). The studio check was not run; the GLB area was compared with `roof.json` directly instead.

### Open issues for round 4, most important first

1. **Tape one roof.** Measure one eave-to-eave width at the shingle edge and one rake-to-rake length. If the city line is on the gutter lip, the width will read 8 to 10 in short. It would settle the largest open question in the error budget and could roughly halve the range. Nothing free can replace it.
2. **House 235247: the main eave may be drawn 0.4 m too far out.** Lidar has no roof returns in the outer 0.25 m of a 14 m eave. That is 2 standard errors, so it is a lead, not a finding. It would be about 6% of that plane.
3. **Slanted open edges.** Decide with photos or a tape whether edges 10 to 45 degrees off level should count as eaves. On 235248 it moves 71 ft.
4. **The confirmed-by-another-plane rule stops at planes that agree.** A sharp fit that is 1.5 to 4 degrees from the city and is confirmed by another plane is still a site check. Letting it override would remove some site checks; it needs more than the 4 cases seen so far.
5. **Faces partly under the roof** (204065) and City Hall's GLB holding 0.6% more area than `roof.json`. Both are site checks.
6. **Ridge against hip on low-slope hip roofs** (235246) is still unstable by a few feet. Not looked at in this round.
7. **Cleaning moves outline corners.** Plan area is up to 0.33% off the footprint (176864). The area range is ten times that, so this is no longer urgent.
8. **The permit rule's 1 January 2023 cut-off is untested**, and a permit whose address point lies off the building would be missed without a word.
9. **`OCCUPIEDDATE` can be years after the build** (363456), so `newer-than-solid` may be a false alarm there.
10. **The "solid surface" calls rest on lidar alone.** A 0.3 m photo cannot show a dormer.
11. The studio's own line totals, and the check in a real browser, are where round 1 left them.
