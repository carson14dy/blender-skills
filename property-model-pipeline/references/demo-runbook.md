# Address to Roof Layer Studio: the fast demo runbook

One address in, one measured house out: a LiDAR-fitted roof report (area, squares, pitch, edge lengths, all
±1σ), property records, hazard history, a PDF, a studio page and, when a GPU box is approved, 4K renders and
a turntable video. Public online data only: aerial and satellite imagery, city GIS, county parcel and
assessor data, USGS and state LiDAR. No drone or phone photos, no listing sites.

How to read this file:
* Section 4 is the run, stage by stage. `demo_run.py run` chains S0-S9; the commands under each stage are
  what it runs, for when a stage has to be repeated by hand.
* Section 5 is the gate table: what stops a run and what to tell the client at each gate.
* Times and credits in section 3 are estimates from two finished jobs and one GPU benchmark until section 10
  ("Measured so far") is filled in after the first real run.
* "The client" is the person who supplied the address and approves any spend. Messages to the client use the
  wording given here, in plain words, without internal ids.

## 0. The one lesson

On the hillside job (Billings, MT) the roof report was settled about 1.5 h in. The remaining ~34 h changed
only how the model looks, with two exceptions that moved roof numbers:
1. drip edges measured from LiDAR instead of overhang priors: roof area +9.4 %;
2. features the owner knew and nobody could see from above (a chimney chase cut through the roof, a roof
   opening that should have been closed): area +0.45 %, rake and step-flashing lengths up to 15 %.

So the demo tier is everything up to and including the measured drip edges, plus one early question to the
client about what cannot be seen from above. Everything after that is the accuracy tier, and only on request.

## 1. Rules (every stage)

* **Public data only.** No logins, tokens, CAPTCHA or bot-wall workarounds, undocumented backends (permit
  system JSON backends, real-estate site APIs, SharePoint `_api`, vendor imagery keys, hazard tools that need
  a key). A blocked source is written as "not publicly available" and the run moves on.
* **No names.** Never store owner, occupant, taxpayer, buyer, seller or contractor names or mailing
  addresses. Every ArcGIS query names its fields; `outFields=*` is refused in code. Storm-event narratives and
  report remarks are free text and are not stored.
* **The repo is public.** No addresses, house numbers, parcel ids, house coordinates or house slugs in any
  repo file. House data lives in `$S/jobs/<slug>/` (scratch). Tests use synthetic values only.
* No git commit or push unless the user asks.
* Minnehaha County's server rejects curl's default User-Agent: use python `requests` with the toolkit
  User-Agent (`propmodel/0.1 (property measurement toolkit)`). Never pretend to be a browser.
* Negative CLI values use `=`: `--flat-z=-1.5,3.5`.
* Never re-run `pm.py lidar` over a curated job without `--keep-datum`. After any refit, rebuild the whole
  chain (blender, details, site, export, package); a stale `model.blend` is the classic "missing windows" bug.
* Before stopping a workflow or an agent, copy its findings into the job's `notes.md`.
* Renders, videos and diagrams of the measured model may go to Higgsfield (approved by the client). Real
  photos of any kind never do. Upscaled media are labelled "upscaled"; the Blender model and the report stay
  the source of truth. Bundles sent to a GPU box carry a neutral id, no address text and no records files.
* GPU box: start work the moment it is ready, poll with checks no more than 50 s apart, stop it the moment
  the job ends or fails, and verify it is stopped (section 9).
* Test under the strict-CSP server before every publish. Publish the studio only from the complete site
  folder, always to the existing studio URL.

## 2. Tiers

### DEMO tier (the default)
Target: report, studio page and PDF live in 40-50 min (65 with a hard roof); 70-95 min with renders.

Trustworthy (measured, with ±):
* roof planes and pitch from the LiDAR plane fit;
* the roof outline at the drip edge, measured from the outermost on-plane LiDAR returns;
* area, squares, edge lengths by kind (ridge, hip, valley, eave, rake, step flashing, headwall), sigma > 0;
* property records and hazard history straight from the public services, with the query time recorded.

Honest but simple (labelled "assumed"):
* walls = outline minus the measured overhang (or an assumed one, said so);
* storeys from the county class plus the LiDAR eave heights;
* doors and windows marked "assumed" or left out; a garage door only where the city paving shows the drive;
* yard = LiDAR terrain plus city paving, sidewalk and street. No plants, no fences.

Not in the demo tier: photos of any kind, listing sites (`pm.py gather` stays off), review loops, colour
matching. One advisor read of the report, capped at 10 minutes.

Past effort that belongs to the demo tier (now scripted or made a gate):
* local-source discovery for a new city (17 min on the hillside job) -> a region profile, 0 min once written;
* the LiDAR rebuild with footprint mask, ground surface mode on hillsides and `--accept`;
* round-0 review items 1-3 of the hillside job: drip edges and wall lines measured from LiDAR (the +9.4 %);
* sigma from a reduced free set (was typed by hand);
* the parcel, assessor and permit queries (now the records stage);
* one build chain, export, package, CSP test, publish;
* asking the client early for features not visible from above (gate G2, not after 14 rounds).

### ACCURACY tier (only when the client asks)
Hard cap: 3 rounds. Stop when the roof MUST items are clear. Owner facts override LiDAR and photo readings
and are labelled "owner". Parallel agents own disjoint files.

Past effort that belongs here:
* hillside job rounds 1-14 (~24 h): windows, doors, trellis, rails, deck boards, rocks, beds, fences,
  colours, terrain breaklines, photo matching and camera-match zones; none of it moved a roof number;
* the photo hunt and the aerial yard inventory;
* the owner-corrections workflow beyond the two roof items above;
* first Sioux Falls job: the photo catalogue and measurement stage (6.2 of 9.75 agent-hours), details and
  yard authoring, the cosmetic pass, hand-made thumbnails.

## 3. Budget per house (estimates until section 10 is filled)

