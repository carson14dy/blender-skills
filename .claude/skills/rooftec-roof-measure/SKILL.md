---
name: rooftec-roof-measure
description: Measure a Sioux Falls roof for $0 from an address, a lat/lon or a city footprint id, and hand it to the Rooftec roof studio. Gives roof area in squares, pitch per plane, ridge, hip, valley, eave, rake and wall-flashing lengths, a lidar cross-check of every pitch, a roof.json with source and confidence on each value, a studio-ready roof.glb and a takeoff report. Use this whenever someone asks to measure a roof, get roof pitch or roof area from an address, make a Sioux Falls roof takeoff or squares estimate, load a real house into the roof studio (roof-visualizer or roof-blender), decode the city 3D building wireframe or multipatch, or check a roof against USGS 3DEP lidar, even if they do not name this skill.
---

# Rooftec roof measure

Turn a Sioux Falls address into a measured roof in about 10 seconds, for $0, from two free public sources: the City of Sioux Falls 3D building solid (June 2023) and USGS 3DEP lidar (December 2020). The city solid gives the outline, the planes and the roof lines; lidar gives the pitch wherever its fit is precise.

## Quick start

Run this from the skill folder. It needs Python 3.9 or newer and numpy; `--lidar` also needs `pip install laspy lazrs` (about 20 seconds, once).

```bash
python3 scripts/roof.py measure --address "224 W 9th St" --out out/roofs --lidar
```

You can replace `--address` with `--oid 235245` (a city Building Footprints OBJECTID) or `--latlon 43.4809,-96.7424`. The command prints the squares, the predominant pitch, the line totals and every flag, and it writes four things into `out/roofs/<footprintId>/`:

1. `roof.json` is the measured roof, with a source and a confidence class on every plane and edge.
2. `roof.glb` is the 3D model for the studio: metres, Y up, the roof mesh named `Roof`, the walls named `Walls`. It carries the same geometry the numbers were measured on, lidar pitches included.
3. `takeoff.md` is the one-page report for a person.
4. `raw/` holds the cached city answers and lidar points, so a second run makes no network request.

Keep `--out` in a git-ignored folder, because the folder names and files can identify a customer's house.

## Workflow

1. **Measure.** Run `measure` with `--lidar`. A first run takes 8 to 25 seconds and makes about 10 to 20 small requests; a repeat run takes under 1 second.
2. **Read the flags before the numbers.** Each flag has a severity: `site-check` means do not use the numbers, `review` means look at that item, `info` is context. The flag list is in `references/accuracy.md`.
3. **Report it as an estimate.** Quote the status line from `takeoff.md` with the numbers. Every value is `estimate` until the accuracy study passes (see the decision rules below).
4. **Hand it to the studio.** Copy `roof.glb` into `roof-visualizer/viewer/` on branch `rooftec-lab` and open `?glb=roof.glb`, or load the file in the Project tab. For Blender, import the GLB; `roof-blender` picks up the object named `Roof`.
5. **Check the hand-off (1 minute).** Run `node scripts/studio_check.mjs --studio <path to roof-visualizer> --glb <roof.glb> --roof <roof.json>`. It runs the studio's own import code and passes when the studio finds the same plane count and the same area within 1%. It needs `npm install` in the studio folder once.

Other subcommands: `find` shows which building a selector resolves to, `fetch` only downloads, `decode` prints the solid's faces as JSON, `lidar` adds the lidar check to a house measured earlier, and `compare` scores a roof against ground truth for the accuracy study. `python3 scripts/roof.py <command> --help` lists the options.

## Decision rules

**Which tier to use.** This skill implements tier A (city solid) and tier B (lidar pitch check). Use them for any building inside city limits that existed in June 2023.

- If the command says the city has no 3D solid, the house is newer than June 2023 or outside the model. Say so, and fall back to a typed pitch on the footprint outline (tier C, an assumption) or a site capture (tier D). Neither is built into this skill yet.
- If the address is not found, ask for a lat/lon or check the spelling. Addresses outside city limits are not in the city layer.

**Which confidence class a value gets.**

