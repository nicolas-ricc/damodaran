"""Small pure financial-math helpers shared across Capa B and Capa C.

These are deliberately tiny, dependency-free functions so the screener engine
and the valuator can share one definition rather than re-deriving the same
formula inline. Each is a pure function of its arguments.
"""

from __future__ import annotations

from collections.abc import Sequence


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
