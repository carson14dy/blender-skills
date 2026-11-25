# Data sources

| Data | Endpoint | Key? | License / note |
|---|---|---|---|
| Geocoding (US) | geocoding.geo.census.gov `onelineaddress` | no | public domain; ±10–50 m, often on the street centreline: prefer a city address-point layer |
| Geocoding fallback | nominatim.openstreetmap.org | no | ODbL; ≤ 1 req/s |
| OSM footprints | Overpass (overpass-api.de, maps.mail.ru mirror, kumi) | no | ODbL, attribute OSM. Often unreachable from sandboxes (each mirror can cost 60 s): `pm.py fetch --no-osm` |
| Microsoft ML footprints | minedbuildings.z5.web.core.windows.net `dataset-links.csv` (zoom-9 quadkey tiles) | no | ODbL. Adds nothing next to a city footprint layer: `--no-ms` |
| LiDAR point clouds | USGS 3DEP EPT on AWS `s3-us-west-2.amazonaws.com/usgs-lidar-public/<project>/ept.json`; index `usgs.entwine.io/boundaries/resources.geojson` | no | public domain |
| LiDAR inventory (USGS WESM) | `index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer/24/query` (explicit outFields: workunit, project, collect_start, collect_end, ql, spec, horiz_crs, vert_crs, geoid, lpc_pub_date, lpc_category, lpc_link, metadata_link) | no | project name, QL and flight dates: use it, not guesswork |
| Bare-earth DEM | elevation.nationalmap.gov `3DEPElevation/ImageServer/identify` | no | public domain |
| Orthophoto (default) | server.arcgisonline.com `World_Imagery/MapServer/export` | no | Esri ToU; attribution; no bulk |
| Orthophoto (public domain) | imagery.nationalmap.gov `USGSNAIPPlus/ImageServer/exportImage` | no | 0.3–0.6 m, sometimes slow |
| Parcels | county/state ArcGIS REST layers (`…/FeatureServer/N/query`) | usually no | public record; search "<county> parcels FeatureServer"; explicit outFields only |
| Parcels nationwide (paid) | Regrid, ReportAll, county APIs | yes | pass their GeoJSON polygon in as an `outline`-type context layer |
| High-res oblique/ortho (paid) | Nearmap, EagleView, Vexcel | yes | better than satellite for tracing; still σ ≥ 0.3 m. Not used in the demo tier |
| Overture buildings | overturemaps.org (GeoParquet on S3/Azure) | no | ODbL/CDLA; needs duckdb |

Outside the US: replace 3DEP with national LiDAR (e.g. UK EA, NL AHN, DK, CH swisstopo) — load
the LAS/LAZ with laspy, convert to the local frame with `LocalFrame.from_geodetic`, and feed the
same `lidar.segment_planes`. Footprint/imagery sources work worldwide.

Always state LiDAR acquisition year and imagery provider in deliverables (`report.md` does).

## Rules for every source

* Public data only. No logins, tokens, CAPTCHA or bot walls, undocumented backends or private site APIs. A
  source that is blocked is written as "not publicly available" and left alone: never retried with a browser
  User-Agent, a cookie from a share link, or a different host name.
* Every ArcGIS query names its fields (`outFields=<list>`); `*` is refused in code. Parcel, assessor, permit and
  tree layers carry owner, taxpayer, buyer / seller and contractor fields under many names (`OWNNAME1`,
  `MRTNM1`, `NameADD`, `PropertyOwner`, `contractor_name`, `SELLERS_NAME`, `FORM_SIGNEDBY`...). Keyword filters
  miss some of them: copy the explicit lists below, and check new layers field by field.
* Never store names, mailing addresses, storm-report narratives or other free-text remarks.
* Record every endpoint used, what it returned and the query time in the job (`data/records.json`,
  `data/hazards.json`, `sources.json`).

## A new city or state: find the local sources first

National layers are the fallback, not the start. Before modelling in a new place, spend ten
minutes finding the local ones; they are usually better and all public. Then write them into a region
profile (`references/regions/<name>.json`; schema in `references/regions/README.md`, checked with
`python3 -m propmodel.regions --check FILE`) so the next house in that city needs no research:

