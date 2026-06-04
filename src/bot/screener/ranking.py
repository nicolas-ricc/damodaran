"""Composite ranking score that orders the screener shortlist (spec §6.5).

Companies that clear all three screener layers — quality gates, value
indicators, trap detection (spec §6.2/§6.3/§6.4) — are *candidates*. This module
turns the surviving universe into an ordered shortlist via a single composite
score::

    score = 0.40 * value_score      (cheapness vs sector)
          + 0.30 * quality_score    (ROIC vs WACC, ROE, margin stability)
          + 0.20 * growth_score     (sustained revenue / FCF growth)
          + 0.10 * margin_of_safety (intrinsic_value DCF / price)

The first three sub-scores are *percentiles within the filtered universe*, not
absolute thresholds (spec §6.5): a candidate is judged cheap/good/fast relative
to its peers that also passed the gates, so the ranking adapts to whatever
universe the screener produced rather than to fixed cut-offs that drift out of
date. Each percentile lies in ``[0, 1]``.

``margin_of_safety`` is deliberately *not* a percentile: it is the candidate's
raw, **absolute and unbounded** ``intrinsic_value / price`` ratio, carried
straight through so it keeps its real-world meaning across runs. Because that
ratio can exceed 1.0 (a candidate priced well below its DCF intrinsic value),
the weighted composite can exceed 100 — it has no strict 0-100 ceiling. The
three percentile components alone are bounded by 100; the margin-of-safety term
is what lifts a deeply undervalued candidate above it.

``margin_of_safety`` is the real ``intrinsic_value / price`` from the DCF valuator
(Capa C, spec §6.5) once **M4.7** has run: :func:`bot.screener.engine.run_screen`
values each shortlisted candidate and feeds the ratio in here. A candidate carries
the neutral placeholder :data:`PLACEHOLDER_MARGIN_OF_SAFETY` (= 0.5) only when no
DCF value is available (the valuator could not value the company, or a caller
passes no value). The percentile maths below is unchanged by this wiring — the
margin-of-safety component is carried straight through to the score.

The public surface is a pure function :func:`rank`: it reads its inputs, holds no
global state, and is deterministic given the same candidates and weights.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Neutral placeholder for the margin-of-safety sub-score until M4.7 wires the
#: real DCF ``intrinsic_value / price`` in (spec §6.5). Mid-scale so it neither
#: rewards nor penalises a candidate the screener cannot yet value.
PLACEHOLDER_MARGIN_OF_SAFETY = 0.5


class RankingWeights(BaseModel):
    """Weights for the four ranking sub-scores (spec §6.5).

    Defaults reproduce the spec's blend. Weights must be non-negative and sum to
    1.0 so the three percentile components stay bounded by 100 and the blend is a
    convex combination; both invariants are validated so a malformed
    ``config/screener_config.yaml`` fails loudly at load time rather than silently
    skewing the ranking. Note the composite is *not* capped at 100: because the
    margin-of-safety component is an absolute, unbounded ``intrinsic_value / price``
    ratio (see :class:`Candidate`), a candidate above 1.0 can push the score past
    100.
    """

    model_config = ConfigDict(frozen=True)

    value: float = Field(default=0.40, ge=0.0, le=1.0)
    quality: float = Field(default=0.30, ge=0.0, le=1.0)
    growth: float = Field(default=0.20, ge=0.0, le=1.0)
    margin_of_safety: float = Field(default=0.10, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> RankingWeights:
        total = self.value + self.quality + self.growth + self.margin_of_safety
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"ranking weights must sum to 1.0, got {total}")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> RankingWeights:
        """Load weights from a YAML file (Pydantic-validated).

        The file is a flat mapping of the four weight names to floats, e.g.::

            value: 0.40
            quality: 0.30
            growth: 0.20
            margin_of_safety: 0.10
        """
        data: Any = yaml.safe_load(path.read_text())
        return cls.model_validate(data)


@dataclass(frozen=True)
class Candidate:
    """A company that has cleared all three screener layers (spec §6.2-§6.4).

    Each dimension is summarised by a single raw metric on which *higher is
    better*, so the percentile rank is unambiguous:

    - ``value_metric``: cheapness vs sector (e.g. the strongest value-indicator
      score from §6.3 — bigger means cheaper relative to peers).
    - ``quality_metric``: ROIC-minus-WACC spread / ROE / margin stability blend
      (§6.5) — bigger means higher quality.
    - ``growth_metric``: sustained revenue / FCF growth (§6.5) — bigger means
      faster.

    ``margin_of_safety`` is the raw ``intrinsic_value / price`` ratio when known;
    it defaults to :data:`PLACEHOLDER_MARGIN_OF_SAFETY` when no DCF value is
    available. Unlike the three metrics above, it is an **absolute, unbounded**
    component carried straight through to the score (not percentile-ranked), so
    the real ratio — and the neutral placeholder — keep their absolute meaning. It
    can exceed 1.0 when intrinsic value is above price, which in turn lets the
    weighted composite exceed 100.
    """

    ticker: str
    value_metric: float
    quality_metric: float
    growth_metric: float
    margin_of_safety: float = PLACEHOLDER_MARGIN_OF_SAFETY


@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate with its percentile sub-scores and composite 0-100 score."""

    ticker: str
    value_score: float
    quality_score: float
    growth_score: float
    margin_of_safety: float
    score: float


