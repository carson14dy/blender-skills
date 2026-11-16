"""USDA NAIP imagery from Microsoft Planetary Computer (anonymous SAS token), cropped and cached.

    rgb, sampler = naip_window(site, half_m=230, year="2025")
    colours = sampler(e, n)   # model-frame east/north metres -> uint8 RGB (N x 3)

NAIP is public domain (USDA FSA). Planetary Computer asks for no key; the token endpoint
`/api/sas/v1/token/naip` returns a short-lived SAS string for the storage account.
"""
import json
import os
import urllib.request

import numpy as np

from common import CACHE, log, proj

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"
UA = {"User-Agent": "roof-studio-lab/0.1 (data tools; python-urllib)", "Content-Type": "application/json"}


def _get(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def find_item(lon, lat, year):
    res = _get(STAC, {"collections": ["naip"], "intersects": {"type": "Point", "coordinates": [lon, lat]},
                      "datetime": "%s-01-01T00:00:00Z/%s-12-31T23:59:59Z" % (year, year), "limit": 5})
    feats = res.get("features", [])
    if not feats:
        raise RuntimeError("no NAIP %s item over %.5f, %.5f" % (year, lon, lat))
    return feats[0]


def naip_window(site, half_m=230.0, year="2025"):
    """Read (and cache) a NAIP crop covering +-half_m around the site. Returns (info, sampler)."""
    os.makedirs(os.path.join(CACHE, "naip"), exist_ok=True)
    cache = os.path.join(CACHE, "naip", "crop-%s-%.5f-%.5f-%d.npz" % (year, site.lon, site.lat, int(half_m)))
    if not os.path.exists(cache):
        import rasterio
        from rasterio.windows import from_bounds
        from pyproj import Transformer
        os.environ.setdefault("CURL_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
        item = find_item(site.lon, site.lat, year)
        tok = _get(TOKEN)["token"]
        href = item["assets"]["image"]["href"] + "?" + tok
        log("NAIP item", item["id"], item["properties"].get("datetime"), "gsd", item["properties"].get("gsd"))
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
            with rasterio.open(href) as src:
                crs = src.crs.to_epsg()
                tr = Transformer.from_crs(4326, crs, always_xy=True)
                # corners of the box in the model frame -> city -> lon/lat -> raster CRS
                es = np.array([-half_m, half_m, -half_m, half_m]) * 1.05
                ns = np.array([-half_m, -half_m, half_m, half_m]) * 1.05
                cx, cy = site.enu_to_city(es, ns)
                lon, lat = proj.city_to_lonlat(cx, cy)
                X, Y = tr.transform(lon, lat)
                win = from_bounds(min(X), min(Y), max(X), max(Y), src.transform)
                data = src.read([1, 2, 3], window=win, boundless=False)
                wt = src.window_transform(win)
        np.savez_compressed(cache, rgb=data, transform=np.array(wt)[:6], crs=crs, item=item["id"],
                            date=item["properties"].get("datetime"))
    z = np.load(cache)
    rgb, t, crs = z["rgb"], z["transform"], int(z["crs"])
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, crs, always_xy=True)
    a, b, c, d, e, f = t

    def sample_lonlat(lon, lat):
        X, Y = tr.transform(np.asarray(lon), np.asarray(lat))
        # inverse affine (no rotation terms in NAIP)
        col = (np.asarray(X) - c) / a
        row = (np.asarray(Y) - f) / e
        ci = np.clip(np.floor(col).astype(int), 0, rgb.shape[2] - 1)
        ri = np.clip(np.floor(row).astype(int), 0, rgb.shape[1] - 1)
        return np.stack([rgb[0, ri, ci], rgb[1, ri, ci], rgb[2, ri, ci]], axis=-1)

    def sampler(east, north):
        cx, cy = site.enu_to_city(np.asarray(east), np.asarray(north))
        return sample_lonlat(*proj.city_to_lonlat(cx, cy))

    sampler.lonlat = sample_lonlat

    info = {"item": str(z["item"]), "date": str(z["date"]), "shape": list(rgb.shape), "pixelM": float(abs(a))}
    return info, sampler
