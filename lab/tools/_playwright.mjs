// Shared Playwright loader and browser launcher for lab tools.
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

export function loadPlaywright() {
  const bases = [process.cwd(), path.resolve(here, '..', '..', 'roof-visualizer')];
  try { bases.push(execSync('npm root -g', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()); } catch { /* no npm */ }
  for (const b of bases) {
    try { return createRequire(path.join(b, 'x.js'))('playwright'); } catch { /* try next */ }
  }
  throw new Error('Playwright not found. Run: npm i -D playwright && npx playwright install chromium');
}

/** Software WebGL where there is no GPU (cloud containers); real GPU otherwise. */
export async function launch({ software } = {}) {
  const { chromium } = loadPlaywright();
  const noGpu = software ?? (process.platform === 'linux' && !process.env.DISPLAY);
  const args = noGpu ? ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] : ['--ignore-gpu-blocklist', '--enable-gpu'];
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: '127.0.0.1,localhost' } : undefined;
  return { browser: await chromium.launch({ args, proxy }), noGpu };
}

export function argParser(argv = process.argv.slice(2)) {
  const flags = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) continue;
    const k = argv[i].slice(2), v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) flags[k] = true; else { flags[k] = v; i++; }
  }
  return flags;
}

/** Open the viewer, wait until it is ready, and collect console errors. */
export async function openViewer(browser, url, { width = 1400, height = 860, colorScheme = 'light' } = {}) {
  const page = await browser.newPage({ viewport: { width, height }, colorScheme });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(e.message));
  const t0 = Date.now();
  await page.goto(url, { waitUntil: 'load', timeout: 120000 });
  await page.waitForFunction(() => window.roofStudio, null, { timeout: 120000 });
  await page.evaluate(() => window.roofStudio.ready);
  // which GPU actually drew the page: a software renderer means timings are not representative
  const gpu = await page.evaluate(() => {
    const gl = window.roofStudio.three.renderer.getContext();
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  }).catch(() => 'unknown');
  return { page, errors, readyMs: Date.now() - t0, gpu };
}
