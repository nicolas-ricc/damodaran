"""Currency normalization — daily FX rates against USD and USD conversion (M2.5).

Per the design spec (§4.3), every financial figure is converted to USD using the
FX rate at the fiscal period-end. Damodaran datasets are already in USD, so they
need no conversion.

Storage: the ``currencies`` table (see ``schema.sql``) holds one row per
``(currency, date)`` with ``rate_to_usd`` — the multiplier turning one unit of
``currency`` into USD::

    usd_amount = amount_in_currency * rate_to_usd

USD is the numeraire: ``get_fx_rate(conn, "USD", ...)`` is always ``1.0`` and no
row is ever stored for it.

Lookups use a *nearest-prior* strategy: a period-end that falls on a weekend or
holiday resolves to the most recent earlier trading day. We never look forward,
so a conversion only ever uses information available on or before the as-of date.

Source of FX data: FMP historical forex prices (pair ``{CURRENCY}USD``, daily
close), via :meth:`bot.ingest.fmp.FmpClient.historical_fx`. FMP is already a
project dependency (international fundamentals + EOD prices), so reusing it keeps
the data pipeline and auth in one place. If FMP's forex coverage proves too
slow/expensive, the ``import_fx_rates`` entry point can be repointed at ECB or
openexchangerates.org without touching the lookup/conversion helpers, which only
read from the ``currencies`` table.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import duckdb

from bot.ingest.base import IngestResult, refresh_run, transaction
from bot.ingest.fmp import FmpClient
from bot.utils.logging import get_logger

log = get_logger(__name__)

USD = "USD"


def upsert_fx_rates(
    conn: duckdb.DuckDBPyConnection,
    *,
    currency: str,
    rows: list[dict[str, Any]],
    source: str = "fmp",
) -> int:
    """Insert/replace daily FX rows for ``currency``. Returns the row count.

    Each row needs ``date`` (ISO string or ``datetime.date``) and ``rate_to_usd``.
    Replaces on the ``(currency, date)`` primary key so re-running is idempotent.
    Assumes it is called inside (or as) a single logical write.
    """
    if not rows:
        return 0
    ccy = currency.upper()
    for r in rows:
        d = r["date"]
        d_iso = d.isoformat() if isinstance(d, date) else str(d)[:10]
        rate = float(r["rate_to_usd"])
        conn.execute(
            "DELETE FROM currencies WHERE currency = ? AND date = ?",
            [ccy, d_iso],
        )
        conn.execute(
            "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES (?, ?, ?, ?)",
            [ccy, d_iso, rate, source],
        )
    return len(rows)


def get_fx_rate(
    conn: duckdb.DuckDBPyConnection,
    currency: str,
    as_of: date,
) -> float | None:
    """Return the ``currency``->USD rate at ``as_of`` using nearest-prior lookup.

    Returns ``1.0`` for USD (the numeraire). Returns ``None`` when ``currency`` is
    unknown or has no observation on or before ``as_of`` (never looks forward).
    """
    ccy = currency.upper()
    if ccy == USD:
        return 1.0
    row = conn.execute(
        """
        SELECT rate_to_usd
        FROM currencies
        WHERE currency = ? AND date <= ?
        ORDER BY date DESC
        LIMIT 1
        """,
        [ccy, as_of.isoformat()],
    ).fetchone()
    if row is None:
        return None
    return float(row[0])


def to_usd(
    conn: duckdb.DuckDBPyConnection,
    amount: float | None,
    currency: str,
    as_of: date,
) -> float | None:
    """Convert ``amount`` in ``currency`` to USD using the FX rate at ``as_of``.

    Passes ``None`` straight through (missing figures stay missing). Raises
    :class:`LookupError` if no FX rate is available for a non-USD currency so
    callers never silently treat a foreign figure as if it were USD.
    """
    if amount is None:
        return None
    rate = get_fx_rate(conn, currency, as_of)
    if rate is None:
        raise LookupError(f"No FX rate for {currency.upper()} on or before {as_of.isoformat()}")
    return amount * rate


def import_fx_rates(
    conn: duckdb.DuckDBPyConnection,
    *,
    api_key: str,
    currency: str,
    start: date | None = None,
    end: date | None = None,
    client: FmpClient | None = None,
) -> IngestResult:
    """Fetch daily ``currency``/USD rates from FMP and upsert them. Atomic on DB.

    Records the run in ``refresh_log``. USD is a no-op (it needs no rows).

    Pass ``client`` to reuse an open :class:`FmpClient` across many currencies
    (the bulk FX refresh shares one for the whole run); otherwise one is opened
    and closed for this call alone.
    """
    ccy = currency.upper()
    with refresh_run(
        conn,
        source="fmp_fx",
        log=log,
        error_event="fmp_fx.import.failed",
        log_fail_event="fmp_fx.refresh_log_insert_failed",
    ) as run:
        run.details = {"currency": ccy}

        fmp = client if client is not None else FmpClient(api_key=api_key)
        try:
            rows = fmp.historical_fx(ccy, start=start, end=end)
        finally:
            if client is None:
                fmp.close()

        with transaction(conn):
            affected = upsert_fx_rates(conn, currency=ccy, rows=rows)

        run.rows_affected = affected
        run.details = {"currency": ccy}
    assert run.result is not None  # refresh_run always sets it on exit
    return run.result
