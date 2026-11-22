# Construction detail: buildings built the way they are framed

Detail is construction grade by default. A simpler build is agreed with the user before building, never chosen during it.

Every stud, plate, header, rafter, sheathing panel, siding board and trim piece is its own object, sized from the lumber standard and placed by the rule a framer uses. The rules give the counts; the counts go into the acceptance file before anything is built (`build-accuracy`); `acceptance_check.py` then counts the scene. Two scripts read one `building.json`:

| Command | Does |
|---|---|
| `construction_kit.py -- --plan building.json` | No geometry. Prints `counts` (every part, by name pattern) and ready `checks` (count, size, spacing, extent, slope, tris) with the rule in `note`. Paste them into the acceptance file. |
| `construction_kit.py -- --build building.json [--only pad walls roof_frame sheathing roofing] --save F` | Pad, wall framing, roof framing, wall sheathing, the `Roof` planes, then the roofing (roof_core.py, when the RoofTec repo is there). |
| `construction_finish.py -- --build building.json [--only siding trim windows doors] --save F` | Siding boards, trim, window and door assemblies. |

`--plan` runs the same builders as `--build` without making objects, so its counts are what the build makes. Repeated parts are linked duplicates (one mesh, many objects); `acceptance_check.py` still counts and sizes each one. Each stage is one headless call that reports `seconds`; nothing needs a window, so the same commands run on a GPU server.

Scope for now: a rectangular footprint, a gable roof with the ridge along y, rectangular openings, one door, double-hung windows. A hip roof, an L-shaped plan, a size the code tables below do not cover, or a missing value fails with a message; nothing is approximated silently.

## building.json

```json
{"name": "Garden shed", "prefix": "Shed", "units": "ft", "footprint": [10, 12], "wall_height": 8,
 "pad": {"thickness_in": 4, "margin_in": 2}, "site": {"ground_snow_psf": 55},
 "framing": {"stud": "2x4", "oc_in": 16, "rafter": "2x6", "rafter_oc_in": 24, "ridge": "1x8", "header": "2x6"},
 "roof": {"pitch": "6/12", "pitch_source": "pitch.json", "overhang_eave_in": 6, "overhang_rake_in": 6,
          "exposure_in": 5.625, "ice_barrier": false, "ridge_vent": false},
 "siding": {"board_in": 8.25, "exposure_in": 7, "thickness_in": 0.3125, "color": "#9CAF88"},
 "trim": {"corner_in": 3.5, "casing_in": 3.5, "fascia": "1x8", "rake": "1x8", "color": "#FFFFFF"},
 "openings": [{"wall": "front", "type": "door", "center_ft": 5, "width_in": 36, "height_in": 80, "panels": 6},
              {"wall": "left", "type": "window", "center_ft": 4, "sill_in": 44, "width_in": 24, "height_in": 36}]}
```

- `footprint` is [width across the ridge, depth along it]; x runs across, y along the ridge. Walls: `front` (y = 0), `back`, `left` (x = 0), `right`. `center_ft` is measured from the corner with the smaller x (front, back) or y (left, right). `wall_height` is plate to plate.
- `roof.pitch_source` names a saved `roof_pitch.py` result (`roof-pitch`) whose pitch equals `roof.pitch`; without it the scripts refuse to run. `ice_barrier` and `ridge_vent` come from the user's design rules (R905.1.2 exempts unheated detached buildings).
- Optional, with their defaults: `framing.tie` 2x4; `sheathing.thickness_in` 0.4375; `siding.clear_in` 1; `trim.thickness_in` 1 (5/4 trim), `trim.soffit` true, `trim.soffit_in` 0.25; a door's `color` (else the trim colour).
- Overhangs are measured to the outer face of the fascia and rake board; the roof deck ends there.

## Parts and rules

