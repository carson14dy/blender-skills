"""Camera rigs for the demo renders (pure Python: numpy only, no Blender).

Every camera is derived from the house bounding box, the ground under it and ``front_az`` (the compass bearing the
front of the house faces): never from fixed coordinates, so the same plan works for any house.

Sets (counts and sizes come from render_job.json; defaults below):
  stills     hero_street  eye height 1.7 m above the ground on the front_az side, swung off square for a 3/4 look
             aerial_34    a front-corner oblique from ~35 deg up
             top_down     orthographic, straight down, north up
  turntable  N frames on a constant-radius orbit (radius from the house bbox so the house never leaves the frame),
             constant height, starting at the front
  train      pinhole views for 3DGRUT / 3DGS with the TRUE poses: a ground ring (eye height above the ground at each
             camera), an aerial orbit at two heights, a nadir grid; plus held-out views between them

Conventions (copied from virtual-homes/vhomes/rigs.py, which stays read-only):
* World frame = the model frame: x east, y north, z up, metres (model.json / the Blender scene).
* Pose: OpenCV camera axes (x right, y down, z forward). ``R``, ``t`` map world -> camera (x_c = R x_w + t), the
  COLMAP convention; ``center`` = -R^T t; ``qvec`` = (w, x, y, z) of R. ``blender_matrix_world`` is the same pose
  for a Blender camera (looks down -Z, +Y up).
* Intrinsics: OPENCV model (fx, fy, cx, cy, k1, k2, p1, p2) of the FINAL pinhole image (no distortion: k = p = 0),
  pixel centres at (i + 0.5, j + 0.5), so a centred principal point is (W/2, H/2) - what Blender renders with zero
  lens shift.
"""
from __future__ import annotations

import math
import os

import numpy as np

EYE_HEIGHT = 1.7

DEFAULTS = {
    "stills": {"size": [3840, 2160], "samples": 192, "hero_swing_deg": 18.0, "hero_hfov_deg": 58.0,
               "aerial_swing_deg": 38.0, "aerial_elev_deg": 34.0, "aerial_hfov_deg": 42.0, "top_margin": 1.45,
               "fill": 0.78},
    "turntable": {"frames": 240, "fps": 24, "size": [1920, 1080], "samples": 64, "elev_deg": 22.0, "hfov_deg": 42.0,
                  "fill": 0.80},
    "train": {"long_side": 1440, "aspect": 1.5, "samples": 96, "hfov_deg": 62.0, "n_ground": 48, "n_orbit": 72,
              "orbit_elev_deg": [28.0, 55.0], "n_nadir": 60, "n_holdout": 20, "fill": 0.80, "nadir_overlap": 0.70},
    "sun": {"az_offset_deg": 35.0, "el_deg": 45.0, "energy": 3.5},
}


# ---------------------------------------------------------------------------------------------------------------
# helpers copied from virtual-homes/vhomes/rigs.py (read-only there)

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


def qvec_to_rot(q):
    w, x, y, z = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def pose_dict(center, R):
    c = np.asarray(center, float)
    t = -R @ c
    c2w = np.eye(4); c2w[:3, :3] = R.T; c2w[:3, 3] = c
    bl = np.eye(4); bl[:3, :3] = R.T @ np.diag([1.0, -1.0, -1.0]); bl[:3, 3] = c
    return {"center": c.tolist(), "R": R.tolist(), "t": t.tolist(), "qvec": rot_to_qvec(R),
            "c2w_opencv": c2w.tolist(), "blender_matrix_world": bl.tolist()}


