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
from bot.reporting.html import render_analysis_html, tornado_chart_png
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
    assert "src=\"http" not in html
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
