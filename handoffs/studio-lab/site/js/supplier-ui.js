// Store features of the studio (lab project sioux-falls-studio): the store picker on the Materials tab,
// the priced list on the List tab, the full-list dialog, the crew view, the project buttons and the
// Blender command on the Project tab. DOM glue only: the rules live in quote.js, project-file.js and
// supplier-products.js. Supplier plan, sections 3, 8, 9 and 10.
//
// No store image is ever requested here: products show color chips drawn with CSS.

import { buildQuote, quoteCSV, crewView, csvFileName, fmtMoney, fmtDate, LINE_LABELS, SLOTS, STORE_IDS, NOT_INCLUDED } from './quote.js';
import { PROJECTS, SUPPLIERS, STUDIO_TYPES, DEFAULT_TYPE_FOR_SLOT, SORTS, typeOf, findType, findProject, slotOf, productsFor, countsFor, unitPrice, colourFamily, defaultFilters, activeCount, applyFilters, facets, sortProducts } from './materials-taxonomy.js';
import { buildProject, parseProject, jobFromProject, compareSnapshot, snapshotNotice, projectFileName, sameProject } from './project-file.js';
import { findProduct, suggestedSelections, storeName, defaultColor, colorEntry, shortName, specFor, toStudioProduct, layerOptionFor, SUGGESTED } from './supplier-products.js';

