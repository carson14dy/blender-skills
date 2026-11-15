// Rendering quality: physically placed sun, analytic sky / HDRI environment,
// tiled high-resolution snapshots, and an optional progressive path tracer
// (three-gpu-pathtracer, MIT) for photoreal stills.

import * as THREE from 'three';

const DEG = Math.PI / 180;

/**
 * Sun position from latitude, day of year and local *solar* time.
 * @returns {{azimuth:number, elevation:number}} degrees; azimuth clockwise from north
 */
export function sunPosition(latDeg, dayOfYear, solarHour) {
  const g = (2 * Math.PI / 365) * (dayOfYear - 1 + (solarHour - 12) / 24);
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g)
    + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  const lat = latDeg * DEG;
  const ha = (solarHour - 12) * 15 * DEG;
  const sinEl = Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(ha);
  const el = Math.asin(Math.max(-1, Math.min(1, sinEl)));
  const az = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat)) + Math.PI;
  return { azimuth: (az / DEG + 360) % 360, elevation: el / DEG };
}

/** World direction (unit vector toward the sun). House front (+Z) faces compass bearing `facingDeg`. */
export function sunDirection({ azimuth, elevation }, facingDeg = 180) {
  const th = (azimuth - facingDeg) * DEG;
  const el = elevation * DEG;
  return new THREE.Vector3(-Math.sin(th) * Math.cos(el), Math.sin(el), Math.cos(th) * Math.cos(el)).normalize();
}

export function dayOfYear(date = new Date()) {
  const start = Date.UTC(date.getFullYear(), 0, 0);
  return Math.floor((Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - start) / 864e5);
}

/**
 * Analytic daylight sky as a float equirect texture. Works as a raster
 * background, as a PMREM source, and as a path tracer environment.
 * The sun disc itself is left out: the DirectionalLight carries the sun.
 */
