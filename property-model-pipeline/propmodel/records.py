"""Property-records stage: parcel, permit, assessor and sale facts from public city and county GIS layers.

Driven entirely by a region profile (:mod:`propmodel.regions`); nothing here knows a city. For one job:

1. the city parcel that CONTAINS the geocoded point (``site.json`` geocode) - method ``point``;
2. every other layer by intersection with that parcel polygon - ``parcel_polygon`` (polygon layers are kept
   when they overlap the parcel by >= 50 %, point layers when the point lies in it);
3. else a key copied from a matched layer (``TAG``, ``PID`` ...) - ``key``;
4. else the address string (``MAINADDRESS LIKE '<STREET>%'``) - ``address``. Any method after the layer's
   first is a fallback and is flagged in the report.

The county layers are chosen by the parcel's county field (``county_sources``). Every query names its fields
(:func:`propmodel.privacy.refuse_star`); attributes are filtered to those fields again on arrival, and address
strings are used for matching only, never stored. A source that fails is written as "source not reachable on
<date>", never dropped or guessed.

Outputs (scratch job folder only): ``data/records.json``, ``out/sections/40_records.md``,
``out/detail_extra/records.json``. All three are privacy-scanned before the stage returns; a hit deletes them.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re

from . import privacy, regions
from .sources import Http, SourceUnreachable, arcgis_select, esri_polygon, shapely_lonlat

STREET_ABBR = {"AVENUE": "AVE", "STREET": "ST", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN", "COURT": "CT",
               "PLACE": "PL", "BOULEVARD": "BLVD", "CIRCLE": "CIR", "TRAIL": "TRL", "PARKWAY": "PKWY", "TERRACE": "TER",
               "HIGHWAY": "HWY", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
REROOF = re.compile(r"re-?shingl|re-?roof|\broof(ing)?\b|shingl", re.I)
NOT_REROOF = re.compile(r"solar|roof\s*top\s*unit|\brtu\b|roof\s*mount|antenna", re.I)
ADDITION = re.compile(r"addition|new\s*(construction|building|dwelling|house|home|res\w*|single|sfd|sfr|sf\b)|"
                      r"new\s+sf\b", re.I)
SITE_CHANGE = re.compile(r"accessory|detached\s+garage|carport|sunroom|four\s+season|4\s+seasons|three\s+season", re.I)
DEAD_STATUS = re.compile(r"void|withdrawn|cancel|expired|denied|revoked|rejected", re.I)
ADDRESS_FIELD = re.compile(r"addr", re.I)          # used to match, never stored
NOT_PUBLIC_DEFAULT = ["living area", "sketch dimensions", "roof material"]
MAX_AGE_S = 3 * 86400                               # permits / sales refresh every few days

# canonical name -> common field names (last dotted part, case-insensitive), used when a layer has no "map"
ALIASES = {
    "year_built": ["YEARBUILT", "YEAR_BUILT", "YR_BUILT"], "storeys": ["NUMBERSTORIES", "STORIES", "NUM_STORIES"],
    "style": ["HOUSE_DESC", "HOUSETYPE", "HOUSE_TYPE", "STYLE"], "grade": ["GRADE"], "grade_desc": ["GRADE_DESC"],
    "condition": ["CONDITION", "COND"], "structure": ["STRUCTURE"], "occupancy": ["OCCUPANCY"],
    "construction": ["CONSTRTYPE"], "lot_sqft": ["SQFT", "SQFTCALC"], "lot_acres": ["ACREAGE", "ACRECALC", "TOTAL_ACREAGE"],
    "legal": ["LEGAL", "LEGALDESC", "LEGAL_DESC"], "land_use": ["ACTIVITY"], "land_use_code": ["LANDUSE"],
    "zoning": ["ZONING", "MRZON1"], "subdivision": ["ADDITION", "SUBDIV", "SUBDIVISION"], "county": ["COUNTY"],
    "parcel_key": ["TAG", "PID", "PARCEL_ID", "PARCEL_NUMBER"], "county_key": ["COUNTYID"],
    "parcel_type": ["PARCELTYPE"], "units": ["NUMUNITS", "UNITS"], "corner_lot": ["CORNERLOT"], "city": ["MUNICIPALITY"],
    "assessed_total": ["TOTAL", "MRTOTC"], "assessed_land": ["MRLNVC"], "assessed_building": ["MRBDVC"],
    "assessed_year": ["ASSMENT_YEAR"], "sale_date": ["SALE_DATE", "INSTR_DATE", "INSTRDATE"],
    "sale_price": ["SALE_PRICE", "SELL_PRICE", "SALEPRICE"], "sale_year": ["SALE_YEAR", "SALEYEAR"],
    "permit_number": ["PERMITNUMBER", "PERMIT"], "permit_type": ["PERMITTYPE", "PROJECTTYPE"],
    "work_class": ["WORKCLASS"], "permit_status": ["PERMITSTATUS"], "apply_date": ["APPLYDATE"],
    "issue_date": ["ISSUEDATE", "DATEAPPROVED"], "finalize_date": ["FINALIZEDATE"],
    "valuation": ["VALUATION", "PROJECTCOST"], "description": ["PROJDESC"], "dwelling_units": ["DWELLINGUNITS"],
    "ground_elev": ["GROUNDELEVATION"], "top_elev": ["BUILDINGTOPELEVATION"], "occupied_date": ["OCCUPIEDDATE"],
    "capture_method": ["CAPTUREMETH"],
}
ROLE_KEYS = {
    "parcel": ["lot_sqft", "lot_acres", "legal", "land_use", "land_use_code", "zoning", "subdivision", "county",
               "parcel_key", "county_key", "parcel_type", "units", "assessed_total", "assessed_land",
               "assessed_building", "assessed_year", "assessed_class"],
    "geocode": ["year_built", "occupancy", "construction", "county", "corner_lot", "city", "parcel_key"],
    "footprint": ["storeys", "structure", "ground_elev", "top_elev", "occupied_date", "capture_method", "units"],
    "structure": ["structure", "units", "occupied_date"],
    "permits": ["permit_number", "permit_type", "work_class", "permit_status", "apply_date", "issue_date",
                "finalize_date", "valuation", "description", "dwelling_units"],
    "assessor": ["assessed_total", "assessed_land", "assessed_building", "assessed_year", "assessed_class",
                 "parcel_key", "county_key", "zoning"],
    "quality": ["style", "grade", "grade_desc", "condition", "year_built", "parcel_key", "county_key"],
    "sales": ["sale_date", "sale_year", "sale_price", "sale_class", "sale_type", "sale_desc", "sale_value",
              "year_built", "condition", "style", "grade", "grade_desc", "assessed_total", "assessed_land",
              "assessed_building", "assessed_year"],
    "zoning": ["zoning"],
}
SINGLE_ROLES = {"parcel", "geocode", "footprint", "structure", "assessor", "quality", "zoning"}
NUMERIC = {"lot_sqft", "lot_acres", "assessed_total", "assessed_land", "assessed_building", "sale_price",
           "valuation", "storeys", "units", "sale_value", "ground_elev", "top_elev", "dwelling_units"}
DATES = {"sale_date", "apply_date", "issue_date", "finalize_date", "occupied_date"}


# ---------------------------------------------------------------------------------------------- small helpers

def today_utc():
    return dt.datetime.now(dt.timezone.utc).date()


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_date(v):
    """A date from ArcGIS epoch ms, a YYYYMMDD integer, an ISO / US string; None otherwise (never a guess)."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if not math.isfinite(v) or v <= 0:
            return None
        if v > 1e11:
            try:
                return dt.datetime.fromtimestamp(v / 1000.0, dt.timezone.utc).date()
            except (OverflowError, OSError, ValueError):
                return None
        if 18000101 <= v <= 21001231:
            s = str(int(v))
            try:
                return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            except ValueError:
                return None
        return None
    s = str(v).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s) or re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if m:
            mo, d, y = map(int, m.groups())
        elif re.fullmatch(r"\d{8}", s):
            return to_date(int(s))
        else:
            return None
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def to_year(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        y = int(float(str(v).strip()[:4]))
    except ValueError:
        return None
    return y if 1700 < y <= today_utc().year + 1 else None


def to_num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    s = re.sub(r"[$,\s]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def norm_street(address):
    """'1 Test Ave, Town, ST' -> '1 TEST AVE' (the city layers' upper-case, abbreviated form)."""
    s = re.sub(r"[.,]", " ", str(address or "").split(",")[0].upper())
    return " ".join(STREET_ABBR.get(w, w) for w in s.split())


def sql_quote(v):
    return str(v).replace("'", "''")


def _last(k):
    return str(k).rsplit(".", 1)[-1].upper()


def canon(attrs, role, mapping=None):
    """Canonical values from one feature's attributes: the layer ``map`` first, then the alias table.
    A list of fields is summed when numeric (assessed land = MRNLVL + MRALVL), else the first non-empty."""
    by_last = {}
    for k, v in (attrs or {}).items():
        by_last.setdefault(_last(k), (k, v))
    out = {}
    keys = list(dict.fromkeys(list((mapping or {}).keys()) + ROLE_KEYS.get(role, [])))
    for c in keys:
        srcs = mapping.get(c) if mapping and c in mapping else None
        if srcs is None:
            srcs = [by_last[a][0] for a in ALIASES.get(c, []) if a in by_last]
            srcs = srcs[:1]
        if isinstance(srcs, str):
            srcs = [srcs]
        vals = []
        for f in srcs or []:
            hit = attrs.get(f) if f in attrs else (by_last.get(_last(f)) or (None, None))[1]
            if hit is not None and not (isinstance(hit, str) and not hit.strip()):
                vals.append(hit)
        if not vals:
            continue
        if c in NUMERIC or len(srcs) > 1:
            nums = [to_num(v) for v in vals]
            if all(n is not None for n in nums):
                out[c] = sum(nums)
                continue
        v = vals[0]
        out[c] = v.strip() if isinstance(v, str) else v
    for c in list(out):
        if c in DATES:
            d = to_date(out[c])
            out[c] = d.isoformat() if d else None
        elif c in ("year_built",):
            out[c] = to_year(out[c])
        elif c == "assessed_year":
            out[c] = to_year(out[c])
    return {k: v for k, v in out.items() if v is not None}


def store_attrs(attrs):
    """Attributes kept in records.json: the requested fields minus address strings."""
    return {k: v for k, v in (attrs or {}).items() if not ADDRESS_FIELD.search(_last(k))}


def parse_house_desc(s):
    """County house description ('40 Newer 1st 2001-current', '1 1/2st') -> {storeys, era}."""
    out = {}
    if not s:
        return out
    m = re.search(r"(?<![\d/])(\d)(?:\s+(\d)/(\d))?\s*st\b", str(s), re.I)
    if m:
        v = float(m.group(1)) + (float(m.group(2)) / float(m.group(3)) if m.group(2) else 0.0)
        out["storeys"] = round(v, 2)
    e = re.search(r"(\d{4})\s*-\s*(\d{4}|current)", str(s), re.I)
    if e:
        out["era"] = f"{e.group(1)}-{e.group(2).lower()}"
    return out


# ---------------------------------------------------------------------------------------------- geometry

class Geo:
    """Lon/lat <-> local metres around the site origin (shapely)."""

    def __init__(self, lat0, lon0):
        from .geo import LocalFrame
        self.frame = LocalFrame(lat0, lon0)

    def to_m(self, g):
        import numpy as np
        import shapely

        def f(c):
            e, n, _ = self.frame.from_geodetic(c[:, 1], c[:, 0])
            return np.column_stack([e, n])
        return shapely.transform(g, f)

    def to_ll(self, g):
        import numpy as np
        import shapely

        def f(c):
            lat, lon, _ = self.frame.to_geodetic(c[:, 0], c[:, 1], 0.0)
            return np.column_stack([lon, lat])
        return shapely.transform(g, f)


# ---------------------------------------------------------------------------------------------- matching

class Ctx:
    def __init__(self, job, profile, http, today=None, street=None):
        self.job = job
        self.profile = profile
        self.http = http
        self.today = today or today_utc()
        self.cfg = _load(job, "job.json") or {}
        self.site = _load(job, "site.json") or {}
        self.ap_init = _load(job, "data/address_point.json") or {}
        geo = self.site.get("geocode") or {}
        lat, lon = geo.get("lat"), geo.get("lon")
        if lat is None and self.ap_init.get("lat") is not None:
            lat, lon = self.ap_init["lat"], self.ap_init["lon"]
        if lat is None:
            raise SystemExit("records: no geocoded point (run `pm.py init` / `demo_run.py run` first: site.json geocode)")
        self.lat, self.lon = float(lat), float(lon)
        self.geo = Geo(self.lat, self.lon)
        self.street = street or norm_street(self.cfg.get("address") or self.site.get("address") or "")
        self.number = self.street.split(" ")[0] if self.street else ""
        self.matched = {}            # layer name -> feature (single roles)
        self.parcel_ll = None        # shapely lon/lat
        self.parcel_m = None         # shapely local metres
        self.sources = []
        self.match = {}
        self.fallbacks = []
        self.never_global = list(profile.get("never_global") or [])

    def point_ll(self):
        from shapely.geometry import Point
        return Point(self.lon, self.lat)


def _load(job, rel):
    p = os.path.join(job, rel)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def _where_fmt(tmpl, ctx):
    return tmpl.format(street=sql_quote(ctx.street), STREET=sql_quote(ctx.street), number=sql_quote(ctx.number),
                       address=sql_quote(ctx.street))


def _key_value(ctx, ref):
    lay_name, field = str(ref).split(".", 1)
    f = ctx.matched.get(lay_name)
    if not f:
        return None
    a = f["attributes"]
    if field in a:
        return a[field]
    for k, v in a.items():
        if _last(k) == _last(field):
            return v
    return None


def _feature_filter(ctx, feats, method, role, multi):
    """Keep the features that belong to this property; rank the best first."""
    if not feats:
        return []
    pm = ctx.parcel_m
    pt_m = ctx.geo.to_m(ctx.point_ll())
    scored = []
    for f in feats:
        g = shapely_lonlat(f.get("geometry"))
        gm = ctx.geo.to_m(g) if g is not None and not g.is_empty else None
        score, keep = 0.0, True
        if gm is not None and gm.geom_type in ("Polygon", "MultiPolygon") and gm.area > 0:
            if method == "point":
                keep = gm.buffer(0.01).contains(pt_m)
                score = -gm.area                       # the smallest polygon holding the point
            elif method == "parcel_polygon" and pm is not None:
                ov = gm.intersection(pm).area
                frac = ov / max(min(gm.area, pm.area), 1e-9)
                keep = frac >= (0.5 if role != "footprint" else 0.5)
                score = frac + (0.5 if gm.buffer(0.01).contains(pt_m) else 0.0) + \
                    (gm.area / 1e6 if role == "footprint" else 0.0)
            else:
                score = -gm.distance(pt_m)
        elif gm is not None and gm.geom_type in ("Point", "MultiPoint"):
            if method == "parcel_polygon" and pm is not None:
                keep = pm.buffer(0.3).contains(gm)
            score = -gm.distance(pt_m)
        f = dict(f, _score=score)
        if keep:
            scored.append(f)
    scored.sort(key=lambda f: -f["_score"])
    for f in scored:
        f.pop("_score", None)
    return scored if multi else scored[:1]


def query_layer(ctx, name, lay, scope_label=""):
    """Run the layer's match methods in order; record the source entry and the method used.
    Returns the kept features ([] when none / unreachable)."""
    role = lay.get("role")
    multi = role not in SINGLE_ROLES
    methods = lay.get("match") or []
    methods = [methods] if isinstance(methods, str) else list(methods)
    never = list(lay.get("never") or []) + ctx.never_global
    fields = lay.get("out_fields") or []
    entry = {"name": name, "label": lay.get("label") or name, "role": role, "url": lay.get("url"),
             "fields": list(fields), "n": 0, "status": "empty", "method": None, "queried_at": None}
    errors, tried = [], []
    kept = []
    for i, m in enumerate(methods):
        params = {}
        if m == "point":
            params = dict(geometry=f"{ctx.lon:.8f},{ctx.lat:.8f}", geometry_type="esriGeometryPoint")
        elif m == "parcel_polygon":
            if ctx.parcel_ll is None:
                tried.append("parcel_polygon (no parcel)")
                continue
            params = dict(geometry=esri_polygon(ctx.parcel_ll), geometry_type="esriGeometryPolygon")
        elif m == "envelope":
            r = float(lay.get("radius_m", 30.0))
            dlat = r / 111320.0
            dlon = r / (111320.0 * math.cos(math.radians(ctx.lat)))
            params = dict(geometry=f"{ctx.lon - dlon:.8f},{ctx.lat - dlat:.8f},{ctx.lon + dlon:.8f},{ctx.lat + dlat:.8f}",
                          geometry_type="esriGeometryEnvelope")
        elif m == "key":
            k = lay.get("key") or {}
            v = _key_value(ctx, k.get("from", "."))
            if v in (None, ""):
                tried.append(f"key (no {k.get('from')})")
                continue
            q = str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else f"'{sql_quote(v)}'"
            params = dict(where=f"{k['field']} = {q}")
        elif m == "address":
            if not ctx.street:
                tried.append("address (no address in job.json)")
                continue
            params = dict(where=_where_fmt(lay.get("address_where") or lay.get("where_template"), ctx))
        else:
            continue
        where = params.pop("where", lay.get("where") or "1=1")
        if lay.get("where") and where != lay.get("where") and m in ("key", "address"):
            where = f"({lay['where']}) AND ({where})"
        try:
            feats, meta = arcgis_select(ctx.http, lay["url"], fields, where=where, never=never,
                                        max_age=lay.get("max_age_s", MAX_AGE_S), **params)
        except SourceUnreachable as e:
            errors.append(f"{m}: {e}")
            tried.append(m)
            continue
        except ValueError as e:          # refused field list: a profile error, never a query
            errors.append(f"{m}: {e}")
            break
        entry["queried_at"] = meta.get("fetched_at")
        entry["from_cache"] = meta.get("from_cache")
        entry["n_returned"] = meta.get("n")
        try:
            kept = _feature_filter(ctx, feats, m, role, multi)
        except Exception as e:  # noqa: BLE001 - a malformed geometry must not end the stage
            errors.append(f"{m}: could not match the reply ({type(e).__name__}: {str(e)[:120]})")
            tried.append(m)
            continue
        tried.append(m)
        if kept:
            entry.update(status="ok", method=m, n=len(kept), fallback=i > 0)
            if meta.get("truncated"):
                entry["note"] = "more records than the page limit; the newest may be missing"
            break
    if not kept:
        if errors and len(errors) >= len([t for t in tried if "(" not in t]):
            entry.update(status="unreachable",
                         message=f"{entry['label']}: source not reachable on {ctx.today.isoformat()}",
                         error="; ".join(errors)[:400])
        else:
            entry.update(status="empty", message=f"{entry['label']}: no record for this property "
                         f"(tried {', '.join(tried) or 'nothing'})", **({"error": "; ".join(errors)[:400]} if errors else {}))
    entry["tried"] = tried
    ctx.sources.append(entry)
    ctx.match[name] = entry["method"] or "none"
    if entry.get("fallback"):
        ctx.fallbacks.append({"source": name, "label": entry["label"], "method": entry["method"],
                              "first_choice": methods[0]})
    if kept and not multi:
        ctx.matched[name] = kept[0]
    return kept


# ---------------------------------------------------------------------------------------------- collection

def _first_role(profile, role, scope="city"):
    got = regions.layers_by_role(profile, role, scope)
    return got[0] if got else (None, None)


def _not_configured(ctx, what):
    ctx.sources.append({"name": what, "label": what, "status": "not_configured", "n": 0,
                        "message": f"{what}: not configured in the region profile"})
    ctx.match[what] = "none"


def collect(job, profile, http=None, today=None, street=None):
    """All records for one job -> the records.json dict (not yet written)."""
    http = http or Http()
    ctx = Ctx(job, profile, http, today=today, street=street)
    rec = {"queried_at": now_iso(), "profile": profile.get("name") or os.path.basename(profile.get("_path") or ""),
           "point": {"source": (ctx.site.get("geocode") or {}).get("source") or "address point"}}

    # 1. city parcel
    name, lay = _first_role(profile, "parcel")
    parcel = None
    if lay:
        got = query_layer(ctx, name, lay)
        if got:
            parcel = got[0]
            g = shapely_lonlat(parcel.get("geometry"))
            if g is not None and g.geom_type in ("Polygon", "MultiPolygon"):
                ctx.parcel_ll = g
                ctx.parcel_m = ctx.geo.to_m(g)
    else:
        _not_configured(ctx, "parcels")
    pc = canon(parcel["attributes"], "parcel", lay.get("map")) if parcel else {}
    rec["parcel"] = {"source": name, "values": pc, "attributes": store_attrs(parcel["attributes"]) if parcel else {},
                     "ring_lonlat": [[round(x, 7), round(y, 7)] for x, y in ctx.parcel_ll.exterior.coords]
                     if ctx.parcel_ll is not None and ctx.parcel_ll.geom_type == "Polygon" else None,
                     "area_m2": round(ctx.parcel_m.area, 1) if ctx.parcel_m is not None else None}

    # 2. address point (year built, occupancy...)
    name, lay = _first_role(profile, "geocode")
    apc, ap_attrs = {}, {}
    if lay:
        got = query_layer(ctx, name, lay)
        if got:
            ap_attrs = got[0]["attributes"]
        elif ctx.ap_init.get("attributes"):
            ap_attrs = privacy.filter_attrs(ctx.ap_init["attributes"], lay.get("out_fields") or [],
                                            list(lay.get("never") or []) + ctx.never_global)
            ctx.match[name] = "address"
            ctx.sources[-1].update(status="ok", method="address", n=1, fallback=True,
                                   message="address point from the init stage (matched by the address string)")
            ctx.fallbacks.append({"source": name, "label": ctx.sources[-1]["label"], "method": "address",
                                  "first_choice": (lay.get("match") or ["?"])[0]})
            ctx.matched[name] = {"attributes": ap_attrs, "geometry": None}
        apc = canon(ap_attrs, "geocode", lay.get("map"))
    rec["address_point"] = {"source": name, "values": apc, "attributes": store_attrs(ap_attrs)}

    # 3. footprint attributes (storeys)
    name, lay = _first_role(profile, "footprint")
    fpc, fp_attrs = {}, {}
    if lay and lay.get("url"):
        got = query_layer(ctx, name, lay)
        if got:
            fp_attrs = got[0]["attributes"]
            fpc = canon(fp_attrs, "footprint", lay.get("map"))
    rec["footprint_attrs"] = {"source": name, "values": fpc, "attributes": store_attrs(fp_attrs)}

    # 4. other city single layers (structures, zoning)
    extra = {}
    for role in ("structure", "zoning"):
        for name, lay in regions.layers_by_role(profile, role):
            got = query_layer(ctx, name, lay)
            if got:
                extra[name] = {"role": role, "values": canon(got[0]["attributes"], role, lay.get("map")),
                               "attributes": store_attrs(got[0]["attributes"])}
    rec["city_extra"] = extra

    # 5. city permits
    permits = []
    plist = regions.layers_by_role(profile, "permits")
    if not plist:
        _not_configured(ctx, "permits")
    for name, lay in plist:
        for f in query_layer(ctx, name, lay):
            permits.append(_permit_row(f, lay, name, ctx.match.get(name)))
    permit_since = {n: l.get("since") for n, l in plist}

    # 6. county
    county_val = pc.get("county") or apc.get("county") or (ctx.ap_init.get("county") if ctx.ap_init else None)
    cname, blk = regions.county_block(profile, county_val)
    rec["county"] = cname or (str(county_val) if county_val else None)
    inside = _inside_city(profile, apc)
    rec["inside_city"] = inside
    assessor, quality, sales, county_extra = {}, {}, [], {}
    if blk:
        lays = list((blk.get("layers") or {}).items())
        lays.sort(key=lambda kv: 0 if kv[1].get("role") == "parcel" else 1)
        for name, lay in lays:
            role = lay.get("role")
            if lay.get("only_outside_city") and inside:
                ctx.sources.append({"name": name, "label": lay.get("label") or name, "role": role, "url": lay.get("url"),
                                    "fields": list(lay.get("out_fields") or []), "n": 0, "status": "skipped",
                                    "message": f"{lay.get('label') or name}: skipped (inside the city limits: the city "
                                               "issues the permits)"})
                ctx.match[name] = "none"
                continue
            got = query_layer(ctx, name, lay, cname)
            if not got:
                continue
            if role == "permits":
                permits += [_permit_row(f, lay, name, ctx.match.get(name)) for f in got]
                permit_since[name] = lay.get("since")
            elif role == "sales":
                for f in got:
                    v = canon(f["attributes"], "sales", lay.get("map"))
                    sales.append({"source": name, "label": lay.get("label") or name, "match": ctx.match.get(name),
                                  **v, "attributes": store_attrs(f["attributes"])})
            elif role == "assessor":
                assessor = {"source": name, "label": lay.get("label") or name,
                            "values": canon(got[0]["attributes"], "assessor", lay.get("map")),
                            "attributes": store_attrs(got[0]["attributes"]), "year_note": lay.get("year_note")}
                if lay.get("year") and not assessor["values"].get("assessed_year"):
                    assessor["values"]["assessed_year"] = lay["year"]
            elif role == "quality":
                quality = {"source": name, "label": lay.get("label") or name,
                           "values": canon(got[0]["attributes"], "quality", lay.get("map")),
                           "attributes": store_attrs(got[0]["attributes"])}
            else:   # county parcel / zoning / context
                county_extra[name] = {"role": role, "label": lay.get("label") or name,
                                      "values": canon(got[0]["attributes"], role if role in ROLE_KEYS else "parcel",
                                                      lay.get("map")),
                                      "attributes": store_attrs(got[0]["attributes"])}
    elif profile.get("county_sources"):
        ctx.sources.append({"name": "county", "label": "county records", "status": "empty", "n": 0,
                            "message": f"county records: the parcel's county {county_val!r} has no county source in "
                                       "the profile"})
    # a county parcel layer can carry the assessed value (Lincoln: Value1..5 on the parcel)
    if not assessor:
        for name, ce in county_extra.items():
            v = ce["values"]
            if any(k.startswith("assessed_") for k in v):
                assessor = {"source": name, "label": ce["label"],
                            "values": {k: x for k, x in v.items() if k.startswith("assessed_")},
                            "attributes": {}, "year_note": None}
                break
    permits.sort(key=lambda p: p.get("finalize_date") or p.get("issue_date") or p.get("apply_date") or "", reverse=True)
    sales.sort(key=lambda s: s.get("sale_date") or str(s.get("sale_year") or ""), reverse=True)
    rec.update(permits=permits, assessor=assessor, quality=quality, sales=sales, county_extra=county_extra)
    rec["ids"] = _ids(ctx)
    rec["match"] = ctx.match
    rec["fallbacks"] = ctx.fallbacks
    rec["sources"] = ctx.sources
    lidar = _lidar_date(job, profile)
    rec["derived"] = derive(rec, ctx.today, lidar, permit_since, profile)
    rec["not_public"] = profile.get("not_public") or NOT_PUBLIC_DEFAULT
    rec["not_public_note"] = profile.get("not_public_note") or \
        "not publicly available (the county property cards are behind a bot wall, which is never worked around)"
    return rec


ID_FIELD = re.compile(r"^(tag|countyid|pid|parcel_?id|parcel_number|map_id)$", re.I)


def _ids(ctx):
    """Parcel identifiers of the matched features (scratch only: the wrapper greps the public repo for them)."""
    out = {}
    for f in ctx.matched.values():
        for k, v in (f.get("attributes") or {}).items():
            last = str(k).rsplit(".", 1)[-1]
            if ID_FIELD.match(last) and v not in (None, ""):
                out.setdefault(last.lower(), str(v))
    return out


def _inside_city(profile, apc):
    name, lay = _first_role(profile, "geocode")
    vals = [str(v).upper() for v in ((lay or {}).get("city_values") or [])]
    if not vals or not apc.get("city"):
        return None
    return str(apc["city"]).upper() in vals


def _permit_row(f, lay, name, method):
    v = canon(f["attributes"], "permits", lay.get("map"))
    text = " / ".join(str(v.get(k)) for k in ("work_class", "permit_type", "description") if v.get(k))
    row = {"source": name, "label": lay.get("label") or name, "match": method, **v,
           "reroof": bool(REROOF.search(text) and not NOT_REROOF.search(text)),
           "addition": bool(ADDITION.search(text)), "site_change": bool(SITE_CHANGE.search(text)),
           "dead": bool(DEAD_STATUS.search(str(v.get("permit_status") or ""))),
           "attributes": store_attrs(f["attributes"])}
    return row


def permit_date(p):
    """The date a permit's work is dated by: finalized, else issued, else applied (ISO str or None)."""
    return p.get("finalize_date") or p.get("issue_date") or p.get("apply_date")


def _lidar_date(job, profile):
    """(date, basis): the site's flight date from data/lidar.json when the LiDAR stage has run, else the
    profile's collection start (conservative), else Jan 1 of the profile's LiDAR year."""
    li = _load(job, "data/lidar.json") or {}
    d = to_date(li.get("flight_date"))
    if d:
        return d, "flight date of this site (LiDAR GpsTime)"
    pl = regions.layer(profile, "lidar") or {}
    col = pl.get("collected") or pl.get("collection")
    if isinstance(col, (list, tuple)) and col and to_date(col[0]):
        return to_date(col[0]), f"start of the LiDAR collection ({col[0]}); the site's own flight date is checked " \
            "again after the LiDAR stage"
    y = to_year(pl.get("year") or li.get("year"))
    if y:
        return dt.date(y, 1, 1), f"LiDAR year {y} (flight date not known yet)"
    return None, "LiDAR date unknown"


def derive(rec, today, lidar=(None, ""), permit_since=None, profile=None):
    """Roof age, permit timeline, the house facts and the changes-after-LiDAR flag (G1)."""
    lidar_d, lidar_basis = lidar if isinstance(lidar, tuple) else (lidar, "")
    pc = (rec.get("parcel") or {}).get("values") or {}
    apc = (rec.get("address_point") or {}).get("values") or {}
    fpc = (rec.get("footprint_attrs") or {}).get("values") or {}
    q = (rec.get("quality") or {}).get("values") or {}
    sales = rec.get("sales") or []
    permits = rec.get("permits") or []
    d = {}
    # year built
    yb, ysrc = None, None
    for v, src in ((apc.get("year_built"), "city address point"), (q.get("year_built"), "county house quality"),
                   *[(s.get("year_built"), s.get("label") or "county sales") for s in sales]):
        if v:
            yb, ysrc = v, src
            break
    d["year_built"] = yb
    d["year_built_source"] = ysrc
    # storeys / style / grade
    hd = parse_house_desc(q.get("style"))
    st = {}
    if fpc.get("storeys"):
        try:
            n = float(fpc["storeys"])
            if n > 0:
                st["city_footprint"] = n
        except (TypeError, ValueError):
            pass
    if hd.get("storeys"):
        st["county"] = hd["storeys"]
    d["storeys"] = st.get("city_footprint") or st.get("county")
    d["storeys_sources"] = st
    d["style"] = q.get("style") or next((s.get("style") for s in sales if s.get("style")), None)
    d["era"] = hd.get("era")
    d["grade"] = q.get("grade") if q.get("grade") not in (None, "") else None
    d["grade_desc"] = q.get("grade_desc") or next((s.get("grade_desc") for s in sales if s.get("grade_desc")), None)
    d["condition"] = q.get("condition") or next((s.get("condition") for s in sales if s.get("condition")), None)
    d["structure"] = fpc.get("structure")
    # lot / land use / zoning
    ce = {}
    for x in (rec.get("county_extra") or {}).values():
        for k, v in (x.get("values") or {}).items():
            ce.setdefault(k, v)
    d["lot_sqft"] = pc.get("lot_sqft") or ce.get("lot_sqft")
    d["lot_acres"] = pc.get("lot_acres") or ce.get("lot_acres")
    if d["lot_sqft"] is None and d["lot_acres"]:
        d["lot_sqft"] = d["lot_acres"] * 43560.0
    if d["lot_acres"] is None and d["lot_sqft"]:
        d["lot_acres"] = d["lot_sqft"] / 43560.0
    d["land_use"] = pc.get("land_use") or pc.get("land_use_code") or ce.get("land_use") or apc.get("occupancy")
    zon = pc.get("zoning") or ce.get("zoning")
    for x in (rec.get("city_extra") or {}).values():
        zon = zon or (x.get("values") or {}).get("zoning")
    d["zoning"] = zon
    d["subdivision"] = pc.get("subdivision") or ce.get("subdivision")
    # assessed value
    av = (rec.get("assessor") or {}).get("values") or {}
    land, bldg, tot = av.get("assessed_land"), av.get("assessed_building"), av.get("assessed_total")
    if tot is None and land is not None and bldg is not None:
        tot = land + bldg
    d["assessed"] = {"land": land, "building": bldg, "total": tot, "year": av.get("assessed_year"),
                     "class": av.get("assessed_class"), "source": (rec.get("assessor") or {}).get("label"),
                     "year_note": (rec.get("assessor") or {}).get("year_note")} if (land or bldg or tot) else None
    # last sale (a public sale with a price)
    priced = [s for s in sales if (s.get("sale_price") or 0) > 0 and (s.get("sale_date") or s.get("sale_year"))]
    d["last_sale"] = ({"date": priced[0].get("sale_date"), "year": priced[0].get("sale_year"),
                       "price": priced[0].get("sale_price"), "source": priced[0].get("label")} if priced else None)
    # permits: timeline, re-roof, roof age
    live = [p for p in permits if not p.get("dead")]
    reroofs = [p for p in live if p.get("reroof") and permit_date(p)]
    reroofs.sort(key=permit_date, reverse=True)
    since = min([s for s in (permit_since or {}).values() if s] or [None]) if permit_since else None
    since = since or None
    d["permits_since"] = since
    if reroofs:
        p = reroofs[0]
        when = to_date(permit_date(p))
        age = (today - when).days / 365.25
        d["last_reroof"] = {"date": when.isoformat(), "work_class": p.get("work_class") or p.get("permit_type"),
                            "basis": "finalized" if p.get("finalize_date") else ("issued" if p.get("issue_date") else "applied"),
                            "source": p.get("label")}
        d["roof_age_years"] = round(age, 1)
        d["roof_age_text"] = f"re-roofed {when.year} ({d['last_reroof']['work_class']} permit " \
                             f"{d['last_reroof']['basis']} {when.isoformat()}), about {max(0, round(age))} years"
    else:
        d["last_reroof"] = None
        since_d = to_date(since) if since else None
        since_txt = since_d.isoformat() if since_d else "the start of the permit records"
        if yb and since_d and yb >= since_d.year:
            d["roof_age_years"] = round(today.year - yb + 0.0, 1)
            d["roof_age_text"] = f"no re-roof permit on record; house built {yb}, so the roof is likely original, " \
                                 f"about {today.year - yb} years"
        elif since_d:
            low = (today - since_d).days / 365.25
            d["roof_age_years"] = None
            d["roof_age_min_years"] = round(low, 1)
            d["roof_age_text"] = f"no re-roof permit since {since_txt}; the roof is at least as old as " \
                                 f"{since_d.year} (about {int(low)}+ years) unless it was re-roofed without a permit" + \
                                 (f"; house built {yb}" if yb else "")
        else:
            d["roof_age_years"] = None
            d["roof_age_text"] = "no re-roof permit found; the permit layer's start date is not in the profile"
    d["permit_timeline"] = [{"date": permit_date(p), "issue_date": p.get("issue_date"),
                             "finalize_date": p.get("finalize_date"), "work_class": p.get("work_class"),
                             "permit_type": p.get("permit_type"), "status": p.get("permit_status"),
                             "valuation": p.get("valuation"), "description": p.get("description"),
                             "reroof": p.get("reroof"), "source": p.get("label")} for p in permits]
    # changes after the LiDAR flight (gate G1)
    reasons, late, site = [], [], []
    if lidar_d:
        for p in live:
            pd_ = to_date(permit_date(p))
            if not pd_ or pd_ <= lidar_d:
                continue
            if p.get("addition"):
                late.append({"date": pd_.isoformat(), "work_class": p.get("work_class") or p.get("permit_type")})
            elif p.get("site_change"):
                site.append({"date": pd_.isoformat(), "work_class": p.get("work_class") or p.get("permit_type")})
        if late:
            reasons.append(f"{len(late)} addition / new-construction permit(s) after the LiDAR ({lidar_d.isoformat()})")
        if yb and yb >= lidar_d.year:
            reasons.append(f"year built {yb} >= LiDAR year {lidar_d.year}")
    d["changes_after_lidar"] = {"flag": bool(reasons), "reasons": reasons, "permits": late, "site_changes": site,
                                "lidar_date": lidar_d.isoformat() if lidar_d else None, "basis": lidar_basis}
    return d


# ---------------------------------------------------------------------------------------------- output

def _money(v):
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "-"


def _md_escape(s):
    return str(s).replace("|", "/").replace("\n", " ")


def section_md(rec):
    d = rec["derived"]
    today = rec["queried_at"][:10]
    lines = ["## Property records", "",
             f"Public city and county GIS services, queried {rec['queried_at'].replace('T', ' ').replace('Z', ' UTC')}. "
             "Each layer was matched to the parcel that contains the address point; a fallback match is flagged below. "
             "Names and postal addresses of people are never requested or stored.", ""]
    rows = [("Roof age", d.get("roof_age_text") or "-",
             (d.get("last_reroof") or {}).get("source") or "building permits")]
    rows.append(("Year built", str(d["year_built"]) if d.get("year_built") else "not on record", d.get("year_built_source") or ""))
    st = []
    if d.get("storeys_sources", {}).get("city_footprint"):
        st.append(f"{d['storeys_sources']['city_footprint']:g} storey(s) (city footprint)")
    if d.get("storeys_sources", {}).get("county"):
        st.append(f"{d['storeys_sources']['county']:g} storey(s) (county)")
    if d.get("style"):
        st.append(f"style \"{_md_escape(d['style'])}\"")
    if d.get("grade") is not None or d.get("grade_desc"):
        st.append("grade " + " ".join(str(x) for x in (d.get("grade"), d.get("grade_desc")) if x not in (None, "")))
    if d.get("condition"):
        st.append(f"condition {d['condition']}")
    rows.append(("Storeys / style / grade", "; ".join(st) or "not on record", "city footprint, county equalization"))
    if d.get("lot_sqft"):
        rows.append(("Lot area", f"{d['lot_sqft']:,.0f} sq ft ({d['lot_acres']:.2f} acres)", "parcel layer"))
    lu = [str(x) for x in (d.get("land_use"), ("zoning " + str(d["zoning"])) if d.get("zoning") else None) if x]
    rows.append(("Land use / zoning", "; ".join(lu) or "not on record", "parcel layer"))
    a = d.get("assessed")
    if a:
        yr = f"assessment year {a['year']}" if a.get("year") else (a.get("year_note") or "year not stated by the layer")
        parts = []
        if a.get("land") is not None:
            parts.append(f"land {_money(a['land'])}")
        if a.get("building") is not None:
            parts.append(f"building {_money(a['building'])}")
        parts.append(f"total {_money(a.get('total'))}")
        rows.append(("Assessed value", " / ".join(parts) + f" ({yr})", a.get("source") or "county"))
    else:
        rows.append(("Assessed value", "not found in the public county layers", ""))
    ls = d.get("last_sale")
    rows.append(("Last sale", f"{ls.get('date') or ls.get('year')}, {_money(ls.get('price'))}" if ls else
                 "no public sale with a price found", (ls or {}).get("source") or ""))
    rows.append(("Not publicly available", ", ".join(rec.get("not_public") or []), rec.get("not_public_note") or ""))
    lines += ["| Item | Value | Source |", "|---|---|---|"]
    lines += [f"| {_md_escape(a_)} | {_md_escape(b)} | {_md_escape(c)} |" for a_, b, c in rows]
    tl = d.get("permit_timeline") or []
    lines += ["", f"### Permit timeline{' (records start ' + d['permits_since'] + ')' if d.get('permits_since') else ''}", ""]
    if tl:
        lines += ["| Date | Work | Type | Status | Valuation | Source |", "|---|---|---|---|---|---|"]
        for p in tl:
            work = p.get("work_class") or p.get("description") or "-"
            if p.get("reroof"):
                work += " (re-roof, not counted: " + str(p.get("status")) + ")" if DEAD_STATUS.search(str(p.get("status") or "")) \
                    else " (re-roof)"
            lines.append(f"| {p.get('date') or '-'} | {_md_escape(work)} | {_md_escape(p.get('permit_type') or '-')} | "
                         f"{_md_escape(p.get('status') or '-')} | {_money(p.get('valuation')) if p.get('valuation') else '-'} | "
                         f"{_md_escape(p.get('source') or '')} |")
    else:
        lines.append("No building permits on record for this parcel in the public permit layers.")
    ch = d.get("changes_after_lidar") or {}
    lines += ["", "### Changes since the LiDAR flight", ""]
    if ch.get("flag"):
        lines.append("**Check before quoting:** " + "; ".join(ch["reasons"]) + ". The LiDAR may not show today's roof.")
    elif ch.get("lidar_date"):
        lines.append(f"No addition or new-construction permit after {ch['lidar_date']} ({ch.get('basis')}).")
    else:
        lines.append("LiDAR date unknown: not checked.")
    if ch.get("site_changes"):
        lines.append("Other site changes after the LiDAR: " + ", ".join(f"{s['work_class']} {s['date']}" for s in ch["site_changes"]) + ".")
    fb = rec.get("fallbacks") or []
    lines += ["", "### Sources and matching", ""]
    for s in rec.get("sources") or []:
        if s.get("status") == "ok":
            fl = " **fallback match**" if s.get("fallback") else ""
            lines.append(f"- {s['label']}: {s['n']} record(s), matched by {s['method'].replace('_', ' ')}{fl}"
                         f" (queried {str(s.get('queried_at') or today)[:16].replace('T', ' ')})")
        else:
            lines.append(f"- {s.get('message') or s['label'] + ': ' + s['status']}")
    if fb:
        lines += ["", "Fallback matches (check them): " + "; ".join(
            f"{f['label']} by {f['method'].replace('_', ' ')} instead of {f['first_choice'].replace('_', ' ')}" for f in fb) + "."]
    return "\n".join(lines) + "\n"


def detail_json(rec):
    """The studio detail block (no parcel ids, addresses, coordinates or raw attributes)."""
    d = rec["derived"]
    return {
        "label": "Property records", "queried_at": rec["queried_at"], "county": rec.get("county"),
        "roof_age": {"text": d.get("roof_age_text"), "years": d.get("roof_age_years"),
                     "last_reroof": d.get("last_reroof")},
        "year_built": d.get("year_built"), "storeys": d.get("storeys"), "style": d.get("style"), "era": d.get("era"),
        "grade": d.get("grade"), "grade_desc": d.get("grade_desc"), "condition": d.get("condition"),
        "lot": {"sqft": d.get("lot_sqft"), "acres": d.get("lot_acres")},
        "land_use": d.get("land_use"), "zoning": d.get("zoning"), "assessed": d.get("assessed"),
        "last_sale": d.get("last_sale"),
        "permit_timeline": [{k: p.get(k) for k in ("date", "work_class", "permit_type", "status", "valuation", "reroof",
                                                   "source")} for p in d.get("permit_timeline") or []],
        "changes_after_lidar": d.get("changes_after_lidar"),
        "not_public": rec.get("not_public"),
        "fallback_matches": [f["label"] for f in rec.get("fallbacks") or []],
        "sources": [{"label": s.get("label"), "status": s.get("status"), "n": s.get("n"), "method": s.get("method"),
                     "queried_at": s.get("queried_at")} for s in rec.get("sources") or []],
    }


def write_outputs(job, rec, profile=None):
    """Write the three files, then privacy-scan them; on any hit delete all three and raise PrivacyError."""
    paths = {"data": os.path.join(job, "data", "records.json"),
             "section": os.path.join(job, "out", "sections", "40_records.md"),
             "detail": os.path.join(job, "out", "detail_extra", "records.json")}
    for p in paths.values():
        os.makedirs(os.path.dirname(p), exist_ok=True)
    _jsave(paths["data"], rec)
    with open(paths["section"], "w") as f:
        f.write(section_md(rec))
    _jsave(paths["detail"], detail_json(rec))
    check_written(list(paths.values()), profile)
    return paths


class PrivacyError(RuntimeError):
    pass


def check_written(paths, profile=None):
    never = privacy.profile_never(profile) if profile else ()
    hits = []
    for p in paths:
        hits += privacy.scan(p, never)
    if hits:
        for p in paths:
            if os.path.exists(p):
                os.remove(p)
        raise PrivacyError("privacy scan: " + "; ".join(f"{h['file']}: {h['where']}: {h['key']}" for h in hits[:20]))


def _jsave(path, obj):
    tmp = path + ".part"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def run(job, profile_ref, http=None, today=None, street=None):
    profile = regions.load(profile_ref)
    rec = collect(job, profile, http=http, today=today, street=street)
    paths = write_outputs(job, rec, profile)
    return rec, paths
