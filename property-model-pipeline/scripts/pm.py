#!/usr/bin/env python3
"""pm — property model pipeline CLI.

    pm.py init PROJECT --address "123 Main St, Town, ST"    (or --latlon 42.03,-93.62)
    pm.py fetch PROJECT                 footprints (OSM + Microsoft), orthophoto, DEM, parcel
    pm.py lidar PROJECT                 USGS 3DEP point cloud -> ground, roof planes, observations
    pm.py suggest PROJECT               starting spec.json (one wing) from LiDAR + footprint
    pm.py obs PROJECT add --target roof.area --value "24.5 sq" --sigma 2% --source "EagleView 2019"
    pm.py obs PROJECT import past.csv   (columns: target,value,sigma,source,kind,date)
    pm.py obs PROJECT import-geo geo_obs.json   (roof_z_wgs84 / outline_wgs84 / z@_wgs84 in lon,lat + absolute m)
    pm.py obs PROJECT list
    pm.py fit PROJECT                   fuse everything -> fit.json, model.json, report.md, overview.png
    pm.py build PROJECT                 geometry + report from spec.json without fitting
    pm.py plot PROJECT                  overview.png only
    pm.py photo-info IMAGE...           EXIF / drone metadata, focal length in px, GSD
    pm.py photo-measure --points pts.json   plane rectification measurement (see references/photo-measurement.md)
    pm.py camera-match PROJECT --image IMG --pairs pairs.json   resect camera, save to cameras.json
    pm.py align --pairs pairs.json      similarity transform (scale+rot+trans) for photogrammetry / AI meshes
    pm.py blender PROJECT [--blender /path/to/blender] [--glb] [--render]
    pm.py obs PROJECT import-multipatch [FILE.json] [--profile NAME | --layer URL --fields F1,F2]   city LOD2 roof
    pm.py resid PROJECT                 per-plane LiDAR residuals of the fitted model -> data/resid.json, resid.png
    pm.py edges PROJECT [--write-obs]   measured drip edges (outermost on-plane returns) -> data/edges.json
    pm.py fit PROJECT --accept --sigma-free pitches,eave_heights [--use-edges]
    pm.py features PROJECT --profile NAME   city paving / sidewalks / parcels / hydrants -> features.json

Every ArcGIS query names its fields (``outFields=*`` is refused). PROPMODEL_OFFLINE=1 = cache-only run:
nothing goes to the network and a cache miss fails fast.

All internal values are metres in a local East-North-Up frame (see propmodel/geo.py).
"""
import argparse
import csv
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

from propmodel import units as U  # noqa: E402
from propmodel.geo import LocalFrame  # noqa: E402

CACHE = os.environ.get("PROPMODEL_CACHE", os.path.expanduser("~/.cache/propmodel"))

# Default 1-sigma for automatically generated observations (see references/accuracy-budget.md)
SIGMA = {
    "osm_outline": 0.6, "ms_outline": 0.7, "lidar_z": 0.12, "lidar_outline_extra": 0.15,
}


# ---------------------------------------------------------------------------
# project helpers
# ---------------------------------------------------------------------------

def P(project, *parts):
    return os.path.join(project, *parts)


def load(project, name, default=None):
    path = P(project, name)
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save(project, name, obj):
    path = P(project, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return path


def frame_of(project):
    return LocalFrame.from_dict(load(project, "site.json")["origin"])


def model_datum(project):
    """Absolute elevation (m) of model z = 0: ground at the site origin."""
    site = load(project, "site.json", {})
    if site.get("datum_m") is not None:
        return float(site["datum_m"])
    li = load(project, "data/lidar.json")
    if li:
        return float(li["ground_plane"][2])
    if site.get("ground_elevation_dem") is not None:
        return float(site["ground_elevation_dem"])
    raise SystemExit("no datum: run `pm.py lidar` first (or set site.json datum_m)")


def set_auto_obs(project, source_prefix, new_obs):
    """Replace auto-generated observations whose source starts with ``source_prefix``."""
    obs = load(project, "observations.json", [])
    obs = [o for o in obs if not str(o.get("source", "")).startswith(source_prefix)]
    obs.extend(new_obs)
    save(project, "observations.json", obs)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_init(a):
    from propmodel import sources
    os.makedirs(a.project, exist_ok=True)
    site = load(a.project, "site.json", {})
    if a.latlon:
        lat, lon = map(float, a.latlon.split(","))
        geo = {"lat": lat, "lon": lon, "source": "user"}
    else:
        geo = sources.geocode(a.address, CACHE)
    site.update({"address": a.address or geo.get("matched", ""), "geocode": geo,
                 "origin": {"lat": geo["lat"], "lon": geo["lon"], "h": 0.0},
                 "parcel_url": a.parcel_url or site.get("parcel_url")})
    if a.parcel_fields:
        site["parcel_fields"] = _field_list(a.parcel_fields)
    if site.get("parcel_url") and not site.get("parcel_fields"):
        sys.exit("--parcel-url needs --parcel-fields F1,F2,... (explicit fields; outFields=* is never sent)")
    save(a.project, "site.json", site)
    print(json.dumps(site, indent=2))


def cmd_gather(a):
    """Address -> listing photos + facts (agent-reach web search/read; public pages only)."""
    from propmodel.gather import gather
    address = a.address
    if not address:
        site_path = os.path.join(a.project, "site.json")
        address = json.load(open(site_path)).get("address") if os.path.exists(site_path) else None
    if not address:
        sys.exit("gather: give --address, or run init with --address first")
    m = gather(address, a.project, max_photos=a.max_photos)
    print(json.dumps({"photos": len(m["photos"]), "pages": [(p["site"], p.get("images_found"), p.get("facts")) for p in m["pages"]]}, indent=1))


def _field_list(v):
    from propmodel.features import check_fields
    f = [x.strip() for x in v.split(",") if x.strip()] if isinstance(v, str) else list(v or [])
    return check_fields(f)


def _geojson_candidates(fc, name):
    """GeoJSON FeatureCollection (lon/lat polygons) -> footprint candidates like sources.arcgis_footprints."""
    out = []
    for i, f in enumerate(fc.get("features", [])):
        g = f.get("geometry") or {}
        rings = [g["coordinates"][0]] if g.get("type") == "Polygon" else \
            [p[0] for p in g.get("coordinates", [])] if g.get("type") == "MultiPolygon" else []
        for ring in rings:
            out.append({"source": name, "id": f"{name}/{f.get('id', i)}", "tags": f.get("properties") or {},
                        "ring_lonlat": [list(p[:2]) for p in ring]})
    return out


def _city_footprints(a, lat, lon):
    """Footprint candidates from the city layer (explicit fields; never outFields=*) or a local GeoJSON."""
    from propmodel import sources
    if a.footprint_geojson:
        with open(a.footprint_geojson) as f:
            return _geojson_candidates(json.load(f), a.footprint_name)
    fields = _field_list(a.footprint_fields or "OBJECTID")
    try:
        got = sources.arcgis_footprints(a.footprint_layer, lat, lon, a.radius, CACHE, out_fields=fields,
                                        where=a.footprint_where or "1=1")
    except TypeError:
        # sources.py without the out_fields contract: query here with the explicit list instead
        from propmodel import features as FT
        from propmodel.geo import LocalFrame as _LF
        env = FT.envelope_lonlat(_LF(lat, lon), a.radius)
        got = _geojson_candidates(FT.arcgis_query(a.footprint_layer, fields, CACHE, envelope=env,
                                                  where=a.footprint_where or "1=1"), a.footprint_name)
    out = []
    for i, c in enumerate(got):
        c = dict(c)
        c["source"] = a.footprint_name
        c["id"] = f"{a.footprint_name}/{str(c.get('id', i)).split('/')[-1]}"
        c["tags"] = {k: v for k, v in (c.get("tags") or {}).items() if k in fields}
        out.append(c)
    return out


def cmd_fetch(a):
    from shapely.geometry import Polygon
    from propmodel import sources
    site = load(a.project, "site.json")
    lat, lon = site["geocode"]["lat"], site["geocode"]["lon"]
    f0 = LocalFrame(lat, lon)
    cands = []
    if not a.no_osm:
        try:
            cands += sources.osm_buildings(lat, lon, a.radius, CACHE)
        except Exception as e:  # noqa: BLE001
            print("OSM footprints failed:", e)
    if not a.no_ms:
        try:
            cands += sources.ms_buildings(lat, lon, a.radius, CACHE)
        except Exception as e:  # noqa: BLE001
            print("Microsoft footprints failed:", e)
    city = bool(a.footprint_layer or a.footprint_geojson)
    if city:
        try:
            cands += _city_footprints(a, lat, lon)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"{a.footprint_name} footprints failed:", e)
    seed = (0.0, 0.0)
    if a.seed:
        seed = tuple(map(float, a.seed.split(",")))
    chosen = {}
    srcs = ([a.footprint_name] if city else []) + ["osm", "ms"]
    for src in srcs:
        got = sources.pick_building([c for c in cands if c["source"] == src], f0, seed)
        if got and got[1].distance(__import__("shapely").geometry.Point(seed)) < a.max_dist:
            chosen[src] = got
    if chosen:
        # re-centre the site origin on the chosen building
        ref = next(chosen[k] for k in srcs if k in chosen)[1].centroid
        clat, clon, _ = f0.to_geodetic(ref.x, ref.y, 0)
        site["origin"] = {"lat": float(clat), "lon": float(clon), "h": 0.0}
    try:
        elev = sources.dem_elevation(site["origin"]["lat"], site["origin"]["lon"], CACHE)
    except Exception as e:  # noqa: BLE001
        print("DEM elevation failed:", e)
        elev = None
    if elev is not None:
        site["origin"]["h"] = elev
        site["ground_elevation_dem"] = elev
    save(a.project, "site.json", site)
    frame = frame_of(a.project)
    fps = {"all": [], "chosen": {}}
    for c in cands:
        ring = frame.ring_from_lonlat(c["ring_lonlat"])
        fps["all"].append({"source": c["source"], "id": c["id"], "tags": c["tags"], "ring": ring})
    obs = []
    for src, (c, _) in chosen.items():
        ring = frame.ring_from_lonlat(c["ring_lonlat"])
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        poly = Polygon(ring)
        fps["chosen"][src] = {"id": c["id"], "tags": c["tags"], "ring": ring, "area_m2": poly.area,
                              "perimeter_m": poly.length,
                              "which": a.footprint_which if (city and src == a.footprint_name) else "roof_outline"}
        authoritative = city and src == a.footprint_name
        obs.append({"target": "outline", "which": a.footprint_which if authoritative else "roof_outline", "polygon": ring,
                    "sigma": a.footprint_sigma if authoritative else SIGMA[f"{src}_outline"], "shift": src,
                    "source": f"auto:{src} footprint",
                    "kind": "footprint", "note": ("city layer, traces the " + ("drip edge" if a.footprint_which == "roof_outline"
                                                                               else "walls")) if authoritative else
                    "imagery-traced footprints follow the roof edge (incl. overhang)"})
        print(f"{src}: {c['id']} area {poly.area:.1f} m2 ({U.sqft(poly.area):.0f} ft2) perimeter {poly.length:.1f} m")
    save(a.project, "data/footprints.json", fps)
    if city:
        set_auto_obs(a.project, f"auto:{a.footprint_name}", [o for o in obs if o["source"] == f"auto:{a.footprint_name} footprint"])
    set_auto_obs(a.project, "auto:osm", [o for o in obs if "osm" in o["source"]])
    set_auto_obs(a.project, "auto:ms", [o for o in obs if "ms" in o["source"]])
    if not a.no_ortho:
        try:
            meta, errs = None, []
            provs = [a.imagery] + [p for p in sources.IMAGERY if p != a.imagery]
            if a.ortho_url:
                u = a.ortho_url.rstrip("/")
                kind = "imageserver" if "/ImageServer" in u else "mapserver"
                if not u.endswith(("/export", "/exportImage")):
                    u += "/exportImage" if kind == "imageserver" else "/export"
                sources.IMAGERY["custom"] = {"url": u, "kind": kind, "attribution": a.ortho_attribution or "orthophoto service"}
                provs = ["custom"] + provs
            for prov in provs:   # fall back when a service is down
                try:
                    meta = sources.ortho_image(frame, a.half, P(a.project, "data/ortho.png"), CACHE, prov)
                    break
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{prov}: {e}")
            if meta is None:
                raise RuntimeError("; ".join(errs))
            print("ortho:", meta["provider"], f"{meta['m_per_px']:.3f} m/px", *(f"(after {e.split(':')[0]} failed)" for e in errs))
        except Exception as e:  # noqa: BLE001
            print("orthophoto failed:", e)
    if site.get("parcel_url"):
        fields = _field_list(a.parcel_fields) if a.parcel_fields else site.get("parcel_fields")
        if not fields:
            sys.exit("parcel query needs --parcel-fields F1,F2,... (explicit fields; outFields=* is never sent)")
        try:
            import inspect
            par = inspect.signature(sources.arcgis_parcel).parameters.get("out_fields")
            arg = ",".join(fields) if (par is not None and par.default == "*") else fields   # pre-contract sources.py
            feats = sources.arcgis_parcel(site["parcel_url"], site["origin"]["lat"], site["origin"]["lon"], CACHE, arg)
            for ft in feats:
                ft["properties"] = {k: v for k, v in (ft.get("properties") or {}).items() if k in fields}
                g = ft.get("geometry") or {}
                if g.get("type") == "Polygon":
                    ft["ring_local"] = frame.ring_from_lonlat(g["coordinates"][0])
            save(a.project, "data/parcel.json", feats)
            print(f"parcel: {len(feats)} feature(s); attributes saved to data/parcel.json")
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            print("parcel query failed:", e)
    print("origin:", site["origin"])


