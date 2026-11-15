// Roof Layer Studio: interactive roof material, layer, build-sequence and
// exploded-view visualizer. Three.js (MIT) + three-gpu-pathtracer (MIT).

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { createHouse, HOUSE_PRESETS } from './house.js';
import { RoofLayers, LAYER_OPTIONS, shadesOf } from './layers.js';
import { BuildPlayer, autoPlan } from './build.js';
import { extractRoofPlanes, analyzeRoof, withoutTriangles } from './roof-geometry.js';
import * as TX from './textures.js';
import { sunPosition, sunDirection, dayOfYear, makeSkyTexture, fitShadow, snapshot, PathTraceMode } from './render.js';
import { pitchLabel, slugify, rgbToHex, clamp } from './util.js';
import { LabelOverlay, drawCallouts, labelReserve, SCREEN_INSETS } from './labels.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const UP = new THREE.Vector3(0, 1, 0);

let renderUntil = 0; // on-demand rendering: draw frames until this time (ms)
const S = {
  presetId: params.get('house') || 'ranch-hip',
  pitch: Number(params.get('pitch')) || 6,
  product: null,
  catalog: [],
  server: null,
  sun: { lat: 39.7, date: new Date(), hour: 15, facing: 180 },
  quality: ['standard', 'high', 'ultra'].includes(params.get('quality')) ? params.get('quality')
    : (window.matchMedia?.('(pointer: coarse)').matches ? 'standard' : 'high'),
  cine: true,
  env: 'sky',
  glb: null,
  planMode: 'auto',
  customPlan: null,
};

// ---------------------------------------------------------------------------
// renderer, scene, camera

const stage = $('stage');
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance', preserveDrawingBuffer: params.has('capture') });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.AgXToneMapping;
renderer.toneMappingExposure = 1;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
stage.prepend(renderer.domElement);

const labelOverlay = new LabelOverlay($('labels'));

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 2000);
camera.position.set(19, 11, 24);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.target.set(0, 3.2, 0);
controls.maxPolarAngle = Math.PI * 0.495;
controls.minDistance = 1.2;
controls.maxDistance = 180;

const sun = new THREE.DirectionalLight(0xfff4e6, 3.2);
sun.castShadow = true;
scene.add(sun, sun.target);
const fill = new THREE.HemisphereLight(0xcfe0ff, 0x4a4436, 0.15);
scene.add(fill);

const pmrem = new THREE.PMREMGenerator(renderer);
let skyTex = null, envRT = null, hdriTex = null;
const ptMode = new PathTraceMode(renderer, scene, camera);
let ptDirty = false;

let house = null, layers = null, glbRoot = null;
const player = new BuildPlayer(null);

// ---------------------------------------------------------------------------
// sizing and quality

function applyQuality() {
  const dpr = window.devicePixelRatio || 1;
  const pr = { standard: 1, high: Math.min(dpr, 2), ultra: Math.min(dpr * 1.5, 3) }[S.quality];
  renderer.setPixelRatio(pr);
  resize();
  if (house) fitShadow(sun, sceneBox(), sunDir(), S.quality === 'standard' ? 2048 : 4096);
}

let busy = false, pendingResize = false;
function resize() {
  if (busy) { pendingResize = true; return; }
  const w = stage.clientWidth, h = stage.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / Math.max(1, h);
  camera.updateProjectionMatrix();
  ptDirty = true;
  invalidate();
}
new ResizeObserver(resize).observe(stage);

function sceneBox() {
  const box = new THREE.Box3();
  if (layers) box.expandByObject(layers.root);
  house?.group.children.forEach((c) => { if (c.name !== 'ground') box.expandByObject(c); });
  if (glbRoot) box.expandByObject(glbRoot);
  if (box.isEmpty()) box.set(new THREE.Vector3(-10, 0, -10), new THREE.Vector3(10, 8, 10));
  return box;
}

// ---------------------------------------------------------------------------
// sun and sky

function sunDir() {
  const pos = sunPosition(S.sun.lat, dayOfYear(S.sun.date), S.sun.hour);
  return sunDirection({ azimuth: pos.azimuth, elevation: Math.max(pos.elevation, 2) }, S.sun.facing);
}

function updateSun() {
  const d = sunDir();
  const el = Math.asin(d.y);
  sun.intensity = 4.2 * THREE.MathUtils.smoothstep(el, 0.0, 0.3) + 0.25;
  sun.color.setHSL(0.09, 0.5 * (1 - THREE.MathUtils.smoothstep(el, 0.05, 0.5)) + 0.08, 0.92);
  fitShadow(sun, sceneBox(), d, S.quality === 'standard' ? 2048 : 4096);
  if (S.env === 'sky') {
    skyTex?.dispose();
    skyTex = makeSkyTexture(d);
    // light the scene from a less saturated copy so shaded slopes are not tinted blue
    const lightSky = makeSkyTexture(d, { width: 256, height: 128, saturation: 0.45 });
    envRT?.dispose();
    envRT = pmrem.fromEquirectangular(lightSky);
    lightSky.dispose();
    scene.environment = envRT.texture;
    scene.background = skyTex;
    scene.environmentIntensity = 0.55;
    scene.backgroundIntensity = 1;
    const hz = new THREE.Color(0.80, 0.85, 0.90).multiplyScalar(0.3 + 0.7 * THREE.MathUtils.smoothstep(el, -0.08, 0.25));
    scene.fog = new THREE.Fog(hz, 90, 520);
  }
  if (ptMode.enabled) { ptMode.envTexture = currentEquirect(); ptDirty = true; }
  invalidate();
}

function currentEquirect() { return S.env === 'hdri' && hdriTex ? hdriTex : skyTex; }

async function setEnv(kind) {
  S.env = kind;
  if (kind === 'hdri') {
    try {
      toast('Loading HDRI from Poly Haven…');
      if (!hdriTex) {
        hdriTex = await new HDRLoader().loadAsync('https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/kloofendal_48d_partly_cloudy_puresky_2k.hdr');
        hdriTex.mapping = THREE.EquirectangularReflectionMapping;
      }
      envRT?.dispose();
      envRT = pmrem.fromEquirectangular(hdriTex);
      scene.environment = envRT.texture;
      scene.background = hdriTex;
      scene.fog = null;
      scene.environmentIntensity = 0.9;
      sun.intensity = 2.2;
      toast('HDRI: Kloofendal partly cloudy (Poly Haven, CC0)');
    } catch (e) {
      toast('The HDRI could not be downloaded here, so the physical sky stays on.');
      $('rEnv').value = 'sky'; S.env = 'sky'; updateSun();
    }
  } else updateSun();
  if (ptMode.enabled) { ptMode.envTexture = currentEquirect(); ptDirty = true; }
}

// ---------------------------------------------------------------------------
// house and layers

