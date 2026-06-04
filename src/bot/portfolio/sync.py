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

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Protocol

from bot.utils.fx import get_fx_rate
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.ingest.ibkr import CashBalance, PortfolioPosition

log = get_logger(__name__)

#: A currency -> USD-rate lookup at a fixed as-of date. Keeping valuation behind
#: this seam lets :func:`value_positions` stay pure (no ``conn``, no I/O).
type FxLookup = Callable[[str], float | None]


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
class _PriceQuote:
    """The latest known close for a ticker, in its listing currency."""

    close: float
    currency: str | None


@dataclass(frozen=True)
class ValuedPosition:
    """A position paired with its computed market value.

    ``market_value is None`` is the *unpriced* sentinel: we had no usable price
    (no row, a non-positive close, or a missing FX rate), so the snapshot stores
    NULL rather than silently falling back to cost basis at the position level.
    """

    position: PortfolioPosition
    market_value: float | None


@dataclass(frozen=True)
class SnapshotSummary:
    """What a single ``sync_portfolio`` run wrote."""

    snapshot_date: date
    accounts: int
    positions: int
    cash_rows: int
    unpriced: int = 0


def value_positions(
    positions: list[PortfolioPosition],
    prices: Mapping[str, _PriceQuote],
    fx: FxLookup,
) -> list[ValuedPosition]:
    """Value each position at its latest market price (a pure, testable step).

    ``prices`` is keyed by upper-cased ticker. Market value is expressed in the
    *position's* currency (so it lines up with ``avg_cost`` for P&L): if the
    price's listing currency matches (or either side is unknown) the close is
    used directly; otherwise it is cross-converted via USD using ``fx``. Any gap
    — no price, a non-positive close, or a missing/non-positive FX rate on either
    the price or position side — yields ``None``.
    """
    return [
        ValuedPosition(
            position=pos,
            market_value=_market_value(pos, prices.get(pos.symbol.upper()), fx),
        )
        for pos in positions
    ]


def _market_value(
    pos: PortfolioPosition, quote: _PriceQuote | None, fx: FxLookup
) -> float | None:
    if quote is None or quote.close <= 0.0:
        return None
    price_ccy = quote.currency
    pos_ccy = pos.currency
    if (
        price_ccy is None
        or pos_ccy is None
        or price_ccy.upper() == pos_ccy.upper()
    ):
        return pos.quantity * quote.close
    rate_price = fx(price_ccy)
    rate_pos = fx(pos_ccy)
    if rate_price is None or rate_pos is None or rate_price <= 0.0 or rate_pos <= 0.0:
        return None
    close_in_pos = quote.close * rate_price / rate_pos
    return pos.quantity * close_in_pos


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

    # Load every ticker's latest close once (one windowed scan, no per-position
    # N+1) and a single FX lookup, then value positions in-process.
    prices = _load_latest_prices(conn, as_of=snap)
    fx = _fx_lookup(conn, snap)

    client.connect()
    try:
        accounts = client.accounts()
        log.info("portfolio_sync_start", snapshot_date=snap.isoformat(), accounts=len(accounts))

        position_count = 0
        cash_count = 0
        unpriced_count = 0
        for account in accounts:
            positions = client.positions(account)
            cash = client.cash_balances(account)
            valued = value_positions(positions, prices, fx)
            _replace_account_day(conn, snap, account)
            _insert_positions(conn, snap, valued)
            _insert_cash(conn, snap, cash)
            position_count += len(positions)
            cash_count += len(cash)
            for vp in valued:
                if vp.market_value is None:
                    unpriced_count += 1
                    log.warning(
                        "portfolio_position_unpriced",
                        ticker=vp.position.symbol,
                        account=account,
                        snapshot_date=snap.isoformat(),
                    )
    finally:
        client.disconnect()

    log.info(
        "portfolio_sync_done",
        snapshot_date=snap.isoformat(),
        accounts=len(accounts),
        positions=position_count,
        cash_rows=cash_count,
        unpriced=unpriced_count,
    )
    return SnapshotSummary(
        snapshot_date=snap,
        accounts=len(accounts),
        positions=position_count,
        cash_rows=cash_count,
        unpriced=unpriced_count,
    )


def _load_latest_prices(
    conn: duckdb.DuckDBPyConnection, *, as_of: date
) -> dict[str, _PriceQuote]:
    """Latest non-null close (and its currency) per ticker on or before ``as_of``.

    One windowed scan resolves the most recent priced row for every ticker —
    never looking forward past the snapshot date — keyed by upper-cased ticker.
    """
    rows = conn.execute(
        "SELECT ticker, close, currency FROM ("
        "  SELECT ticker, close, currency, "
        "         ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn "
        "  FROM prices_daily WHERE close IS NOT NULL AND date <= ?"
        ") WHERE rn = 1",
        [as_of],
    ).fetchall()
    out: dict[str, _PriceQuote] = {}
    for ticker, close, currency in rows:
        if close is None:
            continue
        out[str(ticker).upper()] = _PriceQuote(
            close=float(close),
            currency=str(currency) if currency is not None else None,
        )
    return out


def _fx_lookup(conn: duckdb.DuckDBPyConnection, as_of: date) -> FxLookup:
    """A currency -> USD-rate lookup bound to ``conn`` at ``as_of`` (nearest-prior)."""
    return lambda ccy: get_fx_rate(conn, ccy, as_of)


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
    valued: list[ValuedPosition],
) -> None:
    for vp in valued:
        pos = vp.position
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
                vp.market_value,
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
