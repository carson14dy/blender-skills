"""Seed -> house specification. Every random choice comes from ``numpy.random.default_rng(seed)``.

The spec is plain JSON (dicts, lists, floats) so it can be saved next to the scene and rebuilt exactly.
Roof geometry is described as rectangular *wings* in the format of property-model-pipeline's
``propmodel.roofgeom.Wing`` (centre, azimuth of the ridge, length, width, plate height, pitch, overhangs).
"""
from __future__ import annotations

import math

import numpy as np

from . import GENERATOR_VERSION

ROOF_TYPES = ("gable",)          # more types are added in step 3 (hip, dutch_hip, gambrel, mansard, L, T, multi-wing)

# Approximate sRGB colours of common asphalt shingle blends (photos of manufacturer swatches, averaged).
SHINGLE_COLORS = {
    "charcoal": (66, 66, 68), "weathered_wood": (112, 100, 86), "driftwood": (128, 118, 104),
    "onyx_black": (40, 40, 42), "pewter_gray": (106, 108, 110), "barkwood": (90, 72, 58),
    "slate": (86, 94, 104), "hickory": (112, 84, 62), "hunter_green": (60, 74, 60), "shakewood": (126, 106, 84),
}
SIDING_COLORS = {
    "white": (232, 232, 228), "almond": (226, 214, 190), "clay": (196, 182, 160), "gray": (160, 164, 164),
    "pewter": (128, 132, 134), "sage": (150, 160, 136), "wedgewood_blue": (112, 132, 150), "tan": (196, 176, 146),
    "beige": (214, 200, 174), "red_barn": (140, 60, 50),
}
TRIM_COLORS = {"white": (240, 240, 236), "almond": (226, 214, 190), "black": (36, 36, 36), "bronze": (82, 66, 52)}

# Phone main cameras: 35 mm-equivalent focal length and the full-resolution 4:3 sensor output.
PHONES = {
    "iphone_15": {"equiv_mm": 26.0, "full_res": [4032, 3024]},
    "galaxy_s23": {"equiv_mm": 23.0, "full_res": [4000, 3000]},
    "pixel_8": {"equiv_mm": 25.0, "full_res": [4080, 3072]},
}
DRONES = {"mavic_3e": {"equiv_mm": 24.0, "full_res": [5280, 3956]}}

PITCH_WEIGHTS = {3: 0.04, 4: 0.12, 5: 0.15, 6: 0.18, 7: 0.14, 8: 0.12, 9: 0.08, 10: 0.07, 11: 0.04, 12: 0.06}

SCALE_MARKER_M = 0.6096          # 24 in square checkerboard, 8 x 8 squares of 3 in (crews carry one)

# Sioux Falls, SD area: virtual houses get a plausible (made-up) location for the GPS metadata only.
GEO_BOX = {"lat": (43.48, 43.60), "lon": (-96.82, -96.66), "alt": (430.0, 470.0)}


def _choice(rng, options, p=None):
    keys = list(options)
    return keys[int(rng.choice(len(keys), p=p))]


