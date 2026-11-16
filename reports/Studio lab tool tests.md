# Roof Studio Lab: findings

Four free tools were added to a copy of Roof Layer Studio and tested side by side on the studio's measured job (a house in Sioux Falls). Each has a section in the Lab tab with an on/off control, a Run test button that measures in the viewer's own browser, and a short summary.

How the numbers were taken: headless Chromium 153 (Playwright) with a software GPU (SwiftShader), and a local server that wraps the page like the artifact host and sends the artifact CSP. Two policies were tested: the one given (no 'wasm-unsafe-eval') and the same plus 'wasm-unsafe-eval'. Frame times are only comparable within this machine; real figures come from Run test on a phone or laptop. Load times are from localhost. Sizes are exact.

| Tool | Verdict | One line |
|---|---|---|
| model-viewer AR | Adopt later | Works as a 3D viewer (2.6 MB AR GLB, 0.5 s load); AR itself is very likely blocked inside the artifact frame |
| three.js WebGPU | Skip for now | One shared three core and a faithful WebGL2 fallback, but no speed gain; reveal shaders, path tracer and splats need porting |
| 3d-tiles-renderer | Adopt | 1.37 MB tileset of 97 city solids + ground loads in under 1 s and lands within 4 cm of the house |
| Spark splats | Adopt later | Works as soft context but from lidar it is blurry, needs WebAssembly and is heavy; worth it with a real capture |

## 1. model-viewer (AR)

Built: `buildSceneGlb()` in js/app.js is the existing "Download layers (.glb)" export, now shared. It takes the visible layers and, optionally, the house (walls, trim, openings; terrain, streets and site meshes left out), with new `maxTextureSize`, `jpeg` and `skip` options. The output goes to `<model-viewer ar ar-modes="webxr scene-viewer quick-look" ar-scale="auto" ar-placement="floor">` through a blob: URL. The module build loads via the importmap, so its bare `three` import is the studio's 0.186.1.

Measured (headless desktop):
- Library: 475,465 B raw, 117 KB transferred; import 74–121 ms.
- Copies of three: 1 (r186 shared). The self-contained model-viewer.min.js is 1.07 MB and would add three r183.
- Download-button GLB: 20.8 MB (21,788,248 B), of which 21.46 MB are 9 PNG textures; export 9.4–11.5 s.
- AR GLB with 1024 px PNG: 10.8 MB.
- AR GLB with 1024 px JPEG + exterior layers + house (the Lab default): 2.6 MB (1.80 MB images, 0.55 MB geometry, 367 meshes, 24 materials).
- Viewer load: 0.5–0.64 s.
- `canActivateAR` and immersive-ar: false (no AR hardware).
- In a sandboxed iframe: the 3D view works; `window.open` is refused without allow-popups.
- Under the given CSP, the bundled meshopt decoder's WASM is refused on import. This is harmless for these GLBs, and the Lab swallows that one rejection.

AR by place:
- Inside the artifact frame:
  - WebXR needs the frame to allow xr-spatial-tracking; expect it to be blocked.
  - Scene Viewer needs a public https GLB; a blob: URL is private and artifact files need a login, so it is blocked.
  - Quick Look builds the USDZ in-page and opens it via `<a rel=ar>`, which needs top-level navigation; expect it to be blocked.
- On a normal https page all three work.

Run test prints inIframe, the xr permission, immersive-ar, Quick Look support and canActivateAR, so one tap on an Android phone and an iPhone settles it.

- Pros: Apache-2.0; reuses the studio exporter with no server; one button covers Android and iOS; small when it shares three.
- Cons: the artifact frame likely blocks AR; the export was 20.8 MB (now 2.6 MB for AR); the peer range is three ^0.183, so sharing 0.186 works but is not promised; WebAssembly compiles on import.
- Verdict: adopt later. Adopt the export options now; ship AR from a normal https page or share link that serves the GLB by URL.
- Improve: host an AR page outside the artifact; merge the 367 house meshes before export; add a 1:50 table-top scale.

## 2. three.js WebGPU renderer

Built: two viewports over the stage, WebGLRenderer on the left and WebGPURenderer (three/webgpu 0.186.1) on the right. Both draw one comparison scene: clones of the house and the layers, sharing geometry and materials, with the same sun and sky, and the camera synced. Run test times each renderer alone with the studio loop paused: compile, first frame, 30 frames with a 1-pixel readback (GPU-inclusive), rAF FPS, draw calls, and a pixel diff with thumbnails and a ×4 difference image.

