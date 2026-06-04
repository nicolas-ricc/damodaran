"""Shared sector-benchmark lookup for value-indicator rules (spec §6.3).

Value indicators compare a company against its sector's Damodaran medians
(``damodaran_industry``). This module is the single place that resolves a
company's ``(industry, region[, year])`` to an :class:`IndustryBenchmarks`
snapshot, so every rule looks its benchmark up the same way and missing-data
handling lives in one spot.

The loader degrades gracefully: an unknown industry (or a company with no
industry label at all) yields ``None`` rather than raising, letting the caller
*skip* the dependent rule instead of crashing the screen (issue #5 acceptance
criterion). Individual medians inside a returned row may still be ``NULL`` —
that is the rule's concern (it skips itself), not the loader's.
"""

from __future__ import annotations

import duckdb

from bot.screener.types import IndustryBenchmarks

# Numeric median columns of damodaran_industry surfaced on IndustryBenchmarks,
# in the order selected below. Kept explicit (not SELECT *) so a schema change
# can never silently shift positional unpacking.
_BENCHMARK_COLUMNS: tuple[str, ...] = (
    "wacc",
    "roic",
    "roe",
    "pe",
    "pbv",
    "ev_ebitda",
    "op_margin",
    "net_margin",
)


def load_industry_benchmarks(
    conn: duckdb.DuckDBPyConnection,
    *,
    industry: str | None,
    region: str,
    year: int | None = None,
) -> IndustryBenchmarks | None:
    """Load Damodaran medians for ``(industry, region)`` from the DB.

    Args:
        conn: Open DuckDB connection (schema already applied).
        industry: Damodaran industry label; ``None`` (company has no industry
            mapped) yields ``None`` without touching the DB.
        region: Damodaran region (e.g. ``"US"``).
        year: Dataset year. When ``None``, the most recent available year for
            ``(industry, region)`` is used.

    Returns:
        An :class:`IndustryBenchmarks` for the matched row, or ``None`` if no
        row exists for that industry/region (so the caller can skip the rule).
    """
    if industry is None:
        return None

    select_cols = ", ".join(_BENCHMARK_COLUMNS)
    if year is None:
        row = conn.execute(
            f"SELECT year, {select_cols} FROM damodaran_industry "
            "WHERE industry = ? AND region = ? "
            "ORDER BY year DESC LIMIT 1",
            [industry, region],
        ).fetchone()
    else:
        row = conn.execute(
            f"SELECT year, {select_cols} FROM damodaran_industry "
            "WHERE industry = ? AND region = ? AND year = ?",
            [industry, region, year],
        ).fetchone()

    if row is None:
        return None

    resolved_year, *medians = row
    values = dict(zip(_BENCHMARK_COLUMNS, medians, strict=True))
    return IndustryBenchmarks(
        industry=industry,
        region=region,
        year=resolved_year,
        **values,
    )
