// Procedural PBR textures (colour + normal + roughness) for every roof layer,
// plus processing for supplier / uploaded swatch photos.
//
// Each generator returns a "TexSet": { color, normal, rough, sizeM:[w,h] }
// where the canvases tile seamlessly and sizeM is the real-world size one
// tile covers. UVs on the roof are in metres, so repeat = 1 / sizeM.
//
// Canvas convention: canvas row 0 is the TOP of the tile (highest up-slope).
// Shingle courses therefore have their butt edge at the bottom of each band.

import * as THREE from 'three';
import { rng, makeNoise, hexToRgb, clamp, inToM } from './util.js';

const cache = new Map();

export function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

/** Turn a TexSet into three.js textures with the right colour spaces and wrapping. */
export function toTextures(set, renderer, { repeat = true } = {}) {
  const aniso = renderer?.capabilities?.getMaxAnisotropy?.() ?? 8;
  const mk = (canvas, srgb) => {
    if (!canvas) return null;
    const t = new THREE.CanvasTexture(canvas);
    t.wrapS = t.wrapT = repeat ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
    t.anisotropy = aniso;
    t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    t.repeat.set(1 / set.sizeM[0], 1 / set.sizeM[1]);
    t.generateMipmaps = true;
    t.minFilter = THREE.LinearMipmapLinearFilter;
    t.needsUpdate = true;
    return t;
  };
  return { map: mk(set.color, true), normalMap: mk(set.normal, false), roughnessMap: mk(set.rough, false), sizeM: set.sizeM };
}

// ---------------------------------------------------------------------------
// Height -> normal (Sobel, wrapping so the result still tiles)

export function heightToNormal(height, w, h, strength = 2, wrap = true) {
  const out = new Uint8ClampedArray(w * h * 4);
  const H = (x, y) => {
    if (wrap) { x = (x + w) % w; y = (y + h) % h; } else { x = clamp(x, 0, w - 1); y = clamp(y, 0, h - 1); }
    return height[y * w + x];
  };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const dx = (H(x + 1, y - 1) + 2 * H(x + 1, y) + H(x + 1, y + 1)) - (H(x - 1, y - 1) + 2 * H(x - 1, y) + H(x - 1, y + 1));
      const dy = (H(x - 1, y + 1) + 2 * H(x, y + 1) + H(x + 1, y + 1)) - (H(x - 1, y - 1) + 2 * H(x, y - 1) + H(x + 1, y - 1));
      // canvas y points down (= -v), so the v gradient is -dy
      let nx = -dx * strength, ny = dy * strength, nz = 1;
      const l = Math.hypot(nx, ny, nz);
      const i = (y * w + x) * 4;
      out[i] = (nx / l * 0.5 + 0.5) * 255; out[i + 1] = (ny / l * 0.5 + 0.5) * 255; out[i + 2] = (nz / l * 0.5 + 0.5) * 255; out[i + 3] = 255;
    }
  }
  const c = makeCanvas(w, h);
  c.getContext('2d').putImageData(new ImageData(out, w, h), 0, 0);
  return c;
}

function grayCanvas(values, w, h) {
  const out = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { const v = clamp(values[i]) * 255; out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = v; out[i * 4 + 3] = 255; }
  const c = makeCanvas(w, h);
  c.getContext('2d').putImageData(new ImageData(out, w, h), 0, 0);
  return c;
}

function colorCanvas(rgb, w, h) {
  const out = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) { out[i * 4] = rgb[i * 3]; out[i * 4 + 1] = rgb[i * 3 + 1]; out[i * 4 + 2] = rgb[i * 3 + 2]; out[i * 4 + 3] = 255; }
  const c = makeCanvas(w, h);
  c.getContext('2d').putImageData(new ImageData(out, w, h), 0, 0);
  return c;
}

/** Common pixel loop: shade(x, y) -> [r, g, b, height, rough] */
function paint(w, h, sizeM, shade, { normalStrength = 2 } = {}) {
  const rgb = new Float32Array(w * h * 3), hgt = new Float32Array(w * h), rough = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, g, b, hh, ro] = shade(x, y);
      const i = y * w + x;
      rgb[i * 3] = r; rgb[i * 3 + 1] = g; rgb[i * 3 + 2] = b; hgt[i] = hh; rough[i] = ro;
    }
  }
  return { color: colorCanvas(rgb, w, h), normal: heightToNormal(hgt, w, h, normalStrength), rough: grayCanvas(rough, w, h), sizeM };
}

const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const scale = (c, s) => [c[0] * s, c[1] * s, c[2] * s];

