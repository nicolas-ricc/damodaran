#!/usr/bin/env bash
# First-run setup for a checkout: .env, Damodaran benchmarks, health check.
#
# Usage: scripts/bootstrap.sh [--yes] [--skip-damodaran]
#   --yes             never prompt: take missing required keys from the
#                     environment, and exit 1 naming any that is not there.
#   --skip-damodaran  skip `bot refresh --damodaran` (bot doctor then creates the DB).
#
# Safe to re-run: keys already set in .env are never asked for again and the
# file is only rewritten when a value changes. Exit code is `bot doctor`'s, or
# that of a failed `bot refresh --damodaran`, which stops the run.
set -euo pipefail

# Repo root = parent of this script's directory (resolve symlinks).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO"

REQUIRED_KEYS=(BOT_SEC_USER_AGENT BOT_TIINGO_API_KEY)
declare -A HINTS=(
  [BOT_SEC_USER_AGENT]="Your Name you@example.com, required by SEC fair use"
  [BOT_TIINGO_API_KEY]="free token from tiingo.com"
)
YES=0
SKIP_DAMODARAN=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --skip-damodaran) SKIP_DAMODARAN=1 ;;
    *)
      echo "usage: $0 [--yes] [--skip-damodaran]" >&2
      exit 2
      ;;
  esac
done

ENV_FILE="$REPO/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$REPO/.env.example" "$ENV_FILE"
  echo "Created .env from .env.example"
fi

# True when KEY has a non-blank value in .env (last assignment wins, as in
# python-dotenv). Quotes and an unquoted inline comment are not part of it.
is_set() {
  local line value
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1)" || return 1
  value="${line#*=}"
  if [[ $value =~ ^\"([^\"]*)\" || $value =~ ^\'([^\']*)\' ]]; then
    value="${BASH_REMATCH[1]}"
  else
    value="${value%%#*}"
  fi
  [[ -n "${value//[[:space:]]/}" ]]
}

# Sets ANSWER to a non-blank line read from stdin; exits 1 at EOF.
ask() {
  ANSWER=""
  while [ -z "${ANSWER//[[:space:]]/}" ]; do
    printf '%s (%s): ' "$1" "${HINTS[$1]}" >&2
    if ! IFS= read -r ANSWER; then
      echo >&2
      echo "bootstrap: no value given for $1" >&2
      exit 1
    fi
  done
}

declare -A NEW=()
for key in "${REQUIRED_KEYS[@]}"; do
  if is_set "$key"; then
    echo "$key already set in .env — skipping"
  elif [ "$YES" = 1 ]; then
    value="${!key:-}"
    if [ -z "${value//[[:space:]]/}" ]; then
      echo "bootstrap: $key is empty in .env and not set in the environment" >&2
      exit 1
    fi
    NEW[$key]="$value"
  else
    ask "$key"
    NEW[$key]="$ANSWER"
  fi
done

# Rewrite .env with the new values: a KEY= line is replaced in place (its
# inline comment kept), an absent key is appended; every other line is copied.
if [ "${#NEW[@]}" -gt 0 ]; then
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  # The temp copy holds secrets and .gitignore only covers .env itself.
  trap 'rm -f "$tmp"' EXIT
  declare -A written=()
  while IFS= read -r line || [ -n "$line" ]; do
    for key in "${!NEW[@]}"; do
      if [[ $line =~ ^$key=(\"[^\"]*\"|\'[^\']*\'|[^[:space:]#]*)(.*)$ ]]; then
        rest="${BASH_REMATCH[2]}"
        # KEY=#x: python-dotenv only reads '#' as a comment after whitespace.
        [[ $rest == \#* ]] && rest=" $rest"
        value="${NEW[$key]//\\/\\\\}"
        line="$key=\"${value//\"/\\\"}\"$rest"
        written[$key]=1
      fi
    done
    printf '%s\n' "$line"
  done < "$ENV_FILE" > "$tmp"
  for key in "${!NEW[@]}"; do
    if [ -z "${written[$key]:-}" ]; then
      value="${NEW[$key]//\\/\\\\}"
      printf '%s="%s"\n' "$key" "${value//\"/\\\"}" >> "$tmp"
    fi
  done
  mv "$tmp" "$ENV_FILE"
  echo "Wrote ${!NEW[*]} to .env"
fi

# No explicit DB step: refresh --damodaran and doctor both open BOT_DB_PATH and
# apply the schema, so whichever runs first creates the file.
if [ "$SKIP_DAMODARAN" = 0 ]; then
  echo
  echo "Loading Damodaran sector benchmarks (bot refresh --damodaran)..."
  uv run bot refresh --damodaran
else
  echo
  echo "Skipped Damodaran: run \`uv run bot refresh --damodaran\` before screening."
fi

cat <<'EOF'

IBKR portfolio sync (bot portfolio) reads the IBKR Flex Web Service. Bootstrap
does not call it; set it up once:
  1. Account Management: enable the Flex Web Service and copy its token.
  2. Create one Activity Flex Query with five sections: Open Positions,
     Cash Report, Trades, Corporate Actions, Cash Transactions.
  3. In .env set BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID.
  4. Validate the query: uv run bot flex-capture
  5. Then run: uv run bot portfolio

EOF

status=0
uv run bot doctor || status=$?

cat <<'EOF'

Next steps (README -> Quickstart, steps 3-5):
  uv run bot refresh --fundamentals              # the universe, from SEC EDGAR
  uv run bot refresh --prices --only-missing     # Tiingo prices; re-run per hourly window,
                                                 # or arm the scripts/price_fill.sh drip
  uv run bot screen --preset damodaran_value --top 10
  uv run bot analyze --from-screen
Scheduled daily/weekly runs: scripts/install_cron.sh
EOF

exit "$status"
