"""Small pure financial-math helpers shared across Capa B and Capa C.

These are deliberately tiny, dependency-free functions so the screener engine
and the valuator can share one definition rather than re-deriving the same
formula inline. Each is a pure function of its arguments.
"""

from __future__ import annotations


def cagr(series: tuple[float, ...]) -> float:
    """Compound annual growth rate over ``series`` (most-recent last).

    Returns ``0.0`` when there are fewer than two points or the base value is
    non-positive (so a meaningful growth rate cannot be derived).
    """
    if len(series) < 2 or series[0] <= 0.0:
        return 0.0
    periods = len(series) - 1
    rate: float = (series[-1] / series[0]) ** (1.0 / periods) - 1.0
    return rate
