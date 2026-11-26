"""scripts/studio: GLB <-> embedded glTF, card rows from report.json, the drop-folder merge, size / privacy gates,
md2html and the site manifest check. Offline; synthetic data only (no addresses)."""
import base64
import importlib.util
import json
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.join(HERE, "..", "scripts", "studio")
sys.path.insert(0, STUDIO)

import glb_to_gltf_json as G  # noqa: E402
import md2html  # noqa: E402
import package_house as P  # noqa: E402

M = 0.3048


# ------------------------------------------------------------------------------------------------ fixtures

def tiny_glb(bin_len=36, pad=True, extra_nodes=()):
    """A minimal valid GLB written with struct: one triangle (positions only), compact JSON padded with spaces."""
    binb = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, 1) + bytes(max(0, bin_len - 36))
    nodes = [{"mesh": 0, "name": "Roof F1"}] + [{"name": n} for n in extra_nodes]
    js = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes,
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                         "min": [0, 0, 0], "max": [1, 0, 1]}],
          "bufferViews": [{"buffer": 0, "byteLength": 36}], "buffers": [{"byteLength": len(binb)}]}
    jb = json.dumps(js, separators=(",", ":")).encode()
    jb += b" " * ((4 - len(jb) % 4) % 4)
    bb = binb + (b"\x00" * ((4 - len(binb) % 4) % 4) if pad else b"")
    body = struct.pack("<II", len(jb), 0x4E4F534A) + jb + struct.pack("<II", len(bb), 0x004E4942) + bb
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body, binb


def synthetic_report(sigma=True):
    meas = {"roof.area": 200.0, "roof.facets": 4.0, "edge.ridge": 10.0, "edge.hip": 0.0, "edge.valley": 3.048,
            "edge.eave": 30.48, "edge.rake": 15.24, "edge.sidewall": 0.0, "edge.headwall": 1.524}
    sig = {"roof.area": 5.0, "edge.ridge": 0.1, "edge.eave": 0.3048} if sigma else {k: 0.0 for k in meas}
    facets = [{"id": "F1", "pitch": 6.0, "azimuth": 0.0, "area_m2": 60.0, "wings": ["A"]},
              {"id": "F2", "pitch": 6.0, "azimuth": 180.0, "area_m2": 60.0, "wings": ["A"]},
              {"id": "F3", "pitch": 4.0, "azimuth": 90.0, "area_m2": 50.0, "wings": ["B"]},
              {"id": "F4", "pitch": 4.2, "azimuth": 270.0, "area_m2": 30.0, "wings": ["B"]}]
    return {"site": {"origin": {"lat": 10.123456, "lon": 20.0}}, "measurements_si": meas,
            "measurement_sigma_si": sig, "facets": facets,
            "fit": {"residuals": [{"source": "auto:lidar TEST_DATASET_1", "kind": "lidar"},
                                  {"source": "Synthetic city outline", "kind": "planimetric"}]},
            "caveats": ["synthetic caveat"]}


EXPECTED_ROWS = [
    ["Roof area", "2,153 ± 54 ft²"],
    ["Squares", "21.5 ± 0.5 sq · 24.1 sq with 12 % waste"],
    ["Pitch", "6/12 predominant (60 %) · 4.0–6.0/12"],
    ["Ridge", "32.8 ± 0.3 ft"],
    ["Valleys", "10.0 ft"],
    ["Eaves / rakes", "100.0 ± 1.0 ft / 50.0 ft"],
    ["Step flashing", "none"],
    ["Headwall", "5.0 ft"],
    ["Roof planes", "4"],
]