def cmd_lidar(a):
    import shapely
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from propmodel import ept, lidar
    from propmodel.geo import lonlat_to_mercator, mercator_scale
    site = load(a.project, "site.json")
    frame = frame_of(a.project)
    res = ept.find_resources(frame.lon0, frame.lat0, CACHE)
    if not res:
        sys.exit("no USGS 3DEP EPT coverage here; use photogrammetry / imagery instead")
    print("3DEP datasets:", ", ".join(f"{r['name']}" for r in res))
    pick = next((r for r in res if r["name"] == a.dataset), None)
    if pick is None:
        if a.dataset:
            print(f"WARNING: dataset {a.dataset!r} does not cover this point; using {res[0]['name']}")
        pick = res[0]
    e = ept.EPT(pick["url"], os.path.join(CACHE, "ept"))
    x, y = lonlat_to_mercator(frame.lon0, frame.lat0)
    s = a.half * mercator_scale(frame.lat0)
    extra_names = [v.strip() for v in a.extra_dims.split(",") if v.strip()] if a.extra_dims else []
    prog = lambda i, n, k: print(f"  node {i + 1}/{n} {k}", end="\r")  # noqa: E731
    if extra_names:
        raw, extra = e.read((x - s, y - s, x + s, y + s), progress=prog, extra=extra_names)
    else:
        raw, extra = e.read((x - s, y - s, x + s, y + s), progress=prog), None
    print(f"\n{len(raw)} points from {pick['name']}")
    loc = lidar.to_local(raw, frame)
    ground, ng = lidar.fit_ground(loc)
    dens, spacing = lidar.density(loc)
    fps = load(a.project, "data/footprints.json", {}).get("chosen", {})
    fp = unary_union([Polygon(v["ring"]) for v in fps.values()]) if fps else None
    walls = fp
    # the mask is the footprint + 1.2 m (building_points): enough for a drip-edge outline ~1 m off the LiDAR, not for
    # a WALL-LINE outline under deep eaves -> grow it by --mask-grow (auto: 1.3 m when a chosen outline traces walls)
    grow = a.mask_grow if a.mask_grow is not None else (1.3 if any(v.get("which") == "footprint" for v in fps.values()) else 0.0)
    if fp is not None and grow > 0:
        fp = fp.buffer(grow, join_style="mitre")
        print(f"footprint mask grown by {grow:.2f} m (wall-line outline)")
    if a.footprint_file:
        # an outside planimetric outline (e.g. city Ecopia) in the site frame, moved by its registration shift
        F = json.load(open(a.footprint_file))
        ring = F[a.footprint_key]["ring_enu"] if a.footprint_key else F["ring_enu"]
        dx, dy = (map(float, a.footprint_shift.split(","))) if a.footprint_shift else (0.0, 0.0)
        walls = Polygon([(x + dx, y + dy) for x, y in ring])
        fp = walls.buffer(a.footprint_buffer - 1.2)   # building_points adds 1.2
    if a.seed_only:
        fp = None
    # Model datum = ground elevation at the site origin (a LEVEL datum). Heights above a
    # tilted ground plane would tilt every roof plane by the lot slope and bias pitches.
    datum = float(site.get("datum_m") or ground[2]) if a.keep_datum else float(ground[2])
    surf = None
    if a.ground_mode == "surface":
        # hillside / class-1-only LiDAR: heights above a filtered ground SURFACE, last returns only
        # a house cut into a hill meets the grade at its uphill eave, so the filter would call that roof
        # "ground": cells inside the walls can never be ground (they are filled from around the house)
        inner = walls.buffer(a.walls_grow) if walls is not None else None
        surf = lidar.ground_surface(loc, cell=0.5, exclude=inner)
        hag = loc[:, 2] - lidar.surface_z(surf, loc[:, 0], loc[:, 1])
        last = (loc[:, 4] >= loc[:, 5]) if loc.shape[1] >= 6 else np.ones(len(loc), bool)
        # under the house the ground is only interpolated (from the uphill grade, decks...), so a low
        # uphill eave can sit < 1.5 m above it: accept lower points inside the walls, planes sort them out
        min_hag = np.full(len(loc), a.min_hag)
        if inner is not None:
            min_hag[shapely.contains_xy(inner, loc[:, 0], loc[:, 1])] = a.min_hag_inside
        m = last & (hag > min_hag) & ~np.isin(loc[:, 3], list(lidar.NON_SURFACE))
        if fp is not None:
            m &= shapely.contains_xy(fp.buffer(1.2), loc[:, 0], loc[:, 1])
        b = np.column_stack([loc[m], hag[m]])
    else:
        b = lidar.building_points(loc, ground, footprint=fp, single_returns=not a.keep_multi_returns)
    xyz = np.column_stack([b[:, 0], b[:, 1], b[:, 2] - datum])
    planes = lidar.segment_planes(xyz, thr=a.thr, min_pts=a.min_pts)
    rejected = []
    if a.accept:
        planes, rejected = lidar.accept_planes(planes, xyz, min_pts=a.min_pts, max_rms=a.accept_max_rms, min_area=a.accept_min_area)
        keep = lidar.remove_canopy(xyz, planes)
        if (~keep).any():   # branches over the eaves out, then segment again on the clean cloud
            print(f"canopy over the eaves: {(~keep).sum()} points removed")
            b, xyz = b[keep], xyz[keep]
            planes, rejected = lidar.accept_planes(lidar.segment_planes(xyz, thr=a.thr, min_pts=a.min_pts), xyz,
                                                   min_pts=a.min_pts, max_rms=a.accept_max_rms, min_area=a.accept_min_area)
        for p in rejected:
            print(f"  rejected: n={p['n']} rms {p['rms'] * 100:.1f} cm slope {p['pitch_rise_per_12']:.1f}/12 area {p.get('area_cells_m2', 0):.1f} m2 z {p['z_min']:.2f}-{p['z_max']:.2f}")
    low_flats = []
    if a.accept:
        # a level plane well below every pitched eave is a deck or a slab, not roof
        pitched = [p for p in planes if p["pitch_rise_per_12"] >= 1.0]
        if pitched:
            eave = min(p["z_min"] for p in pitched)
            low_flats = [p for p in planes if p["pitch_rise_per_12"] < 0.5 and p["z_max"] < eave - 1.0]
            planes = [p for p in planes if not any(p is q for q in low_flats)]
    inl = np.zeros(len(xyz), bool)
    label = -np.ones(len(xyz))
    for i, p in enumerate(planes):
        inl[p["indices"]] = True
        label[p["indices"]] = i
    # outline from roof-plane inliers only: overhanging branches / antennas don't inflate it
    roof_outline = lidar.outline(xyz[inl, :2] if inl.sum() > 20 else xyz[:, :2], spacing)
    np.save(P(a.project, "data/lidar_points.npy"), loc[:, :6])  # x, y, z_abs, class, return, n_returns
    np.save(P(a.project, "data/lidar_roof.npy"), np.column_stack([xyz, label]))
    if surf is not None:
        np.savez_compressed(P(a.project, "data/ground_surface.npz"), Z=surf["Z"] - datum, ground=surf["ground"],
                            x0=surf["x0"], y0=surf["y0"], cell=surf["cell"])
    if a.flat_z:
        # decks / slabs: level surfaces outside the roof, from last returns over the ground surface
        lo, hi = map(float, a.flat_z.split(","))
        allz = np.column_stack([loc[:, 0], loc[:, 1], loc[:, 2] - datum])
        nonroof = ~shapely.contains_xy(roof_outline.buffer(0.3), allz[:, 0], allz[:, 1])
        lastm = (loc[:, 4] >= loc[:, 5]) if loc.shape[1] >= 6 else np.ones(len(loc), bool)
        near = np.hypot(allz[:, 0], allz[:, 1]) < 25
        flats = lidar.flat_clusters(allz[lastm & near & nonroof], lo, hi)
        for p in low_flats:   # decks the plane finder saw inside the footprint buffer (if not found already)
            pts = xyz[p["indices"]]
            zc, cxy = float(np.median(pts[:, 2])), pts[:, :2].mean(axis=0)
            if any(abs(f["z"] - zc) < 0.1 and Polygon(f["outline"]).distance(
                    __import__("shapely").geometry.Point(cxy)) < 1.0 for f in flats):
                continue
            ol = lidar.outline(pts[:, :2], spacing)
            flats.append({"z": round(float(np.median(pts[:, 2])), 3), "area_m2": round(ol.area, 2), "n": int(p["n"]),
                          "outline": [list(map(lambda v: round(v, 3), c)) for c in ol.exterior.coords[:-1]], "from": "plane"})
        save(a.project, "data/flat_clusters.json", flats)
        for f in flats:
            c = np.mean(np.array(f["outline"]), axis=0)
            print(f"  flat surface z {f['z']:.2f} m, {f['area_m2']:.1f} m2 ({f['area_m2'] / 0.0929:.0f} ft2), n={f['n']} at ({c[0]:.1f}, {c[1]:.1f})")
    flight = {}
    if extra is not None:
        np.save(P(a.project, "data/lidar_extra.npy"), extra)        # same row order as data/lidar_points.npy
        gcol = next((i for i, nm in enumerate(extra_names) if nm.lower().replace("_", "") == "gpstime"), None)
        if gcol is not None:
            tt = extra[:, gcol]
            on_roof = shapely.contains_xy(roof_outline, loc[:, 0], loc[:, 1])
            flight = lidar.flight_dates(tt[on_roof] if on_roof.sum() >= 20 else tt, getattr(e, "gps_time_type", None))
            print(f"flight date {flight.get('flight_date') or 'unknown'} ({flight.get('gps_time')})"
                  + (" LEAF-ON: trees may hide eaves" if flight.get("leaf_on") else ""))
    out = {"dataset": pick["name"], "year": a.year or pick.get("year"), "points": int(len(raw)),
           "extra_dims": extra_names, **flight,
           "density_pts_m2": dens, "spacing_m": spacing, "ground_plane": ground, "ground_points": ng,
           "ground_z_at_origin": ground[2], "datum_m": datum,
           "ground_local": [ground[0], ground[1], 0.0], "building_points": int(len(xyz)),
           "planes": [{k: v for k, v in p.items() if k != "indices"} for p in planes],
           "roof_outline": list(roof_outline.exterior.coords)[:-1]}
    save(a.project, "data/lidar.json", out)
    site["datum_m"] = datum
    save(a.project, "site.json", site)
    # observations: plane-inlier heights (subsampled) + outline
    rng = np.random.default_rng(0)
    idx = np.flatnonzero(inl)
    if len(idx) > a.max_obs_pts:
        idx = rng.choice(idx, a.max_obs_pts, replace=False)
    src = f"auto:lidar {pick['name']}"
    obs = [{"target": "roof_z", "points": xyz[idx].round(3).tolist(), "sigma": SIGMA["lidar_z"],
            "source": src, "kind": "lidar", "dataset_year": a.year or pick.get("year")},
           {"target": "outline", "which": "roof_outline", "polygon": out["roof_outline"],
            "sigma": round(spacing / 2 + SIGMA["lidar_outline_extra"], 3), "source": src + " outline", "kind": "lidar"}]
    set_auto_obs(a.project, "auto:lidar", obs)
    print(f"density {dens:.1f} pts/m2 (spacing {spacing:.2f} m); ground z {ground[2]:.2f} m; {len(xyz)} roof pts")
    for i, p in enumerate(planes):
        print(f"  P{i + 1}: {p['pitch_rise_per_12']:.2f}/12 ±{p['slope_sigma'] * 12:.2f}  facing "
              f"{p['azimuth'] if p['azimuth'] is None else round(p['azimuth'])}°  n={p['n']}  "
              f"rms {p['rms'] * 100:.1f} cm  z {p['z_min']:.2f}-{p['z_max']:.2f} m")
    if (a.year or pick.get("year")) and site:
        print(f"NOTE: LiDAR flown {a.year or pick['year']} — renovations/additions after that are not in it.")


