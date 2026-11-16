// Project files (viewer/js/project-file.js): build, validate, round trip, price snapshots. Supplier plan, section 8.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildProject, parseProject, compareSnapshot, snapshotNotice, jobFromProject, snapshotItem, projectFileName, sameProject,
  PROJECT_FORMAT, PROJECT_VERSION,
} from '../viewer/js/project-file.js';
import { buildQuote } from '../viewer/js/quote.js';

const MN = 'menards-3064', HD = 'homedepot-4301';

// Fixture catalog: the suggested basket, prices and coverages copied from catalog/suppliers/sioux-falls.json
// (version 1, HEAD eb95163). image and colors[].swatch are kept so the test can check they never reach a project file.
const P = (id, store, layer, price, rest = {}) => ({ id, store, layer, name: `${layer} ${id}`, price, image: `https://cdn.example/${id}.jpg`, colors: [{ name: 'Black', swatch: `https://cdn.example/${id}-sw.jpg` }], ...rest });
const mn = (shelf, rebate, per) => ({ shelf, rebate, rebateThrough: '11/15/26', per });
const PRODUCTS = [
  P('mn-1444450489132', MN, 'covering', { ...mn(46.06, 5.07, 'bundle'), saleThrough: '11/26/26' }, { category: 'shingle', color: 'Sierra Gray', coverage: { sqft: 32.8 } }), // Duration
  P('mn-1642874276146419', MN, 'ridgeCap', mn(79.99, 8.8, 'bundle'), { coverage: { lf: 33 } }), // ProEdge
  P('mn-1444450475975', MN, 'starter', mn(54.97, 6.05, 'bundle'), { coverage: { lf: 105 } }), // Starter Strip Plus
  P('mn-1444450500228', MN, 'underlayment', mn(119, 13.09, 'each'), { coverage: { sqft: 1000 } }), // ProArmor
  P('mn-1444450479015', MN, 'iceWater', mn(119, 13.09, 'each'), { coverage: { sqft: 200 } }), // WeatherLock G
  P('mn-1444424196953', MN, 'dripEdge', mn(9.98, 1.1, 'each'), { pieceFt: 12 }), // Style-D white 12 ft
  P('mn-1444450488871', MN, 'ridgeVent', mn(65.98, 7.26, 'each'), { pieceFt: 20 }), // VentSure 20 ft
  P('mn-1444448528388', MN, 'valley', mn(35.49, 3.9, 'each'), { pieceFt: 10 }), // W valley
  P('hd-309755006', HD, 'covering', { shelf: 46.97, per: 'bundle' }, { category: 'shingle', color: 'Charcoal', coverage: { sqft: 33.33 }, stock: { inStock: true, qty: 141 } }), // Timberline HDZ
  P('hd-206593176', HD, 'ridgeCap', { shelf: 62.97, per: 'bundle' }, { coverage: { lf: 25 }, stock: { inStock: true, qty: 19 } }), // Seal-A-Ridge
  P('hd-202052408', HD, 'starter', { shelf: 54.97, per: 'each' }, { coverage: { lf: 120 } }), // Pro-Start
  P('hd-340399395', HD, 'underlayment', { shelf: 70.8, per: 'roll' }, { coverage: { sqft: 1000 } }), // Pro Synthetic
  P('hd-100083275', HD, 'iceWater', { shelf: 129, per: 'roll' }, { coverage: { sqft: 200 } }), // WeatherWatch 200
  P('hd-100087282', HD, 'dripEdge', { shelf: 7.68, per: 'each' }, { pieceFt: 10 }), // C3 white 10 ft
  P('hd-316349297', HD, 'ridgeVent', { shelf: 61.75, per: 'roll' }, { pieceFt: 20 }), // Air Vent 20 ft
  P('hd-100096067', HD, 'valley', { shelf: 23, per: 'each' }, { coverage: { sqft: 11.7 }, pieceFt: 10 }), // roll valley
];
const catalogWith = (products = PRODUCTS, sources = { menards: { dir: 'lab/data/suppliers/menards-3064-2026-11-15', productsSha256: 'be651dd7b4307a3c' }, homedepot: { file: 'materials.json', sha256: '06040ac740d39e77' } }) => ({
  version: 2, stores: { [MN]: { name: 'Menards Sioux Falls West', captured: '2026-11-15' }, [HD]: { name: 'The Home Depot #4301', captured: '2026-11-15/16' } },
  sources, products,
});
const CATALOG = catalogWith();

