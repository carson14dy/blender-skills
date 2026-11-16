// Studio project files: build, validate and compare price snapshots. Supplier plan, section 8.
// Pure: no DOM, no three, so `node --test` can import it. Saving and opening go through app.js (saveFile, a file input).

import { slugify } from './util.js';
import { SLOTS, STORE_IDS, TYPED_LINES, fmtDate } from './quote.js';

export const PROJECT_FORMAT = 'rooftec-studio-project';
export const PROJECT_VERSION = 1;
/** Keys never written to a project file at any depth: images stay out of project files. */
const HEAVY_KEYS = new Set(['image', 'swatch', 'dataUrl']);
/** Fields of a store product kept in the price snapshot (rebateThrough so the rebate block still reads right). */
const ITEM_KEYS = ['name', 'shelf', 'per', 'startingAt', 'rebate', 'rebateThrough', 'coverage', 'pieceFt', 'packCount'];
const COMPARE_KEYS = ['shelf', 'per', 'startingAt', 'rebate', 'coverage', 'pieceFt', 'packCount'];

const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
const isObj = (x) => x != null && typeof x === 'object' && !Array.isArray(x);
const round2 = (x) => Math.round(x * 100) / 100;

/** Copy as plain JSON, dropping image keys and data: URLs. */
function clean(v) {
  if (Array.isArray(v)) return v.map(clean).filter((x) => x !== undefined);
  if (isObj(v)) {
    const out = {};
    for (const [k, x] of Object.entries(v)) {
      if (HEAVY_KEYS.has(k) || (typeof x === 'string' && x.startsWith('data:'))) continue;
      const c = clean(x);
      if (c !== undefined) out[k] = c;
    }
    return out;
  }
  if (typeof v === 'function' || v === undefined) return undefined;
  if (typeof v === 'number' && !Number.isFinite(v)) return null;
  return v;
}

const roundDeep = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, isNum(v) ? round2(v) : v]));

/** A store product as the price snapshot keeps it. */
export function snapshotItem(p) {
  const pr = p.price || {};
  const src = { name: p.name ?? null, shelf: pr.shelf ?? null, per: pr.per ?? null, startingAt: !!pr.startingAt, rebate: pr.rebate ?? null,
    rebateThrough: pr.rebateThrough ?? null, coverage: p.coverage ? { ...p.coverage } : null, pieceFt: p.pieceFt ?? null, packCount: p.packCount ?? null };
  return Object.fromEntries(ITEM_KEYS.map((k) => [k, src[k]]));
}

/** Source hashes and capture dates, by source key ('menards', 'homedepot'). */
function snapshotSources(catalog) {
  const out = {};
  const stores = Object.entries(catalog?.stores || {});
  for (const [key, src] of Object.entries(catalog?.sources || {})) {
    const entry = {};
    for (const [k, v] of Object.entries(src || {})) if (/sha256/i.test(k)) entry[k] = v;
    const store = stores.find(([id]) => id.split('-')[0] === key);
    entry.captured = store?.[1]?.captured ?? null;
    out[key] = entry;
  }
  return out;
}

function selectedIds(selections) {
  const ids = [];
  for (const byStore of Object.values(selections || {})) {
    for (const c of Object.values(byStore || {})) if (c?.productId && !ids.includes(c.productId)) ids.push(c.productId);
  }
  return ids;
}

/**
 * Build the saved project object (plain JSON).
 * {
 *   job:      S.job (name, shownStore, waste, valleyMetal, selections, typed, snapshot),
 *   site:     { location, lat }            -> project.job
 *   house:    { source: 'preset', presetId, pitch } | { source: 'glb', fileName, units }
 *   sun, layers: { options, custom, hidden }, roof (section 8), measured: quantities(),
 *   catalog:  the store catalog (for the price snapshot), quote: buildQuote() result (for its totals),
 *   savedAt:  ISO time (default now), today: 'YYYY-MM-DD' (default savedAt's date)
 * }
 * While job.snapshot is set (the list shows saved prices), the project keeps that snapshot's date, sources and items.
 */
