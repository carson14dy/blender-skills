# Roof accuracy and quality plan

**Project:** Rooftec, Sioux Falls, SD. **Written:** 2026-11-16 (cloud session, planning only). **Budget:** $0 for software and data.

This plan sits next to `lab/projects/sioux-falls-studio/PLAN.md` on branch `rooftec-lab`. It adds lab experiments 024 to 034. It does not replace steps 016 to 023; section 6 says how they fit together.

Evidence comes from the five research notes in `research_notes/Free roof measurement accuracy tools/` and from the code on `rooftec-lab`. Where I reason beyond them, the text says "inference". Where the notes could not confirm something, it says "unverified".

---

## 1. One-screen summary

**Goal:** type a Sioux Falls address and get a roof that is measured (area, pitch, edge lengths) and shown in 3D at real scale and in real product colors, with every number labelled by where it came from.

**Start here (under 30 minutes):** open a cloud session on `rooftec-lab` and paste this:

> Do "Start here" from `plans/Roof accuracy and quality plan.md`: fetch city footprint 235245 and wireframe 79199, save the raw JSON under `lab/experiments/024-city-solid/out/`, and tell me the file sizes and whether a `binaryPatches` field is present.

The two requests are below. This proves that the cloud session can reach the city service, which is the one thing everything else depends on. Expected: a wireframe answer of roughly 25–35 KB that contains `binaryPatches`.

```bash
mkdir -p lab/experiments/024-city-solid/out && cd lab/experiments/024-city-solid/out
curl -s "https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5/query?objectIds=235245&outFields=*&returnGeometry=true&outSR=32164&f=json" -o footprint-235245.json
curl -s "https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query?objectIds=79199&outFields=*&returnGeometry=true&returnZ=true&f=json" -o wireframe-79199.json
ls -l
```

(The query parameters are rebuilt from the research note, which queried by footprint bounding box. If `objectIds` is refused, use the envelope query described in step 024.)

**Recommended approach**
1. **Use the city's 3D building solid first** (Tier A). It is free, covers 95,901 buildings, and already holds flat roof faces with real heights.
2. **Check every roof against USGS lidar** (Tier B). Lidar is an independent measurement of pitch with a published accuracy.
3. **Prove it on 3–5 roofs you already know** before any number reaches a customer. The city data has no stated accuracy, so we measure it ourselves.
4. **Keep fallbacks small:** a footprint-plus-typed-pitch roof, and the `roofer` program, for houses the city data lacks. A drone capture stays optional.
5. **Raise the picture quality with free materials:** CC0 textures at true size, the hex colors already sampled from store swatches, product-sized geometry, real site context, and Cycles renders on your PC's GPU.

**Accuracy targets** (details in section 2)

| What | Target |
|---|---|
| Sloped roof area | within ±2% of ground truth |
| Pitch on main planes | within ±1°, which is about ±¼ in 12 at 6/12 |
| Edge totals (eave, rake, ridge, hip, valley) | each within ±3% or ±2 ft, whichever is larger |
| Roof outline position | within ±0.5 m (about 1.5 ft) of the lidar roof edge |

**Total time**

| Block | Hours |
|---|---|
| Core: experiments 024–028, 032, 033 | 29 |
| Small additions to existing steps 017, 018, 021, 022 | 3 |
| Fallbacks: 029, 030 | 7 |
| Optional: 031 (drone or phone), 034 (splat) | 10 |
| **Everything** | **49** |

Your own hands-on time in the core is about 4 hours: about 3 hours gathering or taking check measurements, and 1 hour judging renders on the PC. The rest is cloud sessions. At 1–3 hours a day the core takes about three weeks.

---

## 2. Success metrics

### Measurement

| Metric | Target | How it is measured |
|---|---|---|
| Sloped area | ±2% per roof. The study passes if at least 4 of 5 roofs are inside ±2% and none is outside ±4% | Studio total against ground truth (see below). This matches the lab's existing goal in `lab/GOALS.md`, track T2: "a real house measures within 2% of its report" |
| Pitch | ±1° on planes of 20 m² (215 sq ft) or more. The pitch label rounds to the nearest whole x/12 only when city and lidar agree | Plane pitch against a pitch gauge or phone inclinometer on the deck or rake, three readings averaged |
| Edge lengths | Each line-type total within ±3% or ±2 ft. Any single taped edge of 20 ft or more within ±6 in | Tape along eaves and rakes from a ladder or the ground; ridges, hips and valleys from an existing report |
| Outline position | Within ±0.5 m of the lidar roof edge, and at least 95% of above-ground lidar points over the house fall inside the outline | Automatic, in experiment 026 |
| Plane count | Every plane of 30 sq ft or more in the site sketch exists in the model | Count by eye against the newest city imagery (view only) and a site photo |
| Provenance | 100% of measured values carry a source, a capture date and a confidence class | A unit test on the roof file |

