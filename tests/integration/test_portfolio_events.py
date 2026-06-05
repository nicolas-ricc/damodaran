"""Integration test for ``compute_events`` (§8.3 portfolio monitor, M5, #28).

Seeds two consecutive portfolio snapshots plus a fixture filings-log entry and a
corporate action, then asserts the exact set of events emitted by the
reader-orchestrator — and that a price-only move produces no event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import duckdb
import pytest

from bot.portfolio.events import (
    EventType,
    compute_events,
    persist_events,
)
from bot.storage.db import apply_schema
from bot.valuator.narrative_flags import FlagColor, NarrativeFlag

PREV = date(2026, 5, 1)
CURR = date(2026, 5, 2)


@dataclass(frozen=True)
class _DCF:
    intrinsic_value: float


@dataclass(frozen=True)
class _Analysis:
    ticker: str
    dcf_result: _DCF
    current_price: float | None
    narrative_flags: tuple[NarrativeFlag, ...] = field(default_factory=tuple)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _insert_snapshot(
    conn: duckdb.DuckDBPyConnection,
    snapshot_date: date,
    rows: list[tuple[str, float, float, str]],
) -> None:
    for ticker, qty, mv, ccy in rows:
        conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
            "VALUES (?, 'DU1', ?, ?, ?, ?, ?)",
            [snapshot_date, ticker, hash(ticker) & 0xFFFF, qty, mv, ccy],
        )


def test_compute_events_end_to_end(conn: duckdb.DuckDBPyConnection) -> None:
    # PREV snapshot: AAPL (held, stable), MSFT (will be trimmed), GOOG (closed next).
    _insert_snapshot(
        conn,
        PREV,
        [
            ("AAPL", 100.0, 1500.0, "USD"),
            ("MSFT", 100.0, 3000.0, "USD"),
            ("GOOG", 10.0, 1000.0, "USD"),
        ],
    )
    # CURR snapshot: AAPL same qty (price moved only), MSFT trimmed 30%,
    # GOOG closed, NVDA opened large (concentration), AAPL currency flips.
    _insert_snapshot(
        conn,
        CURR,
        [
            ("AAPL", 100.0, 1600.0, "EUR"),  # price up + currency change, qty flat
            ("MSFT", 70.0, 2100.0, "USD"),  # -30% size change
            ("NVDA", 50.0, 9000.0, "USD"),  # opened, big -> concentration
        ],
    )

    # Fixture filing for a held ticker, inside the window.
    conn.execute(
        "INSERT INTO filings_log "
        "(ticker, filing_type, filing_date, accession_number, source) "
        "VALUES ('AAPL', '10-Q', ?, '0001', 'sec-edgar')",
        [CURR],
    )
    # Filing before the window must NOT fire.
    conn.execute(
        "INSERT INTO filings_log "
        "(ticker, filing_type, filing_date, accession_number, source) "
        "VALUES ('AAPL', '10-K', ?, '0000', 'sec-edgar')",
        [date(2026, 4, 1)],
    )
    # Corporate action: a dividend in the window.
    conn.execute(
        "INSERT INTO corporate_actions "
        "(action_id, action_type, ticker, effective_date, details) "
        "VALUES ('a1', 'Dividend', 'MSFT', ?, '{\"amount\": 0.75}')",
        [CURR],
    )

    # An intrinsic-value cross for AAPL, supplied via prev_analyses baseline.
    prev_analyses = {
        "AAPL": _Analysis(
            "AAPL",
            _DCF(90.0),
            current_price=100.0,  # IV below price previously
            narrative_flags=(NarrativeFlag("story_margin", FlagColor.GREEN, "ok"),),
        )
    }

    def fake_analyze(ticker: str, _conn: duckdb.DuckDBPyConnection) -> _Analysis:
        flags: tuple[NarrativeFlag, ...]
        if ticker == "AAPL":
            # IV now above price -> cross; story_margin newly red.
            return _Analysis(
                "AAPL",
                _DCF(120.0),
                current_price=100.0,
                narrative_flags=(NarrativeFlag("story_margin", FlagColor.RED, "now red"),),
            )
        flags = ()
        return _Analysis(ticker, _DCF(10.0), current_price=10.0, narrative_flags=flags)

    events = compute_events(
        conn,
        PREV,
        CURR,
        analyze_fn=fake_analyze,
        prev_analyses=prev_analyses,
    )

    got = {(e.event_type, e.ticker) for e in events}

    # IBKR-observed
    assert (EventType.POSITION_OPENED, "NVDA") in got
    assert (EventType.POSITION_CLOSED, "GOOG") in got
    assert (EventType.POSITION_SIZE_CHANGED, "MSFT") in got
    assert (EventType.CURRENCY_CHANGED, "AAPL") in got
    assert (EventType.DIVIDEND, "MSFT") in got
    # Derived
    assert (EventType.NEW_FILING, "AAPL") in got
    assert (EventType.INTRINSIC_VALUE_CROSSED_PRICE, "AAPL") in got
    assert (EventType.NEW_RED_FLAG, "AAPL") in got
    assert (EventType.CONCENTRATION, "NVDA") in got

    # AAPL qty did NOT change (only its price/market value did) -> no size event.
    assert (EventType.POSITION_SIZE_CHANGED, "AAPL") not in got
    # The pre-window 10-K filing must not fire (only the windowed 10-Q).
    filing_accessions = {
        e.details["accession_number"]
        for e in events
        if e.event_type is EventType.NEW_FILING
    }
    assert filing_accessions == {"0001"}

    # Persist and read back.
    written = persist_events(conn, events)
    assert written == len(events)
    (count,) = conn.execute("SELECT COUNT(*) FROM events_log").fetchone() or (0,)
    assert count == len(events)


def test_price_move_only_emits_nothing(conn: duckdb.DuckDBPyConnection) -> None:
    """Same positions, same qty, only market value (price) moved -> no events.

    Eight equally-weighted holdings (~12.5% each, below the 15% concentration
    threshold) whose prices all rise uniformly: no size change, no concentration,
    no currency change, and an unchanged valuation -> a completely empty stream.
    """
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    _insert_snapshot(conn, PREV, [(t, 100.0, 1000.0, "USD") for t in tickers])
    _insert_snapshot(conn, CURR, [(t, 100.0, 1200.0, "USD") for t in tickers])

    def fake_analyze(ticker: str, _conn: duckdb.DuckDBPyConnection) -> _Analysis:
        # Valuation unchanged: IV stays below price, no new flags.
        return _Analysis(
            ticker,
            _DCF(80.0),
            current_price=100.0,
            narrative_flags=(NarrativeFlag("story_margin", FlagColor.GREEN, "ok"),),
        )

    prev_analyses = {
        t: _Analysis(
            t,
            _DCF(80.0),
            current_price=90.0,
            narrative_flags=(NarrativeFlag("story_margin", FlagColor.GREEN, "ok"),),
        )
        for t in tickers
    }

    events = compute_events(
        conn, PREV, CURR, analyze_fn=fake_analyze, prev_analyses=prev_analyses
    )
    assert events == []


def test_first_snapshot_opens_all_positions(conn: duckdb.DuckDBPyConnection) -> None:
    # Ten equally-weighted holdings (10% each, below the 15% threshold) so the
    # first snapshot yields only "opened" events, not spurious concentration.
    tickers = [f"T{i:02d}" for i in range(10)]
    _insert_snapshot(conn, CURR, [(t, 100.0, 1000.0, "USD") for t in tickers])

    def fake_analyze(ticker: str, _conn: duckdb.DuckDBPyConnection) -> _Analysis:
        return _Analysis(ticker, _DCF(80.0), current_price=100.0)

    events = compute_events(conn, None, CURR, analyze_fn=fake_analyze)
    assert {(e.event_type, e.ticker) for e in events} == {
        (EventType.POSITION_OPENED, t) for t in tickers
    }
