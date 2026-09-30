"""Golden shortlist for the screener's second pass (#53, behavior preservation).

The second pass was refactored to load the whole shortlist with a fixed number
of set-based scans. This test pins the shortlist it produces on a fixture DB to
the exact ``repr`` the pre-refactor code produced, so the refactor is provably
behavior-preserving.

The golden file was captured on commit ``556aa2b`` (before the refactor) with::

    uv run python -c "
    import tempfile, pathlib, duckdb
    from bot.storage.db import apply_schema
    from tests.unit.test_screener_second_pass_golden import GOLDEN, _render, _run
    conn = duckdb.connect(':memory:'); apply_schema(conn)
    GOLDEN.write_text(_render(_run(conn, pathlib.Path(tempfile.mkdtemp()))))
    "

Regenerate it the same way only when a deliberate behavior change is intended.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from bot.screener.config import ScreenerConfig, load_screener_config
from bot.screener.engine import ScreenedCompany, run_screen
from bot.screener.ranking import PLACEHOLDER_MARGIN_OF_SAFETY
from bot.storage.db import apply_schema

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "screener" / "second_pass_shortlist.golden"

#: ``(ticker, revenue growth, operating margin, close, net debt)`` per company.
#: No ``ipo_date``: ``analyze`` derives age from today's date, which would make
#: the golden output drift over time.
_COMPANIES: tuple[tuple[str, float, float, float, float], ...] = (
    ("AAA", 0.10, 0.20, 2.0, -100_000_000.0),
    ("BBB", 0.18, 0.25, 3.5, 200_000_000.0),
    ("CCC", 0.05, 0.17, 1.2, 0.0),
    ("DDD", 0.25, 0.30, 5.0, 500_000_000.0),
    ("EEE", 0.08, 0.22, 2.5, -300_000_000.0),
    ("FFF", 0.12, 0.18, 2.2, 50_000_000.0),
)

#: A manual override for one shortlisted ticker (spec §7.6).
_OVERRIDE = "revenue_growth: 0.06\noperating_margin: 0.19\nnotes: golden fixture\n"


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _preset() -> ScreenerConfig:
    return load_screener_config(
        Path(__file__).resolve().parents[2] / "config" / "presets" / "damodaran_value.yaml"
    )


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO damodaran_country "
        "(country, year, region, risk_free_rate, erp, tax_rate) VALUES (?, ?, ?, ?, ?, ?)",
        ["United States", 2026, "US", 0.04, 0.045, 0.21],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, pe, cost_of_equity, cost_of_debt, "
        "beta_levered, debt_to_equity, op_margin, sales_to_capital, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["Software", "US", 2026, 0.08, 20.0, 0.09, 0.045, 1.05, 0.20, 0.25, 2.5, 5.0],
    )
    for ticker, growth, margin, close, net_debt in _COMPANIES:
        conn.execute(
            "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [ticker, f"{ticker} Corp", "United States", "Software", "Software", "fmp"],
        )
        for offset in range(6):
            rev = 1_000_000_000.0 * ((1.0 + growth) ** offset)
            debt = max(net_debt, 0.0) + 100_000_000.0
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
                    rev * margin,
                    rev * (margin + 0.05),
                    20_000_000.0,
                    rev * margin * 0.75,
                    6_000_000_000.0,
                    debt,
                    debt - net_debt,
                    2_000_000_000.0,
                    500_000_000.0,
                    rev * margin * 0.9,
                    rev * margin * 0.7,
                    1_000_000_000.0,
                    False,
                    "fmp",
                ],
            )
        conn.execute(
            "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [ticker, "2026-05-29", close, close * 1_000_000_000.0, "USD", "fmp"],
        )


def _run(conn: duckdb.DuckDBPyConnection, assumptions_dir: Path) -> tuple[ScreenedCompany, ...]:
    _seed(conn)
    (assumptions_dir / "BBB.yaml").write_text(_OVERRIDE)
    return run_screen(conn, _preset(), top=5, assumptions_dir=assumptions_dir).shortlist


def _render(shortlist: tuple[ScreenedCompany, ...]) -> str:
    return "\n".join(repr(c) for c in shortlist) + "\n"


def test_second_pass_shortlist_matches_golden(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    shortlist = _run(conn, tmp_path)

    # Guard against a vacuous golden: the valuator really valued the shortlist.
    assert any(c.margin_of_safety != PLACEHOLDER_MARGIN_OF_SAFETY for c in shortlist)
    assert _render(shortlist) == GOLDEN.read_text()
