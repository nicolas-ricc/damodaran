"""Only the analysis JSON sidecars under ``reports/`` are committable (issue #92)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


def _ignored(relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative],
        cwd=_REPO,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        "reports/2026-10-01/analysis/AAPL.md",
        "reports/2026-10-01/analysis/AAPL.html",
        "reports/2026-10-01/screen/damodaran_value.md",
        "reports/2026-10-01/screen/damodaran_value.csv",
        "reports/notes.txt",
    ],
)
def test_reports_stay_ignored(path: str) -> None:
    assert _ignored(path)


def test_analysis_sidecar_is_not_ignored() -> None:
    assert not _ignored("reports/2026-10-01/analysis/AAPL.json")
