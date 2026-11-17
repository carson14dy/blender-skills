# Handoff: Sioux Falls Roofing & Exterior Material Prices

**For:** the 3D home rendering / Roof Layer Studio session (`rooftec-lab`)
**From:** the supplier-pricing research session
**Captured:** November 15–16, 2026, Home Depot store #4301 selected on homedepot.com

## TL;DR

- **Home Depot #4301, Sioux Falls, SD (2523 S Louise Ave): 2,763 unique products** with store prices, stock at that store, product images and color variants. This is the complete dataset.
- **Menards: 79 products, partial snapshot** (Council Bluffs, IA default store). Menards blocks automated access, so it's reference only.
- **ABC Supply: no data.** Prices are account-only. The user is getting a branch quote or account separately.

## Files

| Path | Use it for |
|---|---|
| `homedepot/materials.json` | **Start here for 3D work.** One record per product: `name, brand, category, subcategory, color, price, price_per, unit_price, unit, units_per_package, availability, in_stock_sioux_falls, qty_sioux_falls, image, url, color_variants[]`. Each `color_variants` entry has `label`, `item_id`, `swatch_image` (small color chip) and `url`. |
| `homedepot/homedepot_sioux_falls_roofing.xlsx` | The same data for people: Products (filterable), Summary (counts and price ranges per category), Capture log. |
| `homedepot/homedepot_sioux_falls_roofing.csv` | Flat table, for importing anywhere. |
| `menards/` | Partial Menards snapshot: xlsx, csv, and a README with caveats. |
| `scripts/` | How the data was collected (`scrape.js`, Playwright) and built (`build.py`), so it can be refreshed. |

## Categories (Home Depot)

| Category | Unique products | In stock at #4301 | Price range | Median |
|---|---|---|---|---|
| Roof Shingles | 124 | 20 | $2.99 – $422.91 | $58.20 |
| Roof Underlayments (synthetic, felt, peel & stick, ice & water) | 70 | 7 | $30.99 – $618.00 | $108.00 |
| Roof Flashing (incl. drip edge) | 222 | 31 | $0.82 – $220.69 | $30.00 |
| Roof Panels & Metal Roofing | 226 | 7 | $7.48 – $2,369.00 | $118.40 |
| Roll Roofing | 16 | 0 | $49.98 – $185.90 | $134.00 |
| Roofing Tools | 239 | 15 | $3.98 – $6,470.16 | $68.05 |
| Commercial Roofing (coatings, sealants, cement) | 164 | 28 | $2.97 – $6,908.00 | $75.17 |
| Roof Vents (ridge, box, soffit, turbine, etc.) | 407 | 23 | $4.48 – $2,689.00 | $85.18 |
| Gutter Systems (gutters, downspouts, guards, hardware, fittings, splash blocks, tools, sealants) | 981 | 110 | $1.41 – $611.00 | $23.41 |
| Skylights (fixed, vented, solar tubes, flashing kits, shades) | 244 | 3 | $17.89 – $6,305.00 | $268.00 |
| Soffit | 43 | 4 | $14.98 – $37.98 | $24.99 |
| Fascia | 27 | 6 | $9.98 – $139.78 | $54.39 |
| **Total** | **2,763** | **254** | | |

2,489 products have an online price, and the other 274 are "Browse Only" (in-store or special order). All 2,763 have a product image. 581 have color variants with swatch chips. When an item appears in more than one category, it's filed under the most specific one (for example, soffit panels under Soffit, not Roof Vents), and "Also listed in" names the others. Large pallet and commercial quantities explain the high maximum prices.


## Notes for the material picker

- **Images:** `image` is the primary product photo at 1000 px (thdstatic CDN). Swap `_1000.jpg` for `_600` / `_400` / `_145` to get smaller sizes. These are product photos, not tileable textures. For PBR textures, keep using PolyHaven and use these photos for the picker UI and color matching.
- **Colors:** `color` is the color of the listed item. `color_variants` lists the other colors in the same product family, each with a swatch chip image and its own item number. A variant's price can differ from the listed item's; check it with the variant's `url`.
- **Pricing units:** `price` is per `price_per` (each, bundle, roll, panel...). `unit_price` / `unit` give a normalized price where Home Depot provides one, for example per piece or per sq. ft. Shingles are usually sold by the bundle, and 3 bundles cover about 1 roofing square (100 sq. ft.). The bundle's coverage is in the product name, e.g. "(33.33 sq. ft. per Bundle)".
- **Availability:** `Online` = sold online. `Shared` = online and in store. `Browse Only` = in-store or special order, usually with no online price (`price` is null; ask the store).
- **Stock:** `in_stock_sioux_falls` / `qty_sioux_falls` show store #4301's pickup inventory at capture time. It changes daily. Most items aren't stocked in the store but can be shipped or delivered.

## Caveats

- Prices are what homedepot.com showed for store #4301 at capture time. Sales change weekly. Pro/volume pricing (Pro Desk, (605) 323-2880) can be lower.
- These are retail big-box prices. Roofing-distributor prices (ABC Supply) for the same products are often different, especially for shingles by the square.
- Refresh: run `node scripts/homedepot/scrape.js <out_dir> scripts/homedepot/categories.json` (needs Playwright and Chromium), then `python3 scripts/homedepot/build.py <out_dir> <dest>`. It browses the listing pages at shopper pace with the Sioux Falls store selected.
