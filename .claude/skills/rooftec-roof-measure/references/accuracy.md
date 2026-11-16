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
- The city outline is the roof edge within about 0.07 m, measured against lidar returns on 6 houses. That bounds the plan-area error at roughly 2% per house, with no sign of a bias. Lidar cannot do better: its laser spot is about 0.5 m wide.
- The city pitch is about 0.16 in 12 (0.6 degree) lower than the lidar pitch on average. Left uncorrected, that understates sloped area by 0.2 to 0.4%.

## What the tool checks on every roof

1. Roof plan area against the city footprint area. More than 1% apart raises `plan-area-mismatch`. The solid is built on the footprint, so this catches a wrong or broken solid; it says nothing about how accurate the footprint is.
2. Highest roof point against the footprint's top elevation. More than 1.5 ft apart raises `top-height-mismatch`.
3. Flatness of each delivered face. More than 0.5 ft out of flat raises `non-planar-face`.
4. With `--lidar`: the pitch of each plane, and the horizontal shift between the two sources.
5. Provenance on every plane and edge, or the tool refuses to write the file.

## Lidar reconcile thresholds

The values live at the top of `scripts/roofmeasure/lidar.py`. Review round 1 set them from the benchmark; the accuracy study should tune them against ground truth.

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

- An independent fit, with no code from this skill, finds the same difference: lidar is steeper than the city by 0.16 in 12 on average.
- Houses are framed at whole-number pitches, and the lidar pitches of main planes land on them: 8, 6, 6, 4 and 5 in 12 on five benchmark houses, each within about 0.15. The city pitches of the same planes are 0.1 to 0.4 lower and scatter more.
- A fit through 100 or more points over a 4 m run is precise to about 0.1 degree. A city plane rests on a few corner heights.

This is indirect evidence. The accuracy study is still needed, and it can overturn the rule.

## Flags and what to do

Severity `site-check` blocks use. Severity `review` means look at the named item. Severity `info` is context.

**Site-check flags**

- `plan-area-mismatch`: the solid and the footprint disagree. Check that it is the right building; on older multi-unit buildings the solid itself may be poor.
- `lidar-disagrees`: one or more planes differ from lidar by more than the limit, or lidar finds no clean plane. The roof may have changed, or trees cover it.
- `newer-than-solid`: built or occupied after June 2023.

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

**Info flags**

- `small-planes`, `hidden-faces`, `duplicate-faces`, `not-residential`: no action needed; they explain what the data can and cannot show.
- `lidar-pitch`: planes that agree with lidar show the lidar pitch. The city pitch is in `roof.json` as `cityPitchDeg`.
- `split-ridge`: the city drew a ridge as two plane tops with a wall a few centimetres tall between them. The tool counts it as one ridge.
- `newer-than-lidar`: built or occupied after the lidar flight of 19 and 20 December 2020. It is a review flag when lidar was run, because lidar then shows the lot before the house was finished.

## What the data cannot measure

- The wall line. Overhang is a typed default of 12 in with confidence `assumed`.
- Anything built or changed after June 2023, and for the lidar check after December 2020.
- Chimneys, pipe boots, skylights and most dormers under about 30 sq ft.
- The true accuracy of the city solid. The city publishes none, which is why the study in `references/implementation-plan.md` comes first.
