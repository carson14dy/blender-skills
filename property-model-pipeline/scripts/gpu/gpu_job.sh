#!/usr/bin/env bash
# One render job on a rented GPU box, from a clean start: renders of the measured model (4K stills, a
# turntable, splat training views), the MP4, an optional 3DGRUT splat, uploads, timings, a done marker.
#
#   gpu_job.sh ID [--dry-run] [--skip-splat] [--force] [--upload-only]
#
# ID  neutral job id ([a-z0-9_-], 3-48 chars). A house-number-street slug such as "12-elm-st" is refused:
#     bundles and ids sent to the box carry no address text.
#
# Env (set by the session's gpu_rental_exec launcher, see MCP_SEQUENCE.md):
#   BUNDLE_URL   render_bundle.zip (permanent URL from media_upload + media_confirm; file:// works too)
#   PUT_MP4      presigned PUT URL for the turntable MP4 (Topaz input)
#   PUT_STILLS   "hero_street.jpg=URL aerial_34.jpg=URL top_down.jpg=URL" (split on the first '=')
#   PUT_RESULTS  presigned PUT URL for results.zip
#   PUT_JSON     optional file {"turntable.mp4": URL, "hero_street.jpg": URL, ..., "results.zip": URL}
#   PUT_HEADERS  optional extra headers for every PUT, '|'-separated, copied from media_upload's curl
#   SKIP_SPLAT=1 renders only (no 3DGRUT); TT_SIZE=1280x720 (default: render_job.json, 1920x1080)
#   DRY_RUN=1    print the plan and write status lines and markers, no downloads, renders or uploads;
#                DRY_FAIL=<stage> simulates that stage failing (tests: FAIL and SPLAT_SKIPPED paths)
#   Also: RL_ROOT (/workspace/rl), DEVICE (gpu|cpu), MIN_PSNR (28), SPLAT_ITERS (15000), SPLAT_CONFIG
#   (apps/colmap_3dgut.yaml), SPLAT_CAP (400000), SPLAT_MAX_BYTES (11000000), SPLAT_FORMAT (splat.json, the
#   form the artifact host serves; or splat), GRUT_WAIT_MAX (2700 s), RENDER_DEMO, PY_BLENDER, TRAIN_SPLAT, GRUT_ENV, SKIP_ENV=1
#   (tests), RENDER_ARGS (extra render_demo.py flags, e.g. "--max-size 640 --samples 16" for a CPU preview),
#   TT_FRAMES (expected turntable frames; default render_job.json), FPS (render_job.json turntable.fps, else 24), POLL_S (2), FORCE=1 (ignore stage markers), UPLOAD_ONLY=1 (redo the uploads with fresh URLs).
#
# State: all under $RL_ROOT. logs/ID.status gets one line per stage event (start, progress while the
# stage's output grows, ok/fail/skip); per-stage logs in logs/ID/. out/ID/ holds media/, render/, splat/,
# stages/*.ok (resume: a finished stage is skipped on the next run; render_demo.py skips frames that exist),
# timings.json, results.zip and the markers the session polls:
#   encode.marker        the MP4 and stills are encoded and PUT (start Topaz now)
#   SPLAT_SKIPPED.marker the splat failed or missed the PSNR gate; renders still ship
#   DONE.marker          finished (results.zip PUT); stop the box now
#   FAIL.marker          stage=..., reason=..., log tail; stop the box now
# Stage order: bundle, env, grut_env (background), stills, turntable, encode, upload_media, train_views,
# grut_wait, train, compress, results. A splat failure never fails the renders.

# shellcheck disable=SC2329  # stage functions are called through stage() and run_cmd()
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT="$(cd "$HERE/../.." && pwd)"
usage() { awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"; }

ID=""
DRY="${DRY_RUN:-0}"
SKIP_SPLAT="${SKIP_SPLAT:-0}"
FORCE="${FORCE:-0}"
UPLOAD_ONLY="${UPLOAD_ONLY:-0}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --skip-splat) SKIP_SPLAT=1 ;;
    --force) FORCE=1 ;;
    --upload-only) UPLOAD_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "gpu_job: unknown option $1" >&2; usage >&2; exit 2 ;;
    *) [ -z "$ID" ] || { echo "gpu_job: one ID only" >&2; exit 2; }; ID="$1" ;;
  esac
  shift
done
[ -n "$ID" ] || { usage >&2; exit 2; }
if ! [[ "$ID" =~ ^[a-z0-9][a-z0-9_-]{2,47}$ ]]; then
  echo "gpu_job: bad ID '$ID' (use 3-48 of a-z 0-9 _ -)" >&2; exit 2
fi
if [[ "$ID" =~ ^[0-9]+[-_][a-z] ]]; then
  echo "gpu_job: '$ID' looks like a house number and street; use a neutral id" >&2; exit 2
fi
if [ -n "${TT_SIZE:-}" ] && ! [[ "$TT_SIZE" =~ ^[0-9]{3,4}x[0-9]{3,4}$ ]]; then
  echo "gpu_job: TT_SIZE must look like 1920x1080" >&2; exit 2
fi
[ "${DEVICE:-gpu}" = gpu ] || [ "${DEVICE:-gpu}" = cpu ] || { echo "gpu_job: DEVICE is gpu or cpu" >&2; exit 2; }

