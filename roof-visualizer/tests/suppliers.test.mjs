// Supplier catalog: parsing helpers and the built Sioux Falls catalog (lab project sioux-falls-studio, step 015).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { parseCSV, coverageFromName, parseCoverage, pieceFeet, homeDepotLayer } from '../scripts/lib/supplier-catalog.mjs';

const catalog = JSON.parse(fs.readFileSync(new URL('../viewer/catalog/suppliers/sioux-falls.json', import.meta.url), 'utf8'));

test('CSV parser handles BOM, quotes, commas and newlines', () => {
  const rows = parseCSV('﻿a,b\n"x, y","say ""hi""\nthere"\n1,2\n');
  assert.deepEqual(rows, [{ a: 'x, y', b: 'say "hi"\nthere' }, { a: '1', b: '2' }]);
});

test('coverage and piece length come out of names and spec text', () => {
  assert.deepEqual(coverageFromName('Royal Sovereign 3-Tab Roofing Shingles (33.33 sq. ft. per Bundle)'), { sqft: 33.33 });
  assert.deepEqual(coverageFromName('Seal-A-Ridge Hip and Ridge Cap Roofing Shingles (25 lin. ft. per Bundle)'), { lf: 25 });
  assert.deepEqual(coverageFromName('MS-300 36 in. x 66 ft. Ice and Water Armor Underlayment'), { sqft: 198 });
  assert.deepEqual(coverageFromName('3 ft. x 36 ft. (100 sq. ft.) Coverage SBS Self-Adhered'), { sqft: 100 });
  assert.deepEqual(parseCoverage('31 linear foot'), { lf: 31 });
  assert.equal(parseCoverage('Custom square foot'), null);
  assert.equal(pieceFeet('1-3/4" x 1-3/4" x 10\' White Steel Roof Edging- Gutter Apron'), 10);
  assert.equal(pieceFeet('12 ft. Aluminum Matte Black Drip Edge Flashing'), 12);
  assert.equal(pieceFeet('Air Vent 11 in. x 240 in. Rolled Ridge Vent in Black with Nails'), 20);
  assert.equal(pieceFeet('Shinglevent II 1.4 in. x 14 in. x 48 in. Ridge Vent in Black with Nails'), 4);
});

test('Home Depot names map to the right layer', () => {
  const m = (category, name, subcategory = category) => homeDepotLayer({ category, subcategory, name });
  assert.equal(m('Roof Shingles', 'Seal-A-Ridge Charcoal Hip and Ridge Cap Roofing Shingles').layer, 'ridgeCap');
  assert.equal(m('Roof Shingles', 'Pro-Start 120 lin. ft. Eave and Rake Roofing Starter Strip Shingles').layer, 'starter');
  assert.equal(m('Roof Underlayments', 'WeatherWatch 200 sq. ft. Mineral-Surfaced Peel and Stick Roof Leak Barrier').kind, 'iceWater');
  assert.equal(m('Roof Underlayments', 'Euroband 8.86 in. x 32 ft. 23.63 sq. ft. Ice and Water Guard').kind, 'flashingTape');
  assert.equal(m('Roof Underlayments', '2 gal. Trowelable Chimney Crown Repair'), null);
  assert.equal(m('Roof Shingles', 'Roofing Combo: Shingles, StormGuard, Pro-Start, FeltBuster'), null);
});

test('built catalog: both stores cover every priced roof layer, and no price is zero', () => {
  const layers = ['covering', 'ridgeCap', 'starter', 'underlayment', 'iceWater', 'dripEdge', 'ridgeVent'];
  for (const store of Object.keys(catalog.stores)) {
    for (const layer of layers) {
      const priced = catalog.products.filter((p) => p.store === store && p.layer === layer && p.price?.shelf > 0);
      assert.ok(priced.length > 0, `${store} has a priced ${layer}`);
    }
  }
  for (const p of catalog.products) {
    assert.ok(['covering', 'ridgeCap', 'starter', 'underlayment', 'iceWater', 'dripEdge', 'ridgeVent', 'valley'].includes(p.layer), p.id);
    if (p.price) for (const k of ['shelf', 'sale', 'rebate', 'afterRebate']) if (k in p.price) assert.ok(p.price[k] > 0, `${p.id} ${k}`);
    for (const u of [p.image, p.url, ...(p.colors || []).map((c) => c.swatch)].filter(Boolean)) assert.match(u, /^https:\/\//, `${p.id}: images stay links`);
  }
});

test('shingle bundles follow the stated coverage (Menards Duration: 30 squares = 92 bundles at 32.8 sq ft)', () => {
  // heavy designer shingles cover less per bundle (GAF Grand Sequoia: 20 sq ft, 5 bundles a square)
  const shingles = catalog.products.filter((p) => p.layer === 'covering' && p.category === 'shingle' && p.coverage?.sqft);
  assert.ok(shingles.length >= 25);
  for (const p of shingles) assert.ok(p.coverage.sqft >= 14 && p.coverage.sqft < 40, `${p.id}: ${p.coverage.sqft} sq ft per bundle`);
  const duration = catalog.products.find((p) => p.store === 'menards-3064' && /Duration® Designer/.test(p.name));
  assert.equal(duration.price.per, 'bundle');
  assert.equal(Math.ceil((30 * 100) / duration.coverage.sqft), 92);
});
