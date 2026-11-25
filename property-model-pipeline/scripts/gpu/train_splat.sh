#!/usr/bin/env bash
# Train an NVIDIA 3DGRUT (3DGUT) splat on the renders of the measured model and export it as PLY.
#
#   train_splat.sh DATASET RUNDIR [--iters 15000] [--config apps/colmap_3dgut.yaml] [--min-psnr 28] [--dry-run]
#
# DATASET   COLMAP text dataset with the TRUE camera poses (images/, sparse/0/{cameras,images,points3D}.txt),
#           as render_demo.py writes it; its world frame is the Blender world (z up, metres).
# RUNDIR    output folder: dataset/ (held-out ordered view), runs/ (3DGRUT), splat.ply, train.json, train.log
#
# The held-out views are placed on 3DGRUT's test slots (compress_splat.py holdout), so the PSNR in train.json
# is measured on views the splat never trained on. Exit 0 = trained and PSNR >= --min-psnr, 3 = trained but
# PSNR below the gate (splat.ply is still written; the job ships without the splat), 1 = failed, 2 = usage.
#
# Env: GRUT_DIR (default /workspace/vh/3dgrut, built by grut_env.sh), TORCH_EXTENSIONS_DIR (default
# /workspace/vh/torch_extensions: the JIT-built CUDA kernels persist between boxes), TRAIN_TIMEOUT seconds
# (default 2400), HELPER_PY (python for compress_splat.py holdout; default python3), DRY_RUN=1.
# The splat is a visual layer only: nothing measured comes from it.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage() { awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"; }

ITERS=15000
CONFIG="apps/colmap_3dgut.yaml"
MIN_PSNR=28
DRY="${DRY_RUN:-0}"
POS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --iters) ITERS="${2:?}"; shift 2 ;;
    --iters=*) ITERS="${1#*=}"; shift ;;
    --config) CONFIG="${2:?}"; shift 2 ;;
    --config=*) CONFIG="${1#*=}"; shift ;;
    --min-psnr) MIN_PSNR="${2:?}"; shift 2 ;;
    --min-psnr=*) MIN_PSNR="${1#*=}"; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "train_splat: unknown option $1" >&2; usage >&2; exit 2 ;;
    *) POS+=("$1"); shift ;;
  esac
done
[ "${#POS[@]}" -eq 2 ] || { usage >&2; exit 2; }
DATASET="${POS[0]}"; RUNDIR="${POS[1]}"
case "$ITERS" in ''|*[!0-9]*) echo "train_splat: --iters must be a whole number" >&2; exit 2 ;; esac

GRUT_DIR="${GRUT_DIR:-/workspace/vh/3dgrut}"
export TORCH_EXTENSIONS_DIR="${TORCH_EXTENSIONS_DIR:-/workspace/vh/torch_extensions}"
TRAIN_TIMEOUT="${TRAIN_TIMEOUT:-2400}"
HELPER_PY="${HELPER_PY:-python3}"
NPROC="$(nproc 2>/dev/null || echo 4)"
export MAX_JOBS="${MAX_JOBS:-$NPROC}"

train_cmd() {   # $1 = test interval k
  TRAIN_CMD=(python train.py --config-name "$CONFIG" "path=$RUNDIR/dataset" "out_dir=$RUNDIR/runs" experiment_name=splat
             "n_iterations=$ITERS" "dataset.test_split_interval=$1" export_ply.enabled=true
             "export_ply.path=$RUNDIR/splat.ply" test_last=true with_gui=false "num_workers=$NPROC")
}

if [ "$DRY" = "1" ]; then
  train_cmd "<k from split.json>"
  echo "PLAN train_splat: $HELPER_PY $HERE/compress_splat.py holdout $DATASET $RUNDIR/dataset"
  echo "PLAN train_splat: cd $GRUT_DIR && source .venv/bin/activate && TORCH_EXTENSIONS_DIR=$TORCH_EXTENSIONS_DIR timeout $TRAIN_TIMEOUT ${TRAIN_CMD[*]}"
  echo "PLAN train_splat: newest runs/**/metrics.json -> $RUNDIR/train.json (gate: mean_psnr >= $MIN_PSNR)"
  exit 0
fi

[ -f "$DATASET/sparse/0/images.txt" ] || { echo "train_splat: no COLMAP text dataset at $DATASET" >&2; exit 1; }
[ -x "$GRUT_DIR/.venv/bin/python" ] || { echo "train_splat: no 3DGRUT venv at $GRUT_DIR/.venv (run grut_env.sh)" >&2; exit 1; }
mkdir -p "$RUNDIR" "$TORCH_EXTENSIONS_DIR"
RUNDIR="$(cd "$RUNDIR" && pwd)"
LOG="$RUNDIR/train.log"

SPLIT_JSON="$("$HELPER_PY" -I "$HERE/compress_splat.py" holdout "$DATASET" "$RUNDIR/dataset")" || {
  echo "train_splat: dataset preparation failed" >&2; exit 1; }
K="$(printf '%s' "$SPLIT_JSON" | "$HELPER_PY" -I -c 'import json,sys; print(json.load(sys.stdin)["k"])')" || exit 1
echo "train_splat: split $SPLIT_JSON"

train_cmd "$K"

T0=$(date +%s)
(
  cd "$GRUT_DIR" || exit 1
  # shellcheck disable=SC1091
  source .venv/bin/activate || exit 1
  echo "train_splat: torch extensions in $TORCH_EXTENSIONS_DIR, MAX_JOBS=$MAX_JOBS"
  timeout "$TRAIN_TIMEOUT" "${TRAIN_CMD[@]}"
) > "$LOG" 2>&1
RC=$?
SECS=$(( $(date +%s) - T0 ))
if [ "$RC" -ne 0 ]; then
  echo "train_splat: 3DGRUT exited $RC after ${SECS}s (timeout ${TRAIN_TIMEOUT}s = 124); last lines of $LOG:" >&2
  tail -n 25 "$LOG" >&2
  exit 1
fi
[ -s "$RUNDIR/splat.ply" ] || { echo "train_splat: no splat.ply was exported" >&2; tail -n 25 "$LOG" >&2; exit 1; }

METRICS="$(find "$RUNDIR/runs" -name metrics.json -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)"
"$HELPER_PY" -I - "$RUNDIR" "$METRICS" "$ITERS" "$SECS" "$CONFIG" "$MIN_PSNR" <<'PY'
import json, os, sys
rundir, metrics, iters, secs, config, min_psnr = sys.argv[1:7]
m = json.load(open(metrics)) if metrics and os.path.isfile(metrics) else {}
split = json.load(open(os.path.join(rundir, "dataset", "split.json")))
psnr = m.get("mean_psnr")
out = {"psnr": round(psnr, 2) if isinstance(psnr, (int, float)) else None,
       "ssim": m.get("mean_ssim"), "lpips": m.get("mean_lpips"), "iterations": int(iters), "seconds": int(secs),
       "config": config, "k": split["k"], "n_views": split["n"], "n_test": split["n_test"],
       "held_out_source": split["held_out_source"], "min_psnr": float(min_psnr),
       "psnr_ok": isinstance(psnr, (int, float)) and psnr >= float(min_psnr),
       "ply_bytes": os.path.getsize(os.path.join(rundir, "splat.ply")),
       "metrics_file": os.path.relpath(metrics, rundir) if metrics else None}
json.dump(out, open(os.path.join(rundir, "train.json"), "w"), indent=1)
print("train_splat:", json.dumps(out))
sys.exit(0 if out["psnr_ok"] else 3)
PY
