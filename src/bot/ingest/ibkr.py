"""Read-only Interactive Brokers TWS API client (M5).

A thin, **read-only** wrapper over the IBKR *TWS API* (socket), using the
maintained `ib_async <https://github.com/ib-api-reloaded/ib_async>`_ library.
With Trader Workstation (TWS) or IB Gateway running and logged in, the client
connects over the local socket and returns plain data: managed accounts,
positions, per-currency cash balances and trade executions.

Design mirrors the other ingest adapters: connections/config in, plain data out,
no global state. The wire protocol is bundled by ``ib_async`` — we never import
or depend on IBKR's ``ibapi`` directly.

**Read-only discipline.** This module deliberately exposes *no* order-placement,
modification or cancellation surface. The maintainer is also advised to enable
TWS → API → Settings → "Read-Only API" as a belt-and-braces safeguard, and the
connection itself is opened with ``readonly=True``.

Authentication is handled entirely by the TWS desktop login; there is no OAuth,
no REST gateway and no Docker container. Persistence of the returned data into
the DB is a separate concern (#26) and intentionally lives elsewhere.

The data-mapping logic here is unit-tested against mocked ``ib_async`` responses;
the live ``accounts()`` smoke test against a logged-in TWS is a manual step
documented in the README. CI never opens a real socket.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol

from bot.utils.logging import get_logger

if TYPE_CHECKING:
    from bot.config import Settings

log = get_logger(__name__)

# Default TWS API socket. 7496 = live TWS; 7497 = paper TWS; 4001/4002 = IB
# Gateway live/paper. Overridable via Settings / constructor — never hard-coded
# into call sites.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7496
DEFAULT_CLIENT_ID = 1

# IBKR's ExecutionFilter expects ``yyyymmdd-HH:MM:SS`` (or ``yyyymmdd HH:MM:SS``)
# in TWS local time; it is a coarse server-side pre-filter only.
_EXEC_FILTER_TIME_FMT = "%Y%m%d-%H:%M:%S"

# Account-value tags that represent a per-currency cash balance. ``CashBalance``
# is reported once per held currency plus a summary ``BASE`` row we drop; the
# aggregate ``TotalCashBalance`` rows are excluded so callers see one row per
# real currency.
_CASH_TAG = "CashBalance"
_BASE_CURRENCY_SENTINEL = "BASE"


@dataclass(frozen=True)
class PortfolioPosition:
    """A single open position in an account."""

    account: str
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    exchange: str
    quantity: float
    avg_cost: float


@dataclass(frozen=True)
class CashBalance:
    """A per-currency cash balance for an account."""

    account: str
    currency: str
    amount: float


@dataclass(frozen=True)
class TradeExecution:
    """A single trade execution (fill) in an account."""

    account: str
    exec_id: str
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    side: str
    quantity: float
    price: float
    executed_at: datetime
    perm_id: int


class _IB(Protocol):
    """The narrow, read-only slice of ``ib_async.IB`` this client relies on.

    Declared as a Protocol so tests can inject a lightweight fake and ``mypy``
    still checks the call sites — without dragging order-placement methods into
    view.
    """

    def isConnected(self) -> bool: ...  # noqa: N802 - matches ib_async surface

    def connect(self, **kwargs: Any) -> Any: ...

    def disconnect(self) -> Any: ...

    def managedAccounts(self) -> list[str]: ...  # noqa: N802

    def positions(self, account: str = ...) -> list[Any]: ...

    def accountValues(self, account: str = ...) -> list[Any]: ...  # noqa: N802

    def reqExecutions(self, execFilter: Any = ...) -> list[Any]: ...  # noqa: N802, N803


class IbkrClient:
    """Read-only client over a locally-running TWS / IB Gateway socket.

    Construct with a configurable ``host`` / ``port`` / ``client_id`` (defaulting
    to live TWS on ``127.0.0.1:7496``), or via :meth:`from_settings`. The
    underlying ``ib_async.IB`` instance can be injected for testing.

    Exposes exactly four read-only methods — :meth:`accounts`,
    :meth:`positions`, :meth:`cash_balances` and :meth:`trades` — each of which
    lazily connects if needed. There is no order-placement surface.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        client_id: int = DEFAULT_CLIENT_ID,
        *,
        ib: _IB | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib: _IB = ib if ib is not None else _new_ib()

    @classmethod
    def from_settings(cls, settings: Settings, *, ib: _IB | None = None) -> IbkrClient:
        """Build a client from the application :class:`~bot.config.Settings`."""
        return cls(
            host=settings.ibkr_host,
            port=settings.ibkr_port,
            client_id=settings.ibkr_client_id,
            ib=ib,
        )

    # -- connection lifecycle ------------------------------------------------

    def connect(self) -> None:
        """Connect to TWS if not already connected (idempotent, read-only)."""
        if self._ib.isConnected():
            return
        log.info(
            "ibkr_connect",
            host=self._host,
            port=self._port,
            client_id=self._client_id,
        )
        self._ib.connect(
            host=self._host,
            port=self._port,
            clientId=self._client_id,
            readonly=True,
        )

    def disconnect(self) -> None:
        """Disconnect from TWS if connected."""
        if self._ib.isConnected():
            self._ib.disconnect()
            log.info("ibkr_disconnect")

    def _ensure_connected(self) -> None:
        if not self._ib.isConnected():
            self.connect()

    def __enter__(self) -> IbkrClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()

    # -- read-only data ------------------------------------------------------

    def accounts(self) -> list[str]:
        """Return the managed account ids visible to this login."""
        self._ensure_connected()
        return list(self._ib.managedAccounts())

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        """Return open positions for *account_id*."""
        self._ensure_connected()
        rows = self._ib.positions(account_id)
        return [_map_position(row) for row in rows]

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        """Return per-currency cash balances for *account_id*.

        Filters the account-value stream to ``CashBalance`` rows, dropping the
        ``BASE`` summary row so the result is one entry per held currency.
        """
        self._ensure_connected()
        values: list[Any] = self._ib.accountValues(account_id)
        balances: list[CashBalance] = []
        for value in values:
            if value.tag != _CASH_TAG:
                continue
            currency = str(value.currency)
            if currency == _BASE_CURRENCY_SENTINEL:
                continue
            balances.append(
                CashBalance(
                    account=str(value.account),
                    currency=currency,
                    amount=float(value.value),
                )
            )
        return balances

    def trades(
        self, account_id: str, since: datetime | None = None
    ) -> list[TradeExecution]:
        """Return trade executions (fills) for *account_id*, optionally since a date.

        ``since`` is pushed into the server-side ``ExecutionFilter`` as a coarse
        pre-filter and also applied client-side so the boundary is exact. Note
        TWS only retains executions for a limited recent window; older history
        needs Flex (out of scope here).
        """
        self._ensure_connected()
        exec_filter = _build_exec_filter(account_id, since)
        fills = self._ib.reqExecutions(exec_filter)
        trades: list[TradeExecution] = []
        for fill in fills:
            trade = _map_fill(fill)
            if since is not None and trade.executed_at < since:
                continue
            trades.append(trade)
        return trades


