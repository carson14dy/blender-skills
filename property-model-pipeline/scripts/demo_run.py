#!/usr/bin/env python3
"""demo_run — one command per house for the DEMO tier: address -> measured roof report -> studio page.

    python3 demo_run.py new JOB --address "123 Main St, Town, ST" --profile sioux-falls-sd [--label TEXT]
                                [--front-az DEG] [--latlon LAT,LON] [--studio-url URL] [--waste PCT]
    python3 demo_run.py run JOB [--site-dir STUDIO] [--from STAGE] [--to STAGE] [--force STAGE]
                                [--offline] [--no-render] [--yes]
    python3 demo_run.py status JOB          gate table + timing log

JOB is a scratch directory (never inside the repo: the wrapper refuses it). JOB/job.json holds the per-house config
(address, slug, profile, front_az, waste, label, studio_url, skip, flags = extra arguments per stage, e.g.
{"lidar": ["--thr", "0.1"], "build_site": ["--cell", "0.35"]}). House data stays in JOB.

Stages (each idempotent: skipped when its outputs exist and its inputs are unchanged since it last ran; every tool is
called as a subprocess by path):
  init      city address point (profile, explicit fields) -> pm.py init --latlon          G0 one match
  records   scripts/records.py (property records, permits)                                G1p privacy scan
  hazards   scripts/hazards.py (hail / wind / flood)
  fetch     pm.py fetch: city footprint layer from the profile, --no-ms --no-osm, ortho
  lidar     pm.py lidar --dataset --year --accept --extra-dims GpsTime; hillside -> --ground-mode surface
                                                                                          G1 LiDAR vs permits, G2
  city3d    pm.py obs import-multipatch (only when the profile has a LOD2 layer)          G2 LOD2 pitch
  spec      pm.py suggest; STOP until JOB/spec.json is edited (the one manual step)
  fit       pm.py fit + pm.py resid                                                       G3
  edges     pm.py edges --write-obs; pm.py fit --accept --sigma-free pitches,eave_heights --use-edges;
            hazards.py --only roof                                                        G4
  checks    report sanity, out/gates.json, out/sections/90_confidence.md,
            out/detail_extra/confidence.json                                              G5 go / no-go
  blender   pm.py blender --glb --plain-ground                                            G6 mesh area
  details   details_stub.py (when JOB/details.json is missing) + add_details.py
  site      pm.py features --profile, build_site.py --half 30 --cell 0.25, add_site.py
  thumb     render_thumbnail.py --front-az
  diagrams  scripts/roof_diagrams.py                                                      G7 totals
  export    export_studio_glb.py --with-site
  package   repo address check; studio/package_house.py, studio/report_pdf.py
  test      studio/smoke.py (strict CSP)                                                  G8
  publish   writes JOB/publish.json = the exact Artifact call (the agent sends it)
  render    scripts/render_bundle.py, then the GPU MCP sequence path (never rents a box itself)

Exit codes: 0 done (or --to reached), 1 a stage failed, 2 a gate said STOP, 3 the spec needs editing.
Gates: PASS / WARN / STOP in JOB/out/gates.json. STOP gates marked overridable (a human decision: "the LiDAR predates
an addition", "address matched two units", a CONFLICT row) continue with --yes and are listed as accepted in the
confidence statement; privacy, sigma = 0 and an address found in the public repo never do.
Timing: JOB/run_log.json (start / end / seconds / exit per stage, total per run).
--offline: PROPMODEL_OFFLINE=1 for every stage: answers come from PROPMODEL_CACHE only and a miss fails fast.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)

from propmodel import confidence as C  # noqa: E402
from propmodel import features as FT  # noqa: E402

PM = os.path.join(HERE, "pm.py")
STAGES = ["init", "records", "hazards", "fetch", "lidar", "city3d", "spec", "fit", "edges", "checks", "blender",
          "details", "site", "thumb", "diagrams", "export", "package", "test", "publish", "render"]
ORDER = {s: i for i, s in enumerate(STAGES)}
SCRIPTS = {   # owner scripts the wrapper calls by path (missing -> the stage is skipped with a WARN)
    "records": os.path.join(HERE, "records.py"), "hazards": os.path.join(HERE, "hazards.py"),
    "details_stub": os.path.join(HERE, "details_stub.py"),
    "add_details": os.path.join(HERE, "blender", "add_details.py"), "add_site": os.path.join(HERE, "blender", "add_site.py"),
    "build_site": os.path.join(HERE, "build_site.py"), "thumb": os.path.join(HERE, "blender", "render_thumbnail.py"),
    "diagrams": os.path.join(HERE, "roof_diagrams.py"), "export": os.path.join(HERE, "blender", "export_studio_glb.py"),
    "package": os.path.join(HERE, "studio", "package_house.py"), "pdf": os.path.join(HERE, "studio", "report_pdf.py"),
    "smoke": os.path.join(HERE, "studio", "smoke.py"), "render_bundle": os.path.join(HERE, "render_bundle.py"),
    "mcp_sequence": os.path.join(HERE, "gpu", "MCP_SEQUENCE.md"),
}
OVERRIDABLE = {"G0.address", "G1.permits", "G1.year_built", "G2.shift", "G3.conflict", "G4.shift_city"}
STREET_ABBR = {"AVENUE": "AVE", "STREET": "ST", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN", "COURT": "CT",
               "PLACE": "PL", "BOULEVARD": "BLVD", "CIRCLE": "CIR", "TRAIL": "TRL", "PARKWAY": "PKWY", "TERRACE": "TER",
               "HIGHWAY": "HWY", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


class Stop(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def repo_root():
    try:
        return subprocess.run(["git", "-C", TOOL, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.path.dirname(TOOL)


def refuse_in_repo(job):
    rr = os.path.realpath(repo_root())
    jj = os.path.realpath(job)
    if jj == rr or jj.startswith(rr + os.sep):
        raise SystemExit(f"refusing JOB inside the repo ({rr}): house data stays in scratch (the repo is public)")


def jload(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def jsave(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(path + ".tmp", path)


def sha_file(path):
    if not os.path.exists(path):
        return None
    if os.path.isdir(path):
        return "dir"
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(address):
    street = address.split(",")[0]
    return re.sub(r"[^a-z0-9]+", "-", street.lower()).strip("-") or "house"


def norm_street(address):
    s = re.sub(r"[.,]", " ", address.split(",")[0].upper())
    return " ".join(STREET_ABBR.get(w, w) for w in s.split())


class Job:
    def __init__(self, path, site_dir=None, offline=False, yes=False):
        self.dir = os.path.abspath(path)
        self.cfg = jload(self.p("job.json"))
        if self.cfg is None:
            raise SystemExit(f"{self.dir}/job.json not found: run `demo_run.py new {path} --address ... --profile ...`")
        self.profile_ref = self.cfg.get("profile")
        self.profile = FT.load_profile(self.profile_ref) if self.profile_ref else {}
        self.site_dir = os.path.abspath(site_dir) if site_dir else (self.cfg.get("site_dir") and os.path.abspath(self.cfg["site_dir"]))
        self.offline = offline
        self.yes = yes
        self.log = jload(self.p("run_log.json"), {"runs": [], "state": {"stages": {}, "files": {}}})
        self.log.setdefault("state", {}).setdefault("stages", {})
        self.log["state"].setdefault("files", {})
        self.env = dict(os.environ)
        if offline:
            self.env["PROPMODEL_OFFLINE"] = "1"
        self.overrides = set((jload(self.p("out/gates.json"), {}) or {}).get("overrides", []))

    def p(self, *parts):
        return os.path.join(self.dir, *parts)

    @property
    def slug(self):
        return self.cfg.get("slug") or slugify(self.cfg.get("address", "house"))

    def flags(self, key):
        return [str(x) for x in (self.cfg.get("flags") or {}).get(key, [])]

    def save_log(self):
        jsave(self.p("run_log.json"), self.log)

    # -- subprocesses -------------------------------------------------------
    def run(self, cmd, stage, check=True):
        """Run a tool (list of args; .py paths run with this Python). Output -> console and JOB/logs/<stage>.log."""
        if cmd and str(cmd[0]).endswith(".py"):
            cmd = [sys.executable] + cmd
        cmd = [str(c) for c in cmd]
        os.makedirs(self.p("logs"), exist_ok=True)
        with open(self.p("logs", f"{stage}.log"), "a") as lf:
            lf.write(f"\n$ {' '.join(cmd)}\n")
            pr = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=self.env, cwd=TOOL)
            out = []
            for line in pr.stdout:
                out.append(line)
                lf.write(line)
                sys.stdout.write("    " + line)
            pr.wait()
        if check and pr.returncode != 0:
            raise StageFailed(f"{os.path.basename(cmd[1] if len(cmd) > 1 else cmd[0])} exited {pr.returncode}", pr.returncode)
        return pr.returncode, "".join(out)

    def pm(self, *args, stage, check=True):
        return self.run([PM, *args], stage, check=check)

    # -- gates ----------------------------------------------------------------
    def gates_doc(self):
        return jload(self.p("out/gates.json"), {"gates": [], "overrides": []})

    def set_gates(self, stage, gates):
        doc = self.gates_doc()
        doc["gates"] = [g for g in doc.get("gates", []) if g.get("stage") != stage] + [dict(g, stage=stage) for g in gates]
        doc["gates"].sort(key=lambda g: (ORDER.get(g.get("stage"), 99), g["id"]))
        doc["updated"] = now()
        doc["overrides"] = sorted(self.overrides)
        jsave(self.p("out/gates.json"), doc)
        for g in gates:
            mark = {"PASS": "  ", "WARN": "! ", "STOP": "X "}.get(g["status"], "  ")
            print(f"  {mark}{g['id']:<18s} {g['status']:<4s} {g['message']}")
        stops = [g for g in gates if g["status"] == C.STOP]
        hard = [g for g in stops if not (g.get("overridable") or g["id"] in OVERRIDABLE)]
        soft = [g for g in stops if g not in hard]
        if soft and self.yes:
            self.overrides |= {g["id"] for g in soft}
            doc["overrides"] = sorted(self.overrides)
            jsave(self.p("out/gates.json"), doc)
            print("  accepted with --yes: " + ", ".join(g["id"] for g in soft))
            soft = []
        soft = [g for g in soft if g["id"] not in self.overrides]
        if hard or soft:
            raise Stop("; ".join(f"{g['id']}: {g['message']}" for g in hard + soft)
                       + ("" if hard or not soft else "  (a human decision: rerun with --yes to accept it)"))


class StageFailed(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------------------
# stage definitions: inputs (files rel. to JOB, "job:key1,key2", "profile"), outputs, function
# ---------------------------------------------------------------------------

def _sig_input(job, item):
    if item == "profile":
        return hashlib.sha1(json.dumps({k: v for k, v in job.profile.items() if k != "_path"}, sort_keys=True,
                                       default=str).encode()).hexdigest()
    if item.startswith("job:"):
        vals = {}
        for k in item[4:].split(","):
            cur = job.cfg
            for part in k.split("."):
                cur = cur.get(part) if isinstance(cur, dict) else None
            vals[k] = cur
        return hashlib.sha1(json.dumps(vals, sort_keys=True, default=str).encode()).hexdigest()
    return sha_file(item if os.path.isabs(item) else job.p(item))


def site_out(job, *parts):
    return os.path.join(job.site_dir, *parts) if job.site_dir else None


def stage_io(job, name):
    """(inputs, outputs) of a stage."""
    S = {
        "init": (["job:address,latlon,profile", "profile"], ["site.json"]),
        "records": (["job:address,profile", "profile", "site.json"], ["data/records.json"]),
        "hazards": (["job:address,profile,flags.hazards", "profile", "site.json"], ["data/hazards.json"]),
        "fetch": (["job:flags.fetch,profile", "profile", "site.json"], ["data/footprints.json"]),
        "lidar": (["job:flags.lidar,ground_mode,profile", "profile", "data/footprints.json"],
                  ["data/lidar.json", "data/lidar_points.npy", "data/lidar_roof.npy"]),
        "city3d": (["profile", "data/lidar.json"],
                   ["data/lod2.json"] if _lod2(job) else []),
        "spec": ([], []),
        "fit": (["spec.json", "observations.json", "data/lidar.json", "job:flags.fit"],
                ["fit.json", "model.json", "report.json", "data/resid.json", "data/report_s3.json"]),
        "edges": (["fit.json", "model.json", "data/lidar_points.npy", "job:flags.fit,flags.edges"], ["data/edges.json"]),
        "checks": (["report.json", "fit.json", "data/edges.json", "data/lidar.json"],
                   ["out/sections/90_confidence.md", "out/detail_extra/confidence.json"]),
        "blender": (["model.json", "job:flags.blender"], ["out/model.blend"]),
        "details": (["out/model.blend", "details.json"], ["out/model_detailed.blend"]),
        "site": (["out/model_detailed.blend", "fit.json", "profile", "job:flags.build_site,flags.features", "yard.json"],
                 ["features.json", "site_scene.json", "out/model_site.blend"]),
        "thumb": (["out/model_site.blend", "job:front_az,flags.thumb"], ["out/thumb.jpg"]),
        "diagrams": (["report.json", "model.json"], ["out/diagrams/diagrams.json"]),
        "export": (["out/model_site.blend", "job:flags.export"], ["out/studio.glb"]),
        "package": (["out/studio.glb", "report.json", "out/thumb.jpg", "out/sections/90_confidence.md",
                     "job:label,slug,waste,front_az,flags.package"],
                    [p for p in [site_out(job, "houses", f"{job.slug}.gltf.json")] if p]),
        "test": ([p for p in [site_out(job, "houses", f"{job.slug}.gltf.json")] if p], ["out/smoke.log"]),
        "publish": ([], []),
        "render": (["out/model_site.blend", "job:front_az,flags.render"], ["out/render_bundle.zip"]),
    }
    return S[name]


def record_writes(job, snap_before, name):
    for rel, old in snap_before.items():
        cur = sha_file(rel if os.path.isabs(rel) else job.p(rel))
        if cur is not None and cur != old:
            job.log["state"]["files"][rel] = {"sha": cur, "stage": name}


def up_to_date(job, name):
    rec = job.log["state"]["stages"].get(name)
    if not rec or not rec.get("ok"):
        return False
    ins, outs = stage_io(job, name)
    for o in outs:
        if not os.path.exists(o if os.path.isabs(o) else job.p(o)):
            return False
    files = job.log["state"]["files"]
    for item, old in (rec.get("inputs") or {}).items():
        cur = _sig_input(job, item)
        if cur == old:
            continue
        w = files.get(item)
        if w and w.get("sha") == cur and ORDER.get(w.get("stage"), -1) >= ORDER[name]:
            continue        # changed by this stage or a later pipeline stage, not by a person
        return False
    return set(rec.get("inputs") or {}) == set(ins)


TRACKED = ("site.json", "observations.json", "spec.json", "fit.json", "model.json", "report.json", "details.json",
           "yard.json", "data/resid.json", "features.json", "data/footprints.json", "data/lidar.json")


def tracked_files(job, name):
    ins, outs = stage_io(job, name)
    return sorted(set(outs) | {i for i in ins if not i.startswith(("job:", "profile"))} | set(TRACKED))


def snapshot(job, name):
    return {rel: sha_file(rel if os.path.isabs(rel) else job.p(rel)) for rel in tracked_files(job, name)}


def record(job, name, ins_before, snap_before, ok=True):
    """Remember the inputs the stage consumed, and which tracked files THIS stage changed (so a later check can
    tell a pipeline write from a person's edit)."""
    job.log["state"]["stages"][name] = {"ok": ok, "end": now(), "inputs": ins_before}
    for rel, old in snap_before.items():
        cur = sha_file(rel if os.path.isabs(rel) else job.p(rel))
        if cur is not None and cur != old:
            job.log["state"]["files"][rel] = {"sha": cur, "stage": name}


# -- stage functions ----------------------------------------------------------

def address_point(job):
    """City address point for job.json address (explicit fields; G0 counts the matches)."""
    if job.cfg.get("latlon"):
        lat, lon = map(float, str(job.cfg["latlon"]).split(","))
        return {"source": "latlon", "lat": lat, "lon": lon, "n": 1}
    lay = FT.profile_layer(job.profile, "address_points")
    if not lay or not FT.layer_url(lay):
        return {"source": "census"}
    fields = FT.layer_fields(lay)
    street = norm_street(job.cfg["address"]).replace("'", "''")
    num = street.split(" ")[0]
    tmpl = lay.get("where_template") or lay.get("where") or "ADDRESS = '{street}'"
    where = tmpl.format(street=street, STREET=street, address=street, number=num)
    cache = os.environ.get("PROPMODEL_CACHE", os.path.expanduser("~/.cache/propmodel"))
    d = FT.arcgis_query(FT.layer_url(lay), fields, cache, where=where, f="geojson")
    feats = d.get("features", [])
    out = {"source": "address_points", "n": len(feats), "where": where, "layer": FT.layer_url(lay),
           "allowed_counties": lay.get("counties") or job.profile.get("counties")}
    if not feats:
        core = [w for w in street.split(" ")[1:] if w not in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")]
        if core:
            like = f"{lay.get('address_field', 'ADDRESS')} LIKE '{num} %{core[0]}%'"
            try:
                d2 = FT.arcgis_query(FT.layer_url(lay), fields, cache, where=like, f="geojson")
                out["candidates"] = [str((f.get("properties") or {}).get(lay.get("address_field", "ADDRESS")))
                                     for f in d2.get("features", [])][:5]
            except Exception:  # noqa: BLE001
                pass
        return out
    f0 = feats[0]
    pr = f0.get("properties") or {}
    g = f0.get("geometry") or {}
    lat_f, lon_f = lay.get("lat_field", "LAT"), lay.get("lon_field", "LON")
    if pr.get(lat_f) not in (None, "") and pr.get(lon_f) not in (None, ""):
        out["lat"], out["lon"] = float(pr[lat_f]), float(pr[lon_f])
    elif g.get("type") == "Point":
        out["lon"], out["lat"] = map(float, g["coordinates"][:2])
    if len(feats) > 1:
        pts = {(round(float((f.get("geometry") or {}).get("coordinates", [0, 0])[0]), 6),
                round(float((f.get("geometry") or {}).get("coordinates", [0, 0])[1]), 6)) for f in feats}
        out["distinct_locations"] = len(pts)
        if len(pts) == 1:
            out["n"] = 1          # the same point listed twice (e.g. two units at one door): one house
    out["county"] = pr.get(lay.get("county_field", "COUNTY"))
    out["attributes"] = {k: pr.get(k) for k in fields if k in pr}
    return out


def st_init(job):
    ap = address_point(job)
    jsave(job.p("data/address_point.json"), ap)
    if C.privacy_scan([job.p("data/address_point.json")]):
        os.remove(job.p("data/address_point.json"))
        raise Stop("G1p: forbidden (owner-like) field in the address-point attributes: file deleted; fix the profile fields")
    gates = C.g0_address(ap)
    if ap.get("candidates"):
        gates[0]["message"] += " (similar: " + "; ".join(ap["candidates"]) + ")"
    job.set_gates("init", gates)          # raises on a STOP (an overridable one continues with --yes)
    if ap.get("lat") is None:
        job.pm("init", job.dir, "--address", job.cfg["address"], stage="init")
    else:
        job.pm("init", job.dir, "--latlon", f"{ap['lat']},{ap['lon']}", "--address", job.cfg["address"], stage="init")


def _owner_stage(job, name, args):
    script = SCRIPTS[name]
    if not os.path.exists(script):
        job.set_gates(name, [C.gate(f"{name}.missing", C.WARN, f"{os.path.relpath(script, TOOL)} is not installed: "
                                    f"{name} skipped", stage=name)])
        return "missing"
    job.run([script, job.dir, *args], name)
    return "ran"


def st_records(job):
    r = _owner_stage(job, "records", ["--profile", job.profile_ref] if job.profile_ref else [])
    if r == "missing":
        return r
    paths = [job.p("data/records.json"), job.p("out/detail_extra/records.json")]
    hits = C.privacy_scan(paths)
    if hits:
        for p_, _ in hits:
            if os.path.exists(p_):
                os.remove(p_)
        raise Stop("G1p: owner-like fields in " + ", ".join(sorted({f'{os.path.relpath(p_, job.dir)}:{k}' for p_, k in hits}))
                   + " - files deleted")
    job.set_gates("records", [C.gate("G1p.records", C.PASS, "no owner / taxpayer / contractor fields in the records", stage="records")])


def st_hazards(job):
    args = (["--profile", job.profile_ref] if job.profile_ref else []) + ["--years", "10"] + job.flags("hazards")
    r = _owner_stage(job, "hazards", args)
    if r != "missing" and C.privacy_scan([job.p("data/hazards.json")]):
        raise Stop("G1p: owner-like fields in data/hazards.json")
    return r


def st_fetch(job):
    fp = FT.profile_layer(job.profile, "footprints") or {}
    args = ["fetch", job.dir]
    city = bool(FT.layer_url(fp) or fp.get("geojson"))
    if city:
        args += ["--footprint-name", fp.get("name", "city"), "--footprint-which", fp.get("which", "roof_outline"),
                 "--footprint-sigma", str(fp.get("sigma", 0.25))]
        if FT.layer_url(fp):
            args += ["--footprint-layer", FT.layer_url(fp), "--footprint-fields", ",".join(FT.layer_fields(fp)),
                     "--footprint-where", fp.get("where", "1=1")]
        else:
            args += ["--footprint-geojson", FT.resolve_path(job.profile, fp["geojson"])]
        if not job.profile.get("use_ms"):
            args.append("--no-ms")
        if not job.profile.get("use_osm"):
            args.append("--no-osm")
    orth = FT.profile_layer(job.profile, "ortho") or {}
    if FT.layer_url(orth):
        args += ["--ortho-url", FT.layer_url(orth)] + (["--ortho-attribution", orth["attribution"]] if orth.get("attribution") else [])
    job.pm(*args, *job.flags("fetch"), stage="fetch")
    fps = (jload(job.p("data/footprints.json")) or {}).get("chosen", {})
    job.set_gates("fetch", [C.gate("G2.footprint", C.PASS if fps else C.STOP,
                                   ("footprint: " + ", ".join(f"{k} {v['area_m2']:.0f} m2" for k, v in fps.items())) if fps
                                   else "no building footprint near the address point", stage="fetch")])


def st_lidar(job):
    li_prof = (FT.profile_layer(job.profile, "lidar") or {})
    base = ["lidar", job.dir, "--accept", "--extra-dims", "GpsTime"]
    if li_prof.get("dataset"):
        base += ["--dataset", li_prof["dataset"]]
    if li_prof.get("year"):
        base += ["--year", str(li_prof["year"])]
    keep = ["--keep-datum"] if (jload(job.p("site.json")) or {}).get("datum_m") is not None else []
    surface = ["--ground-mode", "surface", "--flat-z=-1.5,3.5"]
    mode = job.cfg.get("ground_mode")
    job.pm(*base, *(surface if mode == "surface" else []), *keep, *job.flags("lidar"), stage="lidar")
    gates, info = C.g2_lidar(job.dir, job.profile)
    if info.get("hillside") and mode != "surface" and mode != "plane":
        print("  hillside lot: LiDAR again with a filtered ground surface (--ground-mode surface)")
        job.pm(*base, *surface, "--keep-datum", *job.flags("lidar"), stage="lidar")
        gates, info = C.g2_lidar(job.dir, job.profile)
        for g in gates:
            if g["id"] == "G2.hillside":
                g["status"], g["message"] = C.WARN, g["message"].split(":")[0] + ": surface ground mode used"
    gates += C.g1_records(jload(job.p("data/records.json")), jload(job.p("data/lidar.json")))
    li = jload(job.p("data/lidar.json")) or {}
    print(f"  ASK THE OWNER NOW (one message, do not wait): overview {job.p('overview.png')}; "
          f"{len(li.get('planes', []))} roof planes, flown {li.get('flight_date') or li.get('year')}. "
          "Anything not visible from above: covered entry, chimney chase, addition since then, roof material?")
    job.set_gates("lidar", gates)


def _lod2(job):
    lay = FT.profile_layer(job.profile, "lod2") or {}
    return lay if (FT.layer_url(lay) or lay.get("file")) else None


def st_city3d(job):
    lay = _lod2(job)
    if not lay:
        return "n/a"
    src = [FT.resolve_path(job.profile, lay["file"])] if lay.get("file") else []
    try:
        job.pm("obs", job.dir, "import-multipatch", *src, "--profile", job.profile_ref, stage="city3d")
    except StageFailed as e:
        job.set_gates("city3d", [C.gate("G2.lod2", C.WARN, f"city LOD2 import failed ({e}): no LOD2 check", stage="city3d")])
        return "failed (non-fatal)"
    job.set_gates("city3d", C.g2_lod2(job.dir))


def st_spec(job):
    spec = job.p("spec.json")
    state = job.log["state"]
    if not os.path.exists(spec):
        job.pm("plot", job.dir, stage="spec", check=False)
        job.pm("suggest", job.dir, stage="spec")
        state["spec_suggested_sha"] = sha_file(spec)
        shutil.copy(spec, job.p("spec_suggested.json"))
    if sha_file(spec) == state.get("spec_suggested_sha"):
        raise Stop(f"edit {spec} (split the plan into wings, roof types; references/model-spec.md), then rerun "
                   f"`demo_run.py run {job.dir} --from fit`. Look at {job.p('overview.png')} and the plane table in "
                   f"data/lidar.json. Time box: 3 fits / 15 min.", code=3)


def st_fit(job):
    job.pm("fit", job.dir, *job.flags("fit"), stage="fit")
    job.pm("resid", job.dir, stage="fit")
    shutil.copy(job.p("report.json"), job.p("data/report_s3.json"))
    job.set_gates("fit", C.g3_fit(job.dir))


def st_edges(job):
    job.pm("edges", job.dir, "--write-obs", *job.flags("edges"), stage="edges")
    job.pm("fit", job.dir, "--accept", "--sigma-free", "pitches,eave_heights", "--use-edges", *job.flags("fit"), stage="edges")
    job.pm("resid", job.dir, stage="edges")
    if "hazards" not in skip_set(job) and os.path.exists(SCRIPTS["hazards"]):
        try:
            job.run([SCRIPTS["hazards"], job.dir, "--only", "roof"] + (["--profile", job.profile_ref] if job.profile_ref else []),
                    "edges")
        except StageFailed as e:
            print(f"  hazards --only roof failed ({e}): tree overhang / roof colour missing")
    job.set_gates("edges", C.g4_edges(job.dir, job.profile))


def write_confidence(job):
    gates = job.gates_doc().get("gates", [])
    md, js = C.confidence(job.dir, gates, job.cfg, overrides=job.overrides)
    os.makedirs(job.p("out/sections"), exist_ok=True)
    with open(job.p("out/sections/90_confidence.md"), "w") as f:
        f.write(md + "\n")
    jsave(job.p("out/detail_extra/confidence.json"), js)
    return js


def st_checks(job):
    gates = C.g5_report(job.dir)
    allg = [g for g in job.gates_doc().get("gates", []) if g.get("stage") != "checks"] + gates
    stops = [g for g in allg if g["status"] == C.STOP and g["id"] not in job.overrides]
    gates.append(C.gate("G5.go", C.STOP if stops else C.PASS,
                        "GO: the numbers are publishable" if not stops else "NO-GO: " + ", ".join(g["id"] for g in stops),
                        stage="checks"))
    job.set_gates("checks", gates)
    js = write_confidence(job)
    imp = (jload(job.p("report.json")) or {}).get("imperial", {})
    print(f"  TELL THE OWNER: {imp.get('roof_area_sqft', 0):,.0f} sq ft ({imp.get('roof_squares', 0):.2f} squares) "
          f"+/- {js.get('squares_sigma')} sq, predominant pitch {js.get('predominant_pitch')}/12, LiDAR "
          f"{js['lidar'].get('flight_date') or js['lidar'].get('year')}; warnings: "
          + (", ".join(g["id"] for g in allg if g["status"] == C.WARN) or "none"))


MESH_AREA = """
import bpy, json, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[-1])
col = bpy.data.collections.get("Roof facets")
tot = 0.0
for o in (col.all_objects if col else []):
    if o.type != "MESH":
        continue
    M = o.matrix_world
    for p in o.data.polygons:
        v = [M @ o.data.vertices[i].co for i in p.vertices]
        for k in range(1, len(v) - 1):
            tot += ((v[k] - v[0]).cross(v[k + 1] - v[0])).length / 2
print("ROOF_MESH_AREA", json.dumps(tot))
"""


def mesh_roof_area(job, blend):
    try:
        r = subprocess.run([sys.executable, "-c", MESH_AREA, blend], capture_output=True, text=True, timeout=300, env=job.env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"ROOF_MESH_AREA (\S+)", r.stdout)
    return float(m.group(1)) if m else None


def st_blender(job):
    job.pm("blender", job.dir, "--glb", "--plain-ground", *job.flags("blender"), stage="blender")
    rep = jload(job.p("report.json")) or {}
    area = (rep.get("measurements_si") or {}).get("roof.area")
    job.set_gates("blender", C.g6_mesh(area, mesh_roof_area(job, job.p("out/model.blend"))))


def st_details(job):
    if not os.path.exists(job.p("details.json")):
        job.run([SCRIPTS["details_stub"], job.dir], "details")
    job.run([SCRIPTS["add_details"], job.p("out/model.blend"), job.p("details.json"), job.p("out/model_detailed.blend")], "details")


def st_site(job):
    args = ["features", job.dir, "--half", "30"] + (["--profile", job.profile_ref] if job.profile_ref else []) + job.flags("features")
    job.pm(*args, stage="site")
    if not os.path.exists(job.p("yard.json")):
        jsave(job.p("yard.json"), {"items": [], "note": "demo tier: no yard items (no photos)"})
    feats = jload(job.p("features.json")) or {}
    sub = ["--address", "subject"] if any((f.get("props") or {}).get("ADDRESS") == "subject" for f in feats.get("parcels", [])) else []
    job.run([SCRIPTS["build_site"], job.dir, job.p("features.json"), job.p("site_scene.json"), "--half", "30", "--cell", "0.25",
             *sub, *job.flags("build_site")], "site")
    job.run([SCRIPTS["add_site"], job.p("out/model_detailed.blend"), job.p("site_scene.json"), job.p("yard.json"),
             job.p("out/model_site.blend")], "site")


def front_az(job):
    if job.cfg.get("front_az") is not None:
        return float(job.cfg["front_az"]), "job.json"
    from propmodel.geo import LocalFrame
    site = jload(job.p("site.json")) or {}
    mj = jload(job.p("model.json")) or {}
    xs = [c[0] for f in mj.get("facets", []) for q in f["polygons"] for c in q["outer"]]
    ys = [c[1] for f in mj.get("facets", []) for q in f["polygons"] for c in q["outer"]]
    cen = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) if xs else (0.0, 0.0)
    gxy = None
    geo = site.get("geocode") or {}
    if geo.get("lat") is not None and site.get("origin"):
        fr = LocalFrame.from_dict(site["origin"])
        x, y, _ = fr.from_geodetic(geo["lat"], geo["lon"])
        gxy = (float(x), float(y))
    return FT.front_azimuth(cen, jload(job.p("features.json")), gxy)


def st_thumb(job):
    az, src = front_az(job)
    job.log["state"]["front_az"] = {"value": az, "source": src}
    print(f"  front faces {az:.0f} deg ({src}; set job.json front_az to override)")
    job.run([SCRIPTS["thumb"], job.p("out/model_site.blend"), job.p("out/thumb.jpg"), "--front-az", f"{az:.1f}",
             *job.flags("thumb")], "thumb")


def st_diagrams(job):
    r = _owner_stage(job, "diagrams", ["--out", job.p("out/diagrams")] + job.flags("diagrams"))
    if r == "missing":
        return r
    d = jload(job.p("out/diagrams/diagrams.json")) or {}
    imp = (jload(job.p("report.json")) or {}).get("imperial", {})
    tot = d.get("totals", d)
    diffs, n = [], 0
    for k, v in (tot.items() if isinstance(tot, dict) else []):
        if k in imp and isinstance(v, (int, float)):
            n += 1
            tol = 1.0 if "sqft" in k else 0.1 if k.endswith("_ft") else 0.01
            if abs(float(v) - float(imp[k])) > tol:
                diffs.append(f"{k} {v} vs {imp[k]:.2f}")
    job.set_gates("diagrams", [C.gate("G7.totals", C.STOP if diffs else (C.PASS if n else C.WARN),
                                      ("diagram totals differ from report.json: " + "; ".join(diffs)) if diffs else
                                      (f"{n} diagram totals equal report.json" if n else "no comparable totals in diagrams.json"),
                                      stage="diagrams")])


def st_export(job):
    job.run([SCRIPTS["export"], job.p("out/model_site.blend"), job.p("out/studio.glb"), "--with-site", *job.flags("export")],
            "export")


def repo_check(job):
    toks = C.address_tokens(job.cfg, jload(job.p("site.json")), jload(job.p("data/records.json")))
    hits = C.grep_repo(repo_root(), toks)
    if hits:
        raise Stop("the public repo working tree contains this house's identifiers: "
                   + ", ".join(f"{f} ({m!r})" for f, m in hits[:10]) + " - remove them before packaging")
    return len(toks)


def st_package(job):
    if not job.site_dir:
        job.set_gates("package", [C.gate("package.site", C.WARN, "no --site-dir (studio folder): package / test / publish "
                                         "skipped", stage="package")])
        return "no site dir"
    n = repo_check(job)
    priv = C.privacy_scan([os.path.join(job.p("out/detail_extra"), f) for f in os.listdir(job.p("out/detail_extra"))]
                          if os.path.isdir(job.p("out/detail_extra")) else [])
    if priv:
        raise Stop("G1p: owner-like fields in " + ", ".join(sorted({os.path.basename(p_) for p_, _ in priv})))
    write_confidence(job)
    if not os.path.exists(SCRIPTS["package"]):
        job.set_gates("package", [C.gate("package.missing", C.WARN, "scripts/studio/package_house.py is not installed",
                                         stage="package")])
        return "missing"
    label = job.cfg.get("label") or job.cfg.get("address", "").split(",")[0]
    az = (job.log["state"].get("front_az") or {}).get("value")
    if az is None:
        az, src = front_az(job)
        job.log["state"]["front_az"] = {"value": az, "source": src}
    args = [SCRIPTS["package"], job.dir, "--site", job.site_dir, "--slug", job.slug, "--label", label]
    if az is not None:
        args += ["--facing", f"{az:.1f}"]
    if job.cfg.get("waste") is not None:
        args += ["--waste", str(job.cfg["waste"])]
    job.run(args + job.flags("package"), "package")
    gates = [C.gate("G8.repo", C.PASS, f"repo working tree clean of this house ({n} identifiers checked)", stage="package")]
    html = site_out(job, "houses", job.slug, "report.html")
    if os.path.exists(SCRIPTS["pdf"]) and html and os.path.exists(html):
        sqft = (jload(job.p("report.json")) or {}).get("imperial", {}).get("roof_area_sqft", 0)
        ndiag = len([f for f in os.listdir(job.p("out/diagrams")) if f.endswith(".svg")]) if os.path.isdir(job.p("out/diagrams")) else 0
        pages = 6 if ndiag >= 4 else 2
        code, _ = job.run([SCRIPTS["pdf"], html, site_out(job, "houses", job.slug, "report.pdf"), "--expect", f"{sqft:.0f}",
                           "--min-pages", str(pages)], "package", check=False)
        gates.append(C.gate("G8.pdf", {0: C.PASS, 3: C.WARN}.get(code, C.STOP),
                            {0: f"report.pdf printed (>= {pages} pages, holds the area {sqft:.0f})",
                             3: "report.pdf not printed: node / Playwright / Chromium missing"}.get(code, f"report_pdf.py exit {code}"),
                            stage="package"))
    job.set_gates("package", gates)


def st_test(job):
    if not job.site_dir:
        return "no site dir"
    if not os.path.exists(SCRIPTS["smoke"]):
        job.set_gates("test", [C.gate("G8.smoke", C.WARN, "scripts/studio/smoke.py is not installed: CSP smoke test skipped",
                                      stage="test")])
        return "missing"
    code, out = job.run([SCRIPTS["smoke"], "--site", job.site_dir, "--house", job.slug, "--job", job.dir,
                         "--out", job.p("out/smoke"), *job.flags("test")], "test", check=False)
    with open(job.p("out/smoke.log"), "w") as f:
        f.write(out)
    summ = (jload(job.p("out/smoke/smoke.json")) or {}).get("summary", {})
    gates = [C.gate("G8.smoke_warn", C.WARN, str(w), stage="test") for w in summ.get("warnings", [])[:5]]
    msg = {0: "studio page under the strict CSP: no errors, squares and card rows equal the report",
           3: "smoke test not run: node / Playwright / Chromium missing"}.get(code, "smoke test failed: "
                                                                             + "; ".join(map(str, summ.get("failures", [])))[:400])
    gates.append(C.gate("G8.smoke", {0: C.PASS, 3: C.WARN}.get(code, C.STOP), msg + " (out/smoke.log)", stage="test"))
    job.set_gates("test", gates)


def st_publish(job):
    if not job.site_dir:
        return "no site dir"
    fmap = dict(jload(job.p("out/studio_files.json")) or {})
    hd = site_out(job, "houses", job.slug)
    if hd and os.path.isdir(hd):
        for dp, _, fn in os.walk(hd):
            for f in fn:
                full = os.path.join(dp, f)
                fmap.setdefault(os.path.relpath(full, job.site_dir), full)
    for rel in ("houses/index.json", f"houses/{job.slug}.gltf.json"):
        if os.path.exists(os.path.join(job.site_dir, rel)):
            fmap.setdefault(rel, os.path.join(job.site_dir, rel))
    url = job.cfg.get("studio_url") or os.environ.get("ROOF_STUDIO_URL")
    call = {"action": "publish", "file_path": os.path.join(job.site_dir, "index.html"), "root": job.site_dir,
            "files": dict(sorted(fmap.items())), "label": (job.cfg.get("label") or job.slug)[:50] + " v1"}
    if url:
        call["url"] = url
    doc = {"tool": "Artifact", "call": call, "written": now(),
           "note": ("Send this Artifact call from the agent. Publish from the COMPLETE studio folder to the existing URL; "
                    "if refused as changed since read, read the flagged paths, merge, publish again.")
           + ("" if url else " No studio URL: set job.json studio_url (or ROOF_STUDIO_URL) to update the existing studio.")}
    jsave(job.p("publish.json"), doc)
    print(f"  publish call written: {job.p('publish.json')} ({len(fmap)} files)")


def st_render(job):
    if not os.path.exists(SCRIPTS["render_bundle"]):
        job.set_gates("render", [C.gate("render.missing", C.WARN, "scripts/render_bundle.py is not installed", stage="render")])
        return "missing"
    job.run([SCRIPTS["render_bundle"], job.dir, "--out", job.p("out/render_bundle.zip"), *job.flags("render")], "render")
    print(f"  GPU job: follow {SCRIPTS['mcp_sequence']} (the wrapper never rents a box)")


FUNCS = {"init": st_init, "records": st_records, "hazards": st_hazards, "fetch": st_fetch, "lidar": st_lidar,
         "city3d": st_city3d, "spec": st_spec, "fit": st_fit, "edges": st_edges, "checks": st_checks,
         "blender": st_blender, "details": st_details, "site": st_site, "thumb": st_thumb, "diagrams": st_diagrams,
         "export": st_export, "package": st_package, "test": st_test, "publish": st_publish, "render": st_render}
ALWAYS = {"spec", "publish"}     # cheap: evaluated on every run


def skip_set(job, no_render=False):
    s = set(job.cfg.get("skip") or [])
    if no_render:
        s |= {"thumb", "render"}
    return s


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_new(a):
    refuse_in_repo(a.job)
    os.makedirs(a.job, exist_ok=True)
    path = os.path.join(a.job, "job.json")
    if os.path.exists(path) and not a.force:
        raise SystemExit(f"{path} exists (--force to overwrite)")
    prof = a.profile
    if prof and os.path.exists(prof):
        prof = os.path.abspath(prof)
    FT.load_profile(prof)     # fail now if the profile is missing
    cfg = {"address": a.address, "slug": a.slug or slugify(a.address), "profile": prof, "label": a.label,
           "front_az": a.front_az, "waste": a.waste, "latlon": a.latlon, "studio_url": a.studio_url,
           "skip": [], "flags": {}, "created": now(),
           "note": "per-house demo config: scratch only, never commit (house data)"}
    jsave(path, cfg)
    print(f"wrote {path}\nnext: python3 {os.path.relpath(__file__)} run {a.job} --site-dir <studio folder>")


def cmd_run(a):
    refuse_in_repo(a.job)
    job = Job(a.job, a.site_dir, offline=a.offline, yes=a.yes)
    if a.site_dir and job.cfg.get("site_dir") != job.site_dir:      # remembered for the next runs
        job.cfg["site_dir"] = job.site_dir
        jsave(job.p("job.json"), job.cfg)
    if a.offline:
        os.environ["PROPMODEL_OFFLINE"] = "1"
        from propmodel import ept
        ept.install_offline_guard()
    lo = STAGES.index(a.from_) if a.from_ else 0
    hi = STAGES.index(a.to) if a.to else len(STAGES) - 1
    force = set(a.force or []) | ({a.from_} if a.from_ else set())
    skip = skip_set(job, a.no_render)
    run = {"start": now(), "args": sys.argv[1:], "stages": [], "offline": bool(a.offline)}
    job.log["runs"].append(run)
    t_run = time.time()
    code = 0
    print(f"demo run {job.dir} ({job.slug}); profile {job.profile_ref}; cache "
          f"{os.environ.get('PROPMODEL_CACHE', '~/.cache/propmodel')}{'; OFFLINE' if a.offline else ''}")
    try:
        for name in STAGES[lo:hi + 1]:
            ent = {"stage": name, "start": now()}
            t0 = time.time()
            if name in skip:
                ent.update(status="skipped (job.json skip / --no-render)", exit=0, seconds=0.0, end=now())
                run["stages"].append(ent)
                print(f"[{name}] skipped (job.json skip / --no-render)")
                continue
            if name not in force and name not in ALWAYS and up_to_date(job, name):
                ent.update(status="up to date", exit=0, seconds=0.0, end=now())
                run["stages"].append(ent)
                print(f"[{name}] up to date")
                continue
            print(f"[{name}] running")
            ins, _ = stage_io(job, name)
            before = {i: _sig_input(job, i) for i in ins}
            snap = snapshot(job, name)
            if os.environ.get("DEMO_RUN_FAIL") == name:     # test hook: simulate a crash in this stage
                ent.update(status="failed (DEMO_RUN_FAIL)", exit=99, seconds=round(time.time() - t0, 2), end=now())
                run["stages"].append(ent)
                job.log["state"]["stages"].pop(name, None)
                code = 1
                print(f"[{name}] FAILED (simulated)")
                break
            try:
                res = FUNCS[name](job)
                record(job, name, before, snap, ok=True)
                ent.update(status=res or "done", exit=0)
            except Stop as e:
                ent.update(status="STOP", exit=e.code, message=str(e))
                job.log["state"]["stages"].pop(name, None)
                record_writes(job, snap, name)
                print(f"[{name}] STOP: {e}")
                code = e.code
            except StageFailed as e:
                ent.update(status="failed", exit=e.code, message=str(e))
                job.log["state"]["stages"].pop(name, None)
                record_writes(job, snap, name)
                print(f"[{name}] FAILED: {e}")
                code = 1
            ent.update(seconds=round(time.time() - t0, 2), end=now())
            run["stages"].append(ent)
            job.save_log()
            if code:
                break
    finally:
        run.update(end=now(), seconds=round(time.time() - t_run, 2), exit=code)
        job.save_log()
    print(f"total {run['seconds']:.1f} s, exit {code}" + (f"; gates: {job.p('out/gates.json')}" if os.path.exists(job.p('out/gates.json')) else ""))
    return code


def cmd_status(a):
    job = Job(a.job)
    c = job.cfg
    print(f"job {job.dir}\n  slug {job.slug}  profile {job.profile_ref}  label {c.get('label')!r}  front_az {c.get('front_az')}")
    doc = job.gates_doc()
    if doc.get("gates"):
        print(f"\ngates ({doc.get('updated')}):")
        for g in doc["gates"]:
            acc = " (accepted)" if g["id"] in set(doc.get("overrides", [])) else ""
            print(f"  {g['id']:<18s} {g['status']:<4s}{acc} {g['message']}")
    st = job.log["state"]["stages"]
    print("\nstages:")
    for s in STAGES:
        r = st.get(s)
        print(f"  {s:<9s} {'ok ' + r['end'] if r and r.get('ok') else '-'}")
    if job.log["runs"]:
        last = job.log["runs"][-1]
        print(f"\nlast run {last['start']} ({last.get('seconds', 0):.1f} s, exit {last.get('exit')}): "
              + " ".join(f"{e['stage']}={e['seconds']:.1f}s[{e['status']}]" for e in last["stages"]))
        tot = {}
        for r in job.log["runs"]:
            for e in r["stages"]:
                tot[e["stage"]] = tot.get(e["stage"], 0.0) + float(e.get("seconds") or 0.0)
        print("time per stage over all runs: " + ", ".join(f"{k} {v:.0f}s" for k, v in tot.items() if v > 0.05)
              + f"; total {sum(float(r.get('seconds') or 0) for r in job.log['runs']):.0f} s in {len(job.log['runs'])} run(s)")
    return 0


class _SafeOut:
    """stdout that survives a closed pipe (`demo_run.py run JOB | head`): the run goes on, the echo stops."""

    def __init__(self, f):
        self.f, self.dead = f, False

    def write(self, s):
        if not self.dead:
            try:
                return self.f.write(s)
            except (BrokenPipeError, ValueError):
                self.dead = True
        return len(s)

    def flush(self):
        if not self.dead:
            try:
                self.f.flush()
            except (BrokenPipeError, ValueError):
                self.dead = True

    def __getattr__(self, k):
        return getattr(self.f, k)


def main(argv=None):
    if not isinstance(sys.stdout, _SafeOut):
        sys.stdout = _SafeOut(sys.stdout)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("new"); s.add_argument("job"); s.add_argument("--address", required=True)
    s.add_argument("--profile", required=True, help="region profile name (references/regions/<name>.json) or path")
    s.add_argument("--label"); s.add_argument("--front-az", type=float); s.add_argument("--slug")
    s.add_argument("--latlon", help="lat,lon when the city address layer has no match (or for tests)")
    s.add_argument("--studio-url", help="existing Roof Layer Studio artifact URL"); s.add_argument("--waste", type=float)
    s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_new)
    s = sp.add_parser("run"); s.add_argument("job"); s.add_argument("--site-dir", help="complete studio folder")
    s.add_argument("--from", dest="from_", choices=STAGES); s.add_argument("--to", choices=STAGES)
    s.add_argument("--force", action="append", choices=STAGES, help="re-run this stage (repeatable)")
    s.add_argument("--offline", action="store_true", help="PROPMODEL_OFFLINE=1: cache only")
    s.add_argument("--no-render", action="store_true", help="skip the thumbnail and the GPU render bundle")
    s.add_argument("--yes", action="store_true", help="accept overridable STOP gates (recorded in the report)")
    s.set_defaults(fn=cmd_run)
    s = sp.add_parser("status"); s.add_argument("job"); s.set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
