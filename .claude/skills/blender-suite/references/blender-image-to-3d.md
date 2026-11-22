# Image to 3D

The execution model is in `SKILL.md`. Cleanup and game-ready steps are in `blender-workflow-recipes`.

## Pick a route
Use the first one that fits, and tell the user which one you chose.
| Route | Cost and privacy | Result |
|---|---|---|
| **1. Local TRELLIS.2** (default) | Free, with no limit. The photo stays on the PC. Needs an NVIDIA GPU with 8 GB | Textured PBR model from one image |
| **2. Free web generator** | Free monthly credits, and the photo is uploaded, so confirm first. The user downloads the file by hand | Textured model, with the service's license terms |
| **3. ChatGPT parts** | Paid API, separate from a ChatGPT subscription, and the photos are uploaded | Editable flat-color model built from simple shapes |

Route 3 is a last resort, or a deliberate choice for a clean editable product model. Its steps are in [the ChatGPT parts guide](image-to-3d-chatgpt-parts.md).

## Route 1: local
**1. Check it's ready.** This changes nothing:
```
python scripts/trellis_generate.py --probe
```
If ComfyUI isn't running or `ready` is false, follow [the setup guide](image-to-3d-local-setup.md). Ask before starting ComfyUI or downloading anything.

**2. Generate.** Run it in the background, because it can take over 10 minutes:
```
python scripts/trellis_generate.py --image photo.jpg --out helmet.glb
```
**3. Import.** Give the real height in meters, because generators don't know the size:
```
scripts/import_generated.py -- --glb helmet.glb --name Helmet --height 0.28 --save helmet.blend
```
This welds the texture seams, stands the model on the ground and leaves no transforms. Re-running replaces only its `GEN_<name>` collection.

**4. Check it.** Run `qa_check.py` on the returned objects, then render it beside the photo. Tell the user what differs.

## Options for trellis_generate.py
| Flag | Default | Notes |
|---|---|---|
| `--res` | 1024 | `512` is about twice as fast or more, but shows clearly less likeness and detail. Use it for drafts |
| `--faces` | 200000 | Triangles in the final mesh. `30000` still looked good on a figure. Use a lower count for real-time work |
| `--tex` | 2048 | Texture size: 512, 1024 or 2048. With `--faces 30000`, `1024` gave a 5 MB file instead of 20 MB |
| `--seed` | 42 | Change it for a different attempt from the same photo |
| `--port` | auto | Otherwise `COMFYUI_PORT`, then 8188, then 8000 |
| `--timeout` | 1800 | Seconds before the job is cancelled |
| `--keep-loaded` | off | Keeps models in graphics memory between runs. By default they're released for Blender |
| `--force` | off | Overwrites `--out`, which is refused otherwise |

## What to expect
Measured on an RTX 5060 Laptop with 8 GB, at 200,000 faces and 2048 textures:
| Subject | 512 | 1024 |
|---|---|---|
| Stylized figure | 101 s | 214 s |
| Ornate thin-legged chair | 103 s | 220 s |
| Pair of leather boots | 158 s | not run |
| Very detailed helmet | 157 s | 542 to 671 s |

Graphics memory peaked between 7.1 and 7.7 GB. Detail, more than object type, sets the time.

**Blender can stay open.** A separate program holding 3.7 GB of graphics memory, idle, barely slowed a run. This wasn't tested against Blender rendering, so don't render during a job. Ask the user to save first, because a GPU crash could lose unsaved work.

Tell the user these limits before they judge the result:
- **It uses one photo.** Hidden sides are invented, so check the back. Multi-view input isn't supported here.
- **Colors can drift.** Boots came out darker than the photo, and a white beard came out gray at 512. Try 1024 or another seed.
- **Fine text and logos may not survive,** and small features can change.
- **The mesh is for props and display, not animation.** It's dense triangles with thousands of small UV islands. Use `blender-retopology-uv` before rigging or hand editing.

## Photos that work
- Show one complete subject, with even light and a plain background. The background is removed automatically.
- A three-quarter view shows the most of the form.
- A pair of objects comes out as separate parts, as a pair of boots did.
- **Every test image was a clean generated picture, so real camera photos are untested.** Expect cluttered photos to do worse, and say so.
- If a photo is cluttered, ChatGPT can make a clean single-subject image first, within a subscription and with no API. This step wasn't tested either.

## Reading the QA result
After welding, 10 of 11 test meshes had no open edges, and the other had 3. Expect these findings, and report them rather than hiding them.
| Finding | Measured | Meaning |
|---|---|---|
| Non-manifold edges, and winding errors on the same spots | Up to 14 edges | Small and invisible in renders. Recalculating normals doesn't remove them. Fix them before 3D printing or simulation |
| Hidden back-to-back faces | Up to 281 pairs | Harmless for rendering |
| Floating or detached part | 2 parts on some models | Often correct, as with two boots. Check it against the photo |

**Real-time use:** generate with fewer faces and smaller textures, then follow recipe 5 in `blender-workflow-recipes`. Its `qa_check.py --profile game` budgets apply. **Presentation:** use `blender-lighting-lookdev` and `blender-camera-moves`.

## Route 2: free web generators
Current limits, as last checked. Confirm them on each site, because they change.
| Service | Free allowance | Free-plan rights |
|---|---|---|
| Meshy | 100 credits a month, about 10 downloads | Meshy owns the output, under CC BY 4.0 with credit |
| Tripo | 200 credits a month, about 8 to 13 models | Tripo keeps rights, and use is public and non-commercial |

Ask before suggesting an upload of anything private. Have the user download a GLB, then continue from step 3 above.

## Errors
| Result | Action |
|---|---|
| "ComfyUI isn't running" | Ask the user to start it, or start it with their OK |
| "ran out of memory" or "stopped responding" | Ask the user to save and close other GPU programs, then retry or use `--res 512` |
| "already exists" | Choose another name. Use `--force` only if the user wants it replaced |
| "was cancelled" after the timeout | Check for other GPU work, then raise `--timeout` |

More causes are in [the setup guide](image-to-3d-local-setup.md).

## Rules
- Never upload a photo without the user's OK. Route 1 uploads nothing.
- A live Blender session is the user's work. Never close it for them.
- Never run Python written by a model from photos. Route 3 uses JSON that a script checks, for this reason.
