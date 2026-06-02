"""Daily, idempotent portfolio snapshot from the read-only IBKR client (M5, #26).

``sync_portfolio`` orchestrates fetch -> write: it asks an :class:`IbkrClient`
for the managed accounts, their open positions and per-currency cash, then
persists an append-only daily snapshot into ``portfolio_snapshots`` and
``cash_balances``.

Idempotency is keyed on ``(snapshot_date, account)``: a re-run on the same
calendar day deletes that day's rows for each account it just fetched and
re-inserts them, so a same-day refresh never duplicates while a new day appends
a fresh snapshot. Only accounts present in *this* run are touched — a snapshot
from another account on the same day is left intact.

Follows the ingest convention: an open connection and a client go in, plain
data comes out; no global state. Diffing snapshots, trades and CLI wiring are
deliberately out of scope (#27, #28, #29).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Protocol

from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.ingest.ibkr import CashBalance, PortfolioPosition

log = get_logger(__name__)


class PortfolioSource(Protocol):
    """The read-only slice of :class:`~bot.ingest.ibkr.IbkrClient` we depend on.

    Declared as a Protocol so tests can inject a lightweight fake while ``mypy``
    still checks the call sites.
    """

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def accounts(self) -> list[str]: ...

    def positions(self, account_id: str) -> list[PortfolioPosition]: ...

    def cash_balances(self, account_id: str) -> list[CashBalance]: ...


@dataclass(frozen=True)
class SnapshotSummary:
    """What a single ``sync_portfolio`` run wrote."""

    snapshot_date: date
    accounts: int
    positions: int
    cash_rows: int


def sync_portfolio(
    conn: duckdb.DuckDBPyConnection,
    client: PortfolioSource,
    *,
    snapshot_date: date | None = None,
) -> SnapshotSummary:
    """Fetch positions + cash for every managed account and write a daily snapshot.

    Args:
        conn: Open DuckDB connection with the schema applied.
        client: A read-only IBKR client (or any :class:`PortfolioSource`).
        snapshot_date: Calendar day to key the snapshot on; defaults to today.

    Returns:
        A :class:`SnapshotSummary` of the rows written.

    The write is idempotent per ``(snapshot_date, account)``: re-running on the
    same day replaces that day's rows for the synced accounts rather than
    appending duplicates.
    """
    snap = snapshot_date if snapshot_date is not None else date.today()

    client.connect()
    try:
        accounts = client.accounts()
        log.info("portfolio_sync_start", snapshot_date=snap.isoformat(), accounts=len(accounts))

        position_count = 0
        cash_count = 0
        for account in accounts:
            positions = client.positions(account)
            cash = client.cash_balances(account)
            _replace_account_day(conn, snap, account)
            _insert_positions(conn, snap, positions)
            _insert_cash(conn, snap, cash)
            position_count += len(positions)
            cash_count += len(cash)
    finally:
        client.disconnect()

    log.info(
        "portfolio_sync_done",
        snapshot_date=snap.isoformat(),
        accounts=len(accounts),
        positions=position_count,
        cash_rows=cash_count,
    )
    return SnapshotSummary(
        snapshot_date=snap,
        accounts=len(accounts),
        positions=position_count,
        cash_rows=cash_count,
    )


def _replace_account_day(
    conn: duckdb.DuckDBPyConnection, snap: date, account: str
) -> None:
    """Clear any existing snapshot rows for ``(snap, account)`` before re-inserting."""
    conn.execute(
        "DELETE FROM portfolio_snapshots WHERE snapshot_date = ? AND account = ?",
        [snap, account],
    )
    conn.execute(
        "DELETE FROM cash_balances WHERE snapshot_date = ? AND account = ?",
        [snap, account],
    )


def _insert_positions(
    conn: duckdb.DuckDBPyConnection,
    snap: date,
    positions: list[PortfolioPosition],
) -> None:
    for pos in positions:
        conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, account, ticker, con_id, sec_type, exchange, "
            "qty, avg_cost, market_value, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                snap,
                pos.account,
                pos.symbol,
                pos.con_id,
                pos.sec_type,
                pos.exchange,
                pos.quantity,
                pos.avg_cost,
                pos.quantity * pos.avg_cost,
                pos.currency,
            ],
        )


def _insert_cash(
    conn: duckdb.DuckDBPyConnection,
    snap: date,
    cash: list[CashBalance],
) -> None:
    for bal in cash:
        conn.execute(
            "INSERT INTO cash_balances "
            "(snapshot_date, account, currency, amount) VALUES (?, ?, ?, ?)",
            [snap, bal.account, bal.currency, bal.amount],
        )