export function buildProject({ job = {}, site = {}, house = {}, sun = {}, layers = {}, roof = {}, measured = {}, catalog = null, quote = null, savedAt, today } = {}) {
  const at = savedAt ?? new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
  const kept = job.snapshot || null;
  const byId = new Map((catalog?.products || []).map((p) => [p.id, p]));
  const items = {};
  for (const id of selectedIds(job.selections)) {
    const item = kept?.items?.[id] ?? (byId.has(id) ? snapshotItem(byId.get(id)) : null);
    if (item) items[id] = item;
  }
  const totals = {};
  for (const [id, t] of Object.entries(quote?.totals || {})) if (id !== 'lowest' && t) totals[id] = { amount: t.amount, status: t.status };
  const p = {
    format: PROJECT_FORMAT, version: PROJECT_VERSION,
    name: job.name ?? 'Untitled roof', savedAt: at,
    job: { location: site.location ?? null, lat: site.lat ?? null },
    house: houseEntry(house),
    sun: { date: sun.date ?? null, hour: sun.hour ?? null, facing: sun.facing ?? null },
    layers: { options: layers.options ?? {}, custom: layers.custom ?? [], hidden: layers.hidden ?? [] },
    roof: roofEntry(roof),
    waste: { pct: job.waste?.pct ?? null, source: job.waste?.source ?? 'suggested' },
    shownStore: job.shownStore ?? STORE_IDS[0], valleyMetal: !!job.valleyMetal,
    selections: job.selections ?? {},
    typed: Object.fromEntries(TYPED_LINES.map((k) => [k, job.typed?.[k] ?? null])),
    measured: roundDeep(measured),
    priceSnapshot: {
      savedOn: kept?.savedOn ?? today ?? at.slice(0, 10),
      sources: kept?.sources ?? snapshotSources(catalog),
      items, totals,
    },
  };
  return clean(p);
}

function houseEntry(h) {
  if (h.source === 'glb') return { source: 'glb', fileName: h.fileName ?? null, units: h.units ?? null };
  return { source: 'preset', presetId: h.presetId ?? null, pitch: h.pitch ?? null };
}

function roofEntry(r) {
  if (r.source === 'photo') return { source: 'photo', name: r.name ?? null };
  if (r.source === 'builtin') return { source: 'builtin', id: r.id ?? null, view: r.view ?? null };
  return { source: 'store', store: r.store ?? null, productId: r.productId ?? null, color: r.color ?? null, view: r.view ?? null };
}

/** <job-slug>.rooftec.json */
export function projectFileName(name) {
  return `${slugify(name || 'roof')}.rooftec.json`;
}

// ---------------------------------------------------------------------------
// open

/**
 * Validate a project file. Accepts the file text or an already-parsed object.
 * -> { ok, project, errors }. Unknown extra keys are kept and ignored. errors[0] is the toast.
 */
export function parseProject(text, { stores = STORE_IDS, slots = SLOTS } = {}) {
  let p = text;
  if (typeof text === 'string') {
    try { p = JSON.parse(text); } catch { return fail('This file is not a studio project: it is not valid JSON.'); }
  }
  if (!isObj(p)) return fail('This file is not a studio project.');
  if (p.format !== PROJECT_FORMAT) return fail(`This file is not a studio project (format ${JSON.stringify(p.format ?? null)}, expected "${PROJECT_FORMAT}").`);
  if (!Number.isInteger(p.version) || p.version < 1) return fail(`This project file has no valid version (${JSON.stringify(p.version ?? null)}).`);
  if (p.version > PROJECT_VERSION) return fail(`This project was saved by a newer studio (file version ${p.version}); this studio opens version ${PROJECT_VERSION}. Update the studio to open it.`);
  const errors = [];
  const storeOk = (s) => stores.includes(s);
  if (p.shownStore != null && !storeOk(p.shownStore)) errors.push(`Unknown store "${p.shownStore}" in shownStore.`);
  if (p.roof?.source === 'store' && p.roof.store != null && !storeOk(p.roof.store)) errors.push(`Unknown store "${p.roof.store}" in roof.`);
  if (p.selections != null && !isObj(p.selections)) errors.push('selections must be an object.');
  for (const [slot, byStore] of Object.entries(isObj(p.selections) ? p.selections : {})) {
    if (!slots.includes(slot)) { errors.push(`Unknown slot "${slot}" in selections.`); continue; }
    if (byStore != null && !isObj(byStore)) { errors.push(`selections.${slot} must be an object.`); continue; }
    for (const [store, choice] of Object.entries(byStore || {})) {
      if (!storeOk(store)) { errors.push(`Unknown store "${store}" in selections.${slot}.`); continue; }
      if (choice == null) continue;
      if (!isObj(choice) || typeof choice.productId !== 'string') errors.push(`selections.${slot}.${store} has no product id.`);
      else for (const k of ['typedPrice', 'typedCoverage']) if (choice[k] != null && !isNum(choice[k])) errors.push(`selections.${slot}.${store}.${k} must be a number.`);
    }
  }
  if (p.house?.source !== 'glb' && !isNum(p.house?.pitch)) errors.push(`Pitch must be a number (got ${JSON.stringify(p.house?.pitch ?? null)}).`);
  if (!isNum(p.waste?.pct)) errors.push(`Waste % must be a number (got ${JSON.stringify(p.waste?.pct ?? null)}).`);
  for (const k of TYPED_LINES) if (p.typed?.[k] != null && !isNum(p.typed[k])) errors.push(`typed.${k} must be a number.`);
  return errors.length ? { ok: false, project: null, errors } : { ok: true, project: p, errors: [] };
}
const fail = (msg) => ({ ok: false, project: null, errors: [msg] });