def cmd_suggest(a):
    from shapely.geometry import Polygon
    from propmodel import lidar
    li = load(a.project, "data/lidar.json")
    if li:
        outline = Polygon(li["roof_outline"])
        wing, info = lidar.suggest_wing(li["planes"], outline)
    else:
        fps = load(a.project, "data/footprints.json")["chosen"]
        ring = next(iter(fps.values()))["ring"]
        poly = Polygon(ring)
        mrr = poly.minimum_rotated_rectangle
        c = list(mrr.exterior.coords)
        e1, e2 = np.subtract(c[1], c[0]), np.subtract(c[2], c[1])
        L, W = np.linalg.norm(e1), np.linalg.norm(e2)
        d = e1 if L >= W else e2
        wing = {"id": "M", "type": "gable", "cx": mrr.centroid.x, "cy": mrr.centroid.y,
                "azimuth": math.degrees(math.atan2(d[0], d[1])) % 180, "length": max(L, W) - 0.9,
                "width": min(L, W) - 0.9, "pitch": 0.5, "eave_height": 2.8}
        info = {}
    wing = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in wing.items()}
    free = [f"{wing['id']}.{k}" for k in ("cx", "cy", "azimuth", "length", "width", "eave_height", "pitch")]
    spec = {"wings": [wing], "free": free, "ties": [], "ground": (li or {}).get("ground_local"), "priors": {
        f"{wing['id']}.eave_overhang": {"value": wing.get("eave_overhang", 0.45), "sigma": 0.15}}}
    if os.path.exists(P(a.project, "spec.json")) and not a.force:
        print("spec.json exists (use --force to overwrite). Suggested:")
        print(json.dumps(spec, indent=2))
        return
    save(a.project, "spec.json", spec)
    print(json.dumps(spec, indent=2), "\n", info)
    print("Edit spec.json: split L/T/U plans into several wings, set roof types, then run `fit`.")