const SLOT_IDS = {
  covering: ['mn-1444450489132', 'hd-309755006'], ridgeCap: ['mn-1642874276146419', 'hd-206593176'], starter: ['mn-1444450475975', 'hd-202052408'],
  underlayment: ['mn-1444450500228', 'hd-340399395'], iceWater: ['mn-1444450479015', 'hd-100083275'], dripEdge: ['mn-1444424196953', 'hd-100087282'],
  ridgeVent: ['mn-1444450488871', 'hd-316349297'], valley: ['mn-1444448528388', 'hd-100096067'],
};
function makeJob() {
  const selections = {};
  for (const [slot, [m, h]] of Object.entries(SLOT_IDS)) selections[slot] = { [MN]: { productId: m, color: null, source: 'suggested' }, [HD]: { productId: h, color: null, source: 'suggested' } };
  selections.covering[MN] = { productId: 'mn-1444450489132', color: 'Sierra Gray', source: 'chosen' };
  selections.dripEdge[HD] = null;
  selections.ridgeCap[HD] = { productId: 'hd-206593176', color: 'Charcoal', source: 'chosen', typedPrice: 59.5 };
  return { name: 'Smith ranch', shownStore: MN, roofSource: 'store', waste: { pct: 17, source: 'suggested' }, valleyMetal: false,
    selections, typed: { nails: 89, deckRepair: null }, snapshot: null, dirty: true };
}
// quantities() for the ranch demo, unrounded (the project rounds them to 0.01)
const Q = { areaSqft: 2743.2455142, squares: 27.432455, eaveFt: 191.2729659, rakeFt: 29.7115332, ridgeFt: 50.6889764, hipFt: 107.2834646, valleyFt: 39.8622047,
  iceSqft: 1055.1000269, iceRows: 2, ventFt: 46.7519685, nailCount: 21840, deckRepairSheets: 3, category: 'shingle' };
const TODAY = '2026-11-16';

function state(job = makeJob(), catalog = CATALOG, extra = {}) {
  const quote = buildQuote({ q: Q, job, catalog, today: TODAY, priceOverride: job.snapshot?.items ?? null });
  return {
    job, catalog, quote, measured: Q, savedAt: '2026-11-16T15:04:00Z',
    site: { location: 'Sioux Falls, SD', lat: 43.54 },
    house: { source: 'preset', presetId: 'ranch-hip', pitch: 6 },
    sun: { date: TODAY, hour: 15, facing: 180 },
    layers: {
      options: { iceRows: 'auto', valleys: true, ridgeVent: true, deckSheets: 3, dripEdge: { id: 'mn-1444424196953', label: 'Style-D White', color: '#f2f2f0', metal: 0.3 } },
      custom: [{ id: 'photo-1', name: 'My shingle', image: 'data:image/jpeg;base64,AAAA', dataUrl: 'data:image/png;base64,BBBB', tint: '#333333' }],
      hidden: ['oldFelt'],
    },
    roof: { source: 'store', store: MN, productId: 'mn-1444450489132', color: 'Sierra Gray', view: { scale: 1, rotation: 0, offsetV: 0, reliefScale: 1, tint: null } },
    ...extra,
  };
}

function keysDeep(v, out = new Set()) {
  if (Array.isArray(v)) v.forEach((x) => keysDeep(x, out));
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) { out.add(k); keysDeep(x, out); }
  return out;
}

// ---------------------------------------------------------------------------

