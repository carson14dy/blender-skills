// Roof Studio Lab: four free tools tried inside the studio, each with an on/off control, a
// "Run test" that measures in this browser, and the findings in short.
//   1. <model-viewer> (Google, Apache-2.0): the current roof in AR on a phone
//   2. three.js WebGPURenderer (MIT, same three@0.186.1): side-by-side with WebGLRenderer
//   3. 3d-tiles-renderer (NASA-AMMOS, Apache-2.0): a local 3D Tiles 1.1 neighbourhood
//   4. Spark (sparkjsdev, MIT): Gaussian-splat surroundings from 3DEP lidar + NAIP 2025
// Libraries load on first use only, so the studio itself starts exactly as before.

import * as THREE from 'three';
import { makeSkyTexture } from './render.js';
import { FINDINGS, PROJECT } from './lab-findings.js';

const RS = window.roofStudio;
const L = RS.lab;
const { scene, camera, renderer, controls } = RS.three;
const MEASURED_ID = '1601-s-discovery-ave';
const MEASURED_FILE = '1601-s-discovery-ave.gltf.json';
const $ = (id) => document.getElementById(id);
const results = {};
L.results = results;

// collect three.js / library warnings (two copies of three, unsupported materials ...)
const warnings = [];
for (const k of ['warn', 'error']) {
  const orig = console[k].bind(console);
  console[k] = (...a) => { try { warnings.push({ k, t: performance.now(), m: a.map((x) => (x?.message || String(x))).join(' ').slice(0, 300) }); } catch (_) { /* ignore */ } orig(...a); };
}
const warningsSince = (t0, re) => warnings.filter((w) => w.t >= t0 && (!re || re.test(w.m))).map((w) => w.m);

// ---------------------------------------------------------------------------
// small helpers

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c);
  return e;
}
const kb = (b) => (b == null ? 'n/a' : b >= 1048576 ? `${(b / 1048576).toFixed(2)} MB` : `${(b / 1024).toFixed(1)} KB`);
const ms = (t) => (t == null ? 'n/a' : t >= 1000 ? `${(t / 1000).toFixed(2)} s` : `${t.toFixed(t < 10 ? 1 : 0)} ms`);
const getJSON = async (u) => (await fetch(u, { cache: 'no-store' })).json();

