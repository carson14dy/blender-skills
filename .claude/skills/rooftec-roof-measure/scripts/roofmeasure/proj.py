"""Map projections needed by the skill, in plain numpy (no pyproj needed).

* EPSG 32164 (NAD83 / BLM 14N, US survey feet) <-> longitude, latitude
* EPSG 3857 (Web Mercator, the lidar EPT's system) <-> longitude, latitude

Transverse Mercator uses the Krueger series (Karney 2011, order n^4), which is
accurate to well under a millimetre inside a UTM zone. NAD83 and WGS84 are
treated as the same datum, as PROJ does by default; the real offset is about
1 m, and the lidar module measures the leftover shift per house.
"""
import numpy as np
from .units import FT_US

_A = 6378137.0
_F = 1 / 298.257222101        # GRS80
_K0 = 0.9996
_LON0 = np.radians(-99.0)     # UTM / BLM zone 14
_FE_M = 500000.0

_n = _F / (2 - _F)
_A1 = _A / (1 + _n) * (1 + _n**2 / 4 + _n**4 / 64)
_ALPHA = [
    _n / 2 - 2 * _n**2 / 3 + 5 * _n**3 / 16 + 41 * _n**4 / 180,
    13 * _n**2 / 48 - 3 * _n**3 / 5 + 557 * _n**4 / 1440,
    61 * _n**3 / 240 - 103 * _n**4 / 140,
    49561 * _n**4 / 161280,
]
_BETA = [
    _n / 2 - 2 * _n**2 / 3 + 37 * _n**3 / 96 - _n**4 / 360,
    _n**2 / 48 + _n**3 / 15 - 437 * _n**4 / 1440,
    17 * _n**3 / 480 - 37 * _n**4 / 840,
    4397 * _n**4 / 161280,
]
_E = np.sqrt(_F * (2 - _F))


def lonlat_to_city(lon, lat):
    """Degrees -> EPSG 32164 easting, northing in US survey feet."""
    lon = np.radians(np.asarray(lon, float))
    lat = np.radians(np.asarray(lat, float))
    s = np.sin(lat)
    t = np.sinh(np.arctanh(s) - _E * np.arctanh(_E * s))
    dl = lon - _LON0
    xi = np.arctan2(t, np.cos(dl))
    eta = np.arctanh(np.sin(dl) / np.sqrt(1 + t * t))
    x, y = eta.copy(), xi.copy()
    for j, a in enumerate(_ALPHA, 1):
        y = y + a * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        x = x + a * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    return (_FE_M + _K0 * _A1 * x) / FT_US, (_K0 * _A1 * y) / FT_US


def city_to_lonlat(e_ft, n_ft):
    """EPSG 32164 feet -> longitude, latitude in degrees."""
    xi = np.asarray(n_ft, float) * FT_US / (_K0 * _A1)
    eta = (np.asarray(e_ft, float) * FT_US - _FE_M) / (_K0 * _A1)
    xi0, eta0 = xi.copy(), eta.copy()
    for j, b in enumerate(_BETA, 1):
        xi0 = xi0 - b * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        eta0 = eta0 - b * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    chi = np.arcsin(np.sin(xi0) / np.cosh(eta0))
    lon = _LON0 + np.arctan2(np.sinh(eta0), np.cos(xi0))
    # conformal latitude -> geodetic latitude by fixed-point iteration
    lat = chi.copy()
    for _ in range(8):
        es = _E * np.sin(lat)
        lat = 2 * np.arctan(np.tan(np.pi / 4 + chi / 2) * ((1 + es) / (1 - es)) ** (_E / 2)) - np.pi / 2
    return np.degrees(lon), np.degrees(lat)


_R = 6378137.0


def webmerc_to_lonlat(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    return np.degrees(x / _R), np.degrees(2 * np.arctan(np.exp(y / _R)) - np.pi / 2)


def lonlat_to_webmerc(lon, lat):
    lon = np.radians(np.asarray(lon, float))
    lat = np.radians(np.asarray(lat, float))
    return _R * lon, _R * np.log(np.tan(np.pi / 4 + lat / 2))


def webmerc_to_city(x, y):
    return lonlat_to_city(*webmerc_to_lonlat(x, y))


def city_to_webmerc(e_ft, n_ft):
    return lonlat_to_webmerc(*city_to_lonlat(e_ft, n_ft))


def grid_convergence_deg(lon, lat):
    """Angle from true north to grid north (degrees, east positive). About +1.6 deg in Sioux Falls."""
    return float(np.degrees(np.arctan(np.tan(np.radians(lon) - _LON0) * np.sin(np.radians(lat)))))
