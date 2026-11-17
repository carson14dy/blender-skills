# Roof measurement research summary

**Written:** 2026-11-16. **Covers:** the supplier-pricing and roof-measurement research done in one cloud session for Rooftec (Sioux Falls, SD), the `rooftec-roof-measure` skill built from it, and five independent review rounds that challenged both.

This is the entry point. It says what is true now, what changed since the first report, and what to do next. Detail lives in the files listed at the end.

---

## Start here

1. **Run the accuracy study (2 to 4.5 hours, about 1 hour of it yours).** Pick 3 to 5 past jobs inside city limits, built before 2020, for which you have a measurement report or tape numbers. Write one small truth file per roof in the format at the top of `.claude/skills/rooftec-roof-measure/scripts/roofmeasure/study.py`. Then run `measure` and `compare` for each. This is the only step that can turn the skill's numbers from `estimate` into `verified`. The full recipe is in the skill's `references/implementation-plan.md`, step 1.
2. **Email the City of Sioux Falls GIS office (15 minutes)** at cityofsfgis@siouxfalls.gov. Ask who made the June 2023 3D building model, what its stated accuracy is, and whether a bulk file exists.
3. **If you have no reports:** tape the eaves and rakes of one simple gable from the ground, and read the pitch with a phone on the rake board. That takes about 1 hour. Do not walk an icy roof for this.

---

## The answer in five lines

1. **Free, accurate roof geometry exists for almost every Sioux Falls house.** The City of Sioux Falls publishes a June 2023 3D solid with planar roof faces for 95,901 buildings, under CC BY 4.0.
2. **Free lidar checks it.** USGS 3DEP lidar (December 2020, 4 to 7 points per m² on the roofs tested) gives an independent pitch. Where its fit is precise, it now sets the pitch.
3. **The outline is the limit, not the pitch.** Free data cannot place the roof edge better than about 4 in (0.10 m), and that is 2 to 5% of the area. Pitch error is only 0.2 to 0.4% of the area.
4. **A skill now does all of this in about 10 seconds per house, for $0.** It outputs `roof.json`, a studio-ready `roof.glb` and a `takeoff.md` report. Every value carries its source and a confidence class.
5. **Nothing is "verified" yet.** No roof has been compared with a tape. One taped eave-to-eave width would settle most of the remaining uncertainty.

---

## Roof measurement findings (final, after five review rounds)

### Data sources that work for $0

| Source | What it gives | Key facts | Licence |
|---|---|---|---|
| City 3D Building Wireframe (Community MapServer layer 66) | One closed solid per building: walls plus planar roof faces | June 2023; US survey feet, EPSG 32164; faces planar to 0.24–0.39 ft; no vendor or accuracy stated; REST only, 1,000 records per query, compressed binary geometry | CC BY 4.0; "not intended for use in mapping products for resale" |
| City Building Footprints (Property MapServer layer 5) | The roof outline including overhang, plus ground and top elevation | About 100,000 polygons; top elevation tracks the ridge within about 1 ft; elevations behave as NAVD88 feet | CC BY 4.0, same wording |
| City Address Points (layer 0) and Building Permits | Address lookup; permits since the 3D capture | Permit points sit exactly on address points; 0 false site checks on 30 houses | CC BY 4.0 |
| USGS 3DEP lidar, SD_EasternSD_3_2020 | An independent point cloud for pitch | QL2; flown 19–20 Dec 2020 over the benchmark; 4–7 pts/m² on roofs (11–14 where flight lines overlap); RMSEz 3.6 cm (Block 1 report); no building class; no newer 3DEP lidar exists | Public domain |
| NAIP 2025 | A 0.3 m aerial photo | Free and anonymous via Microsoft Planetary Computer; leaf-on; roofs appear shifted 0.3–1.5 m, so it cannot set the outline | Public domain |

### What the review rounds established

1. **The city pitch reads slightly low.** Lidar is 0.12 to 0.15 in 12 steeper on average. Across 94 precise main planes on 30 random houses, lidar was within 0.15 of a whole-number pitch 85% of the time, against 50% for the city and 30% by chance. Two flight lines 22° apart agree within 0.04 in 12. This is lidar-internal evidence; one taped roof could still overturn it.
2. **No snow biased the lidar.** NOAA station USW00014944 shows zero snowfall and zero snow depth every day from 15 November to 22 December 2020.
3. **The city outline is the lidar roof edge** within about 0.05 m on average across 38 houses (145 edges), but the method itself carries about 0.08 m of uncertainty. Whether the city line is the shingle edge or the gutter lip is unknown.
4. **Trees can be told apart from roof errors.** Over trees, 83–100% of lidar points are multiple returns, against 0–15% on solid surfaces.
5. **Some roof is in no number.** Lower roof hidden under an upper roof's overhang is about 1.3% of the area on the median house, over 2% on one house in three, and 5.2% at worst, assuming a 12 in overhang. The skill reports it as "Not counted".

