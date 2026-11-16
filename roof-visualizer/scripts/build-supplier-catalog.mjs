#!/usr/bin/env node
// Build viewer/catalog/suppliers/sioux-falls.json from the two store captures.
//   node roof-visualizer/scripts/build-supplier-catalog.mjs \
//     --menards lab/data/suppliers/menards-3064-2026-11-15 \
//     --homedepot <materials.json> [--out roof-visualizer/viewer/catalog/suppliers/sioux-falls.json]
// Home Depot's materials.json is on branch claude/stoic-keller-boixwx (PR #3):
//   git show origin/claude/stoic-keller-boixwx:handoffs/sioux-falls-material-prices/homedepot/materials.json > out/hd.json
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { buildCatalog } from './lib/supplier-catalog.mjs';

const args = process.argv.slice(2);
const arg = (k) => { const i = args.indexOf(`--${k}`); return i >= 0 ? args[i + 1] : null; };
const here = path.dirname(fileURLToPath(import.meta.url));
const mdir = arg('menards'), hd = arg('homedepot');
const out = arg('out') || path.join(here, '..', 'viewer', 'catalog', 'suppliers', 'sioux-falls.json');
if (!mdir && !hd) {
  console.log('Usage: node build-supplier-catalog.mjs --menards <dir> --homedepot <materials.json> [--out file]');
  process.exit(1);
}
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex').slice(0, 16);
const read = (f) => fs.readFileSync(path.join(mdir, f), 'utf8');
const menards = mdir ? { products: read('products.csv'), variations: read('variations.csv'), materials: read('material_library.csv'), manifest: read('asset_manifest.csv') } : null;
const hdBuf = hd ? fs.readFileSync(hd) : null;
const sources = {};
if (mdir) sources.menards = { dir: path.relative(process.cwd(), mdir).split(path.sep).join('/'), productsSha256: sha(menards.products) };
if (hd) sources.homedepot = { file: 'handoffs/sioux-falls-material-prices/homedepot/materials.json (branch claude/stoic-keller-boixwx)', sha256: sha(hdBuf) };
const catalog = buildCatalog({ menards, homeDepot: hdBuf ? JSON.parse(hdBuf.toString('utf8')) : null, sources });
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(catalog));
const kb = (fs.statSync(out).size / 1024).toFixed(0);
console.log(`${catalog.products.length} products -> ${path.relative(process.cwd(), out)} (${kb} KB)`);
for (const [k, v] of Object.entries(catalog.counts).sort()) console.log(`  ${k.padEnd(28)} ${String(v.products).padStart(4)} products, ${String(v.priced).padStart(4)} priced`);