| Class | Meaning | Where it may go |
|---|---|---|
| `verified` | The accuracy study passed and this roof's own checks agree, or a site measurement confirmed it | Customer documents |
| `estimate` | Public data only, or checks disagree, or the study has not passed | Office use, labelled "estimate: verify on site" |
| `assumed` | A typed or default value, such as the 12 in overhang | Office use only, never as a measurement |

Today everything this skill measures is `estimate`, because the accuracy study (plan experiment 027) has not been run. The switch is `STUDY_PASSED` in `scripts/roofmeasure/export.py`; change it only when `references/validation.md` records a pass. After that, a plane becomes `verified` only when lidar agrees with it and the roof has no `site-check` flag.

**When to send someone to verify on site.**

1. Always before a signed contract: confirm one eave length and one pitch, until the study has passed and 10 jobs are logged.
2. Whenever a flag has severity `site-check`: lidar disagrees with a plane and cannot settle it, the roof plan area does not match the footprint, or the building is newer than the data.
3. Whenever the roof was replaced, extended or re-framed after June 2023, which the data cannot see.
4. For flashing details the data never shows: chimneys, pipe boots, skylights and small dormers.

**How lidar sets the pitch of each plane** (planes with 40 or more lidar points):

1. A precise lidar fit supplies the pitch. Precise means 80% or more of the points lie on one plane and the pitch standard error is 0.25 degree or less. If the city pitch was within 1.5 degrees, nothing more happens; if it was 1.5 to 4 degrees off, the plane is flagged for review.
2. An imprecise fit never supplies the pitch. The city pitch is kept if lidar agrees with it, and the plane needs a site check if it does not.
3. Beyond 4 degrees, or with no single lidar plane, the plane needs a site check.

The city pitch reads about 0.16 in 12 lower than lidar on average, and lidar lands on whole-number pitches, which is why lidar wins. This rests on indirect evidence until a roof is taped. `references/accuracy.md` has the thresholds, the evidence and the error budget.

## License and attribution rules

- Put this line wherever the roof or its numbers are shown: "Contains data from the City of Sioux Falls, CC BY 4.0. Lidar: USGS 3DEP." The tool already writes it into `roof.json`, the GLB and the report.
- Use the results in-house. The city licence says the data is not for mapping products for resale, so do not sell the measurements or the model as a product.
- Be polite to the city service: one house per request, never a bulk pull, and let the cache answer repeat runs. The client already waits 1 second between city requests and retries 3 times.
- Keep GPL and AGPL tools (`roofer`, Blender add-ons, OpenDroneMap) as separate programs that exchange files with this skill. Nothing copyleft is bundled here; `references/licenses.md` has the matrix.

## What it does not do yet

- It does not make any value `verified`. That needs the accuracy study on 3 to 5 roofs with known measurements, which is the next step in `references/implementation-plan.md`.
- It does not build tier C (outline plus typed pitch) or tier D (drone or phone capture), and it does not run `roofer`.
- It does not check building permits, so an addition built after June 2023 is invisible unless the city's occupied date or year built shows it.
- It does not clip faces that lie partly under another face. Such buildings get a `plan-area-mismatch` site check instead of a number.
- The studio has no wall-flashing class yet, so the studio's own eave and rake totals differ from `roof.json` on houses with roof-to-wall joints. Treat `roof.json` as the reference; `patches/README.md` explains the one-line studio patch that closes most of the gap.

## Reference files

- `references/data-sources.md`: read when a request fails or you need an endpoint, field name, unit, datum or service limit.
- `references/accuracy.md`: read when judging whether a number is good enough, or when a flag needs explaining.
- `references/roof-json.md`: read when another program must read or write `roof.json`.
- `references/validation.md`: read for the measured results on real houses and how to re-run them.
- `references/benchmark.md`: read before changing the code; it lists the 12 fixed test buildings and the results each review round must compare against.
- `references/review-log.md`: read for what each review round found, fixed and left open.
- `references/implementation-plan.md`: read to choose the next piece of work; it re-sequences plan experiments 024 to 034.
- `references/licenses.md`: read before adding a dependency or a data source.

To test the skill offline, run `python3 -m unittest discover -s tests` from the skill folder (51 tests, under 2 seconds).
