# Open-source roof reconstruction and measurement software (lidar, DSM, footprints) for residential roofing takeoffs

Research date: 2026-11-16. GitHub metadata (stars, last push, latest release, license) was pulled on 2026-11-16 through the ungh.cc GitHub mirror API and the shields.io license badge, because direct GitHub API and github.com HTML access were blocked in this environment. READMEs and LICENSE files were read from raw.githubusercontent.com. Package versions come from registry.npmjs.org and pypi.org. "Verified" below means it was read from the cited page in this session. "Inference" means my reasoning, or background knowledge I could not re-check this session.

## (a, b) Building and LoD2/LoD2.2 roof reconstruction: which tools produce explicit roof planes with ridge and hip topology?

### Takeaway
**roofer** (3DBAG / 3DGI / TU Delft) is the best fit. It is actively maintained: v1.0.0 shipped 2026-04-20, with commits up to 2026-11-15. It takes LAS/LAZ plus a footprint polygon and outputs LoD2.2 piecewise-planar roofs (CityJSONSeq), with C++ and Python bindings and a Docker image. Its license is GPLv3, so run it as a separate internal program. City3D and PolyFit (GPLv3, research prototypes) also produce planar polygon models, but they are harder to build and PolyFit needs facade points. 3dfier only does LoD1 blocks. Building3D and RoofN3D are datasets and benchmarks, not tools. The newer deep-learning repos (Point2Building, Point2WSS, PolyGNN) are research code, several have no license, and none ships a turnkey takeoff pipeline. None of these tools exports labeled "ridge/hip/valley" edges directly. The topology is implicit in shared edges between adjacent planar faces, so the studio must classify edges itself (see Inferences).

### Cited Findings

**Comparison table (metadata verified 2026-11-16)**