def pinhole(width, height, hfov_deg):
    """OPENCV intrinsics of an undistorted pinhole image of ``width`` x ``height`` with the given horizontal FOV."""
    f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    return {"model": "OPENCV", "width": int(width), "height": int(height), "fx": f, "fy": f, "cx": width / 2.0,
            "cy": height / 2.0, "k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0, "hfov_deg": float(hfov_deg)}


def project(points, cam):
    """World points -> pixel coords (N, 2) and depth (N,) with the camera's pinhole model."""
    P = np.atleast_2d(np.asarray(points, float))
    R, t = np.asarray(cam["pose"]["R"]), np.asarray(cam["pose"]["t"])
    X = P @ R.T + t
    z = X[:, 2]
    k = cam["intrinsics"]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = k["fx"] * X[:, 0] / z + k["cx"]
        v = k["fy"] * X[:, 1] / z + k["cy"]
    return np.stack([u, v], axis=1), z


# ---------------------------------------------------------------------------------------------------------------
# geometry

def bbox_from_points(P):
    P = np.asarray(P, float).reshape(-1, 3)
    return P.min(axis=0).tolist(), P.max(axis=0).tolist()


def bbox_from_model(model):
    """(walls_bbox, roof_bbox) from model.json: walls from their profile / bottom points, roof from facet rings."""
    W = [p for w in model.get("walls", []) for p in list(w.get("profile", [])) + list(w.get("bottom", []))]
    F = [c for f in model.get("facets", []) for q in f.get("polygons", []) for c in q["outer"]]
    walls = bbox_from_points(W) if W else None
    roof = bbox_from_points(F) if F else None
    return walls, roof


def union_bbox(*bbs):
    bbs = [b for b in bbs if b]
    lo = np.min([b[0] for b in bbs], axis=0)
    hi = np.max([b[1] for b in bbs], axis=0)
    return lo.tolist(), hi.tolist()


def corners(bb):
    lo, hi = bb
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], float)


def bearing_vec(az_deg, elev_deg=0.0):
    """Unit vector pointing FROM the house TOWARD compass bearing az, raised by elev."""
    a, e = math.radians(az_deg), math.radians(elev_deg)
    return np.array([math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)])


def _cam(name, rig, idx, intr, center, target, split="train", ortho_scale=None, **extra):
    R = look_at(center, target)
    d = {"name": name, "rig": rig, "index": int(idx), "split": split, "intrinsics": intr,
         "pose": pose_dict(center, R), "look_at": [float(v) for v in target]}
    if ortho_scale is not None:
        d["ortho_scale"] = float(ortho_scale)
        d["projection"] = "orthographic"
    else:
        d["projection"] = "perspective"
    d.update(extra)
    return d


def fit_distance(direction, target, pts, intr, fill=0.8, lo=1.0, hi=2000.0):
    """Smallest distance along ``direction`` (unit, from target toward the camera) at which every point projects
    inside ``fill`` of the frame (centred). Binary search."""
    direction = np.asarray(direction, float) / np.linalg.norm(direction)
    target = np.asarray(target, float)
    W, H = intr["width"], intr["height"]

    def ok(d):
        c = target + direction * d
        cam = {"pose": pose_dict(c, look_at(c, target)), "intrinsics": intr}
        uv, z = project(pts, cam)
        if np.any(z <= 0.05):
            return False
        return bool(np.all(np.abs(uv[:, 0] - W / 2) <= fill * W / 2) and np.all(np.abs(uv[:, 1] - H / 2) <= fill * H / 2))

    if not ok(hi):
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _place_above_ground(c, ground_fn, min_clear):
    g = float(ground_fn(c[0], c[1]))
    if c[2] < g + min_clear:
        c = c.copy(); c[2] = g + min_clear
    return c


# ---------------------------------------------------------------------------------------------------------------
# plan

def merged(job):
    """render_job.json values over DEFAULTS (one level deep)."""
    out = {k: dict(v) for k, v in DEFAULTS.items()}
    for k, v in (job or {}).items():
        if isinstance(v, dict) and k in out:
            out[k].update(v)
        else:
            out[k] = v
    return out


def sun_direction(cfg, front_az):
    s = cfg["sun"]
    az = float(s.get("az", front_az + float(s.get("az_offset_deg", 35.0))))
    el = float(s.get("el_deg", 45.0))
    return {"az": az % 360, "el": el, "energy": float(s.get("energy", 3.5)),
            "to_sun": bearing_vec(az, el).tolist()}


