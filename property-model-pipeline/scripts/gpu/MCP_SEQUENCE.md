# GPU render job: the cloud-session checklist (Higgsfield MCP tools)

Runbook stages S10 (GPU job), S11 (Topaz) and the media half of S12. The box runs
`scripts/gpu/gpu_job.sh`; this file is what the Claude session does around it. Every step that costs
credits is marked **(credits)**. Nothing here runs on the client's computer; for that, see the CLI note at
the end.

Rules that never bend (CLAUDE.md, "Rented GPUs and paid services"):

* Rent only at the hourly price the client approved (RTX PRO 6000, compute: 98 credits/h). If
  `gpu_list_gpus` shows another price, or extra cores are added, ask again first.
* Start work the moment the box is ready. Poll with checks no more than 50 s apart.
* Stop the box the moment the job ends, fails or stalls, **before** reading logs or doing anything else,
  then verify it is stopped. Never leave a box running while waiting on Topaz, the client, or anything else.
* Renders, videos and diagrams of the measured model may go to Higgsfield; real photos never. The bundle
  carries a neutral id and no address text or records.

## Before renting (no credits)

- [ ] The model is frozen (S9 published). `render_bundle.zip` is built:
      `python3 $T/scripts/render_bundle.py $J --out $J/out/render_bundle.zip`.
- [ ] Pick a neutral job id, e.g. `rj-<6 random hex>` (not the slug; `gpu_job.sh` refuses
      house-number-street ids). Keep the id-to-job mapping in the job's scratch notes only.
- [ ] Optional rehearsal in the container: `DRY_RUN=1 RL_ROOT=$J/out/gpu_dry bash $T/scripts/gpu/gpu_job.sh <id>`
      prints every command the box will run.

## 0. Pre-flight

- [ ] `balance` - note the credits (needed for the Topaz cost on the first run).
- [ ] `gpu_list_gpus` - find `RTX-PRO-6000`; `credits_per_gpu_hour` must be 98 (approved). If not, stop
      and ask the client. Note `high_demand`.
- [ ] `gpu_my {scope: "live"}` - no box already running. If one is, find out why before renting another
      (two live boxes share `/workspace`).

## 1. Uploads the box needs (no credits)

- [ ] Bundle: `media_upload {filename: "render_bundle.zip", content_type: "application/zip"}` -> run the
      returned curl PUT from the container -> `media_confirm {media_id, type: "file"}` -> the permanent URL
      is `BUNDLE_URL`.
- [ ] Output slots, one call:
      `media_upload {files: [{filename: "turntable_1080p.mp4", content_type: "video/mp4"},
      {filename: "hero_street.jpg", content_type: "image/jpeg"}, {filename: "aerial_34.jpg", content_type: "image/jpeg"},
      {filename: "top_down.jpg", content_type: "image/jpeg"}, {filename: "results.zip", content_type: "application/zip"}]}`.
      Keep each `media_id` and `upload_url`. The upload URL is signed for the `content_type` that
      media_upload returns, not the one you asked for: zips come back as `application/octet-stream`
      (measured 2026-11-25; a PUT with `application/zip` gets 403 SignatureDoesNotMatch), which is what
      gpu_job.sh sends for results.zip. URLs lasted 24 h (`expires_in_seconds: 86400`). If the
      returned curl commands carry other `-H` headers, pass them in `PUT_HEADERS` ('|'-separated).
