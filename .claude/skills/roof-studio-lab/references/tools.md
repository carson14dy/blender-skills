# The four Lab tools

Each tool has a section in the Lab tab with an **On** switch, a **Run test** button and a
"Pros, cons and improvements" block. The code is `js/lab.js`; the short texts and verdicts are
`js/lab-findings.js`; the full write-up is `lab/findings.md`. "Run all four tests" runs them in a row
and fills a JSON box you can copy. `window.roofStudio.lab.tests` exposes the same functions to scripts.

Verdicts mean: **adopt** = put it in the studio now; **adopt later** = worth it once the named
condition is met; **skip** = not worth the porting cost today, revisit when the condition changes.

## 1. `<model-viewer>` AR (verdict: adopt later)

Switching it on exports the scene with `roofStudio.lab.buildSceneGlb()` (the studio's own GLTFExporter
path, with the new `house`, `skip`, `maxTextureSize` and `jpeg` options) and shows it in
`<model-viewer ar>` through a blob URL. The module build of `@google/model-viewer@4.4.0` shares the
page's three 0.186.1, so there is one copy of three.

Measured: 117 KB download; AR GLB 2.6 MB with JPEG 1024 px textures (20.8 MB for the full PNG export);
loads in about 0.5 s. AR is very likely blocked inside the claude.ai frame: WebXR needs the frame to
allow `xr-spatial-tracking`, Scene Viewer needs a public https GLB (a blob URL is private), and Quick
Look needs top-level navigation. AR should work from a normal https page.

Still to check on devices: press Run test on an Android phone and on an iPhone, inside the artifact
and from a normal https page; read `canActivateAR`, `immersive-ar` and Quick Look support.

## 2. WebGPU vs WebGL (verdict: skip for now)

Switching it on opens two viewports over the stage (WebGLRenderer left, WebGPURenderer from
`three/webgpu` right) drawing the same house and layers. Run test pauses the studio loop and times
each renderer, then diffs the two frames.

Measured: `three.webgpu.js` shares `three.core.js` with the studio (one copy, +418 KB). Without
WebGPU it falls back to WebGL2 by itself and matches WebGL within 2/255 per pixel, with the same
frame time. Before adopting, port `patchReveal()` in `js/layers.js` (build reveal and cutaway use
`onBeforeCompile`) to TSL, and replace the WebGL-only path tracer, PMREM and snapshot readback.
Revisit when the draw calls are cut and a WebGPU path tracer is usable.

Still to check: a real WebGPU backend. The headless software adapter loses its device.

## 3. 3D Tiles neighbourhood (verdict: adopt)

`lab/tiles/tileset.json` is 3D Tiles 1.1: a 3DEP ground mesh with NAIP colours, all buildings as
boxes (LOD 0) replaced by the full city solids in four quadrant tiles (LOD 1), and the house's own
city solid (hidden, for the alignment check). The root transform is a real ENU-to-ECEF frame. The
Lab places `tiles.group` with the studio's model offset, the model heading from `lab/data/site.json`
and the inverse ENU frame from `WGS84_ELLIPSOID`.

Measured for the test house: 97 buildings within 200 m, 1.9 MB as base64 JSON, loads in under a
second, +193 draw calls, city solid within 3.6 cm of the model in plan and 7.6 cm at the roof top.
"City solid of this house" shows the alignment. The Detail menu sets the error target (low shows LOD 0).

## 4. Spark splats (verdict: adopt later)

`lab/splat/surroundings.spz.json` is about 96k splats from 3DEP lidar within 70 m, coloured from NAIP
2025. Spark sorts splats with WebAssembly, so the page policy must allow `'wasm-unsafe-eval'`. The Lab
tests that first and says "blocked" when it is missing. Path tracing switches the splats off.

From lidar the result is soft and partly wrong: no walls, leaf-off 2020 trees with 2025 colours, NAIP
roof lean. Adopt Spark for a real drone or phone capture of a site; skip the lidar-only splat.

Still to check: frame rate and first-sort time on a real GPU, and whether the artifact host's CSP
allows `'wasm-unsafe-eval'`.
