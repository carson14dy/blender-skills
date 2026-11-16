// Roof geometry engine.
//
// A roof is a list of RoofPlanes. Each plane has its own 2D frame:
//   u = horizontal distance along the eave direction (metres)
//   v = distance up the slope from the lowest point of the plane (metres)
// Every layer (deck, membranes, shingles, nails, ridge cap...) is generated
// from these frames, so shingle courses always run parallel to the eaves and
// the textures sit at real-world scale on every plane, including hips.
//
// Every surface vertex carries two attributes that drive the build animation:
//   aUp    = metres up-slope (course / roll row = floor(aUp / rowH))
//   aAlong = 0..1 position along the eave (crews work left to right)
// A fragment is visible while floor(aUp/rowH) + aAlong < uReveal.

import * as THREE from 'three';

const UP = new THREE.Vector3(0, 1, 0);
const EPS = 1e-6;

export class RoofPlane {
  /**
   * @param {THREE.Vector3[][]} tris3  triangles in world space
   * @param {THREE.Vector3} [normalHint]
   */
  constructor(tris3, normalHint, id = 0) {
    this.id = id;
    const n = normalHint ? normalHint.clone().normalize() : triNormal(tris3[0]);
    if (n.y < 0) n.negate();
    this.n = n;
    let h = new THREE.Vector3().crossVectors(UP, n);
    if (h.lengthSq() < 1e-6) h.set(1, 0, 0); // flat roof
    h.normalize();
    this.h = h;
    this.b = new THREE.Vector3().crossVectors(n, h).normalize(); // up-slope
    this.slope = Math.acos(Math.min(1, n.y)); // radians from horizontal
    const o = tris3[0][0].clone();
    // project and shift so that min(u)=min(v)=0
    let uMin = Infinity, vMin = Infinity;
    const raw = tris3.map((t) => t.map((p) => {
      const d = p.clone().sub(o);
      const uv = [d.dot(h), d.dot(this.b)];
      uMin = Math.min(uMin, uv[0]); vMin = Math.min(vMin, uv[1]);
      return uv;
    }));
    this.origin = o.clone().addScaledVector(h, uMin).addScaledVector(this.b, vMin);
    // plane offset uses the average of all points, so slightly non-planar input still works
    this.tris = raw.map((t) => t.map(([u, v]) => [u - uMin, v - vMin]));
    this.uMax = 0; this.vMax = 0;
    for (const t of this.tris) for (const [u, v] of t) { this.uMax = Math.max(this.uMax, u); this.vMax = Math.max(this.vMax, v); }
    this.area = this.tris.reduce((s, t) => s + Math.abs(area2(t)) / 2, 0);
    this.edges = boundaryEdges(this.tris).map(([a, b]) => ({ a, b, A: this.to3(a[0], a[1]), B: this.to3(b[0], b[1]), type: 'unknown', other: null }));
  }

  static fromPolygon(points3, id) {
    const n = polygonNormal(points3);
    const tmp = new RoofPlane([points3.slice(0, 3)], n, id); // frame only
    const pts2 = points3.map((p) => tmp.from3(p));
    const contour = pts2.map(([u, v]) => new THREE.Vector2(u, v));
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse();
    const idx = THREE.ShapeUtils.triangulateShape(contour, []);
    const tris3 = idx.map((f) => f.map((i) => tmp.to3(contour[i].x, contour[i].y)));
    return new RoofPlane(tris3, n, id);
  }

  to3(u, v, off = 0, target = new THREE.Vector3()) {
    return target.copy(this.origin).addScaledVector(this.h, u).addScaledVector(this.b, v).addScaledVector(this.n, off);
  }

  from3(p) {
    const d = p.clone().sub(this.origin);
    return [d.dot(this.h), d.dot(this.b)];
  }

  distance(p) { return p.clone().sub(this.origin).dot(this.n); }

  /**
   * Is (u, v) on the plane? A positive margin keeps the point that far inside the
   * plane's outer boundary (interior triangle diagonals are ignored); a negative
   * margin acts as a tolerance.
   */
  contains2(u, v, margin = 0) {
    if (margin <= 0 || !this.edges) {
      for (const t of this.tris) if (pointInTri(u, v, t, Math.min(0, margin))) return true;
      return false;
    }
    if (!this.contains2(u, v, 0)) return false;
    for (const e of this.edges) if (segDist2(u, v, e.a, e.b) < margin) return false;
    return true;
  }

  /** Polygons (2D) = this plane's triangles clipped by half-planes [a,b,c] meaning a*u + b*v + c >= 0. */
  region(halfPlanes = []) {
    const out = [];
    for (const t of this.tris) {
      let poly = t.slice();
      for (const hp of halfPlanes) { poly = clipHalf(poly, hp); if (poly.length < 3) break; }
      if (poly.length >= 3 && Math.abs(polyArea2(poly)) > 1e-8) out.push(poly);
    }
    return out;
  }
}