### Tools

- **Permissive, safe to build in:** PDAL (BSD), Open3D (MIT), pyRANSAC-3D (Apache-2.0), laspy and lazrs, numpy, three.js, three-mesh-bvh, proj4, turf, copc.js, and straight-skeleton **1.x only** (MIT; versions 2.x and 3.x wrap GPL CGAL code although npm labels them MIT).
- **GPL or AGPL, run as a separate program for internal use only:** roofer (3DBAG, GPL-3.0, v1.0; wants about 10 pts/m², so QL2 is sparse for it), City3D, PolyFit, CloudCompare, CGAL algorithms, QGIS, BlenderGIS, Point Cloud I/O; OpenDroneMap/WebODM and OpenMVS (AGPL; never behind a customer-facing website).
- **No ready-made roof-measuring skill, MCP server or add-on existed.** That gap is why the skill was built.
- **Useful agent skills:** `muend/geoai-skills` (MIT) has a `point-cloud-lidar` skill with good discipline on datums and accuracy budgets.

### Capturing a roof yourself

1. **Scale matters more than anything.** Area error is about twice the linear scale error. A 1% area target allows only 0.5% scale error, which is 5 cm over a 10 m eave.
2. **Drone GPS alone is not enough.** Tests ranged from 0.3% to 7% short. One taped scale bar or ArUco ground markers (Find-GCP, free) fixes it.
3. **Commercial drone flights need FAA Part 107:** about $175 for the test and $5 per drone. That is the only non-zero cost found.
4. **Phone LiDAR reaches about 5 m:** good for ladder checks of one eave or one plane, not whole roofs. Scaniverse Classic forbids commercial use; Polycam Free (glTF, with attribution), KIRI Engine Basic, 3d Scanner App and SiteScape allow it.
5. **Avoid non-commercial AI models:** Depth Anything V2 Base and Large, UniDepth, Apple Depth Pro, MASt3R and DUSt3R, and the original 2DGS, PGSR, SuGaR and GOF splat code. Depth Anything V2 Small, MoGe, SAM 2 and gsplat are usable.

### Sources to avoid

