"""Unit tests for the portfolio report data + Jinja2 rendering (M5, #29)."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from bot.portfolio.events import Event, EventType
from bot.portfolio.report import (
    ConcentrationRow,
    HistoryRow,
    PortfolioReport,
    PositionRow,
    build_report,
    render_alerts,
    render_portfolio,
)
from bot.storage.db import apply_schema

D1 = date(2026, 5, 1)
D2 = date(2026, 5, 2)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _insert(
    conn: duckdb.DuckDBPyConnection,
    snapshot_date: date,
    rows: list[tuple[str, int, float, float, float, str]],
) -> None:
    for ticker, con_id, qty, avg_cost, mv, ccy in rows:
        conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, account, ticker, con_id, qty, avg_cost, market_value, currency) "
            "VALUES (?, 'DU1', ?, ?, ?, ?, ?, ?)",
            [snapshot_date, ticker, con_id, qty, avg_cost, mv, ccy],
        )


def test_position_row_pnl_math() -> None:
    p = PositionRow("AAPL", qty=10.0, avg_cost=100.0, market_value=1200.0, currency="USD")
    assert p.cost_basis == 1000.0
    assert p.pnl == 200.0
    assert p.pnl_pct == pytest.approx(0.2)


def test_position_row_pnl_none_when_no_market_value() -> None:
    p = PositionRow("AAPL", qty=10.0, avg_cost=100.0, market_value=None, currency="USD")
    assert p.pnl is None
    assert p.pnl_pct is None


def test_position_row_pnl_pct_zero_basis() -> None:
    p = PositionRow("AAPL", qty=0.0, avg_cost=100.0, market_value=10.0, currency="USD")
    assert p.pnl_pct is None


def test_build_report_aggregates_and_weights(conn: duckdb.DuckDBPyConnection) -> None:
    _insert(
        conn,
        D2,
        [
            ("AAPL", 1, 100.0, 120.0, 17000.0, "USD"),
            ("MSFT", 2, 10.0, 300.0, 1000.0, "USD"),
        ],
    )
    conn.execute(
        "INSERT INTO cash_balances (snapshot_date, account, currency, amount) "
        "VALUES (?, 'DU1', 'USD', 500.0)",
        [D2],
    )
    report = build_report(conn, D2)
    assert report.total_market_value == pytest.approx(18000.0)
    assert report.total_cost_basis == pytest.approx(15000.0)
    assert report.total_pnl == pytest.approx(3000.0)
    assert report.cash == (("USD", 500.0),)
    # Concentration: AAPL 17000/18000 ~94% > 15% threshold; MSFT ~5.6% below it.
    aapl = next(c for c in report.concentration if c.ticker == "AAPL")
    assert aapl.flagged is True
    msft = next(c for c in report.concentration if c.ticker == "MSFT")
    assert msft.flagged is False
    # Sorted descending by weight.
    assert report.concentration[0].ticker == "AAPL"


def test_build_report_history(conn: duckdb.DuckDBPyConnection) -> None:
    _insert(conn, D1, [("AAPL", 1, 10.0, 100.0, 1100.0, "USD")])
    _insert(conn, D2, [("AAPL", 1, 10.0, 100.0, 1300.0, "USD")])
    report = build_report(conn, D2, include_history=True)
    assert [h.snapshot_date for h in report.history] == [D1, D2]
    assert report.history[0].pnl == pytest.approx(100.0)
    assert report.history[1].pnl == pytest.approx(300.0)


def test_build_report_no_history_when_not_requested(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _insert(conn, D2, [("AAPL", 1, 10.0, 100.0, 1100.0, "USD")])
    report = build_report(conn, D2)
    assert report.history == ()


def test_build_report_empty_snapshot(conn: duckdb.DuckDBPyConnection) -> None:
    report = build_report(conn, D2)
    assert report.positions == ()
    assert report.concentration == ()
    assert report.total_market_value == 0.0


def test_render_portfolio_sections() -> None:
    report = PortfolioReport(
        snapshot_date=D2,
        positions=(
            PositionRow("AAPL", 100.0, 120.0, 15000.0, "USD"),
            PositionRow("MSFT", 10.0, 300.0, 3000.0, "USD"),
        ),
        concentration=(
            ConcentrationRow("AAPL", 15000.0, 0.833, True),
            ConcentrationRow("MSFT", 3000.0, 0.167, True),
        ),
        history=(HistoryRow(D1, 17000.0, 15000.0), HistoryRow(D2, 18000.0, 15000.0)),
        cash=(("USD", 500.0),),
        total_market_value=18000.0,
        total_cost_basis=15000.0,
        concentration_threshold=0.15,
        include_history=True,
        include_concentration=True,
    )
    out = render_portfolio(report, generated_on=D2)
    assert "# Portfolio — 2026-05-02" in out
    assert "## Positions" in out
    assert "## Profit & loss" in out
    assert "## Concentration" in out
    assert "## Suggested reviews" in out
    assert "## P&L history" in out
    assert "## Concentration breakdown" in out
    assert "AAPL" in out
    assert "MSFT" in out
    # Flagged position appears in suggested reviews.
    assert "consider trimming" in out


def test_render_portfolio_no_history_section_by_default() -> None:
    report = PortfolioReport(
        snapshot_date=D2,
        positions=(),
        concentration=(),
        history=(),
        cash=(),
        total_market_value=0.0,
        total_cost_basis=0.0,
        concentration_threshold=0.15,
        include_history=False,
        include_concentration=False,
    )
    out = render_portfolio(report, generated_on=D2)
    assert "## P&L history" not in out
    assert "## Concentration breakdown" not in out
    assert "No open positions" in out
    assert "No reviews suggested" in out


def test_render_alerts_with_events() -> None:
    events = [
        Event(EventType.POSITION_OPENED, "NVDA", D2, None, {"qty": 50.0}),
        Event(EventType.CONCENTRATION, "NVDA", D2, None, {"weight": 0.8}),
    ]
    out = render_alerts(events, D2, generated_on=D2)
    assert "# Alerts — 2026-05-02" in out
    assert "2 events detected today." in out
    assert "position_opened" in out
    assert "NVDA" in out


def test_render_alerts_empty_is_present_but_quiet() -> None:
    out = render_alerts([], D2, generated_on=D2)
    assert "# Alerts — 2026-05-02" in out
    assert "No events detected today." in out


def test_render_alerts_singular_event() -> None:
    events = [Event(EventType.DIVIDEND, "MSFT", D2, D1, {"amount": 0.75})]
    out = render_alerts(events, D2, generated_on=D2)
    assert "1 event detected today." in out