// ---------------------------------------------------------------------------
// Roof analysis: classify edges into eave / rake / ridge / hip / valley.

export function analyzeRoof(planes, tol = 0.03) {
  const segs = { eave: [], rake: [], ridge: [], hip: [], valley: [], top: [] };
  // shared edges are found once from each side; remember them by geometry, not by rounded keys
  // (rounding at a grid boundary gave two keys for one edge and double-counted ridges and hips)
  const sharedSeen = [];
  const sameSeg = (s, A, B) => (s.A.distanceTo(A) < tol && s.B.distanceTo(B) < tol) || (s.A.distanceTo(B) < tol && s.B.distanceTo(A) < tol);
  for (const P of planes) {
    for (const e of P.edges) {
      const mid = e.A.clone().add(e.B).multiplyScalar(0.5);
      const inward = inwardDir2(P, e);
      // look for another plane that touches this edge
      let match = null, interior = false;
      for (const Q of planes) {
        if (Q === P) continue;
        if (Math.abs(Q.distance(e.A)) > tol || Math.abs(Q.distance(e.B)) > tol) continue;
        const shared = Q.edges.find((f) => segmentsOverlap(e, f, tol));
        if (shared) { match = { Q, f: shared }; break; }
        const [mu, mv] = Q.from3(mid);
        if (Q.contains2(mu, mv, -0.01)) { match = { Q, f: null }; interior = true; break; }
      }
      const horizontal = Math.abs(e.A.y - e.B.y) < 0.01 + 0.01 * e.A.distanceTo(e.B);
      if (match) {
        e.other = match.Q;
        if (interior) { e.type = 'valley'; }
        else {
          // convexity test: step into P and check which side of Q we are on
          const [mu, mv] = P.from3(mid);
          const probe = P.to3(mu + inward[0] * 0.15, mv + inward[1] * 0.15);
          const convex = match.Q.distance(probe) < 0;
          e.type = convex ? (horizontal ? 'ridge' : 'hip') : 'valley';
        }
        if (!sharedSeen.some((s) => sameSeg(s, e.A, e.B))) {
          const seg = { A: e.A.clone(), B: e.B.clone(), planes: [P, match.Q] };
          sharedSeen.push(seg);
          segs[e.type].push(seg);
        }
      } else {
        if (horizontal) e.type = inward[1] > 0 ? 'eave' : 'top';
        else e.type = 'rake';
        segs[e.type].push({ A: e.A.clone(), B: e.B.clone(), planes: [P] });
      }
    }
  }
  return segs;
}

// ---------------------------------------------------------------------------
// Surface builders

/**
 * Build a BufferGeometry from 2D polygons on planes.
 * @param {{plane: RoofPlane, polys: number[][][]}[]} parts
 * @param {object} o  offset (m), courseH (m, enables stepped courses), stepH (m), thickness (m, adds edge walls)
 */
