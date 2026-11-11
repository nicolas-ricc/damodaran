"""Orchestrate the ``bot portfolio`` cycle: sync -> diff -> report (M5, #29).

:func:`run_portfolio` ties the existing library functions together — it does
**not** re-implement any of them. It:

1. reads the snapshot date from the client (``client.as_of()``, the Flex
   statement date; a statement older than :data:`STALE_AFTER_DAYS` days logs a
   WARNING) and runs :func:`~bot.portfolio.sync.sync_portfolio` to write that
   day's snapshot (idempotent per day);
2. upserts the statement's corporate actions
   (:func:`~bot.ingest.ibkr_flex.upsert_corporate_actions`);
3. appends the executions newer than the stored watermark via
   :func:`~bot.portfolio.trades.sync_trades` (de-duped on ``exec_id``);
4. marks each holding (valuation + quality gates) via
   :func:`~bot.portfolio.marks.mark_holdings`, then computes the §8.3 event
   stream against the previous snapshot via
   :func:`~bot.portfolio.events.compute_events` and persists it
   idempotently (:func:`~bot.portfolio.events.persist_events` skips the events
   already logged for the day, so a same-day re-run adds only new ones);
5. builds + renders the full-state ``portfolio.md`` and the today-only
   ``alerts.md`` under ``reports/YYYY-MM-DD/`` (the same dated-directory
   convention as the other commands). ``alerts.md`` lists the day's logged
   events (:func:`~bot.portfolio.events.load_events`), not only those just
   computed.

``alerts.md`` is always written, but is empty (zero bytes) when there are no
events. Sending ``alerts.md`` is the CLI's job (``bot.notifier``, #32).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from bot.ingest.ibkr_flex import CorporateActionRecord, upsert_corporate_actions
from bot.portfolio.events import compute_events, load_events, persist_events
from bot.portfolio.marks import mark_holdings
from bot.portfolio.report import build_report, render_alerts, render_portfolio
from bot.portfolio.sync import PortfolioSource, sync_portfolio
from bot.portfolio.trades import TradeSource, sync_trades
from bot.reference.currencies import CurrencyTable
from bot.reference.default_spreads import DefaultSpreadTable
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.portfolio.marks import AnalyzeFn
    from bot.screener.rules import Rule

log = get_logger(__name__)

STALE_AFTER_DAYS = 5


class PortfolioClient(PortfolioSource, TradeSource, Protocol):
    """The slice a full portfolio run needs: snapshot, fills, statement date, actions."""

    def as_of(self) -> date:
        """The statement date the snapshot is keyed on."""
        ...

    def corporate_actions(self) -> list[CorporateActionRecord]:
        """The corporate actions carried by the same statement."""
        ...


@dataclass(frozen=True)
class PortfolioRunResult:
    """What a single :func:`run_portfolio` invocation produced."""

    snapshot_date: date
    prev_snapshot_date: date | None
    events: int  # the day's logged events, as listed in alerts.md
    trades_inserted: int
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
    client: PortfolioClient,
    *,
    reports_dir: Path,
    today: date | None = None,
    history: bool = False,
    concentration: bool = False,
    analyze_fn: AnalyzeFn | None = None,
    quality_gates: Sequence[Rule] = (),
    assumptions_dir: Path | None = None,
    currencies: CurrencyTable | None = None,
    default_spreads: DefaultSpreadTable | None = None,
) -> PortfolioRunResult:
    """Run the full sync -> diff -> report cycle and write both report files.

    Args:
        conn: Open DuckDB connection with the schema applied.
        client: A read-only IBKR client (or any :class:`PortfolioClient`).
        reports_dir: Root reports directory; the dated subdir is created under it.
        today: The run day (staleness check and report header); defaults to today.
            The snapshot is keyed on ``client.as_of()``, not on this.
        history: Include the P&L time series in ``portfolio.md`` (``--history``).
        concentration: Include the concentration breakdown (``--concentration``).
        analyze_fn: Optional valuator override threaded into ``mark_holdings``;
            defaults to the real :func:`bot.valuator.analysis.analyze`.
        quality_gates: Screener rules (quality gates + trap detection) applied
            by ``mark_holdings`` when marking each holding; empty means no gating.
        assumptions_dir: ``config/assumptions`` directory (spec §7.6); the default
            valuator applies a holding's ``<TICKER>.yaml`` as ``bot analyze`` does.
        currencies: Per-currency rate table threaded to ``mark_holdings``; ``None``
            loads the default file.
        default_spreads: Default-spread table threaded to ``mark_holdings``; ``None``
            lets the default valuator load it lazily. Ignored with an injected
            ``analyze_fn`` (it owns its own table).

    Returns:
        A :class:`PortfolioRunResult` with the run summary and the two file paths.
    """
    run_day = today if today is not None else date.today()

    # 1. Sync the statement-date snapshot (idempotent per date).
    snapshot_date = client.as_of()
    age = (run_day - snapshot_date).days
    if age > STALE_AFTER_DAYS:
        log.warning(
            "portfolio_statement_stale",
            as_of=snapshot_date.isoformat(),
            today=run_day.isoformat(),
            days=age,
        )
    sync_portfolio(conn, client, snapshot_date=snapshot_date)

    # 2. Corporate actions carried by the same statement.
    upsert_corporate_actions(conn, client.corporate_actions())

    # 3. Append the executions newer than the stored watermark (de-duped).
    trades = sync_trades(conn, client)

    # 4. Mark holdings, then diff against the previous snapshot and persist events.
    prev_date = _previous_snapshot_date(conn, snapshot_date)
    mark_holdings(
        conn,
        snapshot_date,
        analyze_fn=analyze_fn,
        quality_gates=quality_gates,
        assumptions_dir=assumptions_dir,
        currencies=currencies,
        default_spreads=default_spreads,
    )
    events = compute_events(conn, prev_date, snapshot_date)
    logged = persist_events(conn, events)
    day_events = load_events(conn, snapshot_date)

    # 5. Build + render reports under the dated directory.
    report = build_report(
        conn,
        snapshot_date,
        include_history=history,
        include_concentration=concentration,
    )
    portfolio_md = render_portfolio(report, generated_on=run_day)
    alerts_md = render_alerts(day_events, snapshot_date, generated_on=run_day)

    out_dir = reports_dir / snapshot_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    portfolio_path = out_dir / "portfolio.md"
    alerts_path = out_dir / "alerts.md"
    portfolio_path.write_text(portfolio_md)
    alerts_path.write_text(alerts_md)

    log.info(
        "portfolio_report_written",
        snapshot_date=snapshot_date.isoformat(),
        prev_snapshot_date=prev_date.isoformat() if prev_date else None,
        events=len(day_events),
        events_logged=logged,
        trades_inserted=trades.inserted,
        portfolio=str(portfolio_path),
        alerts=str(alerts_path),
    )
    return PortfolioRunResult(
        snapshot_date=snapshot_date,
        prev_snapshot_date=prev_date,
        events=len(day_events),
        trades_inserted=trades.inserted,
        portfolio_path=portfolio_path,
        alerts_path=alerts_path,
    )
