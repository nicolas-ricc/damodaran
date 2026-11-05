#!/usr/bin/env bash
# Bring this checkout up to origin/master before a scheduled run, so the cron
# jobs (daily.sh, weekly.sh, price_fill.sh) always run the latest merged code.
#
# Fast-forward only: it never merges, rebases or discards anything. It skips,
# with a logged line, when the checkout is not a git repository or is on a
# branch other than master (work in progress is left alone). A failed fetch or
# a non-fast-forward exits non-zero; callers log it and run the code they have.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

REMOTE=origin
BRANCH=master

echo "=== $(date -Is) sync ==="
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "sync_master: not a git checkout, skipped"
  exit 0
fi
current="$(git symbolic-ref --quiet --short HEAD || echo "(detached)")"
if [ "$current" != "$BRANCH" ]; then
  echo "sync_master: on $current, not $BRANCH, skipped"
  exit 0
fi

before="$(git rev-parse HEAD)"
if ! git pull -q --ff-only "$REMOTE" "$BRANCH"; then
  echo "sync_master: pull failed, running the code already checked out" >&2
  exit 1
fi
echo "sync_master: $BRANCH ${before:0:7} -> $(git rev-parse --short HEAD)"