export function buildSurface(parts, o = {}) {
  const off = o.offset ?? 0;
  const pos = [], nor = [], uv = [], up = [], along = [];
  const p3 = new THREE.Vector3();
  const pushV = (plane, u, v, h, n) => {
    plane.to3(u, v, h, p3);
    pos.push(p3.x, p3.y, p3.z); nor.push(n.x, n.y, n.z); uv.push(u, v);
    up.push(v); along.push(plane.uMax > EPS ? Math.min(0.9999, u / plane.uMax) : 0);
  };
  for (const { plane, polys } of parts) {
    const n = plane.n;
    if (o.courseH) {
      const e = o.courseH, step = o.stepH ?? 0.005;
      const rows = Math.ceil(plane.vMax / e) + 1;
      // tilt normal of each course a little (butt end is thicker)
      const tilt = Math.atan2(step, e);
      const nc = n.clone().multiplyScalar(Math.cos(tilt)).addScaledVector(plane.b, Math.sin(tilt)).normalize();
      for (let r = 0; r < rows; r++) {
        const v0 = r * e, v1 = (r + 1) * e;
        const hOf = (v) => off + step * (1 - (v - v0) / e);
        for (const poly of polys) {
          const strip = clipHalf(clipHalf(poly, [0, 1, -v0]), [0, -1, v1]);
          if (strip.length < 3) continue;
          for (let i = 1; i < strip.length - 1; i++) {
            for (const q of [strip[0], strip[i], strip[i + 1]]) pushV(plane, q[0], q[1], hOf(q[1]), nc);
          }
          // butt edge (vertical step) along v = v0
          for (let i = 0; i < strip.length; i++) {
            const a = strip[i], b = strip[(i + 1) % strip.length];
            if (Math.abs(a[1] - v0) < 1e-5 && Math.abs(b[1] - v0) < 1e-5) {
              const nb = plane.b.clone().negate();
              const lo = off - (r === 0 ? 0.004 : 0), hi = off + step;
              // two triangles, winding so the face points down-slope
              const [x0, x1] = a[0] < b[0] ? [a, b] : [b, a];
              pushV(plane, x0[0], v0 + 1e-4, lo, nb); pushV(plane, x1[0], v0 + 1e-4, lo, nb); pushV(plane, x1[0], v0 + 1e-4, hi, nb);
              pushV(plane, x0[0], v0 + 1e-4, lo, nb); pushV(plane, x1[0], v0 + 1e-4, hi, nb); pushV(plane, x0[0], v0 + 1e-4, hi, nb);
            }
          }
        }
      }
    } else {
      for (const poly of polys) {
        for (let i = 1; i < poly.length - 1; i++) {
          for (const q of [poly[0], poly[i], poly[i + 1]]) pushV(plane, q[0], q[1], off, n);
        }
      }
    }
    if (o.thickness) {
      // side walls along the outer boundary of the region so sheets read as solid in exploded view
      const t = o.thickness;
      for (const poly of polys) {
        for (let i = 0; i < poly.length; i++) {
          const a = poly[i], b = poly[(i + 1) % poly.length];
          if (!onPlaneBoundary(plane, a, b)) continue;
          const dir = [b[0] - a[0], b[1] - a[1]];
          const len = Math.hypot(dir[0], dir[1]);
          if (len < 1e-4) continue;
          // outward in-plane normal (polygons are CCW)
          const out2 = [dir[1] / len, -dir[0] / len];
          const wn = plane.h.clone().multiplyScalar(out2[0]).addScaledVector(plane.b, out2[1]).normalize();
          const top = off + (o.courseH ? 0 : 0), bot = off - t;
          pushV(plane, a[0], a[1], bot, wn); pushV(plane, b[0], b[1], bot, wn); pushV(plane, b[0], b[1], top, wn);
          pushV(plane, a[0], a[1], bot, wn); pushV(plane, b[0], b[1], top, wn); pushV(plane, a[0], a[1], top, wn);
        }
      }
    }
  }
  return makeGeometry(pos, nor, uv, up, along);
}

/** Full coverage parts for all planes. */
export const fullParts = (planes) => planes.map((plane) => ({ plane, polys: plane.region() }));

/** Strip parts within `width` of each segment of the given kind, measured inside the plane. */
export function stripParts(planes, segs, width, { extend = 0, vMin = null } = {}) {
  const parts = [];
  for (const plane of planes) {
    const polys = [];
    for (const s of segs) {
      if (Math.abs(plane.distance(s.A)) > 0.03 || Math.abs(plane.distance(s.B)) > 0.03) continue;
      const a = plane.from3(s.A), b = plane.from3(s.B);
      const d = [b[0] - a[0], b[1] - a[1]];
      const len = Math.hypot(d[0], d[1]);
      if (len < 1e-3) continue;
      const t = [d[0] / len, d[1] / len];
      const m = [-t[1], t[0]]; // left normal
      // distance from the line within [-width, width] (the plane clip keeps the inside)
      const c0 = -(m[0] * a[0] + m[1] * a[1]);
      const hp = [
        [m[0], m[1], c0 + width],
        [-m[0], -m[1], -c0 + width],
        [t[0], t[1], -(t[0] * a[0] + t[1] * a[1]) + extend],
        [-t[0], -t[1], (t[0] * b[0] + t[1] * b[1]) + extend],
      ];
      // vMin: keep only what lies this far up the slope, so a lapping strip is not coplanar with the one below
      if (vMin) hp.push([0, 1, -vMin]);
      polys.push(...plane.region(hp));
    }
    if (polys.length) parts.push({ plane, polys });
  }
  return parts;
}

/** Parts within `dist` up-slope of the plane's eave edges (ice & water rows, starter strip). */
export function eaveParts(planes, segs, dist) {
  return stripParts(planes, segs.eave, dist);
}

// ---------------------------------------------------------------------------
// Edge profiles: drip edge (L flange) and ridge / hip caps.

