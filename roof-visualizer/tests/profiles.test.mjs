// Metal panel profiles (019) and drip edge profiles (020): the shared table against roof_core.py,
// the ribbed covering surface, caps on the ribs, the rake trim, and edge profiles from store names.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three';
import { buildRoofPlanes, HOUSE_PRESETS } from '../viewer/js/house.js';
import { RoofPlane, analyzeRoof, fullParts, dripEdgeGeometry, capGeometry } from '../viewer/js/roof-geometry.js';
import { PROFILES, panelName, panelProfile, profileFor, ribbedSurface, rakeTrimGeometry, metalCapProfile, onRibs, dripReach } from '../viewer/js/profiles.js';
import { edgeProfileFor, toStudioProduct } from '../viewer/js/supplier-products.js';

const IN = 0.0254;
const COVERING = 0.0190; // H.covering in layers.js and roof_core.py
const near = (actual, expected, tol, what) => assert.ok(Math.abs(actual - expected) <= tol, `${what}: ${actual} vs ${expected}`);

/** Triangles wound against their normal (FrontSide materials cull them). */
function badWinding(g) {
  const p = g.attributes.position.array, n = g.attributes.normal.array;
  let bad = 0;
  for (let i = 0; i < p.length; i += 9) {
    const ax = p[i + 3] - p[i], ay = p[i + 4] - p[i + 1], az = p[i + 5] - p[i + 2];
    const bx = p[i + 6] - p[i], by = p[i + 7] - p[i + 1], bz = p[i + 8] - p[i + 2];
    if ((ay * bz - az * by) * n[i] + (az * bx - ax * bz) * n[i + 1] + (ax * by - ay * bx) * n[i + 2] < 0) bad++;
  }
  return bad;
}
const tris = (g) => g.attributes.position.count / 3;

/** A 6/12 plane 2 m along the eave (u) by 3 m up the slope (v). */
function rectPlane(w = 2, l = 3) {
  const t = Math.atan(0.5);
  const b = new THREE.Vector3(0, Math.sin(t), -Math.cos(t));
  const A = new THREE.Vector3(0, 0, 0), B = new THREE.Vector3(w, 0, 0);
  return RoofPlane.fromPolygon([A, B, B.clone().addScaledVector(b, l), A.clone().addScaledVector(b, l)], 0);
}

test('the profile table is the same JSON as PANEL_PROFILES in roof_core.py', (t) => {
  const py = fs.readFileSync(fileURLToPath(new URL('../../roof-blender/scripts/roof_core.py', import.meta.url)), 'utf8');
  const start = 'PANEL_PROFILES = json.loads(r"""';
  const i = py.indexOf(start);
  if (i < 0) {
    console.log('# skip: roof_core.py has no PANEL_PROFILES block yet (the Blender lane adds it)');
    t.skip('roof_core.py has no PANEL_PROFILES block yet');
    return;
  }
  const j = py.indexOf('""")', i + start.length);
  assert.ok(j > i, 'PANEL_PROFILES block is not closed with """)');
  assert.deepEqual(JSON.parse(py.slice(i + start.length, j)), PROFILES);
});

test('profile table: periodic, first and last h equal, maxH as specified', () => {
  for (const [name, p] of Object.entries(PROFILES)) {
    if (name === 'flat') { assert.equal(p.points.length, 0); continue; }
    assert.equal(p.points[0][0], 0, `${name} starts at u = 0`);
    near(p.points[p.points.length - 1][0], p.periodIn, 1e-9, `${name} ends at the period`);
    assert.equal(p.points[0][1], p.points[p.points.length - 1][1], `${name}: first and last h`);
  }
  near(panelProfile('proRib').maxH, 0.01905, 1e-9, 'proRib maxH');
  near(panelProfile('proSnap').maxH, 0.01905, 1e-9, 'proSnap maxH');
  near(panelProfile('corrugated').maxH, 0.5 * IN, 1e-9, 'corrugated maxH');
  assert.equal(panelProfile('flat'), null);
  // rib spacing / height on a Pro-Rib product scale its table
  const s = panelProfile('proRib', { ribSpacingIn: 12, ribHeightIn: 1 });
  near(s.periodM, 12 * IN, 1e-9, 'scaled period');
  near(s.maxH, 1 * IN, 1e-9, 'scaled height');
});