function buildHouse() {
  if (house) { scene.remove(house.group); disposeTree(house.group); }
  if (layers) { scene.remove(layers.root); disposeTree(layers.root); }
  if (glbRoot) { scene.remove(glbRoot); glbRoot = null; $('origRow').hidden = true; }
  house = createHouse(S.presetId, { pitch: S.pitch, renderer });
  scene.add(house.group);
  makeLayers(house.planes, house.segs);
}

function makeLayers(planes, segs) {
  const prevOptions = layers?.options;
  const prevCustom = layers?.custom || [];
  layers = new RoofLayers({ planes, segs, renderer, overhangM: S.glb ? null : (house?.preset?.overhang ?? null) });
  if (prevOptions) Object.assign(layers.options, prevOptions);
  layers.custom = prevCustom;
  layers.gap = Number($('lyGap').value);
  layers.labelsOn = $('lyLabels').checked;
  layers.rebuildAll(S.product);
  if (S.product) layers.updateProductTransform(S.product.view || {});
  scene.add(layers.root);
  player.layers = layers;
  refreshPlan();
  player.seek(player.duration);
  layers.setExplode($('tbExplode').getAttribute('aria-pressed') === 'true');
  layers.setCutaway($('tbCut').getAttribute('aria-pressed') === 'true', new THREE.Vector3().subVectors(controls.target, camera.position).cross(UP).normalize());
  updateSun();
  renderStack(); renderTakeoff(); updateChips();
  ptDirty = true;
  invalidate();
}

function disposeTree(obj) {
  obj.traverse((o) => {
    if (o.isMesh) { o.geometry?.dispose(); }
  });
}

function frameView(exploded = false, instant = false) {
  const box = sceneBox();
  if (exploded && layers) {
    const n = layers.ordered().filter((r) => r.visible).length;
    box.max.y += n * layers.gap;
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  const dir = camera.position.clone().sub(controls.target).normalize();
  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  let dist = size / (2 * tanV) * (camera.aspect < 1 ? 1.2 : 0.74);
  if (exploded) {
    // keep a strip on the right free for the label column and stay clear of the top bar and toolbar
    const W = Math.max(1, stage.clientWidth), H = Math.max(1, stage.clientHeight);
    const reserve = Math.min(labelReserve(W), W * 0.55);
    const freeX = (W - reserve - SCREEN_INSETS.side) / W;
    const freeY = (H - SCREEN_INSETS.top - SCREEN_INSETS.bottom) / H;
    // the bounding-box diagonal overstates the on-screen width, more so on tall phone views
    const k = W < 520 ? 0.68 : 0.82;
    const fitV = (size / 2) / (tanV * Math.max(0.3, freeY)) * 0.82;
    const fitH = (size / 2) / (tanV * camera.aspect * Math.max(0.3, freeX)) * k;
    dist = Math.max(fitV, fitH);
    // slide the model left by half the reserved strip
    const right = new THREE.Vector3().crossVectors(dir.clone().negate(), UP).normalize();
    const halfW = dist * tanV * camera.aspect;
    center.addScaledVector(right, halfW * (reserve / W));
    // and up a little, because the toolbar covers more than the top bar
    center.y -= dist * tanV * ((SCREEN_INSETS.bottom - SCREEN_INSETS.top) / H);
  }
  tweenCamera(center, center.clone().addScaledVector(dir, dist), instant ? 0 : 0.9);
}

let camTween = null;
function tweenCamera(target, position, dur = 0.9) {
  if (dur <= 0) { controls.target.copy(target); camera.position.copy(position); camTween = null; return; }
  camTween = { t: 0, dur, t0: controls.target.clone(), p0: camera.position.clone(), t1: target, p1: position };
}

// ---------------------------------------------------------------------------
// products

async function loadCatalog() {
  let data = null;
  try { data = await (await fetch('catalog/catalog.json', { cache: 'no-store' })).json(); } catch (_) { /* offline */ }
  S.catalog = (data?.products || []).map((p) => ({ ...p }));
  if (!S.catalog.length) S.catalog = [{ id: 'arch-charcoal', name: 'Architectural Laminate, Charcoal', supplier: 'Built-in', category: 'shingle', exposureIn: 5.625, procedural: { kind: 'architectural' } }];
  renderFilters(); renderCatalog();
}

function imageSrc(src) {
  if (!src) return src;
  if (/^(blob:|data:)/.test(src)) return src;
  const abs = new URL(src, location.href);
  if (abs.origin !== location.origin && S.server) return `api/image?url=${encodeURIComponent(abs.href)}`;
  return abs.href;
}

function loadImage(src) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => res(img);
    img.onerror = () => rej(new Error('The image could not be loaded. If it is on another website, start the local server (scripts/serve.js) so it can be fetched.'));
    img.src = imageSrc(src);
  });
}

async function prepareProduct(p) {
  if (p.procedural) {
    p._texSet = TX.proceduralFor(p.procedural);
    p._palette = p.procedural.palette || shadesOf(p.procedural.color || '#40464d');
  } else if (p.image) {
    const img = p._img || (p._img = await loadImage(p.image));
    const v = p.view || {};
    p._texSet = TX.fromPhoto(img, {
      widthIn: v.widthIn || p.widthIn || 36, heightIn: p.heightIn && !v.widthIn ? p.heightIn : undefined,
      brightness: v.brightness, contrast: v.contrast, saturation: v.saturation, seamless: v.seamless, metal: p.category === 'metal',
    });
    p._palette = shadesOf(averageColor(p._texSet.color));
  }
}

async function applyProduct(p, { keepView = false } = {}) {
  if (!keepView) p.view = p.view || {};
  try {
    showProgress(0.3);
    await prepareProduct(p);
  } catch (e) {
    hideProgress();
    toast(e.message);
    return;
  }
  S.product = p;
  layers.setProduct(p);
  layers.updateProductTransform(p.view || {});
  layers.refreshLabels();
  refreshPlan();
  player.seek(player.t);
  renderCatalog(); renderStack(); renderTakeoff(); updateChips(); syncTune();
  ptDirty = true;
  hideProgress();
  invalidate();
}

function averageColor(canvas) {
  const c = document.createElement('canvas'); c.width = c.height = 8;
  const g = c.getContext('2d'); g.drawImage(canvas, 0, 0, 8, 8);
  const d = g.getImageData(0, 0, 8, 8).data;
  let r = 0, gg = 0, b = 0;
  for (let i = 0; i < d.length; i += 4) { r += d[i]; gg += d[i + 1]; b += d[i + 2]; }
  return rgbToHex([r / 64, gg / 64, b / 64]);
}

const thumbCache = new Map();
function thumbFor(p) {
  if (thumbCache.has(p.id)) return thumbCache.get(p.id);
  let url;
  if (p.procedural) url = TX.swatchDataURL(TX.proceduralFor({ ...p.procedural, res: 160 }), 96);
  else url = imageSrc(p.thumb || p.image);
  thumbCache.set(p.id, url);
  return url;
}

