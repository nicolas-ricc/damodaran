"""Unit tests for the screener engine (spec §6, issue #9).

Exercise snapshot assembly, the three-layer evaluation, and the run/rank join in
isolation against an in-memory DuckDB, with no HTTP and no report I/O.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from bot.screener.benchmarks import load_industry_benchmarks
from bot.screener.config import ScreenerConfig, load_screener_config
from bot.screener.engine import (
    DEFAULT_REGION,
    DEFAULT_TAX_RATE,
    _CompanyRow,
    _load_companies,
    _resolve_region,
    _resolve_tax_rate,
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
        "INSERT INTO damodaran_industry (industry, region, year, wacc, pe) VALUES (?, ?, ?, ?, ?)",
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
                ticker,
                2020 + offset,
                1000.0 * (1.1**offset),
                200.0,
                300.0,
                10.0,
                150.0,
                2000.0,
                0.0,
                100.0,
                1000.0,
                100.0,
                250.0,
                200.0,
                100.0,
                False,
                "fmp",
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


def test_resolve_tax_rate_defaults_when_country_missing(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    assert _resolve_tax_rate(conn, None) == DEFAULT_TAX_RATE
    assert _resolve_tax_rate(conn, "Atlantis") == DEFAULT_TAX_RATE


def test_resolve_tax_rate_reads_country(conn: duckdb.DuckDBPyConnection) -> None:
    # NB: production damodaran_country rows carry no tax_rate yet (the ERP ingest
    # omits it), so this row is inserted by hand to exercise the resolver itself.
    conn.execute(
        "INSERT INTO damodaran_country (country, year, tax_rate) VALUES (?, ?, ?)",
        ["Germany", 2026, 0.30],
    )
    assert _resolve_tax_rate(conn, "Germany") == pytest.approx(0.30)


def test_resolve_tax_rate_rejects_out_of_range(conn: duckdb.DuckDBPyConnection) -> None:
    # A percentage stored as 30 (instead of 0.30), or a >=100% rate, would make
    # (1 - tax_rate) negative; the resolver falls back to the default instead.
    conn.execute(
        "INSERT INTO damodaran_country (country, year, tax_rate) VALUES (?, ?, ?)",
        ["Freedonia", 2026, 30.0],
    )
    assert _resolve_tax_rate(conn, "Freedonia") == DEFAULT_TAX_RATE


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
    # ROIC = ebit*(1-tax)/invested; US country row carries no tax_rate, so the
    # 0.21 default applies: 200 * 0.79 / 1000 = 0.158.
    assert cd.roic == pytest.approx(200.0 * (1.0 - DEFAULT_TAX_RATE) / 1000.0)


def test_build_company_data_roic_uses_country_tax_rate(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["DEU", "Deutsche Test AG", "Germany", "Software", "Software", "fmp"],
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region, tax_rate) VALUES (?, ?, ?, ?)",
        ["Germany", 2026, "Europe", 0.30],
    )
    conn.execute(
        "INSERT INTO financials_annual "
        "(ticker, fiscal_year, revenue, ebit, ebitda, interest_expense, net_income, "
        "total_assets, total_debt, cash, total_equity, goodwill, operating_cashflow, "
        "free_cashflow, shares_diluted, is_restated, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "DEU",
            2026,
            1000.0,
            200.0,
            300.0,
            10.0,
            150.0,
            2000.0,
            0.0,
            100.0,
            1000.0,
            100.0,
            250.0,
            200.0,
            100.0,
            False,
            "fmp",
        ],
    )
    from bot.screener.engine import _AnnualRow

    row = next(r for r in _load_companies(conn) if r.ticker == "DEU")
    annual = conn.execute(
        "SELECT revenue, ebit, ebitda, interest_expense, net_income, total_assets, "
        "total_debt, cash, total_equity, goodwill, operating_cashflow, free_cashflow, "
        "shares_diluted FROM financials_annual WHERE ticker = ? ORDER BY fiscal_year",
        ["DEU"],
    ).fetchall()
    cd = build_company_data(
        conn, row, [_AnnualRow(*r) for r in annual], market_cap=1000.0, close=10.0
    )
    # Germany's 30% tax rate, not the US 21% default: 200 * 0.70 / 1000 = 0.14.
    assert cd.roic == pytest.approx(200.0 * (1.0 - 0.30) / 1000.0)


def _load_tst_annual(conn: duckdb.DuckDBPyConnection) -> list:  # type: ignore[type-arg]
    from bot.screener.engine import _AnnualRow

    rows = conn.execute(
        "SELECT revenue, ebit, ebitda, interest_expense, net_income, total_assets, "
        "total_debt, cash, total_equity, goodwill, operating_cashflow, free_cashflow, "
        "shares_diluted FROM financials_annual WHERE ticker = ? ORDER BY fiscal_year",
        ["TST"],
    ).fetchall()
    return [_AnnualRow(*r) for r in rows]


def test_build_company_data_converts_market_cap_to_usd(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_one(conn)
    conn.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES (?, ?, ?, ?)",
        ["EUR", "2026-05-29", 1.2, "fmp"],
    )
    row = _load_companies(conn)[0]
    cd = build_company_data(
        conn,
        row,
        _load_tst_annual(conn),
        market_cap=1000.0,
        close=10.0,
        currency="EUR",
        as_of=date(2026, 5, 29),
    )
    # The stored market_cap is USD: 1000 EUR * 1.2 = 1200.
    assert cd.market_cap == pytest.approx(1200.0)
    # ev_ebitda is currency-self-consistent: computed from the LOCAL market_cap
    # (1000), not the converted one — (1000 + net_debt(-100)) / ebitda(300).
    assert cd.ev_ebitda == pytest.approx((1000.0 - 100.0) / 300.0)
    # fcf_yield likewise uses local market_cap: fcf(200) / 1000.
    assert cd.fcf_yield == pytest.approx(200.0 / 1000.0)


def test_build_company_data_market_cap_none_when_no_fx_rate(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_one(conn)
    row = _load_companies(conn)[0]
    # No currencies row for GBP -> to_usd raises LookupError -> market_cap None,
    # so MinMarketCap treats it as unmeasurable rather than crashing the run.
    cd = build_company_data(
        conn,
        row,
        _load_tst_annual(conn),
        market_cap=1000.0,
        close=10.0,
        currency="GBP",
        as_of=date(2026, 5, 29),
    )
    assert cd.market_cap is None
    # Ratios still derive from the local market_cap.
    assert cd.ev_ebitda == pytest.approx((1000.0 - 100.0) / 300.0)


def test_build_company_data_usd_market_cap_unchanged(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_one(conn)
    row = _load_companies(conn)[0]
    cd = build_company_data(
        conn,
        row,
        _load_tst_annual(conn),
        market_cap=1000.0,
        close=10.0,
        currency="USD",
        as_of=date(2026, 5, 29),
    )
    assert cd.market_cap == pytest.approx(1000.0)


def test_load_all_annual_groups_oldest_first_per_ticker(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    from bot.screener.engine import _load_all_annual

    _seed_sector(conn)
    _seed_company(conn, "AAA")
    _seed_company(conn, "BBB")
    # A restated row must be excluded.
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, revenue, is_restated, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ["AAA", 2030, 9999.0, True, "fmp"],
    )

    by_ticker = _load_all_annual(conn)
    assert set(by_ticker) == {"AAA", "BBB"}
    assert len(by_ticker["AAA"]) == 6  # restated row excluded
    # Oldest-first: revenue grows 1.1**offset, so ascending.
    revs = [r.revenue for r in by_ticker["AAA"]]
    assert revs == sorted(revs)


def test_load_latest_prices_picks_latest_non_null_per_ticker(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    from bot.screener.engine import _load_latest_prices

    conn.execute(
        "INSERT INTO companies (ticker, name, source) VALUES (?, ?, ?)", ["XYZ", "Xyz", "fmp"]
    )
    # Older row has both; newest row has a close but a NULL market_cap, so the
    # market cap must come from the older row and the close from the newest.
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["XYZ", "2026-05-01", 9.0, 900.0, "EUR", "fmp"],
    )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["XYZ", "2026-05-29", 11.0, None, "EUR", "fmp"],
    )

    prices = _load_latest_prices(conn)
    snap = prices["XYZ"]
    assert snap.close == pytest.approx(11.0)  # newest close
    assert snap.market_cap == pytest.approx(900.0)  # latest non-null cap (older row)
    assert snap.currency == "EUR"
    assert snap.as_of == date(2026, 5, 1)  # the cap's observation date


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
        Path(__file__).resolve().parents[2] / "config" / "presets" / "damodaran_value.yaml"
    )
    result = run_screen(conn, cfg)
    assert result.shortlist == ()
    assert result.screened == 0


def test_load_industry_benchmarks_reused(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_one(conn)
    bench = load_industry_benchmarks(conn, industry="Software", region="US")
    assert bench is not None
    assert bench.pe == 20.0


# --------------------------------------------------------------------------- #
# M4.7 — valuator wiring into the ranking                                      #
# --------------------------------------------------------------------------- #


def _value_preset() -> ScreenerConfig:
    from pathlib import Path

    return load_screener_config(
        Path(__file__).resolve().parents[2] / "config" / "presets" / "damodaran_value.yaml"
    )


def _seed_sector(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert the shared Software sector + US country rows exactly once."""
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region) VALUES (?, ?, ?)",
        ["United States", 2026, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry (industry, region, year, wacc, pe) VALUES (?, ?, ?, ?, ?)",
        ["Software", "US", 2026, 0.08, 20.0],
    )


