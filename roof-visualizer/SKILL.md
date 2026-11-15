---
name: roof-visualizer
description: Interactive 3D roof visualizer (Roof Layer Studio) for roofing sales and production. Swap the roof covering for any supplier product or photo at real-world scale, toggle and change every roofing layer, play an animated build from tear-off to finish, open an exploded "layers view" with labels, and export 4K/8K stills or path-traced renders. Trigger when asked to show a homeowner a new roof color or material, compare shingle options, pull a product image from a supplier, show the roof layers, animate or explain the installation step by step, make an exploded roof diagram, or measure squares and order quantities from a 3D house.
---

# Roof Layer Studio (roof-visualizer)

A browser app (Three.js, MIT) that rebuilds a roof as real layers on top of a 3D house:

| Layer (bottom to top) | Built from |
|---|---|
| Existing shingles + felt | the whole roof, used for the tear-off |
| Roof deck (OSB / plywood, 4x8 sheets) + repair sheets | every roof plane, with edge thickness |
| Drip edge | eaves (under ice & water) and rakes (over underlayment) |
| Ice & water shield | 1-3 rows at the eaves plus 36" centered in valleys |
| Underlayment | synthetic gray/blue/black or #30 felt |
| Starter strip | eaves and rakes |
| Fasteners | every nail on the nail line, 4 or 6 per shingle (about 11,000 on the demo house) |
| Shingles / metal / tile / slate / shake | course-by-course stepped geometry at the product's exposure |
| Ridge vent, hip & ridge cap | ridge and hip lines found from the geometry |

Every layer is built in each plane's own eave-aligned frame, so shingle courses run parallel to the eaves on hips and valleys, and textures sit at their true size (a 36" swatch covers 36" of roof).

## Run it

```bash
cd roof-visualizer && npm install && npm start
```

`npm start` runs `scripts/serve.mjs` (Node 18+, binds to 127.0.0.1:8080) and opens the browser. `npm install` is only needed for Claude-written build plans (`@anthropic-ai/sdk`, optional). The viewer also works as static files (any web server, or the published artifact) without the supplier scanner and Claude plans.

Tests: `npm test` (build player, plan files, supplier parser, SSRF guard).

## What the user can do

- **Materials tab**: built-in procedural products (architectural laminate in 7 colors, 3-tab, standing seam in 4 colors, clay tile, slate, cedar shake) and imported supplier products. "Fit to roof" adjusts scale, rotation, course-line alignment, relief and tint; photos also get width in inches, brightness, contrast, saturation and seamless blending. Normal and roughness maps are generated from the photo.
- **Add supplier product**: paste a supplier product page, pick the swatch from the images found, name it, confirm rights, and it is saved into `viewer/catalog/` and applied. Drag a photo onto the 3D view to try it immediately.
- **Layers tab**: show/hide each layer, change products per layer (deck, underlayment, ice & water type and rows, valleys, drip edge color, nails per shingle, ridge vent), add custom layers (radiant barrier, insulation board, etc.), and read the material takeoff (squares, bundles, LF of eaves/rakes/ridges/hips/valleys, drip edge pieces, ice & water and underlayment rolls, starter, cap, nails).
- **Layers view** (toolbar, key E): layers float apart with a spacing slider and callout labels; press again to close them back down.
- **Cutaway** (key C): stepped cut from the right side of the current view showing every layer at once.
- **Before** (key B): the existing roof; press again for the new roof.
- **Watch build** (Space): tear-off to finish, course by course, with captions and a slowly orbiting camera. Scrub, step, change speed in the Build tab.
- **Render tab**: AgX/ACES/Neutral tone mapping, exposure, physical sky or Poly Haven HDRI (CC0), path tracing (three-gpu-pathtracer, MIT), and snapshots at 1080p/4K/8K/square rendered in tiles (no GPU size limit) with layer labels burned in.
- **Project tab**: house presets (ranch hip + garage gable, two-story gable, cottage hip), pitch 3/12-14/12, load a house model (.glb/.gltf, units selectable), sun by latitude, date, solar time and which way the house faces, export layers as GLB for Blender.

## Using a real house model

Load a `.glb` in the Project tab (or `?glb=path/to/house.glb`). Roof faces are found by mesh or material name (`roof`, `shingle`) or, failing that, by slope and height. They are clustered into planes, the original roof is hidden ("Original roof" toggle brings it back), and every layer is rebuilt on those planes. Name the roof mesh `Roof` in Blender/SketchUp/your capture tool for the most reliable result. Meshes named `RT_layer_*` (exported by this viewer or roof-blender) are ignored and rebuilt.

## Build plans (the "AI generated build")

The build sequence is data. Three sources:

