# spec.json and observations.json

## Frame

Site-local East-North-Up metres; origin = centre of the chosen footprint on the ground
(`site.json → origin` has its lat/lon and DEM elevation). z = 0 is ground at the origin.
`overview.png` has a 5 m scale bar and north arrow; LiDAR plane labels show pitch and
top height above ground (`h`).

## Wing fields

| Field | Meaning |
|---|---|
| `id` | short unique id (`M`, `G`, `F`…) — parameters are addressed as `M.length` |
| `type` | `gable` `hip` `pyramid` `shed` `flat` `gambrel` `mansard` |
| `cx`, `cy` | centre of the WALL rectangle (m) |
| `azimuth` | compass bearing of the length axis = ridge direction for gable/hip (0 = N, 90 = E) |
| `length`, `width` | outside wall dimensions along / across the azimuth |
| `eave_height` | height of the wall plate line (where roof plane meets outer wall face) above z=0 |
| `pitch` | rise/run of the +v side (left of the azimuth direction); `0.5` = 6/12 |
| `pitch_b` | rise/run of the −v side (asymmetric gable / saltbox); default = `pitch` |
| `end_pitch` | hip / mansard end slopes; default = `pitch` |
| `upper_pitch`, `break_inset` | gambrel / mansard upper slope and plan distance wall→break line |
| `eave_overhang`, `rake_overhang` | horizontal overhang beyond the walls (eave sides / gable ends) |
| `shed_high_overhang` | shed: overhang on the high side |
| `eave_height_b` | plate height of the −v side (lopsided / split-level gables with equal pitch); default = `eave_height` |
| `eave_overhang_b` | overhang of the −v side, up to 4 m (a roof that continues over a porch); default = `eave_overhang` |
| `roof_only` | `true` = roof patch with no walls (porch roof, junction patch between wings, carport) |
| `base_z` | wall bottom; with `spec.ground` it is an offset above grade (e.g. a wing on a raised deck) |

Roof of a wing = lower envelope of planes through the wall lines, clipped to the outline grown
by the overhangs. Wings combine like solids: the higher surface wins, except a lower roof is
kept where it runs under a taller wing's overhang (it is real roofing).

Shed: low eave on the +v side. For an azimuth-90 (east) wing, +v is north; use azimuth 270
to put the low side south.

Nearly coplanar pieces from different wings (slope within 0.004, height within 3 cm where they
touch) are merged into one facet, so a plane may be built from several wings (e.g. a main
slope continued by a `roof_only` patch) without double counting or fake seam edges.

## spec.json

```json
{
  "wings": [ {"id": "M", "type": "gable", "cx": 0, "cy": 0, "azimuth": 90, "length": 12, "width": 10,
              "eave_height": 3.4, "pitch": 0.333, "eave_overhang": 0.45, "rake_overhang": 0.3} ],
  "free":  ["M.cx", "M.cy", "M.azimuth", "M.length", "M.width", "M.eave_height", "M.pitch"],
  "ties":  [["M.eave_overhang", "G.eave_overhang"]],
  "priors": {"M.eave_overhang": {"value": "18in", "sigma": "6in"}},
  "ground": [-0.018, 0.007, 0.28],
  "openings": [{"facade": "E", "width": "16ft", "height": "7ft", "count": 1, "label": "garage door"},
               {"facade": "E", "width": "36in", "height": "80in", "count": 1, "label": "front door"}]
}
```

* `ground` = finished grade plane z = a x + b y + c in the model datum; walls start there
  (`pm.py suggest` fills it from the LiDAR ground fit; refine from class-2 points near the walls).
* `openings` = doors/windows per facade (compass of the outward normal) for net siding area.
* `ties` = groups of parameters forced equal; overlapping groups are merged.
* Model datum: z = 0 is the LiDAR ground elevation at the site origin (a level datum, stored in
  `site.json → datum_m`). `pm.py obs JOB import-geo` converts lon/lat + absolute-elevation
  observations (e.g. a city 3D wireframe) into this frame.

## Observation targets

| Target | Example value | Typical source |
|---|---|---|
| `<wing>.<field>` | `"M.length": "39' 7\""` | tape, plans |
| `roof.area`, `roof.area_plan` | `"25.3 sq"`, `"2530 sqft"`, `"235 m2"` | past report |
| `edge.ridge` `edge.hip` `edge.valley` `edge.eave` `edge.rake` `edge.headwall` `edge.sidewall` | `"80 ft"` | past report |
| `roof.pitch_weighted`, `roof.pitch_max` | `"4/12"` | past report |
| `pitch@` + `"xy": [x, y]` | `"4/12"` | pitch gauge on the facet at (x, y) |
| `z@` + `"xy"` | `"5.1m"` | laser/drone height of a roof point |
| `azimuth@` + `"xy"` | `182` | compass on a facet |
| `wing.<id>.ridge_height` | `"16ft 9in"` | laser / drone |
| `footprint.area`, `footprint.perimeter` | `"2130 sqft"` | survey, plans (outside of walls) |
| `wall.area` | `"2500 sqft"` | siding report (gross) |
| `building.height` | `"17 ft"` | |
| `roof_z` (vector) | `"points": [[x,y,z],...]` | LiDAR / photogrammetry |
| `outline` (vector) | `"polygon": [[x,y],...], "which": "roof_outline"\|"footprint", "shift": "<src>"` | traces |

Every scalar needs `sigma` (absolute with units, or `"2%"`), a `source`, and ideally `kind`
(`tape`, `gauge`, `photo`, `lidar`, `past_report`, `assessor`) and `date`.

`past_measurements.csv` for `pm.py obs JOB import`:

```csv
target,value,sigma,source,kind,date
roof.area,25.33 sq,2%,EagleView #12345,past_report,2019-06-02
edge.ridge,79.5 ft,2%,EagleView #12345,past_report,2019-06-02
edge.valley,31 ft,3%,EagleView #12345,past_report,2019-06-02
M.length,39' 8",1in,inspector tape,tape,2026-11-10
pitch@,4/12,0.25/12,inspector gauge,gauge,2026-11-10
```
(`pitch@` rows also need an `xy` column like `"-1.0,3.0"`; get xy from the overview.)