def cmd_obs(a):
    obs = load(a.project, "observations.json", [])
    if a.action == "add":
        o = {"target": a.target, "value": a.value, "sigma": a.sigma, "source": a.source, "kind": a.kind or "manual"}
        if a.xy:
            o["xy"] = list(map(float, a.xy.split(",")))
        if a.date:
            o["date"] = a.date
        from propmodel import fusion
        fusion.prepare([o])  # validate units now
        obs.append(o)
        save(a.project, "observations.json", obs)
        print("added", o)
    elif a.action == "import":
        from propmodel import fusion
        with open(a.file) as f:
            rows = list(csv.DictReader(f))
        new = []
        for r in rows:
            o = {k: v for k, v in r.items() if v not in (None, "")}
            if "xy" in o:
                o["xy"] = list(map(float, o["xy"].split(",")))
            o.setdefault("kind", "past_report")
            fusion.prepare([o])
            new.append(o)
        obs.extend(new)
        save(a.project, "observations.json", obs)
        print(f"imported {len(new)} observations")
    elif a.action == "import-geo":
        # observations in WGS84 + absolute elevation (m, same vertical datum as the LiDAR, e.g. NAVD88)
        frame = frame_of(a.project)
        datum = model_datum(a.project)
        new = []
        for o in json.load(open(a.file)):
            o = dict(o)
            t = o["target"]
            if t == "roof_z_wgs84":
                pts = np.asarray(o.pop("points"), float)
                x, y, _ = frame.from_geodetic(pts[:, 1], pts[:, 0])
                o["points"] = np.column_stack([x, y, pts[:, 2] - datum]).round(4).tolist()
                o["target"] = "roof_z"
            elif t == "outline_wgs84":
                o["polygon"] = frame.ring_from_lonlat(o.pop("polygon"))
                o["target"] = "outline"
            elif t in ("z@_wgs84", "pitch@_wgs84", "azimuth@_wgs84"):
                lon, lat = o.pop("lonlat")
                x, y, _ = frame.from_geodetic(lat, lon)
                o["xy"] = [float(x), float(y)]
                o["target"] = t.replace("_wgs84", "")
                if o["target"] == "z@":
                    o["value"] = U.parse_length(o["value"]) - datum
            o["datum_navd88_m"] = datum
            new.append(o)
        obs.extend(new)
        save(a.project, "observations.json", obs)
        print(f"imported {len(new)} geo observations (datum {datum:.3f} m)")
    elif a.action == "import-multipatch":
        _import_multipatch(a)
    elif a.action == "remove":
        keep = [o for o in obs if not (a.source and str(o.get("source", "")).startswith(a.source))]
        save(a.project, "observations.json", keep)
        print(f"removed {len(obs) - len(keep)}")
    else:
        for i, o in enumerate(obs):
            v = o.get("value", f"[{len(o.get('points', o.get('polygon', [])))} pts]")
            print(f"{i:3d} {o['target']:<24} {str(v):<18} σ={o.get('sigma')!s:<10} {o.get('source')}")


CAVEAT_WORDS = ("assumed", "extrapolated", "estimated", "approximate", "approx", "unverified", "by eye", "±", "+/-")


def wing_notes_md(wings, caveats=None):
    """Markdown 'Wings and caveats' section: every wing's id, type and label (labels are where a wing's
    measured/assumed status is written), plus spec-level ``caveats`` strings. Labels containing a caveat
    word (assumed, extrapolated, ±, ...) are also repeated in the caveat list so they cannot be missed."""
    rows, flagged = [], []
    for w in wings:
        d = w if isinstance(w, dict) else w.to_dict()
        lab = str(d.get("label", "") or "")
        shape = "measured outline" if d.get("outline") else "rectangle"
        if d.get("walls"):
            shape += " + measured walls"
        rows.append(f"| {d['id']} | {d.get('type', '')} | {shape} | {lab.replace('|', '/')} |")
        if any(k in lab.lower() for k in CAVEAT_WORDS):
            flagged.append(f"wing {d['id']}: {lab}")
    if not rows:
        return []
    lines = ["## Wings and caveats", "", "| Wing | Roof | Plan shape | Label |", "|---|---|---|---|", *rows]
    items = flagged + [str(c) for c in (caveats or [])]
    if items:
        lines += ["", "**Caveats** (not fully measured):", *[f"- {c}" for c in items]]
    return lines + [""]


def _grade_levels(project, wings, offset=0.6):
    """``levels`` for roofgeom.build: finished grade along every wall from data/ground_surface.npz (pm.py lidar
    --ground-mode surface), sampled ``offset`` m outside the wall face (NaN where that point falls inside the
    house or off the grid: under a cantilever the grade comes from the walls beside it), and the siding line
    from details.json "foundation" as add_details.py draws it (per-wall top, else wall bottom + default_reveal;
    wings / walls in "skip" are sided from grade). None when neither file exists (plain-ground jobs)."""
    from shapely import contains_xy
    from shapely.ops import unary_union
    gs = P(project, "data/ground_surface.npz")
    det = load(project, "details.json", {}) or {}
    fnd = det.get("foundation")
    if not os.path.exists(gs) and fnd is None:
        return None
    G = np.load(gs) if os.path.exists(gs) else None
    house = unary_union([w.wall_polygon() for w in wings if not w.roof_only]).buffer(0.05)
    fnd = fnd or {}
    skip, tops, reveal = set(fnd.get("skip", [])), fnd.get("walls", {}), float(fnd.get("default_reveal", 0.25))

    def grade(xy):
        if G is None:
            return np.full(len(xy), np.nan)
        Z, c = G["Z"], float(G["cell"])
        fx = (xy[:, 0] - float(G["x0"])) / c - 0.5; fy = (xy[:, 1] - float(G["y0"])) / c - 0.5   # cell centres
        i0, j0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        ok = (i0 >= 0) & (j0 >= 0) & (i0 < Z.shape[1] - 1) & (j0 < Z.shape[0] - 1)
        i0, j0 = np.clip(i0, 0, Z.shape[1] - 2), np.clip(j0, 0, Z.shape[0] - 2)
        tx, ty = fx - i0, fy - j0
        z = (Z[j0, i0] * (1 - tx) * (1 - ty) + Z[j0, i0 + 1] * tx * (1 - ty) + Z[j0 + 1, i0] * (1 - tx) * ty
             + Z[j0 + 1, i0 + 1] * tx * ty)
        return np.where(ok, z, np.nan)

    def levels(key, pts, outward, bottom):
        q = np.asarray(pts, float) + offset * np.asarray(outward, float)
        g = grade(q)
        g[contains_xy(house, q[:, 0], q[:, 1])] = np.nan
        if key in skip or key.split(":")[0] in skip:
            s_ = np.full(len(q), np.nan)                       # no band: sided from grade
        elif key in tops:
            s_ = np.maximum(np.full(len(q), float(tops[key])), bottom)
        else:
            s_ = np.asarray(bottom, float) + reveal
        return g, s_
    levels.grade = grade
    levels.house = house
    return levels


def _details_openings(project, model):
    """details.json openings -> report entries {"facade", "area_m2", "zone": siding|foundation, "label"};
    openings on details "extra_walls" (e.g. a concrete garage front) are returned with those walls:
    ([openings], [{"name", "facade", "area_m2", "material", "openings_m2"}])."""
    from propmodel.report import compass
    det = load(project, "details.json", {}) or {}
    if not det:
        return None, []
    fnd = det.get("foundation") or {}
    skip, tops, reveal = set(fnd.get("skip", [])), fnd.get("walls", {}), float(fnd.get("default_reveal", 0.25))
    walls = {f"{w.wing}:{w.side}": w for w in model.walls}
    extra = {}
    for e in det.get("extra_walls", []):
        (x0, y0, z0), (x1, y1, z1) = e["bottom"][0], e["bottom"][-1]
        L = math.hypot(x1 - x0, y1 - y0)
        extra[e["name"]] = {"name": e["name"], "facade": compass(e.get("bearing")),
                            "material": e.get("material", "siding"),
                            "area_m2": max(L * (e["top_z"] - (z0 + z1) / 2), 0.0), "openings_m2": 0.0}
    out = []
    for o in det.get("openings", []):
        a_ = float(o["width"]) * float(o["height"]) * float(o.get("count", 1))
        k = o.get("wall")
        if k in extra:
            extra[k]["openings_m2"] += a_
            continue
        w = walls.get(k)
        if w is None:
            continue
        zb = min(p[2] for p in w.bottom) if w.bottom else 0.0
        line = zb if (k in skip or k.split(":")[0] in skip) else max(float(tops.get(k, zb + reveal)), zb)
        mid = float(o.get("sill_z", zb)) + float(o["height"]) / 2
        out.append({"facade": compass(w.bearing), "area_m2": a_, "zone": "siding" if mid >= line else "foundation",
                    "label": o.get("label", o.get("kind", ""))})
    return out, list(extra.values())


