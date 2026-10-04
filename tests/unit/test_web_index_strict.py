"""Strict ticker and folder-name validation for the web index (issue #92)."""

from __future__ import annotations

import json
from pathlib import Path

from bot.web.index import scan


def _write(reports: Path, day: str, stem: str, ticker: str) -> None:
    out = reports / day / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "verdict": "n/a", "analysis": {"ticker": ticker}}
    (out / f"{stem}.json").write_text(json.dumps(payload))


def test_stem_with_trailing_newline_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "2026-10-01", "AAPL\n", "AAPL\n")
    assert scan(tmp_path) == []


def test_compact_date_folder_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "20261004", "AAPL", "AAPL")
    assert scan(tmp_path) == []
