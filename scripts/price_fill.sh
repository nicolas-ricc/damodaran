#!/usr/bin/env bash
# Hourly Tiingo free-tier price drip (ADR 0007).
#
# Tiingo's free tier is rate-capped (~50 requests/hour, 500 unique symbols/
# month), so a full-universe price fill takes several hourly windows. This
# script runs `bot refresh --prices --only-missing` — which skips tickers that
# already have a price, spending no quota on them — so each hourly run advances
# through the unpriced remainder until the whole universe is covered.
#
# Portable: it resolves its own repo root and reads the DB path from settings
# (respecting .env / BOT_DB_PATH), so it works from any checkout, not just the
# worktree it was authored in.
#
# Install (run from your checkout root):
#   ( crontab -l 2>/dev/null; \
#     echo "7 * * * * $(pwd)/scripts/price_fill.sh # bot-price-fill" ) | crontab -
# Watch:   tail -f .cache/price_fill.log
# Remove:  crontab -l | grep -v 'bot-price-fill' | crontab -
#
# The DB section (the refresh and the MISSING query) runs under the shared
# .cache/bot.lock that daily.sh and weekly.sh also take. When another bot run
# holds it, this run logs "skipped: DB busy" and exits 0: skipped, not failed.
# The next hourly run catches up (#108).
#
# Requires BOT_TIINGO_API_KEY and BOT_SEC_USER_AGENT in the checkout's .env.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# cron's PATH is minimal — make sure uv is findable. Appended, so a uv
# already on PATH wins.
export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"

mkdir -p "$REPO/.cache"
LOG="$REPO/.cache/price_fill.log"
DONE="$REPO/.cache/price_fill.DONE"
[ -f "$DONE" ] && exit 0   # already complete; remove this file to re-fill

# Run on the latest origin/master (scripts/sync_master.sh). The pull can rewrite
# this very script, which bash reads as it goes, so re-exec once on the new copy.
if [ -z "${BOT_SYNCED:-}" ]; then
  "$SCRIPT_DIR/sync_master.sh" >> "$LOG" 2>&1
  BOT_SYNCED=1 exec "$SCRIPT_DIR/price_fill.sh" "$@"
fi

echo "=== $(date -Is) run ===" >> "$LOG"

LOCK="$REPO/.cache/bot.lock"
exec 9>>"$LOCK"
if ! flock -n 9; then
  echo "skipped: DB busy ($LOCK is held by another bot run); the next hourly run catches up" >> "$LOG"
  exit 0
fi

uv run bot refresh --prices --only-missing >> "$LOG" 2>&1

# Fundamentals-covered tickers still lacking any price row.
MISSING=$(uv run python - <<'PY' 2>>"$LOG"
import duckdb
from bot.config import load_settings

conn = duckdb.connect(str(load_settings().db_path), read_only=True)
print(
    conn.execute(
        "SELECT COUNT(*) FROM companies co "
        "WHERE NOT EXISTS (SELECT 1 FROM prices_daily p WHERE p.ticker = co.ticker)"
    ).fetchone()[0]
)
PY
)
echo "missing=${MISSING:-?}" >> "$LOG"

if [ "${MISSING:-}" = "0" ]; then
  touch "$DONE"
  echo "=== $(date -Is) FILLED — every universe ticker has a price ===" >> "$LOG"
fi