def _seed_company(conn: duckdb.DuckDBPyConnection, ticker: str) -> None:
    """Seed one passing Software company sharing the sector rows from ``_seed_sector``."""
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", "United States", "Software", "Software", "fmp"],
    )
    for offset in range(6):
        rev = 1_000_000_000.0 * (1.1**offset)
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, ebitda, interest_expense, net_income, "
            "total_assets, total_debt, cash, total_equity, goodwill, operating_cashflow, "
            "free_cashflow, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ticker,
                2020 + offset,
                rev,
                rev * 0.2,
                1_000_000_000.0,
                50_000_000.0,
                1_000_000_000.0,
                6_000_000_000.0,
                0.0,
                100_000_000.0,
                2_000_000_000.0,
                500_000_000.0,
                700_000_000.0,
                600_000_000.0,
                1_000_000_000.0,
                False,
                "fmp",
            ],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "2026-05-29", 10.0, 5_000_000_000.0, "USD", "fmp"],
    )


def test_run_screen_uses_valuator_mos(conn: duckdb.DuckDBPyConnection) -> None:
    """The valuator's real MoS lands in each candidate's persisted score."""
    _seed_sector(conn)
    _seed_company(conn, "TST")

    def fake_valuator(_c: duckdb.DuckDBPyConnection, ticker: str) -> float | None:
        return 1.8 if ticker == "TST" else None

    result = run_screen(conn, _value_preset(), valuator=fake_valuator)
    assert len(result.shortlist) == 1
    # Real MoS (1.8) flows through, not the 0.5 placeholder.
    assert result.shortlist[0].margin_of_safety == pytest.approx(1.8)


