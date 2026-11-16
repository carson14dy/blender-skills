# Local image to 3D setup (TRELLIS.2 in ComfyUI)

Run `trellis_generate.py --probe` first. It reports what's already installed, so skip the steps you don't need. Downloads are large, so ask the user before starting one, and give the size.

## What it needs
| Item | Needed | Notes |
|---|---|---|
| GPU | NVIDIA with 8 GB of graphics memory | Tested on an RTX 5060 Laptop. Below 8 GB is untested |
| System memory | 32 GB | A run used about 7.5 GB in the ComfyUI process, on top of what was already open |
| Disk | About 13 GB | About 4.5 GB for ComfyUI, 8.5 GB for models, and up to about 25 MB per generated model |
| CPU only | Not practical | A reduced test took about 27 minutes and used 30 of 31 GB of RAM |

## Install
1. **Install ComfyUI** version 0.43.0 or newer. The Windows portable build is on the [ComfyUI releases page](https://github.com/Comfy-Org/ComfyUI/releases). Pick the `nvidia` file, and extract it with 7-Zip to a short path such as `C:\ComfyUI`. No custom nodes are needed.
2. **Download the models** into `ComfyUI/models/`:

| File | Folder | Size | Address |
|---|---|---|---|
| `trellis_2_int8_convrot.safetensors` | `diffusion_models` | 4.9 GB | [download](https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/diffusion_models/trellis_2_int8_convrot.safetensors) |
| `dino_v3_vit_l.safetensors` | `clip_vision` | 1.1 GB | [download](https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/clip_vision/dino_v3_vit_l.safetensors) |
| `trellis_2_shape_vae_bf16.safetensors` | `vae` | 1.0 GB | [download](https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/vae/trellis_2_shape_vae_bf16.safetensors) |
| `trellis_2_texture_vae_bf16.safetensors` | `vae` | 0.9 GB | [download](https://huggingface.co/Comfy-Org/TRELLIS.2/resolve/main/vae/trellis_2_texture_vae_bf16.safetensors) |
| `birefnet.safetensors` | `background_removal` | 0.4 GB | [download](https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors) |

3. **Start ComfyUI** with `run_nvidia_gpu.bat`. It listens on port 8188. The desktop app usually uses port 8000. Either way, the script finds it.
4. **Check it:** `python scripts/trellis_generate.py --probe` should report `"ready":true`.

## Licenses
This isn't legal advice, so check the terms yourself before selling results.
- **TRELLIS.2:** Microsoft publishes the model under MIT.
- **BiRefNet:** the background remover used here is listed as MIT.
- **DINOv3:** Meta's own license has no commercial exclusion or revenue cap, but it has trade-control and end-use limits, such as military uses.
- **nvdiffrast and nvdiffrec:** Microsoft's own TRELLIS.2 code uses these NVIDIA libraries, which are limited to research and evaluation. ComfyUI's native nodes didn't reference them when version 0.43.0 was searched. Check again if you switch to a custom-node version.

## Troubleshooting
| Symptom | Cause | Action |
|---|---|---|
| `"ready":false` with `missing_models` | A file is missing or in the wrong folder | Download it as listed, then restart ComfyUI |
| `missing_nodes` | ComfyUI is too old | Update ComfyUI |
| "ran out of memory" | Other programs hold graphics memory | Ask the user to save and close them, then retry or use `--res 512` |
| An error mentioning HostBuffer | A dynamic memory problem on this GPU | Restart ComfyUI with `--disable-dynamic-vram` |
| "stopped responding" | ComfyUI crashed or was closed | Check its console and restart it |
| Much slower than usual | Graphics memory is full, so data spills to system memory | Close other GPU programs |
