"""Persist a screen run's shortlist to ``screener_candidates`` (spec §6, §4.3).

One screen run writes one batch of rows keyed by ``run_id``: the ranked
survivors, each with its rank, composite score, the four §6.5 sub-scores, and the
serialised rule names it cleared / tripped. The table keeps history across runs
(``PRIMARY KEY (run_id, ticker)``), so a later report can diff one screen against
another.

The writer is pure-at-the-edges: it accepts an open connection and the already
computed :class:`~bot.screener.engine.ScreenResult`, and only writes — generating
the ``run_id`` (a UUID) is its sole side effect beyond the INSERTs.
"""

from __future__ import annotations

from uuid import uuid4

import duckdb

from bot.screener.engine import ScreenResult


def persist_candidates(
    conn: duckdb.DuckDBPyConnection,
    result: ScreenResult,
    *,
    run_id: str | None = None,
) -> str:
    """Write ``result``'s shortlist to ``screener_candidates`` under a run id.

    Args:
        conn: Open DuckDB connection with the schema applied.
        result: The ranked shortlist to persist (rank order is its list order).
        run_id: Explicit run identifier; a fresh UUID is generated when omitted.

    Returns:
        The ``run_id`` the rows were written under.
    """
    rid = run_id if run_id is not None else uuid4().hex
    for rank_index, company in enumerate(result.shortlist, start=1):
        conn.execute(
            "INSERT INTO screener_candidates "
            "(run_id, preset, ticker, rank, score, value_score, quality_score, "
            "growth_score, mos_score, passed_gates, failed_gates) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                rid,
                result.preset,
                company.ticker,
                rank_index,
                company.score,
                company.value_score,
                company.quality_score,
                company.growth_score,
                company.margin_of_safety,
                list(company.passed_gates),
                list(company.failed_gates),
            ],
        )
    return rid
