// The local server only answers its own page: Host, Origin and Content-Type checks.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const PORT = 18000 + Math.floor(Math.random() * 1000);
const serve = fileURLToPath(new URL('../scripts/serve.mjs', import.meta.url));

function request(path, { method = 'GET', host = `127.0.0.1:${PORT}`, headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: PORT, path, method, headers: { host, ...headers } }, (res) => {
      let data = ''; res.on('data', (c) => { data += c; }); res.on('end', () => resolve({ status: res.statusCode, data }));
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

test('server rejects cross-site and rebinding requests', async (t) => {
  const child = spawn(process.execPath, [serve, '--port', String(PORT)], { stdio: ['ignore', 'pipe', 'pipe'] });
  t.after(() => child.kill());
  await new Promise((r) => child.stdout.once('data', r));
  assert.equal((await request('/api/health')).status, 200);
  assert.equal((await request('/api/health', { host: `evil.example:${PORT}` })).status, 403, 'foreign Host (DNS rebinding)');
  assert.equal((await request('/api/health', { headers: { origin: 'https://evil.example' } })).status, 403, 'foreign Origin');
  assert.equal((await request('/api/health', { headers: { 'sec-fetch-site': 'cross-site' } })).status, 403, 'cross-site fetch');
  const post = await request('/api/swatch', { method: 'POST', headers: { 'content-type': 'text/plain' }, body: '{}' });
  assert.equal(post.status, 403, 'simple (non-JSON) POST');
  const ok = await request('/api/swatch', { method: 'POST', headers: { 'content-type': 'application/json', origin: `http://127.0.0.1:${PORT}` }, body: '{}' });
  assert.equal(ok.status, 400, 'same-origin JSON reaches validation');
  assert.match((await request('/')).data, /roof-studio-server/, 'page is marked as served');
});
