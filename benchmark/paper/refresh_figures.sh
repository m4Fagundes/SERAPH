#!/usr/bin/env bash
# Refresh paper figures from the latest benchmark outputs.
# Run from the repo root: bash benchmark/paper/refresh_figures.sh
set -euo pipefail
SRC="benchmark/results"
DST="benchmark/paper/figures"
mkdir -p "$DST"
for f in pr_pixel_crossdomain.png cellvit_prob_histogram.png study_3metrics_full.png overlay_oral_protocol.png; do
  if [[ -f "$SRC/$f" ]]; then
    cp -v "$SRC/$f" "$DST/$f"
  else
    echo "WARN: $SRC/$f not found — regenerate it from evaluationMethod/ first." >&2
  fi
done
echo "Done."