/** The artifact host serves no .glb or .spz, so binaries ship as base64 JSON (tools/pack_json.py). */
async function fetchPacked(url, init) {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${url.split('/').pop()}: HTTP ${r.status}`);
  const j = await r.json();
  if (j.packed !== 'base64') throw new Error(`${url.split('/').pop()}: not a packed file`);
  const bytes = Uint8Array.fromBase64 ? Uint8Array.fromBase64(j.base64) : Uint8Array.from(atob(j.base64), (c) => c.charCodeAt(0));
  if (bytes.byteLength !== j.bytes) throw new Error(`${j.name}: size mismatch`);
  return bytes.buffer;
}

/** 3d-tiles-renderer plugin: tileset.json names q0.glb (so the GLB parser is chosen); fetch q0.glb.json instead. */
const PackedGlbPlugin = {
  name: 'PACKED_GLB_PLUGIN',
  fetchData(url, options) {
    if (!/\.glb(\?|#|$)/i.test(url)) return null;
    return fetchPacked(url.replace(/\.glb(?=\?|#|$)/i, '.glb.json'), { signal: options?.signal });
  },
};

/** Bytes the browser fetched for URLs matching `re` (Resource Timing; cross-origin needs Timing-Allow-Origin). */
function fetchedBytes(re) {
  const es = performance.getEntriesByType('resource').filter((e) => re.test(e.name));
  if (!es.length) return null;
  const sum = (k) => es.reduce((s, e) => s + (e[k] || 0), 0);
  return { files: es.length, transfer: sum('transferSize'), encoded: sum('encodedBodySize'), decoded: sum('decodedBodySize'), cors: es.some((e) => e.encodedBodySize === 0 && e.duration > 0 && !e.name.startsWith(location.origin)) };
}

/** Frame rate of the studio's own loop for `dur` ms (keeps frames coming while it measures). */
function measureFrames(dur = 2500) {
  return new Promise((resolve) => {
    const times = [], calls = [], tris = [];
    const t0 = performance.now();
    const hook = () => {
      const now = performance.now();
      times.push(now); calls.push(renderer.info.render.calls); tris.push(renderer.info.render.triangles);
      if (now - t0 > dur) {
        L.frameHooks.delete(hook);
        const d = times.slice(1).map((t, i) => t - times[i]).sort((a, b) => a - b);
        const mean = d.reduce((s, x) => s + x, 0) / Math.max(1, d.length);
        resolve({ fps: d.length ? 1000 / mean : 0, meanMs: mean, p95Ms: d[Math.floor(d.length * 0.95)] || 0, frames: d.length,
          drawCalls: calls[calls.length - 1], triangles: tris[tris.length - 1] });
      }
      return true;
    };
    L.frameHooks.add(hook);
    L.invalidate(dur + 200);
  });
}

/** GPU-inclusive time of one studio frame (render + 1-pixel readback), median of n, with the loop paused. */
async function timeMainRender(n = 8) {
  L.setBusy(true);
  try {
    const gl = renderer.getContext(); const px = new Uint8Array(4);
    const t = [];
    renderer.render(scene, camera); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); // warm-up
    for (let i = 0; i < n; i++) {
      const a = performance.now(); renderer.render(scene, camera); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); t.push(performance.now() - a);
      await new Promise((r) => setTimeout(r, 0));
    }
    t.sort((a, b) => a - b);
    return { medianMs: t[Math.floor(n / 2)], calls: renderer.info.render.calls, triangles: renderer.info.render.triangles };
  } finally { L.setBusy(false); }
}

async function ensureMeasured() {
  if (L.houseFile() === MEASURED_FILE && L.houseRoot()) return;
  L.toast('Opening the measured house (1601 S Discovery Ave) for the Lab…');
  await L.openMeasuredHouse(MEASURED_ID);
}
const houseOffset = () => L.houseRoot()?.position.clone() ?? new THREE.Vector3();

let siteP = null;
const site = () => (siteP ??= getJSON('lab/data/site.json'));

function setAttribution() {
  const parts = [];
  if (T.on) parts.push('Contains data from the City of Sioux Falls, CC BY 4.0', 'Lidar: USGS 3DEP');
  if (S.on) { if (!T.on) parts.push('Lidar: USGS 3DEP'); parts.push('Imagery: USDA NAIP 2025'); }
  $('labAttrib').hidden = !parts.length;
  $('labAttrib').textContent = parts.join(' · ');
}

function table(rows) {
  return el('table', { class: 'lab-res' }, rows.map(([k, v, cls]) => el('tr', cls ? { class: cls } : {}, el('td', { text: k }), el('td', { text: String(v) }))));
}

function widenView(on) {
  controls.maxDistance = on ? 650 : 180;
}

// ---------------------------------------------------------------------------
// Tool 1: <model-viewer> AR

const MV = { on: false, url: null, mv: null, loaded: false };
const AR_HIDDEN = ['oldFelt', 'oldShingles', 'deckRepair', 'iceWater', 'underlayment', 'starter', 'nails'];

async function loadModelViewer() {
  if (customElements.get('model-viewer')) return 0;
  const t0 = performance.now();
  // model-viewer bundles a meshopt decoder that compiles WebAssembly on import; a page policy without
  // 'wasm-unsafe-eval' refuses it. Only meshopt-compressed GLBs need it (ours are not), so note it quietly.
  const onRej = (e) => { if (/WebAssembly/.test(String(e.reason?.message || e.reason))) { MV.wasmBlocked = true; e.preventDefault(); } };
  window.addEventListener('unhandledrejection', onRej);
  try {
    await import('@google/model-viewer');
    await customElements.whenDefined('model-viewer');
    await new Promise((r) => setTimeout(r, 50));
  } finally { setTimeout(() => window.removeEventListener('unhandledrejection', onRej), 2000); }
  return performance.now() - t0;
}

/** What a GLB holds: image bytes vs geometry bytes, counts. */
function glbBreakdown(buf) {
  const dv = new DataView(buf);
  const jl = dv.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 20, jl)));
  const imgViews = new Set((json.images || []).map((i) => i.bufferView));
  let img = 0, geo = 0;
  (json.bufferViews || []).forEach((v, i) => { if (imgViews.has(i)) img += v.byteLength; else geo += v.byteLength; });
  return { images: json.images?.length || 0, imageBytes: img, geometryBytes: geo, meshes: json.meshes?.length || 0, materials: json.materials?.length || 0, nodes: json.nodes?.length || 0 };
}

async function mvExport() {
  const house = $('mvHouse').checked;
  const t0 = performance.now();
  const glb = await L.buildSceneGlb({ house, skip: $('mvCovered').checked ? AR_HIDDEN : [], maxTextureSize: Number($('mvTex').value) || Infinity, jpeg: $('mvJpeg').checked });
  const t = performance.now() - t0;
  if (MV.url) URL.revokeObjectURL(MV.url);
  MV.url = URL.createObjectURL(new Blob([glb], { type: 'model/gltf-binary' }));
  return { bytes: glb.byteLength, ms: t };
}

async function mvToggle(on) {
  MV.on = on;
  const box = $('mvBox');
  if (!on) { box.innerHTML = ''; MV.mv = null; if (MV.url) URL.revokeObjectURL(MV.url); MV.url = null; return; }
  await ensureMeasured();
  $('mvStatus').textContent = 'loading <model-viewer>…';
  try {
    await loadModelViewer();
    const ex = await mvExport();
    const mv = el('model-viewer', {
      class: 'lab-mv', src: MV.url, alt: 'Current roof and house in 3D', ar: true, 'ar-modes': 'webxr scene-viewer quick-look',
      'ar-scale': 'auto', 'ar-placement': 'floor', 'camera-controls': true, 'touch-action': 'pan-y', 'shadow-intensity': '0.8',
      exposure: '1', 'tone-mapping': 'agx', 'interaction-prompt': 'none',
    });
    MV.loaded = false;
    mv.addEventListener('load', () => { MV.loaded = true; $('mvStatus').textContent = `loaded ${kb(ex.bytes)} · AR ${mv.canActivateAR ? 'available' : 'not available here'}`; });
    mv.addEventListener('error', (e) => { $('mvStatus').textContent = `error: ${e.detail?.type || 'load failed'}`; });
    mv.addEventListener('ar-status', (e) => { results.modelViewer = { ...(results.modelViewer || {}), arStatus: e.detail.status }; $('mvStatus').textContent = `AR status: ${e.detail.status}`; });
    box.replaceChildren(mv);
    MV.mv = mv;
  } catch (e) {
    console.error(e);
    $('mvStatus').textContent = `could not start: ${e.message}`;
  }
}

async function arProbe() {
  const out = {};
  out.inIframe = (() => { try { return window.self !== window.top; } catch (_) { return true; } })();
  const ua = navigator.userAgent;
  out.platform = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) ? 'iOS' : /Android/.test(ua) ? 'Android' : 'desktop';
  out.webxrApi = !!navigator.xr;
  out.xrPolicy = document.featurePolicy?.allowsFeature ? document.featurePolicy.allowsFeature('xr-spatial-tracking') : 'unknown';
  out.immersiveAr = 'n/a';
  if (navigator.xr) {
    try { out.immersiveAr = await navigator.xr.isSessionSupported('immersive-ar'); } catch (e) { out.immersiveAr = `blocked (${e.name})`; }
  }
  out.quickLookAnchor = (() => { try { return document.createElement('a').relList.supports('ar'); } catch (_) { return false; } })();
  // Scene Viewer is an Android intent that hands Google's app a URL it must download itself: a blob: URL cannot work
  out.sceneViewer = out.platform === 'Android' ? 'needs a public https GLB URL (blob: is private to this page)' : 'Android only';
  return out;
}

async function mvTest() {
  const r = { tool: 'model-viewer 4.4.0 (module build, shares three 0.186.1)' };
  const t0 = performance.now();
  r.importMs = await loadModelViewer();
  await ensureMeasured();
  const full = await (async () => { const a = performance.now(); const g = await L.buildSceneGlb({ house: false }); return { bytes: g.byteLength, ms: performance.now() - a, ...glbBreakdown(g) }; })();
  r.exportLayersOnly = { ...full };
  if (!MV.on) { $('mvOn').checked = true; await mvToggle(true); } else { const ex = await mvExport(); MV.mv.src = MV.url; MV.loaded = false; r.reExport = ex; }
  const ex2 = performance.now();
  const loaded = await new Promise((res) => {
    if (MV.loaded) return res(true);
    const done = (ok) => () => res(ok);
    MV.mv.addEventListener('load', done(true), { once: true });
    MV.mv.addEventListener('error', done(false), { once: true });
    setTimeout(done(false), 20000);
  });
  r.viewerLoadMs = performance.now() - ex2;
  r.loaded = loaded;
  const arBuf = await (await fetch(MV.url)).arrayBuffer();
  r.arGlbBytes = arBuf.byteLength;
  r.arGlb = glbBreakdown(arBuf);
  r.arTextureMax = Number($('mvTex').value) || 'full';
  r.arJpeg = $('mvJpeg').checked;
  r.canActivateAR = !!MV.mv?.canActivateAR;
  Object.assign(r, await arProbe());
  r.bundle = fetchedBytes(/@google\/model-viewer/);
  r.threeRevision = THREE.REVISION;
  r.meshoptWasmBlocked = !!MV.wasmBlocked;
  r.multipleThree = warningsSince(0, /Multiple instances of Three/).length > 0;
  r.mvWarnings = warningsSince(t0, /model-viewer|three/i).slice(0, 5);
  r.totalMs = performance.now() - t0;
  results.modelViewer = { ...(results.modelViewer || {}), ...r };
  const rows = [
    ['Loaded in viewer', loaded ? 'yes' : 'no', loaded ? 'good' : 'bad'],
    ['Library import', ms(r.importMs)],
    ['Library download', r.bundle ? `${kb(r.bundle.transfer || r.bundle.encoded)} (${r.bundle.files} file)` : '475 KB min (cached or no timing)'],
    ['Bundled meshopt decoder (WASM)', r.meshoptWasmBlocked ? 'blocked by page policy (only needed for meshopt GLBs)' : 'ok', r.meshoptWasmBlocked ? 'bad' : ''],
    ['three copies', r.multipleThree ? '2 (warning seen)' : `1 (r${r.threeRevision}, shared)`, r.multipleThree ? 'bad' : 'good'],
    ['AR GLB (exterior layers' + ($('mvHouse').checked ? ' + house' : '') + `, textures ≤ ${r.arTextureMax}${r.arJpeg ? ' JPEG' : ' PNG'})`, `${kb(r.arGlbBytes)}: ${kb(r.arGlb.imageBytes)} images, ${kb(r.arGlb.geometryBytes)} geometry`, r.arGlbBytes > 8e6 ? 'bad' : 'good'],
    ['Download-button GLB (all visible layers)', `${kb(full.bytes)} in ${ms(full.ms)} (${kb(full.imageBytes)} images)`, full.bytes > 8e6 ? 'bad' : ''],
    ['Viewer load after export', ms(r.viewerLoadMs)],
    ['Platform / in iframe', `${r.platform} / ${r.inIframe ? 'yes' : 'no'}`],
    ['WebXR API / xr policy', `${r.webxrApi ? 'yes' : 'no'} / ${r.xrPolicy}`, r.xrPolicy === false ? 'bad' : ''],
    ['immersive-ar supported', String(r.immersiveAr), r.immersiveAr === true ? 'good' : 'bad'],
    ['Quick Look (<a rel=ar>)', r.quickLookAnchor ? 'supported' : 'no', r.quickLookAnchor ? 'good' : ''],
    ['Scene Viewer', r.sceneViewer],
    ['model-viewer canActivateAR', r.canActivateAR ? 'yes' : 'no', r.canActivateAR ? 'good' : 'bad'],
  ];
  $('mvOut').replaceChildren(table(rows));
  return r;
}

// ---------------------------------------------------------------------------
// Tool 2: WebGPU vs WebGL

const C = { on: false, gl: null, gpu: null, scene: null, hook: null, TW: null };
window.__labC = C; // for automated tests

async function buildCompareScene() {
  await ensureMeasured();
  const cs = new THREE.Scene();
  const sky = makeSkyTexture(L.sunDir(), { width: 512, height: 256 });
  cs.background = sky; cs.environment = sky; cs.environmentIntensity = 0.55;
  const sun = L.sun.clone(); sun.target.position.copy(L.sun.target.position); sun.position.copy(L.sun.position);
  sun.shadow.mapSize.set(2048, 2048);
  cs.add(sun, sun.target, L.fill.clone());
  const house = L.houseRoot()?.clone(true); if (house) cs.add(house);
  const lay = L.layersRoot()?.clone(true); if (lay) cs.add(lay);
  cs.userData.sky = sky;
  return cs;
}

function syncCam(cam, w, h) {
  cam.position.copy(camera.position); cam.quaternion.copy(camera.quaternion);
  cam.fov = camera.fov; cam.near = camera.near; cam.far = camera.far; cam.aspect = w / Math.max(1, h); cam.updateProjectionMatrix();
}

async function compareToggle(on) {
  C.on = on;
  const box = $('labCompare');
  if (!on) {
    if (C.hook) L.frameHooks.delete(C.hook);
    for (const r of [C.gl, C.gpu]) { try { r?.renderer.dispose(); r?.renderer.forceContextLoss?.(); } catch (_) { /* ignore */ } }
    C.gl = C.gpu = null; C.scene?.userData.sky?.dispose(); C.scene = null;
    box.hidden = true; box.innerHTML = ''; $('cmpOn').checked = false; return;
  }
  $('cmpStatus').textContent = 'starting…';
  try {
    const t0 = performance.now();
    C.TW ??= await import('three/webgpu');
    const importMs = performance.now() - t0;
    C.scene = await buildCompareScene();
    box.hidden = false; box.innerHTML = '';
    const mk = (title) => {
      const wrap = el('div'); const cv = el('canvas'); const tag = el('div', { class: 'tag' }, title, el('span', { text: '…' }));
      wrap.append(cv, tag); box.append(wrap); return { cv, tag: tag.querySelector('span'), wrap };
    };
    const a = mk('WebGLRenderer'), b = mk('WebGPURenderer');
    box.append(el('button', { class: 'btn close', type: 'button', text: 'Close', onclick: () => compareToggle(false) }));
    const glR = new THREE.WebGLRenderer({ canvas: a.cv, antialias: true, preserveDrawingBuffer: true });
    const gpuR = new C.TW.WebGPURenderer({ canvas: b.cv, antialias: true });
    for (const r of [glR, gpuR]) {
      r.outputColorSpace = THREE.SRGBColorSpace; r.toneMapping = renderer.toneMapping; r.toneMappingExposure = renderer.toneMappingExposure;
      r.shadowMap.enabled = true; r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    }
    glR.shadowMap.type = THREE.PCFShadowMap;
    const ti = performance.now();
    await gpuR.init();
    const initMs = performance.now() - ti;
    const backend = gpuR.backend?.isWebGPUBackend ? 'WebGPU' : 'WebGL2 fallback';
    gpuR.backend?.device?.lost?.then((info) => {
      if (!C.gpu || C.gpu.renderer !== gpuR) return;
      C.gpu.lost = `${info.reason || 'unknown'}: ${info.message || ''}`.trim();
      b.tag.textContent = `WebGPU device lost (${C.gpu.lost})`;
      $('cmpStatus').textContent = `WebGPU device lost: ${C.gpu.lost}`;
      $('cmpStatus').className = 'lab-status warn';
    });
    C.gl = { renderer: glR, cam: new THREE.PerspectiveCamera(), ...a };
    C.gpu = { renderer: gpuR, cam: new THREE.PerspectiveCamera(), backend, initMs, importMs, ...b };
    a.tag.textContent = `WebGL2 · ${glR.getContext().getParameter(glR.getContext().VERSION)}`.slice(0, 60);
    b.tag.textContent = `backend: ${backend} · init ${ms(initMs)}`;
    C.hook = () => { renderBoth(); return false; };
    L.frameHooks.add(C.hook);
    L.invalidate(1500);
    $('cmpStatus').textContent = `on · WebGPURenderer backend: ${backend}`;
  } catch (e) {
    console.error(e);
    $('cmpStatus').textContent = `could not start: ${e.message}`;
  }
}

function sizeOf(x) {
  const w = Math.max(1, x.wrap.clientWidth), h = Math.max(1, x.wrap.clientHeight);
  return [w, h];
}

function renderBoth() {
  if (!C.gl || !C.gpu) return;
  for (const x of [C.gl, C.gpu]) {
    if (x.lost) continue;
    const [w, h] = sizeOf(x);
    const r = x.renderer;
    const cur = r.getSize(new THREE.Vector2());
    if (cur.x !== w || cur.y !== h) r.setSize(w, h, false);
    syncCam(x.cam, w, h);
    r.render(C.scene, x.cam);
  }
}

/** Average time of n frames for one renderer, waiting for the GPU after each (so it is GPU-inclusive). */
async function timeRenderer(x, n = 30) {
  const r = x.renderer;
  const [w, h] = sizeOf(x); syncCam(x.cam, w, h);
  // the same GPU sync for both: read one pixel of the canvas back through a 2D canvas
  const probe = document.createElement('canvas'); probe.width = probe.height = 1;
  const pg = probe.getContext('2d', { willReadFrequently: true });
  const sync = async () => { pg.drawImage(r.domElement, 0, 0, 1, 1); pg.getImageData(0, 0, 1, 1); };
  const tc = performance.now();
  if (r.compileAsync) await r.compileAsync(C.scene, x.cam);
  const compileMs = performance.now() - tc;
  const tf = performance.now(); r.render(C.scene, x.cam); await sync(); const firstMs = performance.now() - tf;
  const cpu = [], tot = [];
  for (let i = 0; i < n; i++) {
    x.cam.position.applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.002);
    const a = performance.now(); r.render(C.scene, x.cam); const b = performance.now(); await sync(); const c = performance.now();
    cpu.push(b - a); tot.push(c - a);
  }
  const avg = (v) => v.reduce((s, t) => s + t, 0) / v.length;
  // rAF frame rate: render once per animation frame for ~1.5 s
  const fps = await new Promise((res) => {
    let k = 0; const t0 = performance.now();
    const step = () => { r.render(C.scene, x.cam); k++; if (performance.now() - t0 < 1500) requestAnimationFrame(step); else res(k / ((performance.now() - t0) / 1000)); };
    requestAnimationFrame(step);
  });
  const info = r.info?.render || {};
  return { compileMs, firstMs, cpuMs: avg(cpu), frameMs: avg(tot), fps, drawCalls: info.drawCalls ?? info.calls, triangles: info.triangles };
}

function capture(x) {
  const [w, h] = sizeOf(x);
  const W = 320, H = Math.max(1, Math.round(320 * h / w));
  syncCam(x.cam, w, h);
  x.renderer.render(C.scene, x.cam);
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  c.getContext('2d').drawImage(x.renderer.domElement, 0, 0, W, H);
  return c;
}

function diffImages(a, b) {
  const W = a.width, H = a.height;
  const da = a.getContext('2d').getImageData(0, 0, W, H).data, db = b.getContext('2d').getImageData(0, 0, W, H).data;
  const out = document.createElement('canvas'); out.width = W; out.height = H;
  const g = out.getContext('2d'); const img = g.createImageData(W, H);
  let sum = 0, big = 0, blankA = true, blankB = true;
  for (let i = 0; i < da.length; i += 4) {
    const d = (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2])) / 3;
    sum += d; if (d > 16) big++;
    if (da[i] || da[i + 1] || da[i + 2]) blankA = false;
    if (db[i] || db[i + 1] || db[i + 2]) blankB = false;
    const v = Math.min(255, d * 4); img.data[i] = v; img.data[i + 1] = v * 0.5; img.data[i + 2] = 0; img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  return { meanAbs: sum / (W * H), pctOver16: (100 * big) / (W * H), blankA, blankB, img: out.toDataURL('image/png') };
}

async function compareTest() {
  const r = {};
  if (!C.on) { $('cmpOn').checked = true; await compareToggle(true); }
  if (!C.gpu) { $('cmpOut').textContent = 'The comparison viewport did not start.'; return null; }
  L.setBusy(true); // the studio's own loop pauses while each renderer is timed alone
  const t0 = performance.now();
  try {
    r.navigatorGpu = !!navigator.gpu;
    const info = C.gpu.renderer.backend?.device?.adapterInfo;
    r.adapter = info ? `${info.vendor || '?'} ${info.architecture || ''} ${info.description || ''}`.trim() : (C.gpu.backend === 'WebGPU' ? 'yes' : 'none (no usable WebGPU adapter)');
    r.backend = C.gpu.backend; r.initMs = C.gpu.initMs; r.importMs = C.gpu.importMs;
    if (C.gpu.lost) throw new Error(`the WebGPU device was lost (${C.gpu.lost}); this browser's WebGPU is not usable here`);
    r.sharedCore = C.TW.Mesh === THREE.Mesh && C.TW.REVISION === THREE.REVISION;
    r.webgl = await timeRenderer(C.gl);
    r.webgpu = await timeRenderer(C.gpu);
    if (C.gpu.lost) r.deviceLost = C.gpu.lost;
    const ia = capture(C.gl), ib = capture(C.gpu);
    const d = diffImages(ia, ib);
    r.diff = { meanAbs: d.meanAbs, pctOver16: d.pctOver16, blankWebGL: d.blankA, blankWebGPU: d.blankB };
    r.bundle = fetchedBytes(/three@0\.186\.1\/build\/three\.(webgpu|tsl)/);
    r.warnings = [...new Set(warningsSince(t0 - 60000, /WebGPU|NodeMaterial|THREE\.|onBeforeCompile|not supported/i))].slice(0, 6);
    $('cmpDiff').replaceChildren(
      el('figure', {}, el('img', { src: ia.toDataURL('image/png'), alt: 'WebGLRenderer frame' }), el('figcaption', { text: 'WebGL' })),
      el('figure', {}, el('img', { src: ib.toDataURL('image/png'), alt: 'WebGPURenderer frame' }), el('figcaption', { text: `WebGPURenderer (${r.backend})` })),
      el('figure', {}, el('img', { src: d.img, alt: 'Difference x4' }), el('figcaption', { text: 'difference ×4' })));
  } catch (e) { results.webgpu = { ...r, error: e.message }; throw e; } finally { L.setBusy(false); }
  results.webgpu = r;
  const rows = [
    ['navigator.gpu / adapter', `${r.navigatorGpu ? 'yes' : 'no'} / ${r.adapter}`],
    ['WebGPURenderer backend used', r.backend, r.backend === 'WebGPU' ? 'good' : 'bad'],
    ['three core shared (one copy)', r.sharedCore ? 'yes' : 'NO', r.sharedCore ? 'good' : 'bad'],
    ['three/webgpu import / init', `${ms(r.importMs)} / ${ms(r.initMs)}`],
    ['Shader compile WebGL / WebGPU', `${ms(r.webgl.compileMs)} / ${ms(r.webgpu.compileMs)}`],
    ['First frame WebGL / WebGPU', `${ms(r.webgl.firstMs)} / ${ms(r.webgpu.firstMs)}`],
    ['Frame (GPU-inclusive) WebGL / WebGPU', `${ms(r.webgl.frameMs)} / ${ms(r.webgpu.frameMs)}`],
    ['CPU submit WebGL / WebGPU', `${ms(r.webgl.cpuMs)} / ${ms(r.webgpu.cpuMs)}`],
    ['rAF FPS WebGL / WebGPU', `${r.webgl.fps.toFixed(1)} / ${r.webgpu.fps.toFixed(1)}`],
    ['Draw calls WebGL / WebGPU', `${r.webgl.drawCalls ?? 'n/a'} / ${r.webgpu.drawCalls ?? 'n/a'}`],
    ['Pixel difference (mean, >16 levels)', r.diff.blankWebGPU || r.diff.blankWebGL ? `n/a: blank frame (${r.diff.blankWebGPU ? 'WebGPU' : 'WebGL'})` : `${r.diff.meanAbs.toFixed(2)} / ${r.diff.pctOver16.toFixed(1)} %`, r.diff.blankWebGPU || r.diff.blankWebGL ? 'bad' : ''],
    ...(r.deviceLost ? [['WebGPU device', `lost: ${r.deviceLost}`, 'bad']] : []),
    ['Library download', r.bundle ? kb(r.bundle.transfer || r.bundle.encoded) : '2.28 MB raw (three.webgpu.js; cached or no timing)'],
  ];
  $('cmpOut').replaceChildren(table(rows), r.warnings.length ? el('pre', { class: 'lab-out', text: `Console:\n${r.warnings.join('\n')}` }) : '');
  return r;
}