def _build_for_report(project, spec, wings_dicts):
    """The model for the report: walls split by finished grade / siding line (_grade_levels), plus the grade
    in front of details.json extra_walls (a garage under a deck stands lower than any wing wall)."""
    from shapely import contains_xy
    from propmodel import roofgeom
    wings = [roofgeom.Wing.from_dict(w) for w in wings_dicts]
    levels = None if spec.get("ground") else _grade_levels(project, wings)
    model = roofgeom.build(wings, ground=spec.get("ground"), levels=levels)
    if levels is not None:
        extra = []
        for e in (load(project, "details.json", {}) or {}).get("extra_walls", []):
            if e.get("bearing") is None:
                continue
            a_, b_ = np.array(e["bottom"][0][:2], float), np.array(e["bottom"][-1][:2], float)
            out = np.array([math.sin(math.radians(e["bearing"])), math.cos(math.radians(e["bearing"]))])
            q = a_ + np.outer(np.linspace(0.05, 0.95, 19), b_ - a_) + 0.6 * out
            g = levels.grade(q)
            g[contains_xy(levels.house, q[:, 0], q[:, 1])] = np.nan
            extra += [float(v) for v in g[np.isfinite(g)]]
        model.grade_extra = extra or None
    return model


def _finish(project, model, fit=None):
    from propmodel import report, roofgeom, plot
    save(project, "model.json", {**roofgeom.to_mesh_json(model), "site": load(project, "site.json")})
    site = load(project, "site.json")
    spec = load(project, "spec.json", {}) or {}
    det_open, extra_walls = _details_openings(project, model)
    md = report.build_report(model, fit, site, openings=det_open if det_open is not None else spec.get("openings"),
                             extra_walls=extra_walls)
    notes = wing_notes_md(model.wings, spec.get("caveats"))
    if notes:
        md = md.rstrip("\n") + "\n\n" + "\n".join(notes)
    with open(P(project, "report.md"), "w") as f:
        f.write(md)
    rj = report.report_json(model, fit, site)
    rj["wings"] = [{"id": w.id, "type": w.type, "label": w.label} for w in model.wings]
    rj["waste_pct_suggested"] = report.suggested_waste(model)[0]
    if fit and fit.get("sigma_free"):
        rj["sigma_note"] = (f"sigma = max of the main fit ({len(fit.get('free', []))} free parameters) and a reduced set "
                            f"({', '.join(fit['sigma_free'])})")
    if spec.get("caveats"):
        rj["caveats"] = list(spec["caveats"])
    save(project, "report.json", rj)
    _plot(project, model)
    print(md)