// ---------------------------------------------------------------------------
// Roof coverings

/**
 * Architectural (laminated) asphalt shingles.
 * Tile = 36" wide x 4 courses at 5-5/8" exposure.
 */
export function architecturalShingle({ palette = ['#3a3d42', '#2b2d30', '#4d5157', '#1f2124'], seed = 11, exposureIn = 5.625, res = 2048 } = {}) {
  const key = 'arch:' + palette.join() + seed + exposureIn + res;
  if (cache.has(key)) return cache.get(key);
  const courses = 4;
  const sizeM = [inToM(36), inToM(exposureIn) * courses];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const ch = h / courses;
  const pxPerM = w / sizeM[0];
  const r = rng(seed);
  const pal = palette.map(hexToRgb);
  const noise = makeNoise(seed, 32);
  // per course: list of teeth [x0, x1, colourIndex, depth]
  const layout = [];
  for (let c = 0; c < courses; c++) {
    const teeth = [];
    let x = 0;
    while (x < w) {
      const tw = (0.07 + r() * 0.16) * pxPerM;
      const gap = (0.015 + r() * 0.06) * pxPerM;
      teeth.push({ x0: x, x1: Math.min(w, x + tw), col: Math.floor(r() * pal.length), shade: 0.85 + r() * 0.3, reach: 0.5 + r() * 0.12 });
      x += tw + gap;
    }
    // shingle ends (each shingle is ~39 3/8"), staggered per course
    const joints = [];
    const L = inToM(39.375) * pxPerM;
    for (let j = (c * 0.37 % 1) * L; j < w; j += L) joints.push(j);
    layout.push({ teeth, joints, base: Math.floor(r() * pal.length) });
  }
  const set = paint(w, h, sizeM, (x, y) => {
    const ci = courses - 1 - Math.floor(y / ch);          // course index from bottom
    const fy = 1 - (y % ch) / ch;                           // 0 at butt edge, 1 at top of exposure
    const L = layout[ci];
    const gx = x / w * 32, gy = y / h * 32;
    const blotch = noise.fbm(gx * 2, gy * 2, 3);
    const gran = r();
    let col = pal[L.base], height = 0.55 + fy * 0.15, ro = 0.86;
    // tooth region (lower part of exposure)
    let tooth = null;
    for (const t of L.teeth) if (x >= t.x0 && x < t.x1) { tooth = t; break; }
    const inTeethZone = fy < (tooth ? tooth.reach : 0.55);
    if (inTeethZone) {
      if (tooth) { col = scale(pal[tooth.col], tooth.shade); height = 0.75 + fy * 0.1; }
      else { col = scale(pal[1 % pal.length], 0.55); height = 0.35; ro = 0.9; } // backer / shadow band
    } else {
      col = mix(pal[L.base], pal[(L.base + 1) % pal.length], blotch);
      height = 0.6 + fy * 0.12;
    }
    // darker shadow line right under the headlap
    if (Math.abs(fy - 0.56) < 0.03) { col = scale(col, 0.82); }
    // butt edge shadow
    if (fy < 0.035) { col = scale(col, 0.6); height -= 0.25; }
    // shingle joints
    for (const j of L.joints) if (Math.abs(x - j) < 1.5) { col = scale(col, 0.5); height -= 0.2; }
    // granules
    const g = 0.86 + gran * 0.28;
    col = scale(col, g * (0.92 + blotch * 0.16));
    if (gran > 0.985) col = scale(pal[(ci + 2) % pal.length], 1.25);
    return [col[0], col[1], col[2], height + gran * 0.08, ro + (gran - 0.5) * 0.08];
  }, { normalStrength: 3 });
  set.exposureM = inToM(exposureIn);
  cache.set(key, set);
  return set;
}