export function makeSkyTexture(sunDir, { width = 1024, height = 512, haze = 0.35, saturation = 1 } = {}) {
  const data = new Float32Array(width * height * 4);
  const el = Math.asin(sunDir.y);
  const day = THREE.MathUtils.smoothstep(el, -0.08, 0.25);
  const golden = 1 - THREE.MathUtils.smoothstep(el, 0.02, 0.35);
  const zenith = new THREE.Color(0.20, 0.36, 0.66).multiplyScalar(0.25 + 0.75 * day);
  const horizon = new THREE.Color(0.80, 0.85, 0.90).lerp(new THREE.Color(0.98, 0.70, 0.48), golden * 0.7).multiplyScalar(0.3 + 0.7 * day);
  const ground = new THREE.Color(0.30, 0.29, 0.24).multiplyScalar(0.25 + 0.75 * day);
  const d = new THREE.Vector3(), c = new THREE.Color();
  for (let j = 0; j < height; j++) {
    const th = ((j + 0.5) / height - 0.5) * Math.PI;
    for (let i = 0; i < width; i++) {
      const ph = ((i + 0.5) / width - 0.5) * 2 * Math.PI;
      d.set(Math.cos(th) * Math.cos(ph), Math.sin(th), Math.cos(th) * Math.sin(ph));
      const cosA = Math.max(0, d.dot(sunDir));
      if (d.y >= 0) {
        const t = Math.pow(1 - d.y, 3 + haze * 3);
        c.copy(zenith).lerp(horizon, t);
        const glow = 0.9 * Math.pow(cosA, 48) + 0.28 * Math.pow(cosA, 6) * (0.5 + golden);
        c.r += glow * 1.0 * day; c.g += glow * 0.86 * day; c.b += glow * 0.66 * day;
      } else {
        const t = Math.min(1, -d.y * 6);
        c.copy(horizon).lerp(ground, t);
      }
      if (saturation !== 1) { const l = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b; c.r = l + (c.r - l) * saturation; c.g = l + (c.g - l) * saturation; c.b = l + (c.b - l) * saturation; }
      const k = (j * width + i) * 4;
      data[k] = c.r; data[k + 1] = c.g; data[k + 2] = c.b; data[k + 3] = 1;
    }
  }
  const tex = new THREE.DataTexture(data, width, height, THREE.RGBAFormat, THREE.FloatType);
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.colorSpace = THREE.LinearSRGBColorSpace;
  tex.minFilter = THREE.LinearFilter; tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

/** Fit a directional light's shadow camera tightly around `box`. */
export function fitShadow(light, box, sunDir, mapSize = 4096) {
  const center = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2;
  light.position.copy(center).addScaledVector(sunDir, radius * 3);
  light.target.position.copy(center);
  const cam = light.shadow.camera;
  cam.left = -radius; cam.right = radius; cam.top = radius; cam.bottom = -radius;
  cam.near = radius * 0.5; cam.far = radius * 6;
  cam.updateProjectionMatrix();
  light.shadow.mapSize.set(mapSize, mapSize);
  light.shadow.bias = -0.00015;
  light.shadow.normalBias = 0.015;
  light.shadow.map?.dispose(); light.shadow.map = null;
}

// ---------------------------------------------------------------------------
// High-resolution snapshot

/**
 * Render `width x height` in tiles (no GPU size limit), burn in visible layer
 * labels, and return a PNG Blob.
 */
export async function snapshot({ renderer, scene, camera, width, height, tile = 2048, overlay = null, beforeTile, pathTracer = null, samples = 64, onProgress }) {
  const out = document.createElement('canvas');
  out.width = width; out.height = height;
  const ctx = out.getContext('2d');
  const prevSize = renderer.getSize(new THREE.Vector2());
  const prevPR = renderer.getPixelRatio();
  const prevAspect = camera.aspect;
  renderer.setPixelRatio(1);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  try {
    if (pathTracer) {
      // path tracing renders the whole frame at once, clamped to the GPU limit
      const max = Math.min(renderer.capabilities.maxTextureSize, 8192);
      const k = Math.min(1, max / Math.max(width, height));
      const w = Math.floor(width * k), h = Math.floor(height * k);
      renderer.setSize(w, h, false);
      pathTracer.updateCamera();
      pathTracer.reset();
      while (pathTracer.samples < samples) {
        pathTracer.render();
        onProgress?.(Math.min(1, pathTracer.samples / samples));
        await new Promise((r) => requestAnimationFrame(r));
      }
      ctx.drawImage(renderer.domElement, 0, 0, w, h, 0, 0, width, height);
    } else {
      const tw = Math.min(tile, width), th = Math.min(tile, height);
      const nx = Math.ceil(width / tw), ny = Math.ceil(height / th);
      let done = 0;
      for (let y = 0; y < height; y += th) {
        for (let x = 0; x < width; x += tw) {
          const w = Math.min(tw, width - x), h = Math.min(th, height - y);
          renderer.setSize(w, h, false);
          camera.setViewOffset(width, height, x, y, w, h);
          beforeTile?.();
          renderer.render(scene, camera);
          ctx.drawImage(renderer.domElement, 0, 0, w, h, x, y, w, h);
          onProgress?.(++done / (nx * ny));
          await new Promise((r) => setTimeout(r, 0));
        }
      }
      camera.clearViewOffset();
    }
    overlay?.(ctx, width, height);
  } finally {
    camera.clearViewOffset();
    camera.aspect = prevAspect;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(prevPR);
    renderer.setSize(prevSize.x, prevSize.y, false);
    pathTracer?.updateCamera();
  }
  return await new Promise((res) => out.toBlob(res, 'image/png'));
}

// ---------------------------------------------------------------------------
// Path tracing

export class PathTraceMode {
  constructor(renderer, scene, camera) {
    this.renderer = renderer; this.scene = scene; this.camera = camera;
    this.pt = null; this.enabled = false; this._swapped = [];
  }

  get samples() { return this.pt ? Math.floor(this.pt.samples) : 0; }

  async enable({ envTexture } = {}) {
    if (!this.pt) {
      const mod = await import('three-gpu-pathtracer');
      this.pt = new mod.WebGLPathTracer(this.renderer);
      this.pt.tiles.set(2, 2);
      this.pt.filterGlossyFactor = 0.5;
      this.pt.minSamples = 1;
      this.pt.renderDelay = 0;
      this.pt.fadeDuration = 250;
      this.pt.bounces = 6;
    }
    this.envTexture = envTexture;
    this.enabled = true;
    this.rebuild();
  }

  /** Replace instanced meshes with merged meshes (the path tracer needs plain meshes). */
  _swapInstanced() {
    this._restoreInstanced();
    this.scene.traverse((o) => {
      if (!o.isInstancedMesh || !o.visible || o.count === 0) return;
      const src = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry;
      const n = o.count, vc = src.attributes.position.count;
      const pos = new Float32Array(n * vc * 3), nor = new Float32Array(n * vc * 3);
      const m = new THREE.Matrix4(), nm = new THREE.Matrix3(), v = new THREE.Vector3();
      for (let i = 0; i < n; i++) {
        o.getMatrixAt(i, m); nm.getNormalMatrix(m);
        for (let k = 0; k < vc; k++) {
          v.fromBufferAttribute(src.attributes.position, k).applyMatrix4(m); pos.set([v.x, v.y, v.z], (i * vc + k) * 3);
          v.fromBufferAttribute(src.attributes.normal, k).applyMatrix3(nm).normalize(); nor.set([v.x, v.y, v.z], (i * vc + k) * 3);
        }
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
      const mesh = new THREE.Mesh(g, o.material);
      mesh.matrixAutoUpdate = false; mesh.matrix.copy(o.matrix);
      o.parent.add(mesh);
      o.visible = false;
      this._swapped.push({ inst: o, mesh });
    });
  }

  _restoreInstanced() {
    for (const { inst, mesh } of this._swapped) { inst.visible = true; mesh.parent?.remove(mesh); mesh.geometry.dispose(); }
    this._swapped = [];
  }

  rebuild() {
    if (!this.enabled || !this.pt) return;
    this._savedEnv = this._savedEnv || { env: this.scene.environment, bg: this.scene.background };
    if (this.envTexture) { this.scene.environment = this.envTexture; this.scene.background = this.envTexture; }
    this._swapInstanced();
    this.scene.updateMatrixWorld(true);
    this.pt.setScene(this.scene, this.camera);
    this._restoreInstancedVisibilityOnly();
  }

  // keep merged meshes in the path-traced scene but let the raster view keep using instancing
  _restoreInstancedVisibilityOnly() {
    for (const { inst, mesh } of this._swapped) { inst.visible = true; mesh.visible = false; }
  }

  render() {
    if (!this.enabled || !this.pt) return;
    // swap visibility while sampling
    for (const { inst, mesh } of this._swapped) { inst.visible = false; mesh.visible = true; }
    this.pt.renderSample();
    for (const { inst, mesh } of this._swapped) { inst.visible = true; mesh.visible = false; }
  }

  updateCamera() { this.pt?.updateCamera(); }
  updateMaterials() { this.pt?.updateMaterials(); }
  updateLights() { this.pt?.updateLights(); }
  reset() { this.pt?.reset(); }

  disable() {
    this.enabled = false;
    this._restoreInstanced();
    if (this._savedEnv) { this.scene.environment = this._savedEnv.env; this.scene.background = this._savedEnv.bg; this._savedEnv = null; }
  }
}
