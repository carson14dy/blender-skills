// Store product -> studio product (render recipe), and the layer option a store
// product sets on the other layers. Pure: no DOM, no three.js, importable by node --test.
//
// Reads the Sioux Falls store catalog (catalog/suppliers/sioux-falls.json). Version 2
// adds `hex`, `palette`, `colorSource`, `colorCheck` and `pbr` on color entries and
// `hex`, `palette`, `colorSource` on the product (its listed color). Version 1 has
// none of them: every product then draws in neutral gray, marked "color not sampled".

import { hashString, hexToRgb, rgbToHex, slugify } from './util.js';

export const STORE_IDS = ['menards-3064', 'homedepot-4301'];
const STORE_SHORT = { 'menards-3064': 'Menards', 'homedepot-4301': 'Home Depot' };

/** Slots of a job: the layer ids that take a store product, plus `valley`. */
export const SLOTS = ['covering', 'ridgeCap', 'starter', 'underlayment', 'iceWater', 'dripEdge', 'ridgeVent', 'valley'];

/** Drawn for a product whose color was not sampled. Unknown is shown as unknown. */
export const NEUTRAL = '#808080';

/**
 * Suggested products for a new job (the test basket). `color: null` means the product's
 * listed color. Shown with a "suggested" tag until the user picks or confirms.
 */
export const SUGGESTED = deepFreeze({
  covering: { 'menards-3064': { productId: 'mn-1444450489132', color: 'Sierra Gray' }, 'homedepot-4301': { productId: 'hd-309755006', color: 'Charcoal' } },
  ridgeCap: { 'menards-3064': { productId: 'mn-1642874276146419', color: null }, 'homedepot-4301': { productId: 'hd-206593176', color: null } },
  starter: { 'menards-3064': { productId: 'mn-1444450475975', color: null }, 'homedepot-4301': { productId: 'hd-202052408', color: null } },
  underlayment: { 'menards-3064': { productId: 'mn-1444450500228', color: null }, 'homedepot-4301': { productId: 'hd-340399395', color: null } },
  iceWater: { 'menards-3064': { productId: 'mn-1444450479015', color: null }, 'homedepot-4301': { productId: 'hd-100083275', color: null } },
  dripEdge: { 'menards-3064': { productId: 'mn-1444424196953', color: null }, 'homedepot-4301': { productId: 'hd-100087282', color: null } },
  ridgeVent: { 'menards-3064': { productId: 'mn-1444450488871', color: null }, 'homedepot-4301': { productId: 'hd-316349297', color: null } },
  valley: { 'menards-3064': { productId: 'mn-1444448528388', color: null }, 'homedepot-4301': { productId: 'hd-100096067', color: null } },
});

function deepFreeze(o) { for (const v of Object.values(o)) if (v && typeof v === 'object') deepFreeze(v); return Object.freeze(o); }

/** The product with this id, or null. */
export function findProduct(catalog, productId) {
  return (catalog?.products || []).find((p) => p.id === productId) || null;
}

/**
 * The suggested choice for every slot and store: { slot: { storeId: Choice | null } },
 * Choice = { productId, color, source: 'suggested' }. A product missing from the catalog gives null.
 */
export function suggestedSelections(catalog) {
  const byId = new Map((catalog?.products || []).map((p) => [p.id, p]));
  const out = {};
  for (const slot of SLOTS) {
    out[slot] = {};
    for (const store of STORE_IDS) {
      const s = SUGGESTED[slot][store];
      const sp = byId.get(s.productId);
      out[slot][store] = sp ? { productId: sp.id, color: s.color ?? defaultColor(sp), source: 'suggested' } : null;
    }
  }
  return out;
}

/** "Menards" / "Home Depot" (the catalog's store name for any other store). */
export function storeName(storeId, catalog = null) {
  return STORE_SHORT[storeId] || catalog?.stores?.[storeId]?.name || storeId || '';
}

