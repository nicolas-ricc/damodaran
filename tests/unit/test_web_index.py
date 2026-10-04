"""Scanning ``reports/*/analysis/*.json`` into companies (issue #92)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from bot.web.index import TICKER_RE, read_sidecar, scan
from structlog.testing import capture_logs


def _write(reports: Path, day: str, ticker: str, payload: Any = None) -> Path:
    out = reports / day / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    if payload is None:
        payload = {
            "schema_version": 1,
            "generated_on": day,
            "verdict": "n/a",
            "analysis": {"ticker": ticker},
        }
    path = out / f"{ticker}.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return path


def test_latest_wins_and_history_is_newest_first(tmp_path: Path) -> None:
    _write(tmp_path, "2026-09-01", "AAPL")
    _write(tmp_path, "2026-10-01", "AAPL")
    _write(tmp_path, "2026-09-15", "MSFT")

    entries = scan(tmp_path)

    assert [e.ticker for e in entries] == ["AAPL", "MSFT"]
    aapl = entries[0]
    assert aapl.latest.date == date(2026, 10, 1)
    assert [r.date for r in aapl.history] == [date(2026, 10, 1), date(2026, 9, 1)]
    assert aapl.latest.data["analysis"]["ticker"] == "AAPL"


def test_malformed_json_is_skipped_with_a_warning(tmp_path: Path) -> None:
    _write(tmp_path, "2026-10-01", "BAD", "{not json")
    _write(tmp_path, "2026-10-01", "GOOD")

    with capture_logs() as logs:
        entries = scan(tmp_path)

    assert [e.ticker for e in entries] == ["GOOD"]
    assert any(log["event"] == "web.sidecar_skipped" for log in logs)


def test_unknown_schema_version_is_skipped(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "2026-10-01",
        "NEW",
        {"schema_version": 2, "verdict": "n/a", "analysis": {"ticker": "NEW"}},
    )
    with capture_logs() as logs:
        assert scan(tmp_path) == []
        assert read_sidecar(path) is None
    assert any(log["event"] == "web.sidecar_skipped" for log in logs)


def test_non_object_json_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "2026-10-01", "LIST", [])
    assert scan(tmp_path) == []


def test_non_date_folder_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "latest", "AAPL")
    assert scan(tmp_path) == []


def test_invalid_ticker_stems_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "2026-10-01", "aapl")
    _write(tmp_path, "2026-10-01", "TOO-LONG-TICKER1")
    _write(tmp_path, "2026-10-01", "A B")
    assert scan(tmp_path) == []


def test_ticker_mismatch_between_stem_and_payload_is_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "2026-10-01",
        "AAPL",
        {"schema_version": 1, "verdict": "n/a", "analysis": {"ticker": "MSFT"}},
    )
    assert scan(tmp_path) == []


def test_dotted_and_dashed_tickers_are_accepted(tmp_path: Path) -> None:
    _write(tmp_path, "2026-10-01", "BRK.B")
    _write(tmp_path, "2026-10-01", "BRK-B")
    assert [e.ticker for e in scan(tmp_path)] == ["BRK-B", "BRK.B"]
    assert TICKER_RE.match("BRK.B")
    assert not TICKER_RE.match("../X")


def test_missing_and_empty_reports_dir(tmp_path: Path) -> None:
    assert scan(tmp_path / "nope") == []
    assert scan(tmp_path) == []
