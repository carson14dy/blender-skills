# Free ($0) agent skills, MCP servers, Blender add-ons, QGIS plugins and JS libraries for roof measurement accuracy

Research date: 2026-11-16. Star counts, last-push dates and SPDX licenses come from the GitHub search API (queried through `agent-reach github search` and `gh api search/repositories`), captured on 2026-11-16. "push" means the last push to any branch, not necessarily a release. In several cases GitHub reported a license as `null` or `NOASSERTION`, and I note this where it happened. npm license and version data comes from registry.npmjs.org `/latest`.

Method note: the per-repo GitHub REST endpoints were blocked in this session, so star and push data comes from the search API, and README text was read from raw.githubusercontent.com. Everything under "Inferences" is my own judgement and was not verified.

---

## 1. Claude Code / agent skills (GIS, lidar, point clouds, Blender, CAD, roofing)

### Takeaway
I found no ready-made skill for measuring roofs from lidar. The closest useful ones are geospatial "method" skills: muend/geoai-skills (it has a `point-cloud-lidar` skill), jaakla/openmapstack-skills, opengeos/geoai-skills and a QGIS/PyQGIS skill pack. There are also Blender modelling skill packs. All of these are MIT and free, but most are young (2026) and have low star counts. Treat them as prompt or reference material to vendor or adapt, not as dependencies you can trust.

