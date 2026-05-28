"""Ranking score for the screener shortlist (M3.6).

Composite formula (spec s6.5):
    score = 0.40 * value_score + 0.30 * quality_score
          + 0.20 * growth_score + 0.10 * margin_of_safety

Each of value_score, quality_score, and growth_score is the percentile of the
candidate within the filtered universe (0 = lowest, 1 = highest).
margin_of_safety is a placeholder of 0.5 until M4.7 wires in the real DCF value.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, model_validator


class RankingWeights(BaseModel):
    """Pydantic-validated composite score weights.

    Weights must sum to exactly 1.0.  Load from YAML / environment before
    calling ``rank()`` to override the spec defaults.
    """

    value: float = 0.40
    quality: float = 0.30
    growth: float = 0.20
    margin_of_safety: float = 0.10

    @model_validator(mode="after")
    def _sum_to_one(self) -> RankingWeights:
        total = self.value + self.quality + self.growth + self.margin_of_safety
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0, got {total:.10f}")
        return self


@dataclass
class Candidate:
    """Pre-screened company ready for composite ranking.

    Callers populate *_raw* fields from rule-level scores (0-1) or any
    normalised metric that captures strength on that dimension.
    """

    ticker: str
    value_raw: float
    quality_raw: float
    growth_raw: float
    # M4.7 will replace this placeholder with a real DCF-derived margin of safety.
    margin_of_safety: float = field(default=0.5)


@dataclass
class ScoredCandidate:
    """Candidate annotated with percentile sub-scores and the composite."""

    ticker: str
    value_score: float  # percentile rank within the filtered universe [0, 1]
    quality_score: float  # percentile rank within the filtered universe [0, 1]
    growth_score: float  # percentile rank within the filtered universe [0, 1]
    margin_of_safety: float  # placeholder 0.5 until M4.7
    composite_score: float  # weighted composite in [0, 1]


def _percentile_ranks(values: Sequence[float]) -> list[float]:
    """Map *values* to percentile ranks in [0, 1].

    Ordinal ranking: the lowest value gets 0.0, the highest gets 1.0.
    Ties receive their natural ordinal position from a stable sort (not
    averaged) — the resulting differences are below scoring noise anyway.
    A single-element universe returns [0.5] (no relative comparison possible).
    """
    n = len(values)
    if n == 1:
        return [0.5]
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    ranks = [0.0] * n
    for rank, (orig_idx, _) in enumerate(indexed):
        ranks[orig_idx] = rank / (n - 1)
    return ranks


def rank(
    candidates: Sequence[Candidate],
    weights: RankingWeights | None = None,
) -> list[ScoredCandidate]:
    """Rank *candidates* by composite score, descending.

    Args:
        candidates: Pre-filtered universe; each entry has already passed all
                    eliminatory rules.
        weights: Score weights.  Defaults to the spec values (0.40/0.30/0.20/0.10).

    Returns:
        Sorted list of :class:`ScoredCandidate`, best first.  Empty input
        returns an empty list.
    """
    if not candidates:
        return []
    if weights is None:
        weights = RankingWeights()

    value_pcts = _percentile_ranks([c.value_raw for c in candidates])
    quality_pcts = _percentile_ranks([c.quality_raw for c in candidates])
    growth_pcts = _percentile_ranks([c.growth_raw for c in candidates])

    scored: list[ScoredCandidate] = []
    for c, vp, qp, gp in zip(candidates, value_pcts, quality_pcts, growth_pcts, strict=True):
        composite = (
            weights.value * vp
            + weights.quality * qp
            + weights.growth * gp
            + weights.margin_of_safety * c.margin_of_safety
        )
        scored.append(
            ScoredCandidate(
                ticker=c.ticker,
                value_score=vp,
                quality_score=qp,
                growth_score=gp,
                margin_of_safety=c.margin_of_safety,
                composite_score=composite,
            )
        )

    return sorted(scored, key=lambda s: s.composite_score, reverse=True)
