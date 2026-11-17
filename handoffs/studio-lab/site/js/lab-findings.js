// Condensed findings shown in the Lab tab. The full write-up, with every number and how it was
// measured, is lab/findings.md. Numbers marked "headless" come from Chromium with a software GPU
// (SwiftShader); run the tests on a real phone or laptop for its own numbers.
export const FINDINGS = {
  modelViewer: {
    verdict: 'Adopt later', verdictClass: 'later',
    measured: 'Headless: library 117 KB transferred (475 KB), shares three r186 (one copy). AR GLB 2.9 MB with 1024 px JPEG textures (exterior layers + house); the Download-button GLB is 20.8 MB, 98 % PNG textures. Viewer loads the GLB in 0.5 s. AR: not available in headless Chromium; inside the claude.ai frame it is expected to be blocked (see Cons). Check on a phone.',
    pros: [
      'Drop-in web component, Apache-2.0; the module build reuses the page\'s three 0.186.1 (no second copy, 117 KB over the wire).',
      'Takes the studio\'s own GLTFExporter output through a blob URL: no server, no upload.',
      'One AR button covers Android (WebXR, Scene Viewer) and iOS (Quick Look, USDZ made in the browser).',
    ],
    cons: [
      'Inside the artifact frame AR is very likely blocked: WebXR needs the frame to allow xr-spatial-tracking, Scene Viewer needs a public https GLB (a blob: URL is private), Quick Look needs top-level navigation.',
      'The studio\'s export is heavy: 20.8 MB with full PNG textures; AR needs the new JPEG + 1024 px + exterior-only options (2.9 MB).',
      'Its peer range is three ^0.183; sharing 0.186 worked here but is not promised. The self-contained build (1.07 MB) carries its own three r183.',
      'Its bundled meshopt decoder compiles WebAssembly on import; a page policy without wasm-unsafe-eval refuses it (harmless for our GLBs, now handled).',
    ],
    improve: [
      'Ship AR from a normal https page (or a share link outside the artifact) that serves the GLB by URL: then Scene Viewer and Quick Look both work.',
      'Keep the AR export light: JPEG, 1024 px, exterior layers only, merged house meshes (458 meshes today).',
      'Set ar-placement floor + ar-scale auto (done) and add a 1:50 "model on the table" scale preset for living-room demos.',
    ],
  },
  webgpu: {
    verdict: 'Skip for now', verdictClass: 'skip',
    measured: 'three/webgpu shares three.core.js with the studio (one copy); +418 KB transferred (2.28 MB). Headless WebGPU (SwiftShader adapter) started, then the device was lost and took the WebGL contexts with it. In WebGL2-fallback mode: same frame time as WebGLRenderer (151 vs 152 ms headless), 945 vs 944 draw calls, mean pixel difference 2.2/255 (1.1 % of pixels over 16 levels: edges and shadow borders).',
    pros: [
      'Same package and version as the studio: no extra dependency, and the core is shared, not duplicated.',
      'Falls back to WebGL2 by itself where WebGPU is missing, and the picture matches WebGLRenderer closely.',
      'TSL node materials would make the layer reveal and cutaway shaders portable to both backends.',
    ],
    cons: [
      'The build-reveal and cutaway shaders (onBeforeCompile in layers.js) are ignored: build playback and cutaway stop working until ported to TSL.',
      'The path tracer (three-gpu-pathtracer WebGLPathTracer), Spark splats, PMREMGenerator(renderer) and the tiled snapshot readback are WebGL-only today.',
      'No measured speed-up: the scene is limited by its 946 draw calls, which WebGPU does not remove.',
      'Shader compile was slower in fallback mode (1.3 s vs 0.05 s headless); WebGPU support on phones is still uneven.',
    ],
    improve: [
      'Cut draw calls first (merge the 466 static house meshes): it helps both renderers and every phone.',
      'Port patchReveal to TSL (discard by reveal key and cut plane) behind a feature flag, then re-run this test on a WebGPU phone.',
      'Revisit when the path tracer has a WebGPU version the studio can use.',
    ],
  },
  tiles: {
    verdict: 'Adopt', verdictClass: 'adopt',
    measured: 'Local 3D Tiles 1.1: 97 city solids within 200 m + a 3DEP ground mesh, 7 tile files, 1.37 MB of GLB shipped as 1.91 MB base64 JSON (the host serves no .glb). Loaded in 0.3 to 0.7 s on localhost; 6 tiles active, 41,160 triangles, +193 draw calls (1,139 vs 946). Alignment through real ECEF coordinates: 3.6 cm in plan, 7.6 cm at the roof top against the measured model (outline fit IoU 0.987, mean 4 cm).',
    pros: [
      'Real georeference: tiles sit in ECEF and land on the studio house within centimetres, so the same path works for any house the roof-measure skill can find.',
      'Small and fast: 1.4 MB of GLB (1.9 MB as base64 JSON) for a 400 m square, two levels of detail, loads in under a second; all data is free (City of Sioux Falls CC BY 4.0, USGS 3DEP).',
      'Plain scene graph: works with the studio\'s lights, fog and shadows, and with the path tracer.',
      'Shows real context the model lacks: neighbours, a shed next door, the school, street layout and grade.',
    ],
    cons: [
      'Each building is its own mesh: about 190 extra draw calls.',
      'City solids are June 2023 and LOD2 (no eaves, no windows); the data may not be resold, so keep the context in-house.',
      '3d-tiles-renderer warns that 3D Tiles 1.1 support is partial; the path tracer ignores the ground\'s NAIP vertex colours (renders white).',
      'Needs the attribution on screen while shown (done) and a wider camera range (the studio caps zoom at 180 m; the Lab widens it).',
    ],
    improve: [
      'Merge each tile\'s buildings into two primitives with EXT_mesh_features ids: about 10 draw calls instead of 190.',
      'Add the georeference (origin, NAVD88 height, heading) to every measured house at build time so no fit is needed.',
      'Build tilesets on demand in the roof-measure skill (tools/build_tileset.py already runs for any Sioux Falls address in about 30 s).',
    ],
  },
  splat: {
    verdict: 'Adopt later', verdictClass: 'later',
    measured: '95,677 splats within 70 m (79,265 ground grid at 0.35 m, 16,412 lidar returns above ground), 780 KB SPZ shipped as 1.07 MB base64 JSON (the host serves no .spz). Library 865 KB transferred (3.0 MB, WASM inline). Decode 0.07 to 0.19 s; first sorted frame 3.5 to 8 s headless (seconds of GPU readback in software, expect far less on a GPU). Needs wasm-unsafe-eval: blocked under the CSP given for the artifact.',
    pros: [
      'Gives a soft, photo-coloured setting (lawn, driveways, street, trees, neighbouring roofs) for about 1 MB.',
      'MIT, three.js-native, mixes with the studio meshes and depth-sorts correctly; works with on-demand rendering through onDirty.',
      'The same viewer would show a real drone or phone capture of the site later with no code change.',
    ],
    cons: [
      'Needs WebAssembly: a page policy without wasm-unsafe-eval stops it (the Lab detects this and says so).',
      'From lidar it is only a blurry approximation: no walls (lidar sees roofs from above), leaf-off December 2020 branches coloured by July 2025 canopy, NAIP roof lean of 0.3 to 1.5 m smears roof colours, anything built after 2020 is missing.',
      'Heavy on weak GPUs: the frame time tripled in the headless test, and the path tracer cannot draw splats (the Lab turns them off).',
    ],
    improve: [
      'Use it for real captures (a drone orbit or a phone walk-around trained to 3DGS), not lidar.',
      'If lidar splats stay: drop above-ground returns inside city solids (the tiles draw those), cap the radius at 50 m and thin to 60k splats.',
      'Ask for wasm-unsafe-eval on the artifact host, or keep Spark to pages that allow it.',
    ],
  },
};

