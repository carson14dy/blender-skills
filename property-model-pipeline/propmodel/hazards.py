"""Hazard history and roof-condition facts for one property, from public sources only.

DEMO MUST
* Hail / wind / tornado reports near the house: NOAA NCEI Storm Events yearly CSV (final; ~16 MB a year,
  downloaded once into PROPMODEL_CACHE and reduced to a small severe-weather subset), then the months NCEI has
  not published yet from the Iowa Environmental Mesonet local-storm-report GeoJSON and the NOAA SPC daily
  report CSVs (both labelled preliminary). Narratives, remarks and comments are never stored.
  Events within 1, 5 and 10 miles of the parcel centre: date, type, hail size (in) or gust (mph, from knots),
  distance; events after the last re-roof permit are flagged (insurance-claim relevance).
* FEMA flood zone: NFHL MapServer/28 on the parcel polygon (worst zone touching the parcel, and at the house).
* After the roof fit (``--only roof``): tree overhang (% of the roof plan with LiDAR returns >= 0.5 m above the
  fitted roof surface, and which edges), roof access flags per facet (walkable <= 6/12, steep 7-9, very steep
  > 9), storeys, highest eave above grade.
DEMO SHOULD: NEXRAD hail signatures (NCEI SWDI nx3hail, bbox query, <= 744 h a request) on the reported hail
dates only, labelled radar-estimated; roof colour from the ortho per facet, labelled an estimate; re-roof
permits within 300 m per year (counts only).
LATER (written as "not included"): MRMS MESH swaths, roof material, code edition / snow / wind design values.

A source that fails is written as "<source>: source not reachable on <date>", never dropped or guessed, and no
hazard result stops a run.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import re

from . import privacy, regions
from .sources import Http, SourceUnreachable, arcgis_select, esri_polygon

KT_TO_MPH = 1.15078
M_PER_MI = 1609.344
STORM_INDEX = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
STORM_RE = re.compile(r"StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz")
IEM_LSR = "https://mesonet.agron.iastate.edu/geojson/lsr.geojson"
SPC_DAILY = "https://www.spc.noaa.gov/climo/reports/{day}_rpts_{kind}.csv"
SWDI_HAIL = "https://www.ncei.noaa.gov/swdiws/csv/nx3hail/{start}:{end}"
NFHL_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
NFHL_FIELDS = ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "STATIC_BFE", "DFIRM_ID"]
NWS_POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
STORM_TYPES = {"Hail": "hail", "Thunderstorm Wind": "wind", "Tornado": "tornado", "High Wind": "wind",
               "Strong Wind": "wind"}
STORM_KEEP = ("EVENT_ID", "BEGIN_YEARMONTH", "BEGIN_DAY", "BEGIN_TIME", "CZ_TIMEZONE", "EVENT_TYPE", "MAGNITUDE",
              "MAGNITUDE_TYPE", "TOR_F_SCALE", "BEGIN_LAT", "BEGIN_LON", "END_LAT", "END_LON", "STATE", "WFO",
              "BEGIN_RANGE", "BEGIN_AZIMUTH", "BEGIN_LOCATION", "SOURCE", "DAMAGE_PROPERTY")
IEM_KIND = {"HAIL": "hail", "TSTM WND GST": "wind", "NON-TSTM WND GST": "wind", "MARINE TSTM WIND": "wind",
            "TSTM WND DMG": "wind_damage", "NON-TSTM WND DMG": "wind_damage", "TORNADO": "tornado"}
RADII_MI = (1, 5, 10)
IEM_CAP = 1000                  # the saved Nov 2026 reply held exactly 1000 features: treat it as a cap
HAIL_BIG_IN = 1.0
WIND_BIG_MPH = 58
PITCH_CLASSES = (("walkable", 6.0), ("steep", 9.0), ("very steep", 99.0))
TODAY = None


# ---------------------------------------------------------------------------------------------- helpers

def today_utc():
    return TODAY or dt.datetime.now(dt.timezone.utc).date()


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _num(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def haversine_mi(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a))) / M_PER_MI


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def compass(b, n=8):
    if b is None:
        return None
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] if n == 8 else \
        ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return names[int((b % 360) / (360 / n) + 0.5) % n]


def kt_to_mph(kt):
    return None if kt is None else kt * KT_TO_MPH


def unreachable(label, day, err=None):
    d = day.isoformat() if hasattr(day, "isoformat") else str(day)
    out = {"status": "unreachable", "message": f"{label}: source not reachable on {d}"}
    if err:
        out["error"] = str(err)[:300]
    return out


def _seg_dist_mi(lat, lon, la1, lo1, la2, lo2):
    """Distance (mi) from a point to a short track segment (local equirectangular approximation)."""
    kx = math.cos(math.radians(lat)) * 69.172
    ky = 69.0
    ax, ay = (lo1 - lon) * kx, (la1 - lat) * ky
    bx, by = (lo2 - lon) * kx, (la2 - lat) * ky
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    return math.hypot(ax + t * dx, ay + t * dy)


# ---------------------------------------------------------------------------------------------- storm events

def parse_storm_csv(fh):
    """NCEI Storm Events 'details' CSV -> (severe rows, latest event date in the file). Keeps hail / wind /
    tornado rows with a point location; narrative columns are never read into the output."""
    rows, latest = [], None
    for r in csv.DictReader(fh):
        ym, day = (r.get("BEGIN_YEARMONTH") or "").strip(), (r.get("BEGIN_DAY") or "").strip()
        try:
            d = dt.date(int(ym[:4]), int(ym[4:6]), int(day))
        except ValueError:
            continue
        latest = d if latest is None or d > latest else latest
        et = (r.get("EVENT_TYPE") or "").strip()
        kind = STORM_TYPES.get(et)
        if not kind:
            continue
        lat, lon = _num(r.get("BEGIN_LAT")), _num(r.get("BEGIN_LON"))
        if lat is None or lon is None:
            continue
        mag = _num(r.get("MAGNITUDE"))
        place = " ".join(str(r.get(k) or "").strip() for k in ("BEGIN_RANGE", "BEGIN_AZIMUTH", "BEGIN_LOCATION")).strip()
        row = {"id": (r.get("EVENT_ID") or "").strip(), "date": d.isoformat(), "time": (r.get("BEGIN_TIME") or "").strip(),
               "tz": (r.get("CZ_TIMEZONE") or "").strip(), "event_type": et, "kind": kind, "lat": lat, "lon": lon,
               "state": (r.get("STATE") or "").strip(), "wfo": (r.get("WFO") or "").strip(), "place": place,
               "reported_by": (r.get("SOURCE") or "").strip(), "damage_property": (r.get("DAMAGE_PROPERTY") or "").strip()}
        la2, lo2 = _num(r.get("END_LAT")), _num(r.get("END_LON"))
        if la2 is not None and lo2 is not None:
            row["lat2"], row["lon2"] = la2, lo2
        if kind == "hail":
            row["size_in"] = mag
        elif kind == "wind":
            mt = (r.get("MAGNITUDE_TYPE") or "").strip().upper()
            row["speed_kt"] = mag
            row["speed_mph"] = round(kt_to_mph(mag)) if mag is not None else None
            row["mag_type"] = mt or None
            row["measured"] = mt.startswith("M") if mt else None
        else:
            row["f_scale"] = (r.get("TOR_F_SCALE") or "").strip() or None
        rows.append(row)
    return rows, latest


def storm_subset(path):
    """Severe-weather subset of one yearly file (cached next to it as .severe.json.gz)."""
    sub = path + ".severe.json.gz"
    if os.path.exists(sub):
        with gzip.open(sub, "rt") as f:
            return json.load(f)
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        rows, latest = parse_storm_csv(f)
    out = {"latest": latest.isoformat() if latest else None, "rows": rows}
    with gzip.open(sub + ".part", "wt") as f:
        json.dump(out, f)
    os.replace(sub + ".part", sub)
    return out


def storm_files(index_html):
    """{year: newest file name} from the NCEI csvfiles directory listing."""
    best = {}
    for m in STORM_RE.finditer(index_html):
        y, c = int(m.group(1)), m.group(2)
        if y not in best or c > best[y][0]:
            best[y] = (c, m.group(0))
    return {y: v[1] for y, v in best.items()}


def near(rows, lat, lon, radius_mi, start=None, end=None):
    """Rows within ``radius_mi`` (tornado tracks by their nearest point), with dist_mi and bearing added."""
    out = []
    for r in rows:
        d = r.get("date")
        if start and d < start.isoformat():
            continue
        if end and d > end.isoformat():
            continue
        dist = haversine_mi(lat, lon, r["lat"], r["lon"])
        if r.get("kind") == "tornado" and r.get("lat2") is not None:
            dist = min(dist, _seg_dist_mi(lat, lon, r["lat"], r["lon"], r["lat2"], r["lon2"]))
        if dist <= radius_mi:
            out.append(dict(r, dist_mi=round(dist, 2), bearing=compass(bearing_deg(lat, lon, r["lat"], r["lon"]))))
    return out


def ncei_events(http, years, day, window_start):
    """Final Storm Events rows for the window -> (rows, covered_through, source entries)."""
    srcs = []
    try:
        idx, meta = http.get(STORM_INDEX, kind="text", max_age=86400, ext=".html")
    except SourceUnreachable as e:
        return [], None, [dict(unreachable("NOAA NCEI Storm Events", day, e), name="ncei_storm_events", url=STORM_INDEX)]
    files = storm_files(idx)
    rows, covered = [], None
    for y in years:
        fn = files.get(y)
        if not fn:
            srcs.append({"name": f"ncei_storm_events_{y}", "label": f"NOAA NCEI Storm Events {y}", "status": "empty",
                         "message": f"NOAA NCEI Storm Events: no {y} file published yet (checked {day.isoformat()})"})
            continue
        url = STORM_INDEX + fn
        try:
            path, m = http.get(url, kind="path", ext=".csv.gz", timeout=900)
            sub = storm_subset(path)
        except (SourceUnreachable, OSError, EOFError) as e:
            srcs.append(dict(unreachable(f"NOAA NCEI Storm Events {y}", day, e), name=f"ncei_storm_events_{y}", url=url))
            continue
        rows += [r for r in sub["rows"] if r["date"] >= window_start.isoformat()]
        lt = dt.date.fromisoformat(sub["latest"]) if sub.get("latest") else None
        if lt and (covered is None or lt > covered):
            covered = lt
        srcs.append({"name": f"ncei_storm_events_{y}", "label": f"NOAA NCEI Storm Events {y}", "status": "ok", "url": url,
                     "file": fn, "n": len(sub["rows"]), "covered_through": sub.get("latest"),
                     "queried_at": m.get("fetched_at")})
    return rows, covered, srcs


def parse_iem_lsr(d, tz=None):
    """IEM local storm reports GeoJSON -> rows (hail / wind / tornado; remarks dropped)."""
    out = []
    for f in (d or {}).get("features") or []:
        p = f.get("properties") or {}
        kind = IEM_KIND.get(str(p.get("typetext") or "").strip().upper())
        if not kind:
            continue
        lat, lon = _num(p.get("lat")), _num(p.get("lon"))
        if lat is None or lon is None:
            g = (f.get("geometry") or {}).get("coordinates") or []
            if len(g) >= 2:
                lon, lat = _num(g[0]), _num(g[1])
        if lat is None or lon is None:
            continue
        try:
            t = dt.datetime.fromisoformat(str(p.get("valid")).replace("Z", "+00:00"))
        except ValueError:
            continue
        local = t.astimezone(tz) if tz else t
        mag, unit = _num(p.get("magf") if p.get("magf") is not None else p.get("magnitude")), str(p.get("unit") or "").upper()
        row = {"date": local.date().isoformat(), "time": local.strftime("%H%M"), "valid_utc": t.strftime("%Y-%m-%dT%H:%MZ"),
               "kind": kind, "event_type": str(p.get("typetext")).strip(), "lat": lat, "lon": lon,
               "place": str(p.get("city") or "").strip(), "state": str(p.get("st") or p.get("state") or "").strip(),
               "wfo": str(p.get("wfo") or "").strip(), "reported_by": str(p.get("source") or "").strip(),
               "measured": (str(p.get("qualifier") or "").upper() == "M") if p.get("qualifier") else None}
        if kind == "hail":
            row["size_in"] = mag
        elif kind == "wind":
            row["speed_mph"] = round(kt_to_mph(mag)) if (mag is not None and unit.startswith("K")) else \
                (round(mag) if mag is not None else None)
        out.append(row)
    return out


def parse_spc_csv(text, day, kind, tz=None):
    """SPC daily report CSV (hail: Size in 1/100 in; wind: Speed mph or UNK; Comments dropped). ``day`` is the
    SPC report day (12 UTC to 12 UTC); Time is HHMM UTC."""
    out = []
    rdr = csv.DictReader(io.StringIO(text))
    for r in rdr:
        lat, lon = _num(r.get("Lat")), _num(r.get("Lon"))
        tm = str(r.get("Time") or "").strip()
        if lat is None or lon is None or not tm.isdigit():
            continue
        hh, mm = int(tm.zfill(4)[:2]), int(tm.zfill(4)[2:])
        d0 = day + dt.timedelta(days=1) if hh < 12 else day
        try:
            t = dt.datetime(d0.year, d0.month, d0.day, hh % 24, mm % 60, tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        local = t.astimezone(tz) if tz else t
        row = {"date": local.date().isoformat(), "time": local.strftime("%H%M"), "valid_utc": t.strftime("%Y-%m-%dT%H:%MZ"),
               "lat": lat, "lon": lon, "place": str(r.get("Location") or "").strip(),
               "state": str(r.get("State") or "").strip()}
        if kind == "hail":
            s = _num(r.get("Size"))
            row.update(kind="hail", event_type="HAIL", size_in=round(s / 100.0, 2) if s is not None else None)
        elif kind == "wind":
            s = _num(r.get("Speed"))
            row.update(kind="wind" if s is not None else "wind_damage", event_type="TSTM WND",
                       speed_mph=round(s) if s is not None else None)
        else:
            row.update(kind="tornado", event_type="TORNADO", f_scale=str(r.get("F_Scale") or "").strip() or None)
        out.append(row)
    return out


def _tz(profile):
    name = ((profile or {}).get("hazards") or {}).get("timezone") or (profile or {}).get("timezone")
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - no tz database: UTC dates
        return None


def wfo_list(http, profile, lat, lon):
    w = ((profile or {}).get("hazards") or {}).get("wfo")
    if w:
        return [w] if isinstance(w, str) else list(w)
    try:
        d, _ = http.get(NWS_POINTS.format(lat=lat, lon=lon), max_age=30 * 86400, headers={"Accept": "application/geo+json"})
        cwa = ((d or {}).get("properties") or {}).get("cwa")
        return [cwa] if cwa else []
    except SourceUnreachable:
        return []


def preliminary_events(http, profile, lat, lon, start, end, day, radius_mi=10.0, spc_all_cap=45):
    """IEM LSR for [start, end] (+ SPC daily cross-check on the report days near the house) -> (rows, sources)."""
    tz = _tz(profile)
    srcs, rows = [], []
    wfos = wfo_list(http, profile, lat, lon)
    iem_ok = False
    if not wfos:
        srcs.append({"name": "iem_lsr", "label": "IEM local storm reports", "status": "skipped",
                     "message": "IEM local storm reports: no NWS office (wfo) in the profile and the NWS points API "
                                f"did not answer on {day.isoformat()}"})
    else:
        chunks, s = [], start
        while s <= end:                     # <= 31 days a request; a window that hits the reply cap is split
            e = min(end, s + dt.timedelta(days=30))
            chunks.append((s, e))
            s = e + dt.timedelta(days=1)
        n, errs, capped = 0, [], []
        while chunks:
            s, e = chunks.pop(0)
            params = {"sts": f"{s.isoformat()}T00:00Z", "ets": f"{(e + dt.timedelta(days=1)).isoformat()}T12:00Z",
                      "wfos": ",".join(wfos)}
            try:
                d, m = http.get(IEM_LSR, params, max_age=6 * 3600 if e >= day - dt.timedelta(days=30) else None,
                                timeout=120)
            except SourceUnreachable as ex:
                errs.append(str(ex))
                continue
            nf = len((d or {}).get("features") or [])
            if nf >= IEM_CAP and e > s:
                mid = s + (e - s) // 2
                chunks[:0] = [(s, mid), (mid + dt.timedelta(days=1), e)]
                continue
            if nf >= IEM_CAP:
                capped.append(s.isoformat())
            got = parse_iem_lsr(d, tz)
            n += len(got)
            rows += [r for r in got if start.isoformat() <= r["date"] <= end.isoformat()]
            iem_ok = True
        if iem_ok:
            srcs.append({"name": "iem_lsr", "label": "IEM local storm reports (preliminary)", "status": "ok", "url": IEM_LSR,
                         "wfo": wfos, "n": n, "window": [start.isoformat(), end.isoformat()],
                         **({"note": f"reply cap reached on {', '.join(capped)}: some reports of that day may be missing"}
                            if capped else {})})
        else:
            srcs.append(dict(unreachable("IEM local storm reports", day, "; ".join(errs)), name="iem_lsr", url=IEM_LSR))
    # SPC daily CSVs: the report days of nearby IEM rows, or (IEM down) the most recent days of the gap
    if iem_ok:
        days = sorted({(dt.datetime.fromisoformat(r["valid_utc"].replace("Z", "+00:00")) - dt.timedelta(hours=12)).date()
                       for r in rows if r["kind"] in ("hail", "wind", "wind_damage") and
                       haversine_mi(lat, lon, r["lat"], r["lon"]) <= 25}, reverse=True)[:30]
    else:
        days = [end - dt.timedelta(days=i) for i in range(min(spc_all_cap, (end - start).days + 1))]
    spc_rows, spc_err, spc_n = [], [], 0
    for d0 in days:
        for kind in ("hail", "wind"):
            url = SPC_DAILY.format(day=d0.strftime("%y%m%d"), kind=kind)
            try:
                text, _ = http.get(url, kind="text", ext=".csv",
                                   max_age=86400 if d0 >= day - dt.timedelta(days=10) else None)
            except SourceUnreachable as ex:
                spc_err.append(str(ex))
                continue
            got = parse_spc_csv(text, d0, kind, tz)
            spc_n += len(got)
            spc_rows += got
    if days:
        if spc_err and len(spc_err) >= 2 * len(days):
            srcs.append(dict(unreachable("NOAA SPC storm reports", day, spc_err[0]), name="spc_daily"))
        else:
            srcs.append({"name": "spc_daily", "label": "NOAA SPC storm reports (preliminary)", "status": "ok",
                         "n": spc_n, "days": len(days), "url": SPC_DAILY.split("{")[0]})
    for r in rows:
        r["source"], r["status"] = "IEM local storm reports", "preliminary"
    kept = []
    for r in spc_rows:
        if not (start.isoformat() <= r["date"] <= end.isoformat()):
            continue
        dup = any(x["kind"] == r["kind"] and abs((dt.date.fromisoformat(x["date"]) - dt.date.fromisoformat(r["date"])).days) <= 1
                  and haversine_mi(x["lat"], x["lon"], r["lat"], r["lon"]) <= 1.25 for x in rows)
        if not dup:
            kept.append(dict(r, source="NOAA SPC storm reports", status="preliminary"))
    return rows + kept, srcs


def flag_after_reroof(events, reroof_date):
    """after_reroof = True / False per event (None when no re-roof permit is on record)."""
    rd = reroof_date.isoformat() if hasattr(reroof_date, "isoformat") else reroof_date
    for e in events:
        e["after_reroof"] = (e["date"] > rd) if rd else None
    return events


def summarize(events, reroof_date=None, years=10, hail_big=HAIL_BIG_IN, wind_big=WIND_BIG_MPH, radii=RADII_MI):
    """Counts and maxima within each radius, the big-hail / big-wind lists and the events after the re-roof."""
    s = {"radii_mi": list(radii), "counts": {}, "max_hail": {}, "max_wind": {}, "years": years,
         "hail_big_in": hail_big, "wind_big_mph": wind_big,
         "reroof_date": reroof_date.isoformat() if hasattr(reroof_date, "isoformat") else reroof_date}
    for r in radii:
        ev = [e for e in events if e["dist_mi"] <= r]
        s["counts"][str(r)] = {k: sum(1 for e in ev if e["kind"] == k) for k in ("hail", "wind", "wind_damage", "tornado")}
        h = [e for e in ev if e["kind"] == "hail" and e.get("size_in")]
        w = [e for e in ev if e["kind"] == "wind" and e.get("speed_mph")]
        s["max_hail"][str(r)] = ({"size_in": max(h, key=lambda e: e["size_in"])["size_in"],
                                  "date": max(h, key=lambda e: e["size_in"])["date"]} if h else None)
        s["max_wind"][str(r)] = ({"speed_mph": max(w, key=lambda e: e["speed_mph"])["speed_mph"],
                                  "date": max(w, key=lambda e: e["speed_mph"])["date"]} if w else None)

    def _l(ev):
        return [{"date": e["date"], "kind": e["kind"], "size_in": e.get("size_in"), "speed_mph": e.get("speed_mph"),
                 "dist_mi": e["dist_mi"], "status": e.get("status")} for e in sorted(ev, key=lambda e: e["date"], reverse=True)]
    s["hail_big_1mi"] = _l([e for e in events if e["kind"] == "hail" and (e.get("size_in") or 0) >= hail_big and e["dist_mi"] <= 1])
    s["wind_big_5mi"] = _l([e for e in events if e["kind"] == "wind" and (e.get("speed_mph") or 0) >= wind_big and e["dist_mi"] <= 5])
    s["after_reroof"] = _l([e for e in events if e.get("after_reroof") and e["dist_mi"] <= 5 and (
        (e["kind"] == "hail" and (e.get("size_in") or 0) >= hail_big) or
        (e["kind"] == "wind" and (e.get("speed_mph") or 0) >= wind_big) or e["kind"] == "tornado")])
    return s


def _fmt_events(lst):
    """'2023-06-10 (1.25 in hail), 2022-08-01 (up to 70 mph wind, 3 reports)': one entry per date and type."""
    if not lst:
        return "none"
    groups = {}
    for e in lst:
        groups.setdefault((e["date"], e["kind"]), []).append(e)
    parts = []
    for (d, kind), ev in sorted(groups.items(), key=lambda kv: kv[0][0], reverse=True):
        if kind == "hail":
            v = max((x.get("size_in") or 0) for x in ev)
            what = f"{v:.2f} in hail" if v else "hail"
        elif kind == "wind":
            v = max((x.get("speed_mph") or 0) for x in ev)
            what = f"{v:.0f} mph wind" if v else "wind"
        else:
            what = kind.replace("_", " ")
        if len(ev) > 1:
            what = f"up to {what}, {len(ev)} reports" if kind in ("hail", "wind") else f"{what}, {len(ev)} reports"
        pre = all(x.get("status") == "preliminary" for x in ev)
        parts.append(f"{d} ({what}{', preliminary' if pre else ''})")
    return ", ".join(parts[:12]) + (f" and {len(parts) - 12} more dates" if len(parts) > 12 else "")


def summary_sentence(s):
    hb, wb = s["hail_big_in"], s["wind_big_mph"]
    parts = [f"Hail >= {hb:.2f} in reported within 1 mile: {_fmt_events(s['hail_big_1mi'])}, last {s['years']} years."]
    mh = s["max_hail"].get("5")
    parts.append(f"Largest hail within 5 miles: {mh['size_in']:.2f} in, {mh['date']}." if mh else "No hail reported within 5 miles.")
    parts.append(f"Wind >= {wb} mph within 5 miles: {_fmt_events(s['wind_big_5mi'])}.")
    if s.get("reroof_date"):
        parts.append(f"Events after the last re-roof permit ({s['reroof_date']}): {_fmt_events(s['after_reroof'])}.")
    else:
        parts.append("No re-roof permit on record, so every event listed may have hit the current roof.")
    return " ".join(parts)


def swdi_parse(text):
    """NCEI SWDI nx3hail CSV -> rows {time, wsr, prob, sevprob, maxsize_in, lat, lon}; raises on an error reply."""
    lines = [l for l in text.splitlines()]
    if lines and lines[0].lower().startswith("error"):
        raise SourceUnreachable(lines[0][:200])
    out = []
    rdr = csv.reader(lines)
    head = None
    for row in rdr:
        if not row or (row and row[0].strip().lower() in ("summary", "")):
            if head is not None:
                break
            continue
        if head is None:
            head = [h.strip().upper() for h in row]
            continue
        rec = dict(zip(head, row))
        lat, lon = _num(rec.get("LAT")), _num(rec.get("LON"))
        if lat is None or lon is None:
            continue
        out.append({"time": rec.get("ZTIME"), "wsr": rec.get("WSR_ID"), "prob": _num(rec.get("PROB")),
                    "sevprob": _num(rec.get("SEVPROB")), "maxsize_in": _num(rec.get("MAXSIZE")), "lat": lat, "lon": lon})
    return out


def radar_hail(http, lat, lon, dates, day, radius_mi=3.0, cap=8, box_mi=10.0, radar_site=None):
    """NEXRAD level-3 hail signatures (storm-cell centroids, every ~5 min) on the given report dates: one 48 h
    bbox query each (+/- ``box_mi``); stats within ``radius_mi`` and the nearest signature. Near the radar the
    storm tops are inside its cone of silence, so the detections there are unreliable (said in ``caveat``)."""
    out, srcs, errs = [], [], []
    d_lat = box_mi / 69.0
    d_lon = d_lat / max(0.2, math.cos(math.radians(lat)))
    bbox = f"{lon - d_lon:.4f},{lat - d_lat:.4f},{lon + d_lon:.4f},{lat + d_lat:.4f}"
    for ds in sorted(set(dates), reverse=True)[:cap]:
        d0 = dt.date.fromisoformat(ds)
        url = SWDI_HAIL.format(start=(d0 - dt.timedelta(days=1)).strftime("%Y%m%d"),
                               end=(d0 + dt.timedelta(days=1)).strftime("%Y%m%d"))
        try:
            text, _ = http.get(url, {"bbox": bbox}, kind="text", ext=".csv",
                               max_age=None if d0 < day - dt.timedelta(days=7) else 86400, timeout=120)
            sig = swdi_parse(text)
        except SourceUnreachable as e:
            errs.append(str(e))
            continue
        allp = [dict(s, dist_mi=round(haversine_mi(lat, lon, s["lat"], s["lon"]), 2)) for s in sig]
        near_ = [s for s in allp if s["dist_mi"] <= radius_mi]
        out.append({"date": ds, "n": len(near_),
                    "max_size_in": max((s["maxsize_in"] or 0 for s in near_), default=None) if near_ else None,
                    "max_prob": max((s["prob"] or 0 for s in near_), default=None) if near_ else None,
                    "max_sevprob": max((s["sevprob"] or 0 for s in near_), default=None) if near_ else None,
                    "nearest_mi": min((s["dist_mi"] for s in allp), default=None) if allp else None,
                    "nearest_size_in": min(allp, key=lambda s: s["dist_mi"])["maxsize_in"] if allp else None})
    caveat = "Radar-estimated (NEXRAD hail signatures are storm-cell centroids, not a swath over the house)."
    if radar_site and radar_site.get("lat") is not None:
        dr = haversine_mi(lat, lon, radar_site["lat"], radar_site["lon"])
        if dr <= 20:
            caveat += (f" The house is {dr:.0f} mi from the {radar_site.get('id', '')} radar: storms overhead sit in its "
                       "cone of silence, so missing signatures here do not mean no hail.")
    if dates:
        if errs and not out:
            srcs.append(dict(unreachable("NCEI SWDI NEXRAD hail signatures", day, errs[0]), name="swdi_nx3hail"))
        else:
            srcs.append({"name": "swdi_nx3hail", "label": "NCEI SWDI NEXRAD hail signatures (radar-estimated)",
                         "status": "ok", "dates": len(out), "radius_mi": radius_mi, "box_mi": box_mi,
                         "url": SWDI_HAIL.split("{")[0]})
    return out, srcs, caveat


# ---------------------------------------------------------------------------------------------- flood

FLOOD_DESC = {"A": "1 % annual-chance flood area (no base flood elevation)", "AE": "1 % annual-chance flood area",
              "AH": "1 % annual-chance shallow flooding (ponding)", "AO": "1 % annual-chance shallow flooding (sheet flow)",
              "AR": "1 % annual-chance flood area (levee being restored)", "A99": "1 % annual-chance flood area (levee under construction)",
              "VE": "coastal high-hazard area", "V": "coastal high-hazard area", "D": "possible but undetermined flood hazard",
              "X": "outside the 1 % annual-chance flood area"}


def flood_rank(zone, subtype="", sfha=None):
    z = str(zone or "").upper().strip()
    sub = str(subtype or "").upper()
    if z.startswith("V"):
        return 6.0
    if z.startswith("A") and z != "AREA NOT INCLUDED":
        return 5.5 if "FLOODWAY" in sub else 5.0
    if str(sfha or "").upper() == "T":
        return 5.0
    if "OPEN WATER" in z:
        return 4.0
    if z in ("X", "B", "C", "X500") or z.startswith("X"):
        if z == "B" or "0.2" in sub or "500" in sub or "LEVEE" in sub or "REDUCED" in sub:
            return 3.0
        return 1.0
    if z == "D":
        return 2.0
    if "NOT INCLUDED" in z:
        return 0.0
    return 0.5


def worst_flood_zone(rows):
    """The worst NFHL zone among the rows (attributes dicts) -> {zone, subtype, sfha, static_bfe, dfirm_id,
    description, rank} or None."""
    best = None
    for a in rows or []:
        r = flood_rank(a.get("FLD_ZONE"), a.get("ZONE_SUBTY"), a.get("SFHA_TF"))
        if best is None or r > best[0]:
            best = (r, a)
    if best is None:
        return None
    r, a = best
    z = str(a.get("FLD_ZONE") or "").strip()
    bfe = _num(a.get("STATIC_BFE"))
    sub = str(a.get("ZONE_SUBTY") or "").strip() or None
    desc = FLOOD_DESC.get(z.upper(), z)
    if z.upper() == "X":
        desc = "0.2 % annual-chance flood area (moderate risk)" if r >= 3 else "minimal flood hazard"
    return {"zone": z, "subtype": sub, "sfha": str(a.get("SFHA_TF") or "").upper() == "T",
            "static_bfe_ft": bfe if bfe is not None and bfe > -9000 else None, "dfirm_id": a.get("DFIRM_ID"),
            "description": desc, "rank": r}


def flood(http, profile, parcel_ll, house_ll, point, day):
    lay = (((profile or {}).get("hazards") or {}).get("layers") or {}).get("flood") or {}
    url = lay.get("url") or NFHL_URL
    fields = lay.get("out_fields") or NFHL_FIELDS
    out = {"source": "FEMA National Flood Hazard Layer", "url": url}
    try:
        if parcel_ll is not None:
            rows, meta = arcgis_select(http, url, fields, geometry=esri_polygon(parcel_ll), return_geometry=False,
                                       max_age=30 * 86400, never=lay.get("never") or ())
            out["basis"] = "parcel polygon"
        else:
            rows, meta = arcgis_select(http, url, fields, geometry=f"{point[1]:.7f},{point[0]:.7f}",
                                       geometry_type="esriGeometryPoint", return_geometry=False, max_age=30 * 86400)
            out["basis"] = "address point (no parcel polygon)"
        att = [r["attributes"] for r in rows]
        out.update(status="ok", queried_at=meta.get("fetched_at"), worst=worst_flood_zone(att),
                   zones=sorted({str(a.get("FLD_ZONE")) + (f" ({a.get('ZONE_SUBTY')})" if a.get("ZONE_SUBTY") else "")
                                 for a in att}))
        if house_ll is not None:
            rows2, _ = arcgis_select(http, url, fields, geometry=esri_polygon(house_ll), return_geometry=False,
                                     max_age=30 * 86400)
            out["at_house"] = worst_flood_zone([r["attributes"] for r in rows2])
        if not att:
            out["note"] = "no NFHL polygon at this parcel (the county may have no digital flood map)"
    except SourceUnreachable as e:
        out.update(unreachable("FEMA NFHL flood zones", day, e))
    return out


# ---------------------------------------------------------------------------------------------- roof facts

def _roof_polys(facets):
    from shapely.geometry import Polygon
    out = []
    for f in facets or []:
        for q in f.get("polygons") or []:
            outer = [(c[0], c[1]) for c in q.get("outer") or []]
            if len(outer) < 3:
                continue
            p = Polygon(outer, [[(c[0], c[1]) for c in h] for h in q.get("holes") or [] if len(h) >= 3])
            if not p.is_valid:
                p = p.buffer(0)
            if p.area > 0:
                out.append((p, f.get("plane"), f))
    return out


def tree_overhang(facets, points, edges=None, cell=1.0, min_dz=0.5, max_dz=40.0, min_patch_m2=2.0, edge_reach=1.5):
    """Share of the roof plan under canopy: LiDAR returns >= ``min_dz`` above the fitted roof surface.

    ``facets``: model.json facets (polygons with 3-D rings, ``plane`` z = a x + b y + c, model frame).
    ``points``: N x 3+ array (x, y, z in the model frame). Cells of ``cell`` m with any canopy return, minus
    patches smaller than ``min_patch_m2`` (chimneys, vents, antennas), clipped to the roof outline.
    Returns {pct, canopy_m2, roof_plan_m2, n_points, edges: [{kind, facade, length_m, covered_m, pct}]}."""
    import numpy as np
    import shapely
    from scipy import ndimage
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    polys = _roof_polys(facets)
    if not polys:
        return None
    roof = unary_union([p for p, _, _ in polys])
    pts = np.asarray(points, float)
    px, py, pz = pts[:, 0], pts[:, 1], pts[:, 2]
    zr = np.full(len(pts), -np.inf)
    for p, pl, _ in polys:
        m = shapely.contains_xy(p, px, py)
        if m.any():
            zr[m] = np.maximum(zr[m], pl[0] * px[m] + pl[1] * py[m] + pl[2])
    on = np.isfinite(zr)
    dz = np.where(on, pz - zr, -np.inf)
    can = on & (dz >= min_dz) & (dz <= max_dz)
    x0, y0, x1, y1 = roof.bounds
    nx, ny = max(1, int(math.ceil((x1 - x0) / cell))), max(1, int(math.ceil((y1 - y0) / cell)))
    occ = np.zeros((nx, ny), bool)
    if can.any():
        i = np.clip(((px[can] - x0) / cell).astype(int), 0, nx - 1)
        j = np.clip(((py[can] - y0) / cell).astype(int), 0, ny - 1)
        occ[i, j] = True
    lab, n = ndimage.label(occ, np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(occ, lab, range(1, n + 1)) * cell * cell
        for k, sz in enumerate(sizes, 1):
            if sz < min_patch_m2:
                occ[lab == k] = False
    ii, jj = np.nonzero(occ)
    canopy = unary_union([box(x0 + a * cell, y0 + b * cell, x0 + (a + 1) * cell, y0 + (b + 1) * cell)
                          for a, b in zip(ii, jj)]).intersection(roof) if len(ii) else None
    area = canopy.area if canopy is not None else 0.0
    out = {"pct": round(100.0 * area / roof.area, 1), "canopy_m2": round(area, 1), "roof_plan_m2": round(roof.area, 1),
           "n_points": int(can.sum()), "cell_m": cell, "min_dz_m": min_dz, "edges": []}
    c = roof.centroid
    for e in edges or []:
        if e.get("kind") not in ("eave", "rake"):
            continue
        a_, b_ = e["p0"][:2], e["p1"][:2]
        L = math.dist(a_, b_)
        if L < 0.3 or canopy is None:
            continue
        line = LineString([a_, b_])
        ns = max(2, int(L / 0.5) + 1)
        hit = sum(1 for k in range(ns) if canopy.distance(line.interpolate(k / (ns - 1), normalized=True)) <= edge_reach)
        cov = L * hit / ns
        if hit:
            mid = line.interpolate(0.5, normalized=True)
            b = (math.degrees(math.atan2(mid.x - c.x, mid.y - c.y)) + 360) % 360
            out["edges"].append({"kind": e["kind"], "facade": compass(b), "length_m": round(L, 2),
                                 "covered_m": round(cov, 2), "pct": round(100.0 * hit / ns)})
    out["edges"].sort(key=lambda r: -r["covered_m"])
    return out


def pitch_class(p12):
    for name, hi in PITCH_CLASSES:
        if p12 <= hi:
            return name
    return PITCH_CLASSES[-1][0]


def roof_access(facets, edges, ground=None, storeys=None):
    """Per-facet steepness classes (by true area), highest / lowest eave and highest ridge above grade."""
    rows, tot = [], 0.0
    by = {n: 0.0 for n, _ in PITCH_CLASSES}
    for f in facets or []:
        p = float(f.get("pitch_rise_per_12") or 0.0)
        a = float(f.get("area_m2") or 0.0)
        if f.get("hidden_from_above"):
            continue
        cls = pitch_class(round(p, 1))
        by[cls] += a
        tot += a
        rows.append({"id": f.get("id"), "pitch": round(p, 1), "class": cls, "area_sqft": round(a * 10.7639),
                     "facing": compass(f.get("azimuth"))})

    def grade_at(x, y):
        if ground is None:
            return 0.0
        Z, gx0, gy0, cell = ground
        i = int(round((x - gx0) / cell))
        j = int(round((y - gy0) / cell))
        import numpy as np
        if 0 <= i < Z.shape[0] and 0 <= j < Z.shape[1] and np.isfinite(Z[i, j]):
            return float(Z[i, j])
        return 0.0
    eaves, ridges = [], []
    for e in edges or []:
        for q in (e["p0"], e["p1"]):
            h = q[2] - grade_at(q[0], q[1])
            (eaves if e.get("kind") == "eave" else ridges if e.get("kind") in ("ridge", "hip") else []).append(h)
    out = {"facets": rows, "share_pct": {k: round(100.0 * v / tot, 1) if tot else 0.0 for k, v in by.items()},
           "rule": "walkable <= 6/12, steep 7-9/12, very steep > 9/12",
           "highest_eave_m": round(max(eaves), 2) if eaves else None, "lowest_eave_m": round(min(eaves), 2) if eaves else None,
           "highest_ridge_m": round(max(ridges), 2) if ridges else None,
           "grade_basis": "LiDAR ground surface" if ground is not None else "ground at the site origin",
           "storeys": storeys}
    if eaves:
        out["highest_eave_ft"] = round(max(eaves) / 0.3048, 1)
    if ridges:
        out["highest_ridge_ft"] = round(max(ridges) / 0.3048, 1)
    return out


def colour_name(rgb):
    import colorsys
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h *= 360
    if v < 0.16:
        return "black"
    if s < 0.14:
        return "charcoal" if v < 0.32 else "dark grey" if v < 0.5 else "grey" if v < 0.7 else "light grey" if v < 0.86 else "white"
    if h < 18 or h >= 340:
        return "dark red" if v < 0.45 else "red"
    if h < 48:
        return "brown" if v < 0.55 else "tan"
    if h < 70:
        return "olive" if v < 0.5 else "beige"
    if h < 170:
        return "dark green" if v < 0.45 else "green"
    if h < 260:
        return "slate blue" if s < 0.35 else "blue"
    return "purple"


def roof_colour(ortho_png, meta, facets, inset_m=0.5):
    """Median sRGB of the ortho pixels inside each facet (inset to stay off the edges; the aerial leans)."""
    import numpy as np
    import shapely
    from PIL import Image
    polys = _roof_polys(facets)
    if not polys:
        return None
    img = np.asarray(Image.open(ortho_png).convert("RGB"))
    H, W = img.shape[:2]
    bx0, by0, bx1, by1 = meta["bounds_local"]
    mpp = (bx1 - bx0) / W
    cx = bx0 + (np.arange(W) + 0.5) * mpp
    cy = by1 - (np.arange(H) + 0.5) * ((by1 - by0) / H)
    X, Y = np.meshgrid(cx, cy)
    per, allpx = [], []
    for p, _, f in polys:
        q = p.buffer(-inset_m)
        if q.is_empty or q.area < 0.5:
            q = p
        m = shapely.contains_xy(q, X, Y)
        if m.sum() < 4:
            continue
        px = img[m]
        allpx.append(px)
        med = [int(v) for v in np.median(px, axis=0)]
        per.append({"facet": f.get("id"), "rgb": med, "hex": "#%02x%02x%02x" % tuple(med), "n_px": int(m.sum())})
    if not allpx:
        return None
    med = [int(v) for v in np.median(np.concatenate(allpx), axis=0)]
    return {"rgb": med, "hex": "#%02x%02x%02x" % tuple(med), "name": colour_name(med), "per_facet": per,
            "n_px": int(sum(len(a) for a in allpx))}


# ---------------------------------------------------------------------------------------------- neighbourhood

def reroof_counts(http, profile, lat, lon, day, radius_m=300, years=5):
    """Re-roof permits within ``radius_m`` per year (counts only; no address, number or location is kept)."""
    lst = regions.layers_by_role(profile or {}, "permits")
    if not lst:
        return {"status": "not_configured", "message": "neighbourhood re-roof permits: no permit layer in the profile"}
    name, lay = lst[0]
    of = lay.get("out_fields") or []
    date_f = ((lay.get("map") or {}).get("issue_date")) or next((f for f in of if f.upper() in ("ISSUEDATE", "DATEAPPROVED")), None)
    where = lay.get("reroof_where")
    if not where or not date_f:
        return {"status": "not_configured", "message": "neighbourhood re-roof permits: the permit layer has no "
                                                       "'reroof_where' / issue-date field in the profile"}
    fields = [f for f in ("OBJECTID",) if f in of] + [date_f]
    label = f"{lay.get('label') or name} (re-roof permits within {radius_m} m)"
    try:
        try:
            rows, meta = arcgis_select(http, lay["url"], fields, where=where, geometry=f"{lon:.7f},{lat:.7f}",
                                       geometry_type="esriGeometryPoint", distance=radius_m, return_geometry=False,
                                       max_age=7 * 86400, max_records=20000)
        except SourceUnreachable:
            d = radius_m / 111320.0
            dl = d / math.cos(math.radians(lat))
            rows, meta = arcgis_select(http, lay["url"], fields, where=where,
                                       geometry=f"{lon - dl:.7f},{lat - d:.7f},{lon + dl:.7f},{lat + d:.7f}",
                                       geometry_type="esriGeometryEnvelope", max_age=7 * 86400, max_records=20000)
            rows = [r for r in rows if r.get("geometry") and r["geometry"].get("type") == "Point" and
                    haversine_mi(lat, lon, r["geometry"]["coordinates"][1], r["geometry"]["coordinates"][0]) * M_PER_MI <= radius_m]
    except SourceUnreachable as e:
        return dict(unreachable(label, day, e), radius_m=radius_m)
    from .records import to_date
    by = {}
    for r in rows:
        d = to_date((r.get("attributes") or {}).get(date_f))
        if d:
            by[d.year] = by.get(d.year, 0) + 1
    y0 = day.year - years
    return {"status": "ok", "label": label, "radius_m": radius_m, "where": where, "queried_at": meta.get("fetched_at"),
            "by_year": {str(y): by.get(y, 0) for y in range(y0, day.year + 1)}, "total_all_years": sum(by.values()),
            "note": "counts only (this property's own permits included); no neighbour address is requested or kept"}


# ---------------------------------------------------------------------------------------------- later stubs

def later(profile):
    out = {
        "mesh": {"status": "not included", "text": "MRMS MESH hail-size swaths: not included (needs a GRIB2 reader "
                 "that is not installed; the IEM archive has 2020 and 2024 files, not 2016). Radar-estimated hail on "
                 "the reported dates is shown instead."},
        "roof_material": {"status": "not included", "text": "Roof material: not publicly recorded by the city or the "
                          "county, so it is not stated. The roof colour estimate and the re-roof permit are shown instead."},
    }
    cn = ((profile or {}).get("hazards") or {}).get("code_notes")
    if cn:
        notes = cn if isinstance(cn, list) else [cn]
        out["code"] = {"status": "ok", "notes": [{k: n.get(k) for k in ("text", "source_url", "read_date", "edition",
                                                                         "ice_barrier", "ground_snow_psf", "wind_mph")
                                                  if n.get(k) is not None} for n in notes]}
    else:
        out["code"] = {"status": "not included", "text": "Building-code edition, ice-barrier rule and snow / wind design "
                       "values: not included (no verified free public source is recorded in the region profile)."}
    return out


# ---------------------------------------------------------------------------------------------- the stage

def _load(job, rel):
    p = os.path.join(job, rel)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def site_point(job):
    """(lat, lon, basis): parcel centroid from records.json, else the geocoded point."""
    rec = _load(job, "data/records.json") or {}
    ring = ((rec.get("parcel") or {}).get("ring_lonlat"))
    if ring and len(ring) >= 3:
        from shapely.geometry import Polygon
        c = Polygon(ring).centroid
        return c.y, c.x, "parcel centre"
    site = _load(job, "site.json") or {}
    g = site.get("geocode") or site.get("origin") or {}
    if g.get("lat") is None:
        raise SystemExit("hazards: no site.json geocode (run init first)")
    return float(g["lat"]), float(g["lon"]), "address point"


def _parcel_and_house(job):
    from shapely.geometry import Polygon
    rec = _load(job, "data/records.json") or {}
    ring = (rec.get("parcel") or {}).get("ring_lonlat")
    parcel = Polygon(ring) if ring and len(ring) >= 3 else None
    house = None
    fps = (_load(job, "data/footprints.json") or {}).get("chosen") or {}
    site = _load(job, "site.json") or {}
    if fps and site.get("origin"):
        from .geo import LocalFrame
        fr = LocalFrame.from_dict(site["origin"])
        ring = next(iter(fps.values())).get("ring")
        if ring and len(ring) >= 3:
            house = Polygon(fr.ring_to_lonlat(ring))
    return parcel, house


def reports(http, profile, lat, lon, years, day, reroof_date, radius_mi=10.0):
    start = dt.date(day.year - years, day.month, min(day.day, 28))
    rows, covered, srcs = ncei_events(http, list(range(start.year, day.year + 1)), day, start)
    for r in rows:
        r["source"], r["status"] = "NOAA NCEI Storm Events", "final"
    events = near(rows, lat, lon, radius_mi, start, covered)
    gap_start = (covered + dt.timedelta(days=1)) if covered else start
    prelim, s2 = ([], [])
    if gap_start <= day:
        prelim, s2 = preliminary_events(http, profile, lat, lon, gap_start, day, day, radius_mi)
    srcs += s2
    events += near(prelim, lat, lon, radius_mi, gap_start, day)
    events.sort(key=lambda e: (e["date"], e.get("time") or ""), reverse=True)
    flag_after_reroof(events, reroof_date)
    hz = (profile or {}).get("hazards") or {}
    summ = summarize(events, reroof_date, years, hz.get("hail_big_in", HAIL_BIG_IN), hz.get("wind_big_mph", WIND_BIG_MPH))
    hail_dates = sorted({e["date"] for e in events if e["kind"] == "hail" and e["dist_mi"] <= 5})
    radar, s3, radar_caveat = radar_hail(http, lat, lon, hail_dates, day, radar_site=hz.get("radar_site"))
    srcs += s3
    for e in events:
        for k in ("lat", "lon", "lat2", "lon2"):
            e.pop(k, None)            # no coordinates kept: distance and bearing from the house say it
    return {"window": [start.isoformat(), day.isoformat()], "final_through": covered.isoformat() if covered else None,
            "radius_mi": radius_mi, "events": events, "summary": summ, "sentence": summary_sentence(summ),
            "radar_hail": radar, "radar_caveat": radar_caveat, "sources": srcs,
            "caveat": "Storm reports are spotter / official reports at points, not measurements at the house; distances "
                      "are from the parcel centre. Reports after the NCEI publication date are preliminary."}


def roof_part(job, profile, records=None):
    import numpy as np
    model = _load(job, "model.json")
    if not model:
        return {"status": "pending", "message": "roof facts need the fitted model: run `hazards.py JOB --only roof` "
                                                "after the fit"}
    out = {"status": "ok"}
    site = _load(job, "site.json") or {}
    li = _load(job, "data/lidar.json") or {}
    ground = None
    gp = os.path.join(job, "data", "ground_surface.npz")
    if os.path.exists(gp):
        g = np.load(gp)
        ground = (g["Z"], float(g["x0"]), float(g["y0"]), float(g["cell"]))
    storeys = ((records or {}).get("derived") or {}).get("storeys")
    out["access"] = roof_access(model.get("facets"), model.get("edges"), ground, storeys)
    pp = os.path.join(job, "data", "lidar_points.npy")
    if os.path.exists(pp) and site.get("datum_m") is not None:
        pts = np.load(pp)
        xyz = np.column_stack([pts[:, 0], pts[:, 1], pts[:, 2] - float(site["datum_m"])])
        if pts.shape[1] >= 4:
            xyz = xyz[~np.isin(pts[:, 3], [7, 18])]          # noise classes
        ov = tree_overhang(model.get("facets"), xyz, model.get("edges"))
        if ov is not None:
            fd = li.get("flight_date")
            leaf = " (leaf-on)" if li.get("leaf_on") else " (leaf-off)" if li.get("leaf_on") is False else \
                " (leaf state unknown)"
            ov["caveat"] = (f"LiDAR flown {fd or li.get('year') or '?'}{leaf}; "
                            "the 3DEP data has no vegetation class, so canopy = any return >= 0.5 m above the fitted roof "
                            "(patches under 2 m2, e.g. chimneys and vents, ignored). A leaf-off flight under-counts deciduous trees.")
        out["tree_overhang"] = ov
    else:
        out["tree_overhang"] = {"status": "pending", "message": "no LiDAR points / datum (run pm.py lidar)"}
    op = os.path.join(job, "data", "ortho.png")
    if os.path.exists(op) and os.path.exists(op + ".json"):
        with open(op + ".json") as f:
            meta = json.load(f)
        try:
            rc = roof_colour(op, meta, model.get("facets"))
        except Exception as e:  # noqa: BLE001 - presentation estimate only
            rc = None
            out["colour_error"] = str(e)[:200]
        if rc:
            ortho = regions.layer(profile or {}, "ortho") or {}
            when = ortho.get("date")
            rc["label"] = (f"estimate from the aerial ({meta.get('attribution') or meta.get('provider') or 'orthophoto'}"
                           f"{', ' + when if when else ''}); not a material or colour survey")
            out["colour"] = rc
    return out


def write_outputs(job, hz):
    paths = {"data": os.path.join(job, "data", "hazards.json"),
             "section": os.path.join(job, "out", "sections", "50_hazards.md"),
             "detail": os.path.join(job, "out", "detail_extra", "hazards.json")}
    for p in paths.values():
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(paths["data"] + ".part", "w") as f:
        json.dump(hz, f, indent=1, default=str)
    os.replace(paths["data"] + ".part", paths["data"])
    with open(paths["section"], "w") as f:
        f.write(section_md(hz))
    with open(paths["detail"], "w") as f:
        json.dump(detail_json(hz), f, indent=1, default=str)
    hits = []
    for p in paths.values():
        hits += privacy.scan(p)
    if hits:
        for p in paths.values():
            os.remove(p)
        raise RuntimeError("privacy scan: " + "; ".join(f"{h['file']}: {h['key']}" for h in hits[:10]))
    return paths


def run(job, profile_ref=None, http=None, parts=None, years=10, today=None):
    """Compute the requested parts and merge them into JOB/data/hazards.json (other parts kept)."""
    global TODAY
    day = today or today_utc()
    TODAY = day
    http = http or Http()
    profile = regions.load(profile_ref) if profile_ref else {}
    parts = set(parts or ("reports", "flood", "permits", "roof"))
    hz = _load(job, "data/hazards.json") or {}
    rec = _load(job, "data/records.json") or {}
    lat, lon, basis = site_point(job)
    reroof = ((rec.get("derived") or {}).get("last_reroof") or {}).get("date")
    hz.update(profile=(profile or {}).get("name"), point_basis=basis, later=later(profile))
    hz.setdefault("parts", {})
    def part(name, fn):
        """No hazard result stops a run: an unexpected failure is written as such, not raised."""
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            hz.setdefault("errors", {})[name] = {"status": "error", "message": f"{name}: failed on {day.isoformat()} "
                                                 f"({type(e).__name__}: {str(e)[:200]})"}
        else:
            (hz.get("errors") or {}).pop(name, None)
        hz["parts"][name] = now_iso()

    def _reports():
        hz["storms"] = reports(http, profile, lat, lon, years, day, reroof,
                               ((profile or {}).get("hazards") or {}).get("storm_radius_mi", 10.0))

    def _flood():
        parcel, house = _parcel_and_house(job)
        hz["flood"] = flood(http, profile, parcel, house, (lat, lon), day)

    def _permits():
        hz["neighbourhood"] = reroof_counts(http, profile, lat, lon, day)

    def _roof():
        r = roof_part(job, profile, rec)
        hz["roof"] = r
        if r.get("colour"):
            hz["roof_colour"] = {k: r["colour"][k] for k in ("rgb", "hex", "name", "label")}
    for name, fn in (("reports", _reports), ("flood", _flood), ("permits", _permits), ("roof", _roof)):
        if name in parts:
            part(name, fn)
    hz["queried_at"] = now_iso()
    return hz, write_outputs(job, hz)


# ---------------------------------------------------------------------------------------------- report text

def _ev_mag(e):
    if e["kind"] == "hail":
        return f"{e['size_in']:.2f} in hail" if e.get("size_in") else "hail"
    if e["kind"] == "wind":
        return f"{e['speed_mph']} mph gust{' (measured)' if e.get('measured') else ''}" if e.get("speed_mph") else "wind"
    if e["kind"] == "wind_damage":
        return "wind damage"
    return f"tornado {e.get('f_scale') or ''}".strip()


def section_md(hz):
    L = ["## Hail, wind and flood", ""]
    st = hz.get("storms")
    if st:
        L += [st["sentence"], "", st["caveat"] + (f" NCEI Storm Events are final through {st['final_through']}." if
                                                  st.get("final_through") else ""), ""]
        ev = st.get("events") or []
        sm = st.get("summary") or {}
        show = significant(ev, sm.get("hail_big_in", HAIL_BIG_IN), sm.get("wind_big_mph", WIND_BIG_MPH))
        if show:
            L += [f"### Significant reports: every report within 1 mile; hail >= {sm.get('hail_big_in', HAIL_BIG_IN):.2f} in, "
                  f"wind >= {sm.get('wind_big_mph', WIND_BIG_MPH)} mph and tornadoes within 5 miles", "",
                  "| Date | Event | Distance | Source | After last re-roof |", "|---|---|---|---|---|"]
            for e in show:
                ar = "yes" if e.get("after_reroof") else "no" if e.get("after_reroof") is False else "-"
                L.append(f"| {e['date']} | {_ev_mag(e)} | {e['dist_mi']:.1f} mi {e.get('bearing') or ''} | "
                         f"{e.get('source')}{' (preliminary)' if e.get('status') == 'preliminary' else ''} | {ar} |")
            if len(ev) > len(show):
                L.append(f"\n{len(ev) - len(show)} more report(s) within {st['radius_mi']:g} miles (smaller hail, weaker "
                         "wind or farther away) are counted below and listed in hazards.json.")
        c = st["summary"]["counts"]
        L += ["", "| Within | Hail | Wind | Tornado |", "|---|---|---|---|"]
        for r in st["summary"]["radii_mi"]:
            k = c[str(r)]
            L.append(f"| {r} mi | {k['hail']} | {k['wind'] + k['wind_damage']} | {k['tornado']} |")
        rh = st.get("radar_hail") or []
        if rh:
            L += ["", "### Radar-indicated hail on the reported dates (NEXRAD, radar-estimated)", "",
                  "| Report date | Signatures within 3 mi | Max estimated size | Probability | Nearest signature |",
                  "|---|---|---|---|---|"]
            for r in rh:
                if r.get("n"):
                    L.append(f"| {r['date']} | {r['n']} | {r['max_size_in']:.2f} in | {r['max_prob']:.0f} % (severe "
                             f"{r['max_sevprob']:.0f} %) | {r['nearest_mi']:.1f} mi |")
                else:
                    near_ = "none within 10 mi" if r.get("nearest_mi") is None else f"{r['nearest_mi']:.1f} mi" + \
                        (f" ({r['nearest_size_in']:.2f} in)" if r.get("nearest_size_in") is not None else "")
                    L.append(f"| {r['date']} | 0 | - | - | {near_} |")
            L += ["", st.get("radar_caveat") or ""]
        for s in st.get("sources") or []:
            if s.get("status") not in ("ok",):
                L.append(f"\n{s.get('message')}")
    fl = hz.get("flood")
    if fl:
        L += ["", "### Flood zone (FEMA)", ""]
        if fl.get("status") == "ok":
            w = fl.get("worst")
            if w:
                L.append(f"Worst zone touching the parcel: **Zone {w['zone']}** ({w['description']})"
                         f"{'; in a Special Flood Hazard Area: lenders with federally backed mortgages require flood insurance' if w['sfha'] else ''}"
                         f"{'; base flood elevation ' + format(w['static_bfe_ft'], '.1f') + ' ft' if w.get('static_bfe_ft') else ''}."
                         f" FIRM panel set {w.get('dfirm_id') or '-'}.")
                ah = fl.get("at_house")
                if ah and ah.get("zone") != w["zone"]:
                    L.append(f"At the house itself: Zone {ah['zone']} ({ah['description']}).")
            else:
                L.append(fl.get("note") or "No flood zone returned.")
        else:
            L.append(fl.get("message"))
    rf = hz.get("roof") or {}
    if rf.get("status") == "ok":
        a = rf.get("access") or {}
        sh = a.get("share_pct") or {}
        L += ["", "### Roof access", "",
              f"By roof area: walkable {sh.get('walkable', 0):.0f} %, steep {sh.get('steep', 0):.0f} %, very steep "
              f"{sh.get('very steep', 0):.0f} % ({a.get('rule')})."]
        if a.get("highest_eave_m") is not None:
            L.append(f"Highest eave {a['highest_eave_m']:.1f} m ({a['highest_eave_ft']:.0f} ft) above grade, lowest "
                     f"{a['lowest_eave_m']:.1f} m; highest ridge {a.get('highest_ridge_m') or 0:.1f} m "
                     f"({a.get('grade_basis')}).{' Storeys on record: ' + format(a['storeys'], 'g') + '.' if a.get('storeys') else ''}")
        ov = rf.get("tree_overhang") or {}
        if ov.get("pct") is not None:
            L += ["", "### Tree overhang", "",
                  f"{ov['pct']:.0f} % of the roof plan ({ov['canopy_m2'] * 10.7639:,.0f} sq ft) has LiDAR returns at least "
                  f"0.5 m above the roof surface."]
            if ov.get("edges"):
                L.append("Edges with canopy within 1.5 m: " + ", ".join(
                    f"{e['facade']} {e['kind']} ({e['pct']} % of {e['length_m'] / 0.3048:.0f} ft)" for e in ov["edges"][:8]) + ".")
            L.append(ov.get("caveat") or "")
        col = rf.get("colour")
        if col:
            L += ["", "### Roof colour (estimate)", "", f"{col['name']} ({col['hex']}), {col['label']}."]
    elif rf.get("message"):
        L += ["", "### Roof access and tree overhang", "", rf["message"]]
    nb = hz.get("neighbourhood") or {}
    if nb.get("status") == "ok":
        L += ["", f"### Re-roof permits within {nb['radius_m']} m", "",
              "| Year | " + " | ".join(nb["by_year"].keys()) + " |", "|---|" + "---|" * len(nb["by_year"]),
              "| Permits | " + " | ".join(str(v) for v in nb["by_year"].values()) + " |", "", nb.get("note") or ""]
    elif nb.get("message"):
        L += ["", nb["message"]]
    for name, err in (hz.get("errors") or {}).items():
        L += ["", err.get("message", f"{name}: failed")]
    lt = hz.get("later") or {}
    L += ["", "### Not included", ""]
    for k in ("mesh", "roof_material", "code"):
        v = lt.get(k) or {}
        if v.get("status") == "ok":
            for n in v.get("notes") or []:
                L.append(f"- {n.get('text') or ''} (source {n.get('source_url')}, read {n.get('read_date')})")
        elif v.get("text"):
            L.append(f"- {v['text']}")
    return "\n".join(L) + "\n"


def significant(ev, hail_big=HAIL_BIG_IN, wind_big=WIND_BIG_MPH, cap=40):
    """Every report within 1 mile; within 5 miles big hail, damaging wind and tornadoes (newest first)."""
    out = [e for e in ev if e["dist_mi"] <= 1 or (e["dist_mi"] <= 5 and (
        (e["kind"] == "hail" and (e.get("size_in") or 0) >= hail_big) or
        (e["kind"] == "wind" and (e.get("speed_mph") or 0) >= wind_big) or e["kind"] in ("tornado", "wind_damage")))]
    return out[:cap]


def detail_json(hz):
    st = hz.get("storms") or {}
    sm = st.get("summary") or {}
    ev = [{k: e.get(k) for k in ("date", "kind", "size_in", "speed_mph", "f_scale", "dist_mi", "bearing", "source",
                                 "status", "after_reroof")}
          for e in significant(st.get("events") or [], sm.get("hail_big_in", HAIL_BIG_IN), sm.get("wind_big_mph", WIND_BIG_MPH))]
    rf = hz.get("roof") or {}
    return {"label": "Hail, wind and flood", "queried_at": hz.get("queried_at"), "sentence": st.get("sentence"),
            "summary": st.get("summary"), "significant_events": ev, "final_through": st.get("final_through"),
            "radar_hail": [r for r in st.get("radar_hail") or [] if r.get("n")], "radar_caveat": st.get("radar_caveat"),
            "flood": {k: (hz.get("flood") or {}).get(k) for k in ("status", "worst", "at_house", "zones", "message")},
            "roof_access": (rf.get("access") or {}).get("share_pct"),
            "highest_eave_ft": (rf.get("access") or {}).get("highest_eave_ft"),
            "tree_overhang": {k: (rf.get("tree_overhang") or {}).get(k) for k in ("pct", "canopy_m2", "edges", "caveat")},
            "roof_colour": hz.get("roof_colour"), "neighbourhood": hz.get("neighbourhood"),
            "not_included": {k: v.get("text") for k, v in (hz.get("later") or {}).items() if v.get("text")},
            "sources": [{k: s.get(k) for k in ("label", "status", "message")} for s in st.get("sources") or []]}
