# The roof.json file

`roof.json` is the one roof file that every tier writes and every program reads. This skill writes version 1. Check a file with `roofmeasure.export.validate_roof_json(doc)`, which returns an empty list when every plane and edge carries its provenance.

## Coordinates

All lengths are metres in a local frame: x is east, y is north, z is up, and z = 0 is the city ground elevation of the footprint. `origin` gives the local origin in EPSG 32164 (US survey feet) with its latitude and longitude. The local origin is subtracted in 64-bit feet before the conversion to metres, so the file is safe to load into 32-bit meshes. For a Y-up viewer use X = x, Y = z, Z = -y.

## Top-level fields

| Field | Content |
|---|---|
| `format`, `version`, `generator`, `createdOn` | `"rooftec-roof"`, `1`, tool version, ISO date |
| `address`, `footprintId`, `solidId` | The typed address if one was given, and the two city OBJECTIDs |
| `origin`, `units`, `building` | Local origin, unit notes, and the footprint attributes (stories, ground and top elevation) |
| `summary` | Plane count, plan and sloped area, squares, predominant pitch, `edgeTotals`, `confidence`, `siteCheckRequired`, `siteCheck` |
| `planes[]`, `edges[]` | The measured roof (next two sections) |
| `assumptions` | Typed defaults such as `overhangM`, each with confidence `assumed` |
| `checks`, `flags` | Sanity checks, the lidar block, and the flag list with `code`, `severity`, `message` |
| `attribution`, `license` | The credit lines that must be shown with the data |

**Read `summary.siteCheckRequired` before any number.** It is `true` when a flag has severity `site-check`, and then the numbers must not be used. `summary.confidence` does not tell you this: it stays `estimate` for a clean roof and for a blocked one. `siteCheck` is the same message as a sentence. The GLB carries `siteCheckRequired` in its scene extras.

`checks.permits` holds the permit lookup: `checked`, `roofShapePermits`, `sinceCapture` (the permits behind a `permit-since-capture` flag) and `lastReshingle`.

## A plane

`id`, `polygon` (outer corner points, counter-clockwise seen from above), `holes`, `pitchDeg`, `pitchIn12`, `azimuthDeg` (the compass direction the plane faces, true north), `planAreaM2`, `areaM2`, `areaFt2`, `planarityM` (how far the delivered city face was from flat), `sourcePitchDeg` (pitch of the face exactly as delivered), `faceCount`, and `provenance`. When lidar was run, `lidar` holds `status` (agree, override, site_check or not_checked), `action` (use_lidar or keep_city), the point counts, the fit error, `pitchSeDeg` (standard error of the lidar pitch), `precise` and the lidar pitch. `lidar.surface` gives the share of lidar points above the roof surface, below it and at ground level (`aboveShare`, `belowShare`, `groundShare`), and `lidar.surfaceNote` is set when one of them is large enough for the `lidar-surface` flag. When lidar supplied the pitch, `pitchProvenance`, `cityPitchDeg` and `cityAreaM2` record what the city solid said, and `polygon`, `pitchDeg` and `areaM2` describe the re-tilted plane. `pitchDeg` can differ from `lidar.lidarPitchDeg` by up to about 0.2 degree where neighbouring planes had to meet.

## An edge

`id`, `type`, end points `a` and `b`, `lengthM`, `lengthFt`, `planes` (the plane ids it belongs to) and `provenance`. The types are:

- `ridge`, `hip`, `valley`: two planes meet. Convex and level is a ridge, convex and sloped is a hip, concave is a valley. A ridge with `splitRidge: true` was drawn in the city model as two plane tops with a sliver wall between them.
- Level means the edge rises less than 3 degrees, or runs within 10 degrees of its plane's contour line seen from above.
- `eave`, `rake`: the outer roof edge. Level at the low side is an eave; sloped is a rake.
- `step_flashing`, `headwall`: the roof meets a wall that rises above it, sloped or level. A `headwall` with `lowSide: true` sits at the bottom of its plane, which usually means the city model simplified a gable tie-in.
- `top`: the level high edge of a single-slope plane that ends at a wall drop.

## A provenance block

`{ "source": "city-solid", "tier": "A", "capturedOn": "2023-06", "confidence": "estimate", "note": "..." }`. The confidence is `verified`, `estimate` or `assumed`. The meaning of each class is in `SKILL.md`.
