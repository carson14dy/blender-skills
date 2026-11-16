#!/usr/bin/env python3
"""Turn one photo into a textured GLB on this PC with TRELLIS.2 in a local ComfyUI. It's free, and the photo stays here.

Host-side (system Python 3.9+, no bpy, no third-party packages). It only talks to ComfyUI on 127.0.0.1,
using ComfyUI's own TRELLIS.2 nodes, so no custom nodes are needed. A job can take several minutes, so run
it in the background. ComfyUI keeps a copy of the photo in its input folder and of the GLB in its output folder.
Usage:
  python trellis_generate.py --probe [--port 8188]
  python trellis_generate.py --image photo.jpg --out model.glb [--res 1024|512] [--faces 200000] [--tex 2048]
      [--seed 42] [--port 8188] [--timeout 1800] [--keep-loaded] [--force]
Without --port it uses COMFYUI_PORT, then tries 8188 and 8000. --keep-loaded leaves the models in graphics
memory afterwards, and --force overwrites --out. Prints one JSON object. Exit code: 0 ok, 1 failed.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOST = "127.0.0.1"
DEFAULT_PORTS = (8188, 8000)
IMAGE_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MIN_VRAM_GB = 7.5
POLL_SECONDS = 2.0
# How long a job may be missing from both the queue and the history before it counts as lost
LOST_AFTER_SECONDS = 15.0
SETUP = "See image-to-3d-local-setup.md for the install steps."
HF = "https://huggingface.co/Comfy-Org"
# node, input, file, models subfolder, download address
MODELS = [
    ("UNETLoader", "unet_name", "trellis_2_int8_convrot.safetensors", "diffusion_models",
     f"{HF}/TRELLIS.2/resolve/main/diffusion_models/trellis_2_int8_convrot.safetensors"),
    ("CLIPVisionLoader", "clip_name", "dino_v3_vit_l.safetensors", "clip_vision",
     f"{HF}/TRELLIS.2/resolve/main/clip_vision/dino_v3_vit_l.safetensors"),
    ("VAELoader", "vae_name", "trellis_2_shape_vae_bf16.safetensors", "vae",
     f"{HF}/TRELLIS.2/resolve/main/vae/trellis_2_shape_vae_bf16.safetensors"),
    ("VAELoader", "vae_name", "trellis_2_texture_vae_bf16.safetensors", "vae",
     f"{HF}/TRELLIS.2/resolve/main/vae/trellis_2_texture_vae_bf16.safetensors"),
    ("LoadBackgroundRemovalModel", "bg_removal_name", "birefnet.safetensors", "background_removal",
     f"{HF}/BiRefNet/resolve/main/background_removal/birefnet.safetensors"),
]
_OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({})).open  # never route local traffic via a proxy


class GenError(Exception):
    pass


class ServerDown(GenError):
    pass


def _request(port, path, data=None, headers=None, timeout=60):
    """Return (status, body bytes). Raise ServerDown if ComfyUI can't be reached."""
    req = urllib.request.Request(f"http://{HOST}:{port}{path}", data=data, headers=headers or {})
    try:
        with _OPEN(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except OSError as e:
        raise ServerDown(f"can't reach ComfyUI on port {port}: {e}") from None


def _json(port, path, data=None, timeout=60):
    headers = {}
    if data is not None:
        data, headers = json.dumps(data).encode(), {"Content-Type": "application/json"}
    status, body = _request(port, path, data, headers, timeout)
    try:
        return status, json.loads(body or b"null")
    except ValueError:
        raise GenError(f"ComfyUI sent a reply to {path} that wasn't JSON (HTTP {status})") from None


def _stats(port):
    """The server's status, or None if nothing answers or it isn't ComfyUI."""
    try:
        status, data = _json(port, "/system_stats", timeout=5)
    except GenError:
        return None
    return data if status == 200 and isinstance(data, dict) and "system" in data else None


def find_server(port=None):
    """Return (port, stats). An explicit port is the only one tried."""
    if port is None and os.environ.get("COMFYUI_PORT"):
        try:
            port = int(os.environ["COMFYUI_PORT"])
        except ValueError:
            raise GenError("COMFYUI_PORT must be a number") from None
    tried = (port,) if port else DEFAULT_PORTS
    for candidate in tried:
        stats = _stats(candidate)
        if stats:
            return candidate, stats
    raise ServerDown(f"ComfyUI isn't running on port {' or '.join(map(str, tried))}. Start it, or pass --port. {SETUP}")


def _options(info, node, field):
    spec = ((info.get(node) or {}).get("input") or {}).get("required", {}).get(field) or [[]]
    if isinstance(spec[0], list):
        return spec[0]
    return (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}).get("options", [])


