#!/usr/bin/env node
// Local server for Roof Layer Studio.
//   node roof-visualizer/scripts/serve.mjs [--port 8080] [--host 127.0.0.1] [--open]
// Serves the viewer and adds the APIs that a static page cannot do itself:
//   GET  /api/health            server capabilities
//   GET  /api/scan?url=          find product images on a supplier page
//   GET  /api/image?url=         fetch a remote image (CORS-safe for WebGL textures)
//   POST /api/swatch            save an image into the catalog
//   GET  /api/plans             list plans/*.json
//   POST /api/plan              Claude writes a build plan (needs @anthropic-ai/sdk + credentials)
// Binds to 127.0.0.1 by default: it is a tool for your own machine.

import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { scanPage, safeFetch, saveSwatch, slugify } from './lib/supplier.mjs';
import { generatePlan, explainError, credentialsAvailable, sdkAvailable, MODEL } from './lib/plan-ai.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const VIEWER = path.resolve(here, '..', 'viewer');
const args = process.argv.slice(2);
const arg = (n, d) => { const i = args.indexOf(`--${n}`); return i === -1 ? d : args[i + 1]; };
const PORT = Number(arg('port', process.env.PORT || 8080));
const HOST = arg('host', '127.0.0.1');
const ALLOW_PRIVATE = args.includes('--allow-private');
// Requests must come from the studio page itself: these Host values only (blocks DNS rebinding),
// and no foreign Origin (blocks other websites calling the API from the contractor's browser).
const LOOPBACK = ['127.0.0.1', 'localhost', '[::1]'];
const ALLOWED_HOSTS = new Set([...LOOPBACK, ...(LOOPBACK.includes(HOST) || HOST === '0.0.0.0' ? [] : [HOST]), ...args.filter((a, i) => args[i - 1] === '--allow-host')].map((h) => `${h}:${PORT}`));
const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/avif', 'image/gif']);
const MAX_AI_PLANS = 20;

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.avif': 'image/avif', '.gif': 'image/gif', '.svg': 'image/svg+xml',
  '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.hdr': 'application/octet-stream', '.bin': 'application/octet-stream',
};

