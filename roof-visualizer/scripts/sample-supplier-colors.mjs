#!/usr/bin/env node
// Sample a color for each store product from its swatch or product photo (lab experiment 016).
//
//   node roof-visualizer/scripts/sample-supplier-colors.mjs [--limit N] [--only menards|homedepot] [--match <regex>]
//        [--refresh | --recheck <check|error>] [--scratch <dir>]
//       downloads the images the catalog links to, one request at a time and 1 s apart per host, and writes the
//       color cache scripts/data/supplier-colors.json. A URL already in the cache is skipped unless --refresh.
//   node roof-visualizer/scripts/sample-supplier-colors.mjs --sheet lab/experiments/016-store-picker-colors/img/chips.jpg
//       draws a contact sheet of flat color chips with names from the built catalog (no downloads, no store images).
//
// Order: build the catalog, sample, build again (it merges the cache), then draw the sheet.
// Rules: honest user-agent, no cookies, no referer; stop a host on 403 or 429 and never work around a refusal;
// image bytes stay in memory (with --scratch they go to that folder, which is deleted at exit).
import fs from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { colorJobs, listedColor, COLOR_LAYERS } from './lib/supplier-catalog.mjs';
import { sampleColor, nameCheck, WHITE_NAME, LIGHT_NEUTRAL_LUMA, MIXED_SPREAD } from './lib/swatch-color.mjs';

