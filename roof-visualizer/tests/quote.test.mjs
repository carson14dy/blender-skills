// Priced materials list (viewer/js/quote.js) against the hand-checked ranch demo, supplier plan section 6.7.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildQuote, quoteCSV, crewView, csvFileName, toQuantities, ventLengthM, ceilQty, ageBanner,
  LINEAR_ALLOWANCE, LAP_ALLOWANCE, HEADER, NOT_INCLUDED,
} from '../viewer/js/quote.js';
import { buildRoofPlanes, HOUSE_PRESETS } from '../viewer/js/house.js';
import { analyzeRoof, measureRoof } from '../viewer/js/roof-geometry.js';

const MN = 'menards-3064', HD = 'homedepot-4301';
const r2 = (x) => Math.round(x * 100) / 100;

// ---------------------------------------------------------------------------
// Fixture catalog. Prices, coverages and stock copied from catalog/suppliers/sioux-falls.json (version 1, HEAD eb95163);
// version 2 keeps these prices. Each product carries its catalog id. Field names as in plan sections 4 and 6.
const REBATE_END = '11/15/26';
const mnPrice = (shelf, rebate, per, extra = {}) => ({ shelf, rebate, rebateThrough: REBATE_END, afterRebate: r2(shelf - rebate), per, ...extra });
const PRODUCTS = [
  // Menards
  { id: 'mn-1444450489132', store: MN, layer: 'covering', category: 'shingle', kind: 'architectural', color: 'Sierra Gray', // Duration
    name: 'Owens Corning TruDefinition Duration Sierra Gray Architectural Roofing Shingles (32.8 sq. ft.)',
    price: mnPrice(46.06, 5.07, 'bundle', { sale: 46.06, saleThrough: '11/26/26' }), coverage: { sqft: 32.8 } },
  { id: 'mn-1642874276146419', store: MN, layer: 'ridgeCap', kind: 'shingleCap', color: 'Williamsburg Gray', // ProEdge
    name: 'Owens Corning ProEdge Hip and Ridge Roofing Shingles (33 lin. ft.)', price: mnPrice(79.99, 8.8, 'bundle'), coverage: { lf: 33 } },
  { id: 'mn-1444450475975', store: MN, layer: 'starter', kind: 'starter', color: 'Black', // Starter Strip Plus
    name: 'Owens Corning Starter Strip Plus Roofing Shingles (105 lin. ft.)', price: mnPrice(54.97, 6.05, 'bundle'), coverage: { lf: 105 } },
  { id: 'mn-1444450500228', store: MN, layer: 'underlayment', kind: 'synthetic', // ProArmor
    name: 'Owens Corning ProArmor Synthetic Roofing Underlayment (1,000 sq. ft.)', price: mnPrice(119, 13.09, 'each'), coverage: { sqft: 1000 } },
  { id: 'mn-1444450479015', store: MN, layer: 'iceWater', kind: 'iceWater', // WeatherLock G
    name: 'Owens Corning WeatherLock G Ice and Water Barrier (200 sq. ft.)', price: mnPrice(119, 13.09, 'each'), coverage: { sqft: 200 } },
  { id: 'mn-1444424196953', store: MN, layer: 'dripEdge', kind: 'dripEdge', color: 'White', // Style-D white 12 ft
    name: '2-3/8" x 1-11/16" x 12\' Style-D White Aluminum Drip Edge', price: mnPrice(9.98, 1.1, 'each'), pieceFt: 12 },
  { id: 'mn-1444450488871', store: MN, layer: 'ridgeVent', kind: 'ridgeVent', color: 'Black', // VentSure 20 ft
    name: 'Owens Corning VentSure 11-1/4" x 20\' Shingle-Over Ridge Vent', price: mnPrice(65.98, 7.26, 'each'), pieceFt: 20 },
  { id: 'mn-1444448528388', store: MN, layer: 'valley', kind: 'valley', color: 'Charcoal Black', // W valley 10 ft
    name: '24" x 10\' Charcoal Black Steel "W" Formed Valley', price: mnPrice(35.49, 3.9, 'each'), pieceFt: 10 },
  { id: 'mn-1444448546780', store: MN, layer: 'covering', category: 'metal', kind: 'proRib', color: 'Brite White', // Pro-Rib Brite White
    name: '36" Pro-Rib Brite White Steel Panel',
    price: mnPrice(116.84, 12.85, '100 sq ft', { sale: 116.84, saleThrough: '11/26/26', startingAt: true }) },
  // Home Depot
  { id: 'hd-309755006', store: HD, layer: 'covering', category: 'shingle', kind: 'architectural', color: 'Charcoal', // Timberline HDZ
    name: 'Timberline HDZ Charcoal Laminated High Definition Shingles (33.33 sq. ft. per Bundle)',
    price: { shelf: 46.97, per: 'bundle' }, coverage: { sqft: 33.33 }, stock: { inStock: true, qty: 141 } },
  { id: 'hd-206593176', store: HD, layer: 'ridgeCap', kind: 'shingleCap', color: 'Charcoal', // Seal-A-Ridge
    name: 'Seal-A-Ridge Charcoal Hip and Ridge Cap Roofing Shingles (25 lin. ft. per Bundle)',
    price: { shelf: 62.97, per: 'bundle' }, coverage: { lf: 25 }, stock: { inStock: true, qty: 19 } },
  { id: 'hd-202052408', store: HD, layer: 'starter', kind: 'starter', // Pro-Start
    name: 'Pro-Start 120 lin. ft. Eave and Rake Roofing Starter Strip Shingles',
    price: { shelf: 54.97, per: 'each' }, coverage: { lf: 120 }, stock: { inStock: true, qty: 15 } },
  { id: 'hd-340399395', store: HD, layer: 'underlayment', kind: 'synthetic', // Pro Synthetic
    name: 'Pro Synthetic Underlayment 1000 sq. ft. 4 ft. x 250 ft.', price: { shelf: 70.8, per: 'roll' }, coverage: { sqft: 1000 }, stock: { inStock: false } },
  { id: 'hd-100083275', store: HD, layer: 'iceWater', kind: 'iceWater', // WeatherWatch 200
    name: 'WeatherWatch 200 sq. ft. Mineral-Surfaced Peel and Stick Roof Leak Barrier Roll',
    price: { shelf: 129, per: 'roll' }, coverage: { sqft: 200 }, stock: { inStock: true, qty: 24 } },
  { id: 'hd-100087282', store: HD, layer: 'dripEdge', kind: 'dripEdge', // C3 white 10 ft
    name: 'C3 x 10 ft. White Aluminum Drip Edge Flashing', price: { shelf: 7.68, per: 'each' }, pieceFt: 10, stock: { inStock: false } },
  { id: 'hd-316349297', store: HD, layer: 'ridgeVent', kind: 'ridgeVent', // Air Vent 20 ft
    name: 'Air Vent 11 in. x 240 in. Rolled Ridge Vent in Black with Nails', price: { shelf: 61.75, per: 'roll' }, pieceFt: 20, stock: { inStock: false } },
  { id: 'hd-100096067', store: HD, layer: 'valley', kind: 'valley', // galvanized roll valley 10 ft
    name: '14 in. x 10 ft. Galvanized Steel Roll Valley Flashing', price: { shelf: 23, per: 'each' }, coverage: { sqft: 11.7 }, pieceFt: 10, stock: { inStock: true, qty: 7 } },
  // made-up products for the unknown-value and pack-count rules (not in the catalog)
  { id: 'hd-fixture-atlas', store: HD, layer: 'covering', category: 'shingle', kind: 'architectural', color: 'Weathered Wood',
    name: 'Atlas Pinnacle Pristine (3 BD/SQ)', price: { shelf: null, per: 'bundle' }, coverage: { sqft: 33.3 } },
  { id: 'hd-fixture-panel-length', store: HD, layer: 'covering', category: 'metal', kind: 'corrugated',
    name: '12 ft. Corrugated Galvanized Steel 29-Gauge Roof Panel', price: { shelf: 25.98, per: 'each' } },
  { id: 'hd-fixture-panel-pack', store: HD, layer: 'covering', category: 'metal', kind: 'corrugated',
    name: '1.4 ft x 3.54 ft Corrugated Polycarbonate Roof Panel 20-Pack', price: { shelf: 189, per: 'each' }, coverage: { sqft: 99.1, basis: 'gross' }, packCount: 20 },
  { id: 'hd-fixture-vent-carton', store: HD, layer: 'ridgeVent', kind: 'ridgeVent',
    name: '4 ft. Ridge Vent, Sold in Carton of 10-Pieces only', price: { shelf: 148, per: 'each' }, pieceFt: 4, packCount: 10 },
  { id: 'hd-fixture-uhdz', store: HD, layer: 'covering', category: 'shingle', kind: 'architectural', color: 'Pewter Gray', // packCount = shingles per bundle
    name: 'Timberline UHDZ Pewter Gray Algae Resistant Laminated High Definition Shingles (33.33 sq. ft. per Bundle)',
    price: { shelf: 54.97, per: 'bundle' }, coverage: { sqft: 33.33 }, packCount: 21 },
  { id: 'mn-fixture-sale', store: MN, layer: 'covering', category: 'shingle', kind: 'architectural',
    name: 'Sale shingle', price: { shelf: 40, per: 'bundle', saleThrough: '11/10/26' }, coverage: { sqft: 33.3 } },
];
const CATALOG = {
  version: 2,
  stores: {
    [MN]: { name: 'Menards Sioux Falls West', captured: '2026-11-15' },
    [HD]: { name: 'The Home Depot #4301', captured: '2026-11-15/16' },
  },
  sources: { menards: { productsSha256: 'be651dd7b4307a3c' }, homedepot: { sha256: '06040ac740d39e77' } },
  products: PRODUCTS,
};

