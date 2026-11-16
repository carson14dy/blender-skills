// Metal panel profiles (019): the shared profile table, the ribbed covering surface,
// the metal hip / ridge cap profile and the rake trim. Pure: no DOM, and three.js only
// through the roof-geometry.js helpers, so node --test can import it.
//
// PROFILES is the same JSON text as PANEL_PROFILES in roof-blender/scripts/roof_core.py
// (tests/profiles.test.mjs compares them). Points are [u, h] in inches within one period:
// u across the slope (the plane's u axis, parallel to the eave; u = 0 at the plane's
// u-origin), h above the pan. Ribs run up the slope.

import { clipHalf, makeGeometry, inwardDir2 } from './roof-geometry.js';

const IN = 0.0254;
const EPS = 1e-6;

export const PROFILES = JSON.parse(String.raw`{
 "proRib":     {"periodIn": 9,    "points": [[0,0.75],[0.375,0.75],[0.875,0],[2.7,0],[3.0,0.09],[3.3,0],[5.7,0],[6.0,0.09],[6.3,0],[8.125,0],[8.625,0.75],[9,0.75]], "note": "Menards Pro-Rib: 36 in. cover, major ribs 9 in. o.c., 3/4 in. high (Menards spec); rib top 3/4 in., base 1-3/4 in. and two minor ribs are assumed"},
 "proSnap":    {"periodIn": 16,   "points": [[0,0.75],[0.1875,0.75],[0.25,0],[15.75,0],[15.8125,0.75],[16,0.75]], "note": "Menards Pro-Snap: 16 in. coverage, 3/4 in. seam (Menards spec); seam top 3/8 in. assumed"},
 "corrugated": {"periodIn": 2.67, "points": [[0,0],[0.33375,0.0732],[0.6675,0.25],[1.00125,0.4268],[1.335,0.5],[1.66875,0.4268],[2.0025,0.25],[2.33625,0.0732],[2.67,0]], "note": "common 2.67 in. pitch, 1/2 in. depth: not store data"},
 "flat":       {"periodIn": 0,    "points": [], "note": "no profile"}
}`);

/** Studio texture kind -> profile name. Any other metal product, and every non-metal product, is flat. */
export const PANEL_FOR_KIND = Object.freeze({ ribbedPanel: 'proRib', standingSeam: 'proSnap', corrugatedPanel: 'corrugated' });

/** 'proRib' | 'proSnap' | 'corrugated' | 'flat' for a studio product. */
export function panelName(product) {
  if (product?.category !== 'metal') return 'flat';
  return PANEL_FOR_KIND[product?.procedural?.kind] || 'flat';
}

const maxOf = (points) => points.reduce((m, p) => Math.max(m, p[1]), 0);

/**
 * A profile in metres: { name, periodM, points: [[u, h], ...], maxH }, or null for flat.
 * ribSpacingIn / ribHeightIn scale the proRib table: u by ribSpacing / 9, h by ribHeight / 0.75.
 */
export function panelProfile(name, { ribSpacingIn, ribHeightIn } = {}) {
  const t = PROFILES[name];
  if (!t || !(t.periodIn > 0) || t.points.length < 2) return null;
  let su = 1, sh = 1;
  if (name === 'proRib') {
    if (ribSpacingIn > 0) su = ribSpacingIn / t.periodIn;
    if (ribHeightIn > 0) sh = ribHeightIn / maxOf(t.points);
  }
  const points = t.points.map(([u, h]) => [u * su * IN, h * sh * IN]);
  return { name, periodM: t.periodIn * su * IN, points, maxH: maxOf(points) };
}

/** The profile drawn for a studio product (null: flat panels, today's surface). */
export function profileFor(product) {
  const name = panelName(product);
  return name === 'flat' ? null : panelProfile(name, product.procedural || {});
}

