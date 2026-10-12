#!/usr/bin/env bash
# Daily cron job (weekdays 09:00, installed by scripts/install_cron.sh):
# refresh prices and FX, then sync the IBKR portfolio. Fundamentals are
# quarterly, so they are refreshed weekly, not here.
#
# Output appends to .cache/daily.log; the exit code is the bot's. `bot
# portfolio` fails while TWS is not running and logged in — that is an
# expected, logged outcome.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# cron's PATH is minimal — make sure uv is findable. Appended, so a uv
# already on PATH wins.
export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"

mkdir -p "$REPO/.cache"
LOG="$REPO/.cache/daily.log"

{
  echo "=== $(date -Is) run ==="
  uv run bot refresh --prices --fx && uv run bot portfolio
} >> "$LOG" 2>&1
