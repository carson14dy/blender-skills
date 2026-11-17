# Review round 2: checks on round 1 and on the research

Date: 2026-11-16. This note records what a second independent review re-checked. It challenges `review-round-1.md` and does not replace it.

**The short version.** Round 1's main decision holds: lidar should supply the pitch, and there was no snow on the flight days. Round 1 was wrong about the licence: the "not for resale" sentence is in each layer's metadata. The biggest gap in the whole chain is not pitch; it is that nothing free can confirm the roof outline to better than 2 to 4% of the area.

## 1. Lidar or city for the pitch: keep lidar

Round 1 decided this on 8 houses it had chosen. The evidence could have been cherry-picked, so round 2 tested it on new houses.

**The test.** 120 random footprint ids between 170000 and 260000 (seed 20261116); 60 were single-family houses occupied before 2020 and larger than 900 sq ft; 32 of those, shuffled with seed 7, were measured with `--lidar`. One download failed and one house had no precise main plane, leaving 30 houses and 94 main planes (215 sq ft or more) with a precise lidar fit.

| Measure | Lidar | City |
|---|---|---|
| Within 0.15 in 12 of a whole-number pitch (chance is 30%) | 85% | 50% |
| Mean offset from the nearest whole-number pitch | -0.04 | -0.14 |
| Mean distance from the nearest whole-number pitch (chance is 0.25) | 0.08 | 0.18 |

- Lidar is steeper than the city on 90% of planes, by 0.12 in 12 on average (0.15 on the 8 benchmark houses; round 1 said 0.16).
- On 29 of 33 houses with two or more large planes, the lidar pitches are closer together than the city pitches. This needs no assumption about whole numbers.
- Typical houses: lidar 4.97, 4.97, 5.00, 4.98 against city 4.97, 4.81, 4.99, 4.70; lidar 3.98, 3.95, 3.96, 3.94 against city 3.85, 3.86, 3.81, 3.85.
- The whole-number argument is weaker on the benchmark than round 1 made it sound: one of its houses is framed at 3.5 in 12, one has a 6.8 in 12 plane that both sources agree on, and one hip roof reads 5.1 to 5.5.

**Could lidar itself be biased?** Each idea was tested.

| Possible cause | Result | Evidence |
|---|---|---|
| Snow on the roofs | No | NOAA daily summaries for station `USW00014944` (Sioux Falls airport): snowfall 0 and snow depth 0 every day from 15 November to 22 December 2020. A 14 cm fall on 10 November was gone by 15 November. The lidar ground matches the city ground while roofs sit about 0.1 m higher; snow would lift both. |
| Scan angle or flight-line offsets | No | House 218452 lies under two flight lines at -13 and +9 degrees. Their pitches per plane: 4.09 and 4.06, 6.76 and 6.80, 4.10 and 4.09. |
| Mixed returns at eaves and ridges | Small | Insets of 0.3, 0.6, 1.0 and 1.5 m change planes of 40 m² or more by 0.1 in 12 at most. |
| Wrong horizontal scale from Web Mercator | No | A missed conversion would change pitch by 38%. `proj.py` matches pyproj to 0.0033 ft (round 1), and the lidar pitches land on whole numbers. |
| An over-confident standard error | No | Pitches fitted to the left and right half of 18 planes differ by 0.8 times the predicted error (median). |

A physical point supports this: range noise and a position offset move a fitted plane; they do not tilt it. The 0.1 m height offset is most likely the wide laser spot triggering on the upper part of a sloped surface (an inference, not tested).

