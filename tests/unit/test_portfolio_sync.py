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
from bot.portfolio import sync as sync_mod
from bot.portfolio.sync import (
    SnapshotSummary,
    _PriceQuote,
    sync_portfolio,
    value_positions,
)
from bot.storage.db import apply_schema
from bot.utils.fx import upsert_fx_rates


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


def _position(
    account: str,
    symbol: str,
    qty: float,
    avg_cost: float,
    currency: str = "USD",
) -> PortfolioPosition:
    return PortfolioPosition(
        account=account,
        con_id=hash(symbol) & 0xFFFF,
        symbol=symbol,
        sec_type="STK",
        currency=currency,
        exchange="NASDAQ",
        quantity=qty,
        avg_cost=avg_cost,
    )


def _seed_price(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    close: float | None,
    *,
    on: date = date(2026, 6, 1),
    currency: str = "USD",
) -> None:
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency) VALUES (?, ?, ?, ?)",
        [ticker.upper(), on, close, currency],
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
    day = date(2026, 6, 1)
    _seed_price(conn, "AAPL", 180.0, on=day)
    _seed_price(conn, "MSFT", 400.0, on=day)
    client = _client()
    summary = sync_portfolio(conn, client, snapshot_date=day)

    assert isinstance(summary, SnapshotSummary)
    assert summary.positions == 2
    assert summary.cash_rows == 1
    assert summary.accounts == 1
    assert summary.unpriced == 0

    positions = conn.execute(
        "SELECT ticker, qty, avg_cost, market_value, currency, account, snapshot_date "
        "FROM portfolio_snapshots ORDER BY ticker"
    ).fetchall()
    assert len(positions) == 2
    aapl = positions[0]
    assert aapl[0] == "AAPL"
    assert aapl[1] == 10.0
    assert aapl[2] == 150.0
    assert aapl[3] == pytest.approx(1800.0)  # qty * latest close (10 * 180)
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


# --------------------------------------------------------------------------- #
# Market-value valuation (#55)                                                  #
# --------------------------------------------------------------------------- #


def _one(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> Any:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return row[0]


def test_market_value_uses_latest_price(conn: duckdb.DuckDBPyConnection) -> None:
    day = date(2026, 6, 1)
    _seed_price(conn, "AAPL", 180.0, on=day)
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "AAPL", 10.0, 150.0)]},
        cash={},
    )
    summary = sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn,
        "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'AAPL'",
        [],
    )
    assert mv == pytest.approx(1800.0)  # 10 * 180, not the 1500 cost basis
    # P&L is therefore non-zero: 1800 - (10 * 150) = 300.
    assert mv - 10.0 * 150.0 == pytest.approx(300.0)
    assert summary.unpriced == 0


def test_unpriced_ticker_stored_null_and_counted(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    day = date(2026, 6, 1)
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "AAPL", 10.0, 150.0)]},
        cash={},
    )
    summary = sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn,
        "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'AAPL'",
        [],
    )
    assert mv is None
    assert summary.unpriced == 1


def test_multi_currency_same_currency_uses_close_directly(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    day = date(2026, 6, 1)
    _seed_price(conn, "SAP", 200.0, on=day, currency="EUR")
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "SAP", 4.0, 180.0, currency="EUR")]},
        cash={},
    )
    sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn, "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'SAP'", []
    )
    assert mv == pytest.approx(800.0)  # 4 * 200, no FX applied


def test_multi_currency_normalization(conn: duckdb.DuckDBPyConnection) -> None:
    day = date(2026, 6, 1)
    # Price listed in USD, but the position is held/cost-based in EUR.
    _seed_price(conn, "ACME", 110.0, on=day, currency="USD")
    upsert_fx_rates(
        conn, currency="EUR", rows=[{"date": day, "rate_to_usd": 1.10}]
    )
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "ACME", 2.0, 90.0, currency="EUR")]},
        cash={},
    )
    sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn, "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'ACME'", []
    )
    # close_usd / rate_eur -> EUR, times qty: 2 * (110 / 1.10) = 200 EUR.
    assert mv == pytest.approx(200.0)


