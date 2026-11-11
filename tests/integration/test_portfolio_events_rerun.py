"""Same-day reruns of the portfolio monitor log each event once (#83).

``persist_events`` skips events already in ``events_log`` and ``load_events``
reads a snapshot day back, in insertion order, for ``alerts.md``.
"""

from __future__ import annotations

import json
from datetime import date

import duckdb
import pytest

from bot.portfolio.events import Event, EventType, load_events, persist_events
from bot.storage.db import apply_schema

PREV = date(2026, 5, 1)
CURR = date(2026, 5, 2)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _count(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM events_log").fetchone()
    assert row is not None
    return int(row[0])


def test_persist_events_twice_writes_once_for_every_event_type(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    events = [Event(t, "AAA", CURR, PREV, {"k": 1.5, "a": "x"}) for t in EventType]
    assert len(events) == 12

    assert persist_events(conn, events) == 12
    assert persist_events(conn, events) == 0
    assert _count(conn) == 12


def test_persist_events_dedupes_within_batch(conn: duckdb.DuckDBPyConnection) -> None:
    e = Event(EventType.CONCENTRATION, "AAA", CURR, PREV, {"weight": 0.2})

    assert persist_events(conn, [e, e]) == 1
    assert _count(conn) == 1


def test_persist_events_keeps_events_differing_only_in_details(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    k = Event(EventType.NEW_FILING, "AAA", CURR, PREV, {"filing_type": "10-K"})
    q = Event(EventType.NEW_FILING, "AAA", CURR, PREV, {"filing_type": "8-K"})
    assert persist_events(conn, [k, q]) == 2

    moved = Event(EventType.NEW_FILING, "AAA", CURR, PREV, {"filing_type": "10-K", "x": 1})
    assert persist_events(conn, [k, moved]) == 1
    assert _count(conn) == 3


def test_persist_events_ignores_details_key_order(conn: duckdb.DuckDBPyConnection) -> None:
    assert persist_events(conn, [Event(EventType.SPLIT, "AAA", CURR, PREV, {"a": 1, "b": 2})]) == 1
    assert persist_events(conn, [Event(EventType.SPLIT, "AAA", CURR, PREV, {"b": 2, "a": 1})]) == 0


def test_persist_events_other_dates_unaffected(conn: duckdb.DuckDBPyConnection) -> None:
    earlier = Event(EventType.DIVIDEND, "AAA", PREV, None, {"amount": 1.0})
    later = Event(EventType.DIVIDEND, "AAA", CURR, PREV, {"amount": 1.0})

    assert persist_events(conn, [earlier]) == 1
    assert persist_events(conn, [later]) == 1
    assert load_events(conn, PREV) == [earlier]


def test_persist_events_empty_batch(conn: duckdb.DuckDBPyConnection) -> None:
    assert persist_events(conn, []) == 0


def test_load_events_round_trips_details(conn: duckdb.DuckDBPyConnection) -> None:
    e1 = Event(EventType.NEW_RED_FLAG, "AAA", CURR, PREV, {"z": 0.123456789, "a": None, "m": "s"})
    e2 = Event(EventType.POSITION_OPENED, "BBB", CURR, None, {"qty": 10.0})
    persist_events(conn, [e1, e2])

    loaded = load_events(conn, CURR)

    assert loaded == [e1, e2]
    assert list(loaded[0].details) == ["z", "a", "m"]
    assert isinstance(loaded[0].event_type, EventType)


def test_load_events_empty_day(conn: duckdb.DuckDBPyConnection) -> None:
    assert load_events(conn, CURR) == []


def test_load_events_collapses_preexisting_duplicates(conn: duckdb.DuckDBPyConnection) -> None:
    e = Event(EventType.CONCENTRATION, "AAA", CURR, PREV, {"weight": 0.2})
    for _ in range(2):  # what the pre-#83 append left behind
        conn.execute(
            "INSERT INTO events_log "
            "(event_type, ticker, prev_snapshot_date, curr_snapshot_date, details) "
            "VALUES (?, ?, ?, ?, ?)",
            [str(e.event_type), e.ticker, PREV, CURR, json.dumps(e.details)],
        )

    assert load_events(conn, CURR) == [e]
