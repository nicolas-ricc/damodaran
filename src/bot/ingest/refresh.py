"""Bulk universe refresh: incremental FMP ingest over a ticker list."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import duckdb

from bot.ingest.fmp import FmpClient, import_company_from_fmp
from bot.utils.logging import get_logger

log = get_logger(__name__)

PROGRESS_INTERVAL = 50

RefreshStatus = Literal["success", "partial", "error"]


@dataclass
class RefreshStats:
    total: int = 0
    imported: int = 0
    skipped: int = 0
    errors: int = 0
    failed_tickers: list[str] = field(default_factory=list)

    @property
    def fail_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.errors / self.total

    @property
    def status(self) -> RefreshStatus:
        rate = self.fail_rate
        if rate < 0.05:
            return "success"
        if rate <= 0.25:
            return "partial"
        return "error"


def _get_known_filing_date(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(filing_date)
        FROM filings_log
        WHERE ticker = ? AND filing_type = 'annual-fmp' AND source = 'fmp'
        """,
        [ticker],
    ).fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _should_skip(
    conn: duckdb.DuckDBPyConnection, ticker: str, *, api_key: str
) -> bool:
    """Return True if FMP's latest annual filling date matches what's already in filings_log."""
    known = _get_known_filing_date(conn, ticker)
    if known is None:
        return False
    with FmpClient(api_key=api_key) as client:
        rows = client.fetch_income_statement(ticker, period="annual", limit=1)
    if not rows:
        return False
    fmp_latest = str(rows[0].get("fillingDate") or rows[0].get("date") or "")
    return bool(fmp_latest and fmp_latest <= known)


def _record_filing_dates(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> None:
    """Record each imported period_end_date into filings_log for future skip checks."""
    rows = conn.execute(
        "SELECT period_end_date FROM financials_annual WHERE ticker = ? AND period_end_date IS NOT NULL",
        [ticker],
    ).fetchall()
    for (d,) in rows:
        if d:
            conn.execute(
                "DELETE FROM filings_log WHERE ticker = ? AND filing_type = 'annual-fmp' AND filing_date = ? AND source = 'fmp'",
                [ticker, str(d)],
            )
            conn.execute(
                "INSERT INTO filings_log (ticker, filing_type, filing_date, source) VALUES (?, 'annual-fmp', ?, 'fmp')",
                [ticker, str(d)],
            )


def refresh_universe(
    conn: duckdb.DuckDBPyConnection,
    tickers: list[str],
    *,
    api_key: str,
) -> RefreshStats:
    """Import / refresh *tickers* from FMP, skipping tickers with unchanged filings.

    Logs progress every PROGRESS_INTERVAL tickers.
    Per-ticker failures are caught and recorded; the run always continues.
    Writes one refresh_log row at the end with aggregate status.
    """
    stats = RefreshStats(total=len(tickers))
    run_id = str(uuid.uuid4())
    started = datetime.utcnow()

    for i, ticker in enumerate(tickers):
        if i > 0 and i % PROGRESS_INTERVAL == 0:
            log.info(
                "refresh.progress",
                processed=i,
                total=stats.total,
                imported=stats.imported,
                skipped=stats.skipped,
                errors=stats.errors,
            )

        try:
            if _should_skip(conn, ticker, api_key=api_key):
                log.debug("refresh.ticker.skipped", ticker=ticker)
                stats.skipped += 1
                continue

            result = import_company_from_fmp(conn, ticker, api_key=api_key)
            if result.status == "success":
                _record_filing_dates(conn, ticker)
                stats.imported += 1
                log.debug("refresh.ticker.imported", ticker=ticker)
            else:
                stats.errors += 1
                stats.failed_tickers.append(ticker)
                log.warning(
                    "refresh.ticker.failed",
                    ticker=ticker,
                    status=result.status,
                    error=result.error_message,
                )

        except Exception as e:
            log.error("refresh.ticker.error", ticker=ticker, error=str(e))
            stats.errors += 1
            stats.failed_tickers.append(ticker)

    log.info(
        "refresh.complete",
        total=stats.total,
        imported=stats.imported,
        skipped=stats.skipped,
        errors=stats.errors,
        status=stats.status,
    )

    finished = datetime.utcnow()
    error_msg: str | None = (
        ", ".join(stats.failed_tickers) if stats.failed_tickers else None
    )
    conn.execute(
        """
        INSERT INTO refresh_log
            (source, run_id, started_at, finished_at, status, rows_affected, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "fmp_refresh",
            run_id,
            started,
            finished,
            stats.status,
            stats.imported,
            error_msg,
        ],
    )

    return stats