Why ±1° and not ±1/12: one step of x/12 is about 3.7–4° near 6/12, and each degree of pitch error changes sloped area by about 0.9% at 6/12 (capture note). So ±1/12 alone would use up the whole 2% area budget. With plan area inside 1% and pitch inside 1°, the two combine to roughly 1.3% (inference: root-sum-square of two independent errors).

**Ground truth, best first:**
1. A tape and pitch-gauge measurement you take yourself.
2. A paid report you already hold (EagleView, Hover). Treat it as a reference, not truth: the only accuracy figures found for those are vendor-commissioned.
3. For simple gables and hips, a hand calculation from taped eave and rake lengths.

### Portrayal

| Metric | Target | How it is measured |
|---|---|---|
| True scale | Shingle exposure, panel rib spacing and trim sizes within ±2% of the product spec | Measure the spacing in a close-up render (`lab/tools/closeup.mjs` makes close-ups today; the measuring is new work); in Blender, `texel_density.py` from `blender-suite` |
| True color | The rendered roof, under neutral light, within ΔE 5 of the committed swatch hex (inference: my proposed tolerance), plus your sign-off against a real sample board | Sample the render in a flat-lit test scene; sign-off is lab backlog experiment 002 |
| Resolution | Web snapshot at 3840×2160 or larger (the studio already tiles to 8K). Cycles still at 3840×2160 with at least 192 samples | `RT_RESULT` line from `roof-blender.mjs` |
| Render time | A 4K Cycles still in under 30 s on your GPU (existing lab goal; unproven until experiment 001 runs) | `seconds` in `RT_RESULT` |
| Realism | Passes `lab/tools/roof_qa.py`, and you sign off five points: courses parallel to eaves, drip edge and caps visible, shadows right for the date, real ground context, no floating or flickering parts | Geometry gate plus a close-up review |

---

## 3. Baseline: how roofs are measured and shown today

**Measuring today**
- A roof enters the studio in two ways: a built-in preset (three houses, with a pitch slider from 3/12 to 14/12), or a `.glb` model loaded in the Project tab.
- For a `.glb`, `extractRoofPlanes()` in `roof-visualizer/viewer/js/roof-geometry.js` finds roof triangles by name or slope and clusters them into `RoofPlane` objects.
- `analyzeRoof()` classifies plane edges into eave, rake, ridge, hip and valley. `measureRoof()` adds up area, squares and edge lengths. The layer stack turns those into a takeoff, and `quote.js` turns the takeoff into store quantities.
- The ranch preset measures 27.4 squares and matches a hand calculation (`tests/geometry.test.mjs`).

**Showing today**
- Procedural textures at true size, stepped shingle courses, real nails, tiled snapshots to 8K, browser path tracing, and Cycles in Blender.
- 324 swatch colors are already sampled to hex in `roof-visualizer/scripts/data/supplier-colors.json` (164 Menards, 160 Home Depot).

**Gaps**
1. **No real house has been measured.** Backlog experiment 003 (a real house against its report) is still open.
2. **No address lookup.** Someone has to supply a 3D model or pick a preset.
3. **The roof geometry has no provenance.** `quote.js` already tags quantities as `measured` or `allowance`, but nothing records where the roof shape itself came from or how sure we are.
4. **Blender's shingle shader "reads like a brick pattern up close"** (`lab/GOALS.md`), and the ground around the house is plain procedural grass.
5. **GPU timings are unknown** until experiment 001 runs on the PC.

Note: `PLAN.md` says steps 016–018 are open, but `rooftec-lab` already holds work-in-progress code for them (`quote.js`, `project-file.js`, `supplier-products.js`, the sampled colors). Confirm their real status before scheduling.

---

## 4. Architecture

### Data flow

```
address
  └─> city address / footprint lookup ──> footprint id, outline, ground and top elevation
        ├─ Tier A  city 3D solid (June 2023) ──────────┐
        ├─ Tier B  3DEP lidar 2020: plane fit, roofer ─┤
        ├─ Tier C  outline + typed pitch + skeleton ───┼─> reconcile ─> roof.json
        └─ Tier D  drone or phone capture + tape ──────┘        (planes, edges, source, confidence)
                                                                  │
              ┌───────────────────────────────────────────────────┤
              v                                                   v
   web studio: RoofPlane.fromPolygon -> analyzeRoof        Blender: Plane.from_polygon in roof_core.py,
   -> measureRoof -> takeoff -> priced list (017)          or a GLB whose roof mesh is named "Roof"
```

### The four tiers

| Tier | Source | Gives | Limits | Role |
|---|---|---|---|---|
| A | City "Building Wireframe", `Data/Community/MapServer/66` | One closed solid per building with planar roof faces. Four test houses gave plausible pitches (for example 5.6–6.1/12 across seven faces) | No stated accuracy or vendor. June 2023. Edges are not labelled. City limits only | First choice |
| B | USGS 3DEP lidar `SD_EasternSD_3_2020` (QL2, about 2 points per m², vertical RMSE about 4 cm) | An independent pitch per plane. With `roofer`, a whole roof model | 2020 data. Too sparse for dormers. Edges uncertain by ±0.35 m or more | Cross-check on every roof; fallback outside the city data |
| C | Outline plus a typed pitch, straight skeleton | A plausible hip roof | Assumes one pitch and equal eave heights. Gables need marking by hand | Last resort, never "measured" |
| D | Drone photos or phone scan, scaled with a tape | The most detail, and the only source for new construction | Needs a site visit, Part 107 for a drone, and a taped scale on every job | Optional |

