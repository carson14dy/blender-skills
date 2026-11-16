// Store features of the studio (lab project sioux-falls-studio): the store picker on the Materials tab,
// the priced list on the List tab, the full-list dialog, the crew view, the project buttons and the
// Blender command on the Project tab. DOM glue only: the rules live in quote.js, project-file.js and
// supplier-products.js. Supplier plan, sections 3, 8, 9 and 10.
//
// No store image is ever requested here: products show color chips drawn with CSS.

import { buildQuote, quoteCSV, crewView, csvFileName, fmtMoney, fmtDate, LINE_LABELS, SLOTS, STORE_IDS, NOT_INCLUDED } from './quote.js';
import { buildProject, parseProject, jobFromProject, compareSnapshot, snapshotNotice, projectFileName, sameProject } from './project-file.js';
import { findProduct, suggestedSelections, storeName, defaultColor, colorEntry, shortName, specFor, toStudioProduct, layerOptionFor, SUGGESTED } from './supplier-products.js';

/** Slots drawn as their own layer, for the exploded-view label (the covering's label is its product name). */
const SLOT_LAYER = { ridgeCap: 'ridgeCap', starter: 'starter', underlayment: 'underlayment', iceWater: 'iceWater', dripEdge: 'dripEdge', ridgeVent: 'ridgeVent' };
/** Slots whose product changes the 3D view. */
const VIEW_SLOTS = new Set(['covering', 'ridgeCap', 'dripEdge', 'underlayment', 'iceWater']);
/** Slots whose colors were sampled from the store images (the others look like their product kind). */
const SAMPLED = new Set(['covering', 'ridgeCap', 'dripEdge', 'valley', 'ridgeVent']);
const AREA_SLOTS = new Set(['covering', 'underlayment', 'iceWater']);
const LEFT_OUT = new Set(['flashingTape', 'closure', 'undercourse']);
const PAGE = 60;
const MN = 'menards-3064', HD = 'homedepot-4301';
const COVER_TYPES = [['all', 'All'], ['shingle', 'Shingle'], ['metal', 'Metal'], ['shake', 'Cedar']];
const STORE_FILTERS = [['both', 'Both'], [MN, 'Menards'], [HD, 'Home Depot']];
const DASH = '–';

// ---------------------------------------------------------------------------
// small DOM helpers

function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false && k !== '') e.append(k);
  return e;
}
const tag = (text, kind = text) => el('span', { class: `sf-tag t-${kind.replace(/\s+/g, '-')}` }, text);
const storeTag = (id) => el('span', { class: `sf-store s-${id === MN ? 'mn' : 'hd'}` }, storeName(id));
const num = (x, d = 0) => Number(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** "bundle" -> "bundles" for a quantity other than 1 (display only). */
function plural(unit, qty) {
  if (!unit || qty === 1) return unit || '';
  return unit.replace(/^(bundle|roll|piece|sheet|case|box)\b/, '$1s').replace(/^(pack|carton) of/, '$1s of');
}

/** Store names carry quotes doubled and trade marks; tidy them for reading. */
const cleanName = (s) => String(s || '').replace(/^"+|"+$/g, '').replace(/""/g, '"').replace(/[®™]/g, '');

/** CSS background for a color entry: the sampled palette as hard color bands, or its flat hex. */
function chipBackground(entry) {
  const pal = (Array.isArray(entry.palette) ? entry.palette : []).filter((h) => /^#[0-9a-f]{6}$/i.test(h)).slice(0, 4);
  if (pal.length < 2) return entry.hex;
  const step = 100 / pal.length;
  return `linear-gradient(135deg, ${pal.map((h, i) => `${h} ${(i * step).toFixed(1)}% ${((i + 1) * step).toFixed(1)}%`).join(', ')})`;
}

function chip(entry, { sampled = true } = {}) {
  const has = !!entry?.hex;
  const s = el('span', { class: `sf-chip${has ? '' : sampled ? ' none' : ' kind'}`, 'aria-hidden': 'true' });
  if (has) s.style.background = chipBackground(entry);
  return s;
}

/** A row of toggle buttons (aria-pressed); `sync()` re-reads the value. */
function segmented(options, get, set, label) {
  const wrap = el('div', { class: 'sf-seg', role: 'group', 'aria-label': label });
  wrap.sync = () => [...wrap.children].forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === get())));
  for (const [v, t] of options) wrap.append(el('button', { type: 'button', class: 'sf-segb', 'data-v': v, onclick: () => { set(v); wrap.sync(); } }, t));
  wrap.sync();
  return wrap;
}

// ---------------------------------------------------------------------------

/**
 * ctx (from app.js): S, params, catalog() -> Promise<store catalog | null>, layers() -> RoofLayers,
 * applyProduct(p, opts), setLayerOptions(opts), renderStack(), waste() -> { pct, source }, setWaste(pct | null),
 * selectTab(id), toast(msg), saveFile(name, blob), projectState() -> { site, house, sun, layers },
 * applyProjectState(project, { fresh }), builtinProduct(id) -> built-in product | null, glbName() -> loaded model file name | null.
 */
