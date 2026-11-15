# Research tracks

What the user wants, where it stands after the first build (experiment 000), and what still has to be proven before it goes into the RoofTec app.

## T1. Pull supplier images and put them on the roof

**Goal:** pick a product from a supplier, see it on the customer's roof, and trust the color and scale.

**Now:** the importer scans a product page, saves the chosen photo with a rights note, and maps it at true size with generated normal and roughness maps. There are 15 procedural products and no licensed supplier images yet.

**Open questions**
- How close is the on-screen color to the real shingle in daylight? Needs a calibrated photo: gray card or color checker, real sample board.
- Which suppliers will give brand-portal or dealer access to swatch images? This is a business step, not code.
- Is Sobel relief from one photo good enough, or should we port an MIT photo-to-PBR shader (NormalMap-Online, Unity-WebGPU-PBR-Maps-Generator)?

**Done when:** three real products from portals or own photos are in the catalog, and side-by-side comparisons with the sample boards are signed off by the user.

## T2. Higher resolution and accuracy

**Goal:** sharper images of each change, and geometry and measurements you can rely on.

**Now:** tiled snapshots to 8K, path tracing in the browser, Cycles in Blender with stepped courses and real nails. Measurements come from the model and match hand calculations: the ranch demo is 27.4 squares (experiment 010 fixed double-counted ridges and hips and the roof hidden under the garage).

**Open questions**
- GPU timings on the user's PC: 4K raster, path tracing to 256 samples, Cycles 4K (experiment 001).
- Measurement accuracy on a real RoofTec house against its measurement report (EagleView, Hover or a hand measure).
- Does Blender's procedural shingle shader need replacing with baked textures from the web catalog? It currently reads like a brick pattern up close.

**Done when:** a real house measures within 2% of its report, and a 4K image of each product renders in under 30 s on the user's GPU.

## T3. Change layers interactively

**Now:** show or hide each layer, choose products per layer, add custom layers, cutaway, and a takeoff table.

**Open questions:** which layers and options contractors actually ask for. Missing pieces: step and counter flashing, chimneys, pipe boots, skylights, valley metal versus woven valleys, gutters as a layer, and manufacturer "system" bundles (matching starter, cap and underlayment per brand).

## T4. AI-generated build, layer by layer

**Now:** a rule-based plan generator, Claude-written plans through the local server (untested without an API key), course-by-course reveal in the web app, and MP4 output from Blender.

**Open questions:** narration (on-screen captions now; spoken voice?), realistic durations from crew data, a plan built automatically from the estimate, and length of the homeowner version versus the crew version.

## T5. Exploded layers view

**Now:** layers float apart vertically, held still, with a spacing slider and callout labels, and close back down. Burned into snapshots. Blender has an animated version.

**Open questions:** per-manufacturer labels and specs, a printable one-page "your roof system" sheet for proposals, and whether exploding along each plane's normal reads better than straight up on complex roofs.

## T6. Getting it into the RoofTec app

**Open questions:** how the app hosts the viewer (iframe, web component or link); the export format from RoofTec models (GLB? units? is the roof mesh named?); mobile performance (compress GLBs with glTF-Transform and meshopt); and where catalogs and plans live per company.

## Experiment backlog

| id | Track | Question | Session |
|---|---|---|---|
| 001 | T2 | GPU baseline on the user's PC (web and Blender) | local |
| 002 | T1 | Color accuracy: calibrated photo of a sample board versus the render | local, then cloud |
| 003 | T2/T6 | Load a real RoofTec house: plane detection, measurement versus report | local |
| 004 | T2 | Blender: bake catalog textures instead of the procedural shingle shader | cloud |
| 005 | T3 | Flashing, chimney and pipe-boot layers | cloud |
| 006 | T6 | GLB size: instance nails, meshopt compression, phone load time | cloud |
| 007 | T4 | Claude-written plans: 5 real job descriptions, review with the user | cloud with API key |
| 008 | T5 | One-page "roof system" proposal sheet from the layers view | cloud |
| 009 | T5 | Layers-view labels on narrow screens: they cover the house and the bottom one hides behind the toolbar. **Done**, see 009 | cloud |
| 010 | all | Independent review by Claude Fable 5.2, and fixes. **Done**, see 010 | cloud |
| 011 | T6 | Offline use: vendor three.js, the path tracer and the fonts; optional service worker | cloud |
| 012 | T2/T6 | Robust roof-plane detection for drone and scan meshes (region growing or RANSAC, T-junctions) | cloud, then local with a real scan |
| 013 | T1 | Supplier photo crop and perspective correction, course detection from the photo | cloud |