# ------------------------------------------------------------------------------------------- config
RL_ROOT="${RL_ROOT:-/workspace/rl}"
IN="$RL_ROOT/in/$ID"
OUT="$RL_ROOT/out/$ID"
LOGS="$RL_ROOT/logs"
SLOG="$LOGS/$ID"
STATUS="$LOGS/$ID.status"
STAGES="$OUT/stages"
MEDIA="$OUT/media"
RENDER_OUT="$OUT/render"
PLAN="$OUT/plan.txt"
TIMINGS_TSV="$OUT/timings.tsv"
UPLOADS_TSV="$OUT/uploads.tsv"
GRUT_EXIT="$STAGES/grut_env.exit"
VENV="${VENV:-$RL_ROOT/venv}"
PY_BLENDER="${PY_BLENDER:-$VENV/bin/python}"
RENDER_DEMO="${RENDER_DEMO:-$TOOLKIT/scripts/blender/render_demo.py}"
TRAIN_SPLAT="${TRAIN_SPLAT:-$HERE/train_splat.sh}"
GRUT_ENV="${GRUT_ENV:-$HERE/grut_env.sh}"
COMPRESS="$HERE/compress_splat.py"
DEVICE="${DEVICE:-gpu}"
TT_SIZE="${TT_SIZE:-}"
FPS="${FPS:-}"
MIN_PSNR="${MIN_PSNR:-28}"
SPLAT_ITERS="${SPLAT_ITERS:-15000}"
SPLAT_CONFIG="${SPLAT_CONFIG:-apps/colmap_3dgut.yaml}"
SPLAT_CAP="${SPLAT_CAP:-400000}"
SPLAT_MAX_BYTES="${SPLAT_MAX_BYTES:-11000000}"
SPLAT_FORMAT="${SPLAT_FORMAT:-splat.json}"
GRUT_WAIT_MAX="${GRUT_WAIT_MAX:-2700}"
STUDIO_MP4_MAX="${STUDIO_MP4_MAX:-12000000}"
PROGRESS_EVERY="${PROGRESS_EVERY:-60}"
POLL_S="${POLL_S:-2}"
BPY_VERSION="${BPY_VERSION:-5.3.0}"
BPY_PYTHON="${BPY_PYTHON:-3.13}"
DRY_FAIL="${DRY_FAIL:-}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$RL_ROOT/uv/python}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$RL_ROOT/uv/cache}"
export PATH="$HOME/.local/bin:$PATH"
STILLS=(hero_street aerial_34 top_down)
APT_PKGS=(libxrender1 libxxf86vm1 libxfixes3 libxi6 libxkbcommon0 libsm6 libgl1 libegl1 libglib2.0-0 libx11-6
          libxext6 ffmpeg curl ca-certificates)
APT_SPLAT=(build-essential git wget)
T_START=$(date +%s)
CURRENT=init
SPLAT_STATE=ok
GRUT_PID=""
BLEND=""
JOBJSON=""
DATASET=""
MP4=""
MASTER=""

mkdir -p "$OUT" "$STAGES" "$MEDIA" "$SLOG" "$IN"

# ------------------------------------------------------------------------------------------- helpers
status() {   # status STAGE TEXT
  local el=$(( $(date +%s) - T_START ))
  local line
  line="$(date -u +%Y-%m-%dT%H:%M:%SZ) +${el}s $1 $2"
  echo "$line" >> "$STATUS"
  echo "$line"
}
plan() { echo "PLAN $1: $2" | tee -a "$PLAN"; }
redact() { local u="$1"; [[ "$u" == *\?* ]] && echo "${u%%\?*}?<signature>" || echo "$u"; }
timing() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$TIMINGS_TSV"; }
kv() { printf '%s=%s\n' "$1" "$2"; }

progress_sig() {   # files and bytes under a path (+ a log), cheap enough to run once a minute
  local w="$1" l="$2"
  find "$w" "$l" -type f -printf '%s\n' 2>/dev/null | awk '{n++; s+=$1} END {printf "%d files %d KB", n, s/1024}'
}

run_cmd() {   # run_cmd STAGE WATCH CMD... : background + progress lines while the output grows
  local name="$1" watch="$2"; shift 2
  if [ "$DRY" = "1" ]; then
    plan "$name" "$*"
    if [ "$DRY_FAIL" = "$name" ]; then echo "simulated failure (DRY_FAIL=$name)" > "$SLOG/$name.log"; return 1; fi
    return 0
  fi
  local log="$SLOG/$name.log" last_sig="" last_t now sig pid
  last_t=$(date +%s)
  "$@" > "$log" 2>&1 &
  pid=$!
  STAGE_PID=$pid
  while kill -0 "$pid" 2>/dev/null; do
    sleep "$POLL_S"
    now=$(date +%s)
    if [ $(( now - last_t )) -ge "$PROGRESS_EVERY" ]; then
      sig="$(progress_sig "$watch" "$log")"
      [ "$sig" != "$last_sig" ] && status "$name" "progress $sig"
      last_sig="$sig"; last_t=$now
    fi
  done
  wait "$pid"
  local rc=$?
  STAGE_PID=""
  return "$rc"
}

stage() {   # stage NAME FUNC [always] : skip-if-done, status lines, timing, ok marker
  local name="$1" fn="$2" always="${3:-}"
  CURRENT="$name"
  if [ "$DRY" != "1" ] && [ "$FORCE" != "1" ] && [ -z "$always" ] && [ -f "$STAGES/$name.ok" ]; then
    status "$name" "skip (done in an earlier run)"; timing "$name" skip 0; return 0
  fi
  status "$name" start
  local t0 rc dt
  t0=$(date +%s)
  "$fn"
  rc=$?
  dt=$(( $(date +%s) - t0 ))
  if [ "$rc" -eq 0 ]; then
    status "$name" "ok ${dt}s"; timing "$name" ok "$dt"
    if [ "$DRY" = "1" ]; then : > "$STAGES/$name.dry"; else date -u +%FT%TZ > "$STAGES/$name.ok"; fi
  else
    status "$name" "fail rc=$rc ${dt}s"; timing "$name" fail "$dt"
  fi
  return "$rc"
}

log_tail() { [ -f "$SLOG/$1.log" ] && tail -n "${2:-20}" "$SLOG/$1.log" | cut -c1-300; }

