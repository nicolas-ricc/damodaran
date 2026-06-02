"""Integration test for the ``bot portfolio`` command (M5, #29).

Drives the full cycle (sync -> diff -> report) against a **mocked**
:class:`~bot.ingest.ibkr.IbkrClient` and asserts that both ``portfolio.md`` and
``alerts.md`` are produced under the dated report directory with the expected
sections.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from bot.ingest.ibkr import CashBalance, PortfolioPosition
from bot.portfolio.command import run_portfolio
from bot.storage.db import apply_schema

TODAY = date(2026, 6, 1)


class _FakeIbkrClient:
    """A lightweight in-memory stand-in for :class:`IbkrClient`."""

    def __init__(self, positions: list[PortfolioPosition], cash: list[CashBalance]) -> None:
        self._positions = positions
        self._cash = cash
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def accounts(self) -> list[str]:
        return ["DU1"]

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        return list(self._positions)

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        return list(self._cash)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _position(symbol: str, con_id: int, qty: float, avg_cost: float) -> PortfolioPosition:
    return PortfolioPosition(
        account="DU1",
        con_id=con_id,
        symbol=symbol,
        sec_type="STK",
        currency="USD",
        exchange="NASDAQ",
        quantity=qty,
        avg_cost=avg_cost,
    )


def _client() -> _FakeIbkrClient:
    """A concentrated two-position book (AAPL ~83% -> concentration event)."""
    return _FakeIbkrClient(
        positions=[
            _position("AAPL", 1, 100.0, 120.0),
            _position("MSFT", 2, 10.0, 300.0),
        ],
        cash=[CashBalance(account="DU1", currency="USD", amount=5000.0)],
    )


def _diversified_client() -> _FakeIbkrClient:
    """Eight ~12.5% holdings (below the 15% concentration threshold)."""
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    return _FakeIbkrClient(
        positions=[_position(s, i, 10.0, 100.0) for i, s in enumerate(symbols, 1)],
        cash=[CashBalance(account="DU1", currency="USD", amount=5000.0)],
    )


def _no_analyze(ticker: str, conn: duckdb.DuckDBPyConnection) -> object:
    raise LookupError("no data for ticker in test")


def test_portfolio_writes_both_reports(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    result = run_portfolio(
        conn,
        _client(),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )

    portfolio_md = tmp_path / TODAY.isoformat() / "portfolio.md"
    alerts_md = tmp_path / TODAY.isoformat() / "alerts.md"

    assert portfolio_md.exists()
    assert alerts_md.exists()
    assert result.portfolio_path == portfolio_md
    assert result.alerts_path == alerts_md

    body = portfolio_md.read_text()
    # Full-state sections.
    assert "# Portfolio" in body
    assert "## Positions" in body
    assert "## Profit & loss" in body or "## Profit and loss" in body
    assert "## Concentration" in body
    assert "AAPL" in body
    assert "MSFT" in body

    alerts = alerts_md.read_text()
    # First snapshot -> every position opens.
    assert "AAPL" in alerts
    assert "MSFT" in alerts


def test_alerts_present_but_empty_when_no_events(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # First run on an earlier day opens everything.
    run_portfolio(
        conn,
        _diversified_client(),
        reports_dir=tmp_path,
        today=date(2026, 5, 31),
        analyze_fn=_no_analyze,
    )
    # Second run, same positions, on a new day -> no events.
    result = run_portfolio(
        conn,
        _diversified_client(),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )

    assert result.events == 0
    alerts_md = tmp_path / TODAY.isoformat() / "alerts.md"
    assert alerts_md.exists()
    assert result.alerts_path == alerts_md
    # Present, with no event rows.
    body = alerts_md.read_text()
    assert "No events detected today." in body
    assert "AAA" not in body


def test_history_and_concentration_flags(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    run_portfolio(
        conn,
        _client(),
        reports_dir=tmp_path,
        today=date(2026, 5, 31),
        analyze_fn=_no_analyze,
    )
    result = run_portfolio(
        conn,
        _client(),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
        history=True,
        concentration=True,
    )

    body = result.portfolio_path.read_text()
    assert "## P&L history" in body or "## History" in body
    # Concentration breakdown section present with both days when --history.
    assert "## Concentration" in body
