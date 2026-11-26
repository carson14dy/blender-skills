#!/usr/bin/env python3
"""Splat helpers for the GPU job (3DGRUT): held-out training order, PLY -> web splat, synthetic PLY, info.

    compress_splat.py holdout SRC_DATASET DST_DATASET [--names-file F] [--cameras-json F] [--k N]
    compress_splat.py compress IN.ply OUT.splat [--max-gaussians 400000] [--max-bytes 11000000]
                      [--format splat|splat.json] [--axis zup-to-yup|none] [--crop-points points3D.txt]
                      [--margin 4] [--min-opacity 0.02] [--meta OUT.json]
    compress_splat.py synth OUT.ply [--n 1000] [--seed 0] [--sh-rest 45] [--center=x,y,z]
    compress_splat.py info FILE            (.ply, .splat or .splat.json)

holdout   3DGRUT holds out every k-th frame of a COLMAP dataset (dataset.test_split_interval). This writes a
          view of SRC (symlinked images, rewritten sparse/0 text files) whose order puts the renderer's
          held-out views exactly on those slots, so the reported test PSNR is measured on views the splat
          never trained on. Held-out views come from --names-file, SRC/holdout.txt, a cameras.json entry
          marked holdout / split "test", or an images/holdout/ (or test/) folder. With none, the order is
          kept and k = 8 (3DGRUT's default). Writes DST/split.json and prints {"k": ...}. Stdlib only.
compress  3DGS-style PLY (pre-activation, as 3DGRUT exports it: x y z, f_dc_*, opacity logit, log scales,
          rot_0..3 = w x y z) -> antimatter15 .splat (32 bytes per gaussian: position f32x3, scale f32x3,
          RGBA u8, rotation u8x4), DC colour only. Drops NaNs, near-transparent and huge gaussians and those
          outside the seed-point box + margin, keeps the most important ones (volume x opacity) up to the
          cap, lowers the cap until the file fits --max-bytes, converts Blender z-up to glTF y-up (the
          studio model's frame), then reads the file back and checks the count. splat.json = the same
          bytes base64 in JSON: the artifact host refuses .splat (and .ply / .spz / .ksplat) but serves
          .json, so the studio uses this form. --max-bytes caps the written file in both forms (11 MB of
          JSON holds about 258k gaussians; 11 MB of .splat about 344k).
synth     a synthetic gable-house splat PLY in Blender coordinates (tests, viewer spikes; no real data).

The splat is a visual layer only; nothing here is a measurement.
Exit codes: 0 ok, 1 error, 2 usage.
"""
import argparse
import base64
import json
import math
import os
import sys

SH_C0 = 0.28209479177387814
BYTES_PER_SPLAT = 32
JSON_HEADER_BYTES = 512
PLY_TYPES = {"float": "f4", "float32": "f4", "double": "f8", "float64": "f8", "uchar": "u1", "uint8": "u1",
             "char": "i1", "int8": "i1", "short": "i2", "int16": "i2", "ushort": "u2", "uint16": "u2",
             "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4"}
HOLDOUT_DIRS = ("holdout", "heldout", "held_out", "test")


class SplatError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ holdout

def read_images_txt(path):
    """COLMAP images.txt -> list of (fields, points2d_line). Two lines per image; the second may be empty."""
    out = []
    with open(path) as f:
        lines = f.read().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 10:
            raise SplatError(f"{path}: bad image line: {line[:80]}")
        pts = lines[i] if i < len(lines) else ""
        i += 1
        out.append((fields, pts.strip()))
    return out


def _holdout_names(src, names_file=None, cameras_json=None):
    """-> (set of held-out names or basenames, source label)."""
    if names_file or os.path.isfile(os.path.join(src, "holdout.txt")):
        p = names_file or os.path.join(src, "holdout.txt")
        names = {ln.strip() for ln in open(p) if ln.strip() and not ln.startswith("#")}
        return names, f"names file {os.path.basename(p)}"
    cands = [cameras_json] if cameras_json else [os.path.join(src, "cameras.json"),
                                                os.path.join(os.path.dirname(os.path.abspath(src)), "cameras.json")]
    for p in cands:
        if not p or not os.path.isfile(p):
            continue
        d = json.load(open(p))
        cams = d.get("cameras", d.get("views", [])) if isinstance(d, dict) else d
        names = set()
        for c in cams if isinstance(cams, list) else []:
            if not isinstance(c, dict):
                continue
            split = str(c.get("split", "")).lower()
            if c.get("holdout") or c.get("held_out") or split in ("test", "holdout", "val", "heldout"):
                n = c.get("image") or c.get("name") or c.get("file") or c.get("path")
                if n:
                    names.add(str(n))
        if names:
            return names, f"cameras json {os.path.basename(p)}"
    return set(), ""