Measured:
- WebGPU flag on (SwiftShader Vulkan adapter "google swiftshader"): the backend was WebGPU, init 21–31 ms, compile 6.0–6.3 s. Then the device was lost ("A valid external Instance reference no longer exists") and the GPU process reset, so the WebGL contexts were lost and restored. This is an environment problem that could not be checked on real hardware.
- WebGPU unavailable: WebGL2 fallback is automatic. Fallback vs WebGLRenderer:
  - Compile: 1.3–1.5 s vs 48 ms.
  - First frame: 5.4–5.8 s vs 1.7–9.8 s.
  - Frame (GPU-inclusive): 166–170 ms vs 169–178 ms.
  - FPS: 20.5 vs 22.6–23.8.
  - Draw calls: 763 vs 751–762.
- Pixel difference: mean 2.1–2.3/255; 0.9–1.2% of pixels over 16 levels (edges and shadow borders).
- three.webgpu.js: 2,284,850 B raw, 418 KB transferred.
- Copies of three: one. three.module.js and three.webgpu.js import the same three.core.js URL (WEBGPU.Mesh === THREE.Mesh).

Would break or need porting:
1. `patchReveal` in js/layers.js (onBeforeCompile + customProgramCacheKey): build reveal and cutaway are ignored. Port to a TSL Fn that Discard()s above uReveal or beyond the cut plane, using the aUp/aAlong/aKey attributes.
2. three-gpu-pathtracer's WebGLPathTracer is WebGL-only; it now logs a deprecation in favour of WebGPUPathTracer.
3. `PMREMGenerator(renderer)` and `envRT.texture` should be replaced by the WebGPU renderer's own environment processing.
4. The tiled snapshot uses sync readPixels and needs readRenderTargetPixelsAsync.
5. Spark (SparkRenderer takes a WebGLRenderer) and `KTX2Loader.detectSupport`.
6. The float sky DataTexture needs float32-filterable.
7. renderer.info field names differ.

Keeps working: standard materials, instanced fasteners, shadows, AgX, fog, OrbitControls, DOM labels, GLTFLoader and GLTFExporter, 3d-tiles-renderer.

- Pros: same package, one core, automatic fallback that matches the WebGL picture.
- Cons: no speed-up (the scene is bound by its 764 draw calls); reveal, cutaway, path tracing, splats and snapshots need porting; slower compile in fallback; WebGPU on phones is uneven and was unstable here.
- Verdict: skip for now.
- Improve: merge static meshes first; port patchReveal to TSL behind a flag and test on a WebGPU phone; revisit when a WebGPU path tracer is usable.

## 3. 3d-tiles-renderer (neighbourhood)

Built: tools/build_tileset.py fetched the 97 City of Sioux Falls 3D building solids in a 400 m square, in 20 requests of 5 records, 1 s apart, cached. It decoded the multipatches, converted every vertex to ECEF via lon/lat and NAVD88 + geoid, and wrote 3D Tiles 1.1 with GLB content:

| File | Contents | Size | Triangles |
|---|---|---|---|
| tileset.json | root transform = ENU→ECEF at the site origin | 2.9 KB | – |
| lod0.glb | LOD0: oriented boxes, geometricError 4 m | 58 KB | 960 |
| q0–q3.glb | LOD1: full solids by quadrant | 204 / 14 / 187 / 31 KB | 5,826 |
| subject.glb | city solid of the house itself (alignment check, hidden) | 5 KB | 54 |
| ground.glb | 3DEP ground, 3 m grid, NAIP 2025 vertex colours, hole under the studio terrain | 895 KB | 34,320 |
| Total | | 1.37 MB (1,433,212 B) | 41,160 |

The Lab places tiles.group with: studio offset × model heading (−0.32°) × (Z-up→Y-up) × inverse(WGS84_ELLIPSOID ENU frame). The georeference is computed in the browser independently of the Python build.

