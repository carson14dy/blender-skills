// Materials browser data: suppliers -> projects -> material types -> products, plus the filter,
// sort and unit-price rules the list uses. Pure (no DOM), so it can be checked in node.
// Every store product lands in exactly one type through its `kind` (checked by assertPartition).

import { isPerBundle } from './quote.js';

export const PROJECTS = [
  { id: 'roof', label: 'Roof', allLabel: 'All roof coverings', icon: 'roof', blurb: 'Shingles, metal and other coverings', types: [
    { id: 'architectural', label: 'Architectural shingles', kinds: ['architectural'], slot: 'covering', blurb: 'Durable with stylish appeal.', goesWith: ['hipRidge', 'starter'] },
    { id: 'threeTab', label: '3-tab shingles', kinds: ['threeTab'], slot: 'covering', blurb: 'A cost effective roofing option.', goesWith: ['hipRidge', 'starter'] },
    { id: 'ribbed', label: 'Ribbed metal panels', kinds: ['panel', 'proRib'], slot: 'covering', blurb: 'Exposed-fastener steel panels with raised ribs.', goesWith: ['metalCap'] },
    { id: 'corrugated', label: 'Corrugated panels', kinds: ['corrugated'], slot: 'covering', blurb: 'Classic wavy panels for sheds, porches and barns.' },
    { id: 'standingSeam', label: 'Standing seam', kinds: ['standingSeam', 'proSnap'], slot: 'covering', blurb: 'Hidden-fastener panels with clean vertical seams.', goesWith: ['metalCap'] },
    { id: 'stoneCoated', label: 'Stone-coated steel', kinds: ['stoneCoated'], slot: 'covering', blurb: 'Steel with a granule finish that looks like shingle or shake.' },
    { id: 'cedar', label: 'Cedar shakes', kinds: ['cedar', 'undercourse'], slot: 'covering', blurb: 'Natural wood with a rustic look.' },
    { id: 'rollRoofing', label: 'Roll roofing', kinds: [], slot: null, blurb: 'For low-slope sheds and porches.' },
    { id: 'tileSlate', label: 'Tile and slate', kinds: [], slot: null, blurb: 'Long-lived premium coverings.' },
  ] },
  { id: 'accessories', label: 'Roof accessories', allLabel: 'All roof accessories', icon: 'ridge', blurb: 'Ridge, starter, edges, valleys, vents', types: [
    { id: 'hipRidge', label: 'Hip & ridge shingles', kinds: ['shingleCap'], slot: 'ridgeCap', linear: true, blurb: 'For use on the peaks of a roof.' },
    { id: 'metalCap', label: 'Metal ridge cap', kinds: ['metalCap'], slot: 'ridgeCap', linear: true, blurb: 'Caps the ridge of a metal roof.' },
    { id: 'starter', label: 'Starter shingles', kinds: ['starter'], slot: 'starter', linear: true, blurb: 'Creates a base and waterproof seal at roof edges.' },
    { id: 'dripEdge', label: 'Drip edge & rake trim', kinds: ['dripEdge', 'rakeTrim'], slot: 'dripEdge', linear: true, blurb: 'Metal edging that sheds water off the eaves and rakes.' },
    { id: 'valley', label: 'Valley flashing', kinds: ['valley'], slot: 'valley', blurb: 'Lines the valleys where two roof planes meet.' },
    { id: 'ridgeVent', label: 'Ridge vents', kinds: ['ridgeVent', 'closure'], slot: 'ridgeVent', linear: true, blurb: 'Lets attic heat and moisture out at the peak.' },
    { id: 'flashing', label: 'Roof flashing', kinds: [], slot: null, blurb: 'Step flashing, pipe boots and wall flashing.' },
    { id: 'roofVents', label: 'Roof vents', kinds: [], slot: null, blurb: 'Box, turbine and powered attic vents.' },
    { id: 'nails', label: 'Roof nails', kinds: [], slot: null, blurb: 'Coil and hand-drive roofing nails.' },
    { id: 'sealants', label: 'Sealants & coatings', kinds: [], slot: null, blurb: 'Roof cement, sealant and coatings.' },
  ] },
  { id: 'underlayment', label: 'Underlayment', allLabel: 'All underlayment', icon: 'roll', blurb: 'Synthetic, felt, ice & water', types: [
    { id: 'synthetic', label: 'Synthetic underlayment', kinds: ['synthetic'], slot: 'underlayment', blurb: 'Light, tear-resistant sheet under the roofing.' },
    { id: 'felt', label: 'Felt & base sheet', kinds: ['felt', 'baseSheet'], slot: 'underlayment', blurb: 'Traditional asphalt-saturated paper.' },
    { id: 'iceWater', label: 'Ice & water shield', kinds: ['iceWater'], slot: 'iceWater', blurb: 'Self-sealing membrane for eaves and valleys.' },
    { id: 'flashingTape', label: 'Flashing tape', kinds: ['flashingTape'], slot: null, blurb: 'Self-adhesive strips for seams and small repairs.' },
  ] },
  { id: 'gutters', label: 'Gutters', allLabel: 'All gutter products', icon: 'gutter', blurb: 'Gutters, downspouts, guards, apron', types: [
    { id: 'gutterApron', label: 'Gutter apron', kinds: ['gutterApron'], slot: 'dripEdge', linear: true, blurb: 'Edge metal that steers water into the gutter.', note: 'Fills the Drip edge line of your list.' },
    { id: 'gutterSystems', label: 'Gutters & downspouts', kinds: [], slot: null, blurb: 'Collects and carries roof water away.' },
    { id: 'gutterGuards', label: 'Gutter guards', kinds: [], slot: null, blurb: 'Keeps leaves out of the gutter.' },
  ] },
];

