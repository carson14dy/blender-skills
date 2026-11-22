"""build_log.py: stages, gates, shortcuts, the blockers `close` checks, the report and the timing line."""
import hashlib
import json
import subprocess
import sys

from run_all import ROOT, TMP

BL = str(ROOT / "scripts" / "build_log.py")
ACCEPT = {"name": "Shed", "units": "ft", "checks": [
    {"id": "windows", "type": "count", "objects": "Shed_Window_*", "expect": 4, "source": "given"},
    {"id": "ridge", "type": "extent", "objects": "Shed_Roof", "expect": 10.5, "source": "assumed", "note": "6/12 pitch"}]}


def _dir(name):
    d = TMP / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "acceptance.json").write_text(json.dumps(ACCEPT))
    return d


def _bl(d, *args, stdin=None):
    """Run build_log.py in folder d. Returns (exit code, parsed last JSON line or the text)."""
    p = subprocess.run([sys.executable, BL, *args, "--log", str(d / "log.json")], input=stdin, capture_output=True,
                       text=True, cwd=d, timeout=60)
    out = p.stdout.strip()
    return p.returncode, json.loads(out.splitlines()[-1]) if out.startswith("{") else out


def _sha(d):
    return hashlib.sha256((d / "acceptance.json").read_bytes()).hexdigest()[:12]


def _acc(d, ok=True, sha=None):
    res = {"ok": True, "pass": ok, "spec_sha": sha or _sha(d), "partial": False, "checked": 2, "passed": 2 - (not ok),
           "failed": [] if ok else ["windows"], "assumed": ["ridge: 6/12 pitch"], "seconds": 0.4,
           "results": [{"id": "windows", "pass": ok, "expect": 4, "got": 4 if ok else 3},
                       {"id": "ridge", "pass": True, "expect": 10.5, "got": 10.5, "unit": "ft"}]}
    return "Blender noise\n@@JSON@@" + json.dumps(res) + "\nmore noise\n"


QA = "@@JSON@@" + json.dumps({"ok": True, "pass": True, "complete": True, "skipped": [], "errors": [],
                              "warnings": ["w1", "w2"], "objects": {"A": {"tris": 12}}, "seconds": 0.2})


def test_build_log_blocks_until_true():
    d = _dir("bl1")
    rc, r = _bl(d, "start", "--name", "Shed", "--accept", "acceptance.json")
    assert rc == 0 and r["checks"] == 2 and r["assumed"] == ["ridge: 6/12 pitch"], r
    assert _bl(d, "start", "--name", "Shed", "--accept", "acceptance.json")[0] == 1        # exists: needs --force
    rc, r = _bl(d, "close")
    text = " | ".join(r["blockers"])
    assert rc == 2 and not r["done"] and len(r["blockers"]) == 3, r
    assert "no full acceptance run" in text and "no qa gate" in text and "look gate" in text, text
    assert _bl(d, "stage", "detail")[0] == 0 and _bl(d, "stage", "other", "--done")[0] == 1
    assert _bl(d, "gate", "acceptance", "--stdin", stdin=_acc(d, ok=False))[1]["stage"] == "detail"
    rc, r = _bl(d, "close")
    msg = ("check 'windows' fails (expected 4, got 3): fix it, or log a shortcut with --check windows "
           "and get the user's yes")
    assert msg in r["blockers"] and any("still open" in b for b in r["blockers"]), r
    assert _bl(d, "stage", "detail", "--done")[1]["seconds"] >= 0
    assert _bl(d, "shortcut", "--kind", "omitted", "--what", "3 windows, not 4", "--why", "x", "--check",
               "windows")[1]["shortcut"] == 1
    blk = _bl(d, "close")[1]["blockers"]
    assert any("windows" in b and "needs the user's yes" in b for b in blk), blk
    assert _bl(d, "shortcut", "--kind", "lazy", "--what", "a", "--why", "b")[0] == 1         # unknown kind
    assert _bl(d, "shortcut", "--kind", "preview", "--what", " ", "--why", "b")[0] == 1      # empty --what
    assert _bl(d, "approve", "7")[0] == 1 and _bl(d, "approve", "1")[0] == 0
    assert not any("windows" in b for b in _bl(d, "close")[1]["blockers"])
    _bl(d, "gate", "qa", "--stdin", stdin=QA)
    _bl(d, "gate", "look", "--pass")                                                         # a look needs a note
    assert any("look" in b for b in _bl(d, "close")[1]["blockers"])
    _bl(d, "gate", "look", "--pass", "--note", "review sheet, 6 views")
    rc, r = _bl(d, "close")
    assert rc == 0 and r["done"] and r["blockers"] == [] and r["shortcuts"] == 1, r
    _bl(d, "gate", "qa", "--stdin", stdin=QA.replace('"complete": true', '"complete": false'))
    assert any("incomplete" in b for b in _bl(d, "close")[1]["blockers"])                   # a skipped QA check