def _is_held(name, held):
    if name in held or os.path.basename(name) in held:
        return True
    return any(h.endswith("/" + name) or name.endswith("/" + h) or os.path.basename(h) == os.path.basename(name)
               for h in held if "/" in h or "/" in name)


def holdout_order(n_train, n_hold):
    """-> (k, kept_hold, order) with order a list of 't'/'h' such that index % k == 0 <=> 'h'.
    Held-out views that do not fit a k-slot are dropped (never trained, never scored)."""
    if n_hold <= 0:
        return 8, 0, ["t"] * n_train
    while n_hold > 0:
        n = n_train + n_hold
        k = max(2, math.ceil(n / n_hold))
        slots = math.ceil(n / k)
        if slots == n_hold:
            return k, n_hold, ["h" if i % k == 0 else "t" for i in range(n)]
        n_hold -= 1                                  # slots < n_hold: drop one held-out view and retry
    return 8, 0, ["t"] * n_train


def cmd_holdout(a):
    src, dst = os.path.abspath(a.src), os.path.abspath(a.dst)
    sp_src = os.path.join(src, "sparse", "0")
    img_txt = os.path.join(sp_src, "images.txt")
    if not os.path.isfile(img_txt):
        raise SplatError(f"no {img_txt} (binary COLMAP models are not supported; export text files)")
    entries = read_images_txt(img_txt)
    held, source = _holdout_names(src, a.names_file, a.cameras_json)
    def first_dir(name):
        return name.replace("\\", "/").split("/", 1)[0].lower() if "/" in name else ""
    is_h = [(_is_held(f[9], held) if held else first_dir(" ".join(f[9:])) in HOLDOUT_DIRS) for f, _ in entries]
    if not held and any(is_h):
        source = "holdout folder"
    hold = [e for e, h in zip(entries, is_h) if h]
    train = [e for e, h in zip(entries, is_h) if not h]
    if a.k and not hold:
        k, kept, order = a.k, 0, ["t"] * len(train)
    else:
        k, kept, order = holdout_order(len(train), len(hold))
    dropped = hold[kept:]
    hold = hold[:kept]
    it_t, it_h = iter(train), iter(hold)
    seq = [next(it_h) if o == "h" else next(it_t) for o in order]

    os.makedirs(os.path.join(dst, "sparse", "0"), exist_ok=True)
    os.makedirs(os.path.join(dst, "images"), exist_ok=True)
    for old in os.listdir(os.path.join(dst, "images")):
        p = os.path.join(dst, "images", old)
        if os.path.islink(p):
            os.remove(p)
    remap, lines, test_names = {}, ["# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME (reordered by compress_splat.py holdout)",
                                   "# POINTS2D[] as (X, Y, POINT3D_ID)"], []
    src_img_dir = os.path.join(src, "images")
    for new_id, (fields, pts) in enumerate(seq, 1):
        name = " ".join(fields[9:])
        flat = name.replace("\\", "/").replace("/", "__")
        new_name = f"{new_id - 1:04d}_{flat}"
        target = os.path.realpath(os.path.join(src_img_dir, name))
        if not os.path.exists(target):
            raise SplatError(f"image missing: {os.path.join(src_img_dir, name)}")
        os.symlink(target, os.path.join(dst, "images", new_name))
        remap[int(fields[0])] = new_id
        lines.append(" ".join([str(new_id)] + fields[1:9] + [new_name]))
        lines.append(pts)
        if (new_id - 1) % k == 0 and kept:
            test_names.append(name)
    with open(os.path.join(dst, "sparse", "0", "images.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    for fn in ("cameras.txt", "cameras.bin"):
        s, d = os.path.join(sp_src, fn), os.path.join(dst, "sparse", "0", fn)
        if os.path.isfile(s):
            if os.path.lexists(d):
                os.remove(d)
            os.symlink(os.path.realpath(s), d)
    p3 = os.path.join(sp_src, "points3D.txt")
    if os.path.isfile(p3):
        with open(p3) as fi, open(os.path.join(dst, "sparse", "0", "points3D.txt"), "w") as fo:
            for line in fi:
                s = line.strip()
                if not s or s.startswith("#"):
                    fo.write(line)
                    continue
                v = s.split()
                track = v[8:]
                keep = []
                for j in range(0, len(track) - 1, 2):
                    img = int(track[j])
                    if img in remap:
                        keep += [str(remap[img]), track[j + 1]]
                fo.write(" ".join(v[:8] + keep) + "\n")
    elif os.path.isfile(os.path.join(sp_src, "points3D.bin")):
        d = os.path.join(dst, "sparse", "0", "points3D.bin")
        if os.path.lexists(d):
            os.remove(d)
        os.symlink(os.path.realpath(os.path.join(sp_src, "points3D.bin")), d)
    split = {"k": k, "n": len(seq), "n_train": len(seq) - len(test_names) if kept else len(seq) - math.ceil(len(seq) / k),
             "n_test": len(test_names) if kept else math.ceil(len(seq) / k), "held_out_source": source or "none (every k-th view)",
             "test": test_names, "dropped_holdout": [" ".join(f[9:]) for f, _ in dropped], "src": src}
    json.dump(split, open(os.path.join(dst, "split.json"), "w"), indent=1)
    print(json.dumps({"k": k, "n": split["n"], "n_test": split["n_test"], "source": split["held_out_source"]}))
    return 0


# ------------------------------------------------------------------------------------------------ PLY

def read_ply(path):
    """Binary PLY with one leading 'vertex' element -> (numpy structured array, property names)."""
    import numpy as np
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise SplatError(f"{path}: not a PLY file")
        fmt, count, props, in_vertex, seen_other = None, None, [], False, False
        while True:
            line = f.readline()
            if not line:
                raise SplatError(f"{path}: header has no end_header")
            t = line.decode("ascii", "replace").strip().split()
            if not t or t[0] in ("comment", "obj_info"):
                continue
            if t[0] == "format":
                fmt = t[1]
            elif t[0] == "element":
                in_vertex = t[1] == "vertex"
                if in_vertex:
                    if seen_other:
                        raise SplatError(f"{path}: the vertex element must come first")
                    count = int(t[2])
                else:
                    seen_other = True
            elif t[0] == "property" and in_vertex:
                if t[1] == "list":
                    raise SplatError(f"{path}: list properties are not supported")
                if t[1] not in PLY_TYPES:
                    raise SplatError(f"{path}: unknown property type {t[1]}")
                props.append((t[2], PLY_TYPES[t[1]]))
            elif t[0] == "end_header":
                break
        if fmt not in ("binary_little_endian", "binary_big_endian"):
            raise SplatError(f"{path}: format {fmt} not supported (binary PLY only)")
        if count is None:
            raise SplatError(f"{path}: no vertex element")
        bo = "<" if fmt == "binary_little_endian" else ">"
        dt = np.dtype([(n, bo + t) for n, t in props])
        data = np.frombuffer(f.read(dt.itemsize * count), dtype=dt, count=count)
    return data, [n for n, _ in props]


def write_ply(path, cols):
    """cols: ordered dict name -> float32 array (all the same length). Binary little endian."""
    import numpy as np
    names = list(cols)
    n = len(cols[names[0]])
    dt = np.dtype([(k, "<f4") for k in names])
    arr = np.empty(n, dtype=dt)
    for k in names:
        arr[k] = cols[k]
    head = ["ply", "format binary_little_endian 1.0", "comment synthetic splat (compress_splat.py synth)",
            f"element vertex {n}"] + [f"property float {k}" for k in names] + ["end_header"]
    with open(path, "wb") as f:
        f.write(("\n".join(head) + "\n").encode("ascii"))
        f.write(arr.tobytes())


def _need(data, names, path):
    miss = [n for n in names if n not in data.dtype.names]
    if miss:
        raise SplatError(f"{path}: missing PLY properties {miss}")


def read_points3d(path):
    import numpy as np
    pts = []
    for line in open(path):
        s = line.strip()
        if s and not s.startswith("#"):
            v = s.split()
            pts.append((float(v[1]), float(v[2]), float(v[3])))
    if not pts:
        raise SplatError(f"{path}: no points")
    return np.asarray(pts)


def quat_mul(a, b):
    """Hamilton product, (w, x, y, z), a single quaternion a times an (N, 4) array b."""
    import numpy as np
    aw, ax, ay, az = a
    bw, bx, by, bz = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], axis=1)


