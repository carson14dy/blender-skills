# Asset safety

From Claude Blender Skills by Mr omi (MIT). Downloaded assets (tutorial packs, car models, add-on zips) can carry code. Check them before anything opens them in a normal Blender, and before they touch the scene.

## Checklist
| # | Step | Pass when |
|---|---|---|
| 1 | Unpack each archive into its own folder (add-ons and anything doubtful into a `quarantine/` folder, not installed) | nothing was run |
| 2 | List each archive's contents for `.exe .bat .ps1 .py .dll` (also `.cmd .vbs .js .jar .msi .scr .lnk .sh`) | none, or each one is read and explained |
| 3 | Virus-scan the archives and the unpacked folders, with signatures updated first | clean, no detections |
| 4 | Check the unpacked file types | only data: `.blend .hdr .jpg .png .tif .txt` |
| 5 | Open every .blend headless with `--disable-autoexec` and run the audit (below) | `"pass": true` |
| 6 | Write the results to `SECURITY.md` in the project | one row per check, with the date |
| 7 | Record each asset's license and credit | source, license, author |

## The audit
```
blender -b --disable-autoexec FILE.blend -P scripts/blend_audit.py
python scripts/run_in_blender.py --blend FILE.blend scripts/blend_audit.py
```
`scripts/run_in_blender.py` starts Blender with factory settings, so auto-run is off; don't add `--user-prefs`. The audit is read-only and prints one JSON line.

| Field | Meaning |
|---|---|
| `pass` | false when the file carries code that could run on load |
| `errors` | text blocks registered to run on load, scripted drivers (Python expressions), OSL script nodes |
| `warnings` | text blocks to read before running any, linked libraries (audit each one too), missing image files |
| `texts`, `scripted_drivers`, `osl_nodes`, `libraries` | the entries behind each count |
| `images` | `total`, `packed`, `missing` paths |
| `autoexec_enabled` | must be false while auditing |

Expect 0 text blocks, 0 scripted drivers, 0 OSL nodes and 0 linked libraries in an asset pack. A missing image is often a junk path left over from the creator's export: relink or ignore it, but list it in `SECURITY.md`.

## Add-ons that ship with assets
- Don't install them. Write your own code for what they do (in `blender-forest` our own scatter and car rig replaced two add-ons).
- If one must be judged, read every `.py`: imports, network, `subprocess`, `os`, `exec`/`eval`, file writes, URLs.
- Precompiled `.pyc` files (`__pycache__`) can't be read. Never install a zip that ships them as-is.
- Keep running Blender with `--disable-autoexec` on those files for the whole project.

## Then the geometry
Safety first, geometry second: once the audit passes, check the meshes you keep with `blender-asset-qa` (`qa_check.py`).
