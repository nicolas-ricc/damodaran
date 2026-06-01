"""Unit tests for the bulk price refresh orchestrator (M2.4 CLI wiring).

Exercise the loop/aggregate/refresh_log behaviour with injected fake importers so
no HTTP happens, mirroring ``test_universe_refresh.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import duckdb
import pytest

from bot.ingest.base import IngestResult
from bot.ingest.universe import refresh_prices_from_fmp
from bot.storage.db import apply_schema, connect


def _db() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


def _seed_company(conn: duckdb.DuckDBPyConnection, ticker: str, currency: str | None) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, currency, source) VALUES (?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", currency, "fmp"],
    )


def _ok_price_importer(rows: int = 10) -> Any:
    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        ticker: str,
        api_key: str,
        since_date: Any = None,
        currency: str | None = None,
    ) -> IngestResult:
        now = datetime.now()
        return IngestResult(
            source="fmp_prices",
            started_at=now,
            finished_at=now,
            status="success",
            rows_affected=rows,
            details={"ticker": ticker, "currency": currency},
        )

    return importer


def test_price_refresh_passes_each_tickers_currency() -> None:
    conn = _db()
    _seed_company(conn, "AAA", "USD")
    _seed_company(conn, "NESN", "CHF")
    seen: dict[str, str | None] = {}

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        ticker: str,
        api_key: str,
        since_date: Any = None,
        currency: str | None = None,
    ) -> IngestResult:
        seen[ticker] = currency
        return _ok_price_importer()(conn, ticker=ticker, api_key=api_key, currency=currency)

    result = refresh_prices_from_fmp(conn, api_key="k", tickers=["AAA", "NESN"], importer=importer)
    assert result.imported == 2
    assert result.failed == 0
    assert seen == {"AAA": "USD", "NESN": "CHF"}


def test_price_refresh_ticker_without_company_uses_none_currency() -> None:
    conn = _db()
    seen: dict[str, str | None] = {}

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        ticker: str,
        api_key: str,
        since_date: Any = None,
        currency: str | None = None,
    ) -> IngestResult:
        seen[ticker] = currency
        return _ok_price_importer()(conn, ticker=ticker, api_key=api_key, currency=currency)

    # No companies row for NOPE → currency None, still imported (not a failure).
    result = refresh_prices_from_fmp(conn, api_key="k", tickers=["NOPE"], importer=importer)
    assert seen == {"NOPE": None}
    assert result.imported == 1
    assert result.failed == 0


def test_price_refresh_isolates_per_ticker_errors() -> None:
    conn = _db()
    for t in ("AAA", "BBB"):
        _seed_company(conn, t, "USD")

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        ticker: str,
        api_key: str,
        since_date: Any = None,
        currency: str | None = None,
    ) -> IngestResult:
        if ticker == "BAD":
            raise ValueError("kaboom")
        return _ok_price_importer()(conn, ticker=ticker, api_key=api_key)

    result = refresh_prices_from_fmp(
        conn, api_key="k", tickers=["AAA", "BAD", "BBB"], importer=importer
    )
    assert result.imported == 2
    assert result.failed == 1
    assert [o.ticker for o in result.failures] == ["BAD"]
    assert result.failures[0].error_message == "kaboom"


def test_price_refresh_writes_summary_row() -> None:
    conn = _db()
    _seed_company(conn, "AAA", "USD")
    result = refresh_prices_from_fmp(
        conn, api_key="k", tickers=["AAA"], importer=_ok_price_importer()
    )
    row = conn.execute(
        "SELECT source, run_id, rows_affected FROM refresh_log WHERE source = 'fmp_prices_universe'"
    ).fetchone()
    assert row is not None
    assert row[0] == "fmp_prices_universe"
    assert row[1] == result.run_id
    assert row[2] == result.imported


def test_price_refresh_empty_universe_is_success() -> None:
    conn = _db()
    result = refresh_prices_from_fmp(conn, api_key="k", tickers=[], importer=_ok_price_importer())
    assert result.total == 0
    assert result.status == "success"


class _CountingClient:
    """Stub FmpClient that counts constructions and returns empty payloads."""

    instances: ClassVar[list[_CountingClient]] = []

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        _CountingClient.instances.append(self)

    def __enter__(self) -> _CountingClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def close(self) -> None:
        return None

    def historical_prices(
        self, ticker: str, *, start: Any = None, end: Any = None
    ) -> list[dict[str, Any]]:
        return []


def test_price_refresh_uses_one_shared_fmp_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real FMP path opens a single FmpClient for the whole run, not one per
    ticker."""
    _CountingClient.instances = []
    monkeypatch.setattr("bot.ingest.universe.FmpClient", _CountingClient)
    monkeypatch.setattr("bot.ingest.fmp.FmpClient", _CountingClient)

    conn = _db()
    for t in ("AAA", "BBB"):
        _seed_company(conn, t, "USD")
    # Default importer (real path) → empty payloads, zero rows, but one client.
    refresh_prices_from_fmp(conn, api_key="k", tickers=["AAA", "BBB"])

    assert len(_CountingClient.instances) == 1