1. **Parcels**: the state or county GIS (search "<state> cadastral" / "<county> parcels
   FeatureServer"). Query with explicit `outFields` (parcel id, legal, acres, values): never
   `outFields=*`, which brings back owner names. Query at the footprint centroid or the city address
   point, not the Census point (a street-centreline point can hit a placeholder parcel).
2. **Building record**: the assessor/CAMA service behind the parcel viewer (year, style, stories,
   basement and daylight basement, garage type and area, decks/porches with areas, fireplaces,
   siding and roof material). Use only the dwelling/building endpoints; skip any owner or
   "property summary" endpoint that returns names.
3. **LiDAR**: the state LiDAR inventory or USGS WESM (project name, flight dates, quality level) tells you
   which 3DEP EPT dataset covers the site and its real acquisition dates (pass `--year`).
   Statewide QL1 collections are often delivered with almost no class-2 (ground) points: use
   `pm.py lidar --ground-mode surface` and `build_site.py --ground filtered` (auto when < 10 %).
4. **City planimetrics**: many cities publish building, deck, driveway and sidewalk polygons
   (e.g. Ecopia) and leaf-off orthophotos on their ArcGIS server. Find out whether the building layer
   traces walls or drip edges (`--footprint-which footprint|roof_outline`; gate G2.convention checks it
   against the LiDAR). Bring the building outline in with its own `shift`; register ground-level
   features (driveways, decks on grade) with a separate shift checked against LiDAR heights.
5. **Permits**: the city's permit layer dates re-roofs and additions (explicit `outFields`; the layers
   carry contractor and owner fields).
6. **Host names**: find the city's ArcGIS host through one of its public web-app items (permit viewer,
   parcel finder), then walk `/rest/services?f=json`. Guessed host names fail.

Record every endpoint, what it returned and what not to call in the job's `sources.json`.

## Sioux Falls, SD (Minnehaha + Lincoln counties), checked 2026-11-25

About 80 % of city parcels are in Minnehaha County and 20 % in Lincoln County (the south side). The city
layers cover both counties; each county's assessor layers cover only that county. Profile:
`references/regions/sioux-falls-sd.json`.

