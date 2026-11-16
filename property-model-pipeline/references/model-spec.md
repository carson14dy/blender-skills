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
| `base_z` | wall bottom (split levels, a wing sitting on another storey) |

Roof of a wing = lower envelope of planes through the wall lines, clipped to the outline grown
by the overhangs. Wings combine like solids: the higher surface wins, except a lower roof is
kept where it runs under a taller wing's overhang (it is real roofing).

Shed: low eave on the +v side. For an azimuth-90 (east) wing, +v is north; use azimuth 270
to put the low side south.

## spec.json

```json
{
  "wings": [ {"id": "M", "type": "gable", "cx": 0, "cy": 0, "azimuth": 90, "length": 12, "width": 10,
              "eave_height": 3.4, "pitch": 0.333, "eave_overhang": 0.45, "rake_overhang": 0.3} ],
  "free":  ["M.cx", "M.cy", "M.azimuth", "M.length", "M.width", "M.eave_height", "M.pitch"],
  "ties":  [["M.eave_overhang", "G.eave_overhang"]],
  "priors": {"M.eave_overhang": {"value": "18in", "sigma": "6in"}}
}
```

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