// ---------------------------------------------------------------------------
// Tool 3: 3D Tiles neighbourhood

const T = { on: false, tiles: null, lib: null, hook: null, stats: null, wrap: null };

async function tilesMatrix(lib) {
  const s = await site();
  const [lon, lat] = s.originLonLat;
  const enu = new THREE.Matrix4();
  lib.WGS84_ELLIPSOID.getEastNorthUpFrame(THREE.MathUtils.degToRad(lat), THREE.MathUtils.degToRad(lon), s.originEllipsoidM, enu);
  const zUpToYUp = new THREE.Matrix4().makeRotationX(-Math.PI / 2); // (e, n, u) -> (e, u, -n)
  const heading = new THREE.Matrix4().makeRotationY(THREE.MathUtils.degToRad(-(s.modelHeadingDeg || 0)));
  const off = new THREE.Matrix4().makeTranslation(houseOffset());
  return off.multiply(heading).multiply(zUpToYUp).multiply(enu.invert());
}

async function tilesToggle(on) {
  T.on = on; setAttribution(); widenView(T.on || S.on);
  if (!on) {
    if (T.tiles) { T.tiles.group.visible = false; }
    L.invalidate(); $('tlStatus').textContent = 'off'; return;
  }
  await ensureMeasured();
  if (T.tiles) { T.tiles.group.matrix.copy(await tilesMatrix(T.lib)); T.tiles.group.matrixWorldNeedsUpdate = true; T.tiles.group.visible = true; L.invalidate(); $('tlStatus').textContent = 'on'; return; }
  $('tlStatus').textContent = 'loading 3d-tiles-renderer…';
  const st = T.stats = { t0: performance.now(), models: 0, tris: 0, errors: [] };
  try {
    const ti = performance.now();
    T.lib ??= await import('3d-tiles-renderer');
    st.importMs = performance.now() - ti;
    const tiles = new T.lib.TilesRenderer('lab/tiles/tileset.json');
    tiles.registerPlugin(PackedGlbPlugin);
    tiles.errorTarget = Number($('tlError').value);
    tiles.setCamera(camera);
    tiles.setResolutionFromRenderer(camera, renderer);
    tiles.group.matrixAutoUpdate = false;
    tiles.group.matrix.copy(await tilesMatrix(T.lib));
    tiles.group.name = 'lab-3dtiles';
    tiles.addEventListener('load-root-tileset', () => { st.rootMs = performance.now() - st.t0; });
    tiles.addEventListener('load-model', ({ scene: m, tile }) => {
      st.models++;
      st.lastModelMs = performance.now() - st.t0;
      m.traverse((o) => {
        if (!o.isMesh) return;
        st.tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3;
        o.receiveShadow = true; o.castShadow = false;
      });
      const subj = m.getObjectByName(`bldg-${T.subjectOid}`);
      if (subj) { T.subject = subj; subj.traverse((o) => { if (o.isMesh) { o.material = o.material.clone(); o.material.transparent = true; o.material.opacity = 0.45; o.material.depthWrite = false; } }); subj.visible = $('tlSubject').checked; }
      L.invalidate(400);
    });
    tiles.addEventListener('tiles-load-end', () => {
      L.invalidate(400);
      if (!st.models) return; // the first load-end follows tileset.json, before any tile content
      st.loadEndMs ??= performance.now() - st.t0;
      if (T.on) $('tlStatus').textContent = `on · ${st.models} tile files loaded in ${ms(st.loadEndMs)}`;
    });
    tiles.addEventListener('load-error', (e) => { st.errors.push(String(e.error?.message || e.url)); });
    tiles.addEventListener('needs-update', () => L.invalidate(300));
    T.subjectOid = (await getJSON('lab/data/tiles.json')).subjectOid;
    scene.add(tiles.group);
    T.tiles = tiles;
    T.hook = () => {
      if (!T.tiles?.group.visible) return false;
      camera.updateMatrixWorld();
      T.tiles.setResolutionFromRenderer(camera, renderer);
      T.tiles.update();
      return T.tiles.loadProgress < 1;
    };
    L.frameHooks.add(T.hook);
    L.invalidate(1500);
    $('tlStatus').textContent = 'on · loading tiles';
  } catch (e) {
    console.error(e);
    $('tlStatus').textContent = `could not start: ${e.message}`;
  }
}

