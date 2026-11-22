# Poly Haven and Variant Renders

The execution model is in `SKILL.md`. This skill gets assets and compares options. Other skills own the rest: `build_pbr_material.py` (`blender-pbr-materials`) wires a texture set into a material, and `turntable.py` (`blender-lighting-lookdev`) builds a light rig and backdrop from an HDRI.

## One call each
```
python scripts/polyhaven_fetch.py --search "brushed metal" --type textures
python scripts/polyhaven_fetch.py --id rusty_metal --res 2k --out assets/
python scripts/polyhaven_fetch.py --id studio_small_09 --res 2k --out assets/
scripts/variant_renders.py -- --hdris assets/studio_small_09/studio_small_09_2k.hdr assets/venice_sunset/venice_sunset_2k.hdr --out //compare/
scripts/variant_renders.py -- --materials M_Oak M_Steel M_Marble --objects Hero --out //finishes/
```
`polyhaven_fetch.py` runs on the host, needs no key and no add-on, and works whichever Blender connection you use. `variant_renders.py` runs in Blender like every other skill script.

## Never guess an asset id
Search first. Names that sound right often don't exist: `brushed_metal` and `carbon_fiber` aren't Poly Haven ids. The search returns real ids, and a wrong id fails with a clear message.

| Type | Good starting ids |
|---|---|
| Studio HDRIs | `studio_small_09` (clean white), `studio_small_08` (warm), `studio_small_03` (soft), `photo_studio_loft_hall` |
| Outdoor HDRIs | `kloppenheim_06_puresky` (overcast), `venice_sunset`, `meadow_2`, `snowy_park_01` |
| Dramatic HDRIs | `industrial_sunset_02_puresky`, `royal_esplanade`, `moonless_golf` |

## Choosing what to download
- **Resolution**: 1k for variant tests and previews, 2k for most finals, 4k only when an HDRI is visible in the background or a texture fills the frame.
- **Texture sets**: you get color, an OpenGL normal, a packed AO/roughness/metal map when one exists, and displacement. The data maps default to PNG, because JPEG artifacts show up in normals. `--format jpg` saves space on previews.
- **Models**: the glTF comes with its binary and textures, in the asset's own folder. Import with `bpy.ops.import_scene.gltf`.

## Texture set to material
```
scripts/build_pbr_material.py -- --name M_Rust --textures assets/rusty_metal --objects Hero
```
Poly Haven's file names are detected automatically, including the color spaces and the packed map. Build every finish this way first, then pass the material names to `variant_renders.py --materials`.

## variant_renders.py
1. Set up the shot first: camera, resolution and engine. The script uses them and needs a scene camera. `--samples` and `--engine` override them for the run.
2. Keep previews cheap: 1k assets and a low `--samples` value, with the resolution at 960×540 or less.
3. Read the result. `grid` is the comparison sheet, `cells` lists each cell's variant from left to right and top to bottom, and `files` holds the full-size renders.
4. Show the grid to the user and let them pick. Then apply the winner properly and do the final render with `render_batch.py --preset final`.

The script restores the world, the material slots, the engine, and the output settings afterward, even when a render fails. HDRIs are applied through a temporary world, so the scene's own world is never edited.

## Rules
- **Judge materials under at least two different HDRIs.** A material that only works in one is wrong (`blender-pbr-materials`).
- Compare one thing at a time. Don't change the camera or the exposure between variants.
- Lights already in the scene stay on during HDRI comparisons. Hide them to see the HDRI alone.
- HDRI variants need Cycles or EEVEE. Workbench ignores the world.
- Use `--rotation` to turn an HDRI so the key light falls on the side you want.
- Poly Haven's assets are CC0, so they need no credit. If you build a tool or service on the live API, its terms ask for a named user-agent and a visible credit to Poly Haven.

## Gotchas
- Paths given to `polyhaven_fetch.py` are normal file paths. Paths given to `variant_renders.py` can use Blender's `//`.
- `--materials` changes the slot on every listed object. Materials shared by other objects aren't edited, only reassigned, and the slots are restored afterward.
- An object with no material slot fails with a clear error. Add a slot or assign any material first.
