"""The valuator values a company in its valuation currency (ADR 0005 §4, #109).

The valuation currency is the reporting currency of the company's latest
non-restated ``financials_annual`` row. Its risk-free rate and nominal-GDP
growth come from ``config/currencies.yaml``; terminal growth is
``min(rfr_ccy, gdp_ccy)``. A currency with no row leaves the GDP-anchored
assumptions unresolved rather than falling back to USD.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
from structlog.testing import capture_logs

from bot.reference.currencies import CurrencyRates, CurrencyTable, load_currency_table
from bot.storage.db import apply_schema, connect
from bot.valuator.assumptions import (
    AssumptionSource,
    bulk_load_assumption_inputs,
    load_assumption_inputs,
    resolve_assumptions,
)
from bot.valuator.story_types import StoryType

REPO_FILE = Path(__file__).resolve().parents[2] / "config" / "currencies.yaml"


def _rates(rfr: float, gdp: float) -> CurrencyRates:
    return CurrencyRates(
        risk_free_rate=rfr,
        nominal_gdp_growth=gdp,
        source="https://example.org/rfr",
        gdp_source="https://example.org/gdp",
        as_of=date(2026, 1, 1),
    )


TABLE: CurrencyTable = {"USD": _rates(0.0395, 0.04), "JPY": _rates(0.0147, 0.0261)}


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = connect(":memory:")
    apply_schema(c)
    c.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, op_margin, "
        " sales_to_capital, tax_rate, debt_to_equity) "
        "VALUES ('Software', 'US', 2026, 0.09, 0.10, 0.04, 0.18, 2.5, 0.21, 0.25)"
    )
    return c


def _seed(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    currencies: tuple[str | None, ...],
    *,
    restated: bool = False,
) -> None:
    """One annual row per currency, oldest first (fiscal years 2021, 2022, ...)."""
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry_damodaran, source) "
        "VALUES (?, ?, 'United States', 'Software', 'test')",
        [ticker, f"{ticker} Inc"],
    )
    for i, currency in enumerate(currencies):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, currency, revenue, ebit, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, 'test')",
            [ticker, 2021 + i, currency, 100.0 * (1.1**i), 15.0, restated],
        )


def test_usd_company_terminal_growth_comes_from_the_currency_file(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The file's USD pair is (0.0395, 0.04): the rate master imported from
    wacc.xls and master's GDP constant, so USD inputs do not move (#109 AC1)."""
    _seed(conn, "ACME", ("USD",))
    result = resolve_assumptions("ACME", conn, currencies=load_currency_table(REPO_FILE))
    assert result.terminal_growth.value == pytest.approx(0.0395)
    assert result.terminal_growth.source is AssumptionSource.RULE_BASED


def test_usd_company_without_history_anchors_revenue_growth_on_usd_gdp(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry_damodaran, source) "
        "VALUES ('NEW', 'New Inc', 'United States', 'Software', 'test')"
    )
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, currency, source) "
        "VALUES ('NEW', 2025, 'USD', 'test')"
    )
    result = resolve_assumptions("NEW", conn, currencies=TABLE)
    assert result.revenue_growth.value == pytest.approx((0.04,) * 5)
    assert result.revenue_growth.source is AssumptionSource.RULE_BASED


def test_jpy_company_uses_the_jpy_rate(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn, "TOYO", ("JPY", "JPY"))
    result = resolve_assumptions("TOYO", conn, currencies=TABLE)
    assert result.terminal_growth.value == pytest.approx(0.0147)


def test_jpy_company_uses_the_jpy_gdp_ceiling(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn, "TOYO", ("JPY",))
    table = {"JPY": _rates(0.03, 0.0261)}
    result = resolve_assumptions("TOYO", conn, currencies=table)
    assert result.terminal_growth.value == pytest.approx(0.0261)


def test_high_growth_fade_targets_the_currency_gdp(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn, "TOYO", ("JPY",) * 4)
    result = resolve_assumptions(
        "TOYO", conn, currencies=TABLE, auto_story_type=StoryType.HIGH_GROWTH
    )
    path = result.revenue_growth.value
    assert path is not None
    assert path[-1] == pytest.approx(0.0261)
    assert result.revenue_growth.source is AssumptionSource.STORY_PATTERN


