"""Public data fetchers: geocoding, building footprints, orthoimagery, parcels, elevation.

All functions cache to disk and return plain Python data. Nothing here needs an API key.
Licensing (check before commercial use):
  * OSM footprints: ODbL (attribution "(c) OpenStreetMap contributors").
  * Microsoft Global ML Building Footprints: ODbL.
  * USGS 3DEP / NAIP: US public domain.
  * Esri World Imagery: Esri terms of use; attribution required; not for bulk download.
  * County parcel services: per county; usually public record.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import time

import numpy as np
import requests

from .geo import LocalFrame, lonlat_to_mercator, mercator_scale

UA = {"User-Agent": "propmodel/0.1 (property measurement toolkit)"}
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
IMAGERY = {
    "esri": {"url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export",
             "kind": "mapserver", "attribution": "Esri, Maxar, Earthstar Geographics, and the GIS User Community"},
    "naip": {"url": "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer/exportImage",
             "kind": "imageserver", "attribution": "USGS NAIP Plus (public domain)"},
}
DEM_IDENTIFY = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/identify"
MS_LINKS = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"


def _cache_path(cache_dir, key, ext):
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, hashlib.sha1(key.encode()).hexdigest()[:20] + ext)


def _get(url, cache_dir, params=None, ext=".json", binary=False, timeout=90, method="GET", data=None, retries=3):
    key = url + json.dumps(params or {}, sort_keys=True) + (data or "")
    path = _cache_path(cache_dir, key, ext)
    if os.path.exists(path):
        raw = open(path, "rb").read()
    else:
        last = None
        for i in range(retries):
            try:
                if method == "POST":
                    r = requests.post(url, data=data, headers=UA, timeout=timeout)
                else:
                    r = requests.get(url, params=params, headers=UA, timeout=timeout)
                r.raise_for_status()
                raw = r.content
                break
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (i + 1))
        else:
            raise last
        open(path, "wb").write(raw)
    return raw if binary else json.loads(raw)


# ---------------------------------------------------------------------------
# geocoding
# ---------------------------------------------------------------------------

def geocode(address, cache_dir):
    """US Census geocoder (rooftop-interpolated on street ranges) with Nominatim fallback.

    Geocodes are only a starting point (+/- 10-50 m); the building is then identified by
    footprint/LiDAR. Always confirm the right structure on the imagery overview.
    """
    try:
        d = _get("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress", cache_dir,
                 {"address": address, "benchmark": "Public_AR_Current", "format": "json"})
        m = d["result"]["addressMatches"]
        if m:
            c = m[0]["coordinates"]
            return {"lat": c["y"], "lon": c["x"], "matched": m[0]["matchedAddress"], "source": "census"}
    except Exception:
        pass
    d = _get("https://nominatim.openstreetmap.org/search", cache_dir, {"q": address, "format": "json", "limit": 1})
    if not d:
        raise ValueError(f"could not geocode {address!r}")
    return {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]), "matched": d[0]["display_name"], "source": "nominatim"}


# ---------------------------------------------------------------------------
# footprints
# ---------------------------------------------------------------------------

def osm_buildings(lat, lon, radius, cache_dir):
    q = f'[out:json][timeout:30];(way["building"](around:{radius},{lat},{lon});relation["building"](around:{radius},{lat},{lon}););out geom tags;'
    last = None
    for url in OVERPASS:
        try:
            d = _get(url, cache_dir, method="POST", data="data=" + requests.utils.quote(q), timeout=60, retries=1)
            break
        except Exception as e:
            last = e
    else:
        raise RuntimeError(f"all Overpass mirrors failed: {last}")
    out = []
    for e in d.get("elements", []):
        if e["type"] == "way" and e.get("geometry"):
            ring = [[p["lon"], p["lat"]] for p in e["geometry"]]
            out.append({"source": "osm", "id": f"way/{e['id']}", "tags": e.get("tags", {}), "ring_lonlat": ring})
        elif e["type"] == "relation":
            for mbr in e.get("members", []):
                if mbr.get("role") == "outer" and mbr.get("geometry"):
                    ring = [[p["lon"], p["lat"]] for p in mbr["geometry"]]
                    out.append({"source": "osm", "id": f"rel/{e['id']}", "tags": e.get("tags", {}), "ring_lonlat": ring})
    return out


def quadkey(lat, lon, z):
    x, y = lonlat_to_mercator(lon, lat)
    n = 2 ** z
    tx = int((x + math.pi * 6378137) / (2 * math.pi * 6378137) * n)
    ty = int((math.pi * 6378137 - y) / (2 * math.pi * 6378137) * n)
    q = ""
    for i in range(z, 0, -1):
        d = 0
        m = 1 << (i - 1)
        if tx & m:
            d += 1
        if ty & m:
            d += 2
        q += str(d)
    return q


def ms_buildings(lat, lon, radius, cache_dir, region=None):
    """Microsoft Global ML Building Footprints within ``radius`` m (downloads one zoom-9 tile)."""
    links = _get(MS_LINKS, cache_dir, ext=".csv", binary=True, timeout=180).decode()
    qk = quadkey(lat, lon, 9)
    rows = [r for r in csv.DictReader(io.StringIO(links)) if r["QuadKey"] == qk and (region is None or r["Location"] == region)]
    if not rows:
        return []
    frame = LocalFrame(lat, lon)
    out = []
    for r in rows:
        raw = _get(r["Url"], cache_dir, ext=".gz", binary=True, timeout=600)
        for line in gzip.decompress(raw).decode().splitlines():
            if not line.strip():
                continue
            f = json.loads(line)
            g = f["geometry"]
            ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
            if abs(cy - lat) * 111000 > radius * 1.5 or abs(cx - lon) * 111000 * math.cos(math.radians(lat)) > radius * 1.5:
                continue
            x, y, _ = frame.from_geodetic(cy, cx)
            if math.hypot(x, y) <= radius:
                out.append({"source": "ms", "id": f"ms/{r['Location']}/{len(out)}", "tags": f.get("properties", {}),
                            "ring_lonlat": ring})
    return out


def pick_building(candidates, frame, seed_xy=(0.0, 0.0)):
    """Footprint containing the seed point, else the nearest one."""
    from shapely.geometry import Polygon, Point
    best, bd = None, 1e18
    for c in candidates:
        poly = Polygon(frame.ring_from_lonlat(c["ring_lonlat"]))
        if not poly.is_valid:
            poly = poly.buffer(0)
        d = poly.distance(Point(seed_xy))
        if d < bd:
            best, bd = (c, poly), d
    return best


# ---------------------------------------------------------------------------
# orthoimagery
# ---------------------------------------------------------------------------

def ortho_image(frame, half_size, out_png, cache_dir, provider="esri", px=1024):
    """Download a north-up orthophoto covering the local square [-half, half]^2 (metres).

    Web Mercator is conformal and grid-north == true-north, so a square 3857 bbox scaled
    by 1/cos(lat) maps to a square in the local ENU frame with < 1e-4 relative error over a
    site. Writes ``out_png`` and ``out_png + '.json'`` with the local bounds and metres/pixel.

    Accuracy: orthophotos show the ROOF outline displaced by building lean (relief
    displacement ~ height * offset_from_nadir / flying_height; 0.2-1.5 m for houses on
    NAIP/satellite). Treat traced outlines as the roof edge with sigma >= 0.5 m and let the
    fusion estimate a per-source shift.
    """
    cfg = IMAGERY[provider]
    x, y = lonlat_to_mercator(frame.lon0, frame.lat0)
    s = half_size * mercator_scale(frame.lat0)
    bbox = f"{x - s},{y - s},{x + s},{y + s}"
    params = {"bbox": bbox, "bboxSR": 3857, "imageSR": 3857, "size": f"{px},{px}", "format": "png", "f": "image"}
    if cfg["kind"] == "imageserver":
        params["format"] = "png"
    raw = _get(cfg["url"], cache_dir, params, ext=".png", binary=True, timeout=120)
    if raw[:4] != b"\x89PNG" and raw[:3] != b"\xff\xd8\xff":
        raise RuntimeError(f"imagery request failed: {raw[:200]!r}")
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    open(out_png, "wb").write(raw)
    meta = {"bounds_local": [-half_size, -half_size, half_size, half_size], "px": px,
            "m_per_px": 2 * half_size / px, "provider": provider, "attribution": cfg["attribution"],
            "origin": frame.to_dict()}
    json.dump(meta, open(out_png + ".json", "w"), indent=2)
    return meta


# ---------------------------------------------------------------------------
# parcels & elevation
# ---------------------------------------------------------------------------

def arcgis_parcel(layer_url, lat, lon, cache_dir, out_fields="*"):
    """Query any ArcGIS REST parcel layer (.../FeatureServer/0 or .../MapServer/N) at a point.

    Find a county/state layer by searching '<county> parcels FeatureServer' or the state GIS
    clearinghouse. Returns GeoJSON features (lon/lat) with assessor attributes.
    Accuracy: GIS parcel lines are often 1-5 m off the imagery (they are digitised from
    deeds/plats, not surveyed for GIS). Use them for context, setbacks and assessor facts,
    not for building dimensions.
    """
    params = {"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields, "returnGeometry": "true",
              "outSR": 4326, "f": "geojson"}
    d = _get(layer_url.rstrip("/") + "/query", cache_dir, params)
    if "error" in d:
        raise RuntimeError(f"parcel query error: {d['error']}")
    return d.get("features", [])


def dem_elevation(lat, lon, cache_dir):
    """3DEP best-available bare-earth elevation (m, NAVD88) at a point."""
    params = {"geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
              "geometryType": "esriGeometryPoint", "returnGeometry": "false", "returnCatalogItems": "false", "f": "json"}
    d = _get(DEM_IDENTIFY, cache_dir, params)
    try:
        return float(d["value"])
    except (KeyError, ValueError, TypeError):
        return None
