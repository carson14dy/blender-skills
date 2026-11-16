// Build-sequence player: state at any time t must be deterministic and scrub both ways.
import test from 'node:test';
import assert from 'node:assert/strict';
import { BuildPlayer, normalizePlan } from '../viewer/js/build.js';

function fakeLayers(ids) {
  const layers = new Map(ids.map((id) => [id, { id, reveal: 1, info: { group: id.startsWith('old') ? 'old' : 'new' } }]));
  return { layers, setReveal(id, v) { layers.get(id).reveal = v; } };
}

const plan = {
  title: 'Test',
  steps: [
    { title: 'Tear off', duration: 4, actions: [{ layer: 'oldShingles', op: 'remove' }] },
    { title: 'Drip eaves', duration: 2, actions: [{ layer: 'dripEdge', op: 'install', from: 0, to: 0.5 }] },
    { title: 'Shingles', duration: 4, actions: [{ layer: 'covering', op: 'install' }, { layer: 'nails', op: 'install' }] },
    { title: 'Drip rakes', duration: 2, actions: [{ layer: 'dripEdge', op: 'install', from: 0.5, to: 1 }] },
  ],
};

test('initial state: existing roof on, new layers off, deck on', () => {
  const L = fakeLayers(['oldShingles', 'deck', 'dripEdge', 'covering', 'nails', 'custom1']);
  const p = new BuildPlayer(L); p.setPlan(plan); p.seek(0);
  assert.equal(L.layers.get('oldShingles').reveal, 1);
  assert.equal(L.layers.get('covering').reveal, 0);
  assert.equal(L.layers.get('deck').reveal, 1);
  assert.equal(L.layers.get('custom1').reveal, 1, 'layers the plan never mentions stay visible');
});

test('tear-off halfway removes half, then drip edge splits eaves and rakes', () => {
  const L = fakeLayers(['oldShingles', 'deck', 'dripEdge', 'covering', 'nails']);
  const p = new BuildPlayer(L); p.setPlan(plan);
  p.seek(2);
  assert.equal(L.layers.get('oldShingles').reveal, 0.5);
  p.seek(6);
  assert.equal(L.layers.get('dripEdge').reveal, 0.5);
  p.seek(8);
  assert.equal(L.layers.get('covering').reveal, 0.5);
  assert.equal(L.layers.get('nails').reveal, 0.5, 'nails follow the courses');
  p.seek(12);
  assert.equal(L.layers.get('dripEdge').reveal, 1);
  assert.equal(L.layers.get('oldShingles').reveal, 0);
});

test('scrubbing backwards restores earlier state', () => {
  const L = fakeLayers(['oldShingles', 'deck', 'dripEdge', 'covering', 'nails']);
  const p = new BuildPlayer(L); p.setPlan(plan);
  p.seek(12); p.seek(1);
  assert.equal(L.layers.get('covering').reveal, 0);
  assert.equal(L.layers.get('oldShingles').reveal, 0.75);
});

test('normalizePlan validates and fills defaults', () => {
  const n = normalizePlan({ steps: [{ actions: [{ layer: 'deck' }] }] });
  assert.equal(n.steps[0].duration, 2);
  assert.equal(n.steps[0].actions[0].op, 'install');
  assert.throws(() => normalizePlan({}), /steps/);
  assert.throws(() => normalizePlan({ steps: [{ actions: [{ op: 'install' }] }] }), /layer/);
});

test('example plans in viewer/plans are valid', async () => {
  const fs = await import('node:fs/promises');
  const dir = new URL('../viewer/plans/', import.meta.url);
  for (const f of (await fs.readdir(dir)).filter((x) => x.endsWith('.json') && x !== 'index.json')) {
    const p = normalizePlan(JSON.parse(await fs.readFile(new URL(f, dir), 'utf8')));
    assert.ok(p.steps.length > 3, f);
  }
});
