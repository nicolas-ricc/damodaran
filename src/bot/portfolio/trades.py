"""Incremental, de-duped trade-execution sync from the IBKR socket (M5, #27).

``sync_trades`` orchestrates fetch -> write: for every managed account it
derives a watermark from ``max(executed_at)`` already stored in ``trades`` and
asks an :class:`IbkrClient` for only the fills newer than that watermark, then
appends them. Inserts are de-duped on the broker ``exec_id`` so an overlapping
look-back window (the live TWS socket re-returns the current session's fills on
every call) can never double-insert.

Corporate actions are **deliberately out of scope** here. The live TWS socket
does not expose dividends/splits/mergers in any reliable form — they come from
IBKR's Flex Web Service, a separate HTTP integration with its own auth (see the
#27 addendum). The ``corporate_actions`` table is created by the schema so the
shape is ready, but nothing in this module populates it; a follow-up issue will
add a Flex importer.

Follows the ingest convention: an open connection and a client go in, plain
data comes out; no global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.ingest.ibkr import TradeExecution

log = get_logger(__name__)


class TradeSource(Protocol):
    """The read-only slice of :class:`~bot.ingest.ibkr.IbkrClient` we depend on.

    Declared as a Protocol so tests can inject a lightweight fake while ``mypy``
    still checks the call sites.
    """

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def accounts(self) -> list[str]: ...

    def trades(
        self, account_id: str, since: datetime | None = None
    ) -> list[TradeExecution]: ...


@dataclass(frozen=True)
class TradeSyncSummary:
    """What a single ``sync_trades`` run wrote."""

    accounts: int
    inserted: int


def sync_trades(
    conn: duckdb.DuckDBPyConnection,
    client: TradeSource,
) -> TradeSyncSummary:
    """Incrementally fetch and append trade executions for every account.

    Args:
        conn: Open DuckDB connection with the schema applied.
        client: A read-only IBKR client (or any :class:`TradeSource`).

    Returns:
        A :class:`TradeSyncSummary` of the rows written.

    For each managed account the watermark is ``max(executed_at)`` already
    stored in ``trades`` (``None`` on the first run). Fetched fills are inserted
    de-duped on the broker ``exec_id``, so re-running with an overlapping
    look-back window never duplicates rows.
    """
    client.connect()
    try:
        accounts = client.accounts()
        log.info("trade_sync_start", accounts=len(accounts))

        inserted = 0
        for account in accounts:
            since = _watermark(conn, account)
            fills = client.trades(account, since=since)
            inserted += _insert_dedup(conn, fills)
    finally:
        client.disconnect()

    log.info("trade_sync_done", accounts=len(accounts), inserted=inserted)
    return TradeSyncSummary(accounts=len(accounts), inserted=inserted)


def _watermark(
    conn: duckdb.DuckDBPyConnection, account: str
) -> datetime | None:
    """Return ``max(executed_at)`` stored for *account* as UTC, or ``None``.

    ``executed_at`` is stored naive-UTC (see schema NOTE); we re-attach UTC so
    the watermark matches the timezone-aware fill timestamps the client filters
    on.
    """
    row = conn.execute(
        "SELECT max(executed_at) FROM trades WHERE account = ?",
        [account],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    value = row[0]
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC)
    raise TypeError(f"expected datetime watermark, got {type(value).__name__}")


def _insert_dedup(
    conn: duckdb.DuckDBPyConnection,
    fills: list[TradeExecution],
) -> int:
    """Insert *fills* de-duped on ``exec_id``; return the number of new rows."""
    inserted = 0
    for fill in fills:
        result = conn.execute(
            "INSERT INTO trades "
            "(exec_id, account, con_id, ticker, sec_type, side, qty, price, "
            "currency, executed_at, perm_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (exec_id) DO NOTHING",
            [
                fill.exec_id,
                fill.account,
                fill.con_id,
                fill.symbol,
                fill.sec_type,
                fill.side,
                fill.quantity,
                fill.price,
                fill.currency,
                _to_naive_utc(fill.executed_at),
                fill.perm_id,
            ],
        )
        inserted += _rowcount(result)
    return inserted


def _to_naive_utc(value: datetime) -> datetime:
    """Normalise a fill timestamp to naive UTC for storage.

    ib_async returns timezone-aware timestamps; we convert to UTC and drop the
    tzinfo so DuckDB stores a plain ``TIMESTAMP`` (no pytz needed at read time).
    Naive inputs are assumed to already be UTC.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _rowcount(result: duckdb.DuckDBPyConnection) -> int:
    """Rows affected by the last INSERT (1 when inserted, 0 when de-duped)."""
    row = result.fetchone()
    if row is None:
        return 0
    count = row[0]
    return int(count) if isinstance(count, int) else 0
