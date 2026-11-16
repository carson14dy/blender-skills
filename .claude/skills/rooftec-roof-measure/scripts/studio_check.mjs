#!/usr/bin/env node
// Load a roof.glb with the roof studio's own import code, headless, and compare
// the studio's measurements with roof.json.
//
//   node studio_check.mjs --studio <path to roof-visualizer> --glb <roof.glb> [--roof <roof.json>]
//
// It repeats what `loadHouseModel()` in roof-visualizer/viewer/js/app.js does:
// GLTFLoader -> centre the model -> extractRoofPlanes -> analyzeRoof -> measureRoof.
// `three` must be installed in the studio folder (npm install in roof-visualizer).
// Exit code 0 = the studio found the roof and its area is within 1% of roof.json.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const arg = (name, dflt = null) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : dflt; };
const studio = arg('studio'), glbPath = arg('glb'), roofPath = arg('roof');
if (!studio || !glbPath) { console.error('usage: node studio_check.mjs --studio <roof-visualizer> --glb <roof.glb> [--roof <roof.json>]'); process.exit(2); }
const url = (p) => pathToFileURL(resolve(studio, p)).href;
let THREE, GLTFLoader, geo;
try {
  THREE = await import(url('node_modules/three/build/three.module.js'));
  ({ GLTFLoader } = await import(url('node_modules/three/examples/jsm/loaders/GLTFLoader.js')));
  geo = await import(url('viewer/js/roof-geometry.js'));
} catch (e) {
  console.error(`Could not load the studio from ${studio}: ${e.message}\nRun "npm install" in roof-visualizer first.`);
  process.exit(2);
}
const buf = readFileSync(glbPath);
const gltf = await new Promise((ok, fail) => new GLTFLoader().parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), '', ok, fail));
const root = gltf.scene;
root.updateMatrixWorld(true);
const box = new THREE.Box3().setFromObject(root);
root.position.x -= (box.min.x + box.max.x) / 2;
root.position.z -= (box.min.z + box.max.z) / 2;
root.position.y -= box.min.y;
root.updateMatrixWorld(true);
const names = []; root.traverse((o) => { if (o.isMesh) names.push(o.name); });
const { planes, roofTris } = geo.extractRoofPlanes(root);
const segs = geo.analyzeRoof(planes);
const m = geo.measureRoof(planes, segs);
const FT = 1200 / 3937, ft = (x) => x / FT;
const out = {
  meshes: names, roofMeshUsed: [...roofTris.keys()].map((x) => x.name),
  planes: m.planes, areaM2: +m.areaM2.toFixed(2), areaFt2: +(m.areaM2 / (FT * FT)).toFixed(1), squares: +m.squares.toFixed(2),
  ft: { eave: +ft(m.eaveM).toFixed(1), rake: +ft(m.rakeM).toFixed(1), ridge: +ft(m.ridgeM).toFixed(1), hip: +ft(m.hipM).toFixed(1), valley: +ft(m.valleyM).toFixed(1),
        top: +ft(segs.top.reduce((s, l) => s + l.A.distanceTo(l.B), 0)).toFixed(1) },
  pitchDeg: planes.map((p) => +(p.slope * 180 / Math.PI).toFixed(2)).sort((a, b) => b - a),
};
let okFlag = planes.length > 0 && out.roofMeshUsed.includes('Roof');
if (roofPath) {
  const roof = JSON.parse(readFileSync(roofPath, 'utf8'));
  const s = roof.summary, t = s.edgeTotals;
  // the studio has no wall-flashing class yet: it counts step flashing as rake and headwall/top as top
  // roof.glb carries the same geometry the areas in roof.json were measured on (lidar re-tilt included)
  const cityArea = roof.planes.reduce((a, p) => a + p.areaM2, 0);
  out.compare = {
    planes: [m.planes, s.planeCount],
    areaM2: [out.areaM2, +cityArea.toFixed(2)], areaDiffPct: +(100 * (m.areaM2 - cityArea) / cityArea).toFixed(2),
    ridgeFt: [out.ft.ridge, t.ridge.lengthFt], hipFt: [out.ft.hip, t.hip.lengthFt], valleyFt: [out.ft.valley, t.valley.lengthFt],
    eaveFt: [out.ft.eave, t.eave.lengthFt],
    rakePlusStepFt: [out.ft.rake, +(t.rake.lengthFt + t.step_flashing.lengthFt).toFixed(1)],
    topPlusHeadwallFt: [out.ft.top, +(t.top.lengthFt + t.headwall.lengthFt).toFixed(1)],
    note: 'each pair is [studio, roof.json]',
  };
  okFlag = okFlag && Math.abs(out.compare.areaDiffPct) <= 1 && m.planes === s.planeCount;
}
out.ok = okFlag;
console.log(JSON.stringify(out, null, 1));
process.exit(okFlag ? 0 : 1);
