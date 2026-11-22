# Construction detail: buildings built the way they are framed

Detail is construction grade by default. A simpler build is agreed with the user before building, never chosen during it.

Every stud, plate, header, rafter, panel, board, trim piece and nail is its own part, sized from the lumber standard and placed by the rule a framer uses. The rules give the counts; the counts go into the acceptance file before anything is built (`build-accuracy`); `acceptance_check.py` then counts the scene. Three scripts read one `building.json`:

| Command | Does |
|---|---|
| `construction_kit.py -- --plan building.json` | No geometry. Prints `counts`, the design-rule values used (`rules`) and ready `checks` (count, size, spacing, extent, slope, tris; nails as `count` of islands) with the rule in `note`. |
| `construction_kit.py -- --build building.json [--only pad walls roof_frame sheathing roofing] --save F` | Pad, wall framing, roof framing, wall sheathing, the `Roof` planes, then roof_core.py's roofing (when the RoofTec repo is there). |
| `construction_finish.py -- --build building.json [--only siding trim windows doors] --save F` | Siding, trim, windows, door. |
| `construction_extras.py -- --build building.json [--only wrap blocking hardware nails] --save F` | House wrap and flashing tape, rake lookouts and frieze blocks, sash locks and screens, nails. |

`--plan` runs the same builders without making objects. Repeated parts share one mesh. Scope: a rectangle, a gable roof along y, rectangular openings, one door, double-hung windows; anything else, or a size the code tables read do not cover, fails with a message.

## building.json and the design rules

```json
{"name": "Garden shed", "prefix": "Shed", "units": "ft", "building": "accessory", "footprint": [10, 12],
 "wall_height": 8, "pad": {"thickness_in": 4}, "site": {"ground_snow_psf": 55},
 "framing": {"stud": "2x4", "oc_in": 16, "rafter": "2x6", "rafter_oc_in": 24, "ridge": "1x8", "header": "2x6"},
 "roof": {"pitch": "6/12", "pitch_source": "pitch.json", "exposure_in": 5.625, "ice_barrier": false, "ridge_vent": false},
 "siding": {"board_in": 8.25, "exposure_in": 7, "thickness_in": 0.3125, "color": "#9CAF88"},
 "trim": {"corner_in": 3.5, "casing_in": 3.5, "fascia": "1x8", "rake": "1x8", "color": "#FFFFFF"},
 "openings": [{"wall": "front", "type": "door", "center_ft": 5, "width_in": 36, "height_in": 80},
              {"wall": "left", "type": "window", "width_in": 24, "height_in": 36}]}
```

- x runs across the ridge, y along it. Walls: `front` (y = 0), `back`, `left` (x = 0), `right`. `center_ft` is from the corner with the smaller x or y. `wall_height` is plate to plate.
- `roof.pitch_source` names a saved `roof_pitch.py` result (`roof-pitch`) whose pitch equals `roof.pitch`.
- A value left out comes from the user's approved `lab/data/design-rules.json` (the file `roof_pitch.py rule` reads; `"rules": "file"` names another): overhangs by `building`, a flush slab, windows equally spaced along their wall with their rough-opening tops level with the door's, the door's style, swing, hinge side, knob height and colour. `--plan` lists each as a design rule, source `standard`. A value in neither fails.
- Optional, with defaults: `framing.tie` 2x4; `sheathing.thickness_in` 0.4375; `siding.lap_in` 1, `siding.clear_in` 1; `trim.thickness_in` 1, `trim.soffit` true, `trim.soffit_in` 0.25.

## Parts and rules