async function waitFor(cond, timeout = 20000) {
  const t0 = performance.now();
  while (!cond()) { if (performance.now() - t0 > timeout) return false; L.invalidate(300); await new Promise((r) => setTimeout(r, 100)); }
  return true;
}

/** World-space box of the meshes named Roof* in the measured house. */
function roofBox() {
  const b = new THREE.Box3();
  L.houseRoot()?.traverse((o) => { if (o.isMesh && /^Roof/.test(o.name)) b.expandByObject(o); });
  return b;
}

async function tilesTest() {
  const r = {};
  const wasOn = T.on && T.tiles;
  if (!T.on) { $('tlOn').checked = true; await tilesToggle(true); }
  if (!T.tiles) { $('tlOut').textContent = 'The tileset did not start.'; return null; }
  // look at the whole neighbourhood from above the house so every LOD 1 tile is wanted
  await waitFor(() => T.tiles.loadProgress >= 1 && T.stats.loadEndMs != null, 25000);
  const st = T.stats;
  const manifest = await getJSON('lab/data/tiles.json');
  const s = await site();
  // alignment: city solid of this house (through ECEF -> ENU -> scene) vs the studio model's roof
  T.tiles.group.updateMatrixWorld(true);
  let align = null;
  if (T.subject) {
    const vis = T.subject.visible; T.subject.visible = true;
    const sb = new THREE.Box3().setFromObject(T.subject); T.subject.visible = vis;
    const rb = roofBox();
    const c1 = sb.getCenter(new THREE.Vector3()), c2 = rb.getCenter(new THREE.Vector3());
    align = { dx: c1.x - c2.x, dz: c1.z - c2.z, dTop: sb.max.y - rb.max.y, planM: Math.hypot(c1.x - c2.x, c1.z - c2.z),
      sizeCity: sb.getSize(new THREE.Vector3()).toArray().map((v) => +v.toFixed(2)), sizeModel: rb.getSize(new THREE.Vector3()).toArray().map((v) => +v.toFixed(2)) };
  }
  // draw calls with and without the tiles
  const on = { ...(await timeMainRender()), fps: (await measureFrames(1500)).fps };
  T.tiles.group.visible = false;
  const off = { ...(await timeMainRender()), fps: (await measureFrames(1500)).fps };
  T.tiles.group.visible = true; L.invalidate(500);
  on.drawCalls = on.calls; off.drawCalls = off.calls;
  const fetched = fetchedBytes(/\/lab\/tiles\//);
  const active = [...T.tiles.activeTiles].map((t) => t.content?.uri || t.contentUri || (t.content && t.content.uri)).filter(Boolean);
  Object.assign(r, {
    importMs: st.importMs, rootTilesetMs: st.rootMs, allTilesMs: st.loadEndMs ?? st.lastModelMs, tilesLoaded: st.models,
    activeTiles: T.tiles.activeTiles.size, visibleTiles: T.tiles.visibleTiles.size, activeUris: active, triangles: Math.round(st.tris),
    drawCallsWith: on.drawCalls, drawCallsWithout: off.drawCalls, fpsWith: on.fps, fpsWithout: off.fps,
    frameMsWith: on.medianMs, frameMsWithout: off.medianMs, trianglesDrawnWith: on.triangles, trianglesDrawnWithout: off.triangles,
    fileBytes: manifest.totalBytes, fetched, buildings: manifest.buildings, errors: st.errors,
    alignBrowser: align, alignFit: s.fit, headingDeg: s.modelHeadingDeg,
  });
  results.tiles = r;
  const rows = [
    ['Tileset (3D Tiles 1.1, glTF content)', `${manifest.buildings} city solids, ${manifest.tiles} tiles, LOD0 boxes → LOD1 solids + ground`],
    ['Library import', ms(r.importMs)],
    ['tileset.json loaded', ms(r.rootTilesetMs)],
    ['All wanted tiles loaded', ms(r.allTilesMs)],
    ['Tile contents loaded / active / visible', `${r.tilesLoaded} / ${r.activeTiles} / ${r.visibleTiles}`],
    ['Active tile files', active.map((u) => u.split('/').pop()).join(', ') || 'n/a'],
    ['Triangles loaded', r.triangles.toLocaleString()],
    ['Draw calls with / without tiles', `${r.drawCallsWith} / ${r.drawCallsWithout}`],
    ['Frame, GPU-inclusive, with / without', `${ms(on.medianMs)} / ${ms(off.medianMs)}`],
    ['FPS with / without tiles', `${on.fps.toFixed(1)} / ${off.fps.toFixed(1)}`],
    ['Files on disk (all tiles)', `${kb(manifest.totalPackedBytes ?? manifest.totalBytes)} as base64 JSON (${kb(manifest.totalBytes)} binary)`],
    ['Fetched by this page', fetched ? `${kb(fetched.encoded)} in ${fetched.files} files` : 'n/a'],
    ['Alignment, plan (this browser)', align ? `${(align.planM * 100).toFixed(1)} cm (dx ${(align.dx * 100).toFixed(1)}, dz ${(align.dz * 100).toFixed(1)})` : 'subject tile not loaded', align && align.planM < 0.3 ? 'good' : 'bad'],
    ['Alignment, roof top (city − model)', align ? `${(align.dTop * 100).toFixed(1)} cm` : 'n/a', align && Math.abs(align.dTop) < 0.3 ? 'good' : 'bad'],
    ['Outline fit (tools/align_house.py)', `IoU ${s.fit.planIoU}, mean ${(s.fit.outlineDistance.meanM * 100).toFixed(0)} cm, p95 ${(s.fit.outlineDistance.p95M * 100).toFixed(0)} cm`],
    ['Model heading vs true north', `${s.modelHeadingDeg.toFixed(2)}° (applied)`],
    ['Load errors', st.errors.length ? st.errors.join('; ') : 'none', st.errors.length ? 'bad' : 'good'],
  ];
  $('tlOut').replaceChildren(table(rows));
  if (!wasOn) { /* leave it on so the result can be seen */ }
  return r;
}

// ---------------------------------------------------------------------------
// Tool 4: Spark splats

const S = { on: false, lib: null, spark: null, mesh: null, stats: null };

async function splatToggle(on) {
  S.on = on; setAttribution(); widenView(T.on || S.on);
  if (!on) { if (S.mesh) S.mesh.visible = false; if (S.spark) S.spark.visible = false; L.invalidate(); $('spStatus').textContent = 'off'; return; }
  await ensureMeasured();
  if (S.mesh) { S.mesh.position.copy(houseOffset()); S.mesh.visible = true; S.spark.visible = true; L.invalidate(600); $('spStatus').textContent = 'on'; return; }
  $('spStatus').textContent = 'loading Spark…';
  const st = S.stats = { t0: performance.now() };
  // Spark sorts splats in WebAssembly; a page policy without 'wasm-unsafe-eval' blocks it
  st.wasmAllowed = await wasmAllowed();
  if (!st.wasmAllowed) {
    st.error = "this page's security policy blocks WebAssembly (needs 'wasm-unsafe-eval'), which Spark needs to sort splats";
    $('spStatus').textContent = `blocked: ${st.error}`;
    $('spStatus').className = 'lab-status warn';
    return;
  }
  try {
    S.lib ??= await import('@sparkjsdev/spark');
    st.importMs = performance.now() - st.t0;
    S.spark = new S.lib.SparkRenderer({ renderer, onDirty: () => L.invalidate(250) });
    S.spark.name = 'lab-spark';
    scene.add(S.spark);
    const tl = performance.now();
    // fetch the bytes here (same-origin, any content type) and tell Spark the format
    const bytes = await fetchPacked('lab/splat/surroundings.spz.json');
    st.fetchMs = performance.now() - tl; st.bytes = bytes.byteLength;
    S.mesh = new S.lib.SplatMesh({ fileBytes: bytes, fileType: S.lib.SplatFileType.SPZ, fileName: 'surroundings.spz' });
    S.mesh.name = 'lab-splat';
    S.mesh.position.copy(houseOffset());
    scene.add(S.mesh);
    await S.mesh.initialized;
    st.loadMs = performance.now() - tl;
    st.splats = S.mesh.packedSplats?.numSplats ?? S.mesh.numSplats ?? null;
    L.invalidate(1500);
    $('spStatus').textContent = `on · ${st.splats?.toLocaleString?.() ?? '?'} splats in ${ms(st.loadMs)}`;
  } catch (e) {
    console.error(e);
    st.error = e.message;
    $('spStatus').textContent = `could not start: ${e.message}`;
  }
}

async function wasmAllowed() {
  try { await WebAssembly.compile(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0])); return true; } catch (_) { return false; }
}

