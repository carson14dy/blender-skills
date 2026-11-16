# The CSP test harness

Start the server on a copy of the site, then run the tests:

```bash
S=.claude/skills/roof-studio-lab/scripts
python3 $S/test/serve.py "$SCRATCH/lab" 8765 &
NODE_PATH=$(npm root -g) LAB_TEST_OUT="$SCRATCH/lab-test" node $S/test/run_all.js            # all parts
NODE_PATH=$(npm root -g) LAB_TEST_OUT="$SCRATCH/lab-test" node $S/test/run_all.js lab,phone  # some parts
```

`serve.py` wraps `index.html` in the platform skeleton (`skeleton-head.html`) and sends the artifact
CSP. `/` uses the policy given for the artifact (no `'wasm-unsafe-eval'`), `/wasm/` adds
`'wasm-unsafe-eval'`, and `/frame.html` loads the page in a sandboxed iframe. It returns 404 for file
types the host does not serve and prints `UNSERVED <path>` on stderr.

`run_all.js` uses the preinstalled Playwright Chromium (`require('playwright')`; do not install
another). Parts: `tabs` (every studio tab, the toolbar, build playback, product change, snapshot,
switching houses), `lab` and `wasm` (all four Lab tests under each policy), `phone` (390 px, light and
dark, the drawer, tiles and splats on), `dark`, and `webgpu` (the real WebGPU path). Environment
variables: `LAB_URL` (default `http://127.0.0.1:8765`), `LAB_TEST_OUT`, `LAB_HOUSE` (default
`1601-s-discovery-ave`). Results land in `LAB_TEST_OUT/results/*.json`, screenshots in `shots/`.

## Reading the results

- Every part should report `errors: []`. Under `/` the splat test reports "blocked ... WebAssembly";
  that is expected. Under `/wasm/` it loads.
- The headless GPU is SwiftShader (software). Use frame times only to compare settings on the same
  run. Spark's first sort takes seconds there; on a GPU it is far faster.
- The `webgpu` part gets a software WebGPU adapter whose device is lost, which also resets the WebGL
  contexts. That is the environment, not the page; run the other parts without it.
- The full run takes about 15 to 25 minutes. Run it in the background and wait for it to exit.
