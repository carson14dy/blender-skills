"""Shared helpers for the Roof Studio Lab data tools.

The tools reuse the rooftec-roof-measure skill's read-only modules (city REST client, multipatch
decoder, projections, EPT lidar reader) by putting its `scripts/` folder on sys.path. Set
ROOF_MEASURE_SCRIPTS to point somewhere else.

Coordinate frames used everywhere in the lab:
  city   EPSG 32164 (NAD83 / BLM 14N), US survey feet
  enu    local east, north, up in metres around the site origin (site.json)
  scene  the studio's three.js frame for a measured house: x = east, y = up, z = -north (metres),
         i.e. glTF Y-up with north = -Z. The studio then shifts the model so its bounding box is
         centred; site.json records that shift as `studioOffset`.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _skill_scripts():
    """The rooftec-roof-measure scripts folder: $ROOF_MEASURE_SCRIPTS, else a sibling skill, else the repo copy."""
    env = os.environ.get("ROOF_MEASURE_SCRIPTS")
    if env:
        return env
    for cand in (os.path.join(HERE, "..", "..", "rooftec-roof-measure", "scripts"),   # .claude/skills/roof-studio-lab/scripts
                 os.path.join(os.getcwd(), ".claude", "skills", "rooftec-roof-measure", "scripts")):
        if os.path.isdir(os.path.join(cand, "roofmeasure")):
            return os.path.abspath(cand)
    return "/home/user/blender-skills/.claude/skills/rooftec-roof-measure/scripts"


SKILL_SCRIPTS = _skill_scripts()
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)

from roofmeasure import cityapi, esri, lidar, proj  # noqa: E402
from roofmeasure.units import FT_US  # noqa: E402

# LAB_OUT: the lab site folder (index.html, lab/ ...); LAB_CACHE: downloads (keep it out of git: it holds
# city answers and lidar for real addresses). Defaults: ./out and ~/.cache/roof-studio-lab.
CACHE = os.environ.get("LAB_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "roof-studio-lab"))
OUT = os.environ.get("LAB_OUT", os.path.join(os.getcwd(), "out"))
DATA = os.path.join(OUT, "lab", "data")

ATTRIBUTION = ("Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP (public domain). "
               "Imagery: USDA NAIP (public domain).")


def http(log=print):
    return cityapi.Http(log=log)


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------- WGS84 / ECEF / ENU

WGS_A = 6378137.0
WGS_F = 1 / 298.257223563
WGS_E2 = WGS_F * (2 - WGS_F)


def geodetic_to_ecef(lon_deg, lat_deg, h):
    lon, lat = np.radians(lon_deg), np.radians(lat_deg)
    n = WGS_A / np.sqrt(1 - WGS_E2 * np.sin(lat) ** 2)
    return np.stack([(n + h) * np.cos(lat) * np.cos(lon), (n + h) * np.cos(lat) * np.sin(lon),
                     (n * (1 - WGS_E2) + h) * np.sin(lat)], axis=-1)


def enu_to_ecef_matrix(lon_deg, lat_deg, h):
    """4x4 column-major-friendly (numpy row-major here) matrix taking ENU metres to ECEF."""
    lon, lat = math.radians(lon_deg), math.radians(lat_deg)
    e = np.array([-math.sin(lon), math.cos(lon), 0.0])
    n = np.array([-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)])
    u = np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2] = e, n, u
    m[:3, 3] = geodetic_to_ecef(lon_deg, lat_deg, h)
    return m


class Site:
    """The site frame from site.json: model origin in EPSG 32164 feet + NAVD88 metres, and the rotation
    from grid north to the model's north that align_house.py fitted (about the meridian convergence)."""

    def __init__(self, d):
        self.d = d
        self.ox, self.oy = d["originCityFt"]
        self.oz = d["originElevM"]
        self.lon, self.lat = d["originLonLat"]
        self.rot = math.radians(d["gridToModelDeg"])

    @staticmethod
    def load(path=None):
        with open(path or os.path.join(DATA, "site.json")) as f:
            return Site(json.load(f))

    def city_to_enu(self, x_ft, y_ft, z_m=None):
        """City feet (and NAVD88 metres) -> model east, north (, up) in metres."""
        dx = (np.asarray(x_ft, float) - self.ox) * FT_US
        dy = (np.asarray(y_ft, float) - self.oy) * FT_US
        c, s = math.cos(self.rot), math.sin(self.rot)
        e = c * dx - s * dy
        n = s * dx + c * dy
        if z_m is None:
            return e, n
        return e, n, np.asarray(z_m, float) - self.oz

    def enu_to_city(self, e, n):
        c, s = math.cos(self.rot), math.sin(self.rot)
        dx = c * np.asarray(e) + s * np.asarray(n)
        dy = -s * np.asarray(e) + c * np.asarray(n)
        return self.ox + dx / FT_US, self.oy + dy / FT_US

    @staticmethod
    def enu_to_scene(e, n, u):
        return np.stack([np.asarray(e), np.asarray(u), -np.asarray(n)], axis=-1)


def write_json(path, obj, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=indent, separators=None if indent else (",", ":"))
