"""``bot portfolio`` end to end over a Flex statement, no TWS (#256, AC1).

The real :class:`~bot.ingest.ibkr_flex.FlexPortfolioClient` reads the synthetic
``statement_sample.xml`` through an ``httpx.MockTransport``; ``run_portfolio``
writes the snapshot, cash, trades, corporate actions, events and both reports
keyed on the statement date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import httpx
import pytest

from bot.ingest import ibkr_flex
from bot.ingest.ibkr_flex import FlexPortfolioClient
from bot.portfolio.command import run_portfolio
from bot.storage.db import apply_schema

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
AS_OF = date(2026, 9, 30)
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
SUCCESS = (
    "<FlexStatementResponse><Status>Success</Status><ReferenceCode>1</ReferenceCode>"
    f"<Url>{GET_URL}</Url></FlexStatementResponse>"
)


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    c.executemany(
        "INSERT INTO prices_daily (ticker, date, close, currency) VALUES (?, ?, ?, 'USD')",
        [("AAPL", AS_OF, 171.1), ("TSLA", AS_OF, 250.0), ("KO", AS_OF, 70.0)],
    )
    return c


def _client(requests: list[httpx.Request]) -> FlexPortfolioClient:
    statement = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/SendRequest"):
            return httpx.Response(200, text=SUCCESS)
        return httpx.Response(200, text=statement)

    return FlexPortfolioClient(
        "token",
        "query",
        tz=ZoneInfo("America/New_York"),
        transport=httpx.MockTransport(handler),
    )


def _no_analyze(
    ticker: str, conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None
) -> object:
    raise LookupError("no data for ticker in test")


def test_full_flow_over_flex_fixture(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    result = run_portfolio(
        conn,
        _client(requests),
        reports_dir=tmp_path,
        today=AS_OF + timedelta(days=1),
        analyze_fn=_no_analyze,
    )

    # One statement download: SendRequest + GetStatement.
    assert len(requests) == 2
    assert result.snapshot_date == AS_OF
    assert (tmp_path / AS_OF.isoformat() / "portfolio.md").exists()
    assert (tmp_path / AS_OF.isoformat() / "alerts.md").exists()

    snapshots = conn.execute(
        "SELECT account, ticker, qty FROM portfolio_snapshots "
        "WHERE snapshot_date = ? ORDER BY account, ticker",
        [AS_OF],
    ).fetchall()
    assert snapshots == [
        ("U1234567", "AAPL", 100.0),
        ("U1234567", "TSLA", -20.0),
        ("U7654321", "KO", 50.0),
    ]

    cash = conn.execute(
        "SELECT account, currency, amount FROM cash_balances "
        "WHERE snapshot_date = ? ORDER BY account, currency",
        [AS_OF],
    ).fetchall()
    assert cash == [
        ("U1234567", "EUR", 500.0),
        ("U1234567", "USD", 12345.67),
        ("U7654321", "USD", 1000.0),
    ]

    trades = conn.execute(
        "SELECT exec_id, account, ticker, side, qty, price, executed_at, perm_id "
        "FROM trades ORDER BY executed_at"
    ).fetchall()
    assert trades == [
        ("0000e0d5.66e6c1a1.01.01", "U1234567", "AAPL", "BUY", 100.0, 150.25,
         datetime(2026, 9, 15, 13, 35), 1234567890),
        ("0000e0d5.66f9a2b3.01.01", "U1234567", "TSLA", "SELL", -20.0, 240.0,
         datetime(2026, 9, 29, 19, 30), 1234567891),
    ]
    assert result.trades_inserted == 2

    actions = {row[0] for row in conn.execute("SELECT action_id FROM corporate_actions").fetchall()}
    assert actions == {"ca:1001", "ca:1002", "ca:1003", "ct:2001", "ct:2003"}

    opened = conn.execute(
        "SELECT ticker FROM events_log WHERE event_type = 'position_opened' "
        "AND curr_snapshot_date = ? ORDER BY ticker",
        [AS_OF],
    ).fetchall()
    assert [row[0] for row in opened] == ["AAPL", "KO", "TSLA"]


def test_rerun_with_the_same_statement_keeps_one_snapshot(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    for day in (AS_OF + timedelta(days=1), AS_OF + timedelta(days=2)):
        run_portfolio(conn, _client([]), reports_dir=tmp_path, today=day, analyze_fn=_no_analyze)

    dates = conn.execute("SELECT DISTINCT snapshot_date FROM portfolio_snapshots").fetchall()
    assert dates == [(AS_OF,)]
    assert conn.execute("SELECT count(*) FROM trades").fetchone() == (2,)
    assert conn.execute("SELECT count(*) FROM corporate_actions").fetchone() == (5,)
    assert [p.name for p in tmp_path.iterdir()] == [AS_OF.isoformat()]