/** Slots drawn as their own layer, for the exploded-view label (the covering's label is its product name). */
const SLOT_LAYER = { ridgeCap: 'ridgeCap', starter: 'starter', underlayment: 'underlayment', iceWater: 'iceWater', dripEdge: 'dripEdge', ridgeVent: 'ridgeVent' };
/** Slots whose product changes the 3D view. */
const VIEW_SLOTS = new Set(['covering', 'ridgeCap', 'dripEdge', 'underlayment', 'iceWater']);
/** Slots whose colors were sampled from the store images (the others look like their product kind). */
const SAMPLED = new Set(['covering', 'ridgeCap', 'dripEdge', 'valley', 'ridgeVent']);
const AREA_SLOTS = new Set(['covering', 'underlayment', 'iceWater']);
const PAGE = 60;
const MN = 'menards-3064', HD = 'homedepot-4301';
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
    else if (VIEW_SLOTS.has(slot)) toastAction(`Chosen for ${storeName(sp.store)}. The roof shows ${storeName(job().shownStore)}.`, `Show ${storeName(sp.store)}`, () => showStore(sp.store));
    changed();
    return done;
  }

  /** A toast with one action button (the toast hides itself after a few seconds). */
  function toastAction(msg, label, fn) {
    ctx.toast(msg);
    const t = $('toast');
    if (!t) return;
    t.append(' ', el('button', { type: 'button', class: 'mat-tact', onclick: () => { t.hidden = true; fn(); } }, label));
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
  // materials browser (Materials tab): suppliers -> projects -> material types -> products.
  // Each type implies the list line (slot) its products fill; choosing still goes through choose().

  /** append children, skipping null / false (Element.append would print them as text) */
  const put = (parent, ...kids) => parent.append(...kids.flat().filter((k) => k != null && k !== false && k !== ''));
  const nav = { level: 1, supplier: null, project: null, type: null, search: null, q: '', find: '', sort: 'recommended', limit: PAGE,
    filters: defaultFilters(), memo: new Map(), scroll: [0, 0, 0, 0, 0], opened: [], expanded: null };
  try { const s = JSON.parse(localStorage.getItem('rls.mat') || '{}'); if (SORTS.some(([id]) => id === s.sort)) nav.sort = s.sort; } catch (_) { /* storage blocked */ }
  let sheetReturn = null;
  let searchTimer = 0;
  const pane = () => document.querySelector('.tabpanes');
  const supplierName = (id) => SUPPLIERS.find((s) => s.id === id)?.name || '';
  const searching = () => nav.search != null;
  const listSupplier = () => (searching() ? 'all' : nav.supplier);
  const scopeKey = () => `${nav.supplier}|${nav.project}|${nav.type}|${nav.search}`;
  const curType = () => (nav.type && !searching() && nav.supplier !== 'studio' ? findType(nav.type)?.type || null : null);
  const allProducts = () => catalog?.products || [];

  const svg = (d, cls = 'mat-ic') => { const s = el('span', { class: cls, 'aria-hidden': 'true' }); s.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`; return s; };
  const ICONS = {
    roof: '<path d="M2.5 13 12 5l9.5 8"/><path d="M5 11v8h14v-8"/><path d="M10 19v-4h4v4"/>',
    ridge: '<path d="M3 16 12 8l9 8"/><path d="M8 12.2 12 9l4 3.2"/><path d="M3 16h18"/>',
    roll: '<rect x="3" y="7" width="10" height="10" rx="5"/><path d="M8 7h10a3 3 0 0 1 0 6h-5"/><circle cx="8" cy="12" r="1.6"/>',
    gutter: '<path d="M3 7h18"/><path d="M4 7v4a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V7"/><path d="M15 14v6"/>',
    all: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    back: '<path d="M15 5 8 12l7 7"/>',
    chev: '<path d="m9 5 7 7-7 7"/>',
    filter: '<path d="M4 6h16"/><path d="M7 12h10"/><path d="M10 18h4"/>',
    sort: '<path d="M7 4v16"/><path d="m3.5 16.5 3.5 3.5 3.5-3.5"/><path d="M17 20V4"/><path d="m13.5 7.5 3.5-3.5 3.5 3.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
  };
  const shortSort = { recommended: 'Recommended', priceAsc: 'Price ↑', priceDesc: 'Price ↓', unitAsc: 'Unit price ↑', name: 'Name', brand: 'Brand', stock: 'In stock' };

  function sortCtx() {
    const chosen = new Set(), suggested = new Set();
    for (const per of Object.values(job()?.selections || {})) for (const c of Object.values(per || {})) if (c?.productId) (c.source === 'suggested' ? suggested : chosen).add(c.productId);
    return { chosen, suggested, name: short, inStock };
  }
  const scope = () => productsFor(allProducts(), { supplier: listSupplier(), project: searching() ? null : nav.project, type: searching() ? null : nav.type });
  const listItems = () => sortProducts(applyFilters(scope(), nav.filters, nav.q, { inStock }), nav.sort, sortCtx());

  /** Move to another level. Forward moves focus to the new title; back returns focus to the card that was opened. */
  function go(patch, { back = false } = {}) {
    const p = pane();
    nav.scroll[nav.level] = p?.scrollTop || 0;
    if (nav.level === 4) nav.memo.set(scopeKey(), { q: nav.q, filters: nav.filters });
    Object.assign(nav, patch);
    if (nav.level === 1) nav.search = null;
    if (nav.level === 4) {
      const m = nav.memo.get(scopeKey());
      nav.q = m ? m.q : searching() ? nav.search : '';
      nav.filters = m ? m.filters : defaultFilters();
      nav.limit = PAGE; nav.expanded = null;
    }
    renderNav();
    if (p) p.scrollTop = back ? nav.scroll[nav.level] : 0;
    const opener = back && nav.opened[nav.level] && $('matBody').querySelector(`[data-key="${CSS.escape(nav.opened[nav.level])}"]`);
    (opener || $('matTitle'))?.focus({ preventScroll: true });
  }

  function forward(key, patch) { nav.opened[nav.level] = key; go(patch); }

  function back() {
    if (nav.level === 1) return;
    let level = nav.level - 1;
    if (searching() || (nav.supplier === 'studio' && level === 2)) level = 1;
    go({ level }, { back: true });
  }

  function buildPicker() {
    const root = $('storePicker');
    if (!root) return;
    root.innerHTML = '';
    root.classList.add('mat');
    const roof = roofChip();
    root.append(
      el('div', { class: 'mat-head', id: 'matHead' },
        el('button', { type: 'button', class: 'mat-back', id: 'matBack', onclick: back }, svg(ICONS.back)),
        el('div', { class: 'mat-titles' }, el('h3', { id: 'matTitle', class: 'mat-title', tabindex: '-1' }), el('nav', { class: 'mat-crumbs', id: 'matCrumbs', 'aria-label': 'Breadcrumb' })),
        roof,
        el('div', { class: 'mat-hbar', id: 'matHeadBar' })),
      el('section', { id: 'matBody', class: 'mat-body', 'aria-labelledby': 'matTitle' }));
    if (!catalog) roof.hidden = true;
    root.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' || (e.altKey && e.key === 'ArrowLeft')) {
        const t = e.target;
        if (e.key === 'Escape' && t.matches?.('input[type="search"]') && t.value) { t.value = ''; t.dispatchEvent(new Event('input')); return; }
        if (nav.level > 1) { e.preventDefault(); back(); }
      }
    });
    renderNav();
  }

  function roofChip() {
    const btn = el('button', { type: 'button', class: 'mat-pill mat-roofb', id: 'matRoof', 'aria-haspopup': 'true', 'aria-expanded': 'false', title: 'Store whose products are drawn on the roof' });
    const menu = el('div', { class: 'mat-menu', role: 'menu', hidden: true },
      STORE_IDS.map((s) => el('button', { type: 'button', role: 'menuitemradio', class: 'mat-mi', 'data-v': s, onclick: () => { close(); showStore(s); } }, storeName(s))));
    const wrap = el('div', { class: 'mat-roof' }, btn, menu);
    const close = () => { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
    btn.onclick = () => { const open = menu.hidden; menu.hidden = !open; btn.setAttribute('aria-expanded', String(open)); if (open) menu.querySelector('[aria-checked="true"]')?.focus(); };
    document.addEventListener('click', (e) => { if (!wrap.contains(e.target)) close(); });
    wrap.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !menu.hidden) { e.stopPropagation(); close(); btn.focus(); } });
    wrap.sync = () => {
      const s = job()?.shownStore;
      btn.textContent = '';
      btn.append(el('span', { class: 'mat-dim' }, 'On roof: '), storeName(s), svg('<path d="m6 9 6 6 6-6"/>', 'mat-ic sm'));
      menu.querySelectorAll('.mat-mi').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.v === s)));
    };
    roofSwitches.push(wrap);
    wrap.sync();
    return wrap;
  }

  function titleText() {
    if (nav.level === 1) return 'Select a supplier';
    if (nav.level === 2) return supplierName(nav.supplier);
    if (nav.supplier === 'studio') return nav.level === 3 ? 'Studio samples' : STUDIO_TYPES.find((t) => t.id === nav.type)?.label || 'Studio samples';
    if (nav.level === 3) return findProject(nav.project)?.label || '';
    if (searching()) return `Results for “${nav.search}”`;
    return curType()?.label || findProject(nav.project)?.allLabel || '';
  }

  function crumbList() {
    const c = [['Suppliers', 1]];
    if (nav.level === 1) return c;
    if (searching()) return [...c, ['Search', null]];
    if (nav.supplier === 'studio') { c.push(['Studio samples', 3]); if (nav.level === 4) c.push([titleText(), 4]); return c; }
    c.push([supplierName(nav.supplier), 2]);
    if (nav.level >= 3) c.push([findProject(nav.project)?.label, 3]);
    if (nav.level === 4) c.push([titleText(), 4]);
    return c;
  }

  function renderMatHead() {
    $('matTitle').textContent = titleText();
    $('matBack').hidden = nav.level === 1;
    const up = crumbList()[crumbList().length - 2];
    $('matBack').setAttribute('aria-label', `Back to ${up ? up[0] : 'Suppliers'}`);
    const nv = $('matCrumbs');
    nv.innerHTML = '';
    nv.hidden = nav.level === 1;
    // the path above this page (the title names the page itself)
    const ol = el('ol');
    for (const [label, level] of crumbList().slice(0, -1)) {
      ol.append(el('li', {}, level == null ? el('span', {}, label)
        : el('button', { type: 'button', class: 'mat-crumb', onclick: () => go({ level }, { back: true }) }, label)));
    }
    nv.append(ol);
  }

  function renderNav() {
    const body = $('matBody');
    if (!body) return;
    renderMatHead();
    body.innerHTML = '';
    body.className = `mat-body l${nav.level}`;
    $('matHeadBar').innerHTML = '';
    const studioList = nav.supplier === 'studio' && nav.level === 4;
    if ($('builtinSec')) $('builtinSec').hidden = !studioList;
    if (nav.level === 1) renderSuppliers(body);
    else if (nav.level === 2) renderProjects(body);
    else if (nav.level === 3) renderTypes(body);
    else if (nav.supplier === 'studio') renderStudioList(body);
    else renderProducts(body);
  }

  // ---- level 1: suppliers ----------------------------------------------------

  function searchBox(id, value, placeholder, oninput) {
    return el('div', { class: 'mat-searchwrap' }, svg(ICONS.search),
      el('input', { id, type: 'search', class: 'mat-search', placeholder, 'aria-label': placeholder, value, autocomplete: 'off', oninput }));
  }

  function renderSuppliers(body) {
    put(body, 
      searchBox('matFind', nav.find, 'Search suppliers or products', (e) => { nav.find = e.target.value; renderSupplierGrid(); }),
      el('ul', { id: 'matGrid', class: 'mat-grid', role: 'list' }),
      el('div', { id: 'matFindAll' }),
      catalog ? null : el('p', { class: 'hint' }, 'The store catalog did not load, so only the studio samples and your photos are offered.'),
      el('div', { class: 'mat-add' },
        el('p', { class: 'mat-addt' }, svg(ICONS.plus), 'Add your own product or photo'),
        el('div', { class: 'row' },
          el('button', { type: 'button', class: 'btn', id: 'matImport', onclick: () => $('btnImport')?.click() }, 'Add supplier product'),
          el('button', { type: 'button', class: 'btn', id: 'matUpload', onclick: () => $('fileSwatch')?.click() }, 'Upload photo')),
        el('p', { class: 'hint' }, 'Or drop a swatch photo anywhere on the 3D view to try it on the roof.')));
    renderSupplierGrid();
  }

  function supplierSub(s) {
    if (s.id === 'studio') return `${ctx.builtinCount?.('all') ?? ''} looks`;
    const n = productsFor(allProducts(), { supplier: s.id }).length;
    return `${s.sub} · ${n} products`;
  }

  function renderSupplierGrid() {
    const grid = $('matGrid');
    if (!grid) return;
    const q = nav.find.trim().toLowerCase();
    grid.innerHTML = '';
    for (const s of SUPPLIERS) {
      if (!catalog && s.id !== 'studio') continue;
      if (q && !`${s.name} ${s.sub}`.toLowerCase().includes(q)) continue;
      const mono = s.mono ? el('span', { class: 'mat-mono', style: `background:${s.tone}` }, s.mono) : el('span', { class: `mat-mono g-${s.glyph}` }, svg(ICONS[s.glyph]));
      grid.append(el('li', {}, el('button', { type: 'button', class: `mat-card sup${nav.supplier === s.id ? ' cur' : ''}`, 'data-key': s.id,
        onclick: () => forward(s.id, s.id === 'studio' ? { level: 3, supplier: 'studio', project: null, type: null } : { level: 2, supplier: s.id, project: null, type: null }) },
      mono, el('span', { class: 'mat-ct' }, el('b', {}, s.name), el('small', {}, supplierSub(s))))));
    }
    const all = $('matFindAll');
    all.innerHTML = '';
    if (catalog && q.length >= 2) {
      const n = applyFilters(allProducts(), defaultFilters(), q).length;
      all.append(el('button', { type: 'button', class: 'mat-findall', 'data-key': 'search', disabled: n === 0,
        onclick: () => forward('search', { level: 4, supplier: 'all', project: null, type: null, search: nav.find.trim() }) },
      svg(ICONS.search), el('span', {}, `Search all products for “${nav.find.trim()}”`), el('small', {}, n ? `${n} match${n === 1 ? '' : 'es'}` : 'no matches')));
    }
    if (!grid.children.length && !all.children.length) grid.append(el('li', { class: 'hint' }, 'No supplier matches.'));
  }

  // ---- level 2: projects -----------------------------------------------------

  function renderProjects(body) {
    const counts = countsFor(allProducts(), nav.supplier);
    const grid = el('ul', { class: 'mat-grid', role: 'list' });
    const order = [...PROJECTS].sort((a, b) => (counts[b.id].total > 0) - (counts[a.id].total > 0));
    for (const pr of order) {
      const n = counts[pr.id].total;
      grid.append(el('li', {}, el('button', { type: 'button', class: `mat-card proj${n ? '' : ' empty'}`, 'data-key': pr.id, 'aria-disabled': n ? null : 'true',
        'aria-label': n ? null : `${pr.label}, not captured yet`,
        onclick: () => (n ? forward(pr.id, { level: 3, project: pr.id, type: null }) : ctx.toast(`No ${pr.label.toLowerCase()} products captured from ${supplierName(nav.supplier)} yet.`)) },
      el('span', { class: 'mat-mono pic' }, svg(ICONS[pr.icon])), el('span', { class: 'mat-ct' }, el('b', {}, pr.label), el('small', {}, n ? `${n} products` : 'Not captured yet')))));
    }
    put(body, el('p', { class: 'mat-lead' }, 'What are you working on?'), grid);
  }

  // ---- level 3: material types -----------------------------------------------

  function mosaic(products) {
    const m = el('span', { class: 'mat-mosaic', 'aria-hidden': 'true' });
    if (!products.length) { m.classList.add('empty'); return m; }
    for (const p of products.slice(0, 4)) {
      const e = colorEntry(p, defaultColor(p));
      const t = el('span', { class: e.hex ? '' : 'none' });
      if (e.hex) t.style.background = chipBackground(e);
      m.append(t);
    }
    return m;
  }

  function typeRow({ key, label, blurb, count, priced, mos, empty, onclick }) {
    return el('li', {}, el('button', { type: 'button', class: `mat-type${empty ? ' empty' : ''}`, 'data-key': key, 'aria-disabled': empty ? 'true' : null,
      'aria-label': empty ? `${label}, not captured yet` : null, onclick },
    mos, el('span', { class: 'mat-tt' }, el('b', {}, label), el('small', {}, empty ? 'Not captured yet' : blurb)),
    empty ? null : el('span', { class: 'mat-tn' }, String(count), priced != null && priced < count ? el('small', {}, `${priced} priced`) : null),
    empty ? null : svg(ICONS.chev, 'mat-ic chev')));
  }

  function renderTypes(body) {
    const ul = el('ul', { class: 'mat-types', role: 'list' });
    if (nav.supplier === 'studio') {
      for (const t of STUDIO_TYPES) {
        const n = ctx.builtinCount?.(t.id) ?? 0;
        const mos = el('span', { class: 'mat-mosaic img', 'aria-hidden': 'true' }, (ctx.builtinThumbs?.(t.id) || []).slice(0, 4).map((src) => el('img', { src, alt: '' })));
        if (!n) mos.classList.add('empty');
        ul.append(typeRow({ key: t.id, label: t.label, blurb: t.blurb, count: n, mos, empty: !n && !t.always,
          onclick: () => (n || t.always ? forward(t.id, { level: 4, type: t.id }) : ctx.toast(`No ${t.label.toLowerCase()} yet.`)) }));
      }
      put(body, ul);
      return;
    }
    const pr = findProject(nav.project);
    const counts = countsFor(allProducts(), nav.supplier)[pr.id];
    const populated = pr.types.filter((t) => counts.types[t.id]?.total > 0);
    if (populated.length > 1) {
      ul.append(typeRow({ key: '*', label: pr.allLabel, blurb: `Everything in ${pr.label.toLowerCase()} from ${supplierName(nav.supplier)}`, count: counts.total, priced: counts.priced,
        mos: mosaic(populated.map((t) => productsFor(allProducts(), { supplier: nav.supplier, type: t.id })[0]).filter(Boolean)), onclick: () => forward('*', { level: 4, type: null }) }));
    }
    const order = [...pr.types].sort((a, b) => (counts.types[b.id]?.total > 0) - (counts.types[a.id]?.total > 0));
    for (const t of order) {
      const c = counts.types[t.id] || { total: 0, priced: 0 };
      ul.append(typeRow({ key: t.id, label: t.label, blurb: t.blurb, count: c.total, priced: c.priced, empty: !c.total,
        mos: mosaic(productsFor(allProducts(), { supplier: nav.supplier, type: t.id })),
        onclick: () => (c.total ? forward(t.id, { level: 4, type: t.id }) : ctx.toast(`No ${t.label.toLowerCase()} captured from ${supplierName(nav.supplier)} yet.`)) }));
    }
    put(body, ul);
  }

  // ---- level 4: products -----------------------------------------------------

  function renderStudioList(body) {
    const s = $('search');
    if (s) s.value = nav.q;
    ctx.setCatalogFilter?.(nav.type);
    put($('matHeadBar'), el('div', { class: 'mat-bar' }, searchBox('matSearch', nav.q, `Search ${titleText().toLowerCase()}`, (e) => {
      nav.q = e.target.value;
      if (s) { s.value = nav.q; s.dispatchEvent(new Event('input')); }
    })));
  }

  function renderProducts(body) {
    const t = curType();
    const pr = findProject(nav.project);
    const what = searching() ? 'all products' : (t?.label || pr?.allLabel || 'products').toLowerCase();
    put($('matHeadBar'), 
      el('div', { class: 'mat-bar' },
        searchBox('matSearch', nav.q, `Search ${what}`, (e) => {
          nav.q = e.target.value; nav.limit = PAGE;
          clearTimeout(searchTimer); searchTimer = setTimeout(renderResults, 120);
        }),
        el('div', { class: 'mat-ctl' },
          el('button', { type: 'button', class: 'mat-pill', id: 'matFilters', onclick: openFilters }, svg(ICONS.filter, 'mat-ic sm'), 'Filters', el('span', { class: 'mat-badge', id: 'matBadge', hidden: true })),
          el('button', { type: 'button', class: 'mat-pill', id: 'matSort', onclick: openSort }, svg(ICONS.sort, 'mat-ic sm'), el('span', { id: 'matSortL' })),
          el('span', { class: 'mat-count', id: 'matCount', 'aria-live': 'polite' }))),
      el('div', { class: 'mat-chips', id: 'matChips' }));
    put(body, 
      t ? el('p', { class: 'hint mat-fills' }, t.slot ? `Fills the ${LINE_LABELS[t.slot]} line of your list.` : 'Listed for reference: your materials list has no line for these yet.', t.note && !/Fills/.test(t.note) ? ` ${t.note}` : '') : null,
      el('div', { id: 'sfChosen', class: 'sf-chosen', 'aria-live': 'polite' }),
      el('div', { id: 'sfResults', class: 'sf-results', role: 'list' }),
      el('button', { type: 'button', class: 'btn', id: 'sfMore', hidden: true, onclick: () => { nav.limit += PAGE; renderResults(); } }, `Show ${PAGE} more`),
      t?.goesWith ? el('div', { class: 'mat-goes' }, el('span', { class: 'sf-k' }, 'Goes with'),
        t.goesWith.map((id) => { const g = findType(id); return el('button', { type: 'button', class: 'mat-pill', onclick: () => go({ level: 4, project: g.project.id, type: id }) }, g.type.label); })) : null);
    renderResults();
  }

  function renderPicker() {
    if (nav.level === 4 && nav.supplier !== 'studio' && $('sfResults')) renderResults();
  }

  function nokeyLabel() {
    if (/^price/.test(nav.sort)) return 'No price: ask the store';
    if (nav.sort === 'unitAsc') return 'No price or coverage not stated';
    if (nav.sort === 'stock') return 'Stock not known';
    return '';
  }

  function renderResults() {
    const box = $('sfResults');
    if (!box || !job()) return;
    const p = pane();
    const top = p?.scrollTop;
    renderChosen();
    renderBar();
    const total = scope().length;
    const items = listItems();
    const counts = new Map();
    for (const x of items) counts.set(short(x), (counts.get(short(x)) || 0) + 1);
    box.innerHTML = '';
    for (const x of items.slice(0, nav.limit)) {
      if (x._nokey && nokeyLabel()) box.append(el('p', { class: 'mat-divider' }, nokeyLabel()));
      box.append(productRow(x, counts.get(short(x)) > 1));
    }
    if (!items.length) box.append(el('div', { class: 'mat-empty' }, el('p', { class: 'hint' }, 'No products match.'), el('button', { type: 'button', class: 'btn', onclick: clearAll }, 'Clear search and filters')));
    $('sfMore').hidden = items.length <= nav.limit;
    $('matCount').textContent = searching() ? `${items.length} result${items.length === 1 ? '' : 's'}` : items.length === total ? `${total} item${total === 1 ? '' : 's'}` : `${items.length} of ${total}`;
    if (p && top != null) p.scrollTop = top;
  }

  function clearAll() {
    nav.q = ''; nav.filters = defaultFilters(); nav.limit = PAGE;
    if ($('matSearch')) $('matSearch').value = '';
    renderResults();
  }

  /** Filter and Sort buttons, the badge and the removable chips of active filters. */
  function renderBar() {
    const n = activeCount(nav.filters);
    const badge = $('matBadge');
    if (badge) { badge.hidden = !n; badge.textContent = String(n); }
    $('matFilters')?.setAttribute('aria-label', n ? `Filters, ${n} active` : 'Filters');
    if ($('matSortL')) $('matSortL').textContent = nav.sort === 'recommended' ? 'Sort' : `Sort: ${shortSort[nav.sort]}`;
    $('matSort')?.setAttribute('aria-label', `Sort, ${sortOptions().find(([id]) => id === nav.sort)?.[1] || 'Recommended'}`);
    const box = $('matChips');
    if (!box) return;
    box.innerHTML = '';
    const f = nav.filters;
    const labels = new Map();
    for (const fc of facets(scope(), f, nav.q, { inStock, supplier: listSupplier(), typeFixed: !!curType() })) for (const o of fc.options) labels.set(`${fc.id}:${o.value}`, o.label);
    const chips = [];
    const add = (text, off) => chips.push(el('button', { type: 'button', class: 'mat-chip', 'aria-label': `Remove filter ${text}`, onclick: () => { off(); nav.limit = PAGE; renderResults(); } }, text, el('span', { 'aria-hidden': 'true' }, '×')));
    if (f.priced) add('Priced only', () => { f.priced = false; });
    if (f.inStock) add('In stock', () => { f.inStock = false; });
    if (f.store !== 'both') add(storeName(f.store), () => { f.store = 'both'; });
    for (const k of ['types', 'kinds', 'brands', 'colours', 'lengths', 'gauges']) for (const v of f[k]) add(labels.get(`${k}:${v}`) || String(v), () => { f[k] = f[k].filter((x) => x !== v); });
    if (f.priceMin != null || f.priceMax != null) add(`${f.priceMin != null ? fmtMoney(f.priceMin) : '$0'}–${f.priceMax != null ? fmtMoney(f.priceMax) : 'any'}`, () => { f.priceMin = null; f.priceMax = null; });
    if (chips.length > 1) chips.push(el('button', { type: 'button', class: 'mat-chip clear', onclick: () => { nav.filters = defaultFilters(); renderResults(); } }, 'Clear all'));
    box.append(...chips);
    box.hidden = !chips.length;
  }

  /** "On your list" strip: what is chosen for this type's line, per store. */
  function renderChosen() {
    const box = $('sfChosen');
    if (!box) return;
    box.innerHTML = '';
    const t = curType();
    if (!t?.slot) { box.hidden = true; return; }
    box.hidden = false;
    box.append(el('p', { class: 'sf-k' }, `On your list: ${LINE_LABELS[t.slot]}`));
    for (const s of nav.supplier === 'all' ? STORE_IDS : [nav.supplier]) {
      const c = job().selections[t.slot]?.[s];
      const sp = c && findProduct(catalog, c.productId);
      const other = sp && typeOf(sp).type.id !== t.id ? typeOf(sp) : null;
      box.append(el('button', { type: 'button', class: 'sf-cho', title: sp ? 'Show it in the list' : 'Pick one below',
        onclick: () => { if (other) go({ level: 4, project: other.project.id, type: other.type.id }); revealRow(s); } },
      sp ? chip(colorEntry(sp, c.color), { sampled: SAMPLED.has(t.slot) }) : el('span', { class: 'sf-chip kind', 'aria-hidden': 'true' }),
      el('span', { class: 'sf-cn' }, storeTag(s), ' ', el('b', {}, sp ? `${short(sp)}${c.color ? `, ${c.color}` : ''}` : 'not chosen'),
        other ? ` (in ${other.type.label})` : null, sp && c.source === 'suggested' ? [' ', tag('suggested')] : null)));
    }
  }

  function dots(sp, colors) {
    const wrap = el('span', { class: 'mat-dots', title: `${colors.length} colours` });
    for (const x of colors.slice(0, 5)) {
      const e = colorEntry(sp, x.name);
      const d = el('span', { class: e.hex ? '' : 'none' });
      if (e.hex) d.style.background = e.hex;
      wrap.append(d);
    }
    if (colors.length > 5) wrap.append(el('small', {}, `+${colors.length - 5}`));
    return wrap;
  }

  function productRow(sp, showFull) {
    const slot = slotOf(sp);
    const c = slot ? job().selections[slot]?.[sp.store] : null;
    const chosen = c?.productId === sp.id;
    let color = chosen ? c.color : defaultColor(sp);
    if (!chosen && nav.filters.colours.length) {
      const m = (sp.colors || []).find((x) => x.name != null && nav.filters.colours.includes(colourFamily(x)));
      if (m) color = m.name;
    }
    const entry = colorEntry(sp, color);
    const sampled = SAMPLED.has(sp.layer);
    const ref = !slot;
    const open = chosen || nav.expanded === sp.id;
    const colors = (sp.colors || []).filter((x) => x.name != null);
    const u = crewLocked ? null : unitPrice(sp);
    const price = priceText(sp);
    const tile = chip(entry, { sampled });
    tile.classList.add('mat-tile');
    const facts = [sp.brand, coverageText(sp), stockText(sp), sampled && !entry.hex ? 'color not sampled' : null].filter(Boolean);
    const wrap = el('div', { class: `sf-item${chosen ? ' on' : ''}`, role: 'listitem', 'data-id': sp.id });
    wrap.append(el('button', { type: 'button', class: 'sf-row mat-row', 'aria-pressed': ref ? null : String(chosen), 'aria-expanded': String(open), title: cleanName(sp.name),
      onclick: () => tapProduct(sp, slot, color) },
    tile,
    el('span', { class: 'sf-rt' },
      el('span', { class: 'mat-r1' }, el('span', { class: 'sf-l1' }, el('b', {}, short(sp)), color ? `, ${color}` : ''),
        price ? el('span', { class: `mat-price${sp.price?.shelf == null ? ' none' : ''}` }, price) : null),
      el('span', { class: 'mat-r2' }, el('span', { class: 'sf-l2' }, listSupplier() === 'all' ? [storeTag(sp.store), ' '] : null, facts.join(' · ')),
        u ? el('span', { class: 'mat-unit' }, `${fmtMoney(u.value)} / ${u.unit}${u.gross ? ' gross' : ''}`) : null),
      colors.length > 1 || chosen || ref ? el('span', { class: 'mat-r3' }, colors.length > 1 ? dots(sp, colors) : null,
        chosen ? tag(c.source === 'suggested' ? 'suggested' : 'chosen') : null, ref ? tag('reference only', 'ref') : null) : null,
      showFull ? el('span', { class: 'sf-l3' }, cleanName(sp.name)) : null)));
    if (open) wrap.append(chosen ? chosenDetail(sp, c, slot) : refDetail(sp));
    return wrap;
  }

  async function tapProduct(sp, slot, color) {
    if (!slot) nav.expanded = nav.expanded === sp.id ? null : sp.id;
    if (!slot) renderResults();
    else await choose(slot, sp, color);
    $('sfResults')?.querySelector(`[data-id="${CSS.escape(sp.id)}"] .sf-row`)?.focus({ preventScroll: true });
  }

  function refDetail(sp) {
    return el('div', { class: 'sf-detail' },
      el('p', { class: 'sf-approx' }, 'Listed for reference: the materials list has no line for it, so it cannot be chosen.'),
      el('p', { class: 'sf-l3' }, cleanName(sp.name), sp.url ? ' · ' : '', sp.url ? el('a', { href: sp.url, target: '_blank', rel: 'noopener noreferrer' }, 'Store page') : null));
  }

  /** Scroll to the chosen row of a store for the current type, clearing search and filters that hide it. */
  function revealRow(store) {
    const t = curType();
    const c = t?.slot && job().selections[t.slot]?.[store];
    if (!c) return;
    let items = listItems();
    if (!items.some((p) => p.id === c.productId)) { clearAll(); items = listItems(); }
    const i = items.findIndex((p) => p.id === c.productId);
    if (i < 0) return;
    if (i >= nav.limit) { nav.limit = Math.ceil((i + 1) / PAGE) * PAGE; renderResults(); }
    const row = $('sfResults').querySelector(`[data-id="${CSS.escape(c.productId)}"]`);
    row?.scrollIntoView({ block: 'center' });
    row?.querySelector('button')?.focus({ preventScroll: true });
  }

  /** From the List tab, the Layers tab or a roof tap: open the type of the product chosen for this line and store. */
  function jumpToPicker(slot, store) {
    ctx.selectTab('materials');
    const c = job().selections[slot]?.[store];
    const sp = c && findProduct(catalog, c.productId);
    const t = sp ? typeOf(sp) : findType(DEFAULT_TYPE_FOR_SLOT[slot]);
    if (!t) return;
    nav.opened[1] = store; nav.opened[2] = t.project.id; nav.opened[3] = t.type.id;
    go({ level: 4, supplier: store, project: t.project.id, type: t.type.id, search: null });
    clearAll();
    revealRow(store);
  }

  // ---- filters and sort sheets -----------------------------------------------

  function sheet() {
    let d = $('matSheet');
    if (!d) {
      d = el('dialog', { id: 'matSheet', class: 'sf mat-sheet', 'aria-labelledby': 'matSheetT' });
      d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
      d.addEventListener('close', () => { sheetReturn?.focus({ preventScroll: true }); });
      document.body.append(d);
    }
    d.classList.remove('sort');
    return d;
  }

  const sheetHead = (title, d) => el('div', { class: 'mat-shead' }, el('h3', { id: 'matSheetT' }, title),
    el('button', { type: 'button', class: 'mat-x', 'aria-label': 'Close', onclick: () => d.close() }, '✕'));
  const group = (label, ...kids) => el('fieldset', { class: 'mat-group' }, el('legend', {}, label), ...kids);

  function openFilters() {
    const d = sheet();
    sheetReturn = $('matFilters');
    const draft = JSON.parse(JSON.stringify(nav.filters));
    const sc = scope();
    const hasHD = sc.some((p) => p.store === HD);
    const priced = sc.some((p) => p.price?.shelf != null);
    const render = () => {
      const focusKey = document.activeElement?.dataset?.fk;
      d.innerHTML = '';
      const n = applyFilters(sc, draft, nav.q, { inStock }).length;
      const fs = facets(sc, draft, nav.q, { inStock, supplier: listSupplier(), typeFixed: !!curType() });
      const body = el('div', { class: 'mat-sbody' });
      const sw = (key, label) => el('label', { class: 'mat-switch' }, el('input', { type: 'checkbox', 'data-fk': key, checked: draft[key], onchange: (e) => { draft[key] = e.target.checked; render(); } }), el('span', {}, label));
      put(body, group('Availability', sw('priced', 'Priced only'), hasHD && !crewLocked ? sw('inStock', 'In stock at Home Depot') : null));
      for (const f of fs) {
        const opts = el('div', { class: `mat-opts${f.id === 'colours' ? ' col' : ''}`, role: 'group', 'aria-label': f.label });
        for (const o of f.options) {
          const on = f.id === 'store' ? draft.store === o.value : draft[f.id].includes(o.value);
          opts.append(el('button', { type: 'button', class: `mat-opt${!o.count && !on ? ' zero' : ''}`, 'aria-pressed': String(on), 'data-fk': `${f.id}:${o.value}`,
            onclick: () => {
              if (f.id === 'store') draft.store = on ? 'both' : o.value;
              else draft[f.id] = on ? draft[f.id].filter((v) => v !== o.value) : [...draft[f.id], o.value];
              render();
            } },
          o.hex ? el('span', { class: 'mat-sw', style: `background:${o.hex}` }) : null, o.label, el('small', {}, String(o.count))));
        }
        put(body, group(f.label, opts));
      }
      if (priced && !crewLocked) {
        const num = (key, label) => el('label', { class: 'mat-num' }, label, el('input', { type: 'number', min: '0', step: '1', inputmode: 'decimal', 'data-fk': key, value: draft[key] ?? '', placeholder: key === 'priceMin' ? '0' : 'any',
          onchange: (e) => { draft[key] = e.target.value === '' ? null : Math.max(0, Number(e.target.value)); render(); } }));
        put(body, group('Price per item', el('div', { class: 'mat-nums' }, num('priceMin', 'Min $'), num('priceMax', 'Max $'))));
      }
      d.append(sheetHead('Filters', d), body,
        el('div', { class: 'mat-sfoot' },
          el('button', { type: 'button', class: 'btn', id: 'matReset', onclick: () => { Object.assign(draft, defaultFilters()); render(); } }, 'Reset'),
          el('button', { type: 'button', class: 'btn primary', id: 'matApply', disabled: n === 0,
            onclick: () => { nav.filters = draft; nav.limit = PAGE; d.close(); renderResults(); } }, n ? `Show ${n} product${n === 1 ? '' : 's'}` : 'No matches')));
      (focusKey && d.querySelector(`[data-fk="${CSS.escape(focusKey)}"]`))?.focus({ preventScroll: true });
    };
    render();
    if (!d.open) d.showModal();
    d.querySelector('.mat-sbody input, .mat-sbody button')?.focus({ preventScroll: true });
  }

  function sortOptions() {
    const t = curType();
    const hasHD = scope().some((p) => p.store === HD);
    return SORTS.filter(([id]) => !(crewLocked && /price|unit/i.test(id)) && !(id === 'stock' && (!hasHD || crewLocked)))
      .map(([id, label]) => [id, id === 'unitAsc' && t?.linear ? 'Price per foot: low to high' : label]);
  }

  function openSort() {
    const d = sheet();
    d.classList.add('sort');
    sheetReturn = $('matSort');
    d.innerHTML = '';
    const radios = sortOptions().map(([id, label]) => el('button', { type: 'button', role: 'radio', class: 'mat-radio', 'aria-checked': String(nav.sort === id), tabindex: nav.sort === id ? '0' : '-1',
      onclick: () => { nav.sort = id; try { localStorage.setItem('rls.mat', JSON.stringify({ sort: id })); } catch (_) { /* storage blocked */ } d.close(); renderResults(); } }, label));
    const rg = el('div', { class: 'mat-sbody', role: 'radiogroup', 'aria-labelledby': 'matSheetT' }, radios,
      el('p', { class: 'hint' }, 'Unit price uses the coverage the store states; "gross" is coverage before overlap. Items without the value go last.'));
    rg.addEventListener('keydown', (e) => {
      const i = radios.indexOf(document.activeElement);
      if (i < 0 || !['ArrowDown', 'ArrowUp'].includes(e.key)) return;
      e.preventDefault();
      radios[(i + (e.key === 'ArrowDown' ? 1 : radios.length - 1)) % radios.length].focus();
    });
    d.append(sheetHead('Sort by', d), rg);
    d.showModal();
    (radios.find((r) => r.getAttribute('aria-checked') === 'true') || radios[0])?.focus({ preventScroll: true });
  }

  /** Studio samples > a type (after an import or upload: My products). */
  function showStudio(type = 'supplier') {
    nav.opened[1] = 'studio'; nav.opened[3] = type;
    go({ level: 4, supplier: 'studio', project: null, type, search: null });
  }

  /** The List tab's "On the roof" store switch (the Materials tab uses the header chip). */
  function roofSwitch() {
    const w = segmented([[MN, 'Menards'], [HD, 'Home Depot']], () => job()?.shownStore, (v) => showStore(v), 'Store whose products are on the roof');
    w.classList.add('sf-roofsw');
    roofSwitches.push(w);
    return w;
  }

  const inStock = (p) => p.stock?.qty > 0 || (p.stock?.inStock === true && p.stock?.qty == null);

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

  function chosenDetail(sp, c, slot = slotOf(sp)) {
    const d = el('div', { class: 'sf-detail' });
    const colors = (sp.colors || []).filter((x) => x.name != null);
    if (colors.length > 1) {
      const g = el('div', { class: 'sf-colors', role: 'group', 'aria-label': `Colors of ${short(sp)}` });
      for (const x of colors) {
        const e = colorEntry(sp, x.name);
        g.append(el('button', { type: 'button', class: 'sf-color', 'aria-pressed': String(x.name === c.color), title: e.hex ? `${x.name} (${e.hex})` : `${x.name}: color not sampled`, onclick: () => choose(slot, sp, x.name) },
          chip(e, { sampled: SAMPLED.has(slot) }), el('span', {}, x.name)));
      }
      d.append(g);
    }
    const notes = approxNotes(sp, c.color);
    if (notes.length) d.append(el('p', { class: 'sf-approx' }, notes.join(' · ')));
    const pr = sp.price || {};
    if (!crewLocked && pr.afterRebate != null) d.append(el('p', { class: 'sf-approx' }, `${fmtMoney(pr.afterRebate)} after mail-in rebate${pr.rebateThrough ? ` through ${pr.rebateThrough}` : ''} (store credit; the list uses the shelf price).`));
    d.append(el('p', { class: 'sf-l3' }, cleanName(sp.name), sp.url ? ' · ' : '', sp.url ? el('a', { href: sp.url, target: '_blank', rel: 'noopener noreferrer' }, 'Store page') : null));
    return d;
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
    showStudio,
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
      /** Materials browser state for tests: get, or go to { level, supplier, project, type, search }. */
      materialsNav: (patch) => { if (patch) go(patch); return { level: nav.level, supplier: nav.supplier, project: nav.project, type: nav.type, search: nav.search, q: nav.q, sort: nav.sort, filters: JSON.parse(JSON.stringify(nav.filters)) }; },
      listText: (crew) => { ensure(); return listText(currentQuote(), crew); },
    },
  };
}
