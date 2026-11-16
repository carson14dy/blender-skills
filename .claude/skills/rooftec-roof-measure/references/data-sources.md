# Data sources

Use the three city layers and the one lidar collection below. Everything here was checked against the live services on 2026-11-16 unless a line says "unverified".

## Rules for calling the services

1. Ask for one house per request, and never more than 5 records (the footprint search around a point asks for up to 25 outlines).
2. Wait at least 1 second between requests to the city host. The client does this.
3. Cache every answer and reuse it forever. A repeat run of a measured house makes 0 requests.
4. Never pull the whole city. Ask the city GIS office (cityofsfgis@siouxfalls.gov) for a file instead.
5. Send a User-Agent that names the tool and nothing personal: `rooftec-roof-measure/0.1 (roof measurement skill; python-urllib)`.

## City of Sioux Falls ArcGIS REST

Base: `https://gis.siouxfalls.gov/arcgis/rest/services/Data`. All three layers use EPSG 32164 (NAD83, BLM zone 14N, US survey feet), allow 1,000 records per query and support paging. Licence: CC BY 4.0, "not intended for use in mapping products for resale".

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
- The outline is the roof edge including overhang, not the wall line. The tool uses `GROUNDELEVATION` as z = 0.

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

## USGS 3DEP lidar

Collection `SD_EasternSD_3_2020` was flown in 2020 and is public domain. The public Entwine Point Tile (EPT) root is `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/SD_EasternSD_3_2020/ept.json`.

**How the tool reads it**

- The EPT is in EPSG 3857 (Web Mercator) with heights in metres. Lengths in 3857 are stretched by about 38% at this latitude, so the tool converts every point to EPSG 32164 before it fits anything. The conversion is in `scripts/roofmeasure/proj.py` and matches PROJ to under 0.01 ft.
- The tool walks the octree for the footprint box plus 4 m, starting at depth 6. One house needs 6 to 12 LAZ nodes, about 2 to 3 MB, read with `laspy` and `lazrs`.
- Nodes are cached in `<out>/_ept/` and shared between neighbouring houses. The clipped points for each house are saved in its `raw/` folder.

**What was measured on the test houses**

- Only classes 1 (unclassified) and 2 (ground) are present. There is no building class, so roof points are picked by height (more than 2 m above ground) and by the city roof outline.
- Roof density was 4 to 5 points per square metre, about twice the nominal figure for this quality level.
- The lidar roof sits 0.09 to 0.24 m from the city solid horizontally and 0.11 to 0.14 m above it (four houses). No datum correction is applied, and none is needed at that size.

## Sources this skill does not use

- City imagery layers for 2025 and 2026 are Nearmap tiles that may be viewed and never downloaded.
- Google Solar API, Google 3D Tiles, Nearmap, EagleView and Hover cost money or need a billing account.
- OpenStreetMap and Overture buildings carry a share-alike database licence; keep them out of our files.
