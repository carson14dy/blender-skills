"""Package one measured job for the Roof Layer Studio site (the folder that is published as the studio artifact).

    python3 package_house.py JOB --site DIR --slug SLUG --label TEXT [--glb JOB/out/studio.glb]
        [--thumb JOB/out/thumb.jpg] [--facing 180] [--view-bearing DEG] [--waste PCT] [--media DIR] [--pdf]
    python3 package_house.py --verify-site DIR [--manifest FILE]       check a restored site folder
    python3 package_house.py --snapshot-site DIR [--manifest-out FILE]  write a new app-file manifest

Writes into DIR:
    houses/SLUG.gltf.json        the studio GLB as embedded glTF JSON (one base64 buffer; the page repacks it)
    houses/SLUG/detail.json      report values ("verified", "sigma", facets, pitch, card rows) + every
                                 JOB/out/detail_extra/<key>.json merged under <key>
    houses/SLUG/report.html      cover (label, date, thumbnail, card numbers) + JOB/out/diagrams/*.svg +
                                 JOB/report.md + every JOB/out/sections/NN_*.md in name order
    houses/SLUG/drone.jpg        the project thumbnail
    houses/SLUG/diagrams/*.svg   the roof diagrams
    houses/SLUG/report.pdf       with --pdf (report_pdf.py on the staged report.html)
    houses/SLUG/media/*, media.json   with --media (stills, turntable_1080p.mp4, splat file, labels, 4K link)
and upserts the house in houses/index.json with EVERY card row rebuilt from JOB/report.json.

Everything is staged in a temporary folder first. Each file is size-checked (warn above 12 MB, fail above 15 MB)
and every text file is privacy-scanned (`python3 -m propmodel.privacy scan DIR`; a built-in key scan when that module
is not installed). Nothing is written to the site unless both pass. The Artifact `files` map for this house
(published path -> local file) is printed and saved to JOB/out/studio_files.json.

The packager knows nothing about what the drop-in sections or detail_extra files contain: any stage can add a
JOB/out/sections/NN_name.md or a JOB/out/detail_extra/<key>.json and it reaches the studio unchanged.
Optional JOB/job.json supplies defaults for slug, label, facing, front_az, view_bearing, waste, subtitle, note.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import glb_to_gltf_json as G  # noqa: E402
import md2html  # noqa: E402

M_PER_FT = 0.3048
SQFT_PER_M2 = 1.0 / M_PER_FT ** 2
MB = 1_000_000
WARN_BYTES, FAIL_BYTES = 12 * MB, 15 * MB
STILL_WARN_BYTES = 3 * MB
LABEL_RENDER = "rendered from the measured model"
LABEL_TOPAZ = "upscaled with Topaz (video only)"
LABEL_SPLAT = "trained on renders of the measured model"
SPLAT_EXT = (".splat", ".ksplat", ".spz", ".sog", ".splat.json")
TEXT_EXT = (".json", ".html", ".htm", ".md", ".svg", ".txt", ".csv", ".css", ".js")
DIAGRAM_ORDER = ("length", "pitch", "area", "summary")
RESERVED_DETAIL_KEYS = {"label", "generated", "modelFrame", "verified", "sigma", "sigmaZero", "pitch", "facets",
                        "wasteSuggestedPct", "cardRows", "sources", "caveats", "review", "media", "pdf"}
DEMO_SQUARES = 27.4      # the studio's built-in demo roof; a page that shows this has not loaded the house

# G1p pattern (runbook): forbidden record keys. The built-in scan is only a fallback for propmodel.privacy.
PRIVACY_KEY = re.compile(r"owner|ownname|taxpayer|mrtnm|mrtadr|buyer|seller|contractor|nameadd|signedby|mail", re.I)
PRIVACY_TOKEN = re.compile(r"\b(own_?name|owner_?names?|taxpayer\w*|mrtnm\w*|mrtadr\w*|nameadd\w*|signedby\w*|"
                           r"mail_?addr(?:ess)?\w*|buyer_?name|seller_?name|contractor_?name)\b", re.I)


class PackageError(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------------------------------------- number formatting

def _sig2(x):
    """Round a positive uncertainty to 2 significant figures; returns (value, decimals)."""
    if not x or x <= 0 or not math.isfinite(x):
        return 0.0, 0
    d = int(math.floor(math.log10(x)))
    nd = -d + 1
    return round(x, nd), max(nd, 0)


def fmt_area_ft2(a, s=0.0):
    """'3,370 ± 100' (area rounded no finer than its 2-significant-figure sigma, never finer than 1 ft²)."""
    sv, _ = _sig2(s)
    if sv <= 0:
        return f"{round(a):,}"
    nd = -int(math.floor(math.log10(sv))) + 1
    nd = min(nd, 0)
    av = int(round(a, nd))
    return f"{av:,} ± {int(round(sv)):,}"


def fmt_len_ft(v, s=0.0):
    if s and s > 0:
        return f"{v:.1f} ± {max(s, 0.1):.1f} ft"
    return f"{v:.1f} ft"


def pitch_bucket(rise):
    """Nearest half pitch, as the report's pitch table: 3.9 -> '4/12', 3.6 -> '3.5/12'."""
    b = round(rise * 2) / 2
    return f"{b:g}/12"


