// Supplier image helpers shared by the local server and the CLI.
// - safeFetch: HTTP(S) only, blocks private/loopback addresses (SSRF guard),
//   follows redirects manually and re-checks each hop, caps response size.
// - scanPage: find product images on a supplier product page.
// - saveSwatch: download (or decode) an image into catalog/swatches and
//   append the product to catalog.json.
//
// Only import images you have the rights to use (brand-portal assets,
// written permission, or your own photos). The catalog records the source
// URL and a rights note for every imported product.

import fs from 'node:fs/promises';
import path from 'node:path';
import dns from 'node:dns/promises';
import { lookup as dnsLookup } from 'node:dns';
import net from 'node:net';
import http from 'node:http';
import https from 'node:https';

export const USER_AGENT = 'RoofLayerStudio/1.0 (+contractor roof visualizer)';
const MAX_HTML = 4 * 1024 * 1024;
const MAX_IMAGE = 25 * 1024 * 1024;

// Addresses a supplier page must never point the server at (RFC 1918, loopback,
// link-local, CGNAT, multicast, unique-local, site-local, documentation, ...).
const BLOCK = new net.BlockList();
for (const [a, p] of [['0.0.0.0', 8], ['10.0.0.0', 8], ['100.64.0.0', 10], ['127.0.0.0', 8], ['169.254.0.0', 16], ['172.16.0.0', 12],
  ['192.0.0.0', 24], ['192.0.2.0', 24], ['192.168.0.0', 16], ['198.18.0.0', 15], ['198.51.100.0', 24], ['203.0.113.0', 24], ['224.0.0.0', 3]]) BLOCK.addSubnet(a, p, 'ipv4');
for (const [a, p] of [['::', 128], ['::1', 128], ['fc00::', 7], ['fe80::', 10], ['fec0::', 10], ['ff00::', 8], ['2001:db8::', 32], ['100::', 64]]) BLOCK.addSubnet(a, p, 'ipv6');

/** IPv4 hidden inside an IPv6 address (mapped ::ffff:a.b.c.d / ::ffff:xxxx:xxxx, NAT64 64:ff9b::/96), or null. */
function embeddedV4(ip) {
  const v = ip.toLowerCase();
  const m = v.match(/^(?:::ffff:|64:ff9b::|::)(\d+\.\d+\.\d+\.\d+)$/);
  if (m) return m[1];
  const h = v.match(/^(?:::ffff:|64:ff9b::)([0-9a-f]{1,4}):([0-9a-f]{1,4})$/);
  if (h) { const a = parseInt(h[1], 16), b = parseInt(h[2], 16); return `${a >> 8}.${a & 255}.${b >> 8}.${b & 255}`; }
  return null;
}

export function isPrivateAddress(ip) {
  if (net.isIPv4(ip)) return BLOCK.check(ip, 'ipv4');
  if (!net.isIPv6(ip)) return true; // not an IP: refuse
  const v4 = embeddedV4(ip);
  if (v4) return BLOCK.check(v4, 'ipv4');
  return BLOCK.check(ip, 'ipv6');
}

const viaProxy = () => !!(process.env.HTTPS_PROXY || process.env.https_proxy);

/** Scheme and address checks before any request. Direct connections are checked again at connect time. */
async function checkHost(url, { allowPrivate = false } = {}) {
  if (!/^https?:$/.test(url.protocol)) throw new Error('Only http and https links are supported.');
  if (url.username || url.password) throw new Error('Links with a user name or password are not supported.');
  if (allowPrivate) return;
  const host = url.hostname.replace(/^\[|\]$/g, '');
  if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.internal') || host.endsWith('.local')) throw new Error('Local addresses are not allowed.');
  if (net.isIP(host)) { if (isPrivateAddress(host)) throw new Error('Private network addresses are not allowed.'); return; }
  let addrs;
  try { addrs = await dns.lookup(host, { all: true }); } catch {
    // behind an outbound proxy the name may only resolve at the proxy
    if (viaProxy()) return;
    throw new Error(`Could not resolve ${host}.`);
  }
  if (addrs.some((a) => isPrivateAddress(a.address))) throw new Error('That host resolves to a private network address.');
}

