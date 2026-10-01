"""Integration test for ``compute_events`` (§8.3 portfolio monitor, M5, #28).

Seeds two consecutive portfolio snapshots, their holding marks, a fixture
filings-log entry and a corporate action, then asserts the exact set of events
emitted by the reader-orchestrator — and that a price-only move produces no
event.
"""

from __future__ import annotations

from datetime import date, datetime

import duckdb
import pytest
from bot.portfolio.marks import HoldingMark, persist_marks

from bot.portfolio.events import (
    EventType,
    compute_events,
    persist_events,
)
from bot.storage.db import apply_schema

PREV = date(2026, 5, 1)
CURR = date(2026, 5, 2)


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


def _insert_filing(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    filing_type: str,
    filing_date: date,
    accession: str,
    fetched_on: date,
) -> None:
    conn.execute(
        "INSERT INTO filings_log "
        "(ticker, filing_type, filing_date, accession_number, source, fetched_at) "
        "VALUES (?, ?, ?, ?, 'sec-edgar', ?)",
        [ticker, filing_type, filing_date, accession, datetime.combine(fetched_on, datetime.min.time())],
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

    # Fixture filing for a held ticker, ingested inside the window.
    _insert_filing(conn, "AAPL", "10-Q", CURR, "0001", fetched_on=CURR)
    # Filing filed and ingested before the window must NOT fire.
    _insert_filing(conn, "AAPL", "10-K", date(2026, 4, 1), "0000", fetched_on=date(2026, 4, 2))
    # Corporate action: a dividend in the window.
    conn.execute(
        "INSERT INTO corporate_actions "
        "(action_id, action_type, ticker, effective_date, details) "
        "VALUES ('a1', 'Dividend', 'MSFT', ?, '{\"amount\": 0.75}')",
        [CURR],
    )

    # Holding marks: AAPL's IV crosses above price, story_margin turns red and
    # it newly fails a gate; MSFT's sector WACC moves 150bps.
    persist_marks(
        conn,
        PREV,
        [
            HoldingMark("AAPL", 90.0, 100.0, red_flags={}, failed_gates=(), sector_wacc=0.08),
            HoldingMark("MSFT", 10.0, 10.0, red_flags={}, failed_gates=(), sector_wacc=0.08),
            HoldingMark("GOOG", 10.0, 10.0, red_flags={}, failed_gates=(), sector_wacc=0.08),
        ],
    )
    persist_marks(
        conn,
        CURR,
        [
            HoldingMark(
                "AAPL",
                120.0,
                100.0,
                red_flags={"story_margin": "now red"},
                failed_gates=("max_net_debt_to_ebitda",),
                sector_wacc=0.08,
            ),
            HoldingMark("MSFT", 10.0, 10.0, red_flags={}, failed_gates=(), sector_wacc=0.095),
            HoldingMark("NVDA", 10.0, 10.0, red_flags={}, failed_gates=(), sector_wacc=0.08),
        ],
    )

    events = compute_events(conn, PREV, CURR)

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
    assert (EventType.BELOW_QUALITY_GATE, "AAPL") in got
    assert (EventType.SECTOR_RECALIBRATED, "MSFT") in got

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

    # Valuation unchanged (IV still below price, the same flag still red, the
    # same gate still failed, same sector WACC) while the price moved.
    for day, price in ((PREV, 90.0), (CURR, 100.0)):
        persist_marks(
            conn,
            day,
            [
                HoldingMark(
                    t,
                    80.0,
                    price,
                    red_flags={"story_margin": "high"},
                    failed_gates=("min_interest_coverage",),
                    sector_wacc=0.08,
                )
                for t in tickers
            ],
        )

    events = compute_events(conn, PREV, CURR)
    assert events == []


def test_first_snapshot_opens_all_positions(conn: duckdb.DuckDBPyConnection) -> None:
    # Ten equally-weighted holdings (10% each, below the 15% threshold) so the
    # first snapshot yields only "opened" events, not spurious concentration.
    tickers = [f"T{i:02d}" for i in range(10)]
    _insert_snapshot(conn, CURR, [(t, 100.0, 1000.0, "USD") for t in tickers])

    persist_marks(conn, CURR, [HoldingMark(t, 80.0, 100.0, red_flags={}) for t in tickers])

    events = compute_events(conn, None, CURR)
    assert {(e.event_type, e.ticker) for e in events} == {
        (EventType.POSITION_OPENED, t) for t in tickers
    }


def test_persistent_red_flag_reported_once(conn: duckdb.DuckDBPyConnection) -> None:
    days = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]
    tickers = [f"T{i:02d}" for i in range(10)]
    for day in days:
        _insert_snapshot(conn, day, [(t, 100.0, 1000.0, "USD") for t in tickers])
    persist_marks(conn, days[0], [HoldingMark(t, 80.0, 100.0, red_flags={}) for t in tickers])
    for day in days[1:]:
        persist_marks(
            conn,
            day,
            [
                HoldingMark(t, 80.0, 100.0, red_flags={"story_margin": "high"} if t == "T00" else {})
                for t in tickers
            ],
        )

    second = compute_events(conn, days[0], days[1])
    third = compute_events(conn, days[1], days[2])

    assert {(e.event_type, e.ticker) for e in second} == {(EventType.NEW_RED_FLAG, "T00")}
    assert third == []


def test_new_filing_reported_once(conn: duckdb.DuckDBPyConnection) -> None:
    tickers = [f"T{i:02d}" for i in range(10)]
    for day in (PREV, CURR):
        _insert_snapshot(conn, day, [(t, 100.0, 1000.0, "USD") for t in tickers])
    # Filed weeks ago, ingested today.
    _insert_filing(conn, "T00", "10-K", date(2026, 4, 10), "k", fetched_on=CURR)

    first = compute_events(conn, PREV, CURR)
    assert [(e.event_type, e.ticker) for e in first] == [(EventType.NEW_FILING, "T00")]
    persist_events(conn, first)

    assert compute_events(conn, PREV, CURR) == []
