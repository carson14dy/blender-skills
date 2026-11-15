#!/usr/bin/env node
// What can this machine run for the RoofTec lab, and what is missing?
//   node lab/tools/doctor.mjs
// Works on Windows, macOS and Linux. Prints a checklist and next steps; never installs anything.

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const rows = [];
const next = [];
const add = (ok, name, detail = '', hint = '') => { rows.push([ok, name, detail]); if (ok === false && hint) next.push(hint); };
const run = (cmd, args, opts = {}) => {
  try { return execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, ...opts }).trim(); } catch { return null; }
};

// Node
const nodeMajor = Number(process.versions.node.split('.')[0]);
add(nodeMajor >= 18, 'Node.js', process.versions.node, 'Install Node 18 or newer from https://nodejs.org');

// git branch
const branch = run('git', ['-C', root, 'branch', '--show-current']);
add(branch === 'rooftec-lab' ? true : branch ? null : false, 'Git branch', branch || 'not a git checkout', 'Run: git checkout rooftec-lab');

// GPU (best effort)
let gpu = null;
if (process.platform === 'win32') gpu = run('powershell', ['-NoProfile', '-Command', '(Get-CimInstance Win32_VideoController).Name -join ", "']);
else if (process.platform === 'darwin') gpu = run('bash', ['-c', "system_profiler SPDisplaysDataType | grep -E 'Chipset Model' | cut -d: -f2 | paste -sd, -"]);
else gpu = run('bash', ['-c', "(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || lspci 2>/dev/null | grep -iE 'vga|3d' | cut -d: -f3) | paste -sd, -"]);
add(gpu ? true : null, 'GPU', gpu || 'none found (cloud sessions render on the CPU)');

// ffmpeg
const ff = run('ffmpeg', ['-version']);
add(!!ff, 'ffmpeg', ff ? ff.split('\n')[0].replace('ffmpeg version ', '') : 'not on PATH', 'Install ffmpeg and add it to PATH (needed for build videos)');

// Blender executable
function findBlender() {
  const c = [];
  if (process.env.BLENDER) c.push(process.env.BLENDER);
  c.push('blender');
  if (process.platform === 'win32') {
    const base = 'C:\\Program Files\\Blender Foundation';
    try { for (const d of fs.readdirSync(base).sort().reverse()) c.push(path.join(base, d, 'blender.exe')); } catch { /* not installed there */ }
    const steam = 'C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe';
    c.push(steam);
  } else if (process.platform === 'darwin') c.push('/Applications/Blender.app/Contents/MacOS/Blender');
  else c.push('/usr/bin/blender', '/snap/bin/blender', '/opt/blender/blender');
  for (const exe of c) {
    const v = run(exe, ['--version'], { timeout: 60000 });
    if (v && /Blender \d/.test(v)) return { exe, version: v.split('\n').find((l) => /^Blender \d/.test(l)) };
  }
  return null;
}
const blender = findBlender();
add(blender ? true : null, 'Blender', blender ? `${blender.version} at ${blender.exe}` : 'not found (set BLENDER=<path to blender>)',
  'Install Blender 4.2 LTS or 5.x, or set BLENDER to its path');

// pip bpy (cloud sessions use this instead of a Blender install)
const py = process.env.LAB_BPY_PYTHON || path.join(os.homedir(), '.cache', 'rooftec-lab', 'bpyenv', process.platform === 'win32' ? 'Scripts\\python.exe' : 'bin/python');
const bpyV = fs.existsSync(py) ? run(py, ['-c', 'import bpy; print(bpy.app.version_string)'], { timeout: 120000 }) : null;
add(bpyV ? true : null, 'bpy (Python module)', bpyV ? `${bpyV} via ${py}` : 'not set up (only needed without a Blender install: bash lab/tools/setup-cloud.sh)');

// blender-mcp addon listening?
const mcp = await new Promise((res) => {
  const s = net.connect({ port: Number(process.env.BLENDER_MCP_PORT || 9876), host: '127.0.0.1' });
  s.setTimeout(1000);
  s.on('connect', () => { s.destroy(); res(true); });
  s.on('error', () => res(false));
  s.on('timeout', () => { s.destroy(); res(false); });
});
add(mcp ? true : null, 'blender-mcp on :9876', mcp ? 'listening' : 'not listening (open Blender, N panel > BlenderMCP > Connect)');

// roof-visualizer deps and Playwright
const rv = path.join(root, 'roof-visualizer');
add(fs.existsSync(path.join(rv, 'node_modules')) ? true : null, 'roof-visualizer npm install', fs.existsSync(path.join(rv, 'node_modules')) ? 'done' : 'not yet (only needed for Claude-written plans)');
let pw = null;
for (const base of [process.cwd(), rv, run('npm', ['root', '-g'], { shell: process.platform === 'win32' })].filter(Boolean)) {
  try { createRequire(path.join(base, 'x.js'))('playwright'); pw = base; break; } catch { /* try next */ }
}
add(pw ? true : null, 'Playwright (for lab/tools capture)', pw ? `found from ${pw}` : 'not installed (npm i -D playwright && npx playwright install chromium)');
add(process.env.ANTHROPIC_API_KEY ? true : null, 'ANTHROPIC_API_KEY', process.env.ANTHROPIC_API_KEY ? 'set' : 'not set (Claude-written build plans stay off)');

// print
const mark = (ok) => (ok === true ? 'OK ' : ok === false ? 'NO ' : ' - ');
console.log(`RoofTec lab doctor · ${os.type()} ${os.release()} · ${os.cpus()[0]?.model || ''}\n`);
for (const [ok, name, detail] of rows) console.log(`${mark(ok)} ${name.padEnd(34)} ${detail}`);
if (next.length) { console.log('\nTo fix:'); next.forEach((n) => console.log(`  - ${n}`)); }
console.log(`\nSession type: ${gpu && blender ? 'local (GPU + Blender): good for renders and timings' : 'cloud-like: good for code, tests and headless checks'}`);
