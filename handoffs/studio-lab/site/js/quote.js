// Priced materials list: measured roof quantities -> store quantities, prices, totals, crew view, CSV.
// Pure: no DOM, no three, so `node --test` can import it. Rules: supplier plan, section 6.
//
// Input `q` is the measured-input object of `RoofLayers.quantities()` (feet and square feet):
//   { areaSqft, squares, eaveFt, rakeFt, ridgeFt, hipFt, valleyFt, iceSqft, iceRows, ventFt,
//     nailCount, deckRepairSheets, category }
// `toQuantities()` below builds it from metric measurements, so layers.js can stay a thin wrapper.

import { slugify } from './util.js';

export const LINEAR_ALLOWANCE = 0.05;
export const LAP_ALLOWANCE = 0.10;
export const ceilQty = (x) => Math.ceil(x - 1e-9);

export const STORE_IDS = ['menards-3064', 'homedepot-4301'];
export const STORE_SHORT = { 'menards-3064': 'Menards', 'homedepot-4301': 'Home Depot' };
/** Product slots: the layer ids that take a store product, plus `valley`. */
export const SLOTS = ['covering', 'ridgeCap', 'starter', 'underlayment', 'iceWater', 'dripEdge', 'ridgeVent', 'valley'];
/** Lines with no store product: the job holds a typed whole-line amount for each. */
export const TYPED_LINES = ['nails', 'deckRepair'];
export const LINE_LABELS = {
  covering: 'Shingles / panels', ridgeCap: 'Hip & ridge cap', starter: 'Starter', underlayment: 'Underlayment',
  iceWater: 'Ice & water', dripEdge: 'Drip edge', ridgeVent: 'Ridge vent', valley: 'Valley',
  nails: 'Fasteners', deckRepair: 'Deck repair',
};
export const HEADER = 'Internal estimate from store snapshots. Not a quote.';
export const NOT_INCLUDED = 'Not included: tax, delivery, labor, flashing, pipe boots, vents other than the ridge vent.';
export const STATUS_TEXT = { priced: 'priced', startingAt: 'starting at', noPrice: 'no price', noQuantity: 'quantity unknown', notChosen: 'not chosen' };

const FT = 0.3048;
const SQFT_M2 = FT * FT;
const DASH = '–'; // en dash: the number column for anything unknown
/** Ridge vent inset at each end and shortest ridge that gets a vent (matches ridgeVentGeometry). */
export const VENT_INSET_M = 0.3;
export const VENT_MIN_M = VENT_INSET_M * 2 + 0.3;

const MISSING = new Set(['noPrice', 'noQuantity', 'notChosen']);
const UNKNOWN = {
  noPrice: { why: 'no price: ask the store', setBy: 'the store (Browse Only item), or type a price' },
  noPriceTyped: { why: 'no price: not in the store data', setBy: 'you: type the amount for this line' },
  noQuantity: { why: 'quantity unknown: the store does not state the coverage', setBy: 'you: type the coverage from the wrapper or spec sheet' },
  notChosen: { why: 'not chosen', setBy: 'you: pick a product' },
};

// ---------------------------------------------------------------------------
// formatting and dates

export const round2 = (x) => Math.round(x * 100) / 100;
export const fmtMoney = (x) => x.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
const fmtNum = (x, d = 0) => x.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** 'YYYY-MM-DD' -> UTC milliseconds, or NaN. */
export function parseISODate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
}
/** Store date 'MM/DD/YY' -> UTC milliseconds, or NaN. */
export function parseMDY(s) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/.exec(String(s || '').trim());
  if (!m) return NaN;
  const y = m[3].length === 2 ? 2000 + +m[3] : +m[3];
  return Date.UTC(y, +m[1] - 1, +m[2]);
}
/** '2026-11-16' -> 'Nov 16, 2026'; a capture '2026-11-15/16' -> 'Nov 15–16, 2026'. */
export function fmtDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:\/(\d{2}))?/.exec(String(s || ''));
  if (!m) return String(s || '');
  return `${MONTHS[+m[2] - 1]} ${+m[3]}${m[4] ? `${DASH}${+m[4]}` : ''}, ${m[1]}`;
}
const DAY = 86400000;

// ---------------------------------------------------------------------------
// measured inputs

