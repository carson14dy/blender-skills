# Review round 1: checks on the research behind the roof measure skill

Date: 2026-11-16. This note records what an independent review re-checked, what held up and what did not. It does not replace the earlier notes.

**The short version.** The data sources are real and the main claims hold. Three things changed: lidar is the better pitch source and should supply the pitch whenever its fit is precise; the lidar over Sioux Falls was flown on 19 and 20 December 2020, which matters for "newer than lidar" checks; and the "not for resale" licence wording could not be found again on any page that can be reached today.

## Claims that were re-checked

| # | Claim in the research | Result | Evidence |
|---|---|---|---|
| 1 | The city footprint is the roof edge (drip line), not the wall line | **Supported, now with independent evidence.** The earlier proof was circular: the solid is built on the footprint, so their plan areas match by construction (0.00% on 10 of 12 benchmark buildings). | Lidar returns on 6 houses: single-return roof points stop 0.19 to 0.31 m inside the outline, all roof returns stop 0.16 to 0.39 m outside it. The midpoint, which is where the roof edge is, sits -0.07 to +0.07 m from the outline. A wall-line footprint would put it 0.3 to 0.6 m outside. |
| 2 | 3DEP `SD_EasternSD_3_2020` is QL2, flown April to December 2020 | **Confirmed, and made exact.** | The 3DEP index (`index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer/24`) says QL 2, Lidar Base Specification 2.1, collected 2020-04-10 to 2020-12-22, vertical datum NAVD88 with GEOID18, published 2022-04-13. The GPS times of 2.5 million points in the 77 tiles over the benchmark houses are all 2020-12-19 or 2020-12-20. |
| 3 | Lidar density is about 2 points per m² (plan) or 4 to 5 (skill v1) | **Higher than both.** | Measured on benchmark roofs: 4.2 to 7.4 points per m² of plan area on single flight lines, and 11.5 to 14.4 where two flight lines overlap (house 218452). |
| 4 | Lidar heights and city heights share a datum | **Confirmed.** | Median lidar ground height minus city `GROUNDELEVATION`: 0.00, +0.02, -0.01, -0.13, -0.14 and +0.15 m on level lots, and up to 1.1 m on sloping lots, because the city stores one ground height per building. Lidar roof planes sit 0.07 to 0.14 m above the city roof planes. |
| 5 | The reprojection from the lidar's Web Mercator to the city grid is right | **Confirmed against PROJ.** | `proj.py` and pyproj 3.8 agree to 0.0033 ft for EPSG 3857 to 32164 and 4326 to 32164. Grid scale at Sioux Falls is 1.0000136 and the height factor is 0.999935, so ground distances are 0.005% longer than grid distances and areas 0.01% larger. No correction is needed. |
| 6 | City data is CC BY 4.0, "not intended for use in mapping products for resale" | **CC BY 4.0 confirmed for DataWorks items; the resale sentence could not be found.** | The DataWorks items for Building Permits and Structures say "The City of Sioux Falls provides open data licensed under the Creative Commons Attribution 4.0 International License." The REST services carry only "City of Sioux Falls" as copyright and a "reference purposes only" notice. The layer metadata page that the earlier note quoted now answers "The administrator has disabled the Services Directory". The Building Wireframe layer is not a DataWorks item, so its CC BY status is an inference from the city's general statement. |
| 7 | A Building Permits layer exists and can flag changed roofs | **Confirmed.** | `Data/Community/MapServer/3`: permits since September 2014 with `MAINADDRESS`, `PERMITTYPE`, `WORKCLASS`, `ISSUEDATE`, `FINALIZEDATE`. A sample of 400 permits since June 2024 holds 27 `Reshingle`, 3 `Addition`, 15 `New – Single Family` and 23 `Remodel/Renovation`. |
| 8 | No newer free lidar covers Sioux Falls | **Confirmed for 3DEP.** | The 3DEP index lists two work units at the city centre: `SD_MINNEHAHACO_2008` and `SD_EasternSD_3_2020`. The public EPT bucket lists the South Dakota collections; the 2021 and 2022 ones (`SD_EasternP2_*_2021`, `SD_CentralNorth_*_D22`) do not reach the city. Not checked: lidar the city or county may hold but not publish. |

