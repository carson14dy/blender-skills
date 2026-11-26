# Measuring from inspection photos

Ask for **original files** (EXIF intact; screenshots and messaging apps strip it).
Best evidence per photo type:

| Photo | What it measures well | How |
|---|---|---|
| Pitch gauge / level on the roof | pitch ±0.25/12 | read it; `obs add --target pitch@ --xy x,y` |
| Tape in frame along an edge | that length ±1 cm | read it; `obs add --target M.length` (or edge) |
| Square-on wall with a door / garage door / brick | lengths & rake pitch ON THAT WALL | `photo-measure` |
| Nadir drone over the roof | plan lengths (GSD) | `photo-info` → GSD, measure px × GSD |
| Oblique drone / ground photos with ≥ 6 identifiable model corners | camera pose, model QA | `camera-match`, overlay render |
| Drone grid (70/70 % overlap) | full metric mesh | ODM/COLMAP → `align` → `measure_mesh.py` |

## 1. Metadata

```bash
python3 pm.py photo-info IMG_0042.JPG DJI_0103.JPG --surface-height 5.1
```
Gives `fx_px` (focal length in pixels: DJI calibrated value, else 35 mm-equivalent ÷ 43.27 mm
× image diagonal), GPS, DJI `RelativeAltitude`, gimbal pitch/yaw, and for drone shots the
GSD at (`RelativeAltitude − surface height`). Gimbal pitch must be ≈ −90° for GSD use.

## 2. Plane rectification (`photo-measure`)

Pick ≥ 4 pixel points on one plane whose plane coordinates you know, e.g. door corners
(0,0) (36in,0) (36in,80in) (0,80in), plane x horizontal, plane y vertical up.
More (6–8) well-spread points beat 4. Then list what to measure:

```json
{
  "ref_px":    [[1812, 2210], [2015, 2206], [2019, 1752], [1809, 1755]],
  "ref_plane": [["0in", "0in"], ["36in", "0in"], ["36in", "80in"], ["0in", "80in"]],
  "px_sigma": 1.5, "ref_sigma": 0.005,
  "measure": [{"name": "gable wall width", "a": [402, 2240], "b": [3610, 2195]}],
  "pitch":   [{"name": "west rake", "low": [430, 1500], "high": [2010, 980]}]
}
```
Output: value ±σ (Monte-Carlo over click noise and reference tolerance). The σ grows quickly
when the reference is small relative to what you measure — prefer a garage door or a long tape
over a door when measuring a whole wall. Pixel coordinates: open the photo and read cursor
positions, or view it with the Read tool and estimate carefully (then use px_sigma ≥ 4).

## 3. Camera match + overlay (`camera-match`)

`pairs.json`: `{"pairs": [{"px": [u, v], "xyz": [x, y, z]}, ...]}` with xyz read from
`model.json` / `report` (eave corners, ridge ends, valley bottoms, wall corners at ground).
≥ 6 non-coplanar pairs; with EXIF intrinsics 4 suffice. Use `--refine-focal` for phones that
crop/stabilise. Result: camera centre, RMS reprojection in px and in metres at the object.
`pm.py blender JOB --render` writes `out/Photo <img>_overlay.png` — misaligned edges show
exactly where the model is wrong; fix the spec and re-fit.

## 4. Drone photogrammetry

Fly a grid (≥ 70 % front/side overlap) plus an oblique orbit; 3–5 GCPs or ≥ 3 known points.
Process with OpenDroneMap (`docker run opendronemap/odm`) or COLMAP; export a mesh/point
cloud. Georeference with `pm.py align --pairs gcp.json` (src = mesh coordinates, dst = local
ENU from the model, LiDAR or survey); report the alignment RMS. A photogrammetric point cloud
can be added to the fit like LiDAR: `{"target": "roof_z", "points": [...], "sigma": 0.05}`.
