# Roof Studio Lab

A copy of Roof Layer Studio with a Lab tab that tests four free tools on 1601 S Discovery Ave: model-viewer (AR), the three.js WebGPU renderer, 3d-tiles-renderer (neighbourhood from City of Sioux Falls 3D solids) and Spark (Gaussian splats from USGS 3DEP lidar coloured with NAIP 2025).

- Live page (private to the owner): https://claude.ai/artifact/588SfLYHjaPoa6Wd2eGKak
- Findings, verdicts and ranked project improvements: `reports/Studio lab tool tests.md`
- `tools/`: the scripts that rebuild the tileset and splat for another house (see "Rebuild for another house" in the findings). `pack_json.py` stores binaries as base64 JSON, because artifacts do not serve .glb or .spz files.

Credit: Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP. Imagery: USDA NAIP 2025.
