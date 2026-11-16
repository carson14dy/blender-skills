// Store product -> studio render recipe (supplier-products.js). Small fixtures, not the
// live catalog, so these tests do not depend on when the catalog is rebuilt.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  toStudioProduct, layerOptionFor, suggestedSelections, paletteFor, colorEntry, defaultColor,
  shortName, specFor, storeName, seedFor, shadesOf, SUGGESTED, SLOTS, STORE_IDS, NEUTRAL,
} from '../viewer/js/supplier-products.js';
import { hashString } from '../viewer/js/util.js';

const MN = 'menards-3064', HD = 'homedepot-4301';
const pbrShingle = { metallic: 0, roughness: 0.9, type: 'asphalt_granule' };

const duration = {
  id: 'mn-1444450489132', store: MN, layer: 'covering', category: 'shingle', kind: 'architectural', brand: 'Owens Corning',
  name: 'Owens Corning® TruDefinition® Duration® Sierra Gray Architectural Roofing Shingles (32.8 sq. ft.)',
  url: 'https://www.menards.com/x', color: 'Sierra Gray', size: { lengthIn: 39.38, widthIn: 13.25, exposureIn: 5.625 },
  hex: '#7d7d7b', palette: ['#7d7d7b', '#6a6a68', '#8f8f8c', '#55524f'], colorSource: 'swatch',
  colors: [
    { name: 'Sierra Gray', hex: '#7d7d7b', palette: ['#7d7d7b', '#6a6a68', '#8f8f8c', '#55524f'], colorSource: 'swatch', pbr: pbrShingle },
    { name: 'Onyx Black', hex: '#2a2b2e', palette: ['#2a2b2e', '#2c2d30', '#28292b'], colorSource: 'swatch', pbr: pbrShingle }, // flat: luma range < 20
    { name: 'Teak' }, // not sampled
  ],
};
const supreme = {
  id: 'mn-1444450488124', store: MN, layer: 'covering', category: 'shingle', kind: 'threeTab', brand: 'Owens Corning',
  name: 'Owens Corning® Supreme® Driftwood 3-Tab Roofing Shingles (33.3 sq ft)', color: 'Driftwood',
  size: { lengthIn: 36, widthIn: 12, exposureIn: 5 }, colors: [{ name: 'Driftwood', hex: '#6d655b' }],
};
const pinnacle = {
  id: 'mn-1536647320756', store: MN, layer: 'covering', category: 'shingle', kind: 'architectural', brand: 'Atlas',
  name: 'Atlas Pinnacle® Pristine Hearthstone Architectural Roofing Shingles (32.8 sq. ft.)', color: 'Hearthstone Gray',
  size: { lengthIn: 42, widthIn: 14, exposureIn: 6 }, colors: [{ name: 'Hearthstone Gray', hex: '#6b6a66' }],
};
const timberline = {
  id: 'hd-309755006', store: HD, layer: 'covering', category: 'shingle', kind: 'architectural', brand: 'GAF',
  name: 'Timberline HDZ Charcoal Algae Resistant Laminated High Definition Shingles (33.33 sq. ft. per Bundle)', color: 'Charcoal',
  hex: '#3e3f42', palette: ['#3e3f42', '#2d2e31', '#55575b', '#1f2022'], colorSource: 'photo', pbr: pbrShingle,
  colors: [{ name: 'Charcoal', itemId: '309755006' }, { name: 'Hickory', hex: '#48332b', colorSource: 'swatch' }],
};
const proRib = {
  id: 'mn-1642874272687630', store: MN, layer: 'covering', category: 'metal', kind: 'proRib', brand: 'Designer Pro Rib',
  name: '36" Designer Pro-Rib® Matte Dover Gray Steel Panel', color: 'Matte Dover Gray',
  size: { widthIn: 38, ribHeightIn: 0.75, ribSpacingIn: 9, gauge: 29 },
  colors: [{ name: 'Matte Dover Gray', hex: '#737578', colorSource: 'photo', pbr: { metallic: 0, roughness: 0.7, type: 'painted_metal_matte' } }],
};
const proSnap = {
  id: 'mn-4283774896157214', store: MN, layer: 'covering', category: 'metal', kind: 'proSnap', brand: 'Premium Pro-Snap',
  name: '16" Premium Pro-Snap® Midnight Black Steel Panel', color: 'Midnight Black', size: { widthIn: 17.5, ribHeightIn: 0.75 },
  colors: [{ name: 'Midnight Black', hex: '#313236', pbr: { metallic: 0, roughness: 0.4, type: 'painted_metal' } }],
};
const shake24 = {
  id: 'mn-1444425380205', store: MN, layer: 'covering', category: 'shake', kind: 'cedar',
  name: '#1 Grade 24" Heavy Western Red Cedar Shakes (20 sq.ft.)', color: 'Cedar', size: { lengthIn: 24, widthIn: 4 },
  colors: [{ name: 'Cedar', hex: '#c8976c' }],
};
const corrugated = {
  id: 'hd-340857990', store: HD, layer: 'covering', category: 'metal', kind: 'corrugated',
  name: '1.4 ft x 3.54 ft Corrugated Profile 30 Gauge Galvanized Steel Roof Panel Black Finish 20-Pack', colors: [],
};
const hdPanel = {
  id: 'hd-306170802', store: HD, layer: 'covering', category: 'metal', kind: 'panel',
  name: '"Fabral Grandrib 3 36"" Panel - Galvanized Metal 29 GA Charcoal Grey (Limited Lifetime Warranty) 4834115851"',
  colors: [{ name: null, hex: '#4a4c50', colorSource: 'name' }], pbr: { metallic: 0.3, roughness: 0.45, type: 'painted_metal' },
};
const stoneCoated = {
  id: 'mn-1642874257824083', store: MN, layer: 'covering', category: 'metal', kind: 'stoneCoated', brand: 'Roser STEELGUARD',
  name: 'Roser® SteelGUARD® Birch Stone Coated Steel Shingles (5 sq ft)', color: 'Birch', size: { lengthIn: 54, widthIn: 18 },
  colors: [{ name: 'Birch', hex: '#8a7f70' }],
};
const catalog = { version: 2, stores: { [MN]: { name: 'Menards Sioux Falls West' }, [HD]: { name: 'The Home Depot #4301' } }, products: [duration, timberline] };

