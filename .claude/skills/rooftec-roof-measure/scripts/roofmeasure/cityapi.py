"""Polite, cached, read-only client for the City of Sioux Falls ArcGIS REST service.

Rules this module keeps (see references/data-sources.md):
* one house per request, never more than 5 records;
* at least 1 second between requests to the same host;
* every answer is cached on disk and reused forever;
* 3 retries with backoff; a User-Agent without personal data.

Field names were verified against the live service on 2026-11-16.
"""
import hashlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

from . import esri

BASE = "https://gis.siouxfalls.gov/arcgis/rest/services/Data"
ADDRESS_LAYER = BASE + "/Property/MapServer/0"
FOOTPRINT_LAYER = BASE + "/Property/MapServer/5"
SOLID_LAYER = BASE + "/Community/MapServer/66"
PERMIT_LAYER = BASE + "/Community/MapServer/3"
# permit work classes that change the shape of a roof ("New ..." covers every kind of new building)
# PERMIT_OTHER classes are reported as information only: 5 of 30 random houses had one since 2023 (review round 3)
PERMIT_OTHER = ("Repair", "Remodel/Renovation")
PERMIT_WHERE = ("WORKCLASS IN ('Addition','Razing','Demolition','Relocated Structure','Reshingle','Repair','Remodel/Renovation') "
                "OR WORKCLASS LIKE 'New%'")
PERMIT_MAX_AGE_DAYS = 30   # permits keep coming, so this one cached answer is asked again after a month
MAX_PERMITS = 25
USER_AGENT = "rooftec-roof-measure/0.1 (roof measurement skill; python-urllib)"
ACCESSORY_STRUCTURES = {190, 290, 390}
MAX_RECORDS = 5


class LookupError_(RuntimeError):
    """A house, address or solid could not be found (message is safe to show to the user)."""


class Http:
    """GET with a disk cache, per-host spacing and retries."""

    def __init__(self, offline=False, min_interval=1.0, timeout=60, retries=3, log=None):
        self.offline = offline
        self.min_interval = min_interval
        self.host_interval = {}  # per-host override, e.g. the public lidar bucket
        self.timeout = timeout
        self.retries = retries
        self.log = log or (lambda msg: None)
        self._last = {}
        self.requests_made = 0

    def _wait(self, host):
        gap = time.time() - self._last.get(host, 0)
        need = self.host_interval.get(host, self.min_interval)
        if gap < need:
            time.sleep(need - gap)
        self._last[host] = time.time()

    def get_bytes(self, url, cache_path=None):
        if cache_path and os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            with open(cache_path, "rb") as f:
                return f.read()
        if self.offline:
            raise LookupError_("offline and not cached: %s" % (cache_path or url))
        host = urllib.parse.urlsplit(url).netloc
        err = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(2 ** attempt)
            self._wait(host)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = r.read()
                self.requests_made += 1
                self.log("GET %s (%d bytes)" % (url.split("?")[0], len(data)))
                break
            except urllib.error.HTTPError as e:
                err = e
                if e.code in (400, 401, 403, 404):
                    raise LookupError_("HTTP %d for %s" % (e.code, url.split("?")[0]))
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, http.client.HTTPException) as e:
                # HTTPException covers IncompleteRead: a download cut off half way is retried like a timeout
                err = e
        else:
            raise LookupError_("no answer from %s after %d tries: %s" % (host, self.retries + 1, err))
        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp = cache_path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, cache_path)
        return data

    def get_json(self, url, params, cache_path=None, max_age_days=None):
        """Cached JSON query. With `max_age_days`, an older cached answer is asked again; if the service
        does not answer, the old answer is still used."""
        q = urllib.parse.urlencode(dict(params, f="json"))
        cached = None
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            stale = max_age_days is not None and time.time() - os.path.getmtime(cache_path) > max_age_days * 86400
            if not stale or self.offline:
                return cached
        try:
            data = json.loads(self.get_bytes(url + "?" + q).decode("utf-8"))
            if isinstance(data, dict) and data.get("error"):
                raise LookupError_("service error from %s: %s" % (url, data["error"].get("message")))
        except (LookupError_, ValueError):
            if cached is None:
                raise
            self.log("could not refresh %s; using the cached answer" % os.path.basename(cache_path))
            return cached
        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        return data


# --------------------------------------------------------------------------- addresses

_SUFFIX = {
    "STREET": "ST", "AVENUE": "AVE", "DRIVE": "DR", "ROAD": "RD", "COURT": "CT", "CIRCLE": "CIR", "PLACE": "PL",
    "BOULEVARD": "BLVD", "LANE": "LN", "TRAIL": "TRL", "PARKWAY": "PKWY", "TERRACE": "TER", "HIGHWAY": "HWY",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
}


