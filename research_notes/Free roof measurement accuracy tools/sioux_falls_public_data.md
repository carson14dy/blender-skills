# Free ($0) public geospatial data for measuring residential roofs in Sioux Falls, SD (Minnehaha and Lincoln counties)

Research date: 2026-11-16. Most facts below were checked live against the publisher's own REST service, S3 bucket or file (queries by point at downtown -96.73,43.55; south side in Lincoln Co. -96.75,43.47; northwest -96.82,43.60). Where a fact comes only from a search-engine summary or from memory, it is flagged.

**Headline finding:** the best free source for this job is not USGS. It is the **City of Sioux Falls' own GIS**, published under **CC BY 4.0** (commercial use allowed with attribution). It includes (a) about 100k authoritative building footprints with **ground elevation and building top elevation** per building, (b) a **3D Building Wireframe (multipatch) layer acquired June 2023** (95,901 features), (c) 1-ft contours from Sanborn (April 2023), and (d) address points with year built and construction type. USGS 3DEP QL2 lidar from 2020 (SD_EasternSD_3_2020) covers both counties and gives an independent point cloud for pitch checks.

## 1. USGS 3DEP lidar covering Sioux Falls

### Takeaway
Sioux Falls (both the Minnehaha and Lincoln county parts) is covered by **SD_EasternSD_3_2020** (project SD_EasternSD_2020_B20). It is **QL2, Lidar Base Spec 2.1, collected 2020-04-10 to 2020-12-22**, measured RMSEz about 4 cm, and free as LAZ, 1 m DEM and EPT. It has **no building class**, so roof points sit in class 1 (Unclassified) and you have to segment them yourself. The older 2008 county lidar (Minnehaha and Lincoln) does not meet 3DEP specs. I found no newer state lidar. The city's own 2023 Sanborn acquisition (see section 5) is newer, but its point cloud is not published.

### Cited Findings
- The 3DEP index (layer 24 "Lidar Point Cloud") returns two work units at all three Sioux Falls test points: **SD_EasternSD_3_2020** (project SD_EasternSD_2020_B20; ql "QL 2"; spec "USGS Lidar Base Specification 2.1"; linear-mode lidar; collect 2020-04-10 to 2020-12-22; LPC published 2022-04-13; horizontal EPSG 6343 = NAD83(2011) UTM 14N; vertical EPSG 5703 = NAVD88 m; LPC category "Meets"; 1 m DEM category "Meets") and the legacy **SD_MINNEHAHACO_2008** / **SD_LINCOLNCO_2008** (collected 2008-05-13 to 05-23; QL "Other"; DEM GSD 3 m; LPC category "Does not meet"; published 2012-09-14) — [USGS 3DEP Elevation Index MapServer, layer 24](https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer/24)
- Download links returned by the index:
  - LAZ tiles: https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/SD_EasternSD_2020_B20/SD_EasternSD_3_2020
  - Source DEM: https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/OPR/Projects/SD_EasternSD_2020_B20/SD_EasternSD_3_2020
  - Metadata: https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/metadata/SD_EasternSD_2020_B20/SD_EasternSD_3_2020
  - Source: [3DEP index](https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer/24)
