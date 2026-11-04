"""Unit tests for the end-to-end analysis pipeline (spec §7.7, issue #16).

The pipeline is a pure function of ``(ticker, conn, override_path)`` that loads a
company's data from the DB, resolves assumptions, runs the two-stage DCF plus
sensitivity and narrative flags, and packages everything the §7.7 report needs.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
import yaml

from bot.reporting.analysis_report import margin_verdict
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import (
    Analysis,
    SanityCheck,
    _sanity_check,
    _SectorMultiples,
    analyze,
    bulk_load_valuation_inputs,
    load_valuation_input,
)
from bot.valuator.assumptions import AssumptionSource
from bot.valuator.hypergrowth import margin_path, parse_story
from bot.valuator.narrative_flags import FlagColor, NarrativeFlag
from bot.valuator.sensitivity import SensitivityAxis
from bot.valuator.story_types import StoryType
from tests.unit.test_valuator_hypergrowth import _STORY

# Fixture money and share counts are written in millions; the valuator refuses
# share counts below 1,000,000, so seeds are scaled up by this factor.
_MILLIONS = 1_000_000.0


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAPL", "Apple Inc", "United States", "USD", "Computers/Peripherals", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country "
        "(country, year, erp, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?)",
        ["United States", 2026, 0.045, 0.21, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, net_margin, sales_to_capital, pe, ev_ebitda, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "Computers/Peripherals",
            "US",
            2026,
            0.085,
            0.09,
            0.045,
            1.05,
            0.20,
            0.28,
            0.22,
            2.5,
            22.0,
            14.0,
            5.0,
        ],
    )
    # A few years of growing revenue so the historical-average growth path and
    # the story-type classifier both have something to work with.
    revenues = {2022: 380_000.0, 2023: 395_000.0, 2024: 410_000.0, 2025: 430_000.0}
    incomes = {2022: 95_000.0, 2023: 97_000.0, 2024: 99_000.0, 2025: 100_000.0}
    for year, revenue in revenues.items():
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                "AAPL",
                year,
                revenue * _MILLIONS,
                revenue * 0.30 * _MILLIONS,
                incomes[year] * _MILLIONS,
                3_000.0 * _MILLIONS,
                110_000.0 * _MILLIONS,
                60_000.0 * _MILLIONS,
                15_500.0 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAPL", "2026-05-29", 150.0, 2_325_000.0 * _MILLIONS, "USD", "fmp"],
    )


@pytest.fixture
def seeded_conn() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    return conn


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = connect(":memory:")
    apply_schema(c)
    return c


def _seed_company(
    conn: duckdb.DuckDBPyConnection, ticker: str, industry_damodaran: str
) -> None:
    """A minimal company + country + sector row, enough to run ``analyze``."""
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, ticker, "United States", "USD", industry_damodaran, "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country "
        "(country, year, erp, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?)",
        ["United States", 2026, 0.045, 0.21, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, net_margin, sales_to_capital, pe, ev_ebitda, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            industry_damodaran,
            "US",
            2026,
            0.09,
            0.10,
            0.06,
            1.20,
            0.30,
            0.12,
            0.08,
            2.0,
            10.0,
            8.0,
            1.2,
        ],
    )


def _seed_volatile_financials(conn: duckdb.DuckDBPyConnection, ticker: str) -> None:
    """Financials whose earnings coefficient of variation clears the §7.1 cyclical
    threshold (``_CYCLICAL_EARNINGS_CV = 0.50``).

    Earnings history ``(100.0, 20.0, 180.0, 10.0, 150.0)``: mean 92.0, population
    stdev ≈67.94, CV ≈0.738 — comfortably above 0.50. Revenue grows steadily (not
    used by the cyclical check but needed for a valid DCF); interest expense is 0
    so interest coverage stays undefined and the company is not classified
    distressed before the cyclical check runs.
    """
    fiscal_years = (2021, 2022, 2023, 2024, 2025)
    revenues = (1_000.0, 1_050.0, 1_100.0, 1_150.0, 1_200.0)
    earnings = (100.0, 20.0, 180.0, 10.0, 150.0)
    for year, revenue, net_income in zip(fiscal_years, revenues, earnings, strict=True):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                ticker,
                year,
                revenue * _MILLIONS,
                net_income * 1.2 * _MILLIONS,
                net_income * _MILLIONS,
                0.0,
                200.0 * _MILLIONS,
                50.0 * _MILLIONS,
                100.0 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )


def _seed_leveraged_financials(conn: duckdb.DuckDBPyConnection, ticker: str) -> None:
    """Financials that carry ``total_debt`` and ``total_equity``, so the pipeline
    can derive :attr:`~bot.valuator.narrative_flags.NarrativeContext.company_debt_weight`
    (55% debt-heavy: 200,000 / (200,000 + 163,636))."""
    fiscal_years = (2022, 2023, 2024, 2025)
    revenues = (380_000.0, 395_000.0, 410_000.0, 430_000.0)
    for year, revenue in zip(fiscal_years, revenues, strict=True):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, total_equity, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                ticker,
                year,
                revenue * _MILLIONS,
                revenue * 0.30 * _MILLIONS,
                revenue * 0.20 * _MILLIONS,
                3_000.0 * _MILLIONS,
                200_000.0 * _MILLIONS,
                60_000.0 * _MILLIONS,
                163_636.0 * _MILLIONS,
                15_500.0 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )


def _seeded_analysis(conn: duckdb.DuckDBPyConnection) -> Analysis:
    """A company with real balance-sheet debt and equity, ready for ``analyze()``.

    No revenue-by-geography source exists, so ``country_exposure`` must stay
    UNKNOWN even here; ``beta_business_risk`` has everything it needs and must
    not be.
    """
    _seed_company(conn, ticker="LEV", industry_damodaran="Computers/Peripherals")
    _seed_leveraged_financials(conn, ticker="LEV")
    return analyze("LEV", conn)


def test_pipeline_does_not_fake_the_erp_gap(conn: duckdb.DuckDBPyConnection) -> None:
    # analysis.py used to pass the same sector ERP as both the weighted and the
    # listing ERP, making the gap identically zero.
    analysis = _seeded_analysis(conn)
    flag = next(f for f in analysis.narrative_flags if f.name == "country_exposure")
    assert flag.color is FlagColor.UNKNOWN


def test_pipeline_supplies_the_company_leverage(conn: duckdb.DuckDBPyConnection) -> None:
    analysis = _seeded_analysis(conn)
    flag = next(f for f in analysis.narrative_flags if f.name == "beta_business_risk")
    assert flag.color is not FlagColor.UNKNOWN


def test_pipeline_does_not_compare_the_sector_margin_to_itself(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # analysis.py used to pass assumptions.operating_margin as the *company*
    # margin. Absent an override that value is read from the same
    # damodaran_industry row as sector.op_margin, so the two sides were
    # bit-identical and the flag was always green with "at/below sector".
    # LEV's realised margin is EBIT/revenue = 30%, the sector median is 12%.
    _seed_company(conn, ticker="LEV", industry_damodaran="Computers/Peripherals")
    _seed_leveraged_financials(conn, ticker="LEV")
    override = tmp_path / "LEV.yaml"
    override.write_text("story_type: high-growth\n")

    analysis = analyze("LEV", conn, override_path=override)
    flag = next(f for f in analysis.narrative_flags if f.name == "story_margin")

    assert analysis.story_type == "high-growth"
    assert flag.color is FlagColor.YELLOW
    assert "30.0%" in flag.reason and "12.0%" in flag.reason
    # A margin materially *above* sector must never be described as at/below it.
    assert "at/below sector" not in flag.reason


def test_pipeline_story_margin_unknown_when_the_sector_row_is_absent(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # A company whose Damodaran industry has no row for its region: the sector
    # median is unavailable, so the check did not run — it must not read as a pass.
    _seed_company(conn, ticker="LEV", industry_damodaran="Computers/Peripherals")
    _seed_leveraged_financials(conn, ticker="LEV")
    conn.execute("UPDATE damodaran_industry SET op_margin = NULL")
    override = tmp_path / "LEV.yaml"
    override.write_text("story_type: high-growth\noperating_margin: 0.25\n")

    analysis = analyze("LEV", conn, override_path=override)
    flag = next(f for f in analysis.narrative_flags if f.name == "story_margin")

    assert flag.color is FlagColor.UNKNOWN
    assert flag.reason.startswith("not evaluated:")


def test_analyze_returns_complete_result(seeded_conn: duckdb.DuckDBPyConnection) -> None:
    analysis = analyze("AAPL", seeded_conn)

    assert analysis.ticker == "AAPL"
    assert analysis.name == "Apple Inc"
    assert analysis.currency == "USD"
    # DCF ran and produced an intrinsic value and year-by-year projections.
    assert analysis.dcf_result.intrinsic_value > 0.0
    assert len(analysis.dcf_result.projections) == 5
    # Story type was auto-assigned (mature-stable for this steady grower).
    assert analysis.story_type == StoryType.MATURE_STABLE
    assert analysis.story_reasons  # at least one reason string
    # Sensitivity: tornado has one entry per axis; the 2-D grid is 5x5.
    assert len(analysis.tornado) == len(list(SensitivityAxis))
    assert len(analysis.grid.cells) == 5
    assert all(len(row) == 5 for row in analysis.grid.cells)
    # Five narrative flags.
    assert len(analysis.narrative_flags) == 5
    assert all(f.color in set(FlagColor) for f in analysis.narrative_flags)


def test_analyze_margin_of_safety_against_price(
    seeded_conn: duckdb.DuckDBPyConnection,
) -> None:
    analysis = analyze("AAPL", seeded_conn)
    assert analysis.current_price == 150.0
    expected = analysis.dcf_result.intrinsic_value / 150.0
    assert analysis.margin_of_safety == pytest.approx(expected)


def test_analyze_assumptions_carry_sources(
    seeded_conn: duckdb.DuckDBPyConnection,
) -> None:
    analysis = analyze("AAPL", seeded_conn)
    # Operating margin defaults to the Damodaran sector median.
    assert analysis.assumptions.operating_margin.source == (
        AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    )
    # Revenue growth comes from the company's own history in the M1 universe.
    assert analysis.assumptions.revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE


def test_analyze_sanity_check_vs_sector_multiples(
    seeded_conn: duckdb.DuckDBPyConnection,
) -> None:
    analysis = analyze("AAPL", seeded_conn)
    # The seed's 2025 net income and diluted shares, both in millions.
    eps = 100_000.0 / 15_500.0
    assert analysis.sanity_check.sector_pe == 22.0
    # The implied P/E is the DCF's multiple; the market P/E sits beside it.
    assert analysis.sanity_check.implied_pe == pytest.approx(
        analysis.dcf_result.intrinsic_value / eps
    )
    assert analysis.sanity_check.market_pe == pytest.approx(23.25)


def _check(
    *,
    current_price: float | None = 100.0,
    net_income: float | None = 10.0,
    shares: float | None = 1.0,
    intrinsic_value: float = 150.0,
) -> SanityCheck:
    return _sanity_check(
        current_price=current_price,
        net_income=net_income,
        shares=shares,
        intrinsic_value=intrinsic_value,
        enterprise_value=500.0,
        revenue=100.0,
        sector=_SectorMultiples(
            region=None, pe=22.0, ev_sales=5.0, op_margin=None, beta_levered=None, erp=None
        ),
    )


def test_sanity_check_implied_pe_comes_from_the_dcf() -> None:
    check = _check()
    assert check.implied_pe == pytest.approx(15.0)
    assert check.market_pe == pytest.approx(10.0)
    assert check.implied_ev_sales == pytest.approx(5.0)
    assert check.sector_pe == 22.0


def test_sanity_check_without_price_keeps_implied_pe() -> None:
    check = _check(current_price=None)
    assert check.implied_pe == pytest.approx(15.0)
    assert check.market_pe is None


@pytest.mark.parametrize("net_income", [0.0, -5.0, None])
def test_sanity_check_non_positive_net_income_gives_no_pe(net_income: float | None) -> None:
    check = _check(net_income=net_income)
    assert check.implied_pe is None
    assert check.market_pe is None


@pytest.mark.parametrize("shares", [0.0, None])
def test_sanity_check_no_shares_gives_no_pe(shares: float | None) -> None:
    check = _check(shares=shares)
    assert check.implied_pe is None
    assert check.market_pe is None


@pytest.mark.parametrize("intrinsic_value", [0.0, -3.0])
def test_sanity_check_non_positive_intrinsic_value_gives_no_implied_pe(
    intrinsic_value: float,
) -> None:
    check = _check(intrinsic_value=intrinsic_value)
    assert check.implied_pe is None
    assert check.market_pe == pytest.approx(10.0)


def test_flags_change_neither_the_verdict_nor_the_sanity_check(
    seeded_conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The analyze boards chain flags, verdict and sanity check in execution order only (#221)."""
    baseline = analyze("AAPL", seeded_conn)

    def red(*args: object, **kwargs: object) -> tuple[NarrativeFlag, ...]:
        return (NarrativeFlag("forced", FlagColor.RED, "forced red"),)

    monkeypatch.setattr("bot.valuator.analysis.narrative_flags", red)
    monkeypatch.setattr("bot.valuator.analysis.hypergrowth_flags", red)
    forced = analyze("AAPL", seeded_conn)
    assert all(f.color is FlagColor.RED for f in forced.narrative_flags)
    assert forced.margin_of_safety == baseline.margin_of_safety
    assert margin_verdict(forced.margin_of_safety) == margin_verdict(baseline.margin_of_safety)
    assert forced.sanity_check == baseline.sanity_check


