"""propmodel.hazards / scripts/hazards.py on recorded-style replies (tests/fixtures/records): Storm Events CSV
parsing (narratives dropped, knots -> mph), the 1 / 5 / 10 mile filter, events after the re-roof, the
preliminary gap (IEM + SPC, de-duplicated), NFHL worst zone, tree overhang on a synthetic roof with a known
canopy patch, roof access classes, unreachable-source wording, and the LATER stubs."""
import datetime as dt
import io
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

import synth_roof  # noqa: E402
from fake_http import FakeServer, PROFILE, text  # noqa: E402
from propmodel import hazards as H  # noqa: E402
from propmodel import privacy  # noqa: E402
from propmodel import records as R  # noqa: E402
from propmodel.sources import Http  # noqa: E402

TODAY = dt.date(2026, 11, 25)
LAT, LON = 10.0, -140.0


def storm_rows():
    rows, latest = H.parse_storm_csv(io.StringIO(text("storm_events_sample.csv")))
    return rows, latest


def make_job(tmp_path, with_records=True):
    job = tmp_path / "job"
    (job / "data").mkdir(parents=True)
    (job / "job.json").write_text(json.dumps({"address": "1 Test Ave, Testville, ZZ", "profile": PROFILE}))
    (job / "site.json").write_text(json.dumps({"geocode": {"lat": LAT, "lon": LON, "source": "user"},
                                               "origin": {"lat": LAT, "lon": LON, "h": 0.0}}))
    if with_records:
        http = Http(cache_dir=str(tmp_path / "cache"), offline=False, transport=FakeServer())
        R.run(str(job), PROFILE, http=http, today=TODAY)
    return str(job)


def test_storm_csv_drops_narratives_and_converts_knots():
    rows, latest = storm_rows()
    assert latest == dt.date(2026, 5, 20)
    assert all(r["event_type"] != "Heavy Snow" for r in rows)              # zone event without a point: dropped
    blob = json.dumps(rows)
    assert "NARRATIVE" not in blob and "PLANTED PERSON" not in blob
    wind = {r["date"]: r for r in rows if r["kind"] == "wind"}
    assert wind["2022-08-01"]["speed_kt"] == 61 and wind["2022-08-01"]["speed_mph"] == 70
    assert wind["2022-08-01"]["measured"] is False                         # EG = estimated gust
    assert wind["2021-05-05"]["speed_mph"] == 58 and wind["2021-05-05"]["measured"] is True   # 50 kt measured
    assert H.kt_to_mph(50) == pytest.approx(57.539, abs=1e-3)


def test_distance_filter_and_tornado_track():
    rows, _ = storm_rows()
    start = dt.date(2016, 11, 25)
    ev = {r["date"]: r for r in H.near(rows, LAT, LON, 10.0, start, TODAY)}
    assert "2019-06-20" not in ev                                          # 15 mi
    assert "2016-03-01" not in ev                                          # before the 10-year window
    assert ev["2018-05-30"]["dist_mi"] == pytest.approx(0.8, abs=0.02)     # track end, not its 12 mi start
    assert ev["2023-06-10"]["dist_mi"] == pytest.approx(0.5, abs=0.01) and ev["2023-06-10"]["bearing"] == "N"
    assert ev["2017-07-04"]["dist_mi"] == pytest.approx(3.0, abs=0.02) and ev["2017-07-04"]["bearing"] == "E"
    one = H.near(rows, LAT, LON, 1.0, start, TODAY)
    assert sorted(e["date"] for e in one) == ["2016-12-01", "2018-05-30", "2023-06-10"]


def test_after_reroof_flag_and_summary():
    rows, _ = storm_rows()
    ev = H.near(rows, LAT, LON, 10.0, dt.date(2016, 11, 25), TODAY)
    for e in ev:
        e["status"] = "final"
    H.flag_after_reroof(ev, "2019-06-12")
    flags = {e["date"]: e["after_reroof"] for e in ev}
    assert flags["2023-06-10"] and flags["2022-08-01"] and not flags["2017-07-04"] and not flags["2018-05-30"]
    s = H.summarize(ev, "2019-06-12", 10)
    assert [e["date"] for e in s["after_reroof"]] == ["2023-06-10", "2022-08-01"]
    assert s["max_hail"]["5"] == {"size_in": 1.75, "date": "2017-07-04"}
    assert s["counts"]["1"]["hail"] == 2 and s["counts"]["10"]["wind"] == 2
    t = H.summary_sentence(s)
    assert "Hail >= 1.00 in reported within 1 mile: 2023-06-10 (1.25 in hail), 2016-12-01 (1.00 in hail)" in t
    assert "Events after the last re-roof permit (2019-06-12): 2023-06-10 (1.25 in hail), 2022-08-01 (70 mph wind)" in t
    H.flag_after_reroof(ev, None)
    assert all(e["after_reroof"] is None for e in ev)
    assert "No re-roof permit on record" in H.summary_sentence(H.summarize(ev, None, 10))


