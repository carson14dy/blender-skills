"""Region profiles: one JSON file per city / county area, so a new city is one file and no code.

A profile (``references/regions/<name>.json``) holds public endpoints and explicit field lists only: never an
address, a parcel id, a house coordinate or a person's name. Loaded by name (``sioux-falls-sd``) or path.

Schema (validated by :func:`validate`; ``python3 -m propmodel.regions --check FILE``)::

    {
      "name": "city-st", "title": "City, ST", "checked": "YYYY-MM-DD", "state": "ST",
      "counties": ["County A", "County B"],             # list (the wrapper's G0 county check)
      "never_global": ["FIELD", ...],                   # optional: refused on every layer
      "layers": {                                       # city / area layers, by kind
        "<kind>": {
          "url": "https://.../MapServer/N",             # or "geojson" / "file" (local, next to the profile)
          "role": "parcel",                             # ROLES below
          "match": ["point", "key", "address"],         # MATCHES below, tried in order (str or list)
          "out_fields": ["OBJECTID", "TAG", ...],        # explicit; never "*"; no name / address / free text
          "never": ["OWNNAME1", ...],                   # this layer's dangerous fields (exact names)
          "map": {"lot_sqft": "SQFT", "assessed_land": ["MRNLVL", "MRALVL"]},   # canonical -> field(s)
          "key": {"field": "TAG", "from": "parcels.TAG"},         # for match "key"
          "address_where": "MAINADDRESS = '{street}'",            # for match "address" ({street}, {number})
          "label": "City parcels", ...                            # anything else the stage reads
        }
      },
      "county_sources": {                               # assessor / sales / county permits, picked by the
        "<County>": {"match_values": ["MINNEHAHA"],     #   parcel's county field
                     "layers": {"<name>": {...same layer schema...}}}
      },
      "hazards": {"wfo": ["XXX"], "layers": {"flood": {...}}, "code_notes": null},
      "lidar": {"dataset": "...", "year": 2020},        # not a query layer: dataset required
      "ortho": {"url": "...", "attribution": "..."}     # imagery: url required
    }

Per-layer extras read by the stages: ``label``, ``county_field`` (parcels), ``address_field``,
``where_template`` / ``lat_field`` / ``lon_field`` (address points, read by demo_run.py), ``since`` (first date
a permit layer covers), ``reroof_where`` (neighbourhood re-roof count), ``only_outside_city`` (county permits),
``city_field`` / ``city_values`` (address points: inside the city limits), ``year`` (assessment year when the
layer has no year field), ``notes``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .privacy import FREE_TEXT, is_forbidden

HERE = os.path.dirname(os.path.abspath(__file__))
REGIONS_DIR = os.path.join(os.path.dirname(HERE), "references", "regions")

ROLES = {"geocode", "parcel", "footprint", "structure", "permits", "assessor", "quality", "sales", "zoning", "lod2",
         "paving", "sidewalk", "hydrants", "curbs", "streets", "trees", "flood", "imagery", "lidar", "context"}
MATCHES = {"point", "parcel_polygon", "key", "address", "envelope", "none"}
NON_QUERY = {"lidar", "ortho", "imagery", "orthophoto"}      # kinds / roles that are not ArcGIS feature queries
SCOPES = ("layers", "city", "sources")                       # where layer dicts may sit (features.profile_layer)
CANONICAL = {   # names the records / hazards stages understand in a layer "map"
    "year_built", "storeys", "style", "grade", "grade_desc", "condition", "structure", "occupancy",
    "construction", "lot_sqft", "lot_acres", "legal", "land_use", "land_use_code", "zoning", "subdivision",
    "parcel_type", "units", "county", "parcel_key", "county_key", "city", "corner_lot",
    "assessed_land", "assessed_building", "assessed_total", "assessed_year", "assessed_class",
    "sale_date", "sale_year", "sale_price", "sale_class", "sale_type", "sale_desc", "sale_value",
    "permit_number", "permit_type", "work_class", "permit_status", "apply_date", "issue_date", "finalize_date",
    "valuation", "description", "dwelling_units",
    "flood_zone", "flood_subtype", "flood_sfha", "flood_bfe", "flood_panel",
    "ground_elev", "top_elev", "occupied_date", "capture_method", "status"}


def find(ref):
    """Path of a profile given a name or a path."""
    if isinstance(ref, str) and (os.path.sep in ref or ref.endswith(".json")):
        return ref
    return os.path.join(REGIONS_DIR, f"{ref}.json")


def load(ref, validate_schema=True):
    """Profile dict (with ``_path``) by name or path; raises FileNotFoundError, or ValueError listing every
    schema error."""
    if isinstance(ref, dict):
        prof = dict(ref)
        path = prof.get("_path")
    else:
        path = find(ref)
        if not os.path.exists(path):
            raise FileNotFoundError(f"region profile {ref!r} not found (looked for {path})")
        with open(path) as f:
            prof = json.load(f)
        prof["_path"] = os.path.abspath(path)
    if validate_schema:
        errs = validate(prof)
        if errs:
            raise ValueError(f"region profile {path or prof.get('name')}: " + "; ".join(errs))
    return prof


load_profile = load


def iter_layers(profile):
    """(dotted name, layer dict) for every layer in the profile: layers / city / sources, every county's
    layers, and the hazard layers."""
    for scope in SCOPES:
        for k, v in (profile.get(scope) or {}).items() if isinstance(profile.get(scope), dict) else []:
            if isinstance(v, dict):
                yield f"{scope}.{k}", v
    for c, blk in (profile.get("county_sources") or {}).items():
        for k, v in ((blk or {}).get("layers") or {}).items():
            if isinstance(v, dict):
                yield f"county_sources.{c}.layers.{k}", v
    for k, v in ((profile.get("hazards") or {}).get("layers") or {}).items():
        if isinstance(v, dict):
            yield f"hazards.layers.{k}", v


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def validate_layer(name, lay, never_global=()):
    errs = []
    kind = name.rsplit(".", 1)[-1]
    role = lay.get("role")
    if kind in NON_QUERY or role in NON_QUERY:
        if (kind == "lidar" or role == "lidar") and not lay.get("dataset"):
            errs.append(f"{name}: lidar needs 'dataset'")
        if (kind != "lidar" and role != "lidar") and not (lay.get("url") or lay.get("file")):
            errs.append(f"{name}: imagery needs 'url'")
        return errs
    if not (lay.get("url") or lay.get("geojson") or lay.get("file")):
        errs.append(f"{name}: missing 'url' (or 'geojson' / 'file')")
    if not role:
        errs.append(f"{name}: missing 'role'")
    elif role not in ROLES:
        errs.append(f"{name}: unknown role {role!r} (one of {', '.join(sorted(ROLES))})")
    match = _as_list(lay.get("match"))
    if not match:
        errs.append(f"{name}: missing 'match'")
    for m in match:
        if m not in MATCHES:
            errs.append(f"{name}: unknown match {m!r} (one of {', '.join(sorted(MATCHES))})")
    if "never" not in lay or not isinstance(lay.get("never"), list):
        errs.append(f"{name}: missing 'never' list (the layer's name / address fields; [] if it has none)")
    never = list(lay.get("never") or []) + list(never_global or [])
    of = lay.get("out_fields")
    if not isinstance(of, list) or not of or not all(isinstance(x, str) and x.strip() for x in of):
        errs.append(f"{name}: 'out_fields' must be an explicit, non-empty list of field names")
        of = [x for x in (of or []) if isinstance(x, str)] if isinstance(of, list) else []
    lo = {x.lower() for x in of}
    for x in of:
        if "*" in x:
            errs.append(f"{name}: out_fields may not contain '*'")
        elif FREE_TEXT.search(x.rsplit(".", 1)[-1]):
            errs.append(f"{name}: out_fields {x!r} is a free-text field (may hold names)")
        elif is_forbidden(x, never):
            errs.append(f"{name}: out_fields {x!r} is a name / address field (forbidden)")
    for x in lay.get("never") or []:
        if x.lower() in lo:
            errs.append(f"{name}: {x!r} is both in out_fields and never")
    if "key" in match:
        k = lay.get("key") or {}
        if not (isinstance(k, dict) and k.get("field") and k.get("from") and "." in str(k.get("from"))):
            errs.append(f"{name}: match 'key' needs \"key\": {{\"field\": F, \"from\": \"<layer>.<FIELD>\"}}")
        elif str(k["field"]).lower() not in lo:
            errs.append(f"{name}: key field {k['field']!r} is not in out_fields")
    if "address" in match and not (lay.get("address_where") or lay.get("where_template")):
        errs.append(f"{name}: match 'address' needs 'address_where' (e.g. \"ADDRESS = '{{street}}'\")")
    for canon, src in (lay.get("map") or {}).items():
        if canon not in CANONICAL:
            errs.append(f"{name}: map key {canon!r} is not a known name ({', '.join(sorted(CANONICAL))})")
        for f in _as_list(src):
            if str(f).lower() not in lo:
                errs.append(f"{name}: map {canon} -> {f!r} is not in out_fields")
    return errs


def validate(profile):
    """List of schema errors (empty = valid)."""
    errs = []
    if not isinstance(profile, dict):
        return ["profile is not a JSON object"]
    c = profile.get("counties")
    if c is not None and not (isinstance(c, list) and all(isinstance(x, str) for x in c)):
        errs.append("'counties' must be a list of county names")
    for cname, blk in (profile.get("county_sources") or {}).items():
        if not isinstance(blk, dict) or not isinstance(blk.get("layers"), dict):
            errs.append(f"county_sources.{cname}: needs 'layers'")
        if not _as_list((blk or {}).get("match_values")):
            errs.append(f"county_sources.{cname}: needs 'match_values' (the parcel's county field values)")
    hz = profile.get("hazards")
    if hz is not None and not isinstance(hz, dict):
        errs.append("'hazards' must be an object")
    cn = (hz or {}).get("code_notes") if isinstance(hz, dict) else None
    if cn:
        for n in (cn if isinstance(cn, list) else [cn]):
            if not (isinstance(n, dict) and n.get("source_url") and n.get("read_date")):
                errs.append("hazards.code_notes: every note needs 'source_url' and 'read_date' (a human read it)")
    ng = profile.get("never_global") or []
    for name, lay in iter_layers(profile):
        errs += validate_layer(name, lay, ng)
    return errs


def layer(profile, kind):
    """A city layer by kind (``layers`` first, then top level / ``city`` / ``sources``), or None."""
    for scope in (profile.get("layers") or {}, profile, profile.get("city") or {}, profile.get("sources") or {}):
        v = scope.get(kind) if isinstance(scope, dict) else None
        if isinstance(v, dict):
            return v
    return None


def layers_by_role(profile, role, scope="city"):
    """[(name, layer)] with that role. scope: city (layers / city / sources) | hazards | a county name."""
    if scope == "hazards":
        src = ((profile.get("hazards") or {}).get("layers") or {}).items()
    elif scope == "city":
        src = []
        for s in SCOPES:
            if isinstance(profile.get(s), dict):
                src += list(profile[s].items())
    else:
        src = (((profile.get("county_sources") or {}).get(scope) or {}).get("layers") or {}).items()
    return [(k, v) for k, v in src if isinstance(v, dict) and v.get("role") == role]


def county_block(profile, county_value):
    """(name, block) of the county source whose match_values contain ``county_value`` (case-insensitive; a
    "A, B" value tries each part), or (None, None)."""
    if not county_value:
        return None, None
    vals = [v.strip().lower() for v in str(county_value).split(",") if v.strip()]
    for name, blk in (profile.get("county_sources") or {}).items():
        mv = [str(x).lower() for x in _as_list((blk or {}).get("match_values"))] + [name.lower()]
        for v in vals:
            if v in mv:
                return name, blk
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m propmodel.regions")
    ap.add_argument("--check", metavar="FILE", nargs="+", help="validate profile file(s); exit 1 on any error")
    a = ap.parse_args(argv)
    if not a.check:
        ap.print_help()
        return 2
    bad = 0
    for p in a.check:
        try:
            prof = load(p, validate_schema=False)
        except (OSError, ValueError) as e:
            print(f"{p}: cannot read: {e}")
            bad += 1
            continue
        errs = validate(prof)
        n = sum(1 for _ in iter_layers(prof))
        if errs:
            bad += 1
            print(f"{p}: {len(errs)} error(s)")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"{p}: OK ({n} layers, counties: {', '.join((prof.get('county_sources') or {}).keys()) or '-'})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