const luma = (hex) => { const v = parseInt(hex.slice(1), 16); return 0.2126 * (v >> 16 & 255) + 0.7152 * (v >> 8 & 255) + 0.0722 * (v & 255); };

test('Duration: architectural, 5-5/8" exposure, its sampled palette of 4', () => {
  const p = toStudioProduct(duration, 'Sierra Gray', catalog);
  assert.equal(p.category, 'shingle');
  assert.equal(p.procedural.kind, 'architectural');
  assert.equal(p.exposureIn, 5.625);
  assert.equal(p.procedural.exposureIn, 5.625);
  assert.deepEqual(p.procedural.palette, duration.colors[0].palette);
  assert.equal(p.procedural.palette.length, 4);
  assert.equal(p.id, 'mn-1444450489132::sierra-gray');
  assert.equal(p.name, 'TruDefinition Duration, Sierra Gray');
  assert.equal(p.supplier, 'Menards');
  assert.deepEqual(p.store, { id: MN, productId: duration.id, color: 'Sierra Gray', url: 'https://www.menards.com/x' });
  assert.deepEqual(p.pbr, pbrShingle);
  assert.deepEqual(p.approx, []);
});

test('the listed color is the default; a flat asphalt palette is widened to shades of the hex', () => {
  assert.equal(toStudioProduct(duration).store.color, 'Sierra Gray');
  const onyx = toStudioProduct(duration, 'Onyx Black');
  assert.deepEqual(onyx.procedural.palette, shadesOf('#2a2b2e'));
  const l = onyx.procedural.palette.map(luma);
  assert.ok(Math.max(...l) - Math.min(...l) >= 20);
  // the same flat palette is kept for a non-asphalt use
  assert.equal(paletteFor(duration.colors[1]).length, 3);
});