venv_repair() {   # a uv venv whose managed Python vanished with an earlier box: reinstall it in place
  local venv="$1" cfg="$1/pyvenv.cfg" home ver
  [ -f "$cfg" ] || return 0
  "$venv/bin/python" -c 'pass' 2>/dev/null && return 0
  home="$(sed -n 's/^home *= *//p' "$cfg" | head -1)"
  ver="$(sed -n 's/^version_info *= *//p' "$cfg" | head -1)"
  [ -n "$home" ] && [ -n "$ver" ] || return 1
  UV_PYTHON_INSTALL_DIR="$(dirname "$(dirname "$home")")" uv python install "$ver" && "$venv/bin/python" -c 'pass'
}

write_timings() {   # timings.json from timings.tsv + uploads.tsv + the stage json files
  python3 -I - "$OUT" "$ID" "$(( $(date +%s) - T_START ))" "$DRY" "$SPLAT_STATE" <<'PY'
import json, os, sys
out, jid, total, dry, splat = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4] == "1", sys.argv[5]
def rows(name):
    p = os.path.join(out, name)
    return [l.rstrip("\n").split("\t") for l in open(p)] if os.path.isfile(p) else []
def js(*parts):
    p = os.path.join(out, *parts)
    try:
        return json.load(open(p))
    except Exception:
        return None
stages = {}
for r in rows("timings.tsv"):
    if len(r) == 3:
        stages[r[0]] = {"status": r[1], "seconds": int(r[2])}
uploads = {r[0]: {"status": r[1], "http": r[2] if len(r) > 2 else ""} for r in rows("uploads.tsv") if r}
box = {}
if os.path.isfile(os.path.join(out, "box.txt")):
    for l in open(os.path.join(out, "box.txt")):
        if "=" in l:
            k, v = l.rstrip("\n").split("=", 1)
            box[k] = v
earlier = []
hist = os.path.join(out, "history")
for h in sorted(os.listdir(hist)) if os.path.isdir(hist) else []:
    t = js("history", h, "timings.json")
    if t:
        earlier.append({"run": h, "total_seconds": t.get("total_seconds"), "dry_run": t.get("dry_run"),
                        "stages": {k: v.get("seconds") for k, v in (t.get("stages") or {}).items()}})
d = {"id": jid, "dry_run": dry, "total_seconds": total, "splat": splat, "stages": stages, "uploads": uploads,
     "box": box, "encode": js("encode.json"), "qa": js("qa.json"), "train": js("splat", "train.json"),
     "compress": js("splat", "compress.json"), "render": js("render", "timings.json"), "earlier_runs": earlier}
tmp = os.path.join(out, "timings.json.part")
json.dump(d, open(tmp, "w"), indent=1)
os.replace(tmp, os.path.join(out, "timings.json"))
PY
}

put_file() {   # put_file NAME FILE URL CONTENT_TYPE -> uploads.tsv; never fails the job
  local name="$1" file="$2" url="$3" ct="$4" code
  if [ -z "$url" ]; then printf '%s\tskipped\tno-url\n' "$name" >> "$UPLOADS_TSV"; return 0; fi
  if [ "$DRY" = "1" ]; then
    plan upload "curl -X PUT -T $file -H 'Content-Type: $ct' $(redact "$url")"
    printf '%s\tdry\t-\n' "$name" >> "$UPLOADS_TSV"; return 0
  fi
  if [ ! -s "$file" ]; then printf '%s\tfailed\tno-file\n' "$name" >> "$UPLOADS_TSV"; return 0; fi
  local hdr=(-H "Content-Type: $ct")
  if [ -n "${PUT_HEADERS:-}" ]; then
    local h
    IFS='|' read -r -a extra <<< "$PUT_HEADERS"
    for h in "${extra[@]}"; do [ -n "$h" ] && hdr+=(-H "$h"); done
  fi
  code="$(curl -sS -o "$SLOG/put_$name.out" -w '%{http_code}' --retry 3 --retry-delay 5 --retry-all-errors \
          --connect-timeout 20 --max-time 900 -X PUT -T "$file" "${hdr[@]}" "$url" 2>"$SLOG/put_$name.err")"
  if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
    printf '%s\tok\t%s\n' "$name" "$code" >> "$UPLOADS_TSV"
  else
    printf '%s\tfailed\t%s\n' "$name" "${code:-none}" >> "$UPLOADS_TSV"
  fi
}

put_url_for() {   # put_url_for NAME -> URL from PUT_JSON, PUT_STILLS, PUT_MP4 or PUT_RESULTS
  local name="$1" pair
  if [ -n "${PUT_JSON:-}" ] && [ -f "$PUT_JSON" ]; then
    python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2],""))' "$PUT_JSON" "$name" && return 0
  fi
  case "$name" in
    results.zip) echo "${PUT_RESULTS:-}"; return 0 ;;
    *.mp4) echo "${PUT_MP4:-}"; return 0 ;;
  esac
  for pair in ${PUT_STILLS:-}; do
    [ "${pair%%=*}" = "$name" ] && { echo "${pair#*=}"; return 0; }
  done
  echo ""
}

kill_children() {
  [ -n "${STAGE_PID:-}" ] && kill "$STAGE_PID" 2>/dev/null
  [ -n "$GRUT_PID" ] && kill "$GRUT_PID" 2>/dev/null
  pkill -P $$ 2>/dev/null
  return 0
}

fail() {   # fail STAGE REASON : FAIL.marker (+ best-effort results.zip with the logs), then exit 1
  local st="$1" why="$2"
  {
    kv stage "$st"; kv reason "$why"; kv time "$(date -u +%FT%TZ)"; kv elapsed_s "$(( $(date +%s) - T_START ))"
    kv dry_run "$DRY"; echo "--- last lines of logs/$ID/$st.log"; log_tail "$st" 20
  } > "$OUT/FAIL.marker.part"
  status "$st" "FAIL: $why"
  kill_children
  if [ "$st" != "results" ] && [ "$DRY" != "1" ]; then build_results >/dev/null 2>&1 && put_file results.zip "$OUT/results.zip" "$(put_url_for results.zip)" application/octet-stream; fi
  write_timings 2>/dev/null
  mv -f "$OUT/FAIL.marker.part" "$OUT/FAIL.marker"
  status job "FAIL.marker written; stop the box"
  exit 1
}

