"""Geodesy: WGS84 <-> ECEF <-> local ENU, Web Mercator, small-area helpers.

Accuracy notes
--------------
* ENU is exact (no projection distortion) at the origin and distorts by
  ~d^2/(2R) away from it -> < 1 mm over a 100 m site. Always use a site-local
  ENU frame for modelling; never model directly in lat/lon or Web Mercator.
* Web Mercator (EPSG:3857) coordinates are inflated by 1/cos(lat). At 40 deg N a
  "10 m" distance in 3857 units is really 7.66 m. USGS 3DEP EPT point clouds are
  delivered in EPSG:3857 -> they MUST be converted before measuring.
"""
import math
import numpy as np

A = 6378137.0                 # WGS84 semi-major axis
F = 1.0 / 298.257223563
E2 = F * (2.0 - F)
R_MERC = 6378137.0


def geodetic_to_ecef(lat, lon, h=0.0):
    lat = np.radians(lat)
    lon = np.radians(lon)
    n = A / np.sqrt(1.0 - E2 * np.sin(lat) ** 2)
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (n * (1.0 - E2) + h) * np.sin(lat)
    return x, y, z


def ecef_to_geodetic(x, y, z):
    """Bowring-style iteration; sub-mm after 5 iterations."""
    x, y, z = map(np.asarray, (x, y, z))
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - E2))
    h = 0.0
    for _ in range(6):
        n = A / np.sqrt(1.0 - E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1.0 - E2 * n / (n + h)))
    return np.degrees(lat), np.degrees(lon), h


class LocalFrame:
    """East-North-Up tangent frame anchored at (lat0, lon0, h0)."""

    def __init__(self, lat0, lon0, h0=0.0):
        self.lat0, self.lon0, self.h0 = float(lat0), float(lon0), float(h0)
        self._o = np.array(geodetic_to_ecef(lat0, lon0, h0))
        la, lo = math.radians(lat0), math.radians(lon0)
        self._R = np.array([
            [-math.sin(lo), math.cos(lo), 0.0],
            [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
            [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)],
        ])

    def to_dict(self):
        return {"lat": self.lat0, "lon": self.lon0, "h": self.h0, "frame": "ENU"}

    @classmethod
    def from_dict(cls, d):
        return cls(d["lat"], d["lon"], d.get("h", 0.0))

    def from_geodetic(self, lat, lon, h=None):
        lat = np.asarray(lat, float)
        lon = np.asarray(lon, float)
        h = np.full_like(lat, self.h0) if h is None else np.asarray(h, float)
        x, y, z = geodetic_to_ecef(lat, lon, h)
        d = np.stack([x - self._o[0], y - self._o[1], z - self._o[2]], axis=0)
        enu = np.tensordot(self._R, d, axes=1)
        return enu[0], enu[1], enu[2]

    def to_geodetic(self, e, n, u=0.0):
        e, n, u = np.broadcast_arrays(np.asarray(e, float), np.asarray(n, float), np.asarray(u, float))
        d = np.tensordot(self._R.T, np.stack([e, n, u]), axes=1)
        return ecef_to_geodetic(d[0] + self._o[0], d[1] + self._o[1], d[2] + self._o[2])

    def ring_from_lonlat(self, ring):
        """[[lon,lat],...] -> [[x,y],...] (metres, ENU)."""
        arr = np.asarray(ring, float)
        x, y, _ = self.from_geodetic(arr[:, 1], arr[:, 0])
        return np.stack([x, y], axis=1).tolist()

    def ring_to_lonlat(self, ring):
        arr = np.asarray(ring, float)
        lat, lon, _ = self.to_geodetic(arr[:, 0], arr[:, 1], 0.0)
        return np.stack([lon, lat], axis=1).tolist()


def mercator_to_lonlat(x, y):
    lon = np.degrees(np.asarray(x) / R_MERC)
    lat = np.degrees(2.0 * np.arctan(np.exp(np.asarray(y) / R_MERC)) - math.pi / 2.0)
    return lon, lat


def lonlat_to_mercator(lon, lat):
    x = np.radians(np.asarray(lon)) * R_MERC
    y = R_MERC * np.log(np.tan(math.pi / 4.0 + np.radians(np.asarray(lat)) / 2.0))
    return x, y


def mercator_scale(lat):
    """Web-Mercator units per true metre at latitude ``lat``."""
    return 1.0 / math.cos(math.radians(lat))


def bbox_lonlat(frame, half_size_m):
    """Lon/lat bbox (minlon, minlat, maxlon, maxlat) of a square around the origin."""
    lat, lon, _ = frame.to_geodetic([-half_size_m, half_size_m], [-half_size_m, half_size_m], 0.0)
    return float(lon[0]), float(lat[0]), float(lon[1]), float(lat[1])


def polygon_area(ring):
    """Signed shoelace area of [[x,y],...] (CCW positive)."""
    a = np.asarray(ring, float)
    if np.allclose(a[0], a[-1]):
        a = a[:-1]
    x, y = a[:, 0], a[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