test('build -> stringify -> parse is the same object', () => {
  const p = buildProject(state());
  const text = JSON.stringify(p);
  const r = parseProject(text);
  assert.equal(r.ok, true, r.errors.join(' '));
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.project, p);
  assert.equal(parseProject(p).ok, true, 'an object is accepted too (roofStudio.loadProject)');
  assert.equal(p.format, PROJECT_FORMAT);
  assert.equal(p.version, PROJECT_VERSION);
  assert.equal(p.name, 'Smith ranch');
  assert.equal(p.savedAt, '2026-11-16T15:04:00Z');
  assert.deepEqual(p.job, { location: 'Sioux Falls, SD', lat: 43.54 });
  assert.deepEqual(p.house, { source: 'preset', presetId: 'ranch-hip', pitch: 6 });
  assert.deepEqual(p.waste, { pct: 17, source: 'suggested' });
  assert.deepEqual(p.typed, { nails: 89, deckRepair: null });
  assert.equal(p.selections.dripEdge[HD], null);
  assert.equal(p.selections.ridgeCap[HD].typedPrice, 59.5);
  assert.equal(p.layers.options.dripEdge.label, 'Style-D White', 'option objects are kept');
  assert.equal(projectFileName(p.name), 'smith-ranch.rooftec.json');
});

test('reopening gives back the job, and the same list totals', () => {
  const s = state();
  const p = JSON.parse(JSON.stringify(buildProject(s)));
  const job = jobFromProject(parseProject(p).project);
  const { snapshot, dirty, ...rest } = job;
  const { snapshot: s0, dirty: d0, ...want } = s.job;
  assert.deepEqual(rest, want);
  assert.equal(dirty, false);
  assert.deepEqual(snapshot, p.priceSnapshot);
  // unchanged catalog: the studio uses the catalog; the totals are the same as before saving
  const cmp = compareSnapshot(p, CATALOG);
  assert.equal(cmp.unchanged, true);
  const again = buildQuote({ q: p.measured, job: { ...job, snapshot: null }, catalog: CATALOG, today: TODAY });
  for (const id of [MN, HD, 'lowest']) assert.equal(again.totals[id].amount, s.quote.totals[id].amount, id);
  assert.deepEqual(p.priceSnapshot.totals, { [MN]: { amount: s.quote.totals[MN].amount, status: s.quote.totals[MN].status }, [HD]: { amount: s.quote.totals[HD].amount, status: s.quote.totals[HD].status } });
  assert.equal(snapshotNotice(cmp, p.priceSnapshot.savedOn), 'Saved Nov 16, 2026');
  // and a second save of the reopened job is the same project
  assert.equal(sameProject(buildProject({ ...s, job: { ...job, snapshot: null }, savedAt: '2026-11-16T18:30:00Z' }), p), true);
});

test('price snapshot: date, sources, one item per chosen product, totals', () => {
  const s = state();
  const snap = buildProject(s).priceSnapshot;
  assert.equal(snap.savedOn, '2026-11-16');
  assert.deepEqual(snap.sources, {
    menards: { productsSha256: 'be651dd7b4307a3c', captured: '2026-11-15' },
    homedepot: { sha256: '06040ac740d39e77', captured: '2026-11-15/16' },
  });
  assert.equal(Object.keys(snap.items).length, 15, '16 suggested products less the cleared Home Depot drip edge');
  assert.deepEqual(snap.items['mn-1444450489132'], {
    name: 'covering mn-1444450489132', shelf: 46.06, per: 'bundle', startingAt: false, rebate: 5.07, rebateThrough: '11/15/26',
    coverage: { sqft: 32.8 }, pieceFt: null, packCount: null,
  });
  assert.deepEqual(snapshotItem(PRODUCTS[5]), { name: 'dripEdge mn-1444424196953', shelf: 9.98, per: 'each', startingAt: false, rebate: 1.1, rebateThrough: '11/15/26', coverage: null, pieceFt: 12, packCount: null });
  // the plan's example total: the default basket, nothing typed
  const plain = makeJob();
  for (const [slot, [m, h]] of Object.entries(SLOT_IDS)) plain.selections[slot] = { [MN]: { productId: m, color: null, source: 'suggested' }, [HD]: { productId: h, color: null, source: 'suggested' } };
  plain.typed = { nails: null, deckRepair: null };
  assert.deepEqual(buildProject(state(plain)).priceSnapshot.totals[MN], { amount: 6746.27, status: 'incomplete' });
});

