"""propmodel.regions: profile schema (url, explicit out_fields, never, role, match on every layer; no name /
address / free-text field may be requested) and the --check CLI."""
import copy
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.path.insert(0, TOOL)

from propmodel import features as FT  # noqa: E402
from propmodel import regions  # noqa: E402

PROFILE = os.path.join(HERE, "fixtures", "records", "profile.json")


def prof():
    with open(PROFILE) as f:
        return json.load(f)


def test_fixture_profile_is_valid_and_loads():
    p = regions.load(PROFILE)
    assert p["_path"].endswith("profile.json")
    names = [n for n, _ in regions.iter_layers(p)]
    assert "layers.parcels" in names and "county_sources.Beta.layers.beta_fullsales" in names
    assert "hazards.layers.flood" in names
    assert [n for n, _ in regions.layers_by_role(p, "permits")] == ["permits"]
    assert regions.county_block(p, "alpha")[0] == "Alpha"
    assert regions.county_block(p, "Gamma, Beta")[0] == "Beta"
    assert regions.county_block(p, "Gamma") == (None, None)
    assert FT.load_profile(PROFILE)["name"] == "testland-zz"           # the wrapper's loader reads it too


@pytest.mark.parametrize("field", ["OWNNAME1", "MRTNM1", "contractor_name", "SELLERS_NAME", "DBO.GIS_Parcels.NameADD",
                                   "PropertyOwner", "OWNEDBY"])
def test_forbidden_field_in_out_fields_is_rejected(field):
    p = prof()
    p["layers"]["parcels"]["out_fields"].append(field)
    errs = regions.validate(p)
    assert any(field in e and "forbidden" in e for e in errs), errs
    with pytest.raises(ValueError):
        regions.load(p)


def test_star_free_text_and_never_overlap_are_rejected():
    p = prof()
    p["layers"]["footprints"]["out_fields"] = ["*"]
    p["county_sources"]["Alpha"]["layers"]["alpha_quality"]["out_fields"].append("FORM_COMMENTS")
    p["county_sources"]["Alpha"]["layers"]["alpha_assessed"]["never"].append("TYPE")
    errs = " | ".join(regions.validate(p))
    assert "'*'" in errs and "free-text" in errs and "both in out_fields and never" in errs


def test_required_keys_on_every_layer():
    base = prof()
    for k in ("url", "role", "match", "never", "out_fields"):
        p = copy.deepcopy(base)
        del p["layers"]["permits"][k]
        assert any("layers.permits" in e for e in regions.validate(p)), k
    p = copy.deepcopy(base)
    p["layers"]["permits"]["role"] = "permit"                          # typo
    p["layers"]["permits"]["match"] = ["polygon"]
    errs = regions.validate(p)
    assert any("unknown role" in e for e in errs) and any("unknown match" in e for e in errs)
    p = copy.deepcopy(base)
    del p["county_sources"]["Beta"]["layers"]["beta_fullsales"]["key"]
    assert any("match 'key' needs" in e for e in regions.validate(p))
    p = copy.deepcopy(base)
    p["county_sources"]["Alpha"]["layers"]["alpha_assessed"]["map"]["assessed_land"] = ["MRLNVC"]
    assert any("not in out_fields" in e for e in regions.validate(p))
    p = copy.deepcopy(base)
    p["hazards"]["code_notes"] = [{"text": "IRC 2021"}]                 # a code note needs its source and read date
    assert any("code_notes" in e for e in regions.validate(p))
    p = copy.deepcopy(base)
    del p["layers"]["lidar"]["dataset"]
    assert any("lidar needs" in e for e in regions.validate(p))


def test_check_cli(tmp_path):
    ok = subprocess.run([sys.executable, "-m", "propmodel.regions", "--check", PROFILE], cwd=TOOL,
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "OK" in ok.stdout
    p = prof()
    p["layers"]["parcels"]["out_fields"].append("OWNNAME1")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(p))
    r = subprocess.run([sys.executable, "-m", "propmodel.regions", "--check", str(bad)], cwd=TOOL,
                       capture_output=True, text=True)
    assert r.returncode == 1 and "OWNNAME1" in r.stdout


def test_repo_profiles_are_valid_and_hold_no_house_data():
    d = regions.REGIONS_DIR
    if not os.path.isdir(d):
        pytest.skip("no references/regions folder yet")
    files = [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".json")]
    for f in files:
        assert regions.validate(regions.load(f, validate_schema=False)) == [], f