def make_job(tmp_path, glb_bytes=None, report=None):
    job = tmp_path / "job"
    (job / "out" / "sections").mkdir(parents=True)
    (job / "out" / "detail_extra").mkdir()
    (job / "out" / "diagrams").mkdir()
    (job / "report.json").write_text(json.dumps(report or synthetic_report()))
    (job / "report.md").write_text("# Property measurement report\n\n## Roof summary\n\n| Quantity | Value |\n"
                                   "|---|---|\n| Total roof area | 2153 ft² |\n| Suggested waste | 12 % (2 hips+valleys) |\n")
    (job / "out" / "studio.glb").write_bytes(glb_bytes or tiny_glb()[0])
    from PIL import Image
    Image.new("RGB", (64, 48), (120, 130, 140)).save(job / "out" / "thumb.jpg")
    for name, head in (("90_confidence.md", "Confidence"), ("40_records.md", "Records"),
                       ("50_hazards.md", "Hazards")):
        (job / "out" / "sections" / name).write_text(f"## {head}\n\n- item for {head.lower()}\n")
    (job / "out" / "sections" / "notes.md").write_text("## Not a section\n")
    (job / "out" / "detail_extra" / "records.json").write_text(json.dumps({"yearBuilt": 1999}))
    (job / "out" / "detail_extra" / "hazards.json").write_text(json.dumps({"hail": [{"sizeIn": 1.0}]}))
    for d in ("summary", "length", "area", "pitch"):
        (job / "out" / "diagrams" / f"{d}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><title>{d}</title></svg>')
    return job


def make_site(tmp_path, entries=None):
    site = tmp_path / "site"
    (site / "houses").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>stub</title>")
    (site / "houses" / "index.json").write_text(json.dumps({"houses": entries or []}))
    return site


def run(job, site, *extra):
    return P.main([str(job), "--site", str(site), "--slug", "test-house", "--label", "Test House", *extra])


# ------------------------------------------------------------------------------------------------ GLB

def test_glb_to_gltf_json_round_trip_byte_identical():
    glb, binb = tiny_glb()
    gl = G.glb_to_gltf(glb)
    assert gl["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,")
    text = G.dumps(gl)
    back = json.loads(text)
    assert G.decode_buffer(back) == binb
    assert G.gltf_to_glb(back) == glb


def test_glb_buffer_shorter_than_padded_chunk():
    glb, binb = tiny_glb(bin_len=38)            # 38 bytes -> BIN chunk padded to 40
    gl = G.glb_to_gltf(glb)
    assert G.decode_buffer(gl) == binb
    assert len(base64.b64decode(gl["buffers"][0]["uri"].split(",", 1)[1])) == 38


def test_read_glb_rejects_non_glb():
    with pytest.raises(G.GlbError):
        G.read_glb(b"not a glb file at all")


# ------------------------------------------------------------------------------------------------ card rows

def test_card_rows_exact_from_report():
    assert P.card_rows(synthetic_report(), waste=12) == EXPECTED_ROWS


def test_card_rows_without_sigma_shows_no_plus_minus():
    rows = dict(P.card_rows(synthetic_report(sigma=False)))
    assert rows["Roof area"] == "2,153 ft²"
    assert rows["Squares"] == "21.5 sq"
    assert "±" not in json.dumps(rows, ensure_ascii=False)


def test_area_rounds_to_sigma():
    assert P.fmt_area_ft2(3369.7, 102.26) == "3,370 ± 100"
    assert P.fmt_area_ft2(2388.4, 37.7) == "2,388 ± 38"
    assert P.fmt_area_ft2(2388.4, 0) == "2,388"


def test_hips_row_only_when_non_zero():
    r = synthetic_report()
    assert "Hips" not in dict(P.card_rows(r))
    r["measurements_si"]["edge.hip"] = 6.096
    assert dict(P.card_rows(r))["Hips"] == "20.0 ft"


def test_detail_json_values_and_reserved_keys():
    d = P.detail_json(synthetic_report(), "Test House", {"records": {"a": 1}}, waste=12)
    assert d["verified"]["areaM2"] == 200.0 and d["verified"]["facets"] == 4
    assert d["verified"]["dripEdgeM"] == round(30.48 + 15.24, 2)
    assert d["sigma"]["areaM2"] == 5.0 and "valleyM" not in d["sigma"]
    assert d["records"] == {"a": 1}
    assert d["cardRows"] == EXPECTED_ROWS
    with pytest.raises(P.PackageError):
        P.detail_json(synthetic_report(), "Test House", {"verified": {}})


# ------------------------------------------------------------------------------------------------ packaging

def test_package_house_end_to_end(tmp_path):
    glb, binb = tiny_glb()
    job = make_job(tmp_path, glb)
    other = {"id": "other-house", "label": "Other", "summary": {"rows": [["Roof area", "1 ft²"]]}}
    stale = {"id": "test-house", "label": "Old", "summary": {"rows": [["Eaves / rakes", "999 ft"]]},
             "media": "houses/test-house/media.json", "pdf": "houses/test-house/report.pdf", "custom": 1}
    site = make_site(tmp_path, [other, stale])
    assert run(job, site, "--facing", "90") == 0

    idx = json.loads((site / "houses" / "index.json").read_text())
    assert [h["id"] for h in idx["houses"]] == ["other-house", "test-house"]       # updated in place
    assert idx["houses"][0] == other
    h = idx["houses"][1]
    assert h["summary"]["rows"] == EXPECTED_ROWS                                   # waste 12 from report.md
    assert h["waste"] == 12 and h["facing"] == 90 and h["lat"] == 10.12
    assert h["custom"] == 1 and h["media"] == "houses/test-house/media.json"       # unmanaged keys kept
    assert "pdf" not in h                                                          # no stale PDF link
    assert h["glb"] == "houses/test-house.gltf.json" and h["thumb"] == "houses/test-house/drone.jpg"
    assert "TEST_DATASET_1" in h["subtitle"]

    gl = json.loads((site / "houses" / "test-house.gltf.json").read_text())
    assert G.decode_buffer(gl) == binb

    hd = site / "houses" / "test-house"
    detail = json.loads((hd / "detail.json").read_text())
    assert detail["records"] == {"yearBuilt": 1999} and detail["hazards"]["hail"][0]["sizeIn"] == 1.0
    assert detail["cardRows"] == EXPECTED_ROWS
    assert sorted(os.listdir(hd / "diagrams")) == ["area.svg", "length.svg", "pitch.svg", "summary.svg"]
    assert (hd / "drone.jpg").exists()

    page = (hd / "report.html").read_text()
    pos = [page.index(t) for t in ('id="s-diagrams"', "Total roof area", ">Records<", ">Hazards<", ">Confidence<")]
    assert pos == sorted(pos)                                  # diagrams, report.md, then sections in name order
    dia = [page.index(f"diagrams/{d}.svg") for d in ("length", "pitch", "area", "summary")]
    assert dia == sorted(dia)
    assert "Not a section" not in page
    assert "2,153 ± 54 ft²" in page and "data-print-css" in page

    fmap = json.loads((job / "out" / "studio_files.json").read_text())
    assert "houses/index.json" in fmap and "houses/test-house.gltf.json" in fmap
    assert all(os.path.exists(v) for v in fmap.values())


def test_reserved_detail_extra_key_fails_and_writes_nothing(tmp_path):
    job = make_job(tmp_path)
    (job / "out" / "detail_extra" / "verified.json").write_text("{}")
    site = make_site(tmp_path)
    before = (site / "houses" / "index.json").read_text()
    assert run(job, site) == 1
    assert (site / "houses" / "index.json").read_text() == before
    assert not (site / "houses" / "test-house").exists()


def test_size_gate_fails_above_15_mb_and_writes_nothing(tmp_path):
    glb, _ = tiny_glb(bin_len=11_400_000)                       # base64 makes it ~15.2 MB
    job = make_job(tmp_path, glb)
    site = make_site(tmp_path)
    assert run(job, site) == 2
    assert json.loads((site / "houses" / "index.json").read_text()) == {"houses": []}
    assert not (site / "houses" / "test-house.gltf.json").exists()


def test_size_check_thresholds(tmp_path):
    big, mid, small = tmp_path / "big.bin", tmp_path / "mid.bin", tmp_path / "small.bin"
    for p, n in ((big, 15_000_001), (mid, 12_500_000), (small, 10)):
        with open(p, "wb") as f:
            f.truncate(n)
    warns, fails = P.size_check([str(big), str(mid), str(small)], str(tmp_path))
    assert len(fails) == 1 and "big.bin" in fails[0]
    assert len(warns) == 1 and "mid.bin" in warns[0]


def test_privacy_scan_catches_planted_ownname(tmp_path):
    job = make_job(tmp_path)
    (job / "out" / "detail_extra" / "records.json").write_text(json.dumps({"OWNNAME": "PLANTED NAME"}))
    site = make_site(tmp_path)
    assert run(job, site) == 3
    assert json.loads((site / "houses" / "index.json").read_text()) == {"houses": []}
    assert not (site / "houses" / "test-house").exists()


def test_builtin_privacy_scan(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"x": {"OwnName": "Z"}, "owner_empty": ""}))
    (tmp_path / "b.md").write_text("Ask the owner about the chimney.\n\n| OWNNAME | x |\n")
    (tmp_path / "c.html").write_text("<p>The owner corrected the porch.</p>")
    hits = P.builtin_privacy_scan(str(tmp_path))
    assert any("a.json" in h and "x.OwnName" in h for h in hits)
    assert not any("owner_empty" in h for h in hits)
    assert any("b.md" in h and "OWNNAME" in h for h in hits)
    assert not any("c.html" in h for h in hits)


