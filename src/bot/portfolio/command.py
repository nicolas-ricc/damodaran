"""Orchestrate the ``bot portfolio`` cycle: sync -> diff -> report (M5, #29).

:func:`run_portfolio` ties the existing library functions together — it does
**not** re-implement any of them. It:

1. runs :func:`~bot.portfolio.sync.sync_portfolio` against the read-only IBKR
   client to write today's snapshot (idempotent per day);
2. computes the §8.3 event stream against the previous snapshot via
   :func:`~bot.portfolio.events.compute_events` and persists it
   (:func:`~bot.portfolio.events.persist_events`);
3. builds + renders the full-state ``portfolio.md`` and the today-only
   ``alerts.md`` under ``reports/YYYY-MM-DD/`` (the same dated-directory
   convention as the other commands).

``alerts.md`` is always written, even with zero events. Sending notifications is
out of scope (#32 owns email/Telegram).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from bot.portfolio.events import compute_events, persist_events
from bot.portfolio.report import build_report, render_alerts, render_portfolio
from bot.portfolio.sync import PortfolioSource, sync_portfolio
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.portfolio.events import _AnalyzeFn

log = get_logger(__name__)


@dataclass(frozen=True)
class PortfolioRunResult:
    """What a single :func:`run_portfolio` invocation produced."""

    snapshot_date: date
    prev_snapshot_date: date | None
    events: int
    portfolio_path: Path
    alerts_path: Path


def _previous_snapshot_date(
    conn: duckdb.DuckDBPyConnection, before: date
) -> date | None:
    """The most recent snapshot strictly before *before*, or ``None``."""
    row = conn.execute(
        "SELECT MAX(snapshot_date) FROM portfolio_snapshots WHERE snapshot_date < ?",
        [before],
    ).fetchone()
    if row is None or row[0] is None:
        return None
    value = row[0]
    return value if isinstance(value, date) else None


def run_portfolio(
    conn: duckdb.DuckDBPyConnection,
    client: PortfolioSource,
    *,
    reports_dir: Path,
    today: date | None = None,
    history: bool = False,
    concentration: bool = False,
    analyze_fn: _AnalyzeFn | None = None,
) -> PortfolioRunResult:
    """Run the full sync -> diff -> report cycle and write both report files.

    Args:
        conn: Open DuckDB connection with the schema applied.
        client: A read-only IBKR client (or any :class:`PortfolioSource`).
        reports_dir: Root reports directory; the dated subdir is created under it.
        today: Calendar day to key the run on; defaults to today.
        history: Include the P&L time series in ``portfolio.md`` (``--history``).
        concentration: Include the concentration breakdown (``--concentration``).
        analyze_fn: Optional valuator override threaded into ``compute_events``;
            defaults to the real :func:`bot.valuator.analysis.analyze`.

    Returns:
        A :class:`PortfolioRunResult` with the run summary and the two file paths.
    """
    run_day = today if today is not None else date.today()

    # 1. Sync today's snapshot (idempotent per day).
    sync_portfolio(conn, client, snapshot_date=run_day)

    # 2. Diff against the previous snapshot and persist the event stream.
    prev_date = _previous_snapshot_date(conn, run_day)
    events = compute_events(conn, prev_date, run_day, analyze_fn=analyze_fn)
    persist_events(conn, events)

    # 3. Build + render reports under the dated directory.
    report = build_report(
        conn,
        run_day,
        include_history=history,
        include_concentration=concentration,
    )
    portfolio_md = render_portfolio(report, generated_on=run_day)
    alerts_md = render_alerts(events, run_day, generated_on=run_day)

    out_dir = reports_dir / run_day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    portfolio_path = out_dir / "portfolio.md"
    alerts_path = out_dir / "alerts.md"
    portfolio_path.write_text(portfolio_md)
    alerts_path.write_text(alerts_md)

    log.info(
        "portfolio_report_written",
        snapshot_date=run_day.isoformat(),
        prev_snapshot_date=prev_date.isoformat() if prev_date else None,
        events=len(events),
        portfolio=str(portfolio_path),
        alerts=str(alerts_path),
    )
    return PortfolioRunResult(
        snapshot_date=run_day,
        prev_snapshot_date=prev_date,
        events=len(events),
        portfolio_path=portfolio_path,
        alerts_path=alerts_path,
    )