/** Three-tab shingles: 12" tabs, 1/4" cut-outs. Used for the old roof too. */
export function threeTabShingle({ palette = ['#4b4b48', '#3f3f3c', '#5a5955'], seed = 5, worn = 0, exposureIn = 5, res = 1536 } = {}) {
  const key = 'tab:' + palette.join() + seed + worn + res;
  if (cache.has(key)) return cache.get(key);
  const courses = 4;
  const sizeM = [inToM(36), inToM(exposureIn) * courses];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const ch = h / courses, pxPerM = w / sizeM[0];
  const tab = inToM(12) * pxPerM, slot = inToM(0.25) * pxPerM;
  const r = rng(seed);
  const pal = palette.map(hexToRgb);
  const noise = makeNoise(seed + 3, 32);
  const set = paint(w, h, sizeM, (x, y) => {
    const ci = courses - 1 - Math.floor(y / ch);
    const fy = 1 - (y % ch) / ch;
    const xs = (x + (ci % 2) * tab * 0.5) % (tab * 3);
    const xt = xs % tab;
    const tabIdx = Math.floor(xs / tab);
    const gx = x / w * 32, gy = y / h * 32;
    const n1 = noise.fbm(gx * 2, gy * 2, 4);
    let col = mix(pal[0], pal[(tabIdx + ci) % pal.length], 0.5 + (n1 - 0.5) * 0.6);
    let height = 0.6 + fy * 0.2, ro = 0.88;
    if (fy < 0.62 && xt < slot) { col = scale(pal[1], 0.4); height = 0.2; } // cut-out
    if (fy < 0.03) { col = scale(col, 0.6); height -= 0.3; }
    const gran = r();
    col = scale(col, 0.85 + gran * 0.3);
    if (worn) {
      // granule loss, algae streaks running down-slope, faded patches
      const streak = noise.fbm(gx * 6, gy * 0.6, 3);
      if (streak > 0.62) col = scale(col, 1 - (streak - 0.62) * 1.6 * worn);
      const bald = noise.fbm(gx * 3 + 11, gy * 3, 3);
      if (bald > 0.66) col = mix(col, [70, 60, 52], (bald - 0.66) * 2.5 * worn);
      col = mix(col, [150, 145, 135], 0.18 * worn * n1);
      ro += 0.05 * worn;
    }
    return [col[0], col[1], col[2], height + gran * 0.06, ro];
  }, { normalStrength: 3 });
  set.exposureM = inToM(exposureIn);
  cache.set(key, set);
  return set;
}

/** Standing seam metal: 16" panels, 1" seams. */
export function standingSeam({ color = '#40464d', seed = 9, panelIn = 16, res = 1024 } = {}) {
  const key = 'seam:' + color + seed + panelIn + res;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [inToM(panelIn) * 2, 1.0];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const base = hexToRgb(color);
  const noise = makeNoise(seed, 16);
  const pw = w / 2;
  const set = paint(w, h, sizeM, (x, y) => {
    const px = x % pw;
    const d = Math.min(px, pw - px) / pw; // 0 at seam
    const seam = Math.exp(-Math.pow(d * 60, 2));
    const stiff = Math.exp(-Math.pow((d - 0.18) * 80, 2)) + Math.exp(-Math.pow((d - 0.32) * 80, 2));
    const oil = noise.fbm(x / w * 16, y / h * 16, 2);
    const shade = 0.96 + oil * 0.08 + seam * 0.05;
    return [base[0] * shade, base[1] * shade, base[2] * shade, seam * 1.0 + stiff * 0.08 + oil * 0.02, 0.38 + oil * 0.08];
  }, { normalStrength: 6 });
  set.metal = true;
  cache.set(key, set);
  return set;
}

/** Clay / concrete S-tile. */
export function clayTile({ palette = ['#a4583a', '#b86b45', '#8d4a31'], seed = 4, res = 1024 } = {}) {
  const key = 'tile:' + palette.join() + seed + res;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [inToM(12) * 3, inToM(13) * 3];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const cw = w / 3, ch = h / 3;
  const pal = palette.map(hexToRgb);
  const r = rng(seed); const noise = makeNoise(seed, 32);
  const tint = Array.from({ length: 9 }, () => [Math.floor(r() * pal.length), 0.9 + r() * 0.2]);
  const set = paint(w, h, sizeM, (x, y) => {
    const ci = 2 - Math.floor(y / ch), ti = Math.floor(x / cw);
    const fx = (x % cw) / cw, fy = 1 - (y % ch) / ch;
    const wave = Math.sin(fx * Math.PI * 2 - Math.PI / 2) * 0.5 + 0.5;
    const [pi, s] = tint[(ci * 3 + ti) % 9];
    const n = noise.fbm(x / w * 24, y / h * 24, 3);
    let col = scale(pal[pi], s * (0.75 + wave * 0.35) * (0.92 + n * 0.16));
    let height = wave * 0.9 + fy * 0.25;
    if (fy < 0.04) { col = scale(col, 0.5); height -= 0.3; }
    return [col[0], col[1], col[2], height, 0.62 + n * 0.1];
  }, { normalStrength: 5 });
  cache.set(key, set);
  return set;
}

