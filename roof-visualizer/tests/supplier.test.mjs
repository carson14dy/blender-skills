// Supplier page parsing and the SSRF guard.
import test from 'node:test';
import assert from 'node:assert/strict';
import { extractImages, isPrivateAddress, safeFetch } from '../scripts/lib/supplier.mjs';

const html = `<html><head><title>Ridge Line Shingle, Pewter | Example Roofing</title>
<meta property="og:image" content="/img/pewter-swatch.jpg">
<meta property="og:site_name" content="Example Roofing">
<script type="application/ld+json">{"@type":"Product","name":"Ridge Line","image":["https://cdn.example.com/p/ridge-pewter-roof.jpg"]}</script>
</head><body>
<img src="/static/logo.svg" alt="logo"><img src="/static/icon-cart.png">
<img data-src="/media/house-front.jpg" alt="Home with pewter shingles">
<img srcset="/media/s-400.jpg 400w, /media/s-1600.jpg 1600w" alt="Shingle colour close-up">
</body></html>`;

test('extractImages ranks product images and drops logos and icons', () => {
  const r = extractImages(html, 'https://www.example.com/products/ridge-line');
  const urls = r.images.map((i) => i.url);
  assert.equal(r.siteName, 'Example Roofing');
  assert.match(r.title, /Ridge Line/);
  assert.equal(urls[0], 'https://cdn.example.com/p/ridge-pewter-roof.jpg');
  assert.ok(urls.includes('https://www.example.com/img/pewter-swatch.jpg'));
  assert.ok(urls.includes('https://www.example.com/media/s-1600.jpg'), 'largest srcset candidate');
  assert.ok(!urls.some((u) => /logo|icon/.test(u)));
});

test('private and loopback addresses are recognised', () => {
  for (const ip of ['127.0.0.1', '10.1.2.3', '192.168.0.10', '172.20.1.1', '169.254.169.254', '::1', 'fd00::1']) assert.ok(isPrivateAddress(ip), ip);
  for (const ip of ['8.8.8.8', '151.101.1.1', '2606:4700::1111']) assert.ok(!isPrivateAddress(ip), ip);
});

test('safeFetch refuses local targets and non-http schemes', async () => {
  await assert.rejects(safeFetch('http://127.0.0.1:9/x'), /Private|Local/);
  await assert.rejects(safeFetch('http://localhost/x'), /Local/);
  await assert.rejects(safeFetch('file:///etc/passwd'), /http/);
});