let filter = 'all';
const FILTERS = [['all', 'All'], ['shingle', 'Shingle'], ['metal', 'Metal'], ['tile', 'Tile, slate, shake'], ['supplier', 'Imported']];
function renderFilters() {
  const el = $('filters');
  el.innerHTML = '';
  for (const [id, label] of FILTERS) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label; b.setAttribute('aria-pressed', String(filter === id));
    b.onclick = () => { filter = id; renderFilters(); renderCatalog(); };
    el.append(b);
  }
}

function renderCatalog() {
  const q = $('search').value.trim().toLowerCase();
  const el = $('catalog');
  el.innerHTML = '';
  for (const p of S.catalog) {
    const imported = p.supplier !== 'Built-in';
    if (filter === 'supplier' && !imported) continue;
    if (filter === 'tile' && !['tile', 'slate', 'shake'].includes(p.category)) continue;
    if (['shingle', 'metal'].includes(filter) && p.category !== filter) continue;
    if (q && !`${p.name} ${p.supplier}`.toLowerCase().includes(q)) continue;
    const b = document.createElement('button');
    b.className = 'card'; b.type = 'button';
    b.setAttribute('aria-pressed', String(S.product?.id === p.id));
    b.title = `${p.name}${p.supplier ? ' · ' + p.supplier : ''}`;
    const img = document.createElement('img');
    img.alt = ''; img.loading = 'lazy'; img.src = thumbFor(p);
    const name = document.createElement('span'); name.textContent = p.name;
    const sup = document.createElement('small'); sup.textContent = p.supplier || '';
    b.append(img, name, sup);
    b.onclick = () => applyProduct(p);
    el.append(b);
  }
  if (!el.children.length) el.innerHTML = '<p class="hint" style="grid-column:1/-1">No products match. Clear the search or add a supplier product.</p>';
}

// ---------------------------------------------------------------------------
// fit-to-roof controls

function syncTune() {
  const v = S.product?.view || {};
  $('tuneScale').value = v.scale ?? 1; $('tuneScaleV').textContent = `${Math.round((v.scale ?? 1) * 100)}%`;
  $('tuneRot').value = v.rotation ?? 0; $('tuneRotV').textContent = `${v.rotation ?? 0}°`;
  $('tuneOffV').value = v.offsetV ?? 0; $('tuneOffVV').textContent = (v.offsetV ?? 0).toFixed(2);
  $('tuneRelief').value = v.reliefScale ?? 1; $('tuneReliefV').textContent = (v.reliefScale ?? 1).toFixed(1);
  $('tuneTint').value = v.tint || '#ffffff';
  const photo = !!S.product?.image;
  $('photoTune').hidden = !photo;
  if (photo) {
    $('tuneW').value = v.widthIn || S.product.widthIn || 36;
    $('tuneBright').value = v.brightness ?? 0; $('tuneContrast').value = v.contrast ?? 0; $('tuneSat').value = v.saturation ?? 0;
    $('tuneSeamless').checked = !!v.seamless;
    $('tuneExposure').value = S.product.exposureIn || 5.625;
    $('tuneCourses').checked = !S.product.flat;
  }
}

function bindTune() {
  const live = (id, key, fmt) => $(id).addEventListener('input', (e) => {
    if (!S.product) return;
    const val = Number(e.target.value);
    S.product.view = { ...S.product.view, [key]: val };
    if (fmt) fmt(val);
    layers.updateProductTransform(S.product.view);
    ptMaterials();
  });
  live('tuneScale', 'scale', (v) => { $('tuneScaleV').textContent = `${Math.round(v * 100)}%`; });
  live('tuneRot', 'rotation', (v) => { $('tuneRotV').textContent = `${v}°`; });
  live('tuneOffV', 'offsetV', (v) => { $('tuneOffVV').textContent = v.toFixed(2); });
  live('tuneRelief', 'reliefScale', (v) => { $('tuneReliefV').textContent = v.toFixed(1); });
  $('tuneTint').addEventListener('input', (e) => { if (!S.product) return; S.product.view = { ...S.product.view, tint: e.target.value }; layers.updateProductTransform(S.product.view); ptMaterials(); });
  $('tuneTintReset').onclick = () => { if (!S.product) return; S.product.view = { ...S.product.view, tint: null }; syncTune(); layers.updateProductTransform(S.product.view); ptMaterials(); };
  // photo re-processing (debounced)
  let timer = null;
  const reprocess = (key, getter) => $(key).addEventListener(key === 'tuneSeamless' ? 'change' : 'input', () => {
    if (!S.product?.image) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      S.product.view = {
        ...S.product.view, widthIn: Number($('tuneW').value) || 36, brightness: Number($('tuneBright').value),
        contrast: Number($('tuneContrast').value), saturation: Number($('tuneSat').value), seamless: $('tuneSeamless').checked,
      };
      applyProduct(S.product, { keepView: true });
    }, 220);
  });
  ['tuneW', 'tuneBright', 'tuneContrast', 'tuneSat', 'tuneSeamless'].forEach((k) => reprocess(k));
  // course geometry for photos: match the exposure printed in the photo, or keep the roof flat
  const regeometry = () => {
    if (!S.product?.image) return;
    S.product.exposureIn = Math.min(14, Math.max(3, Number($('tuneExposure').value) || 5.625));
    S.product.flat = !$('tuneCourses').checked;
    layers.setProduct(S.product);
    layers.updateProductTransform(S.product.view || {});
    player.seek(player.t); renderStack(); renderTakeoff(); ptDirty = true; invalidate();
  };
  $('tuneExposure').addEventListener('change', regeometry);
  $('tuneCourses').addEventListener('change', regeometry);
}

function ptMaterials() { if (ptMode.enabled) ptMode.updateMaterials(); }

// ---------------------------------------------------------------------------
// layers panel

const OPTION_FOR = { deck: 'deck', underlayment: 'underlayment', iceWater: 'iceWater', dripEdge: 'dripEdge' };