/** Time from showing the splats to Spark's first finished depth sort (the first frame that shows them). */
async function firstSortMs() {
  const sp = scene.getObjectByName('lab-spark');
  if (!sp) return null;
  const t0 = performance.now();
  const ok = await waitFor(() => sp.activeSplats > 0, 60000);
  return ok ? performance.now() - t0 : null;
}

async function splatTest() {
  if (!S.on) { $('spOn').checked = true; await splatToggle(true); }
  const st = S.stats || {};
  const meta = await getJSON('lab/data/splat.json');
  const r = { importMs: st.importMs, loadMs: st.loadMs, splats: st.splats, error: st.error || null, file: meta, wasmAllowed: st.wasmAllowed };
  if (S.mesh && !st.error) {
    r.firstSortMs = st.firstSortMs ?? (st.firstSortMs = await firstSortMs());
    const tOn = await timeMainRender();
    const on = await measureFrames(2500);
    S.mesh.visible = false;
    const tOff = await timeMainRender();
    const off = await measureFrames(2000);
    S.mesh.visible = true; L.invalidate(600);
    Object.assign(r, { fpsWith: on.fps, fpsWithout: off.fps, frameMsWith: tOn.medianMs, frameMsWithout: tOff.medianMs, p95With: on.p95Ms,
      drawCallsWith: tOn.calls, drawCallsWithout: tOff.calls });
  }
  r.bundle = fetchedBytes(/@sparkjsdev\/spark/);
  r.fetched = fetchedBytes(/surroundings\.spz\.json/);
  r.wasm = typeof WebAssembly === 'object';
  results.splat = r;
  const rows = [
    ['Loaded', r.error ? `no: ${r.error}` : 'yes', r.error ? 'bad' : 'good'],
    ['Library import (incl. inline WASM)', ms(r.importMs)],
    ['Library download', r.bundle ? kb(r.bundle.transfer || r.bundle.encoded) : '3.0 MB raw (spark.module.js; cached or no timing)'],
    ['Splat file', `${kb(meta.packedBytes ?? meta.bytes)} base64 JSON of a ${kb(meta.bytes)} SPZ (${kb(meta.rawBytes)} unpacked)`],
    ['Splats (ground grid / above ground)', `${(r.splats ?? meta.splats).toLocaleString()} (${meta.groundSplats.toLocaleString()} / ${meta.aboveGroundSplats.toLocaleString()})`],
    ['File fetch / fetch + decode', `${ms(st.fetchMs)} / ${ms(r.loadMs)}`],
    ['First sorted frame (splats visible)', r.firstSortMs != null ? ms(r.firstSortMs) : 'n/a'],
    ['WebAssembly allowed by page policy', r.wasmAllowed === false ? 'no' : 'yes', r.wasmAllowed === false ? 'bad' : 'good'],
    ['FPS with / without splats', r.fpsWith != null ? `${r.fpsWith.toFixed(1)} / ${r.fpsWithout.toFixed(1)}` : 'n/a'],
    ['Frame, GPU-inclusive, with / without', r.frameMsWith != null ? `${ms(r.frameMsWith)} / ${ms(r.frameMsWithout)}` : 'n/a'],
    ['Draw calls with / without', r.drawCallsWith != null ? `${r.drawCallsWith} / ${r.drawCallsWithout}` : 'n/a'],
    ['Radius / density', `${meta.radiusM} m / ${meta.splatsPerM2} splats per m²`],
    ['Lidar above-ground spacing', `${meta.lidarAboveGroundMedianSpacingM} m (Dec 2020, leaf-off)`],
    ['Colour', meta.imagery],
  ];
  $('spOut').replaceChildren(table(rows));
  return r;
}