test('which profile: from the studio product kind; other metal and non-metal products are flat', () => {
  const sp = (kind, extra = {}) => toStudioProduct({ id: `x-${kind}`, store: 'menards-3064', layer: 'covering', kind, name: 'Steel Panel', ...extra });
  assert.equal(panelName(sp('proRib', { size: { ribSpacingIn: 9, ribHeightIn: 0.75 } })), 'proRib');
  assert.equal(panelName(sp('proSnap')), 'proSnap');
  assert.equal(panelName(sp('corrugated')), 'corrugated');
  assert.equal(panelName(sp('architectural')), 'flat');
  assert.equal(panelName({ category: 'metal', image: 'photo.jpg' }), 'flat');
  assert.equal(panelName({ category: 'shingle', procedural: { kind: 'standingSeam' } }), 'flat');
  assert.equal(profileFor(sp('architectural')), null);
  near(profileFor(sp('proRib', { size: { ribSpacingIn: 9, ribHeightIn: 0.75 } })).periodM, 9 * IN, 1e-9, 'Pro-Rib period');
});

test('ribbed surface on a 2 m x 3 m plane: height, rib count, no gaps or overlaps, winding', () => {
  const plane = rectPlane();
  for (const name of ['proRib', 'proSnap', 'corrugated']) {
    const prof = panelProfile(name);
    const g = ribbedSurface(fullParts([plane]), { offset: COVERING, profile: prof });
    const pos = g.attributes.position, uv = g.attributes.uv.array;
    let hMax = -Infinity, hMin = Infinity;
    const p = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) { p.fromBufferAttribute(pos, i); const h = plane.distance(p) - COVERING; hMax = Math.max(hMax, h); hMin = Math.min(hMin, h); }
    near(hMax, prof.maxH, 1e-6, `${name}: highest vertex above the pan`);
    near(hMin, 0, 1e-6, `${name}: lowest vertex on the pan`);
    // projected onto the plane (the uv attribute is u, v in metres): 6 m2, so no gaps and no overlaps
    let area = 0;
    for (let i = 0; i < uv.length; i += 6) area += Math.abs((uv[i + 2] - uv[i]) * (uv[i + 5] - uv[i + 1]) - (uv[i + 4] - uv[i]) * (uv[i + 3] - uv[i + 1])) / 2;
    near(area, 6, 6 * 0.005, `${name}: projected area m2`);
    assert.equal(badWinding(g), 0, `${name}: triangles wound against their normal`);
    // ribs: vertices at the rib-top height, grouped along u (a new rib after a gap of half a period)
    const tops = [];
    for (let i = 0; i < pos.count; i++) { p.fromBufferAttribute(pos, i); if (Math.abs(plane.distance(p) - COVERING - prof.maxH) < 1e-6) tops.push(uv[i * 2]); }
    tops.sort((a, b) => a - b);
    let ribs = 0, last = -Infinity;
    for (const u of tops) { if (u - last > prof.periodM / 2) ribs++; last = u; }
    const expect = Math.floor(2 / prof.periodM);
    assert.ok(Math.abs(ribs - expect) <= 1, `${name}: ${ribs} ribs, expected ${expect} +- 1`);
    // the build attributes follow buildSurface: aUp = v, aAlong = u / uMax
    const upA = g.attributes.aUp.array, al = g.attributes.aAlong.array;
    for (let i = 0; i < upA.length; i += 97) { near(upA[i], uv[i * 2 + 1], 1e-6, 'aUp'); near(al[i], Math.min(0.9999, uv[i * 2] / plane.uMax), 1e-6, 'aAlong'); }
  }
});

test('ranch demo: ribbed covering triangle budget, caps above the rib tops, rake trim', () => {
  const planes = buildRoofPlanes(HOUSE_PRESETS['ranch-hip'], 6);
  const segs = analyzeRoof(planes);
  const counts = {};
  for (const name of ['proRib', 'proSnap', 'corrugated']) {
    const prof = panelProfile(name);
    const g = ribbedSurface(fullParts(planes), { offset: COVERING, profile: prof });
    counts[name] = tris(g);
    assert.equal(badWinding(g), 0, `${name}: winding`);
    const top = onRibs(COVERING, prof);
    // every cap vertex is above the rib tops, except the hem at the outer edge, which dips 3 mm below them by design
    const prof3 = metalCapProfile(top, 5.75);
    assert.ok(prof3[0][1] > COVERING + prof.maxH && prof3[1][1] > COVERING + prof.maxH, `${name}: cap above the ribs`);
    const cap = capGeometry([...segs.hip, ...segs.ridge], { profile: prof3 });
    assert.equal(badWinding(cap), 0, `${name}: cap winding`);
    const trim = rakeTrimGeometry(segs.rake, { top });
    assert.equal(tris(trim), segs.rake.length * 6, 'three legs per rake');
    assert.equal(badWinding(trim), 0, 'rake trim winding');
  }
  console.log(`# covering triangles on the ranch demo: ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(', ')}`);
  assert.ok(counts.corrugated <= 60000, `corrugated ${counts.corrugated} triangles (budget about 60k)`);
});

