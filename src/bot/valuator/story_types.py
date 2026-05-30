"""Auto-classify a company into a Damodaran story type (spec §7.1, issue #14).

Damodaran's life-cycle classification puts every company into one of five
archetypes, each with a distinct projection pattern (spec §7.1)::

    high-growth     fast growth decaying toward the sector, margins improving
    mature-stable   growth ~ GDP nominal, sector-average margins
    mature-decline  controlled negative growth, eroding margins
    cyclical        average through the cycle, not the current year
    distressed      explicit bankruptcy probability, survival-conditional value

The story type drives default assumption resolution: a ``mature-stable`` story
anchors growth on nominal GDP, a ``high-growth`` story ramps down toward the
sector, and so on (see :mod:`bot.valuator.assumptions`).

:func:`classify` is a *pure* function of a :class:`ClassificationFinancials`
snapshot and a :class:`SectorContext` — it reads, it does not write, and it
holds no global state. The signals are exactly those named in spec §7.1:
historical revenue growth, earnings volatility (sigma), company age, sector, and
leverage/solvency. A manual ``story_type`` in ``config/assumptions/<TICKER>.yaml``
overrides this classifier (spec §7.6), wired in
:func:`bot.valuator.assumptions.resolve_assumptions`.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import StrEnum

# --------------------------------------------------------------------------- #
# Classification thresholds (spec §7.1 signals). Tuned for the representative   #
# fixtures; deliberately conservative so the default is the benign             #
# mature-stable archetype rather than an aggressive growth/decline call.       #
# --------------------------------------------------------------------------- #

#: Altman Z below this (when known) marks financial distress (the classic
#: < 1.81 "distress zone").
_DISTRESS_ALTMAN_Z = 1.81

#: Interest coverage (EBIT / interest) at or below this cannot reliably service
#: debt — a distress signal when Altman Z is unavailable or borderline.
_DISTRESS_INTEREST_COVERAGE = 1.0

#: Coefficient of variation of earnings (stdev / |mean|) above which earnings are
#: "volatile" — one half of the cyclical signal (the other is the sector flag).
_CYCLICAL_EARNINGS_CV = 0.50

#: Compound annual revenue growth at/above this is "high growth" (spec §7.1).
_HIGH_GROWTH_CAGR = 0.15

#: Companies older than this are past the high-growth phase regardless of the
#: current growth rate (spec §7.1 age signal).
_MATURE_AGE_YEARS = 25

#: Compound annual revenue growth at/below this (i.e. shrinking) marks decline.
_DECLINE_CAGR = -0.01


class StoryType(StrEnum):
    """Damodaran life-cycle archetype (spec §7.1).

    The string values are the exact tokens used in the spec, in narrative flags,
    and in the ``story_type`` field of ``config/assumptions/<TICKER>.yaml``.
    """

    HIGH_GROWTH = "high-growth"
    MATURE_STABLE = "mature-stable"
    MATURE_DECLINE = "mature-decline"
    CYCLICAL = "cyclical"
    DISTRESSED = "distressed"


@dataclass(frozen=True)
class ClassificationFinancials:
    """The company-level signals the classifier reads (spec §7.1).

    Missing data is ``None`` (scalars) or a short/empty history; the classifier
    degrades gracefully rather than inventing a signal — too little history
    falls back to the benign ``mature-stable`` default.

    Attributes:
        revenue_history: Revenue per fiscal year, oldest first. Drives the
            growth / decline split via compound annual growth.
        earnings_history: Earnings (e.g. net income) per fiscal year, oldest
            first. Drives the earnings-volatility (sigma) cyclical signal.
        age_years: Company age in years; the high-growth archetype requires
            youth as well as growth (``None`` when unknown).
        debt_to_equity: Book debt / equity (a leverage signal, spec §7.1).
        interest_coverage: EBIT / interest expense; low or negative coverage is
            a distress signal (``None`` when unknown).
        altman_z: Altman Z-score; below the distress zone marks ``distressed``
            (``None`` when unknown).
    """

    revenue_history: tuple[float, ...]
    earnings_history: tuple[float, ...]
    age_years: int | None = None
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    altman_z: float | None = None


@dataclass(frozen=True)
class SectorContext:
    """Sector-level signals the classifier reads (spec §7.1).

    Attributes:
        is_cyclical: Whether the company's sector is structurally cyclical
            (e.g. autos, steel, airlines). Cyclical classification needs *both*
            this flag and volatile earnings, so a one-off bad year in a stable
            sector is not mislabelled.
    """

    is_cyclical: bool = False


def _cagr(history: tuple[float, ...]) -> float | None:
    """Compound annual growth rate from the first to the last positive figure.

    Returns ``None`` when there is too little history (< 2 points) or the
    endpoints are non-positive (a CAGR is undefined through zero/negative).
    """
    if len(history) < 2:
        return None
    start, end = history[0], history[-1]
    if start <= 0.0 or end <= 0.0:
        return None
    periods = len(history) - 1
    return float((end / start) ** (1.0 / periods)) - 1.0


def _earnings_cv(history: tuple[float, ...]) -> float | None:
    """Coefficient of variation (stdev / |mean|) of an earnings history.

    Returns ``None`` when there is too little history (< 2 points) or the mean
    is zero (the ratio is undefined).
    """
    if len(history) < 2:
        return None
    mean = statistics.fmean(history)
    if mean == 0.0:
        return None
    return statistics.pstdev(history) / abs(mean)


def _is_distressed(financials: ClassificationFinancials) -> bool:
    """Solvency check: Altman Z in the distress zone or coverage too thin."""
    if financials.altman_z is not None and financials.altman_z < _DISTRESS_ALTMAN_Z:
        return True
    coverage = financials.interest_coverage
    return coverage is not None and coverage <= _DISTRESS_INTEREST_COVERAGE


def _is_cyclical(financials: ClassificationFinancials, sector: SectorContext) -> bool:
    """Cyclical needs *both* a cyclical sector and volatile earnings (§7.1)."""
    if not sector.is_cyclical:
        return False
    cv = _earnings_cv(financials.earnings_history)
    return cv is not None and cv >= _CYCLICAL_EARNINGS_CV


def classify(
    financials: ClassificationFinancials, sector_data: SectorContext
) -> StoryType:
    """Assign a Damodaran story type from §7.1 signals.

    The rules are evaluated in priority order:

    1. **distressed** — Altman Z in the distress zone, or interest coverage at or
       below 1 — wins over everything, even a fast grower that cannot service
       its debt.
    2. **cyclical** — a structurally cyclical sector *and* volatile earnings
       (high coefficient of variation); the current year is not representative.
    3. **high-growth** — high compound revenue growth in a still-young company.
    4. **mature-decline** — shrinking revenue.
    5. **mature-stable** — the default for everything else, including companies
       with too little history to call.

    Args:
        financials: The company-level signals (growth, earnings volatility, age,
            leverage, solvency).
        sector_data: The sector-level signals (currently the cyclical flag).

    Returns:
        The :class:`StoryType` the company is classified into.
    """
    if _is_distressed(financials):
        return StoryType.DISTRESSED
    if _is_cyclical(financials, sector_data):
        return StoryType.CYCLICAL

    cagr = _cagr(financials.revenue_history)
    if cagr is None:
        # No reliable growth signal: fall back to the benign default.
        return StoryType.MATURE_STABLE

    age = financials.age_years
    is_young = age is None or age <= _MATURE_AGE_YEARS
    if cagr >= _HIGH_GROWTH_CAGR and is_young:
        return StoryType.HIGH_GROWTH
    if cagr <= _DECLINE_CAGR:
        return StoryType.MATURE_DECLINE
    return StoryType.MATURE_STABLE
