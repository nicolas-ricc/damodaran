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
from bot.valuator.analysis import analyze
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
