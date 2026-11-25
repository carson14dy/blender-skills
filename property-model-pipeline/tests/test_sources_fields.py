"""propmodel.sources: every ArcGIS query names its fields. outFields=* raises, the list sent is exactly the
list given, and only those attributes come back (city layers carry OWNEDBY, parcel layers OWNNAME1 ...)."""
import inspect
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)
sys.path.insert(0, os.path.join(HERE, "fixtures", "records"))

from propmodel import sources  # noqa: E402
from fake_http import FakeServer  # noqa: E402

FP_REPLY = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "id": 7, "properties": {"OBJECTID": 7, "NUMBERSTORIES": 2, "OWNEDBY": -1, "COMMENTS": "x"},
     "geometry": {"type": "Polygon", "coordinates": [[[-140.0, 10.0], [-140.0, 10.0001], [-139.9999, 10.0001],
                                                      [-139.9999, 10.0], [-140.0, 10.0]]]}}]}
PARCEL_REPLY = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"TAG": "T1", "SQFT": 6000.0, "OWNNAME1": "PLANTED", "MRTADR": "PLANTED"},
     "geometry": None}]}


@pytest.fixture
def capture(monkeypatch):
    seen = []

    def fake_get(url, cache_dir, params=None, **k):
        seen.append({"url": url, "params": dict(params or {})})
        return json.loads(json.dumps(FP_REPLY if "MapServer/5" in url else PARCEL_REPLY))
    monkeypatch.setattr(sources, "_get", fake_get)
    return seen


def test_footprints_star_raises(capture, tmp_path):
    for bad in ("*", ["*"], [], None):
        with pytest.raises(ValueError):
            sources.arcgis_footprints("https://x.test/MapServer/5", 10.0, -140.0, 30, str(tmp_path), bad)
    assert capture == []                                    # nothing was sent
    with pytest.raises(ValueError):                         # a name field is refused before sending
        sources.arcgis_footprints("https://x.test/MapServer/5", 10.0, -140.0, 30, str(tmp_path), ["OBJECTID", "OWNEDBY"])
    assert capture == []


def test_footprints_send_exact_list_and_copy_only_those(capture, tmp_path):
    got = sources.arcgis_footprints("https://x.test/MapServer/5", 10.0, -140.0, 30, str(tmp_path),
                                    out_fields=["OBJECTID", "NUMBERSTORIES"], where="STATUS = 'Existing'")
    p = capture[0]["params"]
    assert p["outFields"] == "OBJECTID,NUMBERSTORIES"
    assert p["where"] == "STATUS = 'Existing'"
    assert got and got[0]["tags"] == {"OBJECTID": 7, "NUMBERSTORIES": 2}     # OWNEDBY / COMMENTS dropped


def test_parcel_requires_fields(capture, tmp_path):
    par = inspect.signature(sources.arcgis_parcel).parameters["out_fields"]
    assert par.default is inspect.Parameter.empty            # pm.py then passes the list itself
    with pytest.raises(TypeError):
        sources.arcgis_parcel("https://x.test/MapServer/1", 10.0, -140.0, str(tmp_path))
    with pytest.raises(ValueError):
        sources.arcgis_parcel("https://x.test/MapServer/1", 10.0, -140.0, str(tmp_path), "*")
    assert capture == []
    feats = sources.arcgis_parcel("https://x.test/MapServer/1", 10.0, -140.0, str(tmp_path), ["TAG", "SQFT"])
    assert capture[0]["params"]["outFields"] == "TAG,SQFT" and capture[0]["params"]["where"] == "1=1"
    assert feats[0]["properties"] == {"TAG": "T1", "SQFT": 6000.0}


def test_arcgis_select_sends_exact_fields_and_filters(tmp_path):
    srv = FakeServer()
    http = sources.Http(cache_dir=str(tmp_path), offline=False, transport=srv)
    fields = ["OBJECTID", "TAG", "SQFT"]
    feats, meta = sources.arcgis_select(http, "https://gis.example.test/arcgis/rest/services/City/MapServer/1", fields,
                                        geometry="-140,10", geometry_type="esriGeometryPoint")
    q = srv.calls[-1]["params"]
    assert q["outFields"] == "OBJECTID,TAG,SQFT" and q["f"] == "json"
    assert all(set(f["attributes"]) <= set(fields) for f in feats)            # OWNNAME1 in the reply: dropped
    assert feats[0]["geometry"]["type"] == "Polygon"
    n = len(srv.calls)
    with pytest.raises(ValueError):
        sources.arcgis_select(http, "https://gis.example.test/arcgis/rest/services/City/MapServer/1", "*")
    with pytest.raises(ValueError):
        sources.arcgis_select(http, "https://gis.example.test/arcgis/rest/services/City/MapServer/1",
                              ["TAG", "OWNNAME1"])
    assert len(srv.calls) == n


def test_http_offline_miss_and_stale_copy(tmp_path):
    srv = FakeServer()
    off = sources.Http(cache_dir=str(tmp_path), offline=True, transport=srv)
    with pytest.raises(sources.SourceUnreachable, match="offline"):
        off.get("https://api.weather.gov/points/10.0000,-140.0000")
    assert srv.calls == []
    on = sources.Http(cache_dir=str(tmp_path), offline=False, transport=srv)
    d, m = on.get("https://api.weather.gov/points/10.0000,-140.0000", max_age=0)
    assert d["properties"]["cwa"] == "XXX" and not m["stale"]
    srv.behaviour["nws"] = "fail"
    d, m = on.get("https://api.weather.gov/points/10.0000,-140.0000", max_age=0)     # down: the cached copy, flagged
    assert m["stale"] and d["properties"]["cwa"] == "XXX"
    d, m = off.get("https://api.weather.gov/points/10.0000,-140.0000")              # offline: cache hit
    assert m["from_cache"]


def test_esri_geometry_conversion():
    g = sources.esri_to_geojson({"rings": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]],
                                           [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8], [0.2, 0.2]]]})
    assert g["type"] == "Polygon" and len(g["coordinates"]) == 2              # one exterior + its hole
    s = sources.shapely_lonlat(g)
    assert abs(s.area - 0.64) < 1e-9
    e = sources.esri_polygon(s)
    assert e["spatialReference"]["wkid"] == 4326 and len(e["rings"]) == 2
    assert sources.esri_to_geojson({"x": 1.0, "y": 2.0}) == {"type": "Point", "coordinates": [1.0, 2.0]}