test('Timberline (Home Depot): listed color takes the product photo hex and palette; variants their swatch', () => {
  const p = toStudioProduct(timberline, 'Charcoal', catalog);
  assert.equal(p.procedural.kind, 'architectural');
  assert.equal(p.exposureIn, 5.625); // no size in the store data
  assert.equal(p.hex, '#3e3f42');
  assert.deepEqual(p.procedural.palette, timberline.palette);
  assert.equal(p.supplier, 'Home Depot');
  assert.deepEqual(p.pbr, pbrShingle); // product-level pbr (Home Depot rule)
  const h = toStudioProduct(timberline, 'Hickory');
  assert.equal(h.hex, '#48332b');
  assert.deepEqual(h.procedural.palette, shadesOf('#48332b'));
});

test('OC Supreme: three-tab at 5"', () => {
  const p = toStudioProduct(supreme);
  assert.equal(p.procedural.kind, 'threeTab');
  assert.equal(p.exposureIn, 5);
  assert.equal(p.category, 'shingle');
  assert.equal(toStudioProduct({ ...supreme, size: undefined }).exposureIn, 5);
});

test('Atlas Pinnacle: 6" exposure with the approx note', () => {
  const p = toStudioProduct(pinnacle);
  assert.equal(p.exposureIn, 6);
  assert.ok(p.approx.includes('exposure 6 in. from the Menards table, not confirmed on the Atlas sheet'));
  assert.ok(!toStudioProduct(duration).approx.some((a) => a.includes('Atlas')));
});

test('Pro-Rib: ribbed panel, 36" cover, major ribs every 9", 3/4" high, 2 minor ribs', () => {
  const p = toStudioProduct(proRib);
  assert.equal(p.category, 'metal');
  assert.equal(p.procedural.kind, 'ribbedPanel');
  assert.equal(p.procedural.coverIn, 36);
  assert.equal(p.procedural.ribSpacingIn, 9);
  assert.equal(p.procedural.ribHeightIn, 0.75);
  assert.equal(p.procedural.minorRibs, 2);
  assert.equal(p.procedural.color, '#737578');
  assert.equal(p.exposureIn, undefined);
  assert.equal(p.pbr.roughness, 0.7); // matte line reads matte
});

test('Pro-Snap: standing seam at 16"', () => {
  const p = toStudioProduct(proSnap);
  assert.equal(p.procedural.kind, 'standingSeam');
  assert.equal(p.procedural.panelIn, 16);
  assert.equal(p.procedural.color, '#313236');
  assert.deepEqual(p.approx, []);
  assert.ok(toStudioProduct({ ...proSnap, kind: 'standingSeam', store: HD }).approx.some((a) => a.includes('16 in.')));
});

test('cedar: exposure from the piece length (24" -> 10, 18" shakes -> 7.5, 18" shingles -> 5.5, 16" -> 5)', () => {
  const p = toStudioProduct(shake24);
  assert.equal(p.category, 'shake');
  assert.equal(p.procedural.kind, 'cedarShake');
  assert.equal(p.exposureIn, 10);
  assert.equal(p.procedural.exposureIn, 10);
  assert.equal(toStudioProduct({ ...shake24, size: { lengthIn: 18 } }).exposureIn, 7.5);
  assert.equal(toStudioProduct({ ...shake24, name: '#2 Grade 18" Western Red Cedar Perfection Shingles', size: { lengthIn: 18 } }).exposureIn, 5.5);
  assert.equal(toStudioProduct({ ...shake24, kind: 'undercourse', size: { lengthIn: 16 } }).exposureIn, 5);
});