Alignment:
- The model has no georeference, so tools/align_house.py fitted one.
- Roof outline vs city footprint: IoU 0.987; outline distance mean 4.1 cm, p95 15 cm, max 20 cm.
- Terrain vs 19,164 lidar ground returns: robust spread 1.4 cm. This check is circular, because the model terrain came from the same lidar.
- Lidar roof returns sit 1.8 cm above the model roof (median of 930).
- The model's north is true north + 0.32° (grid convergence 1.50°). Without that heading correction, buildings 200 m away would be off by 1.1 m.
- In the browser through the full ECEF chain: centre offset 3.6 cm in plan; roof top 7.6 cm lower in the city solid.

Measured (localhost, headless):
- Import 89–499 ms; tileset.json 119–532 ms; all tiles 0.3–0.7 s.
- 7 tile contents loaded, 6 active (LOD1 replaced LOD0); 41,160 triangles.
- Draw calls 957 with vs 764 without.
- GPU-inclusive frame 699 vs 530 ms in software.
- No load errors. The library warns that 3D Tiles 1.1 support is limited.
- The path tracer renders the tiles but ignores the ground's vertex colours.

- Pros: real georeference that can be reused for any Sioux Falls house the skill finds; small and fast; plain three.js meshes; shows what the model lacks (a shed next door, the school, streets, grade).
- Cons:
  - About 190 extra draw calls (one mesh per building).
  - City solids are June 2023 LOD2 with no eaves; the data is "not for resale".
  - Partial 1.1 support.
  - Attribution must be on screen; the Lab shows it.
  - The studio caps zoom at 180 m; the Lab widens it to 650 m while the tiles are on.
- Verdict: adopt.
- Improve: merge buildings per tile into 2 primitives with EXT_mesh_features ids (about 10 draws); store the georeference per house; build tilesets in the roof-measure pipeline (about 30 s first run, 2 s cached).

## 4. Spark (Gaussian-splat surroundings)

Built: tools/build_splat.py took every 3DEP return within 70 m (111,543 points, all octree depths).
- Left out: the house's own returns (1,011, using the footprint + 0.4 m) and ground returns inside the studio terrain square.
- Ground returns were replaced with a 0.35 m grid on the lidar ground: 79,265 splats, none more than 1 m from a return, so none under buildings.
- Kept: 16,412 above-ground returns.
- Shape: flat discs along the local surface (PCA of 12 neighbours) where points are planar, round blobs elsewhere.
- Colour: NAIP 2025-07-28 (0.3 m, 3×3 mean). Written as SPZ v2 (gzip).

Measured:
- File: 780 KB (1.73 MB unpacked), 95,677 splats, 6.2 per m²; above-ground spacing 0.52 m.
- Library: 3.0 MB raw, 865 KB transferred, WASM inline, blob: workers.
- Fetch + decode: 73–186 ms.
- First sorted frame: 2.3–8 s in software, because of the GPU depth readback; on a GPU, tens of ms are expected.
- Frame: 2.2–2.4 s with vs 0.73 s without in software; +1 draw call.
- Under the given CSP WebAssembly is refused, so Spark cannot sort and nothing shows; the Lab checks first and says so. With 'wasm-unsafe-eval' it works.

Looks: useful as soft context from a distance. Lawn, driveways, street and sidewalks continue seamlessly past the model terrain, trees read as trees, and neighbouring roofs show as coloured patches. Up close it is blurry. Limits:
- About 5 returns per m², roofs only, no walls, so neighbouring houses float as roofs.
- The Dec 2020 leaf-off branches take July 2025 canopy colour.
- NAIP lean of 0.3–1.5 m shifts roof colours.
- Anything changed after 2020 is wrong.
- On-demand rendering needs Spark's onDirty hook (wired).

- Pros: MIT; three.js-native; depth-sorts with the meshes; under 1 MB; the same viewer would show a real capture with no code change.
- Cons: needs 'wasm-unsafe-eval'; blurry and partly wrong from lidar; heavy on weak GPUs; the path tracer cannot draw splats (the Lab turns them off when path tracing starts).
- Verdict: adopt later, for real drone or phone captures; skip the lidar-only splat.
- Improve: use a drone orbit or phone walk-around trained to 3DGS; if lidar splats stay, drop returns inside the city solids, cap at 50 m and about 60k splats; ask whether the host can allow 'wasm-unsafe-eval'.

## Ways to improve the project

Ranked by value for effort; all $0.