| Part | Rule | Source |
|---|---|---|
| Lumber | Dry sizes: 1x = 3/4, 5/4 = 1, 2x = 1-1/2 in.; widths 4, 6, 8 = 3-1/2, 5-1/2, 7-1/4 in. | PS 20-20 Table 3 |
| Plates | Bottom plate cut at a door; double top plate, the gable walls' upper plate lapping the long walls | R602.3.2 |
| Studs | End studs; layout every `oc_in` (long walls from their corner, gable walls from the sheathing's corner so panel joints land on studs); dropped if touching an end stud, king or jack; cripples inside an opening. 2x4, <= 24 in., <= 10 ft | R602.3(5) |
| Openings | Rough opening: door + 2 x 2-1/2 in., window + 1/2 in.; 1 king, 1 jack each side; two-member header checked by span, snow load and width | Pease Doors, JELD-WEN; R602.7(1), R602.7.5 |
| Roof framing | Rafter pairs at the ends and every `rafter_oc_in`, birdsmouth on the plate, barge pairs at the rakes (span: least of SPF, DF-L, SP No. 2); ridge as deep as the plumb cut; a 2x4 tie beside each inner pair; gable studs on the wall layout | R802.4.1(7), R802.3, R802.5.2.2 |
| Sheathing, wrap, tape | 4 ft panels from each corner, cut at openings, up to the roof planes; house wrap over all of it; tape lining each rough opening (sill pan, jambs, head) | R703.2, R703.4 |
| Roofing | roof_core.py on `Roof` (deck, drip edge, underlayment, starter, courses, 4 nails a shingle, ridge cap; ice barrier, vent per the rules) | R905.2.8.5, R905.2.6, R905.1.2 |
| Siding | Starter strip; courses = ceil(covered height / exposure), cut at corner boards, casings, rakes; tilted to rest on the course below; on a flush slab it laps 1 in. below the plate, else stops 1 in. above the slab | James Hardie catalog, HZ10 instructions |
| Trim, blocking | 2 corner boards a corner, fascia, rake boards, soffits (fascia and rake must cover rafter + soffit); lookouts 24 in. along each rake from 12 in.; a frieze block in each rafter bay, clear of the ties | trade practice |
| Window, door | Frame, two sashes, glass, casing, drip cap, sash lock, half screen; door jambs, stops, threshold, 6-panel slab, 3 hinges, knobs, casing, drip cap, swing and hinge side as given | |
| Nails | Wall: R602.3(1) items 17 (2-16d end nails each stud end at a plate or sill; gable studs 3 toe nails), 13 (top plates 16d at 16 in.), 18 (2 at each corner lap), 10 (headers 16d at 16 in. each edge), 12 (3-16d king to header), 8 (jack to king 16d at 24 in.). Sheathing: item 31, 6d, 6 in. at panel edges, 12 in. at studs. Siding: R703.3(1) note f, one 6d through the lap at each stud. Trim: Hardie Trim Table 1, 2 nails every 16 in. on 4 in. boards, 3 on 8 in. fascia and rake, 1 in. from ends. Roof: items 6 (3 toe nails a rafter seat), 7 (3-10d toe nails at the ridge), 1 (3-8d a frieze block); Table R802.5.2(1) tie heel joints 7-16d (its 5:12 row: there is no 6:12 row) | IRC 2024; Hardie Trim (2025) |

Drawing tolerances, for `qa_check.py`'s 1 mm coplanar test: nail heads sit 1.2 mm under the surface they are driven into (real: flush); house wrap is 1.8 mm thick, 1.1 mm off the sheathing, so siding and trim sit 2.9 mm out; tape is 1.1 mm thick.

## Hand-over to roof_core.py

The kit makes a mesh object named exactly `Roof`: two planes on the top of the rafters, out to the fascia and rake faces, and runs `{"cmd": "layers", "roof": "Roof", "old_roof": false, "deck_repair": false, "ridge_vent": ..., "ice_rows": ...}` on it, which hides `Roof`. No other part may have "roof" or "shingle" in its name. The result carries `pitches_per_12`; `roof_qa.py --expect` checks squares and lengths.

## Names

`<prefix>_Stud_<wall>_<n>` (end studs `_E1`, `_E2`), `_Plate_<wall>_B<n>` / `_T<n>`, `_King_`, `_Jack_`, `_Cripple_`, `_Header_`, `_Sill_<wall>_<n>`, `_Rafter_<nn>_<L|R>`, `_Rafter_Barge_<end>_<L|R>`, `_Ridge`, `_Tie_<n>`, `_GableStud_<wall>_<n>`, `_Sheathing_<wall>_<n>`, `_Wrap_<wall>`, `_Tape_<n>`, `_Lookout_<n>`, `_Frieze_<n>`, `_Starter_<wall>_<n>`, `_Siding_<wall>_<course>_<piece>`, `_Trim_Corner_<n>`, `_Trim_Fascia_`, `_Trim_Rake_`, `_Trim_Soffit_...`, `_Window_<n>_<part>` (with `_Lock`, `_Screen`), `_Door_<part>`, `_Nails_<Frame|Sheathing|Siding>_<wall>`, `_Nails_Trim`, `_Nails_Roof`, `_Pad`.

## Still not modelled

Fasteners for lookouts (no row in R602.3(1)) and soffits (HardieSoffit instructions not read), electrical, interior finish. Shingles are stepped courses with every nail; one piece per shingle is the user's choice, its own experiment.