/** Kinds listed for reference but not choosable: the quote has no rule for them. */
export const REFERENCE_KINDS = new Set(['flashingTape', 'closure', 'undercourse']);
export const DEFAULT_TYPE_FOR_SLOT = { covering: 'architectural', ridgeCap: 'hipRidge', starter: 'starter', underlayment: 'synthetic', iceWater: 'iceWater', dripEdge: 'dripEdge', ridgeVent: 'ridgeVent', valley: 'valley' };
/** Neutral monograms: not the stores' logos, colours or lettering. */
export const SUPPLIERS = [
  { id: 'menards-3064', name: 'Menards', sub: 'Sioux Falls West', mono: 'M', tone: '#2f6f6a' },
  { id: 'homedepot-4301', name: 'The Home Depot', sub: 'Store #4301', mono: 'HD', tone: '#3b4656' },
  { id: 'all', name: 'All suppliers', sub: 'Compare both stores', glyph: 'all' },
  { id: 'studio', name: 'Studio samples', sub: 'Built-in looks and your photos', glyph: 'roof' },
];
/** Built-in catalog (studio samples): types map onto app.js catalog filters. */
export const STUDIO_TYPES = [
  { id: 'shingle', label: 'Shingles', blurb: 'Architectural and 3-tab looks.' },
  { id: 'metal', label: 'Metal', blurb: 'Standing seam colours.' },
  { id: 'tile', label: 'Tile, slate & shake', blurb: 'Clay tile, natural slate, cedar shake.' },
  { id: 'supplier', label: 'My products', blurb: 'Products you added and photos you uploaded.', always: true },
];
export const KIND_LABELS = { panel: 'Panel', proRib: 'Pro-Rib', standingSeam: 'Standing seam', proSnap: 'Pro-Snap', cedar: 'Shake', undercourse: 'Undercourse',
  dripEdge: 'Drip edge', rakeTrim: 'Rake trim', ridgeVent: 'Ridge vent', closure: 'Closure', felt: 'Felt', baseSheet: 'Base sheet' };

const KIND_TO_TYPE = new Map();
const TYPE_INDEX = new Map();
for (const project of PROJECTS) {
  for (const type of project.types) {
    TYPE_INDEX.set(type.id, { project, type });
    for (const k of type.kinds) {
      if (KIND_TO_TYPE.has(k)) throw new Error(`kind ${k} is in two material types`);
      KIND_TO_TYPE.set(k, { project, type });
    }
  }
}
const OTHER = { project: PROJECTS[1], type: { id: 'other', label: 'Other', kinds: [], slot: null, blurb: 'Products not sorted into a type yet.' } };
const warned = new Set();

/** { project, type } for a store product (unknown kinds land in Roof accessories > Other). */
export function typeOf(p) {
  const t = KIND_TO_TYPE.get(p?.kind);
  if (t) return t;
  if (p && !warned.has(p.kind)) { warned.add(p.kind); console.warn(`materials: no type for kind "${p.kind}"`); }
  return OTHER;
}
export const findType = (id) => TYPE_INDEX.get(id) || null;
export const findProject = (id) => PROJECTS.find((p) => p.id === id) || null;
export const isReference = (p) => REFERENCE_KINDS.has(p.kind);
/** The slot a product fills when chosen (null: reference only). */
export const slotOf = (p) => (isReference(p) ? null : typeOf(p).type.slot || p.layer || null);
export const isStore = (supplier) => supplier === 'menards-3064' || supplier === 'homedepot-4301' || supplier === 'all';