def normalize_address(text):
    """'224 West 9th Street, Sioux Falls, SD 57104' -> '224 W 9TH ST' (the layer stores upper-case USPS style)."""
    t = text.upper().split(",")[0]
    t = re.sub(r"[^A-Z0-9 /#-]", " ", t)
    words = [w for w in t.split() if w]
    out = []
    for i, w in enumerate(words):
        # only abbreviate direction words next to the house number or at the end, and street types at the end
        if w in ("NORTH", "SOUTH", "EAST", "WEST"):
            out.append(_SUFFIX[w] if i in (1, len(words) - 1) else w)
        elif w in _SUFFIX and i >= 2:
            out.append(_SUFFIX[w])
        else:
            out.append(w)
    return " ".join(out)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] + "-" + hashlib.sha1(text.encode()).hexdigest()[:8]


def find_address(http, text, out_root):
    """Return address candidates [{address, oid, x, y, lon, lat, yearBuilt, status, pointType}] (max 5)."""
    norm = normalize_address(text)
    if not re.match(r"^\d+\s+\S+", norm):
        raise LookupError_("address must start with a house number and street, got %r" % text)
    esc = norm.replace("'", "''")
    fields = "OBJECTID,ADDRESS,ALIAS,LON,LAT,MUNICIPALITY,ZIPCODE,STATUS,YEARBUILT,POINTTYPE,UNITTYPE"
    cands = []
    for mode, where in (("exact", "ADDRESS = '%s'" % esc), ("prefix", "ADDRESS LIKE '%s%%'" % esc)):
        cache = os.path.join(out_root, "_lookup", "address-%s-%s.json" % (mode, _slug(norm)))
        d = http.get_json(ADDRESS_LAYER + "/query", {
            "where": where, "outFields": fields, "outSR": 32164, "returnGeometry": "true",
            "resultRecordCount": MAX_RECORDS, "orderByFields": "ADDRESS"}, cache)
        for f in d.get("features", []):
            a, g = f["attributes"], f.get("geometry") or {}
            if g.get("x") is None:
                continue
            cands.append({"address": a.get("ADDRESS"), "oid": a.get("OBJECTID"), "x": g["x"], "y": g["y"],
                          "lon": a.get("LON"), "lat": a.get("LAT"), "yearBuilt": a.get("YEARBUILT"),
                          "status": a.get("STATUS"), "pointType": a.get("POINTTYPE"), "unitType": a.get("UNITTYPE"),
                          "municipality": a.get("MUNICIPALITY"), "match": mode})
        if cands:
            break
    current = [c for c in cands if (c["status"] or "").lower() == "current"]
    return current or cands


# --------------------------------------------------------------------------- footprints

def _footprint_cache(out_root, oid):
    return os.path.join(out_root, str(oid), "raw", "footprint.json")


def footprint_by_oid(http, oid, out_root):
    d = http.get_json(FOOTPRINT_LAYER + "/query", {
        "objectIds": int(oid), "outFields": "*", "returnGeometry": "true", "outSR": 32164},
        _footprint_cache(out_root, int(oid)))
    if not d.get("features"):
        raise LookupError_("no city footprint with OBJECTID %s" % oid)
    return d["features"][0]