test('rake trim: top leg at the top height, face 3.5 in. down, bend clear of the drip edge kick, mitered at the peak', () => {
  const planes = buildRoofPlanes(HOUSE_PRESETS['ranch-hip'], 6);
  const segs = analyzeRoof(planes);
  const top = onRibs(COVERING, panelProfile('proRib'));
  // the garage gable: both rakes lie in one vertical plane, the trims bend out of it (+z)
  const gableZ = segs.rake[0].A.z;
  for (const [edge, out] of [[null, 0.0015 + 0.012 + 0.125 * IN], [{ kickOutIn: 0.5 }, 0.0015 + 0.5 * IN + 0.125 * IN], [{ kickOutIn: 0 }, 0.25 * IN]]) {
    const g = rakeTrimGeometry(segs.rake, { top, clear: dripReach(edge) });
    const p = g.attributes.position, n = g.attributes.normal, uv = g.attributes.uv;
    const v = new THREE.Vector3();
    let onTop = 0, zMax = -Infinity;
    const face = new Map(); // rake : u along it -> distinct heights of the face corners there
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i);
      const P = segs.rake[Math.floor(i / 18)].planes[0];
      if (n.getY(i) > 0.5 && Math.abs(P.distance(v) - top) < 1e-6) onTop++;
      zMax = Math.max(zMax, v.z);
      if (Math.abs(n.getY(i)) < 1e-6) {
        const k = `${Math.floor(i / 18)}:${uv.getX(i).toFixed(6)}`, ys = face.get(k) || [];
        if (!ys.some((y) => Math.abs(y - v.y) < 1e-7)) ys.push(v.y);
        face.set(k, ys);
      }
    }
    assert.equal(onTop, 12, 'top legs lie at `top` in the plane');
    near(zMax - gableZ, out, 1e-6, `bend past the panel edge (kick ${edge?.kickOutIn ?? 'default'})`);
    // face: at each end of each rake, the bend and the foot are 3.5 in. apart vertically
    assert.equal(face.size, 4, 'two ends per rake');
    for (const ys of face.values()) { assert.equal(ys.length, 2); near(Math.abs(ys[0] - ys[1]), 3.5 * IN, 1e-6, 'face drop'); }
  }
  // miter: at the peak the two trims end on one plane, every section point shared (no notch at the apex)
  const g = rakeTrimGeometry(segs.rake, { top, clear: dripReach(null) });
  const p = g.attributes.position;
  const [s0, s1] = segs.rake;
  const peak = [s0.A, s0.B].find((X) => X.distanceTo(s1.A) < 0.03 || X.distanceTo(s1.B) < 0.03);
  const near0 = [[], []];
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const set = near0[Math.floor(i / 18)];
    if (v.distanceTo(peak) < 0.25 && !set.some((q) => q.distanceTo(v) < 1e-7)) set.push(v.clone());
  }
  assert.equal(near0[0].length, 4, 'four section points at the peak end');
  for (const q of near0[0]) assert.ok(near0[1].some((r) => r.distanceTo(q) < 1e-6), `section point ${q.toArray().map((x) => x.toFixed(4))} shared at the peak`);
});

// ---------------------------------------------------------------------------
// 020: drip edge profile from the product name

test('edgeProfileFor: style and sizes from store names', () => {
  const ep = (name, kind = 'dripEdge') => edgeProfileFor({ id: 'x', layer: 'dripEdge', kind, name });
  let e = ep('2-3/8" x 1-11/16" x 12\' Style-D White Aluminum Drip Edge');
  assert.deepEqual([e.style, e.flangeIn, e.faceIn, e.kickOutIn, e.kickDownIn, e.hemIn, e.approx], ['D', 2.375, 1.6875, 0.5, 0.25, 0, []]);
  e = ep('1-3/4" x 1-3/4" x 10\' White Steel Roof Edging- Gutter Apron', 'gutterApron');
  assert.deepEqual([e.style, e.flangeIn, e.faceIn, e.hemIn, e.approx], ['apron', 1.75, 1.75, 0.375, []]);
  e = ep('C3 x 10 ft. White Aluminum Drip Edge Flashing');
  assert.deepEqual([e.style, e.flangeIn, e.faceIn, e.kickOutIn, e.kickDownIn], ['C', 2.0, 1.5, 0.375, 0.375]);
  assert.deepEqual(e.approx, ['size assumed from the profile style']);
  e = ep('2.43 in. x 1 in. x 10 ft. Brown Aluminum F4 1/2 Overhanging Drip Edge');
  assert.deepEqual([e.style, e.flangeIn, e.faceIn, e.approx], ['D', 2.43, 1, []]);
  e = ep('2.47 in. x 10 ft. Aluminum Black Roof Apron Flashing');
  assert.deepEqual([e.style, e.flangeIn, e.faceIn, e.approx], ['apron', 2.5, 2.47, ['flange assumed']]);
  e = ep('3 in. x 12 in. x 10.5 ft. White Galvanized Steel Eave Trim');
  assert.deepEqual([e.style, e.flangeIn, e.faceIn], ['D', 3, 4]);
  assert.equal(e.approx.length, 1);
  assert.match(e.approx[0], /face 12 in\..*4 in\./);
  // more names from the catalog
  assert.deepEqual([ep('1-3/8" x 1-3/8" x 10\' Style-A Galvanized Roof Edge').style, ep('1-3/8" x 1-3/8" x 10\' Style-A Galvanized Roof Edge').faceIn], ['A', 1.375]);
  assert.deepEqual(['C', 2.75, 1], ((x) => [x.style, x.flangeIn, x.faceIn])(ep('2-3/4" x 1" x 10\' Style-C White Steel Roof Edging')));
  assert.deepEqual(['D', 2.375, 1.5], ((x) => [x.style, x.flangeIn, x.faceIn])(ep('F5M 2-3/8 in. x 1-1/2 in. x 10 ft. Brown Galvanized Steel Drip Edge Flashing')));
  assert.equal(ep('F8 Open Mill Finish Aluminum Drip Edge').style, 'D');
  assert.equal(ep('10\' Charcoal Gray Steel Corner & Gable Trim', 'rakeTrim').style, 'rake');
  assert.equal(ep('10\' Charcoal Gray Steel Corner & Gable Trim', 'rakeTrim').faceIn, 3.5);
  assert.equal(ep('F4-1/2 10 ft. White Vinyl Drip Edge').approx[0], 'size assumed from the profile style'); // 1/2 of F4-1/2 is not a size
});