/** The S.job object a project reopens with (snapshot: its price snapshot; the caller clears it when compareSnapshot says unchanged). */
export function jobFromProject(p, { stores = STORE_IDS, slots = SLOTS } = {}) {
  const selections = {};
  for (const slot of slots) {
    selections[slot] = {};
    for (const s of stores) selections[slot][s] = p.selections?.[slot]?.[s] ?? null;
  }
  return {
    name: p.name ?? 'Untitled roof',
    shownStore: p.shownStore ?? stores[0],
    roofSource: p.roof?.source === 'store' ? 'store' : 'builtin',
    waste: { pct: p.waste?.pct ?? null, source: p.waste?.source ?? 'suggested' },
    valleyMetal: !!p.valleyMetal,
    selections,
    typed: Object.fromEntries(TYPED_LINES.map((k) => [k, p.typed?.[k] ?? null])),
    snapshot: p.priceSnapshot ?? null,
    dirty: false,
  };
}

// ---------------------------------------------------------------------------
// price snapshots

const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/**
 * Compare a saved price snapshot (or a whole project) with the loaded catalog.
 * -> { changed: [{ productId, name, was, now, fields }], missing: [{ productId, name, was }], sameSources, unchanged }
 * `was` / `now` are shelf prices; `fields` lists every compared field that differs.
 */
export function compareSnapshot(saved, catalog) {
  const snap = saved?.priceSnapshot ?? saved ?? {};
  const byId = new Map((catalog?.products || []).map((p) => [p.id, p]));
  const changed = [], missing = [];
  for (const [id, item] of Object.entries(snap.items || {})) {
    const live = byId.get(id);
    if (!live) { missing.push({ productId: id, name: item.name ?? id, was: item.shelf ?? null }); continue; }
    const now = snapshotItem(live);
    const fields = COMPARE_KEYS.filter((k) => !same(item[k], now[k]));
    if (fields.length) changed.push({ productId: id, name: item.name ?? now.name, was: item.shelf ?? null, now: now.shelf, fields });
  }
  const current = snapshotSources(catalog);
  const hashes = (srcs) => Object.fromEntries(Object.entries(srcs || {}).map(([k, v]) => [k, Object.fromEntries(Object.entries(v || {}).filter(([f]) => /sha256/i.test(f)))]));
  const sameSources = same(hashes(snap.sources), hashes(current));
  return { changed, missing, sameSources, unchanged: sameSources && !changed.length && !missing.length };
}

/** The list-header line for an opened project. */
export function snapshotNotice(cmp, savedOn) {
  const date = fmtDate(savedOn);
  if (cmp.unchanged) return `Saved ${date}`;
  const n = cmp.changed.filter((c) => c.fields.includes('shelf')).length;
  const other = cmp.changed.length - n;
  const k = cmp.missing.length;
  const parts = [];
  if (n) parts.push(`${n} ${n === 1 ? 'price differs' : 'prices differ'}`);
  if (other) parts.push(`${other} ${other === 1 ? 'product has' : 'products have'} other changes`);
  if (k) parts.push(`${k} ${k === 1 ? 'product is' : 'products are'} gone`);
  const what = parts.length ? parts.join(', ') : 'none of the chosen products changed';
  return `Showing prices as saved on ${date}. The store data has changed since: ${what}.`;
}

/** Deep equality of two projects, ignoring savedAt (the browser round-trip check). */
export function sameProject(a, b) {
  const strip = (p) => { const { savedAt, ...rest } = p || {}; return rest; };
  return canon(strip(a)) === canon(strip(b));
}
function canon(v) {
  if (Array.isArray(v)) return `[${v.map(canon).join(',')}]`;
  if (isObj(v)) return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon(v[k])}`).join(',')}}`;
  return JSON.stringify(v ?? null);
}
