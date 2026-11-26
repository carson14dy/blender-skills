#!/bin/bash
# NVIDIA 3DGRUT environment, cached in /workspace so later boxes skip it.
set -x
W=/workspace/vh; export PATH=$HOME/.local/bin:$PATH; APT="-o DPkg::Lock::Timeout=300"
cd $W
[ -d 3dgrut/.git ] || git clone --recursive https://github.com/nv-tlabs/3dgrut 3dgrut
cd 3dgrut && git submodule update --init --recursive
if [ -x .venv/bin/python ] && .venv/bin/python -c "import threedgrut, torch; assert torch.cuda.is_available()"; then echo GRUT_READY_CACHED; exit 0; fi
command -v wget >/dev/null || (apt-get $APT update -qq && apt-get $APT install -y -qq wget)
DEBIAN_FRONTEND=noninteractive apt-get $APT install -y -qq libgl1-mesa-dev >/dev/null 2>&1 || true
if ! command -v nvcc >/dev/null && [ ! -x /usr/local/cuda/bin/nvcc ]; then
  FORCE_LOCAL_CUDA=1 CUDA_VERSION=12.8 bash scripts/create_venv_cuda.sh 3dgrut
fi
source .venv/bin/activate 2>/dev/null || true
bash install_env_uv.sh 3dgrut
.venv/bin/python -c "import threedgrut, torch; print('GRUT_READY torch', torch.__version__, 'cuda', torch.cuda.is_available())"
