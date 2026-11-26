"""scripts/demo_run.py end to end on the synthetic gable of tests/fixtures/demo_job, fully offline (PROPMODEL_OFFLINE=1,
a generated cache): stage skipping, the spec STOP, resume after a failed stage, gate values, and the measured roof
area within 1 % of the truth although the spec's overhang prior (0.45 m) is far from the true 1.3 m. With the bpy
module, also blender .. export. The tests in this module share one job and run in file order."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
DEMO = os.path.join(TOOL, "scripts", "demo_run.py")
sys.path.insert(0, TOOL)
sys.path.insert(0, os.path.join(HERE, "fixtures", "demo_job"))
import make_fixture as FX  # noqa: E402

_spec = importlib.util.spec_from_file_location("demo_run_mod", DEMO)
DR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DR)

COMPUTE = ("init", "fetch", "lidar", "city3d", "fit", "edges", "checks")


def run(job, *args, env=None):
    e = dict(os.environ)
    e.pop("PROPMODEL_OFFLINE", None)
    e.pop("DEMO_RUN_FAIL", None)
    e["PROPMODEL_CACHE"] = job["cache"]
    e.update(env or {})
    return subprocess.run([sys.executable, DEMO, *args], capture_output=True, text=True, env=e, timeout=1200)


def last_run(job):
    with open(os.path.join(job["dir"], "run_log.json")) as f:
        r = json.load(f)["runs"][-1]
    return r, {s["stage"]: s["status"] for s in r["stages"]}


def gates(job):
    with open(os.path.join(job["dir"], "out", "gates.json")) as f:
        return {g["id"]: g for g in json.load(f)["gates"]}


@pytest.fixture(scope="module")
def job(tmp_path_factory):
    base = tmp_path_factory.mktemp("demo")
    info = FX.build_all(str(base / "fx"))
    j = {"dir": str(base / "job"), "info": info, "cache": info["cache"]}
    r = run(j, "new", j["dir"], "--address", "1 Synthetic Way, Nowhere", "--profile", info["profile"],
            "--latlon", info["latlon"], "--label", "Synthetic test house")
    assert r.returncode == 0, r.stdout + r.stderr
    p = os.path.join(j["dir"], "job.json")
    cfg = json.load(open(p))
    assert cfg["slug"] == "1-synthetic-way" and cfg["profile"] == info["profile"]
    cfg["skip"] = ["records", "hazards"]          # county / hazard services: not in the synthetic cache
    cfg["flags"] = {"thumb": ["--samples", "2", "--size", "120x90"]}
    json.dump(cfg, open(p, "w"), indent=1)
    return j


def test_refuses_job_inside_the_repo(tmp_path):
    r = subprocess.run([sys.executable, DEMO, "new", os.path.join(TOOL, "jobs", "x"), "--address", "1 A St",
                        "--profile", os.path.join(HERE, "fixtures", "demo_job", "profile.json")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "refusing JOB inside the repo" in (r.stdout + r.stderr)
    assert not os.path.exists(os.path.join(TOOL, "jobs"))


def test_init_to_checks(job):
    J = job["dir"]
    # 1) first run stops at the one manual step, with suggest's spec written
    r = run(job, "run", J, "--offline", "--to", "checks")
    assert r.returncode == 3, r.stdout[-3000:]
    assert "edit " in r.stdout and "spec.json" in r.stdout and "overview.png" in r.stdout
    _, st = last_run(job)
    assert st["records"].startswith("skipped") and st["spec"] == "STOP"
    assert all(st[s] not in ("failed", "STOP") for s in ("init", "fetch", "lidar", "city3d"))
    assert os.path.exists(os.path.join(J, "spec_suggested.json"))
    g = gates(job)
    assert g["G2.density"]["status"] == "PASS" and g["G2.density"]["value"] >= 2
    assert g["G2.flight"]["value"] == "2020-12-05" and g["G2.flight"]["status"] == "PASS"   # leaf-off
    assert g["G2.hillside"]["status"] == "PASS"
    assert g["G2.convention"]["status"] == "PASS"            # the fake city layer traces walls; the profile says so
    assert g["G2.coverage"]["value"] >= 0.85
    assert g["G2.shift"]["value"] == pytest.approx([0.55, -0.80], abs=0.15)
    assert g["G2.lod2_pitch"]["status"] == "PASS"
    li = json.load(open(os.path.join(J, "data", "lidar.json")))
    assert li["flight_date"] == "2020-12-05" and li["leaf_on"] is False and li["extra_dims"] == ["GpsTime"]
    # 2) an unedited spec stops again; the stages before it are skipped as up to date
    r = run(job, "run", J, "--offline", "--to", "checks")
    assert r.returncode == 3
    _, st = last_run(job)
    assert [st[s] for s in ("init", "fetch", "lidar", "city3d")] == ["up to date"] * 4
    # 3) the manual step: accept suggest's single gable (a person would split wings here) and label it
    sp = os.path.join(J, "spec.json")
    spec = json.load(open(sp))
    assert spec["priors"]["M.eave_overhang"]["value"] == 0.45 and "M.eave_overhang" not in spec["free"]
    spec["wings"][0]["label"] = "main gable"
    json.dump(spec, open(sp, "w"), indent=1)
    # 4) a crash in the edges stage stops the run; the next run resumes there
    r = run(job, "run", J, "--offline", "--to", "checks", env={"DEMO_RUN_FAIL": "edges"})
    assert r.returncode == 1
    _, st = last_run(job)
    assert st["fit"] == "done" and st["edges"].startswith("failed")
    r = run(job, "run", J, "--offline", "--to", "checks")
    assert r.returncode == 0, r.stdout[-4000:]
    rr, st = last_run(job)
    assert st["fit"] == "up to date" and st["edges"] == "done" and st["checks"] == "done"
    assert rr["seconds"] > 0 and all("seconds" in s and "exit" in s for s in rr["stages"])
    # 5) numbers: the prior-based first fit is several % low; the measured drip edges fix it
    truth = job["info"]["roof_area_m2"]
    s3 = json.load(open(os.path.join(J, "data", "report_s3.json")))["measurements_si"]["roof.area"]
    rep = json.load(open(os.path.join(J, "report.json")))
    area = rep["measurements_si"]["roof.area"]
    assert s3 < 0.98 * truth
    assert area == pytest.approx(truth, rel=0.01)
    assert rep["measurement_sigma_si"]["roof.area"] > 0
    g = gates(job)
    assert all(g[k]["status"] == "PASS" for k in ("G3.roof_rms", "G3.planes", "G3.conflict", "G4.edges", "G4.sigma",
                                                    "G4.shift_city", "G5.lod2_area", "G5.closure", "G5.pitch", "G5.go"))
    assert g["G4.overhang"]["value"]["M.eave_overhang"] == pytest.approx(1.3, abs=0.1)
    assert g["G4.overhang"]["value"]["M.rake_overhang"] == pytest.approx(0.6, abs=0.1)
    assert g["G4.shift_city"]["value"] == pytest.approx([0.55, -0.80], abs=0.15)
    assert g["G1.records"]["status"] == "WARN"                 # no records in this job: said, not hidden
    conf = open(os.path.join(J, "out", "sections", "90_confidence.md")).read()
    assert "## Confidence statement" in conf and "Assumed (not measured)" in conf and "G5.go" in conf
    cj = json.load(open(os.path.join(J, "out", "detail_extra", "confidence.json")))
    assert cj["go"] is True and cj["roof_area_m2"] == pytest.approx(area, abs=0.01)
    # 6) nothing changed -> nothing runs
    r = run(job, "run", J, "--offline", "--to", "checks")
    assert r.returncode == 0
    _, st = last_run(job)
    assert all(st[s] == "up to date" for s in COMPUTE), st
    # 7) status prints the gate table and the timing log
    r = run(job, "status", J)
    assert r.returncode == 0 and "G5.go" in r.stdout and "time per stage" in r.stdout


@pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="needs the bpy module")
def test_blender_to_export(job):
    J = job["dir"]
    if not os.path.exists(os.path.join(J, "report.json")):
        pytest.skip("needs test_init_to_checks first")
    r = run(job, "run", J, "--offline", "--to", "export")
    assert r.returncode == 0, r.stdout[-4000:]
    _, st = last_run(job)
    assert all(st[s] == "done" for s in ("blender", "details", "site", "thumb", "export")), st
    assert st["diagrams"] in ("done", "missing")
    g = gates(job)
    assert g["G6.mesh"]["status"] == "PASS"
    for f in ("out/model.blend", "out/model_detailed.blend", "out/model_site.blend", "out/thumb.jpg", "out/studio.glb",
              "details.json", "features.json", "site_scene.json"):
        assert os.path.exists(os.path.join(J, f)), f
    det = json.load(open(os.path.join(J, "details.json")))
    assert det["openings"] == [] and any("assumed" in c for c in det["caveats"])
    r = run(job, "run", J, "--offline", "--to", "export")
    _, st = last_run(job)
    assert all(st[s] == "up to date" for s in ("blender", "details", "site", "thumb", "export")), st


def test_overridable_stop_needs_yes(tmp_path):
    jd = tmp_path / "j"
    jd.mkdir()
    (jd / "job.json").write_text(json.dumps({"address": "1 A St", "slug": "a"}))
    soft = DR.C.gate("G1.permits", DR.C.STOP, "addition after the LiDAR", stage="lidar", overridable=True)
    hard = DR.C.gate("G4.sigma", DR.C.STOP, "sigma zero", stage="edges")
    with pytest.raises(DR.Stop):
        DR.Job(str(jd)).set_gates("lidar", [soft])
    j = DR.Job(str(jd), yes=True)
    j.set_gates("lidar", [soft])                       # accepted, recorded
    assert "G1.permits" in json.load(open(jd / "out" / "gates.json"))["overrides"]
    DR.Job(str(jd)).set_gates("lidar", [soft])         # stays accepted on later runs
    with pytest.raises(DR.Stop):
        DR.Job(str(jd), yes=True).set_gates("edges", [hard])   # hard gates never pass with --yes


def _pm_module():
    spec = importlib.util.spec_from_file_location("pm_cli_demo", os.path.join(TOOL, "scripts", "pm.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_fetch_sends_explicit_fields_only(monkeypatch):
    pm = _pm_module()
    from propmodel import sources
    seen = {}

    def fake(layer_url, lat, lon, radius, cache_dir, out_fields, where="1=1"):
        seen.update(url=layer_url, out_fields=out_fields, where=where)
        return [{"source": "x", "id": "x/7", "tags": {"OBJECTID": 7, "NUMBERSTORIES": 2, "OWNEDBY": "never"},
                 "ring_lonlat": [[0, 0], [1e-4, 0], [1e-4, 1e-4], [0, 0]]}]
    monkeypatch.setattr(sources, "arcgis_footprints", fake)

    class A:
        footprint_geojson = None
        footprint_layer = "https://gis.example.invalid/arcgis/rest/services/B/MapServer/5"
        footprint_fields = "OBJECTID,NUMBERSTORIES"
        footprint_where = "STATUS='Active'"
        footprint_name = "city"
        radius = 60
    got = pm._city_footprints(A, 10.0, -140.0)
    assert seen["out_fields"] == ["OBJECTID", "NUMBERSTORIES"] and seen["where"] == "STATUS='Active'"
    assert got[0]["source"] == "city" and got[0]["id"] == "city/7"
    assert got[0]["tags"] == {"OBJECTID": 7, "NUMBERSTORIES": 2}          # nothing but the named fields
    with pytest.raises(ValueError):
        pm._field_list("*")
    with pytest.raises(ValueError):
        pm._field_list("OBJECTID,*")


def test_offline_guard_blocks_requests(monkeypatch, tmp_path):
    import requests
    from requests import sessions
    from propmodel import ept, features
    orig = sessions.Session.request
    monkeypatch.setenv("PROPMODEL_OFFLINE", "1")
    try:
        assert ept.install_offline_guard()
        with pytest.raises(ept.OfflineMiss):
            requests.get("https://example.invalid/x")
        with pytest.raises(ept.OfflineMiss):          # the cached helpers fail fast on a miss too
            features.arcgis_query("https://example.invalid/arcgis/rest/services/A/MapServer/0", ["OBJECTID"], str(tmp_path))
        with pytest.raises(ValueError):
            features.arcgis_query("https://example.invalid/x/MapServer/0", ["*"], str(tmp_path))
    finally:
        sessions.Session.request = orig
