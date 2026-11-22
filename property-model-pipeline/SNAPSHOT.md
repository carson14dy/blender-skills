# Snapshot

Copied into `rooftec-lab` on 2026-11-22 from branch `claude/upbeat-franklin-at23bw`, commit `8c6df1d` ("Accuracy round 3 (in progress)"), at the user's request, so that roof pitch for existing homes can use LiDAR first (`references/roof-pitch.md` in the blender-suite skill).

- **Source of truth:** that branch, while its session is still working on it. Refresh this copy from it; do not edit the files here. To refresh:
  `git fetch origin claude/upbeat-franklin-at23bw && git checkout origin/claude/upbeat-franklin-at23bw -- property-model-pipeline`, then delete `examples/ames-ia-demo/overview.jpg` again and keep this file.
- **Left out:** `examples/ames-ia-demo/overview.jpg` (aerial imagery © Esri, Maxar, Earthstar Geographics; it stays on the source branch).
- **Missing dependency:** the code imports `scipy` (`propmodel/lidar.py`), but `requirements.txt` does not list it. Install it as well: `pip install -r requirements.txt scipy`.
- **Tests at this commit** (cloud, 2026-11-22):
  - with pip `bpy` 5.2.4 and scipy: 63 passed;
  - without `bpy`: 47 passed, 16 skipped;
  - without scipy: 11 failed.
