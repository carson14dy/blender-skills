"""Roof diagrams (scripts/roof_diagrams.py, propmodel/diagrams.py): totals equal report.json, one label per edge and
facet in the SVGs, waste rule, mismatch exit code, label placement fallback. Synthetic houses only."""
import json
import os
import re
import sys

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from propmodel import diagrams as D  # noqa: E402
from propmodel import report, roofgeom as R  # noqa: E402
import roof_diagrams  # noqa: E402

FAKE_ADDRESS = "4321 Nonesuch Lane, Faketown, ZZ 00000"


def _job(tmp_path, wings, name):
    j = tmp_path / name
    j.mkdir()
    m = R.build(wings)
    site = {"address": FAKE_ADDRESS, "origin": {"lat": 0.5, "lon": -140.5, "h": 0.0}}
    (j / "model.json").write_text(json.dumps({**R.to_mesh_json(m), "site": site}))
    (j / "report.json").write_text(json.dumps(report.report_json(m, site=site)))
    (j / "data").mkdir()
    (j / "data" / "lidar.json").write_text(json.dumps({"dataset": "SYNTH_TEST", "year": 2020}))
    return str(j), m


def gable():
    return [R.Wing(id="A", type="gable", length=10, width=8, eave_height=3.0, pitch=0.5, eave_overhang=0.45,
                   rake_overhang=0.3)]


def hip_l():
    return [R.Wing(id="A", type="hip", azimuth=90, length=16, width=10, eave_height=3.0, pitch=0.5,
                   eave_overhang=0.45, rake_overhang=0.3),
            R.Wing(id="B", type="gable", cx=4, cy=-8, azimuth=0, length=10, width=7, eave_height=3.0, pitch=0.58,
                   eave_overhang=0.45, rake_overhang=0.3)]


@pytest.mark.parametrize("wings,name", [(gable(), "gable"), (hip_l(), "hip_l")])
def test_totals_equal_report_and_one_label_per_edge_and_facet(tmp_path, wings, name):
    job, m = _job(tmp_path, wings, name)
    assert roof_diagrams.main([job, "--dpi", "60"]) == 0
    out = os.path.join(job, "out", "diagrams")
    d = json.load(open(os.path.join(out, "diagrams.json")))
    imp = json.load(open(os.path.join(job, "report.json")))["imperial"]
    for k in ("roof_area_sqft", "roof_squares", "ridge_ft", "hip_ft", "valley_ft", "rake_ft", "eave_ft", "headwall_ft",
              "sidewall_ft"):
        assert abs(d["totals"][k] - imp[k]) < 1e-6, k
    assert d["totals"]["facets"] == len(m.facets)
    assert d["check"]["ok"] and not d["check"]["diffs"] and not d["labels"]["unresolved"]
    for page in ("length", "pitch", "area", "summary"):
        assert os.path.getsize(os.path.join(out, f"{page}.svg")) > 1000
        assert os.path.getsize(os.path.join(out, f"{page}.png")) > 1000
    length = open(os.path.join(out, "length.svg")).read()
    ids = re.findall(r'id="edge-label-(\d+)"', length)
    assert sorted(map(int, ids)) == list(range(len(m.edges)))          # exactly one label per edge
    for e in m.edges:                                                  # and it carries the edge's length
        assert D.fmt_len(e.length) in length
    pitch = open(os.path.join(out, "pitch.svg")).read()
    area = open(os.path.join(out, "area.svg")).read()
    fids = sorted(f.id for f in m.facets)
    assert sorted(re.findall(r'id="facet-pitch-(F\d+)"', pitch)) == fids
    assert sorted(re.findall(r'id="facet-area-(F\d+)"', area)) == fids
    assert len(re.findall(r'id="facet-pitch-F\d+-arrow"', pitch)) == len(fids)   # every sloped facet has its arrow
    for f in m.facets:
        assert D.fmt_pitch(f.slope * 12) in pitch
        assert f"{D.sqft(f.area_true):,.0f} ft²" in area
    summary = open(os.path.join(out, "summary.svg")).read()
    assert 'id="north-arrow"' in summary and "SYNTH_TEST" in summary and "flown 2020" in summary
    # privacy: nothing from the site block reaches a page or the section
    sec = open(os.path.join(job, "out", "sections", "20_diagrams.md")).read()
    for txt in (length, pitch, area, summary, sec, json.dumps(d)):
        assert "Nonesuch" not in txt and "Faketown" not in txt
    assert "| Waste |" in sec and "suggested" in sec