def plan_cameras(house_bbox, front_az, ground_fn=None, job=None, walls_bbox=None, clear_bbox=None, scale=None):
    """All camera sets. ``house_bbox`` = (lo, hi) of walls + roof (the look-at target is its centre);
    ``walls_bbox`` (default house_bbox) sets the orbit radii; ``clear_bbox`` (default house_bbox) is what ground
    cameras must stay outside; ``ground_fn(x, y) -> z`` (default: the bbox bottom); ``scale`` caps every image's long
    side (tests / previews). Returns a dict with stills, turntable, train, holdout, target, sun, notes."""
    cfg = merged(job)
    lo, hi = (np.asarray(v, float) for v in house_bbox)
    walls_bbox = walls_bbox or house_bbox
    clear_bbox = clear_bbox or house_bbox
    if ground_fn is None:
        z0 = float(lo[2])
        ground_fn = lambda x, y: z0  # noqa: E731
    target = (lo + hi) / 2
    pts = corners(house_bbox)
    wlo, whi = (np.asarray(v, float) for v in walls_bbox)
    clo, chi = (np.asarray(v, float) for v in clear_bbox)
    clear_r = 0.5 * math.hypot(chi[0] - clo[0], chi[1] - clo[1]) + 1.5
    notes = []

    def size(wh):
        w, h = int(wh[0]), int(wh[1])
        if scale and max(w, h) > scale:
            s = scale / max(w, h)
            w, h = max(2, int(round(w * s / 2) * 2)), max(2, int(round(h * s / 2) * 2))
        return w, h

    # -------- stills
    st = cfg["stills"]
    W, H = size(st["size"])
    stills = []
    hero_az = front_az - float(st["hero_swing_deg"])
    intr = pinhole(W, H, float(st["hero_hfov_deg"]))
    flat = bearing_vec(hero_az)
    d = fit_distance(flat, target, pts, intr, fill=float(st["fill"]))
    d = max(d, clear_r + 2.0)
    c = target + flat * d
    c[2] = float(ground_fn(c[0], c[1])) + EYE_HEIGHT
    stills.append(_cam("hero_street", "still", 0, intr, c, target, split="still", eye_height=EYE_HEIGHT,
                       bearing=hero_az % 360))
    aer_az = front_az - float(st["aerial_swing_deg"])
    intr = pinhole(W, H, float(st["aerial_hfov_deg"]))
    dirv = bearing_vec(aer_az, float(st["aerial_elev_deg"]))
    d = fit_distance(dirv, target, pts, intr, fill=float(st["fill"]))
    c = _place_above_ground(target + dirv * d, ground_fn, 2.0)
    stills.append(_cam("aerial_34", "still", 1, intr, c, target, split="still", bearing=aer_az % 360,
                       elev_deg=float(st["aerial_elev_deg"])))
    ext_x, ext_y = (hi[0] - lo[0]) * float(st["top_margin"]), (hi[1] - lo[1]) * float(st["top_margin"])
    ortho = max(ext_x, ext_y * W / H)                 # Blender ortho_scale spans the longer (horizontal) side
    c = np.array([target[0], target[1], hi[2] + 50.0])
    intr = pinhole(W, H, 40.0)
    stills.append(_cam("top_down", "still", 2, intr, c, np.array([target[0], target[1], target[2]]), split="still",
                       ortho_scale=ortho, north_up=True))

    # -------- turntable
    tt = cfg["turntable"]
    W, H = size(tt["size"])
    n_tt = int(tt["frames"])
    intr = pinhole(W, H, float(tt["hfov_deg"]))
    el = float(tt["elev_deg"])
    radius = max(fit_distance(bearing_vec(a, el), target, pts, intr, fill=float(tt["fill"])) for a in range(0, 360, 15))
    turn = []
    start = float(tt.get("start_az") if tt.get("start_az") is not None else front_az)
    for i in range(n_tt):
        a = start + 360.0 * i / n_tt
        c = _place_above_ground(target + bearing_vec(a, el) * radius, ground_fn, 2.0)
        turn.append(_cam(f"tt_{i + 1:04d}", "turntable", i, intr, c, target, split="turntable", bearing=a % 360))

    # -------- training + held-out
    tr = cfg["train"]
    asp = float(tr["aspect"])
    W, H = size((int(tr["long_side"]), int(round(int(tr["long_side"]) / asp / 2) * 2)))
    intr = pinhole(W, H, float(tr["hfov_deg"]))
    train, hold = [], []
    n_hold = int(tr["n_holdout"])
    hold_ground = max(0, round(n_hold * 0.3))
    hold_orbit = max(0, round(n_hold * 0.5))
    hold_nadir = max(0, n_hold - hold_ground - hold_orbit)
    # ground ring at two radii (alternating), eye height above the ground at each camera
    ng = int(tr["n_ground"])
    r_fit = max(fit_distance(bearing_vec(a), target, pts, intr, fill=float(tr["fill"])) for a in range(0, 360, 30))
    r_near = max(r_fit, clear_r + 2.0)
    radii = (r_near, r_near * 1.35)

    def ground_cam(a, r, name, idx, split):
        c = target + bearing_vec(a) * r
        c[2] = float(ground_fn(c[0], c[1])) + EYE_HEIGHT
        return _cam(name, "ground", idx, intr, c, target, split=split, bearing=a % 360, eye_height=EYE_HEIGHT)

    for i in range(ng):
        a = front_az + 360.0 * i / ng
        train.append(ground_cam(a, radii[i % 2], f"ground_{i:03d}", i, "train"))
    for j in range(hold_ground):
        a = front_az + 360.0 * (j * ng / max(hold_ground, 1) + 0.5) / ng
        hold.append(ground_cam(a, radii[j % 2] * 1.1, f"holdout_ground_{j:03d}", j, "holdout"))
    # aerial orbit, two heights
    no = int(tr["n_orbit"])
    elevs = [float(e) for e in tr["orbit_elev_deg"]]
    per = [no // len(elevs) + (1 if k < no % len(elevs) else 0) for k in range(len(elevs))]
    idx = 0
    orbit_r = {}
    for k, (e, n) in enumerate(zip(elevs, per)):
        r = max(fit_distance(bearing_vec(a, e), target, pts, intr, fill=float(tr["fill"])) for a in range(0, 360, 30))
        orbit_r[e] = r
        off = 0.5 * k * 360.0 / max(n, 1)                 # stagger the two rings
        for i in range(n):
            a = front_az + off + 360.0 * i / n
            c = _place_above_ground(target + bearing_vec(a, e) * r, ground_fn, 2.0)
            train.append(_cam(f"orbit_{idx:03d}", "orbit", idx, intr, c, target, bearing=a % 360, elev_deg=e))
            idx += 1
    for j in range(hold_orbit):
        e = elevs[j % len(elevs)]
        n = per[j % len(elevs)]
        a = front_az + 360.0 * (j / max(hold_orbit, 1)) + 180.0 / max(n, 1) + 7.0
        c = _place_above_ground(target + bearing_vec(a, e) * orbit_r[e], ground_fn, 2.0)
        hold.append(_cam(f"holdout_orbit_{j:03d}", "orbit", j, intr, c, target, split="holdout", bearing=a % 360,
                         elev_deg=e))
    # nadir grid: rows x cols ~ n_nadir, footprint overlap from tr["nadir_overlap"], north-up images
    nn = int(tr["n_nadir"])
    ext = np.array([hi[0] - lo[0], hi[1] - lo[1]]) * 1.3 + 4.0
    cols = max(2, int(round(math.sqrt(nn * ext[0] / max(ext[1], 1e-6)))))
    rows = max(2, int(math.ceil(nn / cols)))
    xs = np.linspace(target[0] - ext[0] / 2, target[0] + ext[0] / 2, cols)
    ys = np.linspace(target[1] - ext[1] / 2, target[1] + ext[1] / 2, rows)
    step = max(ext[0] / max(cols - 1, 1), ext[1] / max(rows - 1, 1))
    foot = step / max(1e-3, 1.0 - float(tr["nadir_overlap"]))            # ground footprint (short side) per image
    alt = hi[2] + foot * intr["fx"] / min(W, H)
    grid = [(x, y) for y in ys for x in xs]
    if len(grid) > nn:                                                   # drop the far corners first
        grid.sort(key=lambda p: -((p[0] - target[0]) ** 2 / ext[0] ** 2 + (p[1] - target[1]) ** 2 / ext[1] ** 2))
        grid = sorted(grid[len(grid) - nn:], key=lambda p: (p[1], p[0]))
    for i, (x, y) in enumerate(grid):
        c = np.array([x, y, alt])
        train.append(_cam(f"nadir_{i:03d}", "nadir", i, intr, c, np.array([x, y, alt - 10.0]), altitude=alt))
    quarters = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75), (0.5, 0.5)]
    for j in range(hold_nadir):
        qx, qy = quarters[j % len(quarters)]
        x, y = target[0] - ext[0] / 2 + ext[0] * qx, target[1] - ext[1] / 2 + ext[1] * qy
        c = np.array([x, y, alt * 0.97 + 0.03 * hi[2]])
        hold.append(_cam(f"holdout_nadir_{j:03d}", "nadir", j, intr, c, np.array([x, y, c[2] - 10.0]),
                         split="holdout", altitude=float(c[2])))
    if any(float(c["pose"]["center"][2]) < float(ground_fn(*c["pose"]["center"][:2])) + 0.5 for c in train + hold + turn + stills):
        notes.append("a camera was within 0.5 m of the ground")
    return {"target": target.tolist(), "house_bbox": [lo.tolist(), hi.tolist()], "walls_bbox": [wlo.tolist(), whi.tolist()],
            "front_az": float(front_az), "sun": sun_direction(cfg, front_az), "stills": stills, "turntable": turn,
            "train": train, "holdout": hold,
            "radii": {"ground": list(radii), "turntable": radius, "orbit": {str(k): v for k, v in orbit_r.items()},
                      "nadir_altitude": alt, "clear": clear_r},
            "notes": notes, "config": cfg}