def _plot(project, model=None):
    from propmodel import plot
    fps = load(project, "data/footprints.json", {}).get("chosen", {})
    li = load(project, "data/lidar.json")
    roof = np.load(P(project, "data/lidar_roof.npy")) if os.path.exists(P(project, "data/lidar_roof.npy")) else None
    meta = load(project, "data/ortho.png.json")
    rings = [(f"{k} footprint", v["ring"]) for k, v in fps.items()]
    if li:
        rings.append(("LiDAR outline", li["roof_outline"]))
    pts = [p for _, r in rings for p in r]
    if model is not None:
        b = model.roof_outline().bounds
        pts += [(b[0], b[1]), (b[2], b[3])]
    if not pts:
        pts = [(-15, -15), (15, 15)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    half = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 + 4
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    bounds = (cx - half, cy - half, cx + half, cy + half)
    plot.overview(P(project, "overview.png"), bounds, P(project, "data/ortho.png") if meta else None, meta, rings,
                  roof, li["planes"] if li else (), model, title=load(project, "site.json").get("address"))
    print("wrote", P(project, "overview.png"))


SIGMA_GROUPS = {"pitches": ("pitch", "pitch_b", "end_pitch", "upper_pitch"),
                "eave_heights": ("eave_height", "eave_height_b"),
                "overhangs": ("eave_overhang", "eave_overhang_b", "rake_overhang", "shed_high_overhang"),
                "sizes": ("length", "width"), "positions": ("cx", "cy", "azimuth")}
ALWAYS = {"pitch", "eave_height", "eave_overhang", "rake_overhang", "length", "width", "cx", "cy", "azimuth"}


def expand_free(spec, tokens):
    """--sigma-free tokens -> wing parameter names: group words (pitches, eave_heights, overhangs, sizes, positions),
    bare fields (pitch) for every wing, or explicit names (M.pitch). Optional fields (pitch_b, eave_height_b, ...)
    only where the wing sets them; flat roofs get no pitch."""
    names = []
    for tok in [t.strip() for t in tokens if t.strip()]:
        if "." in tok:
            names.append(tok)
            continue
        flds = SIGMA_GROUPS.get(tok, (tok,))
        for w in spec.get("wings", []):
            for f in flds:
                if f in ("pitch", "pitch_b", "end_pitch", "upper_pitch") and w.get("type") == "flat":
                    continue
                if f in ("end_pitch",) and w.get("type") not in ("hip", "pyramid", "mansard"):
                    continue
                if f == "rake_overhang" and w.get("type") in ("hip", "pyramid", "mansard", "flat"):
                    continue
                if f in ALWAYS or w.get(f) is not None:
                    names.append(f"{w['id']}.{f}")
    return list(dict.fromkeys(names))


def apply_edges(spec, edges_json):
    """Measured overhangs (pm.py edges) -> free parameters with a weak prior centred on the measurement (it replaces
    the author's overhang prior: where the wall line is known, the overhang is measured, not assumed)."""
    spec = dict(spec)
    free, priors, notes = list(spec.get("free", [])), dict(spec.get("priors") or {}), []
    for name, mo in (edges_json.get("overhangs") or {}).items():
        wid = name.split(".", 1)[0]
        w = next((x for x in spec["wings"] if x["id"] == wid), None)
        if w is None or w.get("outline"):
            continue
        if name not in free:
            free.append(name)
        old = priors.get(name)
        priors[name] = {"value": mo["value"], "sigma": round(max(0.25, 2 * float(mo["sigma"])), 3)}
        notes.append(f"{name}: measured {mo['value']:.2f} m ({', '.join(mo.get('from', []))})"
                     + (f", replaces the prior {old['value']} +/- {old['sigma']}" if old else ""))
    spec["free"], spec["priors"] = free, priors
    return spec, notes


def cmd_fit(a):
    from propmodel import fusion
    spec = load(a.project, "spec.json")
    obs = load(a.project, "observations.json", [])
    if a.exclude:
        obs = [o for o in obs if not any(str(o.get("source", "")).startswith(x) for x in a.exclude)]
    fit_spec, notes = dict(spec), []
    if a.use_edges:
        ed = load(a.project, "data/edges.json")
        if ed is None:
            sys.exit("--use-edges: run `pm.py edges PROJECT --write-obs` first")
        fit_spec, notes = apply_edges(spec, ed)
        for n_ in notes:
            print("measured overhang:", n_)
    res = fusion.fit(fit_spec, obs, robust=not a.no_robust, verbose=True)
    res["free"] = list(fit_spec.get("free", []))
    if notes:
        res["edges_notes"] = notes
    if a.sigma_free:
        # sigma from a reduced free set (the geometry stays this fit's): never zero when spec.free is empty,
        # and the larger of the two where both exist (a reduced set alone would ignore the outline uncertainty)
        names = expand_free(fit_spec, a.sigma_free.split(","))
        excl = res.get("excluded", [])
        use = [o for o in obs if not any(o is x for x in excl)]
        sspec = dict(fit_spec, wings=res["wings"], free=names)
        rs = fusion.fit(sspec, use, robust=not a.no_robust, verbose=False, snoop=False)
        main = res.get("measurement_sigma", {})
        red = rs.get("measurement_sigma", {})
        res["measurement_sigma_main"], res["measurement_sigma_reduced"] = main, red
        res["measurement_sigma"] = {k: max(main.get(k, 0.0), red.get(k, 0.0)) for k in set(main) | set(red)}
        res["sigma_free"] = names
        res["params_sigma_free"] = rs.get("params", {})
        print(f"sigma: max of the main fit ({len(res['free'])} free) and the reduced set ({len(names)} free: {', '.join(names)})")
    save(a.project, "fit.json", res)
    fitted = dict(spec)
    fitted["wings"] = res["wings"]
    save(a.project, "spec_fitted.json", fitted)
    model = _build_for_report(a.project, spec, res["wings"])
    _finish(a.project, model, res)
    if a.accept:
        save(a.project, "spec.json", fitted)


def cmd_resid(a):
    from propmodel import confidence, roofgeom
    spec = load(a.project, a.spec) if a.spec else (load(a.project, "spec_fitted.json") or load(a.project, "spec.json"))
    if not spec:
        sys.exit("resid: no spec_fitted.json / spec.json")
    model = roofgeom.build([roofgeom.Wing.from_dict(w) for w in spec["wings"]])
    roof = np.load(P(a.project, "data/lidar_roof.npy"))
    li = load(a.project, "data/lidar.json", {}) or {}
    out = confidence.plane_residuals(model, roof, li.get("planes", []))
    save(a.project, "data/resid.json", out)
    print(f"  {'plane':8s} {'n':>5s} {'out':>5s} {'median':>7s} {'rms':>6s} {'p95|d|':>7s} {'area':>6s} assigned")
    for r in out["planes"]:
        print(f"  {r['plane']:8s} {r['n']:5d} {r['outside']:5d} {r['median_m'] if r['median_m'] is not None else float('nan'):+7.3f} "
              f"{r['rms_m'] if r['rms_m'] is not None else float('nan'):6.3f} {r['p95_abs_m'] if r['p95_abs_m'] is not None else float('nan'):7.2f} "
              f"{r['area_m2'] or 0:6.1f} {r.get('assigned', '')}")
    print(f"covered RMS {out['covered_rms_m']} m; {100 * (out['outside_frac'] or 0):.1f} % of plane returns outside the model;"
          f" unassigned planes >= 8 m2: {out['unassigned_big_planes'] or 'none'}")
    if not a.no_png and confidence.resid_png(model, roof, P(a.project, "resid.png")):
        print("wrote", P(a.project, "resid.png"))


def cmd_edges(a):
    from shapely.geometry import Polygon  # noqa: F401
    from propmodel import edges as E
    mj = load(a.project, "model.json")
    if not mj:
        sys.exit("edges: no model.json (run fit first)")
    pts = np.load(P(a.project, "data/lidar_points.npy"))
    datum = model_datum(a.project)
    xyz = np.column_stack([pts[:, 0], pts[:, 1], pts[:, 2] - datum])
    allx = np.array([c[0] for f in mj["facets"] for q in f["polygons"] for c in q["outer"]])
    ally = np.array([c[1] for f in mj["facets"] for q in f["polygons"] for c in q["outer"]])
    near = (xyz[:, 0] > allx.min() - 6) & (xyz[:, 0] < allx.max() + 6) & (xyz[:, 1] > ally.min() - 6) & (xyz[:, 1] < ally.max() + 6)
    res = E.drip_edges(mj, xyz[near], step=a.step, strip=a.strip, plane_tol=a.plane_tol)
    obs = load(a.project, "observations.json", []) or []
    fit = load(a.project, "fit.json", {}) or {}
    nu = fit.get("nuisance") or {}
    for o in obs:   # a city outline that traces the WALLS: drip edge - wall line = measured overhang
        if o.get("target") == "outline" and o.get("which") == "footprint" and o.get("polygon") and not o.get("disabled"):
            sh = o.get("shift")
            dx, dy = (nu.get(f"shift.{sh}.dx", 0.0), nu.get(f"shift.{sh}.dy", 0.0)) if sh else (0.0, 0.0)
            E.city_wall_overhangs(res, [[x + dx, y + dy] for x, y in o["polygon"]])
            res["wall_line_source"] = o.get("source")
            break
    res["overhangs"] = E.overhang_parameters(res)
    res["datum_m"] = datum
    save(a.project, "data/edges.json", res)
    print(E.table(res))
    for k, v in res["overhangs"].items():
        print(f"measured overhang {k}: {v['value']:.2f} +/- {v['sigma']:.2f} m over {v['n_edges']} edge(s) ({', '.join(v['from'])})")
    if a.write_obs:
        new = E.edge_observations(res)
        set_auto_obs(a.project, "auto:edges", new)
        obs = load(a.project, "observations.json", []) or []
        n_off = 0
        for o in obs:   # the LiDAR hull outline is superseded by the measured drip edges
            if o.get("target") == "outline" and o.get("kind") == "lidar" and str(o.get("source", "")).startswith("auto:lidar"):
                o["disabled"], o["disabled_by"] = bool(new), "pm.py edges (measured drip edges)"
                n_off += bool(new)
        save(a.project, "observations.json", obs)
        print(f"wrote {len(new)} drip-edge observations (auto:edges); LiDAR hull outline {'disabled' if n_off else 'kept'}")


def cmd_features(a):
    from propmodel import features as FT
    prof = FT.load_profile(a.profile) if a.profile else {}
    frame = frame_of(a.project)
    fit = load(a.project, "fit.json", {}) or {}
    shift = FT.city_shift(fit, a.shift_name)
    env = FT.envelope_lonlat(frame, a.half + 10)
    cols, used = {}, {}
    for kind in ("impervious", "sidewalk", "parcels", "hydrants", "curbs"):
        lay = FT.profile_layer(prof, kind)
        if not lay:
            continue
        try:
            if lay.get("geojson"):
                with open(FT.resolve_path(prof, lay["geojson"])) as f:
                    cols[kind] = json.load(f)
            elif FT.layer_url(lay):
                cols[kind] = FT.arcgis_query(FT.layer_url(lay), FT.layer_fields(lay), CACHE, envelope=env,
                                             where=lay.get("where") or "1=1")
            used[kind] = FT.layer_url(lay) or lay.get("geojson")
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"{kind} layer failed: {e}")
    imp = FT.profile_layer(prof, "impervious") or {}
    side = FT.profile_layer(prof, "sidewalk") or {}
    keep = {"impervious": [imp.get("use_field", "SurfaceUse"), imp.get("type_field", "SurfaceType")],
            "sidewalk": [side["width_field"]] if side.get("width_field") else []}
    feats = FT.features_from_geojson(cols, frame, shift, half=a.half, keep_props=keep,
                                     use_field=imp.get("use_field", "SurfaceUse"),
                                     drop_uses=tuple(imp.get("drop_uses", FT.DROP_USES)))
    feats["_meta"] = {"shift_applied": list(shift), "shift_source": f"fit.json shift.{a.shift_name}",
                      "layers": used, "half_m": a.half}
    out = a.out or P(a.project, "features.json")
    with open(out, "w") as f:
        json.dump(feats, f)
    print(f"features: " + ", ".join(f"{k} {len(v)}" for k, v in feats.items() if k != "_meta")
          + f"; city shift ({shift[0]:+.2f}, {shift[1]:+.2f}) m applied -> {out}")


