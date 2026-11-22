#!/usr/bin/env node
// Roof layers in Blender: rebuild every roofing layer on a house model,
// apply supplier materials at real scale, and render high-resolution stills,
// the tear-off -> finish build animation, or the exploded layers view.
//
// Through blender-mcp (Blender open, addon connected on port 9876):
//   node roof-blender/scripts/roof-blender.mjs layers
//   node roof-blender/scripts/roof-blender.mjs material --image ~/swatches/charcoal.jpg --width-in 36
//   node roof-blender/scripts/roof-blender.mjs still --output ~/Desktop/roof.png --samples 256
// Headless (no UI, best for long renders or a render box):
//   node roof-blender/scripts/roof-blender.mjs video --blender /path/to/blender --file house.blend \
//        --plan roof-visualizer/viewer/plans/storm-replacement.json --output ~/Desktop/build.mp4
//
// Commands: demo | layers | material | scene | build | explode | still | video | exploded-video | export | all
// Run with --help for every option.

import net from 'node:net';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const CORE = path.join(here, 'roof_core.py');
const argv = process.argv.slice(2);
const cmd = argv[0] && !argv[0].startsWith('--') ? argv[0] : 'help';
const flags = {};
for (let i = cmd === 'help' ? 0 : 1; i < argv.length; i++) {
  if (!argv[i].startsWith('--')) continue;
  const key = argv[i].slice(2);
  const next = argv[i + 1];
  if (next === undefined || next.startsWith('--')) flags[key] = true; else { flags[key] = next; i++; }
}

const HELP = `roof-blender <command> [options]

Commands
  demo            build a demo house (roof object "Roof")              --pitch 6 --preset ranch-hip|two-story|cottage
  layers          rebuild all roofing layers on the roof               --roof <object> --ice-rows 2 --nails 4|6 --category shingle|metal --no-vent --no-old-roof
                                                                       --panel proRib|proSnap|corrugated|flat   metal panel ribs (default flat)
                                                                       --cap-width-in 11.5   metal hip/ridge cap product width (default 12)
                                                                       --edge "flange,face,kickOut,kickDown,hem"   drip-edge profile, inches
  material        supplier photo (or palette) on the shingles          --image <file> --width-in 36 [--height-in] [--rotation 0] [--relief 0.4] [--category metal]
                                                                       or --palette "#3a3d42,#2b2d30,#4d5157"
  scene           Cycles, physical sky, sun, camera                    --samples 256 --resolution 3840x2160 --sun-elevation 38 --sun-azimuth 215
                                                                       --view-azimuth -35 --view-elevation 24 --distance 1.0 --lens 35
  still           scene + one high-res render                          --output roof.png [--frame N]
  build           keyframe the build sequence                          --plan plan.json --speed 1 --fps 24 [--no-orbit]
  video           build + render frames + encode MP4                   --output build.mp4 [--speed 4] [--frame-step 2]
  exploded-video  exploded layers animation + MP4                      --output layers.mp4 --gap 0.8
  explode         set the exploded view (static)                       --gap 0.8 [--no-labels]
  export          GLB of the layers (and house) for the web viewer     --output roof-layers.glb
  all             demo if needed + layers + material + still           --output roof.png

Connection
  (default)       blender-mcp on localhost --port 9876
  --blender PATH  run Blender headless instead; --file house.blend to open, --save out.blend to keep the result
`;

if (cmd === 'help' || flags.help) { console.log(HELP); process.exit(0); }

