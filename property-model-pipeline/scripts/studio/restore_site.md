# Restoring the Roof Layer Studio site folder

The studio artifact is published from one local folder that must hold the COMPLETE site: `index.html`, all 16 JS
modules under `js/`, `css/`, `catalog/`, `plans/` and `houses/`. A publish sends the whole page plus the files named in
`files`; a folder that holds only part of the site (an old working copy had 6 of the 16 modules) breaks the live page.
When the scratch copy is gone or in doubt, rebuild it from the artifact itself before any publish.

`site_manifest.json` (next to this file) lists the 25 app files of the published version with byte sizes and sha256.
House files (`houses/...`) are not in it: their paths carry street addresses and the repository is public. Their list
and hashes live in the scratch notes (the `studio_manifest.txt` written when the site was last listed), together with
the studio artifact URL. Neither the URL nor any house path belongs in this repository.

## Steps (agent, with the Artifact tool)

1. Find the studio URL: the scratch notes, or `Artifact` `action: "list"` and pick "Roof Layer Studio".
2. List what is published: `Artifact` `action: "list"`, `scope: "files"`, `url: <studio url>`. Expect 42 files on the
   version listed on 2026-11-25 (more once media or new houses were added).
3. Fetch every file into a new, empty folder `ST`:
   `Artifact` `action: "read"`, `url: <studio url>`, `paths: [<every path from step 2>]`, `out_dir: ST`.
   Fetch `index.html` too (it is the page itself; `path: "index.html"`).
4. Verify:
   ```
   python3 scripts/studio/package_house.py --verify-site ST
   python3 scripts/studio/package_house.py --verify-site ST --manifest <scratch>/learn/studio_manifest.txt
   ```
   The first checks the app files against `site_manifest.json`, that every module `index.html` imports exists, and
   that every house in `houses/index.json` has its model, detail, report and thumbnail. The second checks the house
   files' hashes too. Exit 0 = complete.
   A `CHANGED` app file means the published app moved on since this manifest (for example the splat viewer hook).
   Check the change is intended, then refresh the manifest:
   `python3 scripts/studio/package_house.py --snapshot-site ST --manifest-out scripts/studio/site_manifest.json`
   (it never lists `houses/`).
5. From then on: package into `ST` (`package_house.py JOB --site ST ...`), smoke-test `ST` (`smoke.py --site ST
   --house <slug>`), and publish with `file_path: ST/index.html` and the files map package_house prints, always to the
   SAME studio URL (`url: <studio url>`), never as a new artifact. If the publish is refused because a file changed
   since it was read, read the named paths again, merge, and publish again.

## Rules

- Never publish from a folder that failed `--verify-site`.
- Never put the studio URL, a house slug or an address into a repository file; they stay in scratch notes.
- Smoke-test output (`--out`) goes outside `ST`: everything inside `ST` is publishable.
