# Blender Skills for Claude Code

A collection of Claude Code skills for automating 3D product workflows in Blender via MCP.

## Skills

### Measurement-grade property models (accuracy first)
- **[property-model-pipeline](property-model-pipeline/SKILL.md)** — Address → exact Blender model + roof/siding measurement report with ±1σ on every number. Fuses USGS 3DEP LiDAR, satellite/aerial imagery, OSM + Microsoft footprints, county parcel data, inspection photos (EXIF/drone metadata, plane rectification, camera matching) and past measurement reports in one robust least-squares fit; flags and excludes conflicting sources. See [examples/ames-ia-demo](property-model-pipeline/examples/ames-ia-demo/README.md) and [accuracy budget](property-model-pipeline/references/accuracy-budget.md).

### 3D Model Generation (generative — not metric)
- **[image-to-3d](image-to-3d/SKILL.md)** — Convert a single photo into a textured 3D model using Meshy API
- **[multi-image-to-3d](multi-image-to-3d/SKILL.md)** — Convert 1-4 photos from different angles into a high-accuracy 3D model

### Camera Animations
- **[turntable](turntable/SKILL.md)** — 360-degree orbit around the product. Classic product showcase.
- **[slow-zoom](slow-zoom/SKILL.md)** — Cinematic push-in toward a hero detail. Reveal effect.
- **[dolly-rotate](dolly-rotate/SKILL.md)** — Camera moves forward while rotating. Dynamic sweeping shot.
- **[crane-shot](crane-shot/SKILL.md)** — Low to high reveal. Dramatic product unveiling.
- **[dynamic-full-loop](dynamic-full-loop/SKILL.md)** — Speed-ramped loop showing all sides with fast whip transitions.
- **[perfect-loop](perfect-loop/SKILL.md)** — Seamless 360-degree loop for infinite playback.

### Blender Automation
- **[blender-toolkit](blender-toolkit/SKILL.md)** — WebSocket-based geometry, materials, modifiers, and Mixamo animation retargeting.

> Generative image-to-3D meshes have arbitrary scale and invented hidden geometry. Never quote measurements from them; use `property-model-pipeline` (or align the mesh with `pm.py align` and check it against LiDAR/tape first).

## Prerequisites

- Blender 5.x with [blender-mcp](https://github.com/ahujasid/blender-mcp) addon installed
- Claude Code with MCP server configured (`uvx blender-mcp`)
- [Meshy API](https://www.meshy.ai/) key (for 3D generation skills)
- ffmpeg (for video encoding)
- For property-model-pipeline: Python 3.10+ with `pip install -r property-model-pipeline/requirements.txt`; Blender (GUI, `blender -b`, or `pip install bpy`). No API keys needed for US public data.

## Setup

1. Install skills into your project's `.claude/skills/` directory
2. Connect Blender MCP addon (N-panel > BlenderMCP > Connect to Claude)
3. Use natural language to trigger skills: "make a turntable of this product", "zoom in on the logo", etc.

## Output

- All videos render as **ProRes 4444 with alpha** (transparent background)
- Output to `~/Desktop/Blender Videos/`
- 1920x1080, 24fps default