const num = (k, d) => (flags[k] === undefined ? d : Number(flags[k]));
const res = String(flags.resolution || '3840x2160').split('x').map(Number);
const out = flags.output ? path.resolve(String(flags.output).replace(/^~/, os.homedir())) : null;
const sceneCfg = {
  cmd: 'scene', samples: num('samples', 192), resolution: res, sun_elevation: num('sun-elevation', 38), sun_azimuth: num('sun-azimuth', 215),
  view_azimuth: num('view-azimuth', -35), view_elevation: num('view-elevation', 24), distance: num('distance', 0.85), lens: num('lens', 35),
  percentage: num('percentage', 100),
};
const PANELS = ['proRib', 'proSnap', 'corrugated', 'flat'];
if (flags.panel !== undefined && !PANELS.includes(String(flags.panel))) { console.error(`--panel must be one of ${PANELS.join(', ')}`); process.exit(1); }
// --edge "flange,face,kickOut,kickDown,hem" in inches (lab experiment 020); values left out keep today's drip edge
const EDGE_KEYS = ['flange_in', 'face_in', 'kick_out_in', 'kick_down_in', 'hem_in'];
const edgeVals = flags.edge === undefined ? null : String(flags.edge).split(',').map((v) => v.trim()).filter((v) => v !== '').map(Number);
if (edgeVals && (!edgeVals.length || edgeVals.length > 5 || edgeVals.some((v) => !Number.isFinite(v) || v < 0))) {
  console.error('--edge takes up to five inch values: "flange,face,kickOut,kickDown,hem", e.g. "2.375,1.6875,0.5,0.25,0"'); process.exit(1);
}
const layersCfg = {
  cmd: 'layers', roof: flags.roof || null, ice_rows: num('ice-rows', 2), nails_per_shingle: num('nails', 4), category: flags.category || 'shingle',
  ridge_vent: !flags['no-vent'], old_roof: !flags['no-old-roof'], valleys: !flags['no-valleys'],
  exposure_in: num('exposure-in', 5.625), palette: flags.palette ? String(flags.palette).split(',') : null,
  panel: flags.panel ? String(flags.panel) : 'flat', cap_width_in: flags['cap-width-in'] !== undefined ? num('cap-width-in') : null,
  edge_profile: edgeVals ? Object.fromEntries(edgeVals.map((v, i) => [EDGE_KEYS[i], v])) : null,
};
const materialCfg = flags.image || flags.palette ? {
  cmd: 'material', image: flags.image ? path.resolve(String(flags.image).replace(/^~/, os.homedir())) : null, width_in: num('width-in', 36),
  height_in: num('height-in', 0), rotation: num('rotation', 0), relief: num('relief', 0.4), category: flags.category || 'shingle',
  palette: flags.palette ? String(flags.palette).split(',') : null,
} : null;
const plan = flags.plan ? JSON.parse(fs.readFileSync(path.resolve(String(flags.plan)), 'utf8')) : null;
const buildCfg = { cmd: 'build', plan, speed: num('speed', 1), fps: num('fps', 24), orbit: !flags['no-orbit'], orbit_degrees: num('orbit', 50) };

const framesDir = out ? path.join(path.dirname(out), `${path.basename(out, path.extname(out))}_frames`) : null;
const steps = {
  demo: [{ cmd: 'demo', pitch: num('pitch', 6), preset: flags.preset || 'ranch-hip' }],
  layers: [layersCfg],
  material: materialCfg ? [materialCfg] : [],
  scene: [sceneCfg],
  build: [buildCfg],
  explode: [{ cmd: 'explode', gap: num('gap', 0.8), animate: false, labels: !flags['no-labels'] }],
  still: [sceneCfg, { cmd: 'render', output: out || 'roof.png', frame: flags.frame !== undefined ? num('frame') : null }],
  video: [sceneCfg, buildCfg, { cmd: 'render', animation: true, output: framesDir, frame_step: num('frame-step', 1) }],
  'exploded-video': [{ cmd: 'explode', gap: num('gap', 0.8), animate: true, labels: !flags['no-labels'], hold_seconds: num('hold', 4) }, sceneCfg, { cmd: 'render', animation: true, output: framesDir, frame_step: num('frame-step', 1) }],
  export: [{ cmd: 'export', output: out || 'roof-layers.glb' }],
  all: [{ ...layersCfg, ...(materialCfg || {}), ...sceneCfg, cmd: 'all', output: out, mode: 'still' }],
};
if (!steps[cmd]) { console.error(`Unknown command "${cmd}".\n\n${HELP}`); process.exit(1); }
let cfgs = steps[cmd];
if (cmd === 'material' && !materialCfg) { console.error('material needs --image <file> or --palette "#hex,#hex"'); process.exit(1); }
if ((cmd === 'video' || cmd === 'exploded-video') && !out) { console.error(`${cmd} needs --output <file.mp4>`); process.exit(1); }
// a headless Blender starts from the .blend on disk, so build the stack first when it is missing
if (flags.blender && !['demo', 'layers', 'all', 'export'].includes(cmd)) {
  cfgs = [{ ...layersCfg, cmd: 'ensure', fresh: !flags.file, pitch: num('pitch', 6), preset: flags.preset || 'ranch-hip' }, ...(materialCfg && cmd !== 'material' ? [materialCfg] : []), ...cfgs];
}
if (flags.save) cfgs = [...cfgs, { cmd: 'save', path: path.resolve(String(flags.save)) }];

