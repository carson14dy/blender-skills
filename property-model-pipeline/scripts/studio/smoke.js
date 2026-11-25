// Studio smoke run (headless Chromium, desktop + phone): open the site, open one measured house, report what the
// page shows. It only observes; smoke.py decides pass / fail against the report.
//   node smoke.js --url http://127.0.0.1:8766/index.html --house SLUG [--out DIR] [--timeout MS]
// Prints one JSON object: {viewports: {desktop: {...}, phone: {...}}}.
const path = require('path');

function parse(argv) {
  const a = { timeout: 240000, out: null };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--url') a.url = argv[++i];
    else if (k === '--house') a.house = argv[++i];
    else if (k === '--out') a.out = argv[++i];
    else if (k === '--timeout') a.timeout = Number(argv[++i]);
  }
  return a;
}

const MEDIA_SEL = 'video, [data-splat], .splat-view, canvas.splat';

async function mediaState(p, timeout) {
  // every <video> and splat element: visible ones must load, hidden ones are fine
  const t0 = Date.now();
  let last = [];
  while (Date.now() - t0 < timeout) {
    last = await p.evaluate((sel) => [...document.querySelectorAll(sel)].map((el) => {
      const cs = getComputedStyle(el);
      const hidden = el.hidden || cs.display === 'none' || cs.visibility === 'hidden' || el.closest('[hidden]') !== null ||
        (el.offsetParent === null && cs.position !== 'fixed');
      const kind = el.tagName === 'VIDEO' ? 'video' : 'splat';
      let state;
      if (kind === 'video') state = el.error ? 'error' : el.readyState >= 1 ? 'loaded' : 'loading';
      else state = (el.dataset.state || 'unknown').toLowerCase();
      return { kind, hidden, state, src: el.currentSrc || el.getAttribute('src') || el.dataset.src || '' };
    }), MEDIA_SEL);
    const pending = last.filter((m) => !m.hidden && (m.state === 'loading' || m.state === 'unknown'));
    if (!pending.length) break;
    await p.waitForTimeout(500);
  }
  return last;
}

async function runViewport(browser, name, opts, a) {
  const r = { errors: [], console_errors: [], steps: [] };
  const ctx = await browser.newContext(opts);
  const p = await ctx.newPage();
  p.on('pageerror', (e) => r.errors.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error') r.console_errors.push(m.text()); });
  const step = async (label, fn) => {
    try { await fn(); r.steps.push(label); return true; } catch (e) {
      r.failed_step = label; r.step_error = e.message.split('\n')[0]; return false;
    }
  };
  try {
    if (!await step('load', async () => {
      await p.goto(a.url, { waitUntil: 'load', timeout: a.timeout });
      await p.waitForFunction(() => window.roofStudio && document.getElementById('loading') && document.getElementById('loading').hidden,
        null, { timeout: a.timeout });
      await p.waitForTimeout(800);
    })) return r;
    r.squares_before = await p.evaluate(() => { const m = window.roofStudio.state.measure; return m ? +m.squares : null; });
    if (!await step('project tab', async () => {
      await p.click('.tab[data-tab="project"]');
      await p.waitForTimeout(300);
    })) return r;
    const sel = `.measured-card[data-id="${a.house}"]`;
    r.cards = await p.$$eval('.measured-card', (cs) => cs.map((c) => c.dataset.id));
    r.card_found = r.cards.includes(a.house);
    if (!r.card_found) return r;
    r.card_rows = await p.$$eval(`${sel} .mc-table tr`, (trs) => trs.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent)));
    r.card_label = await p.$eval(`${sel} .mc-head b`, (b) => b.textContent);
    r.thumb_ok = await p.evaluate((s) => {
      const img = document.querySelector(`${s} .mc-thumb img`);
      return img ? (img.closest('[hidden]') ? 'hidden' : (img.complete && img.naturalWidth > 0 ? 'loaded' : 'broken')) : 'none';
    }, sel);
    if (!await step('open house', async () => {
      await p.locator(`${sel} .row button`).click();
      await p.waitForFunction((id) => document.getElementById('pHouse').value === `m:${id}`, a.house, { timeout: a.timeout });
      await p.waitForFunction(() => document.getElementById('loading').hidden, null, { timeout: a.timeout });
      await p.waitForTimeout(2500);
    })) return r;
    r.selected = await p.evaluate(() => document.getElementById('pHouse').value);
    r.measure = await p.evaluate(() => {
      const m = window.roofStudio.state.measure;
      return m ? { squares: +m.squares, areaM2: m.areaM2, planes: m.planes ?? null, eaveM: m.eaveM, rakeM: m.rakeM } : null;
    });
    r.toast = await p.evaluate(() => { const t = document.getElementById('toast'); return t ? t.innerText : ''; });
    r.media = await mediaState(p, 30000);
    if (a.out) await p.screenshot({ path: path.join(a.out, `smoke_${name}.png`) });
  } finally {
    await ctx.close();
  }
  return r;
}

(async () => {
  const a = parse(process.argv.slice(2));
  let pw;
  try { pw = require('playwright'); } catch (e) {
    console.log(JSON.stringify({ tooling: true, error: 'playwright not found: ' + e.message }));
    process.exit(3);
  }
  const { chromium, devices } = pw;
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const out = { viewports: {} };
  try {
    for (const [name, opts] of [['desktop', { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }],
      ['phone', devices['iPhone 13']]]) {
      out.viewports[name] = await runViewport(browser, name, opts, a);
    }
  } catch (e) {
    out.error = e.message.split('\n')[0];
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(out));
})();