function renderStack() {
  const el = $('stack');
  el.innerHTML = '';
  const order = layers.ordered().filter((r) => r.id !== 'deckRepair').reverse();
  let level = order.filter((r) => r.visible).length;
  for (const rec of order) {
    const row = document.createElement('div');
    row.className = 'layer' + (rec.info.group === 'old' ? ' old' : '') + (rec.visible ? '' : ' off');
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = rec.userVisible; cb.id = `ly_${rec.id}`;
    cb.setAttribute('aria-label', `Show ${rec.info.label}`);
    cb.onchange = () => { layers.setVisible(rec.id, cb.checked); renderStack(); ptDirty = true; };
    const n = document.createElement('label'); n.className = 'n'; n.htmlFor = cb.id; n.textContent = rec.info.label;
    const lvl = document.createElement('span'); lvl.className = 'lvl'; lvl.textContent = rec.visible ? `L${level--}` : '—';
    const s = document.createElement('div'); s.className = 's'; s.textContent = rec.info.spec || '';
    row.append(cb, n, lvl, s);
    const optKey = OPTION_FOR[rec.id];
    if (optKey) {
      const sel = document.createElement('select');
      sel.setAttribute('aria-label', `${rec.info.label} product`);
      for (const o of LAYER_OPTIONS[optKey]) sel.add(new Option(o.label, o.id, false, layers.options[optKey] === o.id));
      sel.onchange = () => setLayerOption(optKey, sel.value);
      row.append(sel);
    }
    if (rec.id === 'iceWater') {
      const r2 = document.createElement('div'); r2.className = 'row'; r2.style.gridColumn = '2 / 4';
      const rows = document.createElement('select'); rows.setAttribute('aria-label', 'Rows at eaves');
      const auto = layers.overhangM != null ? `Auto: ${layers.iceRows} rows (24" inside the wall)` : 'Auto: 2 rows (overhang unknown)';
      rows.add(new Option(auto, 'auto', false, layers.options.iceRows === 'auto'));
      for (const k of [1, 2, 3]) rows.add(new Option(`${k} row${k > 1 ? 's' : ''} at eaves`, k, false, layers.options.iceRows === k));
      rows.onchange = () => setLayerOption('iceRows', rows.value === 'auto' ? 'auto' : Number(rows.value));
      const v = document.createElement('input'); v.type = 'checkbox'; v.checked = layers.options.valleys; v.id = 'lyValleys';
      v.onchange = () => setLayerOption('valleys', v.checked);
      const vl = document.createElement('label'); vl.htmlFor = 'lyValleys'; vl.textContent = 'Valleys'; vl.style.minWidth = '0';
      r2.append(rows, v, vl);
      row.append(r2);
    }
    if (rec.id === 'deck') {
      const r2 = document.createElement('div'); r2.className = 'row'; r2.style.gridColumn = '2 / 4';
      r2.innerHTML = '<label for="lyRepair" style="min-width:0">Repair allowance</label><input id="lyRepair" type="number" min="0" max="20" step="1" style="width:64px"><span class="hint">sheets</span>';
      const inp = r2.querySelector('input'); inp.value = layers.options.deckRepairSheets;
      inp.onchange = () => setLayerOption('deckRepairSheets', Math.max(0, Math.min(20, Number(inp.value) || 0)));
      row.append(r2);
    }
    if (rec.id === 'nails' && (S.product?.category || 'shingle') === 'shingle') {
      const sel = document.createElement('select'); sel.setAttribute('aria-label', 'Nails per shingle');
      for (const k of [4, 6]) sel.add(new Option(`${k} nails per shingle${k === 6 ? ' (high wind)' : ''}`, k, false, layers.options.nailsPerShingle === k));
      sel.onchange = () => setLayerOption('nailsPerShingle', Number(sel.value));
      row.append(sel);
    }
    if (rec.custom) {
      const rm = document.createElement('button'); rm.className = 'btn'; rm.textContent = 'Remove'; rm.style.gridColumn = '2 / 4'; rm.style.justifySelf = 'start';
      rm.onclick = () => { layers.removeCustomLayer(rec.id); afterLayerChange(); };
      row.append(rm);
    }
    el.append(row);
  }
  const ventRow = document.createElement('div'); ventRow.className = 'row';
  ventRow.innerHTML = `<input type="checkbox" id="lyVent" ${layers.options.ridgeVent !== false ? 'checked' : ''}><label for="lyVent" style="min-width:0;color:var(--fg)">Include ridge vent</label>`;
  ventRow.querySelector('input').onchange = (e) => setLayerOption('ridgeVent', e.target.checked);
  el.append(ventRow);
}

function setLayerOption(key, value) {
  layers.setOption(key, value);
  afterLayerChange();
}

function afterLayerChange() {
  refreshPlan();
  player.seek(player.t);
  renderStack(); renderTakeoff();
  ptDirty = true;
}

let wasteTouched = false;
function renderTakeoff() {
  if (!wasteTouched) $('waste').value = Math.round(layers.suggestedWaste() * 100);
  const rows = layers.takeoff({ waste: (Number($('waste').value) || 0) / 100 });
  $('takeoff').innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
}

// ---------------------------------------------------------------------------
// build plan

async function loadPlanIndex() {
  const sel = $('planSel');
  const add = (value, label) => { if (![...sel.options].some((o) => o.value === value)) sel.add(new Option(label, value)); };
  try {
    const list = await (await fetch('plans/index.json', { cache: 'no-store' })).json();
    for (const p of list.plans || []) add(`plans/${p.file}`, p.title);
  } catch (_) { /* no index */ }
  if (S.server) {
    try { const r = await (await fetch('api/plans')).json(); for (const p of r.plans || []) add(`plans/${p.file}`, p.title || p.file); } catch (_) { /* ignore */ }
  }
}

function refreshPlan() {
  const plan = S.planMode === 'auto' || !S.customPlan ? autoPlan(layers, { product: S.product }) : S.customPlan;
  try { player.setPlan(plan); } catch (e) { toast(`Plan error: ${e.message}`); player.setPlan(autoPlan(layers, { product: S.product })); }
}

async function usePlan(value) {
  if (value === 'auto') { S.planMode = 'auto'; S.customPlan = null; refreshPlan(); return; }
  try {
    const plan = await (await fetch(value, { cache: 'no-store' })).json();
    S.planMode = 'file'; S.customPlan = plan; refreshPlan(); player.seek(0);
    toast(`Loaded plan: ${player.plan.title}`);
  } catch (e) { toast('That plan could not be loaded.'); }
}

function renderSteps() {
  const plan = player.plan;
  $('planTitle').textContent = plan.title;
  $('planSummary').textContent = plan.summary;
  const el = $('steps');
  el.innerHTML = '';
  plan.steps.forEach((s, i) => {
    const li = document.createElement('li');
    li.innerHTML = `<b></b><em>${fmtTime(player.starts[i])}</em>`;
    li.querySelector('b').textContent = s.title;
    li.title = s.detail;
    li.onclick = () => { player.jumpToStep(i); showCaption(true); };
    el.append(li);
  });
}

function fmtTime(t) { const m = Math.floor(t / 60), s = Math.floor(t % 60); return `${m}:${String(s).padStart(2, '0')}`; }

player.on('plan', renderSteps);
player.on('time', ({ t, duration, step, stepProgress }) => {
  invalidate();
  $('bScrub').value = String(Math.round((t / Math.max(duration, 1e-6)) * 1000));
  $('bTime').textContent = `${fmtTime(t)} / ${fmtTime(duration)}`;
  [...$('steps').children].forEach((li, i) => { li.classList.toggle('cur', i === step && t < duration); li.classList.toggle('done', i < step || t >= duration); });
  const s = player.plan.steps[step];
  if (s) {
    $('capStep').textContent = `Step ${step + 1} of ${player.plan.steps.length}`;
    $('capTitle').textContent = s.title;
    $('capDetail').textContent = s.detail;
    $('capBar').style.width = `${Math.round(stepProgress * 100)}%`;
    $('caption').classList.toggle('remove', s.actions.some((a) => a.op === 'remove'));
  }
  const before = t <= 1e-3;
  $('tbBefore').setAttribute('aria-pressed', String(before));
  if (!player.playing && (t >= duration - 1e-3 || before)) showCaption(false);
  ptDirty = true;
});
player.on('play', (on) => {
  $('tbPlay').setAttribute('aria-pressed', String(on));
  $('tbPlay').querySelector('span').textContent = on ? 'Pause' : 'Watch build';
  $('bPlay').textContent = on ? 'Pause' : 'Play';
  if (on) showCaption(true);
});
player.on('done', () => { toast('Build complete.'); setTimeout(() => showCaption(false), 2500); });