/** Natural slate: 12" wide, 10" exposure, cleft surface. */
export function slate({ palette = ['#3b4048', '#454a52', '#33373e', '#4f4a52'], seed = 8, res = 1024 } = {}) {
  const key = 'slate:' + palette.join() + seed + res;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [inToM(12) * 3, inToM(10) * 3];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const cw = w / 3, ch = h / 3;
  const pal = palette.map(hexToRgb);
  const r = rng(seed); const noise = makeNoise(seed, 32);
  const tint = Array.from({ length: 9 }, () => [Math.floor(r() * pal.length), 0.88 + r() * 0.24]);
  const set = paint(w, h, sizeM, (x, y) => {
    const ci = 2 - Math.floor(y / ch);
    const xs = (x + (ci % 2) * cw * 0.5) % w;
    const ti = Math.floor(xs / cw);
    const fx = (xs % cw) / cw, fy = 1 - (y % ch) / ch;
    const [pi, s] = tint[(ci * 3 + ti) % 9];
    const cleft = noise.fbm(x / w * 40, y / h * 12, 4);
    let col = scale(pal[pi], s * (0.9 + cleft * 0.2));
    let height = 0.5 + fy * 0.2 + cleft * 0.25;
    if (fx < 0.006 || fx > 0.994) { col = scale(col, 0.35); height = 0.1; }
    if (fy < 0.03) { col = scale(col, 0.5); height -= 0.3; }
    return [col[0], col[1], col[2], height, 0.55 + cleft * 0.2];
  }, { normalStrength: 4 });
  cache.set(key, set);
  return set;
}

/** Cedar shake: random widths, 7-1/2" exposure, vertical grain. */
export function cedarShake({ palette = ['#8a6a4a', '#7b5e43', '#9a7a58', '#6e5a48'], seed = 21, res = 1024 } = {}) {
  const key = 'shake:' + palette.join() + seed + res;
  if (cache.has(key)) return cache.get(key);
  const courses = 3;
  const sizeM = [inToM(40), inToM(7.5) * courses];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const ch = h / courses, pxPerM = w / sizeM[0];
  const pal = palette.map(hexToRgb);
  const r = rng(seed); const noise = makeNoise(seed, 32);
  const rows = [];
  for (let c = 0; c < courses; c++) {
    const pieces = []; let x = 0;
    while (x < w) { const pw = (0.1 + r() * 0.16) * pxPerM; pieces.push({ x0: x, x1: Math.min(w, x + pw), col: Math.floor(r() * pal.length), s: 0.85 + r() * 0.3 }); x += pw; }
    rows.push(pieces);
  }
  const set = paint(w, h, sizeM, (x, y) => {
    const ci = courses - 1 - Math.floor(y / ch);
    const fy = 1 - (y % ch) / ch;
    const p = rows[ci].find((q) => x >= q.x0 && x < q.x1) || rows[ci][0];
    const grain = noise.fbm(x / w * 90, y / h * 4, 3);
    let col = scale(pal[p.col], p.s * (0.8 + grain * 0.35));
    let height = 0.5 + fy * 0.3 + grain * 0.25;
    if (x - p.x0 < 2.5) { col = scale(col, 0.35); height = 0.1; }
    if (fy < 0.03) { col = scale(col, 0.5); height -= 0.3; }
    return [col[0], col[1], col[2], height, 0.8];
  }, { normalStrength: 4 });
  cache.set(key, set);
  return set;
}

// ---------------------------------------------------------------------------
// Underlayers