/** Length of ridge vent over the given ridge lengths (metres): each ridge of 0.9 m or more, less 0.3 m at each end. */
export function ventLengthM(ridgeLengthsM = []) {
  return ridgeLengthsM.reduce((s, len) => (len < VENT_MIN_M ? s : s + len - 2 * VENT_INSET_M), 0);
}

/**
 * Build the `quantities()` object from metric measurements.
 * measure: measureRoof() output ({ areaM2, eaveM, rakeM, ridgeM, hipM, valleyM }); ridgeLengthsM: each ridge line's length;
 * iceM2: area of the ice & water mesh (0 when the layer is missing); ventOn: false when the ridge vent is off.
 */
export function toQuantities({ measure, ridgeLengthsM = [], iceM2 = 0, iceRows = 0, ventOn = true, nailCount = 0, deckRepairSheets = 0, category = 'shingle' }) {
  const ft = (m) => (m || 0) / FT;
  const areaSqft = (measure.areaM2 || 0) / SQFT_M2;
  return {
    areaSqft, squares: areaSqft / 100,
    eaveFt: ft(measure.eaveM), rakeFt: ft(measure.rakeM), ridgeFt: ft(measure.ridgeM), hipFt: ft(measure.hipM), valleyFt: ft(measure.valleyM),
    iceSqft: (iceM2 || 0) / SQFT_M2, iceRows,
    ventFt: ventOn ? ft(ventLengthM(ridgeLengthsM)) : 0,
    nailCount, deckRepairSheets, category,
  };
}

// ---------------------------------------------------------------------------
// lines

const pctText = (pct, what) => `${pct}% ${what}`;
const FIXED = 'the studio (fixed rule)';

/** The line rules of section 6.2, in list order. `basis` is [value, unit, text]. */
function lineRules(q, job) {
  const lin = (v) => [v, 'ft', `${fmtNum(v, 1)} ft`];
  const area = (v) => [v, 'sq ft', `${fmtNum(v)} sq ft`];
  const waste = Number(job.waste?.pct) || 0;
  const wasteBy = job.waste?.source === 'typed' ? 'you, Waste %'
    : 'suggested from the hips and valleys; change it with Waste % above';
  const iceText = `${fmtNum(q.iceSqft || 0)} sq ft (${q.iceRows || 0} eave rows${q.valleyFt > 0 ? ' + valleys' : ''})`;
  return [
    { slot: 'covering', basis: area(q.areaSqft), pct: waste, what: 'waste', setBy: wasteBy, kind: 'covering' },
    { slot: 'ridgeCap', basis: lin(q.ridgeFt + q.hipFt), pct: LINEAR_ALLOWANCE * 100, what: 'laps and cuts', kind: 'linear', lf: true },
    { slot: 'starter', basis: lin(q.eaveFt + q.rakeFt), pct: LINEAR_ALLOWANCE * 100, what: 'laps and cuts', kind: 'linear', lf: true, skip: q.category === 'metal' },
    { slot: 'underlayment', basis: area(q.areaSqft), pct: LAP_ALLOWANCE * 100, what: 'laps', kind: 'area' },
    { slot: 'iceWater', basis: [q.iceSqft, 'sq ft', iceText], pct: LAP_ALLOWANCE * 100, what: 'laps', kind: 'area', skip: !(q.iceSqft > 0) },
    { slot: 'dripEdge', basis: lin(q.eaveFt + q.rakeFt), pct: LINEAR_ALLOWANCE * 100, what: 'laps and cuts', kind: 'linear' },
    { slot: 'ridgeVent', basis: lin(q.ventFt), pct: 0, kind: 'linear', skip: !(q.ventFt > 0) },
    { slot: 'valley', basis: lin(q.valleyFt), pct: LINEAR_ALLOWANCE * 100, what: 'laps and cuts', kind: 'linear', skip: !job.valleyMetal },
  ].filter((r) => !r.skip);
}

/** Store quantity for one product on one line. typedCoverage is per sold unit, in the line's unit (sq ft or ft). */
const EACH_NOUN = { underlayment: 'roll', iceWater: 'roll', dripEdge: 'piece', valley: 'piece', ridgeVent: 'piece', starter: 'bundle', ridgeCap: 'piece' };