def test_media_bundle(tmp_path):
    job = make_job(tmp_path)
    media = tmp_path / "media"
    media.mkdir()
    for n in ("hero_street.jpg", "top_down.jpg", "aerial_34.png", "turntable_1080p.mp4", "turntable_2160p.mp4",
              "house.spz"):
        (media / n).write_bytes(b"x" * 100)
    (media / "media.json").write_text(json.dumps({"video4kUrl": "https://example.com/v4k.mp4"}))
    site = make_site(tmp_path)
    assert run(job, site, "--media", str(media)) == 0
    mj = json.loads((site / "houses" / "test-house" / "media.json").read_text())
    assert [s["name"] for s in mj["stills"]] == ["hero_street", "top_down"]
    assert all(s["label"] == "rendered from the measured model" for s in mj["stills"])
    assert mj["video"]["src"] == "houses/test-house/media/turntable_1080p.mp4"
    assert mj["video4k"] == {"url": "https://example.com/v4k.mp4", "label": "upscaled with Topaz (video only)"}
    assert mj["splat"][0]["format"] == "spz"
    assert not (site / "houses" / "test-house" / "media" / "turntable_2160p.mp4").exists()
    h = json.loads((site / "houses" / "index.json").read_text())["houses"][0]
    assert h["media"] == "houses/test-house/media.json"
    page = (site / "houses" / "test-house" / "report.html").read_text()
    assert 'id="s-renders"' in page
    assert 'src="media/turntable_1080p.mp4"' in page and 'src="media/hero_street.jpg"' in page
    assert 'href="https://example.com/v4k.mp4"' in page and "upscaled with Topaz" in page
    assert "houses/test-house/media/" not in page          # links resolve next to report.html