// ---------------------------------------------------------------------------
// UI

function findingsBlock(key) {
  const f = FINDINGS[key];
  const list = (title, items) => [el('h5', { text: title }), el('ul', {}, items.map((t) => el('li', { text: t })))];
  return el('details', {}, el('summary', { text: 'Pros, cons and improvements' }),
    el('p', { class: 'hint', text: f.measured }),
    ...list('Pros', f.pros), ...list('Cons', f.cons), ...list('Improve', f.improve));
}

function toolSection({ key, title, lic, what, controls: ctl, statusId, onId, onToggle, run, outId, extra }) {
  const f = FINDINGS[key];
  const sw = el('label', { class: 'lab-switch' }, el('input', { type: 'checkbox', id: onId, onchange: (e) => onToggle(e.target.checked) }), 'On');
  const runBtn = el('button', { class: 'btn primary', type: 'button', text: 'Run test' });
  runBtn.onclick = async () => {
    runBtn.disabled = true; const old = runBtn.textContent; runBtn.textContent = 'Testing…';
    try { await run(); } catch (e) { console.error(e); $(outId).textContent = `Test failed: ${e.message}`; }
    runBtn.disabled = false; runBtn.textContent = old;
  };
  return el('section', { class: 'lab-tool', id: `lab-${key}` },
    el('div', { class: 'lab-head' }, el('h4', { text: title }), el('span', { class: `lab-verdict ${f.verdictClass}`, text: f.verdict })),
    el('p', { class: 'lab-what', text: what }),
    el('p', { class: 'lab-head' }, el('span', { class: 'lic', text: lic })),
    el('div', { class: 'lab-ctrl' }, sw, ...(ctl || []), runBtn),
    el('p', { class: 'lab-status', id: statusId, text: 'off' }),
    extra || '',
    el('div', { id: outId }),
    findingsBlock(key));
}

