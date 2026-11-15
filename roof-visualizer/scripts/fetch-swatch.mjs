#!/usr/bin/env node
// Add a supplier product image to the Roof Layer Studio catalog.
//
//   node roof-visualizer/scripts/fetch-swatch.mjs --scan https://supplier.example/product
//       lists the product images found on a page
//   node roof-visualizer/scripts/fetch-swatch.mjs --image <image-url> --name "Product, Color" \
//       --supplier "Maker" [--category shingle|metal|tile|slate|shake] [--width-in 36] \
//       [--exposure-in 5.625] [--source <product page>] --rights "Brand portal, dealer agreement 2026"
//   node roof-visualizer/scripts/fetch-swatch.mjs --file ./photo.jpg --name "Job 1182 sample" --rights "Own photo"
//
// --rights is required: record where your permission to use the image comes from.

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { scanPage, saveSwatch } from './lib/supplier.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const VIEWER = path.resolve(here, '..', 'viewer');
const args = process.argv.slice(2);
const arg = (n, d) => { const i = args.indexOf(`--${n}`); return i === -1 ? d : args[i + 1]; };

async function main() {
  if (args.includes('--help') || !args.length) {
    console.log(fs.readFile ? (await fs.readFile(fileURLToPath(import.meta.url), 'utf8')).split('\n').slice(1, 14).map((l) => l.replace(/^\/\/ ?/, '')).join('\n') : '');
    return;
  }
  if (arg('scan')) {
    const r = await scanPage(arg('scan'));
    console.log(`${r.title || '(no title)'} · ${r.siteName}`);
    r.images.forEach((im, i) => console.log(`${String(i + 1).padStart(2)}. [${im.source}] ${im.url}${im.alt ? `  "${im.alt}"` : ''}`));
    return;
  }
  const body = {
    name: arg('name'), supplier: arg('supplier'), category: arg('category', 'shingle'),
    widthIn: Number(arg('width-in', 36)), heightIn: arg('height-in') ? Number(arg('height-in')) : undefined,
    exposureIn: arg('exposure-in') ? Number(arg('exposure-in')) : undefined,
    sourceUrl: arg('source'), rights: arg('rights'),
  };
  if (arg('image')) body.imageUrl = arg('image');
  else if (arg('file')) {
    const f = arg('file');
    const ext = path.extname(f).slice(1).toLowerCase().replace('jpg', 'jpeg');
    body.dataUrl = `data:image/${ext};base64,${(await fs.readFile(f)).toString('base64')}`;
    body.supplier = body.supplier || 'Own photo';
  } else throw new Error('Pass --image <url> or --file <path> (or --scan <page>).');
  const product = await saveSwatch(VIEWER, body);
  console.log(`Added ${product.name} (${product.id}) -> ${product.image}`);
  console.log(`Open the viewer with ?product=${product.id}`);
}

main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
