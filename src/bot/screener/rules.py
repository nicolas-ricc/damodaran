"""Rule abstraction and registry for the screener (Capa B)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

_REGISTRY: dict[str, type[Rule]] = {}


@dataclass
class RuleResult:
    passed: bool
    score: float  # 0-1, used for ranking; eliminatory gates set 0.0 when failed
    reason: str


@dataclass
class CompanyData:
    """Lightweight company snapshot passed to every rule during screening."""

    ticker: str
    market_cap: float | None = None
    pe_ratio: float | None = None
    ev_ebitda: float | None = None
    pbv: float | None = None
    roe: float | None = None
    fcf_yield: float | None = None


@dataclass
class IndustryBenchmarks:
    """Damodaran industry-level benchmarks for the company's sector."""

    industry: str | None = None
    pe: float | None = None
    ev_ebitda: float | None = None
    pbv: float | None = None
    roe: float | None = None


class Rule(ABC):
    """Abstract base class for all screener rules."""

    name: ClassVar[str]

    @abstractmethod
    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult: ...


def register[R: Rule](cls: type[R]) -> type[R]:
    """Decorator: register *cls* in the global rule registry under ``cls.name``.

    Raises ValueError on duplicate registration.
    """
    if cls.name in _REGISTRY:
        raise ValueError(f"Rule already registered: {cls.name!r}")
    _REGISTRY[cls.name] = cls
    return cls


def get_rule(name: str) -> type[Rule]:
    """Return the Rule class registered under *name*.

    Raises KeyError if no rule with that name has been registered.
    """
    if name not in _REGISTRY:
        raise KeyError(f"Unknown rule: {name!r}")
    return _REGISTRY[name]


def _no_sector_data() -> RuleResult:
    return RuleResult(passed=False, score=0.0, reason="no_sector_data")


@register
class MarketCapMin(Rule):
    """Eliminatory gate: market cap must be at or above a minimum threshold."""

    name: ClassVar[str] = "market_cap_min"

    def __init__(self, min_market_cap: float = 1_000_000_000.0) -> None:
        self.min_market_cap = min_market_cap

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.market_cap is None:
            return RuleResult(passed=False, score=0.0, reason="market_cap not available")
        if company.market_cap >= self.min_market_cap:
            score = min(company.market_cap / (self.min_market_cap * 10.0), 1.0)
            return RuleResult(
                passed=True,
                score=score,
                reason=f"market_cap {company.market_cap:,.0f} >= {self.min_market_cap:,.0f}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"market_cap {company.market_cap:,.0f} < {self.min_market_cap:,.0f}",
        )


@register
class PEBelowIndustryMultiple(Rule):
    """Value gate: P/E must be below a multiple of the industry median P/E."""

    name: ClassVar[str] = "pe_below_industry_multiple"

    def __init__(self, multiple: float = 0.7) -> None:
        self.multiple = multiple

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if benchmarks.pe is None or benchmarks.pe <= 0:
            return _no_sector_data()
        if company.pe_ratio is None:
            return RuleResult(passed=False, score=0.0, reason="pe_ratio not available")
        threshold = self.multiple * benchmarks.pe
        if company.pe_ratio <= threshold:
            score = 1.0 - company.pe_ratio / threshold
            return RuleResult(
                passed=True,
                score=score,
                reason=(
                    f"pe_ratio {company.pe_ratio:.2f} <= {threshold:.2f}"
                    f" ({self.multiple}× industry median {benchmarks.pe:.2f})"
                ),
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=(
                f"pe_ratio {company.pe_ratio:.2f} > {threshold:.2f}"
                f" ({self.multiple}× industry median {benchmarks.pe:.2f})"
            ),
        )


@register
class EVEBITDABelowIndustryMultiple(Rule):
    """Value gate: EV/EBITDA must be below a multiple of the industry median."""

    name: ClassVar[str] = "ev_ebitda_below_industry_multiple"

    def __init__(self, multiple: float = 0.7) -> None:
        self.multiple = multiple

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if benchmarks.ev_ebitda is None or benchmarks.ev_ebitda <= 0:
            return _no_sector_data()
        if company.ev_ebitda is None:
            return RuleResult(passed=False, score=0.0, reason="ev_ebitda not available")
        threshold = self.multiple * benchmarks.ev_ebitda
        if company.ev_ebitda <= threshold:
            score = 1.0 - company.ev_ebitda / threshold
            return RuleResult(
                passed=True,
                score=score,
                reason=(
                    f"ev_ebitda {company.ev_ebitda:.2f} <= {threshold:.2f}"
                    f" ({self.multiple}× industry median {benchmarks.ev_ebitda:.2f})"
                ),
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=(
                f"ev_ebitda {company.ev_ebitda:.2f} > {threshold:.2f}"
                f" ({self.multiple}× industry median {benchmarks.ev_ebitda:.2f})"
            ),
        )


@register
class PBVBelowIndustryMultipleWithROEAboveMedian(Rule):
    """Value gate: PBV cheap relative to sector AND ROE above sector median."""

    name: ClassVar[str] = "pbv_below_industry_multiple_with_roe_above_median"

    def __init__(self, pbv_multiple: float = 0.7) -> None:
        self.pbv_multiple = pbv_multiple

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if benchmarks.pbv is None or benchmarks.pbv <= 0 or benchmarks.roe is None:
            return _no_sector_data()
        if company.pbv is None:
            return RuleResult(passed=False, score=0.0, reason="pbv not available")
        if company.roe is None:
            return RuleResult(passed=False, score=0.0, reason="roe not available")
        pbv_threshold = self.pbv_multiple * benchmarks.pbv
        pbv_ok = company.pbv <= pbv_threshold
        roe_ok = company.roe >= benchmarks.roe
        if pbv_ok and roe_ok:
            score = 1.0 - company.pbv / pbv_threshold
            return RuleResult(
                passed=True,
                score=score,
                reason=(
                    f"pbv {company.pbv:.2f} <= {pbv_threshold:.2f}"
                    f" ({self.pbv_multiple}× median {benchmarks.pbv:.2f})"
                    f" and roe {company.roe:.2%} >= median {benchmarks.roe:.2%}"
                ),
            )
        if not pbv_ok:
            return RuleResult(
                passed=False,
                score=0.0,
                reason=(
                    f"pbv {company.pbv:.2f} > {pbv_threshold:.2f}"
                    f" ({self.pbv_multiple}× industry median {benchmarks.pbv:.2f})"
                ),
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"roe {company.roe:.2%} < industry median {benchmarks.roe:.2%}",
        )


@register
class FCFYieldAbove(Rule):
    """Value gate: free-cash-flow yield must exceed a minimum threshold."""

    name: ClassVar[str] = "fcf_yield_above"

    def __init__(self, min_yield: float = 0.08) -> None:
        self.min_yield = min_yield

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.fcf_yield is None:
            return RuleResult(passed=False, score=0.0, reason="fcf_yield not available")
        if company.fcf_yield >= self.min_yield:
            score = min(company.fcf_yield / (self.min_yield * 2.0), 1.0)
            return RuleResult(
                passed=True,
                score=score,
                reason=f"fcf_yield {company.fcf_yield:.2%} >= {self.min_yield:.2%}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"fcf_yield {company.fcf_yield:.2%} < {self.min_yield:.2%}",
        )