/** 7/16" OSB roof sheathing, 4x8 sheets laid in staggered rows. */
export function osb({ seed = 2, fresh = false, res = 1536 } = {}) {
  const key = 'osb:' + seed + fresh + res;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [2.4384 * 2, 1.2192 * 2];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const c = makeCanvas(w, h);
  const g = c.getContext('2d', { willReadFrequently: true });
  const r = rng(seed);
  const base = fresh ? [214, 178, 122] : [176, 140, 92];
  g.fillStyle = `rgb(${base})`; g.fillRect(0, 0, w, h);
  const pxPerM = w / sizeM[0];
  // strands
  for (let i = 0; i < 9000; i++) {
    const x = r() * w, y = r() * h;
    const len = (0.04 + r() * 0.08) * pxPerM, wid = (0.006 + r() * 0.012) * pxPerM;
    const a = (r() - 0.5) * 1.2;
    const t = 0.75 + r() * 0.45;
    g.save(); g.translate(x, y); g.rotate(a);
    g.fillStyle = `rgb(${base[0] * t},${base[1] * t * 0.97},${base[2] * t * 0.9})`;
    for (const [ox, oy] of [[0, 0], [w, 0], [-w, 0], [0, h], [0, -h]]) { g.fillRect(-len / 2 + ox, -wid / 2 + oy, len, wid); }
    g.restore();
  }
  // panel seams (1/8" gaps), rows staggered by half a sheet
  g.fillStyle = 'rgba(40,28,16,0.85)';
  const sw = 2.4384 * pxPerM, sh = 1.2192 * pxPerM, gap = Math.max(2, 0.003 * pxPerM);
  g.fillRect(0, 0, w, gap); g.fillRect(0, sh, w, gap);
  for (const [row, off] of [[0, 0], [1, sw / 2]]) {
    for (let x = off; x < w + 1; x += sw) g.fillRect(x % w, row * sh, gap, sh);
  }
  // nail lines over rafters at 24" o.c.
  g.fillStyle = 'rgba(60,60,70,0.55)';
  for (let x = 0; x < w; x += inToM(24) * pxPerM) for (let y = 4; y < h; y += inToM(6) * pxPerM) g.fillRect(x, y, 3, 3);
  // grade stamp (generic)
  g.save(); g.fillStyle = 'rgba(30,60,140,0.5)'; g.font = `bold ${Math.round(0.035 * pxPerM)}px sans-serif`;
  g.fillText('RATED SHEATHING  24/16  7/16 CAT  EXPOSURE 1', 0.4 * pxPerM, 0.5 * pxPerM);
  g.fillText('RATED SHEATHING  24/16  7/16 CAT  EXPOSURE 1', 0.4 * pxPerM + sw / 2, 0.5 * pxPerM + sh);
  g.restore();
  const set = fromColorCanvas(c, sizeM, { strength: 1.5, roughBase: 0.8 });
  cache.set(key, set);
  return set;
}

/** Synthetic underlayment, 48" rolls with 4" laps, printed lap and fastener guides. */
export function syntheticUnderlayment({ color = '#8d9399', print = '#2b4f86', res = 1536 } = {}) {
  const key = 'syn:' + color + print + res;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [2.0, inToM(44)];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const pxPerM = w / sizeM[0];
  const c = makeCanvas(w, h), g = c.getContext('2d', { willReadFrequently: true });
  const base = hexToRgb(color);
  g.fillStyle = color; g.fillRect(0, 0, w, h);
  // woven polypropylene
  const img = g.getImageData(0, 0, w, h);
  const r = rng(3);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    const weave = ((x >> 2) + (y >> 2)) % 2 ? 0.96 : 1.04;
    const j = weave * (0.95 + r() * 0.1);
    img.data[i] = base[0] * j; img.data[i + 1] = base[1] * j; img.data[i + 2] = base[2] * j;
  }
  g.putImageData(img, 0, 0);
  // lap line 4" from the top edge + top edge shadow from the overlapping roll
  g.fillStyle = 'rgba(0,0,0,0.25)'; g.fillRect(0, h - 6, w, 6);
  g.strokeStyle = print; g.lineWidth = 3; g.setLineDash([24, 12]);
  g.beginPath(); g.moveTo(0, inToM(4) * pxPerM); g.lineTo(w, inToM(4) * pxPerM); g.stroke();
  g.setLineDash([]);
  // fastener circles
  g.lineWidth = 2;
  for (let y = inToM(12) * pxPerM; y < h - 10; y += inToM(12) * pxPerM) {
    for (let x = inToM(6) * pxPerM; x < w; x += inToM(12) * pxPerM) { g.beginPath(); g.arc(x, y, 0.012 * pxPerM, 0, Math.PI * 2); g.stroke(); }
  }
  g.fillStyle = print; g.font = `bold ${Math.round(0.04 * pxPerM)}px sans-serif`;
  for (let x = 0.1 * pxPerM; x < w; x += 1.0 * pxPerM) g.fillText('SYNTHETIC UNDERLAYMENT · 4" LAP', x, h * 0.55);
  const set = fromColorCanvas(c, sizeM, { strength: 0.8, roughBase: 0.7 });
  cache.set(key, set);
  return set;
}

/** #30 asphalt-saturated felt (old roof). */
export function felt({ res = 1024 } = {}) {
  if (cache.has('felt' + res)) return cache.get('felt' + res);
  const sizeM = [2.0, inToM(34)];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const noise = makeNoise(17, 32); const r = rng(17);
  const set = paint(w, h, sizeM, (x, y) => {
    const n = noise.fbm(x / w * 48, y / h * 24, 3);
    let v = 38 + n * 22 + r() * 8;
    const line = Math.abs(y - h * 0.12) < 1.5 || Math.abs(y - h * 0.88) < 1.5;
    if (line) v = 150;
    return [v, v, v * 1.02, n * 0.4, 0.75];
  });
  cache.set('felt' + res, set);
  return set;
}