test('no hex: neutral gray and "color not sampled"', () => {
  const teak = toStudioProduct(duration, 'Teak');
  assert.equal(teak.hex, null);
  assert.deepEqual(teak.procedural.palette, shadesOf(NEUTRAL));
  assert.ok(teak.approx.includes('color not sampled'));
  const c = toStudioProduct(corrugated);
  assert.equal(c.procedural.color, NEUTRAL);
  assert.ok(c.approx.includes('color not sampled'));
  // a catalog with no colors at all (version 1) draws everything neutral
  const v1 = toStudioProduct({ ...proRib, colors: [{ name: 'Matte Dover Gray' }] });
  assert.equal(v1.procedural.color, NEUTRAL);
  assert.ok(v1.approx.includes('color not sampled'));
});

test('corrugated, unspecified Home Depot panel and stone-coated get their assumed profiles and notes', () => {
  const c = toStudioProduct(corrugated);
  assert.equal(c.procedural.kind, 'corrugatedPanel');
  assert.equal(c.procedural.pitchIn, 2.67);
  assert.equal(c.procedural.depthIn, 0.5);
  assert.ok(c.approx.some((a) => /common profile, not store data/.test(a)));
  const p = toStudioProduct(hdPanel);
  assert.equal(p.procedural.kind, 'ribbedPanel');
  assert.equal(p.procedural.coverIn, 36);
  assert.equal(p.procedural.ribSpacingIn, 9);
  assert.equal(p.procedural.color, '#4a4c50'); // the null-named entry is the listed color
  assert.ok(p.approx.includes('profile assumed: the store does not state it'));
  assert.ok(p.approx.includes('color from its name, not from a photo'));
  assert.equal(p.name, 'Fabral Grandrib 3');
  assert.equal(p.id, 'hd-306170802::listed');
  const s = toStudioProduct(stoneCoated);
  assert.equal(s.category, 'shingle');
  assert.equal(s.procedural.kind, 'architectural');
  assert.equal(s.exposureIn, 13.3);
  assert.ok(s.approx.includes('drawn as a granule course; real panel profile is later'));
});

test('seed is stable per product and in 1..97', () => {
  for (const sp of [duration, timberline, proRib, corrugated]) {
    const s = toStudioProduct(sp).procedural.seed;
    assert.equal(s, hashString(sp.id) % 97 + 1);
    assert.equal(s, seedFor(sp));
    assert.ok(s >= 1 && s <= 97);
  }
});

test('color entry: listed color, null-named entry, product-level fallback', () => {
  assert.equal(defaultColor(duration), 'Sierra Gray');
  assert.equal(defaultColor(hdPanel), null);
  assert.equal(defaultColor(corrugated), null);
  assert.equal(colorEntry(timberline, 'Charcoal').hex, '#3e3f42');
  assert.equal(colorEntry(timberline, 'charcoal').hex, '#3e3f42');
  assert.equal(colorEntry(timberline, 'Hickory').colorSource, 'swatch');
  assert.equal(colorEntry(duration, 'Teak').hex, undefined); // a variant never borrows the listed color's hex
  assert.equal(colorEntry(hdPanel).pbr.metallic, 0.3);
});