// profile (020, inches, from edgeProfileFor): { flangeIn, faceIn, kickOutIn, kickDownIn, hemIn }; none keeps today's
// shape, and a missing key keeps today's value (as drip_edge_buf in roof_core.py)
export function dripEdgeGeometry(segs, { offEave = 0.013, offRake = 0.019, flange = 0.05, drop = 0.045, profile = null } = {}) {
  const p = profile || {}, m = (k, today) => (p[k] != null ? p[k] * 0.0254 : today);
  flange = m('flangeIn', flange); drop = m('faceIn', drop);
  const kickOut = m('kickOutIn', 0.012), kickDown = m('kickDownIn', 0.006), hem = m('hemIn', 0);
  const pos = [], nor = [], uv = [], up = [], along = [];
  const add = (p, n, u, v, kUp, kAl) => { pos.push(p.x, p.y, p.z); nor.push(n.x, n.y, n.z); uv.push(u, v); up.push(kUp); along.push(kAl); };
  const quad = (a, b, c, d, n, len, kUp, k0, k1) => {
    add(a, n, 0, 0, kUp, k0); add(b, n, len, 0, kUp, k1); add(c, n, len, 0.05, kUp, k1);
    add(a, n, 0, 0, kUp, k0); add(c, n, len, 0.05, kUp, k1); add(d, n, 0, 0.05, kUp, k0);
  };
  const kinds = [['eave', offEave, 0], ['rake', offRake, 1]];
  for (const [kind, off, kUp] of kinds) {
    const list = segs[kind];
    const total = list.reduce((s, e) => s + e.A.distanceTo(e.B), 0) || 1;
    let acc = 0;
    for (const s of list) {
      const P = s.planes[0];
      const len = s.A.distanceTo(s.B);
      const k0 = acc / total, k1 = Math.min(0.9999, (acc + len) / total);
      acc += len;
      const a2 = P.from3(s.A), b2 = P.from3(s.B);
      const inward = inwardDir2(P, { a: a2, b: b2 });
      // outward horizontal direction for the drop face
      const outW = P.h.clone().multiplyScalar(-inward[0]).addScaledVector(P.b, -inward[1]);
      outW.y = 0; outW.normalize();
      // the bend sits 1.5 mm out from the deck edge (in the roof plane, so the flange stays parallel to the
      // layers): the drop then does not share the deck's edge face at the rakes
      const A = P.to3(a2[0] - inward[0] * 0.0015, a2[1] - inward[1] * 0.0015, off);
      const B = P.to3(b2[0] - inward[0] * 0.0015, b2[1] - inward[1] * 0.0015, off);
      const A1 = P.to3(a2[0] + inward[0] * flange, a2[1] + inward[1] * flange, off);
      const B1 = P.to3(b2[0] + inward[0] * flange, b2[1] + inward[1] * flange, off);
      quad(A1, B1, B, A, P.n, len, kUp, k0, k1); // top flange (lies on the deck)
      // then face, kick and hem, each (dOut, dUp) in the outward-horizontal / world-up frame; zero-length legs are skipped
      // the front side looks out and up: outW * (-dUp) + up * dOut (the face looks out, the kick out and up, the hem down)
      let pA = A, pB = B;
      for (const [dOut, dUp] of [[0, -drop], [kickOut, -kickDown], [-hem, 0]]) {
        if (Math.hypot(dOut, dUp) < 1e-6) continue;
        const d = outW.clone().multiplyScalar(dOut).add(new THREE.Vector3(0, dUp, 0));
        const qA = pA.clone().add(d), qB = pB.clone().add(d);
        quad(pA, pB, qB, qA, outW.clone().multiplyScalar(-dUp).add(new THREE.Vector3(0, dOut, 0)).normalize(), len, kUp, k0, k1);
        pA = qA; pB = qB;
      }
    }
  }
  return makeGeometry(pos, nor, uv, up, along, true);
}

/**
 * Caps over ridge and hip lines: a strip bent over the line, `width` down each side.
 * Returns geometry whose u coordinate runs along the line (for cap-shingle textures).
 */
// profile: [[distance from the line, height above the rafters], ...], crest first (for caps draped over a vent)
export function capGeometry(lines, { width = 0.16, off = 0.032, lift = 0, profile = null } = {}) {
  const pos = [], nor = [], uv = [], up = [], along = [];
  const add = (p, n, u, v, a) => { pos.push(p.x, p.y, p.z); nor.push(n.x, n.y, n.z); uv.push(u, v); up.push(0); along.push(a); };
  const total = lines.reduce((s, l) => s + l.A.distanceTo(l.B), 0) || 1;
  let acc = 0;
  for (const l of lines) {
    const len = l.A.distanceTo(l.B);
    const k0 = acc / total, k1 = Math.min(0.9999, (acc + len) / total);
    acc += len;
    // build from the higher end down so hip caps start at the bottom when installed
    let A = l.A, B = l.B;
    if (A.y > B.y + 0.01) [A, B] = [B, A];
    // both halves share one crest, the same height above each plane (otherwise a slit opens along the line)
    const [P0, P1] = l.planes;
    const dn = P1 ? P0.n.dot(P1.n) : -1;
    const bis = dn > -0.5 ? P0.n.clone().add(P1.n).divideScalar(1 + dn) : null;
    for (const P of l.planes) {
      const a2 = P.from3(A), b2 = P.from3(B);
      const inward = inwardDir2(P, { a: a2, b: b2 });
      const o = off + lift;
      // default: a small rise at the line so the cap reads as a rounded piece
      const prof = profile || [[0, o + 0.006], [width, o - 0.004]];
      const across = P.h.clone().multiplyScalar(inward[0]).addScaledVector(P.b, inward[1]);
      const at = (q, w, h) => (w === 0 && bis ? P.to3(q[0], q[1], 0).addScaledVector(bis, h) : P.to3(q[0] + inward[0] * w, q[1] + inward[1] * w, h));
      for (let i = 0; i + 1 < prof.length; i++) {
        const [w0, h0] = prof[i], [w1, h1] = prof[i + 1];
        const n = across.clone().multiplyScalar(h0 - h1).addScaledVector(P.n, w1 - w0).normalize(); // up and away from the line
        const qA = at(a2, w1, h1), qB = at(b2, w1, h1), pA = at(a2, w0, h0), pB = at(b2, w0, h0);
        add(qA, n, 0, w1, k0); add(qB, n, len, w1, k1); add(pB, n, len, w0, k1);
        add(qA, n, 0, w1, k0); add(pB, n, len, w0, k1); add(pA, n, 0, w0, k0);
      }
    }
  }
  const g = makeGeometry(pos, nor, uv, up, along, true);
  return g;
}