function storeQty(rule, need, product, choice) {
  const r = storeQtyRaw(rule, need, product, choice);
  // "4 each" reads badly: name the thing (rolls, pieces, bundles); csv keeps `unit`
  if (r && r.unit === 'each' && EACH_NOUN[rule.slot]) r.noun = rule.slot === 'ridgeCap' && product.kind !== 'metalCap' ? 'bundle' : EACH_NOUN[rule.slot];
  return r;
}

/** Shingles, caps and starters are sold by the bundle: their packCount counts shingles, never packages. */
export function isPerBundle(product) {
  return product.category === 'shingle' || ['shingleCap', 'starter'].includes(product.kind) || (product.price?.per || 'each') === 'bundle';
}

function storeQtyRaw(rule, need, product, choice) {
  const per = product.price?.per || 'each';
  // on shingles, caps and starters packCount counts shingles per bundle, not packages: never a pack
  const perBundle = isPerBundle(product);
  const pack = product.packCount > 1 && !perBundle ? product.packCount : null;
  const typed = Number(choice.typedCoverage) > 0 ? Number(choice.typedCoverage) : null;
  if (rule.kind === 'covering' && per === '100 sq ft') {
    return { qty: ceilQty(need) / 100, unit: 'squares (100 sq ft)', squares: true };
  }
  if (rule.kind !== 'linear') {
    const cov = typed ?? product.coverage?.sqft;
    if (!(cov > 0)) return null;
    const gross = typed == null && product.coverage?.basis === 'gross';
    return { qty: ceilQty(need / cov), unit: pack && rule.kind === 'covering' ? `pack of ${pack}` : per, gross };
  }
  if (typed != null) return { qty: ceilQty(need / typed), unit: pack ? `carton of ${pack}` : per };
  const lf = rule.lf ? product.coverage?.lf : null;
  if (lf > 0) return { qty: ceilQty(need / lf), unit: per };
  if (product.pieceFt > 0) {
    const pieces = ceilQty(need / product.pieceFt);
    return pack ? { qty: ceilQty(pieces / pack), unit: `carton of ${pack}`, pieces } : { qty: pieces, unit: per };
  }
  return null;
}

const catalogIndex = new WeakMap();
function productIndex(catalog) {
  let m = catalogIndex.get(catalog);
  if (!m) { m = new Map((catalog?.products || []).map((p) => [p.id, p])); if (catalog) catalogIndex.set(catalog, m); }
  return m;
}

/** A product as the list prices it: the catalog's, or the saved snapshot item when `priceOverride` has one. */
function resolveProduct(id, byId, priceOverride) {
  const live = byId.get(id) || null;
  const saved = priceOverride?.[id];
  if (!saved) return live ? { product: live, gone: false, current: null } : null;
  const lp = live?.price || {};
  const product = {
    ...(live || {}), id, name: saved.name ?? live?.name ?? id,
    price: { ...lp, shelf: saved.shelf ?? null, per: saved.per ?? lp.per, startingAt: !!saved.startingAt, rebate: saved.rebate ?? null, rebateThrough: saved.rebateThrough ?? lp.rebateThrough },
    coverage: saved.coverage ?? null, pieceFt: saved.pieceFt ?? null, packCount: saved.packCount ?? null,
  };
  let current = null;
  if (live && (lp.shelf ?? null) !== (saved.shelf ?? null)) current = { unitPrice: lp.shelf ?? null, delta: lp.shelf != null && saved.shelf != null ? round2(lp.shelf - saved.shelf) : null };
  return { product, gone: !live, current };
}

function emptyCell(status, extra = {}) {
  const u = UNKNOWN[extra.typedLine && status === 'noPrice' ? 'noPriceTyped' : status] || {};
  const { typedLine, ...rest } = extra;
  return finishTexts({
    status, productId: null, name: null, color: null, suggested: false, qty: null, unit: null, unitPrice: null, priceSource: null,
    lineTotal: null, rebate: null, stock: null, why: u.why ?? null, setBy: u.setBy ?? null, notes: [],
    needs: { price: status === 'noPrice', coverage: status === 'noQuantity' }, current: null,
    ...rest,
  });
}

function finishTexts(c, squares) {
  c.qtyText = c.qty == null ? DASH : squares ? c.qty.toFixed(2) : fmtNum(c.qty);
  c.unitPriceText = c.unitPrice == null ? DASH : fmtMoney(c.unitPrice);
  c.totalText = c.lineTotal == null ? DASH : c.status === 'startingAt' ? `from ${fmtMoney(c.lineTotal)}` : fmtMoney(c.lineTotal);
  return c;
}

