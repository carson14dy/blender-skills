"""propmodel.privacy: field refusal, the FORBIDDEN pattern, and the scan of written files / folders."""
import base64
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)

from propmodel import confidence as C  # noqa: E402
from propmodel import privacy as P  # noqa: E402

DANGEROUS = ["OWNNAME1", "OWNNAME2", "OWNADDRESS", "OWNCITY", "OWNZIP2", "OWNEROCCSTATUS", "OWNEDBY", "OWN_NAME",
             "MRTNM1", "MRTNM2", "MRTADR", "MRTCTY", "MRTSTATE", "MRTZPC", "MRTZPC2", "SELLERS_NAME", "BUYERS_NAME",
             "contractor_name", "PropertyOwner", "DBO.GIS_Parcels.NameADD", "DBO.GIS_Parcels.Add1", "Add2",
             "FORM_SIGNEDBY", "FORM_COMMENTS", "Remarks", "EVENT_NARRATIVE", "DBO.GIS_Parcels.ReInqAddre", "EMAIL"]
SAFE = ["OBJECTID", "TAG", "COUNTYID", "ADDITION", "ACREAGE", "SQFT", "LEGAL", "LANDUSE", "WORKCLASS", "ISSUEDATE",
        "MRLNVC", "MRBDVC", "MRTOTC", "MRNLVL", "TOTAL", "House_desc", "Grade_desc", "DBO.Parcel.PID",
        "DBO.GIS_Parcels.Value1", "SALE_PRICE", "FLD_ZONE", "NUMBERSTORIES", "OCCUPANCY", "name", "url", "fields"]


@pytest.mark.parametrize("f", DANGEROUS)
def test_dangerous_fields_are_forbidden(f):
    assert P.is_forbidden(f)
    with pytest.raises(ValueError):
        P.refuse_star(["OBJECTID", f])


@pytest.mark.parametrize("f", SAFE)
def test_safe_fields_pass(f):
    assert not P.is_forbidden(f)


def test_refuse_star_and_empty():
    for bad in ("*", ["*"], ["OBJECTID", "*"], [], None, "", ["  "]):
        with pytest.raises(ValueError):
            P.refuse_star(bad)
    assert P.refuse_star("OBJECTID, TAG") == ["OBJECTID", "TAG"]
    assert P.refuse_star(["OBJECTID", "TAG"]) == ["OBJECTID", "TAG"]
    with pytest.raises(ValueError):                      # a profile never-list entry is refused too
        P.refuse_star(["OBJECTID", "NAME"], never=["NAME"])


def test_filter_attrs_keeps_only_requested_and_never_forbidden():
    got = P.filter_attrs({"OBJECTID": 1, "tag": "x", "OWNNAME1": "p", "contractor_name": "c"},
                         ["OBJECTID", "TAG", "contractor_name"])
    assert got == {"OBJECTID": 1, "tag": "x"}


def test_scan_finds_planted_keys_and_tokens_but_not_prose(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"parcel": {"ACREAGE": 0.2}, "note": "Names of owners, buyers, sellers and the "
                                "contractor are never requested. Ask the OWNER about the porch."}))
    assert P.scan(str(good)) == []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"rows": [{"OWNNAME1": "x"}, {"MRTADR": "y"}, {"contractor_name": "z"}],
                               "sources": [{"fields": ["OBJECTID", "SELLERS_NAME"]}]}))
    hits = P.scan(str(bad))
    assert sorted(h["key"] for h in hits) == ["MRTADR", "OWNNAME1", "SELLERS_NAME", "contractor_name"]
    assert {h["kind"] for h in hits} == {"key", "value"}
    md = tmp_path / "sec.md"
    md.write_text("## Records\nThe owner input is pending.\n| DBO.GIS_Parcels.Name | x |\nfield MRTNM1 leaked\n")
    keys = [h["key"] for h in P.scan(str(md), never=["DBO.GIS_Parcels.Name"])]
    assert keys == ["DBO.GIS_Parcels.Name", "MRTNM1"]


def test_scan_skips_blobs(tmp_path):
    blob = base64.b64encode(os.urandom(300000)).decode()
    (tmp_path / "m.gltf.json").write_text(json.dumps({"buffers": [{"uri": "data:application/octet-stream;base64," + blob}]}))
    (tmp_path / "d.svg").write_text(f'<svg><image href="data:image/png;base64,{blob}"/></svg>')
    assert P.scan(str(tmp_path)) == []


def test_confidence_privacy_scan_uses_this_module(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"rows": [{"OWNNAME1": "x"}, {"MRTADR": "y"}, {"contractor_name": "z"}]}))
    assert sorted(k for _, k in C.privacy_scan([str(bad)])) == ["MRTADR", "OWNNAME1", "contractor_name"]
    assert P.scan_file(str(bad)) == ["OWNNAME1", "MRTADR", "contractor_name"]


def test_cli_exit_codes(tmp_path):
    d = tmp_path / "site"
    d.mkdir()
    (d / "detail.json").write_text(json.dumps({"records": {"year_built": 1978}}))
    run = lambda: subprocess.run([sys.executable, "-m", "propmodel.privacy", "scan", str(d)], cwd=TOOL,
                                 capture_output=True, text=True)
    r = run()
    assert r.returncode == 0 and "clean" in r.stdout
    (d / "leak.json").write_text(json.dumps({"BUYERS_NAME": "x"}))
    r = run()
    assert r.returncode == 3 and "BUYERS_NAME" in r.stdout


def test_prose_and_code_identifiers_are_not_hits():
    for tok in ("knownNames", "knownNames.has", "TOWNCITY", "townCity", "DOWNTOWN", "unknownAddress", "addition1",
                "ADDITIONNUM", "GmailLink"[:0] or "domain"):
        assert not P.is_forbidden(tok), tok
    assert P.tokens_hits("const knownNames = new Set(); if (knownNames.has(n)) {}") == []
    for tok in ("ownName", "PropOwnName", "OWN_NAME", "OWNZIP2"):
        assert P.is_forbidden(tok), tok