def pitch_summary(facets):
    """Predominant (area-weighted, by nearest half pitch) and range of the facet pitches."""
    fs = [f for f in facets or [] if f.get("pitch") is not None]
    if not fs:
        return {"text": "n/a"}
    area = {}
    for f in fs:
        k = pitch_bucket(float(f["pitch"]))
        area[k] = area.get(k, 0.0) + float(f.get("area_sqft") or float(f.get("area_m2", 0)) * SQFT_PER_M2)
    tot = sum(area.values()) or 1.0
    best = max(area.items(), key=lambda kv: (kv[1], kv[0]))
    lo, hi = min(float(f["pitch"]) for f in fs), max(float(f["pitch"]) for f in fs)
    out = {"predominant": best[0], "predominantShare": round(best[1] / tot, 3),
           "rangeMin": round(lo, 1), "rangeMax": round(hi, 1),
           "byBucket": {k: round(v / tot, 3) for k, v in sorted(area.items())}}
    if len(area) == 1 and hi - lo < 0.25:
        out["text"] = f"{best[0]} (all planes)"
    else:
        out["text"] = f"{best[0]} predominant ({round(100 * best[1] / tot)} %) · {lo:.1f}–{hi:.1f}/12"
    return out


# ---------------------------------------------------------------------------------------------- report values

def _m(report, key, default=0.0):
    v = (report.get("measurements_si") or {}).get(key, default)
    return float(v) if v is not None else default


def _s(report, key):
    v = (report.get("measurement_sigma_si") or {}).get(key, 0.0)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) and v > 0 else 0.0


EDGES = (("ridge", "edge.ridge"), ("hip", "edge.hip"), ("valley", "edge.valley"), ("eave", "edge.eave"),
         ("rake", "edge.rake"), ("stepFlashing", "edge.sidewall"), ("headwall", "edge.headwall"))


def facet_count(report):
    fs = report.get("facets")
    if fs:
        return len(fs)
    return int(round(_m(report, "roof.facets")))


def card_rows(report, waste=None):
    """Every studio card row, from report.json only (no hand-kept numbers): area ± sigma, squares (and with waste),
    pitches, ridge, hips / valleys when non-zero, eaves / rakes, step flashing, headwall, roof plane count."""
    if "measurements_si" not in report or "roof.area" not in report["measurements_si"]:
        raise PackageError("report.json has no measurements_si['roof.area']: run pm.py fit (--accept) first")
    area_ft2 = _m(report, "roof.area") * SQFT_PER_M2
    s_ft2 = _s(report, "roof.area") * SQFT_PER_M2
    rows = [["Roof area", f"{fmt_area_ft2(area_ft2, s_ft2)} ft²"]]
    sq = area_ft2 / 100.0
    sq_txt = f"{sq:.1f}" + (f" ± {max(s_ft2 / 100.0, 0.1):.1f}" if s_ft2 > 0 else "") + " sq"
    if waste:
        sq_txt += f" · {sq * (1 + float(waste) / 100.0):.1f} sq with {float(waste):g} % waste"
    rows.append(["Squares", sq_txt])
    rows.append(["Pitch", pitch_summary(report.get("facets"))["text"]])

    def ln(key):
        return fmt_len_ft(_m(report, key) / M_PER_FT, _s(report, key) / M_PER_FT)

    rows.append(["Ridge", ln("edge.ridge")])
    if _m(report, "edge.hip") > 0.005:
        rows.append(["Hips", ln("edge.hip")])
    if _m(report, "edge.valley") > 0.005:
        rows.append(["Valleys", ln("edge.valley")])
    e, r = _m(report, "edge.eave") / M_PER_FT, _m(report, "edge.rake") / M_PER_FT
    se, sr = _s(report, "edge.eave") / M_PER_FT, _s(report, "edge.rake") / M_PER_FT
    rows.append(["Eaves / rakes", f"{fmt_len_ft(e, se)} / {fmt_len_ft(r, sr)}"])
    for label, key in (("Step flashing", "edge.sidewall"), ("Headwall", "edge.headwall")):
        rows.append([label, ln(key) if _m(report, key) > 0.005 else "none"])
    rows.append(["Roof planes", str(facet_count(report))])
    return rows


def verified_block(report):
    v = {"areaM2": round(_m(report, "roof.area"), 1),
         "areaFt2": round(_m(report, "roof.area") * SQFT_PER_M2, 1),
         "squares": round(_m(report, "roof.area") * SQFT_PER_M2 / 100.0, 2)}
    for name, key in EDGES:
        v[name + "M"] = round(_m(report, key), 2)
    v["dripEdgeM"] = round(_m(report, "edge.eave") + _m(report, "edge.rake"), 2)
    v["facets"] = facet_count(report)
    return v


def sigma_block(report):
    s = {}
    if _s(report, "roof.area"):
        s["areaM2"] = round(_s(report, "roof.area"), 2)
    for name, key in EDGES:
        if _s(report, key):
            s[name + "M"] = round(_s(report, key), 2)
    if _s(report, "edge.eave") or _s(report, "edge.rake"):
        s["dripEdgeM"] = round(math.hypot(_s(report, "edge.eave"), _s(report, "edge.rake")), 2)
    return s


def report_sources(report):
    out = []
    for r in (report.get("fit") or {}).get("residuals", []):
        src = str(r.get("source", "")).strip()
        src = re.sub(r"^auto:\s*", "", src)
        src = re.sub(r"^lidar\s+", "LiDAR ", src)
        if src and src not in out:
            out.append(src)
    return out