test('layer options: cap palette or color, drip edge object, underlayment and ice & water ids', () => {
  const cap = { id: 'mn-cap', store: MN, layer: 'ridgeCap', kind: 'shingleCap', name: 'ProEdge Hip and Ridge', color: 'Williamsburg Gray', colors: [{ name: 'Williamsburg Gray', hex: '#6e6c69' }] };
  assert.deepEqual(layerOptionFor(cap), { capPalette: shadesOf('#6e6c69'), capColor: null });
  const metalCap = { id: 'mn-mcap', store: MN, layer: 'ridgeCap', kind: 'metalCap', name: '10\' Charcoal Gray Residential Ridge Cap', color: 'Charcoal Gray', colors: [{ name: 'Charcoal Gray', hex: '#3d4043' }] };
  assert.deepEqual(layerOptionFor(metalCap), { capColor: '#3d4043', capPalette: null });
  const drip = { id: 'mn-1444424196953', store: MN, layer: 'dripEdge', kind: 'dripEdge', name: '2-3/8" x 1-11/16" x 12\' Style-D White Aluminum Drip Edge', color: 'White', colors: [{ name: 'White', hex: '#efefec', pbr: { metallic: 0, roughness: 0.4 } }] };
  assert.deepEqual(layerOptionFor(drip), { dripEdge: { id: drip.id, label: 'Style-D Aluminum, White', color: '#efefec', metal: 0 } });
  assert.equal(layerOptionFor({ ...drip, colors: [] , color: null }).dripEdge.color, NEUTRAL);
  assert.equal(layerOptionFor({ ...drip, colors: [{ name: 'White', hex: '#efefec' }] }).dripEdge.metal, 0.3);
  const und = (kind, name) => layerOptionFor({ id: 'u', store: HD, layer: 'underlayment', kind, name }).underlayment;
  assert.equal(und('felt', '#30 Felt 3\' x 72\' Roofing Underlayment'), 'felt30');
  assert.equal(und('synthetic', 'Pro Synthetic Underlayment 1000 sq. ft.'), 'syn-gray');
  assert.equal(und('synthetic', 'RhinoRoof Blue Synthetic Underlayment'), 'syn-blue');
  assert.equal(und('synthetic', 'Titanium Black Synthetic Underlayment'), 'syn-black');
  const ice = (name) => layerOptionFor({ id: 'i', store: MN, layer: 'iceWater', kind: 'iceWater', name }).iceWater;
  assert.equal(ice('WeatherLock G 3\' x 66.7\' Granulated Self-Sealing Ice and Water Barrier'), 'granular');
  assert.equal(ice('WeatherWatch 200 sq. ft. Mineral-Surfaced Peel and Stick'), 'granular');
  assert.equal(ice('WeatherLock Mat Self-Sealing Ice and Water Barrier'), 'smooth');
  for (const layer of ['starter', 'ridgeVent', 'valley', 'covering']) assert.deepEqual(layerOptionFor({ id: 'x', store: MN, layer, name: 'x' }), {});
});

test('suggested basket: 8 slots x 2 stores; a product missing from the catalog is null', () => {
  assert.deepEqual(Object.keys(SUGGESTED), SLOTS);
  for (const slot of SLOTS) assert.deepEqual(Object.keys(SUGGESTED[slot]), STORE_IDS);
  assert.equal(SUGGESTED.covering[MN].productId, 'mn-1444450489132');
  assert.equal(SUGGESTED.covering[HD].color, 'Charcoal');
  assert.ok(Object.isFrozen(SUGGESTED.covering[MN]));
  const sel = suggestedSelections(catalog);
  assert.deepEqual(sel.covering[MN], { productId: 'mn-1444450489132', color: 'Sierra Gray', source: 'suggested' });
  assert.deepEqual(sel.covering[HD], { productId: 'hd-309755006', color: 'Charcoal', source: 'suggested' });
  assert.equal(sel.ridgeCap[MN], null);
  assert.equal(sel.valley[HD], null);
});

test('names: short names, label spec, store names', () => {
  assert.equal(shortName(timberline), 'Timberline HDZ');
  assert.equal(shortName(proRib), 'Designer Pro-Rib');
  assert.equal(shortName(proSnap), 'Premium Pro-Snap'); // the brand is the line: kept
  assert.equal(shortName(supreme), 'Supreme');
  assert.equal(specFor(duration, 'Sierra Gray'), 'TruDefinition Duration, Sierra Gray · Menards');
  assert.equal(specFor(hdPanel, null), 'Fabral Grandrib 3 · Home Depot');
  assert.equal(storeName('lowes-1', { stores: { 'lowes-1': { name: "Lowe's" } } }), "Lowe's");
});
