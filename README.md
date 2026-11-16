# Blender Skills for Claude Code

> **You are on `rooftec-lab`**, the research and testing branch for RoofTec 3D homes. Do not merge this branch; finished pieces move to `main` through their own pull requests.

## RoofTec lab: start here

**On your Windows PC (local Claude session):**

1. Follow "Set up this PC" in [lab/NEXT.md](lab/NEXT.md): Git, Node, Blender, ffmpeg, uv and the MCP for Blender addon, about 30 minutes once.
2. In PowerShell:
   ```
   git clone https://github.com/carson14dy/blender-skills.git
   cd blender-skills
   git checkout rooftec-lab
   ```
3. Open this folder in Claude Code (the Claude desktop app's Code tab, or `claude`) and say: **"Do the next local item in lab/NEXT.md"**.
4. Claude runs the environment check, works through the experiment, and pushes its results. Afterwards, tell the cloud session: **"check the lab log"**.

**Where things are:**

| File | What it is |
|---|---|
| [lab/NEXT.md](lab/NEXT.md) | The to-do list for each session, plus the PC setup steps |
| [CLAUDE.md](CLAUDE.md) | Rules every Claude session follows on this branch |
| [lab/LOG.md](lab/LOG.md) | Hand-off notes between sessions, newest first |
| [lab/GOALS.md](lab/GOALS.md) | The research tracks and the experiment backlog |
| [lab/experiments/](lab/experiments/) | One folder per experiment with results and images |
| [lab/tools/](lab/tools/) | Environment check, geometry gate (`roof_qa.py`, blender-suite checks), screenshots, snapshots, Blender stand-ins |

---

A collection of Claude Code skills for automating 3D product workflows in Blender via MCP.

## Skills

### Roofing (RoofTec 3D homes)
- **[roof-visualizer](roof-visualizer/SKILL.md)** — Roof Layer Studio: browser app that swaps the roof for any supplier product or photo at true scale, toggles every layer, plays a tear-off-to-finish build, opens an exploded layers view, measures squares and order quantities, and exports 4K/8K or path-traced stills. `cd roof-visualizer && npm start`
- **[roof-blender](roof-blender/SKILL.md)** — The same layer stack in Blender with stepped shingle courses and real nails: Cycles stills, build videos and exploded-layer videos, through MCP for Blender or headless.
- **[Open-source guide](docs/ROOFTEC-OPEN-SOURCE.md)** — MIT and other permissive tools for the next steps, licenses to avoid, and supplier image rights.

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

## Prerequisites

- **Roofing skills:** Node 18+ (roof-visualizer); Blender 4.2 LTS or 5.x plus ffmpeg (roof-blender). The Blender scripts use the [MCP for Blender](https://github.com/ahujasid/blender-mcp) addon (formerly blender-mcp), installed with `uvx mcp-for-blender install-addon`, or run Blender headless.
- **Product and camera skills:** Blender 5.x with the MCP for Blender addon, Claude Code with the MCP server configured (`uvx mcp-for-blender setup`), a [Meshy API](https://www.meshy.ai/) key for 3D generation, and ffmpeg.

## Setup (product and camera skills)

1. Install skills into your project's `.claude/skills/` directory
2. Open Blender; the MCP for Blender addon starts its server (N panel > MCP for Blender)
3. Use natural language to trigger skills: "make a turntable of this product", "zoom in on the logo", etc.

## Output (camera animation skills)

- Videos render as **ProRes 4444 with alpha** (transparent background) to `~/Desktop/Blender Videos/`, 1920x1080 at 24 fps by default.
- roof-blender writes H.264 MP4 files and 4K PNG stills to the paths you give it; see its SKILL.md.
