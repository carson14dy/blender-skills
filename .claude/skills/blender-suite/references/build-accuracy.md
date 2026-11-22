# Build accuracy

For every build: a model, a scene, a render, a RoofTec house or roof. The order is fixed: correct, complete, checked, and only then fast. `SKILL.md` has the three rules. This page has the procedure.

## 1. Write the acceptance file first
Before any geometry, turn the brief into `acceptance.json`, saved beside the .blend.
1. List what the brief names: parts, sizes, counts, spacing, heights, materials, and the files to deliver with their resolution.
2. Give every number a `source`:
   - `given`: the user said it.
   - `reference`: a drawing, photo, product sheet or report. Name it in `note`.
   - `measured`: read from a supplied model with `scripts/acceptance_check.py -- --measure "House_*" --units ft`.
   - `standard`: a usual size, such as a 6 ft 8 in. door (`blender-scene-setup`, `pbr-values`).
   - `assumed`: you chose it. Say why in `note`.
3. Look a value up before you assume it. A roof pitch is never assumed or asked: `roof-pitch`. Ask the user, once and before building, about anything else that changes what they see or pay for, and about any part you want to simplify. If nobody can answer, go on and log each assumed value as a shortcut.
4. Detail is construction grade (`construction-detail`): the counts its rules imply go into the acceptance file. Every part the brief names gets a `count` check. Give it a `tris` minimum when its shape matters, so a box cannot stand in for it.
5. Start the log: `python scripts/build_log.py start --name "Garden shed" --accept acceptance.json`.

```json
{"name": "Garden shed", "units": "ft",
 "checks": [
  {"id": "footprint", "type": "size", "objects": "Shed_Wall*", "expect": [10, 12, 8], "source": "given"},
  {"id": "ridge", "type": "extent", "objects": "Shed_Roof*", "axis": "z", "side": "max", "expect": 10.5, "source": "standard", "note": "8 ft wall + 6/12 over 5 ft"},
  {"id": "pitch", "type": "slope", "objects": "Shed_Roof", "expect": "6/12", "source": "standard", "note": "roof_pitch.py rule: pitch.json"},
  {"id": "windows", "type": "count", "objects": "Shed_Window_*", "expect": 4, "source": "given"},
  {"id": "window-detail", "type": "tris", "objects": "Shed_Window_*", "each": true, "min": 60, "source": "assumed", "note": "frame, sash and glass"},
  {"id": "stud-spacing", "type": "spacing", "objects": "Shed_Stud_*", "axis": "x", "expect": 16, "unit": "in", "source": "standard"},
  {"id": "roof-on-walls", "type": "gap", "a": "Shed_Wall*", "b": "Shed_Roof*", "axis": "z", "expect": 0, "source": "given"},
  {"id": "siding", "type": "material", "objects": "Shed_Wall*", "expect": "M_Siding*", "textured": true, "source": "given"},
  {"id": "hero", "type": "image", "file": "//render/hero_0001.png", "res": [3840, 2160], "source": "given"}],
 "forbid": {"scope": "Shed_*"}}
```

| Type | Measures | Keys |
|---|---|---|
| `size` | world bounding box of the matched set, or of `each` object | `expect` [x, y, z], null skips an axis; `sorted` ignores orientation |
| `extent` | lowest or highest point on an axis | `axis`, `side` min or max, `expect` |
| `count` | objects, or mesh `islands`, or Geometry Nodes `instances` | `of`, `expect` or `min` and `max` |
| `spacing` | centre to centre along an axis; reports the worst gap | `axis`, `expect` |
| `gap` | from the top of `a` to the bottom of `b` on an axis | `a`, `b`, `axis`, `expect` (0) |
| `position` | `center`, `min`, `max` or `origin` of the set | `anchor`, `at` [x, y, z] |
| `slope` | area-weighted median slope of the faces that point up | `expect` in degrees or "6/12" |
| `area` | surface area, all faces or `facing` up | `expect`; `unit` "sq" is roofing squares |
| `material` | every slot is filled and each name matches | `expect` pattern; `textured` needs an image |
| `tris` | triangles after modifiers, total or `each` | `min`, `max` |
| `image` | the file exists, has the size and is not blank | `file`, `res` |

- `objects` is a name pattern (`Shed_Stud_*`), a list of them, or `collection:Name`. Hidden-from-render objects do not count.
- Units: `m`, `cm`, `mm`, `in`, `ft`, set for the file with `units` or per check with `unit`.
- Tolerance: 1 mm or 0.1 %, whichever is larger. Slopes 0.25 degrees, areas 0.5 %. A check may set `tol` or `tol_pct`, with the reason in `why`. A real house against its measurement report: 2 %.
- `forbid` runs on every full check (not with `--only`): default names ("Cube.001"), untouched grey materials, empty material slots, and names with placeholder, proxy, tmp or todo.
- A check that matches no object fails. So does an unknown type, and so does a file with no checks.