/**
 * DNS lookup that refuses private addresses at connect time, so a host cannot
 * pass the check with a public address and then connect to a private one (DNS rebinding).
 */
function guardedLookup(hostname, options, cb) {
  dnsLookup(hostname, { ...options, all: true }, (err, addrs) => {
    if (err) return cb(err);
    const bad = addrs.find((a) => isPrivateAddress(a.address));
    if (bad) return cb(Object.assign(new Error('That host resolves to a private network address.'), { code: 'EPRIVATE' }));
    if (options.all) return cb(null, addrs);
    cb(null, addrs[0].address, addrs[0].family);
  });
}

/** One request with node:http(s) and the guarded lookup. Resolves { status, headers, body, url }. */
function directGet(url, { accept, maxBytes, timeoutMs, allowPrivate }) {
  return new Promise((resolve, reject) => {
    const mod = url.protocol === 'https:' ? https : http;
    const req = mod.get(url, { headers: { 'user-agent': USER_AGENT, accept }, lookup: allowPrivate ? undefined : guardedLookup, timeout: timeoutMs }, (res) => {
      const len = Number(res.headers['content-length'] || 0);
      if (len > maxBytes) { res.destroy(); return reject(new Error(`The file is larger than ${Math.round(maxBytes / 1048576)} MB.`)); }
      const chunks = []; let total = 0;
      res.on('data', (c) => { total += c.length; if (total > maxBytes) { res.destroy(); reject(new Error(`The file is larger than ${Math.round(maxBytes / 1048576)} MB.`)); } else chunks.push(c); });
      res.on('end', () => resolve({ status: res.statusCode, headers: new Headers(Object.entries(res.headers).flatMap(([k, v]) => [].concat(v).map((x) => [k, String(x)]))), body: Buffer.concat(chunks) }));
      res.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('The site did not answer in time.')));
    req.on('error', (e) => reject(e.code === 'EPRIVATE' ? e : new Error(`Could not fetch ${url.hostname}: ${e.message}`)));
  });
}

/** Same request through fetch (used behind an outbound proxy, where the proxy resolves names). */
async function proxiedGet(url, { accept, maxBytes, timeoutMs }) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { redirect: 'manual', signal: ctrl.signal, headers: { 'user-agent': USER_AGENT, accept } });
    const len = Number(res.headers.get('content-length') || 0);
    if (len > maxBytes) throw new Error(`The file is larger than ${Math.round(maxBytes / 1048576)} MB.`);
    const chunks = []; let total = 0;
    if (res.body) for await (const chunk of res.body) {
      total += chunk.length;
      if (total > maxBytes) throw new Error(`The file is larger than ${Math.round(maxBytes / 1048576)} MB.`);
      chunks.push(chunk);
    }
    return { status: res.status, headers: res.headers, body: Buffer.concat(chunks) };
  } finally { clearTimeout(timer); }
}

/** fetch with SSRF checks, manual redirects and a size cap. Returns { res: {status, headers}, url, buffer }. */
export async function safeFetch(rawUrl, { accept = '*/*', maxBytes = MAX_IMAGE, allowPrivate = false, timeoutMs = 20000 } = {}) {
  let url = new URL(rawUrl);
  for (let hop = 0; hop < 6; hop++) {
    await checkHost(url, { allowPrivate });
    const r = viaProxy() ? await proxiedGet(url, { accept, maxBytes, timeoutMs }) : await directGet(url, { accept, maxBytes, timeoutMs, allowPrivate });
    if (r.status >= 300 && r.status < 400 && r.headers.get('location')) { url = new URL(r.headers.get('location'), url); continue; }
    if (r.status < 200 || r.status >= 300) throw new Error(`The site answered ${r.status}.`);
    return { res: { status: r.status, headers: r.headers }, url: url.href, buffer: r.body };
  }
  throw new Error('Too many redirects.');
}

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
const attr = (tag, name) => {
  const m = tag.match(new RegExp(`\\s${name}\\s*=\\s*("([^"]*)"|'([^']*)'|([^\\s>]+))`, 'i'));
  return m ? decode(m[2] ?? m[3] ?? m[4] ?? '') : null;
};

