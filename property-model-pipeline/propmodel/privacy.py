"""Privacy rules for every public-record query and every file the toolkit writes about a property.

The toolkit reads public parcel, assessor, permit and sales layers. Those layers also carry names and postal
addresses of people (taxpayers, buyers, sellers, contractors, staff who signed a form). None of that may be
requested, stored or published. Three rules, enforced here:

* :func:`refuse_star` - every query names its fields. ``outFields=*``, an empty list, or a field that looks
  like a name / mailing-address field raises ``ValueError`` before anything is sent.
* :data:`FORBIDDEN` - the field-name pattern (owner, taxpayer, the Minnehaha AS400 ``MRTNM*`` / ``MRTADR`` ...
  block, buyer / seller, contractor, Lincoln ``NameADD`` / ``Add1-3``, ``SIGNEDBY``, mail ...). A region
  profile adds its own exact ``never`` lists (see :mod:`propmodel.regions`).
* :func:`scan` - checks written files: JSON keys (any depth) and the field-like tokens inside JSON string
  values and text files (``OWNNAME1``, ``contractor_name``, ``DBO.GIS_Parcels.Name``). Plain English words
  ("owner", "contractor") in prose are not hits, so a report may say what it leaves out.

CLI (used by scripts/studio/package_house.py on the staged house folder)::

    python3 -m propmodel.privacy scan DIR_OR_FILE [--profile NAME] [--json]

exit 0 = clean, 3 = hits (each printed as ``file: where: key``).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Field-name pattern (case-insensitive). `add[1-3]` only as a whole name part (Lincoln DBO.GIS_Parcels.Add1),
# so ADDITION / ADDRESS1-like names of places are not caught by it.
FORBIDDEN = re.compile(
    r"owner|owned_?by|taxpayer|"
    r"mrtnm|mrtadr|mrtcty|mrtzpc|mrtstate|buyer|seller|contractor|nameadd|"
    r"(?<![a-z])add[1-3](?![a-z0-9])|mail|propertyowner|occupant|reinqaddre",
    re.I)
# OWNNAME1, OWN_NAME, OWNADDRESS, OWNCITY, OWNZIP, OWNEDBY, ownName: "own" must start a name part (start, _ . or a
# camel-case "Own"), so words such as knownNames / TOWNCITY are not hits.
OWN_FAMILY = re.compile(r"(?:(?<![A-Za-z])|(?<=[a-z])(?=O))(?i:own)_?(?i:name|addr|address|city|state|zip|edby)")
# FORM_SIGNEDBY / SignedBy, but not UnsignedByteType / gl.UNSIGNED_BYTE
SIGNED_BY = re.compile(r"(?:(?<![A-Za-z])|(?<=[a-z])(?=S))(?i:signed_?by)(?![A-Za-z])")
# Free-text fields may hold anyone's name: never requested either (narratives, remarks, comments).
FREE_TEXT = re.compile(r"(comments?|remarks?|narratives?|commen|comme)(_?\d+)?$", re.I)
# Prose words that match FORBIDDEN but are not field names when written alone in capitals.
PLAIN_CAPS = {"OWNER", "OWNERS", "BUYER", "BUYERS", "SELLER", "SELLERS", "CONTRACTOR", "CONTRACTORS", "MAIL",
              "EMAIL", "OCCUPANT", "OCCUPANTS", "MAILING"}
TEXT_EXT = (".json", ".md", ".html", ".htm", ".txt", ".csv", ".svg", ".js", ".css", ".xml", ".geojson", ".tsv")
_TOKEN = re.compile(r"(?<![A-Za-z0-9_.])[A-Za-z_][A-Za-z0-9_.]{0,63}(?![A-Za-z0-9_])")
_BLOB = re.compile(r"data:[^\s\"')<>]+|[A-Za-z0-9+/=_-]{120,}")
LONG_STRING = 512


def _parts(name):
    s = str(name)
    return s, s.rsplit(".", 1)[-1]


def is_forbidden(name, never=()):
    """True when a field name looks like a person / mailing-address / free-text field, or is in ``never``
    (exact, case-sensitive, on the full name or its last dotted part)."""
    full, last = _parts(name)
    if FORBIDDEN.search(full) or OWN_FAMILY.search(full) or SIGNED_BY.search(full) or FREE_TEXT.search(last):
        return True
    if not never:
        return False
    nv = {str(n) for n in never}
    nv_last = {n.rsplit(".", 1)[-1] for n in nv}
    return full in nv or last in nv or last in nv_last


def refuse_star(fields, never=()):
    """Explicit field list or ValueError. Accepts a list / tuple (or a comma string, split); refuses ``*``,
    an empty list and any field that :func:`is_forbidden` flags."""
    if fields is None:
        raise ValueError("out_fields is required: name the fields (outFields=* is never sent)")
    if isinstance(fields, str):
        fields = [x.strip() for x in fields.split(",")]
    out = [str(x).strip() for x in fields if str(x).strip()]
    if not out:
        raise ValueError("out_fields must be an explicit, non-empty list of field names")
    if any(x == "*" or "*" in x for x in out):
        raise ValueError("outFields=* is refused: name the fields (name / taxpayer fields must never be requested)")
    bad = [x for x in out if is_forbidden(x, never)]
    if bad:
        raise ValueError(f"refusing to request name / address / free-text fields: {', '.join(bad)}")
    return out


def filter_attrs(attrs, allowed, never=()):
    """Only the requested fields (case-insensitive match), and never a forbidden one, whatever the server sent."""
    want = {str(f).lower(): f for f in (allowed or ())}
    out = {}
    for k, v in (attrs or {}).items():
        if str(k).lower() in want and not is_forbidden(k, never):
            out[k] = v
    return out


# ---------------------------------------------------------------------------------------------- scanning

def _field_like(tok):
    """A token that reads as a field name, not a prose word: has _ . or a digit, mixed inner capitals, or is
    all capitals (except the plain words in PLAIN_CAPS)."""
    if any(c in tok for c in "_.") or any(c.isdigit() for c in tok):
        return True
    if tok.isupper():
        return len(tok) >= 4 and tok not in PLAIN_CAPS
    return any(c.isupper() for c in tok[1:])


def _distinct(never):
    """``never`` entries specific enough to look for inside free text (they contain _ . or a digit); a bare
    word like ``Name`` or ``ADDRESS`` is only checked as a JSON key."""
    return tuple(n for n in (never or ()) if re.search(r"[._0-9]", str(n)))


def tokens_hits(text, never=()):
    """Field-like tokens in free text that are forbidden. Blobs (data: URIs, base64 runs) are skipped."""
    text = _BLOB.sub(" ", text)
    nv = _distinct(never)
    hits = []
    for m in _TOKEN.finditer(text):
        tok = m.group(0).strip(".")
        if tok and _field_like(tok) and is_forbidden(tok, nv):
            hits.append(tok)
    return hits


def _walk_json(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield "key", p, k, v
            yield from _walk_json(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_json(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield "value", path, None, obj


def scan_obj(obj, never=(), label=""):
    """Hits in a decoded JSON value: [{file, where, key, kind}]."""
    hits = []
    for kind, path, key, v in _walk_json(obj):
        if kind == "key":
            if is_forbidden(key, never):
                hits.append({"file": label, "where": path, "key": str(key), "kind": "key",
                             "has_value": v not in (None, "", [], {})})
        else:
            if len(v) > LONG_STRING and not any(c.isspace() for c in v[:LONG_STRING]):
                continue                     # a blob (base64 buffer, data URI)
            for tok in tokens_hits(v, never):
                hits.append({"file": label, "where": path, "key": tok, "kind": "value"})
    return hits


def scan_text(text, never=(), label=""):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for tok in tokens_hits(line, never):
            hits.append({"file": label, "where": f"line {i}", "key": tok, "kind": "text"})
    return hits


def _scan_one(path, never=(), label=None):
    label = label or path
    if not path.lower().endswith(TEXT_EXT):
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    if path.lower().endswith((".json", ".geojson")):
        try:
            return scan_obj(json.loads(text), never, label)
        except ValueError:
            pass
    return scan_text(text, never, label)


def scan(path, never=()):
    """Privacy hits in a file or every text file under a directory: [{file, where, key, kind}].
    ``kind``: key (a JSON key), value (a token in a JSON string), text (a token in a text file)."""
    if os.path.isdir(path):
        hits = []
        for dp, _, fs in os.walk(path):
            for n in sorted(fs):
                p = os.path.join(dp, n)
                hits += _scan_one(p, never, os.path.relpath(p, path))
        return hits
    if not os.path.exists(path):
        return []
    return _scan_one(path, never)


def scan_file(path, never=()):
    """The forbidden keys / tokens found in one file (list of str; empty = clean). Used by
    propmodel.confidence.privacy_scan."""
    return [h["key"] for h in scan(path, never)]


def profile_never(profile):
    """Union of every ``never`` list in a region profile (layers, county sources, hazard layers)."""
    out = set(profile.get("never_global") or []) if isinstance(profile, dict) else set()
    try:
        from . import regions
        for _, lay in regions.iter_layers(profile or {}):
            out.update(lay.get("never") or [])
    except Exception:  # noqa: BLE001 - a broken profile must not stop a scan
        pass
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m propmodel.privacy", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="scan a file or a folder; exit 3 on any hit")
    s.add_argument("path")
    s.add_argument("--profile", help="region profile: its never lists are checked too")
    s.add_argument("--json", action="store_true", help="print the hits as JSON")
    a = ap.parse_args(argv)
    never = ()
    if a.profile:
        from . import regions
        never = profile_never(regions.load(a.profile))
    hits = scan(a.path, never)
    if a.json:
        print(json.dumps(hits, indent=1))
    else:
        for h in hits:
            print(f"{h['file']}: {h['where']}: {h['key']} ({h['kind']})")
        print(f"privacy scan: {'clean' if not hits else str(len(hits)) + ' hit(s)'} ({a.path})")
    return 3 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
