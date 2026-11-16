# Free ($0) capture-to-measurement workflows for one residential roof: drone, phone, single-photo, splats

Scope: $0 software that a small roofing business may use commercially, used with hardware it may already own (a consumer drone, a phone), to get roof area within about 1–2% and pitch within ±1/12, then bring the result into Blender or Three.js. Research date: November 2026. Each fact carries a URL. Inferences and worked arithmetic are kept in the "Inferences" sections.

Accuracy budget, worked out here because it drives every later recommendation (inference, simple geometry):
- Area grows with the square of linear scale. A 1% area target allows only about 0.5% linear scale error: 5 cm over a 10 m eave, or 2.5 cm over a 5 m baseline.
- Plane area = footprint / cos(pitch). At 6/12 (26.6°), a 1° pitch error changes area by about tan(26.6°) × 0.01745 ≈ 0.9%. So 1–2% area needs pitch good to about 1–2°, which is tighter than the stated ±1/12 tolerance. Between 5/12 and 7/12, one step of x/12 is about 3.7–4°.
- In height terms, a 1/12 pitch error on a 4 m horizontal run is 0.33 m of rise. Centimetre-level vertical noise therefore meets the pitch target easily. Scale is the hard part, not pitch.

---

## 1. Free drone photogrammetry: pipelines, accuracy, GSD, flight pattern, flight apps, Part 107

### Takeaway
A consumer DJI drone flown as a low nadir grid plus a 45° oblique orbit or cross-grid at about 1 cm GSD, processed in OpenDroneMap/WebODM or COLMAP (+ OpenMVS), gives relative geometry of about 1–3× GSD, i.e. a few cm. That is good enough for pitch and edge lengths. Scale from drone GPS alone is not reliable enough for 1–2% area. The one published roof study that relied on GPS-scaled drone data got a 0.6% average area difference, but its worst roof was off by 2.7%, so add a taped baseline or GCPs. Commercial flight needs a Part 107 certificate: a test fee of about $175 plus $5 drone registration. Free flight planning means DJI Fly's built-in waypoints. Dronelink, Litchi and Map Pilot Pro are paid.

