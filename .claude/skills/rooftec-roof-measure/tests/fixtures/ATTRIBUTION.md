# Fixture data credits

`city/footprint-235245.json` and `city/wireframe-79199.json` are unchanged answers from the City of Sioux Falls ArcGIS REST service, fetched on 2026-11-16:

- Building Footprints, `Data/Property/MapServer/5`, OBJECTID 235245.
- Building Wireframe (3D solid, captured June 2023), `Data/Community/MapServer/66`, OBJECTID 79199.

Contains data from the City of Sioux Falls, licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The city states the data is not a survey, is not guaranteed to be accurate, and is not intended for use in mapping products for resale.

`lidar/lidar_points-235245.npz` holds 5,308 lidar points over the same house, clipped from the USGS 3DEP collection `SD_EasternSD_3_2020` (public EPT on AWS) and reprojected to EPSG 32164. Lidar: USGS 3DEP, public domain.

These files exist so the tests run offline. Do not add fixtures for customer addresses.
