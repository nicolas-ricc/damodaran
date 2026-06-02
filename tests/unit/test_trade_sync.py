"""Unit tests for the incremental, de-duped trade-execution sync (M5, #27).

These drive ``sync_trades`` against a *mocked* ``IbkrClient`` — no live TWS
gateway or socket is opened, so they are safe for CI. The mock records the
``since`` watermark it was called with so we can assert the incremental
behaviour, and returns canned fills.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import duckdb
import pytest

from bot.ingest.ibkr import TradeExecution
from bot.portfolio.trades import TradeSyncSummary, sync_trades
from bot.storage.db import apply_schema


class FakeTradeClient:
    """Stand-in for ``IbkrClient`` returning canned executions per account.

    ``_per_account`` maps an account id to its fills. ``trades`` records the
    ``since`` watermark it was passed for each account so tests can assert the
    incremental fetch. It does *not* itself filter by ``since`` — the real
    client does that, and the sync layer de-dupes regardless — so tests can
    feed an overlapping window deliberately.
    """

    def __init__(
        self,
        *,
        accounts: list[str],
        per_account: dict[str, list[TradeExecution]],
    ) -> None:
        self._accounts = accounts
        self._per_account = per_account
        self.connected = False
        self.disconnected = False
        self.since_calls: dict[str, datetime | None] = {}

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def accounts(self) -> list[str]:
        return list(self._accounts)

    def trades(
        self, account_id: str, since: datetime | None = None
    ) -> list[TradeExecution]:
        self.since_calls[account_id] = since
        return list(self._per_account.get(account_id, []))


def _fill(
    account: str,
    exec_id: str,
    symbol: str,
    when: datetime,
    *,
    side: str = "BOT",
    qty: float = 10.0,
    price: float = 100.0,
) -> TradeExecution:
    return TradeExecution(
        account=account,
        exec_id=exec_id,
        con_id=abs(hash(symbol)) & 0xFFFF,
        symbol=symbol,
        sec_type="STK",
        currency="USD",
        side=side,
        quantity=qty,
        price=price,
        executed_at=when,
        perm_id=abs(hash(exec_id)) & 0xFFFF,
    )


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def test_schema_creates_trade_and_corp_action_tables(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert "trades" in tables
    assert "corporate_actions" in tables


def test_first_run_has_no_watermark_and_inserts_all(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    client = FakeTradeClient(
        accounts=["U1"],
        per_account={
            "U1": [
                _fill("U1", "e1", "AAPL", datetime(2026, 5, 1, 10, 0, tzinfo=UTC)),
                _fill("U1", "e2", "MSFT", datetime(2026, 5, 2, 11, 0, tzinfo=UTC), side="SLD"),
            ]
        },
    )
    summary = sync_trades(conn, client)

    assert isinstance(summary, TradeSyncSummary)
    assert summary.inserted == 2
    assert summary.accounts == 1
    # No prior rows -> first run passes since=None.
    assert client.since_calls["U1"] is None
    assert client.connected is True
    assert client.disconnected is True

    rows = conn.execute(
        "SELECT exec_id, ticker, side, qty, price, account, currency FROM trades "
        "ORDER BY executed_at"
    ).fetchall()
    assert rows == [
        ("e1", "AAPL", "BOT", 10.0, 100.0, "U1", "USD"),
        ("e2", "MSFT", "SLD", 10.0, 100.0, "U1", "USD"),
    ]


def test_incremental_run_uses_max_executed_at_as_watermark(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    first = FakeTradeClient(
        accounts=["U1"],
        per_account={
            "U1": [
                _fill("U1", "e1", "AAPL", datetime(2026, 5, 1, 10, 0, tzinfo=UTC)),
                _fill("U1", "e2", "MSFT", datetime(2026, 5, 3, 9, 30, tzinfo=UTC)),
            ]
        },
    )
    sync_trades(conn, first)

    second = FakeTradeClient(
        accounts=["U1"],
        per_account={
            "U1": [_fill("U1", "e3", "GOOG", datetime(2026, 5, 5, 12, 0, tzinfo=UTC))]
        },
    )
    summary = sync_trades(conn, second)

    assert summary.inserted == 1
    # Watermark is the latest stored fill time for the account.
    assert second.since_calls["U1"] == datetime(2026, 5, 3, 9, 30, tzinfo=UTC)

    count = conn.execute("SELECT count(*) FROM trades").fetchone()
    assert count is not None
    assert count[0] == 3


def test_overlapping_window_does_not_double_insert(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    client = FakeTradeClient(
        accounts=["U1"],
        per_account={
            "U1": [
                _fill("U1", "e1", "AAPL", datetime(2026, 5, 1, 10, 0, tzinfo=UTC)),
                _fill("U1", "e2", "MSFT", datetime(2026, 5, 2, 11, 0, tzinfo=UTC)),
            ]
        },
    )
    sync_trades(conn, client)

    # Same client re-run: the look-back window re-returns e1 + e2 plus a new e3.
    client._per_account["U1"].append(
        _fill("U1", "e3", "GOOG", datetime(2026, 5, 4, 9, 0, tzinfo=UTC))
    )
    summary = sync_trades(conn, client)

    # Only the genuinely-new execution is inserted; e1/e2 are de-duped on exec_id.
    assert summary.inserted == 1

    rows = conn.execute("SELECT exec_id FROM trades ORDER BY exec_id").fetchall()
    assert rows == [("e1",), ("e2",), ("e3",)]


def test_watermark_is_per_account(conn: duckdb.DuckDBPyConnection) -> None:
    client = FakeTradeClient(
        accounts=["A1", "A2"],
        per_account={
            "A1": [_fill("A1", "a1", "AAPL", datetime(2026, 5, 1, 10, 0, tzinfo=UTC))],
            "A2": [_fill("A2", "b1", "MSFT", datetime(2026, 5, 9, 10, 0, tzinfo=UTC))],
        },
    )
    sync_trades(conn, client)

    again = FakeTradeClient(
        accounts=["A1", "A2"],
        per_account={"A1": [], "A2": []},
    )
    sync_trades(conn, again)

    assert again.since_calls["A1"] == datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    assert again.since_calls["A2"] == datetime(2026, 5, 9, 10, 0, tzinfo=UTC)


def test_no_fills_is_handled_gracefully(conn: duckdb.DuckDBPyConnection) -> None:
    client = FakeTradeClient(accounts=["U1"], per_account={"U1": []})
    summary = sync_trades(conn, client)
    assert summary.inserted == 0
    count = conn.execute("SELECT count(*) FROM trades").fetchone()
    assert count is not None
    assert count[0] == 0


def test_corporate_actions_table_left_empty(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Corp actions are deferred (needs IBKR Flex): sync must not touch them."""
    client = FakeTradeClient(
        accounts=["U1"],
        per_account={
            "U1": [_fill("U1", "e1", "AAPL", datetime(2026, 5, 1, 10, 0, tzinfo=UTC))]
        },
    )
    sync_trades(conn, client)
    count: Any = conn.execute("SELECT count(*) FROM corporate_actions").fetchone()
    assert count is not None
    assert count[0] == 0
