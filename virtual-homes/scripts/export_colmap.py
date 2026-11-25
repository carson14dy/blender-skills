#!/usr/bin/env python3
"""Virtual home -> COLMAP text dataset with the TRUE camera poses (for NVIDIA 3DGRUT / 3DGUT, gsplat, nerfstudio).

    python3 scripts/export_colmap.py virtual_homes/house_001            # -> virtual_homes/house_001/colmap/
    python3 train.py --config-name apps/colmap_3dgut.yaml path=<house>/colmap out_dir=runs experiment_name=house_001

Layout written (what 3DGRUT's dataset_colmap.py reads):
    colmap/images/<rig>/<rig>_NNN.png          symlinks (or copies with --copy) of the rendered photos
    colmap/sparse/0/cameras.txt                 one OPENCV camera per device (fx fy cx cy k1 k2 p1 p2)
    colmap/sparse/0/images.txt                  world->camera quaternion + translation per image
    colmap/sparse/0/points3D.txt                initial points sampled on the true roof, walls and ground

The poses and initial points are ground truth, so a splat trained from this is the best case for the SHOW model.
To test the MEASUREMENT pipeline fairly, run COLMAP / photogrammetry on the images alone instead.
"""
import argparse
import json
import os
import shutil

import numpy as np


def _sample_polygon(ring, n, rng):
    """Uniform points on a planar 3-D polygon (fan triangulation; fine for convex facets and wall faces)."""
    P = np.asarray(ring, float)
    tris = [(P[0], P[i], P[i + 1]) for i in range(1, len(P) - 1)]
    areas = np.array([0.5 * np.linalg.norm(np.cross(b - a, c - a)) for a, b, c in tris])
    if areas.sum() <= 0:
        return np.zeros((0, 3))
    pick = rng.choice(len(tris), size=n, p=areas / areas.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    out = []
    for k, (u, v) in zip(pick, zip(s, r2)):
        a, b, c = tris[k]
        out.append((1 - u) * a + u * (1 - v) * b + u * v * c)
    return np.asarray(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("house_dir")
    ap.add_argument("--out")
    ap.add_argument("--copy", action="store_true", help="copy images instead of symlinking")
    ap.add_argument("--points", type=int, default=60000)
    ap.add_argument("--rendered-only", action="store_true", default=True)
    a = ap.parse_args(argv)
    hd = os.path.abspath(a.house_dir)
    out = os.path.abspath(a.out or os.path.join(hd, "colmap"))
    cams = json.load(open(os.path.join(hd, "cameras.json")))
    house = json.load(open(os.path.join(hd, "house.json")))
    sp = os.path.join(out, "sparse", "0")
    os.makedirs(sp, exist_ok=True)

    dev_id = {name: i + 1 for i, name in enumerate(cams["devices"])}
    with open(os.path.join(sp, "cameras.txt"), "w") as f:
        f.write("# CAMERA_ID MODEL WIDTH HEIGHT fx fy cx cy k1 k2 p1 p2 (pixel centres at i+0.5)\n")
        for name, d in cams["devices"].items():
            f.write(f"{dev_id[name]} OPENCV {d['width']} {d['height']} {d['fx']:.6f} {d['fy']:.6f} {d['cx']:.6f} "
                    f"{d['cy']:.6f} {d['k1']:.8f} {d['k2']:.8f} {d['p1']:.8f} {d['p2']:.8f}\n")
    n_img = 0
    with open(os.path.join(sp, "images.txt"), "w") as f:
        f.write("# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME (world->camera, OpenCV axes)\n# POINTS2D (empty)\n")
        for c in cams["cameras"]:
            src = os.path.join(hd, c["image"])
            if not os.path.exists(src):
                continue
            name = c["image"].split("renders/", 1)[1]
            dst = os.path.join(out, "images", name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.lexists(dst):
                os.remove(dst)
            if a.copy:
                shutil.copy2(src, dst)
            else:
                os.symlink(src, dst)
            q, t = c["pose"]["qvec"], c["pose"]["t"]
            n_img += 1
            f.write(f"{n_img} {q[0]:.10f} {q[1]:.10f} {q[2]:.10f} {q[3]:.10f} {t[0]:.8f} {t[1]:.8f} {t[2]:.8f} "
                    f"{dev_id[c['device']]} {name}\n\n")
    rng = np.random.default_rng(house["spec"]["seed"])
    rings = [p["outer"] for fct in house["facets"] for p in fct["rings"]] + [w["polygon"] for w in house["walls"]]
    areas = []
    for r in rings:
        P = np.asarray(r, float)
        n = np.zeros(3)
        for i in range(len(P)):
            n += np.cross(P[i], P[(i + 1) % len(P)])
        areas.append(np.linalg.norm(n) / 2)
    half = 25.0
    ground = [[-half, -half, 0.0], [half, -half, 0.0], [half, half, 0.0], [-half, half, 0.0]]
    rings.append(ground); areas.append(0.5 * sum(areas))          # a third of the points on the lawn
    alloc = np.maximum(1, np.round(a.points * np.asarray(areas) / sum(areas))).astype(int)
    pts = np.concatenate([_sample_polygon(r, k, rng) for r, k in zip(rings, alloc)])
    with open(os.path.join(sp, "points3D.txt"), "w") as f:
        f.write("# POINT3D_ID X Y Z R G B ERROR TRACK[] (sampled on the true surfaces, grey)\n")
        for i, p in enumerate(pts, 1):
            f.write(f"{i} {p[0]:.5f} {p[1]:.5f} {p[2]:.5f} 128 128 128 0\n")
    print(json.dumps({"colmap_dir": out, "images": n_img, "cameras": len(dev_id), "points": len(pts)}))


if __name__ == "__main__":
    main()
