"""Measure the scene against an acceptance file: sizes, counts, spacing, heights, slopes, areas, materials, files.

The file is written BEFORE building, from the brief (references/build-accuracy.md); each check names its source.
Types: size extent count spacing gap position slope area material tris image, plus "forbid". A check that
matches nothing fails. Units m cm mm in ft (area: unit squared or "sq"). Tolerance 1 mm or 0.1 %.
Image paths: // is the .blend folder, other relative paths start at the acceptance file.
Usage:
  blender -b f.blend -P acceptance_check.py -- --accept acceptance.json [--only id1 id2] [--fail-exit]
  blender -b f.blend -P acceptance_check.py -- --measure "Shed_*" [--units ft]     (sizes, no judging)
  MCP: import acceptance_check as a; print(a.run(accept="C:/work/acceptance.json"))
Returns {"pass", "checked", "passed", "failed", "results", "assumed", "forbidden", "warnings", "spec_sha"};
--fail-exit: exit code 2 when "pass" is false (1 = script error).
"""
import fnmatch
import hashlib
import json
import math
import os
import re
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

UNIT = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254, "ft": 0.3048}
SQ = 9.290304  # one roofing square (100 sq ft) in m2
SOURCES = ("given", "reference", "measured", "standard", "assumed")
AXIS = {"x": 0, "y": 1, "z": 2}
DEFAULT_NAME = re.compile(r"^(Cube|Plane|Sphere|Cylinder|Cone|Torus|Suzanne|Circle|Icosphere|Mesh|Empty|"
                          r"Armature|Material|Object|BezierCurve|Text)(\.\d{3})?$")  # scene_audit's, less Camera/Light
LEFTOVER = ("placeholder", "todo", "tmp", "temp", "proxy", "standin", "stand_in", "dummy", "untitled")
TOL_M, TOL_PCT, TOL_DEG = 0.001, 0.1, 0.25


class Bad(Exception):
    """The check fails with this message."""


def _plain(d):  # numpy scalars -> plain Python numbers
    return json.loads(json.dumps(d, default=lambda o: o.item()))


def _r(v, n=4):
    return None if v is None else [_r(x, n) for x in v] if hasattr(v, "__len__") else round(float(v), n)


def _match(sel, types=("MESH",), hidden=False):
    pats = [sel] if isinstance(sel, str) else list(sel or [])
    if not pats:
        raise Bad("no 'objects' pattern")
    out = [o for o in bpy.context.scene.objects if (not types or o.type in types) and (hidden or not o.hide_render)
           and any(fnmatch.fnmatchcase(o.name, p) or (p.startswith("collection:")
                                                      and p[11:] in {c.name for c in o.users_collection}) for p in pats)]
    return sorted(out, key=lambda o: o.name)


def _mesh(ob, dg):  # world-space vertices, triangles, edges (evaluated)
    eo, z = ob.evaluated_get(dg), np.zeros((0, 3), int)
    if ob.type != "MESH":
        return np.array([eo.matrix_world @ Vector(c) for c in eo.bound_box]), z, z[:, :2]
    me = eo.to_mesh()
    try:
        me.calc_loop_triangles()
        co, tri, ed = (np.empty(len(s) * k, dtype=t) for s, k, t in ((me.vertices, 3, float), (me.loop_triangles, 3,
                                                                     np.int32), (me.edges, 2, np.int32)))
        me.vertices.foreach_get("co", co)
        me.loop_triangles.foreach_get("vertices", tri)
        me.edges.foreach_get("vertices", ed)
    finally:
        eo.to_mesh_clear()
    m = np.array(eo.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3], tri.reshape(-1, 3), ed.reshape(-1, 2)


def _bounds(obs, dg):
    pts = [p for p in (_mesh(o, dg)[0] for o in obs) if len(p)]
    if not pts:
        raise Bad("matched objects have no geometry")
    allp = np.vstack(pts)
    return allp.min(0), allp.max(0)


