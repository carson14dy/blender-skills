# Project: Sioux Falls supplier studio

**Goal:** put real products from the two Sioux Falls stores on the 3D roof, in their real colors and sizes, and turn the measured roof into a priced materials list. Build it in the studio first (`roof-visualizer/`, then Blender); once it holds up, port it to the Rooftec app under that app's design rules.

**Status:** plan written 2026-11-16 (cloud). Done since, all in the cloud on 2026-11-16:
- step 015, data intake: 453 roof products, 337 priced (338 until step 016 dropped a 9,999,999.99 placeholder price);
- the studio's Project tab has a Job section: Sioux Falls is the default location, and a line shows the store prices loaded;
- **step 016**, the store picker with sampled colors: 363 of 363 drawn products have a hex, and no store image is stored or loaded;
- **step 017**, the priced list for both stores, with crew view and CSV. The ranch demo matches the hand check: Menards $6,746.27, Home Depot $6,533.59, lowest per line $6,431.38, all incomplete until nails and deck sheets are typed;
- **step 018**, project files: Save then Open is identical, and changed store prices are flagged;
- **step 019, texture part:** Pro-Rib, Pro-Snap and corrugated textures at measured spacing (ribs 9.00 in. on centre);
- **step 022, read-only:** tap a roof plane for its area, pitch, facing and covering.

Open: 019 geometry with 020 (cloud, then local), 021 Blender look-dev (local), 023 data gaps and price refresh (pricing session), and the port to the Rooftec app.

---

## 1. What we have

| Source | What it is | Numbers | Where |
|---|---|---|---|
| Menards, Sioux Falls West #3064 | full roofing catalog, built for a 3D studio | 416 products; 294 assets to model (58 P1, 123 P2, 110 P3, 3 color-sample refs; 122 catalog-only); 567 color materials; 854 variants; 2,613 spec lines; 754 PDFs and links | `lab/data/suppliers/menards-3064-2026-11-15/` (CSV + the package's HANDOFF.md) |
| Home Depot #4301, 2523 S Louise Ave | full roofing and exterior catalog with prices and stock | 2,763 products, 2,489 priced, 581 with color swatches, 254 in stock at the store | PR #3, branch `claude/stoic-keller-boixwx`, `handoffs/sioux-falls-material-prices/homedepot/materials.json` |
| Rooftec design session | the app's design directions and product rules | lead direction "Clarity": light, system font, split view, "tap the roof", to-scale roof plans whose sections are the controls | handoff only; the app repo (`SiouxFallsApp`) is not in this lab |
| This lab | the studio, measurements, layers, Blender pipeline, `blender-suite` skill | ranch demo 27.4 squares, hand-checked | `roof-visualizer/`, `roof-blender/`, `.claude/skills/blender-suite/` |

Facts that shape the plan:
- **Prices are snapshots.** Menards: Nov 15, 2026; its 11% mail-in rebate ended that day. Home Depot: Nov 15–16. Re-capture before anyone quotes from them.
- **Units differ:**
  - shingles are per bundle (Menards 32.8 sq ft; Home Depot states coverage in the name, for example "33.33 sq. ft. per Bundle");
  - Menards steel panels are "starting at" per 100 sq ft;
  - most other items are each.
