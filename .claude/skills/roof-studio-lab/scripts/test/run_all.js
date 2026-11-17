// End-to-end check of the Roof Studio Lab page in headless Chromium (SwiftShader, no real GPU).
// node run_all.js [part]   parts: tabs, lab, wasm, phone, dark, webgpu, iframe (default: all)
const fs = require('fs');
const { open, errors } = require('./lib');
// LAB_URL: where serve.py runs; LAB_TEST_OUT: results and screenshots (default ./lab-test-output);
// LAB_HOUSE: the measured house id from houses/index.json that the Lab tools use.
const path = require('path');
const BASE = process.env.LAB_URL || 'http://127.0.0.1:8765';
const DIR = process.env.LAB_TEST_OUT || path.join(process.cwd(), 'lab-test-output');
const OUT = DIR + '/results';
const SH = DIR + '/shots';
fs.mkdirSync(SH, { recursive: true });
const HOUSE = process.env.LAB_HOUSE || '1601-s-discovery-ave';
fs.mkdirSync(OUT, { recursive: true });
const save = (n, o) => fs.writeFileSync(`${OUT}/${n}.json`, JSON.stringify(o, null, 1));
const only = process.argv[2];
const want = (p) => !only || only.split(',').includes(p);

async function tabs() {
  const { browser, page, logs, readyMs } = await open({ url: `${BASE}/?measured=${HOUSE}` });
  page.setDefaultTimeout(240000);
  const out = { readyMs, tabs: {} };
  for (const t of ['materials', 'layers', 'list', 'build', 'render', 'project', 'lab']) {
    await page.click(`.tab[data-tab="${t}"]`);
    await page.waitForTimeout(400);
    out.tabs[t] = await page.evaluate((t) => { const p = document.querySelector(`.pane[data-pane="${t}"]`); return { visible: !p.hidden, text: p.innerText.length, controls: p.querySelectorAll('button,input,select').length }; }, t);
    await page.screenshot({ path: `${SH}/tab-${t}.png` });
  }
  // toolbar: layers view, cutaway, before, build playback, tap
  await page.click('#tbExplode'); await page.waitForTimeout(1500); await page.screenshot({ path: `${SH}/tool-explode.png` });
  await page.click('#tbExplode'); await page.click('#tbCut'); await page.waitForTimeout(1500); await page.screenshot({ path: `${SH}/tool-cutaway.png` });
  await page.click('#tbCut'); await page.click('#tbBefore'); await page.waitForTimeout(1000); await page.screenshot({ path: `${SH}/tool-before.png` });
  await page.click('#tbBefore');
  out.build = await page.evaluate(async () => { const s = window.roofStudio; s.seek(0.4); await new Promise((r) => setTimeout(r, 300)); const st = s.state; s.seek(1); return { t: st.t, duration: st.duration, layers: st.layers.length }; });
  // product change, layer option, takeoff present
  out.product = await page.evaluate(async () => { const before = window.roofStudio.state.product; await window.roofStudio.setProduct('arch-charcoal'); return { before, after: window.roofStudio.state.product }; });
  out.takeoffRows = await page.evaluate(() => document.querySelectorAll('#takeoff tr').length);
  // snapshot (small), GLB export button state
  out.snapshot = await page.evaluate(async () => { const u = await window.roofStudio.snapshot(640, 360); document.getElementById('dlgSnap').close(); return !!u; });
  out.glbButtonDisabled = await page.evaluate(() => document.getElementById('btnGlb').disabled);
  // switch to a preset and back to the measured house
  await page.click('.tab[data-tab="project"]');
  await page.selectOption('#pHouse', 'ranch-hip'); await page.waitForTimeout(1500);
  out.preset = await page.evaluate(() => window.roofStudio.state.measure.squares);
  await page.selectOption('#pHouse', `m:${HOUSE}`); await page.waitForTimeout(3000);
  out.measured = await page.evaluate(() => window.roofStudio.state.measure.squares);
  out.errors = errors(logs); out.logs = logs.slice(0, 60);
  save('tabs', out); console.log('tabs', JSON.stringify({ readyMs, errors: out.errors, snap: out.snapshot, preset: out.preset, measured: out.measured }));
  await browser.close();
}

