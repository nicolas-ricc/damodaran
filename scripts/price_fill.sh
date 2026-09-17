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
# Requires BOT_TIINGO_API_KEY and BOT_SEC_USER_AGENT in the checkout's .env.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# cron's PATH is minimal — make sure uv is findable.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:$PATH"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

mkdir -p "$REPO/.cache"
LOG="$REPO/.cache/price_fill.log"
DONE="$REPO/.cache/price_fill.DONE"
[ -f "$DONE" ] && exit 0   # already complete; remove this file to re-fill

echo "=== $(date -Is) run ===" >> "$LOG"
"$UV" run bot refresh --prices --only-missing >> "$LOG" 2>&1

# Fundamentals-covered tickers still lacking any price row.
MISSING=$("$UV" run python - <<'PY' 2>>"$LOG"
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
