#!/usr/bin/env bash
# Daily cron job (weekdays 09:00, installed by scripts/install_cron.sh):
# refresh prices and FX, then sync the IBKR portfolio. Fundamentals are
# quarterly, so they are refreshed weekly, not here.
#
# Tiingo's free tier allows ~50 requests/hour, so one price run cannot cover the
# universe: it refreshes stalest-first, skips tickers already up to date, and
# defers the rest. The loop below re-runs it, one separate process per round so
# the DuckDB lock is released between rounds (#108), until nothing is deferred
# or BOT_PRICE_ROUNDS is reached; BOT_PRICE_RETRY_PAUSE seconds between rounds.
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

ROUNDS="${BOT_PRICE_ROUNDS:-12}"
PAUSE="${BOT_PRICE_RETRY_PAUSE:-3600}"

# Refresh prices until no tickers are deferred. Returns the failing round's
# exit code; running out of rounds is not a failure.
refresh_prices() {
  local round out status
  for ((round = 1; round <= ROUNDS; round++)); do
    out="$(uv run bot refresh --prices 2>&1)"
    status=$?
    echo "$out"
    ((status == 0)) || return "$status"
    [[ "$out" == *"tickers deferred"* ]] || return 0
    ((round < ROUNDS)) && sleep "$PAUSE"
  done
  return 0
}

{
  echo "=== $(date -Is) run ==="
  refresh_prices && uv run bot refresh --fx && uv run bot portfolio
} >> "$LOG" 2>&1