// The suggested basket (plan section 3.3).
const SUGGESTED = {
  covering: ['mn-1444450489132', 'hd-309755006'], ridgeCap: ['mn-1642874276146419', 'hd-206593176'],
  starter: ['mn-1444450475975', 'hd-202052408'], underlayment: ['mn-1444450500228', 'hd-340399395'],
  iceWater: ['mn-1444450479015', 'hd-100083275'], dripEdge: ['mn-1444424196953', 'hd-100087282'],
  ridgeVent: ['mn-1444450488871', 'hd-316349297'], valley: ['mn-1444448528388', 'hd-100096067'],
};
function job(over = {}) {
  const byId = new Map(PRODUCTS.map((p) => [p.id, p]));
  const selections = {};
  for (const [slot, [mn, hd]] of Object.entries(SUGGESTED)) {
    selections[slot] = {
      [MN]: { productId: mn, color: byId.get(mn).color ?? null, source: 'suggested' },
      [HD]: { productId: hd, color: byId.get(hd).color ?? null, source: 'suggested' },
    };
  }
  return {
    name: 'Untitled roof', shownStore: MN, roofSource: 'store', waste: { pct: 17, source: 'suggested' }, valleyMetal: false,
    selections, typed: { nails: null, deckRepair: null }, snapshot: null, dirty: false, ...over,
  };
}

