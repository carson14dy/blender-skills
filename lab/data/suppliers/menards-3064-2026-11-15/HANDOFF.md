# Menards roofing: 3D studio handoff

**Captured:** November 15, 2026, from menards.com with the **Sioux Falls West** store (#3064) selected.
**Source:** https://www.menards.com/main/building-materials/roofing/c-5809.htm and its 10 subcategory pages.
**Replaces:** `menards_roofing_handoff.zip` (79 rows from 2 of 11 pages). This package covers every roofing product on the site.

## 1. What this is for

The goal is a 3D studio: roof models where a real Menards product, in a real color, can be put on the roof and swapped. That could be a configurator, renders or a quoting view. This package gives the studio everything it needs from Menards' side:

- **what to build** (`3d/asset_manifest.csv`, 294 assets in priority order);
- **how big each piece is** (dimensions from Menards' specs, or from the product name when specs weren't available);
- **what colors each comes in** (`3d/material_library.csv`, 567 color materials with swatch links);
- **what it costs and how it's sold** (price, rebate, unit, coverage per bundle or roll, SKU), so a 3D roof can produce a materials list.

## 2. What's in the package

| File | What it is |
|---|---|
| `menards_roofing_catalog.xlsx` | **Start here.** Everything below in one workbook: Products, 3D asset manifest, Materials, Variations, Specs, Documents, Summary, Coverage, Facets. |
| `3d/asset_manifest.csv` | One row per product to model: asset ID, priority, asset class, geometry approach, dimensions, a dimension check, color and variant counts, reference image, spec and install PDFs. |
| `3d/material_library.csv` / `.json` | One row per color of each modeled product: material ID, swatch links (small and large), material type, starting PBR values. |
| `data/products.csv` | All 416 products: subcategory, product type, brand, SKU, model, price block, unit, availability, key dimensions, materials, ratings, links, notes. |
| `data/variations.csv` | Every color, length and size option found (854), with swatch image links. |
| `data/specs_long.csv` | Every spec line from every product page read (2,613 lines). |
| `data/documents.csv` | 754 links: technical spec sheets, install guides, warranties, safety data sheets, color charts, product videos. |
| `data/products_full.json` | Listing and detail data together per product, for code. |
| `raw/` | The captures exactly as read from the site (see `raw/README.md`). |
| `scripts/` | How it was captured and rebuilt, plus `swatch_colors.py` (optional, see section 5). |

## 3. The catalog at a glance

| Subcategory | Products | Value after rebate | 3D: P1 / P2 / P3 / not modeled |
|---|---|---|---|
| Asphalt Shingles | 19 | $19.57 – $78.85 | 16 / 3 / 0 / 0 |
| Steel Roofing | 91 | $2.49 – $420.96 | 23 / 26 / 28 / 11 |
| Wood Shakes & Shingles | 6 | $14.99 – $177.99 | 6 / 0 / 0 / 0 |
| Roofing Panels | 22 | $10.40 – $502.78 | 0 / 14 / 7 / 1 |
| Low-Slope | 55 | $9.78 – $1,245.11 | 0 / 15 / 2 / 38 |
| Underlayment | 17 | $12.45 – $154.86 | 0 / 0 / 17 / 0 |
| Ventilation | 62 | $2.13 – $786.72 | 5 / 22 / 3 / 32 |
| Roof Edge & Tools | 27 | $5.59 – $66.65 | 8 / 3 / 7 / 9 |
| Metal Coil & Flashing | 58 | $2.10 – $230.49 | 0 / 40 / 18 / 0 |
| Roof Coatings | 37 | $2.64 – $1,067.11 | 0 / 0 / 9 / 28 |
| Specialty Roofing (other) | 22 | $3.85 – $150.82 | 0 / 0 / 19 / 3 |
| **Total** | **416** | | **58 / 123 / 110 / 122** (+3 color-sample references) |

Price ranges are per unit, and units differ: shingles are per bundle (32.8 sq ft), cut-to-length steel panels are "starting at" per 100 sq ft, most other items are each. 56 brands are represented.

**Priorities.** **P1** is the roof field and the pieces that frame it: shingles, steel panels, stone-coated steel, cedar shakes, hip & ridge, drip edge, rake trim, metal ridge caps and ridge vents. **P2** is what's visible on most roofs: starter, valleys, step/wall flashing, pipe flashings, vents, gutters, snow guards, corrugated panels and low-slope membranes. **P3** is rarely visible or for cutaways only: wall trim, closures, underlayment, trim coil and coating finishes. **Not modeled** covers tools, sealants, adhesives, fasteners, patches and cleaners; they stay in the catalog for materials lists.

## 4. Build plan for the studio

Build systems, not 294 one-off models. The 58 P1 assets reduce to a handful of parametric systems. Colors are material swaps.

**1. Roof-field systems (P1)**

| System | Products | Key numbers (Menards' spec tables) |
|---|---|---|
| Asphalt shingle courses | 11 lines: Owens Corning Duration, Duration Designer, Duration STORM, Duration Flex, Oakridge, Supreme 3-tab; Atlas Pinnacle Pristine, Pinnacle Sun, Castlebrook, StormMaster Shake, Briarwood Pro | OC architectural: 39-3/8" × 13-1/4", 5-5/8" exposure. OC Supreme 3-tab: 36" × 12", 5" exposure. Atlas lines list 42" × 14" with 6" exposure, which matches the bundle more than the shingle, so **confirm on the Atlas spec sheet**. 32.8 sq ft per bundle (3 bundles per square). |
| Steel panel profiles | Pro-Rib (36" coverage) and Pro-Snap (16" coverage), each in standard, Premium, Designer Matte and Multitone versions, plus Realtree camo | Pro-Rib: 38" overall, ribs 9" on center, 3/4" rib height, 29 ga (Premium and Designer Premium are 28 ga). Pro-Snap: 17.5" overall, 3/4" seam height. Sold cut-to-length per 100 sq ft, or precut in 8'–16' lengths (each). |
| Stone-coated steel | Roser SteelGUARD (5 sq ft panels) plus its rake channel, side flashing and hip & ridge | Detail pages for the trim pieces were blocked (section 6); use the spec sheet. |
| Cedar shakes and shingles | 18" and 24" Western Red Cedar shakes (medium, heavy), 18" perfection shingles, 16" undercourse | Lengths and butt thickness from specs; widths are random, so randomize. |

**2. Linear-profile library (P1, then P2)**

Build a cross-section per part and sweep it along roof edges:
- drip edge (Style C and D), gutter apron and roof edge;
- rake and corner & gable trim;
- metal ridge caps;
- hip & ridge shingles, which are instanced, not swept;
- ridge vents, valleys and starter.

The edge profiles' sizes are in the product names ("2-3/8" × 1-11/16" × 12'"), and the manifest's **Size in product name** column has them parsed. Menards' spec tables often list metal thickness as "height" for these parts, so trust the name for the profile.

**3. Objects (P2)**

Static, power and turbine vents; pipe flashings and boots; snow guards; gutter fittings. Each manifest row links a reference image and usually a spec sheet.

**4. Materials**

`3d/material_library.csv` has one row per color, with the swatch link and starting PBR values by material type: asphalt granule, painted metal, matte paint, galvanized, copper, polycarbonate, cedar, EPDM, TPO, and so on. The PBR values are general look-dev starting points, not manufacturer data. Tune each one against its swatch and product photo.

**Suggested conventions** (change them if the studio has its own):
- Use the asset and material IDs from the manifest (`RF_…` roof field, `LP_…` linear profile, `LO_…`, `OB_…` objects, `LY_…` layers, `MT_…` material-only).
- Data is in inches. Model in meters: 1 in = 0.0254 m.
- Roof-field systems run up-slope along +Y with the eave at the origin. Linear profiles extrude along +X. Objects sit with their base flange on the roof plane at the origin.
- Keep source files as `.blend`, export glTF 2.0 (`.glb`) for web or app use, and keep textures at 2K PNG/JPG.
- Track progress in the manifest's **Build status** column.

**Pricing hook.** Every manifest row carries SKU, unit, coverage and value after rebate. A roof area therefore turns into a list. For example, 30 squares of Duration is 90 bundles at $40.99 = $3,689.10 after rebate, before tax, waste and accessories. Prices are a one-day, one-store snapshot (section 6), so re-capture before quoting anyone.

## 5. Optional: swatch colors

`scripts/swatch_colors.py` downloads each material's swatch into `textures/swatches/`. It then fills `base_color_hex` with the swatch's median color and writes `3d/material_library_with_colors.csv`. Run it from the package folder:

```bash
pip install pillow
```

```bash
python scripts/swatch_colors.py --only P1
```

The first command installs the image library. The second does the P1 assets only; drop `--only P1` for all 567. Swatch photos belong to Menards and the manufacturers, so use them as internal reference only. If Menards refuses the downloads (HTTP 403), open the `swatch_large` links in a browser instead.

## 6. Read before relying on it

1. **Product detail pages: 250 of 416 read.** Menards' bot protection (Incapsula) began refusing page reads after 250. The capture stopped there instead of working around it. The other 166 still have full listing data: price, rebate, unit, availability, image and the colors shown on the listing tile. They don't have the spec table, the full color list, PDFs or bundle coverage. The **Detail page read?** column marks them. Six P1 assets are affected: the Style-A galvanized roof edge, the cedar hip & ridge cap, the Multitone universal ridge cap, and the three Roser stone-coated trim pieces.
2. **Color lists can be partial.** Product pages embed at most 12 options per list (48 lists stopped at exactly 12), and blocked products only show the 4–5 colors on the listing tile. Compare **Colors listed** with **Variants on site**; where they differ, open the product page or the color chart in `data/documents.csv`.
3. **Menards' spec tables have errors.** Examples: a ridge vent listed as 240" tall, a zinc strip as 85" tall, an Atlas hip & ridge 36" wide by 12" long. The manifest's **Dimension check** column flags the obvious ones, and 25 P1/P2 assets have no dimensions at all. For anything P1, the manufacturer's spec sheet (linked) beats the Menards table.
4. **Store and date.** These are Sioux Falls West prices on November 15, 2026. Listing and detail prices agreed on all 247 products where both were read. Sale prices run through 11/26/26, but the **11% rebate captured ended 11/15/26**, so next week's rebate may differ. The rebate is a mail-in store credit, not a checkout discount.
5. **One row = one listing tile.** Many tiles stand for a family of colors or lengths. The price is for the variant shown, or a "starting at" price (steel panels). Seven products had no price at this store; "check another store" items such as Atlas Briarwood Pro are among them.
6. **Images and swatches** are linked, not included. They belong to Menards and the manufacturers.

## 7. Open questions for the owner

- **Target:** what will the studio run in (Blender renders, a web viewer such as three.js, or a game engine)? That decides polygon budgets and texture formats.
- **Scope:** model P1 only first, or P1 + P2? P1 alone is 58 assets but about 9 systems.
- **Finish the capture:** the 166 missing detail pages and full color lists need another capture session on a later day. If the site still refuses, fill P1 gaps from manufacturer spec sheets by hand.
- **Swatches:** OK to download them for internal look-dev (section 5)?

## 8. Rebuilding

`scripts/capture_in_browser.md` explains how the data was read. Rebuild the outputs from `raw/` with:

```bash
python scripts/build_catalog.py raw .
```

```bash
python scripts/build_3d_and_workbook.py .
```

Both need Python 3 and `openpyxl`.
