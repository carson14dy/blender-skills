# Example: 3-wing house, Ames IA — public data only

Evidence: USGS 3DEP LiDAR (IA_NorthCentral_2_2020, 3.3 pts/m²), Microsoft + OSM footprints,
Esri orthophoto. No site visit, photos or past reports. `spec.json` = main gable + garage with an
asymmetric (4.3/12 | 2.5/12) roof + front cross-gable.

* Roof 2534 ± 52 ft² (25.3 ± 0.5 sq); LiDAR fits the model with 7 cm RMS.
* The OSM footprint was found to be offset by ~1 m E / 1.2 m S (estimated `shift.osm`).
* Adding a deliberately wrong "2009 report" of 19 squares: flagged at +16.7σ, excluded,
  result unchanged (data snooping).
* Uncertainty is dominated by where the main roof ends over the garage — one tape
  measurement of the garage width would cut the area σ roughly in half.

`overview.jpg` evidence + fitted model · `plan.jpg` / `hero.jpg` Blender renders · `model.glb` metric glTF.
Imagery © Esri, Maxar, Earthstar Geographics; footprints © OpenStreetMap contributors, Microsoft (ODbL).
