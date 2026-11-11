"""Small pure financial-math helpers shared across Capa B and Capa C.

These are deliberately tiny, dependency-free functions so the screener engine
and the valuator can share one definition rather than re-deriving the same
formula inline. Each is a pure function of its arguments.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def cagr(series: Sequence[float]) -> float | None:
    """Compound annual growth rate over ``series`` (most-recent last).

    Only the endpoints matter. Returns ``None`` (never ``0.0``) when the rate is
    undefined: fewer than two points, or a non-positive first or last value. No
    complex result is possible.
    """
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    if first <= 0.0 or last <= 0.0:
        return None
    periods = len(series) - 1
    return float((last / first) ** (1.0 / periods)) - 1.0


def latest_contiguous_run(points: Iterable[tuple[int, float | None]]) -> tuple[float, ...]:
    """Values of the latest run of consecutive fiscal years, oldest first.

    ``points`` are ``(fiscal_year, value)`` pairs, oldest first. A ``None`` value
    or a year that is not the previous year + 1 starts a new run. Returns ``()``
    when no value is present.
    """
    best: list[float] = []
    run: list[float] = []
    prev_year: int | None = None
    for year, value in points:
        if value is None:
            run = []
            prev_year = None
            continue
        if prev_year is None or year != prev_year + 1:
            run = []
        run.append(float(value))
        prev_year = year
        best = run
    return tuple(best)
