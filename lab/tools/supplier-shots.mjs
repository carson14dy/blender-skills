#!/usr/bin/env node
// Screenshots and in-page checks of the store features (Sioux Falls studio, supplier plan section 11).
//   node lab/tools/supplier-shots.mjs --url "http://127.0.0.1:8080/?quality=standard" --out lab/experiments/017-priced-list/img \
//        [--out016 lab/experiments/016-store-picker-colors/img] [--out022 lab/experiments/022-tap-the-roof/img] [--checks] [--sizes desktop,laptop,phone]
//        [--views picker,colors,list,full,crew,tap,duration,timberline,prorib-close (default), project] [--dark] [--wait 2500]
// Writes <view>-<width>.jpg (quality 80). Picker and roof shots are also copied to --out016, tap shots moved to --out022.
// --checks runs the section 11 rows that need the page (ranch numbers, no hotlinks, crew view has no $,
// project round trip, changed-price notice, Pro-Rib rib spacing) and prints PASS/FAIL per row; exit 1 on a failure.

import fs from 'node:fs';
import path from 'node:path';
import { launch, argParser } from './_playwright.mjs';

const f = argParser();
if (!f.url || f.help) {
  console.log('Usage: node lab/tools/supplier-shots.mjs --url <viewer url> --out <dir> [--out016 <dir>] [--checks] [--sizes desktop,laptop,phone] [--views ...]');
  process.exit(f.help ? 0 : 1);
}
const SIZES = { desktop: { w: 1440, h: 900 }, laptop: { w: 1280, h: 720 }, phone: { w: 390, h: 844, mobile: true } };
const ALL_VIEWS = ['picker', 'colors', 'list', 'full', 'crew', 'tap', 'project', 'duration', 'timberline', 'prorib-close'];
const DEFAULT_VIEWS = ALL_VIEWS.filter((v) => v !== 'project');
const WIDE_ONLY = new Set(['colors', 'duration', 'timberline', 'prorib-close']); // 1440 only
const TO_016 = new Set(['picker', 'colors', 'duration', 'timberline', 'prorib-close']);
const sizes = String(f.sizes || 'desktop,laptop,phone').split(',').filter((s) => SIZES[s]);
const views = String(f.views || DEFAULT_VIEWS.join(',')).split(',').filter((v) => ALL_VIEWS.includes(v));
const out = f.out ? path.resolve(String(f.out)) : null;
const out016 = f.out016 ? path.resolve(String(f.out016)) : null;
const out022 = f.out022 ? path.resolve(String(f.out022)) : null;
const wait = Number(f.wait || 2500);
const results = [];
const record = (check, pass, detail) => { results.push({ check, pass, detail }); console.log(`${pass ? 'PASS' : 'FAIL'}  ${check}: ${detail}`); };

async function open(browser, size) {
  const context = await browser.newContext({
    viewport: { width: size.w, height: size.h }, deviceScaleFactor: size.mobile ? 2 : 1,
    isMobile: !!size.mobile, hasTouch: !!size.mobile, colorScheme: f.dark ? 'dark' : 'light',
  });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(String(f.url), { waitUntil: 'load', timeout: 180000 });
  await page.waitForFunction(() => window.roofStudio, null, { timeout: 180000 });
  await page.evaluate(() => window.roofStudio.ready);
  await page.waitForTimeout(1500); // opening camera move
  return { context, page, errors };
}

