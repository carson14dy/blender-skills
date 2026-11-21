---
name: property-model-pipeline
description: Build measurement-grade 3D models of houses/buildings in Blender by fusing inspection photos, satellite/aerial imagery, parcel data, USGS LiDAR and past measurement reports, with every number carrying a ±1σ uncertainty. Use for roof/siding measurement reports (area, squares, pitch, ridge/hip/valley/eave/rake lengths, wall areas), "model this house/property in Blender", "measure this roof", reconciling old reports with new evidence, or checking an inspection against a 3D model.
---

# Property Model Pipeline (measurement-grade)

Turns an address + any evidence you have into an exact parametric Blender model and a
measurement report. Accuracy comes from three rules:

1. **Model, don't trace.** The building is a few *wings* (rectangular sections with a
   gable / hip / shed / flat / gambrel / mansard / pyramid / asymmetric roof). Geometry is
   computed exactly from ~8 numbers per wing (`propmodel/roofgeom.py`) — no hand-drawn
   vertices, no tessellation error, valleys and wall junctions fall out automatically.
2. **Every source is an observation with a σ.** LiDAR points, footprint polygons,
   photo measurements, tape measurements, old EagleView/Hover numbers, assessor data —
   all go into one robust least-squares fit (`propmodel/fusion.py`). Better sources win
   automatically; per-source registration offsets are estimated, not ignored.
3. **Report uncertainty and conflicts.** Every quantity is reported ±1σ, and any source that
   disagrees by > 3σ is flagged CONFLICT (old report before an addition, footprint traced
   at the roof edge, wrong building, unit mistake).

Read `references/accuracy-budget.md` once — it lists the σ to give each kind of evidence and
the classic error traps (Web-Mercator scale, roof-edge vs wall footprints, building lean in
orthophotos, drone altitude above take-off vs above roof, LiDAR older than a renovation).

## Setup (once)

```bash
pip install -r property-model-pipeline/requirements.txt   # numpy shapely laspy pillow requests
pip install bpy        # optional: headless Blender as a Python module (Python 3.11/3.13 wheels)
```
Real Blender (GUI) works too: pass `--blender /path/to/blender`, or drive an open Blender
through the blender-mcp addon with `scripts/blender/send_to_mcp.py`.
`PM=property-model-pipeline/scripts/pm.py` below. Set `PROPMODEL_CACHE` to move the download cache.

## Workflow

```bash
python3 $PM init  JOB --address "123 Main St, Ames, IA"        # or --latlon 42.0078,-93.6897
                  [--parcel-url https://<county>/arcgis/rest/services/Parcels/FeatureServer/0]
python3 $PM fetch JOB        # OSM + Microsoft footprints, orthophoto, 3DEP DEM, parcel attributes
                  [--footprint-layer <city/county ArcGIS footprint layer> --footprint-which roof_outline|footprint]
python3 $PM lidar JOB        # USGS 3DEP point cloud -> level datum, tree-free roof points, planes (pitch ±σ), outline
python3 $PM plot  JOB        # LOOK at JOB/overview.png (Read the image) before modelling
python3 $PM suggest JOB      # one-wing starting spec.json from LiDAR planes
#   -> edit JOB/spec.json: split L/T/U plans into wings, set roof types (see references/model-spec.md)
python3 $PM obs JOB add --target roof.area --value "25.3 sq" --sigma 2% --source "EagleView 2019-06" --kind past_report
python3 $PM obs JOB import past_measurements.csv              # bulk: target,value,sigma,source,kind,date
python3 $PM fit JOB          # -> fit.json, model.json, report.md/.json, overview.png (with model)
python3 $PM blender JOB --glb --render   # -> JOB/out/model.blend, model.glb, plan.png, hero.png
```

Iterate `edit spec → fit → look at overview.png → read the residual table` until:
* LiDAR `roof_z` RMS is ≲ 0.10 m and no observation is flagged CONFLICT (or each conflict is
  explained in the report), and
* the overview shows model edges on the visible roof lines.

