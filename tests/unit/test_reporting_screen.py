"""Unit tests for the screen Markdown + CSV report (issue #9, spec §9.1)."""

from __future__ import annotations

import csv
import io
from datetime import date

from bot.reporting.screen_report import COLUMNS, render_csv, render_markdown
from bot.screener.engine import ScreenedCompany, ScreenResult


def _company(ticker: str, *, sector: str | None = "Software") -> ScreenedCompany:
    return ScreenedCompany(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector=sector,
        region="US",
        market_cap=5e9,
        pe=10.5,
        ev_ebitda=5.0,
        pbv=1.2,
        roe=0.2,
        roic=0.15,
        fcf_yield=0.1,
        passed=True,
        passed_gates=("min_market_cap",),
        failed_gates=(),
        score=87.5,
        value_score=0.9,
        quality_score=0.8,
        growth_score=0.7,
        margin_of_safety=0.5,
    )


def test_markdown_has_header_and_rows() -> None:
    result = ScreenResult(
        preset="damodaran_value",
        shortlist=(_company("AAA"), _company("BBB")),
        screened=12,
    )
    md = render_markdown(result, generated_on=date(2026, 5, 30))
    assert "# Screen — damodaran_value" in md
    assert "Screened 12 companies" in md
    for col in COLUMNS:
        assert col in md
    assert "AAA" in md
    assert "2026-05-30" in md


def test_markdown_empty_shortlist() -> None:
    result = ScreenResult(preset="p", shortlist=(), screened=3)
    md = render_markdown(result, generated_on=date(2026, 5, 30))
    assert "No companies cleared the screen" in md


def test_csv_columns_match_markdown() -> None:
    result = ScreenResult(
        preset="p", shortlist=(_company("AAA"), _company("BBB")), screened=2
    )
    rows = list(csv.DictReader(io.StringIO(render_csv(result))))
    assert len(rows) == 2
    assert tuple(rows[0].keys()) == COLUMNS
    # Machine-readable: numeric cells round-trip through float().
    assert float(rows[0]["score"]) == 87.5
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["rank"] == "1"


def test_csv_renders_none_sector_as_empty() -> None:
    result = ScreenResult(preset="p", shortlist=(_company("AAA", sector=None),), screened=1)
    rows = list(csv.DictReader(io.StringIO(render_csv(result))))
    assert rows[0]["sector"] == ""


def test_csv_empty_shortlist_is_header_only() -> None:
    result = ScreenResult(preset="p", shortlist=(), screened=0)
    out = render_csv(result)
    rows = list(csv.reader(io.StringIO(out)))
    assert len(rows) == 1
    assert tuple(rows[0]) == COLUMNS