/** Ridge vent: a low box over each ridge line, inset from the ends. */
export function ridgeVentGeometry(ridges, { inset = 0.3, width = 0.14, height = 0.032, off = 0.028 } = {}) {
  const lines = [];
  for (const l of ridges) {
    const len = l.A.distanceTo(l.B);
    if (len < inset * 2 + 0.3) continue;
    const dir = l.B.clone().sub(l.A).normalize();
    lines.push({ A: l.A.clone().addScaledVector(dir, inset), B: l.B.clone().addScaledVector(dir, -inset), planes: l.planes });
  }
  const top = capGeometry(lines, { width, off: off + height, lift: 0 });
  // side skirts (the vent's filter mesh)
  const pos = [], nor = [], uv = [], up = [], along = [];
  const total = lines.reduce((s, l) => s + l.A.distanceTo(l.B), 0) || 1;
  let acc = 0;
  for (const l of lines) {
    const len = l.A.distanceTo(l.B);
    const k0 = acc / total, k1 = Math.min(0.9999, (acc + len) / total); acc += len;
    for (const P of l.planes) {
      const a2 = P.from3(l.A), b2 = P.from3(l.B);
      const inward = inwardDir2(P, { a: a2, b: b2 });
      const ua = [a2[0] + inward[0] * width, a2[1] + inward[1] * width];
      const ub = [b2[0] + inward[0] * width, b2[1] + inward[1] * width];
      const lowA = P.to3(ua[0], ua[1], off), lowB = P.to3(ub[0], ub[1], off);
      const hiA = P.to3(ua[0], ua[1], off + height - 0.004), hiB = P.to3(ub[0], ub[1], off + height - 0.004);
      const n = P.h.clone().multiplyScalar(-inward[0]).addScaledVector(P.b, -inward[1]).normalize();
      const v = (p, uu, vv, a) => { pos.push(p.x, p.y, p.z); nor.push(n.x, n.y, n.z); uv.push(uu, vv); up.push(0); along.push(a); };
      v(lowA, 0, 0, k0); v(lowB, len, 0, k1); v(hiB, len, height, k1);
      v(lowA, 0, 0, k0); v(hiB, len, height, k1); v(hiA, 0, height, k0);
    }
  }
  const skirt = makeGeometry(pos, nor, uv, up, along, true);
  return { top, skirt, lines };
}

// ---------------------------------------------------------------------------
// Fasteners

/**
 * Nail positions following the shingle nail line (just above each course's exposure).
 * Returns { matrices: Float32Array(16*n), keys: Float32Array(n), count }.
 */
export function nailLayout(planes, { exposure = 0.1429, spacing = 0.17, off = 0.025, margin = 0.04 } = {}) {
  const mats = [], keys = [];
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();
  for (const P of planes) {
    q.setFromUnitVectors(UP, P.n);
    const rows = Math.ceil(P.vMax / exposure);
    for (let r = 0; r < rows; r++) {
      const v = (r + 1) * exposure + 0.016;
      const stagger = (r % 2) * spacing * 0.5;
      for (let u = margin + stagger; u < P.uMax - margin; u += spacing) {
        if (!P.contains2(u, v, margin)) continue;
        P.to3(u, v, off, p);
        m.compose(p, q, s);
        mats.push(...m.elements);
        keys.push(r + Math.min(0.9999, u / Math.max(P.uMax, EPS)));
      }
    }
  }
  return { matrices: new Float32Array(mats), keys: new Float32Array(keys), count: keys.length };
}

