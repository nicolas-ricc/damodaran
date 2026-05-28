"""Unit tests for the M3.6 ranking module.

Hand-computed expected scores for a 3-candidate fixture universe:

    Candidates (value_raw, quality_raw, growth_raw):
        A = (0.1, 0.9, 0.5)
        B = (0.5, 0.5, 0.9)
        C = (0.9, 0.1, 0.1)

    Percentile ranks (ordinal, 0-indexed, divided by N-1 = 2):
        value:   A=0/2=0.00, B=1/2=0.50, C=2/2=1.00
        quality: A=2/2=1.00, B=1/2=0.50, C=0/2=0.00
        growth:  A=1/2=0.50, B=2/2=1.00, C=0/2=0.00

    Composite (0.40v + 0.30q + 0.20g + 0.10*0.5):
        A: 0.40*0.00 + 0.30*1.00 + 0.20*0.50 + 0.05 = 0.45
        B: 0.40*0.50 + 0.30*0.50 + 0.20*1.00 + 0.05 = 0.60
        C: 0.40*1.00 + 0.30*0.00 + 0.20*0.00 + 0.05 = 0.45

    Sorted descending: B (0.60), A (0.45), C (0.45) — tie broken by stable sort.
"""

import pytest

from bot.screener.ranking import Candidate, RankingWeights, ScoredCandidate, rank

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

A = Candidate(ticker="A", value_raw=0.1, quality_raw=0.9, growth_raw=0.5)
B = Candidate(ticker="B", value_raw=0.5, quality_raw=0.5, growth_raw=0.9)
C = Candidate(ticker="C", value_raw=0.9, quality_raw=0.1, growth_raw=0.1)


# ---------------------------------------------------------------------------
# 3-candidate fixture — main percentile / composite verification
# ---------------------------------------------------------------------------


def test_rank_order_three_candidates() -> None:
    result = rank([A, B, C])
    assert [s.ticker for s in result] == ["B", "A", "C"]


def test_rank_composite_b() -> None:
    result = rank([A, B, C])
    b = next(s for s in result if s.ticker == "B")
    assert b.value_score == pytest.approx(0.5)
    assert b.quality_score == pytest.approx(0.5)
    assert b.growth_score == pytest.approx(1.0)
    assert b.margin_of_safety == pytest.approx(0.5)
    assert b.composite_score == pytest.approx(0.60)


def test_rank_composite_a() -> None:
    result = rank([A, B, C])
    a = next(s for s in result if s.ticker == "A")
    assert a.value_score == pytest.approx(0.0)
    assert a.quality_score == pytest.approx(1.0)
    assert a.growth_score == pytest.approx(0.5)
    assert a.composite_score == pytest.approx(0.45)


def test_rank_composite_c() -> None:
    result = rank([A, B, C])
    c = next(s for s in result if s.ticker == "C")
    assert c.value_score == pytest.approx(1.0)
    assert c.quality_score == pytest.approx(0.0)
    assert c.growth_score == pytest.approx(0.0)
    assert c.composite_score == pytest.approx(0.45)


def test_rank_returns_scored_candidate_instances() -> None:
    result = rank([A, B, C])
    assert all(isinstance(s, ScoredCandidate) for s in result)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_rank_empty_returns_empty() -> None:
    assert rank([]) == []


def test_rank_single_candidate_all_percentiles_half() -> None:
    """Single element — no relative comparison, percentiles default to 0.5."""
    solo = Candidate(ticker="S", value_raw=0.3, quality_raw=0.7, growth_raw=0.9)
    (result,) = rank([solo])
    assert result.ticker == "S"
    assert result.value_score == pytest.approx(0.5)
    assert result.quality_score == pytest.approx(0.5)
    assert result.growth_score == pytest.approx(0.5)
    assert result.margin_of_safety == pytest.approx(0.5)
    # composite = 0.40*0.5 + 0.30*0.5 + 0.20*0.5 + 0.10*0.5 = 0.50
    assert result.composite_score == pytest.approx(0.50)


def test_rank_two_candidates() -> None:
    """
    X = (value=0.3, quality=0.7, growth=0.4), Y = (value=0.8, quality=0.2, growth=0.9)
    N=2: percentile is 0.0 or 1.0.
        value:   X=0.0, Y=1.0
        quality: X=1.0, Y=0.0
        growth:  X=0.0, Y=1.0
    composite:
        X: 0.40*0.0 + 0.30*1.0 + 0.20*0.0 + 0.10*0.5 = 0.35
        Y: 0.40*1.0 + 0.30*0.0 + 0.20*1.0 + 0.10*0.5 = 0.65
    """
    cand_x = Candidate(ticker="X", value_raw=0.3, quality_raw=0.7, growth_raw=0.4)
    cand_y = Candidate(ticker="Y", value_raw=0.8, quality_raw=0.2, growth_raw=0.9)
    result = rank([cand_x, cand_y])
    assert result[0].ticker == "Y"
    assert result[0].composite_score == pytest.approx(0.65)
    assert result[1].ticker == "X"
    assert result[1].composite_score == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# RankingWeights
# ---------------------------------------------------------------------------


def test_default_weights_sum_to_one() -> None:
    w = RankingWeights()
    assert w.value + w.quality + w.growth + w.margin_of_safety == pytest.approx(1.0)


def test_custom_weights_accepted() -> None:
    w = RankingWeights(value=0.50, quality=0.25, growth=0.15, margin_of_safety=0.10)
    assert w.value == pytest.approx(0.50)


def test_invalid_weights_raise_value_error() -> None:
    with pytest.raises(ValueError):
        RankingWeights(value=0.50, quality=0.30, growth=0.20, margin_of_safety=0.20)


def test_custom_weights_affect_ranking() -> None:
    """With pure value weight the highest-value candidate wins."""
    w = RankingWeights(value=0.90, quality=0.05, growth=0.04, margin_of_safety=0.01)
    result = rank([A, B, C], weights=w)
    assert result[0].ticker == "C"  # C has value_raw=0.9, the highest