// ---------------------------------------------------------------------------
// Measured inputs, ranch-hip at 6/12. Q3 is the geometry to three decimals (unit test of the rules); QP is the plan's
// two-decimal figures. QP rounds two needs a cent the other way (see the test 'plan-precision inputs').
const NAILS = 21840; // a stand-in: the count comes from the nails layer, which needs a canvas
const Q3 = {
  areaSqft: 2743.246, squares: 27.432, eaveFt: 191.273, rakeFt: 29.712, ridgeFt: 50.689, hipFt: 107.283, valleyFt: 39.862,
  iceSqft: 1055.10, iceRows: 2, ventFt: 46.752, nailCount: NAILS, deckRepairSheets: 3, category: 'shingle',
};
const QP = { ...Q3, areaSqft: 2743.25, squares: 27.43, eaveFt: 191.27, rakeFt: 29.71, ridgeFt: 50.69, hipFt: 107.28, valleyFt: 39.86, ventFt: 46.75 };

function geometryQ() {
  const planes = buildRoofPlanes(HOUSE_PRESETS['ranch-hip'], 6);
  const segs = analyzeRoof(planes);
  const m = measureRoof(planes, segs);
  // ice & water: eave rows 92.233 m2 + valleys 5.789 m2 (layers.js measures its mesh; it cannot load in Node)
  return { m, q: toQuantities({ measure: m, ridgeLengthsM: segs.ridge.map((l) => l.A.distanceTo(l.B)), iceM2: 92.233 + 5.789, iceRows: 2, nailCount: NAILS, deckRepairSheets: 3 }) };
}

