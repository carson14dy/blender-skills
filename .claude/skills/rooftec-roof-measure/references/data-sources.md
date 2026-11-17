# Data sources

Use the four city layers and the one lidar collection below. Everything here was checked against the live services on 2026-11-16 unless a line says "unverified".

## Rules for calling the services

1. Ask for one house per request, and never more than 5 records (the footprint search around a point asks for up to 25 outlines, and the permit lookup for up to 25 permits).
2. Wait at least 1 second between requests to the city host. The client does this.
3. Cache every answer and reuse it forever. A repeat run of a measured house makes 0 requests.
4. Never pull the whole city. Ask the city GIS office (cityofsfgis@siouxfalls.gov) for a file instead.
5. Send a User-Agent that names the tool and nothing personal: `rooftec-roof-measure/0.1 (roof measurement skill; python-urllib)`.

## City of Sioux Falls ArcGIS REST

Base: `https://gis.siouxfalls.gov/arcgis/rest/services/Data`. All layers use EPSG 32164 (NAD83, BLM zone 14N, US survey feet), allow 1,000 records per query and support paging. Licence: CC BY 4.0, "not intended for use in mapping products for resale". Each layer states this in its own metadata at `<layer url>/metadata?f=xml` (read on 2026-11-16; `references/licenses.md` quotes it). The `format=default` form of that address is switched off, which is why review round 1 could not find the text.

### Address points: `Property/MapServer/0`

- Query by `ADDRESS`, which holds upper-case USPS-style text such as `224 W 9TH ST`. The tool tries an exact match first and then `ADDRESS LIKE '<text>%'`.
- Other verified fields: `HOUSENUM`, `PR1` (prefix direction), `STNM1`, `TYP1`, `PD1`, `LON`, `LAT`, `STATUS` (`Current`), `YEARBUILT` (a string, often empty), `POINTTYPE` (`Building` or `Parcel`), `ADDRCLASS`, `MUNICIPALITY`, `ZIPCODE`, `ALIAS`.
- A `Building` point sits on the house. A `Parcel` point can sit 50 to 120 ft from any building, so the tool takes the nearest footprint within 100 ft and raises the `point-off-building` flag.
- The `LON` and `LAT` fields differ by about 1.2 m (4 ft) from a plain conversion of the point's own coordinates. The tool uses the point geometry, so this does not matter.
- Unverified: whether the city's `AddressLocators` geocoder is public. The tool does not use it.

### Building footprints: `Property/MapServer/5`

- `objectIds=<id>&outFields=*&returnGeometry=true&outSR=32164&f=json` returns one outline.
- Verified fields: `STRUCTURE` (110 single family, 121 twin home, 190 accessory structure, 220 multi-family, and more), `NUMBERSTORIES`, `GROUNDELEVATION`, `BUILDINGTOPELEVATION`, `OCCUPIEDDATE`, `STATUS`, `CAPTUREMETH`, `Shape.STArea()` in square feet.
- The two elevations are feet and agree with NAVD88 to under 1 ft on four houses. The city does not document the datum, so treat NAVD88 as inferred.
- The outline is the roof edge including overhang, not the wall line. Lidar confirms this to about 0.1 m (4 in) on 38 houses, which is as fine as lidar can see (`references/validation.md`). The tool uses `GROUNDELEVATION` as z = 0.
- `GROUNDELEVATION` is one height per building. It matches the lidar ground within 0.15 m on level lots and differs by up to 1.1 m on sloping lots.

### 3D building solids ("Building Wireframe"): `Community/MapServer/66`

The layer holds 95,901 solids captured in June 2023. Each building is one closed solid with no roof or wall labels and no pitch field.

**How to query it**

- Use the footprint's bounding box: `geometry=<xmin,ymin,xmax,ymax>&geometryType=esriGeometryEnvelope&inSR=32164&returnZ=true&f=json`. The tool shrinks the box by 1 ft and keeps the solid whose box overlaps the footprint best. `objectIds=<id>` also works.
- Ask for `f=json` only; `f=geojson` fails on this layer.
- Expect about 3 KB per house. The geometry is `binaryPatches`: base64 of a 12-byte header (shape type `0x80800036`, uncompressed length, compressed length) and a zlib stream that inflates to a standard Esri multipatch shape buffer. `scripts/roofmeasure/esri.py` documents the layout.

**What the decoder must handle**

- Rings repeat their first vertex several times.
- Face winding is not consistent, so "up" cannot be read from the vertex order.
- Some solids hold extra faces under the roof, such as a cap polygon at eave level or the floor of a penthouse. The tool keeps only the top surface.
- The solid's flat base sits 2 to 8 ft below ground, so it is not the ground level.

