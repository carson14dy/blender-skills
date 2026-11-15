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
import net from 'node:net';

export const USER_AGENT = 'RoofLayerStudio/1.0 (+contractor roof visualizer)';
const MAX_HTML = 4 * 1024 * 1024;
const MAX_IMAGE = 25 * 1024 * 1024;

export function isPrivateAddress(ip) {
  if (net.isIPv4(ip)) {
    const [a, b] = ip.split('.').map(Number);
    return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
      || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || a >= 224;
  }
  const v = ip.toLowerCase();
  return v === '::1' || v === '::' || v.startsWith('fc') || v.startsWith('fd') || v.startsWith('fe80') || v.startsWith('::ffff:127.') || v.startsWith('::ffff:10.') || v.startsWith('::ffff:192.168.');
}

async function checkHost(url, { allowPrivate = false } = {}) {
  if (!/^https?:$/.test(url.protocol)) throw new Error('Only http and https links are supported.');
  if (allowPrivate) return;
  const host = url.hostname.replace(/^\[|\]$/g, '');
  if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.internal')) throw new Error('Local addresses are not allowed.');
  if (net.isIP(host)) { if (isPrivateAddress(host)) throw new Error('Private network addresses are not allowed.'); return; }
  try {
    const addrs = await dns.lookup(host, { all: true });
    if (addrs.some((a) => isPrivateAddress(a.address))) throw new Error('That host resolves to a private network address.');
  } catch (e) {
    // Behind an outbound proxy the name may not resolve locally; the proxy resolves it instead.
    if (e.message.includes('private')) throw e;
    if (!process.env.HTTPS_PROXY && !process.env.https_proxy) throw new Error(`Could not resolve ${host}.`);
  }
}

/** fetch with SSRF checks, manual redirects and a size cap. Returns { res, url, buffer }. */
export async function safeFetch(rawUrl, { accept = '*/*', maxBytes = MAX_IMAGE, allowPrivate = false, timeoutMs = 20000 } = {}) {
  let url = new URL(rawUrl);
  for (let hop = 0; hop < 6; hop++) {
    await checkHost(url, { allowPrivate });
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    let res;
    try {
      res = await fetch(url, { redirect: 'manual', signal: ctrl.signal, headers: { 'user-agent': USER_AGENT, accept } });
    } finally { clearTimeout(timer); }
    if (res.status >= 300 && res.status < 400 && res.headers.get('location')) {
      url = new URL(res.headers.get('location'), url);
      continue;
    }
    if (!res.ok) throw new Error(`The site answered ${res.status} ${res.statusText}.`);
    const len = Number(res.headers.get('content-length') || 0);
    if (len > maxBytes) throw new Error(`The file is larger than ${Math.round(maxBytes / 1048576)} MB.`);
    const chunks = []; let total = 0;
    for await (const chunk of res.body) {
      total += chunk.length;
      if (total > maxBytes) throw new Error(`The file is larger than ${Math.round(maxBytes / 1048576)} MB.`);
      chunks.push(chunk);
    }
    return { res, url: url.href, buffer: Buffer.concat(chunks) };
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
