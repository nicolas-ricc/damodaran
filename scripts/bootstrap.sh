#!/usr/bin/env bash
# First-run setup for a checkout: .env, Damodaran benchmarks, health check.
#
# Usage: scripts/bootstrap.sh [--yes] [--skip-damodaran]
#   --yes             never prompt: take missing required keys from the
#                     environment, and exit 1 naming any that is not there.
#   --skip-damodaran  skip `bot refresh --damodaran` (bot doctor then creates the DB).
#
# Safe to re-run: keys already set in .env are never asked for again and the
# file is only rewritten when a value changes. Exit code is `bot doctor`'s.
# shellcheck disable=SC2034  # SKIP_DAMODARAN is consumed by the setup steps added later
set -euo pipefail

# Repo root = parent of this script's directory (resolve symlinks).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO"

REQUIRED_KEYS=(BOT_SEC_USER_AGENT BOT_TIINGO_API_KEY)
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

# Sets ANSWER to a non-empty line read from stdin; exits 1 at EOF.
ask() {
  ANSWER=""
  while [ -z "$ANSWER" ]; do
    printf '%s: ' "$1" >&2
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
    if [ -z "${!key:-}" ]; then
      echo "bootstrap: $key is empty in .env and not set in the environment" >&2
      exit 1
    fi
    NEW[$key]="${!key}"
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
      if [[ $line =~ ^$key=(\"[^\"]*\"|\'[^\']*\'|[^#]*)(.*)$ ]]; then
        rest="${BASH_REMATCH[2]}"
        # An unquoted value's [^#]* ate the spaces before '#'; dotenv needs one.
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

exit 0