splat_skip() {   # splat_skip STAGE REASON : the renders still ship
  SPLAT_STATE="skipped"
  { kv stage "$1"; kv reason "$2"; kv time "$(date -u +%FT%TZ)"; kv dry_run "$DRY"; echo "--- last lines"; log_tail "$1" 12; } \
    > "$OUT/SPLAT_SKIPPED.marker"
  status "$1" "SPLAT_SKIPPED: $2"
  [ -n "$GRUT_PID" ] && kill "$GRUT_PID" 2>/dev/null
  return 0
}

on_exit() {
  local rc=$?
  if [ ! -f "$OUT/DONE.marker" ] && [ ! -f "$OUT/FAIL.marker" ] && [ "${LOCKED:-0}" = 1 ]; then
    { kv stage "$CURRENT"; kv reason "exited unexpectedly (rc $rc)"; kv time "$(date -u +%FT%TZ)"; log_tail "$CURRENT" 20; } > "$OUT/FAIL.marker"
    status "$CURRENT" "FAIL: exited unexpectedly (rc $rc)"
  fi
  [ "${LOCKED:-0}" = 1 ] && rm -rf "$OUT/.lock"
}
on_signal() { kill_children; fail "$CURRENT" "stopped by signal $1"; }

# ------------------------------------------------------------------------------------------- stages
st_bundle() {
  if [ "$DRY" = "1" ]; then
    plan bundle "curl -fsSL --retry 3 -o $IN/bundle.zip $(redact "${BUNDLE_URL:-<BUNDLE_URL>}") && python3 -m zipfile -e $IN/bundle.zip $IN/bundle/"
    [ "$DRY_FAIL" = bundle ] && return 1
    BLEND="$IN/bundle/model_site.blend"; JOBJSON="$IN/bundle/render_job.json"; return 0
  fi
  [ -n "${BUNDLE_URL:-}" ] || { echo "BUNDLE_URL is not set" > "$SLOG/bundle.log"; return 1; }
  rm -rf "$IN/bundle" "$IN/bundle.zip.part"
  curl -fsSL --retry 3 --retry-delay 5 --connect-timeout 20 --max-time 900 -o "$IN/bundle.zip.part" "$BUNDLE_URL" \
    > "$SLOG/bundle.log" 2>&1 || return 1
  mv "$IN/bundle.zip.part" "$IN/bundle.zip"
  python3 -I -m zipfile -e "$IN/bundle.zip" "$IN/bundle/" >> "$SLOG/bundle.log" 2>&1 || return 1
  find_bundle || { echo "no .blend or render_job.json in the bundle" >> "$SLOG/bundle.log"; return 1; }
}

find_bundle() {
  BLEND="$(find "$IN/bundle" -name '*.blend' -type f 2>/dev/null | sort | head -1)"
  JOBJSON="$(find "$IN/bundle" -name 'render_job.json' -type f 2>/dev/null | sort | head -1)"
  [ -n "$BLEND" ] && [ -n "$JOBJSON" ]
}

st_env() {
  local need_apt=0 pkgs=("${APT_PKGS[@]}")
  [ "$SKIP_SPLAT" = 1 ] || pkgs+=("${APT_SPLAT[@]}")
  if [ "$DRY" = "1" ]; then
    plan env "nvidia-smi; apt-get install -y ${pkgs[*]} (archives cached in $RL_ROOT/apt); pip install uv"
    plan env "uv venv -p $BPY_PYTHON $VENV && uv pip install bpy==$BPY_VERSION numpy pillow shapely scipy (reused when it imports)"
    [ "$DRY_FAIL" = env ] && return 1
    return 0
  fi
  {
    echo "box: $(nproc) cores, $(python3 --version 2>&1), $(df -h "$RL_ROOT" 2>/dev/null | tail -1 | awk '{print $4" free"}')"
    if [ "${SKIP_ENV:-0}" = 1 ]; then
      echo "SKIP_ENV=1: checking tools only"
      for t in ffmpeg ffprobe curl python3; do command -v "$t" >/dev/null || { echo "missing $t"; return 1; }; done
      "$PY_BLENDER" -c 'import numpy, PIL' || return 1
      kv gpu "none (SKIP_ENV)" > "$OUT/box.txt"; return 0
    fi
    if [ "$DEVICE" = gpu ]; then
      nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || { echo "no GPU visible"; return 1; }
      { kv gpu "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"; kv cores "$(nproc)"; } > "$OUT/box.txt"
    else
      { kv gpu none; kv cores "$(nproc)"; } > "$OUT/box.txt"
    fi
    command -v ffmpeg >/dev/null || need_apt=1
    for lib in libXrender.so.1 libxkbcommon.so.0 libSM.so.6 libEGL.so.1 libXi.so.6; do
      ldconfig -p 2>/dev/null | grep -q "$lib" || need_apt=1
    done
    [ "$SKIP_SPLAT" = 1 ] || command -v gcc >/dev/null || need_apt=1
    if [ "$need_apt" = 1 ]; then
      mkdir -p "$RL_ROOT/apt/partial"
      local apt=(-o DPkg::Lock::Timeout=600 -o "Dir::Cache::archives=$RL_ROOT/apt")
      if ! { apt-get "${apt[@]}" update -qq && DEBIAN_FRONTEND=noninteractive apt-get "${apt[@]}" install -y -qq "${pkgs[@]}"; }; then
        echo "apt-get failed"; return 1
      fi
    fi
    command -v uv >/dev/null || pip install -q uv || { echo "no uv"; return 1; }
    venv_repair "$VENV" || echo "venv repair failed; recreating"
    if ! "$PY_BLENDER" -c 'import bpy, numpy, PIL' 2>/dev/null; then
      [ -x "$VENV/bin/python" ] || uv venv -q -p "$BPY_PYTHON" "$VENV" || { echo "uv venv failed"; return 1; }
      uv pip install -q -p "$VENV/bin/python" "bpy==$BPY_VERSION" numpy pillow shapely scipy || { echo "pip install bpy failed"; return 1; }
    fi
    "$PY_BLENDER" -c 'import bpy; print("bpy", bpy.app.version_string)' || return 1
    kv bpy "$("$PY_BLENDER" -c 'import bpy; print(bpy.app.version_string)' 2>/dev/null | tail -1)" >> "$OUT/box.txt"
  } > "$SLOG/env.log" 2>&1
}

