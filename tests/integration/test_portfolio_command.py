"""Integration test for the ``bot portfolio`` command (M5, #29).

Drives the full cycle (sync -> diff -> report) against a **mocked**
:class:`~bot.ingest.ibkr.IbkrClient` and asserts that both ``portfolio.md`` and
``alerts.md`` are produced under the dated report directory with the expected
sections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import duckdb
import pytest

from bot.ingest.ibkr import CashBalance, PortfolioPosition, TradeExecution
from bot.portfolio.command import run_portfolio
from bot.portfolio.marks import AnalyzeFn
from bot.screener.rules import Rule, RuleResult
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.storage.db import apply_schema
from bot.valuator.narrative_flags import NarrativeFlag

TODAY = date(2026, 6, 1)


class _FakeIbkrClient:
    """A lightweight in-memory stand-in for :class:`IbkrClient`."""

    def __init__(
        self,
        positions: list[PortfolioPosition],
        cash: list[CashBalance],
        fills: list[TradeExecution] | None = None,
    ) -> None:
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

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        return list(self._positions)

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        return list(self._cash)

    def trades(
        self, account_id: str, since: datetime | None = None
    ) -> list[TradeExecution]:
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


def _client() -> _FakeIbkrClient:
    """A concentrated two-position book (AAPL ~83% -> concentration event)."""
    return _FakeIbkrClient(
        positions=[
            _position("AAPL", 1, 100.0, 120.0),
            _position("MSFT", 2, 10.0, 300.0),
        ],
        cash=[CashBalance(account="DU1", currency="USD", amount=5000.0)],
    )


def _diversified_client() -> _FakeIbkrClient:
    """Eight ~12.5% holdings (below the 15% concentration threshold)."""
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    return _FakeIbkrClient(
        positions=[_position(s, i, 10.0, 100.0) for i, s in enumerate(symbols, 1)],
        cash=[CashBalance(account="DU1", currency="USD", amount=5000.0)],
    )


def _no_analyze(ticker: str, conn: duckdb.DuckDBPyConnection) -> object:
    raise LookupError("no data for ticker in test")


def test_portfolio_writes_both_reports(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
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
        "## Suggested reviews",
    ):
        assert heading in body
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
        _diversified_client(),
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


def test_quiet_day_writes_empty_alerts_after_busy_day(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    busy, quiet = date(2026, 5, 31), TODAY
    run_portfolio(
        conn, _diversified_client(), reports_dir=tmp_path, today=busy, analyze_fn=_no_analyze
    )
    assert (tmp_path / busy.isoformat() / "alerts.md").read_text() != ""
    alerts_md = tmp_path / quiet.isoformat() / "alerts.md"
    alerts_md.parent.mkdir(parents=True)
    alerts_md.write_text("stale content from an earlier run")

    run_portfolio(
        conn, _diversified_client(), reports_dir=tmp_path, today=quiet, analyze_fn=_no_analyze
    )

    assert alerts_md.read_text() == ""


def test_history_and_concentration_flags(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    run_portfolio(
        conn,
        _client(),
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


def test_run_portfolio_appends_new_trades(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    fills = [
        _fill("E1", "AAPL", datetime(2026, 6, 1, 14, 0, tzinfo=UTC)),
        # Bought and sold the same day: no position, still a trade.
        _fill("E2", "TSLA", datetime(2026, 6, 1, 15, 0, tzinfo=UTC)),
    ]
    client = _FakeIbkrClient([_position("AAPL", 1, 10.0, 100.0)], [], fills)

    result = run_portfolio(
        conn, client, reports_dir=tmp_path, today=TODAY, analyze_fn=_no_analyze
    )

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
        _FakeIbkrClient([], [], fills),
        reports_dir=tmp_path,
        today=TODAY,
        analyze_fn=_no_analyze,
    )
    again = _FakeIbkrClient([], [], fills)

    result = run_portfolio(
        conn, again, reports_dir=tmp_path, today=TODAY, analyze_fn=_no_analyze
    )

    assert result.trades_inserted == 0
    assert conn.execute("SELECT count(*) FROM trades").fetchone() == (1,)
    assert again.since_calls == [datetime(2026, 6, 1, 14, 0, tzinfo=UTC)]


def test_run_portfolio_without_fills_records_no_trades(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    result = run_portfolio(
        conn,
        _FakeIbkrClient([], []),
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
    def fn(ticker: str, _conn: duckdb.DuckDBPyConnection) -> _Analysis:
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
        _client(),
        reports_dir=tmp_path,
        today=day1,
        analyze_fn=_valued_at(90.0),  # IV below the 100 price
        quality_gates=[gate],
    )
    gate.fail = True
    run_portfolio(
        conn,
        _client(),
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