| Data | Endpoint | Notes |
|---|---|---|
| Geocode | `gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/0` (address points: LAT, LON, TAG, YEARBUILT, CORNERLOT, COUNTY), or `.../AddressLocators/cityofsf_addresslocator/GeocodeServer` | exact address point; better than the Census geocoder. Use the `.gov` host (the `.org` alias is refused by the sandbox proxy) |
| Roof outline | `.../Data/Property/MapServer/5` Building Footprints | photogrammetric, traces the **drip edge**: `--footprint-which roof_outline --footprint-sigma 0.25`. Sits ~1 m NW of 3DEP: expect a fitted `shift.city` near (+0.55, -0.80) m (the server's NAD83 to WGS84 handling). Native SR 32164 |
| LiDAR | 3DEP EPT `SD_EasternSD_3_2020` (QL2, 100 % of the city, both counties; ~5 pts/m2 measured, 0.45 m spacing) | the only fast LiDAR path. Classes 1/2/7/9/17/18/20 only: **no building and no vegetation class**, so plane segmentation on class 1 is required. Flown Apr-May (can be leaf-on) and Oct-Dec 2020 (leaf-off): **date each site from GpsTime** (`pm.py lidar --extra-dims GpsTime`). `--year 2020` |
| LiDAR (change detection) | 3DEP EPT `SD_MinnehahaCo_2008` (north), `SD_LincolnCo_2008` (south) | ~0.9 pts/m2; additions since 2008 |
| LiDAR fallbacks | TNM API LAZ tiles (rockyweb, rate-limited 429), Planetary Computer COPC (2008 sets only) | not useful; keep the EPT cache (`PROPMODEL_CACHE`) |
| LOD2 roofs | `.../Data/Community/MapServer/66` Building Wireframe (June 2023, multipatch `binaryPatches`, `returnZ=true`, Z in ftUS NAVD88) | low-weight pitch and form check (`pm.py obs JOB import-multipatch --profile sioux-falls-sd`). Its roof edges are the footprint polygon, and it is the same source as the city's permit area: a check, never a second measurement |
| Ortho | Esri World Imagery = the city's Sanborn 2026 flight, 7.6 cm, 2026-04-21 (leaf-off) | `pm.py fetch` default (`--half 40` at 1024 px matches the GSD). Checks and roof colour only, never traced (building lean ~1 m) |
| Ortho (public domain) | USGS NAIP Plus, SD 2022-08-30, 0.6 m | fallback |
| Ortho (history) | city historic tiles `Imagery_1998` ... `Imagery_2014` on `tiles.arcgis.com` (public) | change detection only |
| City Nearmap tiles 2016-2026 | `tiles.arcgis.com/.../Nearmap*` | **now require a token (499)** and are gone from the public directory: do not use, do not ask for tokens |
| Permits | `.../Data/Community/MapServer/3` (points; issued 2015-01-02 to present; WORKCLASS `Reshingle`, `Addition`, `New SF`, `Deck`...) | starts with the 2014 permit-system launch; older permits are not in the layer. Match by point in parcel; exclude `contractor_name` |
| Impervious / paving | `.../Data/Storm/MapServer/37` (2017; SurfaceType, SurfaceUse; the street is one citywide polygon, filter `SurfaceUse='Street'`) | yard paving (`pm.py features --profile sioux-falls-sd`) |
| ROW trees | `.../Data/Trees/MapServer/10` (Height, Spread) | occlusion hints only; owner / contractor fields excluded |
| Assessor (Minnehaha) | `gis.minnehahacounty.gov/minnemap/rest/services/Equalization/HouseQuality_2024/MapServer/1` (House_desc = storeys + era, Grade), `.../Equalization/Residential_Sales/MapServer/{1,0,3}` (2025 / 2024 / 2023 sales, with assessed MRLNVC / MRBDVC / MRTOTC on 2025) | the server's firewall returns 403 to curl's default User-Agent: use python `requests` with the toolkit UA `propmodel/0.1 (property measurement toolkit)` (curl: `-A` with that string). Never a browser UA. Minnehaha parcels only (0 hits on the Lincoln side) |
| Assessor (Lincoln) | `gis.lincolncountysd.gov/arcgis/rest/services/Pro29/{Parcels,FullSales,GoodSales,BuildingPermits}/MapServer` | Lincoln has **no public style, storeys or living-area field** (RecentSales is empty): use the city footprint NUMBERSTORIES and the address-point YEARBUILT. County permits cover only parcels outside city limits; inside, the city layer is the permit source |
| Not available publicly | living area, sketch dimensions, roof material | both counties' property cards are behind a bot wall. The report says "not publicly available"; roof age comes from re-roof permits |

Explicit field lists (every field checked against the layer's `?f=json` on 2026-11-25):

```
# City of Sioux Falls  https://gis.siouxfalls.gov/arcgis/rest/services/Data/...
Property/0  Address    : OBJECTID,TAG,ADDRESS,LAT,LON,ZIPCODE,MUNICIPALITY,COUNTY,STATUS,CORNERLOT,YEARBUILT,OCCUPANCY,CONSTRTYPE,ADDRCLASS,PHOTOACQUISITIONYEAR,PHOTOARCHIVELINK
Property/1  Parcels    : OBJECTID,TAG,ADDRESS,ADDITION,ACREAGE,SQFT,LEGAL,FRONTFOOT,LANDUSE,NUMUNITS,COUNTY,COUNTYID,PARCELTYPE,ZIPCODE
            never      : OWNNAME1,OWNNAME2,OWNADDRESS,OWNCITY,OWNSTATE,OWNZIP,OWNZIP2,OWNEROCCSTATUS,FORM_SIGNEDBY,FORM_COMMENTS
Property/3  Structures : OBJECTID,TAG,STRUCTURE,UNITS,DATE
Property/5  Footprints : OBJECTID,STRUCTURE,UNITS,NUMBERSTORIES,GROUNDELEVATION,BUILDINGTOPELEVATION,OCCUPIEDDATE,STATUS,CAPTUREMETH
            never      : OWNEDBY,COMMENTS
Community/66 Wireframe : OBJECTID,Elevation,Layer   (+ returnZ=true, f=json)
Community/3  Permits   : OBJECTID,MAINADDRESS,PERMITNUMBER,PERMITTYPE,PERMITSTATUS,WORKCLASS,APPLYDATE,ISSUEDATE,FINALIZEDATE,VALUATION,DwellingUnits
            never      : contractor_name
Storm/37    Impervious : OBJECTID,SurfaceType,SurfaceUse
Trees/10    ROW trees  : OBJECTID,CommonName,Genus,Species,Height,Spread,Diameter,Condition,Lat,Lon
            never      : OwnerName,OwnerContactDate,OwnerPlan,Contractor*,Inspector,Creator,created_user

# Minnehaha County  https://gis.minnehahacounty.gov/minnemap/rest/services/...   (toolkit User-Agent)
Equalization/HouseQuality_2024/MapServer/1      : OBJECTID,TAG,COUNTYID,House_desc,Grade,Grade_desc
Equalization/House_Quality_2023_NEW/MapServer/0 : OBJECTID,TAG,COUNTYID,imp_type,grade,grade_desc,HouseType
Equalization/Residential_Sales/MapServer/1 (2025): OBJECTID,TAG,COUNTYID,CLASS,House_desc,grade_desc,CONDITION,SALE_DATE,SALE_PRICE,ASSMENT_YEAR,MRLNVC,MRBDVC,MRTOTC
Equalization/Residential_Sales/MapServer/0 (2024): OBJECTID,TAG,COUNTYID,INSTR_DATE,SELL_PRICE,Year_Built,CLASS,House_Type,Grade,Cond
Equalization/Residential_Sales/MapServer/3 (2023): OBJECTID,TAG,COUNTYID,INSTR_DATE,SELL_PRICE,Year_Built,CLASS,House_Desc,Grade,Condition
   never (any county layer): OWNNAME1,OWNNAME2,OWNADDRESS,OWNCITY,OWNSTATE,OWNZIP,OWNZIP2,OWNEROCCSTATUS,
                             MRTNM1,MRTNM2,MRTADR,MRTCTY,MRTSTATE,MRTZPC,MRTZPC2,FORM_SIGNEDBY,created_user,last_edited_user
   (MRTNM1/2 = taxpayer names and MRTADR... = taxpayer mailing address on the county parcel layers: AS400 names
    that keyword filters miss)

# Lincoln County  https://gis.lincolncountysd.gov/arcgis/rest/services/Pro29/...
Parcels/MapServer/0        : DBO.Parcel.PID,DBO.Parcel.Address,DBO.Parcel.LegalDesc,DBO.Parcel.SqFtCalc,DBO.Parcel.AcreCalc,DBO.Parcel.Subdiv,DBO.Parcel.Lot,DBO.Parcel.Block,DBO.Parcel.Zoning,DBO.GIS_Parcels.Class1,DBO.GIS_Parcels.Value1
                             never: DBO.GIS_Parcels.Name,NameADD,Add1,Add2,Add3,Zip,ReInqAddre,ReInqAddre_1
BuildingPermits/MapServer/2: OBJECTID,PID,DateApproved,Permit,ProjectType,Type,ProjDesc,ProjectCost        never: PropertyOwner
FullSales/MapServer/11     : OBJECTID,PARCEL_ID,SALE_DATE,SALE_YEAR,SALE_PRICE,FULLVALUE,PROPERTY_CLASS,PROPERTY_TYPE,PROPERTY_DESC   never: SELLERS_NAME,BUYERS_NAME
GoodSales/MapServer/5      : OBJECTID,Parcel_Number,SaleYear,Class,Detail,Acres,InstrDate,SalePrice
RecentSales/MapServer/7    : OBJECTID,PARCEL,SALE_DATE,YEAR_BUILT,BASEMENT,SQUARE_FEET,CONSTRUCTION,BEDROOMS,BATH,FIREPLACE,GARAGE_CODE,GARAGE_SIZE,GRADE   (empty on 2026-11-25)
                             never: SELLERS_NAME,BUYERS_NAME,NAME,ADDRESS_1,ADDRESS_2,ADDRESS_3,ZIP_CODE
```

Spatial query template (python `requests`, toolkit UA; the parcel polygon or a small envelope around the
house, never a city-wide owner dump):
```
GET <layer>/query?geometry=<w>,<s>,<e>,<n>&geometryType=esriGeometryEnvelope&inSR=4326
    &spatialRel=esriSpatialRelIntersects&outFields=<explicit list>&returnGeometry=true&outSR=4326&f=json
```

Blocked or off-limits in Sioux Falls. Do not work around any of them:
* county property cards (Beacon, both counties): bot-wall challenge;
* listing and real-estate sites, people-search and owner-lookup sites;
* the permit system's self-service JSON backend (undocumented; the public web UI exists, the backend is not a
  documented API);
* the city's open-data SharePoint folders (2023 city LiDAR, MrSID orthos) through SharePoint's `_api`: the
  share link opens without sign-in, but listing it needs the REST backend. Only with the user's explicit OK;
  3DEP 2020 is the default source, and `pm.py lidar` reads EPT only anyway;
* the county EagleView / Pictometry imagery (a vendor key embedded in the county web map);
* city Nearmap tile services (token required);
* hosts the sandbox refuses: `gis.siouxfalls.org`, `gis.minnehahacounty.org`, `arcgis.sd.gov`, USDA APFO NAIP,
  Esri NAIP. Use the `.gov` hosts above.

## Billings, MT (Yellowstone County), checked 2026-11-21

Profile: `references/regions/billings-mt.json`.

| Data | Endpoint | Notes |
|---|---|---|
| Parcels | state MSDI cadastral `gisservice.mt.gov/arcgis/rest/services/msdi_cadastral_map_v1/MapServer/1` | explicit fields: PARCELID, PropertyID, AssessmentCode, Subdivision, LegalDescriptionShort, PropType, GISAcres, TotalAcres, TotalBuildingValue, TotalLandValue, TaxYear, Township, Range, Section. PARCELID is the geocode the state API takes. Query at the footprint centroid (the Census point can hit a placeholder parcel) |
| Building record | Montana Cadastral API `svc.mt.gov/msl/cadastralapi` (documented, Swagger at `/swagger/v1/swagger.json`) | only `api/v1/TaxYear`, `api/Dwelling`, `api/v1/Buildings`, `api/MarketLand` (year, style, stories, basement, areas, garage, decks, porch, roof, siding). **Never** `api/v1/Properties/Summary`, `Owner` or `Search`: they return names |
| City GIS | `billingsgis.com/arcgis_public/rest/services` (found through the city's permit web app; guessed host names do not exist) | |
| Ortho | `ArcOnline_Raster/Nearmap_2025`, `Nearmap_2024`, `Billings_Nearmap_2023_Imagery` (`/MapServer/export`), 7.5 cm | public on 2026-11-21; lean 1-3.5 m from the LiDAR on steep sites, different per vintage |
| Planimetrics | `Consultant_Services/Ecopia_Impervious_Surfaces_INT/MapServer/4` (layer 5: city + county, split at parcel lines); `CateTitle` = building / deck / driveway / pavement / sidewalk / road | August 2023, from 15 cm imagery. Fit a free `shift.ecopia` (σ 0.6); LiDAR is the position truth |
| Permits | `ArcOnline_Public/BuildingPermits_CodeViolations_EXT/MapServer/0` | explicit fields: Property_Address, Permit_Type, Job_Description, Building_Permit_Num, Permit_Status, Work_Type, Issue_Date, Date_Entered, Last_Inspection_Date. The layer has Owner* and Contractor fields |
| Base map | `ArcOnline_Web_Apps/PublicWorks_BaseMap_INT/MapServer` | sidewalks, address points, roads, hydrants; no footprint or edge-of-pavement layer (Ecopia covers both) |
| County | `gis.yellowstonecountymt.gov/arcgis/rest/services` | `Aerials_2025` (NAIP ~0.3 m); parcel layers: only GEOCODE, TAX_ID, PROP_ID, SUBD, BLK, LOT, SHORTLEGAL (they also carry owner fields) |
| LiDAR | 3DEP EPT `MT_StatewideP4_3_B22` (= state project `YELLOWSTONE_2022_Phase4_3_BllngsQL1`, QL1, flown 2022-07-31 to 08-03); state inventory `mslgis.mt.gov/arcgishosting/rest/services/GEOINFO/LidarInventory/MapServer/2` | classes 1/2 only and few ground points: `--ground-mode surface`, footprint mask, `--accept`. `--year 2022` |
| Ortho (fallback) | state NAIP `gisservice.mt.gov/.../MSDI_Framework/NAIP_2023/ImageServer/exportImage` (0.6 m) | |
| Blocked | listing sites behind bot or login walls, real-estate site APIs, street-level imagery that needs a key or token | skip; never work around |

## Hazard sources (national), checked 2026-11-25

Used by `scripts/hazards.py`. None of these stops a run; a source that fails is written as "source not
reachable on <date>". The region profile gives the NWS forecast office (`wfo`, FSD for Sioux Falls) and the
flood layer.

| Data | Endpoint | Notes |
|---|---|---|
| Hail and wind history | NOAA NCEI Storm Events yearly CSV: `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_details-ftp_v1.0_dYYYY_c<build date>.csv.gz` | one file per year (~16 MB), rebuilt often (the 2026 file was rebuilt 2026-11-19): read the directory listing for the newest `c` date. BEGIN_LAT / BEGIN_LON, EVENT_TYPE, MAGNITUDE (hail in inches, wind in knots). Publication lags a few months. Do not store EVENT_NARRATIVE / EPISODE_NARRATIVE |
| Recent local storm reports | Iowa Environmental Mesonet `https://mesonet.agron.iastate.edu/geojson/lsr.geojson?sts=<ISO start>&ets=<ISO end>&wfos=<WFO>` | GeoJSON points with type, magnitude, valid time. Preliminary: label it. Do not store `remark` |
| Daily storm reports | NOAA SPC `https://www.spc.noaa.gov/climo/reports/YYMMDD_rpts_hail.csv` (also `_wind`, `_torn`) | national, one file per day; preliminary. Do not store `Comments` |
| Radar-indicated hail | NCEI SWDI `https://www.ncei.noaa.gov/swdiws/csv/nx3hail/<YYYYMMDD>:<YYYYMMDD>?bbox=<w>,<s>,<e>,<n>` (NEXRAD level-3 hail signatures: MAXSIZE, PROB, SEVPROB) | use `bbox`: `center=` + `radius=` did not filter (returned the whole country). At most 744 h per request. Query only the dates the reports name, ± 1 day. Radar estimate, not a ground report: label it |
| Flood zone | FEMA NFHL `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query` (Flood Hazard Zones), outFields FLD_ZONE, ZONE_SUBTY, SFHA_TF, STATIC_BFE, DFIRM_ID | query with the parcel polygon; report the worst zone touching the parcel |
| MESH hail swaths (later) | MRMS `MESH_Max_1440min` on the IEM archive `https://mtarchive.geol.iastate.edu/YYYY/MM/DD/mrms/ncep/MESH_Max_1440min/` | answered for 2020 and 2024, 404 for 2016. GRIB2: needs a GRIB reader that is not installed. Not in the demo tier yet |
| Design values (not used) | snow / wind design values, code edition, ice-barrier requirement | no machine-readable public source found; the ASCE hazard tool needs a key. Print nothing until a person records a public source and the date read in the region profile |

Wording rules: storm reports are points reported near the house, not a measurement at the roof. Say "hail of
1.00 in reported 0.6 mi away on <date>", never "the roof was hit". Distances run from the report point to the
parcel centroid.

## Hillside lots

* Heights above a filtered ground SURFACE, last returns only (`--ground-mode surface`); a house cut
  into a slope meets grade at its uphill eave, so the walls (city outline, `--footprint-file`
  with `--footprint-shift`) are masked from the ground and low points inside them are kept
  (`--min-hag-inside`).
* `--accept` keeps real roof planes only (n, RMS, slope, patch area), drops thin strips of
  hillside that happen to lie on a roof plane, removes canopy over the eaves and routes level
  planes below every eave to decks; `--flat-z lo,hi` lists decks and slabs with their heights
  (negative values with `=`: `--flat-z=-1.5,3.5`).
* Expect several floor levels: read them from the deck tops, the garage apron and the uphill
  grade, and put walls on `base_z`; a garage under a deck is presentation geometry
  (`extra_walls` in `details.json`), not a roof wing.
* Re-runs over a curated job: `--keep-datum`, then rebuild the whole chain.