def _percentiles(values: Sequence[float]) -> list[float]:
    """Min-max rank-normalise ``values`` into ``[0.0, 1.0]`` percentiles.

    Each value maps to ``(rank of its magnitude) / (n - 1)``: the smallest value
    scores ``0.0``, the largest ``1.0``, ties share the same percentile. A
    single-element (or degenerate, all-equal) universe collapses to ``1.0`` for
    every member — with no peers to rank against, the candidate sits at the top
    of its own distribution.
    """
    n = len(values)
    if n == 1:
        return [1.0]
    sorted_unique = sorted(set(values))
    span = len(sorted_unique) - 1
    if span == 0:
        # Every value identical: no spread to rank, treat all as top percentile.
        return [1.0] * n
    rank_of = {v: i / span for i, v in enumerate(sorted_unique)}
    return [rank_of[v] for v in values]


def rank(
    candidates: Sequence[Candidate],
    weights: RankingWeights | None = None,
) -> list[ScoredCandidate]:
    """Score and order ``candidates`` by the spec §6.5 composite, best first.

    Value/quality/growth sub-scores are percentiles within ``candidates`` (the
    filtered universe), each in ``[0, 1]``; the margin-of-safety component is the
    candidate's raw, absolute and unbounded ``intrinsic_value / price`` ratio
    (placeholder 0.5 until M4.7). The weighted blend is multiplied by 100: the
    three percentile terms alone stay within 100, but a margin-of-safety ratio
    above 1.0 can lift the final score past 100, so there is no strict ceiling.

    Pure and deterministic: no I/O, no mutation of the inputs. Ties on the final
    score are broken by ticker so the order is stable.
    """
    if not candidates:
        return []
    w = weights if weights is not None else RankingWeights()

    value_pcts = _percentiles([c.value_metric for c in candidates])
    quality_pcts = _percentiles([c.quality_metric for c in candidates])
    growth_pcts = _percentiles([c.growth_metric for c in candidates])

    scored: list[ScoredCandidate] = []
    for candidate, v_pct, q_pct, g_pct in zip(
        candidates, value_pcts, quality_pcts, growth_pcts, strict=True
    ):
        composite = 100.0 * (
            w.value * v_pct
            + w.quality * q_pct
            + w.growth * g_pct
            + w.margin_of_safety * candidate.margin_of_safety
        )
        scored.append(
            ScoredCandidate(
                ticker=candidate.ticker,
                value_score=v_pct,
                quality_score=q_pct,
                growth_score=g_pct,
                margin_of_safety=candidate.margin_of_safety,
                score=composite,
            )
        )

    scored.sort(key=lambda s: (-s.score, s.ticker))
    return scored