def encode_splat(pos, scale, rgba, quat):
    """-> bytes, antimatter15 layout."""
    import numpy as np
    n = len(pos)
    q = quat / np.linalg.norm(quat, axis=1, keepdims=True)
    buf = np.zeros(n, dtype=np.dtype([("p", "<f4", 3), ("s", "<f4", 3), ("c", "u1", 4), ("r", "u1", 4)]))
    buf["p"] = pos
    buf["s"] = scale
    buf["c"] = np.clip(np.round(rgba * 255.0), 0, 255).astype(np.uint8)
    buf["r"] = np.clip(np.round(q * 128.0 + 128.0), 0, 255).astype(np.uint8)
    assert buf.dtype.itemsize == BYTES_PER_SPLAT
    return buf.tobytes()


def decode_splat(raw):
    import numpy as np
    if len(raw) % BYTES_PER_SPLAT:
        raise SplatError(f"splat byte length {len(raw)} is not a multiple of {BYTES_PER_SPLAT}")
    dt = np.dtype([("p", "<f4", 3), ("s", "<f4", 3), ("c", "u1", 4), ("r", "u1", 4)])
    return np.frombuffer(raw, dtype=dt)


def read_web(path):
    """-> raw .splat bytes from a .splat or .splat.json file."""
    if path.endswith(".json"):
        d = json.load(open(path))
        if d.get("format") != "splat":
            raise SplatError(f"{path}: format {d.get('format')!r}, expected 'splat'")
        raw = base64.b64decode(d["base64"])
        if d.get("count") is not None and d["count"] * BYTES_PER_SPLAT != len(raw):
            raise SplatError(f"{path}: count {d['count']} does not match {len(raw)} bytes")
        return raw
    return open(path, "rb").read()


