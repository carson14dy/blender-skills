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
| `summary` | Plane count, plan and sloped area, squares, predominant pitch, `edgeTotals`, `confidence`, `siteCheck` |
| `planes[]`, `edges[]` | The measured roof (next two sections) |
| `assumptions` | Typed defaults such as `overhangM`, each with confidence `assumed` |
| `checks`, `flags` | Sanity checks, the lidar block, and the flag list with `code`, `severity`, `message` |
| `attribution`, `license` | The credit lines that must be shown with the data |

## A plane

`id`, `polygon` (outer corner points, counter-clockwise seen from above), `holes`, `pitchDeg`, `pitchIn12`, `azimuthDeg` (the compass direction the plane faces, true north), `planAreaM2`, `areaM2`, `areaFt2`, `planarityM` (how far the delivered city face was from flat), `sourcePitchDeg` (pitch of the face exactly as delivered), `faceCount`, and `provenance`. When lidar was run, `lidar` holds the status, point count, fit error and lidar pitch. When lidar replaced the pitch, `pitchProvenance`, `cityPitchDeg` and `cityAreaM2` record the change.

## An edge

`id`, `type`, end points `a` and `b`, `lengthM`, `lengthFt`, `planes` (the plane ids it belongs to) and `provenance`. The types are:

- `ridge`, `hip`, `valley`: two planes meet. Convex and level is a ridge, convex and sloped is a hip, concave is a valley.
- `eave`, `rake`: the outer roof edge. Level at the low side is an eave; sloped is a rake.
- `step_flashing`, `headwall`: the roof meets a wall that rises above it, sloped or level. A `headwall` with `lowSide: true` sits at the bottom of its plane, which usually means the city model simplified a gable tie-in.
- `top`: the level high edge of a single-slope plane that ends at a wall drop.

## A provenance block

`{ "source": "city-solid", "tier": "A", "capturedOn": "2023-06", "confidence": "estimate", "note": "..." }`. The confidence is `verified`, `estimate` or `assumed`. The meaning of each class is in `SKILL.md`.
