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
    save(a.project, "site.json", site)
    print(json.dumps(site, indent=2))


def cmd_fetch(a):
    from shapely.geometry import Polygon
    from propmodel import sources
    site = load(a.project, "site.json")
    lat, lon = site["geocode"]["lat"], site["geocode"]["lon"]
    f0 = LocalFrame(lat, lon)
    cands = []
    try:
        cands += sources.osm_buildings(lat, lon, a.radius, CACHE)
    except Exception as e:
        print("OSM footprints failed:", e)
    if not a.no_ms:
        try:
            cands += sources.ms_buildings(lat, lon, a.radius, CACHE)
        except Exception as e:
            print("Microsoft footprints failed:", e)
    if a.footprint_layer:
        try:
            cands += sources.arcgis_footprints(a.footprint_layer, lat, lon, a.radius, CACHE, a.footprint_name)
        except Exception as e:
            print(f"{a.footprint_name} footprints failed:", e)
    seed = (0.0, 0.0)
    if a.seed:
        seed = tuple(map(float, a.seed.split(",")))
    chosen = {}
    srcs = ([a.footprint_name] if a.footprint_layer else []) + ["osm", "ms"]
    for src in srcs:
        got = sources.pick_building([c for c in cands if c["source"] == src], f0, seed)
        if got and got[1].distance(__import__("shapely").geometry.Point(seed)) < a.max_dist:
            chosen[src] = got
    if chosen:
        # re-centre the site origin on the chosen building
        ref = next(chosen[k] for k in srcs if k in chosen)[1].centroid
        clat, clon, _ = f0.to_geodetic(ref.x, ref.y, 0)
        site["origin"] = {"lat": float(clat), "lon": float(clon), "h": 0.0}
    elev = sources.dem_elevation(site["origin"]["lat"], site["origin"]["lon"], CACHE)
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
                              "perimeter_m": poly.length}
        authoritative = a.footprint_layer and src == a.footprint_name
        obs.append({"target": "outline", "which": a.footprint_which if authoritative else "roof_outline", "polygon": ring,
                    "sigma": a.footprint_sigma if authoritative else SIGMA[f"{src}_outline"], "shift": src,
                    "source": f"auto:{src} footprint",
                    "kind": "footprint", "note": "imagery-traced footprints follow the roof edge (incl. overhang)"})
        print(f"{src}: {c['id']} area {poly.area:.1f} m2 ({U.sqft(poly.area):.0f} ft2) perimeter {poly.length:.1f} m")
    save(a.project, "data/footprints.json", fps)
    if a.footprint_layer:
        set_auto_obs(a.project, f"auto:{a.footprint_name}", [o for o in obs if o["source"] == f"auto:{a.footprint_name} footprint"])
    set_auto_obs(a.project, "auto:osm", [o for o in obs if "osm" in o["source"]])
    set_auto_obs(a.project, "auto:ms", [o for o in obs if "ms" in o["source"]])
    try:
        meta = sources.ortho_image(frame, a.half, P(a.project, "data/ortho.png"), CACHE, a.imagery)
        print("ortho:", meta["provider"], f"{meta['m_per_px']:.3f} m/px")
    except Exception as e:
        print("orthophoto failed:", e)
    if site.get("parcel_url"):
        try:
            feats = sources.arcgis_parcel(site["parcel_url"], site["origin"]["lat"], site["origin"]["lon"], CACHE)
            for ft in feats:
                g = ft.get("geometry") or {}
                if g.get("type") == "Polygon":
                    ft["ring_local"] = frame.ring_from_lonlat(g["coordinates"][0])
            save(a.project, "data/parcel.json", feats)
            print(f"parcel: {len(feats)} feature(s); attributes saved to data/parcel.json")
        except Exception as e:
            print("parcel query failed:", e)
    print("origin:", site["origin"])


