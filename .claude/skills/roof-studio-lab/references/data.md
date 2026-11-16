# Rebuild the tileset and splat for another Sioux Falls house

Run the three scripts in this order. Each takes about 2 to 30 seconds; a repeat run uses the cache.

```bash
S=.claude/skills/roof-studio-lab/scripts
export LAB_OUT="$SCRATCH/lab"          # the lab site folder; outputs go to $LAB_OUT/lab/
export LAB_CACHE="$SCRATCH/lab-cache"  # downloads; default ~/.cache/roof-studio-lab
python3 $S/align_house.py --address "<house number and street>" --model "$LAB_OUT/houses/<id>.gltf.json"
python3 $S/build_tileset.py --radius 200
python3 $S/build_splat.py --radius 70
```

`align_house.py` writes `lab/data/site.json`. The studio's measured models carry no georeference, so
the script fits the model's `Roof*` meshes to the city footprint (translation and rotation) and the
model's `Terrain*` mesh to 3DEP ground returns. Check its printout: IoU about 0.98 or better and an
outline distance of a few centimetres mean a good fit. The model needs meshes named `Roof...` and
`Terrain...`; the roof-measure skill's GLBs name the roof `Roof` and have no terrain, so give the
height with a different method or add terrain before using it for those.

`build_tileset.py` writes `lab/tiles/*.glb.json` and `tileset.json`, and `lab/data/tiles.json`.
`build_splat.py` writes `lab/splat/surroundings.spz.json` and `lab/data/splat.json`. Both pack their
binaries as base64 JSON with `pack_json.py` because the artifact host does not serve `.glb` or `.spz`.
The Lab reads the sizes from `lab/data/*.json`, so nothing else needs editing for the same layout.
The Lab code names the test house id (`1601-s-discovery-ave`) in `MEASURED_ID` at the top of
`js/lab.js`; change it to the new house's id from `houses/index.json`.

## Dependencies

Python 3.9 or newer with numpy, scipy, `laspy lazrs` (lidar), `rasterio pyproj` (NAIP), and the
rooftec-roof-measure skill's `scripts/roofmeasure` package. The scripts find that skill next to this
one; set `ROOF_MEASURE_SCRIPTS` when it lives elsewhere.

## Sources, caching and politeness

- City of Sioux Falls ArcGIS: address points, footprints and the 3D building solids
  (`Community/MapServer/66`). Requests ask for 5 records each, 1 second apart, and every answer is
  cached in `LAB_CACHE`. A 400 m square around a house is about 100 solids and 20 requests.
- USGS 3DEP lidar `SD_EasternSD_3_2020` from the public EPT on AWS; nodes are cached and shared.
- USDA NAIP 2025 from Microsoft Planetary Computer (anonymous SAS token from
  `planetarycomputer.microsoft.com/api/sas/v1/token/naip`); the crop is cached.
- The cache holds data for real addresses: keep it out of git.

## Credit and licences

Show "Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP. Imagery: USDA NAIP
2025." wherever the tiles or splats appear. The scripts also write it into `tileset.json`, every GLB's
`asset.copyright` and `lab/data/*.json`. City data is CC BY 4.0 and "not intended for use in mapping
products for resale"; 3DEP and NAIP are public domain.
