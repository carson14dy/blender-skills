# City of Sioux Falls "3D Building Wireframe" layer: hands-on check for residential roof geometry and pitch

Method: read-only ArcGIS REST queries with curl on 2026-11-16, using small result counts (no more than 5 features per query; 5 wireframe features decoded in total). Multipatch geometry comes back as zlib-compressed Esri shape buffers (`binaryPatches`). I decoded these locally with a short Python script and computed face normals, slopes, areas and planarity. I tested four single-family homes (footprint STRUCTURE = 110) in south Sioux Falls, around 43.481 N, 96.73–96.76 W. Every number below comes from those query results unless it is marked as an inference.

Endpoints used:
- Layer: https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66?f=pjson
- Layer metadata: https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/metadata?f=xml (also `&format=default`, ISO 19139)
- Footprints: https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5?f=json and its `/metadata?format=default&f=xml`

## 1. What the layer is: geometry type, SR, fields, description, license, source

### Takeaway
The layer is not a set of labelled roof lines. Each building is one closed 3D solid (`esriGeometryMultiPatch`, hasZ = true). It is built from planar polygon faces: vertical walls plus sloped or flat roof planes. Every feature has the same attributes, which are leftovers from a CAD (MicroStation-style "Cell") import: Layer "3101", RefName "BUILD", Linetype "Solid". There is no ridge, hip, valley or eave label, and no pitch field. Coordinates are in US survey feet (NAD83 BLM Zone 14N ftUS, EPSG 32164). Z values are absolute elevations in feet and line up with NAVD88 (see section 5). The metadata licenses the data under CC BY 4.0, with a "not for mapping products for resale" clause. It does not name a vendor or a capture method.