def test_newest_storm_file_is_chosen():
    files = H.storm_files(text("stormevents_index.html"))
    assert files[2026] == "StormEvents_details-ftp_v1.0_d2026_c20261119.csv.gz" and min(files) == 2015


def test_reports_end_to_end_with_preliminary_gap(tmp_path):
    job = make_job(tmp_path)
    srv = FakeServer()
    hz, paths = H.run(job, PROFILE, http=Http(cache_dir=str(tmp_path / "cache"), offline=False, transport=srv),
                      parts=["reports"], today=TODAY)
    st = hz["storms"]
    assert st["final_through"] == "2026-05-20"
    iem = [e for e in st["events"] if e["source"] == "IEM local storm reports"]
    spc = [e for e in st["events"] if e["source"] == "NOAA SPC storm reports"]
    assert {(e["date"], e["kind"]) for e in iem} == {("2026-07-15", "hail"), ("2026-08-01", "wind")}  # UTC -> local day
    assert len(spc) == 1 and spc[0]["size_in"] == 1.0                      # the SPC copy of the IEM hail is dropped
    assert all(e["status"] == "preliminary" for e in iem + spc)
    assert all(e["after_reroof"] for e in iem + spc)                       # re-roof permit 2019-06-12 (records.json)
    assert not any(k in e for e in st["events"] for k in ("lat", "lon"))   # no coordinates kept
    blob = open(paths["data"]).read() + open(paths["section"]).read() + open(paths["detail"]).read()
    assert "PLANTED" not in blob and "remark" not in blob
    assert st["radar_hail"] and st["radar_hail"][0]["max_size_in"] == 1.75 and st["radar_hail"][0]["nearest_mi"] < 1
    swdi = srv.queries("swdiws")
    assert swdi and all("bbox" in c["params"] and "center" not in c["params"] for c in swdi)
    assert all(":" in c["url"].rsplit("/", 1)[-1] for c in swdi)
    md = open(paths["section"]).read()
    assert "radar-estimated" in md and "(preliminary)" in md and "NCEI Storm Events are final through 2026-05-20" in md
    for p in paths.values():
        assert privacy.scan(p) == []