start_grut() {   # 3DGRUT build/check in the background while the renders run
  rm -f "$GRUT_EXIT"
  if [ "$DRY" = "1" ]; then
    plan grut_env "nohup bash $GRUT_ENV > logs/$ID/grut_env.log (background; cached in /workspace/vh)"
    if [ "$DRY_FAIL" = grut_env ]; then echo 1 > "$GRUT_EXIT"; else echo 0 > "$GRUT_EXIT"; fi
    return 0
  fi
  ( RL_ROOT="$RL_ROOT" bash "$GRUT_ENV" > "$SLOG/grut_env.log" 2>&1; echo $? > "$GRUT_EXIT" ) &
  GRUT_PID=$!
  status grut_env "started in the background (pid $GRUT_PID)"
}

render() {   # render STAGE ONLY [extra args]; RENDER_ARGS adds flags for every set (e.g. "--max-size 640 --samples 16")
  local name="$1" only="$2" more=()
  shift 2
  [ -n "${RENDER_ARGS:-}" ] && read -r -a more <<< "$RENDER_ARGS"
  run_cmd "$name" "$RENDER_OUT" "$PY_BLENDER" "$RENDER_DEMO" "$BLEND" "$RENDER_OUT" --job "$JOBJSON" \
    --device "$DEVICE" --only "$only" "$@" "${more[@]}"
}

find_still() {   # find_still NAME EXT
  find "$RENDER_OUT" -type f -name "$1.$2" 2>/dev/null | sort | head -1
}

st_stills() {
  [ "$DRY" = 1 ] || [ -f "$RENDER_DEMO" ] || { echo "render script not found: $RENDER_DEMO" > "$SLOG/stills.log"; return 1; }
  render stills stills || return 1
  [ "$DRY" = 1 ] && return 0
  local n=0 s
  for s in "${STILLS[@]}"; do
    if [ -n "$(find_still "$s" png)$(find_still "$s" jpg)" ]; then n=$((n + 1)); fi
  done
  [ "$n" -gt 0 ] || { echo "no stills found under $RENDER_OUT" >> "$SLOG/stills.log"; return 1; }
  [ "$n" -eq "${#STILLS[@]}" ] || status stills "warning: $n of ${#STILLS[@]} stills"
}

turntable_frames() { find "$RENDER_OUT" -type f -path '*turntable*' -name '*.png' 2>/dev/null | sort; }

job_value() {   # job_value KEY DEFAULT : turntable.frames etc. from render_job.json
  python3 -I - "$JOBJSON" "$1" "$2" <<'PY'
import json, sys
path, key, default = sys.argv[1:4]
try:
    d = json.load(open(path))
except Exception:
    print(default); sys.exit()
for cand in (key.split("."), key.split(".")[::-1]):
    v = d
    for k in cand:
        v = v.get(k) if isinstance(v, dict) else None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        print(int(v)); sys.exit()
print(default)
PY
}

st_turntable() {
  local extra=()
  [ -n "$TT_SIZE" ] && extra=(--tt-size "$TT_SIZE")
  render turntable turntable "${extra[@]}" || return 1
  [ "$DRY" = 1 ] && return 0
  local want got
  want="${TT_FRAMES:-$(job_value turntable.frames 240)}"
  got="$(turntable_frames | wc -l)"
  echo "turntable frames: $got of $want" >> "$SLOG/turntable.log"
  [ "$got" -ge "$want" ] || { echo "only $got of $want turntable frames" >> "$SLOG/turntable.log"; return 1; }
}

encode_mp4() {   # encode_mp4 OUT CRF
  ffmpeg -y -loglevel error -framerate "$FPS" -i "$OUT/work/tt/%05d.png" -c:v libx264 -preset slow -crf "$2" \
    -pix_fmt yuv420p -movflags +faststart -r "$FPS" "$1"
}

