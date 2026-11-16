// Roof layer stack: builds every layer from the roof planes, owns their
// materials, and drives visibility, build reveal, cutaway and exploded view.

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {
  buildSurface, fullParts, stripParts, eaveParts, dripEdgeGeometry, capGeometry,
  ridgeVentGeometry, nailLayout, nailGeometry, deckPatches, measureRoof,
} from './roof-geometry.js';
import * as TX from './textures.js';
import { inToM, fmtFtIn, easeInOutCubic, hexToRgb, rgbToHex } from './util.js';
import { toQuantities } from './quote.js';

// Physical stack heights above the rafters (metres). Real thicknesses with a
// little separation so nothing z-fights at house scale.
const H = {
  deck: 0.0111, oldFelt: 0.0128, oldShingles: 0.0145, dripEave: 0.0122, iceWater: 0.0134, underlayment: 0.0146,
  dripRake: 0.0158, starter: 0.0172, nails: 0.0222, covering: 0.0190, ridgeVent: 0.0235, cap: 0.0262,
};

export const LAYER_INFO = {
  oldShingles: { label: 'Existing shingles', spec: 'Worn 3-tab · to be torn off', group: 'old' },
  oldFelt: { label: 'Existing felt', spec: '#15 felt · to be removed', group: 'old' },
  deck: { label: 'Roof deck', spec: '7/16" OSB sheathing, 4×8 sheets' },
  deckRepair: { label: 'Deck repair', spec: 'Replacement sheets', hidden: true },
  dripEdge: { label: 'Drip edge', spec: 'Eaves under, rakes over underlayment' },
  iceWater: { label: 'Ice & water shield', spec: 'Self-adhered, eaves + valleys' },
  underlayment: { label: 'Underlayment', spec: 'Synthetic, 4" laps' },
  starter: { label: 'Starter strip', spec: 'Eaves + rakes, sealant to edge' },
  nails: { label: 'Fasteners', spec: '1-1/4" coil nails, 4 per shingle' },
  covering: { label: 'Shingles', spec: 'Architectural laminate' },
  ridgeVent: { label: 'Ridge vent', spec: 'Shingle-over, 18 NFA/ft' },
  ridgeCap: { label: 'Hip & ridge cap', spec: 'Matching cap shingles' },
};

// hidden under a finished covering (the deck edge and drip edge stay visible at the eaves)
// shingle-over ridge vent body, and the cap draped over it onto the shingles (same as roof_core.py)
const VENT_H = 0.032;
const CAP_OVER_VENT = [[0, H.covering + VENT_H + 0.009], [0.142, H.covering + VENT_H - 0.0015], [0.17, H.covering + 0.006]];
const COVERED = new Set(['oldFelt', 'oldShingles', 'deckRepair', 'iceWater', 'underlayment', 'starter', 'nails']);

export const STACK_ORDER = ['oldFelt', 'oldShingles', 'deck', 'deckRepair', 'dripEdge', 'iceWater', 'underlayment', 'starter', 'nails', 'covering', 'ridgeVent', 'ridgeCap'];

// Options for the non-covering layers (what the Layers panel offers)
export const LAYER_OPTIONS = {
  deck: [
    { id: 'osb', label: '7/16" OSB', tex: () => TX.osb({ fresh: false }) },
    { id: 'osb-new', label: '7/16" OSB (new)', tex: () => TX.osb({ fresh: true, seed: 4 }) },
    { id: 'ply', label: '1/2" CDX plywood', tex: () => TX.osb({ fresh: true, seed: 9 }), tint: '#e3c48e' },
  ],
  underlayment: [
    { id: 'syn-gray', label: 'Synthetic, gray', tex: () => TX.syntheticUnderlayment({ color: '#8d9399', print: '#2b4f86' }) },
    { id: 'syn-blue', label: 'Synthetic, blue', tex: () => TX.syntheticUnderlayment({ color: '#3f6fa8', print: '#e8eef6' }) },
    { id: 'syn-black', label: 'Synthetic, black', tex: () => TX.syntheticUnderlayment({ color: '#2c2f33', print: '#d8a23c' }) },
    { id: 'felt30', label: '#30 felt', tex: () => TX.felt() },
  ],
  iceWater: [
    { id: 'granular', label: 'Granular surface', tex: () => TX.iceWater({ granular: true }) },
    { id: 'smooth', label: 'Smooth film (high-temp)', tex: () => TX.iceWater({ granular: false, color: '#3b4a5a' }) },
  ],
  dripEdge: [
    { id: 'white', label: 'White aluminum', color: '#f2f1ec', metal: 0.3 },
    { id: 'black', label: 'Black aluminum', color: '#232427', metal: 0.3 },
    { id: 'brown', label: 'Brown aluminum', color: '#5a3f2b', metal: 0.3 },
    { id: 'galv', label: 'Galvanized steel', color: '#b8bcc0', metal: 0.85 },
  ],
};