Wing-design hints (from the plane list `pm.py lidar` prints and the overview):
* Two big planes facing opposite directions → gable; four → hip; pitch breaks → gambrel/mansard.
* Different ridge heights or pitches → separate wings. A lower garage/porch is its own wing.
* Cross gables: give the projecting wing enough `length` that its ridge dies into the main roof.
* Same plate height & pitch everywhere → `ties` (e.g. `[["M.pitch","G.pitch"]]`) to share evidence.
* Free only what evidence can determine; give everything else a prior (e.g. overhang 0.45 ± 0.15 m).
* Split-level / lopsided gable (equal pitch, plates at different heights): one wing with
  `eave_height_b`. Roof continuing over a porch: `eave_overhang_b`. A roof patch with no walls
  (junction between wings, porch roof): `roof_only: true`. Walls on a sloping lot: `spec.ground`.

Municipal GIS is often the best free source: many cities publish photogrammetric building
footprints (check whether they trace walls or drip edges) and some publish 3-D roof
wireframes/LOD2 multipatches — decode them, bring them in with `obs import-geo`, and expect
a ~1 m horizontal datum offset (NAD83 vs WGS84 handling) that fusion estimates as a shift.
Permit portals (Tyler EnerGov, Accela) date re-roofs and additions: geometry evidence older
than an addition is invalid; a tear-off re-roof leaves geometry valid.

Trees: `pm.py lidar` drops vegetation classes and every non-last return of multi-return
pulses (canopy), the robust fit down-weights stragglers, and the Blender scene contains only
the building. Never trace roof edges under canopy in imagery.

## Photos from inspections

`references/photo-measurement.md` has the full method. Short version:
* `pm.py photo-info IMG...` → focal length in px, GPS, drone altitude/gimbal, nadir GSD.
* `pm.py photo-measure --points pts.json` → rectify a wall/roof plane from a known object
  (door 36×80 in, garage door, brick courses, a tape in frame) and measure lengths or a rake
  pitch on that plane, with Monte-Carlo σ. Feed results in with `pm.py obs JOB add`.
* `pm.py camera-match JOB --image IMG --pairs pairs.json` → resect the camera from ≥ 6
  photo↔model points. RMS > 5 px = the model or a correspondence is wrong. `pm.py blender
  JOB --render` then writes `out/Photo <name>_overlay.png` (model over the photo) for QA.
* Pitch-gauge / tape readings on site are the best evidence there is: σ ≈ 0.25/12 and ≈ 1 cm.

## Photogrammetry / AI meshes

Drone photo sets (ODM / COLMAP / RealityCapture / Polycam) give metric meshes only after
georeferencing: `pm.py align --pairs gcp.json` (≥ 3 point pairs, e.g. roof corners from the
fitted model or surveyed GCPs) → 4×4 similarity transform + RMS. Then
`scripts/blender/measure_mesh.py` measures any mesh in Blender. Generative image-to-3D
(Meshy etc., the `image-to-3d` skills) is NOT metric: never report measurements from it
without aligning and checking it against LiDAR or tape.

## Outputs

| File | Content |
|---|---|
| `report.md` / `report.json` | roof area/squares, waste, pitches, ridge/hip/valley/rake/eave/flashing lengths, facade wall areas, evidence reconciliation, fitted parameters — all ±1σ |
| `model.json` | exact facet polygons, walls, classified edges (consumed by the Blender script) |
| `overview.png` | orthophoto + footprints + LiDAR planes + model edges |
| `out/model.blend`, `out/model.glb` | metric, georeferenced (ENU, 1 unit = 1 m) Blender scene / glTF |
| `out/plan.png`, `out/hero.png`, `out/Photo *_overlay.png` | renders and photo overlays |

## Rest of the house (presentation detail)

`scripts/blender/add_details.py OUT/model.blend details.json OUT/model_detailed.blend` adds
openings (windows, sliders, doors, garage door with section joints, egress), fascia, soffits,
gutters, downspouts, foundation band, decks with posts/railings/balusters, stairs, porch
ceilings, brick piers, lap-siding and shingle-course materials — all in a `Details` collection,
so measured roof/wall geometry and every number in the report stay untouched. Place each
opening by wall (`"M:-u"`), distance along the wall `u`, sill height and size from the photo
measurements; mark anything placed by eye as approximate in its label. The studio export
includes the Details collection.