const tab = (id) => `document.querySelector('.tab[data-tab="${id}"]').click(); document.querySelector('.tabpanes').scrollTop = 0;`;
// close dialogs and a tap card (Escape also removes its outline from the scene)
const closeDialogs = 'document.querySelectorAll("dialog[open]").forEach((d) => d.close()); document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));';
const VIEW_CODE = {
  picker: `${closeDialogs} roofStudio.setCrewView(false); ${tab('materials')}`,
  colors: `${closeDialogs} roofStudio.setCrewView(false); ${tab('materials')} document.querySelector('#sfChosen .sf-cho').click();`,
  list: `${closeDialogs} roofStudio.setCrewView(false); ${tab('list')}`,
  full: `${closeDialogs} roofStudio.setCrewView(false); ${tab('list')} [...document.querySelectorAll('#sfLBtns button')].find((b) => b.textContent === 'Open full list').click();`,
  crew: `${closeDialogs} ${tab('list')} roofStudio.setCrewView(true);`,
  project: `${closeDialogs} roofStudio.setCrewView(false); ${tab('project')}`,
  duration: `${closeDialogs} roofStudio.setCrewView(false); ${tab('materials')} await roofStudio.storeProduct('mn-1444450489132', 'Sierra Gray');`,
  timberline: `${closeDialogs} ${tab('materials')} await roofStudio.storeProduct('hd-309755006', 'Charcoal');`,
  'prorib-close': `${closeDialogs} ${tab('materials')} await roofStudio.storeProduct('mn-1444448546780', 'Ash Gray');
    const { camera, controls } = roofStudio.three;
    controls.enableDamping = false; camera.position.set(5.2, 4.1, 8.2); controls.target.set(4.2, 3.05, 4.7);
    camera.near = 0.02; camera.updateProjectionMatrix(); controls.update();`,
};

/** A screen point over the roof: the covering's bounding-box centre, projected (page pixels). */
const ROOF_POINT = `(() => {
  const { THREE, scene, camera, renderer } = roofStudio.three;
  const box = new THREE.Box3().setFromObject(scene.getObjectByName('RT_layer_covering'));
  const p = box.getCenter(new THREE.Vector3()).project(camera);
  const r = renderer.domElement.getBoundingClientRect();
  return { x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height };
})()`;

/** Horizontal overflow anywhere that should not scroll sideways. */
const OVERFLOW = `(() => {
  const bad = [];
  const doc = document.documentElement;
  if (doc.scrollWidth > window.innerWidth + 1) bad.push('page ' + doc.scrollWidth + ' > ' + window.innerWidth);
  for (const sel of ['.tabpanes', '#sfFull .sf-fbody', '#sfFull', '.tabs']) {
    const e = document.querySelector(sel);
    if (e && e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1 && !(sel === '#sfFull .sf-fbody' && innerWidth > 760)) bad.push(sel + ' ' + e.scrollWidth + ' > ' + e.clientWidth);
  }
  // text that does not fit its own box (nowrap or overflow hidden)
  for (const e of document.querySelectorAll('.sf *:not(.sf-vh), .tab')) {
    if (e.offsetParent && !e.childElementCount && e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible') bad.push('clipped: ' + (e.id || e.className || e.tagName) + ' "' + e.textContent.slice(0, 40) + '"');
  }
  return bad.slice(0, 8);
})()`;