/** The product's listed color name: `color`, else the only color entry's name, else null. */
export function defaultColor(sp) {
  if (sp?.color != null) return sp.color;
  return sp?.colors?.length === 1 ? (sp.colors[0].name ?? null) : null;
}

const isHex = (h) => typeof h === 'string' && /^#[0-9a-f]{6}$/i.test(h);
const defined = (o) => Object.fromEntries(Object.entries(o || {}).filter(([, v]) => v != null));
const norm = (s) => String(s ?? '').trim().toLowerCase();

/**
 * The color entry for a color name, with the product-level hex / palette filled in for its
 * listed color: { name, hex?, palette?, colorSource?, colorCheck?, pbr? }.
 */
export function colorEntry(sp, colorName = defaultColor(sp)) {
  const list = sp?.colors || [];
  const name = colorName ?? null;
  const e = list.find((c) => (c.name ?? null) === name) || (name != null ? list.find((c) => norm(c.name) === norm(name)) : null);
  const listed = name === (defaultColor(sp) ?? null) || (name != null && norm(name) === norm(defaultColor(sp)));
  const fromProduct = listed ? defined({ hex: sp.hex, palette: sp.palette, colorSource: sp.colorSource, colorCheck: sp.colorCheck }) : {};
  const out = { ...fromProduct, ...defined(e), name };
  const pbr = e?.pbr ?? sp?.pbr;
  if (pbr) out.pbr = pbr; else delete out.pbr;
  if (!isHex(out.hex)) delete out.hex; else out.hex = out.hex.toLowerCase();
  return out;
}

const luma = (hex) => { const [r, g, b] = hexToRgb(hex); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };

/** Four shades around one color (same rule as `shadesOf` in layers.js, which needs three.js). */
export function shadesOf(hex) {
  const c = hexToRgb(hex);
  return [rgbToHex(c), rgbToHex(c.map((x) => x * 0.78)), rgbToHex(c.map((x) => Math.min(255, x * 1.18))), rgbToHex(c.map((x) => x * 0.62))];
}

/**
 * Texture palette for a color entry: its sampled palette (largest cluster first) when it has
 * 3 or more colors, else shades of its hex. For asphalt, a palette whose luma range is under 20
 * is too flat to read as a laminate, so shades of the hex are used instead.
 */
export function paletteFor(entry, { asphalt = false } = {}) {
  const hex = isHex(entry?.hex) ? entry.hex.toLowerCase() : NEUTRAL;
  const pal = (Array.isArray(entry?.palette) ? entry.palette : []).filter(isHex).map((h) => h.toLowerCase()).slice(0, 4);
  if (pal.length >= 3) {
    if (!asphalt) return pal;
    const l = pal.map(luma);
    // asphalt: pull each sampled color 40% toward the product color, so blends read as one roof from a distance
    if (Math.max(...l) - Math.min(...l) >= 20) return pal.map((h) => mixHex(h, hex, 0.4));
  }
  return shadesOf(hex);
}

/** Mix two #rrggbb colors: t = 0 gives a, t = 1 gives b. */
export function mixHex(a, b, t) {
  const c = (h, i) => parseInt(h.slice(1 + 2 * i, 3 + 2 * i), 16);
  return '#' + [0, 1, 2].map((i) => Math.round(c(a, i) + (c(b, i) - c(a, i)) * t).toString(16).padStart(2, '0')).join('');
}

/** Texture seed for a product: always the same look for the same product. */
export const seedFor = (sp) => (hashString(String(sp.id)) % 97) + 1;