def _done(name, qa=("--stdin",)):
    """A started log with a passing acceptance run, a qa gate (from QA, or e.g. --pass) and a look."""
    d = _dir(name)
    _bl(d, "start", "--name", "Shed", "--accept", "acceptance.json")
    for args, stdin in ((("gate", "acceptance", "--stdin"), _acc(d)), (("gate", "qa", *qa), QA),
                        (("gate", "look", "--pass", "--note", "ok"), None)):
        _bl(d, *args, stdin=stdin)
    return d


def test_any_failed_gate_blocks():
    d = _done("bl4")
    assert _bl(d, "close")[1]["done"]
    _bl(d, "gate", "look-materials", "--fail", "--note", "Workbench shows flat grey")
    rc, r = _bl(d, "close")
    msg = ("gate 'look-materials' failed: pass it again, or log a shortcut with --check look-materials "
           "and get the user's yes")
    assert rc == 2 and r["blockers"] == [msg], r
    _bl(d, "shortcut", "--kind", "unverified", "--what", "materials not seen", "--why", "x", "--check", "look-materials")
    assert _bl(d, "close")[1]["blockers"] == [msg]                                         # not approved yet
    _bl(d, "approve", "1")                                                                 # the user said yes
    assert _bl(d, "close")[1]["done"]
    _bl(d, "gate", "blockout", "--stdin", stdin=json.dumps({"ok": True, "pass": False, "spec_sha": _sha(d),
                                                             "partial": True, "failed": ["ridge"]}))
    assert any("gate 'blockout' failed" in b for b in _bl(d, "close")[1]["blockers"])      # a partial run counts too
    _bl(d, "gate", "blockout", "--stdin", stdin=json.dumps({"ok": True, "pass": True, "spec_sha": _sha(d),
                                                             "partial": True}))
    assert _bl(d, "close")[1]["done"]                                                      # passed again


def test_manual_qa_does_not_count():
    d = _done("bl5", qa=("--pass",))
    rc, r = _bl(d, "close")
    assert rc == 2 and r["blockers"] == ["qa gate needs a qa_check.py result (--stdin or --result)"], r
    _bl(d, "gate", "qa", "--stdin", stdin=QA)
    assert _bl(d, "close")[1]["done"]


def test_build_log_detects_a_changed_file():
    d = _done("bl2")
    assert _bl(d, "close")[1]["done"]
    looser = dict(ACCEPT, checks=[dict(ACCEPT["checks"][0], expect=3), ACCEPT["checks"][1]])
    (d / "acceptance.json").write_text(json.dumps(looser))                                   # edited to pass
    blk = _bl(d, "close")[1]["blockers"]
    assert any("after the last acceptance run" in b for b in blk) and any("since start" in b for b in blk), blk
    _bl(d, "gate", "acceptance", "--stdin", stdin=_acc(d))
    rc, r = _bl(d, "close")
    assert rc == 2 and len(r["blockers"]) == 1 and "brief-change" in r["blockers"][0], r
    _bl(d, "shortcut", "--kind", "brief-change", "--what", "3 windows", "--why", "the user dropped one")
    assert _bl(d, "close")[1]["done"]