test('measured is the quantities() object rounded to 0.01', () => {
  const m = buildProject(state()).measured;
  assert.deepEqual(m, { areaSqft: 2743.25, squares: 27.43, eaveFt: 191.27, rakeFt: 29.71, ridgeFt: 50.69, hipFt: 107.28, valleyFt: 39.86,
    iceSqft: 1055.1, iceRows: 2, ventFt: 46.75, nailCount: 21840, deckRepairSheets: 3, category: 'shingle' });
});

test('no image, swatch or dataUrl key anywhere in a saved project', () => {
  const p = buildProject(state());
  const keys = keysDeep(p);
  for (const k of ['image', 'swatch', 'dataUrl']) assert.ok(!keys.has(k), `no "${k}" key`);
  assert.ok(!JSON.stringify(p).includes('data:'), 'no data: URL');
  assert.ok(!JSON.stringify(p).includes('cdn.example'), 'no store image link');
  assert.deepEqual(p.layers.custom, [{ id: 'photo-1', name: 'My shingle', tint: '#333333' }]);
});

test('house model and photo roofs save only their names', () => {
  const p = buildProject(state(makeJob(), CATALOG, {
    house: { source: 'glb', fileName: 'smith.glb', units: 'm', buffer: new ArrayBuffer(8), presetId: 'ranch-hip' },
    roof: { source: 'photo', name: 'IMG_2041.jpg', image: 'data:image/jpeg;base64,AAAA', productId: 'x' },
  }));
  assert.deepEqual(p.house, { source: 'glb', fileName: 'smith.glb', units: 'm' });
  assert.deepEqual(p.roof, { source: 'photo', name: 'IMG_2041.jpg' });
  assert.equal(parseProject(JSON.stringify(p)).ok, true, 'no pitch needed for a house model');
  assert.equal(jobFromProject(p).roofSource, 'builtin');
  const b = buildProject(state(makeJob(), CATALOG, { roof: { source: 'builtin', id: 'cedar-shake', view: null } }));
  assert.deepEqual(b.roof, { source: 'builtin', id: 'cedar-shake', view: null });
});

test('a changed price is reported with was and now; a gone product is reported', () => {
  const p = buildProject(state());
  const next = PRODUCTS.filter((x) => x.id !== 'hd-316349297')
    .map((x) => (x.id === 'mn-1444450489132' ? { ...x, price: { ...x.price, shelf: 48.10 } } : x))
    .map((x) => (x.id === 'hd-202052408' ? { ...x, coverage: { lf: 100 } } : x));
  const cat2 = catalogWith(next, { menards: { productsSha256: '0000000000000000' }, homedepot: { sha256: '06040ac740d39e77' } });
  const cmp = compareSnapshot(p, cat2);
  assert.equal(cmp.sameSources, false);
  assert.equal(cmp.unchanged, false);
  assert.deepEqual(cmp.changed, [
    { productId: 'mn-1444450489132', name: 'covering mn-1444450489132', was: 46.06, now: 48.10, fields: ['shelf'] },
    { productId: 'hd-202052408', name: 'starter hd-202052408', was: 54.97, now: 54.97, fields: ['coverage'] },
  ]);
  assert.deepEqual(cmp.missing, [{ productId: 'hd-316349297', name: 'ridgeVent hd-316349297', was: 61.75 }]);
  assert.deepEqual(compareSnapshot(p.priceSnapshot, cat2), cmp, 'the snapshot alone works too');
  assert.equal(snapshotNotice(cmp, p.priceSnapshot.savedOn),
    'Showing prices as saved on Nov 16, 2026. The store data has changed since: 1 price differs, 1 product has other changes, 1 product is gone.');
  // the list keeps the saved prices, so the totals do not move; "now" sits beside the saved price
  const saved = buildQuote({ q: p.measured, job: jobFromProject(p), catalog: cat2, today: TODAY, priceOverride: p.priceSnapshot.items });
  const before = state().quote;
  for (const id of [MN, HD]) assert.equal(saved.totals[id].amount, before.totals[id].amount, id);
  const cov = saved.lines.find((l) => l.slot === 'covering').cells[MN];
  assert.equal(cov.unitPrice, 46.06);
  assert.ok(cov.notes.includes('now $48.10 (+$2.04)'));
  assert.ok(saved.lines.find((l) => l.slot === 'ridgeVent').cells[HD].notes.includes('no longer in the store capture'));
  // re-saving while saved prices are shown keeps the snapshot's date and prices
  const resaved = buildProject({ ...state(jobFromProject(p), cat2), savedAt: '2026-11-20T10:00:00Z' });
  assert.equal(resaved.priceSnapshot.savedOn, '2026-11-16');
  assert.deepEqual(resaved.priceSnapshot.items, p.priceSnapshot.items);
  assert.deepEqual(resaved.priceSnapshot.sources, p.priceSnapshot.sources);
});