### Building permits: `Community/MapServer/3`

- One point per permit since September 2014. The point is the city address point of the building, and that point lies on the footprint (review round 3: every permit on 30 houses, address point on the footprint on 8 of 8). Fields: `MAINADDRESS`, `PERMITNUMBER`, `PERMITTYPE`, `WORKCLASS`, `ISSUEDATE`, `FINALIZEDATE`, `PERMITSTATUS`.
- The tool asks for the permits inside the footprint's bounding box whose `WORKCLASS` is `Addition`, `Razing`, `Demolition`, `Relocated Structure`, `Reshingle`, `Repair`, `Remodel/Renovation` or starts with `New`, newest first, 25 at most, and keeps those whose point lies on the footprint. That is one small request per house, cached as `raw/permits.json`. Permits keep coming, so this one answer is asked again when it is older than 30 days; every other city answer is kept for ever.
- An `Addition`, `Razing`, `Demolition`, `Relocated Structure` or `New ...` permit issued on or after 1 January 2023 raises the `permit-since-capture` site check: the work was probably not finished when the solid was captured in June 2023. The city issued 350 residential `Addition` permits between June 2023 and November 2026.
- `checks.permits.lastReshingle` gives the date of the newest reshingle permit. It is context for the roofer and changes no number.
- `Repair` and `Remodel/Renovation` permits since 2023 raise only the `permit-other` info flag. The city issued about 7,100 of them for houses since January 2023 and 5 of 30 random houses have one; most do not touch the roof line. `New` matches new houses, town homes and duplexes only; sheds and accessory buildings have work classes of their own and are ignored.

## USGS 3DEP lidar

Collection `SD_EasternSD_3_2020` is public domain. The 3DEP index lists it as quality level 2, collected from 2020-04-10 to 2020-12-22, with heights in NAVD88 (GEOID18). The points over the benchmark houses were all flown on 19 and 20 December 2020 (read from their GPS times). The roofs were bare on those days: the Sioux Falls airport station (GHCN `USW00014944`) recorded no snowfall and zero snow depth from 15 November to 22 December 2020. No newer 3DEP lidar covers the city (checked 2026-11-16). The public Entwine Point Tile (EPT) root is `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/SD_EasternSD_3_2020/ept.json`.

**How the tool reads it**

- The EPT is in EPSG 3857 (Web Mercator) with heights in metres. Lengths in 3857 are stretched by about 38% at this latitude, so the tool converts every point to EPSG 32164 before it fits anything. The conversion is in `scripts/roofmeasure/proj.py` and matches PROJ to under 0.01 ft.
- The tool walks the octree for the footprint box plus 4 m, starting at depth 6. One house needs 6 to 12 LAZ nodes, about 2 to 3 MB, read with `laspy` and `lazrs`.
- Nodes are cached in `<out>/_ept/` and shared between neighbouring houses. The clipped points for each house are saved in its `raw/` folder, with the number of returns of each point's pulse (`nr`). A pulse through branches gives several returns and a pulse on a roof gives one, which is how the tool tells a tree from a dormer. Point files saved before review round 3 hold no `nr`; delete `raw/lidar_points.npz` to rebuild one from the cached nodes.

**What was measured on the test houses**

- Only classes 1 (unclassified) and 2 (ground) are present. There is no building class, so roof points are picked by height (more than 2 m above ground) and by the city roof outline.
- Roof density was 4.2 to 7.4 points per square metre of plan area on a single flight line and 11.5 to 14.4 where two lines overlap. The nominal figure for this quality level is 2.
- The laser spot is 0.5 to 1 m wide (the strength of a roof return fades over about 0.9 m across a rake). Returns within that distance of a roof edge, ridge or valley mix two surfaces, so the tool fits planes to points at least 0.6 m inside each plane where it can.
- The lidar roof sits 0.09 to 0.24 m from the city solid horizontally and 0.11 to 0.14 m above it (four houses). No datum correction is applied, and none is needed at that size.

## Sources this skill does not use

- NAIP 2025 aerial photos (0.3 m, flown 28 July 2025, on Microsoft Planetary Computer, STAC collection `naip`) are free and newer than the solid. Review round 3 tried them for the outline: roofs are shifted 0.3 to 1.5 m against the city outline because the photo is not a true orthophoto, so they cannot place an eave. They do show trees, and they could show an addition that has no permit. Not used by the tool.
- City imagery layers for 2025 and 2026 are Nearmap tiles that may be viewed and never downloaded.
- Google Solar API, Google 3D Tiles, Nearmap, EagleView and Hover cost money or need a billing account.
- OpenStreetMap and Overture buildings carry a share-alike database licence; keep them out of our files.
