#!/usr/bin/env python3
"""render_bundle — the zip a rented GPU box needs to render one house, under a neutral id (no address, no records).

    python3 render_bundle.py JOB --out JOB/out/render_bundle.zip [--front-az DEG] [--id ID] [--blend PATH]
                             [--no-pack] [--extra FILE ...] [--tt-size WxH] [--seed-points N]

Members (all under <id>/):
    model_site.blend    JOB/out/model_site.blend, packed (textures inside) and scrubbed with bpy: Labels, LiDAR
                        points and Reference data collections removed, text objects converted to meshes (their
                        geometry stays, the text string goes), text blocks removed, names / string properties holding
                        an address token renamed / dropped, saved uncompressed from a neutral temporary path
                        (--no-pack or no bpy: copied as is, still scanned)
    render_job.json     front_az, house / walls / roof bbox and ground z (from model.json), render sizes, frame
                        counts, samples, sun, the seed-points file name: what scripts/blender/render_demo.py reads
    seed_points.npy     points on the true roof facets and wall faces (float32 N x 3) for the 3DGRUT seed
    bundle.json         member list with sha256, tool name, created time
Refusals (exit 3, nothing written): any member or --extra file from JOB/data/ (records, LiDAR, footprints), or any
member whose text (the blend's raw bytes included) contains one of the job's address tokens (slug, "<number>
<street>", geocode / origin coordinates to 4 decimals, parcel ids: propmodel.confidence.address_tokens, plus the
model's origin and the job folder's path and name). Exit 1 = input error. JOB/out/render_bundle.json records the id <-> bundle mapping locally (scratch).
front_az: --front-az, else job.json front_az, else run_log.json state.front_az (demo_run thumb stage), else 180 with
a warning.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)

import numpy as np  # noqa: E402

from propmodel import rigs_demo as RD  # noqa: E402

TEXT_EXT = (".json", ".txt", ".md", ".csv", ".py", ".sh", ".xml", ".html", ".svg", ".obj", ".mtl", ".ply", ".gltf")
SCRUB_COLLECTIONS = ("Labels", "LiDAR points", "Reference data")
GENERIC_DIRS = {"job", "jobs", "house", "houses", "demo", "scratch", "scratchpad", "render", "renders", "output"}


class Refused(Exception):
    pass


def jload(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def address_tokens(job):
    """Regex tokens that identify the house (case-insensitive)."""
    cfg = jload(os.path.join(job, "job.json"), {}) or {}
    site = jload(os.path.join(job, "site.json"), {}) or {}
    rec = jload(os.path.join(job, "data", "records.json"), {}) or {}
    model = jload(os.path.join(job, "model.json"), {}) or {}
    site = site or model.get("site") or {}
    if not cfg.get("address") and site.get("address"):
        cfg = {**cfg, "address": site["address"]}
    try:
        from propmodel.confidence import address_tokens as conf_tokens
        toks = list(conf_tokens(cfg, site, rec))
    except Exception:  # noqa: BLE001 - owner A's module missing or changed: local fallback below
        toks = []
        if cfg.get("slug"):
            toks.append(re.escape(cfg["slug"]))
        m = re.match(r"^\s*(\d+[A-Za-z]?)\s+(.+)$", (cfg.get("address") or "").split(",")[0])
        if m:
            words = [w for w in m.group(2).split() if w.upper().strip(".") not in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")]
            if words:
                toks.append(rf"\b{re.escape(m.group(1))}\s+(?:[NSEW]{{1,2}}\.?\s+)?{re.escape(words[0])}\b")
        for d in _walk(rec):
            for k, v in d.items():
                if re.search(r"^(tag|countyid|pid|parcel_?id|parcel_number|apn)$", str(k), re.I) and v and len(str(v)) >= 5:
                    toks.append(re.escape(str(v)))
    for src in (site.get("geocode") or {}, site.get("origin") or {}, (model.get("site") or {}).get("origin") or {},
                (model.get("site") or {}).get("geocode") or {}):
        for k in ("lat", "lon"):
            if src.get(k) is not None:
                toks.append(re.escape(f"{float(src[k]):.4f}"))
    # the job folder itself (scratch paths name the house: $S/jobs/<slug>/)
    toks.append(re.escape(os.path.abspath(job)))
    base = os.path.basename(os.path.abspath(job))
    if len(base) >= 6 and re.search(r"[A-Za-z]", base) and base.lower() not in GENERIC_DIRS:
        toks.append(re.escape(base))
    return sorted(set(t for t in toks if t))


def scan_bytes(data, rx):
    if rx is None:
        return None
    m = rx.search(data.decode("latin-1"))
    return m.group(0) if m else None


def front_az(job, override=None):
    if override is not None:
        return float(override), "--front-az"
    cfg = jload(os.path.join(job, "job.json"), {}) or {}
    if cfg.get("front_az") is not None:
        return float(cfg["front_az"]), "job.json"
    st = ((jload(os.path.join(job, "run_log.json"), {}) or {}).get("state") or {}).get("front_az") or {}
    if st.get("value") is not None:
        return float(st["value"]), f"run_log.json ({st.get('source', 'demo_run')})"
    return 180.0, "default 180 (no front_az in job.json / run_log.json): CHECK the hero view"


def neutral_id(job, override=None):
    if override:
        if not re.match(r"^[A-Za-z0-9_-]{3,40}$", override):
            raise ValueError("--id: 3-40 letters, digits, - or _")
        return override
    cfg = jload(os.path.join(job, "job.json"), {}) or {}
    h = hashlib.sha256((os.path.abspath(job) + "|" + str(cfg.get("slug", ""))).encode()).hexdigest()[:10]
    return f"house-{h}"


PACK_SCRIPT = r'''
import bpy, json, re, sys
src, dst, toks_json = sys.argv[-3:]
rx = re.compile("|".join(json.loads(toks_json)), re.I) if json.loads(toks_json) else None
bpy.ops.wm.open_mainfile(filepath=src)
def wipe(obj, attr, value, n):
    # names and paths live in fixed-size buffers that are written whole: a shorter new value would leave the old
    # value's tail after the terminator, so fill the buffer first (Blender clamps to its maximum length)
    setattr(obj, attr, "x" * n)
    setattr(obj, attr, value)
log = {"removed_objects": 0, "fonts_to_mesh": 0, "renamed": 0, "props_dropped": 0, "texts_removed": 0}
for cname in __SCRUB__:
    c = bpy.data.collections.get(cname)
    if c:
        for o in list(c.all_objects):
            bpy.data.objects.remove(o, do_unlink=True); log["removed_objects"] += 1
        bpy.data.collections.remove(c)
dg = bpy.context.evaluated_depsgraph_get()
for o in [o for o in bpy.data.objects if o.type == "FONT"]:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    mo = bpy.data.objects.new("text-mesh", me)
    mo.matrix_world = o.matrix_world.copy()
    for m in o.data.materials:
        me.materials.append(m)
    for c in o.users_collection:
        c.objects.link(mo)
    mo.hide_render = o.hide_render
    bpy.data.objects.remove(o, do_unlink=True); log["fonts_to_mesh"] += 1
for t in list(bpy.data.texts):
    bpy.data.texts.remove(t); log["texts_removed"] += 1
for c in list(bpy.data.curves):
    if c.users == 0:
        bpy.data.curves.remove(c)
colls = [bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.collections, bpy.data.images,
         bpy.data.cameras, bpy.data.lights, bpy.data.node_groups, bpy.data.curves, bpy.data.worlds, bpy.data.scenes]
n = 0
for coll in colls:
    for idb in list(coll):
        if rx and rx.search(idb.name):
            n += 1; wipe(idb, "name", f"item-{n}", 400); log["renamed"] += 1
        for k in list(idb.keys()):
            v = idb.get(k)
            if isinstance(v, str) and rx and (rx.search(v) or rx.search(k)):
                del idb[k]; log["props_dropped"] += 1
for sc in bpy.data.scenes:
    wipe(sc.render, "filepath", "//render/", 1023)
try:
    bpy.ops.file.pack_all()
except RuntimeError as e:
    log["pack_error"] = str(e)
for i, img in enumerate(bpy.data.images):
    if img.packed_file is not None:
        wipe(img, "filepath_raw", f"//textures/img_{i}.png", 1023)
log["libraries"] = [l.filepath for l in bpy.data.libraries]
bpy.ops.wm.save_as_mainfile(filepath=dst, copy=True, compress=False, relative_remap=False)
print("PACKLOG " + json.dumps(log))
'''.replace("__SCRUB__", repr(SCRUB_COLLECTIONS))


def pack_blend(src, dst, tokens):
    """Scrub + pack with bpy in a subprocess. Returns the log dict, or None when bpy is not available."""
    try:
        import importlib.util
        if importlib.util.find_spec("bpy") is None:
            return None
    except Exception:  # noqa: BLE001
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(PACK_SCRIPT)
        script = f.name
    try:
        r = subprocess.run([sys.executable, script, src, dst, json.dumps(tokens)], capture_output=True, text=True,
                           timeout=900)
    finally:
        os.remove(script)
    m = re.search(r"PACKLOG (\{.*\})", r.stdout)
    if r.returncode != 0 or not m or not os.path.exists(dst):
        raise RuntimeError(f"blend packing failed (exit {r.returncode}): {(r.stderr or r.stdout)[-600:]}")
    return json.loads(m.group(1))


def render_job(job, model, faz, faz_src, bid, tt_size=None):
    walls, roof = RD.bbox_from_model(model)
    house = RD.union_bbox(walls, roof)
    gz = None
    g = model.get("ground")
    if g:
        cx, cy = (house[0][0] + house[1][0]) / 2, (house[0][1] + house[1][1]) / 2
        gz = float(g[0] * cx + g[1] * cy + g[2])
    else:
        bots = [p[2] for w in model.get("walls", []) for p in (w.get("bottom") or [])]
        gz = float(min(bots)) if bots else float(house[0][2])
    jb = {"schema": "render_job/1", "id": bid, "front_az": faz, "front_az_source": faz_src,
          "bbox": {"walls": walls, "roof": roof, "house": house}, "ground_z": gz,
          "seed_points": "seed_points.npy", "created": dt.datetime.now().isoformat(timespec="seconds"),
          **{k: dict(v) for k, v in RD.DEFAULTS.items()}}
    if tt_size:
        w, h = (int(v) for v in tt_size.lower().split("x"))
        jb["turntable"]["size"] = [w, h]
    jb["note"] = ("Rendered from the measured model. Cameras are derived from the bbox and front_az by "
                  "scripts/blender/render_demo.py; the blend is the source of truth for geometry.")
    return jb


def build(job, out, a):
    job = os.path.abspath(job)
    data_dir = os.path.join(job, "data") + os.sep
    model = jload(os.path.join(job, "model.json"))
    if not model or not model.get("facets"):
        raise ValueError(f"no facets in {os.path.join(job, 'model.json')}")
    blend = os.path.abspath(a.blend or os.path.join(job, "out", "model_site.blend"))
    if not os.path.exists(blend):
        raise ValueError(f"no blend {blend} (run the site stage first)")
    for p in [blend] + [os.path.abspath(x) for x in (a.extra or [])]:
        if p.startswith(data_dir):
            raise Refused(f"{p} is under JOB/data/ (records / LiDAR / footprints never go in a bundle)")
    toks = address_tokens(job)
    rx = re.compile("|".join(toks), re.I) if toks else None
    bid = neutral_id(job, a.id)
    faz, faz_src = front_az(job, a.front_az)
    tmp = tempfile.mkdtemp(prefix="rb_")
    try:
        stage = os.path.join(tmp, bid)
        os.makedirs(stage)
        dst = os.path.join(stage, "model_site.blend")
        packlog = None if a.no_pack else pack_blend(blend, dst, toks)
        if packlog is None:
            shutil.copy2(blend, dst)
            packlog = {"packed": False, "note": "copied as is (--no-pack or no bpy): textures not packed, not scrubbed"}
        else:
            packlog["packed"] = True
            if packlog.get("libraries"):
                raise Refused(f"the blend links external libraries {packlog['libraries']}: make them local first")
        jb = render_job(job, model, faz, faz_src, bid, a.tt_size)
        with open(os.path.join(stage, "render_job.json"), "w") as f:
            json.dump(jb, f, indent=1)
        np.save(os.path.join(stage, "seed_points.npy"), RD.seed_points_from_model(model, n=a.seed_points))
        for x in a.extra or []:
            shutil.copy2(x, os.path.join(stage, os.path.basename(x)))
        # scan every member: binary members as raw bytes (the blend is saved uncompressed so its strings are visible)
        members = sorted(os.listdir(stage))
        for n in members:
            with open(os.path.join(stage, n), "rb") as f:
                data = f.read()
            hit = scan_bytes(data, rx)
            if hit:
                raise Refused(f"{n} contains an address token ({hit!r})")
        man = {"schema": "render_bundle/1", "id": bid, "created": dt.datetime.now().isoformat(timespec="seconds"),
               "tool": "property-model-pipeline/scripts/render_bundle.py", "pack": packlog,
               "members": {n: {"bytes": os.path.getsize(os.path.join(stage, n)),
                               "sha256": hashlib.sha256(open(os.path.join(stage, n), "rb").read()).hexdigest()}
                           for n in members},
               "tokens_checked": len(toks)}
        with open(os.path.join(stage, "bundle.json"), "w") as f:
            json.dump(man, f, indent=1)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        part = out + ".part"
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for n in members + ["bundle.json"]:
                z.write(os.path.join(stage, n), f"{bid}/{n}")
        os.replace(part, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rec = {"id": bid, "zip": os.path.abspath(out), "bytes": os.path.getsize(out), "front_az": faz,
           "front_az_source": faz_src, "members": man["members"], "pack": packlog, "tokens_checked": len(toks),
           "created": man["created"]}
    os.makedirs(os.path.join(job, "out"), exist_ok=True)
    with open(os.path.join(job, "out", "render_bundle.json"), "w") as f:
        json.dump(rec, f, indent=1)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job")
    ap.add_argument("--out")
    ap.add_argument("--front-az", type=float)
    ap.add_argument("--id")
    ap.add_argument("--blend")
    ap.add_argument("--no-pack", action="store_true")
    ap.add_argument("--extra", action="append", help="another file to include (refused from JOB/data/)")
    ap.add_argument("--tt-size", help="turntable size WxH (default 1920x1080)")
    ap.add_argument("--seed-points", type=int, default=40000)
    a = ap.parse_args(argv)
    out = a.out or os.path.join(a.job, "out", "render_bundle.zip")
    try:
        rec = build(a.job, out, a)
    except Refused as e:
        print(f"render_bundle: REFUSED: {e}", file=sys.stderr)
        for p in (out, out + ".part"):          # never leave an older bundle where a new one was refused
            if os.path.exists(p):
                os.remove(p)
        return 3
    except (ValueError, RuntimeError, OSError) as e:
        print(f"render_bundle: {e}", file=sys.stderr)
        return 1
    print(json.dumps({k: rec[k] for k in ("id", "zip", "bytes", "front_az", "front_az_source", "tokens_checked")}))
    if rec["front_az_source"].startswith("default"):
        print("render_bundle: WARNING front_az defaulted to 180: set job.json front_az", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
