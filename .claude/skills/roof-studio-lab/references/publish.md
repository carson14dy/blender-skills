# Publish the lab as a claude.ai artifact

Publish `index.html` as the page and every other file in the site folder as supporting files with the
same relative paths. Update the existing artifact (its URL is in `handoffs/studio-lab/README.md`)
instead of creating a new one.

## File types

The host serves only these extensions: .html .css .js .mjs .wasm .json .map .geojson .webmanifest
.txt .md .csv .xml .svg .png .jpg .jpeg .gif .webp .avif .ico .woff .woff2 .ttf .otf .mp3 .wav .ogg
.mp4 .webm .pdf. Binary data therefore ships as base64 JSON made by `scripts/pack_json.py`:
`name.glb` becomes `name.glb.json` and `surroundings.spz` becomes `surroundings.spz.json`. Never give
data a misleading extension such as `.wasm`. The Lab decodes these files itself: a 3d-tiles-renderer
plugin turns a request for `q0.glb` into `q0.glb.json` (so `tileset.json` keeps `.glb` URIs), and
Spark gets the decoded bytes as `fileBytes`. The studio's own house model is `houses/<id>.gltf.json`
for the same reason. Each file must be 16 MB or less. Before publishing, run
`find SITE -type f | sed 's/.*\.//' | sort | uniq -c` and the test server, which prints any unserved request.

## The page body

`index.html` is the page body. Remove a leading `<!doctype html><html><head>...</head><body>` line and
the closing `</body></html>` if a downloaded copy has them; the host adds them. Keep the `<title>`.

## Content security policy

Scripts may come only from `cdn.jsdelivr.net/npm/`, `unpkg.com`, `cdnjs.cloudflare.com`,
`cdn.tailwindcss.com` and `code.jquery.com`. Fetches, workers, images and WebAssembly modules must be
files in the site folder or `blob:`/`data:` URLs. Stylesheets may come from Google Fonts. The policy
given for the artifact has no `'wasm-unsafe-eval'`, so WebAssembly cannot compile: Spark then cannot
sort splats (the Lab says so), model-viewer's and three's meshopt decoders are refused (harmless for
these files; the rejections are caught), and Draco or KTX2 models would fail. The Poly Haven HDRI in
the Render tab is on another host and falls back to the built-in sky.

## Pinned versions (all at least two weeks old when chosen, 2026-11-16)

| Library | URL in the importmap |
|---|---|
| three 0.186.1 | `https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js` (+ `examples/jsm/`, `three.webgpu.js`, `three.tsl.js`) |
| 3d-tiles-renderer 0.5.3 | `https://cdn.jsdelivr.net/npm/3d-tiles-renderer@0.5.3/build/index.js` |
| @sparkjsdev/spark 2.4.0 | `https://cdn.jsdelivr.net/npm/@sparkjsdev/spark@2.4.0/dist/spark.module.js` |
| @google/model-viewer 4.4.0 | `https://cdn.jsdelivr.net/npm/@google/model-viewer@4.4.0/dist/model-viewer-module.min.js` |
| three-mesh-bvh 0.9.16, three-gpu-pathtracer 0.0.27 | studio's own entries |

The model-viewer module build imports bare `three`, so it shares the page's three. Its peer range is
`^0.183`; it worked with 0.186.1 in testing, so recheck after any three upgrade.

## Downloads

The page cannot start downloads directly. The studio asks for the `downloads` capability through
`window.claude.use('downloads')` for snapshots and plan JSON. GLB export is disabled inside the
artifact because `.glb` is not a type the viewer can save; the AR viewer works without it.
