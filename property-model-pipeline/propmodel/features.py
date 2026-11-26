"""City planimetric features (paving, sidewalks, parcels, hydrants) -> features.json for build_site.py,
plus the small region-profile and ArcGIS helpers the demo wrapper shares.

Everything here is generic: layer URLs and field lists come from a region profile
(``references/regions/<name>.json``, schema owned by ``propmodel/regions.py``) or the command line,
never from code. Rules kept here:

* every ArcGIS query names its fields: ``out_fields`` is a required list and ``"*"`` raises ValueError;
* parcel attributes are not copied into features.json at all (only ``ADDRESS: "subject"`` on the parcel
  that holds the house, which build_site.py ``--address subject`` draws as the lot);
* city layers come in the city's datum: every coordinate is moved by the registration shift the fit
  estimated for the city footprint (``fit.json`` nuisance ``shift.<name>.dx/dy``; model = city + shift);
* responses are cached under ``PROPMODEL_CACHE``; with ``PROPMODEL_OFFLINE=1`` a cache miss raises
  :class:`propmodel.ept.OfflineMiss` instead of going to the network.
"""
from __future__ import annotations

import hashlib
import json
import math
import os

import numpy as np

from .ept import OfflineMiss, offline

UA = {"User-Agent": "propmodel/0.1 (property measurement toolkit)"}
HERE = os.path.dirname(os.path.abspath(__file__))
REGIONS_DIR = os.path.join(os.path.dirname(HERE), "references", "regions")

# SurfaceUse values that are roofs, not ground paving (never draped on the terrain)
DROP_USES = ("building", "roof", "structure", "house", "garage")


# ---------------------------------------------------------------------------
# region profiles
# ---------------------------------------------------------------------------

def load_profile(ref):
    """Region profile by name (``sioux-falls-sd``) or path. Uses propmodel.regions.load when that module
    exists (it validates the schema); otherwise reads ``references/regions/<name>.json`` directly.
    The returned dict carries ``_path`` (the file it came from, for resolving relative paths)."""
    if ref is None:
        return {}
    if isinstance(ref, dict):
        return ref
    path = ref if (os.path.sep in str(ref) or str(ref).endswith(".json")) else os.path.join(REGIONS_DIR, f"{ref}.json")
    prof = None
    if not os.path.exists(path):
        try:
            from . import regions  # noqa: F401  (owner F)
            load = getattr(regions, "load", None) or getattr(regions, "load_profile", None)
            prof = load(ref) if load else None
        except ImportError:
            prof = None
        if prof is None:
            raise FileNotFoundError(f"region profile {ref!r} not found (looked for {path})")
    else:
        with open(path) as f:
            prof = json.load(f)
    prof = dict(prof)
    prof.setdefault("_path", os.path.abspath(path) if os.path.exists(path) else None)
    return prof


LAYER_SYNONYMS = {
    "address_points": ("address_points", "address_point", "addresses", "address"),
    "footprints": ("footprints", "footprint", "buildings", "building_footprints"),
    "parcels": ("parcels", "parcel"),
    "lod2": ("lod2", "wireframe", "city3d", "buildings_3d", "lod2_roofs"),
    "impervious": ("impervious", "paving", "impervious_surface"),
    "sidewalk": ("sidewalk", "sidewalks"),
    "hydrants": ("hydrants", "hydrant"),
    "curbs": ("curbs", "curb"),
    "streets": ("streets", "street_centerlines", "centerlines"),
    "ortho": ("ortho", "orthophoto", "imagery"),
    "lidar": ("lidar",),
}


def profile_layer(profile, kind):
    """The profile entry for one layer kind (dict) or None. Looks at the top level, then under
    ``layers``, ``city`` and ``sources`` (the schema is owned by regions.py; this accepts the shapes in use)."""
    if not profile:
        return None
    names = LAYER_SYNONYMS.get(kind, (kind,))
    for scope in (profile, profile.get("layers") or {}, profile.get("city") or {}, profile.get("sources") or {}):
        if not isinstance(scope, dict):
            continue
        for n in names:
            v = scope.get(n)
            if isinstance(v, dict):
                return v
            if isinstance(v, str) and kind in ("ortho",):
                return {"url": v}
    return None


def layer_url(layer):
    if not layer:
        return None
    for k in ("url", "service", "endpoint", "layer_url"):
        if layer.get(k):
            return layer[k]
    return None


