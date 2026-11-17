const { chromium } = require('playwright');
exports.open = async function open({ url = (process.env.LAB_URL || 'http://127.0.0.1:8765') + '/', width = 1280, height = 800, scheme = 'light', mobile = false, args = [], webgpu = false } = {}) {
  const a = [...(webgpu ? ['--enable-unsafe-webgpu', '--enable-features=Vulkan'] : ['--disable-features=WebGPU,Vulkan']), '--use-angle=swiftshader', '--ignore-gpu-blocklist', ...args];
  const browser = await chromium.launch({ args: a, proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: '127.0.0.1,localhost' } : undefined });
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile,
    userAgent: mobile ? 'Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36' : undefined });
  const page = await ctx.newPage();
  const logs = [];
  page.on('console', (m) => logs.push(`[${m.type()}] ${m.text()}`.slice(0, 500)));
  page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
  page.on('requestfailed', (r) => logs.push(`[reqfail] ${r.url()} ${r.failure()?.errorText}`));
  const t0 = Date.now();
  await page.goto(url, { waitUntil: 'load', timeout: 120000 });
  await page.waitForFunction(() => window.roofStudio && document.getElementById('loading')?.hidden, null, { timeout: 120000 });
  const readyMs = Date.now() - t0;
  return { browser, page, logs, readyMs };
};
exports.errors = (logs) => logs.filter((l) => /^\[(error|pageerror|reqfail)\]/.test(l));
