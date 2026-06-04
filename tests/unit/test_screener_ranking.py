"""Unit tests for the composite ranking score (spec §6.5, issue M3.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.screener.ranking import (
    Candidate,
    RankingWeights,
    ScoredCandidate,
    rank,
)

# --------------------------------------------------------------------------- #
# Fixture universe with hand-computable percentile expectations.
# --------------------------------------------------------------------------- #
#
# Five candidates. We give each dimension a strictly increasing metric across
# the universe so the percentile ranks are unambiguous. With "rank / (n - 1)"
# normalisation over 5 evenly distinct values, percentiles are
# {0.0, 0.25, 0.5, 0.75, 1.0}.


def _universe() -> list[Candidate]:
    return [
        Candidate(ticker="AAA", value_metric=1.0, quality_metric=1.0, growth_metric=1.0),
        Candidate(ticker="BBB", value_metric=2.0, quality_metric=2.0, growth_metric=2.0),
        Candidate(ticker="CCC", value_metric=3.0, quality_metric=3.0, growth_metric=3.0),
        Candidate(ticker="DDD", value_metric=4.0, quality_metric=4.0, growth_metric=4.0),
        Candidate(ticker="EEE", value_metric=5.0, quality_metric=5.0, growth_metric=5.0),
    ]


def test_rank_returns_one_scored_candidate_per_input() -> None:
    result = rank(_universe())
    assert len(result) == 5
    assert all(isinstance(c, ScoredCandidate) for c in result)


def test_percentiles_are_min_max_rank_normalised() -> None:
    by_ticker = {c.ticker: c for c in rank(_universe())}
    # Strictly increasing metric -> evenly spaced percentiles.
    assert by_ticker["AAA"].value_score == pytest.approx(0.0)
    assert by_ticker["BBB"].value_score == pytest.approx(0.25)
    assert by_ticker["CCC"].value_score == pytest.approx(0.5)
    assert by_ticker["DDD"].value_score == pytest.approx(0.75)
    assert by_ticker["EEE"].value_score == pytest.approx(1.0)


def test_composite_score_uses_default_weights_and_is_0_to_100() -> None:
    # Top candidate: value=quality=growth percentile 1.0, MoS placeholder 0.5.
    # score = 100 * (0.40*1 + 0.30*1 + 0.20*1 + 0.10*0.5) = 100 * 0.95 = 95.0
    top = next(c for c in rank(_universe()) if c.ticker == "EEE")
    assert top.score == pytest.approx(95.0)

    # Bottom candidate: all percentiles 0.0, MoS 0.5.
    # score = 100 * (0 + 0 + 0 + 0.10*0.5) = 5.0
    bottom = next(c for c in rank(_universe()) if c.ticker == "AAA")
    assert bottom.score == pytest.approx(5.0)


def test_result_is_sorted_by_score_descending() -> None:
    result = rank(_universe())
    scores = [c.score for c in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0].ticker == "EEE"
    assert result[-1].ticker == "AAA"


def test_margin_of_safety_is_placeholder_half_by_default() -> None:
    for scored in rank(_universe()):
        assert scored.margin_of_safety == pytest.approx(0.5)


def test_explicit_margin_of_safety_is_passed_through() -> None:
    candidates = [
        Candidate(
            ticker="ZZZ",
            value_metric=1.0,
            quality_metric=1.0,
            growth_metric=1.0,
            margin_of_safety=1.5,
        )
    ]
    [scored] = rank(candidates)
    # Single candidate -> percentiles default to top (1.0) of a degenerate universe.
    assert scored.margin_of_safety == pytest.approx(1.5)


def test_single_candidate_universe_scores_percentile_one() -> None:
    [scored] = rank([Candidate(ticker="ONE", value_metric=42.0, quality_metric=7.0, growth_metric=3.0)])
    assert scored.value_score == pytest.approx(1.0)
    assert scored.quality_score == pytest.approx(1.0)
    assert scored.growth_score == pytest.approx(1.0)


def test_empty_universe_returns_empty_list() -> None:
    assert rank([]) == []


def test_ties_share_the_same_percentile() -> None:
    candidates = [
        Candidate(ticker="A", value_metric=1.0, quality_metric=1.0, growth_metric=1.0),
        Candidate(ticker="B", value_metric=1.0, quality_metric=1.0, growth_metric=1.0),
        Candidate(ticker="C", value_metric=2.0, quality_metric=2.0, growth_metric=2.0),
    ]
    by_ticker = {c.ticker: c for c in rank(candidates)}
    assert by_ticker["A"].value_score == pytest.approx(by_ticker["B"].value_score)
    assert by_ticker["C"].value_score == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Weights configuration (Pydantic-validated, YAML-loadable).
# --------------------------------------------------------------------------- #


def test_default_weights_match_spec() -> None:
    w = RankingWeights()
    assert w.value == pytest.approx(0.40)
    assert w.quality == pytest.approx(0.30)
    assert w.growth == pytest.approx(0.20)
    assert w.margin_of_safety == pytest.approx(0.10)


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        RankingWeights(value=0.5, quality=0.5, growth=0.5, margin_of_safety=0.5)


def test_weights_reject_negative() -> None:
    with pytest.raises(ValueError):
        RankingWeights(value=-0.1, quality=0.4, growth=0.4, margin_of_safety=0.3)


def test_weights_load_from_yaml(tmp_path: Path) -> None:
    cfg = tmp_path / "weights.yaml"
    cfg.write_text(
        "value: 0.25\nquality: 0.25\ngrowth: 0.25\nmargin_of_safety: 0.25\n"
    )
    w = RankingWeights.from_yaml(cfg)
    assert w.value == pytest.approx(0.25)
    assert w.margin_of_safety == pytest.approx(0.25)


def test_custom_weights_change_the_score() -> None:
    # All weight on value: top candidate scores 100, bottom scores 0.
    w = RankingWeights(value=1.0, quality=0.0, growth=0.0, margin_of_safety=0.0)
    by_ticker = {c.ticker: c for c in rank(_universe(), weights=w)}
    assert by_ticker["EEE"].score == pytest.approx(100.0)
    assert by_ticker["AAA"].score == pytest.approx(0.0)
