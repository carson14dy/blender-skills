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
| `summary` | Plane count, plan and sloped area, squares, `areaRange`, predominant pitch, `edgeTotals`, `confidence`, `siteCheckRequired`, `siteCheck` |
| `planes[]`, `edges[]` | The measured roof (next two sections) |
| `assumptions` | Typed defaults such as `overhangM`, each with confidence `assumed` |
| `checks`, `flags` | Sanity checks, the lidar block, and the flag list with `code`, `severity`, `message` |
| `attribution`, `license` | The credit lines that must be shown with the data |

**Read `summary.siteCheckRequired` before any number.** It is `true` when a flag has severity `site-check`, and then the numbers must not be used. `summary.confidence` does not tell you this: it stays `estimate` for a clean roof and for a blocked one. `siteCheck` is the same message as a sentence. The GLB carries `siteCheckRequired` in its scene extras.

**Quote `summary.areaRange` with the area.** It holds `lowFt2`, `highFt2`, `plusMinusFt2` and `plusMinusPct` for the sloped area, the two parts it is made of (`outlinePct`, `pitchPct`), the outline tolerance in metres and the length of open edge it was applied to. It is a likely range from the outline and the pitch, not a guarantee; `references/accuracy.md` explains it. `areaRange.underOverhang` is separate and is not inside the range: `jointFt` (length of the roof-to-wall joints), `assumedOverhangIn`, and the `areaFt2` and `pct` of lower roof that would lie hidden under the upper roof's overhang. Its confidence is `assumed`.

`checks.permits` holds the permit lookup: `checked`, `roofShapePermits`, `sinceCapture` (the permits behind a `permit-since-capture` flag), `otherSinceCapture` (repair and remodel permits, information only) and `lastReshingle`. `checks.lidar.returnCounts` says whether the lidar points carried return counts, which the tree-or-dormer test needs. `checks.glb` holds the triangle counts of `roof.glb` and `roofAreaM2`, the area of its roof mesh. That area equals `summary.slopedAreaM2`, except on a roof where a city face crosses itself (about 1 house in 5): there the mesh holds the face without the twisted corner and is up to 0.4% larger.

## A plane

`id`, `polygon` (outer corner points, counter-clockwise seen from above), `holes`, `pitchDeg`, `pitchIn12`, `azimuthDeg` (the compass direction the plane faces, true north), `planAreaM2`, `areaM2`, `areaFt2`, `planarityM` (how far the delivered city face was from flat), `sourcePitchDeg` (pitch of the face exactly as delivered), `faceCount`, and `provenance`. When lidar was run, `lidar` holds `status` (agree, override, site_check or not_checked), `action` (use_lidar or keep_city), the point counts, the fit error, `pitchSeDeg` (standard error of the lidar pitch), `precise` and the lidar pitch. `lidar.surface` gives the share of lidar points above the roof surface, below it and at ground level (`aboveShare`, `belowShare`, `groundShare`) and the share of the points above that come from multi-return pulses (`aboveMultiShare`). When one of them is large, `lidar.surfaceKind` is `tree`, `solid-above`, `above`, `below` or `ground` and `lidar.surfaceNote` says it in words. `lidar.azimuthDiffDeg` is how far the plane faces from where lidar sees it, and `lidar.siblingPlane` names the plane that confirmed a lidar pitch (see the reconcile rules in `references/accuracy.md`). When lidar supplied the pitch, `pitchProvenance`, `cityPitchDeg` and `cityAreaM2` record what the city solid said, and `polygon`, `pitchDeg` and `areaM2` describe the re-tilted plane. `pitchDeg` can differ from `lidar.lidarPitchDeg` by up to about 0.2 degree where neighbouring planes had to meet.

## An edge

`id`, `type`, end points `a` and `b`, `lengthM`, `lengthFt`, `planes` (the plane ids it belongs to) and `provenance`. The types are:

- `ridge`, `hip`, `valley`: two planes meet. Convex and level is a ridge, convex and sloped is a hip, concave is a valley. A ridge with `splitRidge: true` was drawn in the city model as two plane tops with a sliver wall between them.
- Level means the edge rises less than 3 degrees, or runs within 10 degrees of its plane's contour line seen from above. An open edge that runs more than 45 degrees off the contour line is never level; this matters only on planes flatter than about 0.9 in 12, where every edge rises less than 3 degrees.
- `eave`, `rake`: the outer roof edge. Level at the low side is an eave; sloped is a rake. A rake that runs less than 45 degrees off the level line of its plane is doubtful, and 10 ft or more of such edges raise the `skewed-edge` flag (review from 30 ft).
- `step_flashing`, `headwall`: the roof meets a wall that rises above it, sloped or level. The wall must be at least 10 cm tall above the middle of the edge in the city solid as delivered; the lidar pitch does not change this answer. A `headwall` with `lowSide: true` sits at the bottom of its plane, which usually means the city model simplified a gable tie-in.
- `top`: the level high edge of a single-slope plane that ends at a wall drop.

## A provenance block

`{ "source": "city-solid", "tier": "A", "capturedOn": "2023-06", "confidence": "estimate", "note": "..." }`. The confidence is `verified`, `estimate` or `assumed`. The meaning of each class is in `SKILL.md`.