function build() {
  const pane = $('labPane');
  const runAll = el('button', { class: 'btn', type: 'button', text: 'Run all four tests' });
  runAll.onclick = async () => {
    runAll.disabled = true;
    for (const id of ['lab-modelViewer', 'lab-webgpu', 'lab-tiles', 'lab-splat']) { const b = document.querySelector(`#${id} .btn.primary`); b.click(); await new Promise((r) => setTimeout(r, 50)); await waitFor(() => !b.disabled, 90000); }
    runAll.disabled = false;
    $('labJson').value = JSON.stringify(results, null, 1);
  };
  pane.append(
    el('div', { class: 'lab-intro' },
      el('h3', { text: 'Lab: four free tools' }),
      el('p', { class: 'hint', text: 'Each tool loads only when you turn it on. Tests measure in this browser on this device, so run them on the phone or laptop you care about. They use the measured job, 1601 S Discovery Ave, and open it if another house is showing.' }),
      el('div', { class: 'row' }, runAll)),
    toolSection({ key: 'modelViewer', title: 'AR view: <model-viewer>', lic: '@google/model-viewer 4.4.0 · Apache-2.0',
      what: 'Exports the current roof (and the house) to GLB with the studio\'s own exporter, hands it to <model-viewer> as a blob URL, with an AR button.',
      controls: [el('label', {}, el('input', { type: 'checkbox', id: 'mvHouse', checked: true }), 'House walls'), el('label', {}, el('input', { type: 'checkbox', id: 'mvCovered', checked: true }), 'Exterior layers only'),
        el('label', {}, el('input', { type: 'checkbox', id: 'mvJpeg', checked: true }), 'JPEG'),
        el('label', {}, 'Textures', el('select', { id: 'mvTex' }, el('option', { value: '512', text: '512 px' }), el('option', { value: '1024', text: '1024 px', selected: true }), el('option', { value: '0', text: 'full' })))],
      statusId: 'mvStatus', onId: 'mvOn', onToggle: mvToggle, run: mvTest, outId: 'mvOut', extra: el('div', { id: 'mvBox' }) }),
    toolSection({ key: 'webgpu', title: 'WebGPU renderer vs WebGL', lic: 'three/webgpu 0.186.1 · MIT',
      what: 'Opens two viewports over the 3D view: the same house and layers drawn by WebGLRenderer (left) and WebGPURenderer (right), with the camera synced.',
      statusId: 'cmpStatus', onId: 'cmpOn', onToggle: compareToggle, run: compareTest, outId: 'cmpOut', extra: el('div', { class: 'lab-diff', id: 'cmpDiff' }) }),
    toolSection({ key: 'tiles', title: 'Neighbourhood: 3D Tiles', lic: '3d-tiles-renderer 0.5.3 · Apache-2.0',
      what: 'A local 3D Tiles 1.1 tileset built from 97 City of Sioux Falls building solids within 200 m and a 3DEP ground mesh, placed through real ECEF coordinates.',
      controls: [el('label', {}, el('input', { type: 'checkbox', id: 'tlSubject', onchange: (e) => { if (T.subject) { T.subject.visible = e.target.checked; L.invalidate(); } } }), 'City solid of this house'),
        el('label', {}, 'Detail', el('select', { id: 'tlError', onchange: (e) => { if (T.tiles) { T.tiles.errorTarget = Number(e.target.value); L.invalidate(800); } } },
          el('option', { value: '6', text: 'high' }), el('option', { value: '16', text: 'normal', selected: true }), el('option', { value: '60', text: 'low (LOD0)' })))],
      statusId: 'tlStatus', onId: 'tlOn', onToggle: tilesToggle, run: tilesTest, outId: 'tlOut' }),
    toolSection({ key: 'splat', title: 'Surroundings: Spark splats', lic: '@sparkjsdev/spark 2.4.0 · MIT',
      what: 'Gaussian splats from 3DEP lidar returns within 70 m, coloured from NAIP 2025 imagery: the yard, street, trees and neighbouring roofs around the model.',
      statusId: 'spStatus', onId: 'spOn', onToggle: splatToggle, run: splatTest, outId: 'spOut' }),
    el('section', { class: 'lab-tool' },
      el('div', { class: 'lab-head' }, el('h4', { text: 'Ways to improve the project' })),
      el('p', { class: 'hint', text: 'Ranked by value for effort. Every item stays at $0 in licences and data.' }),
      el('ol', { class: 'lab-rank' }, PROJECT.map((p) => el('li', {}, el('b', { text: p.title }), ` ${p.why} `, el('span', { class: 'cost', text: `[${p.effort}]` })))),
      el('p', { class: 'hint', text: 'Full write-up: lab/findings.md in the artifact files.' })),
    el('section', { class: 'lab-tool' },
      el('div', { class: 'lab-head' }, el('h4', { text: 'Results (JSON)' })),
      el('p', { class: 'hint', text: 'Filled after "Run all four tests"; select and copy to share.' }),
      el('textarea', { id: 'labJson', rows: '5', readonly: true, 'aria-label': 'Lab results as JSON' })),
    el('p', { class: 'hint', text: 'Data: Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP (public domain). Imagery: USDA NAIP 2025 (public domain).' }),
  );
}

// the path tracer cannot draw splats or 3D Tiles content well: switch the experiments off while it runs
$('rPT')?.addEventListener('change', (e) => {
  if (e.target.checked && (S.on || T.on || C.on)) {
    if (S.on) { $('spOn').checked = false; splatToggle(false); }
    if (C.on) compareToggle(false);
    L.toast('Lab splats and comparison turned off while path tracing runs.');
  }
});

build();
await RS.ready;
// run the Lab straight from a link: ?lab=tiles,splat turns those on and opens the tab
const auto = new URLSearchParams(location.search).get('lab');
if (auto) {
  L.selectTab('lab');
  for (const k of auto.split(',')) {
    if (k === 'tiles') { $('tlOn').checked = true; await tilesToggle(true); }
    if (k === 'splat') { $('spOn').checked = true; await splatToggle(true); }
    if (k === 'ar') { $('mvOn').checked = true; await mvToggle(true); }
    if (k === 'compare') { $('cmpOn').checked = true; await compareToggle(true); }
  }
}
L.tests = { mvTest, compareTest, tilesTest, splatTest, tilesToggle, splatToggle, compareToggle, mvToggle };
