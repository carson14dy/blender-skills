# Licences

Keep this skill permissive: Python standard library, numpy, and two optional lidar packages. Check this page before you add a dependency or a data source.

## What ships in this skill

| Item | Licence | Note |
|---|---|---|
| The skill's own code | Same as this repository | Python standard library only, plus numpy |
| numpy | BSD-3-Clause | Required |
| laspy | BSD-2-Clause | Optional, imported only for `--lidar` |
| lazrs (Python bindings of laz-rs) | MIT (laz-rs itself is Apache-2.0) | Optional, imported only for `--lidar` |
| Test fixtures in `tests/fixtures/` | City data CC BY 4.0; lidar public domain | Credits are in `tests/fixtures/ATTRIBUTION.md` |

`pyproj` (MIT) is not needed, because `proj.py` does the two map conversions in numpy. Review round 1 checked both conversions against pyproj 3.8; they agree to 0.0033 ft, and two tests hold the reference values.

## Data

| Dataset | Licence | Required credit |
|---|---|---|
| City 3D solids, footprints, address points, building permits | CC BY 4.0, with the city's own sentence "This data is not intended for use in mapping products for resale" | "Contains data from the City of Sioux Falls, CC BY 4.0", with a note that it was changed and is not a survey |
| USGS 3DEP lidar | Public domain | "Lidar: USGS 3DEP" (requested, not required) |

The tool writes both credits into `roof.json`, into the GLB (`asset.copyright` and scene extras) and at the foot of `takeoff.md`. Keep them when you copy numbers elsewhere.

### What the city licence says, and where

Review round 2 read the licence text on 2026-11-16. Each of the four layers this skill uses carries the same "use limitation" in its own metadata, at `<layer url>/metadata?f=xml` (for example `.../Data/Community/MapServer/66/metadata?f=xml` for the Building Wireframe solids):

- The data is "for public use as described under the Creative Commons Attribution 4.0 United States License", and the link in that sentence goes to `https://creativecommons.org/licenses/by/4.0/`. There is no "United States" edition of version 4.0, so read it as CC BY 4.0 International, which is what the link and the DataWorks portal say.
- "These drawings and data are neither a legally recorded map nor a survey", and are "for reference purposes only".
- "This data is not intended for use in mapping products for resale."

Review round 1 reported that the resale sentence could not be found. It looked at `metadata?format=default` and at the layer page, which answer "The administrator has disabled the Services Directory". The `f=xml` form of the same address works. The Building Wireframe layer does carry its own licence statement, so CC BY 4.0 for the solids is no longer an inference.

What is still an interpretation and not legal advice: that in-house estimating is not a "mapping product for resale". Do not sell the measurements, the model or a map made from them, and ask the city GIS office (cityofsfgis@siouxfalls.gov) before any use that comes close.

## Tools that stay separate programs

Run these as their own programs and exchange files with them. Never import or bundle their code here.

- `roofer` (GPL-3.0): reads a LAZ file and an outline, writes CityJSONSeq. Do not `pip install roofer`; that name on PyPI is an unrelated package.
- Blender and its add-ons (GPL): open `roof.glb`. Renders are yours.
- OpenDroneMap, WebODM, OpenMVS (AGPL-3.0): internal use only, never hosted for customers.
- `straight-skeleton` versions 2 and 3 wrap GPL code. If tier C is built, pin version 1.1.0 (MIT).

## Do not use

- Paid or billing-account sources: Google Solar API, Google 3D Tiles, Nearmap, EagleView, Hover, Cesium ion.
- Non-commercial research code and models, such as MASt3R, DUSt3R and the original 2DGS code.
- City imagery for 2025 and 2026 as a texture or a download. It is view-only Nearmap imagery.