test('drip edge with a profile: the drop equals the face; no profile keeps today\'s shape', () => {
  const planes = buildRoofPlanes(HOUSE_PRESETS['ranch-hip'], 6);
  const segs = analyzeRoof(planes);
  /** Vertical extent of the face (vertical triangles at the eaves, aUp = 0). */
  const drop = (g) => {
    const p = g.attributes.position, n = g.attributes.normal, k = g.attributes.aUp;
    let worst = 0;
    for (let i = 0; i < p.count; i += 3) {
      if (k.getX(i) !== 0 || Math.abs(n.getY(i)) > 1e-6) continue;
      const ys = [0, 1, 2].map((j) => p.getY(i + j));
      worst = Math.max(worst, Math.max(...ys) - Math.min(...ys));
    }
    return worst;
  };
  for (const name of ['2-3/8" x 1-11/16" x 12\' Style-D White Aluminum Drip Edge', '1-3/4" x 1-3/4" x 10\' White Steel Roof Edging- Gutter Apron', 'C3 x 10 ft. White Aluminum Drip Edge Flashing']) {
    const profile = edgeProfileFor({ id: 'x', kind: /Apron/.test(name) ? 'gutterApron' : 'dripEdge', name });
    const g = dripEdgeGeometry(segs, { offEave: 0.0122, offRake: 0.0158, profile });
    near(drop(g), profile.faceIn * IN, 0.001, `${profile.style} face drop`);
    assert.equal(badWinding(g), 0, `${profile.style}: winding`);
    // hem: an apron has one more leg per segment, A-style none for the kick
    const legs = 1 + 1 + (profile.kickOutIn || profile.kickDownIn ? 1 : 0) + (profile.hemIn ? 1 : 0);
    assert.equal(tris(g), (segs.eave.length + segs.rake.length) * legs * 2, `${profile.style}: legs`);
  }
  const g0 = dripEdgeGeometry(segs, { offEave: 0.0122, offRake: 0.0158 });
  near(drop(g0), 0.045, 1e-6, 'default drop');
  assert.equal(tris(g0), (segs.eave.length + segs.rake.length) * 3 * 2, 'default: flange, drop, kick');
  // a missing key keeps today's value (as drip_edge_buf in roof_core.py): flange and face only -> today's kick, no hem
  const gp = dripEdgeGeometry(segs, { offEave: 0.0122, offRake: 0.0158, profile: { flangeIn: 2, faceIn: 1.5 } });
  near(drop(gp), 1.5 * IN, 1e-6, 'partial profile drop');
  const g0p = g0.attributes.position.array, gpp = gp.attributes.position.array;
  assert.equal(gpp.length, g0p.length, 'partial profile: flange, drop, kick');
  // the kick legs (last two triangles of each segment) are today's 12 mm out, 6 mm down: same vector as the default
  const kick = (a, i) => [a[i + 3] - a[i], a[i + 4] - a[i + 1], a[i + 5] - a[i + 2]].map((x) => +x.toFixed(6));
  assert.deepEqual(kick(gpp, 12 * 3), kick(g0p, 12 * 3), 'today\'s kick');
});
