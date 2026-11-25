#!/bin/bash
# vhomes GPU benchmark (Higgsfield RTX PRO 6000). Every stage is stamped in logs/bench.log; logs/bench.done marks the end.
W=/workspace/vh; mkdir -p $W/logs; LOG=$W/logs/bench.log; T0=$(date +%s)
st(){ echo "[$(( $(date +%s) - T0 ))s] $*" | tee -a $LOG; }
APT="-o DPkg::Lock::Timeout=300"
st "box: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader) | cpus $(nproc) | $(python3 --version 2>&1) | $(df -h /workspace | tail -1 | awk '{print $4" free"}')"
export PATH=$HOME/.local/bin:$PATH
command -v uv >/dev/null || { pip install -q uv >>$LOG 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh >>$LOG 2>&1; }
export PATH=$HOME/.local/bin:$PATH
st "uv: $(uv --version 2>&1)"
( bash $W/code/virtual-homes/gpu/grut_install.sh > $W/logs/grut_install.log 2>&1; echo "exit $?" > $W/logs/grut_install.done ) &
if [ ! -x $W/venv/bin/python ]; then uv venv -q -p 3.13 $W/venv >>$LOG 2>&1 && uv pip install -q -p $W/venv/bin/python bpy==5.3.0 numpy shapely pillow >>$LOG 2>&1; fi
st "bpy venv ready"
if ! $W/venv/bin/python -c "import bpy" >>$LOG 2>&1; then
  st "installing system libraries for bpy"
  (apt-get $APT update -qq && DEBIAN_FRONTEND=noninteractive apt-get $APT install -y -qq libxrender1 libxxf86vm1 libxfixes3 libxi6 libxkbcommon0 libsm6 libgl1 libegl1 libglib2.0-0 libx11-6 libxext6) >>$LOG 2>&1
fi
$W/venv/bin/python -c "import bpy; print('bpy', bpy.app.version_string)" >>$LOG 2>&1 || { st "FAIL: bpy does not import"; echo FAIL > $W/logs/bench.done; exit 1; }
st "bpy imports"
cd $W/code/virtual-homes
st "A: house_001, all rigs, 1440 px, 128 spp"
$W/venv/bin/python scripts/make_house.py --seed 1 --out $W/out_1440 --long-side 1440 --samples 128 --device gpu > $W/logs/A.log 2>&1 \
  || { st "FAIL A"; tail -30 $W/logs/A.log >> $LOG; echo FAIL > $W/logs/bench.done; exit 1; }
st "A done: $(tail -1 $W/logs/A.log)"
st "B: house_001, 8 per rig, full device resolution, 128 spp"
$W/venv/bin/python scripts/make_house.py --seed 1 --out $W/out_full --samples 128 --device gpu --max-per-rig 8 > $W/logs/B.log 2>&1 \
  || { st "FAIL B"; tail -30 $W/logs/B.log >> $LOG; }
st "B done: $(tail -1 $W/logs/B.log)"
$W/venv/bin/python scripts/export_colmap.py $W/out_1440/house_001 >> $LOG 2>&1
st "COLMAP export done"
echo RENDER_DONE > $W/logs/bench.done
