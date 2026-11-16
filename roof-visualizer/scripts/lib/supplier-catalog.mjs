// Normalize store catalogs (Menards CSV package, Home Depot materials.json) into one studio catalog.
// Pure functions, no dependencies: the build script and the tests both use them.
// Product photos and swatches stay links: nothing here downloads or stores an image.

/** RFC 4180 CSV -> array of objects (BOM stripped, quoted fields, embedded commas and newlines). */
export function parseCSV(text) {
  text = text.replace(/^﻿/, '');
  const rows = [];
  let row = [], field = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; } else field += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += c;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.length > 1 || r[0] !== '');
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h.trim(), (r[i] ?? '').trim()])));
}

const num = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(String(v).replace(/[$,]/g, ''));
  return Number.isFinite(n) ? n : null;
};
/** A price is a positive number or null: unknown is never zero. */
const price = (v) => { const n = num(v); return n && n > 0 ? n : null; };

/** "32.8 square foot" -> {sqft: 32.8}; "31 linear foot" -> {lf: 31}; anything else -> null. */
export function parseCoverage(text) {
  const t = String(text || '').toLowerCase();
  let m = t.match(/([\d.,]+)\s*(?:square|sq\.?)\s*(?:foot|feet|ft)/);
  if (m) return { sqft: num(m[1]) };
  m = t.match(/([\d.,]+)\s*(?:linear|lin\.?)\s*(?:foot|feet|ft)/);
  if (m) return { lf: num(m[1]) };
  return null;
}

/** Coverage stated in a product name, e.g. "(33.33 sq. ft. per Bundle)", "(25 lin. ft. per Bundle)", "1000 sq. ft. Roll". */
export function coverageFromName(name) {
  const t = String(name || '');
  let m = t.match(/([\d.,]+)\s*sq\.?\s*ft\.?(?:\s*(?:per|\/)\s*(?:bundle|roll|box|carton|pack|package))?/i);
  if (m) return { sqft: num(m[1]) };
  m = t.match(/([\d.,]+)\s*sq\.?\s*(?:per|\/)\s*roll/i) || t.match(/\b(\d+(?:\.\d+)?)\s*(?:square|sq\.?)s?\s+roll/i);
  if (m) return { sqft: num(m[1]) * 100 };
  m = t.match(/([\d.,]+)\s*lin(?:ear|\.)?\s*ft\.?/i);
  if (m) return { lf: num(m[1]) };
  // a roll given as width x length, e.g. "36 in. x 66.7 ft." or "4 ft. x 250 ft."
  m = t.match(/(\d+(?:\.\d+)?)\s*(in|ft)\.?\s*(?:W\s*)?x\s*(\d+(?:\.\d+)?)\s*ft\.?/i);
  if (m) {
    const w = num(m[1]) / (m[2].toLowerCase() === 'in' ? 12 : 1), l = num(m[3]);
    if (w > 0.5 && w < 10 && l >= 10) return { sqft: Math.round(w * l * 10) / 10 };
  }
  return null;
}