def default_subtitle(report):
    src = report_sources(report)
    lidar = [s for s in src if s.lower().startswith("lidar") and "outline" not in s.lower()]
    other = [s for s in src if s not in lidar and "outline" not in s.lower()]
    parts = lidar[:1] + other[:2]
    return "Measured model: " + (" + ".join(parts) if parts else "public LiDAR and city GIS data")


def suggested_waste(job, report_md):
    jj = load_json(os.path.join(job, "job.json"), {}) or {}
    if jj.get("waste") is not None:
        return float(jj["waste"])
    m = re.search(r"Suggested waste\s*\|\s*([\d.]+)\s*%", report_md or "")
    return float(m.group(1)) if m else None


def detail_json(report, label, extras=None, waste=None, note=None, generated=None, rows=None):
    d = {"label": label,
         "generated": generated or dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
         "modelFrame": "site-local ENU metres, z = 0 at the model datum; glTF is Y-up with north = -Z",
         "verified": verified_block(report),
         "sigma": sigma_block(report)}
    if not d["sigma"]:
        d["sigmaZero"] = True
    p = pitch_summary(report.get("facets"))
    d["pitch"] = {k: v for k, v in p.items() if k != "text"}
    d["pitch"]["text"] = p["text"]
    d["facets"] = [{"id": f.get("id"), "pitch": f"{float(f['pitch']):.1f}/12", "rise": round(float(f["pitch"]), 2),
                    "azimuth": None if f.get("azimuth") is None else round(float(f["azimuth"]), 1),
                    "areaM2": round(float(f.get("area_m2", 0)), 2),
                    "areaFt2": round(float(f.get("area_sqft") or float(f.get("area_m2", 0)) * SQFT_PER_M2), 1)}
                   for f in report.get("facets") or []]
    if waste is not None:
        d["wasteSuggestedPct"] = waste
    d["cardRows"] = rows if rows is not None else card_rows(report, waste)
    d["sources"] = report_sources(report)
    if report.get("caveats"):
        d["caveats"] = list(report["caveats"])
    if note:
        d["review"] = note
    for k, v in (extras or {}).items():
        if k in RESERVED_DETAIL_KEYS:
            raise PackageError(f"detail_extra/{k}.json would replace the report key '{k}': rename the file")
        d[k] = v
    return d


# ---------------------------------------------------------------------------------------------- job drop folders

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def collect_sections(job):
    d = os.path.join(job, "out", "sections")
    if not os.path.isdir(d):
        return []
    names = sorted(os.listdir(d))
    use = [n for n in names if re.match(r"^\d\d_.+\.md$", n)]
    for n in names:
        if n.endswith(".md") and n not in use:
            print(f"WARN: out/sections/{n} ignored (name must be NN_name.md)")
    return [(n, os.path.join(d, n)) for n in use]


def collect_extras(job):
    d = os.path.join(job, "out", "detail_extra")
    out = {}
    if not os.path.isdir(d):
        return out
    for n in sorted(os.listdir(d)):
        if not n.endswith(".json"):
            continue
        key = n[:-5]
        try:
            out[key] = load_json(os.path.join(d, n))
        except json.JSONDecodeError as e:
            raise PackageError(f"out/detail_extra/{n} is not valid JSON: {e}")
    return out


def collect_diagrams(job):
    d = os.path.join(job, "out", "diagrams")
    if not os.path.isdir(d):
        return []
    svgs = [n for n in os.listdir(d) if n.lower().endswith(".svg")]

    def key(n):
        s = n.lower()
        for i, k in enumerate(DIAGRAM_ORDER):
            if k in s:
                return (i, s)
        return (len(DIAGRAM_ORDER), s)

    return [(n, os.path.join(d, n)) for n in sorted(svgs, key=key)]


def diagram_caption(name):
    s = re.sub(r"[_-]+", " ", os.path.splitext(name)[0]).strip()
    s = s[:1].upper() + s[1:]
    return s if re.search(r"diagram|summary", s, re.I) else s + " diagram"


# ---------------------------------------------------------------------------------------------- report.html

