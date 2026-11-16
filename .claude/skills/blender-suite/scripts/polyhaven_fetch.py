#!/usr/bin/env python3
"""Search and download CC0 HDRIs, PBR texture sets and models from the Poly Haven API.

Host-side (system Python 3.9+, no bpy, no add-on, no API key). Files are checked against the md5 the
API publishes, and a file already on disk with the right md5 is not downloaded again. Texture files
keep Poly Haven's names, which scripts/build_pbr_material.py detects automatically.
Usage:
  python polyhaven_fetch.py --search "brushed metal" --type textures [--limit 20]
  python polyhaven_fetch.py --id studio_small_09 --res 2k --out assets/
  python polyhaven_fetch.py --id rusty_metal --res 2k --out assets/ [--format png|jpg]
  python polyhaven_fetch.py --id potted_plant_04 --res 1k --out assets/
Prints one JSON object. Exit code: 0 ok, 1 failed. Assets are CC0; credit Poly Haven in your tool's UI.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.polyhaven.com"
ALLOWED_HOSTS = (".polyhaven.com", ".polyhaven.org")
USER_AGENT = "blender-suite/1.0"  # the API terms require a user-agent naming the software
TYPES = {0: "hdris", 1: "textures", 2: "models"}
SOURCE = "Poly Haven (polyhaven.com), CC0"


class FetchError(Exception):
    pass


def _open(url):
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    local = host in ("127.0.0.1", "localhost")
    if not local and (parts.scheme != "https" or not host.endswith(ALLOWED_HOSTS)):
        raise FetchError(f"refusing URL outside Poly Haven: {url}")
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120)


def _json(path):
    try:
        with _open(f"{API}/{path}") as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404 and path.startswith("info/"):
            raise FetchError(f"asset not found: {path[5:]}. Use --search to find a valid id") from None
        raise FetchError(f"Poly Haven API returned HTTP {e.code} for /{path}") from None
    except urllib.error.URLError as e:
        raise FetchError(f"network error: {e.reason}") from None


def _md5(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _save(entry, dest):
    """Download one {url, md5} entry. Returns True when a download happened."""
    if os.path.exists(dest) and _md5(dest) == entry.get("md5"):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    try:
        with _open(entry["url"]) as r, open(tmp, "wb") as f:
            for chunk in iter(lambda: r.read(1024 * 1024), b""):
                f.write(chunk)
    except urllib.error.URLError as e:
        raise FetchError(f"download failed for {entry['url']}: {e}") from None
    if entry.get("md5") and _md5(tmp) != entry["md5"]:
        os.remove(tmp)
        raise FetchError(f"md5 mismatch for {entry['url']}")
    os.replace(tmp, dest)
    return True


def _inside(root, relative):
    """Join a server-supplied relative path, refusing anything that escapes `root`."""
    dest = os.path.normpath(os.path.join(root, relative))
    if os.path.commonpath([os.path.abspath(root), os.path.abspath(dest)]) != os.path.abspath(root):
        raise FetchError(f"refusing unsafe path from the API: {relative}")
    return dest


def search(query, kind="textures", limit=20):
    """Rank assets by how many query words appear in the id, name, categories and tags."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower())]
    hits = []
    for asset_id, info in _json(f"assets?t={kind}").items():
        text = " ".join([asset_id, info.get("name", ""), *info.get("categories", []), *info.get("tags", [])]).lower()
        score = sum(w in text for w in words)
        if score:
            hits.append((-score, -info.get("download_count", 0), asset_id, info))
    hits.sort(key=lambda h: h[:3])
    return {"ok": True, "query": query, "type": kind, "total": len(hits), "source": SOURCE,
            "assets": [{"id": a, "name": i.get("name"), "categories": i.get("categories", [])}
                       for _, _, a, i in hits[:limit]]}


def _variant(files, key, res, fmt):
    """Entry for map `key` at `res`, preferring `fmt`. None when the map doesn't exist."""
    if key not in files:
        return None
    if res not in files[key]:
        raise FetchError(f"{key} has no {res}; available: {sorted(files[key])}")
    variants = files[key][res]
    for f in (fmt, "png", "jpg", "exr"):
        if f in variants:
            return variants[f]
    return next(iter(variants.values()))


def _texture_entries(files, res, fmt):
    # color may be lossy; data maps default to png, because jpeg artifacts show up in normals
    wanted = [("Diffuse", fmt or "jpg"), ("nor_gl", fmt or "png"), ("Displacement", fmt or "png")]
    # arm packs AO, roughness and metal; build_pbr_material.py splits it and ignores the loose maps
    wanted += [("arm", fmt or "png")] if "arm" in files else [("Rough", fmt or "png"), ("AO", fmt or "png")]
    entries = [_variant(files, k, res, f) for k, f in wanted]
    return [e for e in entries if e]


def fetch(asset_id, res="2k", out=".", fmt=None):
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", asset_id):
        raise FetchError(f"invalid asset id: {asset_id}")
    kind = TYPES.get(_json(f"info/{asset_id}").get("type"))
    if kind is None:
        raise FetchError(f"asset not found: {asset_id}. Use --search to find a valid id")
    files = _json(f"files/{asset_id}")
    root = os.path.join(out, asset_id)
    saved, downloaded = [], 0
    if kind == "hdris":
        if res not in files["hdri"]:
            raise FetchError(f"no {res} HDRI; available: {sorted(files['hdri'])}")
        entry = files["hdri"][res].get(fmt or "hdr") or next(iter(files["hdri"][res].values()))
        pairs = [(entry, os.path.join(root, os.path.basename(entry["url"])))]
    elif kind == "textures":
        pairs = [(e, os.path.join(root, os.path.basename(e["url"]))) for e in _texture_entries(files, res, fmt)]
    else:
        if res not in files["gltf"]:
            raise FetchError(f"no {res} model; available: {sorted(files['gltf'])}")
        main = files["gltf"][res]["gltf"]
        pairs = [(main, os.path.join(root, os.path.basename(main["url"])))]
        pairs += [(e, _inside(root, rel)) for rel, e in main.get("include", {}).items()]
    for entry, dest in pairs:
        downloaded += _save(entry, dest)
        saved.append(dest)
    return {"ok": True, "id": asset_id, "type": kind, "res": res, "dir": root, "files": saved,
            "downloaded": downloaded, "source": SOURCE}


def run(search_query=None, kind="textures", limit=20, asset_id=None, res="2k", out=".", fmt=None, **_):
    if search_query:
        return search(search_query, kind, limit)
    if asset_id:
        return fetch(asset_id, res, out, fmt)
    raise FetchError("pass --search or --id")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--search", dest="search_query", default=None)
    p.add_argument("--type", dest="kind", default="textures", choices=sorted(TYPES.values()))
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--id", dest="asset_id", default=None)
    p.add_argument("--res", default="2k")
    p.add_argument("--out", default=".")
    p.add_argument("--format", dest="fmt", default=None)
    args = p.parse_args()
    try:
        result = run(**vars(args))
    except (FetchError, OSError) as e:
        result = {"ok": False, "error": str(e)}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
