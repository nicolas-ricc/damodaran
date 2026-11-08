"""Readers of ``companies.country`` resolve ISO-coded companies (#271).

Providers store ISO 3166 alpha-2 codes (``"US"``) while ``damodaran_country``
is keyed by Damodaran's names (``"United States"``).
"""

from __future__ import annotations

import duckdb
import pytest

from bot.reference import countries
from bot.screener.engine import DEFAULT_REGION, DEFAULT_TAX_RATE, _resolve_region
from bot.screener.engine import _resolve_tax_rate as screener_tax_rate
from bot.storage.db import apply_schema
from bot.valuator.analysis import bulk_load_valuation_inputs, load_valuation_input
from bot.valuator.assumptions import (
    AssumptionSource,
    bulk_load_assumption_inputs,
    load_assumption_inputs,
    resolve_assumptions,
)

#: ``ticker -> companies.country``: ISO codes side by side with a name-coded row.
COMPANIES = {"USCO": "US", "JPCO": "JP", "CHCO": "ch", "NAMED": "United States"}


@pytest.fixture(autouse=True)
def _fresh_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(countries, "_warned", set())


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    for country, region, erp, tax in (
        ("United States", "North America", 0.0423, 0.25),
        ("Japan", "Asia", 0.0512, 0.3062),
        ("Switzerland", "Western Europe", 0.0423, 0.1961),
    ):
        c.execute(
            "INSERT INTO damodaran_country (country, year, region, erp, tax_rate) "
            "VALUES (?, 2026, ?, ?, ?)",
            [country, region, erp, tax],
        )
    for region, margin in (("US", 0.25), ("Japan", 0.12), ("Europe", 0.18)):
        # tax_rate NULL so the valuator reaches its country tax step.
        c.execute(
            "INSERT INTO damodaran_industry "
            "(industry, region, year, wacc, pe, cost_of_equity, cost_of_debt, beta_levered, "
            "debt_to_equity, op_margin, sales_to_capital, tax_rate, ev_sales, roic) "
            "VALUES ('Software', ?, 2026, 0.08, 20.0, 0.09, 0.045, 1.05, 0.2, ?, 2.5, NULL, "
            "5.0, 0.15)",
            [region, margin],
        )
    for ticker, country in COMPANIES.items():
        c.execute(
            "INSERT INTO companies (ticker, name, country, currency, industry_damodaran, "
            "source) VALUES (?, ?, ?, 'USD', 'Software', 'test')",
            [ticker, f"{ticker} Inc", country],
        )
        for i in range(6):
            c.execute(
                "INSERT INTO financials_annual "
                "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
                "total_debt, cash, shares_diluted, total_equity, is_restated, source, currency) "
                "VALUES (?, ?, ?, ?, 100.0, 10.0, 300.0, 50.0, 100.0, 900.0, FALSE, 't', 'USD')",
                [ticker, 2020 + i, 1_000.0 * 1.1**i, 200.0 * 1.1**i],
            )
        c.execute(
            "INSERT INTO prices_daily (ticker, date, close, currency, source) "
            "VALUES (?, DATE '2026-11-06', 50.0, 'USD', 'test')",
            [ticker],
        )
    return c


def test_screener_tax_rate_for_iso_us(conn: duckdb.DuckDBPyConnection) -> None:
    assert screener_tax_rate(conn, "US") == pytest.approx(0.25)
    assert screener_tax_rate(conn, "United States") == pytest.approx(0.25)


def test_screener_region_for_iso_jp(conn: duckdb.DuckDBPyConnection) -> None:
    assert _resolve_region(conn, "JP") == "Japan"
    assert _resolve_region(conn, "CH") == "Europe"
    assert _resolve_region(conn, "US") == "US"


def test_unmapped_code_keeps_screener_defaults(conn: duckdb.DuckDBPyConnection) -> None:
    assert screener_tax_rate(conn, "ZZ") == DEFAULT_TAX_RATE
    assert _resolve_region(conn, "ZZ") == DEFAULT_REGION
    assert screener_tax_rate(conn, None) == DEFAULT_TAX_RATE
    assert _resolve_region(conn, "  ") == DEFAULT_REGION


def test_valuator_country_row_for_iso_us(conn: duckdb.DuckDBPyConnection) -> None:
    inputs = load_assumption_inputs(conn, "USCO")
    assert inputs.country is not None
    assert inputs.country.erp == pytest.approx(0.0423)
    assert inputs.country.tax_rate == pytest.approx(0.25)
    assert inputs.company.country == "US"


def test_valuator_tax_falls_back_to_iso_country(conn: duckdb.DuckDBPyConnection) -> None:
    tax = resolve_assumptions("USCO", conn).tax_rate
    assert tax.value == pytest.approx(0.25)
    assert tax.source is AssumptionSource.SECTOR_DEFAULT_DAMODARAN


def test_single_and_bulk_assumption_country_rows_match(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    bulk = bulk_load_assumption_inputs(conn, list(COMPANIES))
    for ticker in COMPANIES:
        single = load_assumption_inputs(conn, ticker)
        assert single.country is not None, ticker
        assert bulk[ticker].country == single.country, ticker
        assert bulk[ticker].sector == single.sector, ticker
    assert bulk["JPCO"].country is not None and bulk["JPCO"].country.region == "Asia"


def test_single_and_bulk_sector_multiples_match(conn: duckdb.DuckDBPyConnection) -> None:
    bulk = bulk_load_valuation_inputs(conn, list(COMPANIES))
    for ticker in COMPANIES:
        single = load_valuation_input(conn, ticker)
        assert bulk[ticker].sector == single.sector, ticker
    assert bulk["JPCO"].sector.region == "Japan"
    assert bulk["JPCO"].sector.op_margin == pytest.approx(0.12)
    assert bulk["CHCO"].sector.region == "Europe"
    assert load_valuation_input(conn, "JPCO").sector.region == "Japan"
