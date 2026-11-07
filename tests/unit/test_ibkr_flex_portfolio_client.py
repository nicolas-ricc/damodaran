"""FlexPortfolioClient: one lazy download serves the portfolio and trade sources (#256)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from bot.ingest import ibkr_flex
from bot.ingest.ibkr_flex import FlexError, FlexPortfolioClient

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
SUCCESS = (
    "<FlexStatementResponse><Status>Success</Status><ReferenceCode>1</ReferenceCode>"
    f"<Url>{GET_URL}</Url></FlexStatementResponse>"
)
NY = ZoneInfo("America/New_York")
TSLA_FILL = datetime(2026, 9, 29, 19, 30, tzinfo=UTC)
AAPL_FILL = datetime(2026, 9, 15, 13, 35, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)


def _client(get_body: str | None = None) -> tuple[FlexPortfolioClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    body = FIXTURE.read_text(encoding="utf-8") if get_body is None else get_body

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=SUCCESS if request.url.path.endswith("/SendRequest") else body)

    return FlexPortfolioClient("tok", "42", tz=NY, transport=httpx.MockTransport(handler)), seen


def test_downloads_once() -> None:
    client, seen = _client()
    client.connect()
    assert client.as_of() == date(2026, 9, 30)
    accounts = client.accounts()
    client.positions(accounts[0])
    client.cash_balances(accounts[0])
    client.trades(accounts[0])
    client.corporate_actions()
    client.disconnect()
    assert len(seen) == 2


def test_nothing_downloaded_until_used() -> None:
    client, seen = _client()
    client.connect()
    client.disconnect()
    assert seen == []


def test_accounts_in_document_order() -> None:
    client, _ = _client()
    assert client.accounts() == ["U1234567", "U7654321"]


def test_positions_and_cash_filter_by_account() -> None:
    client, _ = _client()
    assert {(p.symbol, p.quantity) for p in client.positions("U1234567")} == {("AAPL", 100), ("TSLA", -20)}
    assert [p.symbol for p in client.positions("U7654321")] == ["KO"]
    assert {(c.currency, c.amount) for c in client.cash_balances("U1234567")} == {("USD", 12345.67), ("EUR", 500)}
    assert [(c.currency, c.amount) for c in client.cash_balances("U7654321")] == [("USD", 1000)]
    assert client.positions("U0000000") == []


def test_trades_without_since_returns_all_for_account() -> None:
    client, _ = _client()
    assert {t.executed_at for t in client.trades("U1234567")} == {AAPL_FILL, TSLA_FILL}
    assert client.trades("U7654321") == []


def test_trades_since_filters_client_side() -> None:
    client, _ = _client()
    got = client.trades("U1234567", since=datetime(2026, 9, 20, tzinfo=UTC))
    assert [t.symbol for t in got] == ["TSLA"]


def test_trades_since_is_inclusive() -> None:
    client, _ = _client()
    got = client.trades("U1234567", since=TSLA_FILL)
    assert [t.executed_at for t in got] == [TSLA_FILL]


def test_trades_since_must_be_aware() -> None:
    client, _ = _client()
    with pytest.raises(ValueError, match="timezone"):
        client.trades("U1234567", since=datetime(2026, 9, 20))


def test_flex_error_propagates() -> None:
    error = (
        "<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode>"
        "<ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>"
    )
    client, _ = _client(get_body=error)
    with pytest.raises(FlexError, match="1012"):
        client.as_of()


def test_network_error_is_flex_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = FlexPortfolioClient("tok", "42", tz=NY, transport=httpx.MockTransport(handler))
    with pytest.raises(FlexError):
        client.as_of()