function showCaption(on) { $('caption').hidden = !on; }

// ---------------------------------------------------------------------------
// supplier import

let found = [], picked = null, pickedFile = null;
function openImport() {
  found = []; picked = null; pickedFile = null;
  $('impFound').innerHTML = ''; $('impStatus').textContent = S.server ? '' : 'Local server not detected: paste a direct image link, or upload a file from the Materials tab.';
  $('impRights').checked = false; updateImportButton();
  $('dlgImport').showModal();
}

function updateImportButton() { $('impAdd').disabled = !(picked && $('impRights').checked && $('impName').value.trim()); }

async function scanUrl() {
  const url = $('impUrl').value.trim();
  if (!url) return;
  $('impStatus').textContent = 'Looking for product images…';
  $('impFound').innerHTML = '';
  found = []; picked = null;
  try {
    if (S.server) {
      const r = await fetch(`api/scan?url=${encodeURIComponent(url)}`);
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'Scan failed');
      found = j.images.map((i) => i.url);
      if (j.title && !$('impName').value) $('impName').value = j.title;
      if (j.siteName && !$('impSupplier').value) $('impSupplier').value = j.siteName;
      $('impStatus').textContent = found.length ? `Found ${found.length} images. Pick the swatch or roof close-up.` : 'No images were found on that page. Paste a direct image link instead.';
    } else {
      found = [url];
      $('impStatus').textContent = 'Using the link as an image.';
    }
  } catch (e) { $('impStatus').textContent = e.message; }
  for (const u of found) {
    const b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-pressed', 'false');
    const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy'; img.src = imageSrc(u);
    img.onerror = () => b.remove();
    b.append(img);
    b.onclick = () => { picked = u; [...$('impFound').children].forEach((c) => c.setAttribute('aria-pressed', String(c === b))); updateImportButton(); };
    $('impFound').append(b);
  }
}

function pickFile(file) {
  if (!file || !file.type.startsWith('image/')) { $('impStatus').textContent = 'Choose a JPG, PNG or WebP image.'; return; }
  pickedFile = file; picked = URL.createObjectURL(file);
  $('impFound').innerHTML = '';
  const b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-pressed', 'true');
  const img = document.createElement('img'); img.alt = ''; img.src = picked; b.append(img);
  $('impFound').append(b);
  if (!$('impName').value) $('impName').value = file.name.replace(/\.[^.]+$/, '');
  if (!$('impSupplier').value) $('impSupplier').value = 'Own photo';
  $('impStatus').textContent = 'Photo from your computer selected.';
  updateImportButton();
}

async function addImported() {
  const product = {
    id: `sup-${slugify($('impSupplier').value || 'supplier')}-${slugify($('impName').value)}`,
    name: $('impName').value.trim(), supplier: $('impSupplier').value.trim() || new URL(picked, location.href).hostname,
    category: $('impCat').value, widthIn: Number($('impW').value) || 36, image: picked, sourceUrl: pickedFile ? '' : $('impUrl').value.trim(),
    rights: 'Confirmed by user at import', addedAt: new Date().toISOString(),
  };
  if (S.server) {
    $('impStatus').textContent = 'Saving to the catalog…';
    try {
      const body = pickedFile
        ? { ...product, image: undefined, dataUrl: await new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(pickedFile); }) }
        : { ...product, imageUrl: picked };
      const r = await fetch('api/swatch', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'Save failed');
      Object.assign(product, j.product, pickedFile ? { image: picked } : {});
    } catch (e) { $('impStatus').textContent = `Not saved: ${e.message}`; return; }
  }
  S.catalog = S.catalog.filter((p) => p.id !== product.id);
  S.catalog.push(product);
  thumbCache.delete(product.id);
  $('dlgImport').close();
  filter = 'supplier'; renderFilters();
  await applyProduct(product);
  toast(S.server ? 'Added to the catalog and applied to the roof.' : 'Applied for this session. Run the local server to keep it in the catalog.');
}

async function useFile(file) {
  if (!file || !file.type.startsWith('image/')) { toast('Drop an image file (JPG, PNG or WebP).'); return; }
  const url = URL.createObjectURL(file);
  const product = { id: `upload-${slugify(file.name)}-${Date.now()}`, name: file.name.replace(/\.[^.]+$/, ''), supplier: 'Uploaded photo', category: 'shingle', widthIn: 36, image: url, sessionOnly: true };
  S.catalog.push(product);
  filter = 'supplier'; renderFilters();
  await applyProduct(product);
  toast(S.server ? 'Photo applied for this session. To keep it, use Add supplier product and confirm your rights to the image.' : 'Photo applied. Set "Photo width" so its scale matches the real shingles.');
}

// ---------------------------------------------------------------------------
// snapshot, export

// Inside a claude.ai artifact, downloads go through the viewer's confirmation
// prompt (the `downloads` capability); in a normal browser a link click works.
const downloadsCap = window.claude?.use ? window.claude.use('downloads').catch(() => null) : Promise.resolve(null);
const inArtifact = !!window.claude?.use;

async function saveFile(filename, blob) {
  const dl = await downloadsCap;
  if (dl) {
    try {
      const r = await dl.save({ filename, data: blob });
      if (r.status === 'saved') toast(`Saved ${filename}`);
    } catch (e) {
      if (e?.code === 'declined') return;
      if (e?.code === 'rejected_extension' || e?.code === 'extension_not_enabled') toast('This file type cannot be saved from this page. Run the viewer locally to export it.');
      else if (e?.code === 'rate_limited') toast('A save prompt is already open.');
      else toast('Saving is not available here. Right-click or long-press the image instead.');
    }
    return;
  }
  if (inArtifact) { toast('Saving is not available here. Right-click or long-press the image instead.'); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 60000);
}

