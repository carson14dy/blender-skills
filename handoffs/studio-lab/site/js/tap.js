// Tap the roof (Sioux Falls studio, supplier plan 9.4): a short tap on a roof plane shows its area,
// pitch, facing and the covering on it, and outlines the plane. Read-only. A drag still orbits:
// only a press that moved less than 6 px and lasted under 400 ms counts as a tap.

import * as THREE from 'three';
import { pitchLabel } from './util.js';

const SQFT = 0.3048 * 0.3048;
const COMPASS = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'];

/** Compass bearing of a plane's downhill direction, with the house front facing `facing` degrees. */
export function facingOf(n, facing = 180) {
  const deg = (Math.atan2(-n.x, n.z) * 180) / Math.PI + facing;
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}

/**
 * opts: dom (the canvas), stage, camera, scene, layers() -> RoofLayers, facing() -> degrees,
 * covering() -> text, onChange() (open the picker on the covering slot), invalidate().
 */
export function createTap({ dom, stage, camera, scene, layers, facing, covering, onChange, invalidate }) {
  const ray = new THREE.Raycaster();
  let down = null, card = null, outline = null, usedLayers = null;

  dom.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, t: performance.now(), id: e.pointerId, button: e.button }; }, { passive: true });
  dom.addEventListener('pointerup', (e) => {
    const d = down; down = null;
    if (!d || d.id !== e.pointerId || d.button !== 0) return;
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) >= 6 || performance.now() - d.t >= 400) return;
    tap(e.clientX, e.clientY);
  }, { passive: true });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && card) close(); });

  function tap(cx, cy) {
    const L = layers();
    if (!L) return;
    const r = dom.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1), camera);
    const hit = ray.intersectObject(L.root, true).find((h) => h.object.visible && !h.object.isLine);
    if (!hit) { close(); return; }
    // the hit layer may be floated up (layers view): measure in the layer's own frame
    let root = hit.object;
    while (root.parent && !root.name.startsWith('RT_layer_')) root = root.parent;
    const p = hit.point.clone().sub(root.position);
    let best = null, bestD = Infinity;
    L.planes.forEach((P, i) => {
      const [u, v] = P.from3(p);
      if (!P.contains2(u, v, -0.08)) return;
      const dist = Math.abs(P.distance(p));
      if (dist < bestD) { bestD = dist; best = { P, i }; }
    });
    if (!best || bestD > 0.25) { close(); return; }
    show(best.P, best.i, L, root, cx - r.left, cy - r.top);
  }

  function show(P, i, L, root, x, y) {
    close();
    usedLayers = L;
    // outline: the plane's boundary, 3 cm above the covering, riding with its layer
    const pts = [];
    for (const e of P.edges) pts.push(P.to3(e.a[0], e.a[1], 0.05), P.to3(e.b[0], e.b[1], 0.05));
    const g = new THREE.BufferGeometry().setFromPoints(pts);
    outline = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x4c9cff, depthTest: false, transparent: true, opacity: 0.95 }));
    outline.name = 'tapOutline';
    outline.renderOrder = 10;
    // a soft fill on the plane, so the outline reads at any distance
    const tri = [];
    for (const t of P.tris) for (const [u, v] of t) tri.push(P.to3(u, v, 0.045));
    const fill = new THREE.Mesh(new THREE.BufferGeometry().setFromPoints(tri), new THREE.MeshBasicMaterial({ color: 0x4c9cff, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false }));
    fill.renderOrder = 9;
    outline.add(fill);
    outline.onBeforeRender = () => {
      if (layers() !== usedLayers) { queueMicrotask(close); return; }
      outline.position.y = root.parent ? root.position.y : 0;
    };
    scene.add(outline);
    const sqft = Math.round(P.area / SQFT);
    const pitch = pitchLabel(Math.round(Math.tan(P.slope) * 12 * 2) / 2);
    card = document.createElement('div');
    card.className = 'sf sf-tap';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', `Roof plane ${i + 1}`);
    const h = document.createElement('p'); h.className = 'sf-tap-h';
    h.textContent = `Roof plane ${i + 1} of ${L.planes.length} · ${sqft.toLocaleString('en-US')} sq ft · ${pitch} · faces ${facingOf(P.n, facing())}`;
    const c = document.createElement('p'); c.textContent = `Covering: ${covering()}`;
    const row = document.createElement('div'); row.className = 'sf-lbtns';
    const change = document.createElement('button'); change.type = 'button'; change.className = 'btn primary'; change.textContent = 'Change product';
    change.onclick = () => { close(); onChange(); };
    const x0 = document.createElement('button'); x0.type = 'button'; x0.className = 'btn'; x0.textContent = 'Close';
    x0.onclick = close;
    row.append(change, x0);
    card.append(h, c, row);
    stage.append(card);
    // near the tap on wide screens; a sheet along the bottom of the 3D view on phones
    if (stage.clientWidth > 560) {
      const w = card.offsetWidth, hh = card.offsetHeight;
      card.style.left = `${Math.max(12, Math.min(stage.clientWidth - w - 12, x + 14))}px`;
      card.style.top = `${Math.max(64, Math.min(stage.clientHeight - hh - 84, y + 14))}px`;
    } else card.classList.add('sheet');
    invalidate();
  }

  function close() {
    card?.remove(); card = null;
    if (outline) { scene.remove(outline); outline.traverse((o) => { o.geometry?.dispose(); o.material?.dispose(); }); outline = null; }
    usedLayers = null;
    invalidate();
  }

  return { close, tapAt: (x, y) => { const r = dom.getBoundingClientRect(); tap(r.left + x, r.top + y); return !!card; }, get open() { return card ? card.querySelector('.sf-tap-h').textContent : null; } };
}
