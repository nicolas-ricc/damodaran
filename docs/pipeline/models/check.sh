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
  # The launcher writes only into a new or empty folder; say so instead of its exit 2.
  if [ -n "$(ls -A "$OUT_DIR/$stem" 2>/dev/null)" ]; then
    errors+=("error  $stem: $OUT_DIR/$stem is not empty; pass a new OUT_DIR")
    continue
  fi
  # The launcher prints its report to stdout; keep that off ours.
  code=0
  "$STATECHART" "$tla" --config "$cfg" --view "$view" --out "$OUT_DIR/$stem" >&2 || code=$?
  if [ ! -f "$report" ]; then
    if [ "$code" -ne 0 ]; then
      errors+=("error  $stem: the launcher failed (exit $code)")
    else
      errors+=("error  $stem: the launcher wrote no report.md")
    fi
    continue
  fi
  if heading="$(grep -E -m1 '^## (.+ breaks|Rules not checked|TLC stopped)$' "$report")"; then
    errors+=("error  $stem: report has '$heading'")
    continue
  fi
  if [ "$code" -ne 0 ]; then
    errors+=("error  $stem: the launcher failed (exit $code)")
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
if [ "$models" -eq 0 ]; then
  errors+=("error  models: no *.tla in $DIR")
fi

if [ "${#errors[@]}" -gt 0 ]; then
  printf '%s\n' "${errors[@]}"
fi
echo "models | $models models, $rules rules, ${#errors[@]} errors"
[ "${#errors[@]}" -eq 0 ]