/**
 * Covering surface with the panel profile as real geometry. Each plane polygon is sliced
 * into strips between consecutive profile breakpoints, repeated across its u range; h(u) is
 * linear inside a strip, so every strip stays planar. Normal: normalize(n - slope * h axis).
 * UVs (u, v) in metres and the build attributes (aUp = v, aAlong = u / uMax) as buildSurface.
 * @param {{plane: RoofPlane, polys: number[][][]}[]} parts
 * @param {{offset?: number, profile: {periodM: number, points: number[][]}}} o  offset = the pan (m above the rafters)
 */
export function ribbedSurface(parts, { offset = 0, profile } = {}) {
  const pos = [], nor = [], uv = [], up = [], along = [];
  const period = profile.periodM, pts = profile.points;
  for (const { plane, polys } of parts) {
    const { origin: o, h: ha, b, n } = plane;
    const aOf = (u) => (plane.uMax > EPS ? Math.min(0.9999, u / plane.uMax) : 0);
    for (const poly of polys) {
      let lo = Infinity, hi = -Infinity;
      for (const q of poly) { lo = Math.min(lo, q[0]); hi = Math.max(hi, q[0]); }
      for (let k = Math.floor(lo / period); k * period < hi; k++) {
        for (let j = 0; j + 1 < pts.length; j++) {
          const u0 = k * period + pts[j][0], u1 = k * period + pts[j + 1][0];
          if (u1 - u0 < EPS || u1 <= lo || u0 >= hi) continue;
          const strip = dedupe(clipHalf(clipHalf(poly, [1, 0, -u0]), [-1, 0, u1]));
          if (strip.length < 3) continue;
          const h0 = pts[j][1], slope = (pts[j + 1][1] - h0) / (u1 - u0);
          let nx = n.x - slope * ha.x, ny = n.y - slope * ha.y, nz = n.z - slope * ha.z;
          const nl = Math.hypot(nx, ny, nz); nx /= nl; ny /= nl; nz /= nl;
          const pushV = ([u, v]) => {
            const h = offset + h0 + slope * (u - u0);
            pos.push(o.x + ha.x * u + b.x * v + n.x * h, o.y + ha.y * u + b.y * v + n.y * h, o.z + ha.z * u + b.z * v + n.z * h);
            nor.push(nx, ny, nz); uv.push(u, v); up.push(v); along.push(aOf(u));
          };
          for (let i = 1; i < strip.length - 1; i++) { pushV(strip[0]); pushV(strip[i]); pushV(strip[i + 1]); }
        }
      }
    }
  }
  return makeGeometry(pos, nor, uv, up, along);
}

/** Drop repeated points (a polygon vertex on a clip line comes out twice). */
function dedupe(poly) {
  const out = [];
  for (const p of poly) {
    const q = out[out.length - 1];
    if (!q || Math.abs(p[0] - q[0]) > 1e-9 || Math.abs(p[1] - q[1]) > 1e-9) out.push(p);
  }
  while (out.length > 1 && Math.abs(out[0][0] - out[out.length - 1][0]) <= 1e-9 && Math.abs(out[0][1] - out[out.length - 1][1]) <= 1e-9) out.pop();
  return out;
}

/** Height above the rafters of what sits on the ribs: the pan + the tallest rib + 3 mm. */
export const onRibs = (coveringH, profile) => coveringH + (profile?.maxH || 0) + 0.003;

/**
 * Metal hip / ridge cap profile for capGeometry: [[distance from the line, height above the rafters], ...].
 * halfWidthIn = half the cap product's widthIn (Menards Residential Ridge Cap 11.5 -> 5.75); 6 with no product.
 */
export function metalCapProfile(top, halfWidthIn = 6) {
  const w = halfWidthIn * IN;
  return [[0, top + 0.010], [w - 0.0127, top + 0.002], [w, top - 0.006]];
}

/** How far the drip edge reaches past the deck edge (m): its 1.5 mm bend plus the kick (today's 12 mm without a profile). */
export const dripReach = (edgeProfile) => 0.0015 + (edgeProfile?.kickOutIn != null ? edgeProfile.kickOutIn * IN : 0.012);

