// Shared helpers: units, seeded random numbers, tileable noise, easing.
// Everything here is dependency-free so it can be reused by the server-side tooling.

export const IN = 0.0254;           // metres per inch
export const FT = 0.3048;           // metres per foot
export const SQUARE_M2 = 9.290304;  // one roofing "square" = 100 sq ft

export const inToM = (inches) => inches * IN;
export const mToIn = (m) => m / IN;

/** Format metres as feet-inches, e.g. 5.625" or 12' 4". */
export function fmtFtIn(m) {
  const totalIn = m / IN;
  if (Math.abs(totalIn) < 12) return `${roundFrac(totalIn)}"`;
  const ft = Math.floor(totalIn / 12);
  const inch = totalIn - ft * 12;
  return inch < 0.06 ? `${ft}'` : `${ft}' ${roundFrac(inch)}"`;
}

/** Round inches to the nearest 1/8 and print as a mixed fraction. */
export function roundFrac(x) {
  const eighths = Math.round(x * 8);
  const whole = Math.floor(eighths / 8);
  let rem = eighths - whole * 8;
  if (rem === 0) return `${whole}`;
  let den = 8;
  while (rem % 2 === 0) { rem /= 2; den /= 2; }
  return whole ? `${whole} ${rem}/${den}` : `${rem}/${den}`;
}

/** Pitch as rise per 12 of run, e.g. 6 -> "6/12". */
export const pitchLabel = (rise) => `${Math.round(rise * 10) / 10}/12`;
export const pitchToRad = (rise) => Math.atan(rise / 12);

// ---------------------------------------------------------------------------
// Seeded PRNG (mulberry32)
export function rng(seed = 1) {
  let a = seed >>> 0;
  return function next() {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

// ---------------------------------------------------------------------------
// Tileable value noise. `period` is the lattice size in cells, so the noise
// repeats every `period` cells and textures built from it tile seamlessly.
export function makeNoise(seed = 7, period = 64) {
  const r = rng(seed);
  const table = new Float32Array(period * period);
  for (let i = 0; i < table.length; i++) table[i] = r();
  const lerp = (a, b, t) => a + (b - a) * t;
  const fade = (t) => t * t * (3 - 2 * t);
  const at = (x, y) => table[((y % period + period) % period) * period + ((x % period + period) % period)];
  function noise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = fade(x - xi), yf = fade(y - yi);
    return lerp(lerp(at(xi, yi), at(xi + 1, yi), xf), lerp(at(xi, yi + 1), at(xi + 1, yi + 1), xf), yf);
  }
  /** Fractal noise; x, y in lattice units; octaves double the frequency (period stays integer). */
  function fbm(x, y, octaves = 4) {
    let sum = 0, amp = 0.5, freq = 1, norm = 0;
    for (let o = 0; o < octaves; o++) {
      sum += amp * noise(x * freq, y * freq);
      norm += amp; amp *= 0.5; freq *= 2;
    }
    return sum / norm;
  }
  return { noise, fbm, period };
}

// ---------------------------------------------------------------------------
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, t) => a + (b - a) * t;
export const smoothstep = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const v = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

export function rgbToHex([r, g, b]) {
  return '#' + [r, g, b].map((x) => clamp(Math.round(x), 0, 255).toString(16).padStart(2, '0')).join('');
}

export function slugify(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'item';
}

/** Small event emitter used by the UI and the timeline. */
export class Emitter {
  constructor() { this._h = new Map(); }
  on(type, fn) { (this._h.get(type) || this._h.set(type, new Set()).get(type)).add(fn); return () => this.off(type, fn); }
  off(type, fn) { this._h.get(type)?.delete(fn); }
  emit(type, payload) { this._h.get(type)?.forEach((fn) => fn(payload)); }
}
