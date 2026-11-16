// Roof measurements against hand-computed values (the takeoff depends on these).
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRoofPlanes, HOUSE_PRESETS } from '../viewer/js/house.js';
import { analyzeRoof, measureRoof, capGeometry, ridgeVentGeometry, dripEdgeGeometry, buildSurface } from '../viewer/js/roof-geometry.js';

const near = (actual, expected, tol, what) => assert.ok(Math.abs(actual - expected) <= tol, `${what}: ${actual.toFixed(3)} vs ${expected.toFixed(3)}`);

function measure(id, pitch) {
  const planes = buildRoofPlanes(HOUSE_PRESETS[id], pitch);
  return { planes, m: measureRoof(planes, analyzeRoof(planes)) };
}

test('ranch hip + front-gable garage at 6/12', () => {
  // main 16 x 10 m, garage 7.2 m wide, 0.45 m overhang, slope factor sqrt(1 + 0.5^2)
  const { planes, m } = measure('ranch-hip', 6);
  const k = Math.sqrt(1.25);
  const hidden = 0.5 * 8.1 * 4.05; // main-roof triangle under the garage roof (plan view)
  near(m.areaM2, (16.9 * 10.9 - hidden + 8.1 * 5.4 + hidden) * k, 0.5, 'area m2'); // 254.85 m2, 27.43 sq
  near(m.eaveM, 2 * 16.9 + 2 * 10.9 - 8.1 + 2 * 5.4, 0.05, 'eaves');                // 58.3 m
  near(m.rakeM, 2 * 4.05 * k, 0.05, 'rakes');
  near(m.ridgeM, 2 * (8.45 - 5.45) + (10.85 - 1.4), 0.05, 'ridges');                 // 6.0 + 9.45
  near(m.hipM, 4 * Math.hypot(5.45 * Math.SQRT2, 5.45 * 0.5), 0.05, 'hips');           // 32.70 m
  near(m.valleyM, 2 * Math.hypot(4.05, 4.05, 2.025), 0.05, 'valleys');               // 12.15 m
  assert.equal(planes.length, 6);
});

test('two-story side gable at 8/12', () => {
  const { m } = measure('two-story', 8);
  const k = Math.sqrt(1 + (8 / 12) ** 2);
  near(m.areaM2, 13.2 * 9.7 * k, 0.3, 'area m2');
  near(m.eaveM, 2 * 13.2, 0.05, 'eaves');
  near(m.rakeM, 4 * 4.85 * k, 0.05, 'rakes');
  near(m.ridgeM, 13.2, 0.05, 'ridge');
  near(m.hipM + m.valleyM, 0, 0.01, 'no hips or valleys');
});

test('cottage full hip at 6/12', () => {
  const { m } = measure('cottage', 6);
  const k = Math.sqrt(1.25);
  near(m.areaM2, 11.8 * 9.8 * k, 0.3, 'area m2');
  near(m.eaveM, 2 * 11.8 + 2 * 9.8, 0.05, 'eaves');
  near(m.ridgeM, 11.8 - 9.8, 0.05, 'ridge');
  near(m.hipM, 4 * Math.hypot(4.9 * Math.SQRT2, 4.9 * 0.5), 0.05, 'hips');
  near(m.rakeM + m.valleyM, 0, 0.01, 'no rakes or valleys');
});

test('every triangle faces its normal (FrontSide materials cull the rest)', () => {
  // found by the blender-master qa_check: half of each cap and 2/3 of the drip edge were wound backwards
  const planes = buildRoofPlanes(HOUSE_PRESETS['ranch-hip'], 6);
  const segs = analyzeRoof(planes);
  const vent = ridgeVentGeometry(segs.ridge);
  const geoms = {
    capRidge: capGeometry(segs.ridge), capHip: capGeometry(segs.hip), ventTop: vent.top, ventSkirt: vent.skirt,
    drip: dripEdgeGeometry(segs), courses: buildSurface(planes.map((P) => ({ plane: P, polys: P.region() })), { courseH: 0.1429 }),
  };
  for (const [name, g] of Object.entries(geoms)) {
    const p = g.attributes.position.array, n = g.attributes.normal.array;
    let bad = 0;
    for (let i = 0; i < p.length; i += 9) {
      const ax = p[i + 3] - p[i], ay = p[i + 4] - p[i + 1], az = p[i + 5] - p[i + 2];
      const bx = p[i + 6] - p[i], by = p[i + 7] - p[i + 1], bz = p[i + 8] - p[i + 2];
      if ((ay * bz - az * by) * n[i] + (az * bx - ax * bz) * n[i + 1] + (ax * by - ay * bx) * n[i + 2] < 0) bad++;
    }
    assert.equal(bad, 0, `${name}: ${bad} of ${p.length / 9} triangles wound against their normal`);
  }
});
