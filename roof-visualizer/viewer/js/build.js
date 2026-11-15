// Build sequence: plan format, rule-based plan generator, and the timeline
// player that turns a plan into per-layer reveal values at any time t.
//
// Plan JSON (see plans/README.md and plans/*.json):
// {
//   "title": "...", "summary": "...",
//   "steps": [
//     { "id": "tearoff", "title": "Tear off existing shingles", "detail": "...",
//       "duration": 6, "camera": "orbit",
//       "actions": [ { "layer": "oldShingles", "op": "remove" } ] }
//   ]
// }
// ops: install (reveal from -> to), remove (reveal to -> from, top rows first),
//      show / hide (instant at step start).  from/to are fractions 0..1 of the
//      layer's build order (e.g. drip edge: 0-0.5 = eaves, 0.5-1 = rakes).

import { Emitter, clamp, fmtFtIn, inToM } from './util.js';

export const PLAN_LAYERS = ['oldShingles', 'oldFelt', 'deck', 'deckRepair', 'dripEdge', 'iceWater', 'underlayment', 'starter', 'nails', 'covering', 'ridgeVent', 'ridgeCap'];

/**
 * Generate a full replacement plan from the current layer stack and options.
 * This is the offline "AI" generator: rules that a roofing PM would follow.
 * A richer plan can be written by Claude (see SKILL.md) or by the server's
 * /api/plan endpoint and loaded with ?plan=plans/<file>.json
 */