let lastSnap = null;
async function takeSnapshot(w, h) {
  const [W, H] = w ? [w, h] : $('rSize').value.split('x').map(Number);
  showProgress(0.02);
  const started = performance.now();
  busy = true;
  let blob;
  try {
    blob = await snapshot({
    renderer, scene, camera, width: W, height: H,
    overlay: $('rLabels').checked ? (ctx, w, h) => drawCallouts(ctx, layers.labelItems(), camera, w, h) : null,
    pathTracer: ptMode.enabled ? ptMode : null, samples: Number($('rSamples').value) || 128,
    onProgress: (p) => showProgress(p),
    });
  } catch (e) {
    console.error(e);
  } finally {
    busy = false;
    if (pendingResize) { pendingResize = false; resize(); }
    invalidate();
  }
  hideProgress();
  if (!blob) { toast(`The ${W} × ${H} image could not be created here. Try a smaller size such as 3840 × 2160.`); return null; }
  const url = URL.createObjectURL(blob);
  lastSnap = { blob, name: `roof-${slugify(S.product?.name || 'render')}-${W}x${H}.png` };
  $('snapImg').src = url;
  $('snapInfo').textContent = `${W} × ${H} px, ${ptMode.enabled ? `path traced, ${$('rSamples').value} samples` : 'rasterized in tiles'}, ${((performance.now() - started) / 1000).toFixed(1)} s.`;
  if (!params.has('capture')) $('dlgSnap').showModal();
  return url;
}

function exportGlb() {
  const exporter = new GLTFExporter();
  const root = new THREE.Group();
  for (const rec of layers.layers.values()) {
    if (!rec.visible) continue;
    const clone = rec.obj.clone(true);
    clone.position.set(0, 0, 0);
    clone.traverse((o) => { if (o.name?.startsWith('label_')) o.parent.remove(o); });
    clone.userData = { rtLayer: rec.id, label: rec.info.label, spec: rec.info.spec, rowH: rec.rowH, level: rec.level };
    root.add(clone);
  }
  exporter.parse(root, (glb) => {
    saveFile(`roof-layers-${slugify(S.product?.name || 'roof')}.glb`, new Blob([glb], { type: 'model/gltf-binary' }));
  }, (e) => toast(`Export failed: ${e.message || e}`), { binary: true, onlyVisible: true });
}

// ---------------------------------------------------------------------------
// GLB house import

async function loadHouseModel(fileOrUrl) {
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  // compressed models (Draco geometry, KTX2 textures); decoders load from the CDN on first use
  const cdn = 'https://cdn.jsdelivr.net/npm/three@0.186.1/examples/jsm/libs/';
  loader.setDRACOLoader(new DRACOLoader().setDecoderPath(`${cdn}draco/gltf/`));
  loader.setKTX2Loader(new KTX2Loader().setTranscoderPath(`${cdn}basis/`).detectSupport(renderer));
  showProgress(0.2);
  try {
    const url = typeof fileOrUrl === 'string' ? fileOrUrl : URL.createObjectURL(fileOrUrl);
    const gltf = await loader.loadAsync(url);
    const root = gltf.scene;
    const unit = Number($('pUnits').value) || 1;
    root.scale.setScalar(unit);
    root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(root);
    root.position.x -= (box.min.x + box.max.x) / 2;
    root.position.z -= (box.min.z + box.max.z) / 2;
    root.position.y -= box.min.y;
    root.updateMatrixWorld(true);
    root.traverse((o) => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; } });
    const { planes, roofTris } = extractRoofPlanes(root);
    if (!planes.length) throw new Error('No roof planes were found. Name the roof mesh "Roof" or check the model units.');
    // keep ground from the demo house, drop the procedural building
    if (house) { scene.remove(house.group); }
    const ground = house?.group.getObjectByName('ground');
    house = { group: new THREE.Group(), planes, segs: analyzeRoof(planes) };
    if (ground) house.group.add(ground);
    scene.add(house.group);
    if (glbRoot) scene.remove(glbRoot);
    glbRoot = root; scene.add(root);
    // remove only the roof triangles; walls in the same mesh stay
    const swaps = [];
    for (const [mesh, tris] of roofTris) {
      const original = mesh.geometry;
      const stripped = withoutTriangles(original, tris);
      mesh.geometry = stripped;
      swaps.push({ mesh, original, stripped });
    }
    S.glb = { swaps };
    $('origRow').hidden = false; $('pOrig').checked = false;
    if (layers) { scene.remove(layers.root); disposeTree(layers.root); }
    makeLayers(planes, house.segs);
    frameView(false);
    toast(`Found ${planes.length} roof planes, ${layers.measure.squares.toFixed(1)} squares.`);
  } catch (e) {
    toast(e.message || 'That model could not be loaded.');
  }
  hideProgress();
}

// ---------------------------------------------------------------------------
// UI helpers

let toastTimer = null;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3800);
}
function showProgress(p) { const el = $('progress'); el.hidden = false; el.style.transform = `scaleX(${clamp(p, 0.02, 1)})`; }
function hideProgress() { $('progress').hidden = true; }

function updateChips() {
  const p = S.product;
  $('chipName').textContent = p ? p.name : 'Default shingles';
  $('chipSwatch').style.backgroundImage = p ? `url("${thumbFor(p)}")` : '';
  $('chipSquares').textContent = `${layers.measure.squares.toFixed(1)} sq`;
  const steepest = Math.max(...layers.planes.map((pl) => pl.slope));
  $('chipPitch').textContent = S.glb ? pitchLabel(Math.tan(steepest) * 12) : pitchLabel(S.pitch);
}

function setPressed(id, on) { $(id).setAttribute('aria-pressed', String(on)); }

function setExplode(on) {
  setPressed('tbExplode', on); $('lyExplode').checked = on;
  layers.setExplode(on);
  frameView(on);
  ptDirty = true;
}
function setCutaway(on) {
  setPressed('tbCut', on); $('lyCut').checked = on;
  // cut from the right-hand side of the current view
  const right = new THREE.Vector3().subVectors(controls.target, camera.position).cross(UP).normalize();
  layers.setCutaway(on, right);
  if (on && ptMode.enabled) toast('The cutaway shows in the live view; path tracing renders whole layers.');
}