st_encode() {
  if [ "$DRY" = "1" ]; then
    plan encode "ffmpeg -framerate $FPS -i <turntable frames> -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart $MEDIA/turntable_1080p.mp4 (crf 23 studio copy if > ${STUDIO_MP4_MAX} bytes)"
    plan encode "stills -> $MEDIA/{hero_street,aerial_34,top_down}.jpg (q88); black-frame check -> qa.json"
    [ "$DRY_FAIL" = encode ] && return 1
    MP4="$MEDIA/turntable_1080p.mp4"; MASTER="$MP4"; return 0
  fi
  {
    mkdir -p "$OUT/work/tt" "$OUT/master"
    rm -f "$OUT/work/tt/"*.png
    local i=0 f h w
    while IFS= read -r f; do i=$((i + 1)); ln -s "$f" "$(printf '%s/work/tt/%05d.png' "$OUT" "$i")"; done < <(turntable_frames)
    [ "$i" -gt 0 ] || { echo "no turntable frames"; return 1; }
    IFS=x read -r w h < <(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$OUT/work/tt/00001.png")
    [ -n "$w" ] && [ -n "$h" ] || { echo "cannot read the frame size"; return 1; }
    MP4="$MEDIA/turntable_${h}p.mp4"
    rm -f "$MEDIA"/turntable_*.mp4 "$OUT/master/"*.mp4
    encode_mp4 "$MP4" 18 || { echo "ffmpeg failed"; return 1; }
    MASTER="$MP4"
    if [ "$(stat -c %s "$MP4")" -gt "$STUDIO_MP4_MAX" ]; then
      MASTER="$OUT/master/turntable_${h}p_crf18.mp4"
      mv "$MP4" "$MASTER"
      encode_mp4 "$MP4" 23 || { echo "ffmpeg (studio copy) failed"; return 1; }
      echo "studio copy at crf 23: $(stat -c %s "$MP4") bytes; master (Topaz input) $(stat -c %s "$MASTER") bytes"
    fi
    local frames
    frames="$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$MASTER")"
    [ "$frames" = "$i" ] || { echo "MP4 has $frames frames, expected $i"; return 1; }
    printf '{"mp4": "%s", "master": "%s", "frames": %s, "fps": %s, "width": %s, "height": %s, "seconds": %s, "bytes": %s, "master_bytes": %s}\n' \
      "$(basename "$MP4")" "$(basename "$MASTER")" "$frames" "$FPS" "$w" "$h" "$(awk "BEGIN{print $frames/$FPS}")" \
      "$(stat -c %s "$MP4")" "$(stat -c %s "$MASTER")" > "$OUT/encode.json"
    local s src
    for s in "${STILLS[@]}"; do
      src="$(find_still "$s" jpg)"
      if [ -n "$src" ]; then cp -f "$src" "$MEDIA/$s.jpg"; continue; fi
      src="$(find_still "$s" png)"
      [ -n "$src" ] && "$PY_BLENDER" -c 'import sys; from PIL import Image; Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], quality=88)' "$src" "$MEDIA/$s.jpg"
    done
    "$PY_BLENDER" - "$OUT/qa.json" "$MEDIA" "$OUT/work/tt" <<'PY'
import glob, json, os, sys
import numpy as np
from PIL import Image
out, media, tt = sys.argv[1:4]
def lum(p):
    im = Image.open(p).convert("L")
    im.thumbnail((256, 256))
    return float(np.asarray(im, dtype=np.float32).mean() / 255.0)
frames = sorted(glob.glob(os.path.join(tt, "*.png")))
sample = frames[::10] + frames[-1:]
res = {"stills": {os.path.basename(p): round(lum(p), 4) for p in sorted(glob.glob(os.path.join(media, "*.jpg")))},
       "frames_checked": len(sample), "frame_lum_min": round(min(lum(p) for p in sample), 4) if sample else None}
dark = [k for k, v in res["stills"].items() if v < 0.02] + (["turntable"] if sample and res["frame_lum_min"] < 0.02 else [])
res["black"] = dark
json.dump(res, open(out, "w"), indent=1)
print("qa", json.dumps(res))
sys.exit(1 if dark else 0)
PY
  } > "$SLOG/encode.log" 2>&1
}

st_upload_media() {
  [ "$DRY" = 1 ] || [ -n "$MP4" ] || { MP4="$(find "$MEDIA" -name 'turntable_*.mp4' | head -1)"; MASTER="$(find "$OUT/master" -name '*.mp4' 2>/dev/null | head -1)"; MASTER="${MASTER:-$MP4}"; }
  : > "$STAGES/uploads_media.tsv"
  UPLOADS_TSV_SAVE="$UPLOADS_TSV"; UPLOADS_TSV="$STAGES/uploads_media.tsv"
  put_file turntable.mp4 "$MASTER" "$(put_url_for turntable.mp4)" video/mp4
  local s
  for s in "${STILLS[@]}"; do
    [ "$DRY" = 1 ] || [ -f "$MEDIA/$s.jpg" ] || continue
    put_file "$s.jpg" "$MEDIA/$s.jpg" "$(put_url_for "$s.jpg")" image/jpeg
  done
  UPLOADS_TSV="$UPLOADS_TSV_SAVE"
  cat "$STAGES/uploads_media.tsv" >> "$UPLOADS_TSV"
  local mp4_state
  mp4_state="$(awk -F'\t' '$1=="turntable.mp4"{print $2}' "$STAGES/uploads_media.tsv")"
  {
    kv mp4 "$(basename "${MASTER:-turntable_1080p.mp4}")"; kv mp4_upload "${mp4_state:-none}"
    kv stills_upload "$(awk -F'\t' '$1!="turntable.mp4"{print $1":"$2}' "$STAGES/uploads_media.tsv" | paste -sd, -)"
    [ -f "$OUT/encode.json" ] && kv encode "$(cat "$OUT/encode.json")"
    kv time "$(date -u +%FT%TZ)"; kv dry_run "$DRY"
  } > "$OUT/encode.marker.part"
  mv -f "$OUT/encode.marker.part" "$OUT/encode.marker"
  [ "$DRY" = 1 ] || cp -f "$OUT/encode.marker" "$STAGES/encode.marker"
  status upload_media "encode.marker written (mp4 upload: ${mp4_state:-none}); start Topaz now"
  return 0
}

st_train_views() {
  render train_views train || return 1
  [ "$DRY" = 1 ] && { DATASET="$RENDER_OUT/train/colmap"; return 0; }
  find_dataset || { echo "no COLMAP dataset (sparse/0/images.txt) under $RENDER_OUT" >> "$SLOG/train_views.log"; return 1; }
}

find_dataset() {
  local f
  f="$(find "$RENDER_OUT" -type f -path '*/sparse/0/images.txt' 2>/dev/null | sort | head -1)"
  [ -n "$f" ] || return 1
  DATASET="$(dirname "$(dirname "$(dirname "$f")")")"
}

