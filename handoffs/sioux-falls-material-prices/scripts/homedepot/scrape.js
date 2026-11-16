// Browse Home Depot roofing categories as a shopper with the Sioux Falls, SD store (#4301) selected,
// and save the product data each listing page loads. Polite pacing; stops a category on any error.
const { chromium } = require('playwright');
const fs = require('fs');

const OUT = process.argv[2];
const CATS_DEFAULT = [
  ['Roof Shingles', '/b/Building-Materials-Roofing-Roof-Shingles/N-5yc1vZc5rb'],
  ['Roof Underlayments', '/b/Building-Materials-Roofing-Roof-Underlayments/N-5yc1vZc5rw'],
  ['Roof Flashing', '/b/Building-Materials-Roofing-Roof-Flashing/N-5yc1vZaqp7'],
  ['Roof Panels & Metal Roofing', '/b/Building-Materials-Roofing-Roof-Panels/N-5yc1vZaq4r'],
  ['Roll Roofing', '/b/Building-Materials-Roofing-Roll-Roofing/N-5yc1vZaqaa'],
  ['Roofing Tools', '/b/Building-Materials-Roofing-Roofing-Tools/N-5yc1vZc938'],
  ['Commercial Roofing (coatings, sealants, cement)', '/b/Building-Materials-Roofing-Commercial-Roofing/N-5yc1vZapzz'],
];
const CATS = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], 'utf8')) : CATS_DEFAULT;
const LOGNAME = process.argv[4] || '_log.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1366, height: 900 }, locale: 'en-US' });
  const p = await ctx.newPage();
  let latest = null; let got = [];
  const pick = start => got.find(j => (j.data.searchModel.searchReport?.startIndex ?? -1) === start) || null;
  p.on('response', async r => {
    if (r.url().includes('federation-gateway/graphql') && r.url().includes('searchModel')) {
      try { const j = await r.json(); if (j?.data?.searchModel?.products) { got.push(j); } } catch (e) {}
    }
  });
  await p.goto('https://www.homedepot.com/l/4301', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(4000);
  await p.getByText('Shop This Store', { exact: true }).first().click();
  await sleep(5000);
  const loc = (await ctx.cookies()).find(c => c.name === 'THD_LOCALIZER');
  console.log('store cookie:', loc ? decodeURIComponent(loc.value).slice(0, 90) : 'MISSING');

  const log = [];
  for (const [name, path, start0] of CATS) {
    let start = start0 || 0, total = null, pages = 0;
    const items = [];
    while (true) {
      latest = null; got = [];
      const url = 'https://www.homedepot.com' + path + (start ? `?Nao=${start}` : '');
      try {
        const resp = await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        for (let i = 0; i < 20 && !(latest = pick(start)); i++) await sleep(1000);
        if (!latest) { await p.mouse.wheel(0, 3000); for (let i = 0; i < 10 && !(latest = pick(start)); i++) await sleep(1000); }
        if (!latest) { log.push({ name, start, status: resp && resp.status(), error: 'no product data' }); console.log(name, start, 'no data, status', resp && resp.status()); break; }
      } catch (e) { log.push({ name, start, error: String(e).slice(0, 200) }); console.log(name, start, 'error', String(e).slice(0, 120)); break; }
      const sm = latest.data.searchModel;
      total = sm.searchReport.totalProducts;
      const prods = sm.products || [];
      items.push(...prods);
      pages++;
      console.log(`${name}: start ${start} got ${prods.length} / total ${total}`);
      start += 24;
      if (!prods.length || start >= total || pages >= 60) break;
      await sleep(3500 + Math.random() * 2000);
    }
    fs.writeFileSync(`${OUT}/${name.replace(/[^A-Za-z]+/g, '_')}${start0 ? '_from' + start0 : ''}.json`, JSON.stringify({ name, path, total, items }));
    log.push({ name, path, total, captured: items.length, pages });
    await sleep(5000);
  }
  fs.writeFileSync(`${OUT}/${LOGNAME}`, JSON.stringify(log, null, 1));
  console.log('DONE');
  await b.close();
})();
