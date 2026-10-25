#!/usr/bin/env bash
# Publish the analysis sidecars (reports/*/analysis/*.json) to origin/master so
# the GitHub Pages viewer rebuilds (`bot site`, .github/workflows/site.yml,
# ADR 0008). Run by scripts/weekly.sh after `bot analyze --from-screen`.
#
# It never commits from this checkout: whatever branch is checked out here, and
# whatever is modified or untracked, stays as it is. Commits go through a
# detached worktree under .cache/site-publish, reset to origin/master on every
# run, into which only the sidecars are copied. Nothing to add -> no commit.
#
# Exit 0 when there is nothing to publish or the push succeeded; the push's exit
# code otherwise (cron has no ssh-agent: the key must work without a passphrase).
set -euo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO"

export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"

REMOTE=origin
BRANCH=master
WORKTREE="$REPO/.cache/site-publish"

mapfile -t sidecars < <(find reports -path 'reports/*/analysis/*.json' -type f 2>/dev/null | sort)
if [ "${#sidecars[@]}" -eq 0 ]; then
  echo "publish_site: no analyses to publish (reports/*/analysis/*.json)"
  exit 0
fi

git fetch -q "$REMOTE" "$BRANCH"
if [ ! -e "$WORKTREE/.git" ]; then
  git worktree prune
  git worktree add -q --detach "$WORKTREE" "$REMOTE/$BRANCH"
fi
# Start from the remote tip: a commit left behind by an earlier failed push is
# rebuilt from the sidecars still on disk, never stacked on.
git -C "$WORKTREE" checkout -q --detach "$REMOTE/$BRANCH"
git -C "$WORKTREE" reset -q --hard
git -C "$WORKTREE" clean -qfd

for f in "${sidecars[@]}"; do
  mkdir -p "$WORKTREE/$(dirname "$f")"
  cp "$f" "$WORKTREE/$f"
done
git -C "$WORKTREE" add -- reports

if git -C "$WORKTREE" diff --cached --quiet; then
  echo "publish_site: no new analyses"
  exit 0
fi

git -C "$WORKTREE" commit -q -m "chore(site): publish analyses $(date +%F)"
if ! git -C "$WORKTREE" push -q "$REMOTE" "HEAD:$BRANCH"; then
  echo "publish_site: push failed (is the SSH key usable without an agent?)" >&2
  exit 1
fi
echo "publish_site: pushed ${#sidecars[@]} sidecar(s) to $REMOTE/$BRANCH"
