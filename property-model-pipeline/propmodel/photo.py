"""Inspection-photo metrology.

1. ``exif(path)``           camera intrinsics, GPS, DJI drone XMP (altitude, gimbal angles).
2. ``gsd(...)``             ground sample distance of nadir drone photos (m / pixel).
3. ``Rectifier``            plane rectification from >= 4 points with known plane coordinates
                            (door, garage door, window, siding courses, brick, a tape in frame):
                            measure anything else on the SAME plane, with Monte-Carlo sigma.
4. ``solve_camera``         camera pose from >= 6 2-D/3-D correspondences (photo <-> model or
                            survey points) -> reprojection error, Blender camera match, and
                            photo-to-model overlay QA.

Known references (US residential, nominal; verify on site when possible):
  exterior door 36 x 80 in (0.914 x 2.032 m) slab; garage door 16 x 7 ft or 8/9 x 7 ft;
  3-tab / architectural shingle exposure 5 in (5-5/8 in for metric-size laminated);
  brick course (modular) 2-2/3 in (3 courses = 8 in); CMU course 8 in;
  lap siding exposure 4, 5, 6 or 7 in (measure one); standard ceiling plate 8 / 9 ft.
"""
from __future__ import annotations

import math
import re

import numpy as np

DIAG_35MM = math.hypot(36.0, 24.0)  # 43.27 mm


# ---------------------------------------------------------------------------
# EXIF / XMP
# ---------------------------------------------------------------------------

def _rat(v):
    try:
        return float(v)
    except TypeError:
        return float(v[0]) / float(v[1])


def _dms(vals, ref):
    d, m, s = (_rat(x) for x in vals)
    out = d + m / 60 + s / 3600
    return -out if ref in ("S", "W") else out


def exif(path):
    from PIL import Image
    img = Image.open(path)
    W, H = img.size
    ex = img.getexif()
    sub = ex.get_ifd(0x8769)
    gps = ex.get_ifd(0x8825)
    info = {"path": path, "width": W, "height": H, "make": ex.get(0x010F), "model": ex.get(0x0110),
            "datetime": sub.get(0x9003) or ex.get(0x0132)}
    f_mm = sub.get(0x920A)
    f35 = sub.get(0xA405)
    info["focal_mm"] = _rat(f_mm) if f_mm else None
    info["focal_35mm"] = float(f35) if f35 else None
    fpx_res, fp_unit = sub.get(0xA20E), sub.get(0xA210)
    fx = None
    if info["focal_35mm"]:
        fx = info["focal_35mm"] / DIAG_35MM * math.hypot(W, H)
        info["focal_source"] = "35mm-equivalent (diagonal)"
    elif info["focal_mm"] and fpx_res:
        unit_mm = {2: 25.4, 3: 10.0, 4: 1.0}.get(fp_unit, 25.4)
        fx = info["focal_mm"] * _rat(fpx_res) / unit_mm
        info["focal_source"] = "focal plane resolution"
    if gps:
        try:
            info["lat"] = _dms(gps[2], gps[1])
            info["lon"] = _dms(gps[4], gps[3])
            if 6 in gps:
                alt = _rat(gps[6])
                info["gps_alt"] = -alt if gps.get(5) == 1 else alt
            if 17 in gps:
                info["gps_img_direction"] = _rat(gps[17])
        except (KeyError, ZeroDivisionError, TypeError):
            pass
    # DJI / drone XMP block (plain text inside the JPEG)
    raw = open(path, "rb").read()
    i = raw.find(b"<x:xmpmeta")
    if i >= 0:
        xmp = raw[i: raw.find(b"</x:xmpmeta>", i) + 12].decode("utf-8", "ignore")
        for key in ("RelativeAltitude", "AbsoluteAltitude", "GimbalPitchDegree", "GimbalYawDegree",
                    "GimbalRollDegree", "FlightYawDegree", "FlightPitchDegree", "FlightRollDegree",
                    "CalibratedFocalLength", "CalibratedOpticalCenterX", "CalibratedOpticalCenterY",
                    "LRFTargetDistance", "LRFTargetAbsAlt"):
            m = re.search(rf'(?:drone-dji|Camera|drone):{key}\s*=\s*"([+\-0-9.eE]+)"', xmp) or \
                re.search(rf"<(?:drone-dji|Camera|drone):{key}>([+\-0-9.eE]+)<", xmp)
            if m:
                info[key] = float(m.group(1))
        if "CalibratedFocalLength" in info:
            fx = info["CalibratedFocalLength"]
            info["focal_source"] = "DJI calibrated (px)"
    info["fx_px"] = fx
    cx = info.get("CalibratedOpticalCenterX", W / 2)
    cy = info.get("CalibratedOpticalCenterY", H / 2)
    info["K"] = [[fx, 0, cx], [0, fx, cy], [0, 0, 1]] if fx else None
    return info


