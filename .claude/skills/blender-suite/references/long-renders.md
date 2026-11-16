# Long Renders

From Claude Blender Skills by Mr omi (MIT). How the film examples got through overnight renders: a car film estimated at 5–8 hours that took about 1 hour (600 frames, 2560x1072), a forest clip of 390 frames at 2560x1440 in about 3 hours, and a 10 s night drone shot in 3.5 hours. Single renders, presets and batches are in `blender-rendering` (`scripts/render_batch.py`).

## Before rendering
- **Benchmark**: `pipelines/forest/scripts/bench.py` renders the same frames with different Cycles settings and prints `BENCH <frame> <seconds>`. 128 samples + OpenImageDenoise looked the same as 256 samples and was about 45% faster (51 s → 28 s a frame).
```
BENCH='{"samples":128,"denoiser":"OPENIMAGEDENOISE"}' blender -b scene/forest.blend --python pipelines/forest/scripts/look.py --python pipelines/forest/scripts/bench.py -- <out_dir> <frame> [frame ...]
```
- **Six test stills at final quality**, checked by eye (`pipelines/car-film/scripts/render_stills.py` renders one per shot).
- **Tell the user the estimate** (seconds a frame × frames) and ask before starting.

## Speed
| Lever | From the examples |
|---|---|
| Adaptive sampling + OptiX denoise | 24–30 samples are enough at night |
| Fewer bounces | night: total 6, diffuse 2, glossy 3, transmission 6, volume 0, clamp indirect 8 (`pipelines/car-film/scripts/11_fast_render.py`) |
| Bake particle caches to disk | without it every frame re-simulated the snow: 158 s → about 6 s a frame |
| Persistent data | the scene stays in GPU memory between frames |
| Camera and distance culling | trees, poles and the snow emitter (`pipelines/car-film/scripts/13_speed_cine.py`) |
| Lighter LODs | the same tree at 1/3 of the faces beyond 30 m from every shot camera |
| Hidden duplicates removed | the tree asset carried extra copies (`pipelines/film/scripts/09_render_opt.py`) |

## Safety
- Render in background Blender from a saved .blend, never in the live window.
- Absolute output paths: relative ones in `blender -b` resolve to the drive root.
- Resumable: `render.use_overwrite = False` + `use_placeholder = True` (`pipelines/car-film/scripts/render_frames.py`), or skip frames already on disk. An interrupted run leaves zero-byte placeholders: delete them before resuming.
- Render only the frames the edit uses. `pipelines/film/scripts/10_render_edit.py` takes a shot list (camera + frame range), numbers frames continuously, skips frames that exist and writes `status.json` beside the output folder (`job`, `total`, `done`, `current`, `last`, `avg` of the last 12 frames):
```
blender -b film.blend --python pipelines/film/scripts/10_render_edit.py -- <outdir> <width> <spp> [blur 0/1]
```
- Below-normal process priority keeps the PC usable (`bench.py`, `render_final.py` in `pipelines/forest/scripts/`).
- One GPU job at a time: `render_all.sh` waits until no other background Blender runs.

## Windows tools
Each has the author's Blender path and project folder written in: edit them first.

| Tool | Does | Edit first |
|---|---|---|
| `pipelines/film/tools/render_window.ps1` | progress panel from `render\status.json`: %, time left, last finished frame | `FILM_ROOT` or `%USERPROFILE%\blender-film` |
| `pipelines/car-film/tools/progress.ps1` | a bar per shot, counts non-empty frames | `blender-car-film`, shot ranges, 600 frames |
| `pipelines/forest/scripts/watch_render.ps1` | frames done, seconds a frame, time left, GPU load | `blender-forest\render\final_2k`, 390 frames |
| `pipelines/car-film/tools/stay_awake.ps1` | keeps the PC awake until the final MP4 exists (max 3 h); no settings changed | the MP4 path |
| `pipelines/forest/scripts/stay_awake_encode.ps1` | keeps the PC awake while `render_final.py` runs, then encodes the MP4 if all 390 frames exist | `blender-forest`, frame count |
| `pipelines/forest/scripts/render_final.cmd` | deletes zero-byte frames, then renders headless | Blender 5.2 path, `blender-forest` |
| `pipelines/car-film/tools/render_all.sh` | Git Bash queue: renders the remaining shots one by one, encodes each and the full film; re-run after a power cut | Blender 5.2 path, `~/blender-car-film`, shot list |

Closing a progress window does not stop the render.

## After rendering
1. Every frame exists and none is zero bytes.
2. No black or broken frames: check brightness per frame; it may jump only at planned cuts.
```
ffmpeg -i frames/f_%04d.png -vf signalstats,metadata=print:key=lavfi.signalstats.YAVG -f null -
```
3. The sound is the approved mix ([film-sound.md](film-sound.md)).
4. Only then encode, as `render_all.sh` does, and shut the PC down only if the user asked:
```
ffmpeg -framerate 30 -i frames/f_%04d.png -i audio/mix.wav -c:v libx264 -preset slow -crf 15 -pix_fmt yuv420p -c:a aac -b:a 320k -t 20 film.mp4
```
