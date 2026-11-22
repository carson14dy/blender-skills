import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from propmodel.roofgeom import Wing  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "pm_cli", os.path.join(os.path.dirname(__file__), "..", "scripts", "pm.py"))
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)


def test_wing_notes_lists_labels_and_flags_caveats():
    wings = [Wing(id="M", type="gable", label="main; north rake under canopy: extrapolated, +/-0.5 m",
                  outline=[[0, 0], [10, 0], [10, 8], [0, 8]]),
             Wing(id="G", type="gable", label="garage"),
             {"id": "P", "type": "shed", "label": "porch | assumed pitch"}]
    md = "\n".join(pm.wing_notes_md(wings, caveats=["spec-level note"]))
    assert "## Wings and caveats" in md
    assert "| M | gable | measured outline |" in md
    assert "| G | gable | rectangle | garage |" in md
    assert "porch / assumed pitch" in md            # a '|' in a label must not break the table
    caveat_part = md.split("**Caveats**", 1)[1]
    assert "wing M:" in caveat_part and "wing P:" in caveat_part and "wing G:" not in caveat_part
    assert "- spec-level note" in caveat_part


def test_wing_notes_without_caveats_has_no_caveat_list():
    md = "\n".join(pm.wing_notes_md([Wing(id="A", label="house")]))
    assert "| A |" in md and "**Caveats**" not in md
    assert pm.wing_notes_md([]) == []