def find_models(info):
    """Return ({file: name ComfyUI knows it by}, [missing models]). Files may sit in a subfolder."""
    found, missing = {}, []
    for node, field, name, folder, url in MODELS:
        match = [o for o in _options(info, node, field) if str(o).replace("\\", "/").rsplit("/", 1)[-1] == name]
        if match:
            found[name] = match[0]
        else:
            missing.append({"file": name, "folder": f"models/{folder}", "url": url})
    return found, missing


def build_graph(image, models, res, faces, tex, seed, prefix):
    """The ComfyUI job for one photo. Settings were measured on an 8 GB GPU."""
    def n(cls, **inputs):
        return {"class_type": cls, "inputs": inputs}

    def sampler(seed_, steps, cfg, scheduler, model, pos, neg, latent):
        return n("KSampler", seed=seed_, steps=steps, cfg=cfg, sampler_name="euler", scheduler=scheduler, denoise=1.0,
                 model=model, positive=pos, negative=neg, latent_image=latent)

    remesh = 768 if res == 1024 else 512
    g = {
        "1": n("LoadImage", image=image),
        "2": n("LoadBackgroundRemovalModel", bg_removal_name=models["birefnet.safetensors"]),
        "3": n("RemoveBackground", bg_removal_model=["2", 0], image=["1", 0]),
        "4": n("ImageCropToMask", images=["1", 0], masks=["3", 0], width=1024, height=1024, pad_factor=1.0,
               grow_mask=0, background="#000000"),
        "5": n("CLIPVisionLoader", clip_name=models["dino_v3_vit_l.safetensors"]),
        "6": n("Trellis2Conditioning", clip_vision_model=["5", 0], image=["4", 0]),
        "7": n("UNETLoader", unet_name=models["trellis_2_int8_convrot.safetensors"], weight_dtype="default"),
        "8": n("VAELoader", vae_name=models["trellis_2_shape_vae_bf16.safetensors"]),
        "9": n("VAELoader", vae_name=models["trellis_2_texture_vae_bf16.safetensors"]),
        "10": n("CFGOverride", model=["7", 0], cfg=1.0, start_percent=0.667, end_percent=1.0),
        "11": n("RescaleCFG", model=["10", 0], multiplier=0.7),
        "12": n("ModelSamplingSD3", model=["11", 0], shift=5.0),
        "13": n("EmptyTrellis2LatentStructure", batch_size=1),
        "14": sampler(seed + 14, 12, 7.5, "normal", ["12", 0], ["6", 0], ["6", 1], ["13", 0]),
        "15": n("VaeDecodeStructureTrellis2", samples=["14", 0], vae=["8", 0], resolution="32"),
        "16": n("Trellis2ShapeStage", positive=["6", 0], negative=["6", 1], voxel=["15", 0]),
        "17": n("CFGOverride", model=["7", 0], cfg=1.0, start_percent=0.769, end_percent=1.0),
        "18": n("RescaleCFG", model=["17", 0], multiplier=0.5),
        "19": sampler(seed, 20, 7.5, "normal", ["18", 0], ["16", 0], ["16", 1], ["16", 2]),
    }
    shape, pos, neg = ["19", 0], ["16", 0], ["16", 1]
    if res == 1024:
        g["20"] = n("Trellis2UpsampleStage", positive=["16", 0], negative=["16", 1], shape_latent=["19", 0],
                    vae=["8", 0], target_resolution=res)
        g["21"] = sampler(seed, 12, 7.5, "simple", ["18", 0], ["20", 0], ["20", 1], ["20", 2])
        shape, pos, neg = ["21", 0], ["20", 0], ["20", 1]
    g.update({
        "22": n("VaeDecodeShapeTrellis", samples=shape, vae=["8", 0]),
        "23": n("Trellis2TextureStage", positive=pos, negative=neg, shape_latent=shape),
        "24": sampler(seed + 1, 12, 1.0, "normal", ["7", 0], ["23", 0], ["23", 1], ["23", 2]),
        "25": n("VaeDecodeTextureTrellis", samples=["24", 0], vae=["9", 0], shape_subdivides=["22", 1]),
        "26": n("RemeshMesh", **{"mesh": ["22", 0], "resolution": remesh, "sign_mode": "solid", "sign_mode.fill": 20.0,
                                 "sign_mode.qef": False, "band": 1.0, "project_back": 0.0, "fix_poles": False,
                                 "smooth_iters": 20, "drop_small_components": 0.01, "precluster_max_verts": 20000000}),
        "27": n("DecimateMesh", mesh=["26", 0], target_face_count=faces, placement_mode="midpoint"),
        "28": n("MeshSmoothNormals", mesh=["27", 0], crease_angle=180.0),
        "29": n("UnwrapMesh", mesh=["28", 0], segmenter="pec", resolution=tex, padding=1, weld_distance=0.0002),
        "30": n("BakeTextureFromVoxel", mesh=["29", 0], voxel_colors=["25", 0], texture_size=tex, reference_mesh=["22", 0]),
        "31": n("BakeNormalMapFromMesh", low_poly=["29", 0], high_poly=["26", 0], resolution=tex, cage_distance=0.05,
                ignore_backfaces=True),
        "32": n("BakeAmbientOcclusion", low_poly=["29", 0], high_poly=["26", 0], resolution=min(tex, 1024), samples=64,
                max_distance=0.71, strength=1.0, bias=0.01),
        "33": n("ApplyTextureToMesh", mesh=["29", 0], base_color=["30", 0], metallic=["30", 1], roughness=["30", 2],
                occlusion=["32", 0], normal_map=["31", 0]),
        "34": n("MeshSmoothNormals", mesh=["33", 0], crease_angle=180.0),
        "35": n("SaveGLB", mesh=["34", 0], filename_prefix=f"3d/{prefix}"),
    })
    return g


