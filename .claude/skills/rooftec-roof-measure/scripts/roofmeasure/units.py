"""Units, constants and the attribution text that must travel with the data."""
import math

FT_US = 1200.0 / 3937.0          # US survey foot in metres (EPSG 32164 uses ftUS)
M2_PER_FT2 = FT_US * FT_US
FT2_PER_SQUARE = 100.0
CITY_SRID = 32164                # NAD83 / BLM 14N (ftUS)
CITY_SOLID_CAPTURED = "2023-06"  # layer description: "acquisition date June 2023"
LIDAR_COLLECTION = "SD_EasternSD_3_2020"
LIDAR_CAPTURED = "2020"

ATTRIBUTION_CITY = (
    "Contains data from the City of Sioux Falls, CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/). Changed: converted to roof "
    "planes and measurements. Not a survey."
)
ATTRIBUTION_LIDAR = "Lidar: USGS 3DEP (public domain)."


def m_to_ft(m):
    return m / FT_US


def m2_to_ft2(a):
    return a / M2_PER_FT2


def pitch_in_12(deg):
    return 12.0 * math.tan(math.radians(deg))


def pitch_label(deg):
    """'5.8/12' style label. Whole-number rounding is left to the reader on purpose."""
    return "%.1f/12" % pitch_in_12(deg)
