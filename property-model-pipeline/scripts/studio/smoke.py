"""Smoke-test one measured house in the studio site under the artifact's strict CSP (gate G8).

    python3 smoke.py --site DIR --house SLUG [--job JOB] [--port 8766] [--out DIR] [--strict-planes]

Starts csp_server.py on the site folder, waits for HTTP 200, runs smoke.js in headless Chromium at a desktop and a
phone viewport, and checks:
  - no page errors and no CSP violations in the console
  - the house card is listed, and its rows equal the rows rebuilt from the report (JOB/report.json when --job is
    given, else the detail.json the packager wrote) and the rows in houses/index.json
  - opening the card selects the house; studio squares within 1 % of the report and not the demo roof (27.4 sq)
  - every visible <video> / splat element loads (hidden ones pass)
  - the plane count the studio found equals the report's facets (a warning unless --strict-planes)
Exit 0 pass, 1 any failure, 3 node / Playwright / Chromium missing. The server is always stopped.
Screenshots go to --out (default: a new temp folder; never inside the site, which is published as is).
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from package_house import DEMO_SQUARES, PackageError, card_rows, load_json  # noqa: E402
from report_pdf import have_playwright, node_env  # noqa: E402

CSP_MARKERS = ("Content Security Policy", "Content-Security-Policy", "Refused to")


def free_port(preferred):
    for port in (preferred, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("no free port")


def wait_http(url, timeout=20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.2)
    return False


def expected(site, house, job=None):
    """-> dict(rows, index_rows, squares, facets, source) the page must show."""
    idx = load_json(os.path.join(site, "houses", "index.json"), {}) or {}
    entry = next((h for h in idx.get("houses", []) if h.get("id") == house), None)
    if entry is None:
        raise PackageError(f"house '{house}' is not in {site}/houses/index.json")
    detail = load_json(os.path.join(site, entry.get("detail", f"houses/{house}/detail.json")), {}) or {}
    exp = {"index_rows": (entry.get("summary") or {}).get("rows", []), "label": entry.get("label")}
    if job:
        rep = load_json(os.path.join(job, "report.json"))
        if rep is None:
            raise PackageError(f"{job}/report.json not found")
        exp["rows"] = card_rows(rep, entry.get("waste"))
        a = rep["measurements_si"]["roof.area"] / 0.09290304
        exp["squares"] = a / 100.0
        exp["facets"] = len(rep.get("facets") or []) or int(rep["measurements_si"].get("roof.facets", 0))
        exp["source"] = "report.json"
    else:
        v = detail.get("verified") or {}
        exp["rows"] = detail.get("cardRows") or exp["index_rows"]
        exp["squares"] = v.get("squares") or (v.get("areaM2", 0) / 0.09290304 / 100.0)
        exp["facets"] = v.get("facets")
        exp["source"] = "detail.json"
    return exp


def judge(obs, exp, strict_planes=False):
    """Observations from smoke.js + expectations -> (failures, warnings) as text lines."""
    fails, warns = [], []
    if obs.get("error"):
        fails.append(f"browser: {obs['error']}")
    if exp["rows"] != exp["index_rows"]:
        fails.append("houses/index.json card rows differ from the report (stale index: re-run package_house.py)")
    for name, r in (obs.get("viewports") or {}).items():
        tag = f"[{name}]"
        if r.get("failed_step"):
            fails.append(f"{tag} step '{r['failed_step']}' failed: {r.get('step_error')}")
        for e in r.get("errors", []):
            fails.append(f"{tag} page error: {e}")
        for e in r.get("console_errors", []):
            (fails if any(k in e for k in CSP_MARKERS) else warns).append(f"{tag} console: {e[:300]}")
        if "card_found" in r and not r["card_found"]:
            fails.append(f"{tag} no card for the house (cards: {r.get('cards')})")
            continue
        if r.get("card_rows") is not None and r["card_rows"] != exp["rows"]:
            fails.append(f"{tag} card rows differ from {exp['source']}: page {r['card_rows']} vs expected {exp['rows']}")
        if r.get("thumb_ok") == "broken":
            fails.append(f"{tag} card thumbnail does not load")
        m = r.get("measure")
        if r.get("selected") is not None and m:
            sq = m.get("squares")
            want = exp.get("squares")
            if sq is None or not want:
                fails.append(f"{tag} no squares to compare (page {sq}, report {want})")
            else:
                if abs(sq - want) / want > 0.01:
                    fails.append(f"{tag} studio squares {sq:.2f} differ from the report {want:.2f} by more than 1 %")
                if abs(want - DEMO_SQUARES) > 0.15 and abs(sq - DEMO_SQUARES) < 0.05:
                    fails.append(f"{tag} studio shows the demo roof ({DEMO_SQUARES} sq): the house did not load")
            pl, want_pl = m.get("planes"), exp.get("facets")
            if pl is not None and want_pl and int(pl) != int(want_pl):
                (fails if strict_planes else warns).append(
                    f"{tag} studio found {pl} roof planes, the report has {want_pl} facets")
        if r.get("toast") and ("could not be loaded" in r["toast"] or "not found" in r["toast"].lower()):
            fails.append(f"{tag} toast: {r['toast']}")
        elif r.get("toast") and "differs from the report" in r["toast"]:
            warns.append(f"{tag} toast: {r['toast']}")
        for md in r.get("media") or []:
            if not md.get("hidden") and md.get("state") not in ("loaded", "ready"):
                fails.append(f"{tag} {md['kind']} {md.get('src', '')!r} is visible but did not load ({md.get('state')})")
    if not obs.get("viewports"):
        fails.append("no viewport ran")
    return fails, warns


def run(site, house, port=8766, out=None, job=None, strict_planes=False, timeout=600):
    """-> (exit code, summary dict)."""
    ok, why = have_playwright()
    if not ok:
        return 3, {"error": f"cannot run the smoke test: {why}"}
    site = os.path.abspath(site)
    exp = expected(site, house, job)
    out = os.path.abspath(out) if out else tempfile.mkdtemp(prefix="studio_smoke_")
    os.makedirs(out, exist_ok=True)
    if os.path.commonpath([out, site]) == site:
        raise PackageError("--out must not be inside the site folder (it is published as is)")
    port = free_port(port)
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "csp_server.py"), site, str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        url = f"http://127.0.0.1:{port}/index.html"
        if not wait_http(url):
            return 1, {"error": f"csp_server did not answer on {url}"}
        cmd = ["node", os.path.join(HERE, "smoke.js"), "--url", url, "--house", house, "--out", out]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=node_env())
        except subprocess.TimeoutExpired:
            return 1, {"error": f"smoke.js timed out after {timeout} s"}
        line = next((ln for ln in reversed(r.stdout.strip().splitlines()) if ln.startswith("{")), "")
        try:
            obs = json.loads(line)
        except json.JSONDecodeError:
            return 1, {"error": "smoke.js gave no result: " + (r.stdout + r.stderr).strip()[-800:]}
        if obs.get("tooling"):
            return 3, {"error": obs.get("error")}
        fails, warns = judge(obs, exp, strict_planes)
        summary = {"pass": not fails, "failures": fails, "warnings": warns, "expected": exp, "out": out,
                   "observed": {k: {kk: v.get(kk) for kk in ("card_rows", "measure", "toast", "media", "selected")}
                                for k, v in (obs.get("viewports") or {}).items()}}
        with open(os.path.join(out, "smoke.json"), "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "raw": obs}, f, indent=1, ensure_ascii=False)
        return (0 if not fails else 1), summary
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()
            srv.wait(5)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", required=True)
    ap.add_argument("--house", required=True, help="house id (slug) in houses/index.json")
    ap.add_argument("--job", help="job folder: compare against its report.json (else the packaged detail.json)")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--out", help="screenshots + smoke.json (default: a new temp folder)")
    ap.add_argument("--strict-planes", action="store_true", help="fail when the plane count differs")
    ap.add_argument("--timeout", type=float, default=600)
    a = ap.parse_args(argv)
    try:
        code, s = run(a.site, a.house, a.port, a.out, a.job, a.strict_planes, a.timeout)
    except PackageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if s.get("error"):
        print(f"ERROR: {s['error']}", file=sys.stderr)
        return code
    for w in s["warnings"]:
        print("WARN: " + w)
    for f in s["failures"]:
        print("FAIL: " + f)
    obs = s["observed"]
    for vp, o in obs.items():
        m = o.get("measure") or {}
        print(f"[{vp}] squares {m.get('squares')}, planes {m.get('planes')}, toast: {o.get('toast')!r}")
    print(f"expected ({s['expected']['source']}): {s['expected']['squares']:.2f} sq, {s['expected']['facets']} facets")
    print(f"screenshots + smoke.json: {s['out']}")
    print("SMOKE PASS" if s["pass"] else "SMOKE FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main())