| Block | Wall-clock | Credits |
|---|---|---|
| S0 intake, S2 fetch + LiDAR | 7 min | 0 |
| S1 records + S1b hazards (parallel to S2) | 3 min (+2 min the first time a year of storm files is downloaded; cached after) | 0 |
| S3 wing spec (the one judgement step) | 10-15 min | 0 |
| S4-S5 drip edges, sigma, report checks, confidence | 8-10 min | 0 |
| S6 build (blender, details, site), thumbnail | 3-5 min | 0 |
| S7 roof diagrams (CPU) | < 1 min | 0 |
| S8-S9 export, package, PDF, CSP smoke test, publish v1 | 7-9 min | 0 |
| **Report + studio page + PDF live** | **40-50 min** (65 with a hard roof) | **0** |
| S10 GPU box: bundle, env reuse, 3 stills at 4K, 240-frame 1080p turntable, ~200 training views, encode | 12-15 min | ~22 |
| S10 3DGRUT splat: train (15k-30k iterations), export, compress | 12-25 min | ~20-40 |
| S11 Topaz 2160p upscale of the 10 s turntable (runs while the splat trains) | 5-15 min | unknown until the first run |
| S12 media publish v2 | 5 min | 0 |
| **Total** | **70-95 min** | **~45-65 box credits + Topaz** |

* The box bills 98 credits per hour, by the second (the approved price; if `gpu_list_gpus` shows a different
  price, ask again).
* One-time: the 3DGRUT build in `/workspace`, about 20-30 billed minutes (~35-50 credits). Rent extra cores for
  that one run only.
* Batch rule: when two or more houses are ready, render them in one box session.
* Without the splat the box time is ~12-15 min (~22 credits).
* No box approved: 3 stills at 4K on CPU (~10 min) plus the diagrams; turntable and splat skipped.
* Running late: drop the splat first (a visual layer only), then Topaz.

## 4. Stages

Notation (scratch paths are examples; nothing house-specific goes into the repo):

```bash
T=<repo>/property-model-pipeline         # this toolkit
S=<scratch dir outside the repo>
export PROPMODEL_CACHE=$S/cache          # every download is cached here; PROPMODEL_OFFLINE=1 = cache only
PM="python3 $T/scripts/pm.py"
J=$S/jobs/<slug>                         # one folder per house (scratch only)
ST=$S/studio_site                        # the COMPLETE studio site folder (scripts/studio/restore_site.md)
```

The one command:

```bash
python3 $T/scripts/demo_run.py new $J --address "<address>" --profile sioux-falls-sd \
    [--label "<card label>"] [--front-az DEG] [--slug SLUG] [--studio-url <existing studio URL>] [--waste PCT] [--latlon LAT,LON]
python3 $T/scripts/demo_run.py run $J --site-dir $ST          # S0-S9 (+ the S10 bundle); stops once at the wing spec (S3)
#   edit $J/spec.json wings, then:
python3 $T/scripts/demo_run.py run $J --site-dir $ST --from fit
python3 $T/scripts/demo_run.py status $J                     # gate table + per-stage timings (run_log.json)
```

* `run` options: `--from STAGE`, `--to STAGE`, `--force STAGE` (re-run that stage; repeatable), `--offline`
  (`PROPMODEL_OFFLINE=1`: cache only, a miss fails fast), `--no-render` (skip the thumbnail and the GPU
  render bundle), `--yes` (accept overridable STOP gates; each override is written into the confidence
  statement).
* Exit codes: 0 done (or `--to` reached), 1 a stage failed, 2 a gate said STOP, 3 the spec needs editing.
* Stages are idempotent: skipped when their outputs exist and their inputs are unchanged since the last run.
* `$J/job.json` holds the per-house config: address, slug, profile, front_az, waste, label, studio_url, skip,
  `ground_mode` (`surface` or `plane` to force the LiDAR ground mode) and `flags` (extra arguments per stage,
  e.g. `{"lidar": ["--thr", "0.1"], "build_site": ["--cell", "0.35"]}`). It lives in scratch with the job.
* `--latlon` is for an address the city address layer does not hold (or for tests); `--studio-url` (or the
  `ROOF_STUDIO_URL` environment variable) is the existing studio artifact the publish call updates.
* The wrapper refuses a job folder inside the repo and searches the repo working tree for the job's address
  tokens before packaging (G8.repo, hard).

Wrapper stage names, in order, and the runbook stage each belongs to:

| Runbook | Wrapper stages |
|---|---|
| S0 | `init` |
| S1, S1b | `records`, `hazards` |
| S2 | `fetch`, `lidar`, `city3d` |
| S3 | `spec`, `fit` |
| S4 | `edges` |
| S5 | `checks` |
| S6 | `blender`, `details`, `site`, `thumb` |
| S7 | `diagrams` |
| S8 | `export`, `package`, `test` |
| S9 | `publish` (writes `publish.json`; the agent sends the Artifact call) |
| S10 | `render` (builds the bundle and prints the MCP sequence; never rents a box itself) |

### S0 intake + region profile (2 min)
* In: the address from the client. Out: `$J/job.json`, `$J/site.json`.
* `demo_run.py new` writes `job.json`. The `init` stage geocodes from the city address-point layer named in
  the profile (exact point, year built, corner lot, county), not from the Census street-centreline point,
  then runs:
  ```bash
  $PM init $J --latlon <lat>,<lon> --address "<address>"
  ```
  Do not pass `--parcel-url` without `--parcel-fields` (the CLI refuses it; the records stage reads the
  parcel anyway).
* Region profile: `references/regions/<name>.json` (schema and the new-city checklist in
  `references/regions/README.md`; check a profile with `python3 -m propmodel.regions --check FILE`).
* New city, no profile: run "A new city or state" in `references/data-sources.md` first (budget +20 min).
  Find the city's ArcGIS host through one of its public web-app items, never by guessing host names. Write
  the profile, check it, then run as normal.
* Gate G0.

### S1 property records (2 min, in parallel with S2; required for every demo house)
```bash
python3 $T/scripts/records.py $J --profile sioux-falls-sd [--offline]
```
* Out: `$J/data/records.json`, `$J/out/sections/40_records.md`, `$J/out/detail_extra/records.json`.
* City layers (Sioux Falls): parcel (lot area, legal description, land use, addition, county, county id),
  address point (year built, occupancy, construction type), footprint attributes (number of stories),
  building permits since 2015 (type, work class, apply / issue / finalize dates, valuation, status).
