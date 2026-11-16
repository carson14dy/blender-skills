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
- With plan area inside 1% and pitch inside 1 degree, the combined area error is about 1.3% (root sum of squares).
- Cleaning the city faces so they are flat and meet exactly changes sloped area by 0.25% or less and plan area by 0.33% or less on the benchmark. It changes pitch by under 0.1 degree on most houses; on a low-slope hip roof and on a twin home it moved a corner about 0.6 m and one pitch by 0.5 to 1.4 degrees. The tool flags those cases as `regularize`.
- **The outline is the largest unknown, not the pitch.** Lidar puts the city outline at the roof edge with a scatter of 0.07 m and a worst case of 0.14 m on 8 houses, and no lean in or out (mean 0.02 m inside). Lidar cannot see finer than that: its laser spot is about 0.5 m wide. A strip 0.1 m wide around a house is 2 to 4% of its plan area, so lidar cannot confirm the 2% area target. Only a taped eave can.
- The city pitch is about 0.13 in 12 (0.5 degree) lower than the lidar pitch on average. Left uncorrected, that understates sloped area by 0.2 to 0.4%, which is small next to the outline.

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
| Override | 1.5 to 4 degrees with a precise fit: use the lidar pitch, flag for review |
| Site check | More than 4 degrees, or 1.5 to 4 degrees with an imprecise fit, or fewer than half the points on one plane |
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
- Using lidar on imprecise fits too. Even those are closer to the house's common pitch than the city is (0.17 against 0.40 in 12 on 26 planes), so a "one house, one pitch" rule would help small planes. It is left for the accuracy study because it changes more than a threshold.

## Flags and what to do

Severity `site-check` blocks use. Severity `review` means look at the named item. Severity `info` is context.

**Site-check flags**

- `plan-area-mismatch`: the solid and the footprint disagree. Check that it is the right building; on older multi-unit buildings the solid itself may be poor.
- `lidar-disagrees`: one or more planes differ from lidar by more than the limit, or lidar finds no clean plane. The roof may have changed, or trees cover it.
- `newer-than-solid`: built or occupied after June 2023.
- `permit-since-capture`: the city issued an addition, new-building, razing, demolition or relocation permit for this building on or after 1 January 2023, so the June 2023 model probably does not show the work. A reshingle permit never raises it.

**Review flags about the model**

- `eave-under-wall`: a level joint under a wall at the bottom of a plane. The city model probably replaced a gable tie-in with a wall; expect valleys there on the real roof.
- `roof-step`: plane tops that end at a wall drop. This is either a real step between roof tiers or a ridge the model split.
- `regularize`, `non-planar-face`, `overlapping-faces`: the city faces fit together poorly. Trust the area less.
- `low-slope`: a plane under 2/12. Confirm the roofing material on site.
- `solid-match`, `point-off-building`, `accessory-structure`: the tool may have picked the wrong building.

**Review flags about the check**

- `no-lidar-check`: run again with `--lidar`.
- `lidar-override`: lidar and the city differed by 1.5 to 4 degrees on a plane and the lidar pitch was used. Look at that plane in the report.
- `lidar-no-check`, `outline-shift`, `top-height-mismatch`: the independent check is weak or shows a mismatch.
- `lidar-surface`: lidar sees more than the roof surface inside a plane, and the plane fit ignores those points, so the plane can still "agree". The message says which of three cases it is. Points above the surface (10% or more of the points, more than 0.3 m up) mean a tree over the roof, or a dormer or upper roof that the city model does not show; expect extra area and valleys if it is a dormer. Points below the surface mean a lower roof or a step the model drew as one plane. Points at ground level (25% or more) mean that part was built after the lidar flight, or is a deck or porch under 2 m. Look at the plane in a photo before you trust its area.

**Info flags**

- `small-planes`, `hidden-faces`, `duplicate-faces`, `not-residential`: no action needed; they explain what the data can and cannot show.
- `permits-not-checked`: the permit lookup did not run (offline, or the city service did not answer). Run again online before you rely on the roof being unchanged.
- `lidar-pitch`: planes that agree with lidar show the lidar pitch. The city pitch is in `roof.json` as `cityPitchDeg`.
- `split-ridge`: the city drew a ridge as two plane tops with a wall a few centimetres tall between them. The tool counts it as one ridge.
- `newer-than-lidar`: built or occupied after the lidar flight of 19 and 20 December 2020. It is a review flag when lidar was run, because lidar then shows the lot before the house was finished.

## What the data cannot measure

- The wall line. Overhang is a typed default of 12 in with confidence `assumed`.
- Anything built or changed after June 2023 without a permit, and for the lidar check after December 2020.
- Chimneys, pipe boots, skylights and most dormers under about 30 sq ft.
- The true accuracy of the city solid. The city publishes none, which is why the study in `references/implementation-plan.md` comes first.
