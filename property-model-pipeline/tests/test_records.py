"""scripts/records.py / propmodel.records on recorded-style replies (tests/fixtures/records: real field names,
invented values, an invented place): county routing, match methods and fallback flags, roof age, changes
after the LiDAR flight, unreachable sources, and no name / taxpayer / contractor / buyer-seller field in any
written file."""
import copy
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "records")
sys.path.insert(0, TOOL)
sys.path.insert(0, FIX)

from fake_http import FakeServer, PROFILE, load  # noqa: E402
from propmodel import confidence as C  # noqa: E402
from propmodel import privacy  # noqa: E402
from propmodel import records as R  # noqa: E402
from propmodel import regions  # noqa: E402
from propmodel.sources import Http  # noqa: E402

TODAY = dt.date(2026, 11, 25)
PLANTED = ("PLANTED", "OWNNAME1", "OWNADDRESS", "MRTNM1", "MRTADR", "contractor_name", "SELLERS_NAME", "BUYERS_NAME",
           "PropertyOwner", "NameADD", "OWNEDBY", "PLANTED PERSON")


def make_job(tmp_path, lidar=None, address="1 Test Ave, Testville, ZZ"):
    job = tmp_path / "job"
    (job / "data").mkdir(parents=True)
    (job / "job.json").write_text(json.dumps({"address": address, "profile": PROFILE}))
    (job / "site.json").write_text(json.dumps({"geocode": {"lat": 10.0, "lon": -140.0, "source": "user"},
                                               "origin": {"lat": 10.0, "lon": -140.0, "h": 0.0}}))
    if lidar:
        (job / "data" / "lidar.json").write_text(json.dumps(lidar))
    return str(job)


def run(job, srv, tmp_path, today=TODAY):
    http = Http(cache_dir=str(tmp_path / "cache"), offline=False, transport=srv)
    return R.run(job, PROFILE, http=http, today=today)


def written(paths):
    return "\n".join(open(p).read() for p in paths.values())


def beta_override(municipality="TESTVILLE"):
    par = load("parcels")
    par["features"][0]["attributes"]["COUNTY"] = "BETA"
    ap = load("address_points")
    ap["features"][0]["attributes"].update(COUNTY="Beta", MUNICIPALITY=municipality)
    return {"parcels": par, "address_points": ap}


def test_alpha_county_end_to_end(tmp_path):
    job = make_job(tmp_path)
    srv = FakeServer()
    rec, paths = run(job, srv, tmp_path)
    assert rec["county"] == "Alpha"
    assert rec["match"]["parcels"] == "point" and rec["match"]["permits"] == "parcel_polygon"
    assert rec["match"]["alpha_assessed"] == "parcel_polygon" and rec["fallbacks"] == []
    d = rec["derived"]
    assert d["assessed"]["land"] == 61000 and d["assessed"]["building"] == 238500 and d["assessed"]["total"] == 299500
    assert d["year_built"] == 1978 and d["storeys"] == 1 and d["grade"] == 4
    assert d["lot_sqft"] == 6458.0 and d["land_use"] == "11 - Single-Family"
    assert d["last_sale"] == {"date": "2023-03-14", "year": None, "price": 289900.0,
                              "source": "Alpha County residential sales 2023"}
    # the neighbour's Addition permit (point in the next parcel) is not this property's
    assert len(rec["permits"]) == 3 and not any(p.get("addition") for p in rec["permits"])
    assert not d["changes_after_lidar"]["flag"]
    # every query named exactly the profile's fields
    prof = regions.load(PROFILE)
    for name, lay in regions.iter_layers(prof):
        if lay.get("out_fields") and "county_sources.Beta" not in name and "hazards" not in name:
            sent = {c["params"].get("outFields") for c in srv.calls if c["url"].startswith(lay["url"])}
            assert sent <= {",".join(lay["out_fields"])}, name
    assert not any("*" in (c["params"].get("outFields") or "") for c in srv.calls)
    # nothing planted by the server reaches a written file; no address string is stored either
    text = written(paths)
    for bad in PLANTED:
        assert bad not in text, bad
    assert "TEST AVE" not in text
    for p in paths.values():
        assert privacy.scan(p, privacy.profile_never(prof)) == []
    # the wrapper's G1 reader and repo-grep tokens understand this schema
    assert C.permits_and_year(rec)[1] == [1978]
    g = {x["id"]: x["status"] for x in C.g1_records(rec, {"flight_date": "2020-12-20", "year": 2020})}
    assert g == {"G1.permits": C.PASS, "G1.year_built": C.PASS}
    assert any("T0000001" in t for t in C.address_tokens({"address": "1 Test Ave"}, None, rec))
    det = json.load(open(paths["detail"]))
    assert "T0000001" not in json.dumps(det) and "ring_lonlat" not in json.dumps(det)


