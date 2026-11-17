# Review round 4: what was checked and what is new

Date: 2026-11-16. Scope: the `rooftec-roof-measure` skill after review round 3 (tag `roof-measure-v4`).

## What matters

1. **One new error source was found: roof hidden under an upper roof's overhang.** It is in no number the tool gives. It makes the area too small by about 1.3% on the median house and by more than 2% on one house in three, if the overhang is 12 in. This is an inference from geometry, not a measurement.
2. **The "confirmed by another plane" pitch rule from round 3 holds on 20 houses it was not built on.**
3. **No new outside source was needed.** Everything below comes from the city layers and the USGS lidar the skill already uses. No web research was done in this round, because no open decision depended on one.

## 1. Roof under an upper roof's overhang

**The argument.**

- The city solid is a closed shape with vertical walls, so its roof planes cannot overlap when seen from above.
- Checked: on 5 houses the plan areas of the planes add up to the outline area within 0.1 m² and to the city footprint within 0.2% (235245: 272.9, 272.9 and 273.2 m²).
- On a real house, a lower roof that meets a wall runs on under the eave or rake of the roof above that wall. Seen from above, the two roofs overlap by the width of that overhang.
- So along every roof-to-wall joint, a strip one overhang wide is missing from the area. It does not matter whether the city drew the joint at the wall or at the upper drip edge: one of the two roofs is short by that strip either way.

**The size**, with the 12 in overhang the skill already carries as an assumed default, on 59 houses (the 8 clean benchmark houses, 31 from round 2, 20 new). Joints the tool flags as `eave-under-wall` are left out:

| Measure | Value |
|---|---|
| Median share of the sloped area | 1.3% |
| Houses with no roof-to-wall joint | 9 |
| Houses over 2% | 19 |
| Largest | 5.2% (122 ft of joints) |
| Houses where it is larger than the printed range | 1 |

**What is not known.** The overhang width. Lidar cannot see under a roof and the 2025 aerial photos are taken from above. Rake overhangs are often narrower than 12 in, and some joints in the city model are not real walls. The tool therefore prints the strip as "up to about" and adds it to no number.

**What settles it.** Measure the overhang at one roof-to-wall joint on a study roof. This is now in the implementation plan.

## 2. The sibling-confirmed pitch rule on held-out houses

**Sample.** Round 2 drew 60 random single-family houses (seed 20261116) and measured the first 32 after a shuffle with seed 7. This round measured the next 20 of that same shuffled list. No earlier round had touched them.

**How often the rule fires.** 7 planes on 6 of the 20 houses; 11 planes on 64 houses in all.

**Independent test.** For each plane, drop every lidar point within 1 m of a point that lies off the fitted surface, then fit again. This is the plane without the tree, the dormer or the lower step.

| House, plane | City pitch | Pitch the rule used | Clean part | Points on the clean part |
|---|---|---|---|---|
| 176864, 0 | 21.22 | 22.03 | 22.07 | 251 |
| 177261, 1 | 17.70 | 18.56 | 18.42 | 52 |
| 235247, 3 | 31.85 | 33.20 | 33.36 | 70 |
| 209733, 0 | 17.83 | 18.31 | 18.36 | 121 |
| 222601, 3 | 21.34 | 22.11 | 22.23 | 45 |
| 241834, 2 | 25.62 | 25.81 | 26.16 | 62 |
| 247949, 0 | 17.33 | 18.23 | 18.30 | 125 |
| 208067, 1 | 24.24 | 25.75 | 26.19 | 91 |
| 233681, 0 | 28.82 | 29.61 | 29.59 | 144 |
| 210115, 1 | 13.17 | 13.95 | too few points | |
| 247949, 4 | 16.26 | 18.06 | too few points | |

- On all 9 planes with a clean part, 100% of its points lie on one surface, and its pitch is closer to the rule's pitch than to the city pitch.
- All 11 planes moved towards a whole-number pitch.
- The fitted pitch moves by 0.09 degree at most over 12 random seeds.
- On 247949 plane 0 a wider point band (0.15 m against the 0.10 m the tool uses) takes in the second surface. The standard error then doubles to 0.35 degree, so the rule would not fire: the standard-error test does its job.

**Limit of this evidence.** It shows the rule lands on what lidar sees on the undisturbed part of the same plane. Whether lidar itself is right about pitch still rests on the round 2 evidence and on no tape.

## 3. Flags on random houses

51 random houses carried 2.6 review flags each on the round 3 code, and only 4 had none. The counts, the decisions and the table are in the skill's `references/review-log.md`, round 4.

## 4. Things checked that changed nothing

- **The area range arithmetic.** Growing the outline by 0.10 m and a random trial give the tool's number on simple roofs (3.9, 2.3 and 3.4%).
- **The studio import.** The current `rooftec-lab` code (commit `39fe9e1`) finds the same plane count and the same area within 0.14% on 12 of 13 benchmark buildings.
- **A cold-cache run** of three houses by id, lat/lon and address: 7 to 9 seconds each, same numbers.

## Where the working files are

Scratch folder `review-r4/` of the session: `v4-baseline.json` and `r4-after.json` (benchmark), `snap-v4.json` and `snap-r4.json` (all 64 houses before and after), `burden.txt` (flag table), `sibling-heldout.txt`, and the scripts in `work/`.