### Cited Findings
**Registries and marketplaces**
- skills.sh search for "lidar" ranks `point-cloud-lidar` from muend/geoai-skills first (80 installs). Next come ROS2 robotics lidar skills (miuav/vibe-coding-ros2), which are not relevant to aerial roofs — [skills.sh ?q=lidar](https://skills.sh/?q=lidar)
- skills.sh search for "geospatial" lists `mapbox-geospatial-operations` (mapbox/mapbox-agent-skills, 2.3K installs), `geospatial-data-pipeline` (curiositech/some_claude_skills, 355), `geospatial-analysis` (itallstartedwithaidea/agent-skills, 125) and isaaccorley/geospatial-skills (`geospatial-frontend`, `geospatial-viewers`) — [skills.sh ?q=geospatial](https://skills.sh/?q=geospatial)
- skills.sh search for "gis" lists `gis` (vamseeachanta/workspace-hub, 98), `opengis-skills` (znlgis/opengis-skills, 48), `open-gis` (jaakla/openmapstack-skills, 79) and `gemgis` (steadfastasart/geoscience-skills, 73) — [skills.sh ?q=gis](https://skills.sh/?q=gis)
- skills.sh search for "blender" is led by `blender-modeling` from roble3/cc-blender-skill (3.7K installs) and `blender-web-pipeline` from freshtechbro/claudedesignskills (4.0K) — [skills.sh ?q=blender](https://skills.sh/?q=blender)
- The skills.sh CLI is vercel-labs/skills (`npx skills`), MIT, 39,520 stars, pushed 2026-11-12 — [GitHub](https://github.com/vercel-labs/skills)
- anthropics/skills (195,387 stars, pushed 2026-11-14) is the official public skills repo. GitHub shows no SPDX license — [GitHub](https://github.com/anthropics/skills)
- The official Claude Code plugin marketplace (anthropics/claude-plugins-official, 317 plugins) has no GIS, lidar or Blender plugin. Its geo-related plugins are `mapbox` ("Mapbox skills and MCP servers… geospatial tools") and `amazon-location-service`. Both are vendor platforms that need accounts or tokens, and their usage-based billing is my inference. It also has `unreal-engine-skills-for-claude-code` — [marketplace.json](https://raw.githubusercontent.com/anthropics/claude-plugins-official/HEAD/.claude-plugin/marketplace.json)
- Curated lists you can mine further: ComposioHQ/awesome-claude-skills (79,584 stars, pushed 2026-09-18), VoltAgent/awesome-agent-skills (37,215 stars, MIT, pushed 2026-11-15), travisvn/awesome-claude-skills (15,830 stars, pushed 2026-04-28) and joevstaas/awesome-claude-skills (7 stars, data engineering and geospatial focus) — [ComposioHQ](https://github.com/ComposioHQ/awesome-claude-skills), [VoltAgent](https://github.com/VoltAgent/awesome-agent-skills), [travisvn](https://github.com/travisvn/awesome-claude-skills), [joevstaas](https://github.com/joevstaas/awesome-claude-skills)

**Geospatial and lidar skills (all $0)**
- **muend/geoai-skills**: MIT, 45 stars, pushed 2026-10-17. It is "a vendor-neutral collection of 18 Agent Skills for the methodological layer between a user request and a geospatial claim". It claims benchmarked critical failures dropped from 14.1% to 4.3% on Claude Code. It is listed on skills.sh and in Awesome Claude Code — [GitHub](https://github.com/muend/geoai-skills)
  - Its `point-cloud-lidar` skill covers "PDAL pipelines, LAS/LAZ/COPC handling, ground classification, DTM/DSM/CHM generation… building metrics". It also owns "vertical datum agreement" and "the vertical-accuracy budget". It warns about "trusting vendor classification blindly", "mixing return types in surfaces" and "ignoring point density when choosing output resolution". Skill license: MIT — [SKILL.md](https://raw.githubusercontent.com/muend/geoai-skills/HEAD/skills/point-cloud-lidar/SKILL.md)
  - Install: `npx skills add muend/geoai-skills` (skills.sh). This is inferred from the skills.sh listing.
- **jaakla/openmapstack-skills**: MIT, 78 stars, pushed 2026-11-10. It has four skills: `open-map-stack`, `reproducible-gis-project`, `geospatial-data-discovery` (it "find[s] and assess[es] open geospatial data") and `spatial-sql`. It is built on STAC, GeoParquet, COG, PMTiles, DuckDB and PostGIS. Install: `npx skills@1.5.26 add jaakla/openmapstack-skills --skill open-map-stack -g`. Its homepage loads optional PostHog analytics, but the skill itself does not — [README](https://github.com/jaakla/openmapstack-skills)
- **opengeos/geoai-skills** (from Qiusheng Wu's opengeos group): MIT, 38 stars, pushed 2026-10-12. It is a Claude Code plugin covering inspecting geodata, downloading satellite imagery (for example NAIP by bbox and year) and AI object detection. Install: `/plugin marketplace add opengeos/geoai-skills` then `/plugin install geoai-skills@geoai-skills`. It needs `pip install geoai-py`, plus `geoai-py[extra]` for Overture Maps — [README](https://github.com/opengeos/geoai-skills)
- **Impertio-Studio/QGIS-Claude-Skill-Package**: MIT, 39 stars, pushed 2026-07-08. It has "19 deterministic skills" teaching "correct, production-quality PyQGIS code". Install: `claude install-skill https://github.com/OpenAEC-Foundation/QGIS-Claude-Skill-Package`, or git clone into your skills directory. The README's install URL points to the OpenAEC-Foundation org, so the repo may have moved — [README](https://github.com/Impertio-Studio/QGIS-Claude-Skill-Package)
- **dekart-xyz/geosql**: MIT, 686 stars, pushed 2026-11-09. It is a skill for PostGIS, BigQuery, Snowflake and Wherobots, and can query Overture Maps shares on BigQuery and Snowflake. Install: `pip install geosql && geosql`. It sends a "best-effort version check… and an opaque random installation ID". Cloud warehouses can cost money, but PostGIS is $0 — [README](https://github.com/dekart-xyz/geosql)
- **tyrrs/gis-convert**: MIT, 2 stars, pushed 2026-06-01. It is a skill and CLI for GIS format conversion, including point clouds and 3D. Install: `npx skills add tyrrs/gis-convert`. The README says this "does not install GDAL/OGR, PROJ, PDAL" — [README](https://github.com/tyrrs/gis-convert)
- **fakmalpradana/claude-skills**: 0 stars, no license, pushed 2026-07-06. It is a personal skill hub with a `lidar-pointcloud` skill ("LAS/LAZ → classification → DTM/DSM → LOD-2 → 3D Tiles pipeline patterns") and a `geospatial-python` skill. **It has no license**, so you have no legal right to reuse it, but you can read it for ideas — [README](https://github.com/fakmalpradana/claude-skills)
- **kylefritz/3d-model-skill**: MIT, 1 star, pushed 2026-11-14. It is a Claude skill that models a house from phone-lidar scans and real measurements into a parametric web 3D viewer, with drawings and a buy list. "Every dimension says where it came from (tape, scan, spec sheet, estimate)". This provenance pattern is relevant to measurement auditability — [README](https://github.com/kylefritz/3d-model-skill)
- Other related skill repos found in GitHub search, all young and low-star (unvetted): ghostship25/super-gis (MIT, 4 stars), Adilmunawar/ZD-claude-plugin (MIT, 10 stars, agricultural geospatial), Anchenry/glode-geospatial (2 stars, no license), and Impertio-Studio/CesiumJS-Claude-Skill-Package (MIT, 2 stars) — [GitHub search "geospatial skill claude"](https://github.com/search?q=geospatial+skill+claude&type=repositories)

**Blender skills (MIT, free)**
- **RobLe3/cc-blender-skill**: MIT, 165 stars, pushed 2026-10-12. It is a Claude Code skill plugin with 10 chain-loadable skills for Blender 5.x, and its `blender-modeling` skill has 3.7K installs on skills.sh — [GitHub](https://github.com/RobLe3/cc-blender-skill), [skills.sh](https://skills.sh/?q=blender)
- **arjun988/blender-skills**: MIT, 3,692 stars, pushed 2026-11-06. It has "94 specialist Blender skills… MCP-powered production pipeline" — [GitHub](https://github.com/arjun988/blender-skills)
- **EL4CTEO/blender-skills**: MIT, 1,227 stars, pushed 2026-11-13. It covers "Professional Blender 5.3 workflows as Agent Skills" — [GitHub](https://github.com/EL4CTEO/blender-skills)
- **majidmanzarpour/blender-game-skills**: MIT, 184 stars, pushed 2026-09-24. It claims assets that are "measured" — [GitHub](https://github.com/majidmanzarpour/blender-game-skills)
- Name collision: the user's own repo is `carson14dy/blender-skills`, and both arjun988 and EL4CTEO use the same repo name. This is not a problem, but worth noting when installing.

### Inferences
- None of these skills does roof-plane fitting or measurement of roof edges (eave, rake, ridge, hip, valley). The studio will still need its own roof-specific skill. The best material to borrow is the datum, accuracy-budget and classification discipline in muend's `point-cloud-lidar` skill, and the source-provenance pattern in kylefritz's skill.
- Most geo skills are under 12 months old and have fewer than 100 stars. Pin to a commit or vendor a copy rather than auto-updating.

### Gaps
- I did not open each Blender skill pack to confirm that any covers precise measurement or CAD-style dimensioning. The descriptions suggest they target art and game production.
- I could not confirm whether `claude install-skill` is a real Claude Code subcommand. It appears only in the Impertio README. Treat cloning into `.claude/skills/` as the reliable method.
- I found no roofing-specific skill on skills.sh, GitHub or the official marketplace (searches: "roof pitch lidar", "roof reconstruction blender", "lidar skill claude").

---

## 2. MCP servers (GIS, geospatial, lidar, USGS, OSM, CAD, Blender)

### Takeaway
Free and maintained options exist for most needs:
- QGIS: nkarasiak/qgis-mcp (very active), or QgisRemoteMCP for headless Docker use.
- GDAL: gdal-mcp.
- OSM and Overpass: cyanheads.
- Overture buildings: PlaceRoot and overture-mcp-server.
- PostGIS: receptopalak/postgis-mcp.
- GeoServer: mahdin75/geoserver-mcp.
- USGS TNM/3DEP catalog: pipeworx, which is rate-limited without a free account.
- Blender: ahujasid's blender-mcp, now renamed `mcp-for-blender`.

There is **no mature PDAL or lidar MCP**. The point-cloud MCPs found are tiny one-person projects (0–5 stars). For lidar, the agent should run PDAL, laspy or Open3D directly in Python or CLI rather than through an MCP.

### Cited Findings
**Directory**
- **sparkgeo/geo-mcp-servers**: MIT, 248 stars, pushed 2026-11-05. It is "a curated, tracked list" of geospatial MCP servers, with an access label for each (open, commercial, paywalled) and a health label (active, stale, archived). It is the best single directory for this area — [README](https://github.com/sparkgeo/geo-mcp-servers)
  - It labels Vexcel MCP (aerial and oblique imagery, DSM/DTM, roof metadata) as **paywalled** — [same](https://github.com/sparkgeo/geo-mcp-servers)
  - It labels Regrid MCP (parcels) and MAIA MCP as **commercial** — [same](https://github.com/sparkgeo/geo-mcp-servers)
  - It labels the Cesium AI Integrations MCP as "official / commercial". The repo itself is Apache-2.0 with 94 stars, pushed 2026-08-19. Cesium ion is the paid part — [same](https://github.com/sparkgeo/geo-mcp-servers), [GitHub](https://github.com/CesiumGS/cesium-ai-integrations)
  - It marks the archived Anthropic Google Maps reference server (which had elevation) as archived and commercial (Google API key) — [same](https://github.com/sparkgeo/geo-mcp-servers)

**QGIS MCPs**
- **nkarasiak/qgis-mcp**: GPL-2.0, 440 stars, pushed 2026-11-11. It provides "125 MCP tools covering layer management, feature editing, processing, rendering, styling, layout & atlas authoring, cross-layer SQL" and works with QGIS 3.28–4.x. The architecture is FastMCP server ↔ TCP socket ↔ QGIS plugin, so it **needs a running QGIS Desktop**. Install: QGIS Plugin Manager → "QGIS MCP", then `claude mcp add -s user qgis -- uvx --from https://github.com/nkarasiak/qgis-mcp/archive/refs/heads/main.zip qgis-mcp-server` — [README](https://github.com/nkarasiak/qgis-mcp); the sparkgeo list rates it "open / active" — [list](https://github.com/sparkgeo/geo-mcp-servers)
- **jjsantos01/qgis_mcp**: the original, 1,153 stars, last push 2025-10-01. GitHub reports **no license**, and fetching LICENSE returned 404. The sparkgeo list rates it "stale". It also needs QGIS Desktop running with the plugin copied in manually — [README](https://github.com/jjsantos01/qgis_mcp), [list](https://github.com/sparkgeo/geo-mcp-servers)
- **nic01asFr/QgisRemoteMCP**: MIT, 11 stars, pushed 2026-10-03. It exposes "a full QGIS Desktop through Docker" (`docker compose up -d --build`) with noVNC for the human. It has 46 tools, including `execute_python` (PyQGIS) and `run_processing` ("~730 Processing algorithms (native, qgis, gdal, grass, 3d)"). Claude Code picks up its `.mcp.json` automatically. It ships MCP resource "skills", including `skill://solar` ("Solar cadastre pipeline (DSM, r.sun…)") — [README](https://github.com/nic01asFr/QgisRemoteMCP). The sparkgeo list shows a sibling, QgisStreamMCP — [list](https://github.com/sparkgeo/geo-mcp-servers)
- Other QGIS bridges in the sparkgeo list: anitagraser/qgis_mcp (QGIS2OllamaMCP, active) and YUYU20061107/gis-agent-bridges (safety-gated multi-GIS) — [list](https://github.com/sparkgeo/geo-mcp-servers)

**GDAL, raster, terrain**
- **JordanGunn/gdal-mcp** (now Wayfinder-Foundry): MIT, 85 stars, pushed 2026-05-25. It wraps GDAL and Rasterio operations "with a reflection middleware that requires structured justification before executing operations whose methodology matters (CRS choice, resampling method…)". It also offers conversion, reprojection, COG output and metadata. Install: `uvx --from gdal-mcp gdal --transport stdio`, or Docker — [README](https://github.com/JordanGunn/gdal-mcp)
- **razinkele/gis-hydro-mcp**: MIT, 1 star, pushed 2026-05-01. Provides DEM slope, aspect and hillshade, sink filling and D8 flow. It is low-trust but shows slope and aspect as MCP tools — [GitHub search "gdal mcp"](https://github.com/search?q=gdal+mcp&type=repositories)
- **mapsmith-ai/MapSmith**: **AGPL-3.0**, 2 stars, pushed 2026-11-13. It does "deterministic GIS geoprocessing… terrain & hydrology (GeoPandas/DuckDB/Whitebox)". It is AGPL, so it is fine internally but has network-use obligations if you expose it as a service — [list](https://github.com/sparkgeo/geo-mcp-servers)

**Point cloud and lidar MCPs (all immature)**
- **jyou-syo/pointcloud-mcp**: MIT, 2 stars, pushed 2026-05-17. It handles LAS/LAZ (load, diff, volume, heatmap, PDF report) and targets Japanese earthworks (i-Construction). The README is in Japanese — [README](https://github.com/jyou-syo/pointcloud-mcp)
- **yufeioptimal/cloudcompare-mcp**: 5 stars, pushed 2026-05-02, **no license**. It offers native `read_cloud_metadata` and `visualize_cloud` (renders top, front and side PNGs the model can see), plus CloudCompare tools (subsample, C2C and C2M distances) — [README](https://github.com/yufeioptimal/cloudcompare-mcp)
- **feelgom/pointcloud-mcp**: 0 stars, no license, pushed 2026-07-14. It does "RANSAC plane detection, and ICP alignment" with Open3D on .ply and .pcd files, and has 3 tools. It is a portfolio demo — [README](https://github.com/feelgom/pointcloud-mcp)
- I found **no PDAL MCP**: GitHub search for "pdal mcp" returned nothing — [GitHub search](https://github.com/search?q=pdal+mcp&type=repositories)

**USGS / The National Map / 3DEP**
- **pipeworx-io/mcp-usgs-national-map**: MIT, 0 stars, pushed 2026-11-09. It wraps the TNM Access API, "the federal download catalog… 3DEP elevation (DEMs and lidar point clouds)…". Tools: `tnm_datasets` and `tnm_search_products(datasets, bbox, polygon, prod_formats…)`. It runs through `npx` and forwards calls to the Pipeworx gateway. "Without a key it calls anonymously, capped at 50 calls a day. A free account [raises limits]". It is unofficial, and **data passes through a third-party gateway** — [README](https://github.com/pipeworx-io/mcp-usgs-national-map)
- **GSA-TTS/mcp-server-usgs-nationalmap**: 0 stars, no license, pushed 2026-11-15. Despite its name, it wraps only NHDPlus HR hydrography, not 3DEP, so it is not useful for roofs — [README](https://github.com/GSA-TTS/mcp-server-usgs-nationalmap)

**OSM, Overpass, Overture (footprints)**
- **cyanheads/openstreetmap-mcp-server**: Apache-2.0, 9 stars, pushed 2026-11-13. It does geocoding, reverse geocoding and Overpass spatial queries over STDIO or Streamable HTTP. Rated "open / active" — [GitHub](https://github.com/cyanheads/openstreetmap-mcp-server), [list](https://github.com/sparkgeo/geo-mcp-servers)
- **jagan-shanmugam/open-streetmap-mcp**: MIT, 235 stars, last push 2025-07-12. Rated "stale" — [list](https://github.com/sparkgeo/geo-mcp-servers)
- **wiseman/osm-mcp**: 91 stars, last push 2025-03-13, no license (stale) — [GitHub search](https://github.com/search?q=openstreetmap+mcp&type=repositories)
- **chuofringer/placeroot**: MIT, 3 stars, pushed 2026-11-14. It works with "Overture Maps places, geocoding, admin boundaries, buildings & isochrones via DuckDB (no ETL, no API key)" and claims "Zero setup… no key, no database". Install: `claude mcp add placeroot -- uvx placeroot` — [README](https://github.com/chuofringer/placeroot), [list](https://github.com/sparkgeo/geo-mcp-servers)
- **srivinod1/overture-mcp-server**: MIT, 5 stars, pushed 2026-03-12. It queries Overture GeoParquet on S3 through DuckDB spatial, including buildings — [README](https://github.com/srivinod1/overture-mcp-server)
- soapboxbuild/overture-mcp (building footprints) is **archived** — [GitHub search](https://github.com/search?q=overture+buildings+mcp&type=repositories)

**PostGIS, GeoServer**
- **receptopalak/postgis-mcp**: 21 stars, pushed 2026-04-21. It is a Node.js PostGIS MCP with multiple connections configured through environment variables. GitHub shows no license and LICENSE returned 404, though the sparkgeo list labels it "open / active" — [list](https://github.com/sparkgeo/geo-mcp-servers)
- **mahdin75/geoserver-mcp**: MIT, 97 stars, pushed 2026-08-16. It connects to the GeoServer REST API. camptocamp/mcp-geoserver is GPL-2.0, 2 stars, pushed 2026-11-12 — [GitHub search "geoserver mcp"](https://github.com/search?q=geoserver+mcp&type=repositories)

**Blender MCPs**
- **ahujasid/blender-mcp → ahujasid/mcp-for-blender**: MIT, 34,540 stars, pushed 2026-11-15. It was "formerly `blender-mcp` — the PyPI package is now `mcp-for-blender`", and "`uvx blender-mcp` still runs the server and no config change is required". Install: `claude mcp add blender uvx mcp-for-blender` plus `uvx mcp-for-blender install-addon` — [README](https://github.com/ahujasid/mcp-for-blender)
  - Telemetry: content collection is opt-in, but "a minimal anonymous usage record" (install ID, session ID, tool name, success, duration) is collected by default. You can disable it with an environment variable documented in the README's "Telemetry Control" section — [README](https://github.com/ahujasid/mcp-for-blender)
- Alternatives: hitkeeen/blender-ai-mcp-addon (MIT, 1,235 stars, pushed 2026-11-12); dhakalnirajan/blender-open-mcp (MIT, 123 stars, pushed 2026-10-27, for open-weights models); scenario-labs/blender-plugin (GPL-3.0, 1,022 stars, built around Scenario's AI generation service, which is likely paid); and VxASI/blender-mcp-vxai (MIT, 301 stars, last push 2025-03-21, stale) — [GitHub search "blender mcp"](https://github.com/search?q=blender+mcp&type=repositories)

**CAD MCPs**
- **neka-nat/freecad-mcp**: MIT, 3,351 stars, pushed 2026-11-12. spkane/freecad-addon-robust-mcp-server: Apache-2.0, 271 stars, pushed 2026-11-15. blwfish/freecad-mcp: LGPL-2.1, 66 stars, 32 tools. bonninr/freecad_mcp: MIT, 230 stars, last push 2025-03-20 (stale) — [GitHub search "freecad mcp"](https://github.com/search?q=freecad+mcp&type=repositories)
- **pzfreo/build123d-mcp**: Apache-2.0, 152 stars, pushed 2026-11-15 (a parametric Python CAD kernel). jdilla1277/agentcad: Apache-2.0, 217 stars. daobataotie/CAD-MCP: MIT, 707 stars (it drives AutoCAD and other commercial CAD, so the host software is paid). AnCode666/multiCAD-mcp: Apache-2.0, 184 stars (commercial CAD hosts) — [GitHub search "cad mcp server"](https://github.com/search?q=cad+mcp+server&type=repositories)

**Other**
- Google Earth Engine MCPs exist (P-Srikanthan/geeflow, MIT, 38 stars; FrontierDevelopmentLab/gee-mcp, MIT, 9 stars). They need a Google Earth Engine account and Cloud project, and commercial GEE use is paid (inference) — [GitHub search "earth engine mcp"](https://github.com/search?q=earth+engine+mcp&type=repositories)
- AWS Registry of Open Data MCP (awslabs/mcp `roda-mcp-server`) lets you search the 1,000+ public S3 datasets — [list](https://github.com/sparkgeo/geo-mcp-servers)

### Inferences
- For a Linux-container agent, the most practical free stack is the following. gdal-mcp, PlaceRoot (or overture-mcp) and cyanheads OSM run as stdio MCPs with no keys. QGIS processing is better called directly through `qgis_process` (section 4) than through a desktop-socket MCP. QgisRemoteMCP is the only QGIS MCP built for Docker or headless use, but it has only 11 stars.
- For 3DEP discovery, the agent can call the public TNM Access API or Planetary Computer STAC directly over HTTP. That avoids the pipeworx gateway's 50-calls-a-day anonymous cap and the third-party data path.
- The point-cloud MCPs are not worth depending on. Wrapping a project-local PDAL + Open3D script as a skill gives more control.

### Gaps
- I did not check mcp.so, glama.ai or the official MCP Registry directly, so I may have missed servers. The sparkgeo list is the most complete geo-specific index I found.
- Pipeworx's terms of service and free-account limits were not checked beyond the README.

---

## 3. Blender add-ons

### Takeaway
The free, commercially usable, maintained set is:
- **BlenderGIS** (GPL-3.0; OSM, basemaps and DEM import; Delaunay terrain; georeferencing). Its SRTM download needs a free OpenTopography key.
- **Point Cloud I/O** (GPL-3.0, on extensions.blender.org; LAS/LAZ import into native point clouds).
- **MeasureIt** (now a free extension, updated for Blender 5.0) or **MeasureIt_ARCH**.
- **CAD Sketcher** (GPL-3.0, constraint sketcher).
- **building_tools** (MIT).
- **Archimesh** (GPL, has a roof maker, limited support).

These are paid: **Point Cloud Visualizer** ($85–$150), **blosm Pro**, and **Roof Generator** (Superhive, $6.30–$63). The **blosm** base version is free (pay-what-you-want).

### Cited Findings
- **BlenderGIS** (domlysz): GPL-3.0, 9,631 stars, last push 2025-12-20. It can "display dynamics web maps inside Blender 3d view, requests for OpenStreetMap data (buildings, roads…), get true elevation data from the NASA SRTM mission", "compute a terrain mesh by Delaunay triangulation" and "manage georeferencing informations of a scene". "Since 2022, the OpenTopography web service requires an API key… This service is still free." — [README](https://github.com/domlysz/BlenderGIS)
- **blosm** (vvoovv): 2,165 stars, pushed 2026-11-12; GitHub shows no SPDX license, but the README says the source is GPL.
  - The base version ("can be downloaded for free"; paying is "completely optional") imports OSM buildings using height and floors, supports "a large number of roof shapes", and downloads terrain at "about 30 meter" resolution.
  - The **Pro (paid, Gumroad)** version adds texturing and "satellite imagery and web maps projected on a terrain". Google 3D cities import needs a Google Map Tiles API key (inference, from the "Google 3D cities" feature) — [README](https://github.com/vvoovv/blosm)
- **Point Cloud Visualizer** (Jakub Uhlík): **paid**, "Standard $85, Pro $150", with 12 months of updates. It is actively updated (3.13.0, released 2026-10-10) — [Superhive](https://superhivemarket.com/products/pcv), [versions](https://superhivemarket.com/products/pcv/versions)
- **Point Cloud I/O** (StudioMedio): free on extensions.blender.org. It imports and exports "E57, PLY, LAS/LAZ, PCD, XYZ, and PTS" into "Blender's native PointCloud object", with classification and intensity as point attributes. LAZ is decoded "via the bundled `lazrs` codec". Version 0.6.0 (2026-09-11) needs Blender 5.1+ — [extension page](https://extensions.blender.org/add-ons/point-cloud-io/), [versions](https://extensions.blender.org/add-ons/point-cloud-io/versions/). Source: studiomedio/blender-point-cloud-io, GPL-3.0, 6 stars, pushed 2026-09-11 — [GitHub search](https://github.com/search?q=point-cloud-io+blender&type=repositories)
- Other LAS importers:
  - pointcloudbase-ux/blender-las-importer: "free", Blender 4.x, LAS/LAZ with RGB, voxel or random thinning; **no license file**; 0 stars — [README](https://github.com/pointcloudbase-ux/blender-las-importer)
  - nittanygeek/LiDAR-Importer: MIT, 78 stars, last push 2024-05-06. The author warns it was "written in 2014… may not be compatible with the latest version of Blender" (abandoned) — [README](https://github.com/nittanygeek/LiDAR-Importer)
  - mnmly/blender-e57-point-cloud-lite: GPL-3.0, an E57 importer for Blender 5.2+ — [GitHub search](https://github.com/search?q=blender+lidar+import&type=repositories)
- **MeasureIt**: formerly bundled, now an extension. Version 1.8.4 (2025-10-24) "fix[es] the problems in Blender 5.0" — [extensions](https://extensions.blender.org/add-ons/measureit/versions/), [source](https://projects.blender.org/antoniov/measureit). Stack Exchange confirms "In Blender 4.2+, MeasureIt is available as an installable Extension" — [SE](https://blender.stackexchange.com/questions/136725/how-to-render-measurements-in-blender)
- **MeasureIt_ARCH** (kevancress): 322 stars, last push 2026-03-20. GitHub reports `NOASSERTION`, and the GPL license is inferred from it being a MeasureIt fork. It "adds tools to create design documentation" — [GitHub](https://github.com/kevancress/MeasureIt_ARCH)
- **CAD Sketcher** (hlorus): GPL-3.0, 3,475 stars, pushed 2026-11-05. It is a "constraint-based geometry sketcher" — [GitHub](https://github.com/hlorus/CAD_Sketcher)
- **building_tools** (ranjian0): MIT, 1,522 stars, pushed 2026-09-24. A "building generation addon" — [GitHub](https://github.com/ranjian0/building_tools)
- **Archimesh**: "was part of Blender 4.1 bundled add-ons. It is now offered as it is, with limited support". It includes `achm_roof_maker.py` (GPL-2.0-or-later) — [extension](https://extensions.blender.org/add-ons/archimesh/), [source](https://projects.blender.org/extensions/archimesh/src/branch/main/source/achm_roof_maker.py)
- **Roof Generator for Blender** (Superhive): it has 23 roof types, plus "pitch, overhang, plan, profile". It is **paid**: Personal $6.30, Commercial $12.60, Studio $63 — [Superhive](https://superhivemarket.com/products/roof-generator-for-blender). Also kaleidawave's "Roof Generator — Geometry Nodes" on itch.io (pricing and license not verified) — [itch.io](https://kaleidawave.itch.io/roof-generator-geometry-nodes)
- **SBCV/Blender-Addon-Photogrammetry-Importer**: MIT, 1,382 stars, last push 2026-02-16. It imports photogrammetry (COLMAP, Meshroom, OpenMVG and similar) cameras and points — [GitHub](https://github.com/SBCV/Blender-Addon-Photogrammetry-Importer)
- **agmmnn/awesome-blender**: CC0, 7,650 stars, pushed 2026-11-15. A curated list of add-ons, including AI and MCP tools — [GitHub](https://github.com/agmmnn/awesome-blender)

### Inferences
- GPL add-ons (BlenderGIS, CAD Sketcher, Point Cloud I/O, Archimesh) are fine for in-house use. GPL obligations apply only when you distribute modified add-on code. Roof models and measurements made with them are not GPL-encumbered.
- For accuracy, the strongest free Blender path is to import 3DEP LAS/LAZ with Point Cloud I/O, cropped to the building in PDAL beforehand, and snap or fit planar triangles to it. Then check edge lengths with MeasureIt. BlenderGIS's SRTM (30 m) and blosm terrain (~30 m) are far too coarse for roof geometry and suit site context only.
- blosm's OSM roof shapes come from OSM tags (often missing for Sioux Falls homes). Treat them as a starting guess, not a measurement.

### Gaps
- I did not verify that BlenderGIS's latest release supports Blender 5.x. Its last push was 2025-12-20.
- I did not verify the MeasureIt_ARCH license file directly, or its Blender 5.x compatibility.
- I found no free Blender add-on that fits roof planes to lidar automatically.

---

## 4. QGIS workflows and plugins for roofs, and headless use

### Takeaway
QGIS (free, GPL) has had a native PDAL-based point-cloud processing provider since 3.32. It can be driven headlessly with `qgis_process` in a Linux container, using a base image such as 3liz/qgis-platform. UMEP (GPL-3.0) adds DSM-based building tools: wall height and aspect, DSM generation, and solar on roofs (SEBE). Roof pitch and aspect from a DSM can be done with native slope and aspect tools.

### Cited Findings
- The QGIS 3.32 changelog says the release "features the long awaited functionality for Native Point Cloud Processing". The "native processing provider… utilizes the pdal_wrench command line tool" and offers information, convert format (LAS↔LAZ), reproject, fix projection, clip by polygon and merge, along with other algorithms. 3.32 also "allows measuring on point cloud points" — [QGIS 3.32 changelog](https://changelog.qgis.org/en/qgis/version/3.32/)
- PDAL algorithms are ordinary Processing calls: "every LiDAR operation is a `processing.run()` call with a dictionary of parameters" — [pyqgis.com](https://pyqgis.com/spatial-data-processing-automation/point-cloud-and-lidar-workflows/run-pdal-algorithms-from-pyqgis/)
- QGIS ships `qgis_process` ("QGIS Processing Executor"), which runs "Processing algorithms and models (built-in or provided by plugins) directly from the command line without starting QGIS Desktop" — [QGIS docs 3.44](https://docs.qgis.org/3.44/en/docs/user_manual/processing/standalone.html); see also [spatialworkflow.io](https://www.spatialworkflow.io/qgis-process-cli-automation/)
- Docker: the 3liz/qgis-platform image "is perfectly suited for using processing with python" — [QGIS-Developer list](https://lists.osgeo.org/pipermail/qgis-developer/2021-November/064332.html). A known gotcha: plugins installed into a container are not loaded by `qgis_process` automatically (issue about UMEP for Processing) — [qgis/QGIS#41218](https://github.com/qgis/QGIS/issues/41218)
- **UMEP** (UMEP-dev/UMEP): GPL-3.0, 106 stars, pushed 2026-09-30. UMEP-processing is GPL-3.0, 15 stars, pushed 2026-09-24. Its tools include:
  - "DSM generator" (from footprints and OSM)
  - "Wall Height and Aspect" ("height and aspect of building walls based on a DSM")
  - "Sky View Factor"
  - "Solar Energy on Building Envelopes (SEBE)", which computes "solar irradiance on building roofs and walls"
  
  UMEP is "free to download" — [UMEP docs](https://umep-docs.readthedocs.io/en/latest/Introduction.html), [GitHub search "umep"](https://github.com/search?q=umep&type=repositories)
- QGIS roof plugins found: DINFO-UniFI/RoofClassify (GPL-2.0, 10 stars; asbestos roof detection from imagery, not geometry) and Benkat-ux/toit_analyzer_rdc (roof counting, 0 stars) — [GitHub search "qgis plugin roof"](https://github.com/search?q=qgis+plugin+roof&type=repositories)
- Lidar-to-building reconstruction (CLI tools usable alongside QGIS):
  - **3DBAG/roofer**: GPL-3.0, 223 stars, pushed 2026-11-15. It "performs fully automatic LoD2 building reconstruction from a pointcloud and a building roofprint polygon", outputs LoD1.2, 1.3 and 2.2 as CityJSONSequence, and offers "C++ and Python bindings". It is developed by the TU Delft spin-off 3DGI and is used to build the national 3DBAG dataset — [README](https://github.com/3DBAG/roofer)
  - **tudelft3d/City3D**: GPL-3.0, 363 stars, last push 2025-09-03 (LoD2 from airborne lidar) — [GitHub search](https://github.com/search?q=building+reconstruction+lidar+lod2&type=repositories)
  - **geoflow3d/geoflow-bundle**: 100 stars, last push 2026-01-06; it is roofer's predecessor (inference) — [GitHub](https://github.com/geoflow3d/geoflow-bundle)
- Other free lidar and DSM tools:
  - **WhiteboxTools** (jblindsay): MIT, 1,227 stars, pushed 2026-05-26. whitebox-python: MIT, 430 stars — [GitHub](https://github.com/jblindsay/whitebox-tools), [GitHub](https://github.com/opengeos/whitebox-python)
  - **PDAL**: 1,433 stars, pushed 2026-11-11; GitHub reports NOASSERTION (it is BSD per the project; inference) — [GitHub](https://github.com/PDAL/PDAL)
  - **laspy**: 512 stars, pushed 2026-05-30 — [GitHub](https://github.com/laspy/laspy)
  - **Open3D**: 14,211 stars, pushed 2026-11-14; has RANSAC plane segmentation (inference) — [GitHub](https://github.com/isl-org/Open3D)
  - **pyRANSAC-3D**: Apache-2.0, 677 stars, pushed 2026-08-28; it can "fit 3D primitive shapes… Detect planes" — [GitHub](https://github.com/leomariga/pyRANSAC-3D)
  - **CloudCompare**: 4,866 stars, pushed 2026-11-15 — [GitHub](https://github.com/CloudCompare/CloudCompare)
- 3DEP access libraries:
  - **hyriver/seamless-3dep**: MIT, 22 stars, pushed 2026-09-14 ("Streamlined Access to USGS 3DEP Topographic Data") — [README](https://github.com/hyriver/seamless-3dep)
  - **hyriver/py3dep**: 56 stars, last push 2025-06-25 — [GitHub](https://github.com/hyriver/py3dep)
  - **hobuinc/usgs-lidar**: 172 stars, pushed 2026-11-15 ("AWS Entwine Point Tiles USGS LiDAR Public Dataset") — [GitHub](https://github.com/hobuinc/usgs-lidar)
  - **cmspeed/OT_3DEP_Workflows**: GPL-3.0, 10 stars (OpenTopography notebooks) — [GitHub search "3dep"](https://github.com/search?q=3dep&type=repositories)
- Imagery and footprint segmentation: **opengeos/segment-geospatial** (samgeo): MIT, 4,210 stars, pushed 2026-11-09 ("segmenting geospatial data with the Segment Anything Model") — [GitHub](https://github.com/opengeos/segment-geospatial)
- Example roof pipelines (unvetted, 0 stars): Dhruv-Kapri/Rooftop-Solar-Potential (MIT; "per-roof planes, shading and irradiance") and lb789123/RoofPlaneSementation (MIT; "Airborne LiDAR roof plane segmentation based on hierarchical clustering") — [GitHub search](https://github.com/search?q=solar+roof+lidar+python&type=repositories)

### Inferences
- A headless pipeline the agent could run in the container. Every step is free, but I have not tested it here:
  1. Get the 3DEP COPC or EPT tile.
  2. Crop with PDAL (directly, or through `qgis_process run pdal:clip`) to the parcel or footprint.
  3. Make a DSM from first returns.
  4. Run `native:slope` / `native:aspect` (or `gdaldem slope|aspect`) for per-cell pitch and azimuth.
  5. Optionally run roofer with the footprint to get LoD2.2 roof planes, then import the planes into Blender as planar triangles.
  
  roofer is the closest free tool to "fit accurate roof planes" automatically. It is GPL, which is fine internally.
- For pitch, fitting planes to classified building points (RANSAC in Open3D or pyRANSAC-3D, or roofer) is more accurate than averaging slope over DSM pixels. DSM slope is noisy at ridges and edges.

### Gaps
- I did not confirm that the PDAL algorithm IDs (for example `pdal:clip`, `pdal:exportrastertin`) or a DSM algorithm are in the current QGIS LTR. The 3.32 changelog list was truncated in my extract.
- I did not test whether QGIS installs (apt `qgis`, `qgis-plugin-grass`) work in this container, or check the image size.
- I did not verify whether roofer distributes Linux binaries or PyPI wheels, or must be built from source.

---

## 5. Three.js / JavaScript libraries for measurement and display (vanilla ES modules from a CDN)

### Takeaway
All the core libraries are free and permissive: three, three-mesh-bvh, 3d-tiles-renderer, loaders.gl, copc, proj4 and turf are MIT or Apache-2.0, and all are actively maintained in November 2026. Potree is maintained but its license is reported ambiguously. The "measuring tool" repos on GitHub are tiny demos (or LGPL), so it is simpler to build measuring on three-mesh-bvh raycasting.

### Cited Findings
| Library | Version and license (npm) | GitHub stars / last push | Role for roof accuracy | Source |
|---|---|---|---|---|
| three | 0.187.0, MIT | n/a | base renderer | [npm](https://registry.npmjs.org/three/latest) |
| three-mesh-bvh (gkjohnson) | 0.9.18, MIT | 3,574 / 2026-11-13 | "speed up raycasting and enable spatial queries against three.js meshes", for precise click-to-measure and snapping | [GitHub](https://github.com/gkjohnson/three-mesh-bvh), [npm](https://registry.npmjs.org/three-mesh-bvh/latest) |
| 3d-tiles-renderer (NASA-AMMOS) | 0.5.4, Apache-2.0 | 2,527 / 2026-11-11 | "Renderer for 3D Tiles… using three.js" (photogrammetry or tiles context) | [GitHub](https://github.com/NASA-AMMOS/3DTilesRendererJS), [npm](https://registry.npmjs.org/3d-tiles-renderer/latest) |
| loaders.gl (@loaders.gl/las, /core) | 4.5.4, MIT | 860 / 2026-11-16 | LAS/LAZ loading in the browser; the LICENSE says "loaders.gl is licensed under the MIT license" | [GitHub](https://github.com/visgl/loaders.gl), [LICENSE](https://raw.githubusercontent.com/visgl/loaders.gl/HEAD/LICENSE), [npm](https://registry.npmjs.org/@loaders.gl/las/latest) |
| copc (connormanning/copc.js) | 0.0.9, MIT | 65 / 2026-08-10 | reads Cloud-Optimized Point Clouds (3DEP is published as COPC on Planetary Computer) | [GitHub](https://github.com/connormanning/copc.js), [npm](https://registry.npmjs.org/copc/latest) |
| potree | GitHub: NOASSERTION (custom header) | 5,667 / 2026-01-08 | full WebGL viewer for large point clouds, with built-in measuring tools (inference) | [GitHub](https://github.com/potree/potree) |
| potree-core (npm) | 2.0.17, MIT | n/a | Potree point-cloud rendering for three.js as a library | [npm](https://registry.npmjs.org/potree-core/latest) |
| PotreeConverter | BSD-2-Clause | 823 / 2026-11-02 | converts LAS/LAZ to Potree format | [GitHub](https://github.com/potree/PotreeConverter) |
| proj4 (proj4js) | 2.23.0, MIT | 2,245 / 2026-11-13 | transforms WGS84 / UTM 14N / SD State Plane, for metric accuracy | [GitHub](https://github.com/proj4js/proj4js), [npm](https://registry.npmjs.org/proj4/latest) |
| @turf/turf | 7.4.0, MIT | 10,547 / 2026-11-11 | footprint area, buffer, simplify, line length | [GitHub](https://github.com/Turfjs/turf), [npm](https://registry.npmjs.org/@turf/turf/latest) |
| earcut (mapbox) | ISC | 2,630 / 2026-10-23 | polygon triangulation (footprint or roof facet to triangles) | [GitHub](https://github.com/mapbox/earcut) |
| maplibre-gl-usgs-lidar (opengeos) | 0.11.6, MIT | 151 / 2026-11-15 | "searching and visualizing USGS 3DEP LiDAR data from Microsoft Planetary Computer (COPC) and AWS Open Data (EPT)", and can "Export a bounded PDAL pipeline that clips selected EPT datasets to a drawn area and writes LAZ" | [README](https://github.com/opengeos/maplibre-gl-usgs-lidar), [npm](https://registry.npmjs.org/maplibre-gl-usgs-lidar/latest) |
| maplibre-gl-js | GitHub: NOASSERTION (BSD-3, inferred) | 12,097 / 2026-11-15 | 2D map and footprint picking | [GitHub](https://github.com/maplibre/maplibre-gl-js) |
| deck.gl | MIT | 14,761 / 2026-11-15 | alternative point-cloud and geo layer renderer | [GitHub](https://github.com/visgl/deck.gl) |

- Measurement-tool repos are weak: ismailazdad/3dViewMeasurement (LGPL-3.0, 53 stars, last push 2023-10-17, three r143, stale) and LearnMernProjects/ThreeJS-Measure-distances-in-3D-space (1 star; "built for the SurgePV Design Studio's solar panel…"). The others have 0 stars — [GitHub search "threejs measure tool"](https://github.com/search?q=threejs+measure+tool&type=repositories)
- tayden/copc-three-demo (0 stars, last push 2025-02-19) shows COPC loading in Three.js — [GitHub search "three.js copc"](https://github.com/search?q=three.js+copc&type=repositories)
- CesiumGS/3d-tiles-tools: Apache-2.0, 547 stars, pushed 2026-10-20 — [GitHub](https://github.com/CesiumGS/3d-tiles-tools)

### Inferences
- three-mesh-bvh, proj4, turf, earcut and copc all load as plain ES modules from jsDelivr or unpkg (`https://cdn.jsdelivr.net/npm/<pkg>@<exact-version>/+esm`), which fits the no-bundler viewer. loaders.gl is heavier, with workers and many sub-packages. For a CDN-only page, `copc` plus a small LAZ decoder may be simpler. (Untested.)
- maplibre-gl-usgs-lidar ships React components and the viewer uses vanilla JS. Its core plugin may still work without React, but I have not verified this. Even without it, its source is a good reference for the 3DEP STAC/COPC search logic (MIT).
- Accuracy gains in the viewer come mainly from two things: projecting to a metric CRS with proj4 before computing lengths and areas, and raycasting against a BVH to snap to vertices and edges. Choice of renderer matters less.

### Gaps
- Potree's exact license was not resolved. GitHub shows NOASSERTION and the LICENSE header is custom. Check `LICENSE` in full before vendoring it.
- I did not test any of these from a CDN in the studio viewer.
- loaders.gl's GitHub license field reads NOASSERTION, though its LICENSE text says MIT (some sub-modules may carry their own licenses).
