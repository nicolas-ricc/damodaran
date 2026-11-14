"""Integration test for the ``bot portfolio`` command (M5, #29).

Drives the full cycle (sync -> diff -> report) against a **mocked**
Flex portfolio client and asserts that both ``portfolio.md`` and
``alerts.md`` are produced under the dated report directory with the expected
sections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb
import pytest
from structlog.testing import capture_logs

from bot.ingest.ibkr import CashBalance, PortfolioPosition, TradeExecution
from bot.ingest.ibkr_flex import CorporateActionRecord
from bot.portfolio.command import run_portfolio
from bot.portfolio.marks import AnalyzeFn
from bot.screener.rules import Rule, RuleResult
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.storage.db import apply_schema
from bot.valuator.narrative_flags import NarrativeFlag

TODAY = date(2026, 6, 1)


class _FakeFlexClient:
    """A lightweight in-memory stand-in for :class:`FlexPortfolioClient`."""

    def __init__(
        self,
        positions: list[PortfolioPosition],
        cash: list[CashBalance],
        fills: list[TradeExecution] | None = None,
        as_of: date = TODAY,
        actions: list[CorporateActionRecord] | None = None,
    ) -> None:
        self._as_of = as_of
        self._actions = actions or []
        self._positions = positions
        self._cash = cash
        self._fills = fills or []
        self.connected = False
        self.since_calls: list[datetime | None] = []

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def accounts(self) -> list[str]:
        return ["DU1"]

    def as_of(self) -> date:
        return self._as_of

    def corporate_actions(self) -> list[CorporateActionRecord]:
        return list(self._actions)

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        return list(self._positions)

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        return list(self._cash)

    def trades(self, account_id: str, since: datetime | None = None) -> list[TradeExecution]:
        # Unfiltered on purpose: the sync layer de-dupes on exec_id.
        self.since_calls.append(since)
        return list(self._fills)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _position(symbol: str, con_id: int, qty: float, avg_cost: float) -> PortfolioPosition:
    return PortfolioPosition(
        account="DU1",
        con_id=con_id,
        symbol=symbol,
        sec_type="STK",
        currency="USD",
        exchange="NASDAQ",
        quantity=qty,
        avg_cost=avg_cost,
    )


def _fill(exec_id: str, symbol: str, when: datetime) -> TradeExecution:
    return TradeExecution(
        account="DU1",
        exec_id=exec_id,
        con_id=1,
        symbol=symbol,
        sec_type="STK",
        currency="USD",
        side="BOT",
        quantity=10.0,
        price=100.0,
        executed_at=when,
        perm_id=1,
    )


def _client(
    as_of: date = TODAY, actions: list[CorporateActionRecord] | None = None
) -> _FakeFlexClient:
    """A concentrated two-position book (AAPL ~83% -> concentration event)."""
    return _FakeFlexClient(
        positions=[
            _position("AAPL", 1, 100.0, 120.0),
            _position("MSFT", 2, 10.0, 300.0),
        ],
        cash=[CashBalance(account="DU1", currency="USD", amount=5000.0)],
        as_of=as_of,
        actions=actions,
    )


def _diversified_client(as_of: date = TODAY) -> _FakeFlexClient:
    """Eight ~12.5% holdings (below the 15% concentration threshold)."""
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    return _FakeFlexClient(
        positions=[_position(s, i, 10.0, 100.0) for i, s in enumerate(symbols, 1)],
        cash=[CashBalance(account="DU1", currency="USD", amount=5000.0)],
        as_of=as_of,
    )


def _no_analyze(
    ticker: str, conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None
) -> object:
    raise LookupError("no data for ticker in test")


def test_portfolio_writes_both_reports(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    # Priced book so P&L and concentration are real: AAPL 15,000 vs MSFT 3,000.
    conn.executemany(
        "INSERT INTO prices_daily (ticker, date, close, currency) VALUES (?, ?, ?, 'USD')",
        [("AAPL", TODAY, 150.0), ("MSFT", TODAY, 300.0)],
    )
    result = run_portfolio(
        conn,
        _client(),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )

    portfolio_md = tmp_path / TODAY.isoformat() / "portfolio.md"
    alerts_md = tmp_path / TODAY.isoformat() / "alerts.md"

    assert portfolio_md.exists()
    assert alerts_md.exists()
    assert result.portfolio_path == portfolio_md
    assert result.alerts_path == alerts_md

    body = portfolio_md.read_text()
    for heading in (
        "# Portfolio — 2026-06-01",
        "## Positions",
        "## Profit & loss",
        "## Concentration",
        "## Detected events",
        "## Suggested reviews",
    ):
        assert heading in body
    assert "| position_opened | AAPL |" in body
    assert "AAPL" in body
    assert "MSFT" in body
    # AAPL is ~83% of the book: the concentration review must name it.
    assert "- **AAPL** is" in body

    alerts = alerts_md.read_text()
    assert "# Alerts — 2026-06-01" in alerts
    assert "| Type | Ticker | Details |" in alerts
    # First snapshot -> every position opens.
    assert "| position_opened | AAPL |" in alerts
    assert "| position_opened | MSFT |" in alerts


def test_alerts_present_but_empty_when_no_events(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # First run on an earlier day opens everything.
    run_portfolio(
        conn,
        _diversified_client(date(2026, 5, 31)),
        reports_dir=tmp_path,
        today=date(2026, 5, 31),
        analyze_fn=_no_analyze,
    )
    # Second run, same positions, on a new day -> no events.
    result = run_portfolio(
        conn,
        _diversified_client(),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )

    assert result.events == 0
    alerts_md = tmp_path / TODAY.isoformat() / "alerts.md"
    assert alerts_md.exists()
    assert result.alerts_path == alerts_md
    assert alerts_md.read_text() == ""
    assert "_No events detected today._" in result.portfolio_path.read_text()


def test_quiet_day_writes_empty_alerts_after_busy_day(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    busy, quiet = date(2026, 5, 31), TODAY
    run_portfolio(
        conn, _diversified_client(busy), reports_dir=tmp_path, today=busy, analyze_fn=_no_analyze
    )
    assert (tmp_path / busy.isoformat() / "alerts.md").read_text() != ""
    alerts_md = tmp_path / quiet.isoformat() / "alerts.md"
    alerts_md.parent.mkdir(parents=True)
    alerts_md.write_text("stale content from an earlier run")

    run_portfolio(
        conn, _diversified_client(), reports_dir=tmp_path, today=quiet, analyze_fn=_no_analyze
    )

    assert alerts_md.read_text() == ""


def test_history_and_concentration_flags(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    run_portfolio(
        conn,
        _client(date(2026, 5, 31)),
        reports_dir=tmp_path,
        today=date(2026, 5, 31),
        analyze_fn=_no_analyze,
    )
    result = run_portfolio(
        conn,
        _client(),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
        history=True,
        concentration=True,
    )

    body = result.portfolio_path.read_text()
    assert "## P&L history" in body
    assert "## Concentration breakdown" in body
    assert "| 2026-05-31 |" in body
    assert "| 2026-06-01 |" in body


def test_run_portfolio_appends_new_trades(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    fills = [
        _fill("E1", "AAPL", datetime(2026, 6, 1, 14, 0, tzinfo=UTC)),
        # Bought and sold the same day: no position, still a trade.
        _fill("E2", "TSLA", datetime(2026, 6, 1, 15, 0, tzinfo=UTC)),
    ]
    client = _FakeFlexClient([_position("AAPL", 1, 10.0, 100.0)], [], fills)

    result = run_portfolio(conn, client, reports_dir=tmp_path, today=TODAY, analyze_fn=_no_analyze)

    assert result.trades_inserted == 2
    rows = conn.execute("SELECT exec_id FROM trades ORDER BY exec_id").fetchall()
    assert rows == [("E1",), ("E2",)]
    assert client.since_calls == [None]
    assert client.connected is False


def test_run_portfolio_same_day_rerun_does_not_duplicate_trades(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fills = [_fill("E1", "AAPL", datetime(2026, 6, 1, 14, 0, tzinfo=UTC))]
    run_portfolio(
        conn,
        _FakeFlexClient([], [], fills),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )
    again = _FakeFlexClient([], [], fills)

    result = run_portfolio(conn, again, reports_dir=tmp_path, today=TODAY, analyze_fn=_no_analyze)

    assert result.trades_inserted == 0
    assert conn.execute("SELECT count(*) FROM trades").fetchone() == (1,)
    assert again.since_calls == [datetime(2026, 6, 1, 14, 0, tzinfo=UTC)]


def test_run_portfolio_without_fills_records_no_trades(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    result = run_portfolio(
        conn,
        _FakeFlexClient([], []),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )

    assert result.trades_inserted == 0
    assert conn.execute("SELECT count(*) FROM trades").fetchone() == (0,)


@dataclass(frozen=True)
class _DCF:
    intrinsic_value: float


@dataclass(frozen=True)
class _Analysis:
    ticker: str
    dcf_result: _DCF
    current_price: float | None
    narrative_flags: tuple[NarrativeFlag, ...] = ()


def _valued_at(iv: float) -> AnalyzeFn:
    def fn(
        ticker: str, _conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None
    ) -> _Analysis:
        return _Analysis(ticker, _DCF(iv), current_price=100.0)

    return cast(AnalyzeFn, fn)


class _ToggleGate(Rule):
    """A quality gate whose verdict the test flips between runs."""

    name = "toggle_gate"

    def __init__(self) -> None:
        self.fail = False

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        return RuleResult(passed=not self.fail)


def _logged(conn: duckdb.DuckDBPyConnection, day: date) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT event_type, ticker FROM events_log WHERE curr_snapshot_date = ?", [day]
    ).fetchall()
    return {(str(r[0]), str(r[1])) for r in rows}


def test_run_portfolio_emits_valuation_events_across_two_runs(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    day1, day2 = date(2026, 6, 1), date(2026, 6, 2)
    conn.execute("INSERT INTO companies (ticker, name, source) VALUES ('AAPL', 'Apple', 'fmp')")
    gate = _ToggleGate()

    run_portfolio(
        conn,
        _client(day1),
        reports_dir=tmp_path,
        today=day1,
        analyze_fn=_valued_at(90.0),  # IV below the 100 price
        quality_gates=[gate],
    )
    gate.fail = True
    run_portfolio(
        conn,
        _client(day2),
        reports_dir=tmp_path,
        today=day2,
        analyze_fn=_valued_at(120.0),  # IV now above price
        quality_gates=[gate],
    )

    logged = _logged(conn, day2)
    assert ("intrinsic_value_crossed_price", "AAPL") in logged
    assert ("intrinsic_value_crossed_price", "MSFT") in logged
    assert ("below_quality_gate", "AAPL") in logged
    # MSFT is not in companies: no gate verdict, so no gate event.
    assert ("below_quality_gate", "MSFT") not in logged
    marked = conn.execute(
        "SELECT snapshot_date, COUNT(*) FROM holding_marks GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert marked == [(day1, 2), (day2, 2)]


def test_corporate_actions_from_client_feed_events(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    client = _client(
        actions=[
            CorporateActionRecord(
                action_id="ct:1",
                account="DU1",
                action_type="dividend",
                ticker="MSFT",
                effective_date=TODAY,
                details={},
            )
        ]
    )

    run_portfolio(conn, client, reports_dir=tmp_path, today=TODAY, analyze_fn=_no_analyze)

    assert conn.execute("SELECT action_id FROM corporate_actions").fetchall() == [("ct:1",)]
    logged = conn.execute(
        "SELECT event_type, ticker FROM events_log WHERE curr_snapshot_date = ?", [TODAY]
    ).fetchall()
    assert ("dividend", "MSFT") in logged


def test_snapshot_keyed_on_as_of(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    as_of = date(2026, 6, 1)
    result = run_portfolio(
        conn,
        _client(as_of),
        reports_dir=tmp_path,
        today=date(2026, 6, 3),
        analyze_fn=_no_analyze,
    )

    assert result.snapshot_date == as_of
    assert result.portfolio_path == tmp_path / "2026-06-01" / "portfolio.md"
    assert not (tmp_path / "2026-06-03").exists()
    dates = conn.execute("SELECT DISTINCT snapshot_date FROM portfolio_snapshots").fetchall()
    assert dates == [(as_of,)]


@pytest.mark.parametrize(("age_days", "stale"), [(6, True), (5, False)])
def test_stale_statement_warns(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path, age_days: int, stale: bool
) -> None:
    today = date(2026, 6, 10)
    as_of = today - timedelta(days=age_days)

    with capture_logs() as logs:
        run_portfolio(
            conn, _client(as_of), reports_dir=tmp_path, today=today, analyze_fn=_no_analyze
        )

    stale_logs = [e for e in logs if e["event"] == "portfolio_statement_stale"]
    if stale:
        assert len(stale_logs) == 1
        assert stale_logs[0]["log_level"] == "warning"
        assert stale_logs[0]["days"] == age_days
    else:
        assert stale_logs == []
    assert (tmp_path / as_of.isoformat() / "portfolio.md").exists()


DAY1, DAY2 = date(2026, 6, 1), date(2026, 6, 2)


def _count(conn: duckdb.DuckDBPyConnection, day: date) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM events_log WHERE curr_snapshot_date = ?", [day]
    ).fetchone()
    assert row is not None
    return int(row[0])


def _insert_filing(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    filing_type: str,
    filing_date: date,
    fetched_at: date,
) -> None:
    conn.execute(
        "INSERT INTO filings_log "
        "(ticker, filing_type, filing_date, accession_number, source, fetched_at) "
        "VALUES (?, ?, ?, ?, 'sec', ?)",
        [
            ticker,
            filing_type,
            filing_date,
            f"{ticker}-{filing_type}",
            datetime.combine(fetched_at, datetime.min.time()),
        ],
    )


def _dividend(day: date) -> CorporateActionRecord:
    return CorporateActionRecord(
        action_id="ct:1",
        account="DU1",
        action_type="dividend",
        ticker="MSFT",
        effective_date=day,
        details={"amount": 2.5},
    )


def _run(
    conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
    day: date,
    *,
    iv: float = 90.0,
    gate: _ToggleGate | None = None,
    actions: list[CorporateActionRecord] | None = None,
) -> tuple[int, bytes]:
    result = run_portfolio(
        conn,
        _client(day, actions=actions),
        reports_dir=tmp_path,
        today=day,
        analyze_fn=_valued_at(iv),
        quality_gates=[gate] if gate is not None else [],
    )
    return result.events, result.alerts_path.read_bytes()


def test_same_day_rerun_is_idempotent(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    conn.execute("INSERT INTO companies (ticker, name, source) VALUES ('AAPL', 'Apple', 'fmp')")
    gate = _ToggleGate()
    _run(conn, tmp_path, DAY1, iv=90.0, gate=gate)
    gate.fail = True
    _insert_filing(conn, "AAPL", "10-Q", DAY2, fetched_at=DAY2)

    first_events, first_alerts = _run(
        conn, tmp_path, DAY2, iv=120.0, gate=gate, actions=[_dividend(DAY2)]
    )
    first_count = _count(conn, DAY2)
    second_events, second_alerts = _run(
        conn, tmp_path, DAY2, iv=120.0, gate=gate, actions=[_dividend(DAY2)]
    )

    assert first_count > 0
    assert _count(conn, DAY2) == first_count
    assert second_alerts == first_alerts
    assert second_events == first_events == first_count
    logged = {t for t, _ in _logged(conn, DAY2)}
    assert {
        "intrinsic_value_crossed_price",
        "below_quality_gate",
        "dividend",
        "new_filing",
    } <= logged


def test_rerun_keeps_new_filing_in_alerts(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _run(conn, tmp_path, DAY1)
    _insert_filing(conn, "AAPL", "10-Q", DAY2, fetched_at=DAY2)

    _run(conn, tmp_path, DAY2)
    _, alerts = _run(conn, tmp_path, DAY2)

    assert "| new_filing | AAPL |" in alerts.decode()
    rows = conn.execute(
        "SELECT COUNT(*) FROM events_log "
        "WHERE event_type = 'new_filing' AND curr_snapshot_date = ?",
        [DAY2],
    ).fetchone()
    assert rows == (1,)


def test_rerun_logs_and_alerts_a_filing_that_arrived_between_runs(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    _run(conn, tmp_path, DAY1)
    _, first_alerts = _run(conn, tmp_path, DAY2, iv=120.0, actions=[_dividend(DAY2)])
    before = _count(conn, DAY2)
    assert before > 0
    _insert_filing(conn, "MSFT", "8-K", DAY2, fetched_at=DAY2)

    _, second_alerts = _run(conn, tmp_path, DAY2, iv=120.0, actions=[_dividend(DAY2)])

    assert _count(conn, DAY2) == before + 1
    rows = conn.execute(
        "SELECT COUNT(*) FROM events_log WHERE event_type = 'new_filing' "
        "AND ticker = 'MSFT' AND curr_snapshot_date = ?",
        [DAY2],
    ).fetchone()
    assert rows == (1,)
    text = second_alerts.decode()
    assert text.count("| new_filing | MSFT |") == 1
    for line in first_alerts.decode().splitlines():
        if line.startswith("| ") and not line.startswith("| Type"):
            assert line in text


def test_rerun_leaves_other_days_untouched(conn: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    _, day1_alerts = _run(conn, tmp_path, DAY1)
    day1_count = _count(conn, DAY1)

    _run(conn, tmp_path, DAY2, iv=120.0, actions=[_dividend(DAY2)])
    _run(conn, tmp_path, DAY2, iv=120.0, actions=[_dividend(DAY2)])

    assert _count(conn, DAY1) == day1_count
    assert (tmp_path / DAY1.isoformat() / "alerts.md").read_bytes() == day1_alerts