| Part | Rule (counts, sizes) | Source |
|---|---|---|
| Lumber | Actual dry sizes: 1x = 3/4 in., 5/4 = 1 in., 2x = 1-1/2 in.; widths 4 = 3-1/2, 6 = 5-1/2, 8 = 7-1/4 in. | PS 20-20 Table 3 |
| Plates | Bottom plate, cut at a door; double top plate; the gable walls' upper plate laps 3.5 in. over the long walls | R602.3.2 |
| Studs | End stud at each end; layout studs every `oc_in` from the wall's start (centres); one touching an end stud, king or jack is dropped; one inside a rough opening becomes cripples. Long walls run through, gable walls fit between. Studs = wall height - 4.5 in. 2x4 only, <= 24 in. o.c., <= 10 ft | R602.3(5) |
| Openings | Rough opening: door + 2 in. wide, + 2.5 in. high; window + 1/2 in. each way. One king and one jack each side; header = two members on edge, checked against the span table at the site's snow load and building width; rough sill and cripples under a window | Pease Doors and JELD-WEN install guides; R602.7(1), R602.7.5 |
| Rafters | Pairs at each end and every `rafter_oc_in`; birdsmouth seat on the plate's full width, heel cut flush with the sheathing; tails cut plumb inside the fascia; a barge pair at each rake. Span checked (SPF #2, 70 psf, 24 in.) | R802.4.1(7) |
| Ridge | One board, at least as deep as the plumb cut, out to the barge rafters; past the gable walls it is cut to the rafter line | R802.3 |
| Ties | A 2x4 tie beside each pair between the gable walls, on the plates; the gable walls tie the end pairs | R802.5.2.2 |
| Gable studs | On the wall layout, from the top plate to the end rafter | trade practice |
| Sheathing | 4 ft panels from each corner, cut at rough openings, up to the roof planes on the gables, notched at the ridge | trade practice |
| Roofing | roof_core.py on `Roof`: deck, drip edge, underlayment, starter, stepped courses, nails (4 a shingle), ridge cap; ice barrier and ridge vent per the rules | R905.2.8.5, R905.2.6, R905.1.2 |
| Siding | Starter strip (board - exposure) under the first course; courses = ceil(covered height / exposure); each course cut at corner boards, casings and the rake; every board tilted so it rests on the one below. Bottom 1 in. above the slab | James Hardie catalog and HZ10 install instructions |
| Trim | Two corner boards per corner (the gable-face board covers the other's edge); fascia (top bevelled to the roof), rake boards, soffits under the rafters at eaves and rakes. The fascia and rake board must cover the rafter plus soffit, or the kit fails | trade practice |
| Window | Frame (head, sill, jambs), two sashes each with two stiles, two rails and a glass pane (meeting rails overlap 1.5 in.), picture-frame casing, drip cap; 150+ triangles | |
| Door | Jambs, stops, threshold, slab with raised panels on both faces, three hinges (7 in. from the top, 11 from the bottom), knob with rose on both sides (36 in. up, 2-3/8 in. backset), casing, drip cap; 400+ triangles | |

## Hand-over to roof_core.py

The kit makes a mesh object named exactly `Roof`: two planes on the top of the rafters, out to the fascia and rake faces. The `roofing` stage runs `{"cmd": "layers", "roof": "Roof", "old_roof": false, "deck_repair": false, "ridge_vent": ..., "ice_rows": ...}` and hides `Roof`. No other part may have "roof" or "shingle" in its name: roof_core.py falls back to such objects. Its result carries `pitches_per_12` per plane; `roof_qa.py --expect` checks squares and edge lengths against the hand values. After roofing the kit removes zero-area sliver faces that roof_core's polygon clipping leaves where a clip line meets a corner (one tripped `qa_check.py`'s z-fighting test on a shed).

## Names

`<prefix>_Stud_<wall>_<n>` (end studs `_E1`, `_E2`), `_Plate_<wall>_B<n>` / `_T<n>`, `_King_`, `_Jack_`, `_Cripple_`, `_Header_`, `_Sill_<wall>_<n>`, `_Rafter_<nn>_<L|R>`, `_Rafter_Barge_<front|back>_<L|R>`, `_Ridge`, `_Tie_<n>`, `_GableStud_<wall>_<n>`, `_Sheathing_<wall>_<n>` (gable pieces `G<n>`), `_Starter_<wall>_<n>`, `_Siding_<wall>_<course>_<piece>`, `_Trim_Corner_<n>`, `_Trim_Fascia_`, `_Trim_Rake_`, `_Trim_Soffit_...`, `_Window_<n>_<part>`, `_Door_<part>`, `_Pad`. Collections: `<prefix>_Pad`, `_Framing`, `_RoofFrame`, `_Sheathing`, `_Siding`, `_Trim`, `_Windows`, `_Doors`.

## Still not modelled

Each is listed for the user, not chosen as a shortcut: house wrap and flashing tape, nails and screws in walls and trim, rake ladder blocking (lookouts) and frieze blocks between rafter tails (both hidden behind the soffits), window locks and screens, electrical, interior finish. Shingles are stepped courses with every nail; one piece per shingle is the user's choice, scheduled as its own experiment (roof_core.py and the web studio together).