wait_grut() {   # wait for the background grut_env.sh (exit code in GRUT_EXIT)
  local t0
  t0=$(date +%s)
  while [ ! -f "$GRUT_EXIT" ]; do
    [ $(( $(date +%s) - t0 )) -lt "$GRUT_WAIT_MAX" ] || { echo "3DGRUT environment not ready after ${GRUT_WAIT_MAX}s"; return 1; }
    sleep "$POLL_S"
  done
  local rc
  rc="$(cat "$GRUT_EXIT")"
  echo "grut_env.sh exit $rc"
  [ "$rc" = 0 ]
}

st_grut_wait() {
  if [ "$DRY" = 1 ]; then
    plan grut_wait "wait for $GRUT_EXIT (max ${GRUT_WAIT_MAX}s)"
    [ "$(cat "$GRUT_EXIT" 2>/dev/null)" = 0 ]; return $?
  fi
  [ -f "$GRUT_EXIT" ] || [ -n "$GRUT_PID" ] || start_grut
  run_cmd grut_wait "$SLOG/grut_env.log" wait_grut
}

st_train() {
  [ -n "$DATASET" ] || find_dataset || [ "$DRY" = 1 ] || { echo "no dataset" > "$SLOG/train.log"; return 1; }
  if [ "$DRY" = 1 ]; then
    plan train "bash $TRAIN_SPLAT ${DATASET:-<dataset>} $OUT/splat --iters $SPLAT_ITERS --config $SPLAT_CONFIG --min-psnr $MIN_PSNR"
    [ "$DRY_FAIL" = train ] && { echo "simulated failure (DRY_FAIL=train)" > "$SLOG/train.log"; return 1; }
    return 0
  fi
  mkdir -p "$OUT/splat"
  RL_ROOT="$RL_ROOT" run_cmd train "$OUT/splat" bash "$TRAIN_SPLAT" "$DATASET" "$OUT/splat" --iters "$SPLAT_ITERS" \
    --config "$SPLAT_CONFIG" --min-psnr "$MIN_PSNR"
}

st_compress() {
  local ext="$SPLAT_FORMAT" crop=()
  [ -n "$DATASET" ] || find_dataset || true
  [ -n "$DATASET" ] && [ -f "$DATASET/sparse/0/points3D.txt" ] && crop=(--crop-points "$DATASET/sparse/0/points3D.txt")
  rm -f "$MEDIA"/splat.*
  run_cmd compress "$OUT/splat" "$PY_BLENDER" "$COMPRESS" compress "$OUT/splat/splat.ply" "$MEDIA/splat.$ext" \
    --max-gaussians "$SPLAT_CAP" --max-bytes "$SPLAT_MAX_BYTES" --format "$SPLAT_FORMAT" "${crop[@]}" \
    --meta "$OUT/splat/compress.json"
}

splat_done() { [ "$DRY" != 1 ] && [ "$FORCE" != 1 ] && [ -f "$STAGES/train.ok" ] && [ -f "$STAGES/compress.ok" ]; }

splat_pipeline() {
  local rc
  if splat_done; then
    for s in train_views grut_wait train compress; do status "$s" "skip (done in an earlier run)"; timing "$s" skip 0; done
    return 0
  fi
  stage train_views st_train_views || { splat_skip train_views "training views did not render"; return 0; }
  stage grut_wait st_grut_wait always || { splat_skip grut_wait "3DGRUT environment not ready (see logs/$ID/grut_env.log)"; return 0; }
  stage train st_train
  rc=$?
  if [ "$rc" -eq 3 ]; then splat_skip train "held-out PSNR below $MIN_PSNR dB (see splat/train.json)"; return 0; fi
  [ "$rc" -eq 0 ] || { splat_skip train "3DGRUT training failed (rc $rc)"; return 0; }
  stage compress st_compress || { splat_skip compress "web splat could not be written within the size cap"; return 0; }
}

write_media_json() {
  python3 -I - "$MEDIA/media.json" "$OUT" "$SPLAT_STATE" <<'PY'
import json, os, sys
path, out, splat = sys.argv[1:4]
def js(*p):
    try:
        return json.load(open(os.path.join(out, *p)))
    except Exception:
        return None
d = {"captions": {"hero_street": "Street view (rendered)", "aerial_34": "Aerial 3/4 view (rendered)",
                  "top_down": "Top-down view (rendered)"},
     "labels": {"stills": "rendered from the measured model", "video": "rendered from the measured model",
                "splat": "visual layer rendered from the measured model; not used for measurements"},
     "turntable": js("encode.json"), "splat": {"state": splat, "train": js("splat", "train.json"),
                                               "compress": js("splat", "compress.json")},
     "generated_by": "scripts/gpu/gpu_job.sh"}
json.dump(d, open(path, "w"), indent=1)
PY
}

