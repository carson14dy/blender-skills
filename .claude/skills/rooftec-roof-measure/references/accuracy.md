# Accuracy: targets, error budget and flags

Treat every number from this skill as an estimate until the accuracy study passes. This page says what "good enough" means, what the tool checks by itself, and what each flag asks you to do.

## Targets

These come from the plan (`plans/Roof accuracy and quality plan.md`, section 2).

| What | Target |
|---|---|
| Sloped roof area | Within 2% of ground truth |
| Pitch on planes of 215 sq ft or more | Within 1 degree, which is about 1/4 in 12 near 6/12 |
| Each line total (ridge, hip, valley, eave, rake) | Within 3% or 2 ft, whichever is larger |
| Roof outline position | Within 0.5 m of the lidar roof |
| Provenance | Every measured value has a source, a capture date and a confidence class |

`python3 scripts/roof.py compare --roof <roof.json> --truth <truth.json>` scores a roof against the first three targets and writes `accuracy.md` beside the roof file.

## Error budget

- One degree of pitch error changes sloped area by about 0.9% at 6/12. That is why the pitch target is 1 degree and not 1 in 12, which would be about 4 degrees.
- With plan area inside 1% and pitch inside 1 degree, the combined area error is about 1.3% (root sum of squares). The outline does not reach 1% today; see the area range below.
- Cleaning the city faces so they are flat and meet exactly changes sloped area by 0.25% or less and plan area by 0.33% or less on the benchmark. It changes pitch by under 0.1 degree on most houses; on a low-slope hip roof and on a twin home it moved a corner about 0.6 m and one pitch by 0.5 to 1.4 degrees. The tool flags those cases as `regularize`.
- **The outline is the largest unknown, not the pitch.** On 38 houses the city outline is the lidar roof edge within 0.05 m on average, the real spread between houses is about 0.05 m, and the lidar method itself is good to about 0.08 m (its laser spot is 0.5 to 1 m wide). Together that is 0.10 m, or 4 in. A strip that wide along the eaves and rakes is 2.3 to 5.4% of the plan area, more on small and cut-up roofs. Lidar and the 2025 aerial photos cannot narrow it, so the 2% area target cannot be confirmed from free data. Only a taped eave-to-eave width can.
- The city pitch is about 0.13 in 12 (0.5 degree) lower than the lidar pitch on average. Left uncorrected, that understates sloped area by 0.2 to 0.4%, which is small next to the outline.
- **Roof hidden under an upper roof's overhang is not counted (review round 4).** Seen from above, the city planes never overlap: on 5 houses their plan areas add up to the footprint within 0.2%. On a real house a lower roof that meets a wall runs on under the eave or rake of the roof above. That strip is real roofing and it is in no number. With a 12 in overhang it is 1.3% of the sloped area on the median of 59 houses, nothing on a plain gable or hip (9 houses), more than 2% on 19 houses and 5% on the worst. It always points the same way: the area is too small. The overhang width is not in any free data, so this is an inference from the geometry, not a measurement.

## The area range

Every roof carries a likely range for its sloped area, in `summary.areaRange` and in the report. Quote it with the area.

1. **Outline part.** The length of the open edges (eaves, rakes and free plane tops, seen from above) times 0.10 m, as a share of the plan area. On the benchmark houses this is 2.3 to 4.4%.
2. **Pitch part.** For each plane, tan(pitch) times the pitch tolerance: 0.3 degree where lidar set the pitch, 1 degree where the city pitch was kept. On clean houses this is 0.1 to 0.4%.
3. The two are combined as independent errors (root sum of squares).

The values are `OUTLINE_TOLERANCE_M`, `PITCH_TOLERANCE_LIDAR_DEG` and `PITCH_TOLERANCE_CITY_DEG` in `scripts/roofmeasure/export.py`. The range is what the evidence supports, not a guarantee. It does not cover a roof that was changed, a dormer the model lacks or a wrong building; the flags cover those. One taped eave-to-eave width, measured at the shingle edge, is the cheapest way to narrow it, and it would also show whether the city line follows the shingles or the gutter.

