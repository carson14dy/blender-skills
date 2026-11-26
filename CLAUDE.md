# Project rules

This repository is public. These rules apply to every session and every agent working in it, mostly around
`property-model-pipeline/` (measured house models from public data). The demo procedure is in
`property-model-pipeline/references/demo-runbook.md`; data sources in
`property-model-pipeline/references/data-sources.md`.

## Data

- Public data only: aerial and satellite imagery, city GIS, county parcel and assessor services, USGS and
  state LiDAR, national hazard services. No logins, no access tokens, no CAPTCHA or bot-wall
  workarounds, no undocumented or private APIs (real-estate site APIs, permit-system JSON backends,
  SharePoint `_api` listings, vendor imagery keys). A blocked source is reported as "not publicly available"
  and left alone: no browser User-Agent, no alternate host, no retry loop.
- Every ArcGIS query names its fields. `outFields=*` is refused in code (`ValueError`); do not add a code path
  that sends it.
- Region profiles (`property-model-pipeline/references/regions/*.json`) hold endpoints and field lists only.
  Check one with `python3 -m propmodel.regions --check FILE` before use.

## Privacy

- Never write owner, occupant, resident, taxpayer, buyer, seller or contractor names, or mailing addresses,
  anywhere: not in job files, notes, reports, studio pages, commits, test fixtures or messages. Request only
  the fields you need; if a response still carries a name, delete it.
- Do not store free-text remarks from public records (storm narratives, permit descriptions naming people).
- The repo is public, so house data stays in scratch: no street addresses, house numbers, parcel ids,
  house-specific coordinates, house slugs, studio URLs or job folders in any file under this repo. Tests use
  synthetic places and values only.
- Real photos (listing, owner, street-level, inspection) never leave the job folder and never go to a
  third-party service.

## Code, tests and git

- No `git commit` or `git push` unless the user asks for it in this session. Before any commit: the test suite
  passes on a fresh run and the diff has no address tokens.
- Negative CLI values use `=`: `--flat-z=-1.5,3.5`, not `--flat-z -1.5,3.5`.
- After any refit, rebuild the whole chain (fit, blender, details, site, export, package). A partial rebuild
  leaves a stale model.
- Never re-run `pm.py lidar` over a curated job without `--keep-datum`.
- Never hand-edit a number in a report; fix the input and refit.

## Parallel agents and workflows

- Parallel agents get disjoint file ownership: no file has two owners in one run. Agents call each other's
  scripts by path instead of editing them.
- Before stopping a workflow or an agent, save its findings (into the job's `notes.md` or the scratch notes).
- Review loops are capped: the demo tier has none; the accuracy tier stops after 3 rounds or when the roof
  items are clear. Facts from the property owner override LiDAR and photo readings.

## Rented GPUs and paid services

- Rent a GPU box only at an hourly price the user approved; if the listed price differs, ask again. Set
  `max_credits_per_hour` to that price and keep `auto_pause_minutes` short (10).
- Start the work the moment the box is ready. Poll with checks no more than 50 s apart. Stop the box the
  moment the job ends, fails or stalls (no progress for 6 min, or past its time limit), before reading logs or
  doing anything else, then verify it is stopped (`gpu_rental` ended, `gpu_my` shows none running).
- Batch several houses into one box session when they are ready together.
- Before the first run of a paid tool with no cost preview (for example a video upscale), ask the user, then
  record the credits and time it took in the runbook's "Measured so far" table.
- Renders, videos and diagrams of the measured model may be sent to Higgsfield. Real photos never. Bundles sent
  to a box carry a neutral id and no address text or records.
- Upscaled or AI-processed media are labelled as such; the measured Blender model and the report stay the
  source of truth, and no measurement is ever taken from an upscaled or generated image.

## Publishing the studio

- Test every studio change under the strict-CSP server (`scripts/studio/smoke.py`, which runs
  `scripts/studio/csp_server.py`) before every publish.
- Publish only from the complete site folder (`package_house.py --verify-site` passes), always to the existing
  studio URL, never as a new artifact. If a publish is refused because a file changed, read the named files,
  merge, and publish again.
- Every studio file stays under 15 MB.
