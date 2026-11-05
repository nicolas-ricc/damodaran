"""Classifier, report reasons and screener read one revenue CAGR (#215)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.screener.engine import _growth_metric
from bot.screener.types import CompanyData
from bot.utils.finance import cagr
from bot.valuator.analysis import _story_reasons
from bot.valuator.story_types import (
    ClassificationFinancials,
    SectorContext,
    StoryType,
    classify,
)


def _company(history: tuple[float, ...]) -> CompanyData:
    return CompanyData(ticker="X", name="X", revenue_history=history)


def _classify(history: tuple[float, ...], age_years: int | None = None) -> StoryType:
    financials = ClassificationFinancials(
        revenue_history=history, earnings_history=(), age_years=age_years
    )
    return classify(financials, SectorContext())


@pytest.mark.parametrize(
    "history",
    [
        pytest.param((100.0, 150.0, 100.0, 150.0), id="sawtooth"),
        pytest.param((100.0, 110.0, 121.0), id="steady"),
    ],
)
def test_one_history_one_number(history: tuple[float, ...]) -> None:
    rate = cagr(history)
    assert rate is not None
    assert _growth_metric(_company(history)) == rate
    reasons = _story_reasons(StoryType.MATURE_STABLE, history, None, overridden=False)
    assert reasons[0] == f"historical revenue CAGR {rate:.1%} over {len(history) - 1} years"
    # Both CAGRs sit below the 15% high-growth bar; the sawtooth's 22.2% mean would not.
    assert _classify(history) is StoryType.MATURE_STABLE


def test_high_growth_threshold_reads_cagr() -> None:
    assert _classify((100.0, 150.0, 100.0, 150.0), age_years=5) is StoryType.MATURE_STABLE
    assert _classify((100.0, 120.0, 140.0, 160.0), age_years=5) is StoryType.HIGH_GROWTH


@pytest.mark.parametrize(
    "history",
    [
        pytest.param((100.0, -50.0, -20.0), id="negative-last"),
        pytest.param((0.0, 10.0), id="zero-first"),
        pytest.param((10.0,), id="one-point"),
    ],
)
def test_undefined_history_is_undefined_everywhere(history: tuple[float, ...]) -> None:
    assert _growth_metric(_company(history)) == 0.0
    reasons = _story_reasons(StoryType.MATURE_STABLE, history, None, overridden=False)
    assert reasons[0] == "too little revenue history for a reliable growth signal"
    assert _classify(history) is StoryType.MATURE_STABLE


def test_hypergrowth_reasons_cite_the_shared_cagr() -> None:
    history = (100.0, 200.0, 400.0)
    rate = cagr(history)
    assert rate is not None
    reasons = _story_reasons(
        StoryType.HYPERGROWTH, history, None, overridden=False, founded_age_years=3
    )
    assert f"revenue CAGR {rate:.1%} over 2 years" in reasons


def test_no_second_revenue_growth_measure_in_src() -> None:
    """``grep -rn "def _cagr\\|fmean(growths" src`` returns nothing."""
    src = Path(__file__).resolve().parents[2] / "src"
    offenders = [
        f"{path}:{n}"
        for path in src.rglob("*.py")
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if "def _cagr" in line or "fmean(growths" in line
    ]
    assert offenders == []
