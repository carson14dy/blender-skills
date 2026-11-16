# Accuracy budget — what σ to give each source, and the traps

σ values are 1-sigma (68 %). When unsure, be conservative: a σ that is too small makes a
source dominate and hides conflicts; the fit's *variance factor* (≈1 is ideal) tells you
whether the σ's are realistic overall.

## Default σ by source

| Source | Quantity | Typical 1σ | Notes |
|---|---|---|---|
| Tape / laser on site | length | 0.5–2 cm | per measurement; more if over landscaping |
| Pitch gauge / digital level on roof | pitch | 0.25/12 (≈1°) | on the field of the facet, not near edges |
| USGS 3DEP LiDAR QL1/QL0 (≥ 8 pts/m²) | point height | 0.08–0.12 m | `roof_z` observation; pitch per facet ±0.05/12 or better |
| USGS 3DEP LiDAR QL2 (2–4 pts/m²) | point height | 0.10–0.15 m | |
| LiDAR roof outline | edge position | spacing/2 + 0.15 m | auto-set by `pm.py lidar` |
| Drone photogrammetry with GCPs | 3-D point | 2–5 cm | without GCPs: GPS-only scale ±1–3 % |
| Nadir drone photo (GSD from altitude) | length | 2–3 px × GSD + 1 % | altitude must be above the measured surface |
| Rectified photo (door / tape reference) | length on that plane | MC σ from `photo-measure` | only valid on the reference plane |
| Esri / Nearmap / satellite ortho trace | edge position | 0.5–1.0 m | building lean; let fusion estimate the shift |
| NAIP (0.6 m) trace | edge position | 0.8–1.5 m | |
| Microsoft ML footprints | edge position | 0.6–1.0 m | `pm.py fetch` uses 0.7 m + estimated shift |
| OSM footprints | edge position | 0.5–2 m | quality varies by mapper; 0.6 m + shift |
| Professional report (EagleView, Hover, GAF QuickMeasure…) | roof area | 1–2 % | per-facet pitch ±0.5/12; lengths ±1–2 % |
| Old hand/insurance sketch | area | 5–10 % | |
| Assessor "building sq ft" | footprint / living area | 10–20 % | definition varies (heated area, excludes garage) |
| Assessor stories / year built | eave height prior | 1 story: 2.7–3.0 m plate; 2 story: 5.4–6.0 m | use as prior, not observation |

## Traps that cost real accuracy

1. **Web Mercator is not metric.** 3DEP EPT and web tiles are EPSG:3857; distances there are
   inflated by 1/cos(lat) (≈ +30 % at 40° N). `propmodel` converts everything to a local ENU
   frame. Never measure in 3857 or in raw lat/lon degrees.
2. **Imagery footprints are ROOF outlines.** MS/OSM/traced polygons follow the drip edge,
   including the overhang (typ. 0.3–0.6 m). Building walls on them inflates wall length by
   2× overhang per side and roof area by several %. They are fed in as `which: roof_outline`.
3. **Building lean (relief displacement).** Orthophotos are rectified to the ground, not the
   roof; roofs appear shifted away from nadir by up to 1–2 m. Fusion estimates a per-source
   `shift.<src>.dx/dy` — check it in the parameter table (a 1 m OSM shift is normal).
4. **Plan area vs true area.** True area = plan area × √(1 + slope²). For uniform pitch and
   plate height, total roof area = roof-outline plan area × slope factor regardless of hip/
   gable layout — a quick sanity check of any report.
5. **Drone altitude.** DJI `RelativeAltitude` is above the take-off point. GSD on a roof uses
   altitude above the ROOF (`photo-info --surface-height`).
6. **Stale data.** LiDAR (year printed by `pm.py lidar`), imagery dates and old reports may
   predate re-roofs, additions or demolitions. A CONFLICT on a dated source is usually this.
7. **Assessor area definitions.** "Living area" excludes garages/porches and counts upper
   floors; it is never the roof footprint.
8. **Rectification only works on one plane.** A door reference measures the wall it is in —
   not the roof above it and not a wall at a different depth.
9. **Correlated samples.** A footprint polygon is one observation from one source, not 100
   independent ones. `fusion` deflates its weight to ≈ one sample per vertex.
10. **Tilted height reference.** Heights above a fitted (sloped) ground plane tilt every roof
    plane by the lot slope: on a 2 % lot, 5.94/12 read as 5.71/12 and 5.98/12 as 6.16/12.
    `pm.py lidar` uses a level datum (ground elevation at the origin).
11. **Datum offsets between public sources.** City GIS served in WGS84 may apply a different
    NAD83→WGS84 transform than the LiDAR (≈1 m in 2026). Give each source a `shift`.
12. **Pitch from far away.** Pitch read off a photo taken at an angle to the gable is biased
    (foreshortening). Rectify the gable wall first, or use LiDAR/gauge.

## Reading the fit

* `roof_z` RMS ≲ 0.10 m on QL1 data = the wing layout matches the real roof. 0.2–0.5 m means a
  missing wing, wrong roof type or wrong ridge direction; look at the overview.
* `variance_factor` ≪ 1: σ's are conservative (fine). ≫ 1: something is mis-modelled or a σ
  is too optimistic; uncertainties are inflated by √factor automatically.
* Large σ on a parameter (e.g. where two wings meet) means no evidence pins it down — add a
  tape measurement or a photo of that spot if the deliverable depends on it.