/** Ice & water barrier: self-adhered, granular or smooth film, 36" rolls. */
export function iceWater({ color = '#2d3138', print = '#c9ced6', granular = true, res = 1024 } = {}) {
  const key = 'iw:' + color + print + granular + res;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [2.0, inToM(33)];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const pxPerM = w / sizeM[0];
  const c = makeCanvas(w, h), g = c.getContext('2d', { willReadFrequently: true });
  g.fillStyle = color; g.fillRect(0, 0, w, h);
  if (granular) {
    const img = g.getImageData(0, 0, w, h); const r = rng(9); const base = hexToRgb(color);
    for (let i = 0; i < w * h; i++) { const j = 0.8 + r() * 0.4; img.data[i * 4] = base[0] * j; img.data[i * 4 + 1] = base[1] * j; img.data[i * 4 + 2] = base[2] * j; }
    g.putImageData(img, 0, 0);
  }
  g.fillStyle = 'rgba(0,0,0,0.3)'; g.fillRect(0, h - 5, w, 5);
  g.fillStyle = print; g.globalAlpha = 0.8; g.font = `bold ${Math.round(0.045 * pxPerM)}px sans-serif`;
  for (let x = 0.15 * pxPerM; x < w; x += 1.0 * pxPerM) g.fillText('ICE & WATER BARRIER', x, h * 0.5);
  g.globalAlpha = 1;
  const set = fromColorCanvas(c, sizeM, { strength: granular ? 1.2 : 0.3, roughBase: granular ? 0.85 : 0.45 });
  cache.set(key, set);
  return set;
}

/** Starter strip: dark asphalt with a factory sealant line. */
export function starterStrip({ res = 512 } = {}) {
  if (cache.has('starter' + res)) return cache.get('starter' + res);
  const sizeM = [1.0, inToM(7)];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const r = rng(31);
  const set = paint(w, h, sizeM, (x, y) => {
    let v = 46 + r() * 22;
    let hh = 0.5 + r() * 0.1;
    if (Math.abs(y - h * 0.3) < h * 0.05) { v = 22; hh = 0.7; }
    return [v, v, v, hh, 0.85];
  }, { normalStrength: 2 });
  cache.set('starter' + res, set);
  return set;
}

/** Hip & ridge cap shingles; u runs along the ridge, 5-5/8" exposure per piece. */
export function ridgeCap({ palette = ['#3a3d42', '#2b2d30', '#4d5157'], seed = 13, res = 1024 } = {}) {
  const key = 'cap:' + palette.join() + seed + res;
  if (cache.has(key)) return cache.get(key);
  const pieces = 8;
  const sizeM = [inToM(5.625) * pieces, 0.16]; // 5-5/8" exposure per cap piece
  const w = res, h = Math.max(64, Math.round(res * sizeM[1] / sizeM[0]));
  const pal = palette.map(hexToRgb); const r = rng(seed);
  const tints = Array.from({ length: pieces }, () => [Math.floor(r() * pal.length), 0.9 + r() * 0.2]);
  const pw = w / pieces;
  const set = paint(w, h, sizeM, (x, y) => {
    const pi = Math.floor(x / pw), fx = (x % pw) / pw;
    const [ci, s] = tints[pi];
    let col = scale(pal[ci], s * (0.85 + r() * 0.3));
    let hh = 0.5 + fx * 0.3;
    if (fx > 0.965) { col = scale(col, 0.55); hh = 0.1; }
    return [col[0], col[1], col[2], hh, 0.86];
  }, { normalStrength: 3 });
  cache.set(key, set);
  return set;
}

// ---------------------------------------------------------------------------
// House exterior

export function lapSiding({ revealIn = 7, res = 512 } = {}) {
  const key = 'siding' + revealIn + res;
  if (cache.has(key)) return cache.get(key);
  const boards = 6;
  const sizeM = [1.0, inToM(revealIn) * boards];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const bh = h / boards; const noise = makeNoise(41, 16);
  const set = paint(w, h, sizeM, (x, y) => {
    const fy = 1 - (y % bh) / bh;
    const grain = noise.fbm(x / w * 40, y / h * 4, 2);
    let v = 235 - (1 - fy) * 14 + grain * 10;
    let hh = fy * 0.6;
    if (fy < 0.06) { v *= 0.72; hh = 0.9; }
    return [v, v, v, hh, 0.55];
  }, { normalStrength: 2.5 });
  cache.set(key, set);
  return set;
}