Review round 4 derived the range again with a separate method on 5 houses: growing the roof outline by 0.10 m, and a random trial over outline and pitch errors. Simple roofs match to 0.05 percentage points. On cut-up roofs the tool's range is wider than the outer outline alone gives (3.3 against 2.8%), because it also counts the edges where an upper roof ends above a lower one.

**The strip under an overhang is reported beside the range, not inside it.** `summary.areaRange.underOverhang` gives the length of the roof-to-wall joints, the assumed overhang (12 in, confidence `assumed`) and the area and share that would be hidden. The report prints it as "Not counted" when it is 5 sq ft or more. Joints the model most likely invented (`eave-under-wall`) are left out. To settle it, measure the overhang at one roof-to-wall joint on site and multiply by the joint length.

## What the tool checks on every roof

1. Roof plan area against the city footprint area. More than 1% apart raises `plan-area-mismatch`. The solid is built on the footprint, so this catches a wrong or broken solid; it says nothing about how accurate the footprint is.
2. Highest roof point against the footprint's top elevation. More than 1.5 ft apart raises `top-height-mismatch`.
3. Flatness of each delivered face. More than 0.5 ft out of flat raises `non-planar-face`.
4. With `--lidar`: the pitch of each plane, and the horizontal shift between the two sources.
5. Provenance on every plane and edge, or the tool refuses to write the file.

## Lidar reconcile thresholds

The values live at the top of `scripts/roofmeasure/lidar.py`. Review round 1 set them from the benchmark, and review round 2 checked them on 30 more houses and left them as they are. The accuracy study should tune them against ground truth.

| Setting | Value |
|---|---|
| Points needed to check a plane | 40, at least 2 m above ground and 0.6 m inside the plane outline (0.3 m when that leaves fewer than 80 points) |
| Precise fit | 80% or more of the points on one plane, and a pitch standard error of 0.25 degree or less |
| Agree | Pitch difference of 1.5 degrees or less. A precise fit supplies the pitch; otherwise the city pitch is kept |
| Confirmed by another plane | A fit that agrees, has a standard error of 0.25 degree or less and fails "precise" only on the 80% rule supplies the pitch when a precise plane of 215 sq ft or more on the same house has the same pitch within 0.5 degree. When that pitch is more than 1.5 degrees from the city pitch, the plane is reported as an override |
| Override | 1.5 to 4 degrees with a precise fit: use the lidar pitch, flag for review |
| Site check | More than 4 degrees, or 1.5 to 4 degrees with an imprecise fit, or fewer than half the points on one plane |
| Small plane, pitch not settled | When every such plane is under 215 sq ft, differs by 4 degrees or less, has half or more of its points on one surface, and together they cover 10% of the roof or less, the house gets a review flag in place of a site check |
| Allowance for an imprecise fit | Twice its own standard error is taken off the difference first |
| Plane fit | RANSAC with a 0.10 m band and a fixed seed, then least squares |

When lidar supplies a pitch, the plane is re-tilted in the 3D model: it keeps facing the way the city face does, the outline corners stay on their wall lines, and the corners are solved again. Plan area does not change, so sloped area, rakes and hips follow the new pitch, and `roof.json`, `roof.glb` and the report describe the same roof. Set `PREFER_LIDAR = False` to go back to keeping the city pitch when the two agree.

### Why lidar supplies the pitch

Review round 2 tested this rule on 30 houses picked at random that the rule was not built on (94 main planes with a precise fit). It held.

- **Whole-number pitches.** Roofs are framed at whole-number pitches. 85% of the lidar pitches are within 0.15 in 12 of a whole number, against 50% of the city pitches; chance would give 30%. On average lidar sits 0.04 below the nearest whole number and the city 0.14 below.
- **One house, one pitch.** The large planes of one house mostly share a pitch. Their lidar pitches are closer together than their city pitches on 29 of 33 houses.
- **Lidar agrees with itself.** Where two flight lines cross a house, at scan angles 22 degrees apart, their pitches differ by 0.01 to 0.04 in 12. Moving the edge inset from 0.3 m to 1.0 m changes a large plane by 0.1 at most. The pitch standard error the tool computes matches the scatter between two halves of a plane.
- **No snow.** The airport weather station recorded no snowfall and zero snow depth for the five weeks before the flight on 19 and 20 December 2020.
- **The size of the bias.** Lidar is steeper than the city by 0.12 in 12 on the 30 new houses and 0.15 on the benchmark; lidar is the steeper one on 90% of planes.

