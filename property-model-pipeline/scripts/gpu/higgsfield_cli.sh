#!/usr/bin/env bash
# Upload a rendered video (or still) to Higgsfield with the official CLI, and run the Topaz 4K upscale only
# if this CLI version offers it. For the client's own computer: the CLI signs in through a browser with a
# localhost callback (`higgsfield auth login`), so it cannot run inside a cloud container; a Claude cloud
# session uses the Higgsfield MCP tools instead (MCP_SEQUENCE.md). The CLI has no GPU rental commands.
#
#   higgsfield_cli.sh FILE [--yes] [--resolution 2160p] [--model NAME] [--dry-run] [--allow-any-name]
#
#   FILE        a render of the measured model: turntable*.mp4, hero_street / aerial_34 / top_down images.
#               Real photos (listing, owner, street-level, inspection) must never be sent; other file names
#               are refused unless --allow-any-name says the file is a render.
#   --yes       the client approved the upscale cost. Without it the script stops after the upload and
#               prints the exact upscale command (the first paid run always needs the client's OK).
#   --model     the CLI model name to use (default: the first Topaz video model `model list` shows)
#   --dry-run   print the commands, run nothing
#
# Steps: `higgsfield upload create FILE` (prints the upload id); then `higgsfield model list --video`.
# Only if it lists a Topaz video model (for example topaz_video): `model get`, `generate cost` when the CLI
# supports it, and with --yes `generate create MODEL --video UPLOAD_ID --resolution 2160p --wait`.
# Otherwise it prints "upload done, run the upscale from a Claude session" and exits 0.
# Checked 2026-11-25: npm @higgsfield/cli 1.2.2 only installs the `hf` binary; its README names
# `generate create` but no upscale command. The binary's strings include a topaz_video job type and
# `generate workflow` / `generate cost`, but the upscale call is NOT confirmed: treat it as a trial.
# Upscaled output is labelled "upscaled with Topaz (video only)"; measurements come only from the report.
set -uo pipefail

usage() { awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"; }

FILE=""
YES=0
DRY="${DRY_RUN:-0}"
RES="2160p"
MODEL=""
ANY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    --allow-any-name) ANY=1 ;;
    --resolution) RES="${2:?}"; shift ;;
    --resolution=*) RES="${1#*=}" ;;
    --model) MODEL="${2:?}"; shift ;;
    --model=*) MODEL="${1#*=}" ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "higgsfield_cli: unknown option $1" >&2; usage >&2; exit 2 ;;
    *) [ -z "$FILE" ] || { echo "higgsfield_cli: one file only" >&2; exit 2; }; FILE="$1" ;;
  esac
  shift
done
[ -n "$FILE" ] || { usage >&2; exit 2; }
[ -f "$FILE" ] || { echo "higgsfield_cli: no such file: $FILE" >&2; exit 2; }
case "$RES" in 1080p|2160p) ;; *) echo "higgsfield_cli: --resolution is 1080p or 2160p" >&2; exit 2 ;; esac

NAME="$(basename "$FILE")"
LOWER="$(printf '%s' "$NAME" | tr '[:upper:]' '[:lower:]')"
IS_VIDEO=0
case "$LOWER" in *.mp4|*.mov|*.webm) IS_VIDEO=1 ;; esac
if [ "$ANY" != 1 ]; then
  case "$LOWER" in
    turntable*.mp4|hero_street*.jpg|hero_street*.png|aerial_34*.jpg|aerial_34*.png|top_down*.jpg|top_down*.png) ;;
    *) echo "higgsfield_cli: '$NAME' is not a known render name (turntable*.mp4, hero_street, aerial_34, top_down)." >&2
       echo "  Real photos never go to Higgsfield. If this file is a render of the measured model, add --allow-any-name." >&2
       exit 3 ;;
  esac
fi

