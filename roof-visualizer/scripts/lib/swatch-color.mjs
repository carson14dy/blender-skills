// Color of a store swatch or product photo, from its pixels (build plan section 5.4).
// Pure, no dependencies: the sampler decodes an image to 96 x 96 RGB with ffmpeg and passes the bytes here.
// Deterministic: no random numbers, so the same image always gives the same color.

/** Luma on sRGB values, 0-255. */
export const luma = (r, g, b) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

const LIN = Array.from({ length: 256 }, (_, i) => { const c = i / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
const toSrgb = (l) => { const c = l <= 0.0031308 ? l * 12.92 : 1.055 * l ** (1 / 2.4) - 0.055; return Math.max(0, Math.min(255, Math.round(c * 255))); };

/** [r, g, b] (0-255) -> "#rrggbb". */
export const hexOf = (c) => '#' + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
/** "#rrggbb" -> [r, g, b]. */
export const rgbOf = (hex) => { const n = parseInt(String(hex).replace('#', ''), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };

/** Color names that mean a white product: the light-neutral step must not remove the product itself. */
export const WHITE_NAME = /\b(white|polar|snow|arctic|alabaster)\b/i;

const BG_MIN = 236, BG_SPREAD = 12;           // background: near-white, near-neutral, connected to the border
const NEUTRAL_CHROMA = 18;                     // light neutrals: siding, sky, glare
export const LIGHT_NEUTRAL_LUMA = { asphalt: 165, other: 205 };
export const MIXED_SPREAD = 60;                // single-color products: clusters this far apart are badges or packaging

/** Mean of pixel indices in linear light, back to sRGB. */
function linearMean(rgb, idx) {
  let r = 0, g = 0, b = 0;
  for (const i of idx) { r += LIN[rgb[i * 3]]; g += LIN[rgb[i * 3 + 1]]; b += LIN[rgb[i * 3 + 2]]; }
  const n = idx.length || 1;
  return [toSrgb(r / n), toSrgb(g / n), toSrgb(b / n)];
}

/** k-means in sRGB, k = 4, seeded at the 12.5/37.5/62.5/87.5 luma percentiles of `idx` (sorted by luma), 8 rounds. */
function kmeans(rgb, idx) {
  const n = idx.length;
  let centers = [0.125, 0.375, 0.625, 0.875].map((q) => { const i = idx[Math.min(n - 1, Math.floor(q * n))]; return [rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]]; });
  const assign = new Int32Array(n);
  const step = () => {
    for (let k = 0; k < n; k++) {
      const i = idx[k] * 3; let best = 0, bd = Infinity;
      for (let c = 0; c < centers.length; c++) {
        const dr = rgb[i] - centers[c][0], dg = rgb[i + 1] - centers[c][1], db = rgb[i + 2] - centers[c][2];
        const d = dr * dr + dg * dg + db * db;
        if (d < bd) { bd = d; best = c; }
      }
      assign[k] = best;
    }
  };
  for (let round = 0; round < 8; round++) {
    step();
    const sum = centers.map(() => [0, 0, 0, 0]);
    for (let k = 0; k < n; k++) { const i = idx[k] * 3, s = sum[assign[k]]; s[0] += rgb[i]; s[1] += rgb[i + 1]; s[2] += rgb[i + 2]; s[3]++; }
    centers = centers.map((c, j) => (sum[j][3] ? [sum[j][0] / sum[j][3], sum[j][1] / sum[j][3], sum[j][2] / sum[j][3]] : c));
  }
  step();
  let clusters = centers.map((c, j) => ({ c, members: [] }));
  for (let k = 0; k < n; k++) clusters[assign[k]].members.push(idx[k]);
  clusters = clusters.filter((x) => x.members.length);
  // merge clusters closer than 6 on every channel
  for (let merged = true; merged;) {
    merged = false;
    clusters.sort((a, b) => b.members.length - a.members.length);
    outer: for (let a = 0; a < clusters.length; a++) {
      for (let b = a + 1; b < clusters.length; b++) {
        const A = clusters[a], B = clusters[b];
        if (A.c.every((v, ch) => Math.abs(v - B.c[ch]) < 6)) {
          const na = A.members.length, nb = B.members.length;
          A.c = A.c.map((v, ch) => (v * na + B.c[ch] * nb) / (na + nb));
          A.members = A.members.concat(B.members);
          clusters.splice(b, 1);
          merged = true;
          break outer;
        }
      }
    }
  }
  return clusters.sort((a, b) => b.members.length - a.members.length);
}

/**
 * Color of an image given as RGB bytes (96 x 96 x 3 from the sampler; any square size works).
 * @returns {{hex: string, palette: string[], method: 'full'|'cutout'|'all', kept: number, check: string[]}}
 */
export function sampleColor(rgb, { whiteName = false, asphalt = false, single = false } = {}) {
  const n = Math.floor(rgb.length / 3), side = Math.round(Math.sqrt(n));
  if (side * side !== n) throw new Error(`sampleColor: expected a square image, got ${n} pixels`);
  const check = [];
  // 1. background: breadth-first from the border through near-white, near-neutral pixels
  const isBg = (i) => { const r = rgb[i * 3], g = rgb[i * 3 + 1], b = rgb[i * 3 + 2]; return Math.min(r, g, b) >= BG_MIN && Math.max(r, g, b) - Math.min(r, g, b) <= BG_SPREAD; };
  const bg = new Uint8Array(n), queue = new Int32Array(n);
  let head = 0, tail = 0;
  const push = (i) => { if (!bg[i] && isBg(i)) { bg[i] = 1; queue[tail++] = i; } };
  for (let x = 0; x < side; x++) { push(x); push((side - 1) * side + x); }
  for (let y = 0; y < side; y++) { push(y * side); push(y * side + side - 1); }
  while (head < tail) {
    const i = queue[head++], x = i % side, y = (i - x) / side;
    if (x > 0) push(i - 1); if (x < side - 1) push(i + 1);
    if (y > 0) push(i - side); if (y < side - 1) push(i + side);
  }
  const kept = (n - tail) / n;
  // 2. white on white: use every pixel
  let method, px = [];
  if (kept < 0.04) { method = 'all'; for (let i = 0; i < n; i++) px.push(i); }
  else { method = kept > 0.97 ? 'full' : 'cutout'; for (let i = 0; i < n; i++) if (!bg[i]) px.push(i); }
  const L = (i) => luma(rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]);
  // 3. light neutrals (siding, sky, glare), unless the product itself is white
  if (!whiteName) {
    const T = asphalt ? LIGHT_NEUTRAL_LUMA.asphalt : LIGHT_NEUTRAL_LUMA.other;
    const keep = px.filter((i) => { const r = rgb[i * 3], g = rgb[i * 3 + 1], b = rgb[i * 3 + 2]; return !(L(i) > T && Math.max(r, g, b) - Math.min(r, g, b) < NEUTRAL_CHROMA); });
    const dropped = 1 - keep.length / px.length;
    if (dropped <= 0.75) { if (dropped > 0.15) check.push('scene'); px = keep; }
  }
  // 4. trim the darkest and lightest 5% by luma (stable: ties keep pixel order)
  const lum = new Float64Array(n);
  for (const i of px) lum[i] = L(i);
  px.sort((a, b) => lum[a] - lum[b] || a - b);
  const cut = Math.floor(px.length * 0.05);
  const trimmed = px.length - 2 * cut > 0 ? px.slice(cut, px.length - cut) : px;
  // 5. palette
  const clusters = kmeans(rgb, trimmed);
  const palette = clusters.map((c) => hexOf(c.c));
  // 6. hex: linear-light mean; a single-color product with far-apart clusters takes its largest cluster
  let hex = hexOf(linearMean(rgb, trimmed));
  if (single && clusters.length > 1) {
    const far = clusters.some((a, i) => clusters.slice(i + 1).some((b) => a.c.some((v, ch) => Math.abs(v - b.c[ch]) > MIXED_SPREAD)));
    if (far) { hex = hexOf(linearMean(rgb, clusters[0].members)); check.push('mixed'); }
  }
  return { hex, palette, method, kept: Math.round(kept * 1000) / 1000, check };
}

const NAME_RULES = [
  { re: /\b(black|onyx|midnight)\b/i, why: 'black: luma under 80', ok: ([r, g, b]) => luma(r, g, b) < 80 },
  { re: WHITE_NAME, why: 'white: luma over 170', ok: ([r, g, b]) => luma(r, g, b) > 170 },
  { re: /\b(red|burgundy|crimson)\b/i, why: 'red: R largest by 25', ok: ([r, g, b]) => r - Math.max(g, b) >= 25 },
  { re: /\b(green|evergreen|forest)\b/i, why: 'green: G >= R and G >= B', ok: ([r, g, b]) => g >= r && g >= b },
  { re: /\bblue\b/i, why: 'blue: B largest', ok: ([r, g, b]) => b > r && b > g },
  // R >= G >= B alone passes a neutral gray (#75756d, the "Beige" cap photo): a brown also needs R - B >= 12
  { re: /\b(brown|bark|hickory|walnut|cedar|tan|beige|sienna)\b/i, why: 'brown: R >= G >= B, R - B >= 12', ok: ([r, g, b]) => r >= g && g >= b && r - b >= 12 },
];

/** Does a sampled hex agree with its color name? Never changes the hex; a failure adds the check 'name-mismatch'. */
export function nameCheck(name, hex) {
  const rgb = rgbOf(hex);
  const failed = NAME_RULES.filter((r) => r.re.test(String(name || '')) && !r.ok(rgb)).map((r) => r.why);
  return { ok: !failed.length, why: failed.length ? failed.join('; ') : null };
}

const NAME_COLORS = [
  [/\bblack\b/i, '#26272a'], [/\bcharcoal\b/i, '#3c3f43'], [/\bwhite\b/i, '#f0efea'],
  [/\b(galvalume|galvanized|mill|silver|stainless)\b/i, '#b5b9bd'], [/\bgr[ae]y\b/i, '#7b7e82'], [/\bbrown\b/i, '#5a3f2b'],
  [/\bbronze\b/i, '#4a3b2e'], [/\b(tan|beige)\b/i, '#b9a586'], [/\bred\b/i, '#7a2b24'], [/\bgreen\b/i, '#2f4a34'],
  [/\bblue\b/i, '#34506e'], [/\bcopper\b/i, '#a5623b'], [/\bcedar\b/i, '#a0744d'],
];

/** A color from words alone, for an entry with no usable image: the color name first, then the product name. Null when no word matches. */
export function colorFromName(colorName, productName = '') {
  for (const text of [colorName, productName]) {
    if (!text) continue;
    for (const [re, hex] of NAME_COLORS) if (re.test(text)) return hex;
  }
  return null;
}
