#!/usr/bin/env bash
# Prepares a fresh clone of this repository for the factory agent.
# Runs as root inside the factory container, in the repository root, before
# the agent starts. If it fails, the run fails.
set -euo pipefail

# The runner image has python3 and node but no uv. uv downloads the Python
# pinned by pyproject (>=3.12) on its own if the system one does not match.
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
uv sync --frozen

# d2 renders docs/pipeline. Best effort: without it the pipeline-diagram workflow renders.
# The standalone release installs through `make install`, and the image has no make.
command -v make >/dev/null || { apt-get update -qq && apt-get install -y -qq make >/dev/null; }
if ! command -v d2 >/dev/null && ! curl -fsSL https://d2lang.com/install.sh | sh -s -- --version "$(cat docs/pipeline/D2_VERSION)" --method standalone --prefix /usr/local; then
  echo "d2 not installed; the pipeline-diagram workflow renders instead"
fi