/** Store products for a supplier ('all' = both), optionally one project and one type. */
export function productsFor(products, { supplier = 'all', project = null, type = null } = {}) {
  return (products || []).filter((p) => {
    if (supplier !== 'all' && p.store !== supplier) return false;
    const t = typeOf(p);
    if (project && t.project.id !== project) return false;
    if (type && t.type.id !== type) return false;
    return true;
  });
}

/** Counts per project and type for a supplier: { [project]: { total, priced, types: { [type]: { total, priced } } } }. */
export function countsFor(products, supplier) {
  const out = {};
  for (const pr of PROJECTS) out[pr.id] = { total: 0, priced: 0, types: Object.fromEntries(pr.types.map((t) => [t.id, { total: 0, priced: 0 }])) };
  for (const p of productsFor(products, { supplier })) {
    const t = typeOf(p);
    const pc = out[t.project.id], tc = pc.types[t.type.id] || (pc.types[t.type.id] = { total: 0, priced: 0 });
    pc.total++; tc.total++;
    if (p.price?.shelf != null) { pc.priced++; tc.priced++; }
  }
  return out;
}

/** Price per square (100 sq ft) or per foot from the stated coverage; null when it cannot be worked out. */
export function unitPrice(p) {
  const shelf = p.price?.shelf;
  if (shelf == null) return null;
  if (p.price.per === '100 sq ft') return { value: shelf, unit: 'sq', gross: false };
  if (p.coverage?.sqft > 0) return { value: (shelf / p.coverage.sqft) * 100, unit: 'sq', gross: p.coverage.basis === 'gross' };
  if (p.coverage?.lf > 0) return { value: shelf / p.coverage.lf, unit: 'ft', gross: false };
  if (p.pieceFt > 0) {
    const pack = p.packCount > 1 && !isPerBundle(p) ? p.packCount : 1;
    return { value: shelf / (p.pieceFt * pack), unit: 'ft', gross: false };
  }
  return null;
}

/** Brand key that merges case variants ("Atlas" / "ATLAS"). */
export function brandKey(p) {
  const b = String(p.brand || '').trim();
  return b ? b.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim() : '';
}

export const COLOUR_FAMILIES = [
  ['black', 'Black', '#1f2124'], ['gray', 'Gray', '#7d828a'], ['brown', 'Brown', '#5b4232'], ['tan', 'Tan', '#b59a74'], ['red', 'Red', '#8e2f27'],
  ['green', 'Green', '#3d5a3b'], ['blue', 'Blue', '#2f4f7a'], ['white', 'White', '#eeeeea'], ['metal', 'Bare metal', '#b5b9bd'],
];

function hsl(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (mx === mn) return { h: 0, s: 0, l };
  const d = mx - mn, s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  let h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, s, l };
}