def test_analyze_manual_override_applied(
    seeded_conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    override = tmp_path / "AAPL.yaml"
    override.write_text(
        "story_type: high-growth\n"
        "operating_margin: 0.35\n"
        "notes: Services mix lifts steady-state margin.\n"
    )
    analysis = analyze("AAPL", seeded_conn, override_path=override)
    assert analysis.story_type == "high-growth"
    assert analysis.assumptions.operating_margin.value == pytest.approx((0.35,) * 5)
    assert analysis.assumptions.operating_margin.source == AssumptionSource.MANUAL
    assert analysis.override_notes == "Services mix lifts steady-state margin."


def test_analyze_uncovered_currency_raises_value_error(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """A currency outside the table leaves terminal_growth unresolved (#109)."""
    _seed_company(conn, ticker="XCO", industry_damodaran="Computers/Peripherals")
    _seed_leveraged_financials(conn, ticker="XCO")
    conn.execute("UPDATE financials_annual SET currency = 'XYZ' WHERE ticker = 'XCO'")
    with pytest.raises(ValueError, match="terminal_growth"):
        analyze("XCO", conn)


def test_analyze_unknown_ticker_raises(seeded_conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(LookupError):
        analyze("NOPE", seeded_conn)


def test_cyclical_story_reachable_from_the_sector(conn: duckdb.DuckDBPyConnection) -> None:
    # A steel company with volatile earnings must classify as cyclical without the
    # caller passing anything: the sector signal now comes from the DB.
    _seed_company(conn, ticker="STEEL", industry_damodaran="Steel")
    _seed_volatile_financials(conn, ticker="STEEL")
    result = analyze("STEEL", conn)
    assert result.story_type == StoryType.CYCLICAL.value


def test_caller_can_still_force_non_cyclical(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_company(conn, ticker="STEEL2", industry_damodaran="Steel")
    _seed_volatile_financials(conn, ticker="STEEL2")
    result = analyze("STEEL2", conn, is_cyclical_sector=False)
    assert result.story_type != StoryType.CYCLICAL.value


def _seed_high_cagr_financials(conn: duckdb.DuckDBPyConnection, ticker: str) -> None:
    """Revenue history with a ~20% CAGR — clears ``_HIGH_GROWTH_CAGR`` (0.15)."""
    fiscal_years = (2021, 2022, 2023, 2024, 2025)
    revenues = (100_000.0, 120_000.0, 144_000.0, 172_800.0, 207_360.0)
    for year, revenue in zip(fiscal_years, revenues, strict=True):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                ticker,
                year,
                revenue * _MILLIONS,
                revenue * 0.15 * _MILLIONS,
                revenue * 0.10 * _MILLIONS,
                0.0,
                0.0,
                0.0,
                1_000.0 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )


def test_analyze_derives_age_from_ipo_date_old_company_is_not_high_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # A 40-year-old company with a 20% revenue CAGR: the age rule (§7.1) must
    # disqualify it from high-growth even though the growth signal clears the
    # threshold on its own.
    _seed_company(conn, ticker="OLD", industry_damodaran="Computers/Peripherals")
    _seed_high_cagr_financials(conn, ticker="OLD")
    ipo_date = date.today() - timedelta(days=40 * 365)
    conn.execute("UPDATE companies SET ipo_date = ? WHERE ticker = ?", [ipo_date, "OLD"])

    result = analyze("OLD", conn)

    assert result.story_type != StoryType.HIGH_GROWTH.value


def test_analyze_derives_age_from_ipo_date_young_company_is_high_growth(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # Same growth profile, but a 5-year-old company: young enough for the
    # high-growth rule to fire once age_years is derived from ipo_date.
    _seed_company(conn, ticker="YOUNG", industry_damodaran="Computers/Peripherals")
    _seed_high_cagr_financials(conn, ticker="YOUNG")
    ipo_date = date.today() - timedelta(days=5 * 365)
    conn.execute("UPDATE companies SET ipo_date = ? WHERE ticker = ?", [ipo_date, "YOUNG"])

    result = analyze("YOUNG", conn)

    assert result.story_type == StoryType.HIGH_GROWTH.value


def test_analyze_explicit_age_years_wins_over_ipo_date(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # A young company by ipo_date, but the caller explicitly passes an old age:
    # the explicit value must win over the derived one.
    _seed_company(conn, ticker="EXPLICIT", industry_damodaran="Computers/Peripherals")
    _seed_high_cagr_financials(conn, ticker="EXPLICIT")
    ipo_date = date.today() - timedelta(days=5 * 365)
    conn.execute("UPDATE companies SET ipo_date = ? WHERE ticker = ?", [ipo_date, "EXPLICIT"])

    result = analyze("EXPLICIT", conn, age_years=40)

    assert result.story_type != StoryType.HIGH_GROWTH.value


# --- #124: implausible share counts are refused ---------------------------------


def _set_latest_shares(conn: duckdb.DuckDBPyConnection, shares: float) -> None:
    conn.execute(
        "UPDATE financials_annual SET shares_diluted = ? WHERE ticker = 'AAPL' "
        "AND fiscal_year = (SELECT max(fiscal_year) FROM financials_annual WHERE ticker = 'AAPL')",
        [shares],
    )


@pytest.mark.parametrize("shares", [732.3, 999_999.0, 100_000_000_001.0])
def test_analyze_refuses_implausible_share_count(
    seeded_conn: duckdb.DuckDBPyConnection, shares: float
) -> None:
    _set_latest_shares(seeded_conn, shares)
    with pytest.raises(ValueError, match="implausible diluted share count"):
        analyze("AAPL", seeded_conn)


@pytest.mark.parametrize("shares", [1_000_000.0, 100_000_000_000.0])
def test_analyze_accepts_share_count_at_bounds(
    seeded_conn: duckdb.DuckDBPyConnection, shares: float
) -> None:
    _set_latest_shares(seeded_conn, shares)
    analyze("AAPL", seeded_conn)


# --- #195: hypergrowth classified before distress, gated on the story file ------


def _seed_anthropic(conn: duckdb.DuckDBPyConnection, ticker: str = "ANTH") -> None:
    """Anthropic at its IPO, in raw units: revenue 1,020M then 20,608M, margin -228%,
    interest coverage below 1, 114B cash; its sector's median margin is 28%."""
    _seed_company(conn, ticker=ticker, industry_damodaran="Software (System & Application)")
    conn.execute("UPDATE damodaran_industry SET op_margin = 0.28")
    for year, revenue in ((2024, 1_020.0), (2025, 20_608.0)):
        ebit = -2.2798 * revenue
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                ticker,
                year,
                revenue * _MILLIONS,
                ebit * _MILLIONS,
                ebit * _MILLIONS,
                1_000.0 * _MILLIONS,
                0.0,
                114_000.0 * _MILLIONS,
                3_298.14 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )


def _flag(a: Analysis, name: str) -> NarrativeFlag:
    return next(f for f in a.narrative_flags if f.name == name)


def _story_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "ANTH.yaml"
    path.write_text(yaml.safe_dump({"story_type": "hypergrowth", "story": _STORY}))
    return path


def test_hypergrowth_without_story_values_as_high_growth_with_red_flag(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_anthropic(conn)
    a = analyze("ANTH", conn)
    assert a.story_type == "high-growth"
    assert a.auto_story_type == "hypergrowth"
    assert a.story_file_present is False
    assert len(a.narrative_flags) == 6
    assert a.narrative_flags[-1].name == "hypergrowth_story"
    assert a.narrative_flags[-1].color is FlagColor.RED
    assert not any("manually overridden" in r for r in a.story_reasons)
    assert (
        "hypergrowth signals but no story file: valued as high-growth, "
        "see the hypergrowth_story flag"
    ) in a.story_reasons


def test_hypergrowth_reasons_list_the_signals(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_anthropic(conn)
    reasons = analyze("ANTH", conn).story_reasons
    assert reasons[:5] == (
        "last-year revenue growth 1920.4%",
        "revenue CAGR 1920.4% over 1 years",
        "operating margin -228.0% below sector 28.0%",
        "founding year unknown",
        "classified as hypergrowth",
    )


def test_hypergrowth_reasons_name_the_founding_age(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic(conn)
    override = tmp_path / "ANTH.yaml"
    override.write_text(f"founded_year: {date.today().year - 5}\n")
    assert "founded 5 years ago" in analyze("ANTH", conn, override_path=override).story_reasons


def test_hypergrowth_with_story_file(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _seed_anthropic(conn)
    a = analyze("ANTH", conn, override_path=_story_yaml(tmp_path))
    assert a.story_type == "hypergrowth"
    assert a.auto_story_type == "hypergrowth"
    assert a.story_file_present is True
    assert _flag(a, "hypergrowth_story").color is FlagColor.GREEN
    # The story drives the projection (#196).
    assert a.assumptions.revenue_growth.source is AssumptionSource.STORY
    assert a.assumptions.operating_margin.source is AssumptionSource.STORY
    assert not any("no story file" in r for r in a.story_reasons)


# --- #196: the story drives the valuation ---------------------------------------


def _seed_anthropic_sheet(conn: duckdb.DuckDBPyConnection, ticker: str = "ANTH") -> None:
    """Anthropic as in Damodaran's 2026-11-03 sheet, in raw dollars: revenue 1,020M then
    35,286M (trailing), EBIT -46,313M (margin -131.25%), coverage < 1, no debt, 112,389M
    cash, 3,302.27M shares; sector WACC 9.13%, margin 28%, ROIC 12%, tax 25%."""
    _seed_company(conn, ticker=ticker, industry_damodaran="Software (System & Application)")
    conn.execute(
        "UPDATE damodaran_industry SET wacc = 0.0913, op_margin = 0.28, roic = 0.12, "
        "tax_rate = 0.25"
    )
    for year, revenue, ebit in ((2024, 1_020.0, -2_325.0), (2025, 35_286.0, -46_313.0)):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, interest_expense, "
            "total_debt, cash, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [
                ticker,
                year,
                revenue * _MILLIONS,
                ebit * _MILLIONS,
                ebit * _MILLIONS,
                1_000.0 * _MILLIONS,
                0.0,
                112_389.0 * _MILLIONS,
                3_302.27 * _MILLIONS,
                False,
                "sec_edgar",
            ],
        )


def _sheet_yaml(tmp_path: Path, **extra: object) -> Path:
    path = tmp_path / "ANTH.yaml"
    # sort_keys=False keeps scenario order (file order is the contract).
    path.write_text(
        yaml.safe_dump({"story_type": "hypergrowth", "story": _STORY, **extra}, sort_keys=False)
    )
    return path


def test_hypergrowth_story_values_anthropic_end_to_end(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic_sheet(conn)
    a = analyze(
        "ANTH", conn, override_path=_sheet_yaml(tmp_path, terminal_growth=0.049, tax_rate=0.25)
    )
    # Expected 438.93: the sheet's adjustments line (3,929 - 472.30) is not an override key.
    assert a.dcf_result.intrinsic_value == pytest.approx(439.24, rel=0.01)
    assert a.story_type == "hypergrowth"
    assert a.assumptions.revenue_growth.source is AssumptionSource.STORY
    assert a.assumptions.operating_margin.source is AssumptionSource.STORY
    assert a.dcf_result.wacc_path is not None
    assert a.financials.fixed_commitments == 485_319.79e6
    assert a.financials.extra_cash == 100_000e6
    assert len(a.narrative_flags) == 8


def test_hypergrowth_story_without_terminal_growth_uses_currency_rule(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic_sheet(conn)
    a = analyze("ANTH", conn, override_path=_sheet_yaml(tmp_path, tax_rate=0.25))
    assert a.assumptions.terminal_growth.source is AssumptionSource.RULE_BASED
    assert a.assumptions.terminal_growth.value == pytest.approx(0.0395)
    assert a.dcf_result.projections[-1].revenue == pytest.approx(1_004_515.6e6, rel=1e-9)
    assert math.isfinite(a.dcf_result.intrinsic_value)


def test_hypergrowth_story_replaces_manual_generic_keys(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic_sheet(conn)
    a = analyze(
        "ANTH",
        conn,
        override_path=_sheet_yaml(
            tmp_path, terminal_growth=0.049, operating_margin=0.35, revenue_growth=0.10
        ),
    )
    assert a.assumptions.operating_margin.source is AssumptionSource.STORY
    assert a.assumptions.operating_margin.value == margin_path(parse_story(_STORY, where="x"))
    assert a.assumptions.revenue_growth.source is AssumptionSource.STORY
    assert a.dcf_result.projections[-1].revenue == pytest.approx(1_004_515.6e6, rel=1e-9)


def test_founded_year_40_years_back_is_distressed(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic(conn)
    override = tmp_path / "ANTH.yaml"
    override.write_text(f"founded_year: {date.today().year - 40}\n")
    a = analyze("ANTH", conn, override_path=override)
    assert a.story_type == "distressed"
    assert len(a.narrative_flags) == 5


def test_mature_company_still_has_five_flags(seeded_conn: duckdb.DuckDBPyConnection) -> None:
    a = analyze("AAPL", seeded_conn)
    assert len(a.narrative_flags) == 5
    assert "hypergrowth_story" not in {f.name for f in a.narrative_flags}
    assert a.auto_story_type == a.story_type
    assert a.story_file_present is False


def test_hypergrowth_fallback_keeps_other_override_keys(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic(conn)
    override = tmp_path / "ANTH.yaml"
    override.write_text("operating_margin: 0.35\n")
    a = analyze("ANTH", conn, override_path=override)
    assert a.story_type == "high-growth"
    assert a.assumptions.operating_margin.source is AssumptionSource.MANUAL
    assert a.narrative_flags[-1].color is FlagColor.RED


def test_manual_override_of_hypergrowth_says_overridden(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic(conn)
    override = tmp_path / "ANTH.yaml"
    override.write_text("story_type: mature-stable\n")
    a = analyze("ANTH", conn, override_path=override)
    assert a.story_type == "mature-stable"
    assert a.story_reasons[0].startswith("manually overridden")
    assert "hypergrowth" in a.story_reasons[0]
    flag = next(f for f in a.narrative_flags if f.name == "hypergrowth_story")
    assert flag.color is FlagColor.RED


def test_story_file_without_hypergrowth_signals_is_yellow(
    seeded_conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # A story file on a mature company: the label is manual, the flag says the
    # classifier does not back it.
    a = analyze("AAPL", seeded_conn, override_path=_story_yaml(tmp_path))
    assert a.story_type == "hypergrowth"
    assert a.auto_story_type != "hypergrowth"
    assert a.story_reasons[0].startswith("manually overridden")
    assert f"would have said {a.auto_story_type}" in a.story_reasons[0]
    assert len(a.narrative_flags) == 8
    assert _flag(a, "hypergrowth_story").color is FlagColor.YELLOW


# --- #197: scenarios, governance verdict, sector ROIC ---------------------------

#: Damodaran's worst and best scenarios in raw dollars (worst drag 10 points).
_SCENARIOS: dict[str, dict[str, float]] = {
    "worst": {
        "target_revenue_y10": 200_000e6,
        "target_margin": 0.10,
        "sales_to_capital": 1.0,
        "wacc_start": 0.0988,
        "regulatory_drag": 0.10,
    },
    "best": {
        "target_revenue_y10": 1_500_000e6,
        "target_margin": 0.40,
        "sales_to_capital": 4.0,
        "wacc_start": 0.0779,
        "regulatory_drag": 0.0,
    },
}


def _seed_price(conn: duckdb.DuckDBPyConnection, ticker: str = "ANTH", close: float = 300.0) -> None:
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "2026-10-30", close, close * 3_302.27 * _MILLIONS, "USD", "stooq"],
    )


def hypergrowth_analysis(
    conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
    *,
    scenarios: bool = True,
    price: bool = True,
) -> Analysis:
    """The Anthropic sheet with the full story (governance 20%), and the scenarios."""
    _seed_anthropic_sheet(conn)
    if price:
        _seed_price(conn)
    extra: dict[str, object] = {"terminal_growth": 0.049, "tax_rate": 0.25}
    if scenarios:
        extra["scenarios"] = _SCENARIOS
    return analyze("ANTH", conn, override_path=_sheet_yaml(tmp_path, **extra))


def test_hypergrowth_scenarios_governance_and_flags(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    a = hypergrowth_analysis(conn, tmp_path)
    assert [s.name for s in a.scenarios] == ["base", "worst", "best"]
    assert a.scenarios[0].equity_value == a.dcf_result.equity_value
    assert a.scenarios[0].intrinsic_value == a.dcf_result.intrinsic_value
    assert a.scenarios[1].equity_value < 0 < a.scenarios[2].equity_value
    assert a.governance_discount == 0.20
    assert a.intrinsic_value_after_governance == a.dcf_result.intrinsic_value * (1 - 0.20)
    assert a.current_price is not None
    assert a.margin_of_safety == a.intrinsic_value_after_governance / a.current_price
    assert len(a.narrative_flags) == 8
    assert [f.name for f in a.narrative_flags[5:]] == [
        "hypergrowth_story",
        "hypergrowth_revenue_scale",
        "hypergrowth_terminal_roic",
    ]
    assert _flag(a, "hypergrowth_revenue_scale").color is FlagColor.YELLOW
    roic = _flag(a, "hypergrowth_terminal_roic")
    assert roic.color is FlagColor.GREEN
    assert "12.0%" in roic.reason


def test_hypergrowth_without_scenarios_has_no_range(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    a = hypergrowth_analysis(conn, tmp_path, scenarios=False)
    assert a.scenarios == ()
    assert a.governance_discount == 0.20


def test_hypergrowth_unreachable_scenario_fails_the_ticker(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _seed_anthropic_sheet(conn)
    override = _sheet_yaml(
        tmp_path, terminal_growth=0.049, scenarios={"worst": {"target_revenue_y10": 1e40}}
    )
    with pytest.raises(ValueError, match="scenario worst"):
        analyze("ANTH", conn, override_path=override)


def test_loaders_carry_sector_roic(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_anthropic_sheet(conn)
    single = load_valuation_input(conn, "ANTH")
    bulk = bulk_load_valuation_inputs(conn, ["ANTH"])["ANTH"]
    assert single.sector.roic == 0.12
    assert bulk.sector.roic == single.sector.roic


def test_mature_company_margin_unchanged(seeded_conn: duckdb.DuckDBPyConnection) -> None:
    a = analyze("AAPL", seeded_conn)
    assert a.governance_discount == 0.0
    assert a.scenarios == ()
    assert a.intrinsic_value_after_governance == a.dcf_result.intrinsic_value
    assert a.current_price is not None
    assert a.margin_of_safety == a.dcf_result.intrinsic_value / a.current_price
