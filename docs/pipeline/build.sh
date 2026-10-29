#!/usr/bin/env bash
# Renders every board (*.d2 except classes.d2) to SVG and PNG with the pinned d2,
# then writes rendered.sha256, the hash of the sources that were rendered.
set -euo pipefail
export LC_ALL=C
cd "$(dirname "$0")"

pinned="$(cat D2_VERSION)"
pinned="${pinned#v}"

if ! command -v d2 >/dev/null; then
    echo "build.sh: d2 is not on PATH. Install d2 v${pinned} (https://d2lang.com/install.sh --version v${pinned}) or let the pipeline-diagram workflow render." >&2
    exit 1
fi

version_re='v?([0-9]+\.[0-9]+\.[0-9]+)'
found=""
if [[ "$(d2 version)" =~ $version_re ]]; then
    found="${BASH_REMATCH[1]}"
fi
if [[ "$found" != "$pinned" ]]; then
    echo "build.sh: found d2 ${found:-of unknown version}, but D2_VERSION pins ${pinned}. Install d2 v${pinned} or let the pipeline-diagram workflow render." >&2
    exit 1
fi

for src in *.d2; do
    [[ "$src" == classes.d2 ]] && continue
    stem="${src%.d2}"
    for ext in svg png; do
        d2 --layout tala --tala-seeds "${TALA_SEEDS:-1}" "$src" "$stem.$ext"
    done
done

cat ./*.d2 | sha256sum | cut -d' ' -f1 > rendered.sha256
