"""FlexClient against httpx.MockTransport: protocol, retries, failures, secrecy (#56)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import quote, quote_plus

import httpx
import pytest
from structlog.testing import capture_logs

from bot.ingest import ibkr_flex
from bot.ingest.ibkr_flex import MAX_POLLS, FlexClient, FlexError
from bot.utils.logging import configure_logging

TOKEN = "1234567890/abc+def=4567"  # not purely alphanumeric: httpx percent-encodes it in URLs
FORMS = (TOKEN, quote(TOKEN, safe=""), quote_plus(TOKEN, safe=""))
QUERY = "987654"
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
STATEMENT = '<FlexQueryResponse queryName="q" type="AF"><FlexStatements count="0" /></FlexQueryResponse>'

SUCCESS = (
    '<FlexStatementResponse timestamp="01 October, 2026 08:30 AM EDT">'
    "<Status>Success</Status><ReferenceCode>1234567890</ReferenceCode>"
    f"<Url>{GET_URL}</Url></FlexStatementResponse>"
)


def _error(status: str, code: str, message: str) -> str:
    return (
        f"<FlexStatementResponse><Status>{status}</Status>"
        f"<ErrorCode>{code}</ErrorCode><ErrorMessage>{message}</ErrorMessage>"
        "</FlexStatementResponse>"
    )


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)


def _client(statement_bodies: list[str], send_body: str = SUCCESS) -> tuple[FlexClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    bodies = iter(statement_bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/SendRequest"):
            return httpx.Response(200, text=send_body)
        return httpx.Response(200, text=next(bodies))

    return FlexClient(TOKEN, QUERY, transport=httpx.MockTransport(handler)), seen


def test_happy_path_sends_both_requests() -> None:
    client, seen = _client([STATEMENT])
    assert client.fetch_statement() == STATEMENT
    send, fetch = seen
    assert send.url.host == "ndcdyn.interactivebrokers.com"
    assert dict(send.url.params) == {"t": TOKEN, "q": QUERY, "v": "3"}
    assert str(fetch.url).startswith(GET_URL)
    assert dict(fetch.url.params) == {"q": "1234567890", "t": TOKEN, "v": "3"}


@pytest.mark.parametrize("code", ["1019", "1009"])
def test_retryable_code_then_success(code: str) -> None:
    client, seen = _client([_error("Warn", code, "Statement generation in progress."), STATEMENT])
    assert client.fetch_statement() == STATEMENT
    assert len(seen) == 3


def test_invalid_token_on_request_fails_fast_with_code() -> None:
    client, seen = _client([], send_body=_error("Fail", "1012", "Token has expired."))
    with pytest.raises(FlexError, match="1012"):
        client.fetch_statement()
    assert len(seen) == 1


def test_non_retryable_code_on_fetch_fails_fast() -> None:
    client, seen = _client([_error("Fail", "1015", "Token is invalid.")])
    with pytest.raises(FlexError, match=r"1015.*Token is invalid"):
        client.fetch_statement()
    assert len(seen) == 2


def test_exhausting_the_polls_fails() -> None:
    client, seen = _client([_error("Warn", "1019", "in progress")] * MAX_POLLS)
    with pytest.raises(FlexError, match=str(MAX_POLLS)):
        client.fetch_statement()
    assert len(seen) == 1 + MAX_POLLS


def test_success_status_on_fetch_is_not_a_statement() -> None:
    client, _ = _client([SUCCESS])
    with pytest.raises(FlexError):
        client.fetch_statement()


def _failing(handler: Callable[[httpx.Request], httpx.Response]) -> FlexClient:
    return FlexClient(TOKEN, QUERY, transport=httpx.MockTransport(handler))


def test_http_error_message_is_scrubbed() -> None:
    client = _failing(lambda request: httpx.Response(500, text="oops"))
    with pytest.raises(FlexError) as exc:
        client.fetch_statement()
    assert all(form not in str(exc.value) for form in FORMS)
    assert "***" in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_transport_error_message_is_scrubbed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    with pytest.raises(FlexError) as exc:
        _failing(handler).fetch_statement()
    assert all(form not in str(exc.value) for form in FORMS)
    assert "***" in str(exc.value)


def test_token_never_logged(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG")
    caplog.set_level(logging.DEBUG)
    client, _ = _client([_error("Warn", "1019", "in progress"), STATEMENT])
    with capture_logs() as logs:
        client.fetch_statement()
        failing, _ = _client([_error("Fail", "1015", "Token is invalid.")])
        with pytest.raises(FlexError):
            failing.fetch_statement()
    out = capsys.readouterr().out
    for form in FORMS:
        assert form not in caplog.text
        assert form not in out
        assert form not in repr(logs)