export class RoofLayers {
  /**
   * @param {object} ctx  planes, segs, renderer
   */
  constructor({ planes, segs, renderer, overhangM = null }) {
    this.overhangM = overhangM; // horizontal eave overhang when known (demo houses), for the 24" ice & water rule
    this.planes = planes;
    this.segs = segs;
    this.renderer = renderer;
    this.root = new THREE.Group();
    this.root.name = 'roofLayers';
    this.layers = new Map(); // id -> layer record
    // iceRows: 'auto' = enough rows to reach 24" inside the exterior wall (needs the overhang); nails: 4 standard, 6 high wind
    this.options = { iceRows: 'auto', valleys: true, nailsPerShingle: 4, deckRepairSheets: 3, deck: 'osb', underlayment: 'syn-gray', iceWater: 'granular', dripEdge: 'white' };
    this._customSeq = 0;
    this.product = null;
    this.explode = 0; this.explodeTarget = 0; this.gap = 0.85;
    this.cut = 1; this.cutTarget = 1;
    this.cutDir = { value: new THREE.Vector3(1, 0, 0) }; // shared by every layer
    this.custom = [];
    this.specOverride = {}; // layer id -> spec line for the exploded-view label (the store product chosen)
    this.labelsOn = true;
    this.measure = measureRoof(planes, segs);
    this._cutRange = [-1, 1];
    this._anchor = this._labelAnchor();
  }

  // -------------------------------------------------------------------------
  // building

  rebuildAll(product) {
    if (product) this.product = product;
    for (const id of [...this.layers.keys()]) this._remove(id);
    this._buildOld();
    this._buildDeck();
    this._buildDrip();
    this._buildIceWater();
    this._buildUnderlayment();
    this._buildCustom();
    this._buildCovering();
    return this;
  }

  _rec(id, obj, { rowH = 1e3, keyMax = 1, materials = [], info = LAYER_INFO[id], level = STACK_ORDER.indexOf(id) } = {}) {
    const uniforms = { uReveal: { value: 1e6 }, uRowH: { value: rowH }, uCut: { value: 1e6 }, uCutDir: this.cutDir };
    for (const m of materials) patchReveal(m.material, uniforms, m.instanced);
    obj.traverse((o) => {
      if (o.isMesh) {
        o.castShadow = !o.userData.noShadow; o.receiveShadow = true;
        const dm = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
        patchReveal(dm, uniforms, o.isInstancedMesh);
        o.customDepthMaterial = dm;
        if (!materials.find((m) => m.material === o.material)) patchReveal(o.material, uniforms, o.isInstancedMesh);
      }
    });
    obj.name = `RT_layer_${id}`;
    const rec = {
      id, obj, uniforms, rowH, keyMax, info: { ...LAYER_INFO[id], ...info, ...(this.specOverride[id] ? { spec: this.specOverride[id] } : {}) }, level,
      visible: true, userVisible: true, reveal: 1, levelPos: 0, label: null,
    };
    this.root.add(obj);
    this.layers.set(id, rec);
    this._makeLabel(rec);
    this.setReveal(id, rec.reveal);
    return rec;
  }

  _remove(id) {
    const rec = this.layers.get(id);
    if (!rec) return;
    rec.obj.traverse((o) => {
      if (!o.isMesh) return;
      o.geometry.dispose();
      o.customDepthMaterial?.dispose();
      for (const m of [].concat(o.material)) disposeMaterial(m);
    });
    this.root.remove(rec.obj);
    this.layers.delete(id);
  }

  _material(set, { color = '#ffffff', metal = 0, rough = 1, side = THREE.DoubleSide, physical = false } = {}) {
    const t = set ? TX.toTextures(set, this.renderer) : {};
    const Mat = physical ? THREE.MeshPhysicalMaterial : THREE.MeshStandardMaterial;
    const m = new Mat({ color, map: t.map || null, normalMap: t.normalMap || null, roughnessMap: t.roughnessMap || null, roughness: rough, metalness: metal, side });
    if (physical) { m.clearcoat = 0.35; m.clearcoatRoughness = 0.35; }
    m.userData.texSet = set;
    return m;
  }

