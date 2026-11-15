// Procedural demo houses with accurate roof geometry (hip, gable, cross-gable
// with valleys). Units: metres, Y up, the front of the house faces +Z.
// The roof planes describe the top of the rafters; layers stack on top.

import * as THREE from 'three';
import { RoofPlane, analyzeRoof } from './roof-geometry.js';
import { lapSiding, grass, concrete, garageDoor, toTextures } from './textures.js';

export const HOUSE_PRESETS = {
  'ranch-hip': {
    label: 'Ranch, hip roof with front-gable garage',
    overhang: 0.45,
    blocks: [
      { id: 'main', cx: 0, cz: 0, w: 16, d: 10, wall: 2.75, roof: 'hip', axis: 'x' },
      { id: 'garage', cx: -4.2, cz: 7.6, w: 7.2, d: 5.6, wall: 2.75, roof: 'gable', axis: 'z', attachTo: 'main', garage: true },
    ],
    door: { x: 2.2 },
  },
  'two-story': {
    label: 'Two-story, side gable',
    overhang: 0.35,
    blocks: [{ id: 'main', cx: 0, cz: 0, w: 12.5, d: 9, wall: 5.6, roof: 'gable', axis: 'x' }],
    door: { x: 0 },
  },
  cottage: {
    label: 'Cottage, full hip',
    overhang: 0.4,
    blocks: [{ id: 'main', cx: 0, cz: 0, w: 11, d: 9, wall: 2.9, roof: 'hip', axis: 'x' }],
    door: { x: -1.5 },
  },
};

/**
 * Compute roof polygons for one rectangular block.
 * @returns {{roof: THREE.Vector3[][], gables: THREE.Vector3[][], eaveY: number, ridgeY: number}}
 */
export function blockRoof(b, pitch, overhang) {
  const p = pitch / 12;
  const swap = b.axis === 'z';
  const L = swap ? b.d : b.w; // along the ridge
  const S = swap ? b.w : b.d; // across the ridge
  const X = L / 2 + overhang, Z = S / 2 + overhang;
  const ye = b.wall - overhang * p, yr = ye + Z * p;
  const V = (x, y, z) => (swap ? new THREE.Vector3(b.cx + z, y, b.cz + x) : new THREE.Vector3(b.cx + x, y, b.cz + z));
  const roof = [], gables = [];
  // the ridge may run past the back of an attached block; it gets clipped later
  const ext = b.attachTo ? (b.ridgeExtend ?? 0) : 0;
  if (b.roof === 'hip') {
    const rx = Math.max(0, X - Z);
    roof.push([V(-X, ye, Z), V(X, ye, Z), V(rx, yr, 0), V(-rx, yr, 0)]);
    roof.push([V(X, ye, -Z), V(-X, ye, -Z), V(-rx, yr, 0), V(rx, yr, 0)]);
    roof.push([V(X, ye, Z), V(X, ye, -Z), V(rx, yr, 0)]);
    roof.push([V(-X, ye, -Z), V(-X, ye, Z), V(-rx, yr, 0)]);
  } else {
    const xb = -X - ext; // back end (may extend into the main roof)
    roof.push([V(xb, ye, Z), V(X, ye, Z), V(X, yr, 0), V(xb, yr, 0)]);
    roof.push([V(X, ye, -Z), V(xb, ye, -Z), V(xb, yr, 0), V(X, yr, 0)]);
    const hw = S / 2;
    for (const sx of b.attachTo ? [1] : [1, -1]) {
      const x = sx * L / 2;
      gables.push([V(x, b.wall, hw), V(x, b.wall, -hw), V(x, b.wall + hw * p, 0)]);
    }
  }
  return { roof, gables, eaveY: ye, ridgeY: yr };
}

/** Clip a 3D polygon to the side of plane (point, normal) where dot(p - point, n) >= 0. */
function clipPoly3(poly, point, n) {
  const out = [];
  const f = (p) => p.clone().sub(point).dot(n);
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length];
    const fa = f(a), fb = f(b);
    if (fa >= -1e-6) out.push(a);
    if ((fa >= -1e-6) !== (fb >= -1e-6)) out.push(a.clone().lerp(b, fa / (fa - fb)));
  }
  return out;
}