/**
 * Metal rake trim over the panel edge along every rake segment (same as rake_trim_buf in roof_core.py).
 * Cross-section from inside to outside: a top leg lying at `top` in the roof plane, its inner end
 * legIn - outIn inside the panel edge; the bend outIn past the edge, or 1/8 in. past `clear` (how far the
 * drip edge under it reaches) when that is further, so the drip edge's kick stays inside the trim; a face
 * faceIn straight down (world vertical); a hem hemIn back toward the house (horizontal). The front side looks
 * out and up (outW * (-dUp) + up * dOut; the leg the plane normal), as the drip edge. Where two rakes meet
 * (a gable peak) both ends are mitered onto the plane bisecting them, so no notch opens at the apex.
 */
export function rakeTrimGeometry(rakes, { top, clear = 0, legIn = 1.5, outIn = 0.25, faceIn = 3.5, hemIn = 0.5 } = {}) {
  const pos = [], nor = [], uv = [], up = [], al = [];
  const out = Math.max(outIn * IN, clear + 0.125 * IN);
  const dir = (E, F) => E.clone().sub(F).normalize();
  /** Slide a trim end at X along its rake (d points to X) onto the plane bisecting it and the rake that meets it there. */
  const miter = (X, d) => {
    for (const t of rakes) {
      for (const [E, F] of [[t.A, t.B], [t.B, t.A]]) {
        const e = dir(E, F);
        if (E.distanceTo(X) < 0.03 && Math.abs(e.dot(d)) < 0.999) {
          const m = d.clone().sub(e).normalize();
          return (p) => p.addScaledVector(d, X.clone().sub(p).dot(m) / d.dot(m));
        }
      }
    }
    return (p) => p;
  };
  for (const s of rakes) {
    const P = s.planes[0];
    const len = s.A.distanceTo(s.B);
    const a2 = P.from3(s.A), b2 = P.from3(s.B);
    const inward = inwardDir2(P, { a: a2, b: b2 });
    const outW = P.h.clone().multiplyScalar(-inward[0]).addScaledVector(P.b, -inward[1]);
    outW.y = 0; outW.normalize();
    const at = (q, d) => P.to3(q[0] - inward[0] * d, q[1] - inward[1] * d, top); // d: distance out past the edge
    const sec = (q, m) => {
      const leg = at(q, (outIn - legIn) * IN), bend = at(q, out);
      const foot = bend.clone(); foot.y -= faceIn * IN;
      const hem = foot.clone().addScaledVector(outW, -hemIn * IN);
      return [leg, bend, foot, hem].map(m);
    };
    const sa = sec(a2, miter(s.A, dir(s.A, s.B))), sb = sec(b2, miter(s.B, dir(s.B, s.A)));
    const normals = [P.n, outW, outW.clone().set(0, -1, 0)]; // leg up the roof, face out, hem down
    // build attributes as the panels under it (aUp = v, aAlong = u / uMax at each end)
    const k = (q) => [q[1], P.uMax > EPS ? Math.min(0.9999, q[0] / P.uMax) : 0];
    const ka = k(a2), kb = k(b2);
    const add = (p, n, u, v, kk) => { pos.push(p.x, p.y, p.z); nor.push(n.x, n.y, n.z); uv.push(u, v); up.push(kk[0]); al.push(kk[1]); };
    let w = 0;
    for (let i = 0; i < 3; i++) {
      const wl = sa[i].distanceTo(sa[i + 1]);
      if (wl < 1e-6) continue;
      const n = normals[i];
      add(sa[i], n, 0, w, ka); add(sb[i], n, len, w, kb); add(sb[i + 1], n, len, w + wl, kb);
      add(sa[i], n, 0, w, ka); add(sb[i + 1], n, len, w + wl, kb); add(sa[i + 1], n, 0, w + wl, ka);
      w += wl;
    }
  }
  return makeGeometry(pos, nor, uv, up, al);
}