### Cited Findings
**Roof-specific accuracy studies**
- Haag Engineering study (17 buildings, about 535 squares, pitches flat to 12:12, Dallas–Fort Worth). On the 13 roofs that were also hand-measured, drone-derived area differed by +1.2% to −2.7% per roof, with an average difference of 0.6% (1.1% average absolute) against an industry goal of ±2%. The largest miss was 95 sq ft (2.7%), on a roof with overhanging trees, and the smallest was 3 sq ft (0.2%). Scaling came from the drone's own onboard GPS, not GCPs or RTK. This was a proprietary Kespry drone with a Pointivo automated pipeline, not free software. — [RT3 Think Tank / Pointivo](https://rt3thinktank.com/drone-photogrammetry-test-are-automated-3d-roof-measurements-accurate-enough/); [PR Newswire 2017](https://www.prnewswire.com/news-releases/independent-study-by-haag-engineering-verifies-the-precision-and-efficacy-of-using-kespry-industrial-drones-for-measuring-and-inspecting-roofs-300507406.html)
- Mini-UAV rooftop area study (38 rooftop footprints, Thailand, 2024), compared with terrestrial survey. Areas measured on the 2D orthomosaic had 1.36% mean relative error (MAE 2.14 m², "98.63% accuracy"). The 3D DSM method was worse ("95.00% accuracy"). These are footprints, not sloped areas. — [IEEE GIS-IDEAS 2024](https://doi.org/10.1109/gis-ideas63212.2024.10991127)
- UK AAIB tape check (Inspire, 40 m height, 75 images). Pix4D distances on 9–15 m legs were 0.3–0.4% short of tape (3–4 cm). After one taped scale bar was added, the differences fell to 0.00–0.01 m. This shows that GPS-scaled models carry a systematic scale error, and that a single scale bar removes it. — [ICAO/AAIB PDF](https://www.icao.int/sites/default/files/airnavigation/AIG/6-Hawkins-Using-a-drone-and-photogrammetry-software-V3.pdf)
- EagleView commissioned CompassData (2025, Denver) to check EagleView reports against drone LiDAR (Optech CL360 on a Freefly Alta X) plus a Trimble X7 TLS. This shows the benchmark the industry uses as ground truth. The source is the vendor itself. — [EagleView/CompassData PDF](https://www.eagleview.com/wp-content/uploads/2025/07/CompassData-Roof-Measurements-Analysis-2025-.pdf)

**OpenDroneMap / WebODM accuracy and GCPs**
- WebODM docs: relative accuracy is "in the order of 1 to 3 times the average GSD". Standard drone GPS gives 2–6 m horizontal absolute accuracy, with vertical 3–4× worse. With GCPs, absolute accuracy improves to about 2.5× GSD horizontal and 4× GSD vertical. For a smaller GSD the docs recommend a flight altitude of 3–4× the height of the highest point. — [WebODM GCP docs](https://docs.webodm.org/ground-control-points/); [ODM map-accuracy docs](https://docs.opendronemap.org/map-accuracy/)
- ODM GCP practice: at least 5 GCPs, each visible in at least 5 images (at least 3 for natural features). The `gcp_list.txt` header can be EPSG, PROJ or `WGS84 UTM 14N`. Each line is `geo_x geo_y geo_z im_x im_y image_name [label]`. `--use-exif` ignores the GCPs. `--force-gps` combines RTK EXIF with GCPs. GCPs can be tagged in the POSM GCPi tool, which is built into WebODM, or in the GCP Editor Pro plugin. — [ODM GCP docs](https://docs.opendronemap.org/gcp/)
- ODM maintainer: there are no "scale constraints" (scale bars) in ODM yet. Relative accuracy improves with careful capture, `--feature-quality`, and setting `--gps-accuracy` near the dataset's real GPS error, since the default is coarse. — [ODM community, 2024](https://community.opendronemap.org/t/increase-relative-accuracy/21617)
- Relative scale can fail without GCPs. One user's no-GCP ortho flown at 125 ft (about 1 cm GSD) measured a 100-yard football field as 93 yards in QGIS, about 7% short. — [ODM community](https://community.opendronemap.org/t/poor-relative-accuracy-of-orthomosaic-without-ground-control/2994)
- Consumer drone plus WebODM, FIG 2026 (DJI Mavic Air 2, 3.8 cm GSD, Trimble R10 GCPs). With no GCPs, planimetric RMSE was 3.379 m. With 4 edge GCPs it was 0.085 m H / 0.283 m V, with 6 GCPs 0.083 / 0.166 m, and with 11 GCPs 0.064 / 0.053 m. — [FIG Congress 2026 abstract](https://fig.net/resources/proceedings/fig_proceedings/fig2026/papers/ts08d/TS08D_seboo_ramgoolam_et_al_14135_abs.pdf)
- Rolling shutter matters on Mavic-class drones. On the same data and 4 GCPs, one user found 16.5 cm radial RMSE in WebODM against 2.46 cm in a commercial processor that applies rolling-shutter correction, at 1.6 cm GSD while flying at about 18 m/s. — [ODM community 2022](https://community.opendronemap.org/t/ground-control-point-application-comparison/10481)
- WebODM's built-in measurement: the 2D map view measures length, area and volume. The Potree 3D viewer has 12 tools, including distance, height, angle, area, volume and profile. ODM has no roof-report plugin (none found). — [WebODM Potree docs](https://docs.webodm.org/tutorials/potree-3d-viewer/); [OCWGIS WebODM tutorial](https://courses.gisopencourseware.org/mod/book/view.php?chapterid=1442&id=500)
- ODM outputs: georeferenced point cloud (`odm_georeferencing/odm_georeferenced_model.laz/ply/csv`), textured mesh (`odm_texturing/odm_textured_model_geo.obj`), GeoTIFF orthophoto, and DSM/DTM (`odm_dem/dsm.tif`). For urban roofs the tutorials recommend raising `--mesh-size` to 300000–600000 and `--mesh-octree-depth` to 10–11. — [ODM outputs](https://docs.opendronemap.org/outputs/); [ODM tutorials](https://docs.opendronemap.org/tutorials/)
- ODM hardware: the minimum is a 64-bit CPU, 4 GB RAM and 20 GB disk, which handles about 100–200 images. The recommendation is 16 GB RAM and 100 GB disk for a few hundred images. ODM docs say a GPU "currently has no impact on performance". The WebODM README says CUDA acceleration is supported on Linux/WSL via `--gpu` with nvidia-docker. The two sources conflict; GPU use is probably partial and optional. Either way, ODM runs CPU-only in Docker, which suits a Linux cloud container. — [ODM install docs](https://docs.opendronemap.org/installation/); [WebODM GitHub](https://github.com/OpenDroneMap/WebUI/)
- A 2026 blog post (aerocartwright.com) reports a DJI Mini with 6 GCPs reaching a checkpoint RMSE of about 3.2 in, limited by smartphone-RTK GCP accuracy of ±2–4 in. It says Metashape, Pix4D and WebODM differ "not much". Its own table is labelled "illustrative ... not a controlled benchmark", so treat it as low weight. — [AeroCartwright](https://aerocartwright.com/library/dji-mini-mapping-accuracy-benchmarks/)

**COLMAP, OpenMVS, Meshroom, newer pipelines**
- COLMAP 4.0.0 (14 March 2026) added GLOMAP global SfM as a first-class mapper (`global_mapper`, `automatic_reconstructor --mapper GLOBAL`), native ALIKED + LightGlue (ONNX, CPU+GPU), EXIF auto-rotation, and new mesh and Python tooling. The standalone GLOMAP repo is now deprecated (BSD-3). — [COLMAP 4.0.0 release](https://github.com/colmap/colmap/releases/tag/4.0.0); [COLMAP changelog](https://colmap.github.io/changelog.html); [GLOMAP LICENSE](https://github.com/colmap/glomap/blob/main/LICENSE)
- COLMAP reads EXIF GPS as pose priors (`pose_prior_mapper`). `model_aligner` can align to GPS/ENU/ECEF or custom coordinates, can optionally skip scale estimation, and can write out the 4×4 transform. — [COLMAP FAQ](https://github.com/colmap/colmap/blob/main/doc/faq.rst); [model_aligner PR #1177](https://github.com/colmap/colmap/pull/1177); [issue #1766](https://github.com/colmap/colmap/issues/1766)
- COLMAP dense MVS (`patch_match_stereo`) is "only implemented on the GPU using CUDA". Sparse SfM runs on CPU. — [COLMAP issue #192](https://github.com/colmap/colmap/issues/192); [COLMAP CLI docs](https://colmap.github.io/cli)
- OpenMVS is licensed AGPL-3.0. Densify uses CUDA for PatchMatch depth estimation only when it is available. A maintainer said the other steps run on CPU. — [openMVS GitHub](https://github.com/cdcseacave/openMVS/); [issue #929](https://github.com/cdcseacave/openMVS/issues/929); [issue #306](https://github.com/cdcseacave/openMVS/issues/306)
- Meshroom and AliceVision are MPL-2.0. AliceVision depth-map computation needs an NVIDIA CUDA GPU, and the developers have no plans to port it. — [Meshroom COPYING](https://github.com/alicevision/Meshroom/blob/develop/COPYING.md); [Meshroom FAQ](https://meshroom-manual.readthedocs.io/en/latest/faq/needs-cuda/needs-cuda.html)
- Feed-forward 3D models from 2024–2026:
  - VGGT: in July 2025 Meta relicensed the code for commercial use, excluding military use, and released a separate gated checkpoint, VGGT-1B-Commercial. The original checkpoint stays non-commercial. — [VGGT GitHub](https://github.com/facebookresearch/vggt); [HF VGGT-1B-Commercial](https://huggingface.co/facebook/VGGT-1B-Commercial)
  - MASt3R / DUSt3R: CC BY-NC-SA 4.0, non-commercial, and the training-data licences restrict further. — [MASt3R LICENSE](https://github.com/naver/mast3r/blob/main/LICENSE); [CHECKPOINTS_NOTICE](https://github.com/naver/mast3r/blob/main/CHECKPOINTS_NOTICE)

**Flight pattern and GSD**
- ODM recommends, for full 3D: a nadir flight at 60% overlap plus a 45° gimbal cross-grid at 70–80% overlap. For 2D/2.5D it recommends 70–80% overlap shot 5–10° off-nadir. — [ODM Flying Tips](https://docs.opendronemap.org/flying/)
- A practitioner who flew grids at 40 and 50 m (85° gimbal, 70/65% overlap) plus one 45° orbit at 30 m still got holes in walls. Adding façade shots at 14 m fixed them. — [ODM community](https://community.opendronemap.org/t/best-settings-for-3d-buildings-and-terrain/12093)
- Pix4D suggests at least 75% front / 60% side overlap in general, and circular missions for a single building. — [Pix4D image acquisition](https://support.pix4d.com/hc/en-us/articles/202557459); [Pix4D circular missions](https://www.pix4d.com/blog/3d-models-choose-angle-between-images-circular-missions)
- Vendor roof guides:
  - Trendspek: nadir at roof height + 12 m, at most 2 m/s, 75/75 overlap, for a GSD under 3 mm on a Mavic 3E. — [Trendspek PDF](https://page.trendspek.com/hubfs/%F0%9F%93%99%20Capture%20Guides%20and%20Resource%20PDFs/Trendspek%20Capture%20Guide%20Top%20Down%20and%20Residential%20Surveys.pdf)
  - SkySnap: 20–40 m AGL for 1–2 cm GSD, a grid plus an angled orbit, at least 80/80 overlap. — [SkySnap](https://skysnap.com/us/drone-mission-planning-linear-construction-vs-3d-roof-model/)
  - SKAND: 80/60 overlap, nadir plus oblique orbits. — [SKAND](https://intercom.help/skandio/en/articles/12249554-steps-on-proper-data-acquisition-of-aerial-drone-surveys-for-buildings)
- DJI Mini 4 Pro camera: 1/1.3-inch 48 MP sensor (9.68 × 7.26 mm) behind a 6.72 mm lens. GSD is 2.1 cm/px at 60 m in 12 MP mode and 1.1 cm in 48 MP mode. The general formula is GSD = H × Sw / (f × W). — [Skyplanr Mini 4 Pro guide](https://skyplanr.com/guides/dji-mini-4-pro-waypoint-missions); [OnlineMapMaker GSD calculator](https://onlinemapmaker.com/gsd-calculator/)
- On the Mini 4 Pro, 48 MP mode forces a 5 s photo interval and about 2.5 m/s to hold 80% overlap. The 12 MP mode allows a 3 s interval at 2–7 m/s. — [Pix-Pro Mini 4 Pro waypoints](https://www.pix-pro.com/blog/mini4pro-waypoints)
- Shiny or repetitive roofs (sheet metal) can garble matching in WebODM. — [r/UAVmapping](https://www.reddit.com/r/UAVmapping/comments/1kgubwu/help_with_webodm_stitching_over_sheetmetal_roofs/)

**Flight-planning apps (cost and commercial status)**
- DJI Fly has built-in Waypoint Flight on the Mini 4 Pro, at no extra cost. Points are set by hand, map-pinned points default to 50 m, and routes are saved for repeat flights. Laying out an even grid by hand is impractical, so third-party planners generate KMZ files that DJI Fly can load. — [Uplink Imaging](https://www.uplinkimaging.com/pages/mini-4-pro-waypoints); [SmartWaypoints](https://www.smartwaypoints.com/guides/dji-mini-4-pro-waypoints); [FlyTheGrid](https://flythegrid.com/mini-4-pro.php)
- Dronelink hobbyist plans are one-time purchases: Basic $29.99 (waypoints and orbits on Mini/Air), Premium $59.99 (adds mapping), Elite $119.99. They are labelled "for recreation, students, or non-profits", so commercial missions need a Professional plan. KMZ export needs Elite or a professional tier. Dronelink is not free, and on the Mini 4 Pro it is Android-only with the RC-N2/N3 controller. — [Dronelink hobbyist pricing](https://app.dronelink.com/pricing/hobbyist); [plan comparison](https://app.dronelink.com/pricing/hobbyist/compare); [Dronelink supported drones](https://www.dronelink.com/download); [KMZ export](https://support.dronelink.com/hc/en-us/articles/4410621290387-Onboard-DJI-Waypoint-Missions-Convert-and-Export-to-KMZ)
- Map Pilot Pro's advanced features come with a Maps Made Easy subscription (Pro is $15/month) or with pay-as-you-go processing points. It is not free. — [Map Pilot Pro](https://www.mapsmadeeasy.com/mappilotpro); [Maps Made Easy pricing](https://www.mapsmadeeasy.com/pricing); [DME support](https://support.dronesmadeeasy.com/hc/en-us/community/posts/27859424052756-Subscriptions-Pro-Pricing)

**FAA Part 107**
- Any non-recreational operation, including roof work for a business, needs a Part 107 Remote Pilot Certificate. Applicants must be at least 16 and must pass the UAG knowledge test. — [FAA AIP 11-5](https://www.faa.gov/air_traffic/publications/atpubs/aip_html/chap11_section_5.html); [FAA commercial operators](https://www.faa.gov/uas/commercial_operators); [14 CFR 107](https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-107)
- Costs: testing centres charge about $175 for the initial test. Recurrent training every 24 calendar months is a free FAA online course. Registration is $5 per drone for 3 years. The drone must comply with Remote ID. — [FAA registration](https://www.faa.gov/uas/getting_started/register_drone); [Passy guide citing FAA](https://www.passyprep.com/exams/faa-part-107/guides/part-107-test-cost/)
- Part 107 operators may fly over people and at night without a waiver if they meet the Operations Over People rule (effective 21 April 2021). — [FAA commercial operators](https://www.faa.gov/uas/commercial_operators)

### Inferences
- **Best $0 drone recipe for one house (inference from the sources above):**
  1. Fly a nadir grid at roof height + 15–25 m, about 0.7–1.1 cm GSD on a Mini 4 Pro in 12 MP mode. GSD is set by height above the roof surface, not above takeoff.
  2. Fly a 45° oblique orbit, or a 45° cross-grid, at a similar height with photos every 5–10°, at 75–80% overlap.
  3. Fly slowly (2–3 m/s) or hover per shot to limit rolling-shutter blur.
  4. Put the sun behind you or shoot under overcast sky.
  5. Process with ODM using `--feature-quality ultra`, `--mesh-octree-depth 11`, `--pc-quality high` and `--dsm`, set `--gps-accuracy` to about 3–5 m, and add GCPs or a scale check (section 2).

  COLMAP 4 (global mapper) + OpenMVS is the alternative when a CUDA GPU is available. COLMAP sparse SfM + OpenMVS also runs on CPU.
- At 1 cm GSD, a relative accuracy of 1–3× GSD is about 1–3 cm. Edge lengths of 6–15 m would then be within about 0.2–0.5%, if scale is right.
- Drone GPS alone gave 0.3–0.4% scale error in the AAIB test, but about 7% in the football-field anecdote. Kespry's GPS scaling worked in the Haag study, but Kespry may have used a better GNSS. A contractor cannot predict which case they will be in, so every job should include at least one taped check distance.
- **AGPL note (inference):** ODM, WebODM and OpenMVS are AGPL-3.0. AGPL allows commercial use. Its source-sharing obligations apply when you distribute the software, or when you let outside users interact with a modified version over a network. Running it internally to produce measurements for estimates is allowed. Running WebODM as a customer-facing web portal would bring obligations to share source of any modifications. "Internal use only" in the studio notes is a safe policy, not a licence requirement.
- Sub-250 g drones (Mini series) used commercially still need Part 107 certification, and need registration under Part 107 (assumption based on FAA rules; the weight exemption applies only to recreational flyers; not separately verified this session).

### Gaps
- I found no peer-reviewed study that measures residential roof area or pitch with free software (ODM/COLMAP) and a sub-$1k consumer drone against tape. The Haag/Kespry study used a proprietary pipeline.
- I could not confirm whether SmartWaypoints, FlyTheGrid, Skyplanr or Pix-Pro Waypoints have free tiers or commercial-use terms. Their pricing was not retrieved.
- No published per-roof pitch error (in degrees) for free pipelines was found.

---

## 2. Scale and accuracy without paid GNSS gear: markers, baselines, EXIF, free GCPs, checks

### Takeaway
For 1–2% area, scale (linear error ≤0.5%) is the main thing to control. Without RTK, use local-coordinate GCPs: 4–6 ArUco targets whose spacing is taped with a measuring tape, then auto-detect them with Find-GCP for ODM, or use COLMAP `model_aligner` with custom coordinates, or simply rescale in Blender from two taped points. Check every job against one or two independent taped lengths, such as a gutter run or the eave-to-eave width.

### Cited Findings
- Find-GCP, now an OpenDroneMap project from BME's GeoForAll Lab, detects OpenCV ArUco markers in photos and writes ODM `gcp_list.txt` automatically. It installs with `pip install opencv-python opencv-contrib-python`. — [ODM Find-GCP page](https://opendronemap.org/findgcp/); [zsiki/Find-GCP](https://github.com/zsiki/Find-GCP); [ODM announcement 2022](https://opendronemap.org/2022/04/find-gcp-joins-opendronemap/)
- In the AAIB test, adding one taped scale distance cut tape-vs-model differences from 3–4 cm (0.3–0.4%) to 0–1 cm. — [ICAO/AAIB PDF](https://www.icao.int/sites/default/files/airnavigation/AIG/6-Hawkins-Using-a-drone-and-photogrammetry-software-V3.pdf)
- ODM has no scale-bar constraint, so scale must come from GPS, GCPs or post-hoc rescaling. — [ODM community](https://community.opendronemap.org/t/increase-relative-accuracy/21617)
- COLMAP `model_aligner` accepts custom (non-GPS) reference coordinates and has a "plane" option for when no GPS exists. It can export the similarity transform. — [COLMAP PR #1371](https://github.com/colmap/colmap/pull/1371); [issue #1766](https://github.com/colmap/colmap/issues/1766)
- Practitioners say no photogrammetry tool can recover true scale from images alone. They advise 5–10 measured distances or scale bars, and say DJI geotags are "okay-ish". — [r/photogrammetry 2025](https://www.reddit.com/r/photogrammetry/comments/1klhc4s/can_metashape_estimate_realworld_scale_from_image/)
- Another practitioner says scale bars around the building work, plus RAW photos with distortion correction off and consistent white balance. — [r/photogrammetry 2026](https://www.reddit.com/r/photogrammetry/comments/1sfsigd/measuring_outside_of_a_building_via_drone/)
- A roofer-facing r/UAVmapping thread (2026) asks about a Mini 5 Pro without GCPs. Replies say a known length was used to confirm scale, "probably within 5cm", and suggest measuring a shingle as a reference. These are anecdotes. — [r/UAVmapping](https://www.reddit.com/r/UAVmapping/comments/1t9v31n/question_webodm_and_roof_measurement_accuracy/)
- Another practitioner skips control points: they measure something on site during the flight, then scale the WebODM mesh in other software. — [r/UAVmapping 2020](https://www.reddit.com/r/UAVmapping/comments/kn4xn1/roofsnap_or_dronedeploy_the_better_roof_measuring/)
- Drone GPS absolute error is 2–6 m horizontal. This shifts the model but does not set its scale. A survey of no-GCP consumer data reported 3.38 m planimetric RMSE. — [WebODM GCP docs](https://docs.webodm.org/ground-control-points/); [FIG 2026](https://fig.net/resources/proceedings/fig_proceedings/fig2026/papers/ts08d/TS08D_seboo_ramgoolam_et_al_14135_abs.pdf)

### Inferences
- **Practical $0 scale and level workflow (inference):**
  1. Print 4–6 large ArUco markers (DICT_4X4 or 5X5, at least 30–40 cm, on foam board or plywood; extra purchase is printing and board only). Place them on the ground around the house, plus one on a flat deck or driveway.
  2. Tape the distances between markers. Use a 100 ft tape; a laser distance meter is an optional extra purchase.
  3. Assign local coordinates: put marker A at the origin and marker B on the +X axis, then trilaterate the rest from the taped distances. Set Z to 0 on markers that sit on a level surface, or take Z from a cheap laser or water level.
  4. Write `gcp_list.txt` with a local projected CRS (for example `WGS84 UTM 14N` offset to near the house, since Sioux Falls is in UTM zone 14N), or run Find-GCP to fill in the pixel coordinates.

  Alternatives: run ODM with EXIF GPS, then rescale the result in Blender with a similarity transform from two taped points, and level it with three points known to share a height, or with the gravity direction from the ground plane.
- Area error ≈ 2 × linear scale error, so a 10 m taped baseline good to ±1 cm (0.1%) adds only about 0.2% area error. Longer baselines spanning the whole house are better.
- Levelling matters for pitch. A 1° tilt of the whole model adds about +1° pitch on one side of a gable and −1° on the other, while area stays nearly unchanged. Averaging opposite faces of a symmetric gable is a quick check for tilt.
- Using the public house footprint as a check: it is only useful as a gross-error check, because public footprint or parcel data is usually metre-level (see the public-aerial notes from other researchers). It cannot validate 1–2%.

### Gaps
- I found no published accuracy figures for Find-GCP in local, tape-only coordinates on a small residential site.
- I found no source quantifying how DJI Mini-series EXIF GPS scale error varies between flights. The AAIB 0.3% figure and the football-field 7% anecdote bracket a wide range.

---

## 3. Phone capture: LiDAR apps with free export and commercial use, Android options, accuracy

### Takeaway
iPhone/iPad Pro LiDAR range is only about 5 m. Accuracy is about 1–2 cm on small objects but several cm to about 10 cm at building scale. That makes phone LiDAR useful from a ladder or on the roof (eave and rake lengths, pitch of one plane), not for whole-roof capture from the ground. Free-export options without a commercial ban: 3d Scanner App (free tier exports OBJ, STL, PLY, glTF, USDZ; a commercial clause in its ToS was not found), SiteScape (free account exports unlimited scans, PLY/E57), and KIRI Engine Basic (free unlimited exports, iOS/Android/Web). Polycam Free allows commercial use with attribution, but exports only glTF. Scaniverse Classic is free but non-commercial.

### Cited Findings
**Accuracy**
- iPhone/iPad LiDAR effective range is about 5 m (16 ft). — [How-To Geek](https://www.howtogeek.com/695823/what-is-lidar-and-how-will-it-work-on-the-iphone/); [Forbes](https://www.forbes.com/sites/sabbirrangwala/2020/11/12/the-iphone-12lidar-at-your-fingertips/)
- iPhone 12 Pro: about ±1 cm absolute accuracy on objects over 10 cm, and about ±10 cm on a 130 × 15 × 10 m coastal cliff. — [Luetzenburg et al., Sci. Rep. 2021](https://www.nature.com/articles/s41598-021-01763-9)
- Free iPhone LiDAR apps (Modelar, 3D Scanner, SiteScape) against a Trimble X7 TLS, 2026. RMS was 1.3–2.0 cm on a statue, 8.1–10.3 cm in a corridor, and 3.7–8.5 cm on a 46.5 m façade. Glass reflections dominated façade error. SiteScape lost tracking in the corridor (a 180° wall inversion). Modelar had the lowest deviations, and point density did not predict accuracy. — [Hamdan et al., J. Geovis. Spatial Anal. 2026](https://link.springer.com/article/10.1007/s41651-026-00288-x)
- iPhone 12 Pro and 15 Pro gave nearly identical RMSE (2.06 vs 2.05 cm) on objects scanned at 0.01–3 m. — [Remote Sensing Letters 2026](https://doi.org/10.1080/2150704x.2026.2720055)
- iPad Pro 2021 indoors: linear readings were 1–2 cm off for 1–3 m lengths in static mode, and error grew with length in dynamic (walking) mode. Areas were within about 1 m². — [Tandfonline 2024](https://www.tandfonline.com/doi/full/10.1080/16874048.2024.2408839)
- A 2026 ISPRS study found image-based reconstruction (COLMAP or Pix4D) beat phone LiDAR on both visual and spatial metrics for buildings. — [McNally et al., ISPRS Annals 2026](https://doi.org/10.5194/isprs-annals-xi-m-1-2026-31-2026)

**App pricing, export and commercial terms**
- **Polycam:** Free exports glTF only. Basic adds OBJ, FBX, DAE, USDZ and STL. Point clouds (LAS, PLY, PTS, XYZ, DXF, georeferenced LAS) need Business ($400/yr). The ToS says you "may copy, modify, publish, distribute, sublicense, commercialize ... any Models you generate", with attribution required for any public display. Use of the Services is "for your internal use only". — [Polycam pricing](https://poly.cam/pricing); [Polycam export formats](https://learn.poly.cam/hc/en-us/articles/27756102599572-What-File-Types-Can-Polycam-Export); [Polycam ToS §5.1–5.2](https://poly.cam/legal/terms-of-service)
- **Scaniverse:** Scaniverse Classic is free with on-device processing, but Niantic says it is for use that "does not include commercial use/financial gain of any kind". The new Scaniverse has a Free plan with 20,000 credits a month (about 10 minutes of capture), metric scale, and FBX/SPZ/PLY export. Its commercial use is aimed at the Pro and Enterprise tiers (Plus $20/mo, Pro $50/mo). Whether the free tier of the new app allows commercial use was not stated. — [Niantic community answer 2026](https://community.nianticspatial.com/t/are-there-any-plans-for-this-to-be-available-in-a-license-for-students/5747); [Niantic Spatial pricing](https://www.nianticspatial.com/pricing)
- **3d Scanner App (Laan Labs):** free, with in-app purchases. The App Store listing advertises OBJ, glTF, GLB, DAE and STL plus point clouds (PTS, PCD, PLY, XYZ, LAS) and DXF floor plans. The vendor pricing page lists the free plan with "Full export support (OBJ, STL, PLY, GLTF, USDZ)" and "Scale-accurate measurements"; the paid tier is $69.99/yr. A 2023 protocols.io guide uses the free app with CloudCompare. — [App Store](https://apps.apple.com/us/app/3d-scanner-app/id1419913995); [3dscannerlidar.com pricing](https://www.3dscannerlidar.com/pricing/); [protocols.io](https://doi.org/10.17504/protocols.io.yxmvm21w9g3p/v3)
- **SiteScape (FARO):** free iOS app that exports PLY or E57. Free accounts "export unlimited scans" and sync one scan at a time to the cloud. The account guide is from around 2021 and was found on Scribd; current FARO terms were not checked. — [AEC Magazine 2021](https://aecmag.com/reality-capture-modelling/sitescape-lidar-scanning-on-the-iphone-ipad/); [SiteScape account guide (Scribd)](https://www.scribd.com/document/557640243/Copy-of-SiteScape-Documentation)
- **KIRI Engine Basic:** free. It has photo-scan photogrammetry (up to 150 photos, 2 GB per scan) and LiDAR scan, with unlimited exports and no watermark (OBJ, FBX, STL, GLB, glTF, USDZ, PLY, XYZ) on iOS, Android and Web. The weekly export cap was removed in v4.0 (August 2025). 3DGS is Pro-only. — [KIRI pricing](https://www.kiriengine.app/pricing); [KIRI Basic vs Pro 2026](https://www.kiriengine.app/blog/kiri-engine-basic-vs-pro); [Digital Production 2025](https://digitalproduction.com/2025/08/27/faster-wider-cleaner-kiri-engine-4-0-drops-mobile-scan-limits/)
- **Android:** a 2026 roundup says KIRI is the only Android app with documented free export. — [3DMag 2026](https://www.3dmag.com/3d-wikipedia/free-3d-scanner-app-android-free-export-limits/)

### Inferences
- With a 5 m range and 4–10 cm building-scale RMS, phone LiDAR from the ground cannot meet 1–2% on a whole roof. It is best used to check pitch and edge lengths on one or two planes from a ladder at the eave, or on the roof.
- A phone's ordinary camera can also feed the same free photogrammetry pipeline (COLMAP or ODM, using `--camera-lens` defaults) as a drone. A pole-mounted phone is an inference, not a tested workflow.
- Polycam Free plus glTF is technically usable in Three.js and Blender, and commercial use of the models is allowed with attribution. Note the "internal use only" wording on the Services themselves. Scaniverse Classic must not be used for paid work.

### Gaps
- No commercial-use clause was found in the 3d Scanner App ToS (the page was found but not fully read). Its website's "non-commercial" wording covers website materials, not scans.
- No study of phone LiDAR on pitched shingle roofs specifically was found.
- Android ARCore depth (non-LiDAR) accuracy for roofs: none found.

---

## 4. Single-image and few-image methods: pitch from one photo, pitch apps, monocular depth, SAM 2

### Takeaway
Pitch from one photo is practical for gable ends: shoot square-on and measure the rake angle with an on-screen protractor or a free camera pitch app. A phone laid on the roof deck gives inclinometer accuracy (assumed to be within ±1°; I found no accuracy figure). Monocular depth models (Depth Anything V2 Small is Apache-2.0; MoGe-2 is MIT) are useful for segmentation help and rough shape, not for 1–2% area. No source was found validating them for roof measurements. Metric3D's weights need an emailed commercial request, UniDepth is CC BY-NC, and Apple Depth Pro is research-only.

### Cited Findings
- **Pitch from photos and apps:**
  - Exact Protractor (on-screen protractor, reads rise:run from photos or Street View; the "Advanced" version adds a perspective protractor). — [Exact Protractor](https://exactprotractor.com/)
  - A browser tool that measures roof pitch from a photo. — [protractoronline.org](https://protractoronline.org/measure-roof-pitch-angle/)
  - Plumb Roof Pro (iOS): pitch from a square-on gable photo plus a pitch gauge; offline, "no subscription" (its price was not stated in the snippet). — [App Store](https://apps.apple.com/us/app/plumb-roof-pro-roofing-calc/id6789787351)
  - LibreCam: a camera sight-line mode that reads x/12 from the ground. — [LibreCam](https://librecam.com/product/roof-pitch-level)
  - Free inclinometer apps: FieldCalc Pitch Meter (free), Clinometer+ (free), Pitchline (free with IAP), Pitch Gauge for Roofers (free, Pro for PDFs). — [FieldCalc](https://builtbyfieldlab.com/apps/framing-carpentry/pitch-meter/); [Clinometer+](https://apps.apple.com/us/app/clinometer-slope-roof-pitch/id6760831012); [Pitchline](https://apps.apple.com/us/app/pitchline-roof-pitch-gauge/id6793016239); [Pitch Gauge for Roofers](https://apps.apple.com/us/app/pitch-gauge-for-roofers/id6809613182)
- **Monocular depth and segmentation licences:**
  - Depth Anything V2: Small (24.8M) is Apache-2.0. Base, Large and Giant are CC-BY-NC-4.0. — [DA-V2 README](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/README.md)
  - Metric3D: code is BSD-2. The author says "If you want to use it commercially, please email me", so commercial use of the weights is unclear. — [Metric3D LICENSE](https://github.com/YvanYin/Metric3D/blob/main/LICENSE); [issue #170](https://github.com/YvanYin/Metric3D/issues/170)
  - UniDepth: CC BY-NC 4.0, non-commercial. — [UniDepth LICENSE](https://github.com/lpiccinelli-eth/UniDepth/blob/main/LICENSE)
  - MoGe (Microsoft): code is MIT, and the Hugging Face weights are labelled MIT. A GitHub issue still asks for an explicit weights licence. — [MoGe LICENSE](https://raw.githubusercontent.com/microsoft/MoGe/main/LICENSE); [issue #98](https://github.com/microsoft/MoGe/issues/98)
  - Apple Depth Pro: Apple ML Research Model licence ("sole purpose of scientific research"), not for commercial use. — [HF DepthPro LICENSE](https://huggingface.co/apple/DepthPro/blob/main/LICENSE)
  - SAM 2: Apache-2.0. — [facebookresearch/sam2](https://github.com/facebookresearch/sam2/)
- Research exists on predicting roof slope or azimuth from a single aerial orthophoto (Mask R-CNN with an attribute head) and generating roof meshes from single aerial images. These are research-grade with no residential tape validation. — [arXiv 2605.26370](https://arxiv.org/html/2605.26370); [arXiv 2303.11215](https://arxiv.org/pdf/2303.11215)

### Inferences
- **Pitch from one photo:** a square-on gable photo with the camera level and a long lens (step back and zoom to reduce perspective) gives the rake angle. Error grows with yaw away from square-on: the measured angle is foreshortened by roughly cos(yaw) on the horizontal run. A few degrees of yaw is minor, but 20–30° of yaw can shift a reading by about one x/12 step. Hip roofs with no visible gable cannot be read this way. Use the drone model or an inclinometer on the deck.
- Monocular depth is relative, or metric only to about 5–10%, so it fails the 1–2% area target. A better use in the studio is as a prior or helper: SAM 2 masks per roof face on drone images, then planes fitted to the photogrammetric point cloud inside each mask. Only the Apache or MIT options (DA-V2 Small, MoGe, SAM 2) are safe for commercial use.

### Gaps
- No study was found reporting the accuracy of photo-based pitch apps or of phone inclinometers on shingles.
- No study was found applying Depth Anything, MoGe or Metric3D to residential roof measurement with ground truth.

---

## 5. Gaussian splats and NeRF for measurement; mesh extraction (2DGS, PGSR, SuGaR, GOF) and licences

### Takeaway
Splats inherit their geometry and scale from the SfM (COLMAP) poses and points they are trained on. Studies find the target positions barely move, but floaters and surface noise appear, so splats add nothing to measurement accuracy over the photogrammetric point cloud. For commercial work the only licence-clean option found is gsplat/nerfstudio (Apache-2.0, which includes a 2DGS trainer). The original 2DGS, PGSR, SuGaR and GOF are all non-commercial.

### Cited Findings
- ISPRS 2026, two buildings, checked against TLS and targets. Gaussian splatting "had minimal impact on the target points and overall structure". Gaussians drifted from the initial cloud, especially before 15k iterations, producing floaters and lower spatial accuracy. Cleaning the COLMAP point cloud reduced floaters. 2DGS removed some floaters but lost visual quality. Three loops around the building improved results, and image-based reconstruction beat phone LiDAR. — [McNally et al., ISPRS Annals 2026](https://doi.org/10.5194/isprs-annals-xi-m-1-2026-31-2026)
- 3DGS from UAV video (54 frames, 9 checkpoints) showed an ICP RMS of 0.0048 m against close-range photogrammetry. That is "structural consistency" with the photogrammetric reference, not absolute accuracy. — [IJIDF 2026](https://www.tandfonline.com/doi/full/10.1080/19479832.2026.2661679)
- An ISPRS 2026 heritage study compared native 3DGS, Postshot and MCMC with MVS on 80 m drone nadir imagery. Moderate 1/8 downsampling beat full resolution for 3DGS. — [ISPRS Archives 2026](https://isprs-archives.copernicus.org/articles/XLVIII-2-W12-2026/143/2026/isprs-archives-XLVIII-2-W12-2026-143-2026.pdf)
- COLMAP outputs have no scale unless they are georeferenced. — [McNally et al. 2026](https://doi.org/10.5194/isprs-annals-xi-m-1-2026-31-2026)
- **Licences:**
  - gsplat: Apache-2.0, CUDA. It ships `examples/simple_trainer_2dgs.py`. A maintainer said mesh extraction for 2DGS would come "shortly", and the current status was not confirmed. — [gsplat GitHub](https://github.com/nerfstudio-project/gsplat/); [simple_trainer_2dgs.py](https://github.com/nerfstudio-project/gsplat/blob/main/examples/simple_trainer_2dgs.py); [gsplat issue #452](https://github.com/nerfstudio-project/gsplat/issues/452)
  - nerfstudio: Apache-2.0. Splatfacto uses gsplat. — [nerfstudio LICENSE](https://github.com/nerfstudio-project/nerfstudio/blob/main/LICENSE); [Splatfacto docs](https://docs.nerf.studio/nerfology/methods/splat.html)
  - Original 2DGS (hbb1): "free for non-commercial, research and evaluation use" (ShanghaiTech). — [2DGS mesh_utils.py header](https://github.com/hbb1/2d-gaussian-splatting/blob/main/utils/mesh_utils.py)
  - PGSR (ZJU): educational, research and non-profit only; commercial use prohibited. — [PGSR LICENSE](https://github.com/zju3dv/PGSR/blob/c07d2de0b779471c70be88a1cf9bf7604679434d/LICENSE.md); [pgsr PyPI (LicenseRef-PGSR-NonCommercial)](https://pypi.org/project/pgsr/)
  - SuGaR: Inria/MPII Gaussian-Splatting licence (research only). — [SuGaR LICENSE](https://github.com/Anttwo/SuGaR/blob/main/LICENSE.md); [SuGaR issue #121](https://github.com/Anttwo/SuGaR/issues/121)
  - GOF (Gaussian Opacity Fields): Inria/MPII licence, non-commercial. — [GOF LICENSE](https://github.com/autonomousvision/gaussian-opacity-fields/blob/main/LICENSE.md)

### Inferences
- For takeoffs, measure on the SfM/MVS dense cloud or mesh and use splats only for the customer-facing visual in Three.js. The ODM/COLMAP point cloud is the measurement source; splats do not add accuracy. Splat training needs an NVIDIA CUDA GPU (gsplat), so it suits a GPU cloud box rather than a CPU-only container.
- If a splat-derived mesh is wanted commercially, gsplat's 2DGS trainer plus your own TSDF or marching-cubes extraction (e.g. Open3D, MIT) is the licence-clean route. Avoid the original 2DGS, PGSR, SuGaR and GOF repos.

### Gaps
- No study was found that measures roof plane pitch or area from splats or splat-derived meshes against tape.
- The current status of gsplat's built-in 2DGS mesh export (as of 2026) was not confirmed.

---

## 6. Fusing capture with the studio: getting a mesh or point cloud into Blender/Three.js, fitting planes, scaling, georeferencing

### Takeaway
ODM gives `odm_textured_model_geo.obj`, LAZ/PLY point clouds and GeoTIFF DSM and orthophoto. COLMAP and OpenMVS give PLY clouds and meshes. All of these import into Blender, either directly (OBJ/PLY) or after a LAZ→PLY conversion. The robust path to the studio's planar-triangle model is: segment each roof face, fit a RANSAC plane to its points, intersect adjacent planes to get ridges, hips and valleys, clip to the eave outline, then compute area, pitch and edge lengths as the studio already does.

### Cited Findings
- ODM output paths and formats: georeferenced point cloud in PLY, LAZ or CSV; textured mesh in OBJ, local and georeferenced; orthophoto and DSM as GeoTIFF, viewable in MeshLab and QGIS. — [ODM outputs](https://docs.opendronemap.org/outputs/); [DeepWiki ODM outputs](https://deepwiki.com/OpenDroneMap/ODM/6-outputs-and-data-formats)
- COLMAP `stereo_fusion` writes `fused.ply`. The `model_aligner` transform can be exported as a 4×4 matrix and reused to transform meshes. — [COLMAP FAQ](https://github.com/colmap/colmap/blob/master/doc/faq.rst); [PR #1177](https://github.com/colmap/colmap/pull/1177)
- WebODM's Potree viewer measures angles and heights directly on the point cloud. This is a quick pitch check before export. — [WebODM Potree docs](https://docs.webodm.org/tutorials/potree-3d-viewer/)
- A practitioner workflow: WebODM mesh → a separate viewer or CAD tool, scaled there from a taped on-site length. — [r/UAVmapping](https://www.reddit.com/r/UAVmapping/comments/kn4xn1/roofsnap_or_dronedeploy_the_better_roof_measuring/)

### Inferences
- **Suggested studio pipeline (inference):**
  1. Run ODM, with GCPs in local or UTM coordinates, or with EXIF only.
  2. Take `odm_georeferenced_model.laz` and convert it to PLY with PDAL or CloudCompare (both free; PDAL is BSD, CloudCompare GPL).
  3. Subtract a local origin. UTM coordinates in the millions lose float32 precision in Blender and Three.js; subtract the origin before import or use the non-geo `odm_textured_model.obj`.
  4. Import into Blender.
  5. Get per-face masks, either from SAM 2 on the orthophoto or nadir images, projected to the point cloud, or from region-growing on normals.
  6. Fit a RANSAC plane per face with Open3D `segment_plane` (MIT) or numpy.
  7. Snap the planes into the studio's triangle model.
  8. Rescale using the taped baseline as a similarity transform.
  9. Level using a known-horizontal feature (eave line or deck), or the gravity-aligned ENU frame that ODM gives when georeferenced.
  10. Report pitch = atan of the plane normal's horizontal/vertical ratio, converted to x/12.

  ENU-aligned ODM output already has Z up. COLMAP output without GPS has an arbitrary frame, and its `model_aligner --alignment_type plane` only roughly levels it.
- Three.js: load OBJ, glTF or PLY with OBJLoader, GLTFLoader or PLYLoader. Convert the ODM mesh to glTF (Blender export) for web delivery, and Draco- or meshopt-compress the cloud and mesh to stay under page size limits.
- QA check per job: compare the model's eave length or gutter run with tape (target within 0.5%), and compare opposite gable pitches (they should match on a symmetric roof). Large disagreement points to a scale or tilt error.

### Gaps
- No ready-made open-source Blender add-on was found that turns a photogrammetric roof point cloud into a roof-report takeoff. This would be custom work in the studio.
- No source was found comparing plane-fit pitch from ODM clouds with inclinometer readings on real roofs.
