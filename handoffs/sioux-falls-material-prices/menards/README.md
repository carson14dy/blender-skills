# Menards Roofing: Price Snapshot (Partial)

Captured: November 15–16, 2026
Source: https://www.menards.com/main/building-materials/roofing/c-5809.htm and its subcategory pages

## What's in this package

| File | What it is |
|---|---|
| `menards_roofing_products.xlsx` | Main deliverable. **Products** sheet (79 rows, filterable, grouped by product type), **Summary** sheet (counts and price ranges by group), **Coverage** sheet (which subcategories were and weren't captured, and why). |
| `menards_roofing_products.csv` | The same product table as plain CSV, for importing into anything. |
| `raw/` | The page text exactly as captured, so anyone can check a row against its source. |
| `scripts/` | The parser (`parse.py`) and workbook builder (`build.py`) used to turn the raw text into the table. |

## Columns

- **Product group**: assigned from the product name (Shingles, Metal roofing panels, Underlayment, Trim coil, Valley, flashing types, Drip edge/trim). Rows marked "Other / unknown" are prices whose product name didn't come through.
- **Menards SKU**: present when the page showed it.
- **Price type**: `sale` or `regular`, as labeled on the page.
- **Price / 11% rebate / Value after rebate**: the shelf price, the mail-in rebate, and the price after the rebate. The 11% rebate is a mail-in **store credit** for future in-store purchases, not a discount at checkout. When the page didn't show value after rebate, it was computed as price − rebate (see Notes).
- **Starting at? / Unit**: metal panels and coil are priced "starting at" per 100 sq. ft. or per linear foot. Others are each, per bundle or per roll.
- **Notes**: variation counts ("24 Variations Available"), shipping flags, quantity rules, "price not captured".
- **Duplicate of row**: some items appear on both the main page and the flashing page.

## Important caveats

1. **This is not the full roofing catalog.** Only 2 of the 11 roofing pages loaded with products, and each of those gave only the first page of its product grid. See the **Coverage** sheet. Menards blocks automated requests from the server this was run on (it returns HTTP 403 even for robots.txt). The third-party page readers used got through only some of the time, and could not render most subcategory grids.
2. **Store and region.** Menards prices are set per store. The pages were read without choosing a store, and the site defaulted to **Council Bluffs, IA**. Sioux Falls, SD store prices may differ. Prices also change weekly with sales.
3. **Possible stale copy.** One of the readers serves cached copies of pages, so a price may be a few days old. Confirm prices before quoting.
4. **Row alignment.** Product names and prices were matched by their order in the page text. Where the page dropped a name or a price, the row is flagged ("name not captured" / "price not captured"), but spot-check important items against `raw/`.
5. **Hidden prices.** Some manufacturers don't let Menards show the lowest price until the item is in the cart (minimum advertised price). Those items may be missing or show a higher price here.
6. **Variations.** Many rows stand for a family of colors, lengths or gauges ("144 Variations Available"). The price shown is for the variant on the tile, or the "starting at" price.

## How to finish the pull (recommended)

- **Quickest and most accurate:** on your own computer, open menards.com, set your store to Sioux Falls, and go through each subcategory listed on the Coverage sheet (Shingles, Metal Roofing, Underlayment, Ventilation, Roof Coating, Low-Slope, Specialty, Edge/Tools). Menards' "My Lists" feature can collect items and their prices in one place.
- **For contractor or volume pricing:** call the Sioux Falls Menards Pro/Contractor desk with a materials list. They can quote quantity pricing that doesn't appear online.
- Compare against ABC Supply once the Sioux Falls branch quote or account is set up.
