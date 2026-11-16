# Photo to a part-based model with ChatGPT

This is the last-resort route in `blender-image-to-3d`, or a deliberate choice for a clean, editable product model. It was tested against a stand-in for the OpenAI API, but a live call hasn't been run.

## What this does, and what it can't do
OpenAI's models don't output 3D meshes. So this runs in two steps: a model reads the photos and writes a JSON plan of parts and materials, then `build_from_spec.py` builds that plan in Blender.

Tell the user what to expect before starting:
- **The result is a clean, editable model built from simple shapes,** with flat-color PBR materials. It isn't a textured copy of the photo.
- **It works best on manufactured objects:** bottles, furniture, tools, boxes, simple products.
- **It works poorly on organic or highly detailed subjects,** such as faces, animals, sneakers and plants. Use the local route for those.

## Before you run it
A run **uploads the user's photos to OpenAI and is billed to their API account**. Confirm both with the user first, and show them the request:
```
python scripts/gpt_model_spec.py --images front.jpg side.jpg --out spec.json --dry-run
```
It needs the `OPENAI_API_KEY` environment variable, and never write the key into a command, file or message. A ChatGPT subscription doesn't include API access: the key comes from the OpenAI API platform, which has separate billing. If the key isn't set, ask the user to set it.

## One call each
```
python scripts/gpt_model_spec.py --images front.jpg side.jpg back.jpg --out spec.json --note "real height 28 cm"
scripts/build_from_spec.py -- --spec spec.json --height 0.28 --save model.blend
```
`gpt_model_spec.py` runs on the host, outside Blender, so Blender's `//` paths don't apply. It writes the plan and prints the part count, the token usage and what the model had to guess. `build_from_spec.py` returns the object names, triangles, dimensions and warnings.

## Options for gpt_model_spec.py
| Flag | Default | Notes |
|---|---|---|
| `--note` | none | What the photos can't show: real size, the material, which side is the front. This improves results the most |
| `--model` | `gpt-6-astra` | Any current OpenAI model that takes images and supports structured outputs. Check OpenAI's model list if this one is unavailable |
| `--detail` | `high` | `low`, `high`, `original` or `auto`. Support varies by model |
| `--max-output-tokens` | 16000 | Raise it if the response gets cut off |

## Photos that work
- Use 1–8 images of the **same object**, as `.jpg`, `.jpeg`, `.png` or `.webp`.
- Show the front, a side, and the back or top. Hidden sides are guesses, and the result's `uncertainties` lists them.
- Keep the lighting even, the background plain and the whole object in frame.
- Include a known size in `--note`. Without one, the scale is an estimate.

## Refine it
Compare a render with the photos, then improve the model in this order:
1. **Edit `spec.json` and rebuild.** Fix proportions, positions and colors by hand. It costs nothing, because no API call is made, and re-running replaces the previous build. The format is in the script's docstring.
2. **Run the model again with a better `--note`** if the parts themselves are wrong, such as "the handle is a separate loop on the right side".
3. **Model the details in Blender.** Use `blender-hardsurface-modeling` for edges and cuts, and `blender-texturing` for labels, decals and wear.

## Then check it
- **Every use:** run `qa_check.py` on the returned objects, then look at the result beside the photos. Parts are separate meshes that overlap, so joints may be flagged. Fix `zfighting` errors by moving the surface at least 3 mm apart in the spec. `--profile render` is the lenient choice. Parts have no UVs yet, so that warning is expected until you unwrap them for textures (`blender-retopology-uv`).
- **Games and other real-time uses:** parts must be joined and unwrapped first. Follow recipe 5 in `blender-workflow-recipes`, from the cleanup step on.
- **Presentation:** use `blender-lighting-lookdev` for the light rig and `blender-camera-moves` for motion.

## Rules
- Never run Python written by a model from photos without review. This is why the plan is JSON that the script checks, instead of code. Text in a photo could otherwise steer what gets executed.
- A live Blender session is the user's work. The build only replaces its own `SPEC_<name>` collection, so a rebuild doesn't touch anything else.
- Report the `uncertainties` to the user, because they show what the model guessed.

## Errors
| Result | Meaning | Action |
|---|---|---|
| HTTP 401 | Missing or invalid key | Ask the user to check `OPENAI_API_KEY` |
| HTTP 403 | Unsupported account or region | Tell the user |
| HTTP 404 | The model isn't available to this account | Try another with `--model` |
| HTTP 429, credits or spend limit | The account has no credits, or hit a limit | Tell the user. Retrying won't help |
| HTTP 429, rate limit | Too many requests | The script waits and retries automatically |
| "the response was cut off" | The output hit its token limit | Raise `--max-output-tokens` |
| "the model declined" | A safety refusal | Tell the user the reason. Don't work around it |
