"""Unit tests for the §7.7 Markdown analysis report renderer (issue #16).

The renderer is a pure projection of an :class:`Analysis` onto Markdown via the
bundled Jinja2 template, with every §7.7 section present.
"""

from __future__ import annotations

import duckdb
import pytest

from bot.reporting.analysis_report import render_analysis
from bot.storage.db import apply_schema, connect
from bot.valuator.analysis import Analysis, analyze


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAPL", "Apple Inc", "United States", "USD", "Computers/Peripherals", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, erp, risk_free_rate, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["United States", 2026, 0.045, 0.04, 0.21, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, sales_to_capital, pe, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            2.5,
            22.0,
            5.0,
        ],
    )
    for year, revenue in {2022: 380_000.0, 2023: 395_000.0, 2024: 410_000.0, 2025: 430_000.0}.items():
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, total_debt, cash, "
            "shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["AAPL", year, revenue, revenue * 0.30, 100_000.0, 110_000.0, 60_000.0,
             15_500.0, False, "sec_edgar"],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ["AAPL", "2026-05-29", 150.0, "USD", "fmp"],
    )


@pytest.fixture
def analysis() -> Analysis:
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    return analyze("AAPL", conn)


def test_render_has_all_sections(analysis: Analysis) -> None:
    md = render_analysis(analysis)
    # The eight §7.7 sections.
    for heading in (
        "# AAPL",
        "Executive summary",
        "Story type",
        "Assumptions",
        "DCF detail",
        "Sensitivity",
        "Narrative flags",
        "Sanity check",
    ):
        assert heading in md, f"missing section: {heading!r}"


def test_render_shows_assumption_sources(analysis: Analysis) -> None:
    md = render_analysis(analysis)
    # Each assumption row labels its provenance.
    assert "sector_default_damodaran" in md
    assert "historical_average" in md


def test_render_shows_year_by_year_and_terminal(analysis: Analysis) -> None:
    md = render_analysis(analysis)
    # One row per forecast year plus a terminal line.
    for year in range(1, 6):
        assert f"| {year} " in md
    assert "Terminal" in md


def test_render_includes_margin_of_safety_headline(analysis: Analysis) -> None:
    md = render_analysis(analysis)
    assert "Margin of safety" in md
    assert f"{analysis.dcf_result.intrinsic_value:,.2f}" in md


def test_render_no_overrides_section_when_absent(analysis: Analysis) -> None:
    md = render_analysis(analysis)
    # The base case has no manual overrides applied.
    assert "Manual overrides" not in md or "No manual overrides" in md
