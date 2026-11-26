// Print a studio report page to PDF with headless Chromium (node Playwright): US letter, print.css, page numbers.
//   node report_pdf.js REPORT.html OUT.pdf [--css print.css] [--expect TEXT]... [--min-pages N] [--timeout MS]
// Prints one JSON line: {ok, pages, bytes, missing: [expected texts not in the printed page], broken: [images],
// errors: [page errors]}. Exit 0 when ok. Run through report_pdf.py, which finds the Playwright install.
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

function parse(argv) {
  const a = { expect: [], minPages: 1, timeout: 90000, pos: [] };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--css') a.css = argv[++i];
    else if (k === '--expect') a.expect.push(argv[++i]);
    else if (k === '--min-pages') a.minPages = Number(argv[++i]);
    else if (k === '--timeout') a.timeout = Number(argv[++i]);
    else a.pos.push(k);
  }
  [a.html, a.out] = a.pos;
  return a;
}

function countPages(buf) {
  const s = buf.toString('latin1');
  const m = s.match(/\/Type\s*\/Page(?![a-zA-Z])/g);
  return m ? m.length : 0;
}

(async () => {
  const a = parse(process.argv.slice(2));
  const res = { ok: false, pages: 0, bytes: 0, missing: [], broken: [], errors: [] };
  if (!a.html || !a.out) {
    console.log(JSON.stringify({ ...res, error: 'usage: report_pdf.js REPORT.html OUT.pdf' }));
    process.exit(2);
  }
  let chromium;
  try { ({ chromium } = require('playwright')); } catch (e) {
    console.log(JSON.stringify({ ...res, error: 'playwright not found: ' + e.message, tooling: true }));
    process.exit(3);
  }
  let browser;
  try {
    browser = await chromium.launch();
    const page = await browser.newPage();
    page.on('pageerror', (e) => res.errors.push(e.message));
    page.setDefaultTimeout(a.timeout);
    try {
      await page.goto(pathToFileURL(path.resolve(a.html)).href, { waitUntil: 'load', timeout: a.timeout });
    } catch (e) {
      res.errors.push('load: ' + e.message.split('\n')[0]);   // e.g. web fonts unreachable: print with fallbacks
    }
    await page.emulateMedia({ media: 'print' });
    if (a.css) {
      const has = await page.evaluate(() => {
        const s = document.querySelector('style[data-print-css]');
        return !!(s && s.textContent.trim().length > 0);
      });
      if (!has) await page.addStyleTag({ content: fs.readFileSync(a.css, 'utf8') });
    }
    await page.evaluate(async () => {
      const wait = (img) => (img.complete ? null : new Promise((r) => { img.onload = img.onerror = r; }));
      await Promise.race([Promise.all([...document.images].map(wait)), new Promise((r) => setTimeout(r, 20000))]);
      if (document.fonts && document.fonts.ready) await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 10000))]);
    });
    const text = await page.evaluate(() => document.body.innerText);
    res.missing = a.expect.filter((t) => !text.includes(t));
    res.broken = await page.evaluate(() => [...document.images].filter((i) => !i.naturalWidth).map((i) => i.getAttribute('src')));
    await page.pdf({
      path: a.out, format: 'Letter', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#666;font-family:sans-serif">' +
        '<span class="pageNumber"></span> / <span class="totalPages"></span></div>',
      margin: { top: '0.55in', bottom: '0.65in', left: '0.55in', right: '0.55in' },
    });
    const buf = fs.readFileSync(a.out);
    res.bytes = buf.length;
    res.pages = countPages(buf);
    res.ok = res.missing.length === 0 && res.broken.length === 0 && res.pages >= a.minPages;
  } catch (e) {
    res.error = e.message.split('\n')[0];
  } finally {
    if (browser) await browser.close();
  }
  console.log(JSON.stringify(res));
  process.exit(res.ok ? 0 : 1);
})();
