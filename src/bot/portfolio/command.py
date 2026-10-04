"""Orchestrate the ``bot portfolio`` cycle: sync -> diff -> report (M5, #29).

:func:`run_portfolio` ties the existing library functions together — it does
**not** re-implement any of them. It:

1. runs :func:`~bot.portfolio.sync.sync_portfolio` against the read-only IBKR
   client to write today's snapshot (idempotent per day);
2. appends the executions newer than the stored watermark via
   :func:`~bot.portfolio.trades.sync_trades` (de-duped on ``exec_id``);
3. marks each holding (valuation + quality gates) via
   :func:`~bot.portfolio.marks.mark_holdings`, then computes the §8.3 event
   stream against the previous snapshot via
   :func:`~bot.portfolio.events.compute_events` and persists it
   (:func:`~bot.portfolio.events.persist_events`);
4. builds + renders the full-state ``portfolio.md`` and the today-only
   ``alerts.md`` under ``reports/YYYY-MM-DD/`` (the same dated-directory
   convention as the other commands).

``alerts.md`` is always written, but is empty (zero bytes) when there are no
events. Sending ``alerts.md`` is the CLI's job (``bot.notifier``, #32).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from bot.portfolio.events import compute_events, persist_events
from bot.portfolio.marks import mark_holdings
from bot.portfolio.report import build_report, render_alerts, render_portfolio
from bot.portfolio.sync import PortfolioSource, sync_portfolio
from bot.portfolio.trades import TradeSource, sync_trades
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.portfolio.marks import AnalyzeFn
    from bot.screener.rules import Rule

log = get_logger(__name__)


class PortfolioClient(PortfolioSource, TradeSource, Protocol):
    """The read-only IBKR slice a full portfolio run needs: snapshot + fills."""


@dataclass(frozen=True)
class PortfolioRunResult:
    """What a single :func:`run_portfolio` invocation produced."""

    snapshot_date: date
    prev_snapshot_date: date | None
    events: int
    trades_inserted: int
    portfolio_path: Path
    alerts_path: Path


def _previous_snapshot_date(conn: duckdb.DuckDBPyConnection, before: date) -> date | None:
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
    client: PortfolioClient,
    *,
    reports_dir: Path,
    today: date | None = None,
    history: bool = False,
    concentration: bool = False,
    analyze_fn: AnalyzeFn | None = None,
    quality_gates: Sequence[Rule] = (),
    assumptions_dir: Path | None = None,
) -> PortfolioRunResult:
    """Run the full sync -> diff -> report cycle and write both report files.

    Args:
        conn: Open DuckDB connection with the schema applied.
        client: A read-only IBKR client (or any :class:`PortfolioClient`).
        reports_dir: Root reports directory; the dated subdir is created under it.
        today: Calendar day to key the run on; defaults to today.
        history: Include the P&L time series in ``portfolio.md`` (``--history``).
        concentration: Include the concentration breakdown (``--concentration``).
        analyze_fn: Optional valuator override threaded into ``mark_holdings``;
            defaults to the real :func:`bot.valuator.analysis.analyze`.
        quality_gates: Screener rules (quality gates + trap detection) applied
            by ``mark_holdings`` when marking each holding; empty means no gating.
        assumptions_dir: ``config/assumptions`` directory (spec §7.6); the default
            valuator applies a holding's ``<TICKER>.yaml`` as ``bot analyze`` does.

    Returns:
        A :class:`PortfolioRunResult` with the run summary and the two file paths.
    """
    run_day = today if today is not None else date.today()

    # 1. Sync today's snapshot (idempotent per day).
    sync_portfolio(conn, client, snapshot_date=run_day)

    # 2. Append the executions newer than the stored watermark (de-duped).
    trades = sync_trades(conn, client)

    # 3. Mark holdings, then diff against the previous snapshot and persist events.
    prev_date = _previous_snapshot_date(conn, run_day)
    mark_holdings(
        conn,
        run_day,
        analyze_fn=analyze_fn,
        quality_gates=quality_gates,
        assumptions_dir=assumptions_dir,
    )
    events = compute_events(conn, prev_date, run_day)
    persist_events(conn, events)

    # 4. Build + render reports under the dated directory.
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
        trades_inserted=trades.inserted,
        portfolio=str(portfolio_path),
        alerts=str(alerts_path),
    )
    return PortfolioRunResult(
        snapshot_date=run_day,
        prev_snapshot_date=prev_date,
        events=len(events),
        trades_inserted=trades.inserted,
        portfolio_path=portfolio_path,
        alerts_path=alerts_path,
    )