* County layers, chosen by the parcel's county:
  * Minnehaha: assessed land / building / total value and assessment year, house class and grade, residential
    sales (date, price, year built, condition);
  * Lincoln: parcel value, class and zoning, full and good sales, county permits (outside city limits only).
* Matching, recorded per source in `match`:
  1. the parcel polygon that contains the geocoded point;
  2. other layers by intersection with that polygon (permits: point in parcel);
  3. fallback: the parcel key, and last the address string. A fallback match is flagged in the report.
* Derived: last re-roof permit and roof age ("re-roofed 2019, about 7 years", or "no re-roof permit since
  2015: the roof is at least as old as 2015 or the year built"), permit timeline, year built, storeys / style
  / grade, lot area, land use / zoning, assessed values and year, last sale date and price where public,
  and the `changes_after_lidar` flag for G1.
* Written as "not publicly available": living area, sketch dimensions, roof material (both counties' property
  cards are behind a bot wall; never worked around).
* Gates G1 and G1p.

### S1b hazards and extra data (1-3 min, in parallel; ranking in section 7)
```bash
python3 $T/scripts/hazards.py $J --profile sioux-falls-sd --years 10 [--offline]
python3 $T/scripts/hazards.py $J --profile sioux-falls-sd --only roof      # again after S4: needs the fitted roof
```
* Out: `$J/data/hazards.json`, `$J/out/sections/50_hazards.md`, `$J/out/detail_extra/hazards.json`.
* `--only reports|flood|roof|permits` re-runs one part.
* No hazard result stops a run. A source that fails is written as "source not reachable on <date>", never
  dropped silently and never filled with a guess.

### S2 fetch + LiDAR (5 min)
```bash
$PM fetch $J --footprint-layer https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/5 \
    --footprint-name city --footprint-which roof_outline --footprint-sigma 0.25 \
    --footprint-fields OBJECTID,STRUCTURE,UNITS,NUMBERSTORIES,GROUNDELEVATION,BUILDINGTOPELEVATION,OCCUPIEDDATE,STATUS,CAPTUREMETH \
    --no-ms --no-osm
$PM lidar $J --dataset SD_EasternSD_3_2020 --year 2020 --accept --extra-dims GpsTime
$PM obs $J import-multipatch --profile sioux-falls-sd          # city LOD2 roof, low weight (wrapper stage city3d)
$PM plot $J                                                     # LOOK at $J/overview.png
```
* Hillside (G2.hillside fired): the wrapper runs the LiDAR again on a filtered ground surface, keeping the
  datum (`job.json` `ground_mode` forces `surface` or `plane`). By hand:
  ```bash
  $PM lidar $J --dataset SD_EasternSD_3_2020 --year 2020 --accept --extra-dims GpsTime --keep-datum \
      --ground-mode surface --flat-z=-1.5,3.5
  ```
  Where the city outline traces walls (a planimetric wall-line layer, as on the hillside job), pass it as
  `--footprint-file <json with ring_enu> --footprint-shift dx,dy` so the walls are masked from the ground.
* Out: `data/footprints.json`, `data/ortho.png` (Esri World Imagery = the city's 2026 7.6 cm aerial: checks
  and colour only, never traced), `data/lidar.json` (plane table, density, flight date from GpsTime),
  `data/lod2.json`, `overview.png`.
* Gate G2, then one message to the client while S3 runs (section 5). Do not wait for the answer: fold it in
  if it arrives before S5, else the report says "owner input pending".

### S3 wing spec: the one manual step (10-15 min)
```bash
$PM suggest $J                 # one-wing starting spec.json from the LiDAR planes
#   hand-edit $J/spec.json from the plane table and overview.png (references/model-spec.md)
$PM fit $J
$PM resid $J                   # per-plane residuals -> data/resid.json, resid.png
```
* `suggest` gets hip-vs-gable wrong on cross-gable houses: do not trust it. Typical edits: gable plus cross
  gable, lopsided gables (`eave_height_b`, `eave_overhang_b`), porch roofs (`roof_only: true`).
* Iterate until G3 passes: roof_z RMS <= 0.10 m, no CONFLICT row, every accepted LiDAR plane of 8 m2 or more
  assigned to a wing.
* Time box: 3 fit iterations or 15 min. Not converged: fall back to one measured outline plus per-plane
  facets (the outline-walls path of the hillside job) and tell the client the report is about 30 min later.

### S4 drip edges + accept (5 min; never skipped)
```bash
$PM edges $J --write-obs                                         # outermost on-plane returns per eave / rake
$PM fit $J --accept --use-edges --sigma-free pitches,eave_heights
python3 $T/scripts/hazards.py $J --profile sioux-falls-sd --only roof
```
* `edges` writes `data/edges.json` and outline observations at the measured drip edges; `--use-edges` frees
  the overhangs it measured, with the measurement as the prior; `--sigma-free` gives a non-zero sigma even
  when the spec frees nothing.
* The wrapper keeps the S3 report as `data/report_s3.json` and prints the area change (expect a few %; the
  hillside job was +9.4 %).
* Gate G4. Edges hidden by trees (too few returns) keep the fitted position and are listed in the report.

### S5 report sanity + confidence statement (3 min)
* `report.json` / `report.md` come from `fit --accept`. The `checks` stage compares them with the city LOD2
  area, the outline perimeter and the LiDAR plane table (G5), and writes `$J/out/gates.json`,
  `$J/out/sections/90_confidence.md` and `$J/out/detail_extra/confidence.json`: ± on area, pitch and each edge
  total, where every number came from (LiDAR dataset and flight date, city outline, LOD2 check, permits),
  measured vs assumed lists, and the gate table with any override.
* Gate G5 is the go / no-go for publishing numbers. A STOP is fixed in the spec, never by editing the report.

### S6 model build (3-5 min; the chain is ~12 s once the inputs exist)
```bash
$PM blender $J --glb --plain-ground
python3 $T/scripts/details_stub.py $J [--garage WALL:U:WIDTH]   # only when details.json is missing
python3 $T/scripts/blender/add_details.py $J/out/model.blend $J/details.json $J/out/model_detailed.blend
$PM features $J --profile sioux-falls-sd         # city paving / sidewalks / street, moved by the fitted shift.city
python3 $T/scripts/build_site.py $J $J/features.json $J/site_scene.json --half 30 --cell 0.25
python3 $T/scripts/blender/add_site.py $J/out/model_detailed.blend $J/site_scene.json $J/yard.json $J/out/model_site.blend
python3 $T/scripts/blender/render_thumbnail.py $J/out/model_site.blend $J/out/thumb.jpg --front-az <deg>
```
* `details_stub.py` writes trim, gutters, soffits, a foundation band and colours; no doors or windows.
  `--garage M:-u:4.9` adds one garage door on that wall (u = distance along the wall, m), labelled "assumed
  (no photo)"; use it only where the city paving shows the driveway. Its `caveats` list what the model does
  not show. Nothing it adds changes a measured number.
* `front_az` default: the bearing from the building centroid to the address point; `job.json` overrides.
* Roof colour is sampled from the ortho at the facet centroids (or `hazards.json` `roof_colour`) and labelled
  an estimate.
* Gate G6.

### S7 roof diagrams (< 1 min, CPU, no AI)
```bash
python3 $T/scripts/roof_diagrams.py $J --out $J/out/diagrams [--dpi 300] [--units ft]
```
* Four letter-size pages, SVG + PNG: length (every edge labelled, coloured by kind, per-kind totals), pitch
  (x/12 per facet with a slope arrow), area (ft2 per facet, total in squares), summary (totals, predominant
  pitch, facet count, the waste table, cap / starter / drip edge / valley / step flashing / ice barrier
  lengths, walkable / steep flags, north arrow, "measured from public LiDAR, flown <date>").
* Also writes `diagrams.json` (every total drawn) and `$J/out/sections/20_diagrams.md`.
* Gate G7.

### S8 export, package, PDF, smoke test (6 min)
```bash
python3 $T/scripts/blender/export_studio_glb.py $J/out/model_site.blend $J/out/studio.glb --with-site [--draco] [--roof-rgb '#rrggbb']
python3 $T/scripts/studio/package_house.py $J --site $ST --slug <slug> --label "<label>" --pdf --min-pdf-pages 6 [--note "..."]
python3 $T/scripts/studio/smoke.py --site $ST --house <slug> --job $J --out $J/out/smoke
```
* The exporter drops the lot line, the grade plane, labels and reference objects, and bakes flat colours.
* `package_house.py` writes `houses/<slug>.gltf.json` (embedded base64 buffer: the artifact host serves no
  `.glb`), `houses/<slug>/{detail.json, report.html, report.pdf, drone.jpg, diagrams/*.svg}` and rebuilds
  EVERY card row of `houses/index.json` from `report.json`. `report.html` = `report.md` + every
  `$J/out/sections/NN_*.md` in name order + the diagrams; `detail.json` = the report values + every
  `$J/out/detail_extra/<key>.json` under its key. This drop-folder contract is how records, hazards,
  diagrams and the confidence statement reach the studio without anyone editing the packager.
* By hand, use `--pdf` rather than a separate `report_pdf.py` call: the PDF is then printed from the staged
  page, size- and privacy-checked, linked from `report.html` and listed in the files map. The wrapper's
  `package` stage runs the repo address check and a privacy scan of the drop folders, writes the confidence
  statement, packages, then prints the PDF with `report_pdf.py REPORT.html OUT.pdf --expect <area ft2>
  --min-pages 6` (2 pages when the diagrams are missing); `report_pdf.py` works on any report page on its own.
* `package_house.py` exit codes: 0 ok, 1 input error, 2 size gate, 3 privacy hit, 4 `--verify-site` failed,
  5 PDF failed. Nothing is written into `$ST` unless every gate passes. The files map is printed and written to
  `$J/out/studio_files.json`.
* `smoke.py` serves `$ST` with `csp_server.py` under the artifact host's strict CSP and drives the page with
  node Playwright (desktop and phone). Exit 0 pass, 1 fail, 3 no node / Playwright / Chromium. Screenshots go
  to `--out`, never inside `$ST` (everything in `$ST` is publishable).
* Gate G8.

### S9 publish v1 (2 min, agent step)
* The `publish` stage writes `$J/publish.json`: the exact Artifact call (`url` = the existing studio URL from
  `job.json` `studio_url` or `ROOF_STUDIO_URL`, `file_path` = `$ST/index.html`, `root` = `$ST`, `files` = only
  this house's files + `houses/index.json`, a label). The agent sends it. Without a studio URL the call has no
  `url`: set it first, or the publish would create a new, broken artifact.
* Refused because a file changed since it was read: read the named paths with the Artifact tool, merge, and
  publish again. Never publish to a new URL; never from a folder that failed `package_house.py --verify-site`.
* The studio URL and house slugs live in scratch notes, never in the repo.
* Tell the client (section 5, G9).

### S10 GPU render job (25-40 min; the model is frozen at S9)
```bash
python3 $T/scripts/render_bundle.py $J --out $J/out/render_bundle.zip
```
* The bundle holds the packed `model_site.blend`, `render_job.json` (cameras from the house bbox and
  `front_az`, frame counts, sizes) and the facet points that seed the splat, under a neutral id. It refuses any
  file from `data/` and any text containing the job's address tokens.
* On the box, `scripts/gpu/gpu_job.sh <id>` runs everything (section 9): `scripts/blender/render_demo.py` for
  the stills, the turntable and the training views; ffmpeg; `scripts/gpu/train_splat.sh` and
  `scripts/gpu/compress_splat.py` for the 3DGRUT splat. All state lives in `/workspace/rl`; one status line per
  stage in `logs/<id>.status`; `DONE.marker` or `FAIL.marker` at the end (`SPLAT_SKIPPED` when only the splat
  failed). `DRY_RUN=1` writes the plan and markers without GPU work.
* `render_demo.py BLEND OUTDIR --job render_job.json [--device gpu|cpu] [--only stills,turntable,train] [--dry-run]`
  renders with Cycles:
  * stills `hero_street` (eye height 1.7 m from the front side), `aerial_34`, `top_down` (orthographic, north
    up), 3840x2160, PNG + JPG;
  * turntable: 240 frames at 24 fps, 1920x1080, constant sun; encoded H.264 crf 18 yuv420p;
  * training set: ~200 pinhole views at 1440 px (ground ring, aerial orbit at two heights, nadir grid, 20
    held out) with `cameras.json` and the COLMAP dataset.
* Out: stills, `turntable_1080p.mp4`, `splat.ply` and the compressed web file, `timings.json`, markers.
* CPU fallback (no box): `render_demo.py ... --device cpu --only stills`.
* Gate G10.

### S11 Topaz 4K (5-15 min)
* Only `turntable_1080p.mp4` goes to Topaz:
  `upscale_video {params: {provider: "topaz", video_id: <media id>, resolution: "2160p", aspect_ratio: "auto"}}`.
  The stills are rendered natively at 4K and the diagrams are vector: no upscaler touches them. The splat and
  the training views are not deliverables. Real photos are never sent.
* `python3 $T/scripts/topaz_manifest.py $J/out/media` writes `topaz_manifest.json` (what is sent, why, and
  the not-sent list) and, after the upscale, records the job id, credits, seconds and the 3-frame check.
* The first run ever: ask the client before spending (`upscale_video` has no cost preflight), read `balance`
  before and after, and write the credits and seconds into section 10. After that the cost is known and there
  is no per-house prompt.
* Gate G11.

### S12 media publish v2 (5 min)
```bash
python3 $T/scripts/studio/package_house.py $J --site $ST --slug <slug> --label "<label>" --pdf \
    --media $J/out/media [--video-4k-url <Topaz download URL>]
python3 $T/scripts/studio/smoke.py --site $ST --house <slug> --job $J --out $J/out/smoke_v2
```
* `--media` takes `*.jpg` / `*.webp` stills (4K q88, each < 3 MB), `turntable_1080p.mp4` (target < 12 MB;
  re-encode at crf 23 if larger), the splat web file and `media.json` (labels "rendered from the measured
  model" and "upscaled with Topaz (video only)", and the 4K download URL, also accepted as `video4kUrl` in
  `media.json`). The 4K file itself is a download link, not a studio file (15 MB limit).
* Smoke test again (video loads, splat view loads or is hidden), then publish to the same URL.
* Tell the client (section 5, G12).

## 5. Gates: thresholds, actions and what to tell the client

Every gate is PASS, WARN or STOP and is logged to `$J/out/gates.json`; `demo_run.py status` prints the table.
"Overridable" STOPs are a human decision and can be accepted with `run --yes`; the override goes into the
confidence statement. Hard STOPs (privacy, sigma = 0, an address in the public repo) never can.

| Gate | Check | PASS | WARN | STOP | Tell the client |
|---|---|---|---|---|---|
| G0.address | address points matched | exactly 1 | Census geocode used (no city layer) | 0, or 2+ (overridable with coordinates in `job.json`) | PASS: "Found the house, starting the model." STOP: "I can't find that address in the city's address list. Can you check the spelling, or give the unit?" |
| G0.county | county is one the profile covers | yes | not covered (county layers missing) | | WARN only if records will be missing: "Some county records may be missing for this one." |
| G1.permits | addition / new-construction permit after the LiDAR flight | none | records not available | any (overridable) | "The public LiDAR was flown in <month year>, and the city shows an addition or new-build permit after that, so the scan may not show today's roof. I can (a) measure the roof as flown and flag it, (b) use the city's 2023 roof model for the shape at lower confidence, or (c) skip this address. Which do you want?" |
| G1.year_built | year built vs LiDAR year | before | | year built >= LiDAR year (overridable) | same message as G1.permits |
| G1p privacy | forbidden keys or values in any saved file | none | | any hit: file deleted, run stopped (hard) | nothing (internal); fix the field list first |
| G2.footprint | a building footprint near the address point | found | | none | "The city has no building outline at that address; is it a new build?" |
| G2.density | LiDAR points on the footprint | >= 2 pts/m2 (expect ~5) | | below | "The public LiDAR is too thin at this house to measure the roof reliably." |
| G2.flight | flight date from GpsTime | leaf-off | leaf-on (late spring / summer) or date unknown | | included in the G2 message: "Trees may hide parts of the eaves." |
| G2.hillside | lot slope, grade spread along the eaves | slope <= 8 % and spread <= 1.2 m | above: re-run with `--ground-mode surface` | | nothing |
| G2.shift | city outline to LiDAR shift | within 0.5 m of the profile's expected shift | further than 0.5 m from it | above 1.5 m (wrong building or datum; overridable) | nothing until fixed |
| G2.coverage | accepted planes cover the city outline | >= 85 % | below (tree-hidden corner, or a deck / carport in the outline) | | in the G2 message if it stays: "Part of the roof is hidden by trees in the scan." |
| G2.convention | city outline at the walls or at the drip edge | matches the profile | does not match | | nothing |
| G2.lod2_pitch / lod2_reg | city LOD2 pitch and fit vs LiDAR | within 1/12; sd < 0.15 m | otherwise (roof changed 2020-2023, a dormer) | | ask in the G2 message: "Was anything on the roof changed after 2020?" |
| **G2 message** | sent once, while S3 runs | | | | the overview image + "I found N roof planes in public LiDAR flown <month year>. Anything I can't see from above: a covered entry, a chimney chase, an addition since <year>, the roof material?" |
| G3.roof_rms | LiDAR roof_z RMS | <= 0.10 m | | above | only past the time box: "This roof is more complex than usual; the report will be about 30 minutes later." |
| G3.planes | accepted planes >= 8 m2 assigned to a wing | all | | any unassigned | same |
| G3.outside | plane returns outside the model | <= 5 % | above | | nothing |
| G3.conflict | observations > 3σ from the fit | none | | any | nothing until explained |
| G4.edges | exterior edge length measured from returns | >= 70 % | below (trees): listed in the report | none measured | nothing |
| G4.overhang | fitted overhang per wing | 0.15-1.6 m | outside 0.15-1.6 m | above 2.5 m | nothing |
| G4.sigma | sigma of the area and every edge total | > 0 | | zero (hard) | nothing |
| G4.shift_city | fitted city shift | near the expected shift | further than 0.5 m from it | above 1.5 m (overridable) | nothing |
| G4.city_drip | city outline vs measured drip edge after the shift | RMS <= 0.25 m | above (the LiDAR drip edge wins) | | nothing |
| G5.lod2_area | roof area vs city LOD2 | within 5 % | outside | | nothing (a check, not a second measurement) |
| G5.closure | eaves + rakes vs outline perimeter | within 2 % | outside | | nothing |
| G5.pitch | largest facet vs LiDAR plane | within 0.5/12 | outside | | nothing |
| **G5 go / no-go** | no STOP left | | | | "Roof: <area> ft2 (± <σ>), <squares> squares, mostly <pitch>/12, from public LiDAR flown <month year>. Last re-roof permit: <year or 'none since 2015'>. <warnings in plain words>." |
| G6.mesh | Blender roof mesh area vs report | within 0.5 % | not measured | outside | nothing |
| G8.repo | the repo working tree holds none of this house's identifiers | clean | | any hit (hard) | nothing (internal); remove the file from the repo |
| G7 diagrams | totals drawn vs `report.json` | equal (0.1 ft, 1 ft2), no label overlap | | differ | nothing |
| G8 package / smoke | every file <= 15 MB (warn > 12 MB); no console errors under the strict CSP; studio squares within 1 % of the report and not the demo value (27.4); card rows equal `report.json`; plane count = report facets or explained; PDF >= 6 pages containing the area figure; privacy scan of every packaged text file | all | plane count differs (explained on the page) | anything else | nothing until fixed |
| G9 published | publish accepted | | | | "<link>. Roof <area> ft2, <squares> squares, <pitch>/12; roof age <from permits>; hail: <summary sentence>; <warnings>. Renders and the 4K video follow in about 30 minutes." |
| G10 renders | frames complete, no black frames (mean luminance), splat PSNR on held-out views >= 28 dB, box verified stopped | all | splat below 28 dB: shipped without the splat | box not verified stopped: stop it before anything else | nothing |
| G11 Topaz | 3840x2160, same duration and frame count ± 1, side-by-side check at 3 timestamps (roof edges not bent, no invented texture) | all | | fails: deliver the 1080p file and say so | first run only, before spending: "The 4K upscale of the turntable costs Higgsfield credits; the price shows only after the first run. OK to run it once?" |
| G12 media live | smoke test v2 passes | | | | "<link> now has the renders and the turntable; 4K download: <link>. Credits used: <n>. The stills and diagrams are exact renders of the measured model; the 4K video is upscaled." |

Fix sizes before gating on them: coarsen the terrain (`build_site.py --cell 0.35 --half 26`), then try
`--draco` (the pip bpy here has no Draco library; the exporter then warns and writes an uncompressed file).

## 6. Costly pitfalls and the gate that catches each

| Pitfall (seen on a real job) | Caught by |
|---|---|
| Roof changed after the LiDAR flight | G1 permits / year built; G2 LOD2 pitch |
| Outline traced at the walls, not the drip edge (or the reverse) | G2.convention; G4 (the measured drip edge wins) |
| Overhang priors far below the real eaves (area 8.6 % low) | S4 is mandatory; G4.overhang, G4.area_change |
| Trees over the eaves, leaf-on flight | G2.flight, G2.coverage; G4.edges lists unmeasured edges; tree-overhang figure |
| City layers ~1 m off the LiDAR | G2.shift, G4.shift_city; city features moved by the fitted shift |
| Hillside ground plane (trees and rocks as roof planes, biased pitch) | G2.hillside -> ground surface mode |
| Wrong building, geocode on the street | G0 address point; G2.shift above 1.5 m |
| Owner / taxpayer / contractor names in saved files | `*` refused in code; G1p and G8 scans |
| Records matched to the wrong parcel | match order point -> polygon -> key -> address, recorded and flagged |
| Sigma = 0 (nothing free in the fit) | G4.sigma |
| Stale studio card rows; studio plane count differs from the report | G8 card-vs-report check |
| CSP blocks the model and the page silently falls back to the demo house | G8 smoke test (squares != demo value) |
| Review loop that never ends | the demo tier has no loop; the accuracy tier is capped at 3 rounds |
| Owner facts arriving after 14 rounds | the G2 question to the client |
| Findings lost when a workflow is stopped | rule in section 1 |
| GPU box left running | section 9 stop rules; `auto_pause_minutes: 10` |
| Hail reports read as "hail hit this roof" | fixed wording, "reported near" label (section 7) |
| Partial studio folder published as a new artifact | `package_house.py --verify-site`; publish only to the existing URL |
| An address committed to the public repo | the wrapper's address grep before packaging (hard) |

## 7. Extra data: ranking and sources (checked 2026-11-25 at the city centre, not at a house)

| Item | Rank | Public source | Notes |
|---|---|---|---|
| Hail and wind history at the house | DEMO MUST | NOAA NCEI Storm Events yearly CSV (`ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_details-ftp_v1.0_dYYYY_c*.csv.gz`) | Files through 2026, rebuilt 2026-11-19. BEGIN_LAT / BEGIN_LON, EVENT_TYPE, MAGNITUDE (hail inches, wind knots). ~16 MB per year, cached once. Publication lags a few months. Narratives are not stored. |
| Recent months (gap filler) | DEMO MUST | Iowa Environmental Mesonet local storm reports GeoJSON (`mesonet.agron.iastate.edu/geojson/lsr.geojson?sts=&ets=&wfos=<WFO>`); NOAA SPC daily reports (`spc.noaa.gov/climo/reports/YYMMDD_rpts_hail.csv`) | Preliminary reports, labelled "preliminary". Remarks are not stored. |
| Radar-indicated hail over the house | DEMO SHOULD | NCEI SWDI `swdiws/csv/nx3hail/<start>:<end>?bbox=<w>,<s>,<e>,<n>` (NEXRAD level-3 hail signatures: MAXSIZE, PROB) | Use `bbox`; `center=` did not filter on 2026-11-25. At most 744 h per request. Query only the reported dates ± 1 day. Label "radar-estimated". |
| MRMS MESH hail swaths | LATER | IEM archive `mtarchive.geol.iastate.edu/YYYY/MM/DD/mrms/ncep/MESH_Max_1440min/` | 200 for 2020 and 2024, 404 for 2016. Needs a GRIB reader (not installed). The best per-house hail-size map; add after the demo. |
| FEMA flood zone | DEMO MUST | FEMA NFHL `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query`, outFields FLD_ZONE, ZONE_SUBTY, SFHA_TF, STATIC_BFE, DFIRM_ID | One query on the parcel polygon; report the worst zone touching the parcel. |
| Tree overhang over the roof | DEMO MUST | the LiDAR already fetched | % of roof area with returns >= 0.5 m above the fitted roof, and which edges. The Sioux Falls 3DEP set has no vegetation class and was mostly flown leaf-off, so it reads low: say so. |
| Roof colour | DEMO SHOULD | the ortho already fetched (2026 aerial) | Median colour per facet -> a colour name + hex, "estimate from aerial". Also colours the model. |
| Roof material | LATER | no public field in either county | "Not publicly recorded; re-roof permit <date>". Never guessed as a fact. |
| Roof access / steepness flags | DEMO MUST (free) | derived from the model | Per facet: walkable (<= 6/12), steep (7-9/12), very steep (> 9/12); storeys; highest eave above grade. |
| Material takeoff + waste table | DEMO MUST (exists) | `report.py` suggests the waste from hips and valleys | On the diagram summary page: squares at 0 / 10 / 12 / 15 / 17 / 20 % waste, ridge + hip cap, starter (eaves + rakes), drip edge, valley, step flashing, ice barrier (eaves + valleys). |
| Printable PDF | DEMO MUST | node Playwright print (python Playwright is not installed) | S8. |
| Confidence statement | DEMO MUST | | S5. |
| Nearby re-roof activity | DEMO SHOULD | the city permits layer | Count of re-roof permits within 300 m per year, last 5 years. Counts only, no neighbour addresses. |
| Code edition, ice barrier, snow and wind design values | LATER | no machine-readable public source found; the ASCE hazard tool needs a key | Add a `code_notes` block to the region profile only after someone reads the city's public building-services page and records the URL and the date read. Until then print nothing. |
| Roof age from old aerials | LATER | city historic tiles 1998-2014 (public) | Only for roofs older than the 2015 start of the permit layer. |

Hail summary wording (generated): "Hail of 1.00 in or more reported within 1 mile: <dates and sizes>, last 10
years. Largest within 5 miles: <size>, <date>. Wind of 58 mph or more within 5 miles: <dates>. Events after
the last re-roof permit (<date>): <list>." Distances run from the report point to the parcel centroid. Reports
are spotter points, not a measurement at the house, and the section says so.

## 8. Tool names (who owns what)

| Tool | Owner group |
|---|---|
| `scripts/demo_run.py` (`new`, `run`, `status`), `scripts/details_stub.py`, `scripts/pm.py`, `propmodel/{fusion,lidar,ept,edges,multipatch,features,confidence}.py` | A: wrapper + core |
| `scripts/studio/{package_house,md2html,glb_to_gltf_json,report_pdf,csp_server,smoke}.py`, `report_pdf.js`, `smoke.js`, `print.css`, `restore_site.md`, `site_manifest.json`, `scripts/blender/export_studio_glb.py` | B: studio tools |
| `references/*.md`, `references/regions/*`, `SKILL.md`, repo-root `CLAUDE.md` | C: docs + profiles |
| `scripts/roof_diagrams.py`, `scripts/render_bundle.py`, `scripts/blender/render_demo.py`, `scripts/topaz_manifest.py`, `propmodel/{diagrams,rigs_demo}.py` | D: render + diagrams |
| `scripts/gpu/{gpu_job.sh,grut_env.sh,train_splat.sh,compress_splat.py,higgsfield_cli.sh,MCP_SEQUENCE.md}` | E: GPU job + splat |
| `scripts/records.py`, `scripts/hazards.py`, `propmodel/{records,hazards,regions,privacy,sources}.py` | F: records + hazards + privacy |

Contracts that keep the owners apart:
* `sources.arcgis_footprints(layer_url, lat, lon, radius, cache_dir, out_fields, where="1=1")` and
  `sources.arcgis_parcel(layer_url, lat, lon, cache_dir, out_fields)`: `out_fields` is a required list and `*`
  raises `ValueError`; only the named attributes are kept.
* Drop folders read by the packager: `$J/out/sections/NN_name.md`, `$J/out/detail_extra/<key>.json`,
  `$J/out/diagrams/*.svg`. The packager never needs to know what is in them.
* `python3 -m propmodel.privacy scan DIR` (non-zero exit = hits) and `python3 -m propmodel.regions --check FILE`.
* The wrapper calls the other groups' scripts as subprocesses by path. `virtual-homes/` is read-only for all.

## 9. GPU + Higgsfield sequence (cloud session, Higgsfield MCP tools)

Pre-flight, no credits: `balance`; `gpu_list_gpus` (the RTX PRO 6000 price; 98 credits/h approved, ask again
if it differs); `gpu_my` (no box already running).

1. Container: build `render_bundle.zip`. `media_upload {filename: "render_bundle.zip"}` -> curl PUT ->
   `media_confirm` -> permanent bundle URL. Request the output slots:
   `media_upload {files: [turntable_1080p.mp4, hero_street.jpg, aerial_34.jpg, top_down.jpg, results.zip]}`.
   If the presigned URLs could expire before the job reaches its upload stage, request them at step 5
   instead (the lifetime is measured once, section 10).
2. `gpu_rent {gpu_type: <id from gpu_list_gpus>, kind: "compute", max_credits_per_hour: 98,
   auto_pause_minutes: 10, idempotency_key: <new uuid>}`; `gpu_show_computer` once; poll `gpu_rental` until the
   box is working.
3. At once, `gpu_rental_exec` (timeout_s <= 90): pull or clone the repo branch into `/workspace/rl/code` and
   start the job with nohup:
   ```bash
   mkdir -p /workspace/rl/logs && cd /workspace/rl && (git -C code pull -q || git clone -q -b <branch> <repo url> code) &&
   BUNDLE_URL=... PUT_MP4=... PUT_STILLS=... PUT_RESULTS=... \
     nohup bash code/property-model-pipeline/scripts/gpu/gpu_job.sh <id> > logs/<id>.log 2>&1 &
   ```
   Optional env: `SKIP_SPLAT=1`, `TT_SIZE`.
4. Poll every 50 s or less: `gpu_rental_exec "tail -3 /workspace/rl/logs/<id>.status; ls /workspace/rl/out/<id>/*.marker"`.
   Stop conditions: `DONE.marker`, `FAIL.marker`, no status change for 6 min, or 60 min elapsed.
5. On `encode.marker`: `media_confirm` the MP4 and start Topaz at once (S11) so it runs while the splat trains.
6. On DONE, FAIL or any stop condition: `gpu_rental_stop` FIRST, then read the logs (they are in
   `/workspace`, which survives the stop). Verify: `gpu_rental` shows the box ended and `gpu_my` shows none
   running. Then `media_confirm` the remaining uploads and download `results.zip` into the container.
7. `jobs_wait` (timeout <= 15 s, looped) for the Topaz job; download the result from the job URL; record the
   credits from `transactions` and the balance difference.

Rules: never leave a box running while waiting on anything else; a box that cannot be verified stopped is the
first thing to fix. The one-time 3DGRUT build is cached in `/workspace` (shared by all of the user's boxes).
Batch two or more houses into one box session.

CLI variant (the client's own computer; the CLI signs in through a browser, so it cannot run in a cloud
container): `scripts/gpu/higgsfield_cli.sh <file>` runs `higgsfield upload create <file>` and, only if
`higgsfield model list` shows a video-upscale model, the upscale; otherwise it prints "upload done, run the
upscale from a Claude session". As of 2026-11-25 the npm package (1.2.2) only installs a binary, its README
names `generate create` but no upscale command, and the CLI has no GPU rental commands: the box is MCP only.

Labels on every delivered medium: stills and turntable "rendered from the measured model"; the 4K video
"upscaled with Topaz (video only)"; the splat view "visual layer rendered from the measured model; not used for
measurements". Measurements come only from the report.

## 10. Measured so far (fill in after each real run; replace estimates in section 3)

| Quantity | Value | Measured on | Notes |
|---|---|---|---|
| GPU box price (RTX PRO 6000, compute) | 98 credits/h, billed per second | 2026-11-25 benchmark | 9 min 38 s cost 15.74 credits |
| Blender Cycles on the box, 1440 px | 2.1 s per image | 2026-11-25 benchmark | full resolution 12-26 s per image, limited by the box's 4 CPU cores |
| 3DGRUT one-time build in `/workspace` | not yet measured | | estimate 20-30 billed min; failed on the benchmark box for lack of compiler and CUDA 12.8 tools |
| Box minutes per house (renders only) | not yet measured | | estimate 12-15 min |
| Box minutes per house (with splat) | not yet measured | | estimate 25-40 min |
| Splat: iterations, held-out PSNR, web file size | not yet measured | | start 15k iterations, cap ~400k gaussians, web file <= 11 MB |
| Topaz 2160p, 10 s 1080p turntable: credits | not yet measured | | ask the client before the first run |
| Topaz 2160p: seconds to finish | not yet measured | | |
| Presigned upload URL lifetime (`media_upload`) | not yet measured | | decides whether slots are requested at step 1 or step 5 |
| Artifact serves `.mp4` / `.pdf` / splat files | not yet tested | | fallbacks: image sequence, a download link, base64 in JSON |
| Wall-clock to report + studio page live | not yet measured | | estimate 40-50 min |
| Wall-clock total per house | not yet measured | | estimate 70-95 min |
| Sioux Falls LiDAR density | 5.0 pts/m2 (5.5 on the roof), 0.45 m spacing | first Sioux Falls job | QL2 nominal >= 2 |
| Sioux Falls city-to-LiDAR shift | about (+0.55, -0.80) m | first Sioux Falls job | the profile's expected shift |
| Studio site file count | 42 files (16 JS modules) | 2026-11-25 listing | grows with houses and media |

## 11. Open items (short spikes, in this order)

1. Does the artifact host serve `.mp4`, `.pdf` and a splat file type? If not: base64 in JSON (raw <= 11 MB)
   for the splat, an image sequence for the turntable, the PDF as a download link.
2. A splat viewer under the artifact CSP (workers, WASM): test under `csp_server.py` before training anything.
   If none loads, the splat stays a download and the studio gets no splat view.
3. Presigned upload URL lifetime; box-to-Higgsfield PUT from inside nohup.
4. Topaz credits and duration for a 10 s 1080p clip (first run, with the client's OK).
5. 3DGRUT iterations for PSNR >= 28 dB on a clean synthetic scene (start 15k) and the gaussian cap that keeps
   the web file <= 11 MB (start 400k).
6. Restore the complete studio folder from the artifact before any publish (`scripts/studio/restore_site.md`).
7. Minnehaha parcel-value layer: confirm the layer that serves assessed values for parcels that have not sold
   (the value fields are confirmed on the 2025 sales layer only); otherwise assessed value shows only for
   sold houses.
8. Storm Events lag: read the newest month in the current-year file and start the gap filler from it.
9. City LiDAR (2023) behind a SharePoint share, the permit system backend, MESH GRIB decoding, code-edition
   notes: only with the client's OK, or after the demo; not in the default path.