export function grass({ res = 512 } = {}) {
  if (cache.has('grass' + res)) return cache.get('grass' + res);
  const sizeM = [3, 3];
  const noise = makeNoise(51, 32); const r = rng(51);
  const set = paint(res, res, sizeM, (x, y) => {
    const n = noise.fbm(x / res * 32, y / res * 32, 4);
    const j = 0.75 + r() * 0.5;
    return [(70 + n * 40) * j, (105 + n * 50) * j, (48 + n * 20) * j, r(), 0.95];
  }, { normalStrength: 1 });
  cache.set('grass' + res, set);
  return set;
}

export function concrete({ res = 512, tone = 168 } = {}) {
  const key = 'concrete' + res + tone;
  if (cache.has(key)) return cache.get(key);
  const sizeM = [2, 2];
  const noise = makeNoise(61, 32); const r = rng(61);
  const set = paint(res, res, sizeM, (x, y) => {
    const n = noise.fbm(x / res * 32, y / res * 32, 4);
    const v = tone * (0.88 + n * 0.2) * (0.96 + r() * 0.08);
    return [v, v * 0.99, v * 0.97, n * 0.3, 0.9];
  }, { normalStrength: 0.8 });
  cache.set(key, set);
  return set;
}

export function garageDoor({ res = 512 } = {}) {
  if (cache.has('garage' + res)) return cache.get('garage' + res);
  const sizeM = [4.9, 2.13];
  const w = res, h = Math.round(res * sizeM[1] / sizeM[0]);
  const set = paint(w, h, sizeM, (x, y) => {
    const fx = (x / w) * 8 % 1, fy = (y / h) * 4 % 1;
    const edge = Math.min(fx, 1 - fx, fy * 2, (1 - fy) * 2);
    let v = 240, hh = 0.5;
    if (edge < 0.06) { v = 215; hh = 0.2; }
    if (fy > 0.97 || fy < 0.02) { v = 170; hh = 0.0; }
    return [v, v, v * 0.98, hh, 0.5];
  }, { normalStrength: 3 });
  cache.set('garage' + res, set);
  return set;
}

// ---------------------------------------------------------------------------
// Supplier / uploaded swatch photos

/**
 * Build a TexSet from a photo.
 * @param {HTMLImageElement|ImageBitmap|HTMLCanvasElement} img
 * @param {object} o  widthIn/heightIn (real size the photo shows), seamless, brightness, contrast, saturation, hue, relief, roughness, metal
 */
export function fromPhoto(img, o = {}) {
  const maxSide = o.maxSide ?? 2048;
  const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
  const k = Math.min(1, maxSide / Math.max(iw, ih));
  const w = Math.max(16, Math.round(iw * k)), h = Math.max(16, Math.round(ih * k));
  const c = makeCanvas(w, h), g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(img, 0, 0, w, h);
  let data = g.getImageData(0, 0, w, h);
  adjustColor(data.data, o);
  if (o.seamless) data = makeSeamless(data, o.seamlessBlend ?? 0.18);
  g.putImageData(data, 0, 0);
  const widthIn = o.widthIn || 36;
  const heightIn = o.heightIn || widthIn * h / w;
  const set = fromColorCanvas(c, [inToM(widthIn), inToM(heightIn)], { strength: o.relief ?? 2.0, roughBase: o.roughness ?? (o.metal ? 0.38 : 0.86), highPass: true });
  set.metal = !!o.metal;
  return set;
}

/** Brightness / contrast / saturation / hue adjustments (in place). */
export function adjustColor(px, { brightness = 0, contrast = 0, saturation = 0, hue = 0 } = {}) {
  if (!brightness && !contrast && !saturation && !hue) return;
  const cf = (1 + contrast);
  const cosH = Math.cos(hue * Math.PI / 180), sinH = Math.sin(hue * Math.PI / 180);
  for (let i = 0; i < px.length; i += 4) {
    let r = px[i], g = px[i + 1], b = px[i + 2];
    if (hue) {
      // rotate around the grey axis (YIQ)
      const y = 0.299 * r + 0.587 * g + 0.114 * b;
      const iq = 0.596 * r - 0.274 * g - 0.322 * b, q = 0.211 * r - 0.523 * g + 0.312 * b;
      const i2 = iq * cosH - q * sinH, q2 = iq * sinH + q * cosH;
      r = y + 0.956 * i2 + 0.621 * q2; g = y - 0.272 * i2 - 0.647 * q2; b = y - 1.106 * i2 + 1.703 * q2;
    }
    const l = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    r = l + (r - l) * (1 + saturation); g = l + (g - l) * (1 + saturation); b = l + (b - l) * (1 + saturation);
    r = (r - 128) * cf + 128 + brightness * 255; g = (g - 128) * cf + 128 + brightness * 255; b = (b - 128) * cf + 128 + brightness * 255;
    px[i] = r; px[i + 1] = g; px[i + 2] = b;
  }
}