def _new_ib() -> _IB:
    """Construct a real ``ib_async.IB`` instance (deferred import).

    Cast through ``Any`` because ``ib_async.IB`` exposes a far larger (incl.
    order-placement) surface than the read-only :class:`_IB` Protocol; we only
    ever call the narrow read-only slice declared above.
    """
    from ib_async import IB

    ib: _IB = IB()  # type: ignore[assignment]  # IB satisfies the read-only slice we use
    return ib


def _map_position(row: Any) -> PortfolioPosition:
    contract = row.contract
    primary = str(getattr(contract, "primaryExchange", "") or "")
    exchange = primary or str(getattr(contract, "exchange", "") or "")
    return PortfolioPosition(
        account=str(row.account),
        con_id=int(contract.conId or 0),
        symbol=str(contract.symbol),
        sec_type=str(contract.secType),
        currency=str(contract.currency),
        exchange=exchange,
        quantity=float(row.position),
        avg_cost=float(row.avgCost),
    )


def _map_fill(fill: Any) -> TradeExecution:
    contract = fill.contract
    execution = fill.execution
    return TradeExecution(
        account=str(execution.acctNumber),
        exec_id=str(execution.execId),
        con_id=int(contract.conId or 0),
        symbol=str(contract.symbol),
        sec_type=str(contract.secType),
        currency=str(contract.currency),
        side=str(execution.side),
        quantity=float(execution.shares),
        price=float(execution.price),
        executed_at=_coerce_dt(execution.time),
        perm_id=int(execution.permId or 0),
    )


def _coerce_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"expected datetime execution time, got {type(value).__name__}")


def _build_exec_filter(account_id: str, since: datetime | None) -> object:
    """Build an ``ib_async.ExecutionFilter`` scoped to the account / since date."""
    from ib_async import ExecutionFilter

    time_str = since.strftime(_EXEC_FILTER_TIME_FMT) if since is not None else ""
    return ExecutionFilter(acctCode=account_id, time=time_str)