def layer_fields(layer, default=("OBJECTID",)):
    """Explicit field list of a profile layer; ``*`` is refused."""
    f = None
    for k in ("out_fields", "outFields", "fields"):
        if layer and layer.get(k):
            f = layer[k]
            break
    if f is None:
        f = list(default)
    if isinstance(f, str):
        f = [x.strip() for x in f.split(",") if x.strip()]
    check_fields(f)
    return list(f)


def check_fields(fields):
    if fields is None or isinstance(fields, str) or not len(fields):
        raise ValueError("out_fields must be an explicit, non-empty list of field names")
    if any(str(x).strip() == "*" for x in fields):
        raise ValueError("outFields=* is refused: name the fields (owner / taxpayer fields must never be requested)")
    return list(fields)


def resolve_path(profile, p):
    """A path from a profile (relative to the profile file)."""
    if not p or os.path.isabs(p):
        return p
    base = os.path.dirname(profile.get("_path") or "") if profile else ""
    return os.path.join(base, p)


# ---------------------------------------------------------------------------
# ArcGIS REST (cached; explicit fields only)
# ---------------------------------------------------------------------------

def _cache_file(url, params, cache_dir, ext=".json"):
    key = url + json.dumps(params or {}, sort_keys=True)
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "arcgis_" + hashlib.sha1(key.encode()).hexdigest()[:20] + ext)


def cached_get_json(url, params, cache_dir, timeout=90):
    path = _cache_file(url, params, cache_dir)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    if offline():
        raise OfflineMiss(f"offline (PROPMODEL_OFFLINE=1): {url} is not in the cache")
    import requests
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    with open(path + ".part", "w") as f:
        json.dump(d, f)
    os.replace(path + ".part", path)
    return d


def arcgis_query(layer_url_, out_fields, cache_dir, envelope=None, point=None, where="1=1", f="geojson",
                 out_sr=4326, extra=None):
    """Query an ArcGIS REST layer (…/MapServer/N or …/FeatureServer/N) with an explicit field list.

    ``envelope`` = (minlon, minlat, maxlon, maxlat) or ``point`` = (lon, lat), both WGS84.
    Returns the decoded JSON (GeoJSON for f=geojson). Raises RuntimeError on a server error."""
    fields = check_fields(out_fields)
    params = {"where": where or "1=1", "outFields": ",".join(fields), "returnGeometry": "true",
              "outSR": out_sr, "f": f}
    if envelope is not None:
        params.update(geometry=",".join(f"{v:.8f}" for v in envelope), geometryType="esriGeometryEnvelope",
                      inSR=4326, spatialRel="esriSpatialRelIntersects")
    elif point is not None:
        params.update(geometry=f"{point[0]:.8f},{point[1]:.8f}", geometryType="esriGeometryPoint",
                      inSR=4326, spatialRel="esriSpatialRelIntersects")
    params.update(extra or {})
    d = cached_get_json(layer_url_.rstrip("/") + "/query", params, cache_dir)
    if isinstance(d, dict) and "error" in d:
        raise RuntimeError(f"ArcGIS query error at {layer_url_}: {d['error']}")
    return d


def envelope_lonlat(frame, half):
    lat, lon, _ = frame.to_geodetic([-half, half], [-half, half], 0.0)
    return float(lon[0]), float(lat[0]), float(lon[1]), float(lat[1])


# ---------------------------------------------------------------------------
# features.json
# ---------------------------------------------------------------------------

def _geom_parts(g):
    """GeoJSON geometry -> (kind, parts) with parts in lon/lat: polygons [[outer, hole...]], lines [[pt..]],
    points [[lon, lat]]."""
    t = (g or {}).get("type")
    c = (g or {}).get("coordinates")
    if t == "Polygon":
        return "polygon", [c]
    if t == "MultiPolygon":
        return "polygon", list(c)
    if t == "LineString":
        return "line", [c]
    if t == "MultiLineString":
        return "line", list(c)
    if t == "Point":
        return "point", [c[:2]]
    if t == "MultiPoint":
        return "point", [p[:2] for p in c]
    return None, []


def _to_local(frame, coords, shift):
    a = np.asarray(coords, float)[:, :2]
    x, y, _ = frame.from_geodetic(a[:, 1], a[:, 0])
    return np.column_stack([x + shift[0], y + shift[1]])