def _tri_geo(obs, dg):  # per-triangle area and unit normal (Blender units)
    a, n = [], []
    for o in obs:
        v, t, _ = _mesh(o, dg)
        x = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
        a.append(np.linalg.norm(x, axis=1) / 2)
        n.append(x / np.maximum(2 * a[-1], 1e-12)[:, None])
    if not sum(x.sum() for x in a):
        raise Bad("matched objects have no faces")
    return np.concatenate(a), np.vstack(n)


def _islands(ob, dg):
    v, _, ed = _mesh(ob, dg)
    parent = list(range(len(v)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in ed.tolist():
        parent[find(a)] = find(b)
    return len({find(i) for i in range(len(v))})


def _unit(u):
    if u not in UNIT:
        raise Bad(f"unit {u!r}: use one of {sorted(UNIT)}")
    return u


class Ctx:
    def __init__(self, spec, folder):
        u, t = _unit(spec.get("units", "m")), spec.get("tolerance") or {}
        self.dg, self.unit, self.folder = bpy.context.evaluated_depsgraph_get(), u, folder
        self.abs_m, self.pct = float(t.get("abs", TOL_M / UNIT[u])) * UNIT[u], float(t.get("pct", TOL_PCT))
        self.scale = bpy.context.scene.unit_settings.scale_length or 1.0

    def u(self, c):  # (Blender units per check unit, unit name)
        unit = _unit(c.get("unit", self.unit))
        return UNIT[unit] / self.scale, unit

    def tol(self, c, expect, unit):  # allowed error, in the check's unit
        e = abs(expect)
        return float(c["tol"]) if "tol" in c else e * float(c["tol_pct"]) / 100 if "tol_pct" in c else \
            max(self.abs_m / UNIT[unit], e * self.pct / 100)


def _judge(c, got, tol):  # (pass, err) against expect within tol, and min/max
    e = c.get("expect")
    if e is None and "min" not in c and "max" not in c:
        raise Bad("needs 'expect', 'min' or 'max'")
    err = None if e is None else got - float(e)
    return ((err is None or abs(err) <= tol + 1e-9) and float(c.get("min", -math.inf)) - 1e-9 <= got
            <= float(c.get("max", math.inf)) + 1e-9), err


def _one(c, cx, got, unit, **extra):  # a single length against expect or min/max
    tol = cx.tol(c, c.get("expect") or 0, unit)
    ok, err = _judge(c, got, tol)
    return {"pass": ok, "expect": c.get("expect"), "got": _r(got), "err": _r(err), "tol": _r(tol), "unit": unit,
            **extra}


def _vec(got, want, tols):  # [x, y, z] against want, null skips an axis
    errs = [None if w is None else g - w for g, w in zip(got, want)]
    return all(e is None or abs(e) <= t + 1e-9 for e, t in zip(errs, tols)), _r(errs)


def _xyz(v, what):
    if not isinstance(v, list) or len(v) != 3:
        raise Bad(what + " [x, y, z] (null skips an axis)")
    return v


def _image(c, cx):
    path = os.path.join(cx.folder, bpy.path.abspath(c["file"]))  # an absolute path stays as it is
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise Bad(f"file missing or empty: {path}")
    im = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = im.size
        r = {"got": [w, h], "expect": c.get("res")}
        ok = (not c.get("res")) or [w, h] == list(c["res"])
        if ok and c.get("not_blank", True):
            if w * h > 40_000_000:
                raise Bad(f"{w}x{h}: too big for not_blank (set it false)")
            px = np.empty(w * h * im.channels, dtype=np.float32)
            im.pixels.foreach_get(px)
            rgb = px.reshape(-1, im.channels)[::97, :3]
            r["range"] = round(float((rgb.max(0) - rgb.min(0)).max()), 4)  # per channel: flat red is blank
            ok = r["range"] > 0.02
    finally:
        bpy.data.images.remove(im)
    return {"pass": ok, **r}


def _check(c, cx):
    typ, hid = c.get("type"), c.get("hidden")
    if typ == "image":
        return _image(c, cx)
    types = tuple(c["types"]) if c.get("types") else (None if typ in ("count", "position") else ("MESH",))
    if typ == "gap":
        a, b = _match(c.get("a"), types, hid), _match(c.get("b"), types, hid)
        if not a or not b:
            raise Bad(f"matched {len(a)} 'a' and {len(b)} 'b' objects")
        k, unit = cx.u(c)
        ax = AXIS[c.get("axis", "z")]
        return _one({"expect": 0, **c}, cx, float(_bounds(b, cx.dg)[0][ax] - _bounds(a, cx.dg)[1][ax]) / k, unit,
                    n=len(a) + len(b))
    obs = _match(c.get("objects"), types, hid)
    if not obs:
        raise Bad("matched 0 objects")
    r = {"n": len(obs)}
    if typ == "count":
        of = c.get("of", "objects")
        if of == "objects":
            got = len(obs)
        elif of == "islands":
            got = sum(_islands(o, cx.dg) for o in obs if o.type == "MESH")
        elif of == "instances":
            got = sum(1 for i in cx.dg.object_instances if i.is_instance and i.parent and i.parent.original in obs)
        else:
            raise Bad(f"count of {of!r}: use objects, islands or instances")
        return {**r, "pass": _judge(c, got, 0)[0], "expect": c.get("expect"), "got": got,
                **{k: c[k] for k in ("min", "max") if k in c}}
    if typ in ("size", "extent", "position", "spacing"):
        k, unit = cx.u(c)
    if typ == "size":
        exp = _xyz(c.get("expect"), "size needs expect")
        want = sorted(exp, key=lambda v: (v is None, v)) if c.get("sorted") else list(exp)
        tols = [None if w is None else cx.tol(c, w, unit) for w in want]
        rows = []
        for group in ([[o] for o in obs] if c.get("each") else [obs]):
            lo, hi = _bounds(group, cx.dg)
            got = [float(hi[i] - lo[i]) / k for i in range(3)]
            got = sorted(got) if c.get("sorted") else got
            ok, err = _vec(got, want, tols)
            rows.append({"object": group[0].name, "got": _r(got), "err": err, "pass": ok})
        bad = [x for x in rows if not x["pass"]]
        top = (bad or rows)[0]
        r.update({"pass": not bad, "expect": exp, "got": top["got"], "err": top["err"], "tol": _r(tols), "unit": unit})
        return {**r, "failing": bad[:10], "failing_count": len(bad)} if c.get("each") else r
    if typ == "extent":
        lo, hi = _bounds(obs, cx.dg)
        return _one(c, cx, float((hi if c.get("side", "max") == "max" else lo)[AXIS[c.get("axis", "z")]]) / k,
                    unit, **r)
    if typ == "position":
        lo, hi = _bounds(obs, cx.dg)
        anchor, at = c.get("anchor", "center"), _xyz(c.get("at"), "position needs at")
        p = np.array(obs[0].matrix_world.translation) if anchor == "origin" else \
            {"center": (lo + hi) / 2, "min": lo, "max": hi}.get(anchor)
        if p is None:
            raise Bad(f"anchor {anchor!r}: use center, min, max or origin")
        tol = cx.tol(c, max(abs(w) for w in at if w is not None), unit)
        ok, err = _vec(p / k, at, [tol] * 3)
        return {**r, "pass": ok, "expect": at, "got": _r(p / k), "err": err, "tol": _r(tol), "unit": unit}
    if typ == "spacing":
        if len(obs) < 2:
            raise Bad(f"spacing needs 2 or more objects, matched {len(obs)}")
        ax, exp = AXIS[c.get("axis", "x")], float(c["expect"])
        cen = sorted(float(sum(_bounds([o], cx.dg))[ax] / 2) / k for o in obs)
        gaps = [b - a for a, b in zip(cen, cen[1:])]
        return _one(c, cx, max(gaps, key=lambda g: abs(g - exp)), unit, min=_r(min(gaps)), max=_r(max(gaps)), **r)
    if typ in ("slope", "area"):
        areas, normals = _tri_geo(obs, cx.dg)
        up = normals[:, 2] > 0.05
        if typ == "slope":
            if not up.any():
                raise Bad("no upward faces")
            ang = np.degrees(np.arccos(np.clip(normals[up, 2], -1, 1)))
            order = np.argsort(ang)
            cum = np.cumsum(areas[up][order])
            got = float(ang[order][np.searchsorted(cum, cum[-1] / 2)])  # area-weighted median
            e = c["expect"]
            want = math.degrees(math.atan2(*map(float, e.split("/")))) if "/" in str(e) else float(e)
            tol = float(c.get("tol", TOL_DEG))
            return {**r, "pass": abs(got - want) <= tol, "expect": e, "expect_deg": _r(want, 3), "got": _r(got, 3),
                    "got_rise_per_12": _r(12 * math.tan(math.radians(got)), 2), "err": _r(got - want, 3),
                    "tol": tol, "unit": "deg"}
        unit = c.get("unit", cx.unit)
        total = float(areas[up].sum() if c.get("facing") == "up" else areas.sum())
        got = total * cx.scale ** 2 / SQ if unit == "sq" else total / cx.u(c)[0] ** 2
        return _one({"tol_pct": 0.5, **c}, cx, got, unit if unit == "sq" else unit + "2", **r)
    if typ == "tris":
        vals = [bx.mesh_tris(o) for o in obs]
        bad = [o.name for o, v in zip(obs, vals) if not _judge(c, v, 0)[0]] if c.get("each") else []
        got = min(vals) if c.get("each") else sum(vals)
        return {**r, "pass": not bad if c.get("each") else _judge(c, got, 0)[0], "got": got,
                **{k: c[k] for k in ("expect", "min", "max") if k in c}, "failing": bad[:10], "failing_count": len(bad)}
    if typ == "material":
        pats = [c["expect"]] if isinstance(c.get("expect"), str) else list(c.get("expect") or [])
        if not pats:
            raise Bad("material needs expect: a name pattern or a list of them")
        bad, seen = [], set()
        for o in obs:
            mats = _mats(o)
            bad += [f"{o.name}: empty slot or no material"] if not mats or None in mats else []
            for m in filter(None, mats):
                seen.add(m.name)
                if not any(fnmatch.fnmatchcase(m.name, p) for p in pats):
                    bad.append(f"{o.name}: {m.name}")
                elif c.get("textured") and not any(n.type == "TEX_IMAGE" and n.image for n in _nodes(m)):
                    bad.append(f"{o.name}: {m.name} has no image texture")
        return {**r, "pass": not bad, "expect": c["expect"], "got": sorted(seen), "failing": bad[:10],
                "failing_count": len(bad)}
    raise Bad(f"unknown check type {typ!r}")


def _mats(o):
    return [s.material for s in o.material_slots]


def _nodes(m):
    return m.node_tree.nodes if m.node_tree else []


def _default_grey(m):
    p = next((n for n in _nodes(m) if n.type == "BSDF_PRINCIPLED"), None)
    if not p:
        return not m.node_tree
    base, rough = p.inputs["Base Color"], p.inputs["Roughness"]
    return (not base.is_linked and all(abs(v - 0.8) < 1e-3 for v in base.default_value[:3])
            and not rough.is_linked and abs(rough.default_value - 0.5) < 1e-3)


def _forbid(f):
    rules = {"default_names": True, "default_materials": True, "empty_slots": True, "name_patterns": LEFTOVER,
             **(f or {})}
    scope = rules.get("scope")
    scope = [scope] if isinstance(scope, str) else scope
    obs = [o for o in bpy.context.scene.objects if o.type not in {"CAMERA", "LIGHT"} and not o.hide_render
           and (not scope or any(fnmatch.fnmatchcase(o.name, p) for p in scope))]
    meshes = [o for o in obs if o.type == "MESH"]
    words = [w.lower() for w in rules["name_patterns"] or []]
    mats = {m for o in meshes for m in _mats(o) if m}
    out = {"name_patterns": [o.name for o in obs if any(w in o.name.lower() for w in words)],
           "default_names": [o.name for o in obs if DEFAULT_NAME.match(o.name)],
           "empty_slots": [o.name for o in meshes if not all(_mats(o) or [None])],
           "default_materials": sorted(m.name for m in mats if DEFAULT_NAME.match(m.name) or _default_grey(m))}
    return [{"rule": k, "count": len(v), "items": v[:15]} for k, v in out.items() if v and rules.get(k)]


def _measure(pattern, unit):
    dg = bpy.context.evaluated_depsgraph_get()
    k = UNIT[unit] / (bpy.context.scene.unit_settings.scale_length or 1.0)
    obs, rows = _match(pattern, None, True), []
    for o in obs[:200]:
        lo, hi = _bounds([o], dg)
        rows.append({"name": o.name, "type": o.type, "size": _r((hi - lo) / k), "min": _r(lo / k), "max": _r(hi / k),
                     "tris": bx.mesh_tris(o) if o.type == "MESH" else 0,
                     "materials": [m.name if m else None for m in _mats(o)]})
    return {"ok": True, "unit": unit, "count": len(obs), "shown": len(rows), "objects": rows}


def run(accept=None, only=None, measure=None, units="m", **_):
    bx.object_mode()
    if measure:
        return _plain(_measure(measure, units))
    if not accept:
        raise ValueError("pass --accept acceptance.json (or --measure PATTERN)")
    with open(bpy.path.abspath(accept), "rb") as f:
        raw = f.read()
    spec = json.loads(raw.decode("utf-8"))
    cx = Ctx(spec, os.path.dirname(os.path.abspath(f.name)))
    results, warnings, assumed, sources, ids = [], [], [], {}, set()
    for i, c in enumerate(spec.get("checks") or []):
        c = c if isinstance(c, dict) else {"type": repr(c)}
        cid = str(c.get("id") or f"check{i + 1}")
        warnings += [f"{cid}: id used twice"] if cid in ids else []
        ids.add(cid)
        if only and cid not in only:
            continue
        src = c.get("source")
        if src not in SOURCES:
            warnings.append(f"{cid}: 'source' is not one of {', '.join(SOURCES)}: counted as assumed")
            src = "assumed"
        sources[src] = sources.get(src, 0) + 1
        assumed += [f"{cid}: {c.get('note') or 'no note'}"] if src == "assumed" else []
        if ("tol" in c or "tol_pct" in c) and not c.get("why"):
            warnings.append(f"{cid}: own tolerance without 'why'")
        try:
            r = _check(c, cx)
        except Exception as e:  # noqa: BLE001 - a malformed check fails; it never stops the run
            r = {"pass": False, "error": str(e) if isinstance(e, Bad) else f"bad check: {type(e).__name__}: {e}",
                 "expect": c.get("expect", c.get("res"))}
        results.append({"id": cid, "type": c.get("type"), "source": src, **r})
    warnings += [f"--only {x}: no such check id" for x in only or [] if x not in ids]
    forbidden = [] if only else _forbid(spec.get("forbid"))
    failed = [r["id"] for r in results if not r["pass"]]
    warnings += [] if results else ["no checks ran: an empty acceptance file cannot pass"]
    return _plain({"ok": True, "pass": bool(results) and not failed and not forbidden, "name": spec.get("name"),
                   "spec_sha": hashlib.sha256(raw).hexdigest()[:12], "units": cx.unit, "checked": len(results),
                   "passed": len(results) - len(failed), "failed": failed, "partial": bool(only),
                   "sources": sources, "assumed": assumed, "forbidden": forbidden, "warnings": warnings,
                   "blender": bpy.app.version_string, "results": results})


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--accept", help="acceptance JSON file")
    p.add_argument("--only", nargs="*", help="check ids to run; forbid is skipped")
    p.add_argument("--measure", help="name pattern: sizes, no judging")
    p.add_argument("--units", default="m", choices=sorted(UNIT))
    p.add_argument("--fail-exit", action="store_true", help="exit code 2 when not a pass")
    res = bx.cli(run, p)
    if res and res.get("pass") is False and "--fail-exit" in bx.argv():
        sys.exit(2)