# ---------------------------------------------------------------------------------------------------------------
# checks + COLMAP

def check_cameras(cams, target, ground_fn, min_clear=0.5):
    """Problems (list of str): orientation not orthonormal / det != 1, quaternion off, camera at or below the ground,
    a non-nadir camera not looking at ``target``."""
    out = []
    t = np.asarray(target, float)
    for c in cams:
        R = np.asarray(c["pose"]["R"])
        if np.abs(R @ R.T - np.eye(3)).max() > 1e-6 or abs(np.linalg.det(R) - 1) > 1e-6:
            out.append(f"{c['name']}: R not a rotation")
        q = np.asarray(c["pose"]["qvec"])
        if abs(np.linalg.norm(q) - 1) > 1e-6 or np.abs(qvec_to_rot(q) - R).max() > 1e-6:
            out.append(f"{c['name']}: qvec does not match R")
        ctr = np.asarray(c["pose"]["center"])
        if ctr[2] < float(ground_fn(ctr[0], ctr[1])) + min_clear:
            out.append(f"{c['name']}: below / at the ground")
        if c["rig"] == "nadir":
            if R[2] @ np.array([0, 0, -1.0]) < 0.999:
                out.append(f"{c['name']}: nadir camera not looking straight down")
        else:
            f = t - ctr
            if R[2] @ (f / np.linalg.norm(f)) < 0.9999:
                out.append(f"{c['name']}: not looking at the house centre")
    return out


