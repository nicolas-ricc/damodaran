#!/usr/bin/env bash
# Weekly cron job (Saturdays 10:00, installed by scripts/install_cron.sh):
# refresh every source, then run the Damodaran value screen.
#
# Output appends to .cache/weekly.log; the exit code is the bot's.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# cron's PATH is minimal — make sure uv is findable. Appended, so a uv
# already on PATH wins.
export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"

mkdir -p "$REPO/.cache"
LOG="$REPO/.cache/weekly.log"

{
  echo "=== $(date -Is) run ==="
  uv run bot refresh --all && uv run bot screen --preset damodaran_value
} >> "$LOG" 2>&1
