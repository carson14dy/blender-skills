"""Construction kit and finish (construction_kit.py, construction_finish.py): the plan's hand-worked vectors,
plan counts against the built scene, refusals, and a clean qa_check on the whole shed."""
import copy
import json
import math

import bpy
from run_all import TMP, skill_module

SPEC = {"name": "Test shed", "prefix": "Shed", "units": "ft", "building": "accessory", "footprint": [10, 12], "wall_height": 8,
        "pad": {"thickness_in": 4}, "site": {"ground_snow_psf": 55},
        "framing": {"stud": "2x4", "oc_in": 16, "rafter": "2x6", "rafter_oc_in": 24, "ridge": "1x8", "header": "2x6"},
        "roof": {"pitch": "6/12", "pitch_source": "pitch.json", "overhang_eave_in": 6, "overhang_rake_in": 6,
                 "exposure_in": 5.625, "ice_barrier": False, "ridge_vent": False},
        "siding": {"board_in": 8.25, "exposure_in": 7, "thickness_in": 0.3125, "color": "#9CAF88"},
        "trim": {"corner_in": 3.5, "casing_in": 3.5, "fascia": "1x8", "rake": "1x8", "color": "#FFFFFF"},
        "openings": [{"wall": "front", "type": "door", "center_ft": 5, "width_in": 36, "height_in": 80, "panels": 6,
                      "swing": "out", "hinges": "left", "knob_in": 36}] +
                    [{"wall": w, "type": "window", "center_ft": c, "sill_in": 44, "width_in": 24, "height_in": 36}
                     for w in ("left", "right") for c in (4, 8)]}
PITCH = {"ok": True, "method": "rule", "rise_per_12": 6.0, "sigma_per_12": 0.0, "nearest_whole": "6/12",
         "whole_within_2_sigma": True, "label": "6/12 (design rule)", "confidence": "ok"}


def _ck():
    return skill_module("blender-suite", "construction_kit")


