#!/usr/bin/env bash
# Vendor DaisyUI's stylesheet into src/bot/web/static/daisyui.css.
#
# Upgrade: edit DAISYUI_VERSION and DAISYUI_SHA256 below, run this script, then
# edit the daisyui line in src/bot/web/static/VERSIONS. The download is checked
# against the pinned SHA-256 and nothing is written on a mismatch.
# DAISYUI_OUT overrides the output path (used by tests).
set -euo pipefail

DAISYUI_VERSION="5.7.50"
DAISYUI_SHA256="6a2cf91a0e9a7da09cf8109c45c3fae171e8967122576043f2b94da47fdf6b64"

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
OUT="${DAISYUI_OUT:-$REPO/src/bot/web/static/daisyui.css}"
VERSION="${1:-$DAISYUI_VERSION}"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl -fsSL "https://cdn.jsdelivr.net/npm/daisyui@${VERSION}/daisyui.css" -o "$tmp"
actual="$(sha256sum "$tmp" | cut -d' ' -f1)"
if [ "$actual" != "$DAISYUI_SHA256" ]; then
  echo "expected $DAISYUI_SHA256" >&2
  echo "actual   $actual" >&2
  exit 1
fi
cp "$tmp" "$OUT"
echo "$OUT"