def _import_multipatch(a):
    from propmodel import features as FT, multipatch as MP
    frame = frame_of(a.project)
    datum = model_datum(a.project)
    prof = FT.load_profile(a.profile) if a.profile else {}
    lay = FT.profile_layer(prof, "lod2") or {}
    url = a.layer or FT.layer_url(lay)
    z_unit = MP.Z_UNITS[(a.z_unit or lay.get("z_unit") or "m").lower()]
    if a.file:
        with open(a.file) as f:
            d = json.load(f)
        source = a.source or f"city LOD2 file {os.path.basename(a.file)}"
    elif url:
        fields = _field_list(a.fields) if a.fields else FT.layer_fields(lay)
        d = FT.arcgis_query(url, fields, CACHE, envelope=FT.envelope_lonlat(frame, a.radius), f="json",
                            where=lay.get("where") or "1=1", extra={"returnZ": "true"})
        source = a.source or f"city LOD2 {lay.get('name') or url.rstrip('/').split('/services/')[-1]}"
    else:
        sys.exit("import-multipatch: give FILE.json, --layer URL or a --profile with a lod2 layer")
    feats = d.get("features", [])
    sr = (d.get("spatialReference") or {}).get("wkid", 4326)
    lonlat = sr in (4326, 4269, None)
    if not lonlat:
        sys.exit(f"import-multipatch: geometry in wkid {sr}; query with outSR=4326 (the default here)")
    allfaces = []
    for ft in feats:
        parts = MP.geometry_parts(ft.get("geometry"))
        faces = MP.faces_from_parts(parts, atol=1e-9 if lonlat else 1e-3)
        faces = MP.classify(MP.to_local(faces, frame, z_unit=z_unit, datum=datum, lonlat=lonlat))
        allfaces.append(faces)
    k, dist = MP.pick_building(allfaces)
    if k is None or dist > 10:
        sys.exit(f"import-multipatch: no LOD2 building at the site ({len(feats)} feature(s))")
    faces = allfaces[k]
    roof = np.load(P(a.project, "data/lidar_roof.npy"))
    reg = MP.register(faces, roof[roof[:, 3] >= 0, :3])
    li = load(a.project, "data/lidar.json", {}) or {}
    summ = MP.summary(faces, li.get("planes"), shift=(reg["dx"], reg["dy"]))
    pts = MP.sample_roof(faces, max_points=a.max_points)
    pts[:, 0] += reg["dx"]; pts[:, 1] += reg["dy"]
    attrs = {kk: v for kk, v in ((feats[k].get("attributes") or feats[k].get("properties") or {}).items())}
    out = {"source": source, "feature": attrs, "registration": reg, "summary": summ, "z_unit": z_unit, "datum_m": datum,
           "faces": MP.local_faces_json(faces)}
    save(a.project, "data/lod2.json", out)
    ob = {"target": "roof_z", "points": np.round(pts, 3).tolist(), "sigma": float(a.sigma) if a.sigma else 0.20,
          "outside_sigma": 0.5,
          "dz_param": f"shift.{a.shift_source}.dz", "source": f"auto:{a.shift_source} {source}", "kind": "lod2",
          "note": f"{len(pts)} samples inside the roof faces (0.35 m inset), horizontally registered to the LiDAR by "
                  f"({reg['dx']:+.2f}, {reg['dy']:+.2f}) m; low weight: a check on form and pitch"}
    set_auto_obs(a.project, f"auto:{a.shift_source}", [ob] if len(pts) else [])
    print(f"LOD2: {len(MP.roof_faces(faces))} roof faces, {summ['roof_area_m2']:.1f} m2 sloped; registration "
          f"({reg['dx']:+.2f}, {reg['dy']:+.2f}, {reg['dz']:+.2f}) m, robust SD {reg['robust_sd_m']} m; {len(pts)} roof_z samples")
    for fr in summ["faces"]:
        if fr.get("pitch_diff") is not None:
            print(f"  face {fr['face']}: {fr['pitch']:.2f}/12 vs LiDAR {fr['lidar_plane']} {fr['pitch_lidar']:.2f}/12 ({fr['pitch_diff']:+.2f})")


def cmd_build(a):
    from propmodel import roofgeom
    spec = load(a.project, "spec.json")
    model = _build_for_report(a.project, spec, spec["wings"])
    _finish(a.project, model, load(a.project, "fit.json") if a.with_fit else None)


def cmd_plot(a):
    from propmodel import roofgeom
    spec = load(a.project, "spec.json")
    model = roofgeom.build([roofgeom.Wing.from_dict(w) for w in spec["wings"]]) if spec else None
    _plot(a.project, model)


def cmd_photo_info(a):
    from propmodel import photo
    for path in a.images:
        info = photo.exif(path)
        if info.get("fx_px") and info.get("RelativeAltitude"):
            alt = info["RelativeAltitude"] - (a.surface_height or 0)
            info["gsd_m_per_px"] = photo.gsd(alt, info["fx_px"])
            info["gsd_note"] = f"nadir GSD at {alt:.1f} m above the surface (RelativeAltitude - surface height)"
        print(json.dumps(info, indent=2, default=str))


def cmd_photo_measure(a):
    """pts.json: {"ref_px": [[u,v]..], "ref_plane": [[x,y]..], "measure": [{"name":..,"a":[u,v],"b":[u,v]}],
                  "pitch": [{"name":..,"low":[u,v],"high":[u,v]}], "px_sigma": 1.5, "ref_sigma": 0.005}"""
    from propmodel import photo
    d = json.load(open(a.points))
    ref_plane = [[U.parse_length(x), U.parse_length(y)] for x, y in d["ref_plane"]]
    r = photo.Rectifier(d["ref_px"], ref_plane, d.get("px_sigma", 1.5), d.get("ref_sigma", 0.005))
    out = {"reference_fit_residual_m": r.ref_residual_m, "measurements": []}
    for m in d.get("measure", []):
        dist, s = r.distance(m["a"], m["b"])
        out["measurements"].append({"name": m["name"], "m": dist, "sigma_m": s, "ft": U.ft(dist), "sigma_ft": U.ft(s)})
    for m in d.get("pitch", []):
        sl, s = r.rise_run(m["low"], m["high"])
        out["measurements"].append({"name": m["name"], "pitch_rise_per_12": sl * 12, "sigma_per_12": s * 12})
    print(json.dumps(out, indent=2))


def cmd_camera_match(a):
    """pairs.json: {"pairs": [{"px":[u,v], "xyz":[x,y,z]} ...]}  (xyz in the local ENU frame)."""
    from propmodel import photo
    info = photo.exif(a.image)
    if a.f35 and not info.get("K"):
        import math as _m
        fx = a.f35 / photo.DIAG_35MM * _m.hypot(info["width"], info["height"])
        info["K"] = [[fx, 0, info["width"] / 2], [0, fx, info["height"] / 2], [0, 0, 1]]
        print(f"no EXIF focal length: assuming {a.f35} mm-equivalent -> fx = {fx:.0f} px (use --refine-focal)")
    d = json.load(open(a.pairs))
    uv = [p["px"] for p in d["pairs"]]
    X = [p["xyz"] for p in d["pairs"]]
    cam = photo.solve_camera(uv, X, K=info["K"] if (info.get("K") and not a.free_focal) else None,
                             refine_focal=a.refine_focal)
    cam["blender"] = photo.blender_camera(cam, info["width"], info["height"])
    cam["image"] = os.path.abspath(a.image)
    cams = load(a.project, "cameras.json", {})
    cams[os.path.basename(a.image)] = cam
    save(a.project, "cameras.json", cams)
    print(json.dumps({k: cam[k] for k in ("centre", "rms_px", "rms_m_at_depth", "mean_depth_m", "errors_px")}, indent=2))
    if cam["rms_px"] > 5:
        print("WARNING: reprojection RMS > 5 px -> a wrong correspondence or the model disagrees with the photo.")


def cmd_align(a):
    """pairs.json: {"pairs": [{"src":[x,y,z], "dst":[x,y,z]}, ...]} -> similarity transform (Umeyama)."""
    d = json.load(open(a.pairs))
    S = np.array([p["src"] for p in d["pairs"]], float)
    D = np.array([p["dst"] for p in d["pairs"]], float)
    ms, md = S.mean(0), D.mean(0)
    Sc, Dc = S - ms, D - md
    Cov = Dc.T @ Sc / len(S)
    Uu, sv, Vt = np.linalg.svd(Cov)
    E = np.eye(3)
    if np.linalg.det(Uu) * np.linalg.det(Vt) < 0:
        E[2, 2] = -1
    R = Uu @ E @ Vt
    scale = np.trace(np.diag(sv) @ E) / np.mean(np.sum(Sc ** 2, 1)) if not a.no_scale else 1.0
    t = md - scale * R @ ms
    res = D - (scale * S @ R.T + t)
    err = np.linalg.norm(res, axis=1)
    M = np.eye(4)
    M[:3, :3] = scale * R
    M[:3, 3] = t
    out = {"scale": float(scale), "R": R.tolist(), "t": t.tolist(), "matrix_4x4": M.tolist(),
           "rms_m": float(np.sqrt(np.mean(err ** 2))), "errors_m": err.tolist()}
    print(json.dumps(out, indent=2))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=2)


