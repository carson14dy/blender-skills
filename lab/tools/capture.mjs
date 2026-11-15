#!/usr/bin/env node
// Screenshots of the web viewer in named states, for experiment write-ups.
//   node lab/tools/capture.mjs --url "http://127.0.0.1:8080/?quality=standard" \
//        --shots finished,layers,cutaway,midbuild,before --out lab/experiments/NNN/img
// Options: --width 1400 --height 860 --dark --software (force CPU WebGL) --png --wait 2000
//          --eval "roofStudio.setProduct('seam-red')"   (runs once before the shots)

import fs from 'node:fs';
import path from 'node:path';
import { launch, openViewer, argParser } from './_playwright.mjs';

const f = argParser();
if (!f.url || f.help) {
  console.log('Usage: node lab/tools/capture.mjs --url <viewer url> --shots finished,layers,cutaway,midbuild,before --out <dir>');
  process.exit(f.help ? 0 : 1);
}

const SHOTS = {
  finished: 'roofStudio.explode(false); roofStudio.cutaway(false); roofStudio.seek(1)',
  layers: 'roofStudio.cutaway(false); roofStudio.seek(1); roofStudio.explode(true)',
  cutaway: 'roofStudio.explode(false); roofStudio.seek(1); roofStudio.cutaway(true)',
  midbuild: 'roofStudio.explode(false); roofStudio.cutaway(false); roofStudio.seek(0.62)',
  tearoff: 'roofStudio.explode(false); roofStudio.cutaway(false); roofStudio.seek(0.12)',
  before: 'roofStudio.explode(false); roofStudio.cutaway(false); roofStudio.seek(0)',
};

const out = path.resolve(String(f.out || 'out/captures'));
fs.mkdirSync(out, { recursive: true });
const shots = String(f.shots || 'finished,layers').split(',').map((s) => s.trim()).filter(Boolean);
const { browser, noGpu } = await launch({ software: f.software ? true : undefined });
try {
  const { page, errors, readyMs } = await openViewer(browser, String(f.url), { width: Number(f.width || 1400), height: Number(f.height || 860), colorScheme: f.dark ? 'dark' : 'light' });
  console.log(`ready in ${readyMs} ms${noGpu ? ' (software WebGL)' : ''}`);
  if (f.eval) await page.evaluate(String(f.eval));
  for (const s of shots) {
    const code = SHOTS[s];
    if (!code) { console.log(`skip unknown shot "${s}" (known: ${Object.keys(SHOTS).join(', ')})`); continue; }
    await page.evaluate(`${code}; roofStudio.settle();`);
    await page.waitForTimeout(Number(f.wait || 2000));
    const file = path.join(out, `${s}.${f.png ? 'png' : 'jpg'}`);
    const t0 = Date.now();
    await page.screenshot({ path: file, timeout: 180000, ...(f.png ? {} : { type: 'jpeg', quality: 85 }) });
    console.log(`${s} -> ${path.relative(process.cwd(), file)} (${Date.now() - t0} ms)`);
  }
  if (errors.length) console.log(`console errors:\n  ${errors.slice(0, 20).join('\n  ')}`);
} finally {
  await browser.close();
}