/** Build roof planes (deck baseline) for a preset. */
export function buildRoofPlanes(preset, pitch) {
  const polys = [];
  const blocks = {};
  for (const b of preset.blocks) {
    const r = blockRoof({ ...b, ridgeExtend: b.attachTo ? 12 : 0 }, b.pitch ?? pitch, preset.overhang);
    blocks[b.id] = { b, ...r, polys: r.roof };
  }
  for (const b of preset.blocks) {
    const blk = blocks[b.id];
    if (!b.attachTo) { polys.push(...blk.roof); continue; }
    // clip the attached block's roof against the parent's roof planes that face it
    const parent = blocks[b.attachTo];
    const toward = new THREE.Vector3(b.cx - parent.b.cx, 0, b.cz - parent.b.cz).normalize();
    for (let poly of blk.roof) {
      for (const pp of parent.roof) {
        const n = polyNormal(pp);
        if (new THREE.Vector3(n.x, 0, n.z).normalize().dot(toward) < 0.7) continue;
        poly = clipPoly3(poly, pp[0], n);
      }
      if (poly.length >= 3) polys.push(poly);
    }
  }
  return polys.map((p, i) => RoofPlane.fromPolygon(p, i));
}

function polyNormal(pts) {
  const n = new THREE.Vector3().subVectors(pts[1], pts[0]).cross(new THREE.Vector3().subVectors(pts[2], pts[0])).normalize();
  if (n.y < 0) n.negate();
  return n;
}

// ---------------------------------------------------------------------------

/**
 * Create the house body (everything except the roof layers).
 * @returns {{group: THREE.Group, planes: RoofPlane[], segs: object, materials: object}}
 */