/**
 * Copy of `geom` without the given triangles (numbers in index order), keeping
 * material groups. Used to remove only the roof from an imported house mesh.
 */
export function withoutTriangles(geom, drop) {
  const g = geom.clone();
  const idx = g.index ? Array.from(g.index.array) : Array.from({ length: g.attributes.position.count }, (_, i) => i);
  const groups = geom.groups.length ? geom.groups : [{ start: 0, count: idx.length, materialIndex: 0 }];
  const out = [], newGroups = [];
  for (const gr of groups) {
    const s0 = out.length;
    for (let i = gr.start; i < Math.min(idx.length, gr.start + gr.count); i += 3) if (!drop.has(i / 3)) out.push(idx[i], idx[i + 1], idx[i + 2]);
    newGroups.push({ start: s0, count: out.length - s0, materialIndex: gr.materialIndex });
  }
  g.setIndex(out);
  g.clearGroups();
  if (geom.groups.length) for (const x of newGroups) g.addGroup(x.start, x.count, x.materialIndex);
  return g;
}

/** A roofing nail: 3/8" head, 1-1/4" shank, pointing down -Y in local space (head at origin). */
export function nailGeometry() {
  // low-poly on purpose: a roof carries ~10k of these
  const r = 0.0055, t = 0.0012;
  const cap = new THREE.CircleGeometry(r, 6);
  cap.rotateX(-Math.PI / 2);
  const rim = new THREE.CylinderGeometry(r, r, t, 6, 1, true);
  rim.translate(0, -t / 2, 0);
  const shank = new THREE.ConeGeometry(0.0016, 0.032, 3, 1, true);
  shank.rotateX(Math.PI);
  shank.translate(0, -t - 0.016, 0);
  return mergeSimple([cap, rim, shank]);
}

// ---------------------------------------------------------------------------
// Deck repair patches: whole 4x8 sheets that sit fully inside a plane.

export function deckPatches(planes, count = 3, seed = 3) {
  let s = seed;
  const rand = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
  const W = 2.438, H = 1.219;
  const out = [];
  const candidates = [];
  for (const P of planes) {
    for (let v = 0.2; v + H < P.vMax; v += H) {
      for (let u = 0.2; u + W < P.uMax; u += W * 0.5) {
        const corners = [[u, v], [u + W, v], [u + W, v + H], [u, v + H]];
        if (corners.every(([a, b]) => P.contains2(a, b, 0.05))) candidates.push({ plane: P, polys: [corners] });
      }
    }
  }
  for (let i = 0; i < count && candidates.length; i++) {
    const k = Math.floor(rand() * candidates.length);
    out.push(candidates.splice(k, 1)[0]);
  }
  return out;
}

// ---------------------------------------------------------------------------
// GLB / mesh import: find roof triangles and cluster them into planes.

/**
 * @param {THREE.Object3D} root
 * @param {object} opts  nameHint regex, minUp (normal.y threshold), topFraction
 * @returns {{planes: RoofPlane[], roofTris: Map<THREE.Mesh, Set<number>>}} roofTris: which triangles of each mesh became roof
 */
export function extractRoofPlanes(root, opts = {}) {
  const nameHint = opts.nameHint ?? /roof|shingle|tile|metal_roof/i;
  const minUp = opts.minUp ?? 0.22;
  const topFraction = opts.topFraction ?? 0.4;
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const yCut = box.min.y + (box.max.y - box.min.y) * topFraction;
  const meshes = [];
  const isLayer = (o) => { for (let p = o; p; p = p.parent) if (/^RT_(layer|label)_/.test(p.name)) return true; return false; };
  root.traverse((o) => {
    if (!o.isMesh || !o.geometry?.attributes?.position) return;
    // layer meshes exported by roof-blender or the viewer are rebuilt here, so skip and hide them
    if (isLayer(o)) { o.visible = false; return; }
    meshes.push(o);
  });
  const named = meshes.filter((m) => nameHint.test(m.name) || nameHint.test(m.material?.name || ''));
  const useNamed = named.length > 0;
  const tris = [];
  const roofTris = new Map(); // mesh -> Set of triangle numbers used as roof
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (const mesh of useNamed ? named : meshes) {
    const g = mesh.geometry;
    const posA = g.attributes.position;
    const index = g.index;
    const triCount = index ? index.count / 3 : posA.count / 3;
    const mirrored = mesh.matrixWorld.determinant() < 0; // negative scale flips the winding
    for (let i = 0; i < triCount; i++) {
      const ia = index ? index.getX(i * 3) : i * 3, ib = index ? index.getX(i * 3 + 1) : i * 3 + 1, ic = index ? index.getX(i * 3 + 2) : i * 3 + 2;
      a.fromBufferAttribute(posA, ia).applyMatrix4(mesh.matrixWorld);
      b.fromBufferAttribute(posA, ib).applyMatrix4(mesh.matrixWorld);
      c.fromBufferAttribute(posA, ic).applyMatrix4(mesh.matrixWorld);
      const t = mirrored ? [a.clone(), c.clone(), b.clone()] : [a.clone(), b.clone(), c.clone()];
      const n = triNormal(t);
      const ar = triArea(t);
      if (ar < 1e-5) continue;
      if (!useNamed) {
        const cy = (a.y + b.y + c.y) / 3;
        if (n.y < minUp || cy < yCut) continue;
      }
      // walls, fascia and the underside of thick roof meshes never become roof planes
      if (n.y < 0.05) continue;
      tris.push({ t, n, d: n.dot(t[0]) });
      if (!roofTris.has(mesh)) roofTris.set(mesh, new Set());
      roofTris.get(mesh).add(i);
    }
  }
  // cluster by normal + offset
  const clusters = [];
  for (const tr of tris) {
    let best = null;
    for (const cl of clusters) {
      if (cl.n.dot(tr.n) > Math.cos(THREE.MathUtils.degToRad(4)) && Math.abs(cl.d - tr.d) < 0.06) { best = cl; break; }
    }
    if (!best) { best = { n: tr.n.clone(), d: tr.d, tris: [], area: 0 }; clusters.push(best); }
    best.tris.push(tr.t);
    best.area += triArea(tr.t);
  }
  const planes = clusters
    .filter((cl) => cl.area > 0.5)
    .map((cl, i) => new RoofPlane(cl.tris.map((t) => t.map((p) => projectToPlane(p, cl.n, cl.d))), cl.n, i));
  return { planes, roofTris };
}