def cmd_compress(a):
    import numpy as np
    data, _ = read_ply(a.inp)
    _need(data, ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2",
                 "rot_0", "rot_1", "rot_2", "rot_3"], a.inp)
    n_in = len(data)
    pos = np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)
    logs = np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], 1).astype(np.float64)
    quat = np.stack([data["rot_0"], data["rot_1"], data["rot_2"], data["rot_3"]], 1).astype(np.float64)
    dc = np.stack([data["f_dc_0"], data["f_dc_1"], data["f_dc_2"]], 1).astype(np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        alpha = 1.0 / (1.0 + np.exp(-data["opacity"].astype(np.float64)))
        scale = np.exp(np.clip(logs, -30, 30))
    qn = np.linalg.norm(quat, axis=1)
    dropped = {}
    keep = np.isfinite(pos).all(1) & np.isfinite(logs).all(1) & np.isfinite(dc).all(1) & np.isfinite(alpha) & (qn > 1e-12)
    dropped["non_finite"] = int((~keep).sum())
    m = alpha >= a.min_opacity
    dropped["transparent"] = int((keep & ~m).sum())
    keep &= m
    crop = None
    if a.crop_points:
        pts = read_points3d(a.crop_points)
        lo, hi = pts.min(0) - a.margin, pts.max(0) + a.margin
        crop = {"min": lo.round(3).tolist(), "max": hi.round(3).tolist(), "margin_m": a.margin}
        m = ((pos >= lo) & (pos <= hi)).all(1)
        dropped["outside_crop"] = int((keep & ~m).sum())
        keep &= m
        max_scale = a.max_scale if a.max_scale else 0.25 * float(np.linalg.norm(hi - lo))
    else:
        max_scale = a.max_scale
    if max_scale:
        m = scale.max(1) <= max_scale
        dropped["huge"] = int((keep & ~m).sum())
        keep &= m
    idx = np.nonzero(keep)[0]
    importance = scale[idx].prod(1) * alpha[idx]
    idx = idx[np.argsort(-importance, kind="stable")]
    cap = min(a.max_gaussians, len(idx))
    # --max-bytes caps the published file: base64 makes the JSON form 4/3 of the raw bytes (+ a short header)
    raw_limit = a.max_bytes if a.format == "splat" else (max(0, a.max_bytes - JSON_HEADER_BYTES) // 4) * 3
    if cap * BYTES_PER_SPLAT > raw_limit:
        cap = raw_limit // BYTES_PER_SPLAT              # lower the cap until the file fits
    dropped["over_cap"] = int(len(idx) - cap)
    idx = idx[:cap]
    if cap == 0:
        raise SplatError("no gaussians left after filtering")
    p, s, q = pos[idx], scale[idx], quat[idx]
    if a.axis == "zup-to-yup":                       # Blender (x, y, z) -> glTF (x, z, -y): -90 deg about X
        p = np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)
        r = math.sqrt(0.5)
        q = quat_mul((r, -r, 0.0, 0.0), q / np.linalg.norm(q, axis=1, keepdims=True))
    rgba = np.concatenate([0.5 + SH_C0 * dc[idx], alpha[idx, None]], 1)
    raw = encode_splat(p, s, rgba, q)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    tmp = a.out + ".part"
    if a.format == "splat.json":
        doc = {"format": "splat", "count": int(cap), "bytesPerSplat": BYTES_PER_SPLAT,
               "frame": "gltf-y-up" if a.axis == "zup-to-yup" else "source",
               "label": "visual layer rendered from the measured model; not used for measurements",
               "base64": base64.b64encode(raw).decode("ascii")}
        with open(tmp, "w") as f:
            json.dump(doc, f, separators=(",", ":"))
    else:
        with open(tmp, "wb") as f:
            f.write(raw)
    os.replace(tmp, a.out)
    back = decode_splat(read_web(a.out))                       # round trip: count and first/last positions
    if len(back) != cap or not np.allclose(back["p"][[0, -1]], p[[0, -1]].astype(np.float32)):
        raise SplatError(f"round trip failed: wrote {cap}, read {len(back)}")
    size = os.path.getsize(a.out)
    if size > a.max_bytes:
        raise SplatError(f"{a.out} is {size} bytes, over the {a.max_bytes} byte cap")
    meta = {"input": os.path.basename(a.inp), "input_count": int(n_in), "written": int(cap), "format": a.format,
            "bytes": int(size), "raw_bytes": len(raw), "max_gaussians": int(a.max_gaussians),
            "max_bytes": int(a.max_bytes), "axis": a.axis, "crop": crop, "dropped": dropped,
            "max_scale_m": round(float(max_scale), 3) if max_scale else None,
            "bbox_out": {"min": p.min(0).round(3).tolist(), "max": p.max(0).round(3).tolist()},
            "label": "visual layer rendered from the measured model; not used for measurements"}
    if a.meta:
        json.dump(meta, open(a.meta, "w"), indent=1)
    print(json.dumps({k: meta[k] for k in ("input_count", "written", "bytes", "format")}))
    return 0


# ------------------------------------------------------------------------------------------------ synth / info

def cmd_synth(a):
    """Gable house (8 x 10 m, eaves 3 m, ridge 5.5 m) on a ground patch, Blender z-up, origin at the centre."""
    import numpy as np
    rng = np.random.default_rng(a.seed)
    n = a.n
    kind = rng.choice(4, size=n, p=[0.35, 0.35, 0.2, 0.1])      # roof, walls, ground, chimney
    u, v = rng.random(n), rng.random(n)
    pos = np.zeros((n, 3))
    col = np.zeros((n, 3))
    w, d, eave, ridge = 8.0, 10.0, 3.0, 5.5
    side = np.where(rng.random(n) < 0.5, -1.0, 1.0)
    r = kind == 0                                       # two roof planes, ridge along y
    pos[r, 0] = side[r] * (w / 2) * u[r]
    pos[r, 1] = (v[r] - 0.5) * d
    pos[r, 2] = ridge - (ridge - eave) * u[r]
    col[r] = (0.30, 0.30, 0.33)
    wl = kind == 1                                      # walls: long sides
    pos[wl, 0] = side[wl] * w / 2
    pos[wl, 1] = (u[wl] - 0.5) * d
    pos[wl, 2] = v[wl] * eave
    col[wl] = (0.85, 0.80, 0.70)
    g = kind == 2
    pos[g, 0] = (u[g] - 0.5) * 24
    pos[g, 1] = (v[g] - 0.5) * 24
    col[g] = (0.35, 0.50, 0.30)
    c = kind == 3                                       # chimney box
    pos[c, 0] = 1.5 + 0.6 * u[c]
    pos[c, 1] = 2.0 + 0.6 * v[c]
    pos[c, 2] = 4.0 + 2.5 * rng.random(c.sum())
    col[c] = (0.55, 0.25, 0.20)
    pos += rng.normal(0, 0.01, pos.shape) + np.asarray(a.center, float)
    q = rng.normal(0, 1, (n, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    cols = {"x": pos[:, 0], "y": pos[:, 1], "z": pos[:, 2],
            "nx": np.zeros(n), "ny": np.zeros(n), "nz": np.ones(n)}
    dc = (col + rng.normal(0, 0.03, col.shape) - 0.5) / SH_C0
    for i in range(3):
        cols[f"f_dc_{i}"] = dc[:, i]
    for i in range(a.sh_rest):
        cols[f"f_rest_{i}"] = np.zeros(n)
    cols["opacity"] = rng.normal(2.5, 0.5, n)
    ls = np.log(np.clip(rng.normal(0.08, 0.02, (n, 3)), 0.01, None))
    for i in range(3):
        cols[f"scale_{i}"] = ls[:, i]
    for i in range(4):
        cols[f"rot_{i}"] = q[:, i]
    write_ply(a.out, {k: np.asarray(vv, dtype=np.float32) for k, vv in cols.items()})
    print(json.dumps({"written": n, "path": a.out, "bytes": os.path.getsize(a.out)}))
    return 0


def cmd_info(a):
    import numpy as np
    if a.path.endswith(".ply"):
        data, names = read_ply(a.path)
        pos = np.stack([data["x"], data["y"], data["z"]], 1) if "x" in names else np.zeros((0, 3))
        out = {"format": "ply", "count": int(len(data)), "properties": len(names)}
    else:
        back = decode_splat(read_web(a.path))
        pos = back["p"]
        out = {"format": "splat.json" if a.path.endswith(".json") else "splat", "count": int(len(back))}
    out["bytes"] = os.path.getsize(a.path)
    if len(pos):
        out["bbox"] = {"min": np.round(pos.min(0), 3).tolist(), "max": np.round(pos.max(0), 3).tolist()}
    print(json.dumps(out))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("holdout")
    h.add_argument("src")
    h.add_argument("dst")
    h.add_argument("--names-file")
    h.add_argument("--cameras-json")
    h.add_argument("--k", type=int, default=0, help="test interval when there are no held-out views (default 8)")
    c = sub.add_parser("compress")
    c.add_argument("inp")
    c.add_argument("out")
    c.add_argument("--max-gaussians", type=int, default=400_000)
    c.add_argument("--max-bytes", type=int, default=11_000_000, help="size cap of the written file (either form)")
    c.add_argument("--format", choices=["splat", "splat.json"], default="splat")
    c.add_argument("--axis", choices=["zup-to-yup", "none"], default="zup-to-yup")
    c.add_argument("--crop-points", help="COLMAP points3D.txt whose box (+ margin) bounds the splat")
    c.add_argument("--margin", type=float, default=4.0)
    c.add_argument("--min-opacity", type=float, default=0.02)
    c.add_argument("--max-scale", type=float, default=0.0, help="metres; default a quarter of the crop box diagonal")
    c.add_argument("--meta")
    s = sub.add_parser("synth")
    s.add_argument("out")
    s.add_argument("--n", type=int, default=1000)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--sh-rest", type=int, default=45)
    s.add_argument("--center", type=lambda v: [float(x) for x in v.split(",")], default=[0.0, 0.0, 0.0],
                   help="x,y,z of the house centre (Blender coordinates); use = for negatives: --center=-5,2,0")
    i = sub.add_parser("info")
    i.add_argument("path")
    a = ap.parse_args(argv)
    try:
        return {"holdout": cmd_holdout, "compress": cmd_compress, "synth": cmd_synth, "info": cmd_info}[a.cmd](a)
    except (SplatError, OSError, ValueError, KeyError) as e:
        print(f"compress_splat {a.cmd}: ERROR {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