/** Piece length of a linear product in feet, from its name ("x 10'", "10 ft.", "240 in."). */
export function pieceFeet(name) {
  const t = String(name || '');
  let m = t.match(/(\d+(?:\.\d+)?)\s*(?:'|ft\.?|feet)(?!\s*x)(?:\s*(?:L|long|length))?/gi);
  if (m) {
    const ft = m.map((s) => num(s.match(/[\d.]+/)[0])).filter((x) => x >= 3 && x <= 50);
    if (ft.length) return Math.max(...ft);
  }
  m = t.match(/(\d+(?:\.\d+)?)\s*in\.?(?=[^x]*$)/i);
  if (m && num(m[1]) >= 36 && num(m[1]) <= 600) return num(m[1]) / 12;
  return null;
}

const UNIT = { '/bndl': 'bundle', '/100sq. ft.': '100 sq ft', '/roll': 'roll', each: 'each', '/lin.ft.': 'lin ft', '/pkg': 'package', '/box': 'box' };

/** Which studio layer a Menards row belongs to (null: not part of the roof layers). */
export function menardsLayer(r) {
  const cls = r['3D asset class'] || '', type = r['Product type (Menards)'] || '', name = r.Product || '';
  if (cls === 'Roof field: asphalt shingle') return { layer: 'covering', category: 'shingle', kind: /3-tab/i.test(type + name) ? 'threeTab' : 'architectural' };
  if (cls === 'Roof field: metal panel') return { layer: 'covering', category: 'metal', kind: /pro-snap/i.test(name) ? 'proSnap' : /pro-rib/i.test(name) ? 'proRib' : 'panel' };
  if (cls === 'Roof field: stone-coated steel') return { layer: 'covering', category: 'metal', kind: 'stoneCoated' };
  if (cls === 'Roof field: wood shake/shingle') return { layer: 'covering', category: 'shake', kind: /undercourse/i.test(name) ? 'undercourse' : 'cedar' };
  if (cls === 'Linear profile: hip & ridge') return { layer: 'ridgeCap', kind: 'shingleCap' };
  if (cls === 'Linear profile: ridge cap (metal)') return { layer: 'ridgeCap', kind: 'metalCap' };
  if (cls === 'Linear profile: starter') return { layer: 'starter', kind: 'starter' };
  if (cls === 'Layer: underlayment (cutaway)') {
    if (/ice|water|leak/i.test(type + name)) return { layer: 'iceWater', kind: 'iceWater' };
    return { layer: 'underlayment', kind: /felt/i.test(type + name) ? 'felt' : /base sheet/i.test(type) ? 'baseSheet' : 'synthetic' };
  }
  if (cls === 'Linear profile: eave/drip edge') return { layer: 'dripEdge', kind: /apron/i.test(type + name) ? 'gutterApron' : 'dripEdge', edge: 'eave' };
  if (cls === 'Linear profile: rake/gable trim') return { layer: 'dripEdge', kind: 'rakeTrim', edge: 'rake' };
  if (cls === 'Linear profile: ridge vent') return { layer: 'ridgeVent', kind: /closure/i.test(type) ? 'closure' : 'ridgeVent' };
  if (cls === 'Linear profile: valley') return { layer: 'valley', kind: 'valley' };
  return null;
}

/** Which studio layer a Home Depot record belongs to (null: not part of the roof layers). */
export function homeDepotLayer(p) {
  const cat = p.category || '', sub = p.subcategory || '', name = p.name || '';
  if (/combo|\bkit\b|gutter|mesh|\bgal\.|trowel|caulk|sealant|coating|primer|crown repair/i.test(name)) return null; // not a roof layer material
  if (cat === 'Roof Shingles') {
    if (/hip|ridge/i.test(name)) return { layer: 'ridgeCap', kind: 'shingleCap' };
    if (/starter/i.test(name)) return { layer: 'starter', kind: 'starter' };
    if (/cedar/i.test(name)) return { layer: 'covering', category: 'shake', kind: 'cedar' };
    return { layer: 'covering', category: 'shingle', kind: /3[- ]tab/i.test(name) ? 'threeTab' : 'architectural' };
  }
  if (cat === 'Roof Underlayments') {
    if (/ice|water|peel|self[- ]adher|leak barrier|weatherwatch|stormguard/i.test(name)) {
      const cov = coverageFromName(name);
      return { layer: 'iceWater', kind: cov?.sqft && cov.sqft < 60 ? 'flashingTape' : 'iceWater' }; // narrow rolls are flashing tape, not eave membrane
    }
    return { layer: 'underlayment', kind: /felt/i.test(name) ? 'felt' : 'synthetic' };
  }
  if (sub === 'Roof Flashing > Drip Edge Flashing') return { layer: 'dripEdge', kind: 'dripEdge', edge: /rake/i.test(name) ? 'rake' : 'eave' };
  if (cat === 'Roof Flashing' && /valley/i.test(name)) return { layer: 'valley', kind: 'valley' };
  if (sub === 'Roof Vents > Ridge Vents') return { layer: 'ridgeVent', kind: 'ridgeVent' };
  if (sub === 'Roof Panels > Metal Roofing') {
    if (/ridge cap|ridge roll|ridge flashing/i.test(name)) return { layer: 'ridgeCap', kind: 'metalCap' };
    if (/drip edge|eave|rake|gable/i.test(name) && /trim|edge|flashing/i.test(name)) return { layer: 'dripEdge', kind: 'metalTrim', edge: /rake|gable/i.test(name) ? 'rake' : 'eave' };
    if (/panel|sheet|roofing/i.test(name) && !/trim|closure|screw|sealant|tape|flashing/i.test(name)) {
      return { layer: 'covering', category: 'metal', kind: /corrugated/i.test(name) ? 'corrugated' : /standing seam/i.test(name) ? 'standingSeam' : 'panel' };
    }
  }
  return null;
}

const compact = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && !v.length)));