def gsd(altitude_m, fx_px):
    """Nadir ground sample distance (m/px) at ``altitude_m`` above the measured surface.

    For roof measurements use altitude above the ROOF, not take-off point:
    alt_above_roof = RelativeAltitude - (roof_height - takeoff_height).
    """
    return altitude_m / fx_px


# ---------------------------------------------------------------------------
# homography plane rectification
# ---------------------------------------------------------------------------

def _normalize(p):
    p = np.asarray(p, float)
    c = p.mean(0)
    s = math.sqrt(2) / max(np.mean(np.linalg.norm(p - c, axis=1)), 1e-12)
    T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
    return T, (np.column_stack([p, np.ones(len(p))]) @ T.T)[:, :2]


def homography(src, dst):
    """DLT homography mapping src (N,2) -> dst (N,2), N >= 4, Hartley-normalised."""
    Ts, s = _normalize(src)
    Td, d = _normalize(dst)
    A = []
    for (x, y), (u, v) in zip(s, d):
        A.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        A.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, Vt = np.linalg.svd(np.array(A))
    Hn = Vt[-1].reshape(3, 3)
    H = np.linalg.inv(Td) @ Hn @ Ts
    return H / H[2, 2]


def apply_h(H, pts):
    p = np.column_stack([np.asarray(pts, float), np.ones(len(pts))]) @ H.T
    return p[:, :2] / p[:, 2:3]


class Rectifier:
    """Measure on a plane in a photo from >= 4 reference points with known plane coords (m)."""

    def __init__(self, img_pts, plane_pts, px_sigma=1.5, ref_sigma=0.005):
        self.img = np.asarray(img_pts, float)
        self.plane = np.asarray(plane_pts, float)
        if len(self.img) < 4:
            raise ValueError("need >= 4 reference points on the plane")
        self.H = homography(self.img, self.plane)
        self.px_sigma, self.ref_sigma = px_sigma, ref_sigma
        back = apply_h(self.H, self.img)
        self.ref_residual_m = float(np.sqrt(np.mean(np.sum((back - self.plane) ** 2, 1))))

    def to_plane(self, pts):
        return apply_h(self.H, pts)

    def distance(self, a_px, b_px, n_mc=500, seed=0):
        """Plane distance between two pixels, with Monte-Carlo 1-sigma (clicks + reference)."""
        rng = np.random.default_rng(seed)
        a, b = self.to_plane([a_px, b_px])
        d0 = float(np.linalg.norm(a - b))
        ds = []
        for _ in range(n_mc):
            H = homography(self.img + rng.normal(0, self.px_sigma, self.img.shape),
                           self.plane + rng.normal(0, self.ref_sigma, self.plane.shape))
            pa, pb = apply_h(H, np.array([a_px, b_px]) + rng.normal(0, self.px_sigma, (2, 2)))
            ds.append(np.linalg.norm(pa - pb))
        return d0, float(np.std(ds))

    def rise_run(self, low_px, high_px, n_mc=500):
        """Pitch of a line on a vertical plane whose plane-y axis is vertical (e.g. a gable rake)."""
        a, b = self.to_plane([low_px, high_px])
        run, rise = abs(b[0] - a[0]), b[1] - a[1]
        rng = np.random.default_rng(1)
        ss = []
        for _ in range(n_mc):
            H = homography(self.img + rng.normal(0, self.px_sigma, self.img.shape),
                           self.plane + rng.normal(0, self.ref_sigma, self.plane.shape))
            pa, pb = apply_h(H, np.array([low_px, high_px]) + rng.normal(0, self.px_sigma, (2, 2)))
            ss.append((pb[1] - pa[1]) / max(abs(pb[0] - pa[0]), 1e-9))
        return rise / max(run, 1e-9), float(np.std(ss))


# ---------------------------------------------------------------------------
# camera resection (PnP)
# ---------------------------------------------------------------------------

def _rodrigues(r):
    th = np.linalg.norm(r)
    if th < 1e-12:
        return np.eye(3)
    k = r / th
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * Kx + (1 - math.cos(th)) * Kx @ Kx


def _rot_to_vec(R):
    c = (np.trace(R) - 1) / 2
    th = math.acos(max(-1.0, min(1.0, c)))
    if th < 1e-9:
        return np.zeros(3)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(th))
    return v * th


def project(K, R, t, X):
    Xc = np.asarray(X, float) @ R.T + t
    x = Xc @ np.asarray(K, float).T
    return x[:, :2] / x[:, 2:3], Xc[:, 2]