async function lab(path = '', name = 'lab') {
  const { browser, page, logs, readyMs } = await open({ url: `${BASE}${path}/?measured=${HOUSE}&tab=lab`, width: 1280, height: 800 });
  page.setDefaultTimeout(300000);
  const res = { readyMs };
  for (const k of ['mvTest', 'compareTest', 'tilesTest', 'splatTest']) {
    const t0 = Date.now();
    res[k] = await page.evaluate(async (k) => { try { return await window.roofStudio.lab.tests[k](); } catch (e) { return { error: e.message }; } }, k);
    res[k + 'WallMs'] = Date.now() - t0;
    const sec = { mvTest: 'lab-modelViewer', compareTest: 'lab-webgpu', tilesTest: 'lab-tiles', splatTest: 'lab-splat' }[k];
    await page.evaluate((id) => document.getElementById(id).scrollIntoView(), sec);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${SH}/${name}-${k}.png`, timeout: 240000 });
    if (k === 'compareTest') await page.evaluate(() => window.roofStudio.lab.tests.compareToggle(false));
    console.log(name, k, 'done in', res[k + 'WallMs'], 'ms', res[k]?.error || '');
  }
  res.resultsJson = await page.evaluate(() => window.roofStudio.lab.results);
  // a wide view with tiles + splats on, after the sort settles
  await page.evaluate(() => { const { camera, controls } = window.roofStudio.three; camera.position.set(45, 38, 75); controls.target.set(0, 2, 0); controls.update(); window.roofStudio.lab.invalidate(2000); });
  await page.waitForTimeout(25000);
  await page.evaluate(() => window.roofStudio.lab.invalidate(800));
  await page.waitForTimeout(6000);
  await page.screenshot({ path: `${SH}/${name}-context.png`, timeout: 240000 });
  res.errors = errors(logs); res.logs = logs.filter((l) => !/Merged metalnessMap/.test(l)).slice(0, 80);
  save(name, res); console.log(name, 'errors', JSON.stringify(res.errors));
  await browser.close();
}

async function phone(scheme) {
  const { browser, page, logs } = await open({ url: `${BASE}/wasm/?measured=${HOUSE}&tab=lab`, width: 390, height: 844, mobile: true, scheme });
  page.setDefaultTimeout(300000);
  await page.screenshot({ path: `${SH}/phone-${scheme}-lab.png` });
  const tabs = await page.evaluate(() => [...document.querySelectorAll('.tab')].map((t) => ({ t: t.textContent, w: t.getBoundingClientRect().width, clipped: t.scrollWidth > t.clientWidth })));
  const hscroll = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  // the studio's phone drawer: tap the handle to hide, tap again to show
  let drawer = null;
  if (await page.$('#sheetHandle')) {
    await page.click('#sheetHandle'); await page.waitForTimeout(500);
    const hidden = await page.evaluate(() => document.getElementById('panel').classList.contains('collapsed'));
    await page.screenshot({ path: `${SH}/phone-${scheme}-drawer-hidden.png` });
    await page.click('#sheetHandle'); await page.waitForTimeout(500);
    const shown = await page.evaluate(() => !document.getElementById('panel').classList.contains('collapsed'));
    drawer = { hidden, shown };
  }
  await page.evaluate(async () => { await window.roofStudio.lab.tests.tilesToggle(true); document.getElementById('tlOn').checked = true; await window.roofStudio.lab.tests.splatToggle(true); document.getElementById('spOn').checked = true; });
  await page.evaluate(() => { const { camera, controls } = window.roofStudio.three; camera.position.set(40, 45, 70); controls.target.set(0, 2, 0); controls.update(); window.roofStudio.lab.invalidate(2000); });
  await page.waitForTimeout(25000);
  await page.evaluate(() => window.roofStudio.lab.invalidate(800));
  await page.waitForTimeout(5000);
  await page.screenshot({ path: `${SH}/phone-${scheme}-context.png`, timeout: 240000 });
  await page.evaluate(() => document.getElementById('lab-tiles').scrollIntoView());
  await page.screenshot({ path: `${SH}/phone-${scheme}-tiles.png`, timeout: 240000 });
  await page.click('.tab[data-tab="materials"]'); await page.waitForTimeout(500);
  await page.screenshot({ path: `${SH}/phone-${scheme}-materials.png`, timeout: 240000 });
  const out = { tabs, hscroll, drawer, errors: errors(logs) };
  save(`phone-${scheme}`, out); console.log('phone', scheme, JSON.stringify(out));
  await browser.close();
}

async function dark() {
  const { browser, page, logs } = await open({ url: `${BASE}/?measured=${HOUSE}&tab=lab`, scheme: 'dark' });
  page.setDefaultTimeout(300000);
  await page.evaluate(async () => { document.getElementById('tlOn').checked = true; await window.roofStudio.lab.tests.tilesToggle(true); });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: `${SH}/desktop-dark-lab.png` });
  await page.evaluate(() => { document.querySelectorAll('#labPane details').forEach((d) => { d.open = true; }); document.getElementById('lab-tiles').scrollIntoView(); });
  await page.screenshot({ path: `${SH}/desktop-dark-findings.png` });
  save('dark', { errors: errors(logs) }); console.log('dark', JSON.stringify(errors(logs)));
  await browser.close();
}

async function webgpu() {
  const { browser, page, logs } = await open({ url: `${BASE}/?measured=${HOUSE}&tab=lab&quality=standard`, width: 1100, height: 700, webgpu: true });
  page.setDefaultTimeout(300000);
  const r = await page.evaluate(async () => { try { return await window.roofStudio.lab.tests.compareTest(); } catch (e) { return { error: e.message, partial: window.roofStudio.lab.results.webgpu }; } });
  await page.waitForTimeout(1500);
  await page.evaluate(() => document.getElementById('lab-webgpu').scrollIntoView());
  await page.screenshot({ path: `${SH}/webgpu-swiftshader.png`, timeout: 240000 });
  save('webgpu-swiftshader', { r, errors: errors(logs), logs: logs.slice(0, 40) }); console.log('webgpu', JSON.stringify(r).slice(0, 600));
  await browser.close();
}

(async () => {
  if (want('tabs')) await tabs();
  if (want('lab')) await lab('', 'lab');
  if (want('wasm')) await lab('/wasm', 'lab-wasm');
  if (want('phone')) { await phone('light'); await phone('dark'); }
  if (want('dark')) await dark();
  if (want('webgpu')) await webgpu();
})().catch((e) => { console.error(e); process.exit(1); });