def sample_triangles(tri, n, rng):
    """Uniform points on triangles (array (m, 3, 3)), allocated by area."""
    tri = np.asarray(tri, float).reshape(-1, 3, 3)
    if len(tri) == 0 or n <= 0:
        return np.zeros((0, 3))
    areas = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    if areas.sum() <= 1e-12:
        return np.zeros((0, 3))
    pick = rng.choice(len(tri), size=n, p=areas / areas.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    T = tri[pick]
    return (1 - s)[:, None] * T[:, 0] + (s * (1 - r2))[:, None] * T[:, 1] + (s * r2)[:, None] * T[:, 2]


def sample_surfaces(rings, n, rng):
    """Uniform points on planar 3-D polygons (fan triangulation), allocated by area."""
    tris = []
    for ring in rings:
        P = np.asarray(ring, float)
        tris += [(P[0], P[i], P[i + 1]) for i in range(1, len(P) - 1)]
    return sample_triangles(np.asarray(tris), n, rng) if tris else np.zeros((0, 3))


def sample_ground(tri, center, radius, n, rng, z_fallback=None):
    """Points on ground triangles (m, 3, 3) within ``radius`` of ``center`` (plan); a flat disc at ``z_fallback``
    when there are no triangles."""
    cx, cy = float(center[0]), float(center[1])
    if tri is None or len(tri) == 0:
        if z_fallback is None:
            return np.zeros((0, 3))
        r = radius * np.sqrt(rng.random(n))
        a = rng.random(n) * 2 * np.pi
        return np.column_stack([cx + r * np.cos(a), cy + r * np.sin(a), np.full(n, float(z_fallback))])
    tri = np.asarray(tri, float)
    c = tri.mean(axis=1)
    tri = tri[np.hypot(c[:, 0] - cx, c[:, 1] - cy) < radius + 5.0]
    out = np.zeros((0, 3))
    for _ in range(4):                                   # oversample, keep the disc, top up if short
        P = sample_triangles(tri, 3 * n, rng)
        P = P[np.hypot(P[:, 0] - cx, P[:, 1] - cy) < radius]
        out = np.vstack([out, P])
        if len(out) >= n:
            break
    return out[:n]


def seed_points_from_model(model, n=40000, seed=7):
    """Points on the true roof facets and wall faces of model.json (the splat seed; no ground)."""
    rng = np.random.default_rng(seed)
    rings = [q["outer"] for f in model.get("facets", []) for q in f.get("polygons", [])]
    roof_area = sum(float(f.get("area_m2", 0)) for f in model.get("facets", []))
    walls = []
    for w in model.get("walls", []):
        prof, bot = w.get("profile") or [], w.get("bottom") or []
        if len(prof) >= 2 and len(bot) >= 2:
            walls.append([bot[0], bot[-1], *reversed([list(p) for p in prof])])
    wall_area = sum(float(w.get("area_exposed_m2", 0)) for w in model.get("walls", []))
    tot = max(roof_area + wall_area, 1e-6)
    a = sample_surfaces(rings, int(n * roof_area / tot), rng)
    b = sample_surfaces(walls, int(n * wall_area / tot), rng)
    return np.vstack([a, b]).astype(np.float32)


def write_colmap(out_dir, cams, points, image_names, colors=None):
    """COLMAP text model (virtual-homes/scripts/export_colmap.py layout): sparse/0/{cameras,images,points3D}.txt.
    ``image_names``: {camera name: path relative to out_dir/images}. One OPENCV camera per distinct intrinsics."""
    sp = os.path.join(out_dir, "sparse", "0")
    os.makedirs(sp, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "images"), exist_ok=True)
    keys, cam_id = [], {}
    for c in cams:
        k = c["intrinsics"]
        key = (k["width"], k["height"], round(k["fx"], 6), round(k["fy"], 6), round(k["cx"], 6), round(k["cy"], 6))
        if key not in cam_id:
            cam_id[key] = len(cam_id) + 1
            keys.append((key, k))
        c["_cam_id"] = cam_id[key]
    with open(os.path.join(sp, "cameras.txt"), "w") as f:
        f.write("# CAMERA_ID MODEL WIDTH HEIGHT fx fy cx cy k1 k2 p1 p2 (pixel centres at i+0.5)\n")
        for key, k in keys:
            f.write(f"{cam_id[key]} OPENCV {k['width']} {k['height']} {k['fx']:.6f} {k['fy']:.6f} {k['cx']:.6f} "
                    f"{k['cy']:.6f} {k['k1']:.8f} {k['k2']:.8f} {k['p1']:.8f} {k['p2']:.8f}\n")
    n = 0
    with open(os.path.join(sp, "images.txt"), "w") as f:
        f.write("# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME (world->camera, OpenCV axes)\n# POINTS2D (empty)\n")
        for c in cams:
            q, t = c["pose"]["qvec"], c["pose"]["t"]
            n += 1
            f.write(f"{n} {q[0]:.10f} {q[1]:.10f} {q[2]:.10f} {q[3]:.10f} {t[0]:.8f} {t[1]:.8f} {t[2]:.8f} "
                    f"{c.pop('_cam_id')} {image_names[c['name']]}\n\n")
    P = np.asarray(points, float).reshape(-1, 3)
    C = np.full((len(P), 3), 128, int) if colors is None else np.asarray(colors, int).reshape(-1, 3)
    with open(os.path.join(sp, "points3D.txt"), "w") as f:
        f.write("# POINT3D_ID X Y Z R G B ERROR TRACK[] (sampled on the true surfaces)\n")
        for i, (p, col) in enumerate(zip(P, C), 1):
            f.write(f"{i} {p[0]:.5f} {p[1]:.5f} {p[2]:.5f} {col[0]} {col[1]} {col[2]} 0\n")
    return {"dir": out_dir, "images": n, "cameras": len(cam_id), "points": int(len(P))}


def read_colmap(sparse_dir):
    """Minimal parser for the three text files (tests and sanity checks)."""
    cams, imgs, pts = {}, [], 0
    with open(os.path.join(sparse_dir, "cameras.txt")) as f:
        for ln in f:
            if ln.startswith("#") or not ln.strip():
                continue
            p = ln.split()
            cams[int(p[0])] = {"model": p[1], "width": int(p[2]), "height": int(p[3]), "params": [float(v) for v in p[4:]]}
    with open(os.path.join(sparse_dir, "images.txt")) as f:
        lines = [ln.rstrip("\n") for ln in f if not ln.startswith("#")]
    for i in range(0, len(lines), 2):
        if not lines[i].strip():
            continue
        p = lines[i].split()
        imgs.append({"id": int(p[0]), "qvec": [float(v) for v in p[1:5]], "t": [float(v) for v in p[5:8]],
                     "camera_id": int(p[8]), "name": p[9]})
    with open(os.path.join(sparse_dir, "points3D.txt")) as f:
        for ln in f:
            if ln.strip() and not ln.startswith("#"):
                pts += 1
    return {"cameras": cams, "images": imgs, "points": pts}