export function createHouse(presetId, { pitch = 6, renderer, sidingColor = '#d9d4c7', trimColor = '#f4f2ec' } = {}) {
  const preset = HOUSE_PRESETS[presetId] || HOUSE_PRESETS['ranch-hip'];
  const group = new THREE.Group();
  group.name = 'house';
  const planes = buildRoofPlanes(preset, pitch);
  const segs = analyzeRoof(planes);

  const sidingTex = toTextures(lapSiding(), renderer);
  const mats = {
    siding: new THREE.MeshStandardMaterial({ color: sidingColor, map: sidingTex.map, normalMap: sidingTex.normalMap, roughnessMap: sidingTex.roughnessMap, roughness: 1 }),
    trim: new THREE.MeshStandardMaterial({ color: trimColor, roughness: 0.55 }),
    glass: new THREE.MeshPhysicalMaterial({ color: '#1a2430', roughness: 0.06, metalness: 0.0, reflectivity: 0.6, clearcoat: 1 }),
    door: new THREE.MeshStandardMaterial({ color: '#3d4a5c', roughness: 0.45 }),
    foundation: new THREE.MeshStandardMaterial({ color: '#9a978f', roughness: 0.95 }),
    gutter: new THREE.MeshStandardMaterial({ color: '#f1efe9', roughness: 0.4, metalness: 0.1 }),
  };
  const gTex = toTextures(garageDoor(), renderer, { repeat: false });
  gTex.map.repeat.set(1, 1); gTex.normalMap.repeat.set(1, 1);
  mats.garage = new THREE.MeshStandardMaterial({ color: '#ffffff', map: gTex.map, normalMap: gTex.normalMap, roughness: 0.5 });
  mats.sidingTex = sidingTex;

  for (const b of preset.blocks) {
    const bp = b.pitch ?? pitch;
    const r = blockRoof(b, bp, preset.overhang);
    // walls (back of attached blocks tucks into the parent)
    let d = b.d, cz = b.cz, w = b.w, cx = b.cx;
    if (b.attachTo) {
      const parent = preset.blocks.find((q) => q.id === b.attachTo);
      if (b.axis === 'z') { const back = parent.cz + parent.d / 2 - 0.3; const front = b.cz + b.d / 2; d = front - back; cz = (front + back) / 2; }
    }
    const walls = new THREE.Mesh(boxWorldUV(w, b.wall, d), mats.siding);
    walls.position.set(cx, b.wall / 2, cz);
    walls.castShadow = walls.receiveShadow = true;
    group.add(walls);
    const fnd = new THREE.Mesh(new THREE.BoxGeometry(w + 0.06, 0.35, d + 0.06), mats.foundation);
    fnd.position.set(cx, 0.1, cz); fnd.receiveShadow = true;
    group.add(fnd);
    for (const tri of r.gables) {
      const m = new THREE.Mesh(polyGeometryWorldUV(tri, new THREE.Vector3(b.cx, 0, b.cz)), mats.siding);
      m.castShadow = m.receiveShadow = true;
      group.add(m);
    }
    // openings on the front (+z) wall
    const frontZ = cz + d / 2;
    if (b.garage) {
      const gd = new THREE.Mesh(new THREE.PlaneGeometry(Math.min(4.9, w - 1.2), 2.13), mats.garage);
      gd.position.set(cx, 1.07, frontZ + 0.02);
      group.add(gd);
      addFrame(group, mats.trim, cx, 1.07, frontZ + 0.03, Math.min(4.9, w - 1.2), 2.13);
    } else {
      const doorX = preset.door?.x ?? 0;
      const door = new THREE.Mesh(new THREE.BoxGeometry(0.95, 2.1, 0.06), mats.door);
      door.position.set(doorX, 1.05 + 0.2, frontZ + 0.03); door.castShadow = true;
      group.add(door);
      addFrame(group, mats.trim, doorX, 1.25, frontZ + 0.05, 0.95, 2.1);
      const storeys = b.wall > 4 ? 2 : 1;
      const left = cx - w / 2, right = cx + w / 2;
      const garageBlock = preset.blocks.find((q) => q.garage);
      for (let s = 0; s < storeys; s++) {
        const y = s * 2.8 + 1.55;
        for (let x = left + 1.6; x < right - 1.0; x += 2.6) {
          if (Math.abs(x - doorX) < 1.3 && s === 0) continue;
          if (garageBlock && x > garageBlock.cx - garageBlock.w / 2 - 0.9 && x < garageBlock.cx + garageBlock.w / 2 + 0.9) continue;
          addWindow(group, mats, x, y, frontZ, 1.2, 1.35, 'z');
        }
      }
      // side and back windows
      for (let s = 0; s < storeys; s++) {
        const y = s * 2.8 + 1.55;
        for (let z = cz - d / 2 + 1.8; z < cz + d / 2 - 1.2; z += 3.2) {
          addWindow(group, mats, right, y, z, 1.1, 1.3, 'x');
          addWindow(group, mats, left, y, z, 1.1, 1.3, '-x');
        }
        for (let x = left + 2; x < right - 1.5; x += 3.4) addWindow(group, mats, x, y, cz - d / 2, 1.1, 1.3, '-z');
      }
    }
  }

  // fascia, soffit and gutters from the roof edges
  addEaveTrim(group, segs, mats, preset.overhang);

  // ground, driveway, walkway
  const gTexs = toTextures(grass(), renderer);
  const G = 1200;
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(G, G), new THREE.MeshStandardMaterial({ color: '#ffffff', map: gTexs.map, normalMap: gTexs.normalMap, roughness: 1 }));
  [gTexs.map, gTexs.normalMap].forEach((t) => t.repeat.set(G / 3, G / 3));
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; ground.name = 'ground';
  group.add(ground);
  const cTex = toTextures(concrete(), renderer);
  const garage = preset.blocks.find((q) => q.garage);
  const concreteMat = new THREE.MeshStandardMaterial({ color: '#ffffff', map: cTex.map, normalMap: cTex.normalMap, roughness: 0.95 });
  if (garage) {
    const len = 12;
    const dw = new THREE.Mesh(new THREE.PlaneGeometry(garage.w - 0.6, len), concreteMat.clone());
    dw.material.map = cTex.map.clone(); dw.material.map.repeat.set((garage.w - 0.6) / 2, len / 2);
    dw.rotation.x = -Math.PI / 2; dw.position.set(garage.cx, 0.01, garage.cz + garage.d / 2 + len / 2); dw.receiveShadow = true;
    group.add(dw);
  }
  const main = preset.blocks[0];
  const walk = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 6), concreteMat);
  walk.rotation.x = -Math.PI / 2; walk.position.set(preset.door?.x ?? 0, 0.012, main.cz + main.d / 2 + 3); walk.receiveShadow = true;
  group.add(walk);

  return { group, planes, segs, materials: mats, preset };
}

function addFrame(group, mat, x, y, z, w, h, t = 0.09) {
  const parts = [[w + t * 2, t, 0, h / 2 + t / 2], [w + t * 2, t, 0, -h / 2 - t / 2], [t, h, -w / 2 - t / 2, 0], [t, h, w / 2 + t / 2, 0]];
  for (const [pw, ph, ox, oy] of parts) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(pw, ph, 0.04), mat);
    m.position.set(x + ox, y + oy, z); m.castShadow = true;
    group.add(m);
  }
}

function addWindow(group, mats, x, y, z, w, h, facing) {
  const g = new THREE.Group();
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mats.glass);
  glass.position.z = 0.01;
  g.add(glass);
  const t = 0.08;
  for (const [pw, ph, ox, oy] of [[w + t * 2, t, 0, h / 2 + t / 2], [w + t * 2, t * 1.4, 0, -h / 2 - t * 0.7], [t, h, -w / 2 - t / 2, 0], [t, h, w / 2 + t / 2, 0], [t * 0.5, h, 0, 0], [w, t * 0.5, 0, 0]]) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(pw, ph, 0.05), mats.trim);
    m.position.set(ox, oy, 0.025); m.castShadow = true;
    g.add(m);
  }
  const rot = { z: 0, x: Math.PI / 2, '-x': -Math.PI / 2, '-z': Math.PI }[facing];
  g.rotation.y = rot;
  g.position.set(x, y, z);
  // nudge outward from the wall
  const out = new THREE.Vector3(0, 0, 0.01).applyAxisAngle(new THREE.Vector3(0, 1, 0), rot);
  g.position.add(out);
  group.add(g);
}

