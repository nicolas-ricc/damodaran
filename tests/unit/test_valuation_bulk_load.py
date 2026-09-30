"""Set-based valuation-input loaders (#53, the screener second-pass N+1).

``bulk_load_valuation_inputs`` / ``bulk_load_assumption_inputs`` load a whole
shortlist with a fixed number of scans. They must return exactly what the
per-ticker loaders return, one ticker at a time, for every edge case the
per-ticker SQL handles (restated rows, NULL revenues, missing Damodaran rows,
the cross-region sector fallback, missing prices).
"""

from __future__ import annotations

from collections.abc import Sequence

import duckdb
import pytest
from structlog.testing import capture_logs

from bot.storage.db import apply_schema
from bot.valuator.analysis import bulk_load_valuation_inputs, load_valuation_input
from bot.valuator.assumptions import bulk_load_assumption_inputs, load_assumption_inputs
from tests.counting_conn import CountingConn

#: ``(fiscal_year, revenue, ebit, is_restated)``
type _Year = tuple[int, float | None, float | None, bool]

_SIX_YEARS: tuple[_Year, ...] = tuple(
    (2020 + i, 1_000.0 * 1.1**i, 200.0 * 1.1**i, False) for i in range(6)
)

#: Tickers with a companies row and at least one non-restated annual row.
VALUABLE = (
    "USA",
    "DEU",
    "NOCTRY",
    "ATL",
    "NOIND",
    "BARE",
    "ZEROREV",
    "ONEYR",
    "NULLREV",
    "RESTATED",
    "OOO",
    "NOPRICE",
    "NULLCLOSE",
)
#: Tickers the bulk loaders must leave out: a companies row without financials,
#: and a ticker that is not in companies at all.
ABSENT = ("NOFIN", "UNKNOWN")


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _company(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    country: str | None = "United States",
    industry: str | None = "Software",
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Inc", country, "USD", industry, "test"],
    )


def _financials(
    conn: duckdb.DuckDBPyConnection, ticker: str, years: Sequence[_Year] = _SIX_YEARS
) -> None:
    for year, revenue, ebit, restated in years:
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, total_debt, "
            "cash, shares_diluted, total_equity, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [ticker, year, revenue, ebit, 100.0, 10.0, 300.0, 50.0, 100.0, 900.0, restated, "t"],
        )


def _price(
    conn: duckdb.DuckDBPyConnection, ticker: str, day: str, close: float | None
) -> None:
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) VALUES (?, ?, ?, ?, ?)",
        [ticker, day, close, "USD", "test"],
    )


def _country(
    conn: duckdb.DuckDBPyConnection, country: str, year: int, region: str, rate: float
) -> None:
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region, risk_free_rate, erp, tax_rate) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [country, year, region, rate, rate + 0.01, 0.21],
    )


def _industry(
    conn: duckdb.DuckDBPyConnection, industry: str, region: str, year: int, margin: float
) -> None:
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, pe, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, sales_to_capital, tax_rate, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [industry, region, year, 0.08, 20.0, 0.09, 0.045, 1.05, 0.2, margin, 2.5, 0.21, 5.0],
    )


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    # Two years per Damodaran key, so "latest year" is exercised.
    _country(conn, "United States", 2025, "North America", 0.03)
    _country(conn, "United States", 2026, "North America", 0.04)
    _country(conn, "Germany", 2026, "Western Europe", 0.025)
    _industry(conn, "Software", "US", 2025, 0.20)
    _industry(conn, "Software", "US", 2026, 0.25)

    for ticker in ("USA", "NOPRICE", "NULLCLOSE"):
        _company(conn, ticker)
        _financials(conn, ticker)
    _company(conn, "DEU", country="Germany")  # Europe has no Software row: cross-region.
    _financials(conn, "DEU")
    _company(conn, "NOCTRY", country=None)
    _financials(conn, "NOCTRY")
    _company(conn, "ATL", country="Atlantis")  # no damodaran_country row at all.
    _financials(conn, "ATL")
    _company(conn, "NOIND", industry=None)
    _financials(conn, "NOIND")
    _company(conn, "BARE", country=None, industry=None)
    _financials(conn, "BARE")
    _company(conn, "ZEROREV")
    _financials(conn, "ZEROREV", [(2020, 0.0, -5.0, False), *_SIX_YEARS[1:]])
    _company(conn, "ONEYR")
    _financials(conn, "ONEYR", _SIX_YEARS[-1:])
    _company(conn, "NULLREV")
    _financials(conn, "NULLREV", [*_SIX_YEARS[:3], (2023, None, 250.0, False), *_SIX_YEARS[4:]])
    _company(conn, "RESTATED")
    _financials(conn, "RESTATED", [*_SIX_YEARS, (2025, 9_999.0, 9_999.0, True)])
    _company(conn, "OOO")
    _financials(conn, "OOO", list(reversed(_SIX_YEARS)))
    _company(conn, "NOFIN")

    for ticker in VALUABLE:
        if ticker not in ("NOPRICE", "NULLCLOSE"):
            _price(conn, ticker, "2026-05-28", 9.0)
            _price(conn, ticker, "2026-05-29", 10.0)
    _price(conn, "NULLCLOSE", "2026-05-28", 8.0)
    _price(conn, "NULLCLOSE", "2026-05-29", None)


