"""Unit tests for the screener engine (spec §6, issue #9).

Exercise snapshot assembly, the three-layer evaluation, and the run/rank join in
isolation against an in-memory DuckDB, with no HTTP and no report I/O.
"""

from __future__ import annotations

import duckdb
import pytest

from bot.screener.benchmarks import load_industry_benchmarks
from bot.screener.config import load_screener_config
from bot.screener.engine import (
    DEFAULT_REGION,
    _CompanyRow,
    _load_companies,
    _resolve_region,
    build_company_data,
    evaluate_company,
    run_screen,
)
from bot.screener.rules import MinMarketCap
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.storage.db import apply_schema


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _seed_one(conn: duckdb.DuckDBPyConnection, ticker: str = "TST") -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "Test Corp", "United States", "Software", "Software", "fmp"],
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region) VALUES (?, ?, ?)",
        ["United States", 2026, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry (industry, region, year, wacc, pe) "
        "VALUES (?, ?, ?, ?, ?)",
        ["Software", "US", 2026, 0.08, 20.0],
    )
    for offset in range(6):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, ebitda, interest_expense, net_income, "
            "total_assets, total_debt, cash, total_equity, goodwill, operating_cashflow, "
            "free_cashflow, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ticker, 2020 + offset, 1000.0 * (1.1**offset), 200.0, 300.0, 10.0, 150.0,
                2000.0, 0.0, 100.0, 1000.0, 100.0, 250.0, 200.0, 100.0, False, "fmp",
            ],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "2026-05-29", 10.0, 1000.0, "USD", "fmp"],
    )


def test_resolve_region_defaults_when_country_missing(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    assert _resolve_region(conn, None) == DEFAULT_REGION
    assert _resolve_region(conn, "Atlantis") == DEFAULT_REGION


def test_resolve_region_maps_country(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region) VALUES (?, ?, ?)",
        ["Germany", 2026, "Europe"],
    )
    assert _resolve_region(conn, "Germany") == "Europe"


def test_build_company_data_derives_ratios(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_one(conn)
    row = _load_companies(conn)[0]
    annual = conn.execute(
        "SELECT revenue, ebit, ebitda, interest_expense, net_income, total_assets, "
        "total_debt, cash, total_equity, goodwill, operating_cashflow, free_cashflow, "
        "shares_diluted FROM financials_annual WHERE ticker = ? ORDER BY fiscal_year",
        ["TST"],
    ).fetchall()
    from bot.screener.engine import _AnnualRow

    cd = build_company_data(
        conn, row, [_AnnualRow(*r) for r in annual], market_cap=1000.0, close=10.0
    )
    assert cd.region == "US"
    assert cd.years_of_financials == 6
    # PE = close / (net_income/shares) = 10 / (150/100) = 6.67.
    assert cd.pe == pytest.approx(10.0 / 1.5)
    # net cash position → negative net debt.
    assert cd.net_debt == pytest.approx(-100.0)
    assert cd.fcf_yield == pytest.approx(200.0 / 1000.0)
    assert len(cd.revenue_history) == 6


def test_build_company_data_handles_no_financials(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    row = _CompanyRow(
        ticker="EMPTY", name="Empty", country=None, industry=None, industry_damodaran=None
    )
    cd = build_company_data(conn, row, [], market_cap=None, close=None)
    assert cd.years_of_financials == 0
    assert cd.pe is None
    assert cd.region == DEFAULT_REGION
    assert cd.revenue_history == ()


def test_evaluate_company_fails_on_gate() -> None:
    company = CompanyData(ticker="X", name="X", market_cap=1.0)
    verdict = evaluate_company(
        company,
        None,
        quality_gates=[MinMarketCap(minimum_usd=1e9)],
        value_indicators=[],
        trap_detection=[],
    )
    assert verdict.passed is False
    assert "min_market_cap" in verdict.failed_gates


def test_evaluate_company_needs_a_value_indicator() -> None:
    company = CompanyData(ticker="X", name="X", market_cap=1e10)
    # Passes the gate but no value indicator → not a candidate.
    verdict = evaluate_company(
        company,
        None,
        quality_gates=[MinMarketCap(minimum_usd=1.0)],
        value_indicators=[],
        trap_detection=[],
    )
    assert verdict.passed is False


def test_evaluate_company_skipped_value_does_not_pass() -> None:
    from bot.screener.rules import PEBelowIndustryMultiple

    company = CompanyData(ticker="X", name="X", market_cap=1e10, pe=None)
    bench = IndustryBenchmarks(industry="i", region="US", year=2026, pe=None)
    verdict = evaluate_company(
        company,
        bench,
        quality_gates=[MinMarketCap(minimum_usd=1.0)],
        value_indicators=[PEBelowIndustryMultiple()],
        trap_detection=[],
    )
    # Indicator skipped (no median) → still no value indicator passed.
    assert verdict.passed is False
    assert "pe_below_industry_multiple" not in verdict.failed_gates


def test_run_screen_empty_universe(conn: duckdb.DuckDBPyConnection) -> None:
    from pathlib import Path

    cfg = load_screener_config(
        Path(__file__).resolve().parents[2]
        / "config"
        / "presets"
        / "damodaran_value.yaml"
    )
    result = run_screen(conn, cfg)
    assert result.shortlist == ()
    assert result.screened == 0


def test_load_industry_benchmarks_reused(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_one(conn)
    bench = load_industry_benchmarks(conn, industry="Software", region="US")
    assert bench is not None
    assert bench.pe == 20.0