def test_build_log_gate_parsing_and_report():
    d = _dir("bl3")
    _bl(d, "start", "--name", "Shed", "--accept", "acceptance.json", "--session", "local")
    _bl(d, "stage", "blockout")
    (d / "acc.txt").write_text(_acc(d))
    (d / "rt.txt").write_text('log line\nRT_QA {"pass": true, "blender": "5.2.4", "tris": 900, "errors": [], '
                              '"warnings": ["w"]}\nroof QA passed\n')
    assert _bl(d, "gate", "acceptance", "--result", "acc.txt")[1]["pass"]
    assert _bl(d, "gate", "qa", "--result", "rt.txt")[1]["pass"]
    assert _bl(d, "gate", "x", "--stdin", stdin="not json")[0] == 1 and _bl(d, "gate", "x", "--stdin", stdin="")[0] == 1
    _bl(d, "stage", "render")
    prev = {"ok": True, "preset": "preview", "samples": 64, "res": [960, 540], "deliverable": False, "device": "CPU",
            "sec_per_image": 3.5, "files": ["a.png"], "warning": "preview quality (64 samples, 50% = 960x540)"}
    assert not _bl(d, "gate", "render", "--stdin", "--deliverable", stdin=json.dumps(prev))[1]["pass"]
    assert any("deliverable gate 'render'" in b for b in _bl(d, "close")[1]["blockers"])
    final = dict(prev, preset="final", samples=512, res=[1920, 1080], deliverable=True, warning=None)
    assert _bl(d, "gate", "render", "--stdin", "--deliverable", stdin=json.dumps(final))[1]["pass"]
    _bl(d, "gate", "look", "--pass", "--note", "hero still, sharp, no fireflies")
    _bl(d, "stage", "render", "--done")
    _bl(d, "shortcut", "--kind", "unverified", "--what", "Window frames not seen up close.", "--why", "no drawing",
        "--effect", "visible closer than 2 m", "--check", "windows")
    _bl(d, "shortcut", "--kind", "preview", "--what", "Hero at 1920x1080", "--why", "no GPU", "--approved")
    rc, text = _bl(d, "report")
    assert rc == 0 and text.startswith("Build: Shed (local, "), text
    for part in ("Acceptance: 2 of 2 checks pass (acceptance.json ", "1. unverified: Window frames not seen up close. "
                 "Why: no drawing. Effect: visible closer than 2 m. Check: windows. NOT APPROVED",
                 "2. preview: Hero at 1920x1080. Why: no GPU. APPROVED", "Assumed values (1): ridge: 6/12 pitch",
                 "qa pass (0 errors, 1 warnings); render pass, final 1920x1080 512 samples; look pass",
                 "\nTime: blockout ", " min, render ", "\nDone: yes, 1 shortcut awaits your OK (1)"):
        assert part in text, (part, text)
    js = _bl(d, "report", "--json")[1]
    assert js["done"] and js["text"].splitlines()[1:] == text.splitlines()[1:], js
    times = d / "times.jsonl"
    for _ in range(2):
        rc, r = _bl(d, "close", "--times", str(times))
        assert rc == 0 and r["done"] and r["unapproved"] == [1], r
    rows = [json.loads(x) for x in times.read_text().splitlines()]
    assert len(rows) == 2 and rows[0]["name"] == "Shed" and rows[0]["blender"] == "5.2.4" and rows[0]["tris"] == 900
    assert set(rows[0]["stages"]) == {"blockout", "render"} and rows[0]["gates"]["acceptance"] == 0.4, rows[0]
    assert rows[0]["renders"][-1] == {"res": [1920, 1080], "samples": 512, "sec_per_image": 3.5, "device": "CPU"}
    assert rows[0]["checks"] == 2 and rows[0]["passed"] == 2 and rows[0]["shortcuts"] == 2 and rows[0]["done"]


def test_rejected_shortcut_blocks_until_redone():
    d = _done("bl6")
    _bl(d, "shortcut", "--kind", "assumed", "--what", "pitch 6/12", "--why", "not in the brief", "--check", "ridge")
    assert _bl(d, "close")[1]["done"]                                       # an assumed value alone does not block
    assert _bl(d, "reject", "2")[0] == 1 and _bl(d, "resolve", "1", "--how", " ")[0] == 1
    assert _bl(d, "reject", "1", "--why", "work the pitch out")[1]["rejected"] == [1]
    rc, r = _bl(d, "close")
    assert rc == 2 and r["blockers"] == ["shortcut 1 rejected by the user: redo it (pitch 6/12)"], r
    assert r["unapproved"] == [] and "REJECTED (work the pitch out)" in _bl(d, "report")[1], r
    _bl(d, "resolve", "1", "--how", "roof_pitch.py rule: 6/12, source standard")
    rc, r = _bl(d, "close")
    assert rc == 0 and r["done"], r
    assert "Check: ridge. REJECTED, redone: roof_pitch.py rule: 6/12, source standard" in _bl(d, "report")[1]
    _bl(d, "approve", "1")
    assert _bl(d, "resolve", "1", "--how", "x")[0] == 1                    # approved: nothing to resolve


def test_simplified_part_needs_yes():
    d = _done("bl7")
    _bl(d, "shortcut", "--kind", "substituted", "--what", "stock door", "--why", "no model of the real one")
    _bl(d, "stage", "detail")
    _bl(d, "shortcut", "--kind", "simplified", "--what", "shingles as stepped courses", "--why", "faster")
    _bl(d, "stage", "detail", "--done")
    rc, r = _bl(d, "close")
    assert rc == 2 and len(r["blockers"]) == 2 and r["unapproved"] == [1, 2], r
    assert r["blockers"][1] == ("shortcut 2 is simplified (shingles as stepped courses): a simpler part needs the "
                                "user's yes (approve 2), or build it in full and resolve 2"), r
    text = _bl(d, "report")[1]
    assert "1. substituted: stock door. Why: no model of the real one. NOT APPROVED" in text, text
    assert "2. simplified: shingles as stepped courses. Why: faster. Logged after start. NOT APPROVED" in text, text
    _bl(d, "approve", "1")                                                  # the user said yes to the stock door
    _bl(d, "resolve", "2", "--how", "every shingle modelled")
    rc, r = _bl(d, "close")
    assert rc == 0 and r["done"] and r["unapproved"] == [], r
    assert "Logged after start. REDONE: every shingle modelled" in _bl(d, "report")[1]