def required_nodes():
    names = {m[2]: "x" for m in MODELS}
    return sorted({v["class_type"] for v in build_graph("x", names, 1024, 1000, 512, 0, "x").values()})


def _device(stats):
    devices = stats.get("devices") or []
    return devices[0] if devices else {}


def _hardware_warning(stats):
    """ComfyUI's free-memory figure ignores other programs, so judge only by what the GPU has."""
    device = _device(stats)
    if str(device.get("type", "")).lower() == "cpu" or not device:
        return "No GPU was found. On the CPU, a reduced test took 27 minutes and nearly all of 32 GB of RAM."
    if device.get("vram_total", 0) / 2**30 < MIN_VRAM_GB:
        return "This GPU has less than the 8 GB this was tested on, and a run peaks near 7.7 GB. It may be slow or fail."
    return None


def probe(port=None, **_):
    port, stats = find_server(port)
    status, info = _json(port, "/object_info", timeout=60)
    if status != 200 or not isinstance(info, dict):
        raise GenError(f"ComfyUI's /object_info returned HTTP {status}")
    missing_nodes = [c for c in required_nodes() if c not in info]
    _, missing_models = find_models(info)
    device = _device(stats)
    warnings = [w for w in [_hardware_warning(stats)] if w]
    ready = not missing_nodes and not missing_models
    result = {"ok": True, "ready": ready, "port": port, "comfyui_version": stats["system"].get("comfyui_version"),
              "gpu": device.get("name"), "vram_total_gb": round(device.get("vram_total", 0) / 2**30, 1),
              "missing_nodes": missing_nodes,
              "missing_models": missing_models, "warnings": warnings}
    if missing_nodes:
        result["fix"] = f"Update ComfyUI, because it's missing TRELLIS.2 nodes. {SETUP}"
    elif missing_models:
        result["fix"] = f"Download each missing model into the listed folder, then restart ComfyUI. {SETUP}"
    return result


def _upload(port, path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXT:
        raise GenError(f"{path}: use {', '.join(sorted(IMAGE_EXT))}")
    size = os.path.getsize(path)
    if not 0 < size <= MAX_IMAGE_BYTES:
        raise GenError(f"{path}: the image is empty or larger than {MAX_IMAGE_BYTES // 2**20} MB")
    with open(path, "rb") as f:
        raw = f.read()
    name = f"bas_{hashlib.sha256(raw).hexdigest()[:16]}{ext}"  # never replaces a file of the user's
    boundary = uuid.uuid4().hex
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
            f"Content-Type: {IMAGE_EXT[ext]}\r\n\r\n").encode()
    status, body = _request(port, "/upload/image", head + raw + f"\r\n--{boundary}--\r\n".encode(),
                            {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)
    if status != 200:
        raise GenError(f"ComfyUI refused the image (HTTP {status}): {body[:300].decode('utf-8', 'replace')}")
    data = json.loads(body)
    return f"{data['subfolder']}/{data['name']}" if data.get("subfolder") else data["name"]


def _failure_reason(entry):
    for kind, data in (entry.get("status") or {}).get("messages") or []:
        if kind == "execution_error":
            text = f"{data.get('exception_type', 'Error')}: {data.get('exception_message', '')}".strip()
            where = data.get("node_type", "a node")
            low = text.lower()
            if any(k in low for k in ("out of memory", "outofmemory", "hostbuffer", "allocation")):
                return (f"{where} ran out of memory ({text[:200]}). Close other GPU programs and retry, or use "
                        "--res 512. If it mentions HostBuffer, restart ComfyUI with --disable-dynamic-vram")
            return f"{where} failed: {text[:400]}"
    return "ComfyUI reported an error without details. Check its console"


def _wait(port, prompt_id, timeout):
    deadline, last_seen, down = time.time() + timeout, time.time(), 0
    while time.time() < deadline:
        try:
            _, hist = _json(port, f"/history/{prompt_id}")
            down = 0
        except ServerDown:
            down += 1
            if down >= 3:
                raise ServerDown("ComfyUI stopped responding during the job. It may have run out of memory or "
                                 "been closed. Check its console, close other GPU programs, then retry") from None
            time.sleep(POLL_SECONDS)
            continue
        entry = hist.get(prompt_id) if isinstance(hist, dict) else None
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise GenError(_failure_reason(entry))
            if status.get("completed", True):
                return entry
        _, queue = _json(port, "/queue")
        queued = [item[1] for key in ("queue_running", "queue_pending") for item in (queue or {}).get(key, [])]
        if prompt_id in queued:
            last_seen = time.time()
        elif time.time() - last_seen > LOST_AFTER_SECONDS:
            raise GenError("the job left ComfyUI's queue without a result. Someone may have cancelled it")
        time.sleep(POLL_SECONDS)
    for path, body in (("/interrupt", {"prompt_id": prompt_id}), ("/queue", {"delete": [prompt_id]})):
        _json(port, path, body)
    raise GenError(f"no result after {timeout} s, so the job was cancelled. Check for other work on the GPU, "
                   "or raise --timeout")


def _save_glb(port, entry, out):
    for node in (entry.get("outputs") or {}).values():
        for items in node.values():
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and str(item.get("filename", "")).lower().endswith(".glb"):
                    query = urllib.parse.urlencode({k: item.get(k, d) for k, d in
                                                    (("filename", ""), ("subfolder", ""), ("type", "output"))})
                    status, data = _request(port, f"/view?{query}", timeout=300)
                    if status != 200 or data[:4] != b"glTF":
                        raise GenError(f"ComfyUI's output file isn't a valid GLB (HTTP {status})")
                    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                    tmp = out + ".part"
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, out)
                    return len(data), item["filename"]
    raise GenError("the job finished without a GLB")