test('three prices and a gone product: the plan notice', () => {
  const p = buildProject(state());
  const bump = new Set(['mn-1444450489132', 'mn-1444450500228', 'hd-100083275']);
  const cat2 = catalogWith(PRODUCTS.filter((x) => x.id !== 'mn-1444448528388').map((x) => (bump.has(x.id) ? { ...x, price: { ...x.price, shelf: x.price.shelf + 1 } } : x)));
  const cmp = compareSnapshot(p, cat2);
  assert.equal(cmp.sameSources, true, 'same hashes');
  assert.equal(snapshotNotice(cmp, '2026-11-16'), 'Showing prices as saved on Nov 16, 2026. The store data has changed since: 3 prices differ, 1 product is gone.');
});

test('validation: newer version, wrong format, unknown ids, non-numeric pitch or waste', () => {
  const good = buildProject(state());
  const bad = (patch) => parseProject(JSON.stringify({ ...JSON.parse(JSON.stringify(good)), ...patch }));
  const v2 = bad({ version: 2 });
  assert.equal(v2.ok, false);
  assert.equal(v2.project, null);
  assert.equal(v2.errors[0], 'This project was saved by a newer studio (file version 2); this studio opens version 1. Update the studio to open it.');
  assert.match(bad({ format: 'something-else' }).errors[0], /not a studio project/);
  assert.match(parseProject('{ not json').errors[0], /not valid JSON/);
  assert.match(parseProject('[1, 2]').errors[0], /not a studio project/);
  assert.match(bad({ version: 0 }).errors[0], /no valid version/);
  assert.equal(bad({ shownStore: 'lowes-1234' }).errors[0], 'Unknown store "lowes-1234" in shownStore.');
  assert.equal(bad({ selections: { ...good.selections, gutter: {} } }).errors[0], 'Unknown slot "gutter" in selections.');
  assert.equal(bad({ selections: { covering: { 'lowes-1234': null } } }).errors[0], 'Unknown store "lowes-1234" in selections.covering.');
  assert.equal(bad({ house: { source: 'preset', presetId: 'ranch-hip', pitch: 'steep' } }).errors[0], 'Pitch must be a number (got "steep").');
  assert.equal(bad({ waste: { pct: '17', source: 'typed' } }).errors[0], 'Waste % must be a number (got "17").');
  assert.match(bad({ typed: { nails: 'eighty', deckRepair: null } }).errors[0], /typed\.nails must be a number/);
  const extra = bad({ futureFeature: { a: 1 } });
  assert.equal(extra.ok, true, 'unknown extra keys are kept and ignored');
  assert.deepEqual(extra.project.futureFeature, { a: 1 });
});

test('sameProject ignores savedAt and key order only', () => {
  const a = buildProject(state());
  const b = buildProject({ ...state(), savedAt: '2026-11-16T23:59:00Z' });
  assert.equal(sameProject(a, b), true);
  const reordered = Object.fromEntries(Object.entries(a).reverse());
  assert.equal(sameProject(a, reordered), true);
  assert.equal(sameProject(a, { ...a, waste: { pct: 15, source: 'typed' } }), false);
});