export function createStoreUI(ctx) {
  const { S } = ctx;
  const $ = (id) => document.getElementById(id);
  const crewLocked = ctx.params.get('view') === 'crew';
  const today = /^\d{4}-\d{2}-\d{2}$/.test(ctx.params.get('today') || '') ? ctx.params.get('today') : localToday();
  let catalog = null;
  const studio = new Map(); // productId::color -> studio product (keeps its fit-to-roof view)
  const names = new Map(); // productId -> shortName
  const pick = { source: 'stores', slot: 'covering', store: 'both', brand: '', type: 'all', priced: true, inStock: false, q: '', limit: PAGE };
  const list = { crew: crewLocked, measured: null, savedHouse: null, notices: [], change: null, loaded: null };
  const roofSwitches = [];
  let baseline = null;
  let seq = 0;

  const short = (sp) => { if (!names.has(sp.id)) names.set(sp.id, shortName(sp)); return names.get(sp.id); };
  const job = () => S.job;

  // -------------------------------------------------------------------------
  // job state

  function newJob() {
    return {
      name: 'Untitled roof', shownStore: MN, roofSource: 'store', waste: { pct: 17, source: 'suggested' }, valleyMetal: false,
      selections: suggestedSelections(catalog), typed: { nails: null, deckRepair: null }, snapshot: null, dirty: false,
    };
  }

  function studioProduct(sp, color) {
    const key = `${sp.id}::${color ?? ''}`;
    if (!studio.has(key)) studio.set(key, toStudioProduct(sp, color, catalog));
    return studio.get(key);
  }

  /** Apply the shown store's choices for these slots to the roof. Resolves when the covering is drawn. */
  async function applySlots(slots = SLOTS) {
    const L = ctx.layers();
    if (!L || !catalog) return;
    const store = job().shownStore;
    const opts = {};
    let product = null;
    for (const slot of slots) {
      const c = job().selections[slot]?.[store];
      const sp = c && findProduct(catalog, c.productId);
      if (!sp) continue;
      if (slot === 'covering') product = studioProduct(sp, c.color);
      else Object.assign(opts, layerOptionFor(sp, c.color));
    }
    const draw = product && product !== S.product;
    // the covering rebuild draws the caps too: set their colors without a rebuild of their own
    if (draw) for (const k of ['capPalette', 'capColor']) if (k in opts) { L.options[k] = opts[k]; delete opts[k]; }
    setLabels();
    if (Object.keys(opts).length) ctx.setLayerOptions(opts);
    if (draw) await ctx.applyProduct(product);
    else ctx.renderStack();
  }

  /** Exploded-view labels and Layers-tab lines name the chosen store product. */
  function setLabels() {
    const L = ctx.layers();
    if (!L || !catalog || !job()) return;
    for (const [slot, id] of Object.entries(SLOT_LAYER)) {
      const c = job().selections[slot]?.[job().shownStore];
      const sp = c && findProduct(catalog, c.productId);
      if (!sp) continue;
      const text = specFor(sp, c.color, catalog);
      L.specOverride[id] = text;
      const rec = L.layers.get(id);
      if (rec) rec.info.spec = text;
    }
  }

  function choose(slot, sp, color) {
    const sel = job().selections[slot] || (job().selections[slot] = {});
    const prev = sel[sp.store];
    const next = { productId: sp.id, color: color ?? null, source: 'chosen' };
    if (prev?.productId === sp.id) for (const k of ['typedPrice', 'typedCoverage']) if (prev[k] != null) next[k] = prev[k];
    sel[sp.store] = next;
    let done = Promise.resolve();
    if (sp.store === job().shownStore) done = applySlots([slot]);
    else if (VIEW_SLOTS.has(slot)) ctx.toast(`Chosen for ${storeName(sp.store)}. The roof shows ${storeName(job().shownStore)} products: switch "On the roof" to see it.`);
    changed();
    return done;
  }

  function showStore(storeId) {
    if (!STORE_IDS.includes(storeId)) return Promise.resolve();
    job().shownStore = storeId;
    roofSwitches.forEach((w) => w.sync());
    if (!job().selections.covering?.[storeId]) ctx.toast(`No covering is chosen for ${storeName(storeId)}: the roof keeps ${S.product?.name || 'its product'}.`);
    const done = applySlots(SLOTS);
    changed();
    return done;
  }

  function changed() {
    job().dirty = true;
    renderPicker();
    refresh();
  }

  // -------------------------------------------------------------------------
  // store picker (Materials tab)

  function buildPicker() {
    const root = $('storePicker');
    if (!root) return;
    root.innerHTML = '';
    const src = segmented([['stores', 'Stores'], ['builtin', 'Built-in and photos']], () => pick.source, setSource, 'Products from');
    src.id = 'sfSource';
    root.append(el('div', { class: 'sf-line' }, el('span', { class: 'sf-k' }, 'Catalog'), src));
    if (!catalog) {
      root.append(el('p', { class: 'hint' }, 'The store catalog did not load, so only the built-in products and photos are offered.'));
      setSource('builtin');
      src.hidden = true;
      return;
    }
    root.append(el('div', { class: 'sf-line' }, el('span', { class: 'sf-k' }, 'On the roof'), roofSwitch()));
    const slotSel = el('select', { id: 'sfSlot', class: 'grow', onchange: (e) => setSlot(e.target.value) });
    for (const s of SLOTS) slotSel.add(new Option(LINE_LABELS[s], s, false, s === pick.slot));
    const narrow = window.matchMedia?.('(max-width: 860px)').matches;
    const typeSeg = segmented(COVER_TYPES, () => pick.type, (v) => { pick.type = v; filtersChanged(); }, 'Type');
    const storeSeg = segmented(STORE_FILTERS, () => pick.store, (v) => { pick.store = v; filtersChanged(); }, 'Store');
    storeSeg.id = 'sfStoreSeg'; typeSeg.id = 'sfTypeSeg';
    const sec = el('div', { id: 'sfStoreSec', class: 'sf-pick' },
      el('div', { class: 'row' }, el('label', { for: 'sfSlot' }, 'Choosing for'), slotSel),
      el('details', { class: 'sf-filters', id: 'sfFilters', open: !narrow },
        el('summary', {}, 'Filters'),
        el('div', { class: 'sf-fgrid' },
          el('div', { class: 'sf-line' }, el('span', { class: 'sf-k' }, 'Store'), storeSeg),
          el('div', { class: 'sf-line', id: 'sfTypeRow' }, el('span', { class: 'sf-k' }, 'Type'), typeSeg),
          el('div', { class: 'row' }, el('label', { for: 'sfBrand' }, 'Brand'), el('select', { id: 'sfBrand', class: 'grow', onchange: (e) => { pick.brand = e.target.value; pick.limit = PAGE; renderResults(); } })),
          el('div', { class: 'sf-checks' },
            el('label', {}, el('input', { type: 'checkbox', id: 'sfPriced', checked: pick.priced, onchange: (e) => { pick.priced = e.target.checked; filtersChanged(); } }), 'Priced only'),
            el('label', {}, el('input', { type: 'checkbox', id: 'sfStock', checked: pick.inStock, onchange: (e) => { pick.inStock = e.target.checked; filtersChanged(); } }), 'In stock at Home Depot')))),
      el('div', { class: 'row' }, el('input', { id: 'sfSearch', class: 'grow', type: 'search', placeholder: 'Search store products', 'aria-label': 'Search store products', oninput: (e) => { pick.q = e.target.value; pick.limit = PAGE; renderResults(); } })),
      el('div', { id: 'sfChosen', class: 'sf-chosen', 'aria-live': 'polite' }),
      el('p', { class: 'hint', id: 'sfCount' }),
      el('div', { id: 'sfResults', class: 'sf-results', role: 'list' }),
      el('button', { type: 'button', class: 'btn', id: 'sfMore', hidden: true, onclick: () => { pick.limit += PAGE; renderResults(); } }, `Show ${PAGE} more`));
    root.append(sec);
    filtersChanged();
  }

  function roofSwitch() {
    const w = segmented([[MN, 'Menards'], [HD, 'Home Depot']], () => job()?.shownStore, (v) => showStore(v), 'Store whose products are on the roof');
    w.classList.add('sf-roofsw');
    roofSwitches.push(w);
    return w;
  }

  function setSource(v) {
    pick.source = v;
    $('sfSource')?.sync?.();
    if ($('builtinSec')) $('builtinSec').hidden = v !== 'builtin';
    if ($('sfStoreSec')) $('sfStoreSec').hidden = v === 'builtin';
  }

  function setSlot(slot) {
    if (!SLOTS.includes(slot)) return;
    pick.slot = slot; pick.brand = ''; pick.limit = PAGE;
    if ($('sfSlot')) $('sfSlot').value = slot;
    filtersChanged();
  }

  const slotProducts = () => (catalog?.products || []).filter((p) => p.layer === pick.slot && !LEFT_OUT.has(p.kind));
  const inStock = (p) => p.stock?.qty > 0 || (p.stock?.inStock === true && p.stock?.qty == null);

  function filtered({ brand = true, search = true } = {}) {
    const words = search ? pick.q.toLowerCase().split(/\s+/).filter(Boolean) : [];
    return slotProducts().filter((p) => {
      if (pick.store !== 'both' && p.store !== pick.store) return false;
      if (pick.slot === 'covering' && pick.type !== 'all' && p.category !== pick.type) return false;
      if (pick.priced && p.price?.shelf == null) return false;
      if (pick.inStock && p.store === HD && !inStock(p)) return false;
      if (brand && pick.brand && (p.brand || '') !== pick.brand) return false;
      if (words.length) {
        const hay = `${p.name} ${p.brand || ''} ${(p.colors || []).map((c) => c.name || '').join(' ')}`.toLowerCase();
        if (!words.every((w) => hay.includes(w))) return false;
      }
      return true;
    });
  }

  /** Store, type, priced or stock changed: rebuild the brand list, then the rows. */
  function filtersChanged() {
    if (!$('sfStoreSec')) return;
    $('sfTypeRow').hidden = pick.slot !== 'covering';
    $('sfStoreSeg')?.sync(); $('sfTypeSeg')?.sync();
    const brands = [...new Set(filtered({ brand: false, search: false }).map((p) => p.brand).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    if (pick.brand && !brands.includes(pick.brand)) pick.brand = '';
    const sel = $('sfBrand');
    sel.innerHTML = '';
    sel.add(new Option('All brands', ''));
    for (const b of brands) sel.add(new Option(b, b, false, b === pick.brand));
    pick.limit = PAGE;
    renderResults();
  }

  function renderPicker() {
    if (!$('sfStoreSec') || !job()) return;
    renderResults();
  }

  function renderResults() {
    const box = $('sfResults');
    if (!box || !job()) return;
    renderChosen();
    const items = filtered();
    const counts = new Map();
    for (const p of items) counts.set(short(p), (counts.get(short(p)) || 0) + 1);
    box.innerHTML = '';
    for (const p of items.slice(0, pick.limit)) box.append(productRow(p, counts.get(short(p)) > 1));
    if (!items.length) box.append(el('p', { class: 'hint' }, 'No store products match. Clear the search or the filters.'));
    $('sfMore').hidden = items.length <= pick.limit;
    $('sfCount').textContent = `${items.length} ${LINE_LABELS[pick.slot].toLowerCase()} product${items.length === 1 ? '' : 's'}${items.length > pick.limit ? `, showing the first ${pick.limit}` : ''}. Tap one to choose it for its store.`;
  }

  function renderChosen() {
    const box = $('sfChosen');
    box.innerHTML = '';
    box.append(el('p', { class: 'sf-k' }, `Chosen for ${LINE_LABELS[pick.slot]}`));
    for (const s of STORE_IDS) {
      const c = job().selections[pick.slot]?.[s];
      const sp = c && findProduct(catalog, c.productId);
      box.append(el('button', { type: 'button', class: 'sf-cho', onclick: () => revealRow(s), title: sp ? 'Show it in the list' : 'Pick one below' },
        sp ? chip(colorEntry(sp, c.color), { sampled: SAMPLED.has(pick.slot) }) : el('span', { class: 'sf-chip kind', 'aria-hidden': 'true' }),
        el('span', { class: 'sf-cn' }, storeTag(s), ' ', el('b', {}, sp ? `${short(sp)}${c.color ? `, ${c.color}` : ''}` : 'not chosen'),
          sp && c.source === 'suggested' ? [' ', tag('suggested')] : null)));
    }
  }

  function priceText(sp) {
    if (crewLocked) return null;
    const pr = sp.price || {};
    if (pr.shelf == null) return 'no price: ask the store';
    const pack = sp.packCount > 1 && sp.category !== 'shingle' && !['shingleCap', 'starter'].includes(sp.kind) && pr.per !== 'bundle';
    return `${pr.startingAt ? 'from ' : ''}${fmtMoney(pr.shelf)} / ${pack ? `pack of ${sp.packCount}` : pr.per || 'each'}`;
  }

  function coverageText(sp) {
    const c = sp.coverage || {};
    if (c.sqft) return `${num(c.sqft, c.sqft % 1 ? 1 : 0)} sq ft${c.basis === 'gross' ? ' gross' : ''}`;
    if (c.lf) return `${num(c.lf, c.lf % 1 ? 1 : 0)} ft`;
    if (sp.pieceFt) return `${num(sp.pieceFt, sp.pieceFt % 1 ? 1 : 0)} ft piece`;
    if (sp.price?.per === '100 sq ft') return 'cut to length';
    return 'coverage not stated';
  }

  function stockText(sp) {
    if (sp.store !== HD || !sp.stock) return null;
    if (sp.stock.qty > 0) return `${num(sp.stock.qty)} in store`;
    if (sp.stock.inStock === false) return 'none in store';
    return null;
  }

  function productRow(sp, showFull) {
    const c = job().selections[pick.slot]?.[sp.store];
    const chosen = c?.productId === sp.id;
    const color = chosen ? c.color : defaultColor(sp);
    const entry = colorEntry(sp, color);
    const sampled = SAMPLED.has(pick.slot);
    const facts = [priceText(sp), coverageText(sp), sp.brand, stockText(sp), sampled && !entry.hex ? 'color not sampled' : null].filter(Boolean);
    const wrap = el('div', { class: `sf-item${chosen ? ' on' : ''}`, role: 'listitem', 'data-id': sp.id });
    wrap.append(el('button', { type: 'button', class: 'sf-row', 'aria-pressed': String(chosen), title: cleanName(sp.name), onclick: () => choose(pick.slot, sp, color) },
      chip(entry, { sampled }),
      el('span', { class: 'sf-rt' },
        el('span', { class: 'sf-l1' }, el('b', {}, short(sp)), color ? `, ${color}` : '', chosen ? [' ', tag(c.source === 'suggested' ? 'suggested' : 'chosen')] : null),
        el('span', { class: 'sf-l2' }, storeTag(sp.store), ' ', facts.join(' · ')),
        showFull ? el('span', { class: 'sf-l3' }, cleanName(sp.name)) : null)));
    if (chosen) wrap.append(chosenDetail(sp, c));
    return wrap;
  }

  function approxNotes(sp, color) {
    if (sp.layer === 'covering') return toStudioProduct(sp, color, catalog).approx;
    if (!SAMPLED.has(sp.layer)) return [];
    const e = colorEntry(sp, color);
    const out = [];
    if (!e.hex) out.push('color not sampled');
    else if (e.colorSource === 'name') out.push('color from its name, not from a photo');
    if (e.colorCheck?.includes('name-mismatch')) out.push('sampled color may not match its name');
    return out;
  }

  function chosenDetail(sp, c) {
    const d = el('div', { class: 'sf-detail' });
    const colors = (sp.colors || []).filter((x) => x.name != null);
    if (colors.length > 1) {
      const g = el('div', { class: 'sf-colors', role: 'group', 'aria-label': `Colors of ${short(sp)}` });
      for (const x of colors) {
        const e = colorEntry(sp, x.name);
        g.append(el('button', { type: 'button', class: 'sf-color', 'aria-pressed': String(x.name === c.color), title: e.hex ? `${x.name} (${e.hex})` : `${x.name}: color not sampled`, onclick: () => choose(pick.slot, sp, x.name) },
          chip(e, { sampled: SAMPLED.has(pick.slot) }), el('span', {}, x.name)));
      }
      d.append(g);
    }
    const notes = approxNotes(sp, c.color);
    if (notes.length) d.append(el('p', { class: 'sf-approx' }, notes.join(' · ')));
    d.append(el('p', { class: 'sf-l3' }, cleanName(sp.name), sp.url ? ' · ' : '', sp.url ? el('a', { href: sp.url, target: '_blank', rel: 'noopener noreferrer' }, 'Store page') : null));
    return d;
  }

  /** Scroll to the chosen row of a store, clearing filters that hide it. */
  function revealRow(store) {
    const c = job().selections[pick.slot]?.[store];
    if (!c) return;
    let items = filtered();
    if (!items.some((p) => p.id === c.productId)) {
      Object.assign(pick, { store: 'both', brand: '', type: 'all', q: '', inStock: false });
      const sp = findProduct(catalog, c.productId);
      if (sp?.price?.shelf == null) pick.priced = false;
      $('sfSearch').value = ''; $('sfPriced').checked = pick.priced; $('sfStock').checked = false;
      filtersChanged();
      items = filtered();
    }
    const i = items.findIndex((p) => p.id === c.productId);
    if (i >= pick.limit) { pick.limit = Math.ceil((i + 1) / PAGE) * PAGE; renderResults(); }
    const row = $('sfResults').querySelector(`[data-id="${CSS.escape(c.productId)}"]`);
    row?.scrollIntoView({ block: 'center' });
    row?.querySelector('button')?.focus({ preventScroll: true });
  }

  function jumpToPicker(slot, store) {
    ctx.selectTab('materials');
    setSource('stores');
    setSlot(slot);
    revealRow(store);
  }

  // -------------------------------------------------------------------------
  // priced list (List tab)

  function currentQuote() {
    const L = ctx.layers();
    const w = ctx.waste();
    job().waste = { pct: w.pct, source: w.source };
    const q = list.measured || L.quantities();
    return buildQuote({ q, job: job(), catalog, today, priceOverride: job().snapshot?.items || null, roofName: S.product?.name });
  }

  function buildList() {
    const pane = $('quotePane');
    if (!pane) return;
    pane.innerHTML = '';
    if (!catalog) { pane.append(el('p', { class: 'hint' }, 'The store catalog did not load, so there is no priced list.')); return; }
    const waste = el('input', { id: 'sfWaste', type: 'number', min: '0', max: '40', step: '1', inputmode: 'numeric',
      oninput: (e) => { if (e.target.value !== '') ctx.setWaste(Math.max(0, Math.min(40, Number(e.target.value) || 0))); } });
    pane.append(
      el('div', { id: 'sfLHead', class: 'sf-lhead' }),
      el('div', { id: 'sfLCtl', class: 'sf-lctl' },
        el('div', { class: 'sf-line' }, el('span', { class: 'sf-k' }, 'On the roof'), roofSwitch()),
        el('div', { class: 'row sf-office' }, el('label', { for: 'sfWaste' }, 'Waste %'), waste, el('span', { class: 'hint', id: 'sfWasteSrc' }),
          el('button', { type: 'button', class: 'sf-linkbtn', id: 'sfWasteReset', onclick: () => ctx.setWaste(null) }, 'Use suggested')),
        el('div', { class: 'row sf-office' }, el('input', { type: 'checkbox', id: 'sfValley', onchange: (e) => { job().valleyMetal = e.target.checked; job().dirty = true; refresh(); } }),
          el('label', { for: 'sfValley', class: 'sf-cl' }, 'Valley metal'), el('span', { class: 'hint' }, 'off: closed valley over ice & water')),
        crewLocked ? null : el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', id: 'sfCrew', 'aria-pressed': String(list.crew), onclick: () => setCrewView(!list.crew) }, 'Crew view'),
          el('span', { class: 'hint' }, 'one store, quantities only, no prices'))),
      el('div', { id: 'sfListBody', class: 'sf-lbody' }),
      el('div', { id: 'sfLBtns', class: 'sf-lbtns' }));
  }

  function refresh() {
    if (!catalog || !job() || !ctx.layers()) return;
    renderList();
  }

  function renderList() {
    if (!$('sfListBody')) return;
    const quote = currentQuote();
    renderHead(quote);
    const w = $('sfWaste');
    if (document.activeElement !== w) w.value = job().waste.pct;
    $('sfWasteSrc').textContent = job().waste.source === 'typed' ? 'typed by you' : 'suggested from the hips and valleys';
    $('sfWasteReset').hidden = job().waste.source !== 'typed';
    $('sfValley').checked = !!job().valleyMetal;
    document.querySelectorAll('#sfLCtl .sf-office').forEach((r) => { r.hidden = list.crew; });
    $('sfCrew')?.setAttribute('aria-pressed', String(list.crew));
    const body = $('sfListBody');
    body.innerHTML = '';
    if (list.crew) renderCrew(body, quote); else renderOffice(body, quote);
    renderButtons();
  }

  function renderHead(quote) {
    const h = $('sfLHead');
    h.innerHTML = '';
    h.append(el('h3', {}, list.crew ? 'Crew list' : 'Materials list'), el('p', { class: 'sf-job' }, job().name));
    if (list.crew) {
      h.append(el('p', { class: 'hint' }, `${storeName(job().shownStore)} products. Quantities come from the 3D model: check them on the roof before ordering.`));
      if (list.measured) h.append(el('p', { class: 'sf-note' }, 'Measurements as saved: the house model is not loaded.'));
      return;
    }
    h.append(el('p', { class: 'sf-hd' }, quote.status.header), el('p', { class: 'hint' }, quote.status.age.text));
    for (const n of list.notices) h.append(el('p', { class: 'sf-note' }, n));
    if (list.measured) h.append(el('p', { class: 'sf-note' }, 'Measurements as saved: the house model is not loaded, so the list uses the numbers stored in the project.'));
    for (const n of quote.notes) if (n !== NOT_INCLUDED) h.append(el('p', { class: 'sf-note' }, n));
    if (job().snapshot) {
      h.append(el('div', { class: 'sf-note sf-snap' }, el('p', {}, snapshotNotice(list.loaded?.cmp || compareSnapshot(job().snapshot, catalog), job().snapshot.savedOn)),
        el('button', { type: 'button', class: 'btn', onclick: useCurrentPrices }, 'Use current prices')));
    } else if (list.loaded?.savedOn) h.append(el('p', { class: 'hint' }, `Saved ${fmtDate(list.loaded.savedOn)}`));
    if (list.change) h.append(el('div', { class: 'sf-note' }, el('p', {}, 'Now priced from the current store data:'), el('ul', {}, list.change.map((t) => el('li', {}, t)))));
  }

  function renderOffice(body, quote) {
    for (const l of quote.lines) body.append(lineCard(l, quote, true));
    body.append(totalsBlock(quote));
    body.append(el('p', { class: 'hint' }, NOT_INCLUDED));
  }

  function basisLine(l) {
    const p = el('p', { class: 'sf-basis' });
    if (l.basis) p.append(l.basis.text, ' ', el('b', {}, 'measured'));
    if (l.allowance) p.append(l.basis ? ' + ' : '', l.allowance.text, ' (', el('b', {}, 'allowance'), ')');
    if (l.basis && l.allowance?.pct) p.append(el('span', { class: 'sf-need' }, ` = ${num(l.need.value, 1)} ${l.need.unit}`));
    return p;
  }

  function lineCard(l, quote, interactive) {
    const card = el('section', { class: 'sf-card', 'aria-label': l.label }, el('h4', {}, l.label), basisLine(l));
    const by = l.allowance?.setBy;
    if (by && !/fixed rule/.test(by)) card.append(el('p', { class: 'sf-setby' }, /^you\b/.test(by) ? `Allowance set by ${by}.` : `Allowance ${by}.`));
    if (l.slot === 'nails' || l.slot === 'deckRepair') { card.append(typedLine(l, quote, interactive)); return card; }
    for (const s of quote.stores) card.append(storeCell(l, s, l.cells[s.id], interactive));
    return card;
  }

  /** Nails and deck repair: no store product; one typed amount for the whole line, both stores. */
  function typedLine(l, quote, interactive) {
    const c = l.cells[quote.stores[0].id];
    const qty = c.qty != null ? `${c.qtyText} ${plural(c.noun || c.unit, c.qty)}` : DASH;
    const box = el('div', { class: `sf-cell st-${c.status}` },
      el('div', { class: 'sf-ch' }, el('span', { class: 'sf-store s-both' }, 'Both stores'), c.priceSource === 'typed' ? tag('typed') : null),
      el('div', { class: 'sf-nums' }, el('span', { class: 'sf-q' }, qty), el('span', { class: 'sf-t' }, c.totalText)));
    if (c.why) box.append(el('p', { class: 'sf-why' }, `${c.why}. Set by ${c.setBy}.`));
    if (interactive) box.append(typedInput('Amount for this line', job().typed?.[l.slot], (v) => { job().typed[l.slot] = v; job().dirty = true; refresh(); }, 'whole line, both stores'));
    return box;
  }

  function productLabel(c) {
    if (!c.productId) return 'not chosen';
    const sp = findProduct(catalog, c.productId);
    return `${sp ? short(sp) : cleanName(c.name || c.productId)}${c.color ? `, ${c.color}` : ''}`;
  }

  function storeCell(l, s, c, interactive) {
    const lower = l.lower === s.id;
    const cell = el('div', { class: `sf-cell st-${c.status}${lower ? ' lower' : ''}` });
    const label = productLabel(c);
    cell.append(el('div', { class: 'sf-ch' }, storeTag(s.id),
      interactive ? el('button', { type: 'button', class: 'sf-prod', title: 'Change it in the store picker', onclick: () => jumpToPicker(l.slot, s.id) }, label) : el('span', { class: 'sf-prod' }, label),
      c.suggested ? tag('suggested') : null, c.priceSource === 'typed' ? tag('typed') : null, c.status === 'startingAt' ? tag('from') : null, lower ? tag('lower') : null));
    const qty = c.qty != null ? `${c.qtyText} ${plural(c.noun || c.unit, c.qty)}` : DASH;
    cell.append(el('div', { class: 'sf-nums' }, el('span', { class: 'sf-q' }, qty),
      c.unitPrice != null ? el('span', { class: 'sf-u' }, `at ${c.unitPriceText}`) : null,
      el('span', { class: 'sf-t' }, c.totalText)));
    if (c.why) cell.append(el('p', { class: 'sf-why' }, `${c.why}. Set by ${c.setBy}.`));
    const notes = [...c.notes];
    if (c.pieces != null) notes.unshift(`${num(c.pieces)} pieces`);
    if (c.stock) cell.append(el('p', { class: `sf-cnote${c.stock.short ? ' short' : ''}` }, c.stock.text));
    if (notes.length) cell.append(el('p', { class: 'sf-cnote' }, notes.join(' · ')));
    if (interactive && c.productId) {
      const choice = job().selections[l.slot]?.[s.id];
      const unit = c.unit || findProduct(catalog, c.productId)?.price?.per || 'unit';
      if (choice && (c.needs?.price || choice.typedPrice != null)) {
        cell.append(typedInput('Type a price', choice.typedPrice, (v) => setTyped(l.slot, s.id, 'typedPrice', v), `per ${unit.replace(/^squares \(100 sq ft\)$/, 'square')}`));
      }
      if (choice && (c.needs?.coverage || choice.typedCoverage != null)) {
        cell.append(typedInput('Type coverage', choice.typedCoverage, (v) => setTyped(l.slot, s.id, 'typedCoverage', v), AREA_SLOTS.has(l.slot) ? 'sq ft per unit sold' : 'ft per unit sold'));
      }
    }
    return cell;
  }

  function typedInput(label, value, commit, hint) {
    const id = `sfT${++seq}`;
    return el('div', { class: 'sf-type' }, el('label', { for: id }, label),
      el('input', { id, type: 'number', min: '0', step: '0.01', inputmode: 'decimal', value: value ?? '', onchange: (e) => commit(e.target.value === '' ? null : Math.max(0, Number(e.target.value))) }),
      hint ? el('span', { class: 'hint' }, hint) : null);
  }

  function setTyped(slot, store, key, v) {
    const c = job().selections[slot]?.[store];
    if (!c) return;
    if (v == null || !Number.isFinite(v)) delete c[key]; else c[key] = v;
    job().dirty = true;
    refresh();
  }

  function statusLine(t) {
    const i = t.text.indexOf(':');
    const lead = t.status === 'incomplete' && i > 0 ? t.text.slice(0, i) : null;
    return el('p', { class: 'sf-tt' }, lead ? [el('b', {}, lead), t.text.slice(i)] : t.text);
  }

  function totalsBlock(quote) {
    const box = el('section', { class: 'sf-card sf-totals', 'aria-label': 'Totals' }, el('h4', {}, 'Totals'));
    for (const s of quote.stores) {
      const t = quote.totals[s.id];
      box.append(el('div', { class: `sf-total st-${t.status}` }, storeTag(s.id), statusLine(t)));
      if (t.rebate) box.append(el('p', { class: 'sf-rebate' }, t.rebate.text));
    }
    const lo = quote.totals.lowest;
    box.append(el('div', { class: `sf-total st-${lo.status}` }, el('span', { class: 'sf-store s-both' }, 'Lowest per line'), statusLine(lo)));
    return box;
  }

  function renderCrew(body, quote) {
    const crew = crewView(quote, job().shownStore);
    crew.lines.forEach((l, i) => {
      const ql = quote.lines[i];
      const c = ql.cells[crew.store.id];
      const product = c.productId ? productLabel(c) : null;
      body.append(el('section', { class: 'sf-card', 'aria-label': l.label }, el('h4', {}, l.label),
        product ? el('p', { class: 'sf-crew-p' }, product) : null,
        el('p', { class: 'sf-crew-q' }, l.qty != null ? `${l.qtyText} ${plural(l.noun || l.unit, l.qty)}` : DASH, l.why ? el('span', { class: 'sf-why' }, ` ${l.why}`) : null),
        el('p', { class: 'sf-basis' }, l.measured, ' ', el('b', {}, ql.basis ? 'measured' : 'allowance'))));
    });
  }

  function renderButtons() {
    const b = $('sfLBtns');
    b.innerHTML = '';
    const btn = (text, fn, primary) => el('button', { type: 'button', class: `btn${primary ? ' primary' : ''}`, onclick: fn }, text);
    if (!list.crew) b.append(btn('Open full list', openFull, true), btn('Download CSV', () => downloadCSV('office')));
    b.append(btn('Download crew CSV', () => downloadCSV('crew')), btn('Copy as text', copyText));
  }

  function setCrewView(on) {
    if (crewLocked && !on) return;
    list.crew = !!on;
    refresh();
  }

  function downloadCSV(view) {
    const quote = currentQuote();
    const text = quoteCSV(quote, view === 'crew' ? { view: 'crew', store: job().shownStore } : { view: 'office' });
    ctx.saveFile(csvFileName(job().name, today, view), new Blob([text], { type: 'text/csv' }));
  }

  /** The list as plain text: office (both stores and totals) or crew (one store, no prices). */
  function listText(quote, crew = list.crew) {
    const out = [`${job().name}: ${crew ? `crew list, ${storeName(job().shownStore)}` : 'materials list'}`];
    if (crew) {
      const cv = crewView(quote, job().shownStore);
      for (const l of cv.lines) out.push(`${l.label}: ${l.product ? `${cleanName(l.product)}${l.color ? `, ${l.color}` : ''}: ` : ''}${l.qty != null ? `${l.qtyText} ${plural(l.noun || l.unit, l.qty)}` : `${DASH} ${l.why || ''}`.trim()} (${l.measured})`);
      return out.join('\n');
    }
    out.push(quote.status.header, quote.status.age.text, '');
    for (const l of quote.lines) {
      out.push(`${l.label}: ${[l.basis ? `${l.basis.text} measured` : null, l.allowance ? `${l.allowance.text} (allowance)` : null].filter(Boolean).join(' + ')}`);
      for (const s of quote.stores) {
        const c = l.cells[s.id];
        out.push(`  ${s.name}: ${c.productId ? productLabel(c) : c.status === 'notChosen' ? 'not chosen' : ''}${c.productId ? ': ' : ''}${c.qty != null ? `${c.qtyText} ${plural(c.noun || c.unit, c.qty)}` : DASH}${c.unitPrice != null ? ` at ${c.unitPriceText}` : ''} = ${c.totalText}${c.why ? ` (${c.why})` : ''}${l.lower === s.id ? ' [lower]' : ''}`);
      }
    }
    out.push('', 'Totals');
    for (const s of quote.stores) {
      out.push(`  ${s.name}: ${quote.totals[s.id].text}`);
      if (quote.totals[s.id].rebate) out.push(`    ${quote.totals[s.id].rebate.text}`);
    }
    out.push(`  Lowest per line: ${quote.totals.lowest.text}`, '', ...quote.notes);
    return out.join('\n');
  }

  async function copyText() {
    const text = listText(currentQuote());
    try { await navigator.clipboard.writeText(text); ctx.toast('Copied the list as text.'); } catch (_) { ctx.toast('Copy is not available here. Use Download CSV instead.'); }
  }

  function useCurrentPrices() {
    const before = currentQuote();
    job().snapshot = null;
    const after = currentQuote();
    list.change = [...before.stores.map((s) => [s.name, before.totals[s.id], after.totals[s.id]]), ['Lowest per line', before.totals.lowest, after.totals.lowest]]
      .map(([n, a, b]) => {
        const d = Math.round((b.amount - a.amount) * 100) / 100;
        return `${n}: ${fmtMoney(a.amount)} as saved, ${fmtMoney(b.amount)} now (${d === 0 ? 'no change' : `${d > 0 ? '+' : '−'}${fmtMoney(Math.abs(d))}`})`;
      });
    job().dirty = true;
    refresh();
  }

  // -------------------------------------------------------------------------
  // full-list dialog: both stores side by side

  function openFull() {
    let d = $('sfFull');
    if (!d) {
      d = el('dialog', { id: 'sfFull', class: 'sf sf-full', 'aria-labelledby': 'sfFullT' });
      d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
      document.body.append(d);
    }
    const quote = currentQuote();
    d.innerHTML = '';
    d.append(el('div', { class: 'sf-fhead' },
      el('div', {}, el('h2', { id: 'sfFullT' }, `Materials list: ${job().name}`), el('p', { class: 'sf-hd' }, quote.status.header), el('p', { class: 'hint' }, quote.status.age.text)),
      el('button', { type: 'button', class: 'btn', onclick: () => d.close() }, 'Close')));
    const scroll = el('div', { class: 'sf-fbody' }, fullTable(quote), el('div', { class: 'sf-fcards' }, quote.lines.map((l) => lineCard(l, quote, false)), totalsBlock(quote)),
      el('p', { class: 'hint' }, NOT_INCLUDED));
    d.append(scroll);
    d.showModal();
  }

  function fullTable(quote) {
    const stores = quote.stores;
    const th = (text, props = {}) => el('th', props, text);
    const colgroup = [el('colgroup', {}, el('col', { class: 'c-line' }), el('col', { class: 'c-meas' })), ...stores.map((s) => el('colgroup', { class: `g-${s.id === MN ? 'mn' : 'hd'}` }, el('col', { class: 'c-prod' }), el('col'), el('col'), el('col')))];
    const head = el('thead', {},
      el('tr', {}, th('Line', { rowspan: 2, scope: 'col' }), th('Measured and allowance', { rowspan: 2, scope: 'col' }), stores.map((s) => th(s.name, { colspan: 4, scope: 'colgroup', class: 'g' }))),
      el('tr', {}, stores.map(() => [th('Product', { scope: 'col' }), th('Qty', { scope: 'col', class: 'n' }), th('Unit price', { scope: 'col', class: 'n' }), th('Total', { scope: 'col', class: 'n' })])));
    const body = el('tbody', {}, quote.lines.map((l) => el('tr', {},
      el('th', { scope: 'row' }, l.label),
      el('td', { class: 'meas' }, basisLine(l)),
      stores.map((s) => {
        const c = l.cells[s.id];
        const lower = l.lower === s.id;
        const isTyped = l.slot === 'nails' || l.slot === 'deckRepair';
        return [
          el('td', { class: 'g0' }, isTyped ? (c.priceSource === 'typed' ? 'typed amount' : '') : productLabel(c),
            c.suggested ? [' ', tag('suggested')] : null, c.priceSource === 'typed' ? [' ', tag('typed')] : null,
            c.why ? el('div', { class: 'sf-why' }, c.why) : null,
            [...(c.stock ? [c.stock.text] : []), ...c.notes].length ? el('div', { class: 'sf-cnote' }, [...(c.stock ? [c.stock.text] : []), ...c.notes].join(' · ')) : null),
          el('td', { class: 'n' }, c.qty != null ? `${c.qtyText} ${plural(c.noun || c.unit, c.qty)}` : DASH),
          el('td', { class: 'n' }, c.unitPriceText),
          el('td', { class: `n tot${lower ? ' lower' : ''}` }, c.totalText, lower ? el('div', {}, tag('lower')) : null),
        ];
      }))));
    const foot = el('tfoot', {},
      el('tr', {}, th('Totals', { scope: 'row', colspan: 2 }), stores.map((s) => el('td', { colspan: 4 }, statusLine(quote.totals[s.id]), quote.totals[s.id].rebate ? el('p', { class: 'sf-rebate' }, quote.totals[s.id].rebate.text) : null))),
      el('tr', {}, th('Lowest per line', { scope: 'row', colspan: 2 }), el('td', { colspan: 4 * stores.length }, statusLine(quote.totals.lowest))));
    return el('div', { class: 'sf-ftable' }, el('table', {}, el('caption', { class: 'sf-vh' }, 'Materials list, both stores side by side'), colgroup, head, body, foot));
  }

  // -------------------------------------------------------------------------
  // project file (Project tab)

  function buildProjectFile() {
    const root = $('projectFile');
    if (!root) return;
    root.innerHTML = '';
    root.append(
      el('h3', {}, 'Project file'),
      el('div', { class: 'row' }, el('label', { for: 'sfJobName' }, 'Job name'),
        el('input', { id: 'sfJobName', class: 'grow', type: 'text', placeholder: 'Untitled roof', oninput: (e) => { if (!job()) return; job().name = e.target.value.trim() || 'Untitled roof'; job().dirty = true; refresh(); } })),
      el('div', { class: 'row sf-pbtns' },
        el('button', { type: 'button', class: 'btn', id: 'sfNew', onclick: onNew }, 'New'),
        crewLocked ? null : el('button', { type: 'button', class: 'btn primary', id: 'sfSave', onclick: save }, 'Save'),
        el('button', { type: 'button', class: 'btn', id: 'sfOpenBtn', onclick: () => $('sfOpen').click() }, 'Open'),
        el('input', { id: 'sfOpen', type: 'file', accept: '.json,application/json', hidden: true, onchange: onOpenFile })),
      el('div', { id: 'sfConfirm', class: 'sf-note', hidden: true }),
      el('p', { class: 'hint', id: 'sfSaved' }, 'Saves the house, layers, store choices and a snapshot of their prices as a .json file. No images are saved.'));
    if (!catalog) root.querySelectorAll('button').forEach((b) => { b.disabled = true; });
  }

  function roofEntry() {
    const p = S.product || {};
    const v = p.view || {};
    const view = { scale: v.scale ?? 1, rotation: v.rotation ?? 0, offsetV: v.offsetV ?? 0, reliefScale: v.reliefScale ?? 1, tint: v.tint ?? null };
    if (p.store) return { source: 'store', store: p.store.id, productId: p.store.productId, color: p.store.color, view };
    if (p.image) return { source: 'photo', name: p.name };
    return { source: 'builtin', id: p.id ?? null, view };
  }

  function project({ savedAt } = {}) {
    const st = ctx.projectState();
    if (list.savedHouse) st.house = list.savedHouse;
    const measured = list.measured || ctx.layers().quantities();
    return buildProject({ job: job(), ...st, roof: roofEntry(), measured, catalog, quote: currentQuote(), today, ...(savedAt ? { savedAt } : {}) });
  }

  function showSaved() {
    const s = list.loaded;
    if (!s?.savedOn) return;
    const caps = Object.values(s.sources || {}).map((x) => x?.captured).filter(Boolean).sort();
    const from = caps[0] ? fmtDate(caps[0].slice(0, 10)).replace(/, \d{4}$/, '') : null;
    $('sfSaved').textContent = `Saved ${fmtDate(s.savedOn)}${from ? ` · prices from ${from}` : ''}`;
  }

  function save() {
    if (!catalog || !job()) return;
    const p = project();
    ctx.saveFile(projectFileName(p.name), new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' }));
    baseline = p;
    job().dirty = false;
    list.loaded = { savedOn: p.priceSnapshot.savedOn, sources: p.priceSnapshot.sources, cmp: list.loaded?.cmp };
    showSaved();
  }

  function isDirty() {
    if (!baseline) return false;
    const d = !sameProject(project({ savedAt: baseline.savedAt }), baseline);
    job().dirty = d;
    return d;
  }

  function onNew() {
    if (!catalog) return;
    const box = $('sfConfirm');
    if (!isDirty()) { box.hidden = true; startNew(); return; }
    box.innerHTML = '';
    box.append(el('p', {}, 'This job has changes that are not saved.'),
      el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn primary', onclick: () => { box.hidden = true; startNew(); } }, 'Discard and start new'),
        el('button', { type: 'button', class: 'btn', onclick: () => { box.hidden = true; } }, 'Cancel')));
    box.hidden = false;
    box.querySelector('button').focus();
  }

  /** New job: the suggested basket on the ranch house at 6/12, Sioux Falls, today. */
  async function startNew() {
    studio.clear();
    const cover = SUGGESTED.covering[MN];
    await ctx.applyProjectState({
      name: 'Untitled roof',
      job: { location: 'Sioux Falls, SD', lat: 43.54 },
      house: { source: 'preset', presetId: 'ranch-hip', pitch: 6 },
      sun: { date: today, hour: 15, facing: 180 },
      layers: { options: {}, custom: [], hidden: [] },
      roof: { source: 'store', store: MN, productId: cover.productId, color: cover.color, view: null },
      waste: { pct: null, source: 'suggested' }, shownStore: MN, valleyMetal: false,
      selections: suggestedSelections(catalog), typed: { nails: null, deckRepair: null }, measured: {}, priceSnapshot: null,
    }, { fresh: true });
    ctx.toast('New job: the suggested store products on the ranch house.');
  }

  async function onOpenFile(e) {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    let text;
    try { text = await f.text(); } catch (_) { ctx.toast('That file could not be read.'); return; }
    const r = await loadProject(text);
    if (r.ok) ctx.toast(`Opened ${f.name}.`);
  }

  /** Validate and open a project (file text or object). */
  async function loadProject(obj) {
    if (!catalog) { ctx.toast('The store catalog did not load, so projects cannot be opened here.'); return { ok: false, errors: ['no catalog'] }; }
    const r = parseProject(obj);
    if (!r.ok) { ctx.toast(r.errors[0]); return { ok: false, errors: r.errors }; }
    await ctx.applyProjectState(r.project);
    return { ok: true, errors: [] };
  }

  /** The supplier part of opening a project; app.js calls it after the house, sun and layers are set. */
  async function applyJob(p, { fresh = false } = {}) {
    const next = jobFromProject(p);
    let cmp = null;
    if (fresh) next.snapshot = null;
    else {
      cmp = compareSnapshot(p, catalog);
      if (cmp.unchanged) next.snapshot = null;
    }
    S.job = next;
    list.notices = []; list.change = null; list.measured = null; list.savedHouse = null;
    list.loaded = fresh ? null : { savedOn: p.priceSnapshot?.savedOn, sources: p.priceSnapshot?.sources, cmp };
    if (!fresh && p.house?.source === 'glb' && ctx.glbName() !== p.house.fileName) {
      list.measured = { ...p.measured };
      list.savedHouse = { ...p.house };
      list.notices.push(`This job used the house model ${p.house.fileName || '(no name)'}. Load it again on the Project tab.`);
    }
    ctx.setWaste(p.waste?.source === 'typed' ? p.waste.pct : null);
    if ($('sfJobName')) $('sfJobName').value = next.name === 'Untitled roof' ? '' : next.name;
    roofSwitches.forEach((w) => w.sync());
    if (fresh) await applySlots(SLOTS);
    else {
      const prod = roofProduct(p.roof);
      if (prod) {
        prod.view = { ...(p.roof?.view || {}) };
        if (prod.view.tint == null) delete prod.view.tint;
        await ctx.applyProduct(prod, { keepView: true });
      }
      setLabels();
      ctx.renderStack();
    }
    $('sfSaved').textContent = fresh ? 'New job, not saved yet.' : '';
    showSaved();
    renderPicker();
    refresh();
    baseline = project();
    S.job.dirty = false;
  }

  function roofProduct(r) {
    if (r?.source === 'store') {
      const sp = findProduct(catalog, r.productId);
      if (sp) return studioProduct(sp, r.color);
      list.notices.push(`The roof product ${r.productId} is no longer in the store capture; the roof shows the built-in default.`);
      return ctx.builtinProduct(null);
    }
    if (r?.source === 'photo') {
      list.notices.push(`The photo ${r.name || ''} is not saved in project files; the roof shows the built-in default.`.replace('  ', ' '));
      ctx.toast(list.notices[list.notices.length - 1]);
      return ctx.builtinProduct(null);
    }
    return ctx.builtinProduct(r?.id ?? null);
  }

  // -------------------------------------------------------------------------
  // Blender command (Project tab, Export)

  function blenderCommands() {
    const p = S.product || {};
    const metal = p.category === 'metal';
    const pal = (p.procedural?.palette || (p.procedural?.color ? [p.procedural.color] : null) || p._palette || []).slice(0, metal ? 1 : 4);
    const exp = p.exposureIn || p.procedural?.exposureIn || 5.625;
    const base = 'node roof-blender/scripts/roof-blender.mjs';
    return [`${base} layers --category ${metal ? 'metal' : 'shingle'}${metal ? '' : ` --exposure-in ${exp}`}`,
      pal.length ? `${base} material --palette "${pal.join(',')}"${metal ? ' --category metal' : ''}` : null].filter(Boolean).join('\n');
  }

  function buildBlenderButton() {
    const glb = $('btnGlb');
    if (!glb || $('sfBlender')) return;
    const pre = el('pre', { class: 'sf-cmd', id: 'sfBlenderCmd', hidden: true });
    glb.after(el('button', { type: 'button', class: 'btn', id: 'sfBlender', onclick: async () => {
      const text = blenderCommands();
      pre.textContent = text; pre.hidden = false;
      try { await navigator.clipboard.writeText(text); ctx.toast('Copied the Blender commands for the product on the roof.'); } catch (_) { ctx.toast('Copy is not available here: select the commands below the button.'); }
    } }, 'Blender command'));
    const hint = el('p', { class: 'hint' }, 'Blender command: copies the roof-blender lines that draw the product on the roof. Not matched in Blender yet: ribbed and corrugated profiles (Blender draws flat panels), drip edge color, cap color separate from the field, matte paint values.');
    ($('glbHint') || glb.parentElement).after(hint, pre);
    pre.classList.add('sf');
  }

  // -------------------------------------------------------------------------
  // lifecycle

  async function init() {
    catalog = await ctx.catalog();
    if (catalog) S.job = newJob();
    buildPicker(); buildList(); buildProjectFile(); buildBlenderButton();
    if (!catalog) setSource('builtin');
    return catalog;
  }

  /** The shown store's covering as a studio product, for the first draw (null without a catalog). */
  function firstProduct() {
    const c = catalog && job()?.selections.covering?.[job().shownStore];
    const sp = c && findProduct(catalog, c.productId);
    return sp ? studioProduct(sp, c.color) : null;
  }

  /** After the first house is built: the other layers follow the shown store, then the list draws. */
  async function afterBuild() {
    if (!catalog) return;
    job().roofSource = S.product?.store ? 'store' : 'builtin';
    await applySlots(SLOTS.filter((s) => s !== 'covering'));
    renderPicker();
    refresh();
    baseline = project();
    if (crewLocked) ctx.selectTab('list');
  }

  /** A new layer stack was made (house, pitch or model change): labels again; saved measurements stop. */
  function onLayers() {
    if (!job()) return;
    list.measured = null; list.savedHouse = null;
    setLabels();
  }

  function onRoof(p) {
    if (!job()) return;
    job().roofSource = p?.store ? 'store' : 'builtin';
  }

  const ensure = () => { if (!catalog) throw new Error('The store catalog is not loaded.'); };

  return {
    init, firstProduct, afterBuild, onLayers, onRoof, refresh, applyJob,
    openPicker: (slot) => { if (catalog && job()) jumpToPicker(slot, job().shownStore); else ctx.selectTab('materials'); },
    api: {
      quote: () => { ensure(); return currentQuote(); },
      project: () => { ensure(); return project(); },
      loadProject: (obj) => loadProject(obj),
      pickStore: (slot, productId, color) => {
        ensure();
        const sp = findProduct(catalog, productId);
        if (!sp || sp.layer !== slot) throw new Error(`No ${slot} product ${productId} in the store catalog.`);
        return choose(slot, sp, color === undefined ? defaultColor(sp) : color);
      },
      showStore: (storeId) => { ensure(); return showStore(storeId); },
      setCrewView: (on = true) => { ensure(); setCrewView(on); },
      storeProduct: async (productId, color) => {
        ensure();
        const sp = findProduct(catalog, productId);
        if (!sp || sp.layer !== 'covering') throw new Error(`No covering ${productId} in the store catalog.`);
        const c = color === undefined ? defaultColor(sp) : color;
        if (sp.store === job().shownStore) return choose('covering', sp, c);
        job().selections.covering[sp.store] = { productId: sp.id, color: c, source: 'chosen' };
        return showStore(sp.store);
      },
      blenderCommand: () => blenderCommands(),
      listText: (crew) => { ensure(); return listText(currentQuote(), crew); },
    },
  };
}
