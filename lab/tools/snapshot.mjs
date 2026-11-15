#!/usr/bin/env node
// High-resolution snapshot from the web viewer (tiled raster or path traced), with timing.
//   node lab/tools/snapshot.mjs --url http://127.0.0.1:8080/ --size 3840x2160 --explode --out out/roof-4k.png
//   node lab/tools/snapshot.mjs --url http://127.0.0.1:8080/ --size 1920x1080 --pt 128 --product arch-weathered --out out/pt.png
// Options: --product <catalog id> --explode --cutaway --t 0.6 (build position 0..1) --pt <samples> --software

import fs from 'node:fs';
import path from 'node:path';
import { launch, openViewer, argParser } from './_playwright.mjs';

const f = argParser();
if (!f.url || !f.out || f.help) {
  console.log('Usage: node lab/tools/snapshot.mjs --url <viewer url> --size 3840x2160 --out <file.png> [--explode] [--cutaway] [--t 0.6] [--pt 128] [--product id]');
  process.exit(f.help ? 0 : 1);
}
const [w, h] = String(f.size || '3840x2160').split('x').map(Number);
const u = new URL(String(f.url));
u.searchParams.set('capture', '1');
if (f.product) u.searchParams.set('product', String(f.product));
const { browser, noGpu } = await launch({ software: f.software ? true : undefined });
try {
  const { page, errors, readyMs } = await openViewer(browser, u.href, { width: 1400, height: 860 });
  console.log(`ready in ${readyMs} ms${noGpu ? ' (software WebGL, slow)' : ''}`);
  const t0 = Date.now();
  const b64 = await page.evaluate(async ({ w, h, explode, cutaway, t, pt }) => {
    const S = window.roofStudio;
    if (t !== undefined) S.seek(Number(t));
    S.explode(!!explode); S.cutaway(!!cutaway); S.settle();
    if (pt) { await S.pathTrace(true); document.getElementById('rSamples').value = String(pt); }
    const url = await S.snapshot(w, h);
    const buf = new Uint8Array(await (await fetch(url)).arrayBuffer());
    let s = '';
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return btoa(s);
  }, { w, h, explode: f.explode, cutaway: f.cutaway, t: f.t, pt: f.pt ? Number(f.pt) : 0 });
  const out = path.resolve(String(f.out));
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, Buffer.from(b64, 'base64'));
  console.log(`${w}x${h}${f.pt ? `, ${f.pt} samples path traced` : ''} -> ${out} in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  if (errors.length) console.log(`console errors:\n  ${errors.slice(0, 20).join('\n  ')}`);
} finally {
  await browser.close();
}
