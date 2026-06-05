"""Unit tests for the read-only IBKR TWS API client (M5).

These exercise the data-mapping logic against *mocked* ``ib_async`` responses;
no live TWS or socket is opened, so they are safe for CI. The live ``accounts()``
smoke test against a logged-in TWS is a documented manual step (see README).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bot.ingest.ibkr import (
    CashBalance,
    IbkrClient,
    PortfolioPosition,
    TradeExecution,
)


def _contract(**kwargs: Any) -> SimpleNamespace:
    base = {
        "conId": 0,
        "symbol": "",
        "secType": "",
        "currency": "",
        "exchange": "",
        "primaryExchange": "",
        "localSymbol": "",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class FakeIB:
    """Minimal stand-in for ``ib_async.IB`` recording calls and returning canned data."""

    def __init__(self) -> None:
        self._connected = False
        self.connect_args: dict[str, Any] | None = None
        self.disconnected = False
        self._managed: list[str] = []
        self._positions: list[Any] = []
        self._account_values: list[Any] = []
        self._fills: list[Any] = []
        self.exec_filter: Any = None

    def isConnected(self) -> bool:  # noqa: N802 - matches ib_async surface
        return self._connected

    def connect(self, **kwargs: Any) -> None:
        self.connect_args = kwargs
        self._connected = True

    def disconnect(self) -> None:
        self.disconnected = True
        self._connected = False

    def managedAccounts(self) -> list[str]:  # noqa: N802
        return self._managed

    def positions(self, account: str = "") -> list[Any]:
        return [p for p in self._positions if not account or p.account == account]

    def accountValues(self, account: str = "") -> list[Any]:  # noqa: N802
        return [v for v in self._account_values if not account or v.account == account]

    def reqExecutions(self, execFilter: Any = None) -> list[Any]:  # noqa: N802, N803
        self.exec_filter = execFilter
        return self._fills


@pytest.fixture
def fake_ib() -> FakeIB:
    return FakeIB()


@pytest.fixture
def client(fake_ib: FakeIB) -> IbkrClient:
    return IbkrClient(host="127.0.0.1", port=7496, client_id=1, ib=fake_ib)


def test_no_order_placement_surface(client: IbkrClient) -> None:
    """Read-only discipline: the client must expose no order-placement methods."""
    forbidden = {
        "placeOrder",
        "place_order",
        "cancelOrder",
        "cancel_order",
        "reqGlobalCancel",
        "bracketOrder",
        "oneCancelsAll",
    }
    surface = {name for name in dir(client) if not name.startswith("_")}
    assert forbidden.isdisjoint(surface), surface & forbidden


def test_connect_passes_configurable_params_and_readonly(fake_ib: FakeIB) -> None:
    client = IbkrClient(host="10.0.0.5", port=7497, client_id=7, ib=fake_ib)
    client.connect()
    assert fake_ib.connect_args is not None
    assert fake_ib.connect_args["host"] == "10.0.0.5"
    assert fake_ib.connect_args["port"] == 7497
    assert fake_ib.connect_args["clientId"] == 7
    # Belt-and-braces: always connect read-only.
    assert fake_ib.connect_args["readonly"] is True


def test_defaults_are_live_tws(fake_ib: FakeIB) -> None:
    client = IbkrClient(ib=fake_ib)
    client.connect()
    assert fake_ib.connect_args is not None
    assert fake_ib.connect_args["host"] == "127.0.0.1"
    assert fake_ib.connect_args["port"] == 7496
    assert fake_ib.connect_args["clientId"] == 1


def test_from_settings_uses_config() -> None:
    settings = SimpleNamespace(ibkr_host="192.168.1.2", ibkr_port=4001, ibkr_client_id=3)
    fake = FakeIB()
    client = IbkrClient.from_settings(settings, ib=fake)  # type: ignore[arg-type]
    client.connect()
    assert fake.connect_args == {
        "host": "192.168.1.2",
        "port": 4001,
        "clientId": 3,
        "readonly": True,
    }


def test_accounts_returns_managed_accounts(client: IbkrClient, fake_ib: FakeIB) -> None:
    fake_ib._managed = ["U1234567", "U7654321"]
    assert client.accounts() == ["U1234567", "U7654321"]


def test_accounts_auto_connects(fake_ib: FakeIB) -> None:
    fake_ib._managed = ["U1"]
    client = IbkrClient(ib=fake_ib)
    assert not fake_ib.isConnected()
    assert client.accounts() == ["U1"]
    assert fake_ib.isConnected()


def test_positions_maps_to_plain_data(client: IbkrClient, fake_ib: FakeIB) -> None:
    fake_ib._positions = [
        SimpleNamespace(
            account="U1",
            contract=_contract(
                conId=11, symbol="AAPL", secType="STK", currency="USD", primaryExchange="NASDAQ"
            ),
            position=10.0,
            avgCost=150.5,
        ),
        SimpleNamespace(
            account="U2",
            contract=_contract(conId=22, symbol="MSFT", secType="STK", currency="USD"),
            position=5.0,
            avgCost=300.0,
        ),
    ]
    out = client.positions("U1")
    assert out == [
        PortfolioPosition(
            account="U1",
            con_id=11,
            symbol="AAPL",
            sec_type="STK",
            currency="USD",
            exchange="NASDAQ",
            quantity=10.0,
            avg_cost=150.5,
        )
    ]


def test_positions_falls_back_to_plain_exchange(client: IbkrClient, fake_ib: FakeIB) -> None:
    fake_ib._positions = [
        SimpleNamespace(
            account="U1",
            contract=_contract(
                conId=22, symbol="VOD", secType="STK", currency="GBP", exchange="LSE"
            ),
            position=100.0,
            avgCost=1.2,
        ),
    ]
    out = client.positions("U1")
    assert out[0].exchange == "LSE"


def test_cash_balances_filters_to_cash_rows(client: IbkrClient, fake_ib: FakeIB) -> None:
    fake_ib._account_values = [
        SimpleNamespace(account="U1", tag="CashBalance", value="1234.56", currency="USD"),
        SimpleNamespace(account="U1", tag="CashBalance", value="789.00", currency="GBP"),
        # The BASE summary row must be excluded.
        SimpleNamespace(account="U1", tag="CashBalance", value="2000.0", currency="BASE"),
        # Non-cash tags must be excluded.
        SimpleNamespace(account="U1", tag="NetLiquidation", value="50000", currency="USD"),
        SimpleNamespace(account="U1", tag="TotalCashBalance", value="9.9", currency="USD"),
    ]
    out = client.cash_balances("U1")
    assert out == [
        CashBalance(account="U1", currency="USD", amount=1234.56),
        CashBalance(account="U1", currency="GBP", amount=789.0),
    ]


def test_trades_maps_fills_and_filters_by_since(client: IbkrClient, fake_ib: FakeIB) -> None:
    early = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    late = datetime(2026, 5, 1, 15, 30, tzinfo=UTC)
    fake_ib._fills = [
        SimpleNamespace(
            contract=_contract(conId=11, symbol="AAPL", secType="STK", currency="USD"),
            execution=SimpleNamespace(
                execId="0001.a",
                acctNumber="U1",
                side="BOT",
                shares=10.0,
                price=150.0,
                time=early,
                permId=99,
            ),
            time=early,
        ),
        SimpleNamespace(
            contract=_contract(conId=22, symbol="MSFT", secType="STK", currency="USD"),
            execution=SimpleNamespace(
                execId="0002.b",
                acctNumber="U1",
                side="SLD",
                shares=5.0,
                price=300.0,
                time=late,
                permId=100,
            ),
            time=late,
        ),
    ]
    out = client.trades("U1", since=datetime(2026, 3, 1, tzinfo=UTC))
    assert out == [
        TradeExecution(
            account="U1",
            exec_id="0002.b",
            con_id=22,
            symbol="MSFT",
            sec_type="STK",
            currency="USD",
            side="SLD",
            quantity=5.0,
            price=300.0,
            executed_at=late,
            perm_id=100,
        )
    ]


def test_trades_passes_account_to_exec_filter(client: IbkrClient, fake_ib: FakeIB) -> None:
    client.trades("U1", since=datetime(2026, 1, 1, tzinfo=UTC))
    assert fake_ib.exec_filter is not None
    assert fake_ib.exec_filter.acctCode == "U1"
    # The since date is pushed into the filter time (yyyymmdd-HH:MM:SS form).
    assert fake_ib.exec_filter.time.startswith("20260101")


def test_trades_without_since_returns_all(client: IbkrClient, fake_ib: FakeIB) -> None:
    t = datetime(2020, 1, 1, tzinfo=UTC)
    fake_ib._fills = [
        SimpleNamespace(
            contract=_contract(conId=1, symbol="X", secType="STK", currency="USD"),
            execution=SimpleNamespace(
                execId="e1", acctNumber="U1", side="BOT", shares=1.0, price=1.0, time=t, permId=1
            ),
            time=t,
        ),
    ]
    out = client.trades("U1")
    assert len(out) == 1
    assert fake_ib.exec_filter.time == ""


def test_disconnect_and_context_manager(fake_ib: FakeIB) -> None:
    with IbkrClient(ib=fake_ib) as client:
        client.connect()
        assert fake_ib.isConnected()
    assert fake_ib.disconnected


def test_connect_is_idempotent(client: IbkrClient, fake_ib: FakeIB) -> None:
    client.connect()
    first = fake_ib.connect_args
    fake_ib.connect_args = None
    client.connect()  # already connected -> no second connect call
    assert fake_ib.connect_args is None
    assert first is not None
