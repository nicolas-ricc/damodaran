"""Unit tests for the bulk FX refresh orchestrator (M2.5 CLI wiring).

Injected fake importers so no HTTP happens, mirroring ``test_prices_refresh.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

import duckdb
import pytest

from bot.ingest.base import IngestResult
from bot.ingest.universe import distinct_non_usd_currencies, refresh_fx_from_fmp
from bot.storage.db import apply_schema, connect


def _db() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


def _company(conn: duckdb.DuckDBPyConnection, ticker: str, currency: str | None) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, currency, source) VALUES (?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", currency, "fmp"],
    )


def _ok_fx_importer(rows: int = 250) -> Any:
    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        currency: str,
        api_key: str,
        start: Any = None,
        end: Any = None,
    ) -> IngestResult:
        now = datetime.now()
        return IngestResult(
            source="fmp_fx",
            started_at=now,
            finished_at=now,
            status="success",
            rows_affected=rows,
            details={"currency": currency},
        )

    return importer


def test_distinct_non_usd_currencies_excludes_usd() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")
    _company(conn, "NESN", "CHF")
    _company(conn, "SAP", "EUR")
    _company(conn, "BMW", "EUR")  # duplicate EUR
    _company(conn, "NIL", None)
    assert distinct_non_usd_currencies(conn) == ["CHF", "EUR"]


def test_fx_refresh_requests_each_distinct_non_usd_currency() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")
    _company(conn, "NESN", "CHF")
    _company(conn, "SAP", "EUR")
    seen: list[str] = []

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        currency: str,
        api_key: str,
        start: Any = None,
        end: Any = None,
    ) -> IngestResult:
        seen.append(currency)
        return _ok_fx_importer()(conn, currency=currency, api_key=api_key)

    result = refresh_fx_from_fmp(conn, api_key="k", importer=importer)
    assert sorted(seen) == ["CHF", "EUR"]  # USD never requested
    assert result.imported == 2


def test_fx_refresh_all_usd_universe_is_success_with_zero_total() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")
    called = False

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        currency: str,
        api_key: str,
        start: Any = None,
        end: Any = None,
    ) -> IngestResult:
        nonlocal called
        called = True
        return _ok_fx_importer()(conn, currency=currency, api_key=api_key)

    result = refresh_fx_from_fmp(conn, api_key="k", importer=importer)
    assert result.total == 0
    assert result.status == "success"
    assert called is False  # no FMP calls for an all-USD universe


def test_fx_refresh_explicit_currencies_override_derivation() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")  # would derive to [] but we pass an explicit list
    seen: list[str] = []

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        currency: str,
        api_key: str,
        start: Any = None,
        end: Any = None,
    ) -> IngestResult:
        seen.append(currency)
        return _ok_fx_importer()(conn, currency=currency, api_key=api_key)

    refresh_fx_from_fmp(conn, api_key="k", currencies=["JPY", "GBP"], importer=importer)
    assert seen == ["JPY", "GBP"]


def test_fx_refresh_isolates_per_currency_errors() -> None:
    conn = _db()
    _company(conn, "A", "CHF")
    _company(conn, "B", "EUR")
    _company(conn, "C", "GBP")

    def importer(
        conn: duckdb.DuckDBPyConnection,
        *,
        currency: str,
        api_key: str,
        start: Any = None,
        end: Any = None,
    ) -> IngestResult:
        if currency == "EUR":
            raise ValueError("fx down")
        return _ok_fx_importer()(conn, currency=currency, api_key=api_key)

    result = refresh_fx_from_fmp(conn, api_key="k", importer=importer)
    assert result.imported == 2
    assert result.failed == 1
    assert [o.ticker for o in result.failures] == ["EUR"]


def test_fx_refresh_writes_summary_row() -> None:
    conn = _db()
    _company(conn, "NESN", "CHF")
    result = refresh_fx_from_fmp(conn, api_key="k", importer=_ok_fx_importer())
    row = conn.execute(
        "SELECT source, run_id FROM refresh_log WHERE source = 'fmp_fx_universe'"
    ).fetchone()
    assert row is not None
    assert row[0] == "fmp_fx_universe"
    assert row[1] == result.run_id


class _CountingClient:
    instances: ClassVar[list[_CountingClient]] = []

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        _CountingClient.instances.append(self)

    def __enter__(self) -> _CountingClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def close(self) -> None:
        return None

    def historical_fx(
        self, currency: str, *, start: Any = None, end: Any = None
    ) -> list[dict[str, Any]]:
        return []


def test_fx_refresh_uses_one_shared_fmp_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _CountingClient.instances = []
    monkeypatch.setattr("bot.ingest.universe.FmpClient", _CountingClient)
    monkeypatch.setattr("bot.utils.fx.FmpClient", _CountingClient)

    conn = _db()
    _company(conn, "NESN", "CHF")
    _company(conn, "SAP", "EUR")
    refresh_fx_from_fmp(conn, api_key="k")  # real importer path
    assert len(_CountingClient.instances) == 1


def test_fx_refresh_all_usd_constructs_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """An all-USD universe makes no FMP calls — and constructs no client."""
    _CountingClient.instances = []
    monkeypatch.setattr("bot.ingest.universe.FmpClient", _CountingClient)
    monkeypatch.setattr("bot.utils.fx.FmpClient", _CountingClient)

    conn = _db()
    _company(conn, "AAA", "USD")
    result = refresh_fx_from_fmp(conn, api_key="k")  # real importer path
    assert result.total == 0
    assert len(_CountingClient.instances) == 0
