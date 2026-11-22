# Roof pitch

A pitch is never assumed and never asked for. It is worked out, and reported with its method, its source and its uncertainty. The tool is `scripts/roof_pitch.py` (plain Python and numpy; Blender's Python has both). Each command prints one JSON line with `slope`, `rise_per_12`, `sigma_per_12`, `degrees`, `sigma_degrees`, `nearest_whole`, `label`, `confidence`, `checks` and `notes`; `--out pitch.json` saves it.

## 1. Use the best source there is

| Rank | Source | Expect | How |
|---|---|---|---|
| 1 | Pitch gauge or level on the roof | ±0.25/12 | `record --method gauge --value 6/12 --source "gauge, south facet, 2026-11-20"` |
| 2 | LiDAR plane fit | ±0.05 to 0.1/12 | `property-model-pipeline/scripts/pm.py lidar`, then `record --method lidar` with the facet's slope |
| 3 | Measured model or scan in Blender | as good as the model | `acceptance_check.py -- --measure "House_*"` (each mesh gets `rise_per_12`) or `roof_core` `pitches_per_12`, then `record --method model`; `points --file facet.npy` for a scan patch |
| 4 | Measurement report | ±0.5/12 per facet | `record --method report`, source = the report and its date |
| 5 | Permit plan set, elevation sheet | ±0.5/12; design intent | `record --method plans`, source = permit and sheet. New homes and additions only; a re-roof permit has no drawings; later changes are not on it. Always cross-check. |
| 6 | Photo of a gable end | the tool's sigma, at least 0.25/12 | `photo`, section 3 |
| 7 | New design, nothing to measure | a rule | `rule`, section 4 |

`--source` is required and names the document: report and date, sheet number, or file. Uncertainties are from `property-model-pipeline/references/accuracy-budget.md`, which also warns that a photo taken at an angle to the gable is biased unless the wall is rectified first (trap 12).

## 2. Cross-check
Use the best source, and one more when there is one: `roof_pitch.py combine a.json b.json`. The result is the inverse-variance mean. An input more than 3 of its own sigma from it is listed in `checks.conflicts`, `agree` is false and `confidence` is low. Report a conflict to the user with both numbers and sources; never average it away. A `rule` result cannot be combined: it is a choice, not a reading.

## 3. Photo of a gable end
```
python scripts/roof_pitch.py photo --image IMG_2041.jpg --points pts.json --overlay out/gable_lines.png --out pitch.json
```
`pts.json`, in pixels of the image as you saw it:
```json
{"view_size": [1568, 1176], "rect_name": "door",
 "rect": [[412, 980], [498, 978], [500, 792], [410, 795]], "rect_size": ["36in", "80in"], "rect_tol": "0.25in",
 "rakes": [[[150, 540], [640, 300]], [[1130, 545], [660, 300]]],
 "horizontals": [[[160, 700], [1120, 705]]], "verticals": [[[140, 560], [142, 1010]]]}
```
- `rect`: rough corners, bottom-left, bottom-right, top-right, top-left, of a rectangle on the gable wall whose real size is known: a door, a garage door, a window from its spec. `rect_size` is width then height (in, ft, m, cm or mm).
- `view_size`: the image size as you saw it. The tool scales the points to the file, which is often larger.
- `rakes`: two points along each rake edge, low then high; one or two rakes. `horizontals` and `verticals` are optional extra lines on the wall (siding, window edges, corner boards); more lines steady the result.
- Rough clicks are fine: each line is refined on the image first. The pitch comes from vanishing points, so the view need not be square-on, and a rake board that hangs in front of the wall gives no bias.

Rules:
- The whole gable and the known rectangle are on the same wall, in the original file: not a screenshot, not cropped or rotated (`view_size` must have the file's shape).
- The size must be right. The image cannot tell a 36 x 80 in. door from a window: a 1.2 m window given as that door read 13.28/12 on a 6/12 test gable, with `confidence` ok. Measure the reference or read it from the product, say whether you clicked the slab or the casing, and cross-check with a second source.
- Open the overlay. Every green line must sit on a wall edge and every red line on its rake. This is the look gate for the method.
- `confidence` is low when a line's residual is above 1.5 px, the two rakes differ by more than 0.5/12, the rectangle's diagonals disagree by more than 1 %, a line kept fewer than 8 edge points, or another edge within 18 px of a rectangle line's clicks is at least 0.75 as strong as the edge it took (`rect_second_edge`: a slab inside its casing, experiment 027). A low result is never used alone.
- Sigma is at least 0.25/12 for a real photo: lens distortion, wall flatness and nominal sizes are not in the fit. `--synthetic` lifts that floor, for rendered test images only.
- On synthetic gables (`tests/test_pitch.py`), clicks 6 to 10 px off read 6/12 seen square-on and 25 degrees off as 6.00 and 5.98, 4/12 at 35 degrees as 4.00, and 12/12 at 30 degrees as 12.00.

## 4. New design: the user's rule
`lab/data/design-rules.json` holds the standing rules the user approved once (`approved_by`, `approved_on`): match the main house when there is one, else `new_build_pitch` for the building type.
```
python scripts/roof_pitch.py rule --covering asphalt_shingle --building accessory --out pitch.json
python scripts/roof_pitch.py rule --covering asphalt_shingle --building accessory --match 5.95/12
```
`--match` takes the main house's measured pitch and rounds it to the nearest whole. Then the code check: asphalt shingles need 2/12 or more, with double underlayment from 2/12 up to 4/12 (IRC R905.2.2); metal panels need 3/12 lapped without sealant, 1/2:12 lapped with sealant, 1/4:12 standing seam (IRC R905.10.2). Below the minimum is an error. Without an approved rules file the command fails: ask the user once, then save the rules.

## 5. Whole pitches
Builders frame to whole numbers. When the nearest whole is within 2 sigma, the `label` reads "6/12 (measured 5.98 ± 0.25)"; otherwise it gives the measured value, such as "5.40/12 ± 0.15".

## 6. In the acceptance file
```json
{"id": "pitch", "type": "slope", "objects": "Shed_Roof", "expect": "6/12", "tol": 1.9, "why": "photo ± 0.25/12, 2 sigma", "source": "measured", "note": "pitch.json: 6/12 (measured 5.98 ± 0.25)"}
```
`tol` is 2 sigma in degrees (twice `sigma_degrees`). From `rule`: `"source": "standard"`, the rule in `note`, the default tolerance. A slope check whose source is `assumed` fails in `acceptance_check.py`.
