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
- Cleaning the city faces so they are flat and meet exactly changed sloped area by 0.25% or less on all six test houses, and pitch by under 0.1 degree on five of them. On the sixth, a low-slope hip roof, it moved one inside corner 0.55 m and changed one pitch by 0.5 degree; the tool flags that case as `regularize`.

## What the tool checks on every roof

1. Roof plan area against the city footprint area. More than 1% apart raises `plan-area-mismatch`.
2. Highest roof point against the footprint's top elevation. More than 1.5 ft apart raises `top-height-mismatch`.
3. Flatness of each delivered face. More than 0.5 ft out of flat raises `non-planar-face`.
4. With `--lidar`: the pitch of each plane, and the horizontal shift between the two sources.
5. Provenance on every plane and edge, or the tool refuses to write the file.

## Lidar reconcile thresholds

The values live at the top of `scripts/roofmeasure/lidar.py`. They are the plan's proposal and are not tuned yet.

| Setting | Value |
|---|---|
| Points needed to check a plane | 40, counted at least 0.3 m inside the plane outline and 2 m above ground |
| Agree | Pitch difference of 1.5 degrees or less: keep the city pitch |
| Override | 1.5 to 4 degrees with a fit error of 0.10 m or less: use the lidar pitch, flag for review |
| Site check | More than 4 degrees, a noisy fit, or fewer than half the points on one plane |
| Plane fit | RANSAC with a 0.10 m band and a fixed seed, then least squares |

When lidar overrides a plane, the sloped area becomes plan area divided by the cosine of the lidar pitch. The 3D geometry is not re-tilted.

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
- `lidar-override`: a pitch came from lidar. Look at that plane in the report.
- `lidar-no-check`, `outline-shift`, `top-height-mismatch`: the independent check is weak or shows a mismatch.

**Info flags**

- `small-planes`, `hidden-faces`, `not-residential`, `newer-than-lidar`: no action needed; they explain what the data can and cannot show.

## What the data cannot measure

- The wall line. Overhang is a typed default of 12 in with confidence `assumed`.
- Anything built or changed after June 2023, and for the lidar check after 2020.
- Chimneys, pipe boots, skylights and most dormers under about 30 sq ft.
- The true accuracy of the city solid. The city publishes none, which is why the study in `references/implementation-plan.md` comes first.