### One roof file for every tier

Every tier writes the same file, `roof.json`, kept under `out/roofs/<footprint-id>/` (already git-ignored, so customer addresses never reach the repo). Proposed fields:

- `format: "rooftec-roof"`, `version`, `address`, `footprintId`.
- `origin`: the local origin in EPSG 32164 (US survey feet) plus latitude and longitude.
- `planes[]`: corner points in local metres, `pitchDeg`, `pitchIn12`, `areaM2`, `planarityM`, and a `provenance` block.
- `edges[]`: `type`, end points, `lengthM`, the planes it joins, and a `provenance` block.
- `checks`: lidar agreement per plane, plan area against the city footprint area, top height against `BUILDINGTOPELEVATION`, permits since capture.
- `attribution`: the text from section 9.

A `provenance` block is `{ source, tier, capturedOn, confidence, note }`. This copies the pattern of the `3d-model-skill` found in the skills note, where "every dimension says where it came from".

### How each tier becomes RoofPlanes

- **Tier A:** unpack the solid, keep faces whose normal points up (drop walls), fit a least-squares plane to each face, project its corners onto that plane, and pass the polygon to `RoofPlane.fromPolygon()`. The test houses were off-plane by at most 0.24–0.39 ft, so this is a small correction; flag any face above 0.5 ft.
- **Tier B, plane fit:** this does not make planes. It makes one pitch per Tier A plane for comparison.
- **Tier B, roofer:** CityJSONSeq output is converted to polygons by our own small script, then `RoofPlane.fromPolygon()`.
- **Tier C:** skeleton faces over the outline, lifted by the typed pitch, then the same call.
- **Tier D:** planes fitted to the photogrammetry point cloud, clipped to the eave outline, then the same call.

On the Blender side, `roof_core.py` has the matching `Plane.from_polygon()` and `roof_source()`. The simplest hand-off is to export a GLB whose roof mesh is named `Roof`, which both programs already understand.

### Overhang and eaves

- The city roof faces stop at the drip line, and the city footprints appear to be roof outlines that include the overhang (inference from four houses: roof plan area matched footprint area to the square foot).
- So area and eave length need no overhang correction. That is what a roofer wants.
- The wall line is unknown. The studio uses it for two things: where to draw walls, and how many ice and water rows reach 24 in inside the wall. Use a typed overhang (default 12 in), flagged `assumed`.
- The solid's flat base is 1.9–8.3 ft below ground. Take ground height from the footprint's `GROUNDELEVATION`, not from the solid.

### Confidence classes and the customer rule

The Rooftec rule is that only measured values reach the customer. A free city model with a "not guaranteed to be accurate" notice is not automatically a measurement, so every value gets one of three classes:

| Class | Meaning | Where it may appear |
|---|---|---|
| `verified` | The tier passed the validation study (027) and this roof's own checks agree, or a site measurement confirmed it | Customer documents |
| `estimate` | One source only, or checks disagree, or the study has not passed yet | Office view, labelled "estimate: verify on site" |
| `assumed` | Typed or default value (overhang, a Tier C pitch) | Office view only, never as a measurement |

Until experiment 027 passes, everything from Tier A is `estimate`.

### Reconciling the tiers

These rules are my proposal (inference). Experiment 027 tunes the thresholds.

1. **Outline:** a scaled and tape-checked Tier D capture beats Tier A; Tier A beats `roofer`; `roofer` beats Tier C.
2. **Pitch, per plane with at least 40 lidar points:**
   - City and lidar agree within 1.5°: keep the city plane and mark the pitch cross-checked.
   - They differ by 1.5° to 4°: lidar overrides the pitch if its plane fit is clean (RMSE 0.10 m or better). The plane is re-tilted about its eave line and its area recomputed. The plane is flagged for review.
   - They differ by more than 4°, or lidar finds no plane: flag "changed or wrong: site check required".
3. **Stale data:** a building permit or occupancy date after June 2023 flags the roof as possibly changed. A house built after 2020 has no lidar check. A house built after June 2023 is not in the solid at all and goes to Tier D or C.
4. **Sanity checks:** roof plan area equals the footprint area within 1%; top height is within about 1 ft of `BUILDINGTOPELEVATION`; sloped area divided by plan area matches the mean pitch.

### Coordinates

