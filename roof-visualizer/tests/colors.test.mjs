// Store color statistic (lab experiment 016): synthetic 96 x 96 images, no network.
import test from 'node:test';
import assert from 'node:assert/strict';
import { sampleColor, nameCheck, colorFromName, rgbOf } from '../scripts/lib/swatch-color.mjs';

const S = 96;
/** 96 x 96 RGB image; fill(x, y) returns a hex. */
const image = (fill) => {
  const a = new Uint8Array(S * S * 3);
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) a.set(rgbOf(fill(x, y)), (y * S + x) * 3);
  return a;
};
const near = (hex, want, tol, msg) => {
  const a = rgbOf(hex), b = rgbOf(want);
  assert.ok(a.every((v, i) => Math.abs(v - b[i]) <= tol), `${msg || ''} ${hex} is not within ${tol} of ${want}`);
};

test('a flat chip is its own color', () => {
  const r = sampleColor(image(() => '#7d3326'));
  assert.equal(r.hex, '#7d3326');
  assert.equal(r.method, 'full');
  assert.equal(r.palette.length, 1);
  assert.deepEqual(r.check, []);
});

test('a product on a white background: the background is cut out', () => {
  // 40% of the frame: 64 x 57.6 -> 64 x 58 rectangle (40.3%)
  const r = sampleColor(image((x, y) => (x >= 16 && x < 80 && y >= 19 && y < 77 ? '#313236' : '#ffffff')));
  near(r.hex, '#313236', 2);
  assert.equal(r.method, 'cutout');
  assert.ok(Math.abs(r.kept - 0.40) <= 0.02, `kept ${r.kept}`);
});

test('white on white uses every pixel', () => {
  const r = sampleColor(image(() => '#f4f4f2'));
  assert.equal(r.method, 'all');
  near(r.hex, '#f4f4f2', 3);
});

test('a shingle in a scene: light siding is dropped and flagged', () => {
  const r = sampleColor(image((x) => (x < S / 2 ? '#60514c' : '#b8b7b6')), { asphalt: true });
  near(r.hex, '#60514c', 4);
  assert.ok(r.check.includes('scene'), r.check.join());
});

test('a single-color product with a badge takes its largest cluster', () => {
  // 70% gray panel, 30% yellow badge (rows 0-28 of 96 = 30.2%)
  const img = image((x, y) => (y < 29 ? '#d6b057' : '#686c70'));
  const r = sampleColor(img, { single: true });
  near(r.hex, '#686c70', 4);
  assert.ok(r.check.includes('mixed'), r.check.join());
  // without the single rule the mean is pulled toward the badge; the mixed result keeps that mean for re-tuning
  const plain = sampleColor(img);
  assert.ok(!plain.check.includes('mixed'));
  assert.notEqual(plain.hex, r.hex);
  assert.equal(r.mean, plain.hex);
  assert.equal(plain.mean, undefined);
});

test('a white product keeps its light pixels', () => {
  const r = sampleColor(image((x) => (x < S / 2 ? '#e8e8e6' : '#d0d0ce')), { whiteName: true });
  assert.ok(!r.check.includes('scene'));
  near(r.hex, '#dcdcda', 6);
});

test('the result is deterministic', () => {
  const img = image((x, y) => ((x * 7 + y * 13) % 5 === 0 ? '#3c3f43' : (x + y) % 3 ? '#5a4f44' : '#806952'));
  assert.deepEqual(sampleColor(img, { asphalt: true }), sampleColor(img, { asphalt: true }));
  const r = sampleColor(img, { asphalt: true });
  assert.ok(r.palette.length >= 2 && r.palette.length <= 4, r.palette.join());
});

test('name check: the hex agrees with the color name, or is flagged', () => {
  assert.equal(nameCheck('Onyx Black', '#7e7975').ok, false);
  assert.equal(nameCheck('Hickory', '#48332b').ok, true);
  assert.equal(nameCheck('Beige', '#75756d').ok, false); // the Menards cap photo that is a gray part
  assert.equal(nameCheck('Royal Slate', '#384140').ok, true); // no rule for slate
  assert.equal(nameCheck('Red', '#7d3326').ok, true);
  assert.equal(nameCheck('Evergreen', '#1d401f').ok, true);
  assert.equal(nameCheck('Polar White', '#efeded').ok, true);
  assert.equal(nameCheck('Cobra SnowCountry Ridge Vent in Black', '#26272a').ok, true); // word match only
});

test('name rule: color name first, then the product name', () => {
  assert.equal(colorFromName('Charcoal', '12 ft. Drip Edge in White'), '#3c3f43');
  assert.equal(colorFromName(null, '12 ft. Aluminum Matte Black Drip Edge Flashing'), '#26272a');
  assert.equal(colorFromName('Hickory', ''), null);
  assert.equal(colorFromName(null, '8 ft. Corrugated Galvanized Steel 29-Gauge Roof Panel'), '#b5b9bd');
  assert.equal(colorFromName(null, '10 ft. Reddish Brown Panel'), '#5a3f2b'); // "red" is a whole word only
});