| Tool | What it does | Input -> Output | Stars / last push / latest release | License | Lang / run |
|---|---|---|---|---|---|
| [3DBAG/roofer](https://github.com/3DBAG/roofer) | Automatic LoD1.2/1.3/2.2 reconstruction from point cloud + roofprint | LAS/LAZ + any OGR polygon source (GPKG, Shapefile, PostGIS) -> CityJSONSeq (.city.jsonl); Python `reconstruct()` returns polygon meshes | 223 / 2026-11-15 / v1.0.0 (2026-04-20) | GPL-3.0 | C++, Python bindings, CLI; binaries for Linux/macOS/Windows plus Docker `3dgi/roofer` |
| [geoflow3d/geoflow-bundle](https://github.com/geoflow3d/geoflow-bundle) (`lod22-reconstruct`) | Predecessor of roofer, flowchart based | footprint GPKG + LAS -> CityJSON, OBJ, GeoPackage, PostgreSQL | 100 / 2026-01-06 / 2024.03.08 | Mixed GPL-3 / AGPL-3 per file (the [gfp-building-reconstruction](https://github.com/geoflow3d/gfp-building-reconstruction) plugin is AGPL-3.0) | C++; Docker image and Windows installer |
| [tudelft3d/City3D](https://github.com/tudelft3d/City3D) | Hypothesis-and-selection LoD2 reconstruction from airborne lidar + footprint (built on PolyFit) | point cloud + footprint -> polygonal building models | 363 / 2025-09-03 / no releases | GPL-3.0 | C++ (CGAL, OpenCV, optional Qt GUI, SCIP bundled or Gurobi optional); build from source |
| [LiangliangNan/PolyFit](https://github.com/LiangliangNan/PolyFit) | Polygonal surface reconstruction from point cloud + pre-extracted planar segments | planar segments -> compact polygonal mesh | 837 / 2025-04-16 / v1.6.0 (2025-03-28) | GPL-3.0 | C++ with Python bindings; prebuilt binaries for Win/macOS/Linux |
| [tudelft3d/3dfier](https://github.com/tudelft3d/3dfier) | 2D polygons + lidar -> LoD1 blocks (flat roofs) | polygons + LAS -> OBJ, CityGML, CityJSON, CSV, PostGIS, STL | 642 / 2026-09-08 / v1.5.0 (2026-09-08) | GPL-3.0 | C++; Docker `tudelft3d/3dfier` |
| [tudelft3d/City4CFD](https://github.com/tudelft3d/City4CFD) | LoD1.2/LoD2 city models for wind (CFD) simulation | footprints + point cloud -> city model | 192 / 2026-08-04 / 0.8.2 (2026-11-15) | AGPL-3.0 | C++ |
| [3DBAG/3dbag-pipeline](https://github.com/3DBAG/3dbag-pipeline) | Production orchestration for 3DBAG | — | 13 / 2026-11-13 / 2025.09.03 | Apache-2.0 | Python (calls roofer) |
| [prs-eth/point2building](https://github.com/prs-eth/point2building) | Learning-based polygonal mesh from airborne lidar | point cloud -> mesh | 88 / 2024-07-24 / none | none specified | Python / DL |
| [KWIKERRR/point2wss](https://github.com/KWIKERRR/point2wss) | ISPRS 2026: masked autoencoding + weighted straight skeleton parametric roofs | lidar -> parametric roof | 9 / 2026-09-03 / none | none specified | Python / DL |
| [chenzhaiyu/polygnn](https://github.com/chenzhaiyu/polygnn) | Polyhedron-based GNN building reconstruction (ISPRS 2024) | point cloud -> polyhedral model | 161 / 2025-03-13 / none | MIT | Python / PyTorch |
| [chenzhaiyu/points2poly](https://github.com/chenzhaiyu/points2poly) | Compact building models via deep implicit fields (ISPRS 2022) | point cloud -> polygonal model | 238 / 2023-12-29 / none | MIT | Python |
| [chenzhaiyu/abspy](https://github.com/chenzhaiyu/abspy) | Adaptive binary space partitioning (a building block for plane-arrangement reconstruction) | planes -> cell complex | 101 / 2026-05-04 / v0.3.0 (2025-06-06) | MIT | Python |
| [GDAOSU/LOD2BuildingModel](https://github.com/GDAOSU/LOD2BuildingModel) (SAT2LoD2) | LoD2 from satellite DSM + orthophoto | DSM + ortho -> LoD2 | 232 / 2024-05-24 / none | not identifiable by GitHub | Python/C++ |
| [Imp3rv1ous/columbus-lidar-lod2](https://github.com/Imp3rv1ous/columbus-lidar-lod2) | Student pipeline: RandLA-Net segmentation + roof plane extraction (Columbus OH lidar) | lidar -> partial | 0 / 2026-11-06 / none | none specified | Python |

**roofer details**
- roofer "performs fully automatic LoD2 building reconstruction from a pointcloud and a building roofprint polygon"; it was developed to create 3DBAG, outputs LoD1.2/1.3/2.2, and is "usable either as a command line application or as a library with C++ and Python bindings". Before 2024 the code lived in Geoflow and the gfp-building-reconstruction plugin; it was refactored into roofer in summer 2024 — [roofer README](https://raw.githubusercontent.com/3DBAG/roofer/HEAD/README.md)
- Its license is "GPLv3" (LICENSE file is GNU GPL v3). The core developers founded 3DGI (a TU Delft spin-off) in 2022, and Kadaster funded development in 2024–2026 — [roofer README](https://raw.githubusercontent.com/3DBAG/roofer/HEAD/README.md)
- Algorithm: (1) roof planes detected by **region growing**; (2) roof lines from plane intersections plus alpha-shape edge fitting; (3) line clustering and regularisation; (4) 2D roof partition of the roofprint; (5) graph-cut optimisation assigning a plane label to each face (λ = "complexity factor"; adjacent faces with the same plane are merged); (6) extrusion. Assumptions: roofs are piecewise planar; models are 2.5D with vertical walls, so "**roof overhangs and balconies cannot be modelled**"; point cloud and footprint must be well aligned — [roofer docs: Reconstruction algorithm](https://innovation.3dbag.nl/roofer/reconstruct_params.html)
- Input requirements: aerial (preferably lidar) point cloud; outliers removed; classified with at least ground (2) and building (6); "We achieve good results with ~10 pts/m2 in the 3D BAG"; homogeneous density with no large gaps; some ground points around the building; LAS/LAZ for the CLI; footprint (preferably a roofprint) in any OGR format; all data in one projected SRS in metres — [roofer docs: Input data requirements](https://innovation.3dbag.nl/roofer/data_requirements.html)
- CLI: `roofer [options] <pointcloud-path>... <polygon-source> <output-directory>`; it tiles internally (no pre-tiling), is multi-threaded (`-j`), filters footprints by attribute (`--filter`), and writes per-building quality attributes (`-a` lists them) — [roofer docs: CLI](https://innovation.3dbag.nl/roofer/cli_application.html)
- Python API: `roofer.reconstruct(points_roof, points_ground, footprint, cfg)` returns `list[Mesh]` (each Mesh is a sequence of polygons); `roofer.triangulate_mesh()` returns (vertices, faces). Tunables in `ReconstructionConfig` include `complexity_factor`, `plane_detect_epsilon`, `plane_detect_k`, `plane_detect_min_points`, `plane_detect_normal_angle`, `line_detect_epsilon`, `thres_alpha`, `thres_reg_line_dist`, `thres_reg_line_ext`, `lod`, `clip_ground`. Because roofer uses floats internally, the docs advise translating data to the origin first — [roofer docs: Python API](https://innovation.3dbag.nl/roofer/api_py.html)
- Install: GitHub release binaries, Docker image `3dgi/roofer`, or build from source. The getting-started page mentions no pip package. Output is CityJSONSeq, convertible with `cjseq` — [roofer docs: Getting started](https://innovation.3dbag.nl/roofer/getting_started.html)
- **Name collision:** the PyPI package `roofer` (0.0.2) is an unrelated image-tile tool by another author (homepage github.com/franckinux/roofer), so do not `pip install roofer` — [PyPI roofer](https://pypi.org/pypi/roofer/json)
- roofer's docs on related tools: "Polyfit performs true 3D building reconstruction ... a more complete building point cloud is required, that also includes all the facades. Typical airborne lidar point clouds are therefor not suitable"; "City3D is more similar to roofer ... 2.5D building reconstruction from a point cloud and a roofprint polygon" — [roofer docs: Related software](https://innovation.3dbag.nl/roofer/related_software.html)

**3DBAG output attributes (useful as a QA template)**
- 3DBAG publishes `b3_rmse_lod22` (RMSE in metres of 3D distances between point cloud and LoD2.2 model), `b3_val3dity_lod22`, `b3_kwaliteitsindicator` (a reliability boolean), `b3_dak_type` (slanted / horizontal / multiple horizontal / no planes ...), and per roof part `b3_hellingshoek` (slope in degrees) and `b3_azimut` (azimuth in degrees), plus point density per AHN epoch (`b3_puntdichtheid_ahn3/4/5`) — [3DBAG attribute schema](https://docs.3dbag.nl/en/schema/attributes/)
- 3DBAG "needs high-quality classified Lidar data at a density of at least 8pts/m2" — [GIM International, 3DBAG article](https://www.gim-international.com/content/article/3dbag-automatically-generated-3d-models-of-10-million-buildings) (via search snippet)
- Course slides describe the AHN input as ~23 cm positional accuracy (height and planimetric) with 8–15 pts/m² on buildings; known limitations include glass roofs and greenhouses — [TU Delft GEO1004 lod2recon slides](https://3d.bk.tudelft.nl/courses/geo1004/data/lod2recon.pdf) (via search snippet)

**City3D / PolyFit**
- City3D implements Huang, Stoter, Peters & Nan, "City3D: Large-scale Building Reconstruction from Airborne LiDAR Point Clouds", Remote Sensing 14(9) 2254, 2022. It is "a research prototype" but has been used for city-scale models; Geodan wrote an article on its "possibilities and limitations". Dependencies: CGAL ≥5.4, OpenCV ≥4, Qt for the GUI only; CLI examples build without Qt; the SCIP solver source is bundled, with Gurobi optional (commercial) — [City3D README](https://raw.githubusercontent.com/tudelft3d/City3D/HEAD/ReadMe.md); [Geodan article](https://research.geodan.nl/the-possibilities-and-limitations-of-city3d-as-large-scale-3d-building-reconstruction-model/)
- A Glasgow LoD1/LoD2 dataset (Zenodo, March 2025) built its LoD2 models with City3D from footprints plus building point clouds — [Zenodo record](https://zenodo.org/records/13935339/latest) (via search snippet)
- PolyFit expects planar segments as input ("you're expected to provide the planar segments as input"; Easy3D's Mapple is suggested for extracting them). It ships prebuilt binaries and Python bindings and has been in CGAL as "Polygonal Surface Reconstruction" since 2019 — [PolyFit README](https://raw.githubusercontent.com/LiangliangNan/PolyFit/HEAD/ReadMe.md)

**Datasets and benchmarks (not tools)**
- Building3D (ICCV 2023, Univ. of Calgary): 16 Estonian cities, 875.39M aerial lidar points, 161.91k buildings; the Tallinn subset has 36k roof point clouds with wireframes; the metric is Average Corner Offset (ACO). It is distributed via building3d.ucalgary.ca and I found no official GitHub tool — [arXiv 2307.11914](https://arxiv.org/pdf/2307.11914); [Building3D site](https://building3d.ucalgary.ca/reconstruction.php)
- RoofN3D (TU Berlin, 2018): training data derived from New York City data, "for free usage" with a citation requirement. The authors say it is "not a benchmark dataset at the moment", and I found no named license — [ISPRS Archives XLII-2 1191](https://isprs-archives.copernicus.org/articles/XLII-2/1191/2018/isprs-archives-XLII-2-1191-2018.pdf); [RoofN3D site](https://roofn3d.gis.tu-berlin.de/)
- A 2026 ISPRS Annals paper on lidar-guided LoD2 roof reconstruction reports roof-surface RMSE of 0.445 m after plane fitting (a different method from roofer) — [ISPRS Annals XI-2-2026-127](https://isprs-annals.copernicus.org/articles/XI-2-2026/127/2026/isprs-annals-XI-2-2026-127-2026.pdf) (via search snippet)

### Inferences
- **Ridge/hip/valley topology:** roofer, City3D and PolyFit output planar polygon faces with shared vertices. Ridge, hip and valley lines can be derived by finding edges shared by two roof faces and classifying them: an edge is a ridge if both faces slope away from it (horizontal edge, normals diverging upward), a hip if it is non-horizontal and convex, and a valley if it is concave. Eaves and rakes are boundary edges (horizontal vs sloped) where a roof face meets a wall. This is a small Python post-process feeding RoofPlane objects. None of the tools emits these labels directly (I found no documentation saying so).
- **USGS QL2 (≥2 pts/m²) is about 4–5x sparser than roofer's tested ~10 pts/m².** Expect simple gable and hip roofs to reconstruct but small planes (dormers, crickets, small hips) to be merged or lost. Lower `plane_detect_min_points` and raise `plane_detect_k` and epsilon carefully. QL1/QL0 (≥8 pts/m²) is in roofer's comfort zone.
- roofer's 2.5D vertical-wall model clips the roof at the footprint (roofprint) edge. Microsoft footprints are derived from imagery and roughly follow roof outlines (including overhang), which suits roofer. Eave overhang depth, however, is not measured from the walls.
- **Recommended architecture:** a container that runs PDAL (fetch/clip/classify 3DEP) -> roofer CLI or Python (GPL, kept as its own process) -> CityJSONSeq -> a small MIT/own Python converter -> RoofPlane JSON -> Three.js/Blender. Communicating via files or the CLI keeps the GPL boundary clean for internal use.

### Gaps
- No published RMSE or pitch-accuracy figure for roofer/3DBAG LoD2.2 at any density was found. The 2021 ISPRS 3DBAG quality paper's numbers were not retrieved.
- City3D paper accuracy numbers (MDPI page returned 403) were not retrieved.
- I did not verify whether roofer GitHub releases include Python wheels, or whether the Python bindings must be built from source.
- I did not determine which SCIP version City3D/PolyFit bundle. SCIP was under the non-commercial ZIB Academic License before v8.0.3 (Apache-2.0 since then); this is background knowledge, and the bundled version must be checked before commercial use.
- No benchmark comparing roofer vs City3D vs DL methods on US QL2 residential data was found.

## (a) Plane segmentation and fitting libraries: capabilities, licenses, and behavior at 2–8 pts/m²

### Takeaway
For DIY roof-plane fitting, **Open3D** (MIT: RANSAC `segment_plane`, `detect_planar_patches`, DBSCAN) and **pyRANSAC-3D** (Apache-2.0) are commercially clean and pip-installable. **CGAL Shape Detection** (efficient RANSAC and region growing) is GPL. **CloudCompare** (and its RANSAC/Facets plugins) is GPL and best used as a manual QA desktop tool. **lidR** is GPL-3 (R). PDAL has no real plane-segmentation filter; its `filters.planefit` is a per-point outlier criterion.

### Cited Findings
- **Open3D** v0.20.0 (2026-09-16), 14.2k stars, last push 2026-11-14, MIT license (LICENSE file), `pip install open3d` — [GitHub isl-org/Open3D](https://github.com/isl-org/Open3D); [LICENSE](https://raw.githubusercontent.com/isl-org/Open3D/HEAD/LICENSE); [PyPI open3d](https://pypi.org/pypi/open3d/json)
- Open3D `PointCloud` exposes `segment_plane()`, `detect_planar_patches()`, `cluster_dbscan()` and `estimate_normals()` — [Open3D PointCloud API](https://www.open3d.org/docs/release/python_api/open3d.geometry.PointCloud.html)
- **pyRANSAC-3D** v0.7.0 (2026-08-18), 677 stars, Apache-2.0; "Python library for fitting 3D primitive shapes to point clouds with RANSAC. Detect planes, spheres, cylinders..." — [GitHub leomariga/pyRANSAC-3D](https://github.com/leomariga/pyRANSAC-3D); [PyPI pyransac3d](https://pypi.org/pypi/pyransac3d/json)
- **CGAL** v6.2.1 (2026-09-04), 6.1k stars. The package overview lists **Shape Detection, Shape Regularization, 2D Straight Skeleton and Polygon Offsetting, Polygonal Surface Reconstruction, Kinetic Space Partition, Kinetic Surface Reconstruction, Point Set Processing, 2D Alpha Shapes, 2D Arrangements, Polygon Mesh Processing: all "License: GPL"** — [CGAL package overview](https://doc.cgal.org/latest/Manual/packages.html)
- CGAL: the Kernel and Support libraries are generally LGPL, while most geometric algorithms are GPL. Distributing software "based on GPLed CGAL data structures" obliges releasing your source under GPL. A commercial license is available from GeometryFactory — [CGAL license page](https://www.cgal.org/license.html)
- **CloudCompare** v2.13.2 (2024-07-11; repo active 2026-11-15), 4.9k stars, GPL (license header says GNU GPL) — [GitHub CloudCompare](https://github.com/CloudCompare/CloudCompare); [license.txt](https://raw.githubusercontent.com/CloudCompare/CloudCompare/HEAD/license.txt)
- **CloudComPy** (Python wrapper for CloudCompare), 353 stars, pushed 2026-10-29. It ships Conda/venv binaries; pip wheels are downloadable from the CloudComPy website, and the Linux wheels need GLIBC ≥2.39 (Ubuntu 24.04) — [CloudComPy README](https://raw.githubusercontent.com/CloudCompare/CloudComPy/HEAD/README.md)
- **lidR** (R) 714 stars, pushed 2026-09-21, last GitHub release tag v4.0.3 (2023; CRAN releases continue), GPL-3.0, described as "Airborne LiDAR data manipulation and visualisation for forestry application". Its successor-style **lasR** (93 stars, pushed 2026-11-15) is also GPL-3.0 — [GitHub r-lidar/lidR](https://github.com/r-lidar/lidR); [GitHub r-lidar/lasR](https://github.com/r-lidar/lasR)
- **Easy3D** (Mapple, the plane extractor recommended by PolyFit) v2.6.1, 1.7k stars, GPL-3.0 — [GitHub LiangliangNan/Easy3D](https://github.com/LiangliangNan/Easy3D)
- **Density effects (literature):** roof plane extraction reached about 80% correctness and completeness at point density "as low as four points/m²", with performance deteriorating as density decreases — [Awrangjeb & Fraser, Remote Sensing 6(5) 3716](https://doi.org/10.3390/rs6053716) (attributed from a search summary; the exact paper attribution among the returned results is uncertain)
- Planimetric accuracy of extracted roof planes stayed within about 1–2x the horizontal point spacing; a ~1 pt/m² dataset showed the most errors, with small planes (<10 m²) missed or merged — [search summary covering MDPI Remote Sensing 12(9) 1363 and related papers](https://www.mdpi.com/2072-4292/12/9/1363) (not read in full; treat as indicative)
- The minimum number of lidar points for a valid plane "is related to the density of the lidar points and the size of considered roof planes" — [Yan, Shan et al., ISPRS J., global optimization roof segmentation](https://engineering.purdue.edu/~jshan/publications/2014/ISPRS%20Journal%20global%20optimization%20Yan.pdf) (via search snippet)
- A 2025 learning-based roof-plane segmenter, RoofSeg (edge-aware transformer), exists as an arXiv paper — [arXiv 2508.19003](https://arxiv.org/pdf/2508.19003) (license and code not checked)

### Inferences
- At QL2 (≥2 pts/m², ≤0.71 m spacing), a 20 m² residential facet holds about 40 points, enough for a stable least-squares plane fit. A 3 m² dormer cheek holds about 6, which is unreliable. A practical pipeline: estimate normals (k ≈ 10–16), region-grow or iteratively RANSAC with a 0.10–0.15 m distance threshold (matching QL2 RMSEz ≤10 cm), merge coplanar segments, then refit each plane by least squares/PCA on its inliers. Pitch from a PCA normal over 40+ points should be considerably better than a raster-slope estimate (inference, not benchmarked).
- I did not verify these this session but believe them from background knowledge: lidR has `segment_shapes()` with plane detectors (`shp_plane`, `shp_hplane`); CloudCompare's qRANSAC_SD plugin implements Schnabel et al. efficient RANSAC and its qFacets plugin extracts planar facets with dip/dip-direction. All are GPL and useful for manual QA.
- Open3D has no built-in normal-based region growing for unorganized clouds. `detect_planar_patches` (a robust-statistics planar patch detector) is the closest equivalent, and its multi-plane output can be refined with RANSAC.

### Gaps
- I found no study benchmarking Open3D/pyRANSAC/CGAL specifically at 2 vs 8 pts/m² on residential roofs.
- The CloudCompare plugins' exact licenses were not checked file by file (the qRANSAC_SD README path returned 404).

## (c) Point-cloud processing pipelines (fetch, classify, normalize, convert)

### Takeaway
**PDAL** (BSD) plus **python-pdal** (BSD) is the backbone: it reads USGS 3DEP Entwine (EPT) directly from AWS by bounds, does SMRF ground classification, height above ground (HAG) and covariance/planarity features, and writes LAS/LAZ/COPC for roofer. laspy (BSD-2) and copclib (BSD) are lightweight Python readers. Untwine and PDAL wrench are GPL-3 (use them as CLIs only).

### Cited Findings
- **PDAL** 2.10.2 (2026-06-12), 1.4k stars, pushed 2026-11-11, BSD license; **python-pdal** 3.5.5 (2026-07-31) BSD — [GitHub PDAL](https://github.com/PDAL/PDAL); [PDAL LICENSE](https://raw.githubusercontent.com/PDAL/PDAL/HEAD/LICENSE.txt); [PyPI pdal](https://pypi.org/pypi/pdal/json)
- The PDAL SMRF docs show a pipeline that reads USGS 3DEP straight from `https://s3-us-west-2.amazonaws.com/usgs-lidar-public/IA_FullState/ept.json` with `readers.ept` and `bounds`, runs `filters.smrf`, and keeps `Classification == 2` — [PDAL filters.smrf](https://pdal.io/en/latest/stages/filters.smrf.html)
- `filters.hag_nn` computes HeightAboveGround from the nearest ground points (ground from SMRF/PMF) — [PDAL filters.hag_nn](https://pdal.io/en/latest/stages/filters.hag_nn.html)
- `filters.covariancefeatures` computes Linearity, **Planarity**, Scattering, Verticality, SurfaceVariation and more; `filters.approximatecoplanar` flags eigenvalue-based coplanar neighbourhoods — [PDAL covariancefeatures](https://pdal.io/en/latest/stages/filters.covariancefeatures.html); [PDAL approximatecoplanar](https://pdal.io/en/latest/stages/filters.approximatecoplanar.html)
- `filters.planefit` computes a per-point "Plane Fit criterion" suited to **outlier detection**, and "produces poor results around small features and creases". It is not plane segmentation — [PDAL filters.planefit](https://pdal.io/en/latest/stages/filters.planefit.html)
- laspy 2.7.0 BSD-2; copclib 2.6.3 BSD; pyvista 0.49.2 MIT — [PyPI laspy](https://pypi.org/pypi/laspy/json); [PyPI copclib](https://pypi.org/pypi/copclib/json); [PyPI pyvista](https://pypi.org/pypi/pyvista/json)
- **Untwine** (COPC/EPT builder) 1.5.1, GPL-3.0; **PDAL wrench** v1.5.1 (2026-07-01), GPL-3.0; **PotreeConverter** 2.1.5 (2026-09-23), BSD-2-Clause — [hobuinc/untwine](https://github.com/hobuinc/untwine); [PDAL/wrench](https://github.com/PDAL/wrench); [potree/PotreeConverter](https://github.com/potree/PotreeConverter)
- 3DEP quality levels (Lidar Base Spec 2020 rev A): **QL0** ≤5 cm RMSEz, ≥8 pls/m², ≤0.35 m spacing; **QL1** ≤10 cm RMSEz, ≥8 pls/m²; **QL2** ≤10 cm RMSEz, ≥2 pls/m², ≤0.71 m spacing; QL3 ≤20 cm, ≥0.5 pls/m² — [USGS Lidar Base Specification 2020 rev A](https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/atoms/files/Lidar-Base-Specification-2020-rev-A.pdf); [USGS QL page](https://www.usgs.gov/3d-elevation-program/topographic-data-quality-levels-qls); [MnGeo FAQ table](https://mngeo.mn.gov/committee/3dgeo/acquisition/faq.html)

### Inferences
- Many 3DEP tiles are already classified (class 6 building). Where class 6 is missing, the SMRF + HAG > 2 m + inside-footprint + planarity filter gives a usable "roof points" set for roofer or custom fitting.
- A Linux container needs only `conda install -c conda-forge pdal python-pdal` plus `pip install open3d laspy`, and the roofer Docker image or binary is a separate service. All are cloud friendly. CloudComPy and City3D are the hardest to containerize (GLIBC/Qt/CGAL build chains).
- Note that 3DEP RMSEz specs are vertical non-vegetated terrain accuracy. Roof-surface noise and horizontal error (often larger) are not covered by the QL numbers.

### Gaps
- I did not confirm whether a public 3DEP COPC mirror (for example on Microsoft Planetary Computer) is currently available. The EPT on AWS is confirmed via the PDAL docs example only.

## Footprint-driven roofs: straight-skeleton libraries and footprint + lidar pitch fitting

### Takeaway
For hip roofs from footprints, the npm **straight-skeleton 1.x** line is pure TypeScript and MIT. **2.x/3.x** (current 3.0.0) wraps **CGAL's GPL Straight_skeleton_2 compiled to Wasm**, even though the npm metadata says MIT. That is a license red flag, so pin 1.x or treat 3.x as GPL. In Python, **bpypolyskel** (GPL-3, Blender-ready, tested on 320k OSM hipped roofs) or the original **polyskel** (LGPL-3, inactive since 2020) are the options. A straight skeleton gives topology (ridges and hips) with equal pitch on all eaves. Lidar is then used to estimate the actual pitch and to validate or override the skeleton.

### Cited Findings
- straight-skeleton (StrandedKitty) README: "a TypeScript library that wraps the basic functionality of **CGAL's straight skeleton implementation using Wasm**"; it accepts point arrays or GeoJSON polygons (with holes); a "less robust but more fast" pure-TypeScript implementation lives in v1 — [straight-skeleton README](https://raw.githubusercontent.com/StrandedKitty/straight-skeleton/HEAD/README.md)
- npm version history: 1.0.0 (2021-12-05), 1.1.0 (2023-03-09), 2.0.0 (2023-09-03), 2.0.2 and 3.0.0 (2026-03-24), all tagged "MIT" in npm metadata. The GitHub repo has 90 stars and an MIT LICENSE — [npm registry straight-skeleton](https://registry.npmjs.org/straight-skeleton); [GitHub](https://github.com/StrandedKitty/straight-skeleton)
- CGAL "2D Straight Skeleton and Polygon Offsetting": License GPL — [CGAL package overview](https://doc.cgal.org/latest/Manual/packages.html)
- **bpypolyskel** v1.1.3 (2025-02-02), pushed 2026-03-13, GPL-3.0. `polygonize()` computes the faces of a hipped roof from a footprint with vertex heights; it was "tested against all 320.000 hipped roofs in the OpenStreetMap database. It runs successfully for 99.99%". Its skeleton "does not provide a straight skeleton in a mathematical sense" because of cleaning/merging tuned for roofs — [bpypolyskel README](https://raw.githubusercontent.com/prochitecture/bpypolyskel/HEAD/README.md)
- **Botffy/polyskel** (Python straight skeleton) LGPL-3.0, 88 stars, last push 2020-10-12 (effectively abandoned) — [GitHub Botffy/polyskel](https://github.com/Botffy/polyskel)
- **scikit-geometry** (CGAL Python wrapper, includes the skeleton) LGPL-3.0 repo license, last push 2024-01-31, not on PyPI under that name — [GitHub scikit-geometry](https://github.com/scikit-geometry/scikit-geometry). Note it wraps GPL CGAL packages (inference from the CGAL package licenses above).
- **Point2WSS** (ISPRS 2026) combines learned features with a *weighted* straight skeleton for parametric LoD2 roofs from lidar, so per-edge weights equal per-eave pitch — [GitHub KWIKERRR/point2wss](https://github.com/KWIKERRR/point2wss); [ResearchGate](https://www.researchgate.net/publication/408463903_Point2WSS_Reconstructing_LoD2_Buildings_from_Aerial_LiDAR_Data_using_Multimodal_Learning_and_Weighted_Straight_Skeleton). No license is specified.
- A Salamanca study reports roof-slope *area* RMSE of ±5.25% at 0.5 pts/m² and 2.63% at 2 pts/m² using a roof-symmetry assumption — [Multi-scale roof characterization from LiDAR data (USAL repository)](https://gredos.usal.es/bitstream/handle/10366/149568/Art2_Multi-scale.pdf?sequence=3&isAllowed=y) (via search snippet; the PDF returned 403, so not verified directly)

### Inferences
- **Footprint + lidar workflow:** (1) Microsoft footprint -> straight skeleton gives facets and ridge/hip lines. (2) Assign lidar roof points to each skeleton facet (point-in-polygon in 2D). (3) Fit a plane per facet with a robust least-squares fit, then take the pitch from the normal. (4) Compare the fitted pitches: if they are consistent, use one common pitch (a symmetric hip roof). If they differ, rebuild with a weighted skeleton (per-edge pitch), or switch to roofer's data-driven output (gable ends, cross-gables, dormers). (5) Flag a mismatch (high plane-fit RMSE or many off-plane points) for manual review. This hybrid is robust at QL2 because the footprint supplies the horizontal geometry, which sparse lidar captures poorly, and lidar supplies only pitch and ridge height, where 40+ points per facet is plenty.
- The skeleton assumes every eave edge is at the same height with the same pitch. Gable roofs need eave/gable edge labeling (weight 0 or vertical on gable edges). Weighted-skeleton support in CGAL 6.x is GPL as well.
- Elevation of the eave line: take the 2D footprint edge, and estimate eave height from the lowest roof points near the edge or from plane intersection with the footprint boundary.

### Gaps
- I found no MIT/BSD weighted-straight-skeleton library for JS or Python.
- I found no published accuracy for skeleton-plus-lidar pitch estimation on residential roofs.

## Measurement accuracy: lidar-derived pitch, area and edge lengths vs ground truth (QL2 vs QL1 vs drone)

### Takeaway
The peer-reviewed evidence for *residential pitch accuracy from public lidar* is thin and mostly comes from solar-potential studies using raster/GIS slope methods. They report roof tilt RMSE around 6.8–7° vs reference data, and roof-plane area RMSE of about 2.6% at 2 pts/m² under a symmetry assumption. Vendor claims (EagleView about 98.5–98.8%, a lidar startup claiming 3–5%) are marketing, not independent studies. I found no independent study comparing QL2 vs QL1 vs drone photogrammetry pitch against tape or inclinometer measurements.

### Cited Findings
- A Cartagena, Colombia lidar + GIS rooftop solar study (2026): best configuration slope RMSE ≈ 6.79° and aspect RMSE ≈ 20.95° against 482 reference polygons — [Processes 14(10) 1592, doi:10.3390/pr14101592](https://doi.org/10.3390/pr14101592) (via search snippet)
- A GIS-based PV suitability study (Energies 2018) validated against installer records: tilt RMSE 7°, mean bias 4°, and 87% of estimated tilts within 10° of the reference — [Energies 11(12) 3506](https://www.mdpi.com/1996-1073/11/12/3506) (via search snippet)
- A UK PV roof study using GIS slope found slope could be "up to 6 degrees lower than reality" with one method; a large building gave a mean pitch of 26° vs an architect plan value of 26.5°; the method tended to under-estimate slope — [ResearchGate: Assessment of Potential for PV Roof Installations by Extraction of Roof Slope from Lidar](https://www.researchgate.net/publication/289367889_Assessment_of_Potential_for_Photovoltaic_Roof_Installations_by_Extraction_of_Roof_Slope_from_Lidar_Data_and_Aggregation_to_Census_Geography) (via search snippet)
- Roof-plane area RMSE ±5.25% at 0.5 pts/m² and 2.63% at 2 pts/m² (symmetry assumption) — [USAL multi-scale roof characterization](https://gredos.usal.es/bitstream/handle/10366/149568/Art2_Multi-scale.pdf?sequence=3&isAllowed=y) (via search snippet)
- Jochem et al. 2009 (Sensors 9(7)) roof plane detection at about 17 pts/m²: completeness 94.4%, correctness 88.4% (947 of 1,003 reference planes matched). The authors state positional accuracy "could not be assessed adequately" for lack of terrestrial reference data, and slope/aspect error was not quantified — [PMC3274168](https://pmc.ncbi.nlm.nih.gov/articles/PMC3274168/)
- Terrain (not roof) lidar slope errors: mean absolute slope error about 1.7°–4.8°, increasing with slope — [USC Scholar Commons lidar slope study](https://scholarcommons.sc.edu/cgi/viewcontent.cgi?article=1264&context=geog_facpub) (via search snippet; terrain DEM slope, not plane fits)
- EagleView claims 98.77% (roof lines) and 98.49% (slope) vs "independent benchmark measurements". The Roofing Brief notes that the June 2025 CompassData study was EagleView-commissioned, reported roof area at 98.43% vs UAV + terrestrial lidar ground truth (Denver), did not disclose the number of roofs, and the full whitepaper is unreleased — [EagleView blog](https://www.eagleview.com/blog/eagleview-roof-measurements-confirmed/); [The Roofing Brief 2026 report](https://theroofingbrief.com/2026-aerial-roof-measurement-software-report/)
- StormConnect (a commercial lidar roof tool) claims 96% agreement with EagleView and 3–5% on total area and pitch, with heavily dormered homes needing a ground check (marketing claim) — [StormConnect](https://stormconnect.io/features/roof-measurement)
- 3DBAG/roofer is built on AHN data of ~23 cm positional accuracy at 8–15 pts/m², and the roof surface quality "primarily depend[s] on the AHN data (point density and positional accuracy)" — [TU Delft lod2recon slides](https://3d.bk.tudelft.nl/courses/geo1004/data/lod2recon.pdf); [3DBAG GEO1004 slides](https://3d.bk.tudelft.nl/courses/backup/geo1004/2022/data/GEO1004_3DBAG.pdf) (via search snippets)

### Inferences
- The 6.8–7° RMSE figures come from raster-slope GIS methods and small or mixed roofs. Plane fitting with many points per facet should do better. Back-of-envelope: with 40 points spread over a 4 m slope run and 10 cm vertical noise, the slope standard error is roughly 0.1/(4·√(40/12)) ≈ 0.014 rad ≈ 0.8° (a statistical estimate, not a measured result). The dominant errors are more likely to be systematic: misassigned points near ridges and eaves, footprint misalignment, and dormers. For roofing, a 6/12 pitch is 26.6° and the 7/12–6/12 difference is about 3.7°, so ~1° accuracy is enough to round to the nearest x/12 pitch on large facets but not reliably on small ones.
- Area: plan (horizontal) area mainly comes from the footprint. Sloped area = plan area / cos(pitch), so a 1° pitch error at 26.6° changes area by about 0.9%. Footprint error (overhang inclusion, Microsoft footprint generalisation of about ±0.5 m on a 12 m edge, ~4% per dimension) likely dominates area error more than lidar density does (inference).
- Edge lengths: ridge and hip lengths derived from plane intersections bounded by the footprint inherit footprint accuracy. Rakes and eaves depend on how the overhang is handled. QL2's 0.71 m spacing makes roof-edge (eave) location uncertain by about ±0.35–0.7 m if it is taken from lidar alone.
- QL1/QL0 (≥8 pts/m²) roughly quadruples points per facet (halving the statistical slope error) and makes dormers resolvable. Drone photogrammetry (typically cm-level GSD) resolves all features and eaves directly. I have no sourced numbers here.

### Gaps
- I found no independent peer-reviewed study of lidar plane-fit roof pitch vs inclinometer/tape on residential roofs, and no QL2 vs QL1 vs drone comparison for roofing takeoffs. This should be measured in-house on a handful of known roofs.
- No independent accuracy validation of EagleView/Hover-type reports was found; only vendor-commissioned figures.

## Browser and JS options: showing LAZ/COPC/EPT under the Three.js roof

### Takeaway
Use **copc.js** (MIT, npm `copc` 0.0.9, Aug 2026) with **laz-perf** (Apache-2.0, Wasm) to stream a clipped COPC around the address into a Three.js `Points` object, or use **loaders.gl** (MIT; `@loaders.gl/las` 4.5.4 stable, `@loaders.gl/copc` 5.0 alpha). **Potree** (BSD-2) is a full viewer, but its last release (1.8.2) dates from Dec 2023. Its converter (PotreeConverter, BSD-2) is active.

### Cited Findings
- copc.js: "A TypeScript library for reading and parsing COPC data", `npm install copc`; `Copc.create(filename or getter)`, `Copc.loadHierarchyPage`, `Copc.loadPointDataView` with per-dimension getters (X, Y, Z, Classification, RGB...) — [copc.js README](https://raw.githubusercontent.com/connormanning/copc.js/HEAD/readme.md)
- copc.js v0.0.9 (2026-08-10), 65 stars, MIT; npm `copc` 0.0.9 MIT — [GitHub connormanning/copc.js](https://github.com/connormanning/copc.js); [npm copc](https://registry.npmjs.org/copc)
- laz-perf: "Alternative LAZ implementation for C++ and JavaScript", 106 stars, pushed 2026-10-18, Apache-2.0; npm `laz-perf` 0.0.7 (2025-02-19) — [GitHub hobuinc/laz-perf](https://github.com/hobuinc/laz-perf); [npm laz-perf](https://registry.npmjs.org/laz-perf)
- loaders.gl v4.5.4 (2026-10-10), 860 stars, MIT; `@loaders.gl/las` 4.5.4 (MIT); `@loaders.gl/copc` latest is 5.0.0-alpha.12 (2026-10-14) — [GitHub visgl/loaders.gl](https://github.com/visgl/loaders.gl); [LICENSE](https://raw.githubusercontent.com/visgl/loaders.gl/HEAD/LICENSE); [npm @loaders.gl/copc](https://registry.npmjs.org/@loaders.gl/copc)
- Potree: "WebGL point cloud viewer for large datasets", 5.7k stars, last push 2026-01-08, latest release 1.8.2 (2023-12-12), BSD 2-clause (Copyright 2011-2020 Markus Schütz) — [GitHub potree/potree](https://github.com/potree/potree); [Potree LICENSE](https://raw.githubusercontent.com/potree/potree/HEAD/LICENSE)
- 3d-tiles-renderer (NASA-AMMOS, Three.js) 0.5.4, Apache-2.0 — [npm 3d-tiles-renderer](https://registry.npmjs.org/3d-tiles-renderer)

### Inferences
- For a single residential lot (about 50 x 50 m at QL2 is roughly 5–20k points), skip streaming formats. Clip server-side with PDAL to a small LAZ or even a JSON/binary Float32 array and load it directly as `THREE.Points`. COPC/copc.js matters only when browsing whole 3DEP tiles. Colour by classification or by distance-to-fitted-plane for the visual check.
- Use the same local origin (subtract a centroid) in PDAL, roofer (which needs it anyway because of float precision) and Three.js to avoid jitter.

### Gaps
- I did not verify whether Potree 1.8.x loads COPC natively, or whether three.js examples have an official LAZ loader.

## License red flags (GPL/AGPL isolation vs commercial-clean)

### Takeaway
Commercially clean for embedding in the studio: Open3D (MIT), pyRANSAC-3D (Apache-2.0), PDAL/python-pdal (BSD), laspy (BSD-2), copclib (BSD), pyvista (MIT), copc.js (MIT), laz-perf (Apache-2.0), loaders.gl (MIT), Potree and PotreeConverter (BSD-2), straight-skeleton **1.x** (MIT, pure TS), polygnn/points2poly/abspy (MIT), 3dbag-pipeline (Apache-2.0). GPL/AGPL tools to run only as separate internal programs: roofer, geoflow (GPL/AGPL mix), City3D, PolyFit, 3dfier, Easy3D, CGAL algorithm packages, CloudCompare, lidR/lasR, untwine, wrench, bpypolyskel, City4CFD (AGPL), and **straight-skeleton 2.x/3.x (CGAL GPL inside Wasm)**. Repos with no license (point2building, point2wss, columbus-lidar-lod2) are all-rights-reserved by default. The RoofN3D/Building3D datasets have unclear terms.

### Cited Findings
- roofer GPLv3 — [roofer README](https://raw.githubusercontent.com/3DBAG/roofer/HEAD/README.md); geoflow-bundle parts are "either GNU General Public License or the GNU Affero General Public License", with examples under CC0 — [geoflow-bundle LICENSE](https://raw.githubusercontent.com/geoflow3d/geoflow-bundle/HEAD/LICENSE); gfp-building-reconstruction AGPL-3.0 — [GitHub](https://github.com/geoflow3d/gfp-building-reconstruction)
- City3D, PolyFit, 3dfier, Easy3D, lidR, lasR, untwine, wrench, bpypolyskel: GPL-3.0; City4CFD: AGPL-3.0 (shields.io/GitHub license detection, 2026-11-16) — [City3D](https://github.com/tudelft3d/City3D); [PolyFit](https://github.com/LiangliangNan/PolyFit); [3dfier](https://github.com/tudelft3d/3dfier); [City4CFD](https://github.com/tudelft3d/City4CFD); [bpypolyskel](https://github.com/prochitecture/bpypolyskel)
- CGAL algorithm packages (Shape Detection, Straight Skeleton, Polygonal Surface Reconstruction, Kinetic reconstruction, Arrangements, PMP, Alpha Shapes) are GPL; Kernel/Support are LGPL; a commercial license is sold by GeometryFactory — [CGAL packages](https://doc.cgal.org/latest/Manual/packages.html); [CGAL license](https://www.cgal.org/license.html)
- straight-skeleton ≥2 wraps CGAL's straight skeleton via Wasm (README), while npm metadata labels every version MIT — [README](https://raw.githubusercontent.com/StrandedKitty/straight-skeleton/HEAD/README.md); [npm](https://registry.npmjs.org/straight-skeleton)
- CloudCompare GPL — [license.txt](https://raw.githubusercontent.com/CloudCompare/CloudCompare/HEAD/license.txt)
- City3D uses an optional commercial solver (Gurobi) and bundles the SCIP source — [City3D README](https://raw.githubusercontent.com/tudelft3d/City3D/HEAD/ReadMe.md)
- point2building, point2wss and columbus-lidar-lod2 have no specified license (GitHub "not specified") — [point2building](https://github.com/prs-eth/point2building); [point2wss](https://github.com/KWIKERRR/point2wss)
- RoofN3D: free usage with a citation requirement and no named license — [RoofN3D site](https://roofn3d.gis.tu-berlin.de/)
- USGS 3DEP lidar is public domain (stated in the assignment context; not re-verified here).

### Inferences
- GPL/AGPL obligations trigger on distribution (AGPL also on providing network access to users). Running roofer, City3D or CloudCompare as unmodified internal tools on the contractor's own server, producing data outputs (CityJSON/roof JSON), creates no source-disclosure duty for the studio code, since GPL covers programs, not their output data. Exposing an AGPL tool (geoflow's gfp-building-reconstruction, City4CFD) as a web service to *customers* could trigger AGPL §13, so prefer roofer (GPL, not AGPL) over geoflow-bundle.
- Do not `import` GPL Python bindings (roofer, PolyFit, CloudComPy, bpypolyskel) into a module you plan to distribute to customers or sell. Call them in a subprocess or container behind a file/CLI boundary. For in-house-only use, even direct import is generally acceptable because nothing is distributed. This is a legal judgment and should be confirmed with counsel if the studio is ever sold or shipped.
- The Blender side: Blender itself is GPL, and add-ons that import `bpy` are generally treated as GPL when distributed, so using bpypolyskel (GPL) inside in-house Blender scripts adds no new constraint (inference).
- For the Three.js studio (if ever shipped to customers as a web app), keep straight-skeleton pinned to `^1.1.0`. Bundling 3.x would ship GPL CGAL code to browsers.
- If City3D/PolyFit are used commercially, verify that the bundled SCIP version is Apache-2.0 (SCIP ≥8.0.3). Older SCIP was under the ZIB Academic License, which is non-commercial (background knowledge, not verified this session).

### Gaps
- I did not check each CloudCompare plugin's license or the CloudComPy license file (LICENSE returned 404).
- The Microsoft Building Footprints license (ODbL) was not re-verified in this session.
