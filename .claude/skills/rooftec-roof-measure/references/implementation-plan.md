# Implementation plan: the shortest path from here

Do the accuracy study next. It takes about 4 hours in total, it is the only step that can turn `estimate` into `verified`, and everything it needs now exists.

This page re-sequences experiments 024 to 034 from `plans/Roof accuracy and quality plan.md`, given what this skill delivered on 2026-11-16.

## Where things stand

| Plan step | Status | What is left |
|---|---|---|
| 024 City solid into the studio | Done through the GLB path | Provenance badges in the studio (part of step 4 below) |
| 025 Edge classes | Done in Python, with wall-flashing classes | The studio's own classifier (step 3 below) |
| 026 Lidar cross-check | Done and working on the 12 benchmark buildings; lidar now supplies the pitch on precise planes | Thresholds tuned by 027 |
| 028 Address lookup, cache, attribution | Done as a command line tool; `SKILL.md` written | The address box and `/api/roof` in the studio (step 4 below) |
| 027, 029 to 034 | Not started | See the order below |

The plan budgeted 15 hours for 024, 025, 026 and 028. About 5 hours of studio work remain from those.

## The order to work in

| # | Step | Who | Hours |
|---|---|---|---|
| 1 | 027 Accuracy study on 3 to 5 roofs | You 0.5 to 3 h, cloud 1.5 h | 2 to 4.5 |
| 2 | Email the city GIS office about vendor, accuracy and a bulk file | You | 0.25 |
| 3 | 025b Studio edge classes: apply the patch, add a wall class, or read edges from `roof.json` | Cloud | 2 |
| 4 | 028b Studio address box, `/api/roof`, confidence badges, and the hooks into steps 017, 018 and 022 | Cloud | 4 |
| 5 | 032 True-scale materials, then 033 site context | Cloud, then your PC | 5 + 3 |

After those five: 029 outline fallback (3 h), 030 `roofer` (4 h), and 031 and 034 only if the study shows the free data falls short (10 h). The remaining core (steps 1 to 5) is about 19 hours, against the plan's 29.

## Step 1 in detail: the accuracy study (027)

1. **You, 30 minutes.** Pick 3 to 5 past jobs inside city limits, built before 2020, with a measurement report or your own tape numbers. Aim for two simple roofs, two with valleys and one complex roof.
2. **You, 10 minutes per roof.** Write a truth file for each. The format is at the top of `scripts/roofmeasure/study.py`: sloped area, predominant pitch, and the ridge, hip, valley, eave and rake totals you have.
3. **Cloud, 30 minutes.** Run `measure --address "<address>" --lidar` for each roof, then `compare --roof <roof.json> --truth <truth.json>`. Each run writes `accuracy.md` beside the roof file.
4. **Cloud, 1 hour.** Add the error table to `references/validation.md`, tune the thresholds in `lidar.py`, and decide the class each tier earns.
5. **Decide.** The study passes if at least 4 of 5 roofs are within 2% on area and none is outside 4%. On a pass, set `STUDY_PASSED = True` in `export.py`. On a fail, stop studio work and look at tier D (step 031) instead.

If you have no reports, tape the eaves and rakes of one simple gable from the ground and take the pitch with a phone on the rake board. That is about 1 hour per roof. Do not walk an icy roof for this.

Questions the study should settle, because the lidar comparison raised them:

- Is the outline right? This matters most. Lidar confirms the city roof outline only to about 0.1 m, which is 2 to 5% of the area, and review round 3 found nothing free that does better. On every study roof, tape one eave-to-eave width and one rake-to-rake length at the shingle edge, and note whether there are gutters: lidar sees gutters as roof, and it is not known whether the city line follows the shingles or the gutter lip.
- Is lidar right about the pitch? Review round 1 found the city pitch low against lidar and switched the tool to the lidar pitch on precise planes. Review round 2 confirmed it on 30 more houses (0.12 in 12 low, lidar on whole-number pitches 85% of the time) and ruled out snow. One taped rake is still the only direct proof (`PREFER_LIDAR` in `lidar.py`).
- Are the delivered faces or the cleaned faces closer to the truth? Both sets of numbers are in `roof.json` (`sourcePitchDeg`, and `checks.solid.sourceSlopedAreaM2`).
- Are the `eave-under-wall` and `roof-step` joints real walls, or valleys and ridges that the city model simplified? The answer decides how those lengths enter a takeoff.
- Are the `skewed-edge` edges eaves? About one house in three has 10 ft or more of open edge that runs at a slant across its plane and is counted as rake.

## What the plan got wrong or did not know

**About the data**

- A solid answer is about 3 KB, not 25 to 35 KB. The "Start here" check should expect that size.
- Some solids hold extra faces under the roof. The plan's rule "keep faces whose normal points up" double-counts them, and face winding cannot tell up from down. The tool keeps the top surface only.
- Roof plan area does not always match the footprint "to the square foot". It did on the four research houses and failed by 10% on an older multi-unit house.
- Address points of type `Parcel` can sit 50 to 120 ft from the building, so "the footprint containing the point" is not enough. The tool takes the nearest footprint within 100 ft and flags it.
- Lidar density on roofs was 4 to 7 points per square metre, not 2, so planes down to about 150 sq ft get a check.

**About the tools**

- The lidar step needs no PDAL, conda or Open3D. `laspy`, `lazrs` and numpy read the public EPT directly in about 6 seconds per house.
- Converting lidar to EPSG 6343 first is unnecessary. The tool converts straight to the city's EPSG 32164, and the measured offset between the sources is 0.1 to 0.25 m.
- The sanity check "sloped area over plan area matches the mean pitch" is always true for flat faces, so it checks nothing. The lidar comparison replaces it.
- Step 024 planned a new `createMeasuredHouse(roofJson)` in the studio. It was not needed: a GLB with a mesh named `Roof` loads through the existing import and gives the same planes and area.
- Step 025 planned to reuse the studio's `analyzeRoof()`. Its level-edge tolerance of 0.6 degrees is too strict for measured roofs, and it misses hips whose edges only partly overlap. Classifying edges from the closed solid, as this skill does, is more reliable.

## Known gaps in this skill, smallest first

The ranked list of open issues is kept in `references/review-log.md`. The ones that need code:

1. Faces that lie partly under another face are kept or dropped whole. Clipping them to the visible surface is about 3 hours and would fix buildings like 204065.
2. Cleaning the delivered faces moves outline corners; plan area drifts up to 0.33% from the footprint. A first attempt to hold the corners made pitches worse, so this needs a better idea.
3. A "one house, one pitch" rule for small planes. On houses whose large planes share a pitch, the city pitch of the smaller planes is 0.40 in 12 off that pitch on average. About 2 hours, and it should wait for the accuracy study.
4. The check in a real browser has not been run. It takes 5 minutes on your PC.

Done in review round 1: the 3D geometry is now re-tilted when lidar supplies a pitch, and houses newer than the lidar are flagged for every kind of lookup.

Done in review round 2: building permits are checked, lidar points off the roof surface are reported, and a blocked roof no longer carries the status "ESTIMATE".