function bindUI() {
  // tabs
  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => selectTab(t.dataset.tab)));
  // toolbar
  $('tbExplode').onclick = () => setExplode($('tbExplode').getAttribute('aria-pressed') !== 'true');
  $('tbCut').onclick = () => setCutaway($('tbCut').getAttribute('aria-pressed') !== 'true');
  $('tbBefore').onclick = () => { player.pause(); if (player.t > 1e-3) { player.seek(0); toast('Existing roof. Press again for the new roof.'); } else player.seek(player.duration); };
  $('tbPlay').onclick = () => { if (ptMode.enabled) togglePT(false); player.toggle(); };
  $('tbSnap').onclick = () => takeSnapshot();
  // materials
  $('search').addEventListener('input', renderCatalog);
  $('btnImport').onclick = openImport;
  $('impScan').onclick = scanUrl;
  $('impUrl').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); scanUrl(); } });
  ['impRights', 'impName'].forEach((id) => $(id).addEventListener('input', updateImportButton));
  $('impAdd').onclick = addImported;
  $('impFile').onchange = (e) => pickFile(e.target.files[0]);
  $('fileSwatch').onchange = (e) => useFile(e.target.files[0]);
  stage.addEventListener('dragover', (e) => e.preventDefault());
  stage.addEventListener('drop', (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (!f) return;
    if (/\.(glb|gltf)$/i.test(f.name)) loadHouseModel(f); else useFile(f);
  });
  bindTune();
  // layers
  $('lyExplode').onchange = (e) => setExplode(e.target.checked);
  $('lyCut').onchange = (e) => setCutaway(e.target.checked);
  $('lyGap').oninput = (e) => { layers.gap = Number(e.target.value); $('lyGapV').textContent = `${Number(e.target.value).toFixed(2)} m`; ptDirty = true; };
  $('lyLabels').onchange = (e) => { layers.labelsOn = e.target.checked; };
  $('btnAddLayer').onclick = () => {
    const name = $('newName').value.trim();
    if (!name) { toast('Give the layer a name first.'); return; }
    layers.addCustomLayer({ label: name, after: $('newAfter').value, coverage: $('newCoverage').value, color: $('newColor').value, spec: $('newCoverage').value === 'eaves' ? 'Eaves, 3 ft' : 'Whole roof' });
    $('newName').value = '';
    afterLayerChange();
    toast(`${name} added to the stack.`);
  };
  $('waste').oninput = () => { wasteTouched = true; renderTakeoff(); };
  // build
  $('bPlay').onclick = () => { if (ptMode.enabled) togglePT(false); player.toggle(); };
  $('bPrev').onclick = () => { player.pause(); player.jumpToStep(Math.max(0, player.stepAt() - 1)); showCaption(true); };
  $('bNext').onclick = () => { player.pause(); const i = player.stepAt(); if (i + 1 < player.plan.steps.length) { player.jumpToStep(i + 1); showCaption(true); } else player.finish(); };
  $('bSpeed').onchange = (e) => { player.speed = Number(e.target.value); };
  $('bScrub').oninput = (e) => { player.pause(); player.seek((Number(e.target.value) / 1000) * player.duration); showCaption(player.t < player.duration && player.t > 0); };
  $('bCine').onchange = (e) => { S.cine = e.target.checked; };
  $('planSel').onchange = (e) => usePlan(e.target.value);
  $('filePlan').onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { S.customPlan = JSON.parse(await f.text()); S.planMode = 'file'; refreshPlan(); player.seek(0); toast(`Loaded plan: ${player.plan.title}`); } catch (err) { toast(`That file is not a valid plan: ${err.message}`); }
  };
  $('btnPlanDl').onclick = () => saveFile(`${slugify(player.plan.title)}.json`, new Blob([JSON.stringify(player.plan, null, 2)], { type: 'application/json' }));
  $('btnAi').onclick = generateAiPlan;
  // render
  $('rQuality').onchange = (e) => { S.quality = e.target.value; applyQuality(); };
  $('rTone').onchange = (e) => { renderer.toneMapping = { agx: THREE.AgXToneMapping, aces: THREE.ACESFilmicToneMapping, neutral: THREE.NeutralToneMapping }[e.target.value]; ptDirty = true; };
  $('rExposure').oninput = (e) => { renderer.toneMappingExposure = Number(e.target.value); };
  $('rEnv').onchange = (e) => setEnv(e.target.value);
  $('rPT').onchange = (e) => togglePT(e.target.checked);
  $('btnSnap').onclick = () => takeSnapshot();
  $('snapClose').onclick = () => $('dlgSnap').close();
  $('snapDl').onclick = () => { if (lastSnap) saveFile(lastSnap.name, lastSnap.blob); };
  // GLB is not a type the artifact viewer can save; the local viewer can
  if (inArtifact) { $('btnGlb').disabled = true; $('btnGlb').title = 'Run the viewer locally (npm start) to export GLB'; $('glbHint').textContent = 'GLB export works in the local viewer (npm start in roof-visualizer). Layer meshes named RT_layer_* open in Blender for Cycles renders.'; }
  // project
  for (const [id, p] of Object.entries(HOUSE_PRESETS)) $('pHouse').add(new Option(p.label, id, false, id === S.presetId));
  $('pHouse').onchange = (e) => { S.presetId = e.target.value; S.glb = null; buildHouse(); frameView(false); };
  let pitchTimer = null;
  $('pPitch').value = S.pitch; $('pPitchV').textContent = pitchLabel(S.pitch);
  $('pPitch').oninput = (e) => {
    S.pitch = Number(e.target.value); $('pPitchV').textContent = pitchLabel(S.pitch);
    clearTimeout(pitchTimer); pitchTimer = setTimeout(() => { if (!S.glb) buildHouse(); }, 160);
  };
  $('fileGlb').onchange = (e) => e.target.files[0] && loadHouseModel(e.target.files[0]);
  $('pOrig').onchange = (e) => {
    S.glb?.swaps.forEach(({ mesh, original, stripped }) => { mesh.geometry = e.target.checked ? original : stripped; });
    if (layers) layers.root.visible = !e.target.checked;
    ptDirty = true;
  };
  $('pDate').valueAsDate = S.sun.date;
  $('pLat').onchange = (e) => { S.sun.lat = Number(e.target.value); updateSun(); };
  $('pDate').onchange = (e) => { if (e.target.valueAsDate) { S.sun.date = e.target.valueAsDate; updateSun(); } };
  $('pHour').oninput = (e) => { S.sun.hour = Number(e.target.value); const h = Math.floor(S.sun.hour), m = Math.round((S.sun.hour - h) * 60); $('pHourV').textContent = `${h}:${String(m).padStart(2, '0')}`; updateSun(); };
  $('pFacing').onchange = (e) => { S.sun.facing = Number(e.target.value); updateSun(); };
  $('btnGlb').onclick = exportGlb;
  // keyboard
  window.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea, select, dialog') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === ' ' && e.target.closest('button, a, [role="tab"]')) return; // let Space press the focused control
    if (e.key === 'e' || e.key === 'E') setExplode($('tbExplode').getAttribute('aria-pressed') !== 'true');
    else if (e.key === 'c' || e.key === 'C') setCutaway($('tbCut').getAttribute('aria-pressed') !== 'true');
    else if (e.key === 'b' || e.key === 'B') $('tbBefore').click();
    else if (e.key === ' ') { e.preventDefault(); $('tbPlay').click(); }
    else if (e.key === 's' || e.key === 'S') takeSnapshot();
  });
  controls.addEventListener('change', () => { invalidate(); if (ptMode.enabled) ptMode.updateCamera(); });
  // render on demand: any interaction keeps frames coming briefly; idle pages stop drawing
  for (const ev of ['pointerdown', 'wheel', 'keydown', 'input', 'change', 'click']) window.addEventListener(ev, () => invalidate(), { passive: true, capture: true });
  window.addEventListener('pointermove', (e) => { if (e.buttons) invalidate(); }, { passive: true });
}

function selectTab(id) {
  document.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === id)));
  document.querySelectorAll('.pane').forEach((p) => { p.hidden = p.dataset.pane !== id; });
}

