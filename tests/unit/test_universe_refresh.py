"""Unit tests for the bulk universe refresh orchestrator (M2.6).

These exercise the orchestration logic — universe parsing, incremental skip via
``filings_log``, per-ticker error isolation, status thresholds, progress logging
and the ``refresh_log`` summary — with injected fakes so no HTTP happens.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from bot.ingest.base import IngestResult
from bot.ingest.universe import (
    TickerOutcome,
    default_universe_path,
    latest_local_filing_date,
    load_universe,
    refresh_universe_from_fmp,
)
from bot.storage.db import apply_schema, connect


def _db() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


def _ok_importer(rows: int = 5) -> Any:
    def importer(conn: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> IngestResult:
        now = datetime.now()
        return IngestResult(
            source="fmp",
            started_at=now,
            finished_at=now,
            status="success",
            rows_affected=rows,
            details={"ticker": ticker},
        )

    return importer


# ---------- universe parsing ----------


def test_load_universe_parses_ticker_column(tmp_path: Path) -> None:
    f = tmp_path / "u.csv"
    f.write_text("ticker,name\nAAPL,Apple\nmsft,Microsoft\nNESN.SW,Nestle\n")
    assert load_universe(f) == ["AAPL", "MSFT", "NESN.SW"]


def test_load_universe_skips_blanks_dupes_and_comments(tmp_path: Path) -> None:
    f = tmp_path / "u.csv"
    f.write_text("# a comment\nticker\nAAPL\n\nAAPL\n  msft  \n")
    assert load_universe(f) == ["AAPL", "MSFT"]


def test_load_universe_first_column_without_header(tmp_path: Path) -> None:
    f = tmp_path / "u.csv"
    f.write_text("AAPL\nMSFT\n")
    assert load_universe(f) == ["AAPL", "MSFT"]


def test_default_universe_ships_and_is_sizeable() -> None:
    tickers = load_universe(default_universe_path())
    assert len(tickers) >= 400
    assert "AAPL" in tickers
    # Contains international FMP-suffixed symbols, not just US.
    assert any("." in t for t in tickers)
    assert len(set(tickers)) == len(tickers)  # de-duplicated


# ---------- incremental skip ----------


def test_skips_ticker_when_remote_filing_not_advanced() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('AAPL', 'FY', '2023-11-03', 'fmp')"
    )
    calls: list[str] = []

    def importer(c: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> IngestResult:
        calls.append(ticker)
        return _ok_importer()(c, ticker=ticker, api_key=api_key)

    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAPL"],
        importer=importer,
        latest_filing_probe=lambda _t: date(2023, 11, 3),
    )
    assert calls == []  # importer never invoked
    assert result.skipped == 1
    assert result.imported == 0
    assert result.status == "success"


def test_imports_when_remote_filing_advanced() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('AAPL', 'FY', '2023-11-03', 'fmp')"
    )
    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAPL"],
        importer=_ok_importer(),
        latest_filing_probe=lambda _t: date(2024, 11, 1),
    )
    assert result.imported == 1
    assert result.skipped == 0


def test_imports_when_no_local_filing_history() -> None:
    conn = _db()
    # Probe would say "unchanged", but with no local history we must import.
    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAPL"],
        importer=_ok_importer(),
        latest_filing_probe=lambda _t: date(2020, 1, 1),
    )
    assert result.imported == 1


def test_probe_failure_falls_through_to_import() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('AAPL', 'FY', '2023-11-03', 'fmp')"
    )

    def boom(_t: str) -> date | None:
        raise RuntimeError("FMP down")

    result = refresh_universe_from_fmp(
        conn, api_key="k", tickers=["AAPL"], importer=_ok_importer(), latest_filing_probe=boom
    )
    assert result.imported == 1
    assert result.failed == 0


def test_latest_local_filing_date_reads_max() -> None:
    conn = _db()
    for d in ("2022-11-01", "2023-11-03", "2021-10-29"):
        conn.execute(
            "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
            "VALUES ('AAPL', 'FY', ?, 'fmp')",
            [d],
        )
    assert latest_local_filing_date(conn, "aapl") == date(2023, 11, 3)
    assert latest_local_filing_date(conn, "MSFT") is None


# ---------- error isolation + status thresholds ----------


def test_per_ticker_error_is_isolated_not_fatal() -> None:
    conn = _db()

    def importer(c: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> IngestResult:
        if ticker == "BAD":
            raise ValueError("kaboom")
        return _ok_importer()(c, ticker=ticker, api_key=api_key)

    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAPL", "BAD", "MSFT"],
        importer=importer,
        latest_filing_probe=lambda _t: None,
    )
    assert result.imported == 2
    assert result.failed == 1
    assert [o.ticker for o in result.failures] == ["BAD"]
    assert result.failures[0].error_message == "kaboom"


def test_non_success_result_counts_as_failure() -> None:
    conn = _db()

    def importer(c: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> IngestResult:
        now = datetime.now()
        return IngestResult(
            source="fmp",
            started_at=now,
            finished_at=now,
            status="error",
            error_message="profile not found",
            details={"ticker": ticker},
        )

    result = refresh_universe_from_fmp(
        conn, api_key="k", tickers=["NOPE"], importer=importer, latest_filing_probe=lambda _t: None
    )
    assert result.failed == 1
    assert result.failures[0].error_message == "profile not found"


@pytest.mark.parametrize(
    ("n_fail", "n_total", "expected"),
    [
        (0, 20, "success"),
        (1, 20, "success"),  # 5% -> success boundary
        (2, 20, "partial"),  # 10% -> partial
        (5, 20, "partial"),  # 25% -> partial boundary
        (6, 20, "error"),  # 30% -> error
    ],
)
def test_status_thresholds(n_fail: int, n_total: int, expected: str) -> None:
    conn = _db()
    fail_set = {f"F{i}" for i in range(n_fail)}

    def importer(c: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> IngestResult:
        if ticker in fail_set:
            raise ValueError("fail")
        return _ok_importer()(c, ticker=ticker, api_key=api_key)

    tickers = [f"F{i}" for i in range(n_fail)] + [
        f"OK{i}" for i in range(n_total - n_fail)
    ]
    result = refresh_universe_from_fmp(
        conn, api_key="k", tickers=tickers, importer=importer, latest_filing_probe=lambda _t: None
    )
    assert result.total == n_total
    assert result.failed == n_fail
    assert result.status == expected


def test_empty_universe_is_success_with_zero_total() -> None:
    conn = _db()
    result = refresh_universe_from_fmp(
        conn, api_key="k", tickers=[], importer=_ok_importer(), latest_filing_probe=lambda _t: None
    )
    assert result.total == 0
    assert result.status == "success"
    assert result.failure_rate == 0.0


# ---------- progress logging + refresh_log ----------


def test_progress_logged_every_n(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _db()
    events: list[tuple[str, dict[str, Any]]] = []

    import bot.ingest.universe as mod

    class _Recorder:
        def info(self, event: str, **kw: Any) -> None:
            events.append((event, kw))

        def warning(self, event: str, **kw: Any) -> None:
            events.append((event, kw))

        def exception(self, event: str, **kw: Any) -> None:
            events.append((event, kw))

    monkeypatch.setattr(mod, "log", _Recorder())

    refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=[f"T{i}" for i in range(5)],
        importer=_ok_importer(),
        latest_filing_probe=lambda _t: None,
        progress_every=2,
    )
    progress = [e for e in events if e[0] == "universe.refresh.progress"]
    # 5 tickers, every 2 -> logged at 2 and 4.
    assert [e[1]["processed"] for e in progress] == [2, 4]


def test_writes_refresh_log_summary_row() -> None:
    conn = _db()

    def importer(c: duckdb.DuckDBPyConnection, *, ticker: str, api_key: str) -> IngestResult:
        if ticker == "BAD":
            raise ValueError("kaboom")
        return _ok_importer()(c, ticker=ticker, api_key=api_key)

    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAPL", "BAD"],
        importer=importer,
        latest_filing_probe=lambda _t: None,
    )
    row = conn.execute(
        "SELECT source, run_id, status, rows_affected, error_message "
        "FROM refresh_log WHERE source = 'fmp_universe'"
    ).fetchone()
    assert row is not None
    source, run_id, _status, rows_affected, error_message = row
    assert source == "fmp_universe"
    assert run_id == result.run_id
    assert rows_affected == 1  # imported count (AAPL)
    assert error_message is not None
    assert "BAD" in error_message


def test_outcome_dataclass_shape() -> None:
    o = TickerOutcome(ticker="AAPL", status="imported", rows_affected=5)
    assert o.ticker == "AAPL"
    assert o.error_message is None