/** Menards package (products.csv, variations.csv, material_library.csv, asset_manifest.csv texts) -> products. */
export function menardsProducts({ products, variations, materials, manifest }, store = 'menards-3064') {
  const P = parseCSV(products), V = parseCSV(variations), ML = parseCSV(materials), AM = parseCSV(manifest);
  const mat = new Map(ML.map((m) => [m.item_id, m]));
  const check = new Map(AM.map((a) => [a['Item ID'], a['Dimension check']]));
  const out = [];
  for (const r of P) {
    const map = menardsLayer(r);
    if (!map) continue;
    const id = r['Item ID'];
    const colors = [];
    const seen = new Set();
    for (const v of V.filter((x) => x.tile_item_id === id && /^color/i.test(x.variation_type))) {
      if (seen.has(v.value)) continue;
      seen.add(v.value);
      const m = mat.get(v.item_id);
      colors.push(compact({ name: v.value, itemId: v.item_id, swatch: v.swatch_large || v.swatch_small, material: m?.material_type, hex: m?.base_color_hex || null }));
    }
    const shown = r['Color / finish shown'];
    if (shown && !seen.has(shown)) colors.unshift(compact({ name: shown, itemId: id, hex: mat.get(id)?.base_color_hex || null }));
    let per = UNIT[r.Unit] || (r.Unit ? r.Unit.replace(/^\//, '') : null);
    const coverage = parseCoverage(r['Coverage area']) || coverageFromName(r.Product);
    if (map.layer === 'covering' && map.category === 'shingle' && coverage?.sqft && coverage.sqft < 60) per = 'bundle'; // listed "each" = one bundle
    out.push(compact({
      id: `mn-${id}`, store, ...map, name: r.Product, brand: r.Brand, sku: r['Menards SKU'], itemId: id, url: r['Product URL'], image: r['Main image'],
      color: shown,
      price: compact({
        shelf: price(r['Shelf price ($)']) ?? price(r['Everyday price ($)']), sale: price(r['Sale price ($)']), saleThrough: r['Sale good through'],
        rebate: price(r['11% rebate ($)']), rebateThrough: r['Rebate good through'], afterRebate: price(r['Value after rebate ($)']),
        per, startingAt: /yes/i.test(r['Starting at?'] || '') || undefined,
      }),
      coverage, pieceFt: ['dripEdge', 'ridgeVent', 'valley'].includes(map.layer) || map.kind === 'metalCap' ? (num(r['Length (in)']) ? num(r['Length (in)']) / 12 : pieceFeet(r.Product)) : null,
      size: compact({
        lengthIn: num(r['Length (in)']), widthIn: num(r['Width (in)']), exposureIn: num(r['Exposure (in)']) || null,
        ribHeightIn: num(r['Rib height (in)']), ribSpacingIn: num(r['Rib spacing o.c. (in)']), gauge: num(r.Gauge),
      }),
      colors, priority: r['3D priority'], detailRead: /yes/i.test(r['Detail page read?'] || ''), dimensionCheck: check.get(id) || null,
      specSheet: r['Spec sheet PDF'], installSheet: r['Install PDF'],
    }));
  }
  for (const p of out) if (p.price && p.price.shelf === undefined && p.price.afterRebate === undefined) delete p.price;
  return out;
}

/** Home Depot materials.json object -> products. */
export function homeDepotProducts(json, store = 'homedepot-4301') {
  const out = [];
  for (const p of json.products || []) {
    const map = homeDepotLayer(p);
    if (!map) continue;
    const coverage = coverageFromName(p.name);
    let per = p.price_per || null;
    if (map.layer === 'covering' && map.category === 'shingle' && coverage?.sqft && coverage.sqft < 60) per = 'bundle';
    if (map.layer === 'ridgeCap' && coverage?.lf && coverage.lf < 60 && per === 'each') per = 'bundle';
    const colors = [];
    if (p.color) colors.push({ name: p.color, itemId: p.id });
    for (const v of p.color_variants || []) if (v.label && !colors.some((c) => c.name === v.label)) colors.push(compact({ name: v.label, itemId: v.item_id, swatch: v.swatch_image }));
    out.push(compact({
      id: `hd-${p.id}`, store, ...map, name: p.name, brand: p.brand, itemId: p.id, url: p.url, image: p.image, color: p.color,
      price: price(p.price) ? compact({ shelf: price(p.price), per, unitPrice: price(p.unit_price), unit: p.unit || null, unitsPerPackage: num(p.units_per_package) || null }) : null,
      coverage, pieceFt: ['dripEdge', 'ridgeVent', 'valley'].includes(map.layer) || map.kind === 'metalCap' ? pieceFeet(p.name) : null,
      colors, availability: p.availability,
      stock: compact({ inStock: p.in_stock_sioux_falls === true, qty: num(p.qty_sioux_falls) }),
    }));
  }
  return out;
}

export const STORES = {
  'menards-3064': { name: 'Menards Sioux Falls West', number: '3064', city: 'Sioux Falls, SD', captured: '2026-11-15',
    notes: ['Shelf price shown; the 11% mail-in rebate ended 11/15/26 and is a store credit, not a checkout discount.',
      '250 of 416 product pages were read before the site stopped answering; the rest lack specs and full color lists.',
      'Spec tables have errors: check dimensionCheck, and prefer the manufacturer spec sheet for P1.'] },
  'homedepot-4301': { name: 'The Home Depot #4301', number: '4301', city: 'Sioux Falls, SD (2523 S Louise Ave)', captured: '2026-11-15/16',
    notes: ['Online price for this store at capture time; Browse Only items have no price (ask the store).',
      'Pro and volume pricing can be lower; color variants can cost more or less than the listed color.'] },
};

/** Build the studio catalog. */
export function buildCatalog({ menards, homeDepot, sources = {} }) {
  const products = [...(menards ? menardsProducts(menards) : []), ...(homeDepot ? homeDepotProducts(homeDepot) : [])];
  const counts = {};
  for (const p of products) {
    const k = `${p.store}/${p.layer}`;
    counts[k] = counts[k] || { products: 0, priced: 0 };
    counts[k].products++;
    if (p.price?.shelf) counts[k].priced++;
  }
  return {
    version: 1,
    project: 'Sioux Falls supplier studio (lab/projects/sioux-falls-studio/PLAN.md)',
    rules: ['Prices are snapshots: re-capture before quoting.', 'A missing price is null, never 0.', 'Images and swatches are links to the stores; none are stored here.'],
    stores: STORES, sources, counts, products,
  };
}