async function togglePT(on) {
  $('rPT').checked = on;
  if (on) {
    player.pause();
    try {
      $('rPTs').textContent = 'compiling…';
      await ptMode.enable({ envTexture: currentEquirect() });
      ptDirty = false;
    } catch (e) {
      console.error(e);
      toast('Path tracing could not start in this browser.');
      $('rPT').checked = false; $('rPTs').textContent = 'off';
    }
  } else { ptMode.disable(); $('rPTs').textContent = 'off'; }
}

async function generateAiPlan() {
  const job = $('jobText').value.trim();
  if (!job) return;
  $('btnAi').disabled = true; $('btnAi').textContent = 'Writing plan…';
  try {
    const r = await fetch('api/plan', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        job,
        layers: layers.ordered().filter((l) => l.visible || l.info.group === 'old').map((l) => ({ id: l.id, label: l.info.label, spec: l.info.spec })),
        measure: layers.measure, product: S.product ? { name: S.product.name, category: S.product.category } : null,
      }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Plan generation failed');
    S.customPlan = j.plan; S.planMode = 'file';
    refreshPlan(); player.seek(0); player.play();
    if (j.saved) await loadPlanIndex();
    toast(`Claude wrote "${player.plan.title}".`);
  } catch (e) { toast(e.message); }
  $('btnAi').disabled = false; $('btnAi').textContent = 'Generate plan';
}

// ---------------------------------------------------------------------------
// main loop

const timer = new THREE.Timer();
let lastPT = 0;
/** Ask for frames for the next `ms` milliseconds (on-demand rendering). */
function invalidate(ms = 700) { renderUntil = Math.max(renderUntil, performance.now() + ms); }
function frame(now) {
  requestAnimationFrame(frame);
  if (busy) return; // a snapshot owns the renderer
  timer.update(now);
  const dt = Math.min(0.05, timer.getDelta());
  const animating = !!camTween || player.playing || (layers && (Math.abs(layers.explodeTarget - layers.explode) > 1e-4 || Math.abs(layers.cutTarget - layers.cut) > 1e-4));
  if (!animating && !ptMode.enabled && performance.now() > renderUntil) return; // idle: nothing to draw
  const moving = layers ? layers.update(dt) : false;
  player.update(dt);
  if (camTween) {
    camTween.t += dt / camTween.dur;
    const k = THREE.MathUtils.smootherstep(Math.min(1, camTween.t), 0, 1);
    controls.target.lerpVectors(camTween.t0, camTween.t1, k);
    camera.position.lerpVectors(camTween.p0, camTween.p1, k);
    if (camTween.t >= 1) camTween = null;
  }
  if (S.cine && player.playing) {
    const off = camera.position.clone().sub(controls.target).applyAxisAngle(UP, dt * 0.07);
    camera.position.copy(controls.target).add(off);
  }
  controls.update();
  const dist = camera.position.distanceTo(controls.target);
  camera.near = clamp(dist * 0.008, 0.01, 0.8);
  camera.far = Math.max(800, dist * 40);
  camera.updateProjectionMatrix();
  if (ptMode.enabled) {
    // the path tracer draws whole layers, so it pauses while a layer is part-built or cut away
    const partial = layers && (layers.isPartial() || layers.cutTarget < 1);
    if (moving || player.playing || partial) {
      renderer.render(scene, camera); ptDirty = true;
      if (partial && performance.now() - lastPT > 250) { $('rPTs').textContent = 'paused: build or cutaway in progress'; lastPT = performance.now(); }
    } else {
      if (ptDirty) { ptMode.rebuild(); ptDirty = false; }
      ptMode.render();
      const now = performance.now();
      if (now - lastPT > 250) { $('rPTs').textContent = `${ptMode.samples} samples`; lastPT = now; }
    }
  } else {
    renderer.render(scene, camera);
  }
  labelOverlay.update(layers ? layers.labelItems() : [], camera, stage.clientWidth, stage.clientHeight);
}

// ---------------------------------------------------------------------------
// boot

async function boot() {
  bindUI();
  $('rQuality').value = S.quality;
  applyQuality();
  // the local server (scripts/serve.js) marks pages it serves; static hosting skips the API entirely
  if (document.querySelector('meta[name="roof-studio-server"]')) {
    try {
      const r = await fetch('api/health', { cache: 'no-store' });
      if (r.ok) S.server = await r.json();
    } catch (_) { /* static hosting */ }
  }
  $('aiBox').hidden = !S.server?.ai;
  await loadCatalog();
  const first = S.catalog.find((p) => p.id === params.get('product')) || S.catalog[0];
  S.product = first;
  await prepareProduct(first);
  buildHouse();
  renderCatalog(); updateChips(); syncTune();
  frameView(false, true);
  await loadPlanIndex();
  if (params.get('plan')) await usePlan(params.get('plan'));
  if (params.get('glb')) await loadHouseModel(params.get('glb'));
  if (params.has('t')) player.seek(Number(params.get('t')) * player.duration);
  if (params.get('explode') === '1') { setExplode(true); layers.explode = 1; frameView(true, true); }
  if (params.get('cut') === '1') { setCutaway(true); layers.cut = 0; }
  if (params.get('tab')) selectTab(params.get('tab'));
  $('loading').hidden = true;
  requestAnimationFrame(frame);
  readyResolve();
}

let readyResolve;
const ready = new Promise((r) => { readyResolve = r; });

// Automation API for Claude skills, tests and demos.
window.roofStudio = {
  ready,
  get state() { return { product: S.product?.id, t: player.t, duration: player.duration, explode: layers?.explodeTarget, measure: layers?.measure, layers: layers && [...layers.layers.values()].map((r) => ({ id: r.id, visible: r.visible, reveal: r.reveal })) }; },
  setProduct: (id) => applyProduct(S.catalog.find((p) => p.id === id) || S.catalog[0]),
  explode: (on = true) => setExplode(on),
  cutaway: (on = true) => setCutaway(on),
  seek: (fraction) => { player.pause(); player.seek(fraction * player.duration); showCaption(fraction > 0 && fraction < 1); },
  play: () => player.play(),
  snapshot: (w, h) => takeSnapshot(w, h),
  loadPlan: (plan) => { S.customPlan = plan; S.planMode = 'file'; refreshPlan(); },
  loadHouse: (url) => loadHouseModel(url),
  pathTrace: (on = true) => togglePT(on),
  settle: () => {
    invalidate(3000);
    if (layers) { layers.explode = layers.explodeTarget; layers.cut = layers.cutTarget; for (let i = 0; i < 60; i++) layers.update(0.2); }
    if (camTween) { controls.target.copy(camTween.t1); camera.position.copy(camTween.p1); camTween = null; }
  },
  three: { THREE, scene, camera, renderer, controls },
};

boot().catch((e) => {
  console.error(e);
  $('loading').textContent = `The viewer could not start: ${e.message}`;
});
