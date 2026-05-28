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


@dataclass
class IndustryBenchmarks:
    """Damodaran industry-level benchmarks for the company's sector."""

    industry: str | None = None


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
