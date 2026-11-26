"""Camera rigs -> ground-truth poses + intrinsics (pure Python; no Blender needed).

Conventions written to cameras.json
* World frame: x east, y north, z up, metres, origin at the house centre on the ground; ``geo_origin`` gives the
  latitude / longitude / ellipsoid-free altitude of that origin (local tangent-plane approximation).
* Pose: OpenCV camera axes (x right, y down, z forward). ``R`` and ``t`` map world -> camera (x_c = R x_w + t), the
  COLMAP convention; ``center`` = -R^T t; ``qvec`` = (w, x, y, z) of R. ``blender_matrix_world`` is the same pose
  for a Blender camera (looks down -Z, +Y up).
* Intrinsics: OPENCV model (fx, fy, cx, cy, k1, k2, p1, p2) in pixels of the FINAL image. Pixel centres sit at
  (i + 0.5, j + 0.5), so the principal point of a centred camera is (W/2, H/2) (COLMAP convention).
  The rendered PNGs really carry that distortion (``post.py`` warps an over-scanned pinhole render).
* ``metadata`` is what a real device would record: GPS with realistic error, compass heading, IMU tilt. Never use
  it as ground truth; ``pose`` is the truth.
"""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Point, Polygon

from .spec import DRONES, PHONES

FULL_FRAME_DIAG_MM = math.hypot(36.0, 24.0)
EARTH_R = 6378137.0


# ---------------------------------------------------------------------------------------------------------------
# intrinsics and poses

def make_intrinsics(equiv_mm, width, height, dist):
    """35 mm-equivalent focal length (defined on the diagonal) -> pixel focal length for this image size."""
    f = math.hypot(width, height) * equiv_mm / FULL_FRAME_DIAG_MM
    return {"model": "OPENCV", "width": int(width), "height": int(height), "fx": f, "fy": f,
            "cx": width / 2.0, "cy": height / 2.0, **dist, "equiv_focal_mm": equiv_mm,
            "hfov_deg": math.degrees(2 * math.atan(width / 2.0 / f))}


def look_at(center, target, roll_deg=0.0):
    """World->camera rotation (OpenCV axes) for a camera at ``center`` looking at ``target``."""
    c, t = np.asarray(center, float), np.asarray(target, float)
    f = t - c
    f /= np.linalg.norm(f)
    r = np.cross(f, [0.0, 0.0, 1.0])
    if np.linalg.norm(r) < 1e-6:                     # looking straight down / up: keep image "up" = north
        r = np.cross(f, [0.0, 1.0, 0.0])
    r /= np.linalg.norm(r)
    d = np.cross(f, r)                               # image down
    a = math.radians(roll_deg)
    r2 = math.cos(a) * r + math.sin(a) * d
    d2 = -math.sin(a) * r + math.cos(a) * d
    return np.stack([r2, d2, f])                     # rows = camera axes in world coords