function storeCell(rule, needValue, choice, ctx) {
  if (!choice || !choice.productId) return emptyCell('notChosen');
  const r = resolveProduct(choice.productId, ctx.byId, ctx.priceOverride);
  if (!r) return emptyCell('notChosen', { productId: choice.productId, notes: ['not in the store capture'] });
  const { product: p, gone, current } = r;
  const sq = storeQty(rule, needValue, p, choice);
  const typedPrice = choice.typedPrice != null && Number.isFinite(Number(choice.typedPrice)) ? Number(choice.typedPrice) : null;
  const unitPrice = typedPrice ?? p.price?.shelf ?? null;
  const priceSource = typedPrice != null ? 'typed' : unitPrice != null ? 'store' : null;
  const status = unitPrice == null ? 'noPrice' : !sq ? 'noQuantity' : priceSource === 'store' && p.price?.startingAt ? 'startingAt' : 'priced';
  const u = UNKNOWN[status] || {};
  const qty = sq ? sq.qty : null;
  const lineTotal = qty != null && unitPrice != null ? round2(qty * unitPrice) : null;
  const notes = [];
  if (sq?.gross) notes.push('gross panel area: side laps are not deducted');
  if (status === 'startingAt') notes.push('starting-at price: color and length change it');
  const saleEnd = parseMDY(p.price?.saleThrough);
  if (saleEnd < ctx.today) notes.push(`sale ended ${p.price.saleThrough}: check the price`);
  if (gone) notes.push('no longer in the store capture');
  if (current) notes.push(current.unitPrice == null ? 'now: no price in the store capture'
    : `now ${fmtMoney(current.unitPrice)} (${current.delta >= 0 ? '+' : '−'}${fmtMoney(Math.abs(current.delta))})`);
  let stock = null;
  if (p.stock && p.stock.qty == null && p.stock.inStock === false) {
    stock = { qty: null, short: false, text: 'not in stock at this store at capture' }; // unknown is never zero
  } else if (p.stock && p.stock.qty != null) {
    const have = p.stock.qty;
    const short = qty != null && qty > have;
    stock = { qty: have, short, text: short ? `store had ${fmtNum(have)}, you need ${fmtNum(qty)}` : `${fmtNum(have)} in store at capture` };
  }
  const rebate = status === 'priced' && priceSource === 'store' && p.price?.rebate > 0 ? round2(qty * p.price.rebate) : null;
  return finishTexts({
    status, productId: p.id, name: p.name ?? null, color: choice.color ?? p.color ?? null, suggested: choice.source === 'suggested',
    qty, unit: sq ? sq.unit : null, noun: sq?.noun ?? null, unitPrice, priceSource, lineTotal, rebate, stock,
    why: u.why ?? null, setBy: u.setBy ?? null, notes,
    needs: { price: unitPrice == null, coverage: !sq }, current,
    ...(sq?.pieces != null ? { pieces: sq.pieces } : {}),
    rebateThrough: rebate != null ? p.price.rebateThrough ?? null : null,
  }, sq?.squares);
}

/** Nails and deck repair: no store product; the job may hold a typed amount for the whole line. */
function typedCell(slot, qty, unit, job) {
  const amt = job.typed?.[slot];
  if (amt == null || !Number.isFinite(Number(amt))) return emptyCell('noPrice', { typedLine: true, qty, unit });
  return finishTexts({
    status: 'priced', productId: null, name: null, color: null, suggested: false, qty, unit, unitPrice: null, priceSource: 'typed',
    lineTotal: round2(Number(amt)), rebate: null, stock: null, why: null, setBy: null, notes: ['amount for this line, typed'],
    needs: { price: false, coverage: false }, current: null,
  });
}

function lowerOf(cells, stores) {
  const known = stores.map((s) => [s, cells[s]]).filter(([, c]) => c.status === 'priced' && c.lineTotal != null);
  if (known.length !== stores.length || known.length < 2) return null;
  known.sort((a, b) => a[1].lineTotal - b[1].lineTotal);
  return known[0][1].lineTotal === known[1][1].lineTotal ? null : known[0][0];
}

// ---------------------------------------------------------------------------
// totals, rebate, age banner

