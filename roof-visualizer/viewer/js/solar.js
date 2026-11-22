// Rooftop solar designer: panel arrays laid on the real roof planes, moved by dragging them and grown
// with the corner handle, an install timeline (mounts -> rails -> panels -> wiring), and the numbers:
// monthly generation (PVGIS-NSRDB table for the site, per tilt and facing), use, bill savings at the
// utility's rates, and the price of the parts and of a professional install.

import * as THREE from 'three';

const GAP = 0.02;          // between panels (m)
const LIFT = 0.12;         // panel top above the roof surface (m)
const EDGE = 0.3;          // clear band along every roof edge (m)
const RIDGE = 0.45;        // clear band below the ridge (fire-code style access, m)
const SNAP = 0.05;
const DEFAULT_PANEL = { id: 'generic-400', name: 'Generic 400 W module', watts: 400, size_mm: [1722, 1134], price: null, per: 'each', generic: true };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

export { MONTHS };

/**
 * ctx: scene, camera, dom (canvas), stage, controls, layers() -> RoofLayers | null, facing() -> degrees,
 * invalidate(ms), onChange(summary), focus(center: Vector3, radius) (optional camera move).
 */
export function createSolar(ctx) {
  const root = new THREE.Group(); root.name = 'solar'; ctx.scene.add(root);
  const S = { data: null, panel: { ...DEFAULT_PANEL }, inverter: null, racking: null, arrays: [], sel: 0, useAvg: null,
    install: 'pro', show: true, anim: null, built: false };
  const mats = makeMaterials();
  const ray = new THREE.Raycaster();
  let drag = null, changeQueued = false;

  // ---------------------------------------------------------------------------- geometry helpers
  const planes = () => ctx.layers()?.planes || [];
  const dims = (a) => { const [L, W] = (S.panel.size_mm || DEFAULT_PANEL.size_mm).map((x) => x / 1000); return a.portrait ? { w: W, h: L } : { w: L, h: W }; };
  const pitchDeg = (P) => THREE.MathUtils.radToDeg(P.slope);
  const bearing = (P) => ((((Math.atan2(-P.n.x, P.n.z) * 180) / Math.PI + ctx.facing()) % 360) + 360) % 360;

  function fits(P, u, v, w, h) {
    const m = EDGE;
    return P.contains2(u, v, m) && P.contains2(u + w, v, m) && P.contains2(u, v + h, m) && P.contains2(u + w, v + h, m)
      && P.contains2(u + w / 2, v + h + (RIDGE - EDGE), m) && P.contains2(u, v + h + (RIDGE - EDGE), 0) && P.contains2(u + w, v + h + (RIDGE - EDGE), 0);
  }

  /** Panel cells of an array: [{ r, c, u, v, ok }]. */
  function cells(a) {
    const P = planes()[a.plane];
    if (!P) return [];
    const { w, h } = dims(a);
    const out = [];
    for (let r = 0; r < a.rows; r++) for (let c = 0; c < a.cols; c++) {
      const u = a.u0 + c * (w + GAP), v = a.v0 + r * (h + GAP);
      out.push({ r, c, u, v, ok: fits(P, u, v, w, h) });
    }
    return out;
  }

  /** The most productive plane that can take at least one panel, and its best spot. */
  function bestPlane() {
    let best = null;
    planes().forEach((P, i) => {
      if (P.slope > THREE.MathUtils.degToRad(60)) return;
      const y = yieldPerKw(pitchDeg(P), bearing(P)).reduce((s, x) => s + x, 0);
      const cap = P.area * y;
      if (!best || cap > best.cap) best = { i, cap, y };
    });
    return best;
  }

  /** Largest rows x cols block that fits on plane i, placed by a coarse search (portrait). */
  function fill(i, { maxPanels = Infinity, portrait = true } = {}) {
    const P = planes()[i];
    const a = { plane: i, u0: 0, v0: 0, rows: 1, cols: 1, portrait };
    const { w, h } = dims(a);
    let best = null;
    const step = 0.1;
    for (let v0 = 0; v0 < P.vMax; v0 += step) {
      for (let u0 = 0; u0 < P.uMax; u0 += step) {
        if (!fits(P, u0, v0, w, h)) continue;
        // grow columns, then rows, while every cell fits
        let cols = 1; while (u0 + (cols + 1) * (w + GAP) - GAP <= P.uMax && fitsBlock(P, u0, v0, cols + 1, 1, w, h)) cols++;
        let rows = 1; while (fitsBlock(P, u0, v0, cols, rows + 1, w, h)) rows++;
        let n = rows * cols;
        if (n > maxPanels) { // trim to the target, keeping it wide
          rows = Math.max(1, Math.min(rows, Math.ceil(maxPanels / cols))); cols = Math.min(cols, Math.ceil(maxPanels / rows)); n = rows * cols;
        }
        if (!best || n > best.n) best = { n, u0, v0, rows, cols };
      }
    }
    if (!best) return null;
    return { ...a, u0: best.u0, v0: best.v0, rows: best.rows, cols: best.cols };
  }
  function fitsBlock(P, u0, v0, cols, rows, w, h) {
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) if (!fits(P, u0 + c * (w + GAP), v0 + r * (h + GAP), w, h)) return false;
    return true;
  }

  // ---------------------------------------------------------------------------- production
  function yieldPerKw(tilt, az) {
    const T = S.data?.pvgis;
    if (!T) return new Array(12).fill(0);
    const k = (t, a) => T.kwh_per_kw[`${t}|${a}`] || T.kwh_per_kw[`${t}|${a % 360}`];
    const tilts = T.tilts;
    const atAz = (t) => {
      if (t === 0) return T.kwh_per_kw['0|180'];
      const st = 15, a = ((az % 360) + 360) % 360, a0 = Math.floor(a / st) * st, a1 = (a0 + st) % 360, f = (a - a0) / st;
      const A = k(t, a0), B = k(t, a1);
      return A.map((x, m) => x * (1 - f) + B[m] * f);
    };
    let i = tilts.findIndex((t) => t >= tilt);
    if (i <= 0) return atAz(tilts[Math.max(0, i)]);
    if (i < 0) return atAz(tilts[tilts.length - 1]);
    const t0 = tilts[i - 1], t1 = tilts[i], f = (tilt - t0) / (t1 - t0);
    const A = atAz(t0), B = atAz(t1);
    return A.map((x, m) => x * (1 - f) + B[m] * f);
  }

  function useMonthly() {
    const U = S.data?.usage;
    const avg = S.useAvg ?? U?.annual_avg ?? 900;
    const shape = U?.shape || new Array(12).fill(1);
    const mean = shape.reduce((s, x) => s + x, 0) / 12;
    return shape.map((x) => (avg * x) / mean);
  }

  function priceOf(p) {
    if (!p || p.price == null) return null;
    const m = /pack of (\d+)/i.exec(p.per || '');
    return m ? p.price / Number(m[1]) : p.price;
  }

  function summary() {
    const R = S.data?.rates || {};
    const A = S.data?.assumptions || {};
    let panels = 0, misfit = 0;
    const gen = new Array(12).fill(0);
    const arrays = S.arrays.map((a, i) => {
      const P = planes()[a.plane];
      const cs = cells(a);
      const n = cs.filter((c) => c.ok).length;
      panels += n; misfit += cs.length - n;
      const kw = (n * S.panel.watts) / 1000;
      const y = P ? yieldPerKw(pitchDeg(P), bearing(P)) : new Array(12).fill(0);
      y.forEach((x, m) => { gen[m] += x * kw; });
      return { i, plane: a.plane, n, rows: a.rows, cols: a.cols, kw, faces: P ? compass(bearing(P)) : '', pitch: P ? pitchDeg(P) : 0, kwhPerKw: y.reduce((s, x) => s + x, 0) };
    });
    const kw = (panels * S.panel.watts) / 1000;
    const use = useMonthly();
    const res = R.residential || {};
    const summer = new Set(res.summer_months || [6, 7, 8, 9]);
    const retail = (m) => ((res.effective_total_cents_kwh?.[summer.has(m + 1) ? 'summer' : 'winter'] ?? A.retail_cents_kwh ?? 13) / 100);
    const exp = R.export || {};
    const buy = (exp.buyback_cents_kwh ?? A.buyback_cents_kwh ?? 3) / 100;
    const method = exp.method || 'monthly_net';
    // Without net metering, only solar the house uses as it is made saves the retail rate. From monthly
    // totals: the daytime part of the month's use (daytime_share) soaks up solar with diminishing returns,
    // used = D (1 - e^(-gen / D)); the rest is exported at the buyback rate.
    const dayShare = A.daytime_share ?? 0.45;
    const meter = panels ? (exp.extra_monthly_charge ?? 0) : 0;
    const months = gen.map((g, m) => {
      const u = use[m];
      let used;
      if (method === 'monthly_net') used = Math.min(g, u);
      else { const D = Math.max(1e-6, u * dayShare); used = D * (1 - Math.exp(-g / D)); }
      const exported = Math.max(0, g - used);
      const saving = used * retail(m) + exported * buy - meter;
      return { m, gen: g, use: u, used, exported, fromGrid: Math.max(0, u - used), saving, billBefore: u * retail(m), billAfter: Math.max(0, u * retail(m) - saving) };
    });
    const annual = (k) => months.reduce((s, x) => s + x[k], 0);
    // price
    const W = kw * 1000;
    const pp = priceOf(S.panel);
    const panelCost = pp != null ? pp * panels : (A.panel_per_w ?? 0.45) * W;
    const invCost = S.inverter && priceOf(S.inverter) != null ? priceOf(S.inverter) * (S.inverter.perPanel === false ? Math.max(1, Math.ceil(W / (S.inverter.watts || 3800))) : panels) : (A.inverter_per_w ?? 0.35) * W;
    const rackCost = S.racking && priceOf(S.racking) != null ? priceOf(S.racking) * Math.ceil(panels / (S.racking.holds || 1)) : (A.racking_per_w ?? 0.15) * W;
    const bos = (A.bos_per_w ?? 0.25) * W + (panels ? (A.permit_fixed ?? 400) : 0);
    const materials = panelCost + invCost + rackCost + bos;
    const proPerW = S.data?.rates?.installed_cost_per_w?.typical ?? A.pro_per_w ?? 3.0;
    const pro = Math.max(materials, proPerW * W);
    const price = S.install === 'pro' ? pro : materials;
    const incentive = (R.federal?.itc_25d_available ? 0.3 : 0) * price;
    const net = price - incentive;
    const save = annual('saving');
    return {
      panels, misfit, kw, arrays, months, monthsLabel: MONTHS,
      annualGen: annual('gen'), annualUse: annual('use'), annualUsed: annual('used'), annualExport: annual('exported'), annualSaving: save,
      offset: annual('use') ? annual('gen') / annual('use') : 0,
      price: { panels: panelCost, inverters: invCost, racking: rackCost, bos, materials, pro, chosen: price, incentive, net, panelGeneric: pp == null },
      payback: save > 0 ? net / save : null, method, buyback: buy, install: S.install, panel: S.panel,
    };
  }

  // ---------------------------------------------------------------------------- 3D
  function makeMaterials() {
    const cv = document.createElement('canvas'); cv.width = 128; cv.height = 192;
    const g = cv.getContext('2d');
    g.fillStyle = '#0d1a2e'; g.fillRect(0, 0, 128, 192);
    g.strokeStyle = 'rgba(150,170,200,0.55)'; g.lineWidth = 1.2;
    for (let x = 0; x <= 6; x++) { g.beginPath(); g.moveTo(4 + x * 20, 4); g.lineTo(4 + x * 20, 188); g.stroke(); }
    for (let y = 0; y <= 10; y++) { g.beginPath(); g.moveTo(4, 4 + y * 18.4); g.lineTo(124, 4 + y * 18.4); g.stroke(); }
    g.strokeStyle = 'rgba(200,210,225,0.35)'; g.lineWidth = 0.6;
    for (let x = 0; x < 6; x++) for (const dx of [7, 14]) { g.beginPath(); g.moveTo(4 + x * 20 + dx, 4); g.lineTo(4 + x * 20 + dx, 188); g.stroke(); }
    const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
    const cellsM = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.22, metalness: 0.35, envMapIntensity: 1.2 });
    const frame = new THREE.MeshStandardMaterial({ color: 0xc8ccd2, roughness: 0.35, metalness: 0.85 });
    const back = new THREE.MeshStandardMaterial({ color: 0xe6e6e6, roughness: 0.8 });
    const bad = new THREE.MeshBasicMaterial({ color: 0xff3b30, transparent: true, opacity: 0.45, depthWrite: false });
    const rail = new THREE.MeshStandardMaterial({ color: 0xb4b9bf, roughness: 0.4, metalness: 0.8 });
    const foot = new THREE.MeshStandardMaterial({ color: 0x2a2c30, roughness: 0.6, metalness: 0.3 });
    const wire = new THREE.LineBasicMaterial({ color: 0x111111 });
    const handle = new THREE.MeshBasicMaterial({ color: 0x1d6ad8, depthTest: false, transparent: true, opacity: 0.95 });
    const sel = new THREE.LineBasicMaterial({ color: 0x4c9cff, depthTest: false, transparent: true, opacity: 0.9 });
    return { panel: [frame, frame, cellsM, back, frame, frame], bad, rail, foot, wire, handle, sel };
  }

  function basis(P) {
    // x along the eave, y out of the roof, z down-slope (right-handed)
    return new THREE.Matrix4().makeBasis(P.h.clone(), P.n.clone(), P.b.clone().negate());
  }

  function place(obj, P, u, v, off, rot) {
    obj.position.copy(P.to3(u, v, off));
    obj.quaternion.setFromRotationMatrix(rot);
  }

  function rebuild() {
    for (const c of [...root.children]) { root.remove(c); c.traverse((o) => { if (o.geometry && !o.userData.shared) o.geometry.dispose(); }); }
    S.arrays.forEach((a, ai) => {
      const P = planes()[a.plane];
      if (!P) return;
      const g = new THREE.Group(); g.name = `solar array ${ai + 1}`; g.userData.array = ai;
      const rot = basis(P);
      const { w, h } = dims(a);
      const panelGeo = new THREE.BoxGeometry(w, 0.035, h);
      const parts = { feet: [], rails: [], panels: [], wires: [] };
      const cs = cells(a);
      // rails: two per row, under the panels, the length of the row
      for (let r = 0; r < a.rows; r++) {
        const rowLen = a.cols * (w + GAP) - GAP;
        for (const fv of [0.25, 0.75]) {
          const v = a.v0 + r * (h + GAP) + h * fv;
          const rail = new THREE.Mesh(new THREE.BoxGeometry(rowLen + 0.1, 0.04, 0.045), mats.rail);
          place(rail, P, a.u0 + rowLen / 2, v, LIFT - 0.055, rot); rail.userData = { kind: 'rail', array: ai, r, u: a.u0 + rowLen / 2, v };
          g.add(rail); parts.rails.push(rail);
          // feet (flashed L-feet) every ~1.2 m along the rail
          const n = Math.max(2, Math.round(rowLen / 1.2) + 1);
          for (let k = 0; k < n; k++) {
            const u = a.u0 + 0.05 + (rowLen - 0.1) * (k / (n - 1));
            const foot = new THREE.Mesh(new THREE.BoxGeometry(0.06, LIFT - 0.06, 0.1), mats.foot);
            place(foot, P, u, v, (LIFT - 0.06) / 2, rot); foot.userData = { kind: 'foot', array: ai, r, k };
            g.add(foot); parts.feet.push(foot);
          }
        }
      }
      for (const c of cs) {
        const m = new THREE.Mesh(panelGeo, c.ok ? mats.panel : mats.bad);
        place(m, P, c.u + w / 2, c.v + h / 2, LIFT, rot);
        m.userData = { kind: 'panel', array: ai, r: c.r, c: c.c, ok: c.ok, home: m.position.clone() };
        m.castShadow = true; m.receiveShadow = true;
        g.add(m); parts.panels.push(m);
      }
      // home run: a cable from the array's low corner down the roof to the eave
      const pts = [P.to3(a.u0 - 0.05, a.v0 + 0.1, LIFT - 0.06), P.to3(a.u0 - 0.05, 0.15, 0.02)];
      const wire = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mats.wire);
      wire.userData = { kind: 'wire', array: ai }; g.add(wire); parts.wires.push(wire);
      // selection outline and the grow handle
      if (ai === S.sel) {
        const u1 = a.u0 + a.cols * (w + GAP) - GAP, v1 = a.v0 + a.rows * (h + GAP) - GAP;
        const ring = [[a.u0, a.v0], [u1, a.v0], [u1, v1], [a.u0, v1], [a.u0, a.v0]].map(([u, v]) => P.to3(u - 0.04, v - 0.04, LIFT + 0.03));
        ring[1] = P.to3(u1 + 0.04, a.v0 - 0.04, LIFT + 0.03); ring[2] = P.to3(u1 + 0.04, v1 + 0.04, LIFT + 0.03); ring[3] = P.to3(a.u0 - 0.04, v1 + 0.04, LIFT + 0.03);
        const outline = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring), mats.sel);
        outline.renderOrder = 20; outline.userData = { kind: 'outline', array: ai }; g.add(outline);
        const hd = new THREE.Mesh(handleGeo, mats.handle);
        hd.position.copy(P.to3(u1 + 0.06, v1 + 0.06, LIFT + 0.08)); hd.renderOrder = 21;
        hd.userData = { kind: 'handle', array: ai }; g.add(hd);
      }
      g.userData.parts = parts;
      root.add(g);
    });
    root.visible = S.show;
    ctx.invalidate(400);
  }
  const handleGeo = new THREE.SphereGeometry(0.16, 20, 14); handleGeo.userData = {};

  // ---------------------------------------------------------------------------- dragging
  function ndc(e) {
    const r = ctx.dom.getBoundingClientRect();
    return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  }
  function rayPlane(P) {
    const pl = new THREE.Plane().setFromNormalAndCoplanarPoint(P.n, P.origin.clone().addScaledVector(P.n, LIFT));
    const p = new THREE.Vector3();
    return ray.ray.intersectPlane(pl, p) ? P.from3(p) : null;
  }
  function roofPlaneUnder() {
    const L = ctx.layers(); if (!L) return null;
    const hit = ray.intersectObject(L.root, true).find((x) => x.object.visible && !x.object.isLine);
    if (!hit) return null;
    let best = null, bestD = Infinity;
    L.planes.forEach((P, i) => { const [u, v] = P.from3(hit.point); if (!P.contains2(u, v, 0)) return; const d = Math.abs(P.distance(hit.point)); if (d < bestD) { bestD = d; best = i; } });
    return bestD < 0.4 ? best : null;
  }

  function onDown(e) {
    if (!S.show || !S.arrays.length || (e.button !== undefined && e.button !== 0)) return;
    ray.setFromCamera(ndc(e), ctx.camera);
    const hit = ray.intersectObject(root, true).find((h) => ['panel', 'handle', 'rail'].includes(h.object.userData.kind));
    if (!hit) return;
    const ud = hit.object.userData;
    const a = S.arrays[ud.array];
    const P = planes()[a.plane];
    const uv = rayPlane(P);
    if (!uv) return;
    e.stopPropagation(); e.preventDefault();
    ctx.controls.enabled = false;
    if (S.sel !== ud.array) { S.sel = ud.array; rebuild(); }
    drag = { kind: ud.kind === 'handle' ? 'grow' : 'move', ai: ud.array, start: uv, u0: a.u0, v0: a.v0, rows: a.rows, cols: a.cols, plane: a.plane, moved: false, id: e.pointerId };
    window.addEventListener('pointermove', onMove, true);
    window.addEventListener('pointerup', onUp, true);
    window.addEventListener('pointercancel', onUp, true);
  }
  function onMove(e) {
    if (!drag || (drag.id !== undefined && e.pointerId !== drag.id)) return;
    e.preventDefault();
    ray.setFromCamera(ndc(e), ctx.camera);
    const a = S.arrays[drag.ai];
    if (drag.kind === 'move') {
      // over another roof plane: carry the array onto it, centred under the pointer
      const other = roofPlaneUnder();
      if (other != null && other !== a.plane && planes()[other].slope < THREE.MathUtils.degToRad(60)) {
        const Q = planes()[other]; const uv = rayPlane(Q);
        if (uv) {
          const { w, h } = dims(a);
          a.plane = other; a.u0 = uv[0] - (a.cols * (w + GAP)) / 2; a.v0 = uv[1] - (a.rows * (h + GAP)) / 2;
          drag = { ...drag, plane: other, start: uv, u0: a.u0, v0: a.v0 };
          drag.moved = true; rebuild(); queueChange(); return;
        }
      }
      const uv = rayPlane(planes()[a.plane]); if (!uv) return;
      const du = uv[0] - drag.start[0], dv = uv[1] - drag.start[1];
      if (Math.hypot(du, dv) > 0.03) drag.moved = true;
      a.u0 = Math.round((drag.u0 + du) / SNAP) * SNAP; a.v0 = Math.round((drag.v0 + dv) / SNAP) * SNAP;
    } else {
      const uv = rayPlane(planes()[a.plane]); if (!uv) return;
      const { w, h } = dims(a);
      a.cols = Math.max(1, Math.min(40, Math.round((uv[0] - a.u0 + GAP) / (w + GAP))));
      a.rows = Math.max(1, Math.min(20, Math.round((uv[1] - a.v0 + GAP) / (h + GAP))));
      drag.moved = true;
    }
    rebuild(); queueChange();
  }
  function onUp(e) {
    if (!drag) return;
    window.removeEventListener('pointermove', onMove, true);
    window.removeEventListener('pointerup', onUp, true);
    window.removeEventListener('pointercancel', onUp, true);
    ctx.controls.enabled = true;
    drag = null; S.lastDragEnd = performance.now();
    rebuild(); queueChange();
  }
  // capture phase on the stage, so a press on a panel never starts an orbit
  ctx.stage.addEventListener('pointerdown', onDown, true);

  function queueChange() {
    if (changeQueued) return;
    changeQueued = true;
    requestAnimationFrame(() => { changeQueued = false; ctx.onChange?.(summary()); });
  }

  // ---------------------------------------------------------------------------- install animation
  function play() {
    if (!S.arrays.length) return;
    rebuild();
    const steps = [];
    let t = 0;
    root.children.forEach((g) => {
      const { feet, rails, panels, wires } = g.userData.parts || {};
      if (!feet) return;
      feet.forEach((o, i) => steps.push({ o, kind: 'foot', t0: t + i * 0.06, dur: 0.25 }));
      t += feet.length * 0.06 + 0.3;
      rails.forEach((o, i) => steps.push({ o, kind: 'rail', t0: t + i * 0.25, dur: 0.45 }));
      t += rails.length * 0.25 + 0.4;
      const ok = panels.filter((p) => p.userData.ok);
      ok.sort((p, q) => p.userData.r - q.userData.r || p.userData.c - q.userData.c).forEach((o, i) => steps.push({ o, kind: 'panel', t0: t + i * 0.22, dur: 0.55 }));
      panels.filter((p) => !p.userData.ok).forEach((o) => { o.visible = false; });
      t += ok.length * 0.22 + 0.5;
      wires.forEach((o) => steps.push({ o, kind: 'wire', t0: t, dur: 0.4 }));
      t += 0.6;
      g.traverse((o) => { if (['outline', 'handle'].includes(o.userData.kind)) o.visible = false; });
    });
    for (const s of steps) { s.home = s.o.position.clone(); s.o.visible = false; s.o.scale.set(1, 1, 1); }
    S.anim = { t: 0, t0: performance.now(), end: t + 0.3, steps };
    S.show = true; root.visible = true;
    const box = new THREE.Box3().setFromObject(root);
    if (!box.isEmpty() && ctx.focus) ctx.focus(box.getCenter(new THREE.Vector3()), box.getSize(new THREE.Vector3()).length() / 2);
    ctx.invalidate(1000);
    queueChange();
  }

  function update(dt) {
    const L = ctx.layers();
    root.visible = S.show && !(L && (L.explode > 0.01 || L.cut < 0.99));
    if (!S.anim) return false;
    const A = S.anim;
    A.t = (performance.now() - A.t0) / 1000;   // wall clock: the same pace however fast frames come
    for (const s of A.steps) {
      const k = THREE.MathUtils.clamp((A.t - s.t0) / s.dur, 0, 1);
      const e = 1 - Math.pow(1 - k, 3);
      s.o.visible = k > 0;
      if (s.kind === 'panel') {
        // lowered in from above the roof, along the roof normal
        const n = s.o.up.clone().applyQuaternion(s.o.quaternion);
        s.o.position.copy(s.home).addScaledVector(n, (1 - e) * 1.4);
      } else if (s.kind === 'rail') s.o.scale.set(Math.max(0.001, e), 1, 1);
      else if (s.kind === 'foot') s.o.scale.set(1, Math.max(0.001, e), 1);
    }
    if (A.t >= A.end) {
      for (const s of A.steps) { s.o.visible = true; s.o.position.copy(s.home); s.o.scale.set(1, 1, 1); }
      S.anim = null; S.built = true; rebuild(); queueChange();
    }
    return true;
  }

  // ---------------------------------------------------------------------------- public
  function ensureArray() {
    if (S.arrays.length || !planes().length) return;
    const b = bestPlane();
    if (!b) return;
    const use = useMonthly().reduce((s, x) => s + x, 0);
    const needKw = use / Math.max(1, b.y);
    const target = Math.max(4, Math.min(24, Math.round((needKw * 1000) / S.panel.watts * 0.6)));   // start near 60 % of use
    const a = fill(b.i, { maxPanels: target });
    if (a) { S.arrays = [a]; S.sel = 0; }
  }

  const api = {
    root,
    get state() { return { arrays: S.arrays.map((a) => ({ ...a })), sel: S.sel, panel: S.panel, install: S.install, useAvg: S.useAvg, show: S.show, animating: !!S.anim }; },
    get animating() { return !!S.anim; },
    get dragging() { return !!drag || performance.now() - (S.lastDragEnd || 0) < 250; },
    setData(d) { S.data = d; queueChange(); },
    setPanel(p) {
      if (!p) return;
      const keepKw = summary().kw;
      S.panel = { ...p, size_mm: p.size_mm || DEFAULT_PANEL.size_mm, watts: p.watts || DEFAULT_PANEL.watts };
      // keep about the same system size with the new module
      if (S.arrays.length && keepKw > 0) {
        const a = S.arrays[S.sel] || S.arrays[0];
        const n = Math.max(1, Math.round((keepKw * 1000) / S.panel.watts));
        a.cols = Math.max(1, Math.min(a.cols, n)); a.rows = Math.max(1, Math.ceil(n / a.cols));
      }
      rebuild(); queueChange();
    },
    setPart(kind, p) { if (kind === 'inverter') S.inverter = p; if (kind === 'racking') S.racking = p; queueChange(); },
    start() { S.show = true; ensureArray(); rebuild(); queueChange(); },
    show(on = true) { S.show = on; root.visible = on; ctx.invalidate(300); queueChange(); },
    resize(dr, dc) { const a = S.arrays[S.sel]; if (!a) return; a.rows = Math.max(1, a.rows + dr); a.cols = Math.max(1, a.cols + dc); rebuild(); queueChange(); },
    rotate() { const a = S.arrays[S.sel]; if (!a) return; a.portrait = !a.portrait; rebuild(); queueChange(); },
    addArray() {
      const used = new Set(S.arrays.map((a) => a.plane));
      const cand = planes().map((P, i) => ({ i, y: yieldPerKw(pitchDeg(P), bearing(P)).reduce((s, x) => s + x, 0) * P.area }))
        .filter((c) => !used.has(c.i) && planes()[c.i].slope < THREE.MathUtils.degToRad(60)).sort((p, q) => q.y - p.y);
      for (const c of cand) { const a = fill(c.i, { maxPanels: 8 }); if (a) { S.arrays.push(a); S.sel = S.arrays.length - 1; break; } }
      rebuild(); queueChange();
    },
    removeArray() { if (!S.arrays.length) return; S.arrays.splice(S.sel, 1); S.sel = Math.max(0, S.sel - 1); rebuild(); queueChange(); },
    select(i) { if (S.arrays[i]) { S.sel = i; rebuild(); queueChange(); } },
    /** Size the system to cover `target` (fraction) of the year's use, best planes first. */
    sizeToUse(target = 1) {
      const need = useMonthly().reduce((s, x) => s + x, 0) * target;
      const order = planes().map((P, i) => ({ i, y: yieldPerKw(pitchDeg(P), bearing(P)).reduce((s, x) => s + x, 0) }))
        .filter((c) => planes()[c.i].slope < THREE.MathUtils.degToRad(60)).sort((p, q) => q.y - p.y);
      const arrays = [];
      let left = need;
      // big faces first (best yield among faces that take 6+ panels), small faces only to top up
      const cap = new Map(order.map((c) => { const f = fill(c.i); return [c.i, f ? cells(f).filter((x) => x.ok).length : 0]; }));
      const ranked = [...order.filter((c) => cap.get(c.i) >= 6), ...order.filter((c) => cap.get(c.i) > 0 && cap.get(c.i) < 6)];
      for (const c of ranked) {
        if (left <= 0) break;
        const perPanel = (c.y * S.panel.watts) / 1000;
        const a = fill(c.i, { maxPanels: Math.ceil(left / perPanel) });
        if (!a) continue;
        const n = cells(a).filter((x) => x.ok).length;
        if (!n) continue;
        arrays.push(a); left -= n * perPanel;
      }
      S.arrays = arrays; S.sel = 0; rebuild(); queueChange();
    },
    fillPlane() { const a = S.arrays[S.sel]; if (!a) return; const f = fill(a.plane, { portrait: a.portrait }); if (f) S.arrays[S.sel] = f; rebuild(); queueChange(); },
    clear() { S.arrays = []; rebuild(); queueChange(); },
    setUse(avg) { S.useAvg = avg; queueChange(); },
    setInstall(mode) { S.install = mode; queueChange(); },
    play,
    update,
    summary,
    /** House or layers changed: drop arrays that no longer sit on a plane, redraw the rest. */
    onLayers() {
      // a different house (another plane count) invalidates the layout; a rebuilt stack of the same house keeps it
      const n = planes().length;
      if (S.planeCount != null && n !== S.planeCount) S.arrays = [];
      S.planeCount = n;
      S.arrays = S.arrays.filter((a) => planes()[a.plane]); if (S.sel >= S.arrays.length) S.sel = 0; rebuild(); queueChange();
    },
    yieldPerKw,
  };
  return api;
}

export function compass(deg) {
  return ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'][Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}
export { DAYS };