const { browser, noGpu } = await launch({ software: f.software ? true : undefined });
try {
  if (out) fs.mkdirSync(out, { recursive: true });
  if (out016) fs.mkdirSync(out016, { recursive: true });
  if (out022) fs.mkdirSync(out022, { recursive: true });
  const allErrors = [];
  const overflow = [];
  for (const sz of sizes) {
    const size = SIZES[sz];
    const vs = views.filter((v) => size.w === 1440 || !WIDE_ONLY.has(v));
    if (!vs.length) continue;
    const { context, page, errors } = await open(browser, size);
    for (const v of vs) {
      if (v === 'tap') {
        await page.evaluate(`${closeDialogs} roofStudio.setCrewView(false); ${tab('materials')} roofStudio.settle();`);
        await page.waitForTimeout(wait);
        const pt = await page.evaluate(ROOF_POINT);
        if (size.mobile) await page.touchscreen.tap(pt.x, pt.y); else await page.mouse.click(pt.x, pt.y);
        await page.waitForTimeout(800);
        const card = await page.evaluate(() => document.querySelector('.sf-tap .sf-tap-h')?.textContent || null);
        record(`Tap the roof (${size.mobile ? 'touch' : 'mouse'}, ${size.w})`, !!card, card || 'no card');
      } else {
        await page.evaluate(`(async () => { ${VIEW_CODE[v]} roofStudio.settle(); })()`);
        await page.waitForTimeout(wait);
      }
      const bad = await page.evaluate(OVERFLOW);
      if (bad.length) overflow.push(`${v}-${size.w}: ${bad.join('; ')}`);
      if (out) {
        const file = path.join(out, `${v}-${size.w}.jpg`);
        const t0 = Date.now();
        await page.screenshot({ path: file, type: 'jpeg', quality: 80, timeout: 180000 });
        console.log(`${v}-${size.w} -> ${path.relative(process.cwd(), file)} (${Date.now() - t0} ms)`);
        if (out016 && TO_016.has(v)) fs.copyFileSync(file, path.join(out016, path.basename(file)));
        if (out022 && v === 'tap') fs.renameSync(file, path.join(out022, path.basename(file)));
      }
    }
    allErrors.push(...errors.map((e) => `${sz}: ${e}`));
    await context.close();
  }
  if (views.length) {
    record('No horizontal scroll or clipped text', !overflow.length, overflow.length ? overflow.join(' | ') : `${sizes.join(', ')} × ${views.join(', ')}`);
  }

  if (f.checks) {
    const { context, page, errors } = await open(browser, SIZES.desktop);
    // ranch numbers on the default job
    const t = await page.evaluate(() => {
      const q = roofStudio.quote();
      const r = (s) => q.totals[s];
      return { mn: r('menards-3064').amount, hd: r('homedepot-4301').amount, lo: q.totals.lowest.amount, st: [r('menards-3064').status, r('homedepot-4301').status, q.totals.lowest.status], rebate: r('menards-3064').rebate?.amount,
        cov: q.lines[0].cells['menards-3064'].qty, vent: q.lines.find((l) => l.slot === 'ridgeVent').need.value };
    });
    record('Ranch numbers in the page', t.mn === 6746.27 && t.hd === 6533.59 && t.lo === 6431.38 && t.st.every((s) => s === 'incomplete') && t.rebate === 742.49 && t.cov === 98 && t.vent === 46.75,
      `Menards ${t.mn}, Home Depot ${t.hd}, lowest ${t.lo}, ${t.st.join('/')}, rebate ${t.rebate}, bundles ${t.cov}, ridge vent ${t.vent} ft`);
    // walk every picker slot and the list, then look for store-image requests
    const hot = await page.evaluate(async () => {
      document.querySelector('.tab[data-tab="materials"]').click();
      const sel = document.getElementById('sfSlot');
      for (const o of sel.options) { sel.value = o.value; sel.dispatchEvent(new Event('change')); await new Promise((r) => setTimeout(r, 50)); }
      sel.value = 'covering'; sel.dispatchEvent(new Event('change'));
      document.querySelector('.tab[data-tab="list"]').click();
      [...document.querySelectorAll('#sfLBtns button')].find((b) => b.textContent === 'Open full list').click();
      await new Promise((r) => setTimeout(r, 300));
      document.getElementById('sfFull').close();
      const res = performance.getEntriesByType('resource').filter((r) => /menardc|thdstatic/.test(r.name)).length;
      const imgs = document.querySelectorAll('#storePicker img, #quotePane img, #sfFull img').length;
      return { res, imgs };
    });
    record('No hotlinks in the picker', hot.res === 0 && hot.imgs === 0, `${hot.res} store-image requests, ${hot.imgs} img elements in the picker, list and dialog`);
    // crew view: no price anywhere in the pane or the crew CSV
    const crew = await page.evaluate(async () => {
      roofStudio.setCrewView(true);
      const pane = document.querySelector('#quotePane').textContent;
      const m = await import(new URL('js/quote.js', location.href).href);
      const csv = m.quoteCSV(roofStudio.quote(), { view: 'crew', store: 'menards-3064' });
      const text = roofStudio.listText(true);
      roofStudio.setCrewView(false);
      return { pane: pane.includes('$'), csv: csv.includes('$'), text: text.includes('$'), lines: (pane.match(/measured|allowance/g) || []).length };
    });
    record('Crew view has no prices', !crew.pane && !crew.csv && !crew.text, `$ in pane ${crew.pane}, in crew CSV ${crew.csv}, in crew text ${crew.text}`);
    // project round trip
    const rt = await page.evaluate(async () => {
      const pf = await import(new URL('js/project-file.js', location.href).href);
      await roofStudio.pickStore('ridgeCap', 'mn-1642874276146419', 'Aged Copper');
      roofStudio.three.controls.update();
      const a = roofStudio.project();
      const qa = roofStudio.quote().totals;
      const r = await roofStudio.loadProject(JSON.parse(JSON.stringify(a)));
      const b = roofStudio.project();
      const qb = roofStudio.quote().totals;
      const keys = (p) => JSON.stringify(p).match(/"(image|swatch|dataUrl)"/g) || [];
      return { ok: r.ok, same: pf.sameProject(a, b), totals: [qa['menards-3064'].amount, qb['menards-3064'].amount, qa['homedepot-4301'].amount, qb['homedepot-4301'].amount], heavy: keys(a).length, roof: [a.roof.productId, b.roof.productId, roofStudio.state.product] };
    });
    record('Round trip (Save then Open)', rt.ok && rt.same && rt.totals[0] === rt.totals[1] && rt.totals[2] === rt.totals[3] && rt.heavy === 0,
      `loaded ${rt.ok}, projects equal apart from savedAt ${rt.same}, totals ${rt.totals.join(' / ')}, image keys ${rt.heavy}, roof ${rt.roof[0]} -> ${rt.roof[2]}`);
    // a hand-edited file: one saved price differs, one saved product is gone
    const snap = await page.evaluate(async () => {
      const p = JSON.parse(JSON.stringify(roofStudio.project()));
      p.priceSnapshot.items['mn-1444450489132'].shelf = 44.02;
      p.selections.valley['menards-3064'] = { productId: 'mn-gone-0001', color: null, source: 'chosen' };
      p.valleyMetal = true;
      p.priceSnapshot.items['mn-gone-0001'] = { name: 'Old W valley 10 ft', shelf: 30, per: 'each', startingAt: false, rebate: null, rebateThrough: null, coverage: null, pieceFt: 10, packCount: null };
      await roofStudio.loadProject(p);
      const head = document.getElementById('sfLHead').textContent;
      const q = roofStudio.quote();
      const cov = q.lines[0].cells['menards-3064'];
      const val = q.lines.find((l) => l.slot === 'valley').cells['menards-3064'];
      const before = q.totals['menards-3064'].amount;
      [...document.querySelectorAll('#sfLHead button')].find((b) => b.textContent === 'Use current prices')?.click();
      const after = roofStudio.quote().totals['menards-3064'].amount;
      const change = document.getElementById('sfLHead').textContent;
      return { head, covNote: cov.notes.join('; '), covPrice: cov.unitPrice, valNote: val.notes.join('; '), before, after, change };
    });
    const noticeOk = /Showing prices as saved on .*1 price differs.*1 product is gone/.test(snap.head);
    record('Changed-price notice (hand-edited file)', noticeOk && snap.covPrice === 44.02 && /now \$46\.06 \(\+\$2\.04\)/.test(snap.covNote) && /no longer in the store capture/.test(snap.valNote) && /as saved, .* now/.test(snap.change),
      `"${(snap.head.match(/Showing prices[^.]*\.[^.]*\./) || [''])[0]}"; cell: ${snap.covNote}; gone: ${snap.valNote}; Menards ${snap.before} -> ${snap.after} after "Use current prices"`);
    // tap vs drag: a short press opens the card, a drag orbits and opens nothing
    await page.evaluate(`${closeDialogs} roofStudio.storeProduct('mn-1444450489132', 'Sierra Gray').then(() => roofStudio.settle())`);
    await page.waitForTimeout(2500);
    const pt = await page.evaluate(ROOF_POINT);
    const cam0 = await page.evaluate(() => roofStudio.three.camera.position.toArray());
    await page.mouse.move(pt.x, pt.y); await page.mouse.down(); await page.mouse.move(pt.x + 60, pt.y + 10, { steps: 6 }); await page.mouse.move(pt.x + 120, pt.y + 20, { steps: 6 }); await page.mouse.up();
    await page.waitForTimeout(600);
    const afterDrag = await page.evaluate(() => ({ cam: roofStudio.three.camera.position.toArray(), card: !!document.querySelector('.sf-tap') }));
    const moved = Math.hypot(...afterDrag.cam.map((c, i) => c - cam0[i]));
    await page.waitForTimeout(1500);
    const pt2 = await page.evaluate(ROOF_POINT);
    await page.mouse.click(pt2.x, pt2.y);
    await page.waitForTimeout(500);
    const tapCard = await page.evaluate(() => document.querySelector('.sf-tap .sf-tap-h')?.textContent || null);
    await page.keyboard.press('Escape');
    const closed = await page.evaluate(() => !document.querySelector('.sf-tap'));
    record('Tap the roof: drag still orbits', moved > 0.5 && !afterDrag.card && !!tapCard && closed, `drag moved the camera ${moved.toFixed(2)} m and opened no card; a click opened "${tapCard}"; Escape closed it ${closed}`);
    // Pro-Rib: ribs every 9 in. on the roof
    const rib = await page.evaluate(async () => {
      await roofStudio.storeProduct('mn-1444448546780', 'Ash Gray');
      const mesh = roofStudio.three.scene.getObjectByName('RT_layer_covering');
      const m = mesh.material;
      const set = m.userData.texSet;
      return { tileM: 1 / m.map.repeat.x, ribs: set.ribsPerTile, ribM: set.ribSpacingM, metal: m.metalness, rough: m.roughness };
    });
    const want = 36 * 0.0254;
    record('Pro-Rib ribs repeat at 9 in.', Math.abs(rib.tileM - want) < 1e-6 && rib.ribs === 4,
      `tile ${rib.tileM.toFixed(4)} m (36 in. = ${want.toFixed(4)} m), ${rib.ribs} ribs per tile = ${(rib.tileM / rib.ribs / 0.0254).toFixed(2)} in. on centre; metalness ${rib.metal}, roughness ${rib.rough.toFixed(2)}`);
    // corrugated (Home Depot) and Pro-Snap (Menards): texture tile = 8 pitches of 2.67 in.; two 16 in. panels per tile
    const prof = await page.evaluate(async () => {
      const tile = async (id) => {
        await roofStudio.storeProduct(id);
        const m = roofStudio.three.scene.getObjectByName('RT_layer_covering').material;
        return { tileM: 1 / m.map.repeat.x, set: { pitchM: m.userData.texSet.pitchM ?? null, sizeM: m.userData.texSet.sizeM } };
      };
      const corr = await tile('hd-338539708');
      const snap = await tile('mn-4283774896157214');
      await roofStudio.storeProduct('mn-1444450489132', 'Sierra Gray');
      return { corr, snap };
    });
    record('Corrugated and Pro-Snap repeat', Math.abs(prof.corr.tileM - 8 * 2.67 * 0.0254) < 1e-6 && Math.abs(prof.snap.tileM - 32 * 0.0254) < 1e-6,
      `corrugated tile ${(prof.corr.tileM / 0.0254).toFixed(2)} in. = 8 × ${(prof.corr.set.pitchM / 0.0254).toFixed(2)} in.; Pro-Snap tile ${(prof.snap.tileM / 0.0254).toFixed(2)} in. = 2 panels, seams every ${(prof.snap.tileM / 2 / 0.0254).toFixed(2)} in.`);
    allErrors.push(...errors.map((e) => `checks: ${e}`));
    await context.close();
  }
  record('Console', allErrors.length === 0, allErrors.length ? allErrors.slice(0, 10).join(' | ') : '0 errors');
  console.log(`WebGL: ${noGpu ? 'software' : 'GPU'}`);
} finally {
  await browser.close();
}
process.exit(results.every((r) => r.pass) ? 0 : 1);
