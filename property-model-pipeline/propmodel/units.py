"""Unit and roof-pitch conversions. Internal unit is always the metre."""
import math

M_PER_FT = 0.3048
M_PER_IN = 0.0254
SQFT_PER_SQM = 1.0 / (M_PER_FT ** 2)
SQFT_PER_SQUARE = 100.0  # roofing "square"


def ft(m):
    return m / M_PER_FT


def m_from_ft(f):
    return f * M_PER_FT


def sqft(m2):
    return m2 * SQFT_PER_SQM


def squares(m2):
    return sqft(m2) / SQFT_PER_SQUARE


def pitch_to_slope(rise_per_12):
    """6 (i.e. 6/12) -> 0.5 rise/run."""
    return rise_per_12 / 12.0


def slope_to_pitch(slope):
    return slope * 12.0


def slope_to_deg(slope):
    return math.degrees(math.atan(slope))


def deg_to_slope(deg):
    return math.tan(math.radians(deg))


def pitch_to_deg(rise_per_12):
    return slope_to_deg(pitch_to_slope(rise_per_12))


def deg_to_pitch(deg):
    return slope_to_pitch(deg_to_slope(deg))


def slope_factor(slope):
    """True-area / plan-area multiplier for a plane of given rise/run."""
    return math.sqrt(1.0 + slope * slope)


def parse_pitch(value):
    """Accept 6, '6', '6/12', '6:12', '26.6deg', '26.6°' -> rise/run slope."""
    if isinstance(value, (int, float)):
        return pitch_to_slope(float(value))
    s = str(value).strip().lower().replace(" ", "")
    if s.endswith("deg") or s.endswith("°"):
        return deg_to_slope(float(s.rstrip("deg°")))
    for sep in ("/", ":", "in"):
        if sep in s:
            a, b = s.split(sep, 1)
            return float(a) / float(b)
    return pitch_to_slope(float(s))


def fmt_pitch(slope):
    return f"{slope_to_pitch(slope):.1f}/12"


def parse_length(value):
    """Parse '24ft', "24'6\"", '7.3m', '18in', 7.3 (assumed metres) -> metres."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower().replace(" ", "")
    if s.endswith("mm"):
        return float(s[:-2]) / 1000.0
    if s.endswith("cm"):
        return float(s[:-2]) / 100.0
    if s.endswith("m"):
        return float(s[:-1])
    if "'" in s or '"' in s:
        feet, inches = 0.0, 0.0
        if "'" in s:
            a, s = s.split("'", 1)
            feet = float(a) if a else 0.0
        s = s.replace('"', "")
        if s:
            inches = float(s)
        return feet * M_PER_FT + inches * M_PER_IN
    if s.endswith("ft"):
        return float(s[:-2]) * M_PER_FT
    if s.endswith("in"):
        return float(s[:-2]) * M_PER_IN
    return float(s)
