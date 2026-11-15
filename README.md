# Blender Skills for Claude Code

A collection of Claude Code skills for automating 3D product workflows in Blender via MCP.

## Skills

### 3D Model Generation
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

### Roofing (RoofTec 3D homes)
- **[roof-visualizer](roof-visualizer/SKILL.md)** — Roof Layer Studio: browser app that swaps the roof for any supplier product or photo at true scale, toggles every layer, plays a tear-off-to-finish build, opens an exploded layers view, measures squares and order quantities, and exports 4K/8K or path-traced stills. `cd roof-visualizer && npm start`
- **[roof-blender](roof-blender/SKILL.md)** — The same layer stack in Blender with stepped shingle courses and real nails: Cycles stills, build videos and exploded-layer videos, through blender-mcp or headless.
- **[Open-source guide](docs/ROOFTEC-OPEN-SOURCE.md)** — MIT and other permissive tools for the next steps, licenses to avoid, and supplier image rights.

## Prerequisites

Roofing skills: Node 18+ for roof-visualizer; Blender 4.2+ (MCP or headless) and ffmpeg for roof-blender.

- Blender 5.x with [blender-mcp](https://github.com/ahujasid/blender-mcp) addon installed
- Claude Code with MCP server configured (`uvx blender-mcp`)
- [Meshy API](https://www.meshy.ai/) key (for 3D generation skills)
- ffmpeg (for video encoding)

## Setup

1. Install skills into your project's `.claude/skills/` directory
2. Connect Blender MCP addon (N-panel > BlenderMCP > Connect to Claude)
3. Use natural language to trigger skills: "make a turntable of this product", "zoom in on the logo", etc.

## Output

- All videos render as **ProRes 4444 with alpha** (transparent background)
- Output to `~/Desktop/Blender Videos/`
- 1920x1080, 24fps default
