# Notice

This skill merges three MIT-licensed works into one skill. See `LICENSE`.

| Part of this skill | Comes from | Copyright |
|---|---|---|
| `scripts/` (43 files), 42 of the references, `assets/`, `tests/` | Blender Agent Skills 1.3.1, https://github.com/EL4CTEO/blender-skills (commit b1b21df) | (c) 2026 EL4CTEO |
| `pipelines/`; the text behind `blender-film`, `blender-forest`, `long-renders`, `film-sound` and `asset-safety`; `blend_audit.py` and `blender_send.py` are rewrites of its audit and send scripts | Claude Blender Skills, https://github.com/mromidev/claude-blender-skills (commit 567116b) | (c) 2026 Mr omi |
| The one-skill layout and router; camera moves, Poly Haven tools, web viewer, photo to 3D scripts and their references | the blender-master skill, version 1.2.1 | its contributors, MIT |
| The merge, `check_skill.py`, `smoke.py`, the pip `bpy` fallback in `run_in_blender.py`, `rooftec` | blender-suite | its contributors, MIT |

blender-master's camera moves, Poly Haven tools, photo to 3D scripts and web viewer were newly written. Their ideas came from kevinbadi/blender-skills, which has no license, so none of its text or code is included. Nothing was taken from the older skills on this repository's `main` branch either.

Left out on purpose: all images and video from the sources, the notes in Claude Blender Skills that describe other people's tutorials, its live bridge (it used the port of the MCP for Blender add-on), and blender-master 1.0.0's Meshy script.

## Things this skill uses but does not include
- **Poly Haven** assets are CC0. A tool built on the live Poly Haven API must name itself in its user-agent and visibly credit Poly Haven.
- **OpenAI API** and **ElevenLabs** are separate paid services with their own terms. Keys are read only from `OPENAI_API_KEY` and `ELEVENLABS_API_KEY`.
- **Local photo to 3D** drives the user's own ComfyUI. No models are included. TRELLIS.2 (MIT, Microsoft), DINOv3 (Meta's own license, with end-use limits) and BiRefNet (MIT) are downloaded separately under their own terms.
- **Meshy and Tripo** are named only as web services the user may choose to use by hand. Their terms apply to what they generate.
- **Pipeline scripts name assets that are not here:** a city pack and a character rig from a tutorial, tutorial forest assets, and "Peugeot 504" by 3d_engineer on Sketchfab (CC BY 4.0, credit required). Names such as "Spider-Man" in `pipelines/film/` are object names from the author's scene. Use your own assets and follow each asset's license.
- **Camera Shakify** and the **MCP for Blender** add-on are separate projects with their own licenses.