/**
 * Make an image tile: blend it with a copy shifted by half its size, weighting
 * the original in the middle and the shifted copy (which wraps cleanly) at the edges.
 */
export function makeSeamless(data, blend = 0.18) {
  const { width: w, height: h } = data;
  const src = data.data;
  const out = new ImageData(w, h);
  const bw = Math.max(1, Math.round(w * blend)), bh = Math.max(1, Math.round(h * blend));
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const ex = Math.min(x, w - 1 - x) / bw, ey = Math.min(y, h - 1 - y) / bh;
      const m = clamp(Math.min(ex, ey));
      const t = m * m * (3 - 2 * m);
      const i = (y * w + x) * 4;
      const j = (((y + (h >> 1)) % h) * w + ((x + (w >> 1)) % w)) * 4;
      for (let k = 0; k < 3; k++) out.data[i + k] = src[i + k] * t + src[j + k] * (1 - t);
      out.data[i + 3] = 255;
    }
  }
  return out;
}

/** Derive normal + roughness maps from a colour canvas using its luminance as height. */
export function fromColorCanvas(c, sizeM, { strength = 2, roughBase = 0.85, highPass = false } = {}) {
  const w = c.width, h = c.height;
  const px = c.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, w, h).data;
  const lum = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) lum[i] = (0.2126 * px[i * 4] + 0.7152 * px[i * 4 + 1] + 0.0722 * px[i * 4 + 2]) / 255;
  let height = lum;
  if (highPass) {
    // remove broad lighting gradients baked into photos so only surface detail drives the normal map
    const blur = boxBlur(lum, w, h, Math.max(4, Math.round(w / 64)));
    height = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) height[i] = 0.5 + (lum[i] - blur[i]);
  }
  const rough = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) rough[i] = clamp(roughBase + (0.5 - height[i]) * 0.12);
  return { color: c, normal: heightToNormal(height, w, h, strength * 2.5), rough: grayCanvas(rough, w, h), sizeM };
}

function boxBlur(src, w, h, r) {
  const tmp = new Float32Array(w * h), out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    let s = 0;
    for (let x = -r; x <= r; x++) s += src[y * w + ((x + w) % w)];
    for (let x = 0; x < w; x++) {
      tmp[y * w + x] = s / (2 * r + 1);
      s += src[y * w + ((x + r + 1) % w)] - src[y * w + ((x - r + w) % w)];
    }
  }
  for (let x = 0; x < w; x++) {
    let s = 0;
    for (let y = -r; y <= r; y++) s += tmp[((y + h) % h) * w + x];
    for (let y = 0; y < h; y++) {
      out[y * w + x] = s / (2 * r + 1);
      s += tmp[((y + r + 1) % h) * w + x] - tmp[((y - r + h) % h) * w + x];
    }
  }
  return out;
}

/** Small preview swatch (data URL) for the catalog grid. */
export function swatchDataURL(set, size = 96) {
  const c = makeCanvas(size, size), g = c.getContext('2d');
  g.drawImage(set.color, 0, 0, set.color.width, Math.min(set.color.height, set.color.width), 0, 0, size, size);
  return c.toDataURL('image/jpeg', 0.85);
}

/** Generate the TexSet for a catalog product's procedural recipe. */
export function proceduralFor(recipe = {}) {
  const k = recipe.kind;
  if (k === 'architectural') return architecturalShingle(recipe);
  if (k === 'threeTab') return threeTabShingle(recipe);
  if (k === 'standingSeam') return standingSeam(recipe);
  if (k === 'clayTile') return clayTile(recipe);
  if (k === 'slate') return slate(recipe);
  if (k === 'cedarShake') return cedarShake(recipe);
  if (k === 'synthetic') return syntheticUnderlayment(recipe);
  if (k === 'felt') return felt(recipe);
  if (k === 'iceWater') return iceWater(recipe);
  return architecturalShingle(recipe);
}