- [ ] Write the slots as JSON for the launcher, keys `turntable.mp4`, `hero_street.jpg`, `aerial_34.jpg`,
      `top_down.jpg`, `results.zip` -> `upload_url`. (Presigned URL lifetime is not yet measured: if
      the MP4 PUT at ~15 min fails with 403, request slots later in the job next time and note it in the
      runbook's "Measured so far" table.)

## 2. Rent **(credits from here on)**

- [ ] `gpu_rent {gpu_type: "RTX-PRO-6000", gpu_count: 1, kind: "compute", max_credits_per_hour: 98,
      auto_pause_minutes: 10, idempotency_key: "<new uuid>"}`. Reuse the same key if the call must be
      repeated. One-time 3DGRUT build only: add `cpu: <cores from gpu_explore>` and set
      `max_credits_per_hour` to the full price the client approved for that box.
- [ ] `gpu_show_computer {session_id}` once.
- [ ] Poll `gpu_rental {session_id}` (no sleeps needed; typical start 15-40 s) until `status: "working"`.

## 3. Start the job at once (one `gpu_rental_exec`, returns in ~10-20 s)

`gpu_rental_exec {session_id, timeout_s: 60, command: ...}` with (fill the `<...>`; the heredoc keeps the
presigned URLs off the process list):

```bash
mkdir -p /workspace/rl/logs /workspace/rl/in/<id> && cd /workspace/rl &&
cat > in/<id>/put.json <<'EOF'
{"turntable.mp4": "<url>", "hero_street.jpg": "<url>", "aerial_34.jpg": "<url>", "top_down.jpg": "<url>", "results.zip": "<url>"}
EOF
if [ -d code/.git ]; then git -C code fetch -q --depth 1 origin <branch> && git -C code reset -q --hard FETCH_HEAD;
else git clone -q --depth 1 -b <branch> <repo url> code; fi && git -C code log --oneline -1 &&
BUNDLE_URL='<bundle url>' PUT_JSON=/workspace/rl/in/<id>/put.json \
  nohup bash code/property-model-pipeline/scripts/gpu/gpu_job.sh <id> > logs/<id>.log 2>&1 < /dev/null &
sleep 8; tail -5 /workspace/rl/logs/<id>.status
```

Options (env, before `nohup`): `SKIP_SPLAT=1` (renders only, ~12-15 min), `TT_SIZE=1280x720`,
`MIN_PSNR=28`, `SPLAT_ITERS=15000`, `SPLAT_CONFIG=apps/colmap_3dgut_mcmc.yaml`.
Repo URL and branch: `git -C <checkout> remote get-url origin` and the working branch. The job refuses a
second copy of itself for the same id, so repeating this exec after an MCP timeout is safe.

## 4. Poll (each call blocks at most ~42 s, then returns)

```bash
cd /workspace/rl; f=logs/<id>.status; s=$(stat -c %s $f 2>/dev/null || echo 0);
timeout 40 bash -c "while [ \"\$(stat -c %s $f 2>/dev/null || echo 0)\" = $s ]; do sleep 2; done";
tail -4 $f; ls out/<id>/*.marker 2>/dev/null; head -6 out/<id>/FAIL.marker 2>/dev/null
```

`gpu_rental_exec {session_id, timeout_s: 55, command: <above>}`. The MCP call times out at 60 s even with
`timeout_s: 90` (seen on the benchmark box), so keep every exec under ~50 s. Never `pkill -f <pattern>`
when the pattern appears in the exec's own command line: it kills the exec itself (exit 143).

Stop conditions (go to step 6 at once):

| Seen | Meaning |
|---|---|
| `DONE.marker` | finished; renders (and the splat unless `SPLAT_SKIPPED.marker`) uploaded in results.zip |
| `FAIL.marker` | `stage=` and `reason=` say what broke; its log tail is in the marker and in results.zip |
| no new status line for 6 min | stalled (stages write a `progress` line every minute while their output grows) |
| 60 min since step 3 (75 min on the one-time 3DGRUT build) | over time |

Status lines look like `2026-11-25T18:00:05Z +312s turntable progress 118 files 20480 KB`.

## 5. On `encode.marker` (the job keeps going; the splat trains meanwhile)

- [ ] `cat out/<id>/encode.marker` in the next poll: `mp4_upload=ok` means the box PUT the master MP4.
- [ ] `media_confirm {media_ids: [<mp4 id>], type: "video"}` and `media_confirm {media_ids: [<still ids>], type: "image"}`
      (only those with `:ok` in `stills_upload`).
- [ ] **(credits, first run needs the client's OK)** The first ever Topaz run: ask the client before
      spending ("The 4K upscale of the turntable costs Higgsfield credits; the price shows only after the
      first run. OK to run it once?"); `balance` right before. After the first run the cost is known and
      no per-house prompt is needed.
- [ ] `upscale_video {params: {provider: "topaz", video_id: <mp4 media id>, resolution: "2160p", aspect_ratio: "auto"}}`
      -> keep the job id. Only the turntable goes to Topaz: stills are native 4K, diagrams are vector.
- [ ] If `mp4_upload=failed`: do not wait; the master MP4 is also inside results.zip. Upload it from the
      container after step 6 (`media_upload` + PUT + `media_confirm`) and start Topaz then.

## 6. Stop first, then everything else

- [ ] `gpu_rental_stop {session_id}` - the first call after DONE, FAIL or a stop condition.
- [ ] Verify: `gpu_rental {session_id}` shows `status: "ended"` (note `credits_spent`) and
      `gpu_my {scope: "live"}` lists no box. If either disagrees, stop again and re-check before anything
      else.
- [ ] `media_confirm {media_ids: [<results.zip id>], type: "file"}` -> URL; download it in the container:
      `curl -fsSL -o $J/out/gpu/<id>/results.zip <url>` and unzip into `$J/out/gpu/<id>/` (renders,
      `timings.json`, `qa.json`, `status.txt`, log tails). Copy `media/*.jpg`, `media/turntable_1080p.mp4`,
      `media/media.json` and the splat (`media/splat.splat.json`, only without `SPLAT_SKIPPED`) to
      `$J/out/media/` for S12. The artifact host refuses `.splat`, `.ply`, `.spz` and `.ksplat` files
      (checked 2026-11-25) but serves `.json`, `.mp4` and `.pdf`, so the splat ships as base64 JSON
      (at most 11 MB, about 258k gaussians).
- [ ] Gate G10: `qa.json` `black` is empty; `encode.json` frames = 240; `timings.json` stages all `ok`;
      splat `train.json` `psnr_ok` true (else ship without the splat); the box is verified stopped.
- [ ] If DONE says `results_upload` is not `ok` (expired URL): new slots (step 1), a short box (step 2),
      then `UPLOAD_ONLY=1 PUT_JSON=... nohup bash .../gpu_job.sh <id> ...` re-sends everything from
      `/workspace` without rendering (about 1-2 min), poll, stop, verify.

## 7. Topaz result (no box running)

- [ ] `jobs_wait {jobs: [{index: 0, job_id: <topaz job>}], timeout_seconds: 15}`; repeat (after
      `poll_after_seconds`) until terminal. Download the result URL in the container.
- [ ] Gate G11: `ffprobe` shows 3840x2160, same duration and frame count +/- 1; compare 3 frames with
      the 1080p source (roof edges straight, no invented texture). If it fails, deliver the 1080p video
      and say so.
- [ ] Record the cost: `transactions {size: 10}` (the Topaz line) and the `balance` difference; box
      `credits_spent`; minutes from `timings.json`. Write them into the runbook's "Measured so far" table.
- [ ] S12: `package_house.py ... --media $J/out/media --video-4k-url <Topaz download URL>`, smoke test,
      publish. Label: stills and turntable "rendered from the measured model"; the 4K file "upscaled with
      Topaz (video only)"; the splat "visual layer rendered from the measured model; not used for
      measurements".

## Batches and the one-time build

* Two or more houses ready together: one box, one exec that chains the jobs
  (`(bash .../gpu_job.sh id1; bash .../gpu_job.sh id2) > logs/batch.log 2>&1 &`, each with its own
  `PUT_JSON`), poll both status files, start each Topaz on its own `encode.marker`, stop after the last
  `DONE` / `FAIL`.
* 3DGRUT is built once into `/workspace/vh/3dgrut` (CUDA 12.8 toolkit inside its venv, kernels in
  `/workspace/vh/torch_extensions`, Pythons in `/workspace/rl/uv/python`). The first build takes about
  20-30 min on 4 cores (about 35-50 credits); rent extra cores for that run only. Later boxes reuse it
  (`grut_env.sh` checks and repairs in about a minute, apt included).
* If `auto_pause_minutes` stops a box mid-job, `/workspace` keeps everything: rent again and re-run the
  step 3 exec; finished stages are skipped and the renderer skips frames that exist.

## Client's own computer (CLI)

`scripts/gpu/higgsfield_cli.sh <render file>` uploads with `higgsfield upload create` and runs the Topaz
upscale only if `higgsfield model list --video` shows a Topaz video model and `--yes` is given; otherwise it
prints "upload done, run the upscale from a Claude session". The CLI signs in through a browser, so it does
not work inside a cloud container, and it has no GPU rental commands: the box is MCP only.