  _buildOld() {
    const felt = this._material(TX.felt());
    const g1 = buildSurface(fullParts(this.planes), { offset: H.oldFelt });
    this._rec('oldFelt', new THREE.Mesh(g1, felt), { rowH: inToM(34), keyMax: this._rowsMax(inToM(34)) });
    const old = TX.threeTabShingle({ worn: 1, palette: ['#57534c', '#4a4741', '#605b52'] });
    const m = this._material(old, { side: THREE.FrontSide });
    const g2 = buildSurface(fullParts(this.planes), { offset: H.oldShingles, courseH: old.exposureM, stepH: 0.004 });
    const mesh = new THREE.Mesh(g2, m);
    const capG = capGeometry([...this.segs.ridge, ...this.segs.hip], { off: H.oldShingles + 0.009 });
    const cap = new THREE.Mesh(capG, this._material(TX.ridgeCap({ palette: ['#57534c', '#4a4741', '#605b52'] })));
    const grp = new THREE.Group(); grp.add(mesh, cap);
    this._rec('oldShingles', grp, { rowH: old.exposureM, keyMax: this._rowsMax(old.exposureM) });
  }

  _buildDeck() {
    const opt = LAYER_OPTIONS.deck.find((o) => o.id === this.options.deck) || LAYER_OPTIONS.deck[0];
    const mat = this._material(opt.tex(), { color: opt.tint || '#ffffff' });
    const g = buildSurface(fullParts(this.planes), { offset: H.deck, thickness: H.deck });
    this._rec('deck', new THREE.Mesh(g, mat), { rowH: 1.2192, keyMax: this._rowsMax(1.2192), info: { spec: `${opt.label} sheathing, 4×8 sheets` } });
    // repair patches: new sheets that appear during the deck repair step
    const patches = deckPatches(this.planes, Math.max(0, Math.round(this.options.deckRepairSheets)));
    const pm = this._material(TX.osb({ fresh: true, seed: 6 }));
    const pg = buildSurface(patches, { offset: H.deck + 0.0012 }); // > 1 mm: no z-fighting with the deck
    this._rec('deckRepair', new THREE.Mesh(pg, pm), { rowH: 1e3, keyMax: 1, info: { spec: `Allowance: ${patches.length} replacement sheet${patches.length === 1 ? '' : 's'}` } });
    this.layers.get('deckRepair').count = patches.length;
  }

  _buildDrip() {
    const v = this.options.dripEdge; // an option id, or a store product's option object { id, label, color, metal }
    const opt = v && typeof v === 'object' ? v : LAYER_OPTIONS.dripEdge.find((o) => o.id === v) || LAYER_OPTIONS.dripEdge[0];
    const g = dripEdgeGeometry(this.segs, { offEave: H.dripEave, offRake: H.dripRake });
    const m = this._material(null, { color: opt.color, metal: opt.metal, rough: 0.35 });
    // eave pieces have aUp = 0, rake pieces aUp = 1 -> keys 0..1 then 1..2
    this._rec('dripEdge', new THREE.Mesh(g, m), { rowH: 1, keyMax: 2, info: { spec: `${opt.label}, eaves under / rakes over` } });
  }

  /** Rows of 36" membrane at the eaves. 'auto' reaches 24" inside the exterior wall (IRC R905.1.2). */
  iceRowsNeeded() {
    if (this.options.iceRows !== 'auto') return { rows: Number(this.options.iceRows), reachIn: null };
    if (this.overhangM == null) return { rows: 2, reachIn: null };
    const roll = inToM(36), lap = inToM(3);
    const steepest = Math.max(...this.planes.map((p) => p.slope));
    const upSlope = (this.overhangM + inToM(24)) / Math.cos(steepest); // horizontal reach measured along the slope
    const rows = Math.max(1, Math.ceil((upSlope - lap) / (roll - lap)));
    return { rows, reachIn: Math.round(upSlope / inToM(1)) };
  }