function totalText(status, amount, missing, typed, oneStore = []) {
  const m = fmtMoney(amount);
  const t = typed ? ', includes typed prices' : '';
  if (status === 'incomplete') {
    const parts = [];
    if (missing.length) parts.push(`Missing: ${missing.join(', ')}.`);
    if (oneStore.length) parts.push(`One store only: ${oneStore.join(', ')}.`);
    return `Total incomplete: ${m} so far${t}. ${parts.join(' ')}`.trim();
  }
  if (status === 'atLeast') return `At least ${m}${t}`;
  return `Materials total ${m}, before tax${t}`;
}

function storeTotal(lines, store, ctx) {
  let sum = 0, startingAt = false, typed = false;
  const missing = [];
  for (const l of lines) {
    const c = l.cells[store];
    if (c.lineTotal != null) sum += c.lineTotal;
    if (MISSING.has(c.status)) missing.push(l.label);
    if (c.status === 'startingAt') startingAt = true;
    if (c.priceSource === 'typed' && c.lineTotal != null) typed = true;
  }
  const amount = round2(sum);
  const status = missing.length ? 'incomplete' : startingAt ? 'atLeast' : 'complete';
  return { store, name: ctx.names[store], amount, status, missing, includesTyped: typed, text: totalText(status, amount, missing, typed), rebate: rebateBlock(lines, store, ctx) };
}

function lowestTotal(lines, stores) {
  let sum = 0, startingAt = false, typed = false;
  const missing = [], oneStore = [], picks = {};
  for (const l of lines) {
    const known = stores.map((s) => [s, l.cells[s]]).filter(([, c]) => c.lineTotal != null && !MISSING.has(c.status));
    if (!known.length) { missing.push(l.label); picks[l.slot] = null; continue; }
    if (known.length < stores.length) oneStore.push(l.label);
    known.sort((a, b) => a[1].lineTotal - b[1].lineTotal);
    const [s, c] = known[0];
    picks[l.slot] = s;
    sum += c.lineTotal;
    if (c.status === 'startingAt') startingAt = true;
    if (c.priceSource === 'typed') typed = true;
  }
  const amount = round2(sum);
  const status = missing.length || oneStore.length ? 'incomplete' : startingAt ? 'atLeast' : 'complete';
  return { store: null, name: 'Lowest per line', amount, status, missing, oneStore, picks, includesTyped: typed, text: totalText(status, amount, missing, typed, oneStore) };
}

function rebateBlock(lines, store, ctx) {
  const cells = lines.map((l) => l.cells[store]).filter((c) => c.rebate != null);
  if (!cells.length) return null;
  const amount = round2(cells.reduce((s, c) => s + c.rebate, 0));
  const base = cells.reduce((s, c) => s + c.lineTotal, 0);
  const pct = base > 0 ? Math.round((amount / base) * 100) : null;
  const dates = cells.map((c) => c.rebateThrough).filter((d) => !Number.isNaN(parseMDY(d)));
  const through = dates.sort((a, b) => parseMDY(b) - parseMDY(a))[0] ?? null;
  const ended = through != null && ctx.today > parseMDY(through);
  const lead = `${pct != null ? `${pct}% ` : ''}mail-in rebate`;
  const text = ended ? `${lead} ended ${through}. It would have been ${fmtMoney(amount)} in store credit. Not in the total.`
    : `${lead}${through ? ` through ${through}` : ''}: ${fmtMoney(amount)} store credit by mail. Not in the total.`;
  return { amount, pct, through, ended, text };
}

/** "Prices captured Nov 15, 2026 (Menards) and Nov 15–16, 2026 (Home Depot). Re-capture before quoting." */
export function ageBanner(catalog, stores, today) {
  const names = storeNames(catalog, stores);
  const caps = stores.map((s) => ({ s, cap: catalog?.stores?.[s]?.captured })).filter((x) => x.cap);
  const text = `Prices captured ${caps.map((x) => `${fmtDate(x.cap)} (${names[x.s]})`).join(' and ')}. Re-capture before quoting.`;
  const oldest = Math.min(...caps.map((x) => parseISODate(x.cap)).filter((t) => !Number.isNaN(t)));
  const t = typeof today === 'number' ? today : parseISODate(today);
  const daysOld = Number.isFinite(oldest) && Number.isFinite(t) ? Math.round((t - oldest) / DAY) : null;
  return { text: daysOld != null && daysOld > 7 ? `${daysOld} days old. ${text}` : text, daysOld };
}