/** Colour family of one colour entry ({ hex, name, material }). */
export function colourFamily(entry) {
  const name = `${entry?.name || ''}`;
  if (/galvan|galvalume|bare|mill finish/i.test(name) || /galv/i.test(entry?.material || '')) return 'metal';
  if (!/^#[0-9a-f]{6}$/i.test(entry?.hex || '')) return null;
  const { h, s, l } = hsl(entry.hex);
  if (l < 0.2) return 'black';
  if (s < 0.12) return l > 0.8 ? 'white' : 'gray';
  if (h >= 345 || h < 20) return 'red';
  if (h < 45) return l < 0.45 ? 'brown' : 'tan';
  if (h < 70) return 'tan';
  if (h < 170) return 'green';
  if (h < 260) return 'blue';
  return 'red';
}
export const coloursOf = (p) => (p.colors?.length ? p.colors : p.hex ? [{ name: p.color, hex: p.hex }] : []);
export const familiesOf = (p) => new Set(coloursOf(p).map(colourFamily).filter(Boolean));

/** Panel length in feet: pieceFt, else the longer side of "W ft x L ft" in the name. */
export function lengthFt(p) {
  if (p.pieceFt > 0) return Math.round(p.pieceFt * 10) / 10;
  const m = /(\d+(?:\.\d+)?)\s*ft\.?\s*x\s*(\d+(?:\.\d+)?)\s*ft/i.exec(String(p.name || ''));
  return m ? Math.max(Number(m[1]), Number(m[2])) : null;
}

/** Steel gauge from the name ("29 GA", "26-Gauge"). */
export function gaugeOf(p) {
  const m = /\b(\d{2})\s*-?\s*(?:gauge|ga)\b/i.exec(String(p.name || ''));
  return m ? Number(m[1]) : null;
}

export const defaultFilters = () => ({ priced: false, inStock: false, store: 'both', types: [], kinds: [], brands: [], colours: [], priceMin: null, priceMax: null, lengths: [], gauges: [] });

/** Number of filters that differ from the defaults (the badge). */
export function activeCount(f) {
  const d = defaultFilters();
  let n = 0;
  if (f.priced !== d.priced) n++;
  if (f.inStock) n++;
  if (f.store !== 'both') n++;
  for (const k of ['types', 'kinds', 'brands', 'colours', 'lengths', 'gauges']) n += f[k].length;
  if (f.priceMin != null || f.priceMax != null) n++;
  return n;
}

const searchHay = (p) => `${p.name} ${p.brand || ''} ${(p.colors || []).map((c) => c.name || '').join(' ')}`.toLowerCase();

/** Apply filters and search. `skip` names one facet to leave out (for that facet's own counts). */
export function applyFilters(products, f, q = '', { inStock = () => true, skip = null } = {}) {
  const words = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
  return products.filter((p) => {
    if (skip !== 'priced' && f.priced && p.price?.shelf == null) return false;
    if (skip !== 'inStock' && f.inStock && p.store === 'homedepot-4301' && !inStock(p)) return false;
    if (skip !== 'store' && f.store !== 'both' && p.store !== f.store) return false;
    if (skip !== 'types' && f.types.length && !f.types.includes(typeOf(p).type.id)) return false;
    if (skip !== 'kinds' && f.kinds.length && !f.kinds.includes(p.kind)) return false;
    if (skip !== 'brands' && f.brands.length && !f.brands.includes(brandKey(p) || '~')) return false;
    if (skip !== 'colours' && f.colours.length) { const fam = familiesOf(p); if (!f.colours.some((c) => fam.has(c))) return false; }
    if (skip !== 'price' && (f.priceMin != null || f.priceMax != null)) {
      const v = p.price?.shelf;
      if (v == null || (f.priceMin != null && v < f.priceMin) || (f.priceMax != null && v > f.priceMax)) return false;
    }
    if (skip !== 'lengths' && f.lengths.length && !f.lengths.includes(lengthFt(p))) return false;
    if (skip !== 'gauges' && f.gauges.length && !f.gauges.includes(gaugeOf(p))) return false;
    if (words.length) { const hay = searchHay(p); if (!words.every((w) => hay.includes(w))) return false; }
    return true;
  });
}

/** Facet options over a scope: [{ id, label, options: [{ value, label, count, hex? }] }], facets with < 2 values omitted. */
export function facets(scope, f, q, { inStock, supplier, typeFixed }) {
  const out = [];
  const count = (skip, key) => {
    const m = new Map();
    for (const p of applyFilters(scope, f, q, { inStock, skip })) for (const v of key(p)) m.set(v, (m.get(v) || 0) + 1);
    return m;
  };
  const all = (key) => { const s = new Map(); for (const p of scope) for (const [v, l] of key(p)) s.set(v, l); return s; };
  const facet = (id, label, skip, keyed) => {
    const values = all(keyed);
    if (values.size < 2) return;
    const c = count(skip, (p) => keyed(p).map(([v]) => v));
    out.push({ id, label, options: [...values].map(([value, l]) => ({ value, label: l, count: c.get(value) || 0 })) });
  };
  if (supplier === 'all') facet('store', 'Supplier', 'store', (p) => [[p.store, p.store === 'menards-3064' ? 'Menards' : 'Home Depot']]);
  if (!typeFixed) facet('types', 'Type', 'types', (p) => [[typeOf(p).type.id, typeOf(p).type.label]]);
  facet('kinds', 'Style', 'kinds', (p) => (KIND_LABELS[p.kind] ? [[p.kind, KIND_LABELS[p.kind]]] : []));
  const brands = new Map();
  for (const p of scope) if (!brands.has(brandKey(p) || '~')) brands.set(brandKey(p) || '~', String(p.brand || '').trim() || 'Unbranded');
  facet('brands', 'Brand', 'brands', (p) => [[brandKey(p) || '~', brands.get(brandKey(p) || '~')]]);
  const famIdx = Object.fromEntries(COLOUR_FAMILIES.map(([id, l, hex]) => [id, { l, hex }]));
  facet('colours', 'Colour', 'colours', (p) => [...familiesOf(p)].map((c) => [c, famIdx[c].l]));
  const cf = out.find((x) => x.id === 'colours');
  if (cf) { cf.options.sort((a, b) => COLOUR_FAMILIES.findIndex((c) => c[0] === a.value) - COLOUR_FAMILIES.findIndex((c) => c[0] === b.value)); cf.options.forEach((o) => { o.hex = famIdx[o.value].hex; }); }
  facet('lengths', 'Length', 'lengths', (p) => (lengthFt(p) != null ? [[lengthFt(p), `${lengthFt(p)} ft`]] : []));
  facet('gauges', 'Gauge', 'gauges', (p) => (gaugeOf(p) != null ? [[gaugeOf(p), `${gaugeOf(p)} gauge`]] : []));
  const gf = out.find((x) => x.id === 'gauges');
  if (gf) gf.options.sort((a, b) => a.value - b.value);
  const lf = out.find((x) => x.id === 'lengths');
  if (lf) lf.options.sort((a, b) => a.value - b.value);
  const bf = out.find((x) => x.id === 'brands');
  if (bf) bf.options.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  return out;
}

export const SORTS = [
  ['recommended', 'Recommended'], ['priceAsc', 'Price: low to high'], ['priceDesc', 'Price: high to low'],
  ['unitAsc', 'Price per square: low to high'], ['name', 'Name A–Z'], ['brand', 'Brand A–Z'], ['stock', 'In stock: most first'],
];

/**
 * Sort a product list. ctx: { chosen: Set(id), suggested: Set(id), name(p), inStock(p) }.
 * Products missing the sort key (no price, no unit price) always go last; they are flagged `_nokey`.
 */
export function sortProducts(list, sortId, ctx) {
  const name = (p) => ctx.name(p).toLowerCase();
  const byName = (a, b) => name(a).localeCompare(name(b));
  const rec = (p) => [ctx.chosen.has(p.id) ? 0 : 1, ctx.suggested.has(p.id) ? 0 : 1, p.price?.shelf == null ? 1 : 0, p.store === 'homedepot-4301' && ctx.inStock(p) ? 0 : 1, p.priority ?? 999];
  const cmpArr = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i]; return 0; };
  const keyed = (key, dir = 1) => {
    const has = [], none = [];
    for (const p of list) (key(p) == null ? none : has).push(p);
    has.sort((a, b) => (key(a) - key(b)) * dir || byName(a, b));
    none.sort(byName);
    none.forEach((p, i) => { p._nokey = i === 0; });
    has.forEach((p) => { p._nokey = false; });
    return [...has, ...none];
  };
  list.forEach((p) => { p._nokey = false; });
  switch (sortId) {
    case 'priceAsc': return keyed((p) => p.price?.shelf ?? null);
    case 'priceDesc': return keyed((p) => p.price?.shelf ?? null, -1);
    case 'unitAsc': return keyed((p) => { const u = unitPrice(p); return u ? (u.unit === 'sq' ? 0 : 1e7) + u.value : null; });
    case 'name': return [...list].sort(byName);
    case 'brand': return [...list].sort((a, b) => (brandKey(a) || '~').localeCompare(brandKey(b) || '~') || byName(a, b));
    case 'stock': return keyed((p) => (p.stock?.qty != null ? -p.stock.qty : null));
    default: return [...list].sort((a, b) => cmpArr(rec(a), rec(b)) || byName(a, b));
  }
}

/** Check that every product lands in exactly one type: { ok, unassigned, counts }. */
export function assertPartition(products) {
  const unassigned = [];
  const counts = {};
  for (const p of products) {
    const t = KIND_TO_TYPE.get(p.kind);
    if (!t) { unassigned.push(p.id); continue; }
    const k = `${t.project.id}/${t.type.id}`;
    counts[k] = counts[k] || { 'menards-3064': 0, 'homedepot-4301': 0 };
    counts[k][p.store] = (counts[k][p.store] || 0) + 1;
  }
  return { ok: !unassigned.length, unassigned, counts };
}
