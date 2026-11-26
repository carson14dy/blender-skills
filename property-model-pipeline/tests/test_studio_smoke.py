"""scripts/studio/smoke.py: the pass / fail rules (offline), and a real headless-Chromium run under the CSP server
against a stub page that implements the studio's DOM contract (skipped when node / Playwright / Chromium is
missing). Synthetic data only."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.join(HERE, "..", "scripts", "studio")
sys.path.insert(0, STUDIO)
sys.path.insert(0, HERE)

import package_house as P  # noqa: E402
import smoke  # noqa: E402
from report_pdf import have_playwright  # noqa: E402
from test_package_house import EXPECTED_ROWS, make_job  # noqa: E402

EXP = {"rows": EXPECTED_ROWS, "index_rows": EXPECTED_ROWS, "squares": 21.53, "facets": 4, "source": "report.json"}


def obs(**vp):
    base = {"errors": [], "console_errors": [], "steps": ["load"], "card_found": True, "card_rows": EXPECTED_ROWS,
            "thumb_ok": "loaded", "selected": "m:test-house",
            "measure": {"squares": 21.55, "planes": 4}, "toast": "Found 4 roof planes", "media": []}
    base.update(vp)
    return {"viewports": {"desktop": base}}


def test_judge_pass():
    assert smoke.judge(obs(), EXP) == ([], [])


@pytest.mark.parametrize("override, needle", [
    ({"card_rows": [["Eaves / rakes", "999 ft"]]}, "card rows differ"),
    ({"measure": {"squares": 27.4, "planes": 6}}, "demo roof"),
    ({"measure": {"squares": 21.9, "planes": 4}}, "more than 1 %"),
    ({"errors": ["TypeError: x is undefined"]}, "page error"),
    ({"console_errors": ["Refused to connect to 'data:...' because it violates the Content Security Policy"]}, "console"),
    ({"card_found": False, "cards": ["other"]}, "no card"),
    ({"media": [{"kind": "video", "hidden": False, "state": "error", "src": "v.mp4"}]}, "did not load"),
    ({"failed_step": "open house", "step_error": "timeout"}, "step 'open house'"),
])
def test_judge_failures(override, needle):
    fails, _ = smoke.judge(obs(**override), EXP)
    assert any(needle in f for f in fails), fails


def test_judge_stale_index_rows():
    fails, _ = smoke.judge(obs(), dict(EXP, index_rows=[["Roof area", "1 ft²"]]))
    assert any("stale index" in f for f in fails)


def test_judge_planes_warning_or_strict_failure():
    o = obs(measure={"squares": 21.55, "planes": 5})
    fails, warns = smoke.judge(o, EXP)
    assert not fails and any("5 roof planes" in w for w in warns)
    fails, _ = smoke.judge(o, EXP, strict_planes=True)
    assert any("5 roof planes" in f for f in fails)


def test_judge_hidden_media_passes_and_other_console_errors_warn():
    o = obs(media=[{"kind": "splat", "hidden": True, "state": "unknown"},
                   {"kind": "video", "hidden": False, "state": "loaded"}],
            console_errors=["Failed to load resource: favicon.ico 404"])
    fails, warns = smoke.judge(o, EXP)
    assert not fails and any("favicon" in w for w in warns)


# ------------------------------------------------------------------------------------------------ browser run

STUB = r"""<!doctype html><html><head><meta charset="utf-8"><title>studio stub</title></head><body>
<div id="loading">loading</div><div id="toast" hidden></div>
<button class="tab" data-tab="project">Project</button>
<select id="pHouse"><option value="">demo</option></select>
<div id="measuredList"></div>
<script>
(async () => {
  const mode = (await (await fetch('stub.json')).json()).mode;
  const S = { measure: { squares: 27.4, areaM2: 254.6, planes: 6 } };
  window.roofStudio = { get state() { return { measure: S.measure }; } };
  const idx = await (await fetch('houses/index.json')).json();
  const list = document.getElementById('measuredList');
  for (const h of idx.houses) {
    document.getElementById('pHouse').append(new Option(h.label, 'm:' + h.id));
    const card = document.createElement('div');
    card.className = 'measured-card'; card.dataset.id = h.id;
    card.innerHTML = '<div class="mc-head"><b></b></div><table class="mc-table"></table><div class="row"><button>Open</button></div>';
    card.querySelector('b').textContent = h.label;
    const t = card.querySelector('.mc-table');
    for (const [a, b] of h.summary.rows) {
      const tr = t.insertRow(); tr.insertCell().textContent = a; tr.insertCell().textContent = b;
    }
    card.querySelector('button').onclick = async () => {
      const d = await (await fetch(h.detail)).json();
      document.getElementById('pHouse').value = 'm:' + h.id;
      if (mode !== 'demo') S.measure = { squares: d.verified.areaM2 / 9.290304, areaM2: d.verified.areaM2, planes: d.verified.facets };
      if (mode === 'csp') { try { await fetch('data:application/octet-stream;base64,AAAA'); } catch (e) { /* blocked */ } }
      const toast = document.getElementById('toast'); toast.hidden = false; toast.innerText = 'Found roof planes';
    };
    list.append(card);
  }
  document.getElementById('loading').hidden = true;
})();
</script></body></html>
"""

needs_browser = pytest.mark.skipif(not have_playwright()[0], reason="needs node + playwright + chromium")


@pytest.fixture
def stub_site(tmp_path):
    job = make_job(tmp_path)
    site = tmp_path / "site"
    (site / "houses").mkdir(parents=True)
    (site / "index.html").write_text(STUB)
    (site / "houses" / "index.json").write_text(json.dumps({"houses": []}))
    assert P.main([str(job), "--site", str(site), "--slug", "test-house", "--label", "Test House"]) == 0
    return job, site


@needs_browser
@pytest.mark.parametrize("mode, code, needle", [("ok", 0, None), ("demo", 1, "demo roof"), ("csp", 1, "console")])
def test_smoke_against_stub_page(stub_site, tmp_path, mode, code, needle):
    job, site = stub_site
    (site / "stub.json").write_text(json.dumps({"mode": mode}))
    rc, summary = smoke.run(str(site), "test-house", port=8766, out=str(tmp_path / "out"), job=str(job), timeout=300)
    assert rc == code, summary
    assert set(summary["observed"]) == {"desktop", "phone"}
    if needle:
        assert any(needle in f for f in summary["failures"]), summary["failures"]
    else:
        assert summary["pass"] and (tmp_path / "out" / "smoke_desktop.png").exists()


def test_smoke_out_must_not_be_inside_site(stub_site):
    if not have_playwright()[0]:
        pytest.skip("needs node + playwright + chromium")
    _, site = stub_site
    with pytest.raises(P.PackageError):
        smoke.run(str(site), "test-house", out=str(site / "shots"))


@needs_browser
def test_report_pdf_from_packaged_page(stub_site, tmp_path):
    import report_pdf
    _, site = stub_site
    html = site / "houses" / "test-house" / "report.html"
    pdf = tmp_path / "report.pdf"
    res = report_pdf.render(str(html), str(pdf), expect=["2,153 ± 54 ft²"], min_pages=6)
    assert res["ok"], res
    assert res["pages"] >= 9          # cover + 4 diagrams + measurements + 3 sections, each on its own page
    assert pdf.read_bytes()[:5] == b"%PDF-"
    res = report_pdf.render(str(html), str(tmp_path / "x.pdf"), expect=["not in the report"])
    assert not res["ok"] and res["missing"] == ["not in the report"]