// Behind an HTTPS proxy (cloud sessions) Node's fetch needs --use-env-proxy; restart with it once.
if ((process.env.HTTPS_PROXY || process.env.https_proxy) && !process.execArgv.includes('--use-env-proxy') && !process.env.NODE_USE_ENV_PROXY) {
  const r = spawnSync(process.execPath, ['--use-env-proxy', '--disable-warning=UNDICI-EHPA', ...process.execArgv, fileURLToPath(import.meta.url), ...process.argv.slice(2)], { stdio: 'inherit' });
  process.exit(r.status ?? 1);
}

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const arg = (k) => { const i = args.indexOf(`--${k}`); return i >= 0 ? args[i + 1] : null; };
const has = (k) => args.includes(`--${k}`);
const CATALOG = arg('catalog') || path.join(here, '..', 'viewer', 'catalog', 'suppliers', 'sioux-falls.json');
const CACHE = arg('cache') || path.join(here, 'data', 'supplier-colors.json');
const UA = 'roof-lab-color-sampler/1.0 (internal color reference)';
const MAX_BYTES = 4 * 1024 * 1024, TIMEOUT_MS = 20000, GAP_MS = 1000, RETRY_MS = 5000, SIDE = 96;
const today = new Date().toISOString().slice(0, 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const catalog = JSON.parse(fs.readFileSync(CATALOG, 'utf8'));

/** Keys sorted at every level, 1-space indent: later diffs stay small. */
const sorted = (v) => (Array.isArray(v) ? v.map(sorted) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v);
const writeCache = (cache) => { fs.mkdirSync(path.dirname(CACHE), { recursive: true }); fs.writeFileSync(CACHE, JSON.stringify(sorted(cache), null, 1) + '\n'); };

/** Smaller downloads: Home Depot product photos come in a 300 px size. */
const fetchUrl = (u) => (/thdstatic\.com\/productImages\//.test(u) ? u.replace(/_1000\.jpg$/, '_300.jpg') : u);

/** Statistic flags for one image, from the product that links to it (section 5.4). */
function flagsFor(p, job) {
  return {
    asphalt: p.category === 'shingle' || p.kind === 'shingleCap',
    single: p.category === 'metal' || ['dripEdge', 'valley', 'ridgeVent'].includes(p.layer) || p.kind === 'metalCap',
    // the product name names the listed color only, not the other variants
    whiteName: WHITE_NAME.test(job.name || '') || (job.listed && WHITE_NAME.test(p.name)),
  };
}

/** Image bytes -> 96 x 96 RGB through ffmpeg; the aspect ratio is not kept (it does not change a color statistic). */
function decode(bytes) {
  return new Promise((resolve) => {
    const ff = spawn('ffmpeg', ['-v', 'error', '-i', 'pipe:0', '-frames:v', '1', '-vf', `scale=${SIDE}:${SIDE}:flags=area`, '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']);
    const out = [], err = [];
    ff.stdout.on('data', (d) => out.push(d));
    ff.stderr.on('data', (d) => err.push(d));
    ff.stdin.on('error', () => {}); // ffmpeg may close stdin early on a bad file
    ff.on('close', () => {
      const buf = Buffer.concat(out);
      if (buf.length === SIDE * SIDE * 3) resolve({ rgb: new Uint8Array(buf) });
      else resolve({ error: `decode failed: ${(Buffer.concat(err).toString().split('\n')[0] || `${buf.length} bytes`).slice(0, 120)}` });
    });
    ff.stdin.end(bytes);
  });
}

/** One GET. Returns { bytes } | { refused: status } | { retry: why } | { error: why }. */
async function get(url) {
  let res;
  try {
    res = await fetch(url, { headers: { 'user-agent': UA }, redirect: 'follow', signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (e) {
    const why = `${e.name === 'TimeoutError' ? 'timeout' : e.message}${e.cause?.message ? `: ${e.cause.message}` : ''}`;
    if (/\b(403|407|429)\b/.test(why)) return { refused: why }; // the proxy or the store said no
    return { retry: why.slice(0, 160) };
  }
  if (res.status === 403 || res.status === 429) { res.body?.cancel().catch(() => {}); return { refused: `HTTP ${res.status}` }; }
  if (res.status >= 500) { res.body?.cancel().catch(() => {}); return { retry: `HTTP ${res.status}` }; }
  if (!res.ok) { res.body?.cancel().catch(() => {}); return { error: `HTTP ${res.status}` }; }
  if (Number(res.headers.get('content-length')) > MAX_BYTES) { res.body?.cancel().catch(() => {}); return { error: 'too large' }; }
  const chunks = [];
  let n = 0;
  try {
    for await (const c of res.body) {
      n += c.length;
      if (n > MAX_BYTES) { return { error: 'too large' }; }
      chunks.push(c);
    }
  } catch (e) { return { retry: e.name === 'TimeoutError' ? 'timeout' : e.message.slice(0, 160) }; }
  return { bytes: Buffer.concat(chunks) };
}

async function sample() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) { console.error('ffmpeg not found: install it (node lab/tools/doctor.mjs lists it).'); process.exit(1); }
  const cache = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, 'utf8')) : {};
  const only = arg('only'), match = arg('match') ? new RegExp(arg('match'), 'i') : null, limit = Number(arg('limit')) || Infinity;
  const scratch = arg('scratch');
  if (scratch) fs.mkdirSync(scratch, { recursive: true });
  const cleanup = () => { if (scratch && fs.existsSync(scratch)) fs.rmSync(scratch, { recursive: true, force: true }); };
  process.on('SIGINT', () => { writeCache(cache); cleanup(); console.log('\nInterrupted: cache written.'); process.exit(130); });

  // one job per URL: the first product that links to it sets the flags
  const jobs = new Map();
  for (const p of catalog.products) {
    if (only && !p.store.startsWith(only)) continue;
    for (const j of colorJobs(p)) if (!jobs.has(j.url) && (!match || match.test(j.url) || match.test(p.id))) jobs.set(j.url, { ...j, product: p, flags: flagsFor(p, j) });
  }
  // --recheck <check|error>: sample again only the images whose cache entry has that check (e.g. mixed) or an error
  const recheck = arg('recheck');
  const todo = [...jobs.values()].filter((j) => (recheck ? (recheck === 'error' ? cache[j.url]?.error : cache[j.url]?.check?.includes(recheck)) : has('refresh') || !cache[j.url]));
  const cached = jobs.size - todo.length;
  const queues = new Map(); // host -> jobs, taken in turn so one host's gap is another's request
  for (const j of todo.slice(0, limit)) { const h = new URL(fetchUrl(j.url)).host; if (!queues.has(h)) queues.set(h, []); queues.get(h).push(j); }
  const total = [...queues.values()].reduce((s, q) => s + q.length, 0);
  console.log(`${jobs.size} images linked; ${cached} already in the cache; ${total} to fetch from ${[...queues.keys()].join(', ') || 'no host'}`);
  console.log(`statistic: light-neutral luma ${LIGHT_NEUTRAL_LUMA.asphalt} (asphalt) / ${LIGHT_NEUTRAL_LUMA.other}, mixed spread ${MIXED_SPREAD}`);

  const ready = new Map([...queues.keys()].map((h) => [h, 0]));
  const stopped = new Map();
  let done = 0, sampledN = 0, failed = 0, flagged = 0;
  while ([...queues.values()].some((q) => q.length)) {
    const host = [...queues.keys()].filter((h) => queues.get(h).length).sort((a, b) => ready.get(a) - ready.get(b))[0];
    const job = queues.get(host).shift();
    const wait = ready.get(host) - Date.now();
    if (wait > 0) await sleep(wait);
    const url = fetchUrl(job.url);
    let r = await get(url);
    if (r.retry) { await sleep(RETRY_MS); r = await get(url); if (r.retry) r = { error: r.retry }; }
    ready.set(host, Date.now() + GAP_MS);
    done++;
    const tag = `[${String(done).padStart(3)}/${total}] ${job.product.id.padEnd(22)} ${String(job.name ?? '(no color name)').slice(0, 24).padEnd(24)}`;
    if (r.refused) {
      const left = queues.get(host).length;
      stopped.set(host, { why: r.refused, left: left + 1 });
      queues.set(host, []);
      console.log(`${tag} REFUSED ${r.refused}: stopping ${host} for this run, ${left + 1} left unfetched`);
      continue;
    }
    let entry;
    if (r.error) entry = { error: r.error, sampled: today };
    else {
      if (scratch) fs.writeFileSync(path.join(scratch, `${String(done).padStart(4, '0')}${path.extname(new URL(url).pathname) || '.img'}`), r.bytes);
      const d = await decode(r.bytes);
      if (d.error) entry = { error: d.error, sampled: today };
      else {
        const s = sampleColor(d.rgb, job.flags);
        entry = { hex: s.hex, palette: s.palette, method: s.method, kept: s.kept, check: s.check, ...(s.mean ? { mean: s.mean } : {}), sampled: today };
      }
    }
    cache[job.url] = entry;
    if (entry.error) { failed++; console.log(`${tag} ERROR ${entry.error}`); }
    else {
      sampledN++;
      const flags = [...entry.check];
      if (job.name && !nameCheck(job.name, entry.hex).ok) flags.push('name-mismatch');
      if (flags.length) flagged++;
      console.log(`${tag} ${entry.hex} ${entry.method.padEnd(6)} kept ${entry.kept.toFixed(2)} ${flags.join(',')}`);
    }
    if (done % 20 === 0) writeCache(cache);
  }
  writeCache(cache);
  cleanup();
  const all = Object.values(cache);
  console.log(`\nthis run: sampled ${sampledN}, cached ${cached} (skipped), failed ${failed}, flagged ${flagged}`);
  for (const [h, s] of stopped) console.log(`stopped ${h}: ${s.why}; ${s.left} left unfetched (they keep a name color until a later run)`);
  console.log(`cache: ${all.length} images, ${all.filter((e) => e.hex).length} with a color, ${all.filter((e) => e.error).length} errors -> ${path.relative(process.cwd(), CACHE)}`);
  console.log('next: rebuild the catalog (build-supplier-catalog.mjs) to merge the colors, then draw the sheet with --sheet <file.jpg>');
}

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const shortName = (p) => p.name.replace(/[®™]/g, '').replace(/\s*\([^)]*\)/g, '').replace(/\s+/g, ' ').trim();