SCREEN_CSS = """
:root { --bg:#eef1f4; --panel:#fff; --panel-2:#f2f4f7; --line:#d8dde4; --fg:#18202c; --fg-dim:#5a6577;
  --accent:#1d6ad8; --caution:#b9650a; --ok:#1f8556;
  --font-body:"Barlow",system-ui,-apple-system,"Segoe UI",sans-serif;
  --font-ui:"Barlow Semi Condensed","Barlow",system-ui,sans-serif; --font-mono:"JetBrains Mono",ui-monospace,Menlo,monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0f1318; --panel:#161b22; --panel-2:#1d232c;
  --line:#2a323d; --fg:#e8ecf1; --fg-dim:#97a3b3; --accent:#4c9cff; --caution:#f0a23a; --ok:#4fc08d; color-scheme:dark; } }
:root[data-theme="dark"] { --bg:#0f1318; --panel:#161b22; --panel-2:#1d232c; --line:#2a323d; --fg:#e8ecf1; --fg-dim:#97a3b3;
  --accent:#4c9cff; --caution:#f0a23a; --ok:#4fc08d; color-scheme:dark; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 var(--font-body); -webkit-font-smoothing:antialiased; }
main.wrap { max-width:980px; margin:0 auto; padding:28px 16px 48px; display:grid; gap:20px; }
.cover h1 { margin:0; font:700 28px/1.15 var(--font-ui); text-wrap:balance; }
.cover .eyebrow { margin:0; font:600 12px/1 var(--font-ui); letter-spacing:.09em; text-transform:uppercase; color:var(--fg-dim); }
.cover .meta { margin:6px 0 12px; color:var(--fg-dim); }
.cover-img { width:100%; max-height:420px; object-fit:cover; border-radius:10px; border:1px solid var(--line); display:block; margin-bottom:12px; }
section, .cover { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px 18px; min-width:0; }
section { display:grid; gap:10px; }
h2 { margin:0; font:700 15px/1.2 var(--font-ui); letter-spacing:.06em; text-transform:uppercase; color:var(--fg-dim); }
h3 { margin:8px 0 0; font:600 16px/1.25 var(--font-ui); }
.tw { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
th { font:600 12px/1.2 var(--font-ui); letter-spacing:.05em; text-transform:uppercase; color:var(--fg-dim); }
table.kpi td:first-child { color:var(--fg-dim); width:38%; }
table.kpi td:last-child { font-variant-numeric:tabular-nums; }
p { margin:0; }
ul, ol { margin:0; padding-left:20px; display:grid; gap:4px; }
code { font-family:var(--font-mono); font-size:13px; }
blockquote { margin:0; border-left:3px solid var(--caution); padding:8px 10px; background:var(--panel-2); border-radius:0 7px 7px 0; }
figure.diagram { margin:0; display:grid; gap:6px; }
figure.diagram img { width:100%; background:#fff; border-radius:8px; border:1px solid var(--line); }
figcaption, .note { color:var(--fg-dim); font-size:13.5px; }
.links { display:flex; gap:12px; flex-wrap:wrap; margin-top:10px; }
.links a { color:var(--accent); }
img { max-width:100%; }
video.turntable { width:100%; border-radius:10px; border:1px solid var(--line); background:#000; display:block; }
.stills { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:12px; }
figure.still { margin:0; display:grid; gap:6px; }
figure.still img { width:100%; border-radius:8px; border:1px solid var(--line); display:block; }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&'
         'family=Barlow+Semi+Condensed:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">')


def _section_id(name):
    return "s-" + re.sub(r"[^a-z0-9]+", "-", os.path.splitext(name)[0].lower()).strip("-")


def media_section(media, base):
    """Renders block for the report page from a media.json dict; `base` = the house folder prefix its src paths carry
    ("houses/SLUG/"), stripped so the links resolve next to report.html. Empty string when there is nothing to show."""
    if not media:
        return ""
    e = html.escape

    def rel(src):
        return src[len(base):] if src.startswith(base) else src

    out = []
    video = media.get("video")
    if video and video.get("src"):
        out.append(f'<video class="turntable screen-only" controls playsinline preload="metadata" '
                   f'src="{e(rel(video["src"]))}"></video>'
                   f'<p class="note screen-only">Turntable, 1080p, {e(video.get("label") or LABEL_RENDER)}.</p>')
    v4 = media.get("video4k") or {}
    if v4.get("url", "").startswith("https://"):
        out.append(f'<p class="links screen-only"><a href="{e(v4["url"])}" target="_blank" rel="noopener">'
                   f'4K turntable ({e(v4.get("label") or LABEL_TOPAZ)})</a></p>')
    stills = [s for s in media.get("stills") or [] if s.get("src")]
    if stills:
        figs = "".join(f'<figure class="still"><img src="{e(rel(s["src"]))}" alt="{e(s.get("caption") or s["name"])}"'
                       f' loading="lazy"><figcaption>{e(s.get("caption") or s["name"])}</figcaption></figure>'
                       for s in stills)
        out.append(f'<div class="stills">{figs}</div>')
    if not out:
        return ""
    return ('<section class="part renders" id="s-renders"><h2>Renders</h2>'
            '<p class="note">Pictures and video of the measured model. They are for viewing only: every number comes '
            'from the measurements below, never from an image.</p>' + "".join(out) + "</section>")


def report_html(label, generated, rows, report_md, sections=(), diagrams=(), thumb=None, note=None,
                pdf_href=None, print_css="", renders=""):
    """The studio report page. `sections`: [(file name, markdown)], `diagrams`: [(file name, href)], `renders`: the
    media_section() block (shown after the cover)."""
    e = html.escape
    kpi = "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td></tr>" for a, b in rows)
    cover = ['<header class="cover">', '<p class="eyebrow">Roof measurement report</p>', f"<h1>{e(label)}</h1>",
             f'<p class="meta">Generated {e(generated)} from public aerial, LiDAR and GIS data (no site visit)</p>']
    if thumb:
        cover.append(f'<img class="cover-img" src="{e(thumb)}" alt="3D view of the measured model">')
    cover.append(f'<table class="kpi"><tbody>{kpi}</tbody></table>')
    if note:
        cover.append(f'<p class="note">{e(note)}</p>')
    if pdf_href:
        cover.append(f'<p class="links screen-only"><a href="{e(pdf_href)}" download>Download the PDF report</a></p>')
    cover.append("</header>")
    parts = ["\n".join(cover)]
    if renders:
        parts.append(renders)
    if diagrams:
        figs = "".join(f'<figure class="diagram"><img src="{e(href)}" alt="{e(diagram_caption(n))}">'
                       f"<figcaption>{e(diagram_caption(n))}</figcaption></figure>" for n, href in diagrams)
        parts.append(f'<section class="part diagrams" id="s-diagrams"><h2>Roof diagrams</h2>{figs}</section>')
    parts.append(f'<section class="part measurements" id="s-measurements">{md2html.convert(report_md, 1)}</section>')
    for name, md in sections:
        parts.append(f'<section class="part" id="{_section_id(name)}">{md2html.convert(md, 1)}</section>')
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            f"<title>Roof report · {e(label)}</title>\n{FONTS}\n<style>{SCREEN_CSS}</style>\n"
            f"<style media=\"print\" data-print-css>{print_css}</style>\n</head>\n"
            "<body><main class=\"wrap\">\n" + "\n".join(parts) + "\n</main></body>\n</html>\n")


# ---------------------------------------------------------------------------------------------- gates

def size_check(paths, root):
    """-> (warnings, failures) as text lines; `paths` absolute, reported relative to `root`."""
    warns, fails = [], []
    for p in paths:
        n = os.path.getsize(p)
        rel = os.path.relpath(p, root)
        if n > FAIL_BYTES:
            fails.append(f"{rel}: {n / MB:.1f} MB > 15 MB (artifact limit)")
        elif n > WARN_BYTES:
            warns.append(f"{rel}: {n / MB:.1f} MB > 12 MB")
        if "/media/" in "/" + rel.replace(os.sep, "/") and rel.lower().endswith((".jpg", ".jpeg", ".webp")) \
                and n > STILL_WARN_BYTES:
            warns.append(f"{rel}: still {n / MB:.1f} MB > 3 MB (re-save at q85)")
    return warns, fails


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, k, v
            yield from _walk_keys(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def builtin_privacy_scan(root):
    """Fallback for propmodel.privacy: forbidden keys (G1p pattern) with a non-empty value in JSON files, and
    record-field tokens (OWNNAME, TAXPAYER, MAIL_ADDRESS ...) in other text files. Returns hit lines."""
    hits = []
    for dp, _, fs in os.walk(root):
        for n in sorted(fs):
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, root)
            if not n.lower().endswith(TEXT_EXT):
                continue
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if n.lower().endswith(".json"):
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    obj = None
                if obj is not None:
                    for path, k, v in _walk_keys(obj):
                        if PRIVACY_KEY.search(str(k)) and v not in (None, "", [], {}):
                            hits.append(f"{rel}: key '{path}'")
                    continue
            for m in PRIVACY_TOKEN.finditer(text):
                hits.append(f"{rel}: token '{m.group(0)}'")
    return hits


def privacy_scan(root):
    """-> (ok, report text, which scanner). Uses F's `python3 -m propmodel.privacy scan DIR` when installed."""
    have = os.path.exists(os.path.join(TOOLKIT, "propmodel", "privacy.py")) or \
        os.path.isdir(os.path.join(TOOLKIT, "propmodel", "privacy"))
    if have:
        env = dict(os.environ, PYTHONPATH=TOOLKIT + os.pathsep + os.environ.get("PYTHONPATH", ""))
        r = subprocess.run([sys.executable, "-m", "propmodel.privacy", "scan", root], cwd=TOOLKIT, env=env,
                           capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip(), "propmodel.privacy"
    hits = builtin_privacy_scan(root)
    return not hits, "\n".join(hits), "built-in key scan (propmodel.privacy not installed)"


# ---------------------------------------------------------------------------------------------- media

def media_files(media_dir, slug, video_4k_url=None):
    """-> ({published path: source path}, media.json dict) for a render/GPU output folder."""
    if not os.path.isdir(media_dir):
        raise PackageError(f"--media folder not found: {media_dir}")
    meta = load_json(os.path.join(media_dir, "media.json"), {}) or {}
    names = sorted(os.listdir(media_dir))
    base = f"houses/{slug}/media"
    files, stills, splats, video = {}, [], [], None
    captions = meta.get("captions", {}) if isinstance(meta.get("captions"), dict) else {}
    for n in names:
        p = os.path.join(media_dir, n)
        low = n.lower()
        if not os.path.isfile(p) or n == "media.json":
            continue
        if low.endswith((".jpg", ".jpeg", ".webp")) and not low.startswith("thumb"):
            files[f"{base}/{n}"] = p
            stills.append({"src": f"{base}/{n}", "name": os.path.splitext(n)[0], "label": LABEL_RENDER,
                           "caption": captions.get(os.path.splitext(n)[0], ""), "bytes": os.path.getsize(p)})
        elif low.endswith(".png"):
            print(f"WARN: media/{n} skipped (publish stills as JPG; PNG at 4K is too large)")
        elif low == "turntable_1080p.mp4":
            files[f"{base}/{n}"] = p
            video = {"src": f"{base}/{n}", "label": LABEL_RENDER, "bytes": os.path.getsize(p)}
        elif low.endswith(".mp4"):
            print(f"WARN: media/{n} skipped (only turntable_1080p.mp4 is published; the 4K file is a download link)")
        elif low.endswith(SPLAT_EXT):
            files[f"{base}/{n}"] = p
            fmt = "splat.json" if low.endswith(".splat.json") else os.path.splitext(low)[1].lstrip(".")
            splats.append({"src": f"{base}/{n}", "format": fmt, "label": LABEL_SPLAT, "bytes": os.path.getsize(p)})
    url4k = video_4k_url or meta.get("video4kUrl") or meta.get("video_4k_url")
    mj = {"label": LABEL_RENDER, "stills": stills, "video": video,
          "video4k": {"url": url4k, "label": LABEL_TOPAZ} if url4k else None,
          "splat": splats,
          "note": "Stills, video and splat are made from the measured model; the report and model are the source "
                  "of truth for every number."}
    if not files:
        print(f"WARN: no publishable media in {media_dir}")
    return files, mj


# ---------------------------------------------------------------------------------------------- site index

OPTIONAL_ENTRY_KEYS = ("lat", "waste", "thumb", "pdf")     # managed here: dropped when this run does not set them


def upsert_index(index, entry):
    """Replace the entry with the same id in place, else append. Keys this tool does not manage (and a "media" link
    from an earlier --media run) are kept; managed optional keys this run did not set are dropped, so no stale
    thumbnail or PDF link survives."""
    houses = index.setdefault("houses", [])
    for i, h in enumerate(houses):
        if h.get("id") == entry["id"]:
            merged = {k: v for k, v in h.items() if k not in OPTIONAL_ENTRY_KEYS}
            merged.update(entry)
            houses[i] = merged
            return index, "updated"
    houses.append(entry)
    return index, "added"


def save_thumb(src, dst, max_w=1600):
    try:
        from PIL import Image
    except ImportError:
        shutil.copyfile(src, dst)
        return
    im = Image.open(src).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    im.save(dst, quality=82)


# ---------------------------------------------------------------------------------------------- site manifest

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_manifest(path):
    """JSON manifest ({"files": [{"path", "bytes", "sha256"}]}) or the text listing 'path bytes sha256 [source]'."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        js = json.loads(text)
        return js.get("files", []), js
    except json.JSONDecodeError:
        pass
    files = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{64}", parts[2]):
            files.append({"path": parts[0], "bytes": int(parts[1]), "sha256": parts[2]})
    return files, {}


def module_closure_missing(site):
    """Relative scripts and ES-module imports reachable from index.html that are missing from the folder."""
    missing, seen = [], set()
    todo = []
    idx = os.path.join(site, "index.html")
    if not os.path.exists(idx):
        return ["index.html"]
    with open(idx, encoding="utf-8", errors="replace") as f:
        for m in re.finditer(r"<script[^>]*\bsrc=[\"']([^\"':]+)[\"']", f.read()):
            todo.append(os.path.normpath(m.group(1)))
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        p = os.path.join(site, rel)
        if not os.path.exists(p):
            missing.append(rel)
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            src = f.read()
        for m in re.finditer(r"(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)[\"'](\.{1,2}/[^\"']+)[\"']", src):
            todo.append(os.path.normpath(os.path.join(os.path.dirname(rel), m.group(1))))
    return sorted(missing)


def verify_site(site, manifest_path):
    """Check a site folder against a manifest + its own module graph + houses/index.json. -> (ok, lines)."""
    lines, ok = [], True
    files, meta = read_manifest(manifest_path)
    for e in files:
        p = os.path.join(site, e["path"])
        if not os.path.exists(p):
            ok = False
            lines.append(f"MISSING  {e['path']}")
        elif e.get("sha256") and sha256(p) != e["sha256"]:
            ok = False
            lines.append(f"CHANGED  {e['path']} (sha256 differs from the manifest)")
    lines.append(f"manifest: {len(files)} files checked ({os.path.basename(manifest_path)})")
    miss = module_closure_missing(site)
    for m in miss:
        ok = False
        lines.append(f"MISSING  {m} (imported by the page)")
    idx = load_json(os.path.join(site, "houses", "index.json"), None)
    if idx is None:
        lines.append("WARN     houses/index.json not found (no measured houses)")
    else:
        for h in idx.get("houses", []):
            for k in ("glb", "detail", "report", "thumb"):
                if h.get(k) and not os.path.exists(os.path.join(site, h[k])):
                    ok = False
                    lines.append(f"MISSING  {h[k]} (houses/index.json {h.get('id')}.{k})")
            g = h.get("glb")
            if g and os.path.exists(os.path.join(site, g)) and os.path.getsize(os.path.join(site, g)) > FAIL_BYTES:
                ok = False
                lines.append(f"TOO BIG  {g}")
        lines.append(f"houses/index.json: {len(idx.get('houses', []))} houses")
    if meta.get("siteFileCount"):
        n = sum(len(fs) for _, _, fs in os.walk(site))
        lines.append(f"folder holds {n} files (published site: {meta['siteFileCount']})")
    return ok, lines


def snapshot_manifest(site):
    files = []
    for dp, _, fs in os.walk(site):
        for n in fs:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, site).replace(os.sep, "/")
            if rel.startswith("houses/"):
                continue           # house files carry addresses: never in the public repo
            files.append({"path": rel, "bytes": os.path.getsize(p), "sha256": sha256(p)})
    return {"note": "Roof Layer Studio app files (houses/ excluded: house files stay in scratch and the artifact)",
            "generated": dt.date.today().isoformat(), "files": sorted(files, key=lambda e: e["path"])}


# ---------------------------------------------------------------------------------------------- main

def package(a):
    job = os.path.abspath(a.job)
    site = os.path.abspath(a.site)
    jj = load_json(os.path.join(job, "job.json"), {}) or {}
    slug = a.slug or jj.get("slug")
    label = a.label or jj.get("label")
    if not slug or not label:
        raise PackageError("--slug and --label are required (or set slug / label in JOB/job.json)")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", slug):
        raise PackageError(f"slug '{slug}' must be lower-case letters, digits and dashes")
    if not os.path.isdir(site) or not os.path.exists(os.path.join(site, "index.html")):
        raise PackageError(f"--site {site} is not a studio folder (no index.html); restore it first (restore_site.md)")
    report = load_json(os.path.join(job, "report.json"))
    if report is None:
        raise PackageError(f"{job}/report.json not found: run pm.py fit first")
    md_path = os.path.join(job, "report.md")
    report_md = open(md_path, encoding="utf-8").read() if os.path.exists(md_path) else ""
    glb = a.glb or os.path.join(job, "out", "studio.glb")
    if not os.path.exists(glb):
        raise PackageError(f"{glb} not found: run scripts/blender/export_studio_glb.py first")
    thumb = a.thumb or os.path.join(job, "out", "thumb.jpg")
    waste = a.waste if a.waste is not None else suggested_waste(job, report_md)
    facing = a.facing if a.facing is not None else float(jj.get("facing", 180))
    vb = a.view_bearing if a.view_bearing is not None else jj.get("view_bearing", jj.get("front_az", facing))
    note = a.note or jj.get("note")
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = card_rows(report, waste)
    if not sigma_block(report):
        print("WARN: measurement_sigma_si is empty or all zero: the card shows no ± (gate G4 should have stopped)")
    extras = collect_extras(job)
    sections = collect_sections(job)
    diagrams = collect_diagrams(job)
    with open(os.path.join(HERE, "print.css"), encoding="utf-8") as f:
        print_css = f.read()

    with tempfile.TemporaryDirectory(prefix="studio_pkg_") as stage:
        hdir = os.path.join(stage, "houses", slug)
        os.makedirs(os.path.join(hdir, "diagrams") if diagrams else hdir, exist_ok=True)
        staged = {}

        def put(pub, path):
            staged[pub] = path

        # model
        with open(glb, "rb") as f:
            gl = G.glb_to_gltf(f.read())
        text = G.dumps(gl)
        nbytes = len(text.encode("utf-8"))
        if nbytes > FAIL_BYTES:
            raise PackageError(f"houses/{slug}.gltf.json would be {nbytes / MB:.1f} MB > 15 MB: coarsen the terrain "
                               "(build_site.py --cell 0.35 --half 26) or export with --draco", 2)
        gp = os.path.join(stage, "houses", f"{slug}.gltf.json")
        with open(gp, "w", encoding="utf-8") as f:
            f.write(text)
        put(f"houses/{slug}.gltf.json", gp)
        s = G.summary(gl)
        print(f"model: {s['nodes']} nodes, {s['meshes']} meshes, {nbytes / MB:.2f} MB"
              + (f", extensions {', '.join(s['extensions'])}" if s["extensions"] else ""))
        bad = [n for n in s["names"] if n.startswith(("Lot line", "Ground (grade)", "Ground ortho"))]
        if bad:
            print(f"WARN: the model still holds reference objects {bad[:4]}: re-export without --keep-lot-line")

        # thumbnail
        thumb_href = None
        if os.path.exists(thumb):
            tp = os.path.join(hdir, "drone.jpg")
            save_thumb(thumb, tp)
            put(f"houses/{slug}/drone.jpg", tp)
            thumb_href = "drone.jpg"
        else:
            print(f"WARN: thumbnail {thumb} not found: the card shows no picture")

        # diagrams
        dia_hrefs = []
        for n, p in diagrams:
            dp = os.path.join(hdir, "diagrams", n)
            shutil.copyfile(p, dp)
            put(f"houses/{slug}/diagrams/{n}", dp)
            dia_hrefs.append((n, f"diagrams/{n}"))

        # media (staged before the report page, which shows it)
        media_pub, mj = None, None
        if a.media:
            mfiles, mj = media_files(a.media, slug, a.video_4k_url)
            for pub, src in mfiles.items():
                dst = os.path.join(stage, pub)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
                put(pub, dst)
            media_pub = f"houses/{slug}/media.json"
            mp = os.path.join(stage, media_pub)
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(mj, f, indent=1, ensure_ascii=False)
            put(media_pub, mp)

        # report page
        sec_md = [(n, open(p, encoding="utf-8").read()) for n, p in sections]
        pdf_pub = f"houses/{slug}/report.pdf"
        pdf_exists = bool(a.pdf)
        if not a.pdf and os.path.exists(os.path.join(site, pdf_pub)):
            print(f"WARN: {pdf_pub} in the site is from an earlier package and is no longer linked: "
                  "re-run with --pdf so the PDF carries these numbers")
        page = report_html(label, generated, rows, report_md, sec_md, dia_hrefs, thumb_href, note,
                           "report.pdf" if pdf_exists else None, print_css, media_section(mj, f"houses/{slug}/"))
        rp = os.path.join(hdir, "report.html")
        with open(rp, "w", encoding="utf-8") as f:
            f.write(page)
        put(f"houses/{slug}/report.html", rp)

        # detail.json
        detail = detail_json(report, label, extras, waste, note, generated, rows)
        if pdf_exists:
            detail["pdf"] = pdf_pub

        if media_pub:
            detail["media"] = media_pub
        dj = os.path.join(hdir, "detail.json")
        with open(dj, "w", encoding="utf-8") as f:
            json.dump(detail, f, indent=1, ensure_ascii=False)
        put(f"houses/{slug}/detail.json", dj)

        # index entry
        lat = None
        site_meta = report.get("site") or {}
        for src in (site_meta.get("origin"), site_meta.get("geocode")):
            if isinstance(src, dict) and src.get("lat") is not None:
                lat = round(float(src["lat"]), 2)      # sun position only: ~1 km is plenty
                break
        entry = {"id": slug, "label": label, "jobName": a.job_name or jj.get("job_name") or label,
                 "subtitle": a.subtitle or jj.get("subtitle") or default_subtitle(report),
                 "glb": f"houses/{slug}.gltf.json", "detail": f"houses/{slug}/detail.json",
                 "report": f"houses/{slug}/report.html", "facing": facing,
                 "summary": {"rows": rows},
                 "view": {"bearing": float(vb), "elevation": 23,
                          "note": "camera bearing from the house (front_az unless --view-bearing)"}}
        if lat is not None:
            entry["lat"] = lat
        if waste is not None:
            entry["waste"] = waste
        if thumb_href:
            entry["thumb"] = f"houses/{slug}/drone.jpg"
        if pdf_exists:
            entry["pdf"] = pdf_pub
        if media_pub:
            entry["media"] = media_pub
        index = load_json(os.path.join(site, "houses", "index.json"), {"houses": []})
        index, how = upsert_index(index, entry)
        ip = os.path.join(stage, "houses", "index.json")
        with open(ip, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        put("houses/index.json", ip)

        # PDF (optional, from the staged page so it carries exactly these numbers)
        if a.pdf:
            sys.path.insert(0, HERE)
            import report_pdf
            pp = os.path.join(hdir, "report.pdf")
            res = report_pdf.render(rp, pp, expect=[rows[0][1].split(" ")[0]], min_pages=a.min_pdf_pages)
            if not res.get("ok"):
                raise PackageError(f"PDF failed: {res.get('error') or res}", 5)
            put(pdf_pub, pp)
            print(f"pdf: {res.get('pages')} pages, {os.path.getsize(pp) / MB:.2f} MB")

        # gates
        warns, fails = size_check(list(staged.values()), stage)
        for w in warns:
            print("WARN: " + w)
        if fails:
            raise PackageError("size gate failed:\n  " + "\n  ".join(fails), 2)
        ok, out, which = privacy_scan(stage)
        print(f"privacy scan ({which}): {'clean' if ok else 'HITS'}")
        if not ok:
            raise PackageError("privacy scan found record fields; nothing was written to the site:\n" + out, 3)

        # install
        for pub, path in staged.items():
            dst = os.path.join(site, pub)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(path, dst)

    fmap = {pub: os.path.join(site, pub) for pub in sorted(staged)}
    os.makedirs(os.path.join(job, "out"), exist_ok=True)
    with open(os.path.join(job, "out", "studio_files.json"), "w", encoding="utf-8") as f:
        json.dump(fmap, f, indent=1)
    print(f"index: {how} '{slug}' ({len(index['houses'])} houses)")
    for r_ in rows:
        print(f"  {r_[0]}: {r_[1]}")
    print("Artifact files map (publish from the complete site folder to the existing studio URL):")
    print(json.dumps(fmap, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Package a measured job for the Roof Layer Studio site.")
    ap.add_argument("job", nargs="?", help="job folder (report.json, report.md, out/...)")
    ap.add_argument("--site", help="the complete studio site folder")
    ap.add_argument("--slug")
    ap.add_argument("--label")
    ap.add_argument("--glb", help="default JOB/out/studio.glb")
    ap.add_argument("--thumb", help="default JOB/out/thumb.jpg")
    ap.add_argument("--facing", type=float, help="studio 'Front faces' compass (default job.json facing or 180)")
    ap.add_argument("--view-bearing", type=float, help="camera bearing for the opening view (default front_az)")
    ap.add_argument("--waste", type=float, help="waste %% (default job.json waste or the report's suggestion)")
    ap.add_argument("--media", help="render output folder: stills, turntable_1080p.mp4, splat file, media.json")
    ap.add_argument("--video-4k-url", help="download URL of the Topaz 4K video")
    ap.add_argument("--subtitle")
    ap.add_argument("--job-name")
    ap.add_argument("--note", help="one paragraph shown on the report cover and saved as detail.review")
    ap.add_argument("--pdf", action="store_true", help="also print houses/SLUG/report.pdf (node Playwright)")
    ap.add_argument("--min-pdf-pages", type=int, default=1)
    ap.add_argument("--verify-site", metavar="DIR")
    ap.add_argument("--manifest", default=os.path.join(HERE, "site_manifest.json"))
    ap.add_argument("--snapshot-site", metavar="DIR")
    ap.add_argument("--manifest-out")
    a = ap.parse_args(argv)
    try:
        if a.verify_site:
            ok, lines = verify_site(os.path.abspath(a.verify_site), a.manifest)
            print("\n".join(lines))
            missing = [ln for ln in lines if ln.startswith(("MISSING", "TOO BIG"))]
            if ok:
                print("site OK")
            elif missing:
                print(f"site INCOMPLETE ({len(missing)} problems): do not publish from this folder")
            else:
                print("site differs from the manifest: expected after packaging a house; right after a restore it "
                      "means the download is not the published version")
            return 0 if ok else 4
        if a.snapshot_site:
            m = snapshot_manifest(os.path.abspath(a.snapshot_site))
            text = json.dumps(m, indent=1)
            if a.manifest_out:
                with open(a.manifest_out, "w", encoding="utf-8") as f:
                    f.write(text + "\n")
                print(f"wrote {a.manifest_out} ({len(m['files'])} files)")
            else:
                print(text)
            return 0
        if not a.job or not a.site:
            ap.error("JOB and --site are required")
        return package(a)
    except PackageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return e.code
    except G.GlbError as e:
        print(f"ERROR: model: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