def test_county_routing_beta_inside_city(tmp_path):
    job = make_job(tmp_path)
    srv = FakeServer(override=beta_override("TESTVILLE"))
    rec, paths = run(job, srv, tmp_path)
    assert rec["county"] == "Beta" and rec["inside_city"] is True
    assert not srv.queries("county-a.example.test")                 # no Alpha layer was asked
    assert rec["match"]["beta_parcels"] == "point" and rec["match"]["beta_fullsales"] == "key"
    assert rec["match"]["beta_permits"] == "none"
    skipped = [s for s in rec["sources"] if s["name"] == "beta_permits"][0]
    assert skipped["status"] == "skipped" and "inside the city limits" in skipped["message"]
    d = rec["derived"]
    assert d["assessed"]["total"] == 312000 and d["assessed"]["class"] == "NA-O"
    assert d["last_sale"]["date"] == "2020-08-17" and d["last_sale"]["price"] == 275000   # the $0 sale is skipped
    assert d["zoning"] == "R1"
    text = written(paths)
    for bad in PLANTED:
        assert bad not in text, bad


def test_county_permits_outside_city_and_g1(tmp_path):
    job = make_job(tmp_path, lidar={"flight_date": "2020-12-20", "year": 2020})
    srv = FakeServer(override=beta_override("RURAL TOWNSHIP"))
    rec, _ = run(job, srv, tmp_path)
    assert rec["inside_city"] is False and rec["match"]["beta_permits"] == "key"
    q = srv.queries("BuildingPermits")[0]["params"]
    assert q["where"] == "PID = 'B-000-001'" and "PropertyOwner" not in q["outFields"]
    ch = rec["derived"]["changes_after_lidar"]
    assert ch["flag"] and ch["permits"] == [{"date": "2021-09-30", "work_class": "Addition"}]
    assert ch["basis"].startswith("flight date of this site")
    g = {x["id"]: x["status"] for x in C.g1_records(rec, {"flight_date": "2020-12-20", "year": 2020})}
    assert g["G1.permits"] == C.STOP


def test_fallback_match_is_recorded_and_flagged(tmp_path):
    job = make_job(tmp_path)
    srv = FakeServer(behaviour={"permits": "empty_spatial", "parcels": "empty_spatial"})
    rec, paths = run(job, srv, tmp_path)
    assert rec["match"]["parcels"] == "address"                     # parcel by the address string
    assert rec["match"]["permits"] == "address"
    assert rec["match"]["alpha_assessed"] == "parcel_polygon"        # the parcel polygon still drives the rest
    fb = {f["source"]: f for f in rec["fallbacks"]}
    assert fb["permits"]["first_choice"] == "parcel_polygon" and fb["parcels"]["first_choice"] == "point"
    md = open(paths["section"]).read()
    assert "fallback match" in md and "City building permits by address instead of parcel polygon" in md
    assert "City building permits" in json.load(open(paths["detail"]))["fallback_matches"]
    where = srv.queries("Community/MapServer/3")[-1]["params"]["where"]
    assert where == "MAINADDRESS LIKE '1 TEST AVE%'"
    # the address fallback matched only this house's permits (not the neighbour's)
    assert len(rec["permits"]) == 3


def test_unreachable_source_is_written_not_dropped(tmp_path):
    job = make_job(tmp_path)
    srv = FakeServer(behaviour={"alpha_assessed": "fail"})
    rec, paths = run(job, srv, tmp_path)
    s = [x for x in rec["sources"] if x["name"] == "alpha_assessed"][0]
    assert s["status"] == "unreachable"
    assert s["message"] == "Alpha County assessed values: source not reachable on 2026-11-25"
    assert rec["derived"]["assessed"] is None
    md = open(paths["section"]).read()
    assert "Alpha County assessed values: source not reachable on 2026-11-25" in md
    assert "not found in the public county layers" in md


