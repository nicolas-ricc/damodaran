from datetime import date

import duckdb
import pytest

from bot.portfolio.freshness import (
    MAX_SNAPSHOT_AGE_BUSINESS_DAYS,
    business_days_between,
    latest_snapshot_date,
)
from bot.storage.db import apply_schema

# 2026-11-06 is a Friday.
FRI = date(2026, 11, 6)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (FRI, date(2026, 11, 9), 1),  # Friday -> Monday
        (FRI, date(2026, 11, 10), 2),  # Friday -> Tuesday
        (FRI, date(2026, 11, 11), 3),  # Friday -> Wednesday
        (date(2026, 11, 7), date(2026, 11, 8), 0),  # Saturday -> Sunday
        (date(2026, 11, 11), date(2026, 11, 11), 0),  # same day
        (FRI, date(2026, 11, 16), 6),  # two weekends
        (date(2026, 11, 10), date(2026, 11, 9), 0),  # end before start
        (FRI, date(2026, 11, 8), 0),  # Friday -> Sunday
    ],
)
def test_business_days_between(start: date, end: date, expected: int) -> None:
    assert business_days_between(start, end) == expected


def test_max_snapshot_age_is_two() -> None:
    assert MAX_SNAPSHOT_AGE_BUSINESS_DAYS == 2


def test_latest_snapshot_date_empty_table_is_none(conn: duckdb.DuckDBPyConnection) -> None:
    assert latest_snapshot_date(conn) is None


def test_latest_snapshot_date_returns_the_newest(conn: duckdb.DuckDBPyConnection) -> None:
    for day, ticker in [(date(2026, 11, 4), "AAPL"), (FRI, "AAPL"), (FRI, "MSFT")]:
        conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
            "VALUES (?, 'DU1', ?, 1, 10.0, 1000.0, 'USD')",
            [day, ticker],
        )

    result = latest_snapshot_date(conn)

    assert result == FRI
    assert isinstance(result, date)
