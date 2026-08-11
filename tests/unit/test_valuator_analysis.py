"""Unit tests for the end-to-end analysis pipeline (spec §7.7, issue #16).

The pipeline is a pure function of ``(ticker, conn, override_path)`` that loads a
company's data from the DB, resolves assumptions, runs the two-stage DCF plus
sensitivity and narrative flags, and packages everything the §7.7 report needs.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import Analysis, analyze
from bot.valuator.assumptions import AssumptionSource
from bot.valuator.narrative_flags import FlagColor
from bot.valuator.sensitivity import SensitivityAxis
from bot.valuator.story_types import StoryType


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAPL", "Apple Inc", "United States", "USD", "Computers/Peripherals", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country "
        "(country, year, erp, risk_free_rate, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["United States", 2026, 0.045, 0.04, 0.21, "US"],
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
            "total_debt, cash, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "AAPL",
                year,
                revenue,
                revenue * 0.30,
                incomes[year],
                3_000.0,
                110_000.0,
                60_000.0,
                15_500.0,
                False,
                "sec_edgar",
            ],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAPL", "2026-05-29", 150.0, 2_325_000.0, "USD", "fmp"],
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
        "(country, year, erp, risk_free_rate, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["United States", 2026, 0.045, 0.04, 0.21, "US"],
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
            "total_debt, cash, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ticker,
                year,
                revenue,
                net_income * 1.2,
                net_income,
                0.0,
                200.0,
                50.0,
                100.0,
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
            "total_debt, cash, total_equity, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ticker,
                year,
                revenue,
                revenue * 0.30,
                revenue * 0.20,
                3_000.0,
                200_000.0,
                60_000.0,
                163_636.0,
                15_500.0,
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
    # The implied PE (price / EPS) is compared to the sector PE multiple.
    assert analysis.sanity_check.sector_pe == 22.0
    assert analysis.sanity_check.implied_pe is not None
    assert analysis.sanity_check.implied_pe > 0.0


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
    assert analysis.assumptions.operating_margin.value == pytest.approx(0.35)
    assert analysis.assumptions.operating_margin.source == AssumptionSource.MANUAL
    assert analysis.override_notes == "Services mix lifts steady-state margin."


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
