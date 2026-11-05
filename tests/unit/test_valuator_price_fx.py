"""The margin of safety is measured on a price in the valuation currency (#222, ADR 0005).

The newest close is in the listing currency (``prices_daily.currency``); the
intrinsic value is in the valuation currency (the currency of the newest
non-restated ``financials_annual`` row). ``analyze`` converts the close with the
``currencies`` rates on or before its date before every price-based figure.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest
from structlog.testing import capture_logs

from bot.reporting.analysis_report import margin_verdict
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import analyze, bulk_load_valuation_inputs, load_valuation_input
from tests.unit.test_valuator_analysis import _seed

CLOSE_DATE = date(2026, 5, 29)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = connect(":memory:")
    apply_schema(c)
    _seed(c)
    return c


def _eur_reporter(conn: duckdb.DuckDBPyConnection, *, close: float = 110.0) -> None:
    """AAPL reports in EUR and trades at ``close`` USD on the close date."""
    conn.execute("UPDATE financials_annual SET currency = 'EUR' WHERE ticker = 'AAPL'")
    conn.execute("UPDATE prices_daily SET close = ? WHERE ticker = 'AAPL'", [close])


def _rate(conn: duckdb.DuckDBPyConnection, currency: str, day: str, rate: float) -> None:
    conn.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES (?, ?, ?, 'test')",
        [currency, day, rate],
    )


def test_usd_company_unchanged(conn: duckdb.DuckDBPyConnection) -> None:
    analysis = analyze("AAPL", conn)
    assert analysis.fx_rate is None
    assert analysis.listing_price == 150.0
    assert analysis.current_price == 150.0
    assert analysis.valuation_currency == "USD"
    assert analysis.price_currency == "USD"
    assert analysis.price_date == CLOSE_DATE
    assert analysis.margin_of_safety == pytest.approx(
        analysis.intrinsic_value_after_governance / 150.0
    )


def test_eur_company_close_converted(conn: duckdb.DuckDBPyConnection) -> None:
    _eur_reporter(conn)
    _rate(conn, "EUR", "2026-05-29", 1.10)
    analysis = analyze("AAPL", conn)
    assert analysis.current_price == pytest.approx(100.0)
    assert analysis.margin_of_safety == pytest.approx(
        analysis.intrinsic_value_after_governance / 100.0
    )
    assert analysis.listing_price == 110.0
    assert analysis.price_currency == "USD"
    assert analysis.valuation_currency == "EUR"
    assert analysis.fx_rate == pytest.approx(1 / 1.10)
    assert analysis.price_date == CLOSE_DATE
    assert analysis.grid.reference_price == pytest.approx(100.0)
    eps = 100_000.0 / 15_500.0  # 2025 net income / diluted shares, both in millions
    assert analysis.sanity_check.market_pe == pytest.approx(100.0 / eps)


def test_nearest_prior_rate_is_used(conn: duckdb.DuckDBPyConnection) -> None:
    _eur_reporter(conn)
    _rate(conn, "EUR", "2026-05-26", 1.10)
    _rate(conn, "EUR", "2026-05-30", 2.0)
    analysis = analyze("AAPL", conn)
    assert analysis.current_price == pytest.approx(100.0)


def test_no_rate_on_or_before_close_date_gives_no_price(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _eur_reporter(conn)
    _rate(conn, "EUR", "2026-06-01", 1.10)
    with capture_logs() as logs:
        analysis = analyze("AAPL", conn, warned=set())
    assert analysis.current_price is None
    assert analysis.listing_price == 110.0
    assert analysis.fx_rate is None
    assert analysis.margin_of_safety is None
    assert margin_verdict(analysis.margin_of_safety) == "n/a"
    assert all(cell.margin_of_safety is None for row in analysis.grid.cells for cell in row)
    assert analysis.sanity_check.market_pe is None
    missing = [e for e in logs if e["event"] == "analysis.price_fx_missing"]
    assert len(missing) == 1
    assert missing[0]["listing"] == "USD"
    assert missing[0]["valuation"] == "EUR"


def test_null_listing_currency_uses_close(conn: duckdb.DuckDBPyConnection) -> None:
    _eur_reporter(conn)
    conn.execute("UPDATE prices_daily SET currency = NULL WHERE ticker = 'AAPL'")
    analysis = analyze("AAPL", conn)
    assert analysis.current_price == 110.0
    assert analysis.fx_rate is None


def test_analyze_with_preloaded_inputs_converts(conn: duckdb.DuckDBPyConnection) -> None:
    _eur_reporter(conn)
    _rate(conn, "EUR", "2026-05-29", 1.10)
    preloaded = bulk_load_valuation_inputs(conn, ["AAPL"])["AAPL"]
    assert analyze("AAPL", conn, company=preloaded).current_price == pytest.approx(
        analyze("AAPL", conn).current_price
    )


def test_per_ticker_loader_warns_once_per_run(conn: duckdb.DuckDBPyConnection) -> None:
    _eur_reporter(conn)
    warned: set[str | None] = set()
    with capture_logs() as logs:
        load_valuation_input(conn, "AAPL", warned=warned)
        load_valuation_input(conn, "AAPL", warned=warned)
    assert [e["event"] for e in logs].count("analysis.price_fx_missing") == 1


def test_price_as_of_converts_with_the_rate_of_the_bounded_close(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # #225 AC4: the bounded close (110 USD on 05-31) converts at the EUR rate of
    # 05-31 (1.10), not at the newer one of 06-02 (1.20).
    conn.execute("UPDATE financials_annual SET currency = 'EUR' WHERE ticker = 'AAPL'")
    conn.execute("DELETE FROM prices_daily WHERE ticker = 'AAPL'")
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) VALUES "
        "('AAPL', '2026-05-31', 110.0, 'USD', 'fmp'), ('AAPL', '2026-06-02', 132.0, 'USD', 'fmp')"
    )
    _rate(conn, "EUR", "2026-05-31", 1.10)
    _rate(conn, "EUR", "2026-06-02", 1.20)

    bounded = analyze("AAPL", conn, price_as_of=date(2026, 6, 1))
    assert bounded.current_price == pytest.approx(100.0)
    assert bounded.fx_rate == pytest.approx(1 / 1.10)
    assert bounded.price_date == date(2026, 5, 31)

    newest = analyze("AAPL", conn)
    assert newest.current_price == pytest.approx(110.0)
