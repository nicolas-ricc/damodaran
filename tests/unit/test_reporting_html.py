"""Unit tests for the §7.7 HTML analysis report renderer (issue #30, M6.1).

The HTML renderer turns the Markdown report of M4.6 into a self-contained HTML
page (no external assets) and injects a base64-inlined Matplotlib tornado chart
whose bars match the textual tornado of M4.3 — same ordering and same values.
"""

from __future__ import annotations

import base64
import re

import duckdb
import pytest

from bot.reporting.analysis_report import render_analysis
from bot.reporting.html import (
    render_analysis_html,
    sensitivity_heatmap_html,
    tornado_chart_png,
)
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
    for year, revenue in {
        2022: 380_000.0,
        2023: 395_000.0,
        2024: 410_000.0,
        2025: 430_000.0,
    }.items():
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


def test_tornado_chart_is_png_bytes(analysis: Analysis) -> None:
    png = tornado_chart_png(analysis.tornado)
    # PNG magic number.
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_html_is_self_contained_with_inlined_chart(analysis: Analysis) -> None:
    html = render_analysis_html(analysis)
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<html" in html and "</html>" in html
    # The tornado chart is inlined as a base64 data URI — no external assets.
    assert "data:image/png;base64," in html
    # No tag-level external references: no <img src=http…>, <script src=…>, or <link>.
    # (The inlined Plotly bundle may contain http URLs in JS *string literals*, but
    # the page fetches nothing on load — those are not tag attributes.)
    assert 'img class="tornado" alt' in html
    assert "<img" in html and 'src="data:image/png' in html
    assert "<script src=" not in html
    assert "<link" not in html
    # The base64 payload decodes back to a PNG.
    match = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
    assert match is not None
    assert base64.b64decode(match.group(1))[:8] == b"\x89PNG\r\n\x1a\n"


def test_html_embeds_rendered_markdown(analysis: Analysis) -> None:
    html = render_analysis_html(analysis)
    # MD→HTML: the §7.7 headings become real HTML headings.
    assert "<h1" in html
    assert "AAPL" in html
    # Section names from the Markdown survive the conversion.
    for section in ("Executive summary", "Sensitivity", "Narrative flags", "Sanity check"):
        assert section in html


def test_chart_matches_textual_tornado_ordering_and_values(analysis: Analysis) -> None:
    # The chart axis labels and impacts come straight from a.tornado, which is
    # the same source the Markdown table renders — so ordering and values match.
    md = render_analysis(analysis)
    for entry in analysis.tornado:
        assert entry.axis.value in md
    # The renderer must read the same ordered tornado entries (descending impact).
    impacts = [entry.impact for entry in analysis.tornado]
    assert impacts == sorted(impacts, reverse=True)


def test_heatmap_fragment_inlines_plotly_js_and_renders_a_plot(analysis: Analysis) -> None:
    # M6.2: the 2-D sensitivity grid renders to an interactive Plotly heatmap whose
    # JS is inlined (no external <script src>) so the fragment is self-contained.
    fragment = sensitivity_heatmap_html(analysis.grid)
    # The Plotly library is embedded, not pulled from a CDN: no external script tag.
    assert "<script" in fragment
    assert 'script src="http' not in fragment.lower()
    assert "<script src=" not in fragment
    # The heatmap trace is present.
    assert '"type":"heatmap"' in fragment.replace(" ", "")


def test_heatmap_z_values_are_the_grid_margins_of_safety(analysis: Analysis) -> None:
    # Every cell's margin of safety must appear in the heatmap's z matrix so the
    # colours faithfully encode the grid the Markdown table renders.
    fragment = sensitivity_heatmap_html(analysis.grid)
    for row in analysis.grid.cells:
        for cell in row:
            assert str(round(cell.margin_of_safety, 4)) in fragment


def test_heatmap_hover_shows_margin_of_safety_and_intrinsic_value(analysis: Analysis) -> None:
    # Acceptance: hover tooltip shows per-cell margin of safety and intrinsic value.
    fragment = sensitivity_heatmap_html(analysis.grid)
    assert "Margin of safety" in fragment
    assert "Intrinsic value" in fragment
    # The per-cell intrinsic values are carried as customdata for the tooltip.
    for row in analysis.grid.cells:
        for cell in row:
            assert str(round(cell.intrinsic_value, 4)) in fragment


def test_full_report_embeds_the_self_contained_heatmap(analysis: Analysis) -> None:
    # The M6.1 report now also carries the interactive heatmap, still self-contained.
    html = render_analysis_html(analysis)
    # No external script tags slipped in alongside the inlined library.
    assert "<script src=" not in html
    assert 'script src="http' not in html.lower()
    # The axis names from the grid are present so the heatmap is labelled.
    assert analysis.grid.axis_a.value in html
    assert analysis.grid.axis_b.value in html
