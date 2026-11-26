#!/usr/bin/env bash
# Make (or reuse) the NVIDIA 3DGRUT environment on a rented GPU box; everything that is slow to build is
# cached under /workspace, which persists between boxes (/root, /tmp and system paths do not).
#
#   grut_env.sh [--check] [--dry-run]
#
#   --check    only verify the cached environment (exit 0 ready, 1 not ready); installs nothing
#   --dry-run  print the plan (also DRY_RUN=1)
#
# Steps: apt build-essential git wget (the box has no compiler; CUDA 12.8 nvcc is installed by 3DGRUT's
# own script into the venv), uv via pip, then virtual-homes/gpu/grut_install.sh BY PATH (clone --recursive
# nv-tlabs/3dgrut, FORCE_LOCAL_CUDA=1 CUDA_VERSION=12.8 scripts/create_venv_cuda.sh, install_env_uv.sh;
# Blackwell needs CUDA 12.8), then an import check. Writes $VH_ROOT/grut_ready.json when ready.
#
# Persistence fixes (the first benchmark box showed both):
#   * uv puts managed Pythons in ~/.local/share/uv, which is lost with the box, leaving the cached venv
#     pointing at a missing interpreter. UV_PYTHON_INSTALL_DIR is set under /workspace for new installs,
#     and a venv whose interpreter vanished is repaired by reinstalling that exact Python where it was.
#   * 3DGRUT JIT-compiles its CUDA kernels into TORCH_EXTENSIONS_DIR (default ~/.cache): kept under
#     /workspace so later boxes skip the compile. MAX_JOBS = all cores (rent extra cores for the first build).
#
# Env: VH_ROOT (/workspace/vh), GRUT_DIR ($VH_ROOT/3dgrut), RL_ROOT (/workspace/rl, for the uv and apt
# caches), GRUT_INSTALL (path to grut_install.sh; default from this repo), DRY_RUN=1.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
usage() { awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"; }

CHECK=0
DRY="${DRY_RUN:-0}"
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "grut_env: unknown argument $1" >&2; usage >&2; exit 2 ;;
  esac
done

VH_ROOT="${VH_ROOT:-/workspace/vh}"
GRUT_DIR="${GRUT_DIR:-$VH_ROOT/3dgrut}"
RL_ROOT="${RL_ROOT:-/workspace/rl}"
GRUT_INSTALL="${GRUT_INSTALL:-$REPO/virtual-homes/gpu/grut_install.sh}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$RL_ROOT/uv/python}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$RL_ROOT/uv/cache}"
export TORCH_EXTENSIONS_DIR="${TORCH_EXTENSIONS_DIR:-$VH_ROOT/torch_extensions}"
export MAX_JOBS="${MAX_JOBS:-$(nproc 2>/dev/null || echo 4)}"
export PATH="$HOME/.local/bin:$PATH"
APT_CACHE="$RL_ROOT/apt"
APT_PKGS=(build-essential git wget ca-certificates)
CHECK_PY='import threedgrut, torch; assert torch.cuda.is_available(), "no CUDA device"; print("GRUT_READY torch", torch.__version__, "cuda", torch.version.cuda)'

log() { echo "[grut_env $(date -u +%H:%M:%S)] $*"; }

if [ "$DRY" = "1" ]; then
  echo "PLAN grut_env: apt-get install -y ${APT_PKGS[*]} (archives cached in $APT_CACHE)"
  echo "PLAN grut_env: pip install uv (if missing); UV_PYTHON_INSTALL_DIR=$UV_PYTHON_INSTALL_DIR UV_CACHE_DIR=$UV_CACHE_DIR"
  echo "PLAN grut_env: repair $GRUT_DIR/.venv if its interpreter is missing"
  echo "PLAN grut_env: MAX_JOBS=$MAX_JOBS TORCH_EXTENSIONS_DIR=$TORCH_EXTENSIONS_DIR bash $GRUT_INSTALL"
  echo "PLAN grut_env: $GRUT_DIR/.venv/bin/python -c '$CHECK_PY' -> $VH_ROOT/grut_ready.json"
  exit 0
fi

check_ready() {
  [ -x "$GRUT_DIR/.venv/bin/python" ] && (cd "$GRUT_DIR" && .venv/bin/python -c "$CHECK_PY")
}

# A venv's interpreter lives where uv installed that Python ("home" in pyvenv.cfg). If the box that made it
# is gone, reinstall the same version at the same place, so the packages in the venv work again.
venv_repair() {
  local venv="$1" cfg home ver dir
  cfg="$venv/pyvenv.cfg"
  [ -f "$cfg" ] || return 0
  [ -x "$venv/bin/python" ] && "$venv/bin/python" -c 'pass' 2>/dev/null && return 0
  home="$(sed -n 's/^home *= *//p' "$cfg" | head -1)"
  ver="$(sed -n 's/^version_info *= *//p' "$cfg" | head -1)"
  [ -n "$ver" ] || ver="$(sed -n 's/^version *= *//p' "$cfg" | head -1)"
  [ -n "$home" ] && [ -n "$ver" ] || { log "cannot repair $venv (no home/version in pyvenv.cfg)"; return 1; }
  # home = <install dir>/cpython-<ver>-<platform>/bin
  dir="$(dirname "$(dirname "$home")")"
  log "repairing $venv: Python $ver missing at $home; reinstalling into $dir"
  UV_PYTHON_INSTALL_DIR="$dir" uv python install "$ver" || return 1
  "$venv/bin/python" -c 'pass'
}

if [ "$CHECK" = "1" ]; then
  venv_repair "$GRUT_DIR/.venv" >/dev/null 2>&1 || true
  check_ready; exit $?
fi

mkdir -p "$VH_ROOT" "$UV_PYTHON_INSTALL_DIR" "$UV_CACHE_DIR" "$TORCH_EXTENSIONS_DIR" "$APT_CACHE/partial"
T0=$(date +%s)
log "start: $(nproc) cores, MAX_JOBS=$MAX_JOBS, GRUT_DIR=$GRUT_DIR"

if ! command -v gcc >/dev/null || ! command -v git >/dev/null || ! command -v wget >/dev/null; then
  log "apt: ${APT_PKGS[*]}"
  APT=(-o DPkg::Lock::Timeout=600 -o "Dir::Cache::archives=$APT_CACHE")
  (apt-get "${APT[@]}" update -qq && DEBIAN_FRONTEND=noninteractive apt-get "${APT[@]}" install -y -qq "${APT_PKGS[@]}") \
    || { log "FAIL: apt-get could not install ${APT_PKGS[*]}"; exit 1; }
fi
command -v uv >/dev/null || pip install -q uv || { log "FAIL: no uv"; exit 1; }
log "uv $(uv --version 2>&1 | head -1); gcc $(gcc -dumpversion)"

venv_repair "$GRUT_DIR/.venv" || log "venv repair failed; grut_install.sh will try to rebuild"
if check_ready; then
  log "cached 3DGRUT environment is ready"
else
  [ -f "$GRUT_INSTALL" ] || { log "FAIL: $GRUT_INSTALL not found"; exit 1; }
  log "building 3DGRUT (first time on this /workspace: 20-30 min on 4 cores)"
  bash "$GRUT_INSTALL" || log "grut_install.sh exited $? (checking the result anyway)"
  check_ready || { log "FAIL: 3DGRUT does not import with CUDA after grut_install.sh"; exit 1; }
fi

# The venv must not depend on this box's home directory: record where its interpreter lives.
PYHOME="$(sed -n 's/^home *= *//p' "$GRUT_DIR/.venv/pyvenv.cfg" 2>/dev/null | head -1)"
case "$PYHOME" in
  /workspace/*|"$VH_ROOT"*|"$RL_ROOT"*) PERSIST=true ;;
  *) PERSIST=false; log "note: the venv interpreter is outside /workspace ($PYHOME); the next box repairs it (about 10 s)" ;;
esac
"$GRUT_DIR/.venv/bin/python" - "$VH_ROOT/grut_ready.json" "$(( $(date +%s) - T0 ))" "$PERSIST" "$PYHOME" <<'PY'
import json, os, sys, time
import torch
out, secs, persist, home = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "true", sys.argv[4]
d = {"ready": True, "torch": torch.__version__, "cuda": torch.version.cuda,
     "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
     "seconds_this_run": secs, "cores": os.cpu_count(), "interpreter_home": home,
     "interpreter_persists": persist, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
json.dump(d, open(out, "w"), indent=1)
print("GRUT_READY", json.dumps(d))
PY
