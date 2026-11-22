"""propmodel — measurement-grade property modeling toolkit.

Everything inside this package works in a *local metric frame*:
  x = East (m), y = North (m), z = Up (m), origin = site origin on the ground.
Conversion to/from WGS84 lives in :mod:`propmodel.geo`. Unit conversion for
reports lives in :mod:`propmodel.units`.
"""
__version__ = "0.1.0"
