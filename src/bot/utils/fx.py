"""FX rate lookups and USD conversion helpers.

Uses the `currencies` table populated by `bot.ingest.fx`.
"""

from __future__ import annotations

from datetime import date

import duckdb


def get_fx_rate(
    conn: duckdb.DuckDBPyConnection,
    currency: str,
    as_of: date,
) -> float | None:
    """Return rate_to_usd for `currency` on `as_of`, using nearest-prior lookup.

    Finds the most recent rate on or before `as_of`.  Returns None if no rate
    exists at or before that date.  USD always returns 1.0 without a DB hit.
    """
    if currency.upper() == "USD":
        return 1.0
    row = conn.execute(
        """
        SELECT rate_to_usd
        FROM currencies
        WHERE currency = ? AND date <= ?
        ORDER BY date DESC
        LIMIT 1
        """,
        [currency.upper(), as_of.isoformat()],
    ).fetchone()
    if row is None:
        return None
    result: float = row[0]
    return result


def to_usd(
    conn: duckdb.DuckDBPyConnection,
    amount: float,
    currency: str,
    as_of: date,
) -> float | None:
    """Convert `amount` from `currency` to USD as of `as_of`.

    Returns None if no FX rate is available on or before `as_of`.
    """
    rate = get_fx_rate(conn, currency, as_of)
    if rate is None:
        return None
    return amount * rate