function addEaveTrim(group, segs, mats, overhang) {
  const fasciaH = 0.19;
  const geomF = [], geomS = [], geomG = [];
  const pushQuad = (arr, a, b, c, d) => { arr.push(a, b, c, a, c, d); };
  for (const kind of ['eave', 'rake']) {
    for (const s of segs[kind]) {
      const P = s.planes[0];
      const a2 = P.from3(s.A), b2 = P.from3(s.B);
      const mid = [(a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2];
      // outward horizontal direction
      const dir = new THREE.Vector3().subVectors(s.B, s.A).normalize();
      let out = new THREE.Vector3(dir.z, 0, -dir.x).normalize();
      const probe = P.to3(mid[0], mid[1]).addScaledVector(out, -0.1);
      const [pu, pv] = P.from3(probe);
      if (!P.contains2(pu, pv)) out.negate();
      const A = s.A.clone().addScaledVector(out, -0.005), B = s.B.clone().addScaledVector(out, -0.005);
      const down = new THREE.Vector3(0, -fasciaH, 0);
      pushQuad(geomF, A, B, B.clone().add(down), A.clone().add(down));
      if (kind === 'eave') {
        const inA = A.clone().add(down).addScaledVector(out, -overhang), inB = B.clone().add(down).addScaledVector(out, -overhang);
        pushQuad(geomS, A.clone().add(down), B.clone().add(down), inB, inA);
        // K-style gutter: front lip + bottom
        const gA = A.clone().addScaledVector(out, 0.13).add(new THREE.Vector3(0, -0.03, 0));
        const gB = B.clone().addScaledVector(out, 0.13).add(new THREE.Vector3(0, -0.03, 0));
        const gDown = new THREE.Vector3(0, -0.12, 0);
        pushQuad(geomG, gA, gB, gB.clone().add(gDown), gA.clone().add(gDown));
        pushQuad(geomG, gA.clone().add(gDown), gB.clone().add(gDown), B.clone().add(new THREE.Vector3(0, -0.15, 0)), A.clone().add(new THREE.Vector3(0, -0.15, 0)));
      }
    }
  }
  const mk = (pts, mat, name) => {
    if (!pts.length) return;
    const g = new THREE.BufferGeometry().setFromPoints(pts);
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat.clone());
    m.material.side = THREE.DoubleSide;
    m.castShadow = true; m.receiveShadow = true; m.name = name;
    group.add(m);
  };
  mk(geomF, mats.trim, 'fascia');
  mk(geomS, mats.trim, 'soffit');
  mk(geomG, mats.gutter, 'gutters');
}

/** Box with UVs in metres so siding textures keep their real scale. */
export function boxWorldUV(w, h, d) {
  const g = new THREE.BoxGeometry(w, h, d);
  const pos = g.attributes.position, nor = g.attributes.normal, uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i) + w / 2, y = pos.getY(i) + h / 2, z = pos.getZ(i) + d / 2;
    const nx = Math.abs(nor.getX(i)), ny = Math.abs(nor.getY(i));
    if (nx > 0.5) uv.setXY(i, z, y); else if (ny > 0.5) uv.setXY(i, x, z); else uv.setXY(i, x, y);
  }
  return g;
}

function polyGeometryWorldUV(pts, center) {
  const g = new THREE.BufferGeometry();
  const pos = [], uv = [];
  const n = new THREE.Vector3().subVectors(pts[1], pts[0]).cross(new THREE.Vector3().subVectors(pts[2], pts[0])).normalize();
  const cen = pts.reduce((s, p) => s.add(p), new THREE.Vector3()).multiplyScalar(1 / pts.length);
  const outward = cen.clone().sub(center).setY(0);
  let ordered = pts;
  if (n.dot(outward) < 0) ordered = [...pts].reverse();
  const horiz = Math.abs(n.x) > Math.abs(n.z) ? 'z' : 'x';
  for (let i = 1; i < ordered.length - 1; i++) {
    for (const p of [ordered[0], ordered[i], ordered[i + 1]]) { pos.push(p.x, p.y, p.z); uv.push(p[horiz], p.y); }
  }
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.computeVertexNormals();
  return g;
}