const send = (res, status, body, headers = {}) => {
  res.writeHead(status, { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', ...headers });
  res.end(body);
};
const json = (res, status, obj) => send(res, status, JSON.stringify(obj), { 'content-type': 'application/json; charset=utf-8' });

async function readBody(req, max = 30 * 1024 * 1024) {
  const chunks = []; let total = 0;
  for await (const c of req) { total += c.length; if (total > max) throw new Error('Request too large.'); chunks.push(c); }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

let aiReady = null;
async function health() {
  if (aiReady === null) aiReady = (await sdkAvailable()) && credentialsAvailable();
  return { ok: true, version: 1, ai: aiReady, model: aiReady ? MODEL : null };
}

async function listPlans() {
  const dir = path.join(VIEWER, 'plans');
  const files = (await fs.readdir(dir)).filter((f) => f.endsWith('.json') && f !== 'index.json');
  const plans = [];
  for (const file of files) {
    try { const p = JSON.parse(await fs.readFile(path.join(dir, file), 'utf8')); plans.push({ file, title: p.title || file }); } catch { /* skip invalid */ }
  }
  return plans;
}

async function serveStatic(req, res, urlPath) {
  let rel = decodeURIComponent(urlPath);
  if (rel.endsWith('/')) rel += 'index.html';
  const file = path.resolve(VIEWER, '.' + rel);
  if (!file.startsWith(VIEWER + path.sep) && file !== VIEWER) return send(res, 403, 'Forbidden');
  try {
    let data = await fs.readFile(file);
    const type = TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
    if (file.endsWith('index.html')) {
      // tell the page that the API is available
      data = Buffer.from(data.toString('utf8').replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="roof-studio-server" content="1">'));
    }
    send(res, 200, data, { 'content-type': type });
  } catch {
    send(res, 404, 'Not found');
  }
}

/** Same-origin checks for API calls. Returns an error message, or null when the request is allowed. */
function rejectReason(req) {
  if (!ALLOWED_HOSTS.has(String(req.headers.host || '').toLowerCase())) return 'Unexpected Host header.';
  const origin = req.headers.origin;
  if (origin && origin !== 'null' && !ALLOWED_HOSTS.has(origin.replace(/^https?:\/\//, '').toLowerCase())) return 'Cross-site requests are not allowed.';
  const site = req.headers['sec-fetch-site'];
  if (site && !['same-origin', 'none'].includes(site)) return 'Cross-site requests are not allowed.';
  if (req.method === 'POST' && !String(req.headers['content-type'] || '').startsWith('application/json')) return 'Send JSON.';
  return null;
}

async function pruneAiPlans() {
  const dir = path.join(VIEWER, 'plans');
  const files = [];
  for (const f of await fs.readdir(dir)) if (/^ai-.*\.json$/.test(f)) files.push({ f, t: (await fs.stat(path.join(dir, f))).mtimeMs });
  files.sort((a, b) => b.t - a.t);
  for (const { f } of files.slice(MAX_AI_PLANS)) await fs.rm(path.join(dir, f), { force: true });
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://localhost');
  const p = u.pathname;
  if (p.startsWith('/api/')) {
    const why = rejectReason(req);
    if (why) return json(res, 403, { error: why });
  }
  try {
    if (p === '/api/health') return json(res, 200, await health());
    if (p === '/api/scan') {
      const target = u.searchParams.get('url');
      if (!target) return json(res, 400, { error: 'Add ?url=' });
      return json(res, 200, await scanPage(target, { allowPrivate: ALLOW_PRIVATE }));
    }
    if (p === '/api/image') {
      const target = u.searchParams.get('url');
      if (!target) return json(res, 400, { error: 'Add ?url=' });
      const r = await safeFetch(target, { accept: 'image/*', allowPrivate: ALLOW_PRIVATE });
      const type = (r.res.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
      // raster images only: an SVG served from this origin could run script next to the API
      if (!IMAGE_TYPES.has(type)) return json(res, 415, { error: 'That link is not a JPG, PNG, WebP, AVIF or GIF image.' });
      return send(res, 200, r.buffer, { 'content-type': type, 'x-content-type-options': 'nosniff', 'content-security-policy': "sandbox; default-src 'none'", 'cache-control': 'max-age=3600' });
    }
    if (p === '/api/swatch' && req.method === 'POST') {
      const body = await readBody(req);
      const product = await saveSwatch(VIEWER, body, { allowPrivate: ALLOW_PRIVATE });
      return json(res, 200, { product });
    }
    if (p === '/api/plans') return json(res, 200, { plans: await listPlans() });
    if (p === '/api/plan' && req.method === 'POST') {
      const body = await readBody(req, 1024 * 1024);
      if (!body.job) return json(res, 400, { error: 'Describe the job first.' });
      try {
        const plan = await generatePlan(body);
        const file = `ai-${slugify(plan.title)}-${Date.now().toString(36)}.json`;
        await fs.writeFile(path.join(VIEWER, 'plans', file), JSON.stringify(plan, null, 2) + '\n');
        await pruneAiPlans(); // keep the newest 20 Claude-written plans
        return json(res, 200, { plan, saved: true, file });
      } catch (e) {
        const { status, error } = await explainError(e);
        return json(res, status, { error });
      }
    }
    if (p.startsWith('/api/')) return json(res, 404, { error: 'Unknown endpoint.' });
    return serveStatic(req, res, p);
  } catch (e) {
    return json(res, 400, { error: e.message || String(e) });
  }
});

server.listen(PORT, HOST, async () => {
  const url = `http://${HOST === '0.0.0.0' ? 'localhost' : HOST}:${PORT}/`;
  const h = await health();
  console.log(`Roof Layer Studio: ${url}`);
  console.log(`  catalog: ${path.join(VIEWER, 'catalog', 'catalog.json')}`);
  console.log(`  Claude build plans: ${h.ai ? `on (${MODEL})` : 'off (npm install, then set ANTHROPIC_API_KEY or run "ant auth login")'}`);
  if (args.includes('--open')) {
    const cmd = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start' : 'xdg-open';
    spawn(cmd, [url], { stdio: 'ignore', detached: true, shell: process.platform === 'win32' }).unref();
  }
});