build_results() {   # results.zip: media, timings, markers, log tails (no blend, no training views, no PLY)
  write_timings
  [ -d "$MEDIA" ] && write_media_json
  python3 -I - "$OUT" "$LOGS" "$ID" <<'PY'
import glob, os, sys, zipfile
out, logs, jid = sys.argv[1:4]
tmp = os.path.join(out, "results.zip.part")
up = {}
if os.path.isfile(os.path.join(out, "uploads.tsv")):
    for l in open(os.path.join(out, "uploads.tsv")):
        r = l.rstrip("\n").split("\t")
        up[r[0]] = r[1] if len(r) > 1 else ""
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(glob.glob(os.path.join(out, "media", "*"))):
        z.write(p, "media/" + os.path.basename(p), compress_type=zipfile.ZIP_STORED if p.endswith((".mp4", ".jpg")) else zipfile.ZIP_DEFLATED)
    if up.get("turntable.mp4") != "ok":               # Topaz never got the master: ship it here
        for p in glob.glob(os.path.join(out, "master", "*.mp4")):
            z.write(p, "master/" + os.path.basename(p), compress_type=zipfile.ZIP_STORED)
    for name in ("timings.json", "qa.json", "encode.json", "encode.marker", "SPLAT_SKIPPED.marker", "FAIL.marker.part",
                 "render/timings.json", "render/plan.json",
                 "uploads.tsv", "plan.txt", "box.txt", "splat/train.json", "splat/compress.json", "splat/dataset/split.json"):
        p = os.path.join(out, name)
        if os.path.isfile(p):
            z.write(p, name.replace(".part", ""))
    st = os.path.join(logs, jid + ".status")
    if os.path.isfile(st):
        z.write(st, "status.txt")
    tails = [(p, "logs/" + os.path.basename(p)) for p in sorted(glob.glob(os.path.join(logs, jid, "*.log")))]
    tails.append((os.path.join(out, "splat", "train.log"), "logs/3dgrut_train.log"))
    for p, arc in tails:
        if os.path.isfile(p):
            lines = open(p, errors="replace").read().splitlines()[-200:]
            z.writestr(arc, "\n".join(lines) + "\n")
os.replace(tmp, os.path.join(out, "results.zip"))
PY
}

st_results() {
  if [ "$DRY" = 1 ]; then
    plan results "zip media/, timings.json, qa.json, markers, log tails -> $OUT/results.zip"
    put_file results.zip "$OUT/results.zip" "$(put_url_for results.zip)" application/octet-stream
    [ "$DRY_FAIL" = results ] && return 1
    return 0
  fi
  build_results > "$SLOG/results.log" 2>&1 || return 1
  put_file results.zip "$OUT/results.zip" "$(put_url_for results.zip)" application/octet-stream
}

# ------------------------------------------------------------------------------------------- main
LOCKED=0
if ! mkdir "$OUT/.lock" 2>/dev/null; then
  owner="$(cat "$OUT/.lock/owner" 2>/dev/null)"
  boot="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || hostname)"
  if [ "${owner%% *}" = "$boot" ] && kill -0 "${owner##* }" 2>/dev/null; then
    echo "gpu_job: $ID is already running here (pid ${owner##* }); not starting a second copy"
    exit 0
  fi
  rm -rf "$OUT/.lock"; mkdir "$OUT/.lock" || { echo "gpu_job: cannot take the lock" >&2; exit 1; }
fi
LOCKED=1
echo "$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || hostname) $$" > "$OUT/.lock/owner"
trap on_exit EXIT
trap 'on_signal TERM' TERM
trap 'on_signal INT' INT

# a new run starts clean: old terminal markers move to history/, so a poll never reads a stale DONE or FAIL
HIST="$OUT/history/$(date -u +%Y%m%dT%H%M%SZ)"
for m in DONE.marker FAIL.marker SPLAT_SKIPPED.marker encode.marker timings.json results.zip uploads.tsv timings.tsv plan.txt; do
  [ -e "$OUT/$m" ] && { mkdir -p "$HIST"; mv -f "$OUT/$m" "$HIST/"; }
done
rm -f "$STAGES"/*.dry
status job "start id=$ID dry_run=$DRY skip_splat=$SKIP_SPLAT upload_only=$UPLOAD_ONLY device=$DEVICE pid=$$"
[ "$DRY" = 1 ] && plan job "RL_ROOT=$RL_ROOT render=$RENDER_DEMO python=$PY_BLENDER"

if [ "$UPLOAD_ONLY" = 1 ]; then
  [ -d "$MEDIA" ] && [ -n "$(ls -A "$MEDIA" 2>/dev/null)" ] || fail upload_media "UPLOAD_ONLY=1 but $MEDIA is empty"
  FPS="${FPS:-24}"
  stage upload_media st_upload_media always
  stage results st_results always || fail results "results.zip could not be built"
else
  stage bundle st_bundle || fail bundle "bundle download or unpack failed${BUNDLE_URL:+ ($(redact "$BUNDLE_URL"))}"
  [ "$DRY" = 1 ] || [ -n "$BLEND" ] || find_bundle || fail bundle "bundle has no .blend or render_job.json"
  [ -n "$FPS" ] || FPS="$(job_value turntable.fps 24)"
  stage env st_env always || fail env "environment setup failed (apt, uv or bpy)"
  if [ "$SKIP_SPLAT" != 1 ] && ! splat_done; then start_grut; fi
  stage stills st_stills || fail stills "4K stills did not render"
  stage turntable st_turntable || fail turntable "turntable frames incomplete"
  stage encode st_encode || fail encode "MP4 encode, still conversion or black-frame check failed"
  stage upload_media st_upload_media || true
  [ -f "$OUT/encode.marker" ] || cp -f "$STAGES/encode.marker" "$OUT/encode.marker" 2>/dev/null   # resumed run
  if [ "$SKIP_SPLAT" = 1 ]; then splat_skip splat "SKIP_SPLAT=1 (renders only)"; else splat_pipeline; fi
  stage results st_results always || fail results "results.zip could not be built"
fi

write_timings
failed_up="$(awk -F'\t' '$2=="failed"{print $1}' "$UPLOADS_TSV" 2>/dev/null | paste -sd, -)"
{
  kv status "done"; kv id "$ID"; kv splat "$SPLAT_STATE"; kv uploads_failed "${failed_up:-none}"
  kv results_upload "$(awk -F'\t' '$1=="results.zip"{s=$2} END{print s}' "$UPLOADS_TSV" 2>/dev/null)"
  kv total_s "$(( $(date +%s) - T_START ))"; kv time "$(date -u +%FT%TZ)"; kv dry_run "$DRY"
} > "$OUT/DONE.marker.part"
mv -f "$OUT/DONE.marker.part" "$OUT/DONE.marker"
status job "DONE.marker written (splat ${SPLAT_STATE}, failed uploads: ${failed_up:-none}); stop the box"
exit 0
