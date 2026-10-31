#!/usr/bin/env bash
# Check every TLA+ model in this folder with the statechart launcher.
# Usage: STATECHART=<launcher> TLA2TOOLS=<tla2tools.jar> check.sh OUT_DIR
# JAVA (optional) is passed through to the launcher by the environment.
set -euo pipefail

: "${STATECHART:?STATECHART must be the path of the statechart launcher}"
: "${TLA2TOOLS:?TLA2TOOLS must be the path of tla2tools.jar}"
export TLA2TOOLS
OUT_DIR="${1:-}"
if [ -z "$OUT_DIR" ]; then
  echo "usage: check.sh OUT_DIR" >&2
  exit 2
fi
mkdir -p "$OUT_DIR"

DIR="$(cd "$(dirname "$0")" && pwd)"
errors=()
models=0
rules=0

shopt -s nullglob
for tla in "$DIR"/*.tla; do
  stem="$(basename "$tla" .tla)"
  models=$((models + 1))
  cfg="$DIR/$stem.cfg"
  view="$DIR/$stem.view.js"
  report="$OUT_DIR/$stem/report.md"

  if [ ! -f "$cfg" ]; then
    errors+=("error  $stem: $stem.cfg is missing")
    continue
  fi
  if [ ! -f "$view" ]; then
    errors+=("error  $stem: $stem.view.js is missing")
    continue
  fi
  if ! "$STATECHART" "$tla" --config "$cfg" --view "$view" --out "$OUT_DIR/$stem"; then
    errors+=("error  $stem: the launcher failed")
    continue
  fi
  if [ ! -f "$report" ]; then
    errors+=("error  $stem: the launcher wrote no report.md")
    continue
  fi
  if heading="$(grep -E -m1 '^## (.+ breaks|Rules not checked|TLC stopped)$' "$report")"; then
    errors+=("error  $stem: report has '$heading'")
    continue
  fi
  if ! grep -q '^## Rules that hold$' "$report"; then
    errors+=("error  $stem: report has no '## Rules that hold'")
    continue
  fi
  names="$(awk 'found { print; exit } /^## Rules that hold$/ { found = 1 }' "$report")"
  count="$(printf '%s\n' "$names" | tr ',' '\n' | grep -c '[^[:space:]]' || true)"
  rules=$((rules + count))
done

if [ "${#errors[@]}" -gt 0 ]; then
  printf '%s\n' "${errors[@]}"
fi
echo "models | $models models, $rules rules, ${#errors[@]} errors"
[ "${#errors[@]}" -eq 0 ]