- **City data** is EPSG 32164 (NAD83, BLM Zone 14N, US survey feet). Heights are feet and line up with NAVD88 (inferred by the note from sub-foot agreement with USGS; the city does not document it).
- **Subtract first, convert second.** Coordinates look like 15,802,731.75 ft. Subtract the house's minimum corner while still in 64-bit numbers, then convert to metres. Two reasons:
  - 32-bit floats, which Three.js and Blender meshes use, resolve only about 1 ft at that size.
  - The US survey foot (1200/3937 m, about 0.3048006 m) differs from the international foot by 2 parts per million. That is nothing across a house but about 30 ft across the full coordinate (inference: my arithmetic).
- **Axes:** city x is east, y is north, z is up. The web studio is Y-up, so use X = east, Y = up, Z = −north. Blender is Z-up and takes the city axes as they are.
- **Lidar** is streamed as EPT in EPSG 3857 (Web Mercator), where lengths are stretched by about 38% at this latitude (inference: 1/cos 43.5°). Always reproject to EPSG 6343 (UTM 14N metres, the data's native system) before fitting anything. Heights are NAVD88 metres.
- **Datum mismatch:** the city uses the original NAD83 and the lidar NAD83(2011). The offset here is unverified; clip lidar with a 1 m buffer and measure the offset in 026.
- **Map scale:** the projection's distance distortion at Sioux Falls is under 0.01% (inference: my arithmetic), so no ground-scale correction is needed.

---

## 5. Phased steps

Each step is one lab experiment with its own folder under `lab/experiments/`, written up from `lab/experiments/_template/README.md`. New measuring code goes in a new top-level folder, `roof-measure/` (Python, with tests), beside `roof-visualizer/` and `roof-blender/`.

| # | Step | Session | Hours | Done when |
|---|---|---|---|---|
| 024 | City solid into the studio, one house | cloud | 4 | Footprint 235245 shows in the studio with 7 roof planes; plan area 2,941 sq ft and sloped area 3,269 sq ft within 0.5% |
| 025 | Edge classes on city solids | cloud | 3 | Ridge, hip, valley, eave, rake and wall-flashing totals on 2 houses match a hand count from the geometry within 1 ft |
| 026 | Lidar cross-check | cloud | 4 | A per-plane pitch comparison table for the 4 research houses, and the reconcile rules pass unit tests |
| 027 | Accuracy study on 3–5 roofs | cloud + you on site | 3 + 3 | An error table against ground truth, and a pass or fail against section 2 |
| 028 | Address lookup, cache and attribution | cloud | 4 | Typing a test address loads a measured roof in under 10 s; a second load makes no network request |
| 029 | Outline and skeleton fallback | cloud | 3 | A house treated as missing gets a hip roof from its outline and a typed pitch, labelled `assumed` |
| 030 | `roofer` as a separate program | cloud | 4 | `roofer` output for 2 houses loads in the studio, with pitch within 2° of Tier A on main planes; or a written "not good enough at QL2" |
| 031 | Drone or phone capture protocol (optional) | cloud, then you on site and PC | 2 + 4 | One house captured; a taped check length matches the model within 0.5% |
| 032 | True-scale CC0 materials and swatch colors | cloud, then local | 4 + 1 | Three products render at spec size and swatch color in both the web studio and Cycles |
| 033 | Site context | cloud | 3 | The measured house sits on a real aerial ground image, with neighbors as grey blocks and credits shown |
| 034 | Splat or point-cloud surroundings (optional) | local | 4 | A splat of one captured house displays around the rebuilt roof in the studio |

### 024 · City solid into the studio, one house
- **What:** fetch one building, unpack the solid, turn roof faces into `RoofPlane`s, write `roof.json`, and show it in the studio.
- **Tools:** Python standard library only (`zlib`, `struct`, `json`) for the decoder; three.js (MIT) in the studio. The research session's decoder script was not saved, so it is rewritten here with tests.
- **In → out:** footprint id → raw city JSON (cached) → `roof.json` → a new `createMeasuredHouse(roofJson)` in `house.js` that returns the same `{group, planes, segs, materials}` shape as `createHouse()`.
- **Details:** the geometry arrives as `binaryPatches`, a base64, zlib-compressed Esri shape buffer (type 0x80800036). Drop the repeated closing vertices. Query one house by its footprint bounding box (`inSR=32164`, `returnZ=true`); each such query returned exactly one solid in the research.
- **Risks:** the Esri format has surprises (allow 1 extra hour); the cloud session may not reach `gis.siouxfalls.gov` (the "Start here" check finds this out). Fallback: ask the city GIS office for a file export.

### 025 · Edge classes on city solids
- **What:** reuse `analyzeRoof()`, which already tells ridge, hip and valley apart by convexity and merges collinear pieces. Add what real solids need.
- **New work:** (1) a `wall` class for edges where a lower roof meets a wall that rises above it, which today would be counted as rake or top; (2) a larger matching tolerance or vertex snapping, because faces projected onto their best-fit planes can open gaps of a few centimetres (the current tolerance is 0.03 m); (3) the same changes in `roof_core.py`.
- **Tools:** existing studio code; the solid's own wall faces tell us which edges touch a wall.
- **Done when:** see the table; plus `npm test` and `roof_qa.py` still pass.
- **Risks:** the research note's rough classifier inflated rake and hip totals at roof steps. This is the step most likely to overrun.

### 026 · Lidar cross-check
- **What:** for one footprint, pull lidar points, keep the roof, fit a plane inside each Tier A face, and compare pitches.
- **Tools:** PDAL and python-pdal (BSD), Open3D (MIT) or pyRANSAC-3D (Apache-2.0), laspy (BSD-2). Install with `conda install -c conda-forge pdal python-pdal` and `pip install open3d laspy` (suggested by the note; untested in our cloud container). Borrow the datum and accuracy-budget checklist from the `point-cloud-lidar` skill in muend/geoai-skills (MIT), as a pinned reference copy.
- **Pipeline:** `readers.ept` on `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/SD_EasternSD_3_2020/ept.json` with bounds → reproject to EPSG 6343 → crop to the outline plus 1 m → height above ground → keep points more than 2 m up → assign points to Tier A faces → least-squares plane per face.
- **Out:** `lidar.laz` (cached), a pitch table, the `checks` block in `roof.json`, and a small point array the studio can show as `THREE.Points` for a visual check.
- **Risks:** there is no building class in this lidar, so roof points must be separated by height and outline. Planes under about 10 m² get too few points. Trees over the roof add noise. No published study gives pitch accuracy for this method, so 027 measures it.

### 027 · Accuracy study on 3–5 roofs
- **What:** run Tiers A and B on roofs with known measurements and report the errors. This replaces backlog experiment 003.
- **Roofs to pick:** two simple (gable, hip), two medium (cross-gable with valleys), one complex (dormers). All inside city limits, built before 2020, shape unchanged since.
- **Your part (about 3 hours, or under 1 hour if reports exist):** find existing measurement reports first. If you measure by hand, tape eaves and rakes and take the pitch from a ladder at the eave or from a square-on gable photo. It is winter: do not walk an icy roof for this.
- **Out:** a table per roof: area, pitch per main plane, and each edge total, for city alone, lidar alone and reconciled, against truth. Then the tuned thresholds and the confidence class each tier earns.
- **Risks:** a paid report is not truth; phone inclinometer accuracy is unverified in the notes; five roofs is a small sample, so keep logging every later job.

### 028 · Address lookup, cache and attribution
- **What:** a box in the Project tab: type an address, get the measured roof with its confidence badges.
- **Flow:** address → city address layer (`Data/Property/MapServer/0`) → footprint containing that point (`MapServer/5`) → solid by bounding box (`MapServer/66`) → 024, 025, 026 → `roof.json`. A new `GET /api/roof?address=` in `scripts/serve.mjs` runs the Python tool as a separate process.
- **Service rules (see also section 10):** one house per request, no more than 5 records and about one request per second; cache raw answers per house forever; never pull the whole city without asking the city GIS office first; show the attribution line wherever the roof is shown.
- **Tools:** existing server (Node), `roof-measure/` (Python). No new libraries.
- **Risks:** the address layer's field names, and whether the city's `AddressLocators` geocoder is public, are unverified. Fallback: paste coordinates. Another free federal geocoder may exist but was not researched.
- **Also in this step:** write `roof-measure/SKILL.md`, because the notes found no ready-made roof-measuring skill.

### 029 · Outline and skeleton fallback
- **What:** for a house with an outline but no usable solid, build a hip roof from the outline and a typed pitch.
- **Tools:** `straight-skeleton` pinned to **1.1.0** (MIT, pure TypeScript). Versions 2 and 3 wrap GPL CGAL code and must not be bundled.
- **In → out:** city footprint, or a Microsoft footprint outside the city (CDLA-Permissive-2.0) → skeleton faces → `roof.json` with every value `assumed`, or `estimate` once lidar confirms the pitch.
- **Risks:** the 1.x library is described as less robust; gables need a manual "this edge is a gable" switch; Microsoft outlines can be off by about half a metre per edge (the note's inference).

### 030 · `roofer` as a separate program
- **What:** try 3DBAG's `roofer` (GPL-3.0, v1.0.0) on our sparse lidar for houses missing from the city data.
- **How:** run the release binary or the `3dgi/roofer` Docker image as its own process. It reads a LAZ file and an outline and writes CityJSONSeq; our own script converts that. Do not `pip install roofer`: that PyPI name is an unrelated package.
- **Prep needed:** `roofer` wants ground (class 2) and building (class 6) points in a metric system, so we label the roof points from 026 as class 6 ourselves and move the data to a local origin.
- **Risks:** `roofer` is tested at about 10 points per m²; ours has about 2, so small planes will merge or vanish. It cannot model overhangs. Time-box it to 4 hours and accept "not good enough" as a valid result.

### 031 · Drone or phone capture protocol (optional)
- **What:** a one-page field checklist and a processing recipe, for new construction and for roofs where Tiers A and B disagree.
- **Recipe from the capture note:** a nadir grid at roof height plus 15–25 m, then a 45° orbit; fly at 2–3 m/s; place 4–6 printed ArUco markers and tape the distances between them; process in OpenDroneMap (AGPL-3.0, CPU only, as a separate internal program) with Find-GCP, or in COLMAP 4.0 (BSD-3); always tape one extra check length.
- **Why the tape:** area error is about twice the scale error, so scale must be inside 0.5%. Drone GPS alone gave 0.3% in one test and about 7% in another.
- **Phone:** phone lidar reaches about 5 m, so it suits one plane from a ladder, not a whole roof. Free tiers differ; see section 9.
- **Risks:** commercial flying needs an FAA Part 107 certificate; shiny metal roofs can defeat photo matching; the free flight-planning options are limited to DJI Fly's manual waypoints.

### 032 · True-scale CC0 materials and swatch colors
- **What:** replace the weakest procedural looks with photo-based PBR sets, tinted to the store's swatch hex, at true size, in both renderers.
- **Tools:** Poly Haven and ambientCG textures (CC0); `blender-suite` scripts `polyhaven_fetch.py`, `build_pbr_material.py`, `texel_density.py`; Material Maker or NormalMap-Online (MIT) if a map is missing.
- **In → out:** hex colors in `supplier-colors.json` (from step 016) plus product sizes from the two store datasets → one material recipe per product family (base texture, tint, tile size in metres) that the web catalog and `roof_core.py` both read.
- **Rule kept:** colors are committed hex values; store images are never committed.
- **Risks:** one flat hex cannot describe a blended shingle (the sampler already stores a four-color palette, so use it); a swatch hex is not a calibrated color, so the final judge is your eye against a sample board.

### 033 · Site context
- **What:** put the measured house on its real lot.
- **Ground image:** NAIP 2025 at 0.3 m from Microsoft Planetary Computer (public domain USDA imagery; needs a free anonymous token). A 60 m lot is only about 200 pixels wide, so this suits aerial views. For close hero shots keep CC0 grass and concrete and use NAIP for layout.
- **Sharper option:** the city's own orthophotos are tagged CC BY 4.0 but sit behind a OneDrive link that could not be opened by script (unverified). You opening that link in a browser takes five minutes.
- **Never:** the city's 2025 and 2026 imagery layers. They are Nearmap tiles, and the license forbids download.
- **Neighbors and sun:** nearby city solids as plain grey blocks (same CC BY credit); the sun already follows latitude, date and time.
- **Risks:** NAIP is leaf-on, so trees hide some eaves; aerial images show the old roof, so mask the house itself.

### 034 · Splat or point-cloud surroundings (optional)
- **What:** show a drone capture of the real yard around the rebuilt roof, for visuals only. The notes are clear that splats add no measuring accuracy.
- **Tools:** gsplat or nerfstudio (Apache-2.0) to train on the PC's GPU; Spark or GaussianSplats3D (MIT) to display in the studio. Avoid the original 2DGS, PGSR, SuGaR and GOF code: all are non-commercial.
- **Needs:** photos from 031. **Risks:** training needs an NVIDIA GPU; large files on phones.

### Product-accurate geometry: already planned, with tighter tests

No new experiment is needed. Existing steps own this; this plan only adds a measured close-up to each "done when":

| Geometry | Owner | Added test |
|---|---|---|
| Shingle exposure per product | 016 | Course spacing in a close-up within ±2% of the stated exposure |
| Panel ribs (Pro-Rib 36 in cover, 9 in ribs; Pro-Snap 16 in) and metal ridge cap | 019 | Already "spacing matches the spec"; add the ±2% number |
| Drip edge, gutter apron, rake trim profiles | 020 | Profile leg sizes within ±2% of the parsed sizes |
| Shingle hip and ridge cap | 016 | Cap width and exposure from the product data, not the default |

---

## 6. Integration with the existing PLAN.md

| Existing step | Change |
|---|---|
| 016 product picker | No change in scope. Its hex colors feed 032. Adds the close-up tests above |
| 017 priced list | Depends on the roof's confidence. Each measured line inherits it; a list built on an `estimate` roof shows "estimate: verify on site" and cannot be exported for a customer. About 1 hour |
| 018 project files | `house.source` gains a third value, `measured`, with the roof file's tier, capture date and attribution. About 30 minutes |
| 019, 020 profiles | Unchanged, plus the tests above. Together they are this plan's "product-accurate geometry" |
| 021 Blender look-dev | Moves later. Run it on a real measured house with 032 materials and 033 context, on the local GPU. About 1 extra hour. Needs experiment 001 first |
| 022 tap the roof | Depends on 024 and 025. Each tapped plane also shows its source and confidence. About 30 minutes |
| 023 data gaps | Unchanged. The Atlas shingle sizes it lists matter more now, because they drive geometry |
| Backlog 003 real house | Merged into 027 |
| Backlog 002 color accuracy | Becomes the sign-off for 032 |

**Recommended order**
1. 024, 025, 026: get one real roof in and checked.
2. 016, 017, 018 as already planned (finish what is in progress), with the small additions above.
3. 027: the accuracy study. Start gathering reports on day 1, since it depends on you.
4. 028, then 022: address lookup, then tap the roof.
5. 032, 019, 020, 033, then 021: picture quality, ending with the Cycles renders.
6. 029, 030: fallbacks. Then 023. Then 031 and 034 only if wanted.

---

## 7. Scope

**In scope**
- Residential roofs inside Sioux Falls city limits, measured from free public data and checked against lidar.
- A source and confidence label on every measured value.
- Fallbacks for houses without city data, clearly labelled.
- True-scale, true-color portrayal in the web studio and in Blender Cycles.
- An optional capture protocol for drone or phone.

**Out of scope**
- Prices, quotes and store data refreshes (steps 017 and 023 own those).
- Selling measurement reports or map products. The city license says "not for resale mapping products".
- Any paid or billing-account source: Google Solar API, Google 3D Tiles, Nearmap, EagleView, Hover, Cesium ion.
- Flashing details the data cannot see: chimneys, pipe boots, skylights (lab track T3).
- Porting to the Rooftec app. That follows `PLAN.md`: a separate session, after the studio holds up.

**Later**
- A request to the city for a bulk file, the 2023 lidar, and the solid's vendor and accuracy.
- Batch pre-measuring a neighborhood after hail.
- Dormer-level detail from a drone capture; lidar-fitted weighted skeletons; a newer 3DEP collection if one appears.

---

## 8. Costs

**Software and data: $0**

| Item | Cost | Why it is $0 |
|---|---|---|
| City solids, footprints, addresses, permits | $0 | Public REST service, CC BY 4.0 |
| USGS 3DEP lidar, NAIP imagery | $0 | US Government public domain, no account |
| PDAL, Open3D, laspy, three.js, straight-skeleton 1.x | $0 | BSD, MIT, Apache-2.0 |
| roofer, Blender, OpenDroneMap, QGIS, CloudCompare | $0 | GPL or AGPL, run as separate internal programs |
| Poly Haven and ambientCG textures and skies | $0 | CC0 |
| **Total** | **$0** | |

Cloud sessions and the PC are costs you already carry; they are not counted here.

**Optional hardware and regulatory costs (not software or data)**

| Item | Cost | Needed for |
|---|---|---|
| FAA Part 107 knowledge test | about $175 | Any commercial drone flight (031) |
| FAA drone registration | $5 per drone, 3 years | 031 |
| Printed ArUco boards, 4–6 at 30–40 cm | printing and board only (price not researched) | 031 |
| Drone | not priced; only if you do not own one | 031 |
| 100 ft tape, pitch gauge app | likely owned; free apps exist | 027 |
| Laser distance meter | optional (price not researched) | 027, 031 |

---

## 9. License matrix

"Bundle" means it may ship inside the studio. "Separate" means run it as its own program and exchange files. "Internal" means in-house use only.

### Data

| Dataset | License | Use | Attribution or note |
|---|---|---|---|
| City 3D Building Wireframe, Building Footprints, Address, Permits | CC BY 4.0, with "not intended for use in mapping products for resale" | Internal measuring and display. Do not resell the data. This reading is the note's, not legal advice | "Building data: City of Sioux Falls, CC BY 4.0 (creativecommons.org/licenses/by/4.0). Changed: converted to roof planes and measurements. Not a survey." |
| USGS 3DEP lidar | Public domain (standard USGS policy; not re-fetched) | Any | Credit requested: "Lidar: USGS 3DEP" |
| NAIP 2025 | Public domain (USDA; the catalog's "proprietary" tag is a placeholder) | Any | Courtesy: "Imagery: USDA NAIP" |
| City orthophotos (OneDrive folder) | Tagged CC BY 4.0; contents unverified | Check before use | Same city credit |
| City 2025 and 2026 imagery (Nearmap tiles) | View only; no download | **Look, never save or texture** | — |
| Microsoft building footprints | CDLA-Permissive-2.0 | Any | None required |
| Overture, OpenStreetMap buildings | ODbL, share-alike on derived databases | Avoid mixing into our files | — |
| Poly Haven, ambientCG | CC0 | Bundle | None required |
| Store swatches and product photos | Owned by the stores and makers | Sample to hex; never commit images | Source URL kept with each hex |

### Tools

| Tool | License | Use |
|---|---|---|
| three.js, three-mesh-bvh, proj4js, turf, loaders.gl, copc.js | MIT | Bundle |
| earcut | ISC | Bundle |
| straight-skeleton **1.1.0** | MIT (keep its notice) | Bundle. Versions 2 and 3 are GPL inside; do not bundle |
| PDAL, python-pdal, laspy | BSD | Bundle or call |
| Open3D; pyRANSAC-3D | MIT; Apache-2.0 | Bundle or call |
| geoai-skills `point-cloud-lidar` | MIT | Vendor a pinned copy as reference |
| COLMAP; gsplat, nerfstudio, SAM 2 | BSD-3; Apache-2.0 | Bundle or call |
| Spark, GaussianSplats3D, Material Maker, NormalMap-Online | MIT | Bundle |
| **roofer**, bpypolyskel, CloudCompare, QGIS | GPL | Separate, internal |
| Blender; add-ons Point Cloud I/O (GPL-3.0, needs Blender 5.1+) and MeasureIt (free extension; license not stated in the notes) | GPL | Separate, internal. Renders are yours |
| **OpenDroneMap, WebODM, OpenMVS** | AGPL-3.0 | Separate, internal. Never host for customers |
| Find-GCP, OpenCV | Not stated in the notes | Verify before use |
| Phone apps: KIRI Engine Basic, 3d Scanner App, Polycam Free | Free tiers; terms vary (Polycam: glTF only, attribution, "internal use only" wording; 3d Scanner App: commercial clause not found) | Read the terms before a paid job |

### Do not use (non-commercial or paid)

- Scaniverse Classic; MASt3R and DUSt3R; the original 2DGS, PGSR, SuGaR and GOF; Depth Anything V2 Base, Large and Giant; UniDepth; Apple Depth Pro.
- Google Solar API, Google Photorealistic 3D Tiles, Cesium ion's free tier, Nearmap, EagleView, Hover.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **The city solid's accuracy and vendor are unknown** | Experiment 027 measures it; nothing is `verified` before that; lidar checks every roof; ask the city (question 4) |
| **2023 data against newer roofs and additions** | Check occupancy and permit dates; compare by eye with the newest city imagery (viewing is allowed); send changed houses to Tier D or C |
| **QL2 lidar is sparse (about 2 points per m²)** | Use lidar for pitch only, on planes with 40 or more points; take outlines from the city; expect dormers to be missed |
| **The city service changes, slows or blocks us** | One house per request, cached forever; no bulk pulls; keep one public test house as a fixture so tests run offline; ask for a file export |
| **GPL or AGPL code leaking into the studio** | Those tools run as separate programs behind files; pin `straight-skeleton` to 1.1.0; if the studio is ever sold or hosted for customers, have the boundary checked by a lawyer |
| **Nearmap restrictions** | The 2025 and 2026 layers are for looking only; 033 uses NAIP or the city's own orthophotos |
| **An `estimate` reaches a customer** | The confidence class travels with every value into 017; customer export is blocked unless all measured lines are `verified` |
| **Edge classes wrong at roof steps** | 025 adds the wall class and is tested against hand counts; 027 compares edge totals with truth |
| **Winter stops hand measuring** | Use existing reports first; measure from the eave or the ground; do not walk icy roofs |
| **Cloud container cannot install PDAL or reach the data hosts** | "Start here" tests the city host; 026 tests conda and the AWS host first; if blocked, run 026 on the PC |

---

## 11. Open questions for you

| # | Question | Recommended default |
|---|---|---|
| 1 | Do you have measurement reports or your own measurements for 3–5 past jobs inside city limits? | Yes: use them for 027. Otherwise tape three simple roofs from the eaves |
| 2 | After 027 passes, may `verified` city-plus-lidar numbers go on customer documents without a site check? | No. Confirm one eave length and one pitch on site before a signed contract, until 10 jobs are logged |
| 3 | Do you own a drone, and do you want a Part 107 certificate? | Skip 031 and 034 until 027 shows where the free data falls short |
| 4 | May I draft a short email for you to send to the city GIS office (cityofsfgis@siouxfalls.gov), asking for the solid's vendor and accuracy and whether a bulk file or the 2023 lidar is available? | Yes. It costs nothing and could settle the biggest unknown |
| 5 | How many of your jobs are outside city limits (Brandon, Harrisburg, Tea)? | If under 20%, use Tier C labelled `estimate` and leave 030 for later |

---

## 12. First-week schedule

| Day | Time | What |
|---|---|---|
| 1 | 30 min + 2 h | **You:** run "Start here", then list 3–5 past jobs that have reports (addresses stay in a git-ignored `out/` folder). **Cloud:** 024, the decoder and its tests |
| 2 | 2 h | **Cloud:** finish 024. House 235245 appears in the studio; numbers match the research note; screenshots saved |
| 3 | 3 h | **Cloud:** 025, edge classes, including the wall class and the Blender copy |
| 4 | 3 h | **Cloud:** 026, lidar pull and plane fit for the four research houses |
| 5 | 1 h + 1–2 h | **Cloud:** finish 026 and run your 027 addresses through Tiers A and B. **You:** hand over the reports, or tape eaves on one simple roof |
| 6 | 2–3 h | **Cloud:** write up 027: the error table, tuned thresholds, and the class each tier earns |
| 7 | 1 h | **You and cloud:** read the 027 result and decide go or no-go on 028. Update `lab/NEXT.md`, `lab/LOG.md` and `PLAN.md` |

If 027 fails the ±2% area target, do not start 028. Go to question 3 and experiment 031 instead, because the free public data alone would not be good enough.