function storeNames(catalog, stores) {
  return Object.fromEntries(stores.map((s) => [s, STORE_SHORT[s] || catalog?.stores?.[s]?.name || s]));
}

// ---------------------------------------------------------------------------
// the quote

/**
 * buildQuote({ q, job, catalog, today, priceOverride?, roofName? }) -> { lines, totals, notes, status, stores, shownStore, today }
 * q: the quantities() object. job: S.job (waste, valleyMetal, selections, typed, roofSource, shownStore).
 * catalog: the supplier catalog ({ stores, products }). today: 'YYYY-MM-DD'.
 * priceOverride: product id -> saved snapshot item (section 8); those prices replace the catalog's.
 */
export function buildQuote({ q, job = {}, catalog, today, priceOverride = null, roofName = null }) {
  const stores = catalog?.stores ? Object.keys(catalog.stores) : STORE_IDS.slice();
  const names = storeNames(catalog, stores);
  const t = parseISODate(today);
  const ctx = { byId: productIndex(catalog), priceOverride, today: t, names };
  const lines = [];
  for (const rule of lineRules(q, job)) {
    const [value, unit, text] = rule.basis;
    // quantities come from the need as shown (to 0.01): the list's arithmetic must be checkable by hand,
    // and a 0.004 ft overshoot of a rounded figure must not buy one more bundle or piece
    const need = { value: round2(value * (1 + rule.pct / 100)), unit };
    const cells = {};
    for (const s of stores) cells[s] = storeCell(rule, need.value, job.selections?.[rule.slot]?.[s] ?? null, ctx);
    lines.push({
      slot: rule.slot, label: LINE_LABELS[rule.slot],
      basis: { value, unit, text, source: 'measured' },
      allowance: rule.pct > 0 ? { pct: rule.pct, text: pctText(rule.pct, rule.what), source: 'allowance', setBy: rule.setBy || FIXED } : null,
      need, cells, lower: lowerOf(cells, stores),
    });
  }
  // fasteners: counted in the model, priced only by a typed amount
  const nails = q.nailCount > 0 ? q.nailCount : null;
  const nailCells = Object.fromEntries(stores.map((s) => [s, typedCell('nails', nails, 'nails', job)]));
  lines.push({
    slot: 'nails', label: LINE_LABELS.nails,
    basis: { value: nails, unit: 'nails', text: nails ? `${fmtNum(nails)} nails, counted in the model` : 'not counted: the nails layer is off', source: 'measured' },
    allowance: null, need: { value: nails, unit: 'nails' }, cells: nailCells, lower: lowerOf(nailCells, stores),
  });
  // deck repair: the whole line is an allowance
  const sheets = q.deckRepairSheets > 0 ? q.deckRepairSheets : 0;
  if (sheets) {
    const deckCells = Object.fromEntries(stores.map((s) => [s, typedCell('deckRepair', sheets, 'sheets', job)]));
    lines.push({
      slot: 'deckRepair', label: LINE_LABELS.deckRepair, basis: null,
      allowance: { pct: null, text: `${sheets} sheets allowance`, source: 'allowance', setBy: 'you, Deck repair allowance on the Layers tab' },
      need: { value: sheets, unit: 'sheets' }, cells: deckCells, lower: lowerOf(deckCells, stores),
    });
  }
  const totals = Object.fromEntries(stores.map((s) => [s, storeTotal(lines, s, ctx)]));
  totals.lowest = lowestTotal(lines, stores);
  const notes = [NOT_INCLUDED];
  if (job.roofSource === 'builtin') notes.unshift(`The roof shows ${roofName || 'a built-in product'}, which is not a store product. Prices below are for the store products chosen.`);
  return {
    lines, totals, notes,
    status: { header: HEADER, age: ageBanner(catalog, stores, t), prices: priceOverride ? 'saved' : 'catalog' },
    stores: stores.map((id) => ({ id, name: names[id] })),
    shownStore: job.shownStore && stores.includes(job.shownStore) ? job.shownStore : stores[0],
    today,
  };
}

// ---------------------------------------------------------------------------
// crew view and CSV

