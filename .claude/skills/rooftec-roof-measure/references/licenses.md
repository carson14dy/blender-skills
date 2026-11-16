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
| City 3D solids, footprints, address points | CC BY 4.0 as stated on the city's DataWorks portal; the research note also quotes "not intended for use in mapping products for resale", which review round 1 could not find again | "Contains data from the City of Sioux Falls, CC BY 4.0", with a note that it was changed and is not a survey |
| USGS 3DEP lidar | Public domain | "Lidar: USGS 3DEP" (requested, not required) |

The tool writes both credits into `roof.json`, into the GLB (`asset.copyright` and scene extras) and at the foot of `takeoff.md`. Keep them when you copy numbers elsewhere.

The Building Wireframe layer is not listed on DataWorks and carries no licence statement of its own, so CC BY 4.0 for that layer is an inference from the city's general open-data statement. Ask the city GIS office to confirm it. Reading the city licence as allowing in-house estimating is the research note's interpretation and not legal advice. Do not sell the measurements, the model or a map made from them.

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
