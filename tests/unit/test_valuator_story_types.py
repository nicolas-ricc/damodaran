"""Unit tests for the story-type classifier (issue #14 / M4.4, spec §7.1).

Spec §7.1 assigns every company one of five life-cycle archetypes —
``high-growth``, ``mature-stable``, ``mature-decline``, ``cyclical``,
``distressed`` — from historical growth, earnings volatility, age, sector and
leverage. :func:`classify` is a pure function over a
:class:`ClassificationFinancials` snapshot and a :class:`SectorContext`, so each
archetype is pinned against representative fixture data with no I/O.

These tests cover every story type and the precedence between the rules
(distressed before everything; cyclical's high-volatility signal; the growth /
decline split for the rest).
"""

from __future__ import annotations

import dataclasses

import pytest

from bot.valuator.story_types import (
    ClassificationFinancials,
    SectorContext,
    StoryType,
    classify,
)


def _financials(**overrides: object) -> ClassificationFinancials:
    """A healthy, middle-aged, low-volatility, modestly-growing company.

    Defaults land on ``mature-stable``; each test perturbs the fields that drive
    a different archetype.
    """
    base: dict[str, object] = dict(
        revenue_history=(1000.0, 1030.0, 1061.0, 1093.0, 1126.0),
        earnings_history=(100.0, 103.0, 106.0, 109.0, 112.0),
        age_years=40,
        debt_to_equity=0.4,
        interest_coverage=8.0,
        altman_z=4.0,
    )
    base.update(overrides)
    return ClassificationFinancials(**base)  # type: ignore[arg-type]


def _sector(**overrides: object) -> SectorContext:
    base: dict[str, object] = dict(is_cyclical=False)
    base.update(overrides)
    return SectorContext(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# distressed                                                                   #
# --------------------------------------------------------------------------- #


def test_distressed_from_low_altman_z() -> None:
    fin = _financials(altman_z=1.0)
    assert classify(fin, _sector()) is StoryType.DISTRESSED


def test_distressed_from_negative_interest_coverage() -> None:
    fin = _financials(interest_coverage=-2.0, altman_z=None)
    assert classify(fin, _sector()) is StoryType.DISTRESSED


def test_distressed_takes_precedence_over_high_growth() -> None:
    """A fast grower that cannot service its debt is still distressed."""
    fin = _financials(
        revenue_history=(100.0, 140.0, 200.0, 280.0, 400.0),
        age_years=3,
        altman_z=1.2,
        interest_coverage=0.5,
        debt_to_equity=5.0,
    )
    assert classify(fin, _sector()) is StoryType.DISTRESSED


# --------------------------------------------------------------------------- #
# cyclical                                                                     #
# --------------------------------------------------------------------------- #


def test_cyclical_from_sector_flag_and_volatile_earnings() -> None:
    fin = _financials(
        earnings_history=(100.0, 20.0, 140.0, 10.0, 160.0),
        revenue_history=(1000.0, 700.0, 1200.0, 650.0, 1300.0),
    )
    assert classify(fin, _sector(is_cyclical=True)) is StoryType.CYCLICAL


def test_cyclical_requires_the_sector_flag() -> None:
    """Volatile earnings alone, without a cyclical sector, are not cyclical."""
    fin = _financials(
        earnings_history=(100.0, 20.0, 140.0, 10.0, 160.0),
        revenue_history=(1000.0, 700.0, 1200.0, 650.0, 1300.0),
    )
    assert classify(fin, _sector(is_cyclical=False)) is not StoryType.CYCLICAL


# --------------------------------------------------------------------------- #
# high-growth                                                                  #
# --------------------------------------------------------------------------- #


def test_high_growth_from_strong_revenue_growth_and_youth() -> None:
    fin = _financials(
        revenue_history=(100.0, 135.0, 180.0, 240.0, 320.0),
        earnings_history=(5.0, 8.0, 14.0, 22.0, 35.0),
        age_years=6,
    )
    assert classify(fin, _sector()) is StoryType.HIGH_GROWTH


def test_old_company_with_fast_growth_is_not_high_growth() -> None:
    """High-growth requires youth as well as growth (spec §7.1 age signal)."""
    fin = _financials(
        revenue_history=(100.0, 135.0, 180.0, 240.0, 320.0),
        earnings_history=(5.0, 8.0, 14.0, 22.0, 35.0),
        age_years=80,
    )
    assert classify(fin, _sector()) is not StoryType.HIGH_GROWTH


# --------------------------------------------------------------------------- #
# mature-stable                                                                #
# --------------------------------------------------------------------------- #


def test_mature_stable_is_the_default_for_steady_companies() -> None:
    assert classify(_financials(), _sector()) is StoryType.MATURE_STABLE


# --------------------------------------------------------------------------- #
# mature-decline                                                               #
# --------------------------------------------------------------------------- #


def test_mature_decline_from_shrinking_revenue() -> None:
    fin = _financials(
        revenue_history=(1300.0, 1230.0, 1150.0, 1080.0, 1000.0),
        earnings_history=(160.0, 150.0, 138.0, 128.0, 118.0),
    )
    assert classify(fin, _sector()) is StoryType.MATURE_DECLINE


# --------------------------------------------------------------------------- #
# missing data                                                                 #
# --------------------------------------------------------------------------- #


def test_too_little_history_falls_back_to_mature_stable() -> None:
    """With < 2 revenue points there is no growth signal — default stable."""
    fin = _financials(revenue_history=(1000.0,), earnings_history=(100.0,))
    assert classify(fin, _sector()) is StoryType.MATURE_STABLE


def test_missing_altman_z_still_distressed_on_coverage() -> None:
    fin = _financials(altman_z=None, interest_coverage=0.2)
    assert classify(fin, _sector()) is StoryType.DISTRESSED


def test_cyclical_falls_through_when_earnings_mean_is_zero() -> None:
    """Zero-mean earnings make the CV undefined, so the cyclical test cannot fire.

    Even in a cyclical sector, undefined volatility falls through to the
    growth-based classification (here: mature-stable defaults).
    """
    fin = _financials(earnings_history=(100.0, -100.0))
    assert classify(fin, _sector(is_cyclical=True)) is not StoryType.CYCLICAL


def test_high_growth_through_negative_revenue_endpoint_is_not_growth() -> None:
    """A non-positive revenue endpoint makes CAGR undefined — default stable."""
    fin = _financials(revenue_history=(100.0, -50.0), earnings_history=(10.0, 5.0))
    assert classify(fin, _sector()) is StoryType.MATURE_STABLE


def test_story_type_values_match_spec_strings() -> None:
    """The enum's string values are exactly the spec §7.1 / override-YAML tokens."""
    assert StoryType.HIGH_GROWTH == "high-growth"
    assert StoryType.MATURE_STABLE == "mature-stable"
    assert StoryType.MATURE_DECLINE == "mature-decline"
    assert StoryType.CYCLICAL == "cyclical"
    assert StoryType.DISTRESSED == "distressed"


def test_classification_inputs_are_immutable() -> None:
    fin = _financials()
    with pytest.raises(dataclasses.FrozenInstanceError):
        fin.age_years = 1  # type: ignore[misc]