/** One store, no prices anywhere: line, product, color, quantity, unit, measured basis. */
export function crewView(quote, storeId = quote.shownStore) {
  const store = quote.stores.find((s) => s.id === storeId) || quote.stores[0];
  return {
    store: { id: store.id, name: store.name },
    lines: quote.lines.map((l) => {
      const c = l.cells[store.id];
      const unknownQty = c.qty == null || c.status === 'notChosen';
      return {
        slot: l.slot, label: l.label, product: c.name, color: c.color,
        qty: c.status === 'notChosen' ? null : c.qty, qtyText: c.status === 'notChosen' ? DASH : c.qtyText, unit: c.unit, noun: c.noun ?? null,
        measured: l.basis ? l.basis.text : l.allowance?.text ?? '',
        why: unknownQty && c.status !== 'noPrice' ? c.why : null,
      };
    }),
  };
}

const OFFICE_COLS = ['Line', 'Measured', 'Allowance', 'Store', 'Product', 'Color', 'Quantity', 'Unit', 'Unit price', 'Price source', 'Line total', 'Status', 'Note'];
const CREW_COLS = ['Line', 'Product', 'Color', 'Quantity', 'Unit', 'Measured'];

function csvField(v) {
  const s = v == null ? '' : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
const csvQty = (c) => (c.qty == null || c.status === 'notChosen' ? '' : c.unit?.startsWith('squares') ? c.qty.toFixed(2) : String(c.qty));

/** RFC 4180 CSV, CRLF line ends, UTF-8 BOM. view 'office' (both stores, or `store`) or 'crew' (one store, no prices). */
export function quoteCSV(quote, { view = 'office', store } = {}) {
  const rows = [];
  if (view === 'crew') {
    const crew = crewView(quote, store || quote.shownStore);
    rows.push(CREW_COLS);
    for (const l of crew.lines) rows.push([l.label, l.product ?? l.why ?? '', l.color ?? '', l.qty ?? '', l.unit ?? '', l.why && l.product ? `${l.measured}; ${l.why}` : l.measured]);
  } else {
    const stores = quote.stores.filter((s) => !store || s.id === store);
    const pad = (r) => r.concat(Array(OFFICE_COLS.length - r.length).fill(''));
    rows.push(OFFICE_COLS);
    for (const l of quote.lines) {
      for (const s of stores) {
        const c = l.cells[s.id];
        const note = [c.why, c.setBy ? `set by ${c.setBy}` : null, ...c.notes, c.stock?.text, c.suggested ? 'suggested' : null, l.lower === s.id ? 'lower' : null]
          .filter(Boolean).join('; ');
        rows.push([l.label, l.basis?.text ?? '', l.allowance?.text ?? '', s.name, c.name ?? '', c.color ?? '', csvQty(c), c.unit ?? '',
          c.unitPrice != null ? c.unitPrice.toFixed(2) : '', c.priceSource ?? '', c.lineTotal != null ? c.lineTotal.toFixed(2) : '', STATUS_TEXT[c.status], note]);
      }
    }
    rows.push(pad([]));
    for (const s of stores) {
      const t = quote.totals[s.id];
      rows.push(pad(['Total', '', '', s.name, '', '', '', '', '', '', t.amount.toFixed(2), t.status, t.text]));
    }
    if (!store) { const t = quote.totals.lowest; rows.push(pad(['Total', '', '', t.name, '', '', '', '', '', '', t.amount.toFixed(2), t.status, t.text])); }
    for (const s of stores) {
      const r = quote.totals[s.id].rebate;
      if (r) rows.push(pad(['Rebate', '', '', s.name, '', '', '', '', '', '', r.amount.toFixed(2), 'not in the total', r.text]));
    }
    rows.push(pad(['Prices captured', '', '', '', '', '', '', '', '', '', '', '', quote.status.age.text]));
    rows.push(pad([quote.status.header]));
    for (const n of quote.notes) rows.push(pad([n]));
  }
  return '﻿' + rows.map((r) => r.map(csvField).join(',')).join('\r\n') + '\r\n';
}

/** materials-<job-slug>-<YYYY-MM-DD>.csv, or materials-crew-… for the crew file. */
export function csvFileName(jobName, today, view = 'office') {
  return `materials-${view === 'crew' ? 'crew-' : ''}${slugify(jobName || 'roof')}-${today}.csv`;
}
