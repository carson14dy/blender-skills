# Property measurement report

- **Site**: residential test house, Ames, IA (public 3DEP LiDAR + OSM/Microsoft footprints; coordinates omitted)
- **Generated**: 2026-11-16T02:01
- **Method**: parametric model fitted to all evidence by robust weighted least squares; ± values are 1-sigma (68 %) uncertainties propagated from the evidence.

## Roof summary

| Quantity | Value | Metric |
|---|---|---|
| Total roof area | 2534 ± 52 ft² (25.34 ± 0.52 sq) | 235.4 ± 4.9 m² |
| Plan (footprint-projected) roof area | 2418 ft² | 224.6 m² |
| Facets | 6 | |
| Predominant pitch (area-weighted) | 3.7/12 | 17.2° |
| Suggested waste | 12 % (4 hips+valleys) → order 28.38 sq | |
| Max height above grade | 16.8 ± 0.0 ft | 5.13 m |

## Lengths

| Edge | Length (ft) | Length (m) |
|---|---|---|
| Ridge | 80.0 ± 1.2 | 24.39 ± 0.38 |
| Valley | 31.0 ± 1.7 | 9.44 ± 0.52 |
| Rake | 142.5 ± 2.6 | 43.44 ± 0.79 |
| Eave | 124.7 ± 1.8 | 38.01 ± 0.54 |
| Transition | 1.9 ± 3.7 | 0.57 ± 1.13 |
| Headwall | 14.6 ± 1.3 | 4.44 ± 0.40 |
| Sidewall | 37.7 ± 2.4 | 11.49 ± 0.72 |
| Drip edge (eaves+rakes) | 267.2 | 81.45 |
| Ridge cap (ridges+hips) | 80.0 | 24.39 |
| Step flashing (sidewalls) / headwall | 37.7 / 14.6 | |

## Facets

| Facet | Pitch | Faces | Area (ft²) | Area (m²) | Note |
|---|---|---|---|---|---|
| F1 | 4.0/12 | N | 796 | 73.9 |  |
| F2 | 4.0/12 | S | 634 | 58.9 | partly under upper overhang |
| F3 | 4.3/12 | N | 259 | 24.1 | partly under upper overhang |
| F4 | 2.5/12 | S | 430 | 39.9 | partly under upper overhang |
| F5 | 3.7/12 | W | 221 | 20.6 | partly under upper overhang |
| F6 | 3.7/12 | E | 194 | 18.0 |  |

| Pitch | Area (ft²) | Share |
|---|---|---|
| 2.5/12 | 430 | 17 % |
| 3.5/12 | 415 | 16 % |
| 4/12 | 1430 | 56 % |
| 4.5/12 | 259 | 10 % |

## Walls (siding)

| Facade | Area (ft²) | Area (m²) |
|---|---|---|
| N | 640 | 59.5 |
| E | 606 | 56.3 |
| S | 683 | 63.4 |
| W | 596 | 55.3 |
| **Total (gross, openings not deducted)** | **2524 ± 73** | 234.5 ± 6.7 |

Footprint (outside of walls): 2142 ft² (199.0 m²), perimeter 207.1 ft.

## Evidence reconciliation

Fit: χ² = 193.5 on 839 dof (variance factor 0.23; ≈1 means the stated source uncertainties are realistic).

| Source | Target | Observed | Model | Residual (σ) | Flag |
|---|---|---|---|---|---|
| auto:osm footprint | outline (130 samples) | | RMS 0.154 m | 0.3 | ok |
| auto:ms footprint | outline (118 samples) | | RMS 0.119 m | 0.2 | ok |
| auto:lidar IA_NorthCentral_2_2020 | roof_z (483 samples) | | RMS 0.072 m | 0.6 | ok |
| auto:lidar IA_NorthCentral_2_2020 outline | outline (127 samples) | | RMS 0.124 m | 0.3 | ok |

## Fitted parameters

| Parameter | Value | 1σ |
|---|---|---|
| M.cx | -0.739 m (-2.42 ft) | 0.421 m |
| M.cy | -0.321 m (-1.05 ft) | 0.024 m |
| M.azimuth | 88.54° | 0.33° |
| M.length | 12.073 m (39.61 ft) | 0.829 m |
| M.width | 10.338 m (33.92 ft) | 0.412 m |
| M.eave_height | 3.406 m (11.17 ft) | 0.070 m |
| M.pitch | 4.0/12 | 0.06/12 |
| G.cx | 7.634 m (25.05 ft) | 0.418 m |
| G.cy | -0.919 m (-3.02 ft) | 0.084 m |
| G.length | 5.768 m (18.92 ft) | 0.827 m |
| G.width | 10.305 m (33.81 ft) | 0.383 m |
| G.eave_height | 3.258 m (10.69 ft) | 0.053 m |
| G.pitch | 4.3/12 | 0.23/12 |
| G.pitch_b | 2.5/12 | 0.08/12 |
| F.cx | -3.682 m (-12.08 ft) | 0.044 m |
| F.cy | -5.267 m (-17.28 ft) | 0.224 m |
| F.width | 6.907 m (22.66 ft) | 0.465 m |
| F.eave_height | 3.421 m (11.22 ft) | 0.075 m |
| F.pitch | 3.7/12 | 0.15/12 |
| M.eave_overhang | 0.366 m (1.20 ft) | 0.147 m |
| shift.osm.dx | 1.020 m (3.35 ft) | 0.292 m |
| shift.osm.dy | -1.191 m (-3.91 ft) | 0.245 m |
| shift.ms.dx | -0.041 m (-0.13 ft) | 0.499 m |
| shift.ms.dy | -0.429 m (-1.41 ft) | 0.476 m |

_Model geometry is exact for the fitted parameters; uncertainty comes only from the evidence._
