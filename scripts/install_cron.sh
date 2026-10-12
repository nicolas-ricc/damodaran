#!/usr/bin/env bash
# Install the bot's daily and weekly cron jobs, or remove them with --remove.
#
# Each line carries a marker comment (# bot-daily, # bot-weekly), so a second
# install adds nothing and --remove drops exactly those lines; every other
# crontab line is kept as is. Logs land in .cache/daily.log and .cache/weekly.log.
#
# Usage: scripts/install_cron.sh [--remove]
# CRONTAB overrides the crontab command (tests point it at a fake).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
CRONTAB="${CRONTAB:-crontab}"
ERR="$(mktemp)"
trap 'rm -f "$ERR"' EXIT

case "$*" in
  "" | --remove) ;;
  *)
    echo "usage: $0 [--remove]" >&2
    exit 2
    ;;
esac

MARKERS=("# bot-daily" "# bot-weekly")
LINES=(
  "0 9  * * 1-5  $REPO/scripts/daily.sh   # bot-daily"
  "0 10 * * 6    $REPO/scripts/weekly.sh  # bot-weekly"
)

# "no crontab for <user>" means start from an empty one; any other failure to
# read it aborts, so a transient error can never wipe the user's crontab.
if ! current="$("$CRONTAB" -l 2>"$ERR")"; then
  if ! grep -q "no crontab" "$ERR"; then
    echo "install_cron: cannot read the crontab: $(cat "$ERR")" >&2
    exit 1
  fi
  current=""
fi

if [ "${1:-}" = --remove ]; then
  # Commented-out copies of our lines go too; "# bot-daily-old" does not.
  new="$(grep -vE -e "${MARKERS[0]}[[:space:]]*\$" -e "${MARKERS[1]}[[:space:]]*\$" <<<"$current" || true)"
  echo "removed: ${MARKERS[*]}"
else
  new="$current"
  for i in "${!MARKERS[@]}"; do
    # Only an active line counts: a commented-out one is a disabled job.
    if grep -qE -- "^[[:space:]]*[^#[:space:]].*${MARKERS[$i]}[[:space:]]*\$" <<<"$current"; then
      echo "already installed: ${MARKERS[$i]}"
    else
      new="${new:+$new$'\n'}${LINES[$i]}"
      echo "added: ${LINES[$i]}"
    fi
  done
fi

[ "$new" = "$current" ] || printf '%s\n' "$new" | "$CRONTAB" -
