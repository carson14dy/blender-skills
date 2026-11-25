"""Print a studio report page (houses/<slug>/report.html) to a US-letter PDF with node Playwright + print.css.

    python3 report_pdf.py REPORT.html OUT.pdf [--expect TEXT]... [--min-pages N] [--css FILE]

The page order comes from report.html (package_house.py): cover with label, date, thumbnail and the card numbers;
one roof diagram per page; the measurement tables; then each drop-in section (property records, hail / wind, flood
zone, confidence with the measured-vs-assumed caveats) on its own page. --expect checks that the printed text holds
a figure (e.g. the roof area); --min-pages fails a PDF that is too short. Exit 0 ok, 1 failed check, 3 no node /
Playwright / Chromium (Python Playwright is not needed: this uses the node install the smoke test also uses).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRINT_CSS = os.path.join(HERE, "print.css")
JS = os.path.join(HERE, "report_pdf.js")


def node_env():
    """Environment in which `require('playwright')` resolves: NODE_PATH plus the global npm root."""
    env = dict(os.environ)
    paths = [p for p in env.get("NODE_PATH", "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=30).stdout.strip()
            if root and root not in paths:
                paths.append(root)
        except (OSError, subprocess.SubprocessError):
            pass
    env["NODE_PATH"] = os.pathsep.join(paths)
    return env


def have_playwright():
    """-> (ok, reason). True when node, the playwright package and its Chromium build are all present."""
    node = shutil.which("node")
    if not node:
        return False, "node not found"
    probe = ("const {chromium}=require('playwright');const fs=require('fs');const p=chromium.executablePath();"
             "process.stdout.write(fs.existsSync(p)?'ok':'missing '+p)")
    try:
        r = subprocess.run([node, "-e", probe], capture_output=True, text=True, timeout=60, env=node_env())
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"node failed: {e}"
    if r.returncode != 0:
        return False, "playwright not installed for node (" + (r.stderr.strip().splitlines() or ["?"])[-1] + ")"
    if r.stdout.strip() != "ok":
        return False, "chromium for playwright not installed (" + r.stdout.strip() + ")"
    return True, "ok"


def pdf_info(path):
    """(pages, text) with pypdf when installed, else (None, None)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, None
    rd = PdfReader(path)
    text = "\n".join((p.extract_text() or "") for p in rd.pages)
    return len(rd.pages), text


def render(html_path, pdf_path, expect=(), min_pages=1, css=PRINT_CSS, timeout_s=180):
    """Print html_path to pdf_path. -> dict {ok, pages, bytes, missing, broken, errors[, error, tooling]}."""
    ok, why = have_playwright()
    if not ok:
        return {"ok": False, "tooling": True, "error": why}
    cmd = ["node", JS, os.path.abspath(html_path), os.path.abspath(pdf_path), "--min-pages", str(min_pages),
           "--timeout", str(int(timeout_s * 1000 / 2))]
    if css:
        cmd += ["--css", css]
    for t in expect or ():
        cmd += ["--expect", t]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=node_env())
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout_s} s"}
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        res = json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "error": (r.stdout + r.stderr).strip()[-800:]}
    if res.get("ok"):
        pages, text = pdf_info(pdf_path)
        if pages is not None:
            res["pages"] = pages
            norm = " ".join(text.split())
            res["missing_in_pdf_text"] = [t for t in expect or () if " ".join(t.split()) not in norm]
            if pages < min_pages:
                res["ok"] = False
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("html")
    ap.add_argument("pdf")
    ap.add_argument("--expect", action="append", default=[], help="text the printed page must contain")
    ap.add_argument("--min-pages", type=int, default=1)
    ap.add_argument("--css", default=PRINT_CSS, help="print stylesheet (used when the page has none embedded)")
    ap.add_argument("--timeout", type=float, default=180)
    a = ap.parse_args(argv)
    res = render(a.html, a.pdf, a.expect, a.min_pages, a.css, a.timeout)
    print(json.dumps(res))
    if res.get("tooling"):
        print(f"ERROR: cannot print: {res.get('error')}", file=sys.stderr)
        return 3
    if not res.get("ok"):
        print(f"ERROR: PDF check failed: {res.get('error') or res}", file=sys.stderr)
        return 1
    if res.get("missing_in_pdf_text"):
        print(f"WARN: not found in the extracted PDF text: {res['missing_in_pdf_text']}")
    print(f"wrote {a.pdf}: {res['pages']} pages, {res['bytes'] / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