1. **Show the attribution with measured jobs.** The model uses City of Sioux Falls GIS (CC BY 4.0) and USGS 3DEP, but the studio never shows "Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP." Effort: XS, 30 min.
2. **Merge the house's 375 static meshes by material.** They cause 764 draw calls per frame (colour + shadow passes); merging gives about 50. This is the biggest phone win and also shrinks AR exports. Effort: S, half a day.
3. **Open the measured job by default.** The studio starts on the demo ranch preset, and an artifact link cannot pass ?measured=. Effort: XS, 15 min.
4. **Show accuracy with every number.** The chips say "23.9 sq" while the report says 23.9 ± 0.4 sq. The report says "verified" while the roof-measure rules say "estimate" until the accuracy study passes. Effort: S, 2 h.
5. **Make the GLB export phone- and AR-ready.** It is 20.8 MB, 98% PNG; the `jpeg`/`maxTextureSize`/`skip` options now exist (2.6 MB). Effort: XS, 1 h.
6. **Store the georeference per house.** Write origin lon/lat, NAVD88 height and heading into detail.json from the measuring pipeline. Effort: XS, 1 h.
7. **Ship the house model as binary.** The 4.0 MB base64 .gltf.json is decoded with atob on the main thread; as GLB it would be 2.8 MB (the tiles show .glb is served), less with KHR_mesh_quantization. Effort: S, 2 h.
8. **Vendor or hide what cannot work in the artifact.** The Poly Haven HDRI (blocked by connect-src; the studio falls back with a toast), the Draco/KTX2 decoders from jsDelivr, and meshopt and Spark, which need 'wasm-unsafe-eval'. The meshopt import no longer logs an error. Effort: S, 2 h.
9. **Adopt 3D Tiles context for every measured job.** Merge buildings per tile first. Effort: M, 1–2 days.
10. **Phone tab bar.** The 7 tabs fit at 390 px (55.7 px each, 11.5 px type) but are tight; an icon bar or a "More" overflow would scale beyond 7. Effort: S, 2 h.
11. **Context-loss recovery.** A GPU reset lost and restored the studio's WebGL context. Rebuild the canvas textures and PMREM on webglcontextrestored, and test on iOS. Effort: S, half a day.

Nothing in the existing studio broke. These all ran with no console errors, in light and dark, desktop and phone: all six tabs, Layers view, Cutaway, Before, build playback, product change, takeoff, snapshot, switching to a preset and back, and path tracing with the tiles on.

## Only checkable on a real device

- AR on Android and iPhone, inside the artifact and from a normal https page.
- A working WebGPU backend.
- Real frame rates, and Spark's sort time on a GPU.
- Whether the host CSP includes 'wasm-unsafe-eval'.

## Rebuild for another house

```
cd studio-lab
python3 tools/align_house.py --address "<Sioux Falls address>" --model out/houses/<id>.gltf.json
python3 tools/build_tileset.py --radius 200
python3 tools/build_splat.py --radius 70
```

Needs Python 3.9+, numpy, scipy, laspy + lazrs, rasterio + pyproj, and the rooftec-roof-measure `scripts/` folder (set ROOF_MEASURE_SCRIPTS if it lives elsewhere). Downloads are cached in studio-lab/cache/; outputs go to out/lab/.

## Licences and attribution

| Item | Licence | Notes |
|---|---|---|
| @google/model-viewer 4.4.0 (2026-10-09) | Apache-2.0 | bundles Lit, BSD-3-Clause |
| three.js three/webgpu, three/tsl 0.186.1 | MIT | |
| 3d-tiles-renderer 0.5.3 (2026-09-18, NASA-AMMOS) | Apache-2.0 | |
| @sparkjsdev/spark 2.4.0 (2026-10-20) | MIT | |
| City of Sioux Falls GIS: 3D solids, footprints, address points (June 2023) | CC BY 4.0 | "not intended for use in mapping products for resale" |
| USGS 3DEP SD_EasternSD_3_2020 (Dec 2020) | public domain | credit USGS |
| USDA NAIP 2025 (sd_m_4309626_sw_14_030_20250728) via Microsoft Planetary Computer | public domain | USDA FSA |
| Python tools: numpy, scipy, laspy, lazrs, rasterio, pyproj | BSD / MIT / Apache | in tools/ only, not shipped |

Required credit: "Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP. Imagery: USDA NAIP 2025." It is shown on screen while the tiles or splats are on, in the Lab tab, in tileset.json (asset.extras.attribution), in every GLB's asset.copyright, and in lab/data/*.json.
