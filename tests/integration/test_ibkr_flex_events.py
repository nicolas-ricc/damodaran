"""Fixture -> upsert -> compute_events: Flex rows make DIVIDEND/SPLIT fire (#56)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest
from bot.ingest.ibkr_flex import (
    CorporateActionRecord,
    parse_flex_statement,
    upsert_corporate_actions,
)

from bot.portfolio.events import EventType, compute_events
from bot.storage.db import apply_schema

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
PREV = date(2026, 9, 1)
CURR = date(2026, 9, 30)
HELD = ("AAPL", "GE", "ATVI", "MSFT", "KO")


@pytest.fixture
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(str(tmp_path / "flex.duckdb"))
    apply_schema(c)
    return c


def _records() -> list[CorporateActionRecord]:
    return parse_flex_statement(FIXTURE.read_text(encoding="utf-8"))


def test_importing_the_fixture_twice_is_idempotent(conn: duckdb.DuckDBPyConnection) -> None:
    assert upsert_corporate_actions(conn, _records()) == 5
    assert upsert_corporate_actions(conn, _records()) == 0
    assert conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone() == (5,)


def test_upsert_stores_the_mapped_columns(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_corporate_actions(conn, _records())
    row = conn.execute(
        "SELECT account, action_type, ticker, effective_date, details, source "
        "FROM corporate_actions WHERE action_id = 'ca:1001'"
    ).fetchone()
    assert row is not None
    assert row[:4] == ("U1234567", "split", "AAPL", date(2026, 9, 15))
    assert json.loads(row[4])["ratio"] == "4:1"
    assert row[5] == "ibkr-flex"


def _snapshot(conn: duckdb.DuckDBPyConnection, day: date) -> None:
    for i, ticker in enumerate(HELD):
        conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
            "VALUES (?, 'U1234567', ?, ?, 10, 1000, 'USD')",
            [day, ticker, i + 1],
        )


def test_fixture_rows_become_dividend_and_split_events(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_corporate_actions(conn, _records())
    _snapshot(conn, PREV)
    _snapshot(conn, CURR)

    events = compute_events(conn, PREV, CURR)
    corporate = sorted(
        (e.event_type, e.ticker)
        for e in events
        if e.event_type in (EventType.DIVIDEND, EventType.SPLIT)
    )
    assert corporate == sorted([
        (EventType.DIVIDEND, "MSFT"),
        (EventType.DIVIDEND, "KO"),
        (EventType.SPLIT, "AAPL"),
        (EventType.SPLIT, "GE"),
    ])
    assert not [e for e in events if e.ticker == "ATVI"]