def _free(port):
    """Give the graphics memory back, so that Blender can use it."""
    try:
        _json(port, "/free", {"unload_models": True, "free_memory": True})
    except GenError:
        pass


def generate(image=None, out=None, res=1024, faces=200000, tex=2048, seed=42, port=None, timeout=1800,
             keep_loaded=False, force=False, **_):
    if not image or not out:
        raise GenError("--image and --out are required, or use --probe")
    if not str(out).lower().endswith(".glb"):
        raise GenError("--out must end in .glb")
    if os.path.exists(out) and not force:
        raise GenError(f"{out} already exists. Choose another name, or pass --force to overwrite it")
    if not os.path.isfile(image):
        raise GenError(f"{image}: file not found")
    if res not in (512, 1024) or tex not in (512, 1024, 2048) or not 1000 <= faces <= 1000000 or timeout <= 0:
        raise GenError("--res must be 512 or 1024, --tex 512, 1024 or 2048, --faces 1000 to 1000000, --timeout above 0")
    state = probe(port)
    if not state["ready"]:
        raise GenError(f"{state.get('fix')} Missing: {[m['file'] for m in state['missing_models']] or state['missing_nodes']}")
    port = state["port"]
    _, info = _json(port, "/object_info", timeout=60)
    models, _unused = find_models(info)
    name = _upload(port, image)
    prefix = "bas_" + "".join(c if c.isalnum() else "_" for c in os.path.splitext(os.path.basename(out))[0])[:60]
    graph = build_graph(name, models, res, faces, tex, seed, prefix)
    start = time.time()
    status, reply = _json(port, "/prompt", {"prompt": graph, "client_id": uuid.uuid4().hex})
    if status != 200 or not (reply or {}).get("prompt_id"):
        raise GenError(f"ComfyUI rejected the job (HTTP {status}): {json.dumps(reply)[:600]}")
    try:
        entry = _wait(port, reply["prompt_id"], timeout)
        size, filename = _save_glb(port, entry, out)
    finally:
        if not keep_loaded:
            _free(port)
    return {"ok": True, "out": out, "mb": round(size / 2**20, 1), "seconds": round(time.time() - start, 1), "res": res,
            "faces": faces, "tex": tex, "seed": seed, "port": port, "comfyui_output": filename,
            "warnings": state["warnings"]}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--probe", action="store_true", help="check that ComfyUI and the models are ready, and change nothing")
    p.add_argument("--image", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--res", type=int, default=1024, help="1024 for the better result, 512 for a quick draft")
    p.add_argument("--faces", type=int, default=200000)
    p.add_argument("--tex", type=int, default=2048)
    p.add_argument("--seed", type=int, default=42, help="change it for a different attempt from the same photo")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--keep-loaded", action="store_true")
    p.add_argument("--force", action="store_true")
    args = vars(p.parse_args())
    try:
        result = probe(**args) if args.pop("probe") else generate(**args)
    except (GenError, OSError) as e:
        result = {"ok": False, "error": str(e)}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