- **Gaps:**
  - 274 Home Depot items have no online price ("Browse Only").
  - Menards read 250 of 416 detail pages before its bot protection stopped the capture. Six P1 assets lack specs.
  - Menards spec tables contain errors, which the manifest's Dimension check column flags.
  - Atlas shingle sizes (42" x 14", 6" exposure) look like bundle sizes. Confirm them on the Atlas spec sheet.
- **Images:** product photos and swatches belong to the stores and manufacturers. They are linked, never committed (repo rule 5). Home Depot photos are not tileable textures, so they suit a picker and color matching only.

## 2. Decisions (defaults; change any of them)

| Question | Decision | Why |
|---|---|---|
| Where does it run first? | The web studio (three.js), then Blender for marketing renders | The studio already has layers, takeoff and photo materials; Blender reuses the plan JSON |
| Which products first? | P1: shingle fields, steel panels (Pro-Rib, Pro-Snap), cedar shakes, hip & ridge, drip edge, rake trim, metal ridge caps, ridge vents. Then P2 (starter, valleys, flashing, pipe boots, vents, gutters) | P1 is what a homeowner sees; 58 assets reduce to about 9 parametric systems |
| Build style | Systems, not one-off models: one parametric generator per system, and colors as material swaps | Matches the Menards build plan and the studio's existing generators |
| Colors | A hex color per swatch, computed once from the swatch image. The hex values are committed; the images are not | Real colors without storing anyone's images. **Approved by the user, 2026-11-16** |
| Shingle bundles | From each product's stated coverage: 30 squares of Duration is 92 bundles at 32.8 sq ft each, not a flat 3 per square (90). Heavy designer lines differ more: GAF Grand Sequoia covers 20 sq ft, so 5 bundles a square | Coverage is printed on every bundle; a flat 3 per square under-orders |
| Which price to show | The shelf price. The rebate is a separate line marked "mail-in, ended 11/15" | A rebate is a store credit, not a checkout price |
| Missing price | "no price: ask the store", never $0; a list with any unpriced item shows "total incomplete" | Rooftec rule: unknown is never zero |
| Measured or estimated | Each line says where its quantity comes from: measured from the roof, or an allowance such as waste or deck repair | Rooftec rule: only measured values reach the customer |
| Crew view | A switch that hides every price | Rooftec rule: the crew never sees prices |
| Which store | Both side by side, with the cheaper one per line highlighted. **Confirmed by the user, 2026-11-16** | Both are 10 minutes apart in Sioux Falls |
| Location | New projects default to Sioux Falls, SD (43.54 N) for the sun | Every job here is local |

## 3. Steps

Each step is one lab experiment with its own folder and write-up. Times are estimates.

| # | Step | Session | Time | Done when |
|---|---|---|---|---|
| 015 | **Supplier data intake:** normalize both stores into one studio catalog, mapped to layer ids, with units and coverage parsed | cloud | 1.5 h | **done**, see `lab/experiments/015-supplier-intake/` |
| 016 | **Product picker with real colors:** Materials tab, "Sioux Falls stores" list. Filter by layer, store and brand; show color chips; apply a product to its layer at its real exposure and size | cloud | 3 h | a Menards Duration and a Home Depot shingle each render in their own color, with screenshots |
| 017 | **Priced materials list:** each takeoff line gets a product, a quantity in the store's unit (bundles from coverage, rolls, pieces) and a price. Totals per store, the Rooftec rules above, a crew view and a CSV download | cloud | 3 h | ranch demo: hand-checked quantities for every line; 30 sq of Duration gives 92 bundles |
| 018 | **Project files:** New, Save and Open a project as JSON (house, pitch, products per layer, waste, stores, price snapshot date). Sioux Falls defaults | cloud | 2 h | a saved project reopens identically; the snapshot date shows on the list |
| 019 | **Steel panel profiles:** Pro-Rib (36" coverage, 9" ribs, 3/4" rib) and Pro-Snap (16", 3/4" seam) as geometry in the web studio and `roof_core.py`; metal ridge cap and rake trim | cloud, then local | 3 h + 30 min | panel spacing measured in a close-up matches the spec |
| 020 | **Edge profiles from product names:** drip edge Style C and D, gutter apron and rake trim cross-sections from the parsed sizes (for example 1-3/4" x 1-3/4") | cloud | 2 h | `roof_qa.py` passes, and a close-up matches each profile |
| 021 | **Blender look-dev and renders:** P1 products in Cycles with `blender-suite` (`blender-pbr-materials`, `scene_mood.py --time golden`), on the GPU | local | 2 h | one golden-hour still per store's best-selling shingle, timing logged |
| 022 | **"Tap the roof":** tap a roof plane to see its measured area and pitch and its product, and to change it (Clarity's interaction) | cloud | 3 h | works with a mouse and on a phone; screenshots at 3 widths |
| 023 | **Data gaps and refresh:** Atlas spec sheets; the six Menards P1 gaps from manufacturer PDFs; a refresh before any real quote | pricing session or by hand | — | gaps listed in the catalog are closed |

**Port to the Rooftec app** after 016–018 hold up, in a separate session in `SiouxFallsApp`, following its Clarity rules and `docs/spec/constants.md`. Leave app settings such as waste, markup and the unset MAT/PRC constants to the app. The studio only shows its own estimates and labels them that way.

## 4. Layer mapping (used by 015)

| Studio layer | Menards (3D asset class or product type) | Home Depot (category plus name) | Quantity rule |
|---|---|---|---|
| `covering` shingle | Roof field: asphalt shingle | Roof Shingles, not hip/ridge or starter | bundles = squares x (1 + waste) x 100 / sq ft per bundle |
| `covering` metal | Roof field: metal panel, stone-coated steel | Roof Panels & Metal Roofing (panels) | squares, or panels from coverage width and run length |
| `covering` shake | Roof field: wood shake/shingle | Roof Shingles with "shake" in the name | bundles from coverage |
| `ridgeCap` | Linear profile: hip & ridge, ridge cap (metal) | Roof Shingles with "hip" or "ridge" in the name | LF (ridges + hips) / LF per bundle |
| `starter` | Linear profile: starter | Roof Shingles with "starter" in the name | LF (eaves + rakes) / LF per bundle |
| `underlayment` | Layer: underlayment (synthetic, felt) | Roof Underlayments (synthetic, felt) | area / roll coverage |
| `iceWater` | Ice and Water Barrier | Roof Underlayments (peel & stick, ice & water) | ice area / roll coverage |
| `dripEdge` | Linear profile: eave/drip edge, rake/gable trim | Roof Flashing, drip edge | LF / piece length |
| `ridgeVent` | Linear profile: ridge vent | Roof Vents, ridge | LF / piece length |
| valleys (P2) | Linear profile: valley | Roof Flashing, valley | LF / piece length |
| `deck` | not in either roofing catalog | not in either roofing catalog | "no price: lumber is not in this data" |

## 5. Open questions (yours)

None open. Answered 2026-11-16:
1. **Swatch colors:** yes. Download the chips, keep only one hex color each, never commit the images.
2. **Stores:** both side by side.

**Tools for this project:**
- `graphify` builds a code map: run `graphify update .`, then `graphify query "<question>"`. Use it before grepping.
- The `blender-suite` skill (`.claude/skills/blender-suite/`) handles Blender work. It is also packaged as `blender-suite.skill` for claude.ai.

## 6. Not in this project
- The Rooftec app's four tools (Inbox, Schedule, Notes, Website stats) and its server plan: that question is owed to you by the design session, not this one.
- Installing the design session's skill package (impeccable, apple-design and others): only if 022 needs it, with your OK, because Impeccable's hook edits `~/.claude/settings.json` and its launcher downloads and contacts impeccable.style.
- ABC Supply prices: account-only; add them when you have a branch quote.