def _ring_distance(rings, x, y):
    """Distance in feet from a point to a polygon outline (0 when inside)."""
    inside, best = False, float("inf")
    for ring in rings:
        r = np.asarray(ring, float)[:, :2]
        a, b = r, np.roll(r, -1, axis=0)
        cond = (a[:, 1] > y) != (b[:, 1] > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
        if np.count_nonzero(cond & (x < xi)) % 2:
            inside = not inside
        d = b - a
        t = np.clip(((x - a[:, 0]) * d[:, 0] + (y - a[:, 1]) * d[:, 1]) / np.maximum((d ** 2).sum(1), 1e-12), 0, 1)
        best = min(best, float(np.hypot(a[:, 0] + t * d[:, 0] - x, a[:, 1] + t * d[:, 1] - y).min()))
    return 0.0 if inside else best


def footprint_by_point(http, x, y, out_root, in_sr=32164, search_ft=100.0):
    """Footprint containing a point; if none, the nearest primary structure within `search_ft`.

    Returns (feature, distance_ft). x, y are EPSG 32164 feet, or lon, lat when in_sr=4326.
    """
    if in_sr == 4326:
        from .proj import lonlat_to_city
        x, y = (float(v) for v in lonlat_to_city(x, y))
    tag = "%.1f_%.1f" % (x, y)
    env = "%.2f,%.2f,%.2f,%.2f" % (x - search_ft, y - search_ft, x + search_ft, y + search_ft)
    d = http.get_json(FOOTPRINT_LAYER + "/query", {
        "geometry": env, "geometryType": "esriGeometryEnvelope", "inSR": 32164,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "true", "outSR": 32164,
        "resultRecordCount": 25}, os.path.join(out_root, "_lookup", "footprints-near-%s.json" % tag))
    best = None
    for f in d.get("features", []):
        dist = _ring_distance(f["geometry"]["rings"], x, y)
        if dist > search_ft:
            continue
        key = (dist > 0 and f["attributes"].get("STRUCTURE") in ACCESSORY_STRUCTURES, round(dist, 1),
               -(f["attributes"].get("Shape.STArea()") or 0))
        if best is None or key < best[0]:
            best = (key, f, dist)
    if best is None:
        raise LookupError_("no city footprint within %.0f ft of that point; the house may be outside city data "
                           "(use tier C or D, see SKILL.md)" % search_ft)
    _, f, dist = best
    # keep a per-house copy so later runs need no lookup
    cache = _footprint_cache(out_root, f["attributes"]["OBJECTID"])
    if not os.path.exists(cache):
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(dict(d, features=[f]), fh)
    return f, dist


def footprint_bbox(feature):
    pts = np.concatenate([np.asarray(r, float)[:, :2] for r in feature["geometry"]["rings"]])
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


# --------------------------------------------------------------------------- 3D solids

def solid_for_footprint(http, footprint, out_root):
    """The Building Wireframe solid that best covers a footprint. Returns (feature, info dict)."""
    oid = footprint["attributes"]["OBJECTID"]
    x0, y0, x1, y1 = footprint_bbox(footprint)
    shrink = min(1.0, (x1 - x0) / 4, (y1 - y0) / 4)  # stay off the neighbours' walls
    env = "%.3f,%.3f,%.3f,%.3f" % (x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink)
    d = http.get_json(SOLID_LAYER + "/query", {
        "geometry": env, "geometryType": "esriGeometryEnvelope", "inSR": 32164,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "true", "returnZ": "true",
        "resultRecordCount": MAX_RECORDS}, os.path.join(out_root, str(oid), "raw", "wireframe.json"))
    return pick_solid(d, footprint)


def pick_solid(response, footprint):
    feats = response.get("features", [])
    if not feats:
        raise LookupError_(
            "the city has no 3D solid over footprint %s (built after June 2023, or outside the model). "
            "Use tier C (outline + typed pitch) or tier D (site capture)." % footprint["attributes"]["OBJECTID"])
    fx0, fy0, fx1, fy1 = footprint_bbox(footprint)
    best = None
    for f in feats:
        try:
            _, shape = esri.decode_feature(f)
        except esri.MultipatchError:
            continue
        bx0, by0, bx1, by1 = shape["bbox"]
        iw, ih = min(fx1, bx1) - max(fx0, bx0), min(fy1, by1) - max(fy0, by0)
        inter = max(iw, 0) * max(ih, 0)
        union = (fx1 - fx0) * (fy1 - fy0) + (bx1 - bx0) * (by1 - by0) - inter
        iou = inter / union if union > 0 else 0
        if best is None or iou > best[1]:
            best = (f, iou)
    if best is None:
        raise LookupError_("the city solid over this footprint could not be decoded")
    return best[0], {"candidates": len(feats), "bboxIoU": round(best[1], 4),
                     "exceededTransferLimit": bool(response.get("exceededTransferLimit"))}


# --------------------------------------------------------------------------- building permits

def _in_rings(rings, x, y, tol=3.0):
    """True when (x, y) is inside the footprint or within `tol` feet of its outline."""
    inside = False
    for ring in rings:
        r = np.asarray(ring, float)[:, :2]
        for (ax, ay), (bx, by) in zip(r, np.roll(r, -1, axis=0)):
            if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                inside = not inside
    return inside or _ring_distance(rings, x, y) <= tol


def permits_for_footprint(http, footprint, out_root):
    """Building permits whose point lies on this footprint and whose work changes or renews a roof.

    One small request, cached like the others. Returns a list of {"workClass", "issuedMs", "status"},
    newest first. The permit points sit on the building (checked on 5 benchmark houses in review round 2).
    """
    oid = footprint["attributes"]["OBJECTID"]
    x0, y0, x1, y1 = footprint_bbox(footprint)
    d = http.get_json(PERMIT_LAYER + "/query", {
        "geometry": "%.3f,%.3f,%.3f,%.3f" % (x0, y0, x1, y1), "geometryType": "esriGeometryEnvelope", "inSR": 32164,
        "outSR": 32164, "spatialRel": "esriSpatialRelIntersects", "where": PERMIT_WHERE,
        "outFields": "WORKCLASS,ISSUEDATE,PERMITSTATUS", "orderByFields": "ISSUEDATE DESC", "returnGeometry": "true",
        "resultRecordCount": MAX_PERMITS}, os.path.join(out_root, str(oid), "raw", "permits.json"),
        max_age_days=PERMIT_MAX_AGE_DAYS)
    out = []
    for f in d.get("features", []):
        g, a = f.get("geometry") or {}, f.get("attributes") or {}
        if "x" in g and not _in_rings(footprint["geometry"]["rings"], g["x"], g["y"]):
            continue   # a neighbour's permit inside this footprint's bounding box
        out.append({"workClass": a.get("WORKCLASS") or "", "issuedMs": a.get("ISSUEDATE"), "status": a.get("PERMITSTATUS")})
    return sorted(out, key=lambda p: -(p["issuedMs"] or 0))
