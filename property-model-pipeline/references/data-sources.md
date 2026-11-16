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