# --------------------------------------------------------------------------- #
# bulk_load_assumption_inputs                                                  #
# --------------------------------------------------------------------------- #


def test_bulk_assumption_inputs_match_per_ticker(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn)
    bulk = bulk_load_assumption_inputs(conn, VALUABLE + ABSENT)
    known = [*VALUABLE, "NOFIN"]  # NOFIN has a companies row, so it has assumption inputs.
    assert bulk == {t: load_assumption_inputs(conn, t) for t in known}


def test_bulk_assumption_inputs_log_cross_region_substitution(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn)
    with capture_logs() as events:
        inputs = bulk_load_assumption_inputs(conn, ["DEU"])
    assert inputs["DEU"].sector_is_cross_region
    assert any(e["event"] == "assumptions.sector.cross_region_substitution" for e in events)


def test_cross_region_fallback_ties_break_by_region(conn: duckdb.DuckDBPyConnection) -> None:
    # Two non-matching regions share the latest year: both paths take the
    # alphabetically first region, not whichever row the engine returns first.
    _country(conn, "Germany", 2026, "Western Europe", 0.025)
    _industry(conn, "Chips", "Japan", 2026, 0.40)
    _industry(conn, "Chips", "Global", 2026, 0.10)
    _company(conn, "CHP", country="Germany", industry="Chips")
    _financials(conn, "CHP")

    per_ticker = load_assumption_inputs(conn, "CHP")
    bulk = bulk_load_assumption_inputs(conn, ["CHP"])["CHP"]
    assert per_ticker.sector is not None
    assert per_ticker.sector.op_margin == 0.10
    assert bulk == per_ticker


def test_bulk_assumption_inputs_all_null_country_and_industry(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # No company carries a country or an industry, so the lists bound to the
    # Damodaran queries are empty.
    _seed(conn)
    assert bulk_load_assumption_inputs(conn, ["BARE"]) == {
        "BARE": load_assumption_inputs(conn, "BARE")
    }


def test_bulk_assumption_inputs_empty(conn: duckdb.DuckDBPyConnection) -> None:
    spy = CountingConn(conn)
    assert bulk_load_assumption_inputs(spy, []) == {}  # type: ignore[arg-type]
    assert spy.executes == 0


def test_bulk_assumption_inputs_query_count_is_constant(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn)
    one, many = CountingConn(conn), CountingConn(conn)
    bulk_load_assumption_inputs(one, ["USA"])  # type: ignore[arg-type]
    bulk_load_assumption_inputs(many, VALUABLE + ABSENT)  # type: ignore[arg-type]
    assert one.executes == many.executes


# --------------------------------------------------------------------------- #
# bulk_load_valuation_inputs                                                   #
# --------------------------------------------------------------------------- #


def test_bulk_valuation_inputs_match_per_ticker(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn)
    bulk = bulk_load_valuation_inputs(conn, VALUABLE + ABSENT)
    assert bulk == {t: load_valuation_input(conn, t) for t in VALUABLE}
    assert bulk["NOPRICE"].current_price is None
    assert bulk["NULLCLOSE"].current_price == 8.0


def test_bulk_valuation_inputs_key_by_upper_cased_ticker(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn)
    assert bulk_load_valuation_inputs(conn, ["usa"]) == {"USA": load_valuation_input(conn, "usa")}


def test_bulk_valuation_inputs_empty(conn: duckdb.DuckDBPyConnection) -> None:
    spy = CountingConn(conn)
    assert bulk_load_valuation_inputs(spy, []) == {}  # type: ignore[arg-type]
    assert spy.executes == 0


def test_bulk_valuation_inputs_query_count_is_constant(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn)
    one, many = CountingConn(conn), CountingConn(conn)
    bulk_load_valuation_inputs(one, ["USA"])  # type: ignore[arg-type]
    bulk_load_valuation_inputs(many, VALUABLE + ABSENT)  # type: ignore[arg-type]
    assert one.executes == many.executes


def test_bulk_valuation_inputs_without_financials_returns_empty(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn)
    assert bulk_load_valuation_inputs(conn, ["NOFIN", "UNKNOWN"]) == {}