def cmd_lidar(a):
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
    pick = next((r for r in res if r["name"] == a.dataset), res[0])
    e = ept.EPT(pick["url"], os.path.join(CACHE, "ept"))
    x, y = lonlat_to_mercator(frame.lon0, frame.lat0)
    s = a.half * mercator_scale(frame.lat0)
    raw = e.read((x - s, y - s, x + s, y + s), progress=lambda i, n, k: print(f"  node {i + 1}/{n} {k}", end="\r"))
    print(f"\n{len(raw)} points from {pick['name']}")
    loc = lidar.to_local(raw, frame)
    ground, ng = lidar.fit_ground(loc)
    dens, spacing = lidar.density(loc)
    fps = load(a.project, "data/footprints.json", {}).get("chosen", {})
    fp = unary_union([Polygon(v["ring"]) for v in fps.values()]) if fps else None
    if a.seed_only:
        fp = None
    b = lidar.building_points(loc, ground, footprint=fp)
    xyz = np.column_stack([b[:, 0], b[:, 1], b[:, 6]])  # height above ground
    planes = lidar.segment_planes(xyz, thr=a.thr, min_pts=a.min_pts)
    inl = np.zeros(len(xyz), bool)
    label = -np.ones(len(xyz))
    for i, p in enumerate(planes):
        inl[p["indices"]] = True
        label[p["indices"]] = i
    # outline from roof-plane inliers only: overhanging branches / antennas don't inflate it
    roof_outline = lidar.outline(xyz[inl, :2] if inl.sum() > 20 else xyz[:, :2], spacing)
    np.save(P(a.project, "data/lidar_points.npy"), np.column_stack([loc[:, :3], loc[:, 3]]))
    np.save(P(a.project, "data/lidar_roof.npy"), np.column_stack([xyz, label]))
    out = {"dataset": pick["name"], "year": pick.get("year"), "points": int(len(raw)),
           "density_pts_m2": dens, "spacing_m": spacing, "ground_plane": ground, "ground_points": ng,
           "ground_z_at_origin": ground[2], "building_points": int(len(xyz)),
           "planes": [{k: v for k, v in p.items() if k != "indices"} for p in planes],
           "roof_outline": list(roof_outline.exterior.coords)[:-1]}
    save(a.project, "data/lidar.json", out)
    # observations: plane-inlier heights (subsampled) + outline
    rng = np.random.default_rng(0)
    idx = np.flatnonzero(inl)
    if len(idx) > a.max_obs_pts:
        idx = rng.choice(idx, a.max_obs_pts, replace=False)
    src = f"auto:lidar {pick['name']}"
    obs = [{"target": "roof_z", "points": xyz[idx].round(3).tolist(), "sigma": SIGMA["lidar_z"],
            "source": src, "kind": "lidar", "dataset_year": pick.get("year")},
           {"target": "outline", "which": "roof_outline", "polygon": out["roof_outline"],
            "sigma": round(spacing / 2 + SIGMA["lidar_outline_extra"], 3), "source": src + " outline", "kind": "lidar"}]
    set_auto_obs(a.project, "auto:lidar", obs)
    print(f"density {dens:.1f} pts/m2 (spacing {spacing:.2f} m); ground z {ground[2]:.2f} m; {len(xyz)} roof pts")
    for i, p in enumerate(planes):
        print(f"  P{i + 1}: {p['pitch_rise_per_12']:.2f}/12 ±{p['slope_sigma'] * 12:.2f}  facing "
              f"{p['azimuth'] if p['azimuth'] is None else round(p['azimuth'])}°  n={p['n']}  "
              f"rms {p['rms'] * 100:.1f} cm  z {p['z_min']:.2f}-{p['z_max']:.2f} m")
    if pick.get("year") and site:
        print(f"NOTE: LiDAR flown {pick['year']} — renovations/additions after that are not in it.")


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
    spec = {"wings": [wing], "free": free, "ties": [], "priors": {
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
    elif a.action == "remove":
        keep = [o for o in obs if not (a.source and str(o.get("source", "")).startswith(a.source))]
        save(a.project, "observations.json", keep)
        print(f"removed {len(obs) - len(keep)}")
    else:
        for i, o in enumerate(obs):
            v = o.get("value", f"[{len(o.get('points', o.get('polygon', [])))} pts]")
            print(f"{i:3d} {o['target']:<24} {str(v):<18} σ={o.get('sigma')!s:<10} {o.get('source')}")


def _finish(project, model, fit=None):
    from propmodel import report, roofgeom, plot
    save(project, "model.json", {**roofgeom.to_mesh_json(model), "site": load(project, "site.json")})
    site = load(project, "site.json")
    spec = load(project, "spec.json", {}) or {}
    md = report.build_report(model, fit, site, openings=spec.get("openings"))
    with open(P(project, "report.md"), "w") as f:
        f.write(md)
    save(project, "report.json", report.report_json(model, fit, site))
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


def cmd_fit(a):
    from propmodel import fusion, roofgeom
    spec = load(a.project, "spec.json")
    obs = load(a.project, "observations.json", [])
    if a.exclude:
        obs = [o for o in obs if not any(str(o.get("source", "")).startswith(x) for x in a.exclude)]
    res = fusion.fit(spec, obs, robust=not a.no_robust, verbose=True)
    save(a.project, "fit.json", res)
    fitted = dict(spec)
    fitted["wings"] = res["wings"]
    save(a.project, "spec_fitted.json", fitted)
    model = roofgeom.build([roofgeom.Wing.from_dict(w) for w in res["wings"]], ground=spec.get("ground"))
    _finish(a.project, model, res)
    if a.accept:
        save(a.project, "spec.json", fitted)


def cmd_build(a):
    from propmodel import roofgeom
    spec = load(a.project, "spec.json")
    model = roofgeom.build([roofgeom.Wing.from_dict(w) for w in spec["wings"]], ground=spec.get("ground"))
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
    if os.path.exists(P(a.project, "data/ortho.png")):
        args += ["--ortho", P(a.project, "data/ortho.png")]
    if not a.no_points:
        if a.all_points and os.path.exists(P(a.project, "data/lidar_points.npy")):
            pts = np.load(P(a.project, "data/lidar_points.npy"))
            g = load(a.project, "data/lidar.json")["ground_plane"]
            hag = pts[:, 2] - (g[0] * pts[:, 0] + g[1] * pts[:, 1] + g[2])
            keep = np.hypot(pts[:, 0], pts[:, 1]) < 40
            xyz = np.column_stack([pts[keep, :2], hag[keep]])
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
    s.add_argument("--parcel-url", help="ArcGIS REST parcel layer URL (…/FeatureServer/0)"); s.set_defaults(fn=cmd_init)
    s = sp.add_parser("fetch"); s.add_argument("project"); s.add_argument("--radius", type=float, default=60)
    s.add_argument("--half", type=float, default=40, help="orthophoto half-size (m)")
    s.add_argument("--imagery", default="esri", choices=["esri", "naip"]); s.add_argument("--no-ms", action="store_true")
    s.add_argument("--seed", help="x,y (m) of the target building relative to the geocode if it picked a neighbour")
    s.add_argument("--max-dist", type=float, default=25.0)
    s.add_argument("--footprint-layer", help="ArcGIS REST polygon layer with authoritative footprints (city/county)")
    s.add_argument("--footprint-name", default="city"); s.add_argument("--footprint-sigma", type=float, default=0.25)
    s.add_argument("--footprint-which", default="footprint", choices=["footprint", "roof_outline"],
                   help="does that layer trace walls (footprint) or drip edges (roof_outline)?")
    s.set_defaults(fn=cmd_fetch)
    s = sp.add_parser("lidar"); s.add_argument("project"); s.add_argument("--dataset")
    s.add_argument("--half", type=float, default=35); s.add_argument("--thr", type=float, default=0.12)
    s.add_argument("--min-pts", type=int, default=25); s.add_argument("--max-obs-pts", type=int, default=600)
    s.add_argument("--seed-only", action="store_true", help="ignore footprints; take the blob at the origin")
    s.set_defaults(fn=cmd_lidar)
    s = sp.add_parser("suggest"); s.add_argument("project"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_suggest)
    s = sp.add_parser("obs"); s.add_argument("project"); s.add_argument("action", choices=["add", "import", "import-geo", "list", "remove"])
    s.add_argument("file", nargs="?"); s.add_argument("--target"); s.add_argument("--value"); s.add_argument("--sigma")
    s.add_argument("--source"); s.add_argument("--kind"); s.add_argument("--xy"); s.add_argument("--date"); s.set_defaults(fn=cmd_obs)
    s = sp.add_parser("fit"); s.add_argument("project"); s.add_argument("--exclude", nargs="*", default=[])
    s.add_argument("--no-robust", action="store_true"); s.add_argument("--accept", action="store_true", help="write fitted wings back to spec.json")
    s.set_defaults(fn=cmd_fit)
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
    s.set_defaults(fn=cmd_blender)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