### Cited Findings
- Layer name "Building Wireframe", type Feature Layer, `"geometryType": "esriGeometryMultiPatch"`, `"hasZ": true`, `"hasM": true`, `capabilities: "Query,Map,Data"`, `maxRecordCount: 1000`, `supportsPagination: true`, `supportedQueryFormats: "JSON, geoJSON"` — [Layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66?f=pjson)
- Description (full text): "3D Building wireframes layer, acquisition date June 2023." `copyrightText: "City of Sioux Falls"` — [Layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66?f=pjson)
- Spatial reference wkid 32164. The metadata gives the projection as `NAD_1983_BLM_Zone_14N_ftUS` with linear unit "Foot_US (0.304801)". zTolerance is 0.001 and xyTolerance about 0.0033 ft — [Layer metadata XML](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/metadata?f=xml)
- The layer extent reports zmin = zmax = -100000. This is a placeholder: the features themselves have real Z values, from 1288.0 to 1671.3 for the `Elevation` attribute (outStatistics query) — [Layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66?f=pjson)
- Fields: OBJECTID, FID_, `GIS.BuildingWireframe.Entity` (String 16), Level_, Layer, Color, Linetype, Elevation (Double), LineWt, RefName, Shape. The metadata also lists created_user/date, last_edited_user/date and GlobalID, but the service does not expose them. No field defines the units or meaning of `Elevation` — [Layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66?f=pjson); [metadata](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/metadata?f=xml)
- `returnDistinctValues` queries on the whole layer each return one value. Entity = "Cell", Layer = "3101", Level_ = 1, Color = 0, Linetype = "Solid", RefName = "BUILD". No attribute separates ridge, eave or hip, or roof from wall — [Query endpoint](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query)
- Feature count is 95,901 (`returnCountOnly`, and also `returnIdsOnly` gives 95,901 IDs). The footprint layer metadata lists 97,503 footprints — [Query](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query?where=1%3D1&returnCountOnly=true&f=json); [Footprint metadata](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5/metadata?format=default&f=xml)
- License text from the metadata: "This data is produced and maintained by the City of Sioux Falls Civic Analytics Division. This licensed data is intended for use internally by the City of Sioux Falls and also for public use as described under the Creative Commons Attribution 4.0 United States License [link to creativecommons.org/licenses/by/4.0/]… These drawings and data are neither a legally recorded map nor a survey… intended for broad planning purposes only… not guaranteed to be accurate, correct or complete… This data is not intended for use in mapping products for resale." Metadata date 2024-09-15; keywords include "Downloadable Data" — [Layer metadata (ISO)](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/metadata?format=default&f=xml)
- The parent MapServer's service description adds: "reference purposes only… does not guarantee accuracy… should not be solely relied upon for any decision making" — [Community MapServer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer?f=json)
- No vendor, capture method (stereo compilation or lidar) or accuracy statement appears in the layer JSON or either metadata format. For comparison, the sibling "Elevation Contours" layer (layer 8) says it was "generated by the Sanborn Map Company in April 2023" at a 1-ft interval — [Contours layer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/8?f=json)
- A web search found no public record that names the 2023 wireframe vendor. Press coverage of Sioux Falls aerial mapping is about the city's Nearmap subscription, including plans to use Nearmap's 3D mesh in ArcGIS Urban — [Nearmap customer story](https://nearmap.com/customer-stories/detailed-aerial-maps-in-sioux-falls); [GovTech](https://www.govtech.com/products/aerial-imagery-software-streamlines-city-work-in-sioux-falls.html)

### Inferences
- The Entity = "Cell", Level, Color and LineWt fields are the standard attributes ArcGIS adds when it imports MicroStation DGN cells. So the wireframe was most likely delivered as a DGN/CAD 3D model by a contractor and then converted to multipatch. Sanborn (2023 contours) and Nearmap (imagery and 3D) are both plausible sources, but neither is confirmed.
- Planar roof facets that join cleanly at ridges and hips (section 2) are typical of photogrammetric or lidar-assisted LOD2 roof modelling, not raw point clouds. The method is still unconfirmed.
- The "United States License" wording links to the international by/4.0 URL. CC has no ported "4.0 United States" license, so treat it as CC BY 4.0. The city's ArcGIS Online items say "Creative Commons Attribution 4.0 International License" (section 4).

### Gaps
- No published horizontal or vertical accuracy, vendor, or capture method. Only the city GIS office (cityofsfgis@siouxfalls.gov, per the metadata) could confirm these.
- The meaning of the per-feature `Elevation` attribute is undocumented (see section 2).

## 2. What residential features look like: vertices, Z variation, line types, units

### Takeaway
Each house is one multipatch made of 27–38 planar faces stored as "FirstRing" parts (part type 4). All parts are walls (exactly vertical) or roof planes. Wall bottoms sit at one flat base elevation. Wall tops trace the roof perimeter. Roof planes rise from eave height to ridge height, so the Z values do vary the way real roof lines would. The ridges, hips, valleys, eaves and rakes exist only implicitly, as shared edges between faces. You have to derive them from the topology because no edge is labelled. Units are US feet throughout.

### Cited Findings (my decoding of query results; queries used the footprint bounding boxes as envelopes, inSR = 32164, `returnZ=true`)
Source for all rows: the [wireframe query endpoint](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query) and the [footprint query endpoint](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5/query).

| Footprint OID (single-family) | Wireframe OID | Faces (walls/roof) | Points | Plan bbox (ft) | Wireframe Z min–max (ft) | Footprint GROUNDELEVATION / BUILDINGTOPELEVATION | Stories attr |
|---|---|---|---|---|---|---|---|
| 235245 | 79199 | 31 (24/7) | 239 | 65.2 × 79.8 | 1482.50 – 1504.03 | 1484.40 / 1504.30 | 2 |
| 235246 | 75599 | 32 (20/12) | 240 | 88.4 × 73.4 | 1508.63 – 1534.90 | 1515.32 / 1535.40 | 2 |
| 235247 | 80293 | 27 (20/7) | 204 | 53.0 × 84.1 | 1514.86 – 1549.55 | 1519.25 / 1549.46 | 3 |
| 235248 | 78055 | 38 (27/11) | 284 | 88.9 × 64.7 | 1512.00 – 1541.55 | 1520.27 / 1542.60 | 2 |

- Each envelope query over a house footprint returned exactly one wireframe feature, so the layer has one multipatch per building. All attributes were the constant values listed in section 1 (RefName "BUILD"). The per-feature `Elevation` value (1493.74, 1522.88, 1532.02, 1527.03) falls between the base and the top of each model and matches neither eave nor ridge.
- Each ring repeats its start vertex several times. This is a decoding artefact: the closing and duplicate vertices have zero-length edges. Wall rings run from Z = base (for example, relative Z 0.00) up to the roof perimeter heights (for example, 12.35 and 15.48 ft above base).
- The roof planes are close to planar. The maximum out-of-plane deviation of any roof-face vertex was 0.24, 0.33, 0.24 and 0.39 ft for the four houses (SVD plane fit).
- The plan (horizontal) area of the roof faces matched the footprint polygon's `Shape.STArea()` to the square foot on all four houses: 2941/2941, 4622/4622, 2668/2668 and 3254/3254 sq ft.
- Large features exist too. One feature near 43.531 N, 96.756 W (OID 87334) has 613 faces and 4,930 points, a 692 × 852 ft bbox and Z of 1494.0–1629.8. It is presumably a large institutional building.
- The highest roof Z is 0.09–1.05 ft from the footprint layer's `BUILDINGTOPELEVATION` (−0.27, −0.50, +0.09, −1.05 ft, wireframe minus footprint).

### Inferences
- Roof area equals footprint area exactly, and walls drop vertically from the roof perimeter. So the model has no separate overhang. The "eave" edges in the model are the outer roof edge (drip edge), and the city's footprints appear to be roof outlines rather than foundation outlines. A roofer can treat the plan area as including overhangs. Wall-line measurements cannot be taken from this data.
- The wireframe base is a single flat Z that sits 1.9–8.3 ft below the footprint's ground elevation. It looks like the lowest adjacent grade or a modelling datum, not the finished floor, so do not use base-to-eave height as wall height without checking.
- My crude topology classifier (roof–roof horizontal edge = ridge; roof–roof sloped edge = hip or valley; roof–wall horizontal edge = eave; roof–wall sloped edge = rake) produced per-house edge totals. Examples: house 235245 gave ridge 84.9 ft, hip/valley 25.0, eave 116.2, rake 245.9. House 235246 (a hip roof) gave hip/valley 341.0 and eave 270.5. These totals are not trustworthy as written: wall-step edges between roof tiers and split edges inflate the rake and hip counts. They do show that line lengths can be computed from the geometry, but only after real cleanup (merging collinear segments, telling hips from valleys by convexity, handling roof steps). Nothing in the data does this for you.

### Gaps
- Model level of detail is unknown: whether chimneys, dormers and small bump-outs are captured, and what the minimum feature size is. The faces as small as 26–40 sq ft on these houses suggest dormers or small facets are modelled, but I did not compare them with imagery.
- No ground-truth check against a field-measured roof was possible here.

## 3. Worked example: implied pitch from 3D coordinates (house 235245, wireframe OID 79199)

### Takeaway
House 235245 is a gable/hip combination. It is 65.2 × 79.8 ft in plan and 21.5 ft from base to the top ridge. Eaves sit about 11.8–12.4 ft above base and the main ridge about 21.4–21.5 ft above base. From the coordinates, the implied pitch is about 5.8/12 (25.4°), and all seven roof faces read 5.6–6.1/12, which points to a uniform 6/12 roof. That is plausible for a residence. The other three houses came out at about 3.0–3.5/12, 7.5–8.0/12 and 4.3–6.5/12.

### Cited Findings (computed from decoded vertices; coordinates relative to the model's min corner: x0 = 2239372.92, y0 = 15802731.75, z0 = 1482.50 ft) — [wireframe query](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query)
- Main ridge runs from (47.86, 6.80, 21.53) to (30.22, 57.33, 21.41). Horizontal length is about 53.5 ft and it drops only 0.12 ft along its length, so it is effectively level.
- The largest roof face (face 30, about 1,179 sq ft sloped area) has an eave vertex at (28.75, 0.00, 11.78) and a ridge vertex at (47.86, 6.80, 21.53). Rise is 9.75 ft and run is 20.28 ft, giving 9.75 / 20.28 × 12 = 5.77/12. The face normal gives 25.4°, which is 5.7/12.
- Face-normal slopes on all 7 roof faces: 26.3°, 26.6°, 25.1°, 25.9°, 26.9°, 25.3°, 25.4°. These equal 5.6–6.1 in 12.
- Horizontal extent is 65.2 × 79.8 ft bbox and 2,941 sq ft roof plan area. Vertical extent is 21.53 ft from the flat base to the ridge. Ridge sits 9.1–9.8 ft above the eaves.
- Summed sloped roof area is 3,269 sq ft (32.7 squares, before waste). That is 1.11 × plan area, consistent with 6/12, where the slope factor is 1.118.
- The other houses, as face-normal pitch ranges with area statistics:
  - 235246: 12 faces, 14.0–16.2°, which is 3.0–3.5/12 (a low-slope hip). Plan area 4,622 sq ft, sloped area 4,793 sq ft, eave about 20 ft above base, ridge about 26.3 ft above base.
  - 235247: 7 faces, 29.7–33.6°, which is 6.8–8.0/12. Two eave tiers at about 13.5 and 22.4 ft above base, ridge 34.7 ft above base. A check vector on face 21 gave rise 12.31 over run 18.89, which is 7.8/12. Sloped area 3,178 sq ft.
  - 235248: 11 faces, mostly 23.5–26.8° (5.2–6.1/12). One face is 19.7° (4.3/12) and one small face is 28.5° (6.5/12). Sloped area 3,580 sq ft.

### Inferences
- The values cluster tightly within each roof (for example, 5.6–6.1/12 on one house) and fall into common framing pitches (about 3/12, 6/12, 8/12). That suggests the model holds real pitch information to within roughly ±0.5/12, but this is not validated against field data. The face-to-face spread of about 0.5/12 on a roof that is presumably uniform is a rough indicator of the noise level.
- 235246 at about 3–3.5/12 is low but within the range used on some ranch and hip homes. It is below the 4/12 most asphalt-shingle work assumes, so it deserves a ground-truth check before any trust is placed in it.
- For a contractor, the data gives a free and probably decent first estimate of pitch and of plan and sloped area for any city building captured in June 2023. It is not a measurement report: it carries no accuracy guarantee, has no labelled line types, does not reflect roofs changed after June 2023, and has no overhang or eave detail beyond the outer edge.

### Gaps
- Not validated against a known pitch, such as a permit drawing or a field measurement, for any of these houses.
- Sample size is small: four single-family homes in one part of the city.

## 4. Bulk download, record limits, license

### Takeaway
The wireframe is available only through the REST MapServer layer. It is not listed on the city's DataWorks (ArcGIS Hub) portal and has no ArcGIS Online item. Queries are capped at 1,000 records each, but pagination works, so the full 95,901 features could in principle be pulled with about 96 paged requests (not done here). GeoJSON output fails for this multipatch layer, so only Esri JSON with compressed `binaryPatches` is available. The license is CC BY 4.0 per the layer metadata, with a "not for mapping products for resale" caveat. Building Footprints, by contrast, is a DataWorks/ArcGIS Online item marked CC BY 4.0 International.

### Cited Findings
- `maxRecordCount: 1000`, `supportsPagination: true`. A test with `resultOffset=95000&resultRecordCount=3` returned OIDs 95001–95003 with `exceededTransferLimit: true` — [Layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66?f=pjson); [query](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query)
- `f=geojson` on a single wireframe feature returned `{"error":{"code":400,"message":"Failed to execute query."}}` even though the layer advertises geoJSON. `f=json` returns `binaryPatches`: base64 of an Esri extended shape buffer, type 0x80800036 (General MultiPatch with the HasZ and Compressed flags), zlib-deflated — [query](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query)
- The DataWorks Hub search API returns `numberMatched: 0` for "wireframe". Building-related items that do appear include Building Permits and Structures, both marked CC-BY-4.0 — [DataWorks search API](https://dataworks.siouxfalls.gov/api/search/v1/collections/dataset/items?q=wireframe&limit=5); [DataWorks](https://dataworks.siouxfalls.gov/)
- ArcGIS Online search of the `cityofsiouxfallsgis` account for wireframe, 3D or scene items found no wireframe item. It did find a "Building Footprints" item (3ca4a96b…) pointing to Property/MapServer/5, whose license reads "The City of Sioux Falls provides open data licensed under the Creative Commons Attribution 4.0 International License" — [ArcGIS item 3ca4a96b2f5847fdbac6568c6dc20ee3](https://www.arcgis.com/home/item.html?id=3ca4a96b2f5847fdbac6568c6dc20ee3)
- Building Footprints is also listed in the data.gov catalog, harvested from the city portal — [data.gov Building Footprints](https://catalog.data.gov/dataset/building-footprints-b129f)
- The REST root (`/arcgis/rest/services?f=json`) lists folders AddressLocators, DashboardData, Data and Utilities. A "Basemaps" folder exists but returns "Token Required". The HTML Services Directory is disabled: "The administrator has disabled the Services Directory" — [REST root](https://gis.siouxfalls.gov/arcgis/rest/services?f=json)

### Inferences
- The metadata keyword "Downloadable Data" and the "Data" capability suggest download is intended. In practice it means scripted paging of the REST layer plus a custom multipatch decoder, or using ArcGIS Pro, which reads the MapServer layer natively. One house at a time costs nothing and is easy. A citywide pull is feasible but heavy, around 25–35 KB of base64 per house.
- "Not intended for use in mapping products for resale" probably restricts reselling the data as a map product. Using it internally to estimate a job is probably fine under CC BY with attribution. That reading is mine, not legal advice.

### Gaps
- I did not test whether ArcGIS Pro or other clients can export the layer to a file geodatabase or other 3D formats.

## 5. Building Footprints layer (Property/MapServer/5): elevation units, datum, and whether top = ridge

### Takeaway
GROUNDELEVATION and BUILDINGTOPELEVATION are absolute elevations in feet. They agree with USGS 3DEP (NAVD88, feet) to within 0.03–0.9 ft at the four test houses, so the datum is effectively NAVD88 feet. The datum is inferred, because the city documents neither units nor datum. BUILDINGTOPELEVATION matches the wireframe's highest roof point, the main ridge on these houses, within about 0.1–1.05 ft. "Top elevation" therefore approximates ridge height. Subtracting ground gives about 20–30 ft building heights, but this is not eave height.

### Cited Findings
- Fields include STRUCTURE (coded; 110 = Single Family Home, 121 = Twin Home, and so on), UNITS, NUMBERSTORIES, GROUNDELEVATION, BUILDINGTOPELEVATION, OCCUPIEDDATE, STATUS, OWNEDBY, CAPTUREMETH and Shape.STArea(). The CAPTUREMETH domain includes "Consultant Deliverable" (all four test houses), "Aerial Photo Digitized", "CAD Drawing" and others — [Footprints layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5?f=json)
- Description: "Authoritative building footprint polygons… derived by consultants on a 2-4 year cycle, with additional footprints being added by City staff in between acquisitions based on building site plans or other reference information." The metadata gives no units or datum for the elevation fields, only labels/aliases. The ISO metadata's verticalCRS is "other:see_referenceSystemInfo", which has no vertical CRS — [Footprints layer JSON](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5?f=json); [Footprints metadata](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5/metadata?format=default&f=xml)
- For all STRUCTURE = 110 footprints: count 47,415, GROUNDELEVATION range 1302.05–1566.44, BUILDINGTOPELEVATION range 1329.20–1592.50 — [Footprints query (outStatistics)](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5/query)
- Ground elevation compared with the USGS Elevation Point Query Service (3DEP 1 m, feet, at each footprint's vertex-mean centroid):
  - 235245: 1484.40 vs 1484.42
  - 235246: 1515.32 vs 1516.20
  - 235247: 1519.25 vs 1519.22
  - 235248: 1520.27 vs 1520.44
  — [USGS EPQS](https://epqs.nationalmap.gov/v1/json?x=-96.74243635172236&y=43.480905090381256&units=Feet&wkid=4326&includeDate=false) (other three points queried the same way)
- The city Benchmark layer (Community layer 67) stores a `NAVD88ELEV` field, so the city's survey control is NAVD88 — [Benchmark layer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/67?f=json)
- Top elevation vs wireframe maximum Z: 1504.30 vs 1504.03; 1535.40 vs 1534.90; 1549.46 vs 1549.55; 1542.60 vs 1541.55 — [footprint query](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5/query); [wireframe query](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66/query)

### Inferences
- Units are US feet, and the vertical datum is almost certainly NAVD88: the 3DEP agreement is sub-foot, and the city's benchmarks are NAVD88.
- BUILDINGTOPELEVATION is a highest-point value, matching the top ridge on these four homes. It may come from the same 2023 model or from a different epoch, since the footprint metadata is dated 2026-10-07. It could be a chimney top on other houses. Top minus ground gives overall height (19.9, 20.1, 30.2 and 22.3 ft here). Pitch cannot come from the footprint layer alone, because it holds no eave elevation. You need the wireframe for that.
- Footprint area equals the wireframe roof plan area, which supports reading the footprints as roof outlines including overhang.

### Gaps
- The city does not document the datum or units for these fields. Confirmation would need the city GIS office.

## 6. Newest city orthoimagery: year, resolution, access

### Takeaway
The newest city imagery is "2026 Imagery": 6-inch Nearmap imagery published by the city on 2026-11-06 as an ArcGIS Online tile layer. Year layers exist for 2016 through 2026, with older layers going back to 1998. It is tiles-only (`exportTilesAllowed: false`). The Nearmap license forbids download and forbids display at scales larger than 1:564, and the cache stops at level 20 (level 21 returns 404). The city's own gis.siouxfalls.gov server has no public imagery service. A DataWorks "Imagery" item links to a city OneDrive "Open Data/Imagery" folder marked CC BY 4.0, but it returned HTTP 401 to a non-browser request, so its contents are unverified.

### Cited Findings
- "2026 Imagery" item 028eceb03d874679a319960bf2605ca0, created 2026-11-06, public: "Tile layer containing authoritative tiled 6" Nearmap imagery from 2026 for Sioux Falls, South Dakota." Credits: "City of Sioux Falls, Nearmap" — [ArcGIS item](https://www.arcgis.com/home/item.html?id=028eceb03d874679a319960bf2605ca0)
- License on the 2026 and 2025 items: "This public facing imagery has licensing restrictions from Nearmap. The imagery cannot be made available at a scale < 1:564 (6"). The imagery cannot be made available for download." — [2026 item](https://www.arcgis.com/home/item.html?id=028eceb03d874679a319960bf2605ca0); [2025 item](https://www.arcgis.com/home/item.html?id=affc8ce87b684eb1acb7e3ce8f97d286)
- Tile service `NearmapPublicFacingTilePackage2026/MapServer`: `capabilities: "Map,TilesOnly,Tilemap"`, `exportTilesAllowed: false`, Web Mercator (3857), PNG tiles. The deepest listed LODs are 20 (0.149 m, 1:564), 21, 22 and 23. In practice a level-20 tile returned 200 and a level-21 tile returned 404 near 43.492 N, 96.790 W — [2026 tile service](https://tiles.arcgis.com/tiles/YpECgwASS4iMvgsA/arcgis/rest/services/NearmapPublicFacingTilePackage2026/MapServer?f=json)
- Other year layers by the same owner: 2016–2020 (`NearmapTilePackage20xx`), 2021, 2022, 2025 and 2026 (`NearmapPublicFacingTilePackage20xx`), 2023 and 2024 (`2023_Imagery`, `2024_Imagery`), plus 2014, 2012, 2008, 2004, 2002 and 1998. There is also a "City of Sioux Falls Historic Imagery Viewer" web app — [ArcGIS Online search, owner cityofsiouxfallsgis](https://www.arcgis.com/sharing/rest/search?q=owner%3Acityofsiouxfallsgis%20imagery&f=json); [Historic Imagery Viewer](https://experience.arcgis.com/experience/e0435da0d5ac427eb8ff13c3121306e2)
- The DataWorks "Imagery" Document Link (fc1859a2…) is described as "Link to Imagery of Sioux Falls, South Dakota" and marked CC BY 4.0 International. It points to a SharePoint/OneDrive folder; a curl request was redirected to `…/Documents/Open Data/Imagery` with HTTP 401 — [ArcGIS item](https://www.arcgis.com/home/item.html?id=fc1859a2592145418ab51025d55ab872)
- The gis.siouxfalls.gov REST server exposes no imagery, ortho, ImageServer or WMS service publicly. Only the token-protected "Basemaps" folder is a candidate — [REST root](https://gis.siouxfalls.gov/arcgis/rest/services?f=json)

### Inferences
- The newest imagery (2026, 6 in) can be viewed for free, but the license makes it view-only, so it is not usable as a downloadable measurement base. At level 20, a Web Mercator pixel at 43.5° N covers about 0.108 m (about 4.3 in) of ground, but the source is 6 in. That is enough to check roof shape, dormers and changes since June 2023, but not for photogrammetric pitch measurement.
- The OneDrive "Open Data/Imagery" folder may hold older, city-owned, downloadable orthos, since it carries the CC BY tag and Nearmap years are explicitly non-downloadable. This needs a browser check.

### Gaps
- Exact 2026 Nearmap capture date (month) not stated in the item or the service.
- Contents of the OneDrive imagery folder unverified (HTTP 401 to curl; browser access not attempted per constraints).
- I did not check county (Minnehaha or Lincoln) or state imagery services.