def features_from_geojson(collections, frame, shift=(0.0, 0.0), half=30.0, subject_xy=(0.0, 0.0),
                          keep_props=None, drop_uses=DROP_USES, use_field="SurfaceUse"):
    """{kind: GeoJSON FeatureCollection (lon/lat)} -> build_site features dict in the model frame.

    Geometries are moved by ``shift`` (city -> model), clipped to the square [-half - 5, half + 5]^2 (a
    citywide street polygon becomes the piece around the lot), impervious polygons whose ``use_field``
    is a roof use are dropped, and only ``keep_props[kind]`` attributes are kept. Parcels get no
    attributes except ``ADDRESS: "subject"`` on the one containing ``subject_xy``."""
    from shapely.geometry import Polygon, LineString, Point, box
    clip = box(-half - 5, -half - 5, half + 5, half + 5)
    out = {}
    keep_props = keep_props or {}
    for kind, fc in collections.items():
        rows = []
        for ft in (fc or {}).get("features", []):
            props = ft.get("properties") or {}
            if kind == "impervious":
                use = str(props.get(use_field, "")).strip().lower()
                if use and any(use.startswith(d) for d in drop_uses):
                    continue
            gk, parts = _geom_parts(ft.get("geometry"))
            if gk is None:
                continue
            keep = {k: props[k] for k in keep_props.get(kind, ()) if k in props}
            if gk == "polygon":
                for poly in parts:
                    rings = [_to_local(frame, r, shift) for r in poly if len(r) >= 4]
                    if not rings:
                        continue
                    P = Polygon(rings[0], rings[1:]).buffer(0)
                    if kind == "parcels":
                        sub = P.contains(Point(subject_xy))
                        P2 = P
                        keep = {"ADDRESS": "subject"} if sub else {}
                    else:
                        P2 = P.intersection(clip)
                    if P2.is_empty:
                        continue
                    for q in getattr(P2, "geoms", [P2]):
                        if q.geom_type != "Polygon" or q.area < 0.05:
                            continue
                        rows.append({"geoms": [[[round(x, 3), round(y, 3)] for x, y in q.exterior.coords]]
                                     + [[[round(x, 3), round(y, 3)] for x, y in h.coords] for h in q.interiors],
                                     "props": dict(keep)})
            elif gk == "line":
                for ln in parts:
                    L = LineString(_to_local(frame, ln, shift)).intersection(clip)
                    for q in getattr(L, "geoms", [L]):
                        if q.geom_type == "LineString" and q.length > 0.1:
                            rows.append({"geoms": [[[round(x, 3), round(y, 3)] for x, y in q.coords]], "props": dict(keep)})
            else:
                for p in parts:
                    xy = _to_local(frame, [p], shift)[0]
                    if clip.contains(Point(xy)):
                        rows.append({"geoms": [[round(float(xy[0]), 3), round(float(xy[1]), 3)]], "props": dict(keep)})
        out[kind] = rows
    return out


def city_shift(fit, name="city"):
    """(dx, dy) the fit estimated for a city source (model = city + shift); (0, 0) when not fitted."""
    nu = (fit or {}).get("nuisance") or {}
    return float(nu.get(f"shift.{name}.dx", 0.0)), float(nu.get(f"shift.{name}.dy", 0.0))


def front_azimuth(model_centroid, features=None, geocode_xy=None, default=180.0):
    """Bearing (deg) the front of the house faces: towards the nearest street polygon (features
    impervious with SurfaceUse 'Street'), else towards the geocode point (Census points lie on the
    street centreline), else ``default``."""
    from shapely.geometry import Point, shape  # noqa: F401
    from shapely.geometry import Polygon
    from shapely.ops import nearest_points, unary_union
    c = Point(model_centroid)
    streets = []
    for fe in (features or {}).get("impervious", []):
        if str((fe.get("props") or {}).get("SurfaceUse", "")).lower().startswith("street"):
            g = fe["geoms"]
            try:
                streets.append(Polygon(g[0], g[1:]))
            except Exception:  # noqa: BLE001
                continue
    if streets:
        p = nearest_points(c, unary_union(streets))[1]
        if p.distance(c) > 1.0:
            return round(math.degrees(math.atan2(p.x - c.x, p.y - c.y)) % 360, 1), "nearest street"
    if geocode_xy is not None and math.hypot(geocode_xy[0] - c.x, geocode_xy[1] - c.y) > 3.0:
        return round(math.degrees(math.atan2(geocode_xy[0] - c.x, geocode_xy[1] - c.y)) % 360, 1), "geocode point"
    return float(default), "default"