// Ways to improve the studio overall, ranked by value for effort. All stay at $0.
export const PROJECT = [
  { title: 'Show the data attribution with measured jobs.', why: 'The measured house uses City of Sioux Falls GIS (CC BY 4.0) and USGS 3DEP, but the studio never shows the credit line; the licence requires it wherever the model or numbers appear.', effort: 'XS, 30 min' },
  { title: 'Merge the measured house\'s 466 static meshes.', why: '946 draw calls per frame (shadow pass included) for one house since the November model update (764 before); merging by material would drop it to about 50 and help every phone, WebGPU or not.', effort: 'S, half a day' },
    { title: 'Show accuracy with every number.', why: 'The chips say "23.9 sq" bare while the report says 23.9 ± 0.4 sq; the report calls values "verified" while the roof-measure rules call public-data values "estimate" until the accuracy study passes. Show ± and one status word.', effort: 'S, 2 hours' },
  { title: 'Make the GLB export phone- and AR-ready.', why: 'All visible layers export to 20.8 MB (98 % PNG textures); JPEG + 1024 px + exterior-only gives 2.9 MB. The options exist now in buildSceneGlb.', effort: 'XS, done in the Lab; 1 hour to expose' },
  { title: 'Store the georeference with each measured house.', why: 'The model has no origin; the Lab had to fit it (IoU 0.987). Writing origin lat/lon, NAVD88 height and heading (0.32° here) into detail.json makes tiles, splats and AR anchors automatic.', effort: 'XS, 1 hour' },
  { title: 'Shrink the house model.', why: 'The 5.4 MB base64 .gltf.json is decoded with atob on the main thread. The host serves no .glb, so keep JSON but quantize the geometry inside it (KHR_mesh_quantization, no decoder) and decode with Uint8Array.fromBase64 where available.', effort: 'S, 2 hours' },
  { title: 'Remove features that cannot work in the artifact.', why: 'The Poly Haven HDRI, the Draco/KTX2 decoders and meshopt (WebAssembly) are fetched from other hosts or need wasm-unsafe-eval; vendor a 1k HDRI and the decoders, or hide the options.', effort: 'S, 2 hours' },
  { title: 'Add neighbourhood context with 3D Tiles.', why: 'Adopt the Lab\'s tileset path: 1.9 MB as JSON, sub-second load, centimetre alignment.', effort: 'M, 1 to 2 days' },
];