def test_report_without_media_has_no_renders_section(tmp_path):
    job = make_job(tmp_path)
    site = make_site(tmp_path)
    assert run(job, site) == 0
    page = (site / "houses" / "test-house" / "report.html").read_text()
    assert "s-renders" not in page and "<video" not in page


def test_media_section_drops_a_non_https_4k_link():
    block = P.media_section({"stills": [], "video": None, "video4k": {"url": "javascript:alert(1)"}}, "houses/h/")
    assert block == ""


# ------------------------------------------------------------------------------------------------ md2html

def test_md2html_tables_lists_and_escaping():
    md = ("# Title\n\nSome **bold** and _it_ and `a<b`.\n\n| A | B |\n|:--|--:|\n| 1 | 2 |\n| x | <y> |\n\n"
          "- one\n- two\n  - nested\n\n1. first\n2. second\n\n[ok](https://example.com) [bad](javascript:alert(1))\n")
    h = md2html.convert(md, heading_offset=1)
    assert "<h2>Title</h2>" in h
    assert "<b>bold</b>" in h and "<i>it</i>" in h and "<code>a&lt;b</code>" in h
    assert '<th style="text-align:right">B</th>' in h and "<td>1</td>" in h and "&lt;y&gt;" in h
    assert "<ul><li>one</li><li>two<ul><li>nested</li></ul></li></ul>" in h
    assert "<ol><li>first</li><li>second</li></ol>" in h
    assert 'href="https://example.com"' in h and "javascript" not in h


def test_md2html_table_without_separator_and_paragraph_join():
    h = md2html.convert("| a | b |\n| c | d |\n\nline one\nline two\n")
    assert "<thead>" not in h and "<td>c</td>" in h
    assert "<p>line one line two</p>" in h


# ------------------------------------------------------------------------------------------------ site manifest

def test_verify_site_detects_missing_changed_and_unimported(tmp_path):
    site = tmp_path / "site"
    (site / "js").mkdir(parents=True)
    (site / "houses").mkdir()
    (site / "index.html").write_text('<script type="module" src="js/app.js"></script>')
    (site / "js" / "app.js").write_text("import { a } from './util.js';\nimport('./lazy.js');\n")
    (site / "js" / "util.js").write_text("export const a = 1;\n")
    (site / "houses" / "index.json").write_text(json.dumps({"houses": [{"id": "h", "glb": "houses/h.gltf.json"}]}))
    snap = P.snapshot_manifest(str(site))
    assert all(not e["path"].startswith("houses/") for e in snap["files"])
    man = tmp_path / "m.json"
    man.write_text(json.dumps(snap))
    ok, lines = P.verify_site(str(site), str(man))
    assert not ok
    assert any("js/lazy.js" in ln for ln in lines) and any("houses/h.gltf.json" in ln for ln in lines)
    (site / "js" / "lazy.js").write_text("")
    (site / "houses" / "h.gltf.json").write_text("{}")
    assert P.verify_site(str(site), str(man))[0]
    (site / "js" / "util.js").write_text("export const a = 2;\n")
    ok, lines = P.verify_site(str(site), str(man))
    assert not ok and any(ln.startswith("CHANGED") and "util.js" in ln for ln in lines)


def test_repo_site_manifest_has_no_house_paths():
    with open(os.path.join(STUDIO, "site_manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    paths = [e["path"] for e in m["files"]]
    assert paths and not any(p.startswith("houses/") for p in paths)
    assert sum(p.startswith("js/") for p in paths) == 16 and "index.html" in paths
    assert m["siteFileCount"] == len(paths) + m["houseFileCount"]


@pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="needs Pillow")
def test_thumb_is_downscaled(tmp_path):
    from PIL import Image
    src = tmp_path / "t.png"
    Image.new("RGB", (3200, 1800), (1, 2, 3)).save(src)
    P.save_thumb(str(src), str(tmp_path / "o.jpg"))
    assert Image.open(tmp_path / "o.jpg").size == (1600, 900)
