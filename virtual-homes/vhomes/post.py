"""Raw pinhole render -> realistic phone / drone image (numpy + Pillow; no Blender needed).

1. Lens distortion: the raw render is an over-scanned pinhole image with the same focal length in pixels. Every
   output pixel is pulled from it through the inverse OPENCV model, so the final PNG has exactly the k1, k2, p1, p2
   written to cameras.json.
2. Optical blur (Gaussian), occasional hand-shake motion blur, sensor noise, 8-bit quantisation.
3. Metadata: noisy GPS / heading are written as PNG text chunks (``vhomes`` JSON) for tools that want them.
"""
from __future__ import annotations

import json
import math

import numpy as np

_MAP_CACHE = {}


def _undistort_norm(xd, yd, k, iters=12):
    x, y = xd.copy(), yd.copy()
    for _ in range(iters):
        r2 = x * x + y * y
        rad = 1 + k["k1"] * r2 + k["k2"] * r2 * r2
        dx = 2 * k["p1"] * x * y + k["p2"] * (r2 + 2 * x * x)
        dy = k["p1"] * (r2 + 2 * y * y) + 2 * k["p2"] * x * y
        x = (xd - dx) / rad
        y = (yd - dy) / rad
    return x, y


def overscan_pad(intr):
    """Pixels to add on each side of the raw render so every distorted output pixel has a source."""
    W, H = intr["width"], intr["height"]
    t = np.linspace(0, 1, 401)
    us = np.concatenate([t * W, t * W, np.zeros_like(t), np.full_like(t, W)])
    vs = np.concatenate([np.zeros_like(t), np.full_like(t, H), t * H, t * H])
    x, y = _undistort_norm((us - intr["cx"]) / intr["fx"], (vs - intr["cy"]) / intr["fy"], intr)
    px = int(math.ceil(max(0.0, np.max(np.abs(x)) * intr["fx"] - W / 2))) + 2
    py = int(math.ceil(max(0.0, np.max(np.abs(y)) * intr["fy"] - H / 2))) + 2
    return px, py


def _source_map(intr, pad):
    key = (intr["width"], intr["height"], intr["fx"], intr["k1"], intr["k2"], intr["p1"], intr["p2"], pad)
    if key in _MAP_CACHE:
        return _MAP_CACHE[key]
    W, H = intr["width"], intr["height"]
    u, v = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    x, y = _undistort_norm((u - intr["cx"]) / intr["fx"], (v - intr["cy"]) / intr["fy"], intr)
    Wr, Hr = W + 2 * pad[0], H + 2 * pad[1]
    su = intr["fx"] * x + Wr / 2.0 - 0.5          # continuous index (pixel centres at integers)
    sv = intr["fy"] * y + Hr / 2.0 - 0.5
    _MAP_CACHE[key] = (su.astype(np.float32), sv.astype(np.float32))
    return _MAP_CACHE[key]


def _bilinear(img, su, sv):
    H, W = img.shape[:2]
    x0 = np.clip(np.floor(su).astype(int), 0, W - 2); y0 = np.clip(np.floor(sv).astype(int), 0, H - 2)
    fx = np.clip(su - x0, 0, 1)[..., None]; fy = np.clip(sv - y0, 0, 1)[..., None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _motion_kernel_blur(img, length, angle_deg):
    n = max(2, int(round(length)))
    a = math.radians(angle_deg)
    acc = np.zeros_like(img)
    for i in range(n):
        s = i - (n - 1) / 2
        dx, dy = int(round(s * math.cos(a))), int(round(s * math.sin(a)))
        acc += np.roll(np.roll(img, dy, axis=0), dx, axis=1)
    return acc / n


def finish(raw_path, out_path, cam, pad, seed):
    from PIL import Image, ImageFilter
    from PIL.PngImagePlugin import PngInfo
    intr = cam["intrinsics"]
    raw = np.asarray(Image.open(raw_path).convert("RGB"), dtype=np.float32)
    su, sv = _source_map(intr, pad)
    img = _bilinear(raw, su, sv)
    if cam.get("motion_blur_px"):
        img = _motion_kernel_blur(img, cam["motion_blur_px"], cam["motion_blur_angle_deg"])
    pil = Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8))
    if cam.get("blur_sigma_px", 0) > 0.05:
        pil = pil.filter(ImageFilter.GaussianBlur(cam["blur_sigma_px"]))
    rng = np.random.default_rng(seed)
    out = np.asarray(pil, dtype=np.float32) + rng.normal(0, cam.get("noise_sigma", 0.0), (intr["height"], intr["width"], 1))
    pil = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))
    info = PngInfo()
    info.add_text("vhomes", json.dumps({"device": cam["device"], "metadata": cam["metadata"],
                                        "note": "metadata is noisy like a real device; true pose is in cameras.json"}))
    pil.save(out_path, pnginfo=info)
    return out_path
