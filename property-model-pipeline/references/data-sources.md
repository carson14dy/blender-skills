# Data sources

| Data | Endpoint | Key? | License / note |
|---|---|---|---|
| Geocoding (US) | geocoding.geo.census.gov `onelineaddress` | no | public domain; ±10–50 m |
| Geocoding fallback | nominatim.openstreetmap.org | no | ODbL; ≤ 1 req/s |
| OSM footprints | Overpass (overpass-api.de, maps.mail.ru mirror, kumi) | no | ODbL, attribute OSM |
| Microsoft ML footprints | minedbuildings.z5.web.core.windows.net `dataset-links.csv` (zoom-9 quadkey tiles) | no | ODbL |
| LiDAR point clouds | USGS 3DEP EPT on AWS `s3-us-west-2.amazonaws.com/usgs-lidar-public/<project>/ept.json`; index `usgs.entwine.io/boundaries/resources.geojson` | no | public domain |
| Bare-earth DEM | elevation.nationalmap.gov `3DEPElevation/ImageServer/identify` | no | public domain |
| Orthophoto (default) | server.arcgisonline.com `World_Imagery/MapServer/export` | no | Esri ToU; attribution; no bulk |
| Orthophoto (public domain) | imagery.nationalmap.gov `USGSNAIPPlus/ImageServer/exportImage` | no | 0.3–0.6 m, sometimes slow |
| Parcels | county/state ArcGIS REST layers (`…/FeatureServer/N/query`) | usually no | public record; search "<county> parcels FeatureServer" |
| Parcels nationwide (paid) | Regrid, ReportAll, county APIs | yes | pass their GeoJSON polygon in as an `outline`-type context layer |
| High-res oblique/ortho (paid) | Nearmap, EagleView, Vexcel | yes | better than satellite for tracing; still σ ≥ 0.3 m |
| Overture buildings | overturemaps.org (GeoParquet on S3/Azure) | no | ODbL/CDLA; needs duckdb |

Outside the US: replace 3DEP with national LiDAR (e.g. UK EA, NL AHN, DK, CH swisstopo) — load
the LAS/LAZ with laspy, convert to the local frame with `LocalFrame.from_geodetic`, and feed the
same `lidar.segment_planes`. Footprint/imagery sources work worldwide.

Always state LiDAR acquisition year and imagery provider in deliverables (`report.md` does).

## A new city or state: find the local sources first

National layers are the fallback, not the start. Before modelling in a new place, spend ten
minutes finding the local ones; they are usually better and all public:

1. **Parcels**: the state or county GIS (search "<state> cadastral" / "<county> parcels
   FeatureServer"). Query with explicit `outFields` (parcel id, legal, acres, values): never
   `outFields=*`, which brings back owner names. Note the layer URL in the job's `sources.json`.
2. **Building record**: the assessor/CAMA service behind the parcel viewer (year, style, stories,
   basement and daylight basement, garage type and area, decks/porches with areas, fireplaces,
   siding and roof material). Use only the dwelling/building endpoints; skip any owner or
   "property summary" endpoint that returns names.
3. **LiDAR**: the state LiDAR inventory (project name, flight dates, quality level) tells you
   which 3DEP EPT dataset covers the site and its real acquisition dates (pass `--year`).
   Statewide QL1 collections are often delivered with almost no class-2 (ground) points: use
   `pm.py lidar --ground-mode surface` and `build_site.py --ground filtered` (auto when < 10 %).
4. **City planimetrics**: many cities publish building, deck, driveway and sidewalk polygons
   (e.g. Ecopia) and leaf-off orthophotos (e.g. Nearmap 7.5 cm) on their ArcGIS server. Bring the
   building outline in as an `outline` observation with its own `shift`; register ground-level
   features (driveways, decks on grade) with a separate shift checked against LiDAR heights.
5. **Permits**: the city's permit layer dates re-roofs and additions (explicit `outFields`).

Record every endpoint, what it returned and what not to call in the job's `sources.json`.

## Hillside lots

* Heights above a filtered ground SURFACE, last returns only (`--ground-mode surface`); a house cut
  into a slope meets grade at its uphill eave, so the walls (city outline, `--footprint-file`
  with `--footprint-shift`) are masked from the ground and low points inside them are kept
  (`--min-hag-inside`).
* `--accept` keeps real roof planes only (n, RMS, slope, patch area), drops thin strips of
  hillside that happen to lie on a roof plane, removes canopy over the eaves and routes level
  planes below every eave to decks; `--flat-z lo,hi` lists decks and slabs with their heights.
* Expect several floor levels: read them from the deck tops, the garage apron and the uphill
  grade, and put walls on `base_z`; a garage under a deck is presentation geometry
  (`extra_walls` in `details.json`), not a roof wing.
