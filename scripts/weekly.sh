#!/usr/bin/env bash
# Weekly cron job (Saturdays 10:00, installed by scripts/install_cron.sh):
# refresh every source, run the Damodaran value screen, analyze its shortlist,
# then publish the analysis sidecars to master so the Pages viewer rebuilds
# (scripts/publish_site.sh). Each step runs only if the previous one succeeded.
#
# Each bot command runs under the shared .cache/bot.lock (#108), waiting up to
# BOT_DB_LOCK_WAIT seconds (default 900) for it; on timeout it fails with a
# logged "lock timeout:" line and exit 75. publish_site.sh runs without the lock.
#
# Output appends to .cache/weekly.log; the exit code is the first failing step's.
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

# Run on the latest origin/master (scripts/sync_master.sh). The pull can rewrite
# this very script, which bash reads as it goes, so re-exec once on the new copy.
if [ -z "${BOT_SYNCED:-}" ]; then
  "$SCRIPT_DIR/sync_master.sh" >> "$LOG" 2>&1
  BOT_SYNCED=1 exec "$SCRIPT_DIR/weekly.sh" "$@"
fi

LOCK="$REPO/.cache/bot.lock"
LOCK_WAIT="${BOT_DB_LOCK_WAIT:-900}"
# A non-numeric wait would make flock fail before it even tries.
[[ "$LOCK_WAIT" =~ ^[0-9]+$ ]] || LOCK_WAIT=900
LOCK_BUSY=75  # EX_TEMPFAIL; bot itself exits 0, 1 or 2

# Run one bot command holding the shared DB lock (#108), waiting up to
# LOCK_WAIT seconds for it. Exits LOCK_BUSY, with a log line, on timeout.
locked() {
  flock -w "$LOCK_WAIT" -E "$LOCK_BUSY" "$LOCK" "$@"
  local status=$?
  ((status != LOCK_BUSY)) || echo "lock timeout: $LOCK still held after ${LOCK_WAIT}s, skipped: $*"
  return "$status"
}

{
  echo "=== $(date -Is) run ==="
  locked uv run bot refresh --all \
    && locked uv run bot screen --preset damodaran_value \
    && locked uv run bot analyze --from-screen \
    && "$SCRIPT_DIR/publish_site.sh"
} >> "$LOG" 2>&1