CLI=""
for c in higgsfield higgs; do command -v "$c" >/dev/null 2>&1 && { CLI="$c"; break; }; done
if [ -z "$CLI" ] && [ "$DRY" != 1 ]; then
  echo "higgsfield_cli: the Higgsfield CLI is not installed. Install it with: npm install -g @higgsfield/cli" >&2
  echo "  then sign in once with: higgsfield auth login (opens a browser)" >&2
  exit 4
fi
CLI="${CLI:-higgsfield}"

run() {   # run CMD... : echo, then run unless dry
  echo "+ $*"
  [ "$DRY" = 1 ] && return 0
  "$@"
}

UUID_RE='[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'

echo "== 1. upload $NAME ($(wc -c < "$FILE" | tr -d ' ') bytes)"
if [ "$DRY" = 1 ]; then
  run "$CLI" upload create "$FILE"
  UPLOAD_ID="<upload id>"
else
  OUTPUT="$("$CLI" upload create "$FILE" 2>&1)"
  RC=$?
  echo "$OUTPUT"
  if [ "$RC" -ne 0 ]; then
    echo "higgsfield_cli: upload failed (exit $RC). If it says you are not signed in, run: $CLI auth login" >&2
    exit 1
  fi
  UPLOAD_ID="$(printf '%s\n' "$OUTPUT" | grep -oE "$UUID_RE" | head -1)"
  [ -n "$UPLOAD_ID" ] || { echo "higgsfield_cli: upload finished but no id was printed; see the output above" >&2; exit 1; }
  echo "upload id: $UPLOAD_ID"
fi

if [ "$IS_VIDEO" != 1 ]; then
  echo "upload done (stills are rendered at 4K natively and never go through an upscaler)"
  exit 0
fi

echo "== 2. does this CLI offer a Topaz video upscale?"
if [ -z "$MODEL" ]; then
  if [ "$DRY" = 1 ]; then
    run "$CLI" model list --video
    MODEL="<topaz video model>"
  else
    LIST="$("$CLI" model list --video 2>&1)" || LIST=""
    MODEL="$(printf '%s\n' "$LIST" | grep -oiE '[a-z0-9_.-]*topaz[a-z0-9_.-]*' | grep -iv image | head -1)"
    OTHERS="$(printf '%s\n' "$LIST" | grep -oiE '[a-z0-9_.-]*video_upscale[a-z0-9_.-]*' | sort -u | paste -sd, -)"
    if [ -z "$MODEL" ]; then
      [ -n "$OTHERS" ] && echo "This CLI lists other video upscalers ($OTHERS), but the client chose Topaz; not using them."
      echo "upload done, run the upscale from a Claude session"
      echo "  (MCP: upscale_video {params: {provider: \"topaz\", video_id: <media id>, resolution: \"$RES\", aspect_ratio: \"auto\"}})"
      exit 0
    fi
  fi
fi
echo "Topaz video model: $MODEL"
run "$CLI" model get "$MODEL" || true
echo "== 3. cost (if this CLI can estimate it)"
run "$CLI" generate cost "$MODEL" --video "$UPLOAD_ID" --resolution "$RES" || echo "(no cost estimate from the CLI)"
UPSCALE=("$CLI" generate create "$MODEL" --video "$UPLOAD_ID" --resolution "$RES" --wait)
if [ "$YES" != 1 ]; then
  echo "Not upscaling without --yes. The first paid upscale needs the client's OK; then run:"
  echo "  ${UPSCALE[*]}"
  echo "  (or re-run: $0 $FILE --yes)"
  exit 0
fi
echo "== 4. upscale (approved with --yes)"
if ! run "${UPSCALE[@]}"; then
  echo "higgsfield_cli: the CLI rejected the upscale call. Check the parameters '$CLI model get $MODEL' lists," >&2
  echo "  or run the upscale from a Claude session (upscale_video, provider topaz)." >&2
  exit 1
fi
echo "Record the credits used (Higgsfield account page or a Claude session's 'transactions') in the runbook."
echo "Label the result: upscaled with Topaz (video only)."