These sources are paid or view-only, or their terms forbid extracting and storing measurements: Google Solar API, Google Photorealistic 3D Tiles, Nearmap (including the city's own 2026 6-inch imagery, which is view-only), EagleView, Cesium ion's free tier, and Esri World Imagery. These terms were taken from the notes and were not re-checked during review.

---

## Corrections to the first report

The first report (`reports/Free roof measurement accuracy tools.md`) was written before the review rounds. These points in it have since been corrected:

| First report said | Now known |
|---|---|
| QL2 lidar has "at least 2 points/m²" | Measured 4–7 pts/m² on benchmark roofs, 11–14 where flight lines overlap |
| City pitch is the primary pitch source | Lidar sets the pitch where its fit is precise; the city reads 0.12–0.15 in 12 low |
| Lidar edge uncertainty is about ±0.35 m | The city outline matches the lidar roof edge within about 0.05 m on average; the honest floor is about 0.10 m, which is 2–5% of the area |
| A solid answer is 25–35 KB | About 3 KB per building |
| NAIP 2025 can confirm the outline | Roofs are shifted 0.3–1.5 m in NAIP, so it is useful only for spotting trees and changes |
| The "not for resale" licence line needs checking | Confirmed in each layer's own metadata at `<layer>/metadata?f=xml` |

---

## Supplier pricing findings

1. **ABC Supply:** the Price Items API is free to join but returns only your own account's negotiated prices, 50 items per request. Production access needs an ABC customer account. Its terms ban price-comparison tools and redistribution. No public prices exist; get a branch quote or open an account.
2. **Menards:** it blocks automated access from cloud servers (HTTP 403 even for robots.txt). Only a 79-product partial snapshot was captured, defaulting to the Council Bluffs, IA store. A fuller Menards #3064 dataset made by another session is on branch `rooftec-lab` under `lab/data/suppliers/`.
3. **Home Depot:** with the Sioux Falls store (#4301, 2523 S Louise Ave) selected as a shopper would, 2,763 roofing and exterior products were captured. Each has a price, pickup stock, images and color swatches. 274 are "Browse Only" with no online price. This is a snapshot from 15–16 November 2026; prices change weekly.

---

## The skill: `rooftec-roof-measure`

**Run it** from `.claude/skills/rooftec-roof-measure/`:

```bash
python3 scripts/roof.py measure --address "224 W 9th St" --out out/roofs --lidar
```

`--oid <footprint id>` or `--latlon <lat>,<lon>` also work. The lidar check needs `pip install laspy lazrs` once. Keep `--out` in a git-ignored folder, because its contents can identify a customer's house.

**What it does:** finds the building; decodes the city solid; builds roof planes; classifies ridge, hip, valley, eave, rake and wall-flashing edges; fits lidar planes and reconciles pitch; checks permits since the capture; and writes `roof.json`, `roof.glb` and `takeoff.md`. Each value is `estimate`, `assumed` or (after the accuracy study) `verified`. About 1 random house in 7 comes back "SITE CHECK REQUIRED", and the tool says so before any number.

**How it was tested:** 79 offline unit tests pass, including from a clean copy. A 13-building benchmark plus 51 random houses and 20 held-out houses were used across the rounds. The studio's own import code loads the GLB on 55 of 64 houses with identical plane counts; the other 9 differ only in how the studio groups planes, with area within 0.3%.

### Review rounds

| Round | Rating | Main result |
|---|---|---|
| Build (v1) | — | Working pipeline; house 235245 reproduced at 5.6–6.1 in 12 and 3,269 sq ft |
| 1 (v2) | MAJOR | Ridge-length bugs fixed; a lidar test that could never fail replaced; lidar now sets pitch |
| 2 (v3) | MODERATE | No snow; licence confirmed; permit check and "SITE CHECK REQUIRED" headline added; no number moved |
| 3 (v4) | MODERATE | Area "likely range" added; trees separated from real errors; 3 planes moved up to 0.39 in 12 |
| 4 (v5) | MAJOR (one bug) | Rake and eave mixed up on near-flat roofs; flag noise cut from 2.6 to 1.7 review flags per house |
| 5 (v6) | MAJOR (one bug) | GLB area was up to 2.9% high on 12 of 64 houses from twisted city faces; all outputs now agree |

The loop stopped at its five-round cap. Benchmark area and main-plane pitch did not move in rounds 4 or 5; the last two ratings come from bugs in outputs the benchmark did not cover. Git tags `roof-measure-v1` to `roof-measure-v6` exist in the local clone only (they were not pushed).

### State of the skill

1. **Trustworthy now:** plan area, the pitch of large planes, and agreement between `roof.json`, the report, the command line and the GLB.
2. **Trustworthy as a range:** sloped area, to the printed 2–5%, plus the "Not counted" strip under overhangs.
3. **Needs a look:** line classes at roof-to-wall joints and slanted edges, anything under a `review` flag, and small planes.
4. **Only a tape can settle:** where the shingle edge is, how wide the overhangs are, and whether lidar is right about pitch.
5. **Not built yet:** the outline-plus-typed-pitch fallback (tier C), drone or phone capture (tier D), roofer, and the studio address box. The skill's `references/implementation-plan.md` puts the remaining core work at about 19 hours, against the original plan's 29.

---

## Licences and attribution

- City data: "Contains data from the City of Sioux Falls, CC BY 4.0." The licence adds that the data is "not intended for use in mapping products for resale", so in-house estimating is fine and selling the models as maps is not. This is a reading of the licence text, not legal advice.
- USGS 3DEP and NAIP: public domain; credit "USGS 3D Elevation Program" and "USDA NAIP" when shown.
- The skill uses only permissive dependencies. GPL and AGPL tools stay outside it as separate programs.
- Product photos and swatches belong to the stores and manufacturers. Link them, and commit only derived hex colors, as the studio plan already requires.

---

## Files

All paths are on branch `claude/stoic-keller-boixwx`, in draft PR https://github.com/carson14dy/blender-skills/pull/3.

| Path | What it is |
|---|---|
| `reports/Roof measurement research summary.md` | This file |
| `reports/Free roof measurement accuracy tools.md` | The first research report, before review (see the corrections above) |
| `research_notes/Free roof measurement accuracy tools/` | Five research notes plus one note per review round (`review-round-1.md` to `review-round-5.md`) |
| `plans/Roof accuracy and quality plan.md` | The original plan, experiments 024–034 |
| `.claude/skills/rooftec-roof-measure/` | The skill; start with `SKILL.md`. The review history is in `references/review-log.md`, the benchmark in `references/benchmark.md`, and the remaining work in `references/implementation-plan.md` |
| `handoffs/sioux-falls-material-prices/` | Home Depot #4301 and Menards price data for the 3D studio; start with `HANDOFF.md` |