// ---------------------------------------------------------------------------
// Measurements for the estimate panel.

export function measureRoof(planes, segs) {
  const area = planes.reduce((s, p) => s + p.area, 0);
  const len = (list) => list.reduce((s, l) => s + l.A.distanceTo(l.B), 0);
  return {
    areaM2: area,
    squares: area / 9.290304,
    eaveM: len(segs.eave), rakeM: len(segs.rake), ridgeM: len(segs.ridge), hipM: len(segs.hip), valleyM: len(segs.valley),
    planes: planes.length,
  };
}

// ---------------------------------------------------------------------------
// internal helpers

/** Wind every triangle so its front side faces its normal: FrontSide materials cull the rest. */
function orientTriangles(pos, nor, uv, up, along) {
  const swap = (arr, w, i, j) => { for (let k = 0; k < w; k++) { const t = arr[i * w + k]; arr[i * w + k] = arr[j * w + k]; arr[j * w + k] = t; } };
  for (let t = 0; t + 2 < pos.length / 3; t += 3) {
    const i = t * 3;
    const ax = pos[i + 3] - pos[i], ay = pos[i + 4] - pos[i + 1], az = pos[i + 5] - pos[i + 2];
    const bx = pos[i + 6] - pos[i], by = pos[i + 7] - pos[i + 1], bz = pos[i + 8] - pos[i + 2];
    const d = (ay * bz - az * by) * nor[i] + (az * bx - ax * bz) * nor[i + 1] + (ax * by - ay * bx) * nor[i + 2];
    if (d < 0) { swap(pos, 3, t + 1, t + 2); swap(nor, 3, t + 1, t + 2); swap(uv, 2, t + 1, t + 2); swap(up, 1, t + 1, t + 2); swap(along, 1, t + 1, t + 2); }
  }
}

export function makeGeometry(pos, nor, uv, up, along) {
  orientTriangles(pos, nor, uv, up, along);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setAttribute('aUp', new THREE.Float32BufferAttribute(up, 1));
  g.setAttribute('aAlong', new THREE.Float32BufferAttribute(along, 1));
  g.computeBoundingBox(); g.computeBoundingSphere();
  return g;
}

function mergeSimple(geoms) {
  const pos = [], nor = [];
  for (let g of geoms) {
    g = g.index ? g.toNonIndexed() : g;
    pos.push(...g.attributes.position.array); nor.push(...g.attributes.normal.array);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  return g;
}

function triNormal(t) {
  return new THREE.Vector3().subVectors(t[1], t[0]).cross(new THREE.Vector3().subVectors(t[2], t[0])).normalize();
}
function triArea(t) {
  return new THREE.Vector3().subVectors(t[1], t[0]).cross(new THREE.Vector3().subVectors(t[2], t[0])).length() / 2;
}
function polygonNormal(pts) {
  const n = new THREE.Vector3();
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    n.x += (a.y - b.y) * (a.z + b.z); n.y += (a.z - b.z) * (a.x + b.x); n.z += (a.x - b.x) * (a.y + b.y);
  }
  n.normalize();
  if (n.y < 0) n.negate();
  return n;
}
function projectToPlane(p, n, d) { return p.clone().addScaledVector(n, d - n.dot(p)); }

