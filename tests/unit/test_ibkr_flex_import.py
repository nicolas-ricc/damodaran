"""import_corporate_actions: no-op when unconfigured, full path when configured (#56)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import httpx
import pytest
from bot.ingest.ibkr_flex import import_corporate_actions
from structlog.testing import capture_logs

from bot.config import Settings
from bot.ingest import ibkr_flex
from bot.storage.db import apply_schema

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
SUCCESS = (
    "<FlexStatementResponse><Status>Success</Status><ReferenceCode>1</ReferenceCode>"
    "<Url>https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement</Url>"
    "</FlexStatementResponse>"
)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _settings(token: str, query_id: str) -> Settings:
    return Settings(
        sec_user_agent="Test test@example.com",
        ibkr_flex_token=token,
        ibkr_flex_query_id=query_id,
        _env_file=None,  # type: ignore[call-arg]
    )


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError("no HTTP call expected")


@pytest.mark.parametrize(
    ("token", "query_id"), [("", ""), ("tok", ""), ("", "42"), ("  ", "42"), ("tok", " ")]
)
def test_unconfigured_is_a_noop_with_one_info_line(
    conn: duckdb.DuckDBPyConnection, token: str, query_id: str
) -> None:
    with capture_logs() as logs:
        result = import_corporate_actions(
            conn, _settings(token, query_id), transport=httpx.MockTransport(_refuse)
        )
    assert result is None
    assert [e["log_level"] for e in logs] == ["info"]


def test_configured_imports_the_statement(
    conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)
    statement = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/SendRequest"):
            assert request.url.params["t"] == "tok" and request.url.params["q"] == "42"
            return httpx.Response(200, text=SUCCESS)
        return httpx.Response(200, text=statement)

    settings = _settings(" tok ", " 42 ")
    assert import_corporate_actions(conn, settings, transport=httpx.MockTransport(handler)) == 5
    assert import_corporate_actions(conn, settings, transport=httpx.MockTransport(handler)) == 0
