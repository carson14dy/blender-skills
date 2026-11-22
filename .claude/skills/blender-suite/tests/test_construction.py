"""Construction kit and finish (construction_kit.py, construction_finish.py): the plan's hand-worked vectors,
plan counts against the built scene, refusals, and a clean qa_check on the whole shed."""
import copy
import json
import math

import bpy
from run_all import TMP, skill_module

SPEC = {"name": "Test shed", "prefix": "Shed", "units": "ft", "footprint": [10, 12], "wall_height": 8,
        "pad": {"thickness_in": 4, "margin_in": 2}, "site": {"ground_snow_psf": 55},
        "framing": {"stud": "2x4", "oc_in": 16, "rafter": "2x6", "rafter_oc_in": 24, "ridge": "1x8", "header": "2x6"},
        "roof": {"pitch": "6/12", "pitch_source": "pitch.json", "overhang_eave_in": 6, "overhang_rake_in": 6,
                 "exposure_in": 5.625, "ice_barrier": False, "ridge_vent": False},
        "siding": {"board_in": 8.25, "exposure_in": 7, "thickness_in": 0.3125, "color": "#9CAF88"},
        "trim": {"corner_in": 3.5, "casing_in": 3.5, "fascia": "1x8", "rake": "1x8", "color": "#FFFFFF"},
        "openings": [{"wall": "front", "type": "door", "center_ft": 5, "width_in": 36, "height_in": 80, "panels": 6}] +
                    [{"wall": w, "type": "window", "center_ft": c, "sill_in": 44, "width_in": 24, "height_in": 36}
                     for w in ("left", "right") for c in (4, 8)]}
PITCH = {"ok": True, "method": "rule", "rise_per_12": 6.0, "sigma_per_12": 0.0, "nearest_whole": "6/12",
         "whole_within_2_sigma": True, "label": "6/12 (design rule)", "confidence": "ok"}


def _ck():
    return skill_module("blender-suite", "construction_kit")


def _spec(name="building.json", **change):
    s = copy.deepcopy(SPEC)
    for k, v in change.items():
        if isinstance(v, dict):
            s[k] = {**s.get(k, {}), **v}
        else:
            s[k] = v
    (TMP / "pitch.json").write_text(json.dumps(PITCH))
    (TMP / name).write_text(json.dumps(s))
    return str(TMP / name)


def _kinds(members):
    out = {}
    for m in members:
        k = m[0].split("_")[0] + ("E" if m[0].endswith("_E") else "")
        out[k] = out.get(k, 0) + 1
    return out


def test_wall_without_openings():
    """144 in. x 96 in., 16 in. o.c.: 2 end studs + layout at 16 to 128 = 10 studs of 91.5 in.; 1 bottom, 2 top plates."""
    m = _ck().frame_wall(144, 96, 16, [])
    k = _kinds(m)
    studs = [x for x in m if x[0].startswith("Stud")]
    assert k.get("Stud", 0) + k.get("StudE", 0) == 10, k
    assert sorted(round((x[1] + x[2]) / 2, 3) for x in studs if not x[0].endswith("_E")) == [16 * i for i in range(1, 9)]
    assert all(abs(x[4] - x[3] - 91.5) < 1e-9 for x in studs)
    assert [x[0] for x in m].count("Plate_{w}_B") == 1 and [x[0] for x in m].count("Plate_{w}_T") == 2


def test_wall_with_a_door():
    """113 in. wall, 36 x 80 door centred: rough opening 38 in. (37.5 to 75.5); layout 16, 32, 80, 96 stay,
    48 and 64 become cripples, 112 touches the end stud and is dropped."""
    ck = _ck()
    m = ck.frame_wall(113, 96, 16, [ck.ro({"type": "door", "center_ft": 5, "width_in": 36, "height_in": 80}, "front", 3.5)])
    k = _kinds(m)
    layout = sorted((x[1] + x[2]) / 2 for x in m if x[0] == "Stud_{w}_")
    assert layout == [16, 32, 80, 96], layout
    assert k["Stud"] + k["StudE"] + k["King"] == 8 and k["Jack"] == 2 and k["Cripple"] == 2, k
    assert k["Header"] == 2 and k["Plate"] == 4, k                     # 2 bottom pieces + 2 top plates
    assert sorted((x[1] + x[2]) / 2 for x in m if x[0] == "Cripple_{w}_") == [48, 64]
    jacks = sorted(x[1] for x in m if x[0] == "Jack_{w}_")
    assert jacks == [36, 75.5] and all(x[4] == 82.5 for x in m if x[0] == "Jack_{w}_")