const area2 = (t) => (t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1]);
function polyArea2(poly) {
  let s = 0;
  for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; s += a[0] * b[1] - b[0] * a[1]; }
  return s;
}

function pointInTri(u, v, t, margin = 0) {
  // barycentric with optional inward margin (metres)
  const [a, b, c] = t;
  const s = area2(t);
  if (Math.abs(s) < 1e-12) return false;
  const sign = Math.sign(s);
  const edges = [[a, b], [b, c], [c, a]];
  for (const [p, q] of edges) {
    const ex = q[0] - p[0], ey = q[1] - p[1];
    const len = Math.hypot(ex, ey) || 1;
    const cross = (ex * (v - p[1]) - ey * (u - p[0])) * sign / len;
    if (cross < margin - 1e-9) return false;
  }
  return true;
}

function segDist2(u, v, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy || 1e-12;
  const t = Math.max(0, Math.min(1, ((u - a[0]) * dx + (v - a[1]) * dy) / l2));
  return Math.hypot(u - (a[0] + dx * t), v - (a[1] + dy * t));
}

export function clipHalf(poly, [a, b, c]) {
  const out = [];
  const f = (p) => a * p[0] + b * p[1] + c;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length];
    const fp = f(p), fq = f(q);
    if (fp >= 0) out.push(p);
    if ((fp >= 0) !== (fq >= 0)) {
      const t = fp / (fp - fq);
      out.push([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]);
    }
  }
  // make CCW
  if (out.length >= 3 && polyArea2(out) < 0) out.reverse();
  return out;
}

function boundaryEdges(tris) {
  const key = (p) => `${Math.round(p[0] * 500)},${Math.round(p[1] * 500)}`;
  const map = new Map();
  for (let t of tris) {
    if (area2(t) < 0) t = [t[0], t[2], t[1]];
    for (let i = 0; i < 3; i++) {
      const a = t[i], b = t[(i + 1) % 3];
      const k1 = key(a) + '|' + key(b), k2 = key(b) + '|' + key(a);
      if (map.has(k2)) map.delete(k2); else map.set(k1, [a, b]);
    }
  }
  return mergeCollinear([...map.values()]);
}

function mergeCollinear(edges) {
  // join consecutive collinear boundary edges so eaves are single segments
  const key = (p) => `${Math.round(p[0] * 500)},${Math.round(p[1] * 500)}`;
  const byStart = new Map(edges.map((e) => [key(e[0]), e]));
  const used = new Set();
  const out = [];
  for (const e of edges) {
    if (used.has(e)) continue;
    used.add(e);
    let [a, b] = e;
    let next = byStart.get(key(b));
    while (next && !used.has(next) && collinear(a, b, next[1])) { used.add(next); b = next[1]; next = byStart.get(key(b)); }
    out.push([a, b]);
  }
  return out;
}
function collinear(a, b, c) {
  const abx = b[0] - a[0], aby = b[1] - a[1], bcx = c[0] - b[0], bcy = c[1] - b[1];
  const cross = abx * bcy - aby * bcx;
  return Math.abs(cross) < 1e-4 * Math.hypot(abx, aby) * Math.hypot(bcx, bcy) + 1e-9 && abx * bcx + aby * bcy > 0;
}

export function inwardDir2(P, e) {
  const a = e.a, b = e.b;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  let m = [-dy / len, dx / len];
  const mid = [(a[0] + b[0]) / 2 + m[0] * 0.05, (a[1] + b[1]) / 2 + m[1] * 0.05];
  if (!P.contains2(mid[0], mid[1])) m = [-m[0], -m[1]];
  return m;
}

function onPlaneBoundary(P, a, b) {
  const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const m = [-dy / len * 0.02, dx / len * 0.02];
  const inA = P.contains2(mid[0] + m[0], mid[1] + m[1]);
  const inB = P.contains2(mid[0] - m[0], mid[1] - m[1]);
  return inA !== inB;
}

function segmentsOverlap(e, f, tol) {
  const same = (p, q) => p.distanceTo(q) < tol;
  if ((same(e.A, f.A) && same(e.B, f.B)) || (same(e.A, f.B) && same(e.B, f.A))) return true;
  // partial overlap: both endpoints of the shorter lie on the longer
  const onSeg = (p, s) => {
    const ab = s.B.clone().sub(s.A); const t = p.clone().sub(s.A).dot(ab) / ab.lengthSq();
    if (t < -0.01 || t > 1.01) return false;
    return s.A.clone().addScaledVector(ab, t).distanceTo(p) < tol;
  };
  const le = e.A.distanceTo(e.B), lf = f.A.distanceTo(f.B);
  const [s, l] = le < lf ? [e, f] : [f, e];
  return onSeg(s.A, l) && onSeg(s.B, l);
}