## Yard and grounding

`scripts/build_site.py JOB features.json site_scene.json` builds the site from the LiDAR ground
returns (class 2, model datum): a terrain grid plus crisp draped overlays for street, concrete
(driveway, walks, sidewalks) and rock beds from planimetric polygons (city "impervious surface",
sidewalk lines buffered by their width), curb lines, the subject parcel and point features
(hydrants). `scripts/blender/add_site.py detailed.blend site_scene.json yard.json out.blend`
adds it in Blender (collection `Site`; yard items: AC unit, fire pit, egress well, meters) and
GROUNDS the house: walls and foundation extend 0.3 m below the terrain under them, deck posts,
stair stringers, downspouts, piers and stoops land on it. No vegetation is generated.
Window wells: give the yard item the well's width, projection, rim and floor heights, and pass
the same outline to `build_site.py --cutouts` so the pit is really cut out of the ground (a well
drawn on unbroken ground buries a below-grade egress window). LiDAR returns from inside an
existing well drag the surface down around it; the cut-out levels the grade there.
Trace bed edges and small fittings on solved photo cameras (ground plane or wall plane), not by
eye: add one or two near-field anchors (a wall corner at grade, a feature located on the ortho)
when all match points are on the building, or near-ground projections drift by a metre. City
features come in the city's datum — apply the per-source shift the fit estimated.
`export_studio_glb.py ... --with-site` includes the site; procedural colours are baked to flat
glTF colours on export.

Hillside lots and new cities: find the local parcel, assessor, LiDAR-inventory and planimetric
layers first (`references/data-sources.md`, "A new city or state"). For a house cut into a slope run
`pm.py lidar --ground-mode surface --footprint-file <city outline> --footprint-shift dx,dy --accept
--flat-z lo,hi` (filtered ground surface, real roof planes only, decks listed with their heights) and
`build_site.py --ground filtered --ground-exclude decks.json --house-extra garage.json`. In
`details.json`, `extra_walls` carry a garage under a deck (with its door), `skylights` and
`chimneys` sit on the fitted roof, and `post_edges` keeps posts off deck edges that walls carry.

## Web viewers / Roof Layer Studio

`scripts/blender/export_studio_glb.py OUT/model.blend house.glb` writes a viewer-ready model:
roof facets named `Roof F1…` (so plane finders pick them up), walls joined as siding, no labels,
ground, trees or cameras. Where a host cannot serve `.glb` (e.g. Claude artifacts), convert it to
embedded glTF JSON (base64 buffer, saved as `.gltf.json`). Do NOT let the page `fetch()` that
`data:` buffer — sandboxed hosts' Content-Security-Policy blocks it and the load silently fails.
Decode the base64 in the page, repack a GLB `ArrayBuffer` and call `GLTFLoader.parseAsync`. Test
web deliveries under a restrictive CSP, not on a bare local server.
Project-card thumbnails: `scripts/blender/render_thumbnail.py SITE.blend thumb.jpg --front-az <bearing the
front faces>` renders the house alone (yard surfaces hidden, details kept) on a light backdrop with a soft
contact shadow from a front-corner 3/4 view, auto-cropped to 4:3 — the look of contractor design tools. List
it as `thumb` in the viewer's project index.
Automatic edge classification in viewers can double-count where one roof runs under another's
overhang; ship the report's verified edge lengths alongside the model for takeoffs.

## Rules

* Never invent observations or σ to make a fit look good; a missing source is just missing.
* Tell the user the LiDAR year and any CONFLICT rows, in plain words, with the report.
* Units: internally metres. Accept "42' 6\"", "12.95m", "25.3 sq", "2450 sqft", "6/12", "26.6deg".
* Attribution: Esri imagery / OSM / Microsoft footprints require attribution in deliverables
  (`references/data-sources.md`).
