"""`scripts/vendor_daisyui.sh` with a fake `curl`: no network (issue #258)."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "vendor_daisyui.sh"
VENDORED = REPO_ROOT / "src" / "bot" / "web" / "static" / "daisyui.css"
PINNED = "6a2cf91a0e9a7da09cf8109c45c3fae171e8967122576043f2b94da47fdf6b64"

# Writes $FAKE_CURL_BODY (a file path) to the argument after `-o`.
_FAKE_CURL = """#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  if [ "$1" = -o ]; then cp "$FAKE_CURL_BODY" "$2"; exit 0; fi
  shift
done
exit 2
"""


def _run(tmp_path: Path, body: Path, out: Path) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(_FAKE_CURL)
    curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_CURL_BODY": str(body),
        "DAISYUI_OUT": str(out),
    }
    return subprocess.run(
        [str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60, check=False
    )


def test_mismatched_download_writes_nothing(tmp_path: Path) -> None:
    body = tmp_path / "body.css"
    body.write_bytes(b"not daisyui")
    out = tmp_path / "daisyui.css"
    out.write_bytes(b"old")
    result = _run(tmp_path, body, out)
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert PINNED in output
    assert hashlib.sha256(b"not daisyui").hexdigest() in output
    assert out.read_bytes() == b"old"


def test_matching_download_writes_the_file(tmp_path: Path) -> None:
    out = tmp_path / "daisyui.css"
    result = _run(tmp_path, VENDORED, out)
    assert result.returncode == 0, result.stderr
    assert out.read_bytes() == VENDORED.read_bytes()
    assert str(out) in result.stdout