def test_unpriced_when_fx_missing(conn: duckdb.DuckDBPyConnection) -> None:
    day = date(2026, 6, 1)
    _seed_price(conn, "VOD", 100.0, on=day, currency="USD")  # price USD
    # Position in GBP, but no GBP FX rate seeded -> cannot normalize.
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "VOD", 5.0, 90.0, currency="GBP")]},
        cash={},
    )
    summary = sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn, "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'VOD'", []
    )
    assert mv is None
    assert summary.unpriced == 1


def test_latest_price_respects_snapshot_date(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    d1 = date(2026, 6, 1)
    d2 = date(2026, 6, 2)
    _seed_price(conn, "AAPL", 100.0, on=d1)
    _seed_price(conn, "AAPL", 120.0, on=d2)  # future relative to the d1 sync
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "AAPL", 10.0, 150.0)]},
        cash={},
    )
    sync_portfolio(conn, client, snapshot_date=d1)

    mv = _one(
        conn,
        "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'AAPL' "
        "AND snapshot_date = ?",
        [d1],
    )
    assert mv == pytest.approx(1000.0)  # uses d1's 100, never d2's 120


def test_nonpositive_close_treated_as_unpriced(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    day = date(2026, 6, 1)
    _seed_price(conn, "AAPL", 0.0, on=day)
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "AAPL", 10.0, 150.0)]},
        cash={},
    )
    summary = sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn, "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'AAPL'", []
    )
    assert mv is None
    assert summary.unpriced == 1


def test_short_position_negative_market_value(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    day = date(2026, 6, 1)
    _seed_price(conn, "AAPL", 180.0, on=day)
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={"DU1": [_position("DU1", "AAPL", -10.0, 150.0)]},
        cash={},
    )
    sync_portfolio(conn, client, snapshot_date=day)

    mv = _one(
        conn, "SELECT market_value FROM portfolio_snapshots WHERE ticker = 'AAPL'", []
    )
    assert mv == pytest.approx(-1800.0)  # short: qty negative
    # P&L for a short: market_value - cost_basis = -1800 - (-1500) = -300.
    assert mv - (-10.0 * 150.0) == pytest.approx(-300.0)


def test_value_positions_is_pure() -> None:
    rates = {"USD": 1.0, "EUR": 1.10}
    positions = [
        _position("A", "AAPL", 10.0, 150.0),  # priced, USD
        _position("A", "NOPRICE", 5.0, 10.0),  # no quote
        _position("A", "ACME", 2.0, 90.0, currency="EUR"),  # cross-currency
    ]
    prices = {
        "AAPL": _PriceQuote(close=180.0, currency="USD"),
        "ACME": _PriceQuote(close=110.0, currency="USD"),
    }
    valued = value_positions(positions, prices, lambda c: rates.get(c.upper()))

    by_ticker = {v.position.symbol: v.market_value for v in valued}
    assert by_ticker["AAPL"] == pytest.approx(1800.0)
    assert by_ticker["NOPRICE"] is None
    assert by_ticker["ACME"] == pytest.approx(200.0)  # 2 * 110 / 1.10


def test_value_positions_zero_price_side_fx_is_unpriced() -> None:
    # A bogus non-positive rate on the price side must yield unpriced (None),
    # not a position valued at 0 (mirrors the position-side rate guard).
    rates = {"USD": 0.0, "EUR": 1.10}
    positions = [_position("A", "ACME", 2.0, 90.0, currency="EUR")]
    prices = {"ACME": _PriceQuote(close=110.0, currency="USD")}
    valued = value_positions(positions, prices, lambda c: rates.get(c.upper()))
    assert valued[0].market_value is None


def test_prices_loaded_once_regardless_of_position_count(
    conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    day = date(2026, 6, 1)
    for sym in ("AAPL", "MSFT", "NVDA"):
        _seed_price(conn, sym, 100.0, on=day)

    calls = {"n": 0}
    real = sync_mod._load_latest_prices

    def spy(*args: Any, **kwargs: Any) -> dict[str, _PriceQuote]:
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(sync_mod, "_load_latest_prices", spy)
    client = FakeIbkrClient(
        accounts=["DU1"],
        positions={
            "DU1": [
                _position("DU1", "AAPL", 1.0, 10.0),
                _position("DU1", "MSFT", 2.0, 20.0),
                _position("DU1", "NVDA", 3.0, 30.0),
            ]
        },
        cash={},
    )
    sync_portfolio(conn, client, snapshot_date=day)
    # One windowed scan loads every ticker — no per-position N+1.
    assert calls["n"] == 1