export function autoPlan(layers, { product } = {}) {
  const m = layers.measure;
  const opt = layers.options;
  const sq = m.squares;
  const has = (id) => layers.layers.has(id);
  const cat = product?.category || 'shingle';
  const isMetal = cat === 'metal';
  const lf = (x) => `${Math.round(x / 0.3048)} ft`;
  const scale = (base, perSq) => +(base + perSq * sq).toFixed(1);
  const steps = [];
  steps.push({
    id: 'site', title: 'Site protection', camera: 'orbit', duration: 2,
    detail: 'Tarps over landscaping, plywood against the walls, dumpster placed by the driveway, magnetic sweeper staged.',
    actions: [],
  });
  steps.push({
    id: 'tearoff', title: 'Tear off existing shingles', camera: 'orbit', duration: scale(3, 0.12),
    detail: `Strip ${sq.toFixed(1)} squares from the ridge down, plane by plane. Old nails pulled or driven flush.`,
    actions: [{ layer: 'oldShingles', op: 'remove' }],
  });
  steps.push({
    id: 'felt', title: 'Remove old felt', duration: scale(1.5, 0.05),
    detail: 'Felt and any remaining fasteners come off so the deck can be inspected.',
    actions: [{ layer: 'oldFelt', op: 'remove' }],
  });
  steps.push({
    id: 'deck', title: 'Inspect and repair the deck', camera: 'top', duration: 3,
    detail: (() => {
      const n = layers.layers.get('deckRepair')?.count ?? 0;
      return `Walk the deck for soft spots and delamination. ${n ? `Allowance shown: ${n} sheet${n > 1 ? 's' : ''} of 7/16" OSB replaced; the real count is set on site.` : 'No sheet replacement allowed for.'} Deck re-nailed where loose.`;
    })(),
    actions: [{ layer: 'deckRepair', op: 'install' }],
  });
  if (has('dripEdge')) steps.push({
    id: 'drip-eave', title: 'Drip edge at the eaves', duration: 2,
    detail: `${lf(m.eaveM)} of drip edge along the eaves, fastened 12" o.c., under the ice & water shield.`,
    actions: [{ layer: 'dripEdge', op: 'install', from: 0, to: 0.5 }],
  });
  if (has('iceWater')) steps.push({
    id: 'ice', title: 'Ice & water shield', duration: scale(2, 0.05),
    detail: (() => {
      const { rows, reachIn } = layers.iceRowsNeeded ? layers.iceRowsNeeded() : { rows: opt.iceRows, reachIn: null };
      const reach = reachIn ? ` reaching ${reachIn}" up the slope, 24" inside the exterior wall` : '';
      return `${rows} row${rows > 1 ? 's' : ''} of 36" self-adhered membrane at the eaves${reach}${opt.valleys && m.valleyM > 0 ? `, plus ${lf(m.valleyM)} of valley centered 18" each side` : ''}. 3" side laps, 6" end laps.`;
    })(),
    actions: [{ layer: 'iceWater', op: 'install' }],
  });
  if (has('underlayment')) steps.push({
    id: 'underlayment', title: 'Underlayment', duration: scale(2.5, 0.08),
    detail: `${layers.layers.get('underlayment').info.spec}. Rolled out bottom to top, cap nails 12" o.c. on the laps, 24" in the field.`,
    actions: [{ layer: 'underlayment', op: 'install' }],
  });
  if (has('dripEdge')) steps.push({
    id: 'drip-rake', title: 'Drip edge at the rakes', duration: 1.5,
    detail: `${lf(m.rakeM)} of drip edge on the rakes, installed over the underlayment so water sheds onto it.`,
    actions: [{ layer: 'dripEdge', op: 'install', from: 0.5, to: 1 }],
  });
  if (has('starter')) steps.push({
    id: 'starter', title: 'Starter strip', duration: 2,
    detail: `Starter course along ${lf(m.eaveM + m.rakeM)} of eaves and rakes, sealant strip toward the edge, overhanging the drip edge 1/4"–3/4".`,
    actions: [{ layer: 'starter', op: 'install' }],
  });
  const covering = layers.layers.get('covering');
  const exposure = covering?.rowH || inToM(5.625);
  steps.push({
    id: 'field', title: isMetal ? 'Metal panels' : cat === 'shingle' ? 'Shingles, course by course' : `${cat === 'tile' ? 'Tile' : cat === 'slate' ? 'Slate' : 'Shakes'}, course by course`, camera: 'orbit', duration: scale(5, 0.35),
    detail: isMetal
      ? 'Panels set left to right, each seam clipped 24" o.c. and mechanically seamed.'
      : cat === 'shingle'
        ? `${Math.ceil(sq * 3 * (1 + (layers.suggestedWaste?.() ?? 0.12)))} bundles. ${fmtFtIn(exposure)} exposure, ${opt.nailsPerShingle} nails per shingle on the nail line${opt.nailsPerShingle >= 6 ? ' (high-wind pattern)' : ''}, 6" minimum offset between courses.`
        : `${fmtFtIn(exposure)} exposure, laid from the eaves up and fastened per the manufacturer's instructions for ${cat}.`,
    actions: [{ layer: 'covering', op: 'install' }, { layer: 'nails', op: 'install' }],
  });
  if (has('ridgeVent')) steps.push({
    id: 'vent', title: 'Ridge vent', duration: 2,
    detail: `Ridge slot cut 1" each side of the ridge board, ${lf(m.ridgeM)} of shingle-over vent fastened with 1-3/4" nails.`,
    actions: [{ layer: 'ridgeVent', op: 'install' }],
  });
  if (has('ridgeCap')) steps.push({
    id: 'cap', title: 'Hip & ridge cap', duration: 2.5,
    detail: `${lf(m.ridgeM + m.hipM)} of cap installed from the bottom of each hip up and into the prevailing wind on ridges.`,
    actions: [{ layer: 'ridgeCap', op: 'install' }],
  });
  steps.push({
    id: 'cleanup', title: 'Clean-up and final inspection', camera: 'orbit', duration: 2,
    detail: 'Magnetic sweep of the yard and driveway, gutters cleared, photos of every plane for the warranty file.',
    actions: [],
  });
  return {
    title: `${product?.name || 'Roof'} replacement`,
    summary: `${sq.toFixed(1)} squares, ${m.planes} planes. Auto-generated from the layer stack.`,
    generator: 'auto',
    steps,
  };
}

/** Validate and normalise a plan loaded from JSON. Throws with a readable message. */
export const PLAN_OPS = ['install', 'remove', 'show', 'hide'];