1. **Generated from the layer stack** (default): rule-based, with real specs (exposure, nails per shingle, ice & water rows, laps, LF from the model).
2. **Claude**: in the Build tab, describe the job in plain words; the server calls Claude (`claude-opus-5-5`, structured JSON output, server-side refusal fallback enabled) and saves the plan to `viewer/plans/ai-*.json`. Needs `npm install` plus `ANTHROPIC_API_KEY` (or `ant auth login`).
3. **A JSON file** written by you or by Claude Code in this session: put it in `viewer/plans/`, add it to `viewer/plans/index.json`, or open `?plan=plans/<file>.json`.

When the user asks you (Claude) to plan a job, write the plan file yourself using this format and the examples in `viewer/plans/`:

```json
{
  "title": "Storm claim replacement",
  "summary": "One line for the Build tab.",
  "steps": [
    { "id": "tear", "title": "Tear off to the deck", "duration": 7, "camera": "orbit",
      "detail": "One or two plain sentences for the homeowner, with the real spec.",
      "actions": [ { "layer": "oldShingles", "op": "remove" } ] },
    { "id": "eaves", "title": "Drip edge at the eaves", "duration": 1.5,
      "actions": [ { "layer": "dripEdge", "op": "install", "from": 0, "to": 0.5 } ] }
  ]
}
```

- `layer`: `oldShingles`, `oldFelt`, `deck`, `deckRepair`, `dripEdge`, `iceWater`, `underlayment`, `starter`, `nails`, `covering`, `ridgeVent`, `ridgeCap` (custom layers are `custom1`, `custom2`...).
- `op`: `install` (reveal `from`->`to`), `remove` (top rows first), `show`, `hide`.
- `dripEdge` 0-0.5 is the eaves, 0.5-1 the rakes. Install `nails` in the same step as `covering`.
- `duration` is in animation seconds (1.5-10). Old layers start visible; everything else starts hidden; the deck is present unless a step installs it.

## URL parameters and automation

`?house=ranch-hip|two-story|cottage&pitch=8&product=<catalog id>&plan=plans/x.json&glb=house.glb&t=0.6&explode=1&cut=1&tab=layers&quality=standard|high|ultra`

`window.roofStudio` (for Playwright scripts or demos): `ready`, `state`, `setProduct(id)`, `explode(bool)`, `cutaway(bool)`, `seek(fraction)`, `play()`, `snapshot(w, h)` (returns a blob URL), `loadPlan(obj)`, `loadHouse(url)`, `pathTrace(bool)`, `settle()`.

Example: render a 4K exploded diagram from the command line with the preinstalled Playwright:

```js
await page.goto('http://127.0.0.1:8080/?product=arch-weathered&explode=1&capture=1');
await page.evaluate(() => roofStudio.ready);
const url = await page.evaluate(async () => { roofStudio.settle(); return roofStudio.snapshot(3840, 2160); });
```

## Supplier images: rights

Manufacturer websites generally do not allow reusing their product photos without written permission (checked for GAF, Owens Corning, CertainTeed, Atlas; see `docs/ROOFTEC-OPEN-SOURCE.md`). Use assets from the manufacturer's contractor or brand portal, images you have written permission for, or your own photos of the product. The importer requires a rights confirmation and records `sourceUrl` and `rights` on every catalog entry. Pick straight-on, flat photos of a shingle section; whole-house photos and rendered spheres do not map correctly. Set "Photo width" to the real width the photo shows.

CLI equivalent:

```bash
node roof-visualizer/scripts/fetch-swatch.mjs --scan https://supplier.example/product-page
node roof-visualizer/scripts/fetch-swatch.mjs --image <image-url> --name "Line, Color" --supplier "Maker" --width-in 36 --rights "Brand portal, dealer agreement"
node roof-visualizer/scripts/fetch-swatch.mjs --file ./sample.jpg --name "Job 1182 sample board" --rights "Own photo"
```

## Server endpoints (scripts/serve.mjs)

`GET /api/health`, `GET /api/scan?url=`, `GET /api/image?url=` (CORS-safe proxy for textures), `POST /api/swatch`, `GET /api/plans`, `POST /api/plan`. Remote fetches are http(s) only, block private and loopback addresses (re-checked on every redirect), and are capped at 25 MB. `--allow-private` lifts the address check for an internal asset server.

## Files

```
roof-visualizer/
  scripts/serve.mjs            local server
  scripts/fetch-swatch.mjs     CLI importer
  scripts/lib/supplier.mjs     scan, safe fetch, save to catalog
  scripts/lib/plan-ai.mjs      Claude plan generation
  viewer/index.html            app shell (import map pins three@0.186.1, three-gpu-pathtracer@0.0.27)
  viewer/js/roof-geometry.js   planes, edge classification, layer meshes, nails, caps
  viewer/js/layers.js          layer stack, reveal shader, explode, cutaway, takeoff
  viewer/js/build.js           plan format, generator, player
  viewer/js/textures.js        procedural PBR textures, photo processing
  viewer/js/house.js           demo houses
  viewer/js/render.js          sun, sky, tiled snapshots, path tracing
  viewer/js/labels.js          exploded-view callouts
  viewer/catalog/              catalog.json + swatches/
  viewer/plans/                build plans
```