def _cx():
    return skill_module("blender-suite", "construction_extras")


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
    the rake board's face). Siding at 7 in.: 14 courses on the eave walls, as on a 96 in. wall (from 1 in. below
    the plate to the soffit: 96 + 1 - 2.59 = 94.41 in.)."""
    r = _ck().run(plan=_spec())
    c, chk = r["counts"], {x["id"]: x for x in r["checks"]}
    assert c["Shed_Rafter_*"] == 18 and c["Shed_Rafter_Barge_*"] == 4 and c["Shed_Rafter_[0-9]*"] == 14
    assert chk["size-ridge"]["expect"] == [0.75, 7.25, 154.5], chk["size-ridge"]
    covered = 96 + 1 - (0.4375 + 0.3125 * 8.25 / 7 + 0.3125 + 3.5) * 0.5 - 0.25 * math.hypot(1, 0.5)
    assert math.ceil(96 / 7) == 14 == math.ceil(covered / 7) == c["Shed_Siding_left_*_1"], (covered, c)
    # gable walls pull their layout from the sheathing corner (-7/16 in.), so panel joints at 47.56 and 95.56 in.
    # land on studs: back wall 2 end + 7 layout = 9
    assert c["Shed_Tie_*"] == 5 and c["Shed_Stud_front_*"] == 6 and c["Shed_Stud_back_*"] == 9
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
        assert cf.run(build=path)["ok"] and _cx().run(build=path)["ok"]
        acc = TMP / f"acc{oc}.json"
        acc.write_text(json.dumps({"name": "t", "units": "in", "checks": plan["checks"], "forbid": {"scope": "Shed_*"}}))
        res = ac.run(accept=str(acc))   # (the Roof planes have no material: roof_core hides them once it roofs)
        assert res["pass"], ([x for x in res["results"] if not x["pass"]][:3], res["forbidden"])
        if oc == 16:
            n16 = plan["counts"]["Shed_Stud_back_*"]
    assert plan["counts"]["Shed_Stud_back_*"] == 6 < n16 == 9   # 24 in. from the corner: 4 layout + 2 end studs


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
    _cx().run(build=path)
    obs = [o.name for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render]
    res = qa.run(objects=obs, profile="render", max_tris=0)
    assert res["complete"] and not res["errors"], res["errors"][:5]
    low = min((o.matrix_world @ v.co).z for o in bpy.data.objects if o.name.startswith(("Shed_Siding", "Shed_Starter"))
              for v in o.data.vertices) / 0.0254
    plate = min(o.matrix_world.translation.z for o in bpy.data.objects if o.name.startswith("Shed_Plate")) / 0.0254
    assert abs(plate - 4) < 1e-6 and abs(low - 3) < 1e-6, (low, plate)   # the siding laps 1 in. below the plate
    if r["notes"] and r["notes"][0].startswith("roofing:"):
        assert {o.get("rt_layer") for o in bpy.data.objects if o.get("rt_layer")} == \
            {"deck", "dripEdge", "underlayment", "starter", "nails", "covering", "ridgeCap"}   # no ice, vent, repair
        # 12 nail rows a plane (73.79 in. slope) x 16 nails (156 in. at 9.84 in., 4 cm margins) x 2 planes = 384
        assert len(bpy.data.objects["RT_layer_nails"].data.polygons) == 384 * 10


def test_design_rules_fill_the_gaps():
    """Values building.json leaves out come from the user's approved rules and are reported, not assumed."""
    rules = {"approved_by": "user", "approved_on": "2026-11-22", "overhang_in": {"accessory": {"eave": 6, "rake": 6}},
             "layout": {"pad_margin_in": 0, "windows": "equally spaced along their wall", "window_head":
                        "level with the door head", "door_knob_in": 36, "door_color": "matches the trim"},
             "doors": {"accessory": {"style": "6-panel", "swing": "out", "hinges": "left, seen from outside"}}}
    (TMP / "rules.json").write_text(json.dumps(rules))
    s = copy.deepcopy(SPEC)
    s["rules"], s["roof"] = "rules.json", {k: v for k, v in s["roof"].items() if not k.startswith("overhang")}
    s["openings"] = [{k: v for k, v in o.items() if k in ("wall", "type", "width_in", "height_in")} for o in s["openings"]]
    s["openings"][0]["center_ft"] = 5
    (TMP / "pitch.json").write_text(json.dumps(PITCH))
    (TMP / "ruled.json").write_text(json.dumps(s))
    ck = _ck()
    s2, G = ck.load(str(TMP / "ruled.json"))
    win = [o for o in s2["openings"] if o["type"] == "window"]
    assert [o["center_ft"] for o in win] == [4, 8, 4, 8] and {o["sill_in"] for o in win} == {80 + 2.25 - 36}
    assert G["ove"] == 6 and s2["openings"][0]["swing"] == "out" and s2["openings"][0]["panels"] == 6
    assert len(G["rules"]) == 16 and all("design rule" in x for x in G["rules"])   # 2 overhangs, pad, 5 door, 8 window


def test_extras_by_rule():
    """Back gable wall, no openings: item 17 end nails 9 studs x 2 ends x 2 = 36; item 13 top plate 16d at 16 in.
    from 8 in.: 8, 24 .. 104 = 7; item 18 corner laps 2 x 2 = 4; gable studs 7 x 3 toe nails = 21: 68 in all.
    Lookouts 24 in. along the rake from 12 in.: 12, 36, 60 in. (54.4 in. < the ridge face at 59.6) = 3 a rake x 4;
    frieze blocks: 6 bays a side x 2; windows 19 parts + lock + screen = 21."""
    r = _ck().run(plan=_spec())
    c, n = r["counts"], {x["objects"]: x["expect"] for x in r["checks"] if x["id"].startswith("nails-")}
    assert n["Shed_Nails_Frame_back"] == 68, n
    assert c["Shed_Lookout_*"] == 12 and c["Shed_Frieze_*"] == 12 and c["Shed_Window_1_*"] == 21
    assert c["Shed_Wrap_*"] == 4 and c["Shed_Tape_*"] == 5


def test_door_swings_out_hinges_left():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    skill_module("blender-suite", "construction_finish").run(build=_spec(), only=["doors"])
    bpy.context.view_layer.update()
    lo = lambda n, i: min((bpy.data.objects[n].matrix_world @ v.co)[i] for v in bpy.data.objects[n].data.vertices) / 0.0254  # noqa: E731
    assert lo("Shed_Door_Hinge_1", 1) < lo("Shed_Door_Slab", 1) < lo("Shed_Door_Stop_L", 1)   # knuckles outside
    assert lo("Shed_Door_Hinge_1", 0) < 60 < lo("Shed_Door_Knob_Ext", 0)                      # hinges on the left
