"""Per-snapshot valuation facts for held tickers (spec §8.3, #28).

The derived portfolio events (IV crossing price, a newly red flag, a quality
gate failing, a sector WACC recalibration) are diffs between two snapshots, so
each snapshot persists a :class:`HoldingMark` per held ticker and the baseline
is always read back from ``holding_marks`` rather than recomputed.

``None`` fields mean "unknown", never "clean": ``red_flags=None`` is a ticker
that could not be valued, ``failed_gates=None`` one the gates could not be
evaluated for. Detectors must not read either as an all-clear.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Protocol

import duckdb

from bot.ingest.base import transaction
from bot.screener.engine import load_holding_inputs
from bot.screener.rules import Rule
from bot.screener.types import IndustryBenchmarks
from bot.utils.logging import get_logger
from bot.valuator.narrative_flags import FlagColor

if TYPE_CHECKING:
    from bot.valuator.analysis import Analysis

log = get_logger(__name__)


@dataclass(frozen=True)
class HoldingMark:
    ticker: str
    intrinsic_value: float | None = None
    price: float | None = None
    red_flags: dict[str, str] | None = None  # flag name -> reason; None = not valued
    failed_gates: tuple[str, ...] | None = None  # None = gates not evaluable
    sector_wacc: float | None = None


class AnalyzeFn(Protocol):
    def __call__(self, ticker: str, conn: duckdb.DuckDBPyConnection) -> Analysis: ...


def persist_marks(
    conn: duckdb.DuckDBPyConnection, snapshot_date: date, marks: list[HoldingMark]
) -> int:
    """Replace the marks of ``snapshot_date``; returns the rows written."""
    rows = [
        [
            snapshot_date,
            m.ticker,
            m.intrinsic_value,
            m.price,
            None if m.red_flags is None else json.dumps(m.red_flags),
            None if m.failed_gates is None else list(m.failed_gates),
            m.sector_wacc,
        ]
        for m in marks
    ]
    with transaction(conn):
        conn.execute("DELETE FROM holding_marks WHERE snapshot_date = ?", [snapshot_date])
        if rows:
            conn.executemany(
                "INSERT INTO holding_marks (snapshot_date, ticker, intrinsic_value, price, "
                "red_flags, failed_gates, sector_wacc) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
    return len(rows)


def load_marks(conn: duckdb.DuckDBPyConnection, snapshot_date: date) -> dict[str, HoldingMark]:
    rows = conn.execute(
        "SELECT ticker, intrinsic_value, price, red_flags, failed_gates, sector_wacc "
        "FROM holding_marks WHERE snapshot_date = ?",
        [snapshot_date],
    ).fetchall()
    return {
        r[0]: HoldingMark(
            ticker=r[0],
            intrinsic_value=r[1],
            price=r[2],
            red_flags=None if r[3] is None else dict(json.loads(r[3])),
            failed_gates=None if r[4] is None else tuple(r[4]),
            sector_wacc=r[5],
        )
        for r in rows
    }


def _held_tickers(conn: duckdb.DuckDBPyConnection, snapshot_date: date) -> list[str]:
    rows = conn.execute(
        "SELECT UPPER(ticker) FROM portfolio_snapshots WHERE snapshot_date = ? "
        "GROUP BY UPPER(ticker) HAVING SUM(qty) <> 0 ORDER BY 1",
        [snapshot_date],
    ).fetchall()
    return [r[0] for r in rows]


def mark_holdings(
    conn: duckdb.DuckDBPyConnection,
    snapshot_date: date,
    *,
    analyze_fn: AnalyzeFn | None = None,
    quality_gates: Sequence[Rule] = (),
) -> list[HoldingMark]:
    """Value and gate every ticker held on ``snapshot_date``, and persist the marks."""
    if analyze_fn is None:
        from bot.valuator.analysis import analyze as _analyze

        def analyze_fn_default(ticker: str, conn: duckdb.DuckDBPyConnection) -> Analysis:
            return _analyze(ticker, conn)

        analyze_fn = analyze_fn_default

    tickers = _held_tickers(conn, snapshot_date)
    inputs = load_holding_inputs(conn, tickers)
    marks: list[HoldingMark] = []
    for ticker in tickers:
        intrinsic_value: float | None = None
        price: float | None = None
        red_flags: dict[str, str] | None = None
        try:
            analysis = analyze_fn(ticker, conn)
        except (LookupError, ValueError) as exc:
            log.debug("marks.analyze_skipped", ticker=ticker, error=str(exc))
        else:
            intrinsic_value = analysis.dcf_result.intrinsic_value
            price = analysis.current_price
            red_flags = {
                f.name: f.reason for f in analysis.narrative_flags if f.color is FlagColor.RED
            }

        failed_gates: tuple[str, ...] | None = None
        sector_wacc: float | None = None
        if ticker in inputs:
            company, benchmarks = inputs[ticker]
            sector_wacc = benchmarks.wacc if benchmarks else None
            bench = benchmarks or IndustryBenchmarks(industry="", region="", year=0)
            failed_gates = tuple(
                g.name
                for g in quality_gates
                if not (r := g.evaluate(company, bench)).passed and not r.skipped
            )
        marks.append(
            HoldingMark(
                ticker=ticker,
                intrinsic_value=intrinsic_value,
                price=price,
                red_flags=red_flags,
                failed_gates=failed_gates,
                sector_wacc=sector_wacc,
            )
        )
    persist_marks(conn, snapshot_date, marks)
    return marks
