"""Unit tests for the daily, idempotent portfolio snapshot (M5, #26).

These drive ``sync_portfolio`` against a *mocked* ``IbkrClient`` — no live TWS
gateway or socket is opened, so they are safe for CI.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import duckdb
import pytest

from bot.ingest.ibkr import CashBalance, PortfolioPosition
from bot.portfolio.sync import SnapshotSummary, sync_portfolio
from bot.storage.db import apply_schema


class FakeIbkrClient:
    """Stand-in for ``IbkrClient`` returning canned accounts / positions / cash."""

    def __init__(
        self,
        *,
        accounts: list[str],
        positions: dict[str, list[PortfolioPosition]],
        cash: dict[str, list[CashBalance]],
    ) -> None:
        self._accounts = accounts
        self._positions = positions
        self._cash = cash
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def accounts(self) -> list[str]:
        return list(self._accounts)

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        return list(self._positions.get(account_id, []))

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        return list(self._cash.get(account_id, []))


def _position(account: str, symbol: str, qty: float, avg_cost: float) -> PortfolioPosition:
    return PortfolioPosition(
        account=account,
        con_id=hash(symbol) & 0xFFFF,
        symbol=symbol,
        sec_type="STK",
        currency="USD",
        exchange="NASDAQ",
        quantity=qty,
        avg_cost=avg_cost,
    )


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _client(account: str = "DU111") -> FakeIbkrClient:
    return FakeIbkrClient(
        accounts=[account],
        positions={
            account: [
                _position(account, "AAPL", 10.0, 150.0),
                _position(account, "MSFT", 5.0, 300.0),
            ]
        },
        cash={account: [CashBalance(account=account, currency="USD", amount=1234.5)]},
    )


def test_schema_creates_snapshot_tables(conn: duckdb.DuckDBPyConnection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert "portfolio_snapshots" in tables
    assert "cash_balances" in tables


def test_sync_writes_positions_and_cash(conn: duckdb.DuckDBPyConnection) -> None:
    client = _client()
    summary = sync_portfolio(conn, client, snapshot_date=date(2026, 6, 1))

    assert isinstance(summary, SnapshotSummary)
    assert summary.positions == 2
    assert summary.cash_rows == 1
    assert summary.accounts == 1

    positions = conn.execute(
        "SELECT ticker, qty, avg_cost, market_value, currency, account, snapshot_date "
        "FROM portfolio_snapshots ORDER BY ticker"
    ).fetchall()
    assert len(positions) == 2
    aapl = positions[0]
    assert aapl[0] == "AAPL"
    assert aapl[1] == 10.0
    assert aapl[2] == 150.0
    assert aapl[3] == pytest.approx(1500.0)  # qty * avg_cost
    assert aapl[4] == "USD"
    assert aapl[5] == "DU111"
    assert aapl[6] == date(2026, 6, 1)

    cash = conn.execute(
        "SELECT currency, amount, account, snapshot_date FROM cash_balances"
    ).fetchall()
    assert cash == [("USD", pytest.approx(1234.5), "DU111", date(2026, 6, 1))]


def test_sync_connects_and_disconnects(conn: duckdb.DuckDBPyConnection) -> None:
    client = _client()
    sync_portfolio(conn, client, snapshot_date=date(2026, 6, 1))
    assert client.connected is True
    assert client.disconnected is True


def test_same_day_rerun_replaces_rows(conn: duckdb.DuckDBPyConnection) -> None:
    day = date(2026, 6, 1)
    sync_portfolio(conn, _client(), snapshot_date=day)

    # Second run same day with fewer positions: must replace, not append.
    account = "DU111"
    smaller = FakeIbkrClient(
        accounts=[account],
        positions={account: [_position(account, "AAPL", 20.0, 160.0)]},
        cash={account: [CashBalance(account=account, currency="EUR", amount=99.0)]},
    )
    sync_portfolio(conn, smaller, snapshot_date=day)

    positions = conn.execute(
        "SELECT ticker, qty FROM portfolio_snapshots WHERE snapshot_date = ?",
        [day],
    ).fetchall()
    assert positions == [("AAPL", 20.0)]

    cash = conn.execute(
        "SELECT currency, amount FROM cash_balances WHERE snapshot_date = ?",
        [day],
    ).fetchall()
    assert cash == [("EUR", pytest.approx(99.0))]


def test_different_day_appends(conn: duckdb.DuckDBPyConnection) -> None:
    sync_portfolio(conn, _client(), snapshot_date=date(2026, 6, 1))
    sync_portfolio(conn, _client(), snapshot_date=date(2026, 6, 2))

    days = conn.execute(
        "SELECT DISTINCT snapshot_date FROM portfolio_snapshots ORDER BY snapshot_date"
    ).fetchall()
    assert days == [(date(2026, 6, 1),), (date(2026, 6, 2),)]

    total = conn.execute("SELECT count(*) FROM portfolio_snapshots").fetchone()
    assert total is not None
    assert total[0] == 4


def test_rerun_only_replaces_synced_account(conn: duckdb.DuckDBPyConnection) -> None:
    day = date(2026, 6, 1)
    two = FakeIbkrClient(
        accounts=["A1", "A2"],
        positions={
            "A1": [_position("A1", "AAPL", 1.0, 10.0)],
            "A2": [_position("A2", "MSFT", 2.0, 20.0)],
        },
        cash={},
    )
    sync_portfolio(conn, two, snapshot_date=day)

    only_a1 = FakeIbkrClient(
        accounts=["A1"],
        positions={"A1": [_position("A1", "AAPL", 9.0, 10.0)]},
        cash={},
    )
    sync_portfolio(conn, only_a1, snapshot_date=day)

    rows = conn.execute(
        "SELECT account, ticker, qty FROM portfolio_snapshots "
        "WHERE snapshot_date = ? ORDER BY account, ticker",
        [day],
    ).fetchall()
    assert rows == [("A1", "AAPL", 9.0), ("A2", "MSFT", 2.0)]


def test_defaults_snapshot_date_to_today(
    conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed = date(2026, 3, 14)

    class _FixedDate(date):
        @classmethod
        def today(cls) -> date:  # type: ignore[override]
            return fixed

    monkeypatch.setattr("bot.portfolio.sync.date", _FixedDate)
    summary = sync_portfolio(conn, _client())
    assert summary.snapshot_date == fixed
    stored: Any = conn.execute(
        "SELECT DISTINCT snapshot_date FROM portfolio_snapshots"
    ).fetchone()
    assert stored is not None
    assert stored[0] == fixed