def test_run_screen_falls_back_to_placeholder_when_unvaluable(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """A candidate the valuator cannot value keeps the neutral placeholder."""
    from bot.screener.ranking import PLACEHOLDER_MARGIN_OF_SAFETY

    _seed_sector(conn)
    _seed_company(conn, "TST")

    def none_valuator(_c: duckdb.DuckDBPyConnection, _t: str) -> float | None:
        return None

    result = run_screen(conn, _value_preset(), valuator=none_valuator)
    assert result.shortlist[0].margin_of_safety == pytest.approx(PLACEHOLDER_MARGIN_OF_SAFETY)


def test_run_screen_none_valuator_keeps_placeholder(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Passing ``valuator=None`` skips valuation (first-pass placeholder kept)."""
    from bot.screener.ranking import PLACEHOLDER_MARGIN_OF_SAFETY

    _seed_sector(conn)
    _seed_company(conn, "TST")
    result = run_screen(conn, _value_preset(), valuator=None)
    assert result.shortlist[0].margin_of_safety == pytest.approx(PLACEHOLDER_MARGIN_OF_SAFETY)


def test_run_screen_valuator_runs_only_on_top_n(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The valuator (second pass) runs only on the top-N shortlist, not all."""
    _seed_sector(conn)
    for tkr in ("AAA", "BBB", "CCC"):
        _seed_company(conn, tkr)

    valued: list[str] = []

    def recording_valuator(_c: duckdb.DuckDBPyConnection, ticker: str) -> float | None:
        valued.append(ticker)
        return 1.0

    result = run_screen(conn, _value_preset(), top=2, valuator=recording_valuator)
    assert len(result.shortlist) == 2
    # Only the two shortlisted candidates were valued.
    assert len(valued) == 2


def test_dcf_margin_of_safety_swallows_lookup_error(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The default valuator returns None for an unknown/unvaluable ticker."""
    from bot.screener.engine import _dcf_margin_of_safety

    assert _dcf_margin_of_safety(conn, "NOPE") is None


def test_dcf_margin_of_safety_returns_real_ratio(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """The default valuator returns the DCF intrinsic/price ratio when valuable."""
    from bot.screener.engine import _dcf_margin_of_safety
    from tests.unit.test_valuator_analysis import _seed as _seed_valuable

    _seed_valuable(conn)
    mos = _dcf_margin_of_safety(conn, "AAPL")
    assert mos is not None
    assert mos > 0.0


def test_run_screen_reranks_when_valuator_differs_from_placeholder(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Real MoS re-orders an otherwise-tied shortlist (placeholder vs valuator)."""
    # Two near-identical candidates: ranking is a near tie under the placeholder.
    _seed_sector(conn)
    _seed_company(conn, "AAA")
    _seed_company(conn, "BBB")

    placeholder_run = run_screen(conn, _value_preset(), valuator=None)
    placeholder_order = [c.ticker for c in placeholder_run.shortlist]

    # Give BBB a far higher margin of safety than AAA.
    def skewed_valuator(_c: duckdb.DuckDBPyConnection, ticker: str) -> float | None:
        return {"AAA": 0.6, "BBB": 5.0}.get(ticker)

    valued_run = run_screen(conn, _value_preset(), valuator=skewed_valuator)
    valued_order = [c.ticker for c in valued_run.shortlist]

    # BBB's higher MoS lifts it to the top under the real valuator.
    assert valued_order[0] == "BBB"
    # And the order genuinely changed relative to the placeholder ranking.
    assert valued_order != placeholder_order
