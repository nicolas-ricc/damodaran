"""E2E: EDGAR+Stooq fundamentals and prices land in DuckDB through the port.

Mirrors ``tests/e2e/test_pipeline.py``'s pattern of driving the real
``import_company``/``refresh_prices`` orchestration against a fixture-backed
provider, but here the provider is the real :class:`EdgarStooqProvider`
parsing code — HTTP is faked at the transport (``httpx.MockTransport``) via
the handlers already exercised in ``tests/unit/test_edgar_stooq_provider.py``,
reused here rather than copied.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import httpx
import pytest

from bot.ingest.edgar_stooq import EdgarStooqProvider
from bot.ingest.universe import import_company, latest_local_filing_date, refresh_prices
from bot.storage.db import apply_schema, connect
from tests.unit.test_edgar_stooq_provider import _edgar_handler, _stooq_handler


@pytest.fixture()
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    c = connect(tmp_path / "test.duckdb")
    apply_schema(c)
    return c


def _provider() -> EdgarStooqProvider:
    return EdgarStooqProvider(
        sec_user_agent="Test test@example.com",
        sec_transport=httpx.MockTransport(_edgar_handler),
        stooq_transport=httpx.MockTransport(_stooq_handler),
    )


def test_import_company_lands_row_with_damodaran_industry(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    result = import_company(conn, ticker="AAPL", provider=_provider())
    assert result.status == "success"
    row = conn.execute(
        "SELECT name, industry, industry_damodaran, source FROM companies WHERE ticker='AAPL'"
    ).fetchone()
    assert row is not None
    name, industry, industry_damodaran, source = row
    assert name == "Apple Inc."
    assert industry == "Electronic Computers"
    assert source == "edgar_stooq"
    assert industry_damodaran is not None  # Task 4's mapping resolved it
    annual = conn.execute(
        "SELECT revenue FROM financials_annual WHERE ticker='AAPL'"
    ).fetchall()
    assert annual and annual[0][0] == pytest.approx(400000000000)


def test_import_company_populates_the_edgar_stooq_watermark(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The incremental-skip logic in universe._refresh_one reads

    ``latest_local_filing_date(conn, sym, provider.name)`` i.e. source
    "edgar_stooq" (not "sec_edgar"). Filings must land stamped with the
    provider's own name so a later ``refresh --fundamentals`` run can find
    this watermark and skip re-importing an unchanged ticker.
    """
    import_company(conn, ticker="AAPL", provider=_provider())
    watermark = latest_local_filing_date(conn, "AAPL", "edgar_stooq")
    assert watermark is not None


def test_refresh_prices_lands_stooq_bars(conn: duckdb.DuckDBPyConnection) -> None:
    import_company(conn, ticker="AAPL", provider=_provider())
    result = refresh_prices(conn, tickers=["AAPL"], provider=_provider())
    assert result.failed == 0, result.outcomes
    n = conn.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()
    assert n is not None and n[0] == 3
