"""Offline stand-in for the public services used by the records / hazards tests.

FakeServer(...) is a ``transport`` for :class:`propmodel.sources.Http`: it answers from responses/ (recorded
style, synthetic values), returns every feature of a layer for a spatial query (the code under test must do
the per-property filtering itself), honours ``where`` clauses of the form ``FIELD = 'v'`` / ``FIELD = n`` /
``FIELD LIKE 'v%'``, and records every call. ``behaviour[layer]`` = "fail" (connection error), "empty_spatial"
(no features for a spatial query) or "empty"; ``override[layer]`` replaces a layer's reply.
"""
import copy
import csv
import gzip
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RESP = os.path.join(HERE, "responses")
PROFILE = os.path.join(HERE, "profile.json")

ROUTES = [  # (url regex, response key)
    (r"City/MapServer/0/query", "address_points"),
    (r"City/MapServer/1/query", "parcels"),
    (r"City/MapServer/5/query", "footprints"),
    (r"Community/MapServer/3/query", "permits"),
    (r"AssessedValues/MapServer/1/query", "alpha_assessed"),
    (r"HouseQuality_2024/MapServer/1/query", "alpha_quality"),
    (r"Residential_Sales/MapServer/1/query", "alpha_sales_2025"),
    (r"Residential_Sales/MapServer/3/query", "alpha_sales_2023"),
    (r"Pro29/Parcels/MapServer/0/query", "beta_parcels"),
    (r"Pro29/BuildingPermits/MapServer/2/query", "beta_permits"),
    (r"Pro29/FullSales/MapServer/11/query", "beta_fullsales"),
    (r"NFHL/MapServer/28/query", "nfhl"),
]


def load(key):
    with open(os.path.join(RESP, key + (".json" if "." not in key else ""))) as f:
        return json.load(f) if key.endswith(".json") or "." not in key else f.read()


def text(name):
    with open(os.path.join(RESP, name)) as f:
        return f.read()


def storm_year_gz(year):
    """The sample Storm Events rows of one year, gzipped like the NCEI files."""
    src = text("storm_events_sample.csv")
    rdr = csv.reader(io.StringIO(src))
    head = next(rdr)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(head)
    for r in rdr:
        if r[0][:4] == str(year):
            w.writerow(r)
    return gzip.compress(out.getvalue().encode())


def _where_ok(where, attrs):
    if not where or where.strip() == "1=1":
        return True
    ok = True
    for m in re.finditer(r"(\w[\w.]*)\s*(=|LIKE)\s*('(?:[^']|'')*'|[\d.]+)", where):
        f, op, v = m.groups()
        val = attrs.get(f)
        v = v[1:-1].replace("''", "'") if v.startswith("'") else v
        if op == "LIKE":
            ok &= str(val or "").startswith(v.rstrip("%"))
        else:
            ok &= str(val) == v
    return ok


class FakeServer:
    def __init__(self, behaviour=None, override=None):
        self.behaviour = dict(behaviour or {})
        self.override = dict(override or {})
        self.calls = []

    def __call__(self, method, url, params=None, data=None, timeout=60, headers=None, stream_to=None):
        p = dict(params or data or {})
        self.calls.append({"method": method, "url": url, "params": p})
        if "stormevents/csvfiles/" in url:
            if url.endswith("/csvfiles/"):
                return self._b("storm_index", text("stormevents_index.html"))
            m = re.search(r"_d(\d{4})_c", url)
            return self._b("storm_file", storm_year_gz(int(m.group(1))), raw=True)
        if "mesonet.agron.iastate.edu" in url:
            return self._b("iem", json.dumps(load("iem_lsr")))
        if "spc.noaa.gov" in url:
            day = re.search(r"/(\d{6})_rpts_(\w+)\.csv", url)
            name = f"spc_{day.group(1)}_{day.group(2)}.csv"
            if not os.path.exists(os.path.join(RESP, name)):
                return self._b("spc", "Time,Size,Location,County,State,Lat,Lon,Comments\n")
            return self._b("spc", text(name))
        if "swdiws" in url:
            return self._b("swdi", text("swdi_nx3hail.csv"))
        if "api.weather.gov" in url:
            return self._b("nws", json.dumps({"properties": {"cwa": "XXX"}}))
        for rx, key in ROUTES:
            if re.search(rx, url):
                return self._arcgis(key, p)
        raise ConnectionError(f"fake server: no route for {url}")

    def _b(self, key, body, raw=False):
        if self.behaviour.get(key) == "fail":
            raise ConnectionError(f"fake server: {key} down")
        return body if raw else body.encode()

    def _arcgis(self, key, p):
        b = self.behaviour.get(key)
        if b == "fail":
            raise ConnectionError(f"fake server: {key} down")
        d = copy.deepcopy(self.override[key]) if key in self.override else load(key)
        if key == "parcels" and p.get("geometry") and not self.override.get(key):
            d["features"] = d["features"] + load("parcels_neighbour")["features"]
        feats = d.get("features") or []
        spatial = bool(p.get("geometry"))
        if b == "empty" or (b == "empty_spatial" and spatial):
            feats = []
        feats = [f for f in feats if _where_ok(p.get("where"), f.get("attributes") or {})]
        d["features"] = feats
        return json.dumps(d).encode()

    def queries(self, key_rx):
        return [c for c in self.calls if re.search(key_rx, c["url"])]