/** Validate and normalise a plan loaded from JSON. Throws with a readable message. */
export function normalizePlan(plan) {
  if (!plan || !Array.isArray(plan.steps)) throw new Error('Plan needs a "steps" array.');
  if (plan.steps.length > 200) throw new Error('Plan has more than 200 steps.');
  const num = (v, d, i, k) => {
    if (v === undefined || v === null) return d;
    const n = Number(v);
    if (!Number.isFinite(n)) throw new Error(`Step ${i + 1}: "${k}" must be a number.`);
    return n;
  };
  const steps = plan.steps.map((s, i) => {
    const actions = (s.actions || []).map((a) => {
      if (!a || typeof a.layer !== 'string' || !a.layer) throw new Error(`Step ${i + 1}: every action needs a "layer".`);
      const op = a.op || 'install';
      if (!PLAN_OPS.includes(op)) throw new Error(`Step ${i + 1}: unknown op "${op}" (use ${PLAN_OPS.join(', ')}).`);
      return { layer: a.layer, op, from: clamp(num(a.from, 0, i, 'from')), to: clamp(num(a.to, 1, i, 'to')) };
    });
    return {
      id: String(s.id || `step${i + 1}`), title: String(s.title || `Step ${i + 1}`), detail: String(s.detail || ''),
      duration: Math.min(120, Math.max(0.2, num(s.duration, 2, i, 'duration'))), camera: s.camera || null, actions,
    };
  });
  return { title: String(plan.title || 'Build plan'), summary: String(plan.summary || ''), generator: plan.generator || 'file', steps };
}

export class BuildPlayer extends Emitter {
  constructor(layers) {
    super();
    this.layers = layers;
    this.plan = null;
    this.t = 0;
    this.playing = false;
    this.speed = 1;
    this.starts = [];
  }

  setPlan(plan) {
    this.plan = normalizePlan(plan);
    // layers the model does not have (e.g. ridgeVent on a gable without vent) are skipped, and reported
    const known = this.layers ? new Set(this.layers.layers.keys()) : null;
    this.unknownLayers = known ? [...new Set(this.plan.steps.flatMap((s) => s.actions.map((a) => a.layer)).filter((id) => !known.has(id)))] : [];
    let acc = 0;
    this.starts = this.plan.steps.map((s) => { const st = acc; acc += s.duration; return st; });
    this.duration = acc;
    this.seek(Math.min(this.t, this.duration));
    this.emit('plan', this.plan);
  }

  stepAt(t = this.t) {
    if (!this.plan) return -1;
    for (let i = this.starts.length - 1; i >= 0; i--) if (t >= this.starts[i]) return i;
    return 0;
  }

  /** Compute and apply every layer's reveal for time t. */
  seek(t) {
    if (!this.plan) return;
    this.t = clamp(t, 0, this.duration);
    const L = this.layers;
    const state = new Map();
    // initial state: existing roof on, everything new off
    for (const rec of L.layers.values()) state.set(rec.id, rec.info.group === 'old' ? 1 : 0);
    const touched = new Set(this.plan.steps.flatMap((s) => s.actions.map((a) => a.layer)));
    // layers the plan never mentions are shown from the start (e.g. custom layers)
    for (const rec of L.layers.values()) if (!touched.has(rec.id) && rec.info.group !== 'old') state.set(rec.id, 1);
    // the deck is already there under the old roof unless the plan installs it (new construction)
    const deckInstalled = this.plan.steps.some((s) => s.actions.some((a) => a.layer === 'deck' && a.op === 'install'));
    if (!deckInstalled) state.set('deck', 1);
    this.plan.steps.forEach((s, i) => {
      const p = clamp((this.t - this.starts[i]) / s.duration);
      if (p <= 0) return;
      for (const a of s.actions) {
        if (a.op === 'install') state.set(a.layer, a.from + (a.to - a.from) * p);
        else if (a.op === 'remove') state.set(a.layer, a.to - (a.to - a.from) * p);
        else if (a.op === 'show') state.set(a.layer, 1);
        else if (a.op === 'hide') state.set(a.layer, 0);
      }
    });
    for (const [id, v] of state) L.setReveal(id, v);
    const i = this.stepAt();
    this.emit('time', { t: this.t, duration: this.duration, step: i, stepProgress: clamp((this.t - this.starts[i]) / this.plan.steps[i].duration) });
  }

  play() { if (this.t >= this.duration - 1e-3) this.seek(0); this.playing = true; this.emit('play', true); }
  pause() { this.playing = false; this.emit('play', false); }
  toggle() { this.playing ? this.pause() : this.play(); }
  jumpToStep(i) { this.seek(this.starts[i] + 1e-3); }
  finish() { this.pause(); this.seek(this.duration); }
  reset() { this.pause(); this.seek(0); }

  update(dt) {
    if (!this.playing) return false;
    this.seek(this.t + dt * this.speed);
    if (this.t >= this.duration) { this.pause(); this.emit('done'); }
    return true;
  }
}