/** Pick the widest candidate from a srcset attribute. */
function bestFromSrcset(srcset) {
  let best = null, bestW = -1;
  for (const part of srcset.split(',')) {
    const [u, d] = part.trim().split(/\s+/);
    if (!u) continue;
    const w = d ? parseFloat(d) * (d.endsWith('x') ? 1000 : 1) : 0;
    if (w > bestW) { bestW = w; best = u; }
  }
  return best;
}

/**
 * Find candidate product images on a page.
 * @returns {{title:string, siteName:string, images:{url:string, alt:string, source:string}[]}}
 */
export function extractImages(html, baseUrl) {
  const out = [];
  const seen = new Set();
  const push = (u, alt = '', source = 'img') => {
    if (!u || u.startsWith('data:')) return;
    let abs;
    try { abs = new URL(u.trim(), baseUrl).href; } catch { return; }
    if (!/^https?:/.test(abs)) return;
    if (/\.svg(\?|$)/i.test(abs) || /(sprite|favicon|icon[-_]|logo|badge|spinner|placeholder|pixel\.gif)/i.test(abs)) return;
    const key = abs.replace(/[?#].*$/, '');
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ url: abs, alt: alt.slice(0, 140), source });
  };
  for (const m of html.matchAll(/<meta\b[^>]*>/gi)) {
    const p = (attr(m[0], 'property') || attr(m[0], 'name') || '').toLowerCase();
    if (['og:image', 'og:image:url', 'og:image:secure_url', 'twitter:image', 'twitter:image:src'].includes(p)) push(attr(m[0], 'content'), '', 'meta');
  }
  for (const m of html.matchAll(/<link\b[^>]*>/gi)) if ((attr(m[0], 'rel') || '').toLowerCase() === 'image_src') push(attr(m[0], 'href'), '', 'link');
  for (const m of html.matchAll(/<script[^>]+application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi)) {
    try {
      const walk = (o) => {
        if (!o || typeof o !== 'object') return;
        if (Array.isArray(o)) return o.forEach(walk);
        if (o.image) [].concat(o.image).forEach((im) => push(typeof im === 'string' ? im : im?.url || im?.contentUrl, o.name || '', 'json-ld'));
        Object.values(o).forEach(walk);
      };
      walk(JSON.parse(m[1]));
    } catch { /* malformed JSON-LD */ }
  }
  for (const m of html.matchAll(/<(img|source)\b[^>]*>/gi)) {
    const tag = m[0];
    const alt = attr(tag, 'alt') || '';
    const srcset = attr(tag, 'srcset') || attr(tag, 'data-srcset');
    if (srcset) push(bestFromSrcset(srcset), alt);
    for (const a of ['data-zoom-image', 'data-large', 'data-src', 'data-lazy-src', 'data-original', 'src']) {
      const v = attr(tag, a);
      if (v) { push(v, alt); break; }
    }
  }
  // product imagery first: JSON-LD and meta images, then alt text that mentions roofing words
  const score = (i) => (i.source === 'json-ld' ? 4 : i.source === 'meta' ? 3 : 0) + (/shingle|roof|swatch|color|colour|tile|metal|slate|shake/i.test(i.alt + i.url) ? 2 : 0);
  out.sort((a, b) => score(b) - score(a));
  const title = decode((html.match(/<meta[^>]+property=["']og:title["'][^>]*content=["']([^"']+)/i) || html.match(/<title[^>]*>([^<]+)/i) || [])[1] || '').trim();
  const siteName = decode((html.match(/<meta[^>]+property=["']og:site_name["'][^>]*content=["']([^"']+)/i) || [])[1] || '').trim() || new URL(baseUrl).hostname.replace(/^www\./, '');
  return { title, siteName, images: out.slice(0, 80) };
}

export async function scanPage(pageUrl, opts = {}) {
  const { res, url, buffer } = await safeFetch(pageUrl, { accept: 'text/html,application/xhtml+xml,image/*', maxBytes: MAX_HTML, ...opts });
  const type = res.headers.get('content-type') || '';
  if (type.startsWith('image/')) return { title: '', siteName: new URL(url).hostname, images: [{ url, alt: '', source: 'direct' }] };
  return extractImages(buffer.toString('utf8'), url);
}

export function slugify(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'item';
}

const EXT = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/avif': 'avif', 'image/gif': 'gif' };

/**
 * Save a swatch image and register the product in the catalog.
 * @param {string} viewerDir  roof-visualizer/viewer
 * @param {object} p  name, supplier, category, widthIn, heightIn, exposureIn, sourceUrl, rights, imageUrl | dataUrl
 */
export async function saveSwatch(viewerDir, p, opts = {}) {
  if (!p.name) throw new Error('A product name is required.');
  if (!p.rights) throw new Error('Confirm that you have the rights to use this image.');
  let buffer, type;
  if (p.dataUrl) {
    const m = String(p.dataUrl).match(/^data:(image\/[a-z+]+);base64,(.+)$/);
    if (!m) throw new Error('The uploaded file is not an image.');
    type = m[1]; buffer = Buffer.from(m[2], 'base64');
    if (buffer.length > MAX_IMAGE) throw new Error('The image is larger than 25 MB.');
  } else if (p.imageUrl) {
    const r = await safeFetch(p.imageUrl, { accept: 'image/*', ...opts });
    type = (r.res.headers.get('content-type') || '').split(';')[0];
    buffer = r.buffer;
  } else throw new Error('Send imageUrl or dataUrl.');
  const ext = EXT[type];
  if (!ext) throw new Error(`Unsupported image type "${type || 'unknown'}". Use JPG, PNG or WebP.`);
  const supplier = p.supplier || (p.imageUrl ? new URL(p.imageUrl).hostname.replace(/^www\./, '') : 'Uploaded photo');
  const id = p.id && /^[a-z0-9-]+$/.test(p.id) ? p.id : `sup-${slugify(supplier)}-${slugify(p.name)}`;
  const file = `${id}.${ext}`;
  const dir = path.join(viewerDir, 'catalog', 'swatches');
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(path.join(dir, file), buffer);
  const catalogPath = path.join(viewerDir, 'catalog', 'catalog.json');
  const catalog = JSON.parse(await fs.readFile(catalogPath, 'utf8'));
  const product = {
    id, name: p.name, supplier, category: ['shingle', 'metal', 'tile', 'slate', 'shake'].includes(p.category) ? p.category : 'shingle',
    image: `catalog/swatches/${file}`,
    widthIn: Number(p.widthIn) || 36,
    ...(p.heightIn ? { heightIn: Number(p.heightIn) } : {}),
    ...(p.exposureIn ? { exposureIn: Number(p.exposureIn) } : {}),
    sourceUrl: p.sourceUrl || p.imageUrl || null,
    rights: typeof p.rights === 'string' ? p.rights : 'Confirmed by user at import',
    addedAt: new Date().toISOString(),
  };
  catalog.products = (catalog.products || []).filter((x) => x.id !== id);
  catalog.products.push(product);
  await fs.writeFile(catalogPath, JSON.stringify(catalog, null, 2) + '\n');
  return product;
}
