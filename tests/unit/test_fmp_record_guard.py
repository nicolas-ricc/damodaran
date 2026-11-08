"""Proves, offline, that re-recording the FMP cassettes without a real key aborts.

A copy of the FMP integration tests and their cassettes runs in a subprocess
with ``--vcr-record=all``. The proxies point at a dead loopback port, so a
request that slipped past the guard would fail instead of reaching FMP.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COPIED = [
    "pyproject.toml",
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/vcr_settings.py",
    "tests/integration/__init__.py",
    "tests/integration/conftest.py",
    "tests/integration/test_fmp_client.py",
]
DEAD_PROXY = "http://127.0.0.1:9"


def _snapshot(cassettes: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(cassettes.iterdir())}


def _record_fmp_client(tmp_path: Path, key: str | None) -> tuple[str, dict[str, bytes], Path]:
    """Run the copied FMP client tests with ``--vcr-record=all``; return stdout and snapshot."""
    for rel in COPIED:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, tmp_path / rel)
    cassettes = tmp_path / "tests" / "fixtures" / "cassettes" / "fmp"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "cassettes" / "fmp", cassettes)
    before = _snapshot(cassettes)

    env = {k: v for k, v in os.environ.items() if k not in {"BOT_FMP_API_KEY", "PYTEST_ADDOPTS"}}
    env |= {"HTTPS_PROXY": DEAD_PROXY, "HTTP_PROXY": DEAD_PROXY}
    if key is not None:
        env["BOT_FMP_API_KEY"] = key
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/test_fmp_client.py",
            "--vcr-record=all",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    return result.stdout, before, cassettes


@pytest.mark.parametrize("key", [None, "test-fmp-key", "  "], ids=["unset", "dummy", "blank"])
def test_record_without_key_aborts_and_keeps_cassettes(tmp_path: Path, key: str | None) -> None:
    stdout, before, cassettes = _record_fmp_client(tmp_path, key)
    assert "BOT_FMP_API_KEY" in stdout
    assert "no FMP cassette was recorded" in stdout
    assert _snapshot(cassettes) == before


def test_record_with_real_key_sends_it_and_never_echoes_it(tmp_path: Path) -> None:
    # The guard lets the run through: requests reach the dead proxy and fail.
    stdout, before, cassettes = _record_fmp_client(tmp_path, "real-key-xyz")
    assert "no FMP cassette was recorded" not in stdout
    assert "ConnectError" in stdout
    assert "real-key-xyz" not in stdout
    assert _snapshot(cassettes) == before
