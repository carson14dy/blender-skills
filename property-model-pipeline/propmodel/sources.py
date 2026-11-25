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


def arcgis_footprints(layer_url, lat, lon, radius, cache_dir, out_fields, where="1=1", name="city"):
    """Building footprints from any ArcGIS REST polygon layer (city/county planimetrics).

    ``out_fields`` is a required explicit list (``"*"``, an empty list or a name / owner field raises
    ValueError, see :func:`propmodel.privacy.refuse_star`); only those attributes are copied into ``tags``
    (city layers carry e.g. ``OWNEDBY``, which is never requested).

    Municipal photogrammetric footprints are usually the most accurate public outline
    (typ. +/-0.15-0.3 m) but may follow walls OR drip edges depending on the capture spec —
    check against LiDAR/orthophoto and set ``which`` accordingly.
    """
    from .privacy import filter_attrs, refuse_star
    fields = refuse_star(out_fields)
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * math.cos(math.radians(lat)))
    params = {"where": where or "1=1",
              "geometry": f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}",
              "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
              "outFields": ",".join(fields), "returnGeometry": "true", "outSR": 4326, "f": "geojson"}
    d = _get(layer_url.rstrip("/") + "/query", cache_dir, params)
    if "error" in d:
        raise RuntimeError(f"footprint query error: {d['error']}")
    out = []
    for i, f in enumerate(d.get("features", [])):
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            rings = [g["coordinates"][0]]
        elif g.get("type") == "MultiPolygon":
            rings = [p[0] for p in g["coordinates"]]
        else:
            continue
        tags = filter_attrs(f.get("properties") or {}, fields)
        for ring in rings:
            out.append({"source": name, "id": f"{name}/{f.get('id', i)}", "tags": dict(tags),
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

def arcgis_parcel(layer_url, lat, lon, cache_dir, out_fields, where="1=1"):
    """Query any ArcGIS REST parcel layer (.../FeatureServer/0 or .../MapServer/N) at a point.

    ``out_fields`` is a required explicit list: parcel layers carry taxpayer names and mailing addresses
    (``OWNNAME1``, ``MRTNM1``, ``MRTADR`` ...), so ``"*"`` raises ValueError and only the named attributes
    come back. Returns GeoJSON features (lon/lat).
    Find a county/state layer by searching '<county> parcels FeatureServer' or the state GIS
    clearinghouse; the property-records stage (scripts/records.py) reads them through a region profile.
    Accuracy: GIS parcel lines are often 1-5 m off the imagery (they are digitised from
    deeds/plats, not surveyed for GIS). Use them for context, setbacks and assessor facts,
    not for building dimensions.
    """
    from .privacy import filter_attrs, refuse_star
    fields = refuse_star(out_fields)
    params = {"where": where or "1=1", "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "outFields": ",".join(fields), "returnGeometry": "true",
              "outSR": 4326, "f": "geojson"}
    d = _get(layer_url.rstrip("/") + "/query", cache_dir, params)
    if "error" in d:
        raise RuntimeError(f"parcel query error: {d['error']}")
    feats = d.get("features", [])
    for ft in feats:
        ft["properties"] = filter_attrs(ft.get("properties") or {}, fields)
    return feats


def dem_elevation(lat, lon, cache_dir):
    """3DEP best-available bare-earth elevation (m, NAVD88) at a point."""
    params = {"geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
              "geometryType": "esriGeometryPoint", "returnGeometry": "false", "returnCatalogItems": "false", "f": "json"}
    d = _get(DEM_IDENTIFY, cache_dir, params)
    try:
        return float(d["value"])
    except (KeyError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# cached, offline-aware HTTP and explicit-field ArcGIS queries (records / hazards stages)
# ---------------------------------------------------------------------------

class SourceUnreachable(RuntimeError):
    """A public source did not answer: network or HTTP error, ArcGIS error body, unreadable reply, or an
    offline run (PROPMODEL_OFFLINE=1) whose answer is not in the cache. Callers write "source not reachable
    on <date>" and carry on; they never guess the value."""


def default_cache_dir():
    return os.environ.get("PROPMODEL_CACHE", os.path.expanduser("~/.cache/propmodel"))


def _offline_env():
    return os.environ.get("PROPMODEL_OFFLINE", "") not in ("", "0", "false", "no")


def requests_transport(method, url, params=None, data=None, timeout=60, headers=None, stream_to=None):
    """Default transport: python requests with the toolkit User-Agent (some county WAFs refuse curl's).
    Returns the body (bytes), or None after streaming it into ``stream_to``."""
    hdr = dict(UA)
    hdr.update(headers or {})
    if method == "POST":
        r = requests.post(url, data=data if data is not None else params, headers=hdr, timeout=timeout)
    else:
        r = requests.get(url, params=params, headers=hdr, timeout=timeout, stream=bool(stream_to))
    r.raise_for_status()
    if stream_to:
        tmp = stream_to + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        os.replace(tmp, stream_to)
        return None
    return r.content


def _iso_utc(ts):
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Http:
    """Cached GET/POST for public sources. ``max_age`` (s) re-fetches live sources (permits, storm reports);
    ``None`` keeps a reply forever (versioned files). Offline (PROPMODEL_OFFLINE=1 or ``offline=True``): cache
    only, a miss raises :class:`SourceUnreachable`. A failed fetch with a stale copy in the cache returns the
    copy (meta ``stale``). ``transport(method, url, params=, data=, timeout=, headers=, stream_to=)`` is
    replaceable (tests feed recorded responses)."""

    def __init__(self, cache_dir=None, offline=None, transport=None, refresh=False):
        self.cache_dir = cache_dir or default_cache_dir()
        self.offline = _offline_env() if offline is None else bool(offline)
        self.transport = transport or requests_transport
        self.refresh = bool(refresh)

    def cache_path(self, url, params=None, data=None, ext=".json"):
        key = url + json.dumps(params or {}, sort_keys=True, default=str) + \
            (json.dumps(data, sort_keys=True, default=str) if data else "")
        d = os.path.join(self.cache_dir, "public")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, hashlib.sha1(key.encode()).hexdigest()[:24] + ext)

    def get(self, url, params=None, *, data=None, method="GET", kind="json", max_age=None, timeout=60, ext=None,
            headers=None):
        """-> (value, meta). kind: json | text | bytes | path (the cached file; large files stream to disk).
        meta: {url, fetched_at (UTC ISO), from_cache, stale}."""
        ext = ext or {"json": ".json", "text": ".txt", "bytes": ".bin", "path": ".bin"}[kind]
        path = self.cache_path(url, params, data, ext)
        have = os.path.exists(path)
        fresh = have and (max_age is None or time.time() - os.path.getmtime(path) <= max_age)
        use_cache = have and (self.offline or (fresh and not self.refresh))
        stale = False
        if not use_cache:
            if self.offline:
                raise SourceUnreachable(f"offline run (PROPMODEL_OFFLINE=1): {url} is not in the cache")
            try:
                raw = self.transport(method, url, params=params, data=data, timeout=timeout, headers=headers,
                                     stream_to=path if kind == "path" else None)
                if raw is not None:
                    tmp = path + ".part"
                    with open(tmp, "wb") as f:
                        f.write(raw)
                    os.replace(tmp, path)
                elif not os.path.exists(path):
                    raise SourceUnreachable(f"empty reply from {url}")
            except SourceUnreachable:
                raise
            except Exception as e:  # noqa: BLE001 - any network / HTTP failure
                if not have:
                    raise SourceUnreachable(f"{type(e).__name__}: {str(e)[:200]}") from e
                stale = True
        meta = {"url": url, "fetched_at": _iso_utc(os.path.getmtime(path)), "from_cache": use_cache or stale,
                "stale": stale}
        if kind == "path":
            return path, meta
        with open(path, "rb") as f:
            raw = f.read()
        if kind == "bytes":
            return raw, meta
        if kind == "text":
            return raw.decode("utf-8", errors="replace"), meta
        try:
            return json.loads(raw), meta
        except ValueError as e:
            os.remove(path)
            raise SourceUnreachable(f"reply from {url} is not JSON: {raw[:120]!r}") from e

    def forget(self, url, params=None, data=None, ext=".json"):
        p = self.cache_path(url, params, data, ext)
        if os.path.exists(p):
            os.remove(p)


def esri_to_geojson(g):
    """ArcGIS JSON geometry -> GeoJSON-like dict (Point / Polygon / MultiPolygon / MultiLineString) or None.
    Polygon rings: exterior rings are clockwise in ArcGIS, holes counter-clockwise."""
    if not g:
        return None
    if "x" in g and "y" in g:
        if g["x"] is None or g["y"] is None:
            return None
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if g.get("rings"):
        outers, holes = [], []
        for r in g["rings"]:
            a = 0.0
            for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
                a += x0 * y1 - x1 * y0
            (outers if a < 0 else holes).append([list(p[:2]) for p in r])
        if not outers:                       # counter-clockwise only: treat them as exteriors
            outers, holes = holes, []
        polys = [[o] for o in outers]
        if holes and len(polys) == 1:
            polys[0] += holes
        elif holes:
            from shapely.geometry import Point, Polygon
            for h in holes:
                pt = Point(h[0])
                for p in polys:
                    if Polygon(p[0]).contains(pt):
                        p.append(h)
                        break
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": polys[0]}
        return {"type": "MultiPolygon", "coordinates": polys}
    if g.get("paths"):
        return {"type": "MultiLineString", "coordinates": g["paths"]}
    if g.get("points"):
        return {"type": "MultiPoint", "coordinates": g["points"]}
    return None


def shapely_lonlat(geo):
    """GeoJSON-like dict (lon/lat) -> shapely geometry (None for empty)."""
    if not geo:
        return None
    from shapely.geometry import shape
    try:
        s = shape(geo)
        return s if s.is_valid else s.buffer(0)
    except Exception:  # noqa: BLE001
        return None


def esri_polygon(poly_lonlat):
    """shapely (Multi)Polygon in lon/lat -> ArcGIS JSON polygon (WGS84; exterior clockwise)."""
    from shapely.geometry.polygon import orient
    parts = list(getattr(poly_lonlat, "geoms", [poly_lonlat]))
    rings = []
    for p in parts:
        p = orient(p, sign=-1.0)
        rings.append([[round(x, 8), round(y, 8)] for x, y in p.exterior.coords])
        for r in p.interiors:
            rings.append([[round(x, 8), round(y, 8)] for x, y in r.coords])
    return {"rings": rings, "spatialReference": {"wkid": 4326}}


def arcgis_select(http, layer_url, out_fields, *, where="1=1", geometry=None, geometry_type=None,
                  spatial_rel="esriSpatialRelIntersects", in_sr=4326, return_geometry=True, out_sr=4326,
                  distance=None, units="esriSRUnit_Meter", max_age=None, max_records=4000, never=(),
                  timeout=60):
    """Query one ArcGIS REST layer or table with an explicit field list (never ``*``; never a name field).

    ``geometry``: an ArcGIS JSON geometry dict (or "lon,lat" / "xmin,ymin,xmax,ymax" string) in ``in_sr``.
    Long geometries go by POST. Pages through ``exceededTransferLimit`` up to ``max_records``.
    Returns (features, meta): features = [{"attributes": {requested fields only}, "geometry": GeoJSON-like
    (lon/lat) or None}]; meta = {url, fetched_at, from_cache, stale, n, truncated}. Raises SourceUnreachable."""
    from .privacy import filter_attrs, refuse_star
    fields = refuse_star(out_fields, never)
    url = layer_url.rstrip("/") + "/query"
    params = {"where": where or "1=1", "outFields": ",".join(fields),
              "returnGeometry": "true" if return_geometry else "false", "outSR": out_sr, "f": "json"}
    if geometry is not None:
        g = geometry if isinstance(geometry, str) else json.dumps(geometry, separators=(",", ":"))
        params.update(geometry=g, geometryType=geometry_type or "esriGeometryPolygon", inSR=in_sr,
                      spatialRel=spatial_rel)
    if distance:
        params.update(distance=distance, units=units)
    if "OBJECTID" in fields:
        params["orderByFields"] = "OBJECTID"
    method = "POST" if len(params.get("geometry", "")) > 1500 else "GET"
    feats, meta, truncated = [], None, False
    while True:
        p = dict(params)
        if feats:
            p["resultOffset"] = len(feats)
        d, m = http.get(url, None if method == "POST" else p, data=p if method == "POST" else None, method=method,
                        max_age=max_age, timeout=timeout)
        meta = meta or m
        if not isinstance(d, dict) or "error" in d:
            http.forget(url, None if method == "POST" else p, p if method == "POST" else None)
            err = d.get("error") if isinstance(d, dict) else d
            raise SourceUnreachable(f"ArcGIS error at {layer_url}: {str(err)[:200]}")
        page = d.get("features") or []
        for f in page:
            feats.append({"attributes": filter_attrs(f.get("attributes") or {}, fields, never),
                          "geometry": esri_to_geojson(f.get("geometry")) if return_geometry else None})
        if not d.get("exceededTransferLimit") or not page:
            break
        if len(feats) >= max_records:
            truncated = True
            break
    meta = dict(meta, n=len(feats), truncated=truncated, fields=fields)
    return feats, meta
