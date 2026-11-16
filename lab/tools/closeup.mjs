#!/usr/bin/env node
// Close-up screenshots of roof details in the web viewer (ridge end, hip foot), for geometry checks.
//   node lab/tools/closeup.mjs --url "http://127.0.0.1:8080/?quality=standard" --out lab/experiments/NNN/img/web
// Writes <out>-ridge.jpg and <out>-hip.jpg. Options: --software, --wait 2500
import fs from 'node:fs';
import path from 'node:path';
import { launch, openViewer, argParser } from './_playwright.mjs';

const f = argParser();
if (!f.url || !f.out) { console.log('Usage: node lab/tools/closeup.mjs --url <viewer url> --out <path prefix>'); process.exit(1); }
const VIEWS = {
  ridge: { pos: [4.9, 5.45, 2.2], target: [2.6, 5.25, 0] }, // end of the main ridge, where the hips start
  hip: { pos: [9.8, 2.95, -7.3], target: [8.0, 2.45, -5.5] }, // foot of a hip at the back corner
};
const { browser } = await launch({ software: f.software ? true : undefined });
try {
  const { page, gpu } = await openViewer(browser, String(f.url), { width: 900, height: 560 });
  console.log(`WebGL renderer: ${gpu}`);
  await page.evaluate('roofStudio.explode(false); roofStudio.cutaway(false); roofStudio.seek(1); roofStudio.settle()');
  await page.waitForTimeout(3000); // let the opening camera move finish before taking over the camera
  fs.mkdirSync(path.dirname(path.resolve(String(f.out))), { recursive: true });
  for (const [name, v] of Object.entries(VIEWS)) {
    await page.evaluate(({ pos, target }) => {
      const { camera, controls } = window.roofStudio.three;
      controls.enableDamping = false;
      camera.position.set(...pos); controls.target.set(...target); camera.near = 0.02; camera.updateProjectionMatrix(); controls.update();
      window.roofStudio.settle();
    }, v);
    await page.waitForTimeout(Number(f.wait || 2500));
    const file = `${path.resolve(String(f.out))}-${name}.jpg`;
    await page.screenshot({ path: file, type: 'jpeg', quality: 85, timeout: 180000 });
    console.log(`${name} -> ${path.relative(process.cwd(), file)}`);
  }
} finally {
  await browser.close();
}