// ---------------------------------------------------------------------------

function viaMcp(configs) {
  const port = num('port', 9876);
  const code = `${fs.readFileSync(CORE, 'utf8')}\n\nrun(${JSON.stringify(JSON.stringify(configs))})\n`;
  return new Promise((resolve, reject) => {
    const sock = new net.Socket();
    sock.setTimeout(num('timeout', 3600) * 1000);
    let data = '';
    sock.connect(port, '127.0.0.1', () => sock.write(JSON.stringify({ type: 'execute_code', params: { code } })));
    sock.on('data', (c) => {
      data += c.toString();
      try { const r = JSON.parse(data); sock.destroy(); resolve(r); } catch { /* wait for the rest */ }
    });
    sock.on('timeout', () => { sock.destroy(); reject(new Error('Blender did not answer in time (use --blender for long renders).')); });
    sock.on('error', (e) => reject(new Error(`Could not reach blender-mcp on port ${port}: ${e.message}. Open Blender, connect the MCP addon, or pass --blender <path> to run headless.`)));
  }).then((r) => {
    if (r.status === 'error') {
      let msg = r.message || 'Blender reported an error';
      try { const j = JSON.parse(msg); msg = j.error || j.message || msg; } catch { /* plain text */ }
      throw new Error(msg);
    }
    const text = typeof r.result === 'string' ? r.result : r.result?.result || JSON.stringify(r.result || '');
    return text;
  });
}

function viaHeadless(configs) {
  const blender = String(flags.blender === true ? 'blender' : flags.blender);
  const cfgFile = path.join(os.tmpdir(), `roof-blender-${process.pid}.json`);
  fs.writeFileSync(cfgFile, JSON.stringify(configs));
  const args = ['-b'];
  if (flags.file) args.push(path.resolve(String(flags.file)));
  else args.push('--factory-startup');
  args.push('--python-exit-code', '1', '--python', CORE, '--', cfgFile); // a Python error must fail the run
  return new Promise((resolve, reject) => {
    const p = spawn(blender, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let text = '';
    p.stdout.on('data', (d) => { const s = d.toString(); text += s; s.split('\n').filter((l) => /^\[roof\]|Fra:\d+|Saved:/.test(l)).forEach((l) => console.log(l.trim().slice(0, 160))); });
    p.stderr.on('data', (d) => { text += d.toString(); });
    p.on('error', (e) => reject(new Error(`Could not start Blender at "${blender}": ${e.message}`)));
    p.on('close', (code) => { fs.rmSync(cfgFile, { force: true }); code === 0 ? resolve(text) : reject(new Error(`Blender exited with ${code}\n${text.split('\n').slice(-25).join('\n')}`)); });
  });
}

function encode(dir, file, fps, step = 1) {
  const frames = fs.readdirSync(dir).filter((f) => /^frame_\d+\.png$/.test(f)).sort();
  if (!frames.length) throw new Error(`No frames found in ${dir}`);
  // concat list: each rendered frame stands for `step` timeline frames, so playback speed stays right
  const list = path.join(dir, 'frames.txt');
  const dur = (step / fps).toFixed(6);
  fs.writeFileSync(list, frames.map((f) => `file '${f}'\nduration ${dur}`).join('\n') + `\nfile '${frames[frames.length - 1]}'\n`);
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-r', String(fps),
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '17', '-preset', 'slow', '-movflags', '+faststart', file], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error('ffmpeg failed (is it installed and on PATH?)');
  console.log(`Video: ${file} (${frames.length} rendered frames, ${(frames.length * step / fps).toFixed(1)} s at ${fps} fps)`);
}

(async () => {
  const text = flags.blender ? await viaHeadless(cfgs) : await viaMcp(cfgs);
  const results = text.split('\n').filter((l) => l.startsWith('RT_RESULT ')).map((l) => JSON.parse(l.slice(10)));
  if (!results.length) throw new Error(`Blender finished without a result. Last output:\n${text.split('\n').slice(-20).join('\n')}`);
  for (const r of results) console.log(JSON.stringify(r));
  if ((cmd === 'video' || cmd === 'exploded-video') && out) encode(framesDir, out, num('fps', 24), num('frame-step', 1));
})().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
