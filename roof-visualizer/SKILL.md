---
name: roof-visualizer
description: Interactive 3D roof visualizer (Roof Layer Studio) for roofing sales and production. Swap the roof covering for any supplier product or photo at real-world scale, toggle and change every roofing layer, play an animated build from tear-off to finish, open an exploded "layers view" with labels, and export 4K/8K stills or path-traced renders. Trigger when asked to show a homeowner a new roof color or material, compare shingle options, pull a product image from a supplier, show the roof layers, animate or explain the installation step by step, make an exploded roof diagram, or measure squares and order quantities from a 3D house.
---

# Roof Layer Studio (roof-visualizer)

A browser app (Three.js, MIT) that rebuilds a roof as real layers on top of a 3D house:

| Layer (bottom to top) | Built from |
|---|---|
| Existing shingles + felt | the whole roof, used for the tear-off |
| Roof deck (OSB / plywood, 4x8 sheets) + repair allowance | every roof plane, with edge thickness; the number of replacement sheets is an input |
| Drip edge | eaves (under ice & water) and rakes (over underlayment) |
| Ice & water shield | rows at the eaves (auto: enough to reach 24" inside the exterior wall, from the overhang and pitch) plus 36" centered in valleys, applied after the eave rows |
| Underlayment | synthetic gray/blue/black or #30 felt |
| Starter strip | eaves and rakes |
| Fasteners | every nail on the nail line, 4 per shingle (6 for high-wind zones) |
| Shingles / metal / tile / slate / shake | course-by-course stepped geometry at the product's exposure |
| Ridge vent, hip & ridge cap | ridge and hip lines found from the geometry |

Every layer is built in each plane's own eave-aligned frame, so shingle courses run parallel to the eaves on hips and valleys, and textures sit at their true size (a 36" swatch covers 36" of roof).

## Run it

```bash
cd roof-visualizer && npm install && npm start
```

`npm start` runs `scripts/serve.mjs` (Node 18+, binds to 127.0.0.1:8080) and opens the browser. `npm install` is only needed for Claude-written build plans (`@anthropic-ai/sdk`, optional). The viewer also works as static files (any web server, or the published artifact) without the supplier scanner and Claude plans.

Tests: `npm test` (build player, plan files, supplier parser, SSRF guard, store catalog and colors, render recipes, priced list, project files).

## What the user can do

- **Materials tab** (default): a drill-down browser, suppliers > projects > material types > products (`viewer/js/materials-taxonomy.js`).
  - Suppliers: Menards #3064, Home Depot #4301, All suppliers (both side by side), Studio samples (built-in looks and photos). Catalog: `viewer/catalog/suppliers/sioux-falls.json`, plus `suppliers/solar.json` for solar.
  - Projects: Roof, Roof accessories, Underlayment, Gutters, Solar. Each material type says which line of the List it fills, or that it is listed for reference only.
  - A product list has search, Filters and Sort (recommended, price, unit price, name, brand, in stock). "On your list" shows the chosen product per store. "On roof" in the header picks which store's products are drawn.
  - Rows show a color chip from the sampled palette (hatched when not sampled), price with unit, coverage and stock. Tap a row to choose it for its store; the chosen row lists its colors. Back, Escape or Alt+Left goes up a level.
  - No store image is loaded, only CSS chips, so it works offline and in an artifact. A new job starts with a suggested basket per store, tagged "suggested". The List tab's product names and "Change product" jump to the right list.
- **Solar** (`viewer/js/solar.js`, data in `viewer/catalog/solar.json`): panel arrays laid on the real roof planes, dragged and grown with a corner handle, with an install timeline (mounts, rails, panels, wiring), monthly generation from a PVGIS table for Sioux Falls by tilt and facing, bill savings, and parts and install prices.
- **Materials tab, Built-in and photos**: built-in procedural products (architectural laminate in 7 colors, 3-tab, standing seam in 4 colors, clay tile, slate, cedar shake) and imported supplier products. "Fit to roof" adjusts scale, rotation, course-line alignment, relief and tint; photos also get width in inches, brightness, contrast, saturation and seamless blending. Normal and roughness maps are generated from the photo.
- **Add supplier product:**
  - Paste a supplier product page or pick a file, choose the swatch, name it and confirm rights. It is saved into `viewer/catalog/` and applied.
  - A photo dragged onto the 3D view is only tried for that session; nothing is saved without the rights confirmation.
  - For photos, set the photo width, the course exposure visible in the photo, and whether the courses are drawn in 3D.
- **Layers tab:**
  - Show or hide each layer, and change products per layer: deck and repair allowance, underlayment, ice & water type and rows, valleys, drip edge colour, nails per shingle, ridge vent.
  - Add custom layers (radiant barrier, insulation board, etc.).
  - Read the measurements: squares, a waste allowance suggested from the hips and valleys, LF of eaves, rakes, ridges, hips, valleys and ridge vent (0.3 m off each end of each ridge), ice & water area and rows, field nails and the deck repair allowance. Order quantities and prices are on the List tab.
  - Measurements are checked against hand calculations in `tests/geometry.test.mjs`.
- **List tab:** the priced materials list for both stores (`viewer/js/quote.js`).
  - Each line shows the measured basis, the allowance and who sets it. Each store cell shows product, quantity in the store's unit (bundles from coverage, rolls, pieces, cartons), unit price, line total and a "lower" tag.
  - Totals: per store and lowest per line, each "incomplete", "at least" or complete. The Menards rebate is shown apart and never subtracted. The capture dates are always shown.
  - Unknowns show a dash with the reason and who sets it, never a zero. Type a price, a coverage, or an amount for the nails and deck repair lines.
  - Controls: Waste %, valley metal, Crew view (one store, no prices at all; `?view=crew` locks it).
  - Buttons: Open full list (both stores side by side), Download CSV, Download crew CSV, Copy as text.
- **Tap the roof:** a short tap on a roof plane shows its area, pitch, facing and covering, with "Change product". A drag still orbits.
- **Layers view** (toolbar, key E): layers float apart with a spacing slider and callout labels; press again to close them back down.
- **Cutaway** (key C): stepped cut from the right side of the current view showing every layer at once.
- **Before** (key B): the existing roof; press again for the new roof.
- **Watch build** (Space): tear-off to finish, course by course, with captions and a slowly orbiting camera. Scrub, step, change speed in the Build tab.
- **Render tab:**
  - AgX, ACES or Neutral tone mapping, and exposure.
  - Physical sky, or a Poly Haven HDRI (CC0).
  - Path tracing (three-gpu-pathtracer, MIT). It pauses while a layer is part-built or cut away, because it can only draw whole layers.
  - Snapshots at 1080p, 4K, 8K or square, rendered in tiles (no GPU size limit) with layer labels burned in.
  - The view renders only while something changes, and phones start on Standard quality.
- **Project tab, Projects** (measured jobs): real houses listed in `viewer/houses/index.json`, each with a model, a detail file and a report. That folder is git-ignored (addresses and photos stay out of this public repo); without it the section hides itself.
- **Project tab, Project file**: job name, New (asks first when there are unsaved changes), Save (`<job>.rooftec.json`: house, sun, layers, store choices, waste, typed amounts, measurements and a price snapshot; no images), Open.
  - When the store data changed since the save, the list keeps the saved prices with "now $X" beside each changed one, and "Use current prices" switches.
- **Project tab**: house presets (ranch hip + garage gable, two-story gable, cottage hip), pitch 3/12-14/12, load a house model (.glb/.gltf, units selectable), sun by latitude, date, solar time and which way the house faces, export layers as GLB for Blender, and "Blender command" (the `roof-blender.mjs layers` and `material --palette` lines for the product on the roof).

## Using a real house model

Load a `.glb` in the Project tab (or `?glb=path/to/house.glb`); Draco, KTX2 and meshopt compression are supported.

1. Roof faces are found by mesh or material name (`roof`, `shingle`) or, failing that, by slope and height. Mirrored meshes are handled.
2. They are clustered into planes.
3. Only the roof triangles are removed from the model, so walls in the same mesh stay. The "Original roof" toggle brings the roof back.
4. Every layer is rebuilt on those planes. Name the roof mesh `Roof` in Blender/SketchUp/your capture tool for the most reliable result. Meshes named `RT_layer_*` (exported by this viewer or roof-blender) are ignored and rebuilt.

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

`?house=ranch-hip|two-story|cottage&pitch=8&product=<catalog id>&plan=plans/x.json&glb=house.glb&t=0.6&explode=1&cut=1&tab=layers|list&quality=standard|high|ultra&view=crew&today=YYYY-MM-DD`

Without `?product=`, the studio opens with the shown store's covering (Menards Duration, Sierra Gray); `?product=arch-charcoal` opens the first built-in product as before. A store metal roof's ridge cap takes the covering's metal values (metallic, roughness), so cap and panels match.

`window.roofStudio` (for Playwright scripts or demos): `ready`, `state`, `setProduct(id)`, `explode(bool)`, `cutaway(bool)`, `seek(fraction)`, `play()`, `snapshot(w, h)` (returns a blob URL), `loadPlan(obj)`, `loadHouse(url)`, `pathTrace(bool)`, `settle()`.
Store features: `suppliers()` (the store catalog), `quote()`, `project()`, `loadProject(obj)`, `pickStore(slot, productId, color)`, `showStore(storeId)`, `storeProduct(productId, color)`, `setCrewView(bool)`, `listText(crew)`, `blenderCommand()`, `tapRoof(x, y)`.
Screenshots and in-page checks of the store features: `node lab/tools/supplier-shots.mjs --url <viewer url> --out <dir> --checks`.

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

Endpoints: `GET /api/health`, `GET /api/scan?url=`, `GET /api/image?url=` (raster images only, for textures), `POST /api/swatch`, `GET /api/plans`, `POST /api/plan`.

The server answers only its own page:
- `Host` must be the loopback address and port (defeats DNS rebinding).
- A foreign `Origin` or a cross-site `Sec-Fetch-Site` is refused.
- POST bodies must be JSON. Add `--allow-host <name>` to serve it on a LAN name.

Remote fetches:
- http(s) only.
- Private, loopback, link-local and IPv6-mapped addresses are blocked. This is checked before connecting, at connect time (so DNS answers cannot switch to a private address), and on every redirect.
- Capped at 25 MB.
- `--allow-private` lifts the address check for an internal asset server.

Claude-written plans keep only the newest 20 files.

## Files

```
roof-visualizer/
  scripts/serve.mjs            local server
  scripts/fetch-swatch.mjs     CLI importer
  scripts/lib/supplier.mjs     scan, safe fetch, save to catalog
  scripts/lib/plan-ai.mjs      Claude plan generation
  scripts/build-supplier-catalog.mjs + lib/supplier-catalog.mjs   store captures -> catalog/suppliers/*.json
  viewer/index.html            app shell (import map pins three@0.186.1, three-gpu-pathtracer@0.0.27)
  viewer/js/roof-geometry.js   planes, edge classification, layer meshes, nails, caps
  viewer/js/layers.js          layer stack, reveal shader, explode, cutaway, takeoff
  viewer/js/build.js           plan format, generator, player
  viewer/js/textures.js        procedural PBR textures, photo processing
  viewer/js/house.js           demo houses
  viewer/js/render.js          sun, sky, tiled snapshots, path tracing
  viewer/js/labels.js          exploded-view callouts
  viewer/js/supplier-products.js  store product -> studio product (render recipe), layer options (pure)
  viewer/js/quote.js           priced list rules, crew view, CSV (pure)
  viewer/js/project-file.js    project files: build, validate, compare price snapshots (pure)
  viewer/js/supplier-ui.js     Materials browser, List tab, full-list dialog, project buttons, Blender command
  viewer/js/materials-taxonomy.js  suppliers, projects, material types, filters and sorts (pure)
  viewer/js/solar.js           rooftop solar designer: arrays, install timeline, generation and savings
  viewer/js/tap.js             tap a roof plane
  viewer/css/suppliers.css     styles of the store features
  viewer/catalog/              catalog.json + swatches/; suppliers/sioux-falls.json (Menards #3064, Home Depot #4301: products, units, coverage, prices; images stay links)
  viewer/catalog/solar.json    PVGIS generation table for Sioux Falls (site rounded to 0.01 degree)
  viewer/houses/               measured real jobs (git-ignored; optional)
  viewer/plans/                build plans
```
