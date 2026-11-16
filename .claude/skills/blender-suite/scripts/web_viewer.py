#!/usr/bin/env python3
"""Write a standalone three.js viewer page for a GLB (orbit, auto-rotate, neutral lighting).

Host-side (system Python 3.9+, no bpy). By default the GLB is embedded, so the one HTML file opens by
double-click: browsers block loading a separate .glb from a file:// page. --no-embed keeps the GLB
separate for a web server. Materials are shown exactly as exported. Decoders for the meshopt, Draco
and KTX2 compression used by the web preset are included. three.js loads from a CDN, so viewing needs
internet access.
Usage:
  python web_viewer.py --glb export/scene.glb [--out export/scene.html] [--title "My Product"]
      [--bg "#111111"] [--no-rotate] [--no-embed]
Prints one JSON object. Exit code: 0 ok, 1 failed.
"""
import argparse
import base64
import html
import json
import os
import re
import struct
import sys

THREE = "0.170.0"
CDN = f"https://cdn.jsdelivr.net/npm/three@{THREE}"
EMBED_WARN_MB = 25

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: @@BG@@; }
  canvas { display: block; }
  #msg { position: fixed; inset: 0; display: grid; place-items: center; padding: 16px;
         color: #bbb; font: 15px system-ui, sans-serif; text-align: center; pointer-events: none; }
</style>
<script type="importmap">
{ "imports": { "three": "@@CDN@@/build/three.module.js", "three/addons/": "@@CDN@@/examples/jsm/" } }
</script>
</head>
<body data-state="loading">
<div id="msg">Loading model</div>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const GLB_BASE64 = "@@GLB_BASE64@@";
const GLB_URL = "@@GLB_URL@@";
const msg = document.getElementById('msg');

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.NeutralToneMapping;   // matches Khronos PBR Neutral in Blender
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('@@BG@@');
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;

const camera = new THREE.PerspectiveCamera(35, innerWidth / innerHeight, 0.01, 1000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = @@ROTATE@@;

const loader = new GLTFLoader();
loader.setDRACOLoader(new DRACOLoader().setDecoderPath('@@CDN@@/examples/jsm/libs/draco/gltf/'));
loader.setKTX2Loader(new KTX2Loader().setTranscoderPath('@@CDN@@/examples/jsm/libs/basis/').detectSupport(renderer));
loader.setMeshoptDecoder(MeshoptDecoder);

function show(gltf) {
  const model = gltf.scene;
  scene.add(model);
  const box = new THREE.Box3().setFromObject(model);
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1e-3);
  model.position.sub(box.getCenter(new THREE.Vector3()));
  const vfov = THREE.MathUtils.degToRad(camera.fov);
  const narrow = Math.min(vfov, 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect));
  const dist = radius / Math.sin(narrow / 2) * 1.15;
  camera.position.set(dist * 0.6, dist * 0.35, dist * 0.72);
  camera.near = dist / 100;
  camera.far = dist * 20;
  camera.updateProjectionMatrix();
  controls.update();
  msg.remove();
  let meshes = 0;
  model.traverse((o) => { if (o.isMesh) meshes++; });
  document.body.dataset.meshes = meshes;
  document.body.dataset.state = 'ready';
}

function fail(err) {
  console.error(err);
  msg.textContent = 'Could not load the model: ' + (err.message || err);
  document.body.dataset.state = 'error';
}

if (GLB_BASE64) {
  const bytes = Uint8Array.from(atob(GLB_BASE64), (c) => c.charCodeAt(0));
  loader.parse(bytes.buffer, '', show, fail);
} else {
  loader.load(GLB_URL, show, undefined, fail);
}

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});
</script>
</body>
</html>
"""


def glb_info(path):
    """Check the GLB header and read the extensions it uses."""
    with open(path, "rb") as f:
        head = f.read(20)
        if len(head) < 20 or head[:4] != b"glTF":
            raise ValueError(f"{path} is not a GLB")
        chunk_len = struct.unpack("<I", head[12:16])[0]
        doc = json.loads(f.read(chunk_len))
    return {"meshes": len(doc.get("meshes", [])), "extensions": doc.get("extensionsUsed", [])}


def run(glb=None, out=None, title=None, bg="#111111", no_rotate=False, no_embed=False, **_):
    if not glb:
        raise ValueError("--glb is required")
    if not re.fullmatch(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?", bg):
        raise ValueError("--bg must be a hex color such as #111111")
    info = glb_info(glb)
    out = out or os.path.splitext(glb)[0] + ".html"
    name = title or os.path.splitext(os.path.basename(glb))[0]
    size_mb = os.path.getsize(glb) / (1024 * 1024)
    warnings = []
    data, url = "", ""
    if no_embed:
        rel = os.path.relpath(os.path.abspath(glb), os.path.dirname(os.path.abspath(out)))
        url = "/".join(rel.split(os.sep))
        url = "".join(c if c.isalnum() or c in "-_./" else f"%{ord(c):02X}" for c in url)
        warnings.append("a separate GLB needs a web server; it won't load from a file:// page")
    else:
        with open(glb, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        if size_mb > EMBED_WARN_MB:
            warnings.append(f"{size_mb:.0f} MB embedded makes a slow page; compress it or use --no-embed")
    page = (PAGE.replace("@@TITLE@@", html.escape(name)).replace("@@BG@@", bg).replace("@@CDN@@", CDN)
            .replace("@@ROTATE@@", "false" if no_rotate else "true").replace("@@GLB_URL@@", url)
            .replace("@@GLB_BASE64@@", data))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    return {"ok": True, "html": out, "kb": round(os.path.getsize(out) / 1024, 1), "embedded": not no_embed,
            "three": THREE, "warnings": warnings, **info}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--glb", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--bg", default="#111111")
    p.add_argument("--no-rotate", action="store_true")
    p.add_argument("--no-embed", action="store_true")
    args = p.parse_args()
    try:
        result = run(**vars(args))
    except (ValueError, OSError) as e:
        result = {"ok": False, "error": str(e)}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
