# Merge a newer original-studio build into the lab

Keep three folders side by side: BASE (the studio build the lab was made from), NEW (the newer
studio build, downloaded from its artifact) and LAB (the lab site). Keep BASE: the next merge needs
the build you merge now as its base.

1. List the changes: `diff -rq BASE NEW`.
2. Run `scripts/merge_studio.sh BASE NEW LAB`. It copies LAB to `LAB.before-merge`, takes NEW's
   version of every file the lab did not touch, adds new studio files, and 3-way merges files both
   sides changed with `git merge-file` (base BASE, ours LAB, theirs NEW). It prints each file and the
   conflict count, and lists files the studio removed without deleting them.
3. Resolve each conflict by hand so both the studio change and the Lab work. Then run `node --check`
   on every merged `.js` file.
4. Check the places the lab touches:
   - `index.html`: no `<!doctype><html><head>` skeleton and no closing `</body></html>` (the host adds
     them), the `<title>` and brand "Roof Studio Lab", the importmap entries for `three/webgpu`,
     `three/tsl`, `3d-tiles-renderer`, `@sparkjsdev/spark` and `@google/model-viewer`,
     `css/lab.css`, the Lab tab button, `#labPane`, `#labCompare`, `#labAttrib`, and `js/lab.js`
     after `js/app.js`. The first studio tab button has `aria-selected="true"`; keep that as the studio
     sets it and add Lab with `false`.
   - `css/suppliers.css`: `.tabs { grid-template-columns: repeat(N, minmax(0, 1fr)) }` must equal the
     number of tab buttons (7 today). If the studio added a tab, raise N and recheck the phone widths.
   - `js/app.js`: the `MeshoptDecoder.ready?.catch` line, `buildSceneGlb()`, the `frameHooks` lines in
     `frame()`, and the `lab:` object in `window.roofStudio`.
5. If the house model changed, re-run `align_house.py` and compare `lab/data/site.json` with the old
   copy. When `originCityFt`, `originElevM` and `modelHeadingDeg` are unchanged, the tiles and splat
   stay valid; otherwise rebuild them (see `data.md`). The studio's model offset is read at run time.
6. Run the full test (`testing.md`) and look at the phone screenshots: the studio may change the phone
   layout (in November 2026 the panel became a drawer over the stage, and `css/lab.css` now uses its
   `--sheet-vis` variable to keep the attribution and the comparison view above the drawer).
7. Update `lab/findings.md` and `js/lab-findings.js` if numbers or studio behaviour changed.

The November 2026 merge had one conflict (the tab buttons in `index.html`); `suppliers.css` and
`app.js` merged cleanly.

The 17 November 2026 merge (studio version 1794875264-e252: resizable phone drawer, Materials as the opening tab, a saved house camera view) again had one conflict, the tab buttons. The house georeference was unchanged, so the tiles and splat were kept. Keep the studio's own choice of opening tab; the Lab button always stays `aria-selected="false"`.