  _buildIceWater() {
    const opt = LAYER_OPTIONS.iceWater.find((o) => o.id === this.options.iceWater) || LAYER_OPTIONS.iceWater[0];
    const roll = inToM(36), lap = inToM(3);
    const { rows, reachIn } = this.iceRowsNeeded();
    const rowH = roll - lap;
    const geoms = [buildSurface(eaveParts(this.planes, this.segs, rows * rowH + lap), { offset: H.iceWater })];
    const valleys = this.options.valleys && this.segs.valley.length;
    if (valleys) {
      // valley sheets go on after the eave rows: give them the last key row
      // they start where the eave rows end (a butt joint), so no two sheets share a plane
      const vg = buildSurface(stripParts(this.planes, this.segs.valley, roll / 2, { vMin: rows * rowH + lap }), { offset: H.iceWater });
      vg.attributes.aUp.array.fill(rows * rowH + 1e-3);
      geoms.push(vg);
    }
    const g = geoms.length > 1 ? mergeGeometries(geoms) : geoms[0];
    const set = opt.tex();
    this.iceRows = rows;
    this._rec('iceWater', new THREE.Mesh(g, this._material(set)), {
      rowH, keyMax: rows + (valleys ? 1 : 0),
      info: { spec: `${opt.label}: ${rows} row${rows > 1 ? 's' : ''} at eaves${reachIn ? ` (${reachIn}" up the slope)` : ''}${valleys ? ' + valleys' : ''}` },
    });
  }

  _buildUnderlayment() {
    const opt = LAYER_OPTIONS.underlayment.find((o) => o.id === this.options.underlayment) || LAYER_OPTIONS.underlayment[0];
    const set = opt.tex();
    const rowH = set.sizeM[1];
    const g = buildSurface(fullParts(this.planes), { offset: H.underlayment });
    this._rec('underlayment', new THREE.Mesh(g, this._material(set)), { rowH, keyMax: this._rowsMax(rowH), info: { label: opt.id === 'felt30' ? 'Felt underlayment' : 'Underlayment', spec: `${opt.label}, ${opt.id === 'felt30' ? '2"' : '4"'} horizontal laps` } });
  }

  _buildCustom(list = this.custom) {
    list.forEach((c) => {
      const set = c.texSet || null;
      const g = buildSurface(c.coverage === 'eaves' ? eaveParts(this.planes, this.segs, 0.9) : fullParts(this.planes), { offset: H[c.after] ? H[c.after] + 0.0005 : H.underlayment + 0.0006 });
      const rec = this._rec(c.id, new THREE.Mesh(g, this._material(set, { color: c.color || '#ffffff' })), {
        rowH: 1.0, keyMax: this._rowsMax(1.0), info: { label: c.label, spec: c.spec || 'Custom layer' }, level: STACK_ORDER.indexOf(c.after) + 0.5,
      });
      rec.custom = true;
    });
  }

  /** Build starter, nails, covering, ridge vent and ridge cap for the selected product. */
  _buildCovering() {
    for (const id of ['starter', 'nails', 'covering', 'ridgeVent', 'ridgeCap']) this._remove(id);
    const p = this.product || {};
    const cat = p.category || 'shingle';
    const isMetal = cat === 'metal';
    const set = p._texSet || TX.architecturalShingle();
    const exposure = inToM(p.exposureIn || (cat === 'tile' ? 13 : cat === 'slate' ? 10 : cat === 'shake' ? 7.5 : 5.625));
    const stepH = cat === 'tile' ? 0.02 : cat === 'slate' || cat === 'shake' ? 0.009 : 0.005;
    const palette = p._palette || p.procedural?.palette || [p.procedural?.color || '#3a3d42'];

    // starter strip (not used under standing seam panels)
    if (!isMetal) {
      const starterParts = [...eaveParts(this.planes, this.segs, inToM(7)), ...stripParts(this.planes, this.segs.rake, inToM(7), { vMin: inToM(7) })];
      const g = buildSurface(starterParts, { offset: H.starter });
      this._rec('starter', new THREE.Mesh(g, this._material(TX.starterStrip())), { rowH: 1e3, keyMax: 1 });
    }

    // fasteners
    if (isMetal) {
      const clips = nailLayout(this.planes, { exposure: 0.6, spacing: inToM(16), off: H.underlayment + 0.003 });
      this._fasteners(clips, 'Panel clips', 'Concealed clips at each seam, 24" o.c.', 0.6);
    } else {
      const spacing = this.options.nailsPerShingle >= 6 ? inToM(39.375) / 6 : inToM(39.375) / 4;
      const nails = nailLayout(this.planes, { exposure, spacing, off: H.nails });
      this._fasteners(nails, 'Fasteners', `1-1/4" coil nails, ${this.options.nailsPerShingle} per shingle`, exposure);
    }

    // the covering itself
    const parts = fullParts(this.planes);
    const flat = isMetal || p.flat;
    const g = flat ? buildSurface(parts, { offset: H.covering }) : buildSurface(parts, { offset: H.covering, courseH: exposure, stepH });
    const mat = this._material(set, { side: THREE.FrontSide, metal: isMetal ? (p.pbr?.metallic ?? 0.55) : 0, rough: isMetal && p.pbr?.roughness != null ? p.pbr.roughness / TX.roughMean(set) : 1, physical: isMetal });
    if (p.tint) mat.color.set(p.tint);
    this._applyTransform(mat, p);
    this._rec('covering', new THREE.Mesh(g, mat), {
      rowH: isMetal ? 1e3 : exposure, keyMax: isMetal ? 1 : this._rowsMax(exposure),
      info: { label: isMetal ? 'Metal panels' : cat === 'tile' ? 'Roof tile' : cat === 'slate' ? 'Slate' : cat === 'shake' ? 'Cedar shakes' : 'Shingles', spec: p.name ? `${p.name}${p.supplier ? ' · ' + p.supplier : ''}` : 'Architectural laminate' },
    });

    // ridge vent (ridges only) and hip & ridge caps
    const hasVent = this.options.ridgeVent !== false && this.segs.ridge.length;
    if (hasVent) {
      const rv = ridgeVentGeometry(this.segs.ridge, { off: H.covering, height: VENT_H }); // sides stand on the shingles: no gap under the vent
      const grp = new THREE.Group();
      const vm = this._material(null, { color: '#1d1f22', rough: 0.7 });
      grp.add(new THREE.Mesh(rv.top, vm), new THREE.Mesh(rv.skirt, this._material(null, { color: '#2a2c2f', rough: 0.9 })));
      this._rec('ridgeVent', grp, { rowH: 1e3, keyMax: 1 });
    }
    const capSet = isMetal ? null : TX.ridgeCap({ palette: this.options.capPalette || (palette.length > 1 ? palette : shadesOf(palette[0])) });
    const capMat = this._material(capSet, { color: isMetal ? (this.options.capColor || p.procedural?.color || '#40464d') : '#ffffff', metal: isMetal ? (p.pbr?.metallic ?? 0.55) : 0, rough: isMetal ? (p.pbr?.roughness ?? 0.4) : 1, side: THREE.FrontSide });
    // hips are capped first (bottom up), then the ridge: ridge pieces get key row 1 when hips exist
    const grp = new THREE.Group();
    const hips = this.segs.hip.length > 0, ridges = this.segs.ridge.length > 0;
    if (hips) grp.add(new THREE.Mesh(capGeometry(this.segs.hip, { off: H.cap }), capMat));
    if (ridges) {
      const rg = capGeometry(this.segs.ridge, hasVent ? { profile: CAP_OVER_VENT } : { off: H.cap });
      if (hips) rg.attributes.aUp.array.fill(1);
      grp.add(new THREE.Mesh(rg, capMat));
    }
    if (grp.children.length) this._rec('ridgeCap', grp, { rowH: 1, keyMax: hips && ridges ? 2 : 1, info: { spec: isMetal ? 'Matching metal ridge cap' : 'Matching cap shingles, 5-5/8" exposure' } });
    this._applyState();
  }

  _fasteners(layout, label, spec, rowH) {
    const geo = nailGeometry();
    geo.setAttribute('aKey', new THREE.InstancedBufferAttribute(layout.keys, 1));
    const mat = new THREE.MeshStandardMaterial({ color: '#b9bcc0', metalness: 0.9, roughness: 0.35 });
    const mesh = new THREE.InstancedMesh(geo, mat, Math.max(1, layout.count));
    for (let i = 0; i < layout.count; i++) mesh.instanceMatrix.array.set(layout.matrices.subarray(i * 16, i * 16 + 16), i * 16);
    mesh.instanceMatrix.needsUpdate = true;
    mesh.count = layout.count;
    mesh.computeBoundingSphere();
    mesh.frustumCulled = false;
    mesh.userData.noShadow = true;
    this._rec('nails', mesh, { rowH, keyMax: this._rowsMax(rowH), materials: [{ material: mat, instanced: true }], info: { label, spec: `${spec} · ${layout.count.toLocaleString()} total` } });
    this.layers.get('nails').count = layout.count;
  }

  _rowsMax(rowH) {
    const vMax = Math.max(...this.planes.map((p) => p.vMax));
    return Math.floor(vMax / rowH) + 1;
  }

  // -------------------------------------------------------------------------
  // covering product

  /** Apply a catalog product (procedural recipe or photo already loaded into _texSet). */
  setProduct(product) {
    this.product = product;
    this._buildCovering();
  }

  /** Update texture transform / tint without rebuilding geometry. */
  updateProductTransform(p) {
    const rec = this.layers.get('covering');
    if (!rec) return;
    const mat = rec.obj.material;
    if (p.tint) mat.color.set(p.tint); else mat.color.set('#ffffff');
    this._applyTransform(mat, p);
  }

  _applyTransform(mat, p) {
    const set = mat.userData.texSet;
    if (!set) return;
    const sx = set.sizeM[0] * (p.scale || 1), sy = set.sizeM[1] * (p.scale || 1);
    for (const t of [mat.map, mat.normalMap, mat.roughnessMap]) {
      if (!t) continue;
      t.repeat.set(1 / sx, 1 / sy);
      t.rotation = THREE.MathUtils.degToRad(p.rotation || 0);
      t.offset.set(p.offsetU || 0, p.offsetV || 0);
    }
    if (mat.normalScale) mat.normalScale.setScalar(p.reliefScale ?? 1);
  }

  setOption(key, value) {
    this.options[key] = value;
    const rebuild = {
      deck: () => { this._remove('deck'); this._remove('deckRepair'); this._buildDeck(); },
      underlayment: () => { this._remove('underlayment'); this._buildUnderlayment(); },
      iceWater: () => { this._remove('iceWater'); this._buildIceWater(); },
      iceRows: () => { this._remove('iceWater'); this._buildIceWater(); },
      valleys: () => { this._remove('iceWater'); this._buildIceWater(); },
      dripEdge: () => { this._remove('dripEdge'); this._buildDrip(); },
      nailsPerShingle: () => this._buildCovering(),
      deckRepairSheets: () => { this._remove('deck'); this._remove('deckRepair'); this._buildDeck(); },
      ridgeVent: () => this._buildCovering(),
      capPalette: () => this._buildCovering(), capColor: () => this._buildCovering(),
    }[key];
    rebuild?.();
    this._applyState();
  }

  addCustomLayer(c) {
    const id = 'custom' + (++this._customSeq); // never reused, even after a removal
    this.custom.push({ id, ...c });
    LAYER_INFO[id] = { label: c.label, spec: c.spec || 'Custom layer' };
    this._buildCustom([this.custom[this.custom.length - 1]]);
    this._applyState();
    return id;
  }

  removeCustomLayer(id) {
    this.custom = this.custom.filter((c) => c.id !== id);
    this._remove(id);
    this._applyState();
  }

  // -------------------------------------------------------------------------
  // state

  /** Reveal fraction (0..1) of a layer in its build order. */
  setReveal(id, frac) {
    const rec = this.layers.get(id);
    if (!rec) return;
    rec.reveal = frac;
    rec.uniforms.uReveal.value = frac >= 1 ? 1e6 : frac <= 0 ? -1 : frac * rec.keyMax;
    rec.visible = rec.userVisible && frac > 0;
    rec.obj.visible = rec.visible;
  }

  setVisible(id, v) {
    const rec = this.layers.get(id);
    if (!rec) return;
    rec.userVisible = v;
    rec.visible = v && rec.reveal > 0;
    rec.obj.visible = rec.visible;
  }

  setAllRevealed(on = true) {
    for (const rec of this.layers.values()) this.setReveal(rec.id, rec.info.group === 'old' ? (on ? 0 : 1) : on ? 1 : 0);
  }

  setExplode(on) { this.explodeTarget = on ? 1 : 0; }
  /** @param {THREE.Vector3} [dir] horizontal direction to cut from (defaults to +X) */
  setCutaway(on, dir) {
    this.cutTarget = on ? 0 : 1;
    if (dir) { this.cutDir.value.copy(dir).setY(0).normalize(); }
    this._cutRange = this._range(this.cutDir.value);
  }

  _range(dir) {
    let lo = Infinity, hi = -Infinity;
    for (const p of this.planes) for (const t of p.tris) for (const [u, v] of t) { const d = p.to3(u, v).dot(dir); lo = Math.min(lo, d); hi = Math.max(hi, d); }
    return [lo, hi];
  }

  /** Ordered list of layer records (bottom to top). */
  ordered() {
    return [...this.layers.values()].sort((a, b) => a.level - b.level);
  }

  _applyState() {
    for (const rec of this.layers.values()) {
      rec.obj.visible = rec.visible;
    }
  }

  /** Layers that cannot be seen once the covering is finished and the stack is closed. */
  _applyOcclusion(e) {
    const cov = this.layers.get('covering');
    const sealed = !!cov && cov.visible && cov.reveal >= 1 && e < 0.002 && this.cut >= 0.999;
    for (const rec of this.layers.values()) {
      const hidden = sealed && COVERED.has(rec.id);
      rec.obj.visible = rec.visible && !hidden;
    }
    return sealed;
  }

  /** Per-frame animation of explode and cutaway. Returns true while animating. */
  update(dt) {
    let moving = false;
    const k = 1 - Math.exp(-dt * 4.5);
    const de = this.explodeTarget - this.explode;
    if (Math.abs(de) > 1e-4) { this.explode += de * k; moving = true; } else this.explode = this.explodeTarget;
    const dc = this.cutTarget - this.cut;
    if (Math.abs(dc) > 1e-4) { this.cut += dc * k; moving = true; } else this.cut = this.cutTarget;
    // pack visible layers into levels
    let level = 0;
    const order = this.ordered();
    const e = easeInOutCubic(Math.min(1, Math.max(0, this.explode)));
    let cutLevel = 0;
    for (const rec of order) {
      const shown = rec.visible && rec.id !== 'deckRepair';
      const target = shown ? level : rec.levelPos;
      if (shown) level++;
      if (rec.id === 'deckRepair') rec.levelPos = this.layers.get('deck')?.levelPos ?? 0;
      else rec.levelPos += (target - rec.levelPos) * k;
      rec.obj.position.y = rec.levelPos * this.gap * e;
      // cutaway: each higher layer is cut back further along the cut direction (world space)
      const [cMin, cMax] = this._cutRange;
      const span = cMax - cMin;
      const cutAt = this.cut >= 0.999 ? 1e6 : cMax + 0.01 - (1 - this.cut) * span * (0.2 + cutLevel * 0.07);
      rec.uniforms.uCut.value = rec.info.group === 'old' || rec.id === 'deck' ? 1e6 : cutAt;
      if (shown && rec.info.group !== 'old') cutLevel++;
      rec.labelShow = this.labelsOn && shown && e > 0.35;
      rec.labelOpacity = rec.labelShow ? Math.min(1, (e - 0.35) / 0.4) : 0;
    }
    this._applyOcclusion(e);
    return moving;
  }

  // -------------------------------------------------------------------------
  // labels for the exploded view

  _labelAnchor() {
    let best = null, score = -Infinity;
    for (const p of this.planes) for (const t of p.tris) for (const [u, v] of t) {
      const q = p.to3(u, v);
      const s = q.x + q.z * 0.35 - q.y * 0.5;
      if (s > score) { score = s; best = q; }
    }
    return best || new THREE.Vector3();
  }

  /** Anchor point on the layer's own geometry, toward the front-right of the roof. */
  _anchorFor(rec) {
    let best = null, score = -Infinity;
    const v = new THREE.Vector3(), m = new THREE.Matrix4();
    const consider = (x, y, z) => { const s = x + z * 0.35 - y * 0.5; if (s > score) { score = s; best = new THREE.Vector3(x, y, z); } };
    rec.obj.traverse((o) => {
      if (!o.isMesh) return;
      if (o.isInstancedMesh) {
        for (let i = 0; i < o.count; i += 3) { o.getMatrixAt(i, m); v.setFromMatrixPosition(m); consider(v.x, v.y, v.z); }
        return;
      }
      const pos = o.geometry.attributes.position;
      const stride = Math.max(1, Math.floor(pos.count / 4000));
      for (let i = 0; i < pos.count; i += stride) consider(pos.getX(i), pos.getY(i), pos.getZ(i));
    });
    return best || this._anchor.clone();
  }

  _makeLabel(rec) {
    if (rec.info.hidden) return;
    const anchor = new THREE.Object3D();
    anchor.name = `label_${rec.id}`;
    anchor.position.copy(this._anchorFor(rec));
    rec.obj.add(anchor);
    rec.label = anchor;
  }

  refreshLabels() { /* titles are read live by labelItems() */ }

  /** Items for the callout overlay and snapshot export. */
  labelItems() {
    const out = [];
    for (const rec of this.layers.values()) {
      if (!rec.label) continue;
      out.push({ id: rec.id, object: rec.label, title: rec.info.label, spec: rec.info.spec || '', show: !!rec.labelShow && rec.obj.visible, opacity: rec.labelOpacity ?? 1 });
    }
    return out;
  }

  // -------------------------------------------------------------------------
  // takeoff (material quantities) for the estimate panel

  /** Suggested waste: 10% on simple gables, 15% with hips or valleys, up to 20% on cut-up roofs. */
  suggestedWaste() {
    const m = this.measure;
    if (!m.hipM && !m.valleyM) return 0.10;
    const cut = (m.hipM + m.valleyM) / Math.max(1, m.eaveM + m.rakeM);
    return cut > 0.8 ? 0.20 : cut > 0.4 ? 0.17 : 0.15;
  }

  /** Measured inputs for the materials list (quote.js). Feet and square feet. */
  quantities() {
    const ice = this.layers.get('iceWater');
    return toQuantities({
      measure: this.measure,
      ridgeLengthsM: this.segs.ridge.map((l) => l.A.distanceTo(l.B)),
      iceM2: ice ? geomArea(ice.obj.geometry) : 0,
      iceRows: ice ? this.iceRows : 0,
      ventOn: this.options.ridgeVent !== false,
      nailCount: this.layers.get('nails')?.count || 0,
      deckRepairSheets: Math.max(0, Math.round(this.options.deckRepairSheets || 0)),
      category: this.product?.category || 'shingle',
    });
  }

  /** Measurements only. Order quantities and prices are on the List tab (quote.js reads quantities()). */
  takeoff({ waste = this.suggestedWaste() } = {}) {
    const m = this.measure;
    const q = this.quantities();
    const valleys = this.options.valleys && this.segs.valley.length;
    return [
      ['Roof area', `${m.areaM2.toFixed(1)} m² · ${q.areaSqft.toFixed(0)} sq ft`],
      ['Squares (before waste)', q.squares.toFixed(2)],
      [`Waste allowance`, `${Math.round(waste * 100)}%`],
      ['Eaves', fmtLen(m.eaveM)], ['Rakes', fmtLen(m.rakeM)], ['Ridges', fmtLen(m.ridgeM)], ['Hips', fmtLen(m.hipM)], ['Valleys', fmtLen(m.valleyM)],
      ['Ice & water area', q.iceSqft > 0 ? `${q.iceSqft.toFixed(0)} sq ft · ${q.iceRows} row${q.iceRows === 1 ? '' : 's'} at eaves${valleys ? ' + valleys' : ''}` : '—'],
      ['Ridge vent', q.ventFt > 0 ? fmtLen(q.ventFt * 0.3048) : '—'],
      [q.category === 'metal' ? 'Panel clips (count)' : q.category === 'shingle' ? 'Field nails (count)' : 'Fasteners (count)', q.nailCount.toLocaleString()],
      ['Deck repair allowance (sheets)', `${q.deckRepairSheets}`],
    ];
  }

  /** True while any visible layer is only partly built (the path tracer cannot show that). */
  isPartial() {
    for (const rec of this.layers.values()) if (rec.visible && rec.reveal > 0 && rec.reveal < 1) return true;
    return false;
  }
}

/** Dispose a material and every texture it holds. */
export function disposeMaterial(m) {
  if (!m) return;
  for (const k of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'alphaMap', 'bumpMap']) m[k]?.dispose?.();
  m.dispose();
}

function fmtLen(m) { return `${(m / 0.3048).toFixed(1)} ft · ${m.toFixed(2)} m`; }
function geomArea(g) {
  if (!g) return 0;
  const p = g.attributes.position; let s = 0;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let i = 0; i < p.count; i += 3) {
    a.fromBufferAttribute(p, i); b.fromBufferAttribute(p, i + 1); c.fromBufferAttribute(p, i + 2);
    s += b.sub(a).cross(c.sub(a)).length() / 2;
  }
  return s;
}