def test_independent_lengths_and_waste_rule(tmp_path):
    job, m = _job(tmp_path, gable(), "g")
    roof_diagrams.main([job, "--dpi", "50"])
    d = json.load(open(os.path.join(job, "out", "diagrams", "diagrams.json")))
    # gable 10 x 8 m, rake overhang 0.3 m: the ridge is 10.6 m whatever the fit says
    assert abs(d["totals"]["ridge_ft"] - 10.6 / 0.3048) < 1e-6
    assert d["by_kind"]["ridge"]["count"] == 1 and d["by_kind"]["eave"]["count"] == 2
    w, n = report.suggested_waste(m)
    assert (d["waste"]["suggested_pct"], d["waste"]["hips_valleys"]) == (w, n) == (10, 0)
    rows = {r["pct"]: r for r in d["waste"]["rows"]}
    assert sorted(rows) == [0, 10, 12, 15, 17, 20] and rows[10]["suggested"] and sum(r["suggested"] for r in rows.values()) == 1
    assert abs(rows[15]["squares"] - d["totals"]["roof_squares"] * 1.15) < 1e-9
    acc = d["accessories_ft"]
    assert abs(acc["drip_edge"] - (d["totals"]["eave_ft"] + d["totals"]["rake_ft"])) < 1e-9
    assert abs(acc["ridge_cap"] - (d["totals"]["ridge_ft"] + d["totals"]["hip_ft"])) < 1e-9
    assert abs(acc["ice_barrier"] - (d["totals"]["eave_ft"] + d["totals"]["valley_ft"])) < 1e-9
    assert d["access"]["summary"]["walkable"]["facets"] == 2           # 6/12 is walkable


def test_hip_waste_and_chosen_row(tmp_path):
    job, m = _job(tmp_path, hip_l(), "h")
    roof_diagrams.main([job, "--dpi", "50", "--waste", "13"])
    d = json.load(open(os.path.join(job, "out", "diagrams", "diagrams.json")))
    w, n = report.suggested_waste(m)
    assert d["waste"]["suggested_pct"] == w and d["waste"]["hips_valleys"] == n and n >= 2
    chosen = [r for r in d["waste"]["rows"] if r["chosen"]]
    assert [r["pct"] for r in chosen] == [13]


def test_stale_report_exits_2(tmp_path):
    job, _ = _job(tmp_path, gable(), "stale")
    rp = os.path.join(job, "report.json")
    r = json.load(open(rp))
    r["imperial"]["ridge_ft"] += 0.5
    json.dump(r, open(rp, "w"))
    assert roof_diagrams.main([job, "--dpi", "50"]) == 2
    d = json.load(open(os.path.join(job, "out", "diagrams", "diagrams.json")))
    assert not d["check"]["ok"] and d["check"]["diffs"][0]["key"] == "ridge_ft"
    # inside the tolerance (0.1 ft) is not a difference
    r["imperial"]["ridge_ft"] -= 0.45
    json.dump(r, open(rp, "w"))
    assert roof_diagrams.main([job, "--dpi", "50"]) == 0


def test_missing_inputs_exit_1(tmp_path):
    assert roof_diagrams.main([str(tmp_path), "--dpi", "50"]) == 1


def test_label_placer_leader_fallback_and_unresolved():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(4, 4), dpi=80)
    ax = fig.add_axes((0.1, 0.1, 0.8, 0.8))
    ax.set_xlim(0, 20); ax.set_ylim(0, 20)
    pl = D.LabelPlacer(ax)
    a = np.array([10.0, 10.0])
    r1 = pl.place("a", "12.3'", a, [(a, 0.0, False)])
    r2 = pl.place("b", "45.6'", a, [(a, 0.0, False)])                 # same spot, no fallback: unresolved
    assert r1["resolved"] and not r2["resolved"]
    cands = [(a, 0.0, False)] + [(a + u * 3.0, 0.0, True) for u in D._dirs(np.array([1.0, 0.0]))]
    r3 = pl.place("c", "7.8'", a, cands)                             # leader-line fallback resolves it
    assert r3["resolved"] and r3["leader"]
    plt.close(fig)
