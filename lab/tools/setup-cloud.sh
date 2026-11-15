#!/usr/bin/env bash
# Cloud sessions have no Blender install: put Blender in a Python venv instead.
#   bash lab/tools/setup-cloud.sh
# Creates ~/.cache/rooftec-lab/bpyenv with bpy (Blender 5.2 LTS as a module, CPU rendering),
# and a blender-shim that roof-blender.mjs can use as --blender.
set -euo pipefail
VENV="${LAB_VENV:-$HOME/.cache/rooftec-lab/bpyenv}"
BPY_VERSION="${BPY_VERSION:-5.2.4}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY=python3
if ! $PY -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)'; then
  echo "bpy $BPY_VERSION needs Python 3.13; found $($PY --version). Set BPY_VERSION to match your Python." >&2
fi
if [ ! -x "$VENV/bin/python" ]; then
  $PY -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c 'import bpy' 2>/dev/null; then
  echo "Installing bpy==$BPY_VERSION (about 430 MB)..."
  "$VENV/bin/pip" install -q "bpy==$BPY_VERSION"
fi
"$VENV/bin/python" -c 'import bpy; print("bpy", bpy.app.version_string)'

SHIM="$VENV/bin/blender-shim"
cat > "$SHIM" <<EOF
#!/usr/bin/env bash
# Accepts roof-blender's headless call: blender -b [file|--factory-startup] --python CORE -- cfg
FILE=""
while [ "\$#" -gt 0 ] && [ "\$1" != "--python" ]; do
  case "\$1" in -b|--factory-startup) ;; *) FILE="\$1" ;; esac
  shift
done
CORE="\$2"; shift 3
exec "$VENV/bin/python" - "\$FILE" "\$CORE" "\$1" <<'PY'
import sys, bpy
blend, core, cfg = sys.argv[1], sys.argv[2], sys.argv[3]
if blend:
    bpy.ops.wm.open_mainfile(filepath=blend)
sys.argv = ["blender", "--", cfg]
exec(compile(open(core).read(), core, "exec"), {"__name__": "__main__"})
PY
EOF
chmod +x "$SHIM"

cat <<EOF

Ready.
  export LAB_BPY_PYTHON=$VENV/bin/python
  Blender checks:   \$LAB_BPY_PYTHON roof-blender/tests/test_roof_core.py
  Headless runs:    node roof-blender/scripts/roof-blender.mjs still --blender $SHIM --output out/roof.png --samples 16 --resolution 960x540
  MCP stand-in:     \$LAB_BPY_PYTHON $HERE/mock_blender_mcp.py &
EOF
