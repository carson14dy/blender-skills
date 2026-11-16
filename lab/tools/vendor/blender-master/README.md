# blender-master checks (vendored)

Four scripts copied unchanged from the **blender-master** Claude skill (`/anthropic-skills:blender-master`), so cloud and local lab sessions run the same checks even where the skill is not installed. MIT license: see `LICENSE` (EL4CTEO) and `NOTICE-upstream.md`.

| Script | What it checks |
|---|---|
| `qa_check.py` | z-fighting, floating parts, flipped normals, topology, scale, UVs, materials |
| `review_shots.py` | multi-angle Workbench contact sheet for a visual check |
| `env_report.py` | Blender version, engines, GPU, add-ons, units, color management |
| `_bpyx.py` | shared helpers for the three above |

Use them through `lab/tools/roof_qa.py` (the roof layer gate) or directly:

```bash
blender -b out/qa/roof.blend --python lab/tools/vendor/blender-master/qa_check.py -- --profile render --objects RT_layer_covering RT_layer_ridgeCap
```

With pip `bpy` (cloud), import `bpy` before these scripts, as `lab/tools/roof_qa.py` does: `env_report.py` needs Blender's `addon_utils`, which `import bpy` puts on the path. `review_shots.py` needs EGL (`apt-get install -y libegl1 libegl-mesa0`).

To update: copy the same four files from a newer skill and rerun `lab/tools/roof_qa.py`. Do not edit them here.
