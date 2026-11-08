"""Portfolio snapshot freshness for ``bot doctor``'s portfolio-sync check (#118).

Age is counted in business days (Mon-Fri) so a Friday snapshot is not stale on
Saturday or Sunday. Holidays are not modelled.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb

MAX_SNAPSHOT_AGE_BUSINESS_DAYS = 2


def business_days_between(start: date, end: date) -> int:
    """Count weekdays in ``(start, end]``; 0 when ``end <= start``."""
    if end <= start:
        return 0
    days = (end - start).days
    return sum(1 for i in range(1, days + 1) if (start + timedelta(days=i)).weekday() < 5)


def latest_snapshot_date(conn: duckdb.DuckDBPyConnection) -> date | None:
    """Newest ``snapshot_date`` in ``portfolio_snapshots``, or None when empty."""
    row = conn.execute("SELECT MAX(snapshot_date) FROM portfolio_snapshots").fetchone()
    if row is None or row[0] is None:
        return None
    value: date = row[0]
    return value