This is still indirect evidence, because no roof has been taped. It is now strong enough that a tape is more likely to adjust the thresholds than to overturn the rule.

Two things were tried in round 2 and not adopted:

- Refusing a fit when the two halves of a plane give different pitches. On the 6 planes it would have refused, the lidar pitch was the better one on 3 and within 0.1 in 12 of the city on 3.
- Using lidar on imprecise fits too. Round 2 measured 0.17 against 0.40 in 12 from the house's common pitch on 26 planes. Round 3 measured it again on 71 imprecise planes that have a precise plane of similar pitch on the same house: the city is 0.26 in 12 away on average and the plane's own lidar pitch 0.22, and for planes under 215 sq ft 0.29 against 0.26. That is too small a gain for a general "one house, one pitch" rule.

Round 3 adopted one narrow case, "confirmed by another plane" in the table above. The 80% rule guards against a fit pulled off the roof by a tree or a second surface; a sharp fit that lands on the pitch of a precise plane of the same house was not pulled anywhere. All 4 such planes on 38 houses moved to a whole-number pitch (the city was 0.29 in 12 from one on average, lidar 0.09). On benchmark house 176864 it is the largest plane: the model drew three roof sections as one face, lidar fits the middle one, and its pitch equals the other side of the ridge.

Review round 4 tested the rule on 20 more houses that no earlier round had measured. It fired on 7 planes there, 11 in all on 64 houses. The test was a fit on only the part of each plane that lies more than 1 m from any off-surface point. On the 9 planes where enough points were left, all of those points lie on one surface, and their pitch is closer to the pitch the rule used (0.44 degree away at most) than to the city pitch on all 9. All 11 planes moved towards a whole-number pitch, and the pitch stays within 0.1 degree when the fit is started from other random seeds. Two of the 11 were more than 1.5 degrees from the city pitch (1.5 and 1.8) and carried no flag; such a plane is now an override.

**Why a small plane with an unsettled pitch is not a site check.** On 51 random houses, 9 were a site check because of lidar. On 3 of them the cause was one plane of 188 to 208 sq ft where lidar sees one clean surface 2.3 to 3.6 degrees from the city pitch with a standard error just over the 0.25 degree limit (0.251 and 0.252 on two of them). Either pitch gives a total area within 0.21% of the other. The plane still shows "site check" in the report, and the flag names it.

## Flags and what to do

Severity `site-check` blocks use. Severity `review` means look at the named item. Severity `info` is context.

Review round 4 counted the flags on 51 random houses. A house carried 2.6 review flags on average and only 4 houses had none, mostly because of flags that asked for nothing. Four flags now use `review` only when the amount matters, and `lidar-pitch` is gone. The average is 1.7, and 12 houses have none. The table is in `references/review-log.md`.

**Site-check flags**

- `plan-area-mismatch`: the solid and the footprint disagree. Check that it is the right building; on older multi-unit buildings the solid itself may be poor.
- `lidar-disagrees`: one or more planes differ from lidar by more than the limit, or lidar finds no clean plane. The roof may have changed, or trees cover it. It is a review flag, not a site check, when only small planes are affected (see "Small plane, pitch not settled" above): check the pitch of the named plane on site.
- `newer-than-solid`: built or occupied after June 2023.
- `permit-since-capture`: the city issued an addition, new-building, razing, demolition or relocation permit for this building on or after 1 January 2023, so the June 2023 model probably does not show the work. A reshingle permit never raises it.

**Review flags about the model**

