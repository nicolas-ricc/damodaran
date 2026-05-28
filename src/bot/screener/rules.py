"""Rule abstraction and registry for the screener (Capa B)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
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
    # M3.3 quality gate rules
    years_history: int | None = None
    sector: str | None = None
    net_debt: float | None = None
    ebitda: float | None = None
    ebit: float | None = None
    interest_expense: float | None = None
    operating_cashflow_history: list[float] = field(default_factory=list)
    goodwill: float | None = None
    total_assets: float | None = None
    # M3.4 value indicator rules
    pe_ratio: float | None = None
    ev_ebitda: float | None = None
    pbv: float | None = None
    roe: float | None = None
    fcf_yield: float | None = None
    # M3.5 trap detection
    revenue_3y: list[float] | None = None
    op_margin_3y: list[float] | None = None
    roic: float | None = None
    net_income: float | None = None
    operating_cashflow: float | None = None
    shares_diluted_3y: list[float] | None = None
    auditor_changed: bool | None = None
    has_late_filings: bool | None = None


@dataclass
class IndustryBenchmarks:
    """Damodaran industry-level benchmarks for the company's sector."""

    industry: str | None = None
    # M3.4 value indicator rules
    pe: float | None = None
    ev_ebitda: float | None = None
    pbv: float | None = None
    roe: float | None = None
    # M3.5 trap detection
    wacc: float | None = None


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


# ---------------------------------------------------------------------------
# M3.3 Quality Gate Rules
# ---------------------------------------------------------------------------


@register
class MinMarketCap(Rule):
    """Quality gate: company must meet a minimum market capitalisation (default 100M USD)."""

    name: ClassVar[str] = "min_market_cap"

    def __init__(self, min_usd: float = 100_000_000.0) -> None:
        self.min_usd = min_usd

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.market_cap is None:
            return RuleResult(passed=False, score=0.0, reason="market_cap not available")
        if company.market_cap >= self.min_usd:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"market_cap {company.market_cap:,.0f} >= {self.min_usd:,.0f}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"market_cap {company.market_cap:,.0f} < {self.min_usd:,.0f}",
        )


@register
class MinYearsHistory(Rule):
    """Quality gate: company must have at least N years of financial history (default 5)."""

    name: ClassVar[str] = "min_years_history"

    def __init__(self, min_years: int = 5) -> None:
        self.min_years = min_years

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.years_history is None:
            return RuleResult(passed=False, score=0.0, reason="years_history not available")
        if company.years_history >= self.min_years:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"years_history {company.years_history} >= {self.min_years}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"years_history {company.years_history} < {self.min_years}",
        )


@register
class ExcludeSectors(Rule):
    """Quality gate: exclude companies in certain sectors (default: Banks, Insurance)."""

    name: ClassVar[str] = "exclude_sectors"

    def __init__(self, excluded: Sequence[str] = ("Banks", "Insurance")) -> None:
        self._excluded: frozenset[str] = frozenset(excluded)

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.sector is None:
            return RuleResult(passed=False, score=0.0, reason="sector not available")
        if company.sector in self._excluded:
            return RuleResult(
                passed=False,
                score=0.0,
                reason=f"sector {company.sector!r} is excluded",
            )
        return RuleResult(
            passed=True,
            score=1.0,
            reason=f"sector {company.sector!r} is not excluded",
        )


@register
class MaxNetDebtToEBITDA(Rule):
    """Quality gate: net debt / EBITDA must not exceed threshold (default 4.0)."""

    name: ClassVar[str] = "max_net_debt_to_ebitda"

    def __init__(self, max_ratio: float = 4.0) -> None:
        self.max_ratio = max_ratio

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.net_debt is None or company.ebitda is None:
            return RuleResult(passed=False, score=0.0, reason="net_debt or ebitda not available")
        if company.ebitda <= 0:
            return RuleResult(
                passed=False,
                score=0.0,
                reason=f"ebitda {company.ebitda:,.0f} <= 0; ratio undefined",
            )
        ratio = company.net_debt / company.ebitda
        if ratio <= self.max_ratio:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"net_debt/ebitda {ratio:.2f} <= {self.max_ratio}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"net_debt/ebitda {ratio:.2f} > {self.max_ratio}",
        )


@register
class MinInterestCoverage(Rule):
    """Quality gate: EBIT / interest expense must be at or above threshold (default 2.0)."""

    name: ClassVar[str] = "min_interest_coverage"

    def __init__(self, min_ratio: float = 2.0) -> None:
        self.min_ratio = min_ratio

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.ebit is None or company.interest_expense is None:
            return RuleResult(
                passed=False, score=0.0, reason="ebit or interest_expense not available"
            )
        if company.interest_expense <= 0:
            return RuleResult(passed=True, score=1.0, reason="interest_expense <= 0 (no leverage)")
        ratio = company.ebit / company.interest_expense
        if ratio >= self.min_ratio:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"interest_coverage {ratio:.2f} >= {self.min_ratio}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"interest_coverage {ratio:.2f} < {self.min_ratio}",
        )


@register
class PositiveOperatingCashflow(Rule):
    """Quality gate: OCF must be positive in at least 4 of the last 5 years."""

    name: ClassVar[str] = "positive_operating_cashflow"

    def __init__(self, min_positive_years: int = 4, lookback_years: int = 5) -> None:
        self.min_positive_years = min_positive_years
        self.lookback_years = lookback_years

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        history = company.operating_cashflow_history
        if not history:
            return RuleResult(
                passed=False, score=0.0, reason="operating_cashflow_history not available"
            )
        window = history[-self.lookback_years :]
        positive_count = sum(1 for ocf in window if ocf > 0)
        if positive_count >= self.min_positive_years:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"{positive_count}/{len(window)} years with positive OCF >= {self.min_positive_years}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"{positive_count}/{len(window)} years with positive OCF < {self.min_positive_years}",
        )


@register
class MaxGoodwillToAssets(Rule):
    """Quality gate: goodwill / total assets must not exceed threshold (default 0.5)."""

    name: ClassVar[str] = "max_goodwill_to_assets"

    def __init__(self, max_ratio: float = 0.5) -> None:
        self.max_ratio = max_ratio

    def evaluate(self, company: CompanyData, benchmarks: IndustryBenchmarks) -> RuleResult:
        if company.goodwill is None or company.total_assets is None:
            return RuleResult(
                passed=False, score=0.0, reason="goodwill or total_assets not available"
            )
        if company.total_assets <= 0:
            return RuleResult(
                passed=False,
                score=0.0,
                reason=f"total_assets {company.total_assets:,.0f} <= 0; ratio undefined",
            )
        ratio = company.goodwill / company.total_assets
        if ratio <= self.max_ratio:
            return RuleResult(
                passed=True,
                score=1.0,
                reason=f"goodwill/assets {ratio:.2f} <= {self.max_ratio}",
            )
        return RuleResult(
            passed=False,
            score=0.0,
            reason=f"goodwill/assets {ratio:.2f} > {self.max_ratio}",
        )


# ---------------------------------------------------------------------------
# M3.4 Value Indicator Rules
# ---------------------------------------------------------------------------


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