def test_roof_age_with_and_without_reshingle():
    base = {"parcel": {"values": {}}, "address_point": {"values": {"year_built": 1978}}, "permits": [], "sales": []}
    with_p = copy.deepcopy(base)
    with_p["permits"] = [
        {"work_class": "Reshingle", "issue_date": "2019-05-21", "finalize_date": "2019-06-12", "reroof": True,
         "permit_status": "Finaled", "label": "City building permits"},
        {"work_class": "Reshingle", "issue_date": "2024-07-02", "reroof": True, "dead": True, "permit_status": "Expired"}]
    d = R.derive(with_p, TODAY, (dt.date(2020, 12, 20), "flight"), {"permits": "2015-01-02"})
    assert d["last_reroof"]["date"] == "2019-06-12" and d["last_reroof"]["basis"] == "finalized"
    assert d["roof_age_years"] == 7.5
    assert d["roof_age_text"] == "re-roofed 2019 (Reshingle permit finalized 2019-06-12), about 7 years"
    d = R.derive(base, TODAY, (None, ""), {"permits": "2015-01-02"})
    assert d["last_reroof"] is None and d["roof_age_years"] is None and d["roof_age_min_years"] == 11.9
    assert d["roof_age_text"].startswith("no re-roof permit since 2015-01-02; the roof is at least as old as 2015")
    new = copy.deepcopy(base)
    new["address_point"]["values"]["year_built"] = 2018
    d = R.derive(new, TODAY, (None, ""), {"permits": "2015-01-02"})
    assert d["roof_age_years"] == 8 and "likely original" in d["roof_age_text"]


@pytest.mark.parametrize("work,flag,site", [("Addition", True, False), ("New SF", True, False),
                                            ("New Single Family Dwelling", True, False), ("Reshingle", False, False),
                                            ("Accessory Structure", False, True), ("Deck", False, False)])
def test_changes_after_lidar(work, flag, site):
    p = {"work_class": work, "finalize_date": "2022-09-09", "reroof": bool(R.REROOF.search(work)),
         "addition": bool(R.ADDITION.search(work)), "site_change": bool(R.SITE_CHANGE.search(work))}
    rec = {"address_point": {"values": {"year_built": 1978}}, "permits": [p], "sales": []}
    ch = R.derive(rec, TODAY, (dt.date(2020, 12, 20), "flight"))["changes_after_lidar"]
    assert ch["flag"] is flag and bool(ch["site_changes"]) is site
    before = dict(p, finalize_date="2019-09-09")
    ch = R.derive(dict(rec, permits=[before]), TODAY, (dt.date(2020, 12, 20), "flight"))["changes_after_lidar"]
    assert ch["flag"] is False


def test_year_built_after_lidar_flags():
    rec = {"address_point": {"values": {"year_built": 2021}}, "permits": [], "sales": []}
    ch = R.derive(rec, TODAY, (dt.date(2020, 4, 10), "collection start"))["changes_after_lidar"]
    assert ch["flag"] and "year built 2021" in ch["reasons"][0]


def test_planted_field_is_caught_and_files_deleted(tmp_path):
    job = make_job(tmp_path)
    rec, paths = run(job, FakeServer(), tmp_path)
    bad = copy.deepcopy(rec)
    bad["parcel"]["attributes"]["OWNNAME1"] = "PLANTED NAME"
    with open(paths["data"], "w") as f:
        json.dump(bad, f)
    hits = privacy.scan(paths["data"])
    assert [h["key"] for h in hits] == ["OWNNAME1"]
    with pytest.raises(R.PrivacyError):
        R.check_written(list(paths.values()))
    assert not any(os.path.exists(p) for p in paths.values())
    with pytest.raises(R.PrivacyError):                            # and through write_outputs itself
        R.write_outputs(job, bad)
    assert not os.path.exists(paths["data"])


def test_cli_offline_from_cache(tmp_path):
    job = make_job(tmp_path)
    cache = tmp_path / "cache"
    run(job, FakeServer(), tmp_path)                                # fills the cache
    for p in ("data/records.json", "out/sections/40_records.md", "out/detail_extra/records.json"):
        os.remove(os.path.join(job, p))
    env = dict(os.environ, PROPMODEL_CACHE=str(cache))
    r = subprocess.run([sys.executable, os.path.join(TOOL, "scripts", "records.py"), job, "--profile", PROFILE,
                        "--offline"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "roof age: re-roofed 2019" in r.stdout
    assert os.path.exists(os.path.join(job, "out", "detail_extra", "records.json"))
    empty = tmp_path / "empty_cache"
    env["PROPMODEL_CACHE"] = str(empty)                             # offline with nothing cached: written as such
    r = subprocess.run([sys.executable, os.path.join(TOOL, "scripts", "records.py"), job, "--profile", PROFILE,
                        "--offline"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "source not reachable on" in r.stdout