export function shadesOf(hex) {
  const c = hexToRgb(hex);
  return [rgbToHex(c), rgbToHex(c.map((x) => x * 0.78)), rgbToHex(c.map((x) => Math.min(255, x * 1.18))), rgbToHex(c.map((x) => x * 0.62))];
}

/**
 * Inject the build-reveal and cutaway test into a three.js material.
 * key = floor(aUp / uRowH) + aAlong for surfaces; aKey for instanced fasteners.
 */
export function patchReveal(material, uniforms, instanced = false) {
  if (material.userData.rtPatched) return;
  material.userData.rtPatched = true;
  const prev = material.onBeforeCompile;
  material.onBeforeCompile = (shader, r) => {
    prev?.(shader, r);
    shader.uniforms.uReveal = uniforms.uReveal;
    shader.uniforms.uRowH = uniforms.uRowH;
    shader.uniforms.uCut = uniforms.uCut;
    shader.uniforms.uCutDir = uniforms.uCutDir;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
attribute float aUp;
attribute float aAlong;
uniform vec3 uCutDir;
varying float vRtUp;
varying float vRtAlong;
varying float vRtCut;
${instanced ? 'attribute float aKey;\nvarying float vRtKey;' : ''}`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
vRtUp = aUp;
vRtAlong = aAlong;
vec4 rtWorld = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
rtWorld = instanceMatrix * rtWorld;
#endif
rtWorld = modelMatrix * rtWorld;
vRtCut = dot(rtWorld.xyz, uCutDir);
${instanced ? 'vRtKey = aKey;\nvRtAlong = fract(aKey);' : ''}`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
uniform float uReveal;
uniform float uRowH;
uniform float uCut;
varying float vRtUp;
varying float vRtAlong;
varying float vRtCut;
${instanced ? 'varying float vRtKey;' : ''}`)
      .replace('void main() {', `void main() {
  float rtKey = ${instanced ? 'vRtKey' : 'floor(vRtUp / uRowH + 1e-4) + vRtAlong'};
  if (rtKey > uReveal) discard;
  if (vRtCut > uCut) discard;`);
  };
  material.customProgramCacheKey = () => 'rt-reveal-' + (instanced ? 'i' : 's');
  material.needsUpdate = true;
}
