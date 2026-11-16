// Supplier catalog: parsing helpers and the built Sioux Falls catalog (lab project sioux-falls-studio, step 015).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { parseCSV, coverageFromName, parseCoverage, pieceFeet, homeDepotLayer, packCount, panelCoverage, mergeColors, colorJobs } from '../scripts/lib/supplier-catalog.mjs';

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

test('catalog version 2: 453 products, 337 priced, no placeholder price', () => {
  assert.equal(catalog.version, 2);
  assert.equal(catalog.products.length, 453);
  assert.equal(catalog.products.filter((p) => p.price?.shelf).length, 337);
  assert.equal(catalog.sources.homedepot.sha256, '06040ac740d39e77');
  for (const p of catalog.products) if (p.price?.shelf) assert.ok(p.price.shelf <= 5000, `${p.id}: shelf ${p.price.shelf}`);
  assert.equal(catalog.products.find((p) => p.id === 'mn-1642874365673314').price, undefined); // VB Defender, 9,999,999.99
});

test('pack counts: pieces in one sold package, 2-100', () => {
  assert.equal(packCount('CV1 Classic Rib 3 ft. Foam Ridge Vent (4-Pack)'), 4);
  assert.equal(packCount('1.47 ft. x 3.44 ft. 20 Pack Corrugated Galvanized Metal Roof Panels'), 20);
  assert.equal(packCount('1.47 ft x 3.54 ft 10PCS Galvanized Steel Roof Panel'), 10);
  assert.equal(packCount('Shingle Over, Edge Vent, Intake Vent (Sold in Carton of 10-Pieces only)'), 10);
  assert.equal(packCount('Shinglevent II 1.4 in. x 14 in. x 48 in. Ridge Vent (Sold in Carton of 10/40 ft.)'), 10);
  assert.equal(packCount('8 ft. Corrugated Galvanized Steel 29-Gauge Roof Panel'), null);
  assert.equal(packCount('Roof Anchor 120-Pieces Load Capacity'), null);
  assert.equal(packCount('Cobra SnowCountry Ridge Exhaust Vent in Black (1-Piece)'), null);
  const vent = catalog.products.find((p) => /^Shinglevent II/.test(p.name));
  assert.equal(vent.packCount, 10);
  assert.equal(vent.pieceFt, 4); // one piece; the carton is 40 ft
});

test('coverage: bundles per square, and metal panel packs by gross area', () => {
  assert.deepEqual(coverageFromName('IKO Cambridge Asphalt Architectural Shingles - Dual Black (3 BD/SQ)'), { sqft: 33.3 });
  assert.deepEqual(coverageFromName('IKO Armour Shake Premium Asphalt Designer Roof Shingles Greystone (4 BD/SQ)'), { sqft: 25 });
  assert.deepEqual(panelCoverage('1.4 ft x 3.54 ft Corrugated Profile 30 Gauge Galvanized Steel Roof Panel Black Finish 20-Pack'), { sqft: 99.1, basis: 'gross' });
  assert.deepEqual(panelCoverage('3.54 ft x 1.64 ft Corrugated Roof Panel 24-Gauge Steel Roof Panel in Gray (20-Pack)'), { sqft: 116.1, basis: 'gross' });
  assert.deepEqual(panelCoverage('1.48 ft.. x 3.54 ft.. Corrugated 26-Gauge Galvanized Steel Roof Panel in Silver (18-Pack)'), { sqft: 94.3, basis: 'gross' });
  assert.equal(panelCoverage('12 ft. Corrugated Galvanized Steel 29-Gauge Roof Panel'), null);
  assert.equal(panelCoverage('4 ft. x 50 ft. Aluminum Roof Panel'), null); // 200 sq ft is a roll, not a panel
  const p = (id) => catalog.products.find((x) => x.id === id);
  assert.deepEqual(p('hd-340755396').coverage, { sqft: 1500, basis: 'gross' }); // "3 ft. x 10 ft. ... 50PCS", not one 30 sq ft roll
  assert.equal(p('hd-205532379').coverage, undefined); // a length alone: quantity unknown
  for (const m of catalog.products.filter((x) => x.store === 'menards-3064' && x.kind === 'metalCap')) assert.equal(m.coverage, undefined, m.id);
});

test('PBR starting values: Menards from the material table, Home Depot by rule', () => {
  const p = (id) => catalog.products.find((x) => x.id === id);
  const duration = p('mn-1444450489132');
  assert.deepEqual(duration.colors[0].pbr, { metallic: 0, roughness: 0.9, type: 'asphalt_granule' });
  assert.deepEqual(duration.pbr, duration.colors[0].pbr);
  assert.deepEqual(p('hd-309755006').pbr, { metallic: 0, roughness: 0.9, type: 'asphalt_granule' });
  assert.equal(p('hd-205532379').pbr.type, 'galvanized'); // "12 ft. Corrugated Galvanized Steel": no paint color
  assert.equal(p('hd-340857990').pbr.type, 'painted_metal'); // galvanized steel, "Black Finish"
  assert.equal(p('hd-314709071').pbr.type, 'painted_metal'); // SM-Rib Galvalume "in Red"
});

test('colors: one source per entry, overrides win, unknown stays unknown', () => {
  const prod = () => ({ id: 'hd-1', store: 'homedepot-4301', layer: 'covering', category: 'metal', itemId: '1', name: '8 ft. Panel in Red', image: 'https://img/1_1000.jpg',
    color: 'Red', colors: [{ name: 'Red', itemId: '1' }, { name: 'Green', itemId: '2', swatch: 'https://img/green.png' }, { name: 'Hickory', itemId: '3' }] });
  assert.deepEqual(colorJobs(prod()).map((j) => [j.name, j.url, j.source]), [['Red', 'https://img/1_1000.jpg', 'photo'], ['Green', 'https://img/green.png', 'swatch']]);
  const cache = { 'https://img/1_1000.jpg': { hex: '#7e382c', palette: ['#7e382c'], check: [] }, 'https://img/green.png': { hex: '#7e382c', palette: ['#7e382c'], check: ['mixed'] } };
  const a = mergeColors(prod(), cache, {});
  assert.deepEqual([a.hex, a.colorSource, a.palette], ['#7e382c', 'photo', ['#7e382c']]);
  assert.deepEqual(a.colors[1].colorCheck, ['mixed', 'name-mismatch']); // a red chip named Green
  assert.equal(a.colors[2].hex, undefined); // no image, no color word, and the product name is the listed color's
  const b = mergeColors(prod(), cache, { 'hd-1|Red': { hex: '#AA0000', note: 'store page' } });
  assert.deepEqual([b.hex, b.colorSource], ['#aa0000', 'override']);
  const c = mergeColors({ ...prod(), color: undefined, colors: undefined, name: '8 ft. Panel in Black' }, {}, {});
  assert.deepEqual(c.colors, [{ name: null, hex: '#26272a', colorSource: 'name' }]); // no color listed: the photo's entry has name null
  assert.equal(mergeColors({ ...prod(), layer: 'starter' }, cache, {}).hex, undefined); // starter is not sampled
});