def test_latest_annual_row_decides_the_valuation_currency(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn, "SWAP", ("USD", "JPY"))
    inputs = load_assumption_inputs(conn, "SWAP", currencies=TABLE)
    assert inputs.valuation_currency == "JPY"
    assert inputs.currency_rates == TABLE["JPY"]


def test_lowercase_currency_resolves(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn, "LOW", (" usd",))
    inputs = load_assumption_inputs(conn, "LOW", currencies=TABLE)
    assert inputs.valuation_currency == "USD"
    assert inputs.currency_rates == TABLE["USD"]


def test_bulk_and_single_loaders_agree_on_currency(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn, "SWAP", ("USD", "JPY"))
    _seed(conn, "ACME", ("USD",))
    bulk = bulk_load_assumption_inputs(conn, ["SWAP", "ACME"], currencies=TABLE)
    for ticker in ("SWAP", "ACME"):
        single = load_assumption_inputs(conn, ticker, currencies=TABLE)
        assert bulk[ticker].valuation_currency == single.valuation_currency
        assert bulk[ticker].currency_rates == single.currency_rates


def test_uncovered_currency_leaves_terminal_growth_unresolved(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn, "XCO", ("XYZ",))
    result = resolve_assumptions("XCO", conn, currencies=TABLE)
    assert result.terminal_growth.value is None
    assert result.terminal_growth.source is AssumptionSource.UNRESOLVED
    with pytest.raises(ValueError, match="terminal_growth"):
        result.to_dcf_assumptions()


def test_no_history_revenue_growth_unresolved_when_currency_uncovered(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn, "XCO", ("XYZ",))
    result = resolve_assumptions("XCO", conn, currencies=TABLE)
    assert result.revenue_growth.value is None
    assert result.revenue_growth.source is AssumptionSource.UNRESOLVED


def test_high_growth_without_currency_falls_back_to_historical_average(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn, "XCO", ("XYZ",) * 4)
    result = resolve_assumptions(
        "XCO", conn, currencies=TABLE, auto_story_type=StoryType.HIGH_GROWTH
    )
    assert result.revenue_growth.source is AssumptionSource.HISTORICAL_AVERAGE


def test_manual_terminal_growth_wins_over_uncovered_currency(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed(conn, "XCO", ("XYZ",))
    override = tmp_path / "XCO.yaml"
    override.write_text("terminal_growth: 0.02\n")
    result = resolve_assumptions("XCO", conn, override, currencies=TABLE)
    assert result.terminal_growth.value == pytest.approx(0.02)
    assert result.terminal_growth.source is AssumptionSource.MANUAL


@pytest.mark.parametrize(
    ("currencies", "restated"), [((None,), False), (("USD",), True), ((), False)],
    ids=["null-currency", "only-restated", "no-rows"],
)
def test_unknown_valuation_currency_is_uncovered(
    conn: duckdb.DuckDBPyConnection, currencies: tuple[str | None, ...], restated: bool
) -> None:
    _seed(conn, "UNK", currencies, restated=restated)
    result = resolve_assumptions("UNK", conn, currencies=TABLE)
    assert result.terminal_growth.source is AssumptionSource.UNRESOLVED


def test_uncovered_currency_warns_once_per_bulk_load(conn: duckdb.DuckDBPyConnection) -> None:
    _seed(conn, "XA", ("XYZ",))
    _seed(conn, "XB", ("XYZ",))
    with capture_logs() as logs:
        bulk_load_assumption_inputs(conn, ["XA", "XB"], currencies=TABLE)
    events = [e for e in logs if e["event"] == "assumptions.currency_uncovered"]
    assert len(events) == 1
    assert events[0]["currency"] == "XYZ"


def test_shared_warned_set_logs_each_currency_once_per_run(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed(conn, "XA", ("XYZ",))
    _seed(conn, "XB", ("XYZ",))
    warned: set[str | None] = set()
    with capture_logs() as logs:
        load_assumption_inputs(conn, "XA", currencies=TABLE, warned=warned)
        load_assumption_inputs(conn, "XB", currencies=TABLE, warned=warned)
        bulk_load_assumption_inputs(conn, ["XA", "XB"], currencies=TABLE, warned=warned)
    events = [e for e in logs if e["event"] == "assumptions.currency_uncovered"]
    assert len(events) == 1
    assert warned == {"XYZ"}