- The 1 m DEM GeoTIFFs are staged at `StagedProducts/Elevation/1m/Projects/SD_EasternSD_2020_B20/TIFF/` (for example `USGS_1M_14_x52y501_SD_EasternSD_2020_B20.tif`), with a `0_file_download_links.txt` index file — [prd-tnm S3 listing](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/1m/Projects/SD_EasternSD_2020_B20/)
- LPC QA report for work unit 3: 6,803 LAS 1.4 files, point record format 6, sensor "ALS80" (Leica), scan angle ±16°, GPS time Apr 10–Dec 22 2020. **Classes present: 1 Unclassified, 2 Ground, 7 Low Noise, 9 Water, 17 Bridge Deck, 18 High Noise, 20 Ignored Ground. There is no class 6 (Building).** — [USGS_SD_EasternSD_3_2020_FINAL_LPC_Report.txt](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/SD_EasternSD_2020_B20/SD_EasternSD_3_2020/reports/USGS_SD_EasternSD_3_2020_FINAL_LPC_Report.txt)
- The USGS NGTOC validation report (2022-03-07) says the work unit is "EXPECTED TO MEET 3D Elevation Program requirements", with QL2, LBS 2.1, Geoid18, and data "produced to meet 9.8 cm absolute vertical accuracy at the 95-percent confidence level in non-vegetated, open terrain". It notes "Classifications beyond the minimum are not verified by USGS" — [Summary Report PDF](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/SD_EasternSD_2020_B20/SD_EasternSD_3_2020/reports/USGS_SD_EasternSD_3_2020_Summary_Report.pdf)
- Project accuracy report (labelled "Block 1"):
  - Swath NVA: RMSEz 3.9 cm, NVA 6.2 cm at 95%.
  - Classified LPC: RMSEz 3.6 cm, NVA 7.1 cm, VVA 13.7 cm.
  - Derived DEM: RMSEz 4.2 cm, NVA 8.3 cm, VVA 13.9 cm.
  - Spec limits: RMSEz ≤10 cm, NVA ≤19.6 cm, VVA ≤29.4 cm, swath-overlap RMSDz ≤8 cm (max ±16 cm).
  - Source: [USGS_SD_EasternSD_Block1_Project_Accuracy_Report.pdf](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/SD_EasternSD_2020_B20/vertical_accuracy/accuracy_report/USGS_SD_EasternSD_Block1_Project_Accuracy_Report.pdf)