def _dlt_camera(img, X):
    # Hartley normalisation of both point sets for conditioning
    Ti, imgn = _normalize(img)
    Xm = np.asarray(X, float).mean(0)
    sX = math.sqrt(3) / max(np.mean(np.linalg.norm(X - Xm, axis=1)), 1e-12)
    TX = np.diag([sX, sX, sX, 1.0])
    TX[:3, 3] = -sX * Xm
    Xn = (np.column_stack([X, np.ones(len(X))]) @ TX.T)[:, :3]
    A = []
    for (u, v), (x, y, z) in zip(imgn, Xn):
        A.append([x, y, z, 1, 0, 0, 0, 0, -u * x, -u * y, -u * z, -u])
        A.append([0, 0, 0, 0, x, y, z, 1, -v * x, -v * y, -v * z, -v])
    _, _, Vt = np.linalg.svd(np.array(A))
    P = np.linalg.inv(Ti) @ Vt[-1].reshape(3, 4) @ TX
    P = P * np.sign(np.linalg.det(P[:, :3]))  # det(M) > 0  =>  points in front, proper rotation
    M = P[:, :3]
    # RQ decomposition
    Qq, Rq = np.linalg.qr(np.flipud(M).T)
    Kd = np.flipud(np.fliplr(Rq.T))
    R = np.flipud(Qq.T)
    S = np.diag(np.sign(np.diag(Kd)))
    Kd, R = Kd @ S, S @ R
    t = np.linalg.solve(Kd, P[:, 3])
    Kd = Kd / Kd[2, 2]
    return Kd, R, t


def solve_camera(img_pts, world_pts, K=None, refine_focal=False, iters=50):
    """Resect a camera. Returns dict with K, R (world->cam), t, centre, rms_px, per-point errors."""
    img = np.asarray(img_pts, float)
    X = np.asarray(world_pts, float)
    if len(img) < 6 and K is None:
        raise ValueError("need >= 6 points without intrinsics (>= 4 with K)")
    Kd, R, t = _dlt_camera(img, X) if len(img) >= 6 else (None, None, None)
    if K is None:
        K = Kd
    K = np.array(K, float)
    if R is None:
        # crude init: camera 30 m from centroid looking at it, refined below
        c = X.mean(0)
        R, t = np.eye(3), -c + np.array([0, 0, 30.0])
    p = np.concatenate([_rot_to_vec(R), t, [K[0, 0]] if refine_focal else []])

    def res(pv):
        Kk = K.copy()
        if refine_focal:
            Kk[0, 0] = Kk[1, 1] = pv[6]
        uv, _ = project(Kk, _rodrigues(pv[:3]), pv[3:6], X)
        return (uv - img).ravel()

    lam = 1e-3
    r = res(p)
    for _ in range(iters):
        J = np.zeros((len(r), len(p)))
        for j in range(len(p)):
            h = 1e-6 if j < 3 else 1e-4 * max(1.0, abs(p[j]))
            dp = np.zeros_like(p)
            dp[j] = h
            J[:, j] = (res(p + dp) - res(p - dp)) / (2 * h)
        A, g = J.T @ J, J.T @ r
        done = False
        for _ in range(10):
            step = -np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), g)
            rn = res(p + step)
            if rn @ rn < r @ r:
                p, r = p + step, rn
                lam /= 3
                done = np.linalg.norm(step) < 1e-10
                break
            lam *= 5
        else:
            break
        if done:
            break
    Kf = K.copy()
    if refine_focal:
        Kf[0, 0] = Kf[1, 1] = p[6]
    Rf, tf = _rodrigues(p[:3]), p[3:6]
    uv, depth = project(Kf, Rf, tf, X)
    err = np.linalg.norm(uv - img, axis=1)
    centre = -Rf.T @ tf
    return {"K": Kf.tolist(), "R": Rf.tolist(), "t": tf.tolist(), "centre": centre.tolist(),
            "rms_px": float(np.sqrt(np.mean(err ** 2))), "errors_px": err.tolist(),
            "mean_depth_m": float(np.mean(depth)),
            "rms_m_at_depth": float(np.sqrt(np.mean(err ** 2)) * np.mean(depth) / Kf[0, 0])}


def blender_camera(cam, width, height):
    """Convert an OpenCV-style camera to Blender camera settings (sensor fit horizontal, 36 mm)."""
    K, R, t = np.array(cam["K"]), np.array(cam["R"]), np.array(cam["t"])
    C = -R.T @ t
    # OpenCV cam axes (x right, y down, z fwd) -> Blender cam axes (x right, y up, z back)
    Rbw = R.T @ np.diag([1, -1, -1])
    sensor = 36.0
    lens = K[0, 0] / width * sensor
    big = max(width, height)
    return {"location": C.tolist(), "matrix_rotation": Rbw.tolist(), "lens": lens, "sensor_width": sensor,
            "sensor_fit": "HORIZONTAL", "shift_x": -(K[0, 2] - width / 2) / big,
            "shift_y": (K[1, 2] - height / 2) / big, "resolution": [width, height],
            "pixel_aspect": K[1, 1] / K[0, 0]}