def test_plan_matches_the_rules():
    """Roof 144 in. long, 24 in. o.c., 6 in. rake overhang: 7 pairs + 2 barge pairs = 18 rafters. The ridge runs out
    to the barge rafters: 144 + 2 x (6 - 0.75 in. rake board) = 154.5 in. (the plan said 156, which ends it at
    the rake board's face). Siding at 7 in.: 14 courses on the eave walls, as on a 96 in. wall."""
    r = _ck().run(plan=_spec())
    c, chk = r["counts"], {x["id"]: x for x in r["checks"]}
    assert c["Shed_Rafter_*"] == 18 and c["Shed_Rafter_Barge_*"] == 4 and c["Shed_Rafter_[0-9]*"] == 14
    assert chk["size-ridge"]["expect"] == [0.75, 7.25, 154.5], chk["size-ridge"]
    covered = 96 - 1 - (0.4375 + 0.3125 * 8.25 / 7 + 0.3125 + 3.5) * 0.5 - 0.25 * math.hypot(1, 0.5)
    assert math.ceil(96 / 7) == 14 == math.ceil(covered / 7) == c["Shed_Siding_left_*_1"], (covered, c)
    assert c["Shed_Tie_*"] == 5 and c["Shed_Stud_front_*"] == 6 and c["Shed_Stud_back_*"] == 8
    assert c["Shed_Window_*_Frame_Head"] == 4 and c["Shed_Trim_Corner_*"] == 8
    assert chk["size-stud-front"]["expect"] == [1.5, 3.5, 91.5]
    assert all(x["source"] in ("standard", "given") for x in r["checks"])


def test_built_scene_matches_the_plan_and_oc_changes_both():
    ck, cf, ac = _ck(), skill_module("blender-suite", "construction_finish"), skill_module("blender-suite",
                                                                                      "acceptance_check")
    for oc, name in ((16, "b16.json"), (24, "b24.json")):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        path = _spec(name, framing={"oc_in": oc})
        plan = ck.run(plan=path)
        assert ck.run(build=path, only=["pad", "walls", "roof_frame", "sheathing"])["ok"]
        assert cf.run(build=path)["ok"]
        acc = TMP / f"acc{oc}.json"
        acc.write_text(json.dumps({"name": "t", "units": "in", "checks": plan["checks"], "forbid": {"scope": "Shed_*"}}))
        res = ac.run(accept=str(acc))   # (the Roof planes have no material: roof_core hides them once it roofs)
        assert res["pass"], ([x for x in res["results"] if not x["pass"]][:3], res["forbidden"])
        if oc == 16:
            n16 = plan["counts"]["Shed_Stud_back_*"]
    assert plan["counts"]["Shed_Stud_back_*"] == 6 < n16 == 8   # 113 in.: layout at 24..96 + 2 end studs


def test_linked_duplicates():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    r = _ck().run(build=_spec(), only=["walls"])
    assert r["meshes"] < r["parts"] / 3, r
    studs = [o for o in bpy.data.objects if o.name.startswith("Shed_Stud_back_")]
    assert len({o.data.name for o in studs}) == 1


def test_refusals():
    ck = _ck()
    for change, words in (({"roof": {"pitch_source": None}}, "pitch_source is missing"),
                          ({"roof": {"type": "hip"}}, "gable roofs only"),
                          ({"footprint": [[0, 0], [10, 0], [10, 12], [0, 12], [0, 6]]}, "rectangles only"),
                          ({"roof": {"pitch": "8/12"}}, "does not match"),
                          ({"framing": {"header": "2x4"}}, "R602.7(1)"),
                          ({"site": {"ground_snow_psf": 90}}, "70 psf"),
                          ({"trim": {"fascia": "1x6"}}, "fascia")):
        try:
            ck.run(plan=_spec("bad.json", **change))
        except ck.Bad as e:
            assert words in str(e), (change, str(e))
        else:
            raise AssertionError(f"{change} was accepted")


def test_built_shed_passes_qa():
    """The whole shed (with roof_core's layers when the repo has it): qa_check complete, 0 errors."""
    ck, cf, qa = _ck(), skill_module("blender-suite", "construction_finish"), skill_module("blender-suite", "qa_check")
    path = _spec()
    r = ck.run(build=path)
    cf.run(build=path)
    obs = [o.name for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render]
    res = qa.run(objects=obs, profile="render", max_tris=0)
    assert res["complete"] and not res["errors"], res["errors"][:5]
    if r["notes"] and r["notes"][0].startswith("roofing:"):
        assert {o.get("rt_layer") for o in bpy.data.objects if o.get("rt_layer")} == \
            {"deck", "dripEdge", "underlayment", "starter", "nails", "covering", "ridgeCap"}   # no ice, vent, repair