- Relative-accuracy shapefiles (smooth-surface repeatability and swath overlap) exist for each work unit, including `SD_EasternSD_3_Lidar_Relative_Accuracy_*` — [S3 listing](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/metadata/SD_EasternSD_2020_B20/vertical_accuracy/accuracy_report/relative_accuracy/)
- Entwine Point Tiles (EPT, streamable with PDAL or Potree) are on AWS Open Data with no account needed: `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/SD_EasternSD_3_2020/ept.json`. It holds 42,653,365,611 points, stored as LAZ in EPSG:3857, with dimensions including Classification, ReturnNumber, NumberOfReturns, ScanAngleRank, GpsTime, ScanChannel and ClassFlags (no RGB) — [ept.json](https://s3-us-west-2.amazonaws.com/usgs-lidar-public/SD_EasternSD_3_2020/ept.json)
- The Entwine resource list also has `SD_MinnehahaCo_2008` (2.39 billion points) and `SD_LincolnCo_2008` (1.93 billion points) — [hobuinc/usgs-lidar resources.geojson](https://raw.githubusercontent.com/hobuinc/usgs-lidar/master/boundaries/resources.geojson)
- QL2 under the USGS Lidar Base Specification means aggregate nominal pulse density ≥2 pts/m² (nominal pulse spacing ≤0.71 m) and RMSEz ≤10 cm — [USGS Lidar Base Specification](https://www.usgs.gov/ngp-standards-and-specifications/lidar-base-specification-online) (not re-fetched this session; these are standard LBS values)
- Roof-accuracy literature: Sánchez-Aparicio et al. (2020) compared 0.5, 1, 2 and 14 pts/m² lidar for roof area on residential and industrial buildings. They found that 0.5 pts/m² gives significant area errors, 1–2 pts/m² gives "a great improvement… with no significant difference among them", and 14 pts/m² improves results further but not in proportion to the extra density. Behaviour differed for roofs below and above 200 m² — [Remote Sensing 12(22):3726, doi:10.3390/rs12223726](https://www.mdpi.com/2072-4292/12/22/3726/htm) (abstract checked via [Crossref](https://api.crossref.org/works/10.3390/rs12223726))
- A search summary of a 2026 CaGIS abstract reports 3DEP-derived building heights against reference data in a suburban site with R² = 0.87, MAE 1.8 m and RMSE 2.4 m, with lower agreement for complex Houston roofs — [Liu et al., CaGIS 2026 abstract](https://cartogis.org/docs/conferences/CaGIS_2026/abstracts/research/Liu_et_al_research_abstract_CaGIS_2026.pdf) (not opened directly; the numbers come from the search snippet)
- The same search summary attributed to an ISPRS paper the statement that a 2 m grid cannot capture dormers and chimneys on residential roofs — [ISPRS Archives XXXII-3-W14 p137](https://www.isprs.org/proceedings/XXXII/3-W14/pdf/p137.pdf) (snippet only)

### Inferences
- At 2 or more pts/m², a typical 40–60 m²-footprint plane of a 2,000 ft² house gets roughly 80–200 or more points per plane, counting the flight-line overlap typical of QL2 collections. Fitting a plane to that many points should give pitch within about ±1–2° (roughly ±0.25–0.5 in/12) on main planes, because per-point vertical noise (σ ≈ 4 cm) averages down over a plane several metres across. This is my estimate, not a measured value. Small dormers, crickets and planes under about 10 m² will be poorly sampled.
- Area from lidar alone is limited by edge location: with about 0.7 m point spacing, eave and rake lines are uncertain by about ±0.35 m. On a 15 m × 12 m footprint that is roughly ±5–8% of plan area. The better method is to use lidar for **pitch** and the city footprint polygon (or a manual eave line) for **plan outline**, then compute sloped area = plan area / cos(pitch). This is consistent with Sánchez-Aparicio et al. finding slope and orientation more robust than area.
- Because there is no building class, isolate roof points by clipping class 1 points to a footprint polygon, then filtering to points above the ground plus about 2 m, and run RANSAC or region-growing plane fitting. PDAL `filters.crop` with `filters.hag_delaunay` (height above ground) does this directly from the EPT URL.
- Data are 6 years old (2020). Re-roofs don't change geometry, but additions and new subdivisions built since 2020 (Sioux Falls is growing fast on its south and east edges) won't appear.
- License: USGS 3DEP data are U.S. Government public domain, so they can be used commercially. That is the standard USGS policy, not something re-fetched this session.

### Gaps
- The accuracy PDF is titled "Block 1" but sits in the project-level folder. I could not confirm which numbers apply specifically to work unit 3 (Sioux Falls).
- I did not find the stated aggregate nominal pulse density or spacing (ANPD/ANPS) for this work unit; the accuracy PDF mentions ANPS without a value in the extracted text. The FGDC XML metadata in `spatial_metadata/` or the LAS files would answer it.
- I did not check South Dakota state (BIT/DANR) or Minnehaha County for any lidar newer than 2020. The WESM index shows nothing newer than 2020 at these points.
- I found no peer-reviewed study that directly measures roof **pitch** error from QL2 3DEP on U.S. houses.

## 2. Aerial imagery

### Takeaway
**NAIP 2025 is 0.3 m (about 12 in) for South Dakota**, collected 2025-07-28 at Sioux Falls (leaf-on), and it is free through Microsoft Planetary Computer. Earlier NAIP years (2016–2022) are 0.6 m. The City of Sioux Falls publishes its own orthos under CC BY 4.0, distributed through a SharePoint folder linked from DataWorks. Third-party catalogs list 6-inch (2004, 2008) and 1-foot (2016, 2018, 2020) years. I did not verify the newest city year or confirm direct downloads. I found no free oblique imagery: the city uses Nearmap, which is paid.

### Cited Findings
- Planetary Computer NAIP STAC items at Sioux Falls (quarter-quad m_4309627_sw):

  | Date | GSD |
  |---|---|
  | 2025-07-28 | 0.3 m |
  | 2022-08-30 | 0.6 m |
  | 2021-08-21 | 0.6 m |
  | 2020-09-05 | 0.6 m |
  | 2018-08-25 | 0.6 m |
  | 2016-09-11 | 0.6 m |
  | 2014 | 1.0 m |
  | 2012 | 1.0 m |

  The collection's STAC `license` field reads "proprietary" (this is a STAC placeholder; NAIP itself is USDA public domain, see Inferences). Source: [Planetary Computer STAC API, collection naip](https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip)
- Access: STAC search at `https://planetarycomputer.microsoft.com/api/stac/v1/search` (collection `naip`). Assets are Cloud-Optimized GeoTIFFs (4-band RGBN) and need a free, anonymous SAS token from the Planetary Computer token endpoint; no account is required for reading — [Planetary Computer NAIP](https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip)
- The City of Sioux Falls DataWorks "Imagery" item links to a SharePoint folder (`siouxfalls-my.sharepoint.com/.../cityofsfgis_siouxfalls_gov/...`). The license text reads "The City of Sioux Falls provides open data licensed under the Creative Commons Attribution 4.0…" — [DataWorks Hub search API](https://dataworks.siouxfalls.gov/api/search/v1/collections/all/items?q=imagery); [DataWorks Imagery item](https://dataworks.siouxfalls.gov/documents/cityofsfgis::imagery)
- City historic imagery viewer (view only): [Experience Builder app](https://experience.arcgis.com/experience/e0435da0d5ac427eb8ff13c3121306e2) — [DataWorks](https://dataworks.siouxfalls.gov/apps/cityofsfgis::city-of-sioux-falls-historic-imagery-viewer)
- Third-party catalog (AmeriGEOSS) mirrors of city imagery list:
  - 2008: 6-inch colour, flown 2008-04-28 (spring, leaf-off), CC BY 4.0
  - 2004: 6-inch spring
  - 2016, 2018, 2020: 1-foot August
  - Sources: [2008 Imagery](https://data.amerigeoss.org/dataset/2008-imagery-a7da1), [2016 Imagery](https://data.amerigeoss.org/dataset/2016-imagery-1902e), [2020 Imagery](https://data.amerigeoss.org/dataset/2020-imagery-250de) (via search summary; the pages were not opened)
- The city's address points carry `PHOTOARCHIVELINK` and `PHOTOACQUISITIONYEAR` fields, which suggests per-address photo archives — [City Property MapServer layer 0 (Address)](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/0)
- Nearmap has a customer story on Sioux Falls, which indicates the city subscribes to Nearmap (commercial) — [Nearmap customer story](https://cf.nmws.nearmap.com/customer-stories/detailed-aerial-maps-in-sioux-falls)

### Inferences
- NAIP is USDA FSA imagery and public domain (standard USDA policy), so commercial use is fine. At 0.3 m (2025) it is good enough to trace eaves to about ±0.3–0.5 m and to check roof shape and changes since the 2020 lidar. It is leaf-on, so trees hide some eaves.
- The city's April 2023 Sanborn contours and June 2023 wireframes (section 5) strongly suggest a 2023 Sanborn aerial and lidar acquisition. The matching 2023 orthoimagery (likely 3–6 in) may be in the SharePoint folder, but this is unverified.
- No free oblique imagery source was found. Google Street View and Nearmap obliques are not free for this use (see section 6).

### Gaps
- I could not list the SharePoint folder's contents (it needs a browser and may need a login), so the newest city ortho year, resolution, format and whether it can actually be downloaded are unverified.
- I found no Minnehaha or Lincoln County ortho WMS endpoints; the county GIS hostnames returned proxy 502 errors.
- South Dakota statewide imagery programs were not checked.

## 3. Building footprints

### Takeaway
Use the **City of Sioux Falls Building Footprints**: authoritative, consultant-captured on a 2–4 year cycle, about 100k polygons, with ground and roof-top elevation and number of stories, under CC BY 4.0. Microsoft footprints (now CDLA-Permissive-2.0), Overture (ODbL, share-alike) and FEMA USA Structures (ORNL, imagery dated May 2025) are fallbacks for areas outside city limits.

### Cited Findings
- **City Building Footprints**:
  - Service: `https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5`. Polygon layer, 100,346 features. Queryable as JSON, GeoJSON or PBF with maxRecordCount 1000, so page through it.
  - Description: "Authoritative building footprint polygons for Sioux Falls, SD. Footprints are derived by consultants on a 2-4 year cycle, with additional footprints being added by City staff in between acquisitions…"
  - Fields: STRUCTURE (use code), UNITS, NUMBERSTORIES, **GROUNDELEVATION, BUILDINGTOPELEVATION**, OCCUPIEDDATE, STATUS, CAPTUREMETH, Shape area and length.
  - Example single-family record (STRUCTURE 110, 2 stories): GROUNDELEVATION 1440.52, BUILDINGTOPELEVATION 1461.60, area 2001.3, CAPTUREMETH "Consultant Deliverable".
  - Source: [City Property MapServer/5](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5)
- City Structures points (layer 3, 80,947 features): footprint centroids with structure code, housing units and final inspection date — [MapServer/3](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/3)
- City service terms: "reference purposes only… does not guarantee accuracy… intended for broad planning purposes only." The DataWorks license is CC BY 4.0 — [Property MapServer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer); [DataWorks](https://dataworks.siouxfalls.gov/api/search/v1/collections/all/items?q=imagery)
- **Microsoft GlobalMLBuildingFootprints**: "1.4B buildings from Bing Maps imagery between 2014 and 2024… freely available for download and use under **CDLA Permissive 2.0**". The 2026-08-13 global refresh is indexed by `https://bfppub.blob.core.windows.net/%24web/2026-08-13/dataset-links.csv`. Several 2026 updates added U.S. footprints plus height estimates from Vexcel imagery dated 2021–2025 — [GitHub README](https://github.com/microsoft/GlobalMLBuildingFootprints)
- **Overture buildings**: the theme is published under **ODbL** because it includes OSM. It conflates OSM, ML-derived sources and others, merges height attributes between matches, and requires a footprint area >10 m² for ML-derived sources — [Overture buildings guide](https://docs.overturemaps.org/guides/buildings/)
- **FEMA USA Structures**: queried at 2715 S Willow Ave (Minnehaha County). Fields include OCC_CLS "Residential", PRIM_OCC "Single Family Dwelling", SQFEET 2079.8, SOURCE "ORNL", VAL_METHOD "Manual", IMAGE_DATE 2025-05-03, PROD_DATE 2026-04-16 and **HEIGHT null**. Service: `https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/USA_Structures_View/FeatureServer/0` — [FEMA USA Structures FeatureServer](https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/USA_Structures_View/FeatureServer/0)

### Inferences
- City footprint areas appear to be in **square feet** and elevations in **feet** (NAVD88, probably SD State Plane South). A 2001-unit area for a 2-story house matches FEMA's 2,080 ft² for a neighbouring house, and 1440 is a plausible Sioux Falls elevation in feet. That gives about 21 ft from ground to top for a 2-story house, which is plausible. Confirm in the layer metadata before use.
- BUILDINGTOPELEVATION is probably the ridge or top elevation from the consultant's photogrammetry or lidar. Combined with an eave height (from lidar or from stories), it gives a rough ridge-height check: ridge rise / half-span gives pitch for simple gables.
- Footprints are usually drawn at the roof edge (drip line) in photogrammetric capture, so they approximate the roof plan outline including overhang. This is unverified; check CAPTUREMETH and the metadata.
- License flags: city CC BY 4.0 (attribution required; commercial OK); Microsoft CDLA-Permissive-2.0 (commercial OK); Overture/OSM ODbL (commercial OK but **share-alike** on derived databases); FEMA USA Structures is a federal product, generally public domain (not re-verified).
- OSM coverage in Sioux Falls could not be measured (the Overpass request failed). Overture already blends OSM with ML footprints, so it is a practical proxy.

### Gaps
- The positional accuracy of city footprints is not stated in the service description (no RMSE given); the item metadata or FGDC XML may have it.
- Microsoft's U.S. positional accuracy and precision/recall for Sioux Falls were not found.
- OSM building completeness in Sioux Falls is unmeasured.

## 4. Parcel and assessor data

### Takeaway
The city's address points are free (CC BY 4.0) and carry **YEARBUILT, OCCUPANCY and CONSTRTYPE**, and the city Parcels layer is published. Minnehaha County publishes a parcel MapServer. I did not confirm Lincoln County parcel access or roof-type or square-footage fields from either county assessor.

### Cited Findings
- City Address layer fields include TAG (Parcel ID), YEARBUILT, OCCUPANCY, CONSTRTYPE, PHOTOARCHIVELINK and PHOTOACQUISITIONYEAR — [City Property MapServer/0](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/0)
- City Property service layers: Address, Parcels, Preliminary Parcels, Structures, Building Footprints, Easements, Subdivisions, Zoning, Parcels UMA and PLSS — [Property MapServer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer)
- The city Community service has a Building Permits layer (id 3), which can flag recent re-roof or addition permits — [Community MapServer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer)
- Minnehaha County parcels service: `https://gis.minnehahacounty.gov/minnemap/rest/services/Parcels/MapServer`, plus a 12/01/2020 parcel freeze snapshot that includes City of Sioux Falls parcels — [search result for gis.minnehahacounty.gov](https://gis.minnehahacounty.gov/minnemap/rest/services/Parcels/MapServer) (endpoint returned a proxy 502 from this sandbox; not inspected)
- Third-party parcel counts: Minnehaha 72,445 (Land Records); Lincoln 32,155 (Land Records) and 31,894 (Regrid). These are commercial resellers — [Land Records Minnehaha](https://www.landrecords.us/documentation/coverage/counties/46-099-minnehaha), [Land Records Lincoln](https://www.landrecords.us/documentation/coverage/counties/46-083-lincoln)

### Inferences
- Year built is useful for sanity checks (for example, pre-1960 houses often have steeper 8–12/12 pitches; 1990s–2010s tract homes often have 5–8/12 hips). I found no field for roof type or roof area.
- The city Building Permits layer plus Structures DATE can tell you whether a house changed after the 2020 lidar or 2023 city capture.

### Gaps
- I could not inspect the Minnehaha County parcel fields (proxy 502). Whether the assessor publishes sq ft, roof type or roof material for free is unknown.
- I found no official Lincoln County, SD parcel GIS or assessor service.

## 5. Elevation products (DEM, DSM, nDSM) and city 3D data

### Takeaway
The free 3DEP 1 m bare-earth DEM exists for SD_EasternSD_2020_B20, but USGS does not distribute a DSM. Build your own DSM and nDSM from the LAZ or EPT points (first returns, or class 1 above ground) minus the DEM. Separately, the **city publishes 3D Building Wireframes (June 2023) as multipatch**. If these are roof-line wireframes from stereo photogrammetry, they are the highest-value free source for direct roof edge lengths and pitch.

### Cited Findings
- 1 m DEM tiles (IMG/GeoTIFF, 10 km × 10 km) are distributed for 3DEP 1 m projects; SD_EasternSD_2020_B20 1 m TIFFs are on S3 — [3DEP Index service description](https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer); [S3 1m listing](https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/1m/Projects/SD_EasternSD_2020_B20/)
- The 3DEP index service lists DEMs, lidar point clouds, and IfSAR DSMs (Alaska only) as distributable. No lidar DSM product is listed for the lower 48 — [3DEP Index MapServer](https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer)
- **City Building Wireframe**:
  - Service: `https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66`. Geometry type esriGeometryMultiPatch, 95,901 features. Description: "3D Building wireframes layer, acquisition date June 2023."
  - Fields: Entity ("Cell"), Level, Layer (e.g. "3101"), Elevation (e.g. 1449.70), RefName ("BUILD"), i.e. CAD-style attributes.
  - Source: [Community MapServer/66](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/66)
- City Elevation Contours: "generated by the Sanborn Map Company in April 2023… 1-foot contour interval", 136,047 features — [Community MapServer/8](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/8)
- The city Community service also lists a "Benchmark" layer (id 67), useful as vertical control — [Community MapServer](https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer)

### Inferences
- The wireframe's CAD attributes (Cell/Level/Layer/LineWt) suggest a MicroStation or DGN photogrammetric compilation by Sanborn from 2023 stereo imagery. Such compilations typically capture eaves, ridges, hips and valleys as 3D lines at roughly ±0.5 ft accuracy. This is plausible but unverified; check by querying geometry for a known house (`returnGeometry=true`, `f=json`, then read the multipatch rings). If confirmed, it gives eave/ridge/hip/valley lengths directly and pitch from the vertex Z values, which maps closely to the roof studio's planar triangles.
- MapServer multipatch query output may return only footprint-style JSON. If the 3D geometry doesn't come through, ask the city GIS office (cityofsfgis) for the file geodatabase or DGN under the same CC BY license.
- nDSM recipe: PDAL `readers.ept` → `filters.crop` (parcel or footprint buffer) → `filters.hag_delaunay` (or subtract the 1 m DEM) → keep HeightAboveGround > 2 m within the footprint → `filters.cluster` or plane segmentation. Mean roof height above ground can be compared with the city's BUILDINGTOPELEVATION − GROUNDELEVATION.
- The 2023 Sanborn 1-ft contours imply the city also holds 2023 lidar or a 2023 DEM. These are not published in the REST services seen here; a records request might be free.

### Gaps
- I did not check whether multipatch geometry downloads intact from MapServer/66, or how accurate it is.
- I did not confirm whether the city's 2023 lidar point cloud is distributable.

## 6. "Free" sources to avoid (not $0, or restrictive terms)

### Takeaway
Exclude Google Solar API, Google Photorealistic 3D Tiles, Nearmap, EagleView and Cesium ion (for Google 3D Tiles): each is either paid, needs a billing account, or has terms that forbid extracting or deriving measurements and storing them. These reasons come from prior knowledge and were not re-verified this session.

### Cited Findings
- The City of Sioux Falls uses Nearmap, a paid subscription — [Nearmap customer story](https://cf.nmws.nearmap.com/customer-stories/detailed-aerial-maps-in-sioux-falls)

### Inferences (not re-verified this session; check vendor pages)
- **Google Solar API** (buildingInsights gives roof segment pitch and azimuth): needs a Google Cloud billing account, is pay-per-request after any free monthly credit, and Google Maps Platform terms restrict caching and storing results and building derivative datasets. A business might stay within the free credit, but it is not unconditionally $0, and storing roof measurements is restricted. Pages to check: https://developers.google.com/maps/documentation/solar and https://cloud.google.com/maps-platform/terms
- **Google Photorealistic 3D Tiles**: needs a billing-enabled API key, and the terms forbid extracting or measuring geometry offline and require Google attribution. Not usable for taking measurements into Blender.
- **Cesium ion**: the free Community tier is for non-commercial/personal use; commercial use needs a paid plan. Streaming Google 3D Tiles through ion carries Google's terms.
- **Nearmap / EagleView / Hover / Pictometry**: commercial subscriptions or per-report fees.
- **Esri World Imagery basemap**: usable for viewing under Esri terms, but not licensed for derivative-measurement datasets without an Esri subscription. Treat it as visual only.
- **Regrid / ReportAll / Land Records parcels**: paid resellers of county parcel data. Use the city and county services directly.

### Gaps
- I did not fetch the current Google, Cesium or Nearmap pricing and terms pages in November 2026. Confirm before final publication.