def rot_to_qvec(R):
    R = np.asarray(R, float)
    w = math.sqrt(max(0.0, 1.0 + R[0, 0] + R[1, 1] + R[2, 2])) / 2.0
    if w > 1e-6:
        return [w, (R[2, 1] - R[1, 2]) / (4 * w), (R[0, 2] - R[2, 0]) / (4 * w), (R[1, 0] - R[0, 1]) / (4 * w)]
    i = int(np.argmax(np.diag(R)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(max(0.0, 1.0 + R[i, i] - R[j, j] - R[k, k])) * 2
    q = [0.0, 0.0, 0.0, 0.0]
    q[0] = (R[k, j] - R[j, k]) / s
    q[1 + i] = s / 4
    q[1 + j] = (R[j, i] + R[i, j]) / s
    q[1 + k] = (R[k, i] + R[i, k]) / s
    return q


def pose_dict(center, R):
    c = np.asarray(center, float)
    t = -R @ c
    c2w = np.eye(4); c2w[:3, :3] = R.T; c2w[:3, 3] = c
    bl = np.eye(4); bl[:3, :3] = R.T @ np.diag([1.0, -1.0, -1.0]); bl[:3, 3] = c
    return {"center": c.tolist(), "R": R.tolist(), "t": t.tolist(), "qvec": rot_to_qvec(R),
            "c2w_opencv": c2w.tolist(), "blender_matrix_world": bl.tolist()}


def project(points, cam):
    """Project world points with the camera's full OPENCV model -> pixel coords (N, 2) and depth (N,)."""
    P = np.atleast_2d(np.asarray(points, float))
    R, t = np.asarray(cam["pose"]["R"]), np.asarray(cam["pose"]["t"])
    X = P @ R.T + t
    z = X[:, 2]
    x, y = X[:, 0] / z, X[:, 1] / z
    k = cam["intrinsics"]
    r2 = x * x + y * y
    rad = 1 + k["k1"] * r2 + k["k2"] * r2 * r2
    xd = x * rad + 2 * k["p1"] * x * y + k["p2"] * (r2 + 2 * x * x)
    yd = y * rad + k["p1"] * (r2 + 2 * y * y) + 2 * k["p2"] * x * y
    return np.stack([k["fx"] * xd + k["cx"], k["fy"] * yd + k["cy"]], axis=1), z


def enu_to_geo(p, origin):
    lat0 = math.radians(origin["lat"])
    return (origin["lat"] + math.degrees(p[1] / EARTH_R),
            origin["lon"] + math.degrees(p[0] / (EARTH_R * math.cos(lat0))),
            origin["ground_alt_m"] + p[2])


# ---------------------------------------------------------------------------------------------------------------
# rigs

def _device_distortion(rng, kind):
    if kind == "phone":
        return {"k1": float(rng.uniform(-0.05, 0.03)), "k2": float(rng.uniform(-0.02, 0.03)),
                "p1": float(rng.uniform(-5e-4, 5e-4)), "p2": float(rng.uniform(-5e-4, 5e-4))}
    return {"k1": float(rng.uniform(-0.03, 0.01)), "k2": float(rng.uniform(-0.01, 0.01)),
            "p1": float(rng.uniform(-2e-4, 2e-4)), "p2": float(rng.uniform(-2e-4, 2e-4))}


def _scaled_res(full_res, long_side):
    w, h = full_res
    if long_side is None or long_side >= max(w, h):
        return w, h
    s = long_side / max(w, h)
    return int(round(w * s / 2) * 2), int(round(h * s / 2) * 2)


def _image_effects(rng, kind, blur_scale):
    e = {"exposure_ev": float(np.clip(rng.normal(0, 0.25 if kind == "phone" else 0.12), -0.6, 0.6)),
         "blur_sigma_px": float(abs(rng.normal(0, 0.45)) * blur_scale),
         "noise_sigma": float(rng.uniform(1.0, 2.5) if kind == "phone" else rng.uniform(0.6, 1.4))}
    if kind == "phone" and rng.random() < 0.12:
        e["motion_blur_px"] = float(rng.uniform(2.0, 6.0) * blur_scale)
        e["motion_blur_angle_deg"] = float(rng.uniform(0, 180))
    return e


def _metadata(rng, center, R, geo, gps_bias, kind):
    sh, sv = (1.0, 2.0) if kind == "phone" else (0.4, 0.8)
    noisy = np.asarray(center) + gps_bias + np.array([rng.normal(0, sh), rng.normal(0, sh), rng.normal(0, sv)])
    lat, lon, alt = enu_to_geo(noisy, geo)
    f = np.asarray(R)[2]
    heading = (math.degrees(math.atan2(f[0], f[1])) + rng.normal(0, 6.0 if kind == "phone" else 2.0)) % 360
    pitch = math.degrees(math.asin(np.clip(-f[2], -1, 1))) + rng.normal(0, 1.0)
    return {"gps_lat": lat, "gps_lon": lon, "gps_alt_m": alt,
            "gps_error_m": (noisy - np.asarray(center)).tolist(),
            "gps_sigma_m": {"horizontal": float(math.hypot(gps_bias[0], gps_bias[1]) + sh), "vertical": sv},
            "compass_heading_deg": heading, "camera_pitch_down_deg": pitch}


def _cam(rig, idx, device_name, intr, center, target, roll, rng, geo, gps_bias, kind, blur_scale, **extra):
    R = look_at(center, target, roll)
    return {"image": f"renders/{rig}/{rig}_{idx:03d}.png", "rig": rig, "index": idx, "device": device_name,
            "intrinsics": intr, "pose": pose_dict(center, R), "look_at": list(map(float, target)),
            "roll_deg": float(roll), **_image_effects(rng, kind, blur_scale),
            "metadata": _metadata(rng, center, R, geo, gps_bias, kind), **extra}


def ground_rig(house, rng, n, intr, dev, geo, blur_scale):
    w = house["spec"]["wings"][0]
    half_diag = 0.5 * math.hypot(w["length"] + 2 * w["rake_overhang"], w["width"] + 2 * w["eave_overhang"])
    plate, top = house["heights"]["plate_m"], house["heights"]["max_m"]
    bias = np.array([rng.normal(0, 2.0), rng.normal(0, 2.0), rng.normal(0, 3.0)])
    start = rng.uniform(0, 2 * math.pi)
    cams = []
    for i in range(n):
        a = start + 2 * math.pi * i / n + rng.uniform(-0.3, 0.3) * 2 * math.pi / n
        r = half_diag + rng.uniform(4.0, 12.0)
        c = np.array([r * math.sin(a), r * math.cos(a), rng.uniform(1.45, 1.75)])
        tgt = np.array([rng.uniform(-w["length"] / 4, w["length"] / 4) * 0.5,
                        rng.uniform(-w["width"] / 4, w["width"] / 4) * 0.5, rng.uniform(plate - 0.8, top)])
        roll = float(np.clip(rng.normal(0, 1.5), -3, 3))
        cams.append(_cam("ground", i, dev, intr, c, tgt, roll, rng, geo, bias, "phone", blur_scale))
    return cams


def roof_rig(house, rng, n, intr, dev, geo, blur_scale, walkable_x12=8.0):
    facets = [f for f in house["facets"] if not f["hidden_from_above"]]
    polys = {f["id"]: Polygon([p[:2] for p in f["rings"][0]["outer"]]) for f in facets}
    areas = np.array([polys[f["id"]].area for f in facets])
    alloc = np.maximum(1, np.round(n * areas / areas.sum())).astype(int)
    while alloc.sum() > n:
        alloc[int(np.argmax(alloc))] -= 1
    bias = np.array([rng.normal(0, 2.0), rng.normal(0, 2.0), rng.normal(0, 3.0)])
    pts_of_interest = [np.array(d["center"]) for d in house["details"]] + \
                      [np.array(m["center"]) for m in house["markers"] if m["id"] == "roof"]
    cams, idx = [], 0
    for f, k in zip(facets, alloc):
        a, b, c0 = f["plane"]
        slope = math.hypot(a, b)
        e = np.array(f["frame"]["eave"]); up = np.array(f["frame"]["up"])
        up_plan = np.array([up[0], up[1], 0.0]); up_plan /= max(np.linalg.norm(up_plan), 1e-9)
        inner = polys[f["id"]].buffer(-0.8)
        x0, y0, x1, y1 = inner.bounds
        zmax = max(p[2] for p in f["rings"][0]["outer"])
        walk = slope * 12 <= walkable_x12
        for j in range(int(k)):
            if walk:
                for _ in range(200):
                    p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
                    if inner.contains(Point(p)):
                        break
                foot = np.array([p[0], p[1], a * p[0] + b * p[1] + c0])
                eye = foot + np.array([0, 0, rng.uniform(1.45, 1.70)])
                mode = rng.choice(["down", "across", "up", "detail", "feet"], p=[0.3, 0.25, 0.15, 0.15, 0.15])
                if mode == "detail" and pts_of_interest:
                    tgt = pts_of_interest[int(rng.integers(len(pts_of_interest)))]
                    if np.linalg.norm(tgt[:2] - eye[:2]) < 0.8:
                        mode = "down"
                if mode == "down":
                    tgt = foot - up_plan * rng.uniform(2.5, 5.0); tgt[2] = foot[2] - rng.uniform(1.0, 2.5)
                elif mode == "across":
                    tgt = foot + e * rng.choice([-1, 1]) * rng.uniform(4, 8); tgt[2] = foot[2] - rng.uniform(0.3, 1.2)
                elif mode == "up":
                    tgt = foot + up_plan * rng.uniform(2.0, 4.0); tgt[2] = zmax + rng.uniform(-0.3, 0.5)
                elif mode == "feet":
                    tgt = foot + up_plan * rng.uniform(-1.0, 1.0) + e * rng.uniform(-1, 1); tgt[2] = foot[2] - 0.1
                roll = float(np.clip(rng.normal(0, 2.0), -4, 4))
                cams.append(_cam("roof", idx, dev, intr, eye, tgt, roll, rng, geo, bias, "phone", blur_scale,
                                 facet=f["id"], shot=str(mode), standing_on_roof=True))
            else:
                # too steep to walk: ladder shots from the eave looking up the facet
                eaves = [np.array(v) for v in f["rings"][0]["outer"] if abs(v[2] - min(q[2] for q in f["rings"][0]["outer"])) < 1e-6]
                p0, p1 = eaves[0], eaves[-1]
                s = rng.uniform(0.15, 0.85)
                base = p0 + (p1 - p0) * s
                eye = base - up_plan * rng.uniform(0.4, 0.9) + np.array([0, 0, rng.uniform(0.3, 0.8)])
                tgt = base + up_plan * rng.uniform(2.0, 5.0); tgt[2] = base[2] + slope * np.linalg.norm(tgt[:2] - base[:2])
                roll = float(np.clip(rng.normal(0, 2.0), -4, 4))
                cams.append(_cam("roof", idx, dev, intr, eye, tgt, roll, rng, geo, bias, "phone", blur_scale,
                                 facet=f["id"], shot="ladder", standing_on_roof=False))
            idx += 1
    return cams


def drone_rig(house, rng, intr, dev, geo, blur_scale, alt=35.0, overlap=0.75, orbit_n=24, low_n=16):
    w = house["spec"]["wings"][0]
    half_diag = 0.5 * math.hypot(w["length"] + 2 * w["rake_overhang"], w["width"] + 2 * w["eave_overhang"])
    top = house["heights"]["max_m"]
    bias = np.array([rng.normal(0, 0.7), rng.normal(0, 0.7), rng.normal(0, 1.0)])
    fx = intr["fx"]
    gw = intr["width"] / fx * (alt - top)            # ground footprint at roof height
    gh = intr["height"] / fx * (alt - top)
    ext = half_diag + 4.0
    sx, sy = gw * (1 - overlap), gh * (1 - overlap)
    xs = np.arange(-ext, ext + 1e-6, sx); ys = np.arange(-ext, ext + 1e-6, sy)
    cams, idx = [], 0
    for j, y in enumerate(ys):                       # lawn-mower pattern, north-up images
        row = xs if j % 2 == 0 else xs[::-1]
        for x in row:
            c = np.array([x + rng.normal(0, 0.15), y + rng.normal(0, 0.15), alt + rng.normal(0, 0.2)])
            tgt = c - np.array([0, 0, 10.0])
            cams.append(_cam("drone", idx, dev, intr, c, tgt, float(rng.normal(0, 0.3)), rng, geo, bias, "drone",
                             blur_scale, shot="nadir"))
            idx += 1
    for ring, (n, radius, height) in enumerate(((orbit_n, max(1.6 * half_diag, 18.0), 25.0),
                                                (low_n, max(1.3 * half_diag, 14.0), 12.0))):
        a0 = rng.uniform(0, 2 * math.pi)
        for i in range(n):
            a = a0 + 2 * math.pi * i / n
            c = np.array([radius * math.sin(a), radius * math.cos(a), height + rng.normal(0, 0.3)])
            tgt = np.array([rng.normal(0, 0.5), rng.normal(0, 0.5), top * 0.6])
            cams.append(_cam("drone", idx, dev, intr, c, tgt, float(rng.normal(0, 0.3)), rng, geo, bias, "drone",
                             blur_scale, shot=f"orbit{ring}"))
            idx += 1
    return cams


def make_cameras(house, long_side=None, n_ground=40, n_roof=60, rigs=("ground", "roof", "drone")):
    spec = house["spec"]
    rng = np.random.default_rng(spec["seed"] + 15485863)
    phone_name = spec["capture"]["phone"]; drone_name = spec["capture"]["drone"]
    phone, drone = PHONES[phone_name], DRONES[drone_name]
    pw, ph = _scaled_res(phone["full_res"], long_side)
    dw, dh = _scaled_res(drone["full_res"], long_side)
    blur_p = pw / phone["full_res"][0]
    blur_d = dw / drone["full_res"][0]
    pi = make_intrinsics(phone["equiv_mm"], pw, ph, _device_distortion(rng, "phone"))
    di = make_intrinsics(drone["equiv_mm"], dw, dh, _device_distortion(rng, "drone"))
    geo = spec["site"]
    out = []
    # each rig draws from its own sub-stream so changing one rig's count never moves another rig's cameras
    if "ground" in rigs:
        out += ground_rig(house, np.random.default_rng([spec["seed"], 1]), n_ground, pi, phone_name, geo, blur_p)
    if "roof" in rigs:
        out += roof_rig(house, np.random.default_rng([spec["seed"], 2]), n_roof, pi, phone_name, geo, blur_p)
    if "drone" in rigs:
        out += drone_rig(house, np.random.default_rng([spec["seed"], 3]), di, drone_name, geo, blur_d)
    return {
        "schema": "vhomes.cameras/1",
        "house_id": spec["house_id"],
        "conventions": __doc__.split("Conventions written to cameras.json", 1)[1].strip(),
        "geo_origin": {"lat": geo["lat"], "lon": geo["lon"], "ground_alt_m": geo["ground_alt_m"],
                       "frame": "local east-north-up tangent plane at the origin"},
        "sun": spec["lighting"],
        "devices": {phone_name: {"kind": "phone", **pi}, drone_name: {"kind": "drone", **di}},
        "cameras": out,
    }