**Two changes were tried and dropped.** Refusing fits whose halves disagree would have rejected 6 planes in 43 houses, and on 3 of them lidar was right and the city wrong by 0.4 to 0.7 in 12. Trusting imprecise fits is supported (they are 0.17 in 12 from the house's common pitch, the city 0.40, on 26 planes), and the better form of it is a "one house, one pitch" rule. That is a new rule, so it waits for a taped roof.

## 2. The outline, not the pitch, limits area accuracy

Round 1 said the city outline is the roof edge "within about 0.07 m" and that this bounds plan area at roughly 2%.

- Round 1's own script, re-run on all 8 clean benchmark houses, gives a mean of 0.02 m inside the outline, a scatter of 0.07 m and a worst case of 0.14 m. "Within 0.07 m" is true for 7 of 8.
- The method assumes the laser spot is symmetric, so that the roof edge is midway between where single returns stop and where all returns stop. Those two limits are 0.4 to 0.6 m apart.
- A strip 0.1 m wide around a house is 2 to 4% of its plan area (3.6% on house 218452).

So the finding is sound as "the outline is the roof edge, not the wall line" and weak as an accuracy figure. The main report already said that eaves from lidar alone are uncertain by 5 to 8% of plan area; the same limit applies to checking them. Pitch moves sloped area by 0.2 to 0.4%. The accuracy study should therefore tape eaves first.

## 3. The licence: the resale sentence exists

Round 1 could not find "not intended for use in mapping products for resale" and concluded that CC BY 4.0 for the Building Wireframe layer was an inference.

- `https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/metadata?f=xml` answers with the layer's full metadata (read 2026-11-16). Its use limitation says the data is "for public use as described under the Creative Commons Attribution 4.0 United States License" (the link goes to `creativecommons.org/licenses/by/4.0/`), that it is "neither a legally recorded map nor a survey", and ends with "This data is not intended for use in mapping products for resale."
- The same text is in the metadata of the footprints (`Property/MapServer/5`), the address points (`Property/MapServer/0`) and the building permits (`Community/MapServer/3`).
- `metadata?format=default` answers 403 "The administrator has disabled the Services Directory". That is the form round 1 tried.
- The service-level item info has an empty licence field and only the "reference purposes only" notice.

The earlier research (`sioux_falls_public_data.md`) was right. Whether in-house estimating counts as a "mapping product for resale" is still an interpretation; the email to the city GIS office should ask.

## 4. Other claims spot-checked

| Claim | Result | Evidence |
|---|---|---|
| The lidar points were flown on 19 and 20 December 2020 | Confirmed | GPS times of the points over the 8 clean benchmark houses fall on those two days only. |
| No newer 3DEP lidar covers the city | Confirmed | The 3DEP index at the city centre lists `SD_MINNEHAHACO_2008` and `SD_EasternSD_3_2020` (QL 2, collected 2020-04-10 to 2020-12-22). |
| NAIP 2025 is 0.3 m and free | Confirmed | Planetary Computer STAC lists `sd_m_4309627_sw_14_030_20250728` with a ground sample distance of 0.3 m. |
| The permit layer can flag changed roofs | Confirmed and now used | Permit points sit on the building (5 houses). 350 residential `Addition` permits were issued between June 2023 and November 2026. |
| `OCCUPIEDDATE` marks a new house | Weaker than assumed | Footprint 363456 is "occupied December 2025" and has a new-house permit from February 2021 and a basement-finish permit from December 2022. The occupied date can trail the build by years. |

## 5. New things the data can show

- **What sits on or under a roof plane.** The plane fit discards points off the plane, and those points are informative. On 43 houses: a tree 4 m above a plane (all multiple returns), solid single returns 0.7 to 1.5 m above two planes of an 8 in 12 roof (most likely dormers missing from the city model), a twin home whose units step by 0.4 m where the city drew one plane, and a 400 sq ft plane with 63% ground points (built after the flight). The skill now reports these shares.
- **Return numbers separate trees from structures.** Multiple returns are 100% of the points above the tree-covered plane and 6 to 14% above the two planes with solid objects. The skill's cached points do not keep the return number yet.
- **Reshingle permits.** The city issued 3,647 since June 2023. The date of the last one is in `roof.json` now; it is sales context, not a measurement.
- **A footprint redrawn after an addition.** Two of three houses with a 2024 addition have new footprint ids (above 489000) and their 2023 solid no longer matches, which the existing plan-area check catches (13% off on one).

## 6. Better free data or methods that were looked for

- Newer lidar: none.
- A second source for the outline: none found that is finer than lidar. NAIP 2025 at 0.3 m is no finer, and the city's 2025 and 2026 imagery is view-only.
- Change detection after June 2023 without a permit: NAIP 2025 could do it. Not built.

## Not checked in this round

- Any roof against a tape or a paid report. This is still the one check that can make a number `verified`.
- The `lidar-surface` thresholds against photos.
- The studio import, which round 1 ran; the roof geometry did not change in round 2.
- The 3DEP project report's accuracy figures.