const TODAY = '2026-11-16';
/** Split one CSV record (no line breaks inside fields). */
function csvFields(r) {
  const out = [];
  let f = '', quoted = false;
  for (let i = 0; i < r.length; i++) {
    const ch = r[i];
    if (quoted) {
      if (ch === '"' && r[i + 1] === '"') { f += '"'; i++; } else if (ch === '"') quoted = false; else f += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { out.push(f); f = ''; } else f += ch;
  }
  out.push(f);
  return out;
}
const quote = (q = Q3, j = job(), extra = {}) => buildQuote({ q, job: j, catalog: CATALOG, today: TODAY, ...extra });
const line = (Qt, slot) => Qt.lines.find((l) => l.slot === slot);

// slot: need, Menards qty and total, Home Depot qty and total, lower (plan 6.7 table)
const TABLE = {
  covering: [3209.60, 98, 4513.88, 97, 4556.09, MN],
  ridgeCap: [165.87, 6, 479.94, 7, 440.79, HD],
  starter: [232.03, 3, 164.91, 2, 109.94, HD],
  underlayment: [3017.57, 4, 476.00, 4, 283.20, HD],
  iceWater: [1160.61, 6, 714.00, 6, 774.00, MN],
  dripEdge: [232.03, 20, 199.60, 24, 184.32, HD],
  ridgeVent: [46.75, 3, 197.94, 3, 185.25, HD],
};

// ---------------------------------------------------------------------------

test('constants and rounding up', () => {
  assert.equal(LINEAR_ALLOWANCE, 0.05);
  assert.equal(LAP_ALLOWANCE, 0.10);
  assert.equal(ceilQty(150), 150);
  assert.equal(ceilQty(3000 / 20), 150);
  assert.equal(ceilQty(150.0000000001), 150, 'float noise does not add a bundle');
  assert.equal(ceilQty(150.01), 151);
});

test('measured inputs from the ranch geometry match the plan', () => {
  const { m, q } = geometryQ();
  const want = { areaSqft: 2743.25, squares: 27.43, eaveFt: 191.27, rakeFt: 29.71, ridgeFt: 50.69, hipFt: 107.28, valleyFt: 39.86, iceSqft: 1055.10, ventFt: 46.75 };
  for (const [k, v] of Object.entries(want)) assert.equal(r2(q[k]), v, k);
  for (const k of Object.keys(Q3)) if (typeof Q3[k] === 'number') assert.ok(Math.abs(q[k] - Q3[k]) < 0.0006, `${k}: ${q[k]} vs ${Q3[k]}`);
  // ridges 6.00 m + 9.45 m; the vent loses 0.3 m at each end of each ridge (not once overall)
  assert.equal(r2(ventLengthM([6.0, 9.45])), 14.25);
  assert.equal(ventLengthM([0.89]), 0, 'ridges under 0.9 m get no vent');
  assert.equal(toQuantities({ measure: m, ridgeLengthsM: [6, 9.45], ventOn: false }).ventFt, 0);
  // suggestedWaste(): (hips 32.70 + valleys 12.15) / (eaves 58.30 + rakes 9.06) = 0.666, in the 17% band (0.4, 0.8]
  const cut = (m.hipM + m.valleyM) / (m.eaveM + m.rakeM);
  assert.equal(Math.round(cut * 1000) / 1000, 0.666);
  assert.ok(cut > 0.4 && cut <= 0.8);
});

test('ranch demo: every line of the 6.7 table', () => {
  const Qt = quote();
  assert.deepEqual(Qt.lines.map((l) => l.slot), ['covering', 'ridgeCap', 'starter', 'underlayment', 'iceWater', 'dripEdge', 'ridgeVent', 'nails', 'deckRepair']);
  for (const [slot, [need, mq, mt, hq, ht, lower]] of Object.entries(TABLE)) {
    const l = line(Qt, slot);
    assert.equal(l.need.value, need, `${slot} need`);
    assert.equal(l.cells[MN].qty, mq, `${slot} Menards qty`);
    assert.equal(l.cells[MN].lineTotal, mt, `${slot} Menards total`);
    assert.equal(l.cells[HD].qty, hq, `${slot} Home Depot qty`);
    assert.equal(l.cells[HD].lineTotal, ht, `${slot} Home Depot total`);
    assert.equal(l.lower, lower, `${slot} lower`);
    assert.equal(l.cells[MN].status, 'priced');
    assert.equal(l.cells[HD].status, 'priced');
  }
  const cov = line(Qt, 'covering');
  assert.equal(cov.basis.text, '2,743 sq ft');
  assert.equal(cov.basis.source, 'measured');
  assert.deepEqual([cov.allowance.pct, cov.allowance.text, cov.allowance.source], [17, '17% waste', 'allowance']);
  assert.equal(cov.cells[MN].unit, 'bundle');
  assert.equal(cov.cells[MN].unitPrice, 46.06);
  assert.equal(cov.cells[MN].totalText, '$4,513.88');
  assert.equal(cov.cells[HD].unitPrice, 46.97);
  assert.equal(cov.cells[MN].suggested, true);
  assert.equal(line(Qt, 'ridgeVent').allowance, null, 'ridge vent has no allowance');
  assert.equal(line(Qt, 'ridgeCap').allowance.text, '5% laps and cuts');
  assert.equal(line(Qt, 'underlayment').allowance.text, '10% laps');
  // nails and deck repair: no price in either store, no "lower"
  for (const slot of ['nails', 'deckRepair']) {
    const l = line(Qt, slot);
    assert.equal(l.lower, null);
    for (const s of [MN, HD]) {
      const c = l.cells[s];
      assert.equal(c.status, 'noPrice');
      assert.equal(c.why, 'no price: not in the store data');
      assert.equal(c.lineTotal, null);
      assert.equal(c.totalText, '–', 'an unknown total prints an en dash, never 0');
    }
  }
  assert.equal(line(Qt, 'nails').cells[MN].qty, NAILS);
  assert.equal(line(Qt, 'deckRepair').need.value, 3);
  assert.equal(line(Qt, 'deckRepair').cells[HD].unit, 'sheets');
});

test('ranch demo totals: all three incomplete', () => {
  const { totals } = quote();
  assert.equal(totals[MN].amount, 6746.27);
  assert.equal(totals[HD].amount, 6533.59);
  assert.equal(totals.lowest.amount, 6431.38);
  assert.equal(r2(4513.88 + 440.79 + 109.94 + 283.20 + 714.00 + 184.32 + 185.25), 6431.38);
  for (const t of [totals[MN], totals[HD], totals.lowest]) {
    assert.equal(t.status, 'incomplete');
    assert.deepEqual(t.missing, ['Fasteners', 'Deck repair']);
    assert.equal(t.includesTyped, false);
  }
  assert.equal(totals[MN].text, 'Total incomplete: $6,746.27 so far. Missing: Fasteners, Deck repair.');
  assert.equal(totals[HD].text, 'Total incomplete: $6,533.59 so far. Missing: Fasteners, Deck repair.');
  assert.deepEqual(totals.lowest.picks, { covering: MN, ridgeCap: HD, starter: HD, underlayment: HD, iceWater: MN, dripEdge: HD, ridgeVent: HD, nails: null, deckRepair: null });
});

test('typed whole-line amounts for nails and deck repair complete both totals', () => {
  const Qt = quote(Q3, job({ typed: { nails: 89.00, deckRepair: 96.00 } }));
  assert.equal(Qt.totals[MN].amount, 6931.27);
  assert.equal(Qt.totals[HD].amount, 6718.59);
  assert.equal(Qt.totals.lowest.amount, 6616.38);
  for (const s of [MN, HD]) {
    assert.equal(Qt.totals[s].status, 'complete');
    assert.equal(Qt.totals[s].includesTyped, true);
    assert.match(Qt.totals[s].text, /includes typed prices/);
  }
  assert.equal(Qt.totals[MN].text, 'Materials total $6,931.27, before tax, includes typed prices');
  assert.equal(Qt.totals.lowest.status, 'complete');
  const nails = line(Qt, 'nails');
  assert.equal(nails.cells[MN].lineTotal, 89);
  assert.equal(nails.cells[MN].priceSource, 'typed');
  assert.equal(nails.lower, null, 'a tie gets no tag');
  assert.equal(line(Qt, 'deckRepair').cells[HD].lineTotal, 96);
});

test('Menards rebate: a separate block, never subtracted', () => {
  const { totals } = quote();
  const r = totals[MN].rebate;
  assert.equal(r2(98 * 5.07 + 6 * 8.80 + 3 * 6.05 + 4 * 13.09 + 6 * 13.09 + 20 * 1.10 + 3 * 7.26), 742.49);
  assert.equal(r.amount, 742.49);
  assert.equal(r.pct, 11);
  assert.equal(r.through, '11/15/26');
  assert.equal(r.ended, true);
  assert.equal(r.text, '11% mail-in rebate ended 11/15/26. It would have been $742.49 in store credit. Not in the total.');
  assert.equal(totals[MN].amount, 6746.27, 'the rebate is not in the total');
  assert.equal(totals[HD].rebate, null);
  const before = buildQuote({ q: Q3, job: job(), catalog: CATALOG, today: '2026-11-15' }).totals[MN].rebate;
  assert.equal(before.ended, false, 'still running on its last day');
  assert.equal(before.text, '11% mail-in rebate through 11/15/26: $742.49 store credit by mail. Not in the total.');
});

test('valley metal on: 41.86 ft', () => {
  const l = line(quote(Q3, job({ valleyMetal: true })), 'valley');
  assert.equal(l.need.value, 41.86);
  assert.equal(l.cells[MN].qty, 5);
  assert.equal(l.cells[MN].lineTotal, 177.45);
  assert.equal(l.cells[HD].qty, 5);
  assert.equal(l.cells[HD].lineTotal, 115.00);
  assert.equal(l.lower, HD);
  assert.equal(line(quote(), 'valley'), undefined, 'no valley line while valley metal is off');
});

test('Home Depot stock at capture', () => {
  const Qt = quote();
  const cov = line(Qt, 'covering').cells[HD].stock;
  assert.deepEqual([cov.qty, cov.short, cov.text], [141, false, '141 in store at capture']);
  const cap = line(Qt, 'ridgeCap').cells[HD].stock;
  assert.deepEqual([cap.qty, cap.short], [19, false]);
  assert.equal(line(Qt, 'covering').cells[MN].stock, null, 'Menards has no stock data');
  // 19 on hand, 24 needed: ridge cap at 600 ft
  const short = line(quote({ ...Q3, ridgeFt: 400, hipFt: 171.43 }), 'ridgeCap').cells[HD];
  assert.equal(short.qty, 24);
  assert.deepEqual([short.stock.short, short.stock.text], [true, 'store had 19, you need 24']);
});

test('Pro-Rib starting-at steel on the roof', () => {
  const j = job({ typed: { nails: 89, deckRepair: 96 } });
  j.selections.covering[MN] = { productId: 'mn-1444448546780', color: 'Brite White', source: 'chosen' };
  const Qt = quote({ ...Q3, category: 'metal' }, j);
  const c = line(Qt, 'covering').cells[MN];
  assert.equal(c.status, 'startingAt');
  assert.equal(c.qty, 32.10);
  assert.equal(c.qtyText, '32.10');
  assert.equal(c.unit, 'squares (100 sq ft)');
  assert.equal(c.lineTotal, 3750.56);
  assert.equal(c.totalText, 'from $3,750.56');
  assert.ok(c.notes.includes('starting-at price: color and length change it'));
  assert.equal(c.rebate, null, 'no rebate counted on a starting-at price');
  assert.equal(line(Qt, 'covering').lower, null, 'a starting-at price is never "lower"');
  assert.equal(line(Qt, 'starter'), undefined, 'no starter under metal');
  assert.equal(Qt.totals[MN].status, 'atLeast');
  assert.equal(Qt.totals[MN].amount, r2(3750.56 + 479.94 + 476 + 714 + 199.60 + 197.94 + 89 + 96));
  assert.equal(Qt.totals[MN].text, 'At least $6,003.04, includes typed prices');
  assert.equal(Qt.totals[HD].amount, r2(6533.59 - 109.94 + 185));
  assert.equal(Qt.totals[HD].status, 'complete');
  assert.equal(Qt.totals.lowest.status, 'atLeast');
});

test('plan check at zero waste: 30 squares', () => {
  const q = { ...Q3, areaSqft: 3000, squares: 30 };
  const j = job({ waste: { pct: 0, source: 'typed' } });
  const cov = line(quote(q, j), 'covering');
  assert.equal(cov.need.value, 3000);
  assert.equal(cov.allowance, null);
  assert.equal(cov.cells[MN].qty, 92);
  j.selections.covering[MN].typedCoverage = 20;
  assert.equal(line(quote(q, j), 'covering').cells[MN].qty, 150);
  const at20 = { ...CATALOG, products: PRODUCTS.map((p) => (p.id === 'mn-1444450489132' ? { ...p, coverage: { sqft: 20 } } : p)) };
  assert.equal(line(buildQuote({ q, job: job({ waste: { pct: 0, source: 'typed' } }), catalog: at20, today: TODAY }), 'covering').cells[MN].qty, 150);
});

test('measurements from the geometry give the same list', () => {
  const { q } = geometryQ();
  const Qt = quote(q, job({ valleyMetal: true }));
  for (const [slot, [need, mq, mt, hq, ht]] of Object.entries(TABLE)) {
    const l = line(Qt, slot);
    assert.deepEqual([l.need.value, l.cells[MN].qty, l.cells[MN].lineTotal, l.cells[HD].qty, l.cells[HD].lineTotal], [need, mq, mt, hq, ht], slot);
  }
  assert.equal(line(Qt, 'valley').need.value, 41.86);
  assert.equal(Qt.totals[MN].amount, r2(6746.27 + 177.45));
  assert.equal(Qt.totals[HD].amount, r2(6533.59 + 115));
  const plain = quote(q);
  assert.deepEqual([plain.totals[MN].amount, plain.totals[HD].amount, plain.totals.lowest.amount], [6746.27, 6533.59, 6431.38]);
});

test('plan-precision inputs: same quantities and totals; two needs differ by a cent', () => {
  const a = quote(Q3, job({ valleyMetal: true })), b = quote(QP, job({ valleyMetal: true }));
  for (const l of a.lines) {
    const m = line(b, l.slot);
    for (const s of [MN, HD]) assert.deepEqual([m.cells[s].qty, m.cells[s].lineTotal], [l.cells[s].qty, l.cells[s].lineTotal], `${l.slot} ${s}`);
  }
  // 2743.25 x 1.10 = 3017.575 and 39.86 x 1.05 = 41.853: the plan's 3,017.57 and 41.86 come from the unrounded geometry
  assert.equal(line(b, 'underlayment').need.value, 3017.58);
  assert.equal(line(b, 'valley').need.value, 41.85);
  assert.deepEqual([b.totals[MN].amount, b.totals[HD].amount], [a.totals[MN].amount, a.totals[HD].amount]);
});

test('unknowns name who sets them, and no zero is printed', () => {
  const j = job();
  j.selections.covering[HD] = { productId: 'hd-fixture-atlas', color: 'Weathered Wood', source: 'chosen' };
  j.selections.starter[HD] = null;
  j.selections.ridgeVent[MN] = { productId: 'mn-gone-from-catalog', color: null, source: 'chosen' };
  let Qt = quote(Q3, j);
  const noPrice = line(Qt, 'covering').cells[HD];
  assert.deepEqual([noPrice.status, noPrice.why, noPrice.setBy], ['noPrice', 'no price: ask the store', 'the store (Browse Only item), or type a price']);
  assert.equal(noPrice.qty, 97, 'the quantity is still known');
  assert.deepEqual([noPrice.unitPriceText, noPrice.totalText], ['–', '–']);
  assert.equal(line(Qt, 'covering').lower, null);
  const notChosen = line(Qt, 'starter').cells[HD];
  assert.deepEqual([notChosen.status, notChosen.why, notChosen.setBy, notChosen.qtyText], ['notChosen', 'not chosen', 'you: pick a product', '–']);
  assert.equal(line(Qt, 'ridgeVent').cells[MN].status, 'notChosen', 'an id missing from the catalog reads "not chosen"');
  assert.deepEqual(Qt.totals[HD].missing, ['Shingles / panels', 'Starter', 'Fasteners', 'Deck repair']);
  // lowest per line uses the one known cell and is marked incomplete
  assert.deepEqual(Qt.totals.lowest.oneStore, ['Shingles / panels', 'Starter', 'Ridge vent']);
  assert.equal(Qt.totals.lowest.picks.covering, MN);

  const k = job();
  k.selections.covering[HD] = { productId: 'hd-fixture-panel-length', color: null, source: 'chosen' };
  Qt = quote(Q3, k);
  const noQty = line(Qt, 'covering').cells[HD];
  assert.deepEqual([noQty.status, noQty.why, noQty.setBy], ['noQuantity', 'quantity unknown: the store does not state the coverage', 'you: type the coverage from the wrapper or spec sheet']);
  assert.deepEqual([noQty.qty, noQty.qtyText, noQty.lineTotal], [null, '–', null]);
  assert.equal(noQty.needs.coverage, true);
  k.selections.covering[HD].typedCoverage = 36;
  const fixed = line(quote(Q3, k), 'covering').cells[HD];
  assert.deepEqual([fixed.status, fixed.qty, fixed.lineTotal], ['priced', ceilQty(3209.60 / 36), r2(ceilQty(3209.60 / 36) * 25.98)]);
});

test('pack counts and gross panel area', () => {
  const j = job();
  j.selections.covering[HD] = { productId: 'hd-fixture-panel-pack', color: null, source: 'chosen' };
  j.selections.ridgeVent[HD] = { productId: 'hd-fixture-vent-carton', color: null, source: 'chosen' };
  const Qt = quote(Q3, j);
  const panel = line(Qt, 'covering').cells[HD];
  assert.equal(panel.qty, 33); // 3,209.60 / 99.1 = 32.4
  assert.equal(panel.unit, 'pack of 20');
  assert.ok(panel.notes.includes('gross panel area: side laps are not deducted'));
  const vent = line(Qt, 'ridgeVent').cells[HD];
  assert.equal(vent.pieces, 12); // 46.75 / 4
  assert.equal(vent.qty, 2);
  assert.equal(vent.unit, 'carton of 10');
  assert.equal(vent.lineTotal, 296);
});

test('packCount on a shingle counts shingles per bundle: still bundles, price per bundle', () => {
  const j = job();
  j.selections.covering[HD] = { productId: 'hd-fixture-uhdz', color: 'Pewter Gray', source: 'chosen' };
  const c = line(quote(Q3, j), 'covering').cells[HD];
  assert.deepEqual([c.qty, c.unit, c.unitPrice, c.lineTotal], [97, 'bundle', 54.97, r2(97 * 54.97)]);
});

test('typed unit price on a store product', () => {
  const j = job();
  j.selections.covering[HD] = { productId: 'hd-fixture-atlas', color: 'Weathered Wood', source: 'chosen', typedPrice: 41.5 };
  const Qt = quote(Q3, j);
  const c = line(Qt, 'covering').cells[HD];
  assert.deepEqual([c.status, c.priceSource, c.unitPrice, c.lineTotal], ['priced', 'typed', 41.5, r2(97 * 41.5)]);
  assert.equal(Qt.totals[HD].includesTyped, true);
  assert.match(Qt.totals[HD].text, /includes typed prices/);
});

test('sale ended note, age banner, header and notes', () => {
  const j = job();
  j.selections.covering[MN] = { productId: 'mn-fixture-sale', color: null, source: 'chosen' };
  assert.ok(line(quote(Q3, j), 'covering').cells[MN].notes.includes('sale ended 11/10/26: check the price'));
  assert.ok(!line(quote(), 'covering').cells[MN].notes.some((n) => /sale ended/.test(n)), 'Duration sale runs to 11/26/26');
  const Qt = quote();
  assert.equal(Qt.status.header, HEADER);
  assert.equal(HEADER, 'Internal estimate from store snapshots. Not a quote.');
  assert.equal(Qt.status.age.text, 'Prices captured Nov 15, 2026 (Menards) and Nov 15–16, 2026 (Home Depot). Re-capture before quoting.');
  assert.equal(Qt.status.age.daysOld, 1);
  assert.equal(ageBanner(CATALOG, [MN, HD], '2026-11-30').text.startsWith('15 days old. Prices captured Nov 15, 2026'), true);
  assert.deepEqual(Qt.notes, [NOT_INCLUDED]);
  assert.equal(NOT_INCLUDED, 'Not included: tax, delivery, labor, flashing, pipe boots, vents other than the ridge vent.');
  const b = quote(Q3, job({ roofSource: 'builtin' }), { roofName: 'Cedar shake (built-in)' });
  assert.equal(b.notes[0], 'The roof shows Cedar shake (built-in), which is not a store product. Prices below are for the store products chosen.');
  for (const t of Object.values(Qt.totals)) assert.doesNotMatch(t.text, /approv|quote/i);
});

test('saved prices (priceOverride) are shown with the current price beside them', () => {
  const saved = {
    'mn-1444450489132': { name: 'Duration, as saved', shelf: 44.02, per: 'bundle', startingAt: false, rebate: 5.07, coverage: { sqft: 32.8 }, pieceFt: null, packCount: null },
    'mn-retired': { name: 'Retired ridge vent', shelf: 60, per: 'each', startingAt: false, rebate: null, coverage: null, pieceFt: 20, packCount: null },
  };
  const j = job();
  j.selections.ridgeVent[MN] = { productId: 'mn-retired', color: null, source: 'chosen' };
  const Qt = quote(Q3, j, { priceOverride: saved });
  assert.equal(Qt.status.prices, 'saved');
  const c = line(Qt, 'covering').cells[MN];
  assert.deepEqual([c.unitPrice, c.lineTotal, c.name], [44.02, r2(98 * 44.02), 'Duration, as saved']);
  assert.deepEqual(c.current, { unitPrice: 46.06, delta: 2.04 });
  assert.ok(c.notes.includes('now $46.06 (+$2.04)'));
  const gone = line(Qt, 'ridgeVent').cells[MN];
  assert.deepEqual([gone.status, gone.name, gone.lineTotal], ['priced', 'Retired ridge vent', 180]);
  assert.ok(gone.notes.includes('no longer in the store capture'));
});

test('crew view and crew CSV carry no prices', () => {
  const Qt = quote(Q3, job({ typed: { nails: 89, deckRepair: 96 } }));
  const crew = crewView(Qt, MN);
  assert.equal(crew.store.name, 'Menards');
  const banned = ['unitPrice', 'lineTotal', 'rebate', 'totals', 'lower', 'priceSource', 'unitPriceText', 'totalText'];
  const keys = JSON.stringify(crew);
  for (const k of banned) assert.ok(!keys.includes(`"${k}"`), `crew view has no ${k}`);
  assert.ok(!keys.includes('$'));
  assert.deepEqual(crew.lines.find((l) => l.slot === 'covering'), {
    slot: 'covering', label: 'Shingles / panels', product: PRODUCTS[0].name, color: 'Sierra Gray', qty: 98, qtyText: '98', unit: 'bundle', measured: '2,743 sq ft', why: null,
  });
  const csv = quoteCSV(Qt, { view: 'crew', store: MN });
  assert.ok(!csv.includes('$'), 'no $ anywhere in the crew file');
  assert.ok(csv.startsWith('﻿Line,Product,Color,Quantity,Unit,Measured\r\n'));
  const rows = csv.slice(1).trimEnd().split('\r\n');
  assert.equal(rows.length, 1 + Qt.lines.length);
  assert.ok(rows.includes('Ridge vent,Owens Corning VentSure 11-1/4" x 20\' Shingle-Over Ridge Vent,Black,3,each,46.8 ft') === false, 'a field with a quote is quoted');
  assert.ok(rows.includes('Ridge vent,"Owens Corning VentSure 11-1/4"" x 20\' Shingle-Over Ridge Vent",Black,3,each,46.8 ft'));
});

test('office CSV: RFC 4180, CRLF, BOM, one row per line per store, totals, rebate, capture dates', () => {
  const Qt = quote();
  const csv = quoteCSV(Qt);
  assert.ok(csv.startsWith('﻿Line,Measured,Allowance,Store,Product,Color,Quantity,Unit,Unit price,Price source,Line total,Status,Note\r\n'));
  assert.ok(csv.endsWith('\r\n'));
  assert.ok(!/[^\r]\n/.test(csv), 'every line ends in CRLF');
  const rows = csv.slice(1).trimEnd().split('\r\n');
  assert.ok(rows.includes('Shingles / panels,"2,743 sq ft",17% waste,Menards,Owens Corning TruDefinition Duration Sierra Gray Architectural Roofing Shingles (32.8 sq. ft.),Sierra Gray,98,bundle,46.06,store,4513.88,priced,suggested; lower'));
  assert.ok(rows.some((r) => r.startsWith('Fasteners,') && r.includes(',Menards,,,21840,nails,,,,no price,no price: not in the store data; set by you: type the amount for this line')));
  assert.ok(rows.includes('Total,,,Menards,,,,,,,6746.27,incomplete,"Total incomplete: $6,746.27 so far. Missing: Fasteners, Deck repair."'));
  assert.ok(rows.includes('Total,,,Home Depot,,,,,,,6533.59,incomplete,"Total incomplete: $6,533.59 so far. Missing: Fasteners, Deck repair."'));
  assert.ok(rows.some((r) => r.startsWith('Total,,,Lowest per line,,,,,,,6431.38,incomplete,')));
  assert.ok(rows.includes('Rebate,,,Menards,,,,,,,742.49,not in the total,11% mail-in rebate ended 11/15/26. It would have been $742.49 in store credit. Not in the total.'));
  assert.ok(rows.some((r) => r.startsWith('Prices captured,') && r.endsWith('Re-capture before quoting."')));
  // 9 lines x 2 stores, header, blank, 3 totals, rebate, capture, header note, not-included note
  assert.equal(rows.length, 1 + 9 * 2 + 1 + 3 + 1 + 1 + 1 + 1);
  for (const r of rows) assert.equal(csvFields(r).length, 13, `13 fields: ${r}`);
  assert.deepEqual(csvFields('a,"b, ""c""",,d'), ['a', 'b, "c"', '', 'd']);
  assert.equal(csvFileName('Untitled roof', TODAY), 'materials-untitled-roof-2026-11-16.csv');
  assert.equal(csvFileName('Untitled roof', TODAY, 'crew'), 'materials-crew-untitled-roof-2026-11-16.csv');
});