const GENERIC = /\b(?:algae resistant|architectural|laminated|laminate|3-tab|three-tab|roofing|roof|shingles?|steel|panels?|hip (?:and|&) ridge|ridge cap|ridge vent|starter|synthetic|underlayment|ice (?:and|&) water|drip edge|valley|shakes?)\b/gi;
const MEASURE = /(?:\b\d[\d.,/-]*\s*(?:lin\.?\s*ft\.?|sq\.?\s*ft\.?|ft\.?|in\.?|"|'|’|”|′|″)\s*(?:[WLH]\b\s*)?(?:x\s*)?)+/gi;
const PACK = /\b\d+\s*-?\s*(?:pcs?|pack|pk|pieces?)\b/gi;
const hasOwnWord = (s) => /[a-z0-9]{2,}/i.test(s.replace(GENERIC, ' '));

/** Short product line name for cards and labels, e.g. "TruDefinition Duration", "Timberline HDZ", "Designer Premium Pro-Rib". */
export function shortName(sp) {
  let t = String(sp?.name || '').replace(/^"+|"+$/g, '').replace(/""/g, '"');
  t = t.replace(/[®™©]/g, '').replace(/\([^)]*\)/g, ' ').replace(MEASURE, ' ').replace(PACK, ' ').replace(/\s+/g, ' ').trim();
  const color = defaultColor(sp);
  if (color) t = t.replace(new RegExp(`\\b${color.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}\\b`, 'i'), ' ').replace(/\s+/g, ' ').trim();
  // drop a leading brand ("Owens Corning"), unless that leaves only generic words ("Premium Pro-Rib" is the line)
  if (sp?.brand && norm(t).startsWith(norm(sp.brand) + ' ') && hasOwnWord(t.slice(sp.brand.length))) t = t.slice(sp.brand.length).trim();
  // cut at the first generic word that follows at least one word of the product's own
  for (const m of t.matchAll(GENERIC)) {
    const head = t.slice(0, m.index);
    if (head.trim().length >= 6 && hasOwnWord(head)) { t = head; break; }
  }
  t = t.replace(/[\s,;:\-–]+$/, '').trim();
  if (t.length > 40) t = t.slice(0, 40).replace(/\s+\S*$/, '');
  return t || String(sp?.name || sp?.id || '').slice(0, 40);
}

/** The exploded-view label line for a store product: "Duration, Sierra Gray · Menards". */
export function specFor(sp, colorName = defaultColor(sp), catalog = null) {
  return `${shortName(sp)}${colorName ? `, ${colorName}` : ''} · ${storeName(sp.store, catalog)}`;
}

/** Cedar exposure from the piece length: 16" -> 5, 18" -> 7.5 (shakes) or 5.5 (shingles), 24" -> 10. */
function cedarExposure(sp) {
  const L = sp.size?.lengthIn;
  if (!L) return null;
  if (L <= 16.5) return 5;
  if (L <= 20) return /shake/i.test(sp.name || '') ? 7.5 : 5.5;
  return 10;
}

/**
 * A store covering as a studio product, in the shape `applyProduct()` takes:
 * { id, name, supplier, category, exposureIn?, procedural: { kind, palette | color, exposureIn?, seed, ...sizes },
 *   pbr, hex, store: { id, productId, color, url }, approx: [notes shown on the card] }.
 */
export function toStudioProduct(sp, colorName = defaultColor(sp), catalog = null) {
  const entry = colorEntry(sp, colorName);
  const hex = entry.hex || null;
  const approx = [];
  if (!hex) approx.push('color not sampled');
  else if (entry.colorSource === 'name') approx.push('color from its name, not from a photo');
  if (entry.colorCheck?.includes('name-mismatch')) approx.push('sampled color may not match its name');
  const seed = seedFor(sp);
  const size = sp.size || {};
  let category, exposureIn, procedural;
  const asShingle = (kind, exp, { asphalt = true } = {}) => {
    category = 'shingle'; exposureIn = exp;
    procedural = { kind, palette: paletteFor(entry, { asphalt }), exposureIn: exp, seed };
  };
  const asMetal = (kind, sizes) => {
    category = 'metal';
    procedural = { kind, color: hex || NEUTRAL, seed, ...sizes };
  };
  switch (sp.kind) {
    case 'architectural': {
      asShingle('architectural', size.exposureIn || 5.625);
      if (/atlas/i.test(`${sp.brand || ''} ${sp.name || ''}`) && exposureIn === 6) approx.push('exposure 6 in. from the Menards table, not confirmed on the Atlas sheet');
      break;
    }
    case 'threeTab':
      asShingle('threeTab', size.exposureIn || 5);
      break;
    case 'cedar':
    case 'undercourse': {
      const exp = cedarExposure(sp);
      asShingle('cedarShake', exp || 7.5, { asphalt: false });
      category = 'shake';
      if (!exp) approx.push('exposure assumed 7.5 in.: the store does not give the length');
      break;
    }
    case 'proRib':
      asMetal('ribbedPanel', { coverIn: 36, ribSpacingIn: size.ribSpacingIn || 9, ribHeightIn: size.ribHeightIn || 0.75, minorRibs: 2 });
      break;
    case 'proSnap':
    case 'standingSeam':
      asMetal('standingSeam', { panelIn: 16, ...(size.ribHeightIn ? { seamIn: size.ribHeightIn } : {}) });
      if (sp.kind === 'standingSeam') approx.push('seam spacing assumed 16 in.: the store does not state it');
      break;
    case 'corrugated':
      asMetal('corrugatedPanel', { pitchIn: 2.67, depthIn: 0.5 });
      approx.push('corrugation 2.67 in. x 0.5 in. is the common profile, not store data');
      break;
    case 'panel':
      asMetal('ribbedPanel', { coverIn: 36, ribSpacingIn: 9, ribHeightIn: 0.75, minorRibs: 2 });
      approx.push('profile assumed: the store does not state it');
      break;
    case 'stoneCoated':
      asShingle('architectural', 13.3);
      approx.push('drawn as a granule course; real panel profile is later');
      break;
    default:
      asShingle('architectural', size.exposureIn || 5.625);
      approx.push('drawn as an architectural shingle: no recipe for this product type');
  }
  const product = {
    id: `${sp.id}::${slugify(colorName ?? 'listed')}`,
    name: colorName ? `${shortName(sp)}, ${colorName}` : shortName(sp),
    supplier: storeName(sp.store, catalog),
    category,
    ...(exposureIn ? { exposureIn } : {}),
    procedural,
    pbr: entry.pbr || null,
    hex,
    store: { id: sp.store, productId: sp.id, color: colorName ?? null, url: sp.url || null },
    approx,
  };
  return product;
}

// ---------------------------------------------------------------------------
// Drip edge profile (020): style and inch sizes from the product name.

/** Kick and hem always come from the style; flange and face when the name gives none. Inches. */
export const EDGE_STYLES = deepFreeze({
  A: { flangeIn: 1.375, faceIn: 1.375, kickOutIn: 0, kickDownIn: 0, hemIn: 0 },
  C: { flangeIn: 2.0, faceIn: 1.5, kickOutIn: 0.375, kickDownIn: 0.375, hemIn: 0 },
  D: { flangeIn: 2.375, faceIn: 1.6875, kickOutIn: 0.5, kickDownIn: 0.25, hemIn: 0 },
  apron: { flangeIn: 2.5, faceIn: 2.0, kickOutIn: 0, kickDownIn: 0, hemIn: 0.375 },
  rake: { flangeIn: 1.5, faceIn: 3.5, kickOutIn: 0, kickDownIn: 0, hemIn: 0.5 },
});

// an inch size: 2-3/8", 1-11/16", 2.43 in., 3/4", 1 in (not a number that is part of a code such as F4 or C3)
const INCH = /(?<![\w.\/-])(?:(\d+)-(\d+)\/(\d+)|(\d+)\/(\d+)|(\d+(?:\.\d+)?))\s*(?:"|”|″|in\b\.?|inch(?:es)?\b)/gi;
// a length in feet: 12', 10 ft, 10.5 ft. (the first one ends the cross-section sizes)
const FEET = /(?<![\d.\/-])\d+(?:\.\d+)?\s*(?:'|’|′|ft\b|feet\b)/i;

/**
 * Cross-section of a drip edge, gutter apron or rake trim from its name:
 * { style: 'A' | 'C' | 'D' | 'apron' | 'rake', flangeIn, faceIn, kickOutIn, kickDownIn, hemIn, approx: [notes] }.
 * The first two inch sizes before the length are the flange (deck leg) and the face; a single one is the face.
 * Menards `size.widthIn` is not used: its spec table is unreliable for edging.
 */
export function edgeProfileFor(sp) {
  const name = String(sp?.name || '').replace(/""/g, '"');
  const style = /style[- ]?a\b/i.test(name) ? 'A'
    : /style[- ]?c\b|\bC3\b/i.test(name) ? 'C'
      : /style[- ]?d\b|\bD[- ]style\b|\bF\s?\d/i.test(name) ? 'D'
        : sp?.kind === 'gutterApron' || /apron/i.test(name) ? 'apron'
          : sp?.kind === 'rakeTrim' ? 'rake' : 'D';
  const def = EDGE_STYLES[style];
  const approx = [];
  const feet = name.search(FEET);
  const head = feet >= 0 ? name.slice(0, feet) : name;
  const sizes = [...head.matchAll(INCH)].slice(0, 2).map((m) => (m[1] ? +m[1] + m[2] / m[3] : m[4] ? m[4] / m[5] : +m[6]));
  let flangeIn = def.flangeIn, faceIn = def.faceIn;
  if (sizes.length >= 2) [flangeIn, faceIn] = sizes;
  else if (sizes.length === 1) { faceIn = sizes[0]; approx.push('flange assumed'); }
  else approx.push('size assumed from the profile style');
  const clamp = (what, v, lo, hi) => {
    const c = Math.min(hi, Math.max(lo, v));
    if (c !== v) approx.push(`${what} ${+v.toFixed(3)} in. read from the name, drawn at ${c} in.`);
    return c;
  };
  flangeIn = clamp('flange', flangeIn, 0.75, 6);
  faceIn = clamp('face', faceIn, 0.5, 4);
  return { style, flangeIn, faceIn, kickOutIn: def.kickOutIn, kickDownIn: def.kickDownIn, hemIn: def.hemIn, approx };
}

/**
 * What a store product changes on the other layers, as layer option key -> value
 * (pass each to `layers.setOption(key, value)`). Empty when the 3D view does not change.
 *   ridgeCap: { capPalette, capColor, capWidthIn } (capPalette or capColor null; capWidthIn = a metal cap's widthIn, else null);
 *   dripEdge: { dripEdge: { id, label, color, metal, profile } } (profile from edgeProfileFor);
 *   underlayment: { underlayment: 'felt30' | 'syn-gray' | 'syn-blue' | 'syn-black' }; iceWater: { iceWater: 'granular' | 'smooth' }.
 */
export function layerOptionFor(sp, colorName = defaultColor(sp)) {
  const entry = colorEntry(sp, colorName);
  const hex = entry.hex || null;
  const words = `${sp.name || ''} ${colorName || ''}`;
  switch (sp.layer) {
    case 'ridgeCap':
      return sp.kind === 'metalCap' ? { capColor: hex || NEUTRAL, capPalette: null, capWidthIn: sp.size?.widthIn > 0 ? sp.size.widthIn : null } : { capPalette: paletteFor(entry, { asphalt: true }), capColor: null, capWidthIn: null };
    case 'dripEdge':
      return { dripEdge: { id: sp.id, label: colorName ? `${shortName(sp)}, ${colorName}` : shortName(sp), color: hex || NEUTRAL, metal: entry.pbr?.metallic ?? 0.3, profile: edgeProfileFor(sp) } };
    case 'underlayment':
      if (sp.kind === 'felt') return { underlayment: 'felt30' };
      return { underlayment: /\bblue\b/i.test(words) ? 'syn-blue' : /\bblack\b/i.test(words) ? 'syn-black' : 'syn-gray' };
    case 'iceWater':
      return { iceWater: /granul|mineral/i.test(sp.name || '') ? 'granular' : 'smooth' };
    default:
      return {}; // starter, ridge vent, valley (and the covering, which goes through toStudioProduct)
  }
}
