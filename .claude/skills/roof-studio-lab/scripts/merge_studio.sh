#!/usr/bin/env bash
# Merge a newer original-studio build into the lab, file by file.
#   merge_studio.sh BASE NEW LAB
#   BASE = the studio build the lab was made from, NEW = the newer studio build, LAB = the lab site (out/)
# Files only the studio changed are copied from NEW; files both changed are 3-way merged into LAB with
# `git merge-file` (conflict markers left in place: resolve by hand). Before anything, LAB is copied to
# LAB.before-merge. Nothing is deleted from LAB.
set -euo pipefail
BASE=$1; NEW=$2; LAB=$3
[ -d "$BASE" ] && [ -d "$NEW" ] && [ -d "$LAB" ] || { echo "usage: $0 BASE NEW LAB" >&2; exit 2; }
rm -rf "$LAB.before-merge"; cp -r "$LAB" "$LAB.before-merge"
conflicts=0
while IFS= read -r -d '' f; do
  f=${f#"$NEW"/}
  if [ ! -f "$BASE/$f" ]; then
    if [ -f "$LAB/$f" ] && ! cmp -s "$NEW/$f" "$LAB/$f"; then echo "ADDED-BOTH (check by hand): $f"; continue; fi
    mkdir -p "$(dirname "$LAB/$f")"; cp "$NEW/$f" "$LAB/$f"; echo "new:      $f"; continue
  fi
  cmp -s "$BASE/$f" "$NEW/$f" && continue                       # studio did not change it
  if cmp -s "$BASE/$f" "$LAB/$f"; then cp "$NEW/$f" "$LAB/$f"; echo "theirs:   $f"; continue; fi
  if git merge-file -L lab -L base -L studio "$LAB/$f" "$BASE/$f" "$NEW/$f"; then echo "merged:   $f"
  else n=$?; conflicts=$((conflicts + n)); echo "CONFLICT: $f ($n)"; fi
done < <(find "$NEW" -type f -print0)
while IFS= read -r -d '' f; do
  f=${f#"$BASE"/}; [ -f "$NEW/$f" ] || echo "REMOVED in the new studio (left in LAB, check): $f"
done < <(find "$BASE" -type f -print0)
echo "conflict hunks: $conflicts"