/** Contact sheet of our own flat chips (no store image is drawn), rendered with Playwright. */
async function sheet(file) {
  const STORE = { 'menards-3064': 'Menards', 'homedepot-4301': 'Home Depot' };
  const rows = [];
  for (const store of Object.keys(STORE)) {
    for (const layer of COLOR_LAYERS) {
      const ps = catalog.products.filter((p) => p.store === store && p.layer === layer);
      if (!ps.length) continue;
      const chips = [];
      for (const p of ps) {
        const listed = listedColor(p);
        chips.push({ p, c: listed || { name: null }, variant: false });
        for (const c of p.colors || []) if (c !== listed && c.colorCheck?.length) chips.push({ p, c, variant: true }); // flagged variants too
      }
      rows.push({ title: `${STORE[store]} · ${layer} · ${ps.length} products`, chips });
    }
  }
  const W = 1600, COLS = 10;
  const chip = ({ p, c, variant }) => {
    const hex = c.hex;
    const flags = c.colorCheck || [];
    const pal = (c.palette || []).map((h) => `<i style="background:${h}"></i>`).join('');
    const src = { swatch: 'S', photo: 'P', name: 'N', override: 'O' }[c.colorSource] || '–';
    return `<div class="chip${flags.length ? ' flag' : ''}"><div class="sw" style="${hex ? `background:${hex}` : ''}">${hex ? '' : '<span>color not sampled</span>'}${flags.length ? `<b>${esc(flags.map((f) => ({ scene: 'scene', mixed: 'mixed', 'name-mismatch': 'name?' }[f] || f)).join(' '))}</b>` : ''}</div>`
      + `<div class="pal">${pal}</div><div class="t">${esc((variant ? '↳ ' : '') + (c.name ?? '(no color name)'))}</div><div class="n">${esc(shortName(p))}</div><div class="h">${hex || ''} · ${src}</div></div>`;
  };
  const html = `<!doctype html><meta charset="utf-8"><style>
    body{margin:0;background:#fff;font:11px/1.25 "DejaVu Sans",Arial,sans-serif;color:#222;width:${W}px}
    header{padding:12px 16px 4px;font-size:15px} header small{display:block;font-size:11px;color:#555;margin-top:3px}
    h2{font-size:12px;margin:10px 16px 4px;color:#333}
    .grid{display:grid;grid-template-columns:repeat(${COLS},1fr);gap:6px;padding:0 16px}
    .chip{min-width:0} .sw{height:34px;border:1px solid #0002;position:relative;display:flex;align-items:center;justify-content:center}
    .sw span{font-size:9px;color:#555} .sw:not([style*=background]){background:repeating-linear-gradient(45deg,#eee 0 5px,#ccc 5px 10px)}
    .flag .sw{outline:3px solid #e8590c;outline-offset:-1px} .sw b{position:absolute;right:0;top:0;background:#e8590c;color:#fff;font-size:9px;padding:1px 3px}
    .pal{display:flex;height:6px} .pal i{flex:1}
    .t,.n,.h{white-space:nowrap;overflow:hidden;text-overflow:ellipsis} .t{font-weight:bold} .n{color:#555;font-size:9.5px} .h{color:#777;font-size:9px}
  </style><header>Store colors, sampled ${esc(today)}: listed color of each product, plus flagged variants (↳)
    <small>Flat chips drawn from the sampled hex; no store image. Strip under a chip: palette, largest cluster first. S swatch · P product photo · N name rule · O override · hatched: color not sampled. Orange: flagged (scene, mixed, name? = name mismatch).</small></header>
    ${rows.map((r) => `<h2>${esc(r.title)}</h2><div class="grid">${r.chips.map(chip).join('')}</div>`).join('')}<div style="height:12px"></div>`;
  const { launch } = await import('../../lab/tools/_playwright.mjs');
  const { browser } = await launch({ software: true });
  try {
    const page = await browser.newPage({ viewport: { width: W, height: 800 } });
    await page.setContent(html);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await page.screenshot({ path: file, type: 'jpeg', quality: 80, fullPage: true });
  } finally { await browser.close(); }
  const listed = rows.flatMap((r) => r.chips.filter((x) => !x.variant));
  const count = (f) => listed.filter((x) => (x.c.colorCheck || []).includes(f)).length;
  console.log(`${file}: ${listed.length} listed colors, ${listed.filter((x) => x.c.hex).length} with a hex; flagged scene ${count('scene')}, mixed ${count('mixed')}, name-mismatch ${count('name-mismatch')}; ${rows.reduce((s, r) => s + r.chips.length, 0) - listed.length} flagged variants`);
}

if (arg('sheet')) await sheet(arg('sheet'));
else await sample();