def make_spec(seed: int, house_id: str | None = None, roof_type: str = "gable") -> dict:
    """Return the full specification of one virtual house (deterministic in ``seed``)."""
    if roof_type not in ROOF_TYPES:
        raise NotImplementedError(f"roof type {roof_type!r} is not built yet (available: {ROOF_TYPES})")
    rng = np.random.default_rng(seed)
    house_id = house_id or f"house_{seed:03d}"

    storeys = int(rng.choice([1, 2], p=[0.6, 0.4]))
    if storeys == 1:
        area = rng.uniform(111.0, 223.0)                    # 1200-2400 ft2 on one floor
        plate = rng.uniform(2.90, 3.40)                     # wall plate above grade (incl. 0.3-0.6 m foundation)
    else:
        area = rng.uniform(84.0, 149.0)                     # 900-1600 ft2 per floor
        plate = rng.uniform(5.70, 6.30)
    aspect = rng.uniform(1.3, 2.0)
    width = round(math.sqrt(area / aspect), 2)
    length = round(width * aspect, 2)
    pitch12 = int(_choice(rng, PITCH_WEIGHTS, p=np.array(list(PITCH_WEIGHTS.values())) / sum(PITCH_WEIGHTS.values())))
    eave_oh = round(rng.uniform(0.30, 0.60), 2)
    rake_oh = round(rng.uniform(0.30, 0.60), 2)
    ridge_az = float(rng.choice([0.0, 90.0]))
    if rng.random() < 0.3:
        ridge_az += round(rng.uniform(-20.0, 20.0), 1)
    front_side = str(rng.choice(["+v", "-v"]))            # eave side facing the street (front door, driveway)

    wings = [{
        "id": "A", "type": roof_type, "cx": 0.0, "cy": 0.0, "azimuth": ridge_az % 360.0,
        "length": length, "width": width, "eave_height": round(plate, 2), "pitch": pitch12 / 12.0,
        "eave_overhang": eave_oh, "rake_overhang": rake_oh,
    }]

    ridge_vent = bool(rng.random() < 0.5)
    details = {
        "ridge_vent": ridge_vent,
        "box_vents": 0 if ridge_vent else int(rng.integers(2, 7)),
        "pipe_boots": int(rng.integers(1, 5)),
        "chimneys": 0, "skylights": 0,                      # step 3
    }

    tod = _choice(rng, {"morning": 0, "midday": 0, "afternoon": 0})
    sun_az = {"morning": rng.uniform(95, 140), "midday": rng.uniform(160, 200), "afternoon": rng.uniform(220, 265)}[tod]
    sun_el = {"morning": rng.uniform(15, 35), "midday": rng.uniform(45, 65), "afternoon": rng.uniform(20, 45)}[tod]

    shingle = _choice(rng, SHINGLE_COLORS)
    siding = _choice(rng, SIDING_COLORS)
    trim = _choice(rng, TRIM_COLORS, p=[0.7, 0.15, 0.08, 0.07])
    return {
        "schema": "vhomes.spec/1",
        "generator_version": GENERATOR_VERSION,
        "house_id": house_id,
        "seed": int(seed),
        "roof_type": roof_type,
        "storeys": storeys,
        "front_side": front_side,
        "wings": wings,
        "materials": {
            "shingle_style": _choice(rng, {"architectural": 0, "three_tab": 0}, p=[0.75, 0.25]),
            "shingle_color_name": shingle, "shingle_color": list(SHINGLE_COLORS[shingle]),
            "siding_color_name": siding, "siding_color": list(SIDING_COLORS[siding]),
            "trim_color_name": trim, "trim_color": list(TRIM_COLORS[trim]),
            "gutter_color": list(TRIM_COLORS[trim]) if trim != "black" else [36, 36, 36],
            "siding_exposure_m": float(rng.choice([0.1016, 0.1270, 0.1778])),   # 4, 5, 7 in laps
            "foundation_height_m": round(float(rng.uniform(0.25, 0.55)), 2),
        },
        "details": details,
        "site": {
            "lat": round(float(rng.uniform(*GEO_BOX["lat"])), 6),
            "lon": round(float(rng.uniform(*GEO_BOX["lon"])), 6),
            "ground_alt_m": round(float(rng.uniform(*GEO_BOX["alt"])), 1),
            "lawn_half_size_m": 40.0,
        },
        "lighting": {"time_of_day": tod, "sun_azimuth_deg": round(float(sun_az), 1),
                     "sun_elevation_deg": round(float(sun_el), 1),
                     "air_density": round(float(rng.uniform(0.8, 1.6)), 2),
                     "aerosol_density": round(float(rng.uniform(0.6, 2.5)), 2)},
        "capture": {"phone": _choice(rng, PHONES), "drone": "mavic_3e"},
        "scale_marker_m": SCALE_MARKER_M,
        "trees": [],                                        # step 3: partial occlusion
    }