@pytest.mark.parametrize("rows,zone,sfha", [
    ([{"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD", "SFHA_TF": "F"}], "X", False),
    ([{"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD", "SFHA_TF": "F"},
      {"FLD_ZONE": "X", "ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "SFHA_TF": "F"}], "X", False),
    ([{"FLD_ZONE": "X", "SFHA_TF": "F"}, {"FLD_ZONE": "AE", "SFHA_TF": "T", "STATIC_BFE": 1401.2},
      {"FLD_ZONE": "D", "SFHA_TF": "F"}], "AE", True),
    ([{"FLD_ZONE": "AE", "SFHA_TF": "T"}, {"FLD_ZONE": "AE", "ZONE_SUBTY": "FLOODWAY", "SFHA_TF": "T"},
      {"FLD_ZONE": "VE", "SFHA_TF": "T"}], "VE", True),
])
def test_nfhl_worst_zone(rows, zone, sfha):
    w = H.worst_flood_zone(rows)
    assert w["zone"] == zone and w["sfha"] is sfha
    assert H.worst_flood_zone([]) is None


def test_nfhl_details():
    w = H.worst_flood_zone([{"FLD_ZONE": "X", "ZONE_SUBTY": "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "SFHA_TF": "F",
                             "STATIC_BFE": -9999}, {"FLD_ZONE": "X", "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD"}])
    assert w["description"].startswith("0.2 % annual-chance") and w["static_bfe_ft"] is None
    w = H.worst_flood_zone([{"FLD_ZONE": "AE", "ZONE_SUBTY": "FLOODWAY", "SFHA_TF": "T"}, {"FLD_ZONE": "AE", "SFHA_TF": "T"}])
    assert w["subtype"] == "FLOODWAY"


def test_tree_overhang_known_canopy_patch():
    import numpy as np
    m = synth_roof.model()
    pts = synth_roof.points()
    xyz = np.column_stack([pts[:, 0], pts[:, 1], pts[:, 2] - synth_roof.DATUM])
    ov = H.tree_overhang(m["facets"], xyz, m["edges"])
    assert ov["roof_plan_m2"] == 200.0 and ov["canopy_m2"] == 16.0 and ov["pct"] == 8.0   # chimney ignored
    assert [(e["kind"], e["facade"]) for e in ov["edges"]] == [("rake", "W")]
    assert 30 <= ov["edges"][0]["pct"] <= 40
    bare = xyz[xyz[:, 2] < xyz[:, 1] * 0.25 + 3.0 + 0.4]                   # no canopy returns at all
    assert H.tree_overhang(m["facets"], bare, m["edges"])["pct"] == 0.0


def test_roof_access_classes():
    facets = [{"id": f"F{i}", "pitch_rise_per_12": p, "area_m2": 10.0, "azimuth": 180}
              for i, p in enumerate((4.0, 6.0, 6.5, 8.0, 9.0, 10.0))]
    edges = [{"kind": "eave", "p0": [0, 0, 2.8], "p1": [5, 0, 2.8]}, {"kind": "eave", "p0": [0, 9, 5.9], "p1": [5, 9, 5.9]},
             {"kind": "ridge", "p0": [0, 4, 8.1], "p1": [5, 4, 8.1]}]
    a = H.roof_access(facets, edges, storeys=2)
    assert [f["class"] for f in a["facets"]] == ["walkable", "walkable", "steep", "steep", "steep", "very steep"]
    assert a["share_pct"] == {"walkable": 33.3, "steep": 50.0, "very steep": 16.7}
    assert a["highest_eave_m"] == 5.9 and a["lowest_eave_m"] == 2.8 and a["highest_ridge_m"] == 8.1


def test_roof_part_merges_and_writes_colour(tmp_path):
    job = make_job(tmp_path)
    http = Http(cache_dir=str(tmp_path / "cache"), offline=False, transport=FakeServer())
    H.run(job, PROFILE, http=http, parts=["reports", "flood"], today=TODAY)
    hz, _ = H.run(job, PROFILE, http=http, parts=["roof"], today=TODAY)
    assert hz["roof"]["status"] == "pending" and hz["storms"]["events"]           # no model yet; reports kept
    synth_roof.write(job)
    hz, paths = H.run(job, PROFILE, http=Http(cache_dir=str(tmp_path / "cache"), offline=True), parts=["roof"],
                      today=TODAY)
    assert hz["storms"]["events"] and hz["flood"]["worst"]["zone"] == "AE"       # earlier parts kept
    assert hz["roof"]["tree_overhang"]["pct"] == 8.0
    assert hz["roof_colour"]["rgb"] == list(synth_roof.ROOF_RGB) and hz["roof_colour"]["name"] == "brown"
    assert "estimate" in hz["roof_colour"]["label"] and "2026-04-21" in hz["roof_colour"]["label"]
    assert hz["roof"]["access"]["storeys"] == 1.0
    md = open(paths["section"]).read()
    assert "Tree overhang" in md and "8 % of the roof plan" in md and "leaf-off" in md


def test_unreachable_wording_and_no_stop(tmp_path):
    job = make_job(tmp_path, with_records=False)

    def down(method, url, **k):
        raise ConnectionError("network down")
    hz, paths = H.run(job, PROFILE, http=Http(cache_dir=str(tmp_path / "c2"), offline=False, transport=down),
                      today=TODAY)
    assert hz["flood"]["status"] == "unreachable"
    assert hz["flood"]["message"] == "FEMA NFHL flood zones: source not reachable on 2026-11-25"
    msgs = [s.get("message") for s in hz["storms"]["sources"]]
    assert "NOAA NCEI Storm Events: source not reachable on 2026-11-25" in msgs
    assert "IEM local storm reports: source not reachable on 2026-11-25" in msgs
    assert hz["neighbourhood"]["status"] == "unreachable"
    assert hz["storms"]["events"] == []                                          # nothing guessed
    md = open(paths["section"]).read()
    assert md.count("source not reachable on 2026-11-25") >= 3
    off = H.run(job, PROFILE, http=Http(cache_dir=str(tmp_path / "c3"), offline=True), today=TODAY)[0]
    assert off["flood"]["status"] == "unreachable" and "offline" in off["flood"]["error"]


def test_neighbourhood_counts_only(tmp_path):
    job = make_job(tmp_path)
    srv = FakeServer()
    hz, paths = H.run(job, PROFILE, http=Http(cache_dir=str(tmp_path / "cache"), offline=False, transport=srv),
                      parts=["permits"], today=TODAY)
    nb = hz["neighbourhood"]
    assert nb["status"] == "ok" and nb["by_year"]["2024"] == 1 and set(nb["by_year"]) == {str(y) for y in range(2021, 2027)}
    q = srv.queries("Community/MapServer/3")[-1]["params"]
    assert q["where"] == "WORKCLASS = 'Reshingle'" and q["outFields"] == "OBJECTID,ISSUEDATE"
    assert q["distance"] == 300 and q["returnGeometry"] == "false"
    assert "TEST AVE" not in json.dumps(nb)


def test_later_stubs_and_code_notes():
    lt = H.later({})
    assert all(v["status"] == "not included" for v in lt.values())
    assert "GRIB2" in lt["mesh"]["text"] and "not publicly recorded" in lt["roof_material"]["text"]
    cn = {"hazards": {"code_notes": [{"text": "City adopted the 2021 IRC", "source_url": "https://example.test/code",
                                      "read_date": "2026-11-20"}]}}
    c = H.later(cn)["code"]
    assert c["status"] == "ok" and c["notes"][0]["read_date"] == "2026-11-20"


def test_swdi_error_reply_and_parse():
    with pytest.raises(H.SourceUnreachable):
        H.swdi_parse("error,ERROR VALIDATING 'dateRange=startDate:endDate'.  maximum 744 hours.")
    rows = H.swdi_parse(text("swdi_nx3hail.csv"))
    assert len(rows) == 2 and rows[0]["maxsize_in"] == 1.75 and rows[0]["prob"] == 100


def test_cli_offline(tmp_path):
    job = make_job(tmp_path)
    cache = tmp_path / "cache"
    H.run(job, PROFILE, http=Http(cache_dir=str(cache), offline=False, transport=FakeServer()), today=dt.date.today())
    env = dict(os.environ, PROPMODEL_CACHE=str(cache))
    r = subprocess.run([sys.executable, os.path.join(TOOL, "scripts", "hazards.py"), job, "--profile", PROFILE,
                        "--only", "flood,permits", "--offline"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "flood zone AE" in r.stdout
    r = subprocess.run([sys.executable, os.path.join(TOOL, "scripts", "hazards.py"), job, "--only", "hail"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "unknown part" in r.stderr


def test_iem_window_that_hits_the_reply_cap_is_split(tmp_path):
    import json as _json
    real = FakeServer()
    rain = {"type": "Feature", "properties": {"typetext": "RAIN", "magf": 0.1, "valid": "2026-07-01T00:00:00Z",
                                              "lat": LAT, "lon": LON}, "geometry": None}

    def capped(method, url, params=None, **k):
        if "mesonet" in url:
            sts = dt.date.fromisoformat(params["sts"][:10])
            ets = dt.date.fromisoformat(params["ets"][:10])
            if (ets - sts).days > 3:                                  # a long window: the server's cap
                return _json.dumps({"type": "FeatureCollection", "features": [rain] * H.IEM_CAP}).encode()
        return real(method, url, params=params, **k)
    rows, srcs = H.preliminary_events(Http(cache_dir=str(tmp_path), offline=False, transport=capped),
                                      {"hazards": {"wfo": ["XXX"], "timezone": "America/Chicago"}}, LAT, LON,
                                      dt.date(2026, 7, 1), dt.date(2026, 8, 30), TODAY)
    assert any(r["kind"] == "hail" and r["date"] == "2026-07-15" for r in rows)       # found after the split
    iem = [s for s in srcs if s["name"] == "iem_lsr"][0]
    assert iem["status"] == "ok" and "note" not in iem


def test_radar_caveat_near_the_radar(tmp_path):
    http = Http(cache_dir=str(tmp_path), offline=False, transport=FakeServer())
    _, _, cav = H.radar_hail(http, LAT, LON, ["2026-07-15"], TODAY, radar_site={"id": "KXXX", "lat": 10.03, "lon": -140.0})
    assert "cone of silence" in cav and "KXXX" in cav
    _, _, cav = H.radar_hail(http, LAT, LON, ["2026-07-15"], TODAY, radar_site={"id": "KYYY", "lat": 11.0, "lon": -140.0})
    assert "cone of silence" not in cav