- `eave-under-wall`: a level joint under a wall at the bottom of a plane. The city model probably replaced a gable tie-in with a wall; expect valleys there on the real roof.
- `roof-step`: plane tops that end at a wall drop. This is either a real step between roof tiers or a ridge the model split. Review from 10 ft; info below that (about half of all houses have a few feet).
- `regularize`: making the planes flat, or giving them the lidar pitch, moved a corner. The ridge, hip and valley lines that meet there can be off by about that much. Review from 2 ft, or when a gap is left; info from 1 ft, which is inside what the report says about any line end.
- `non-planar-face`, `overlapping-faces`: the city faces fit together poorly. Trust the area less.
- `low-slope`: a plane under 2/12. Confirm the roofing material on site.
- `solid-match`: more than one city solid touched the footprint. Review when the chosen one overlaps poorly or its plan area does not match the footprint; info when both fit, which is the usual case of a neighbour's solid close by.
- `point-off-building`, `accessory-structure`: the tool may have picked the wrong building.

**Review flags about the check**

- `no-lidar-check`: run again with `--lidar`.
- `lidar-override`: lidar and the city differed by 1.5 to 4 degrees on a plane and the lidar pitch was used. The message names the planes. About one house in four has it.
- `lidar-no-check`, `outline-shift`, `top-height-mismatch`: the independent check is weak or shows a mismatch.
- `lidar-surface`: lidar does not see the modelled surface on part of a plane, and the plane fit ignores those points, so the plane can still "agree". The message says which case it is. A solid surface above the plane (10% or more of the points, more than 0.3 m up, 30% or fewer of them from multi-return pulses) is a dormer or raised roof part the city model does not show; expect extra area and valleys. Points below the surface mean a lower roof part or a step the model drew as one plane. Points at ground level (25% or more) mean that part was built after the lidar flight, or is a deck or porch under 2 m. Look at the plane in a photo before you trust its area and lines. On 64 houses this fires on about one in three. Round 4 looked at all 22 hits: the part lidar does not see as modelled is 0.7% of the roof at the least and 2% or more on 20 of them, so it stays a review flag.
- `skewed-edge`: 10 ft or more of open edge is counted as rake but runs less than 45 degrees off the level line of its plane. Water runs off such an edge like an eave. Either the model drew the plane askew or it merged roof facets over an angled wall. Check on a photo whether those edges need eave treatment (drip edge, starter, ice barrier, gutter). Review from 30 ft (one house in six); info from 10 ft, because that little does not change an order. The 30 ft line is a judgement, not a measured limit.
- `lidar-azimuth`: a plane faces 8 degrees or more away from where lidar sees it (planes of 2/12 or steeper with 40 lidar points). The pitch check does not see this. Its edges are probably drawn askew.

**Info flags**

- `small-planes`, `hidden-faces`, `duplicate-faces`, `not-residential`: no action needed; they explain what the data can and cannot show.
- `tree-over-roof`: a tree hangs over a plane (the lidar points above it come from pulses with several returns). The roof under it is taken from the city model; lidar checked only the open part. No action needed.
- `permit-other`: a `Repair` or `Remodel/Renovation` permit was issued since January 2023. Such work seldom changes the roof shape; ask the owner.
- `permits-not-checked`: the permit lookup did not run (offline, or the city service did not answer). Run again online before you rely on the roof being unchanged.
- Planes that agree with lidar show the lidar pitch with no flag. The report's lidar section counts them, and the city pitch is in `roof.json` as `cityPitchDeg`. (The `lidar-pitch` flag fired on every house and was removed in round 4.)
- `split-ridge`: the city drew a ridge as two plane tops with a wall a few centimetres tall between them. The tool counts it as one ridge.
- `newer-than-lidar`: built or occupied after the lidar flight of 19 and 20 December 2020. It is a review flag when lidar was run, because lidar then shows the lot before the house was finished.

## What the data cannot measure

- The wall line. Overhang is a typed default of 12 in with confidence `assumed`; it is not added to any area or length, because the city outline already is the roof edge. It is used for one thing: the "not counted" strip under upper-roof overhangs.
- The lower roof under the overhang of an upper roof (see the error budget).
- The roof edge closer than about 4 in, or whether the outline follows the shingles or the gutter.
- Anything built or changed after June 2023 without a permit, and for the lidar check after December 2020.
- Chimneys, pipe boots, skylights and most dormers under about 30 sq ft.
- The true accuracy of the city solid. The city publishes none, which is why the study in `references/implementation-plan.md` comes first.