def cmd_blender(a):
    script = os.path.join(HERE, "blender", "build_model.py")
    args = ["--model", P(a.project, "model.json"), "--out", P(a.project, "out")]
    if a.plain_ground:
        args.append("--plain-ground")
    elif os.path.exists(P(a.project, "data/ortho.png")):
        args += ["--ortho", P(a.project, "data/ortho.png")]
    if not a.no_points:
        if a.all_points and os.path.exists(P(a.project, "data/lidar_points.npy")):
            pts = np.load(P(a.project, "data/lidar_points.npy"))
            keep = np.hypot(pts[:, 0], pts[:, 1]) < 40
            xyz = np.column_stack([pts[keep, :2], pts[keep, 2] - model_datum(a.project)])
        elif os.path.exists(P(a.project, "data/lidar_roof.npy")):
            xyz = np.load(P(a.project, "data/lidar_roof.npy"))[:, :3]  # building points, height above ground
        else:
            xyz = None
        if xyz is not None:
            np.savetxt(P(a.project, "data/lidar_points_hag.xyz"), xyz, fmt="%.3f")
            args += ["--points", P(a.project, "data/lidar_points_hag.xyz")]
    if os.path.exists(P(a.project, "cameras.json")):
        args += ["--cameras", P(a.project, "cameras.json")]
    if a.glb:
        args.append("--glb")
    if a.render:
        args.append("--render")
    if a.blender:
        cmd = [a.blender, "-b", "--factory-startup", "-P", script, "--"] + args
    else:
        cmd = [sys.executable, script] + args  # uses the `bpy` pip module
    print(" ".join(cmd))
    sys.exit(subprocess.call(cmd))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("init"); s.add_argument("project"); s.add_argument("--address"); s.add_argument("--latlon")
    s.add_argument("--parcel-url", help="ArcGIS REST parcel layer URL (…/FeatureServer/0)")
    s.add_argument("--parcel-fields", help="explicit attribute list for --parcel-url (required with it)"); s.set_defaults(fn=cmd_init)
    s = sp.add_parser("gather"); s.add_argument("project"); s.add_argument("--address"); s.add_argument("--max-photos", type=int, default=120)
    s.set_defaults(fn=cmd_gather)
    s = sp.add_parser("fetch"); s.add_argument("project"); s.add_argument("--radius", type=float, default=60)
    s.add_argument("--half", type=float, default=40, help="orthophoto half-size (m)")
    s.add_argument("--imagery", default="esri", choices=["esri", "naip"]); s.add_argument("--no-ms", action="store_true")
    s.add_argument("--seed", help="x,y (m) of the target building relative to the geocode if it picked a neighbour")
    s.add_argument("--max-dist", type=float, default=25.0)
    s.add_argument("--footprint-layer", help="ArcGIS REST polygon layer with authoritative footprints (city/county)")
    s.add_argument("--footprint-name", default="city"); s.add_argument("--footprint-sigma", type=float, default=0.25)
    s.add_argument("--footprint-which", default="footprint", choices=["footprint", "roof_outline"],
                   help="does that layer trace walls (footprint) or drip edges (roof_outline)?")
    s.add_argument("--footprint-fields", help="explicit attribute list for the footprint layer (default OBJECTID)")
    s.add_argument("--footprint-where", default="1=1", help="where clause, e.g. \"CateTitle='Building'\"")
    s.add_argument("--footprint-geojson", help="local GeoJSON (lon/lat polygons) instead of --footprint-layer")
    s.add_argument("--parcel-fields", help="explicit attribute list for site.json parcel_url")
    s.add_argument("--no-osm", action="store_true", help="skip OpenStreetMap (Overpass mirrors can time out for minutes)")
    s.add_argument("--no-ortho", action="store_true")
    s.add_argument("--ortho-url", help="ArcGIS MapServer / ImageServer of a city orthophoto (tried first)")
    s.add_argument("--ortho-attribution")
    s.set_defaults(fn=cmd_fetch)
    s = sp.add_parser("lidar"); s.add_argument("project"); s.add_argument("--dataset")
    s.add_argument("--ground-mode", default="plane", choices=["plane", "surface"],
                   help="surface: morphological ground surface + last returns (hillsides, class-1-only LiDAR)")
    s.add_argument("--footprint-file", help="json with ring_enu outline(s) in the site frame (e.g. city planimetrics)")
    s.add_argument("--footprint-key"); s.add_argument("--footprint-shift", help="dx,dy registration shift (m)")
    s.add_argument("--footprint-buffer", type=float, default=2.5)
    s.add_argument("--mask-grow", type=float, help="extra growth of the footprint mask (m); default 1.3 for a wall-line "
                   "footprint (fetch --footprint-which footprint), else 0")
    s.add_argument("--min-hag", type=float, default=1.5)
    s.add_argument("--min-hag-inside", type=float, default=0.4, help="surface mode: min height inside the (grown) walls")
    s.add_argument("--walls-grow", type=float, default=1.0, help="surface mode: grow the walls by this for the no-ground mask")
    s.add_argument("--accept", action="store_true", help="keep only real roof planes (n, rms, slope, area) and drop canopy over eaves")
    s.add_argument("--accept-max-rms", type=float, default=0.06); s.add_argument("--accept-min-area", type=float, default=8.0)
    s.add_argument("--keep-datum", action="store_true", help="keep site.json datum_m (re-runs: numbers stay comparable)")
    s.add_argument("--year", type=int, help="acquisition year when the EPT metadata lacks it")
    s.add_argument("--flat-z", help="lo,hi: find level surfaces (decks, slabs) between these heights (model datum)")
    s.add_argument("--half", type=float, default=35); s.add_argument("--thr", type=float, default=0.12)
    s.add_argument("--min-pts", type=int, default=25); s.add_argument("--max-obs-pts", type=int, default=600)
    s.add_argument("--seed-only", action="store_true", help="ignore footprints; take the blob at the origin")
    s.add_argument("--keep-multi-returns", action="store_true", help="keep non-last returns (default drops them: tree canopy)")
    s.add_argument("--extra-dims", help="extra LAS dimensions, e.g. GpsTime,Intensity -> data/lidar_extra.npy; "
                   "GpsTime also gives the flight date in lidar.json")
    s.set_defaults(fn=cmd_lidar)
    s = sp.add_parser("suggest"); s.add_argument("project"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_suggest)
    s = sp.add_parser("obs"); s.add_argument("project")
    s.add_argument("action", choices=["add", "import", "import-geo", "import-multipatch", "list", "remove"])
    s.add_argument("file", nargs="?"); s.add_argument("--target"); s.add_argument("--value"); s.add_argument("--sigma")
    s.add_argument("--source"); s.add_argument("--kind"); s.add_argument("--xy"); s.add_argument("--date")
    s.add_argument("--profile", help="import-multipatch: region profile with a lod2 layer")
    s.add_argument("--layer", help="import-multipatch: ArcGIS multipatch layer URL"); s.add_argument("--fields")
    s.add_argument("--z-unit", help="import-multipatch: m | ft | ftUS (default from the profile, else m)")
    s.add_argument("--radius", type=float, default=30.0); s.add_argument("--max-points", type=int, default=300)
    s.add_argument("--shift-source", default="city3d", help="import-multipatch: nuisance name (shift.<name>.dz)")
    s.set_defaults(fn=cmd_obs)
    s = sp.add_parser("fit"); s.add_argument("project"); s.add_argument("--exclude", nargs="*", default=[])
    s.add_argument("--no-robust", action="store_true"); s.add_argument("--accept", action="store_true", help="write fitted wings back to spec.json")
    s.add_argument("--sigma-free", help="sigma from a reduced free set too, e.g. pitches,eave_heights (or M.pitch,...)")
    s.add_argument("--use-edges", action="store_true", help="free the overhangs pm.py edges measured (prior = the measurement)")
    s.set_defaults(fn=cmd_fit)
    s = sp.add_parser("resid"); s.add_argument("project"); s.add_argument("--spec", help="default spec_fitted.json")
    s.add_argument("--no-png", action="store_true"); s.set_defaults(fn=cmd_resid)
    s = sp.add_parser("edges"); s.add_argument("project"); s.add_argument("--write-obs", action="store_true")
    s.add_argument("--step", type=float, default=0.5); s.add_argument("--strip", type=float, default=1.0)
    s.add_argument("--plane-tol", type=float, default=0.25); s.set_defaults(fn=cmd_edges)
    s = sp.add_parser("features"); s.add_argument("project"); s.add_argument("--profile")
    s.add_argument("--half", type=float, default=30.0); s.add_argument("--shift-name", default="city")
    s.add_argument("--out", help="default PROJECT/features.json"); s.set_defaults(fn=cmd_features)
    s = sp.add_parser("build"); s.add_argument("project"); s.add_argument("--with-fit", action="store_true"); s.set_defaults(fn=cmd_build)
    s = sp.add_parser("plot"); s.add_argument("project"); s.set_defaults(fn=cmd_plot)
    s = sp.add_parser("photo-info"); s.add_argument("images", nargs="+"); s.add_argument("--surface-height", type=float)
    s.set_defaults(fn=cmd_photo_info)
    s = sp.add_parser("photo-measure"); s.add_argument("--points", required=True); s.set_defaults(fn=cmd_photo_measure)
    s = sp.add_parser("camera-match"); s.add_argument("project"); s.add_argument("--image", required=True)
    s.add_argument("--pairs", required=True); s.add_argument("--refine-focal", action="store_true")
    s.add_argument("--free-focal", action="store_true")
    s.add_argument("--f35", type=float, help="35mm-equivalent focal length when EXIF is missing (iPhone main camera: 26)")
    s.set_defaults(fn=cmd_camera_match)
    s = sp.add_parser("align"); s.add_argument("--pairs", required=True); s.add_argument("--out"); s.add_argument("--no-scale", action="store_true")
    s.set_defaults(fn=cmd_align)
    s = sp.add_parser("blender"); s.add_argument("project"); s.add_argument("--blender"); s.add_argument("--glb", action="store_true")
    s.add_argument("--render", action="store_true"); s.add_argument("--no-points", action="store_true")
    s.add_argument("--all-points", action="store_true", help="whole LiDAR tile (trees, ground) instead of building points")
    s.add_argument("--plain-ground", action="store_true", help="neutral grade plane instead of the orthophoto (keeps trees out)")
    s.set_defaults(fn=cmd_blender)
    a = ap.parse_args()
    from propmodel import ept
    if ept.install_offline_guard():
        print("offline: PROPMODEL_OFFLINE=1, answers from PROPMODEL_CACHE only")
    a.fn(a)


if __name__ == "__main__":
    main()
