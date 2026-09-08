"""Unit tests for the §7.7 Markdown analysis report renderer (issue #16).

The renderer is a pure projection of an :class:`Analysis` onto Markdown via the
bundled Jinja2 template, with every §7.7 section present.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

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
def conn() -> duckdb.DuckDBPyConnection:
    c = connect(":memory:")
    apply_schema(c)
    return c


@pytest.fixture
def analysis() -> Analysis:
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    return analyze("AAPL", conn)


def _seeded_analysis(
    conn: duckdb.DuckDBPyConnection,
    *,
    override_path: Path | None = None,
    intrinsic_per_share: float | None = None,
) -> Analysis:
    """Seed a fresh in-memory DB and run ``analyze`` on it (issue #16 helper).

    ``override_path`` is passed straight through to :func:`analyze` so a manual
    override can be exercised. ``intrinsic_per_share`` overrides the resulting
    ``dcf_result.intrinsic_value`` after the fact — the fixture data has no lever
    to force a specific DCF output, and the per-share formatting tests only care
    about the rendered magnitude, not a realistic valuation.
    """
    _seed(conn)
    analysis = analyze("AAPL", conn, override_path=override_path)
    if intrinsic_per_share is not None:
        analysis = dataclasses.replace(
            analysis,
            dcf_result=dataclasses.replace(
                analysis.dcf_result, intrinsic_value=intrinsic_per_share
            ),
        )
    return analysis


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


def test_markdown_report_keeps_flag_colours_as_plain_words(analysis: Analysis) -> None:
    # cli.py writes the .md next to the .html as its own user-facing deliverable,
    # so the HTML class hook the report's flag cells carry must be opt-in: the
    # default render stays plain Markdown, spans and all other markup out.
    md = render_analysis(analysis)
    assert "<span" not in md
    for flag in analysis.narrative_flags:
        assert f"| {flag.color} |" in md


def test_report_shows_exactly_one_wacc(analysis: Analysis) -> None:
    # There used to be two: a sector-resolved Assumptions.wacc in §3 and the
    # DCF-computed one in §1, which disagree. Only the computed one is real.
    md = render_analysis(analysis)
    assert md.count("| WACC ") == 0, "no assumptions-table WACC row"
    computed = f"{analysis.dcf_result.wacc:.1%}"
    assert computed in md


def test_report_shows_the_sourced_wacc_components(analysis: Analysis) -> None:
    # The components are what actually carry provenance, so they are what §7.3
    # traceability needs in the table.
    md = render_analysis(analysis)
    for label in ("Cost of equity", "Pre-tax cost of debt", "Equity weight", "Debt weight"):
        assert label in md, label


def test_manual_story_type_does_not_contradict_its_reasons(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    override = tmp_path / "X.yaml"
    override.write_text("story_type: distressed\n")
    analysis = _seeded_analysis(conn, override_path=override)
    assert analysis.story_type == "distressed"
    md = render_analysis(analysis)
    # The reasons used to describe the auto-classification, contradicting the
    # heading two lines above.
    assert "manually overridden" in md
    for other in ("mature-stable", "high-growth", "cyclical", "mature-decline"):
        assert f"classified as {other}" not in md


def test_report_shows_constant_margin_path_as_one_number(analysis: Analysis) -> None:
    # The base fixture has no growth/margin branching (not classified high-growth
    # or cyclical), so the operating-margin path is flat — the report shows the
    # single value, not a misleadingly precise range.
    assert analysis.assumptions.operating_margin.value is not None
    assert min(analysis.assumptions.operating_margin.value) == max(
        analysis.assumptions.operating_margin.value
    )
    md = render_analysis(analysis)
    assert "→" not in md.split("Operating margin")[1].split("\n")[0]


def test_report_shows_varying_margin_path_as_a_range(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    override = tmp_path / "X.yaml"
    override.write_text("operating_margin: [0.13, 0.14, 0.15, 0.16, 0.185]\n")
    analysis = _seeded_analysis(conn, override_path=override)
    md = render_analysis(analysis)
    assert "13.0% → 18.5%" in md


def test_tornado_path_axes_are_labelled_year_one(analysis: Analysis) -> None:
    # The tornado's revenue_growth / operating_margin rows swing year 1 only
    # (bot.valuator.sensitivity._axis_endpoint_value); a non-uniform,
    # story-branched path is not flat across years, so the report must not
    # imply the whole path moved by labelling the row as if it were.
    md = render_analysis(analysis)
    assert "revenue_growth (yr 1)" in md
    assert "operating_margin (yr 1)" in md
    # Scalar axes are unaffected.
    assert "tax_rate (yr 1)" not in md
    assert "| tax_rate |" in md


def test_per_share_values_are_not_scaled_to_thousands() -> None:
    from bot.reporting.analysis_report import _fmt_per_share

    # A per-share price of 1500 is 1500, not "1.50K".
    assert _fmt_per_share(1500.0) == "1500.00"
    assert _fmt_per_share(12.3456) == "12.35"
    assert _fmt_per_share(None) == "—"


def test_report_renders_per_share_values_unscaled(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    analysis = _seeded_analysis(conn, intrinsic_per_share=1500.0)
    md = render_analysis(analysis)
    assert "1500.00" in md
    assert "1.50K" not in md

def test_grid_heading_reflects_the_no_price_mode(analysis: Analysis) -> None:
    # With a price the cells are margins of safety; without one they are intrinsic
    # values. The heading used to claim "margin of safety" in both modes, while
    # only a note below said otherwise (the HTML title already switched).
    with_price = render_analysis(analysis)
    assert "margin of safety (intrinsic ÷ price)" in with_price
    assert "intrinsic value (no price available)" not in with_price

    no_price = render_analysis(
        dataclasses.replace(
            analysis,
            current_price=None,
            margin_of_safety=None,
            grid=dataclasses.replace(analysis.grid, reference_price=None),
        )
    )
    assert "intrinsic value (no price available)" in no_price
    assert "margin of safety (intrinsic ÷ price)" not in no_price