## The finding that changes a decision: use the lidar pitch

The first build kept the city pitch whenever lidar agreed within 1.5 degrees and left "is the city pitch really 0.6 degree low?" for the tape-measure study. The review found enough evidence to decide now.

1. **The bias is real and is not a software artefact.** An independent fit (own decoder, pyproj, trimmed least squares, no skill code) gives the same result as the skill: lidar reads steeper than the city by 0.16 in 12 on average over 44 planes, about 3% in slope.
2. **Lidar lands on whole-number pitches; the city does not.** Houses are framed at whole-number pitches. With points taken 0.6 m inside each plane edge, the main planes read: house 235247 lidar 7.99, 7.99, 7.87, 7.85, 7.87 against city 7.83, 7.98, 7.73, 7.45, 7.77 (an 8/12 roof); house 235248 lidar 6.07, 5.92, 5.95, 5.82, 5.97, 5.88, 6.01 against city 5.84, 5.90, 5.64, 6.08, 5.67, 5.71, 5.25 (6/12); house 235245 lidar 5.91, 6.03, 6.04 against city 5.69, 5.93, 6.01 (6/12); house 177261 lidar 3.95, 4.03 against city 3.81, 3.83 (4/12); house 176864 lidar 4.86, 4.85, 4.99, 4.99 against city 4.66, 4.52, 4.60, 4.83 (5/12).
3. **Lidar is the more precise instrument for slope.** A fit through 100 to 500 points with 2 to 4 cm scatter over a 4 to 6 m run has a pitch standard error under 0.1 degree. A city plane rests on a few photogrammetric corner heights.

Decision taken in the skill: a plane with a precise lidar fit (80% or more of its points on one plane, pitch standard error 0.25 degree or less) shows the lidar pitch, and the geometry is re-tilted to match. The city pitch stays in `roof.json` as `cityPitchDeg`. The switch is `PREFER_LIDAR` in `lidar.py`. This is an inference from indirect evidence. One taped roof can still overturn it, so the accuracy study stays the next step.

Effect on the benchmark: sloped area rises 0.1 to 0.4%, and main-plane pitches rise by up to 0.3 in 12.

## Other findings

- **Lidar cannot place a roof edge better than about 0.25 m.** The laser spot is about 0.5 m wide (inferred from where single returns stop and multiple returns start). Lidar is a good check that the outline is not a wall line, and a poor tool for eave lengths. This agrees with the report's headline "checks pitch but cannot place eaves".
- **Points near a ridge, valley or eave bias the pitch slightly.** Moving the inset from 0.3 m to 0.6 m brought main-plane pitches closer to whole numbers (mean distance 0.208 to 0.197 in 12 over 44 planes; clearly better on the large planes). The skill now uses 0.6 m when that leaves 80 points and 0.3 m otherwise.
- **Snow is an open question.** The points were flown on 19 and 20 December. The 3DEP specification asks for snow-free ground, and the pitches are clean, but this was not checked against weather records.

## Better free options that were looked for

- Newer public lidar: none (row 8).
- A better footprint source: none needed. The city outline agrees with the lidar roof edge within the lidar's own resolution.
- Methods to improve pitch from sparse lidar: the whole-number-pitch prior above. A per-house "snap to the nearest whole pitch when all main planes are within 0.15 in 12 of it" rule would be cheap, and is left for the study to justify.
- NAIP 2025 was not used in this round. At 0.3 m it cannot beat the lidar edge result.

## Not checked in this round

- The accuracy figures in the 3DEP project report (RMSEz 3.6 cm).
- Whether the city would confirm the licence of the Building Wireframe layer in writing. Add this question to the planned email to the city GIS office.
- Roofer's needs (line-total tolerances) with a roofer.