## 2. Build in stages, with a gate after each
| Stage | Gate before moving on |
|---|---|
| Blockout: every part, real size and place | `acceptance_check.py -- --accept acceptance.json --only <size, count and position ids>` |
| Detail: every named part modelled | `qa_check.py` with `"pass": true` and `"complete": true`; the full acceptance file |
| Materials | `material` checks; look in material shading |
| Light and camera | look from the delivery camera |
| Deliverables: render, export | `image` checks; `render_batch.py` result has `"deliverable": true`; exported files re-read |

Record each stage and gate, so the log holds the result and the time:
```
python scripts/build_log.py stage detail
python scripts/run_in_blender.py --blend shed.blend scripts/acceptance_check.py -- --accept acceptance.json | python scripts/build_log.py gate acceptance --stdin
python scripts/build_log.py gate look --pass --note "review sheet out/review.png, 6 views, solid and wire"
python scripts/build_log.py stage detail --done
```
Live through MCP: `print(json.dumps(acceptance_check.run(accept=...)))`, save the text to a file, then `gate acceptance --result file.json`.

When a check fails, fix the model. Change the acceptance file only when the brief itself changed, and log that as a shortcut of kind `brief-change`.

## 3. What counts as a shortcut
Any of these is a shortcut. Log it the moment you take it:
- a primitive or a copy standing in for a named part; fewer items than the brief counts;
- a flat plane or a texture where the brief implies depth (windows, ribs, trim, panels);
- a default, flat-color or untextured material where a product or finish was named;
- an assumed size, color or product (a pitch is never assumed);
- a skipped stage (UVs, bevels, a bake) or a skipped, narrowed or loosened check;
- a QA warning left in place, or a script result with a `warning` or a fallback;
- a render below the asked resolution or samples, or a preview preset;
- anything you did not look at, or could not test here (GPU, engine import, a real phone).
```
python scripts/build_log.py shortcut --kind simplified --what "Window frames are one extruded profile, no sash" --why "no window drawing" --effect "visible closer than 2 m" --check window-detail
```
Kinds: `simplified`, `omitted`, `substituted`, `assumed`, `preview`, `unverified`, `tolerance`, `brief-change`.
A logged shortcut is honest. An unlogged one is a defect. A shortcut that makes a check fail needs the user's yes, recorded with `build_log.py approve <number>`.
A simplified, omitted or substituted part must be agreed before building. Logged afterwards without a yes, it blocks `close`. `build_log.py reject N` records a no: redo the part, then `resolve N --how "<what you did>"`.

Never do these: edit or delete a check to get a pass, report a preview as the final render, call a blockout finished, or say "done" while `close` lists blockers.

## 4. Done
`python scripts/build_log.py close` prints `"done": true` only when:
- the last full acceptance run passed, or every failing check has an approved shortcut;
- the acceptance file is the one the build started with, or the change is logged;
- the last `qa` gate passed, was complete and came from a `qa_check.py` result (not `--pass`), and a `look` gate with a note passed;
- no gate's last result is a fail (pass it again, or log a shortcut with `--check <gate>` and get the user's yes);
- no simplified, omitted or substituted part lacks the user's yes, and no rejected shortcut is unresolved;
- no deliverable render is preview quality, and no stage is open.

Other unapproved shortcuts do not block, but they are listed for the user's OK: `close` returns them as `"unapproved"` and the report ends `Done: yes, N shortcuts await your OK (1, 2)`. Only the user approves; never run `approve` on your own.

Then paste `python scripts/build_log.py report` into the final message. It lists checks passed and failed with numbers, every shortcut, every assumed value, and the time per stage. Add what the report cannot know: what you did not verify.

## 5. Speed comes later, and never costs accuracy
Collect now: every script run from the command line reports `seconds`; the log times each stage; `close --times <file>` adds one line per build to a timing file.
A speed-up is safe when the same acceptance file and `qa_check.py` give the same result, and the delivered image or file is the same within a stated measure. Examples: instances for repeats, `--only` checks inside a stage with the full run at its end, cached bakes, persistent render data, background renders, a sample count proven equal by an A/B at final resolution (`long-renders`).
A corner cut changes a result: fewer parts, less detail, lower resolution, unproven samples, a skipped gate. It needs the user's yes and a log entry.
Prove a speed-up once with an A/B (both times, both check results), then make it the default.
