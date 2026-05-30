"""Rule abstraction and registry for the mechanical screener (Capa B).

Every screener filter — quality gate, value indicator, trap detector (spec
§6.2/§6.3/§6.4) — is a :class:`Rule` subclass: a pure, dependency-free unit that
maps ``(CompanyData, IndustryBenchmarks)`` to a :class:`RuleResult`. Rules carry
no state of their own beyond configuration passed at construction, so they are
testable in isolation against fixtures (CONTEXT.md / spec §6.6).

The registry decouples YAML config from Python classes: a rule registers itself
under a unique ``name`` via the :func:`register` decorator, and the engine
resolves names to classes with :func:`get_rule`. This lets
``config/screener_config.yaml`` reference rules by name without importing them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bot.screener.types import CompanyData, IndustryBenchmarks


@dataclass(frozen=True)
class RuleResult:
    """Verdict of a single rule for a single company.

    Attributes:
        passed: Whether the company clears this rule. For eliminatory gates this
            is the only thing that matters; ``False`` disqualifies the company.
        score: Continuous strength in ``[0.0, 1.0]`` for ranking rules (spec
            §6.5). Eliminatory gates leave this at ``0.0``.
        reason: Human-readable explanation for debugging / report traceability.
        skipped: ``True`` when the rule could not be evaluated for lack of data
            (e.g. a value indicator whose industry has no Damodaran median, spec
            §6.3). A skipped rule never counts as a *pass* (``passed`` stays
            ``False``), but callers can tell "failed the test" apart from "could
            not run the test" — the latter must not, on its own, disqualify a
            company that other indicators vouch for.
    """

    passed: bool
    score: float = 0.0
    reason: str = ""
    skipped: bool = False


class Rule(ABC):
    """Base class for all screener rules.

    Subclasses set a class-level ``name`` (unique registry key) and implement
    :meth:`evaluate`. ``evaluate`` MUST be pure: no I/O, no mutation of its
    inputs, deterministic given the same arguments.
    """

    #: Unique registry identifier; set on each concrete subclass.
    name: str

    @abstractmethod
    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        """Evaluate ``company`` against ``benchmarks`` and return a verdict."""
        raise NotImplementedError


# name -> Rule subclass. Populated by the ``register`` decorator at import time.
_REGISTRY: dict[str, type[Rule]] = {}


def register(cls: type[Rule]) -> type[Rule]:
    """Class decorator registering ``cls`` under its ``name``.

    Raises:
        ValueError: if the class has no non-empty ``name``, or the name is
            already registered (duplicate names would make YAML references
            ambiguous).
    """
    name = getattr(cls, "name", "")
    if not name:
        raise ValueError(f"{cls.__name__} must define a non-empty class-level `name`")
    if name in _REGISTRY:
        existing = _REGISTRY[name].__name__
        raise ValueError(
            f"rule name {name!r} already registered to {existing}; names must be unique"
        )
    _REGISTRY[name] = cls
    return cls


def get_rule(name: str) -> type[Rule]:
    """Resolve a registered rule class by ``name``.

    Raises:
        KeyError: if no rule is registered under ``name``.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"unknown rule {name!r}; registered rules: {known}") from None


def registered_rules() -> dict[str, type[Rule]]:
    """Return a copy of the registry (name -> rule class), for introspection."""
    return dict(_REGISTRY)


@register
class MarketCapMin(Rule):
    """Quality gate: market cap must clear a floor (spec §6.2, default USD 100M).

    A trivial reference rule exercising the abstraction end to end. A company
    with no market-cap datum fails the gate — the screener will not vouch for a
    company it cannot size.
    """

    name = "market_cap_min"

    def __init__(self, minimum_usd: float = 100_000_000.0) -> None:
        self.minimum_usd = minimum_usd

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.market_cap is None:
            return RuleResult(passed=False, reason="market_cap unavailable")
        passed = company.market_cap >= self.minimum_usd
        reason = (
            f"market_cap {company.market_cap:,.0f} "
            f"{'>=' if passed else '<'} minimum {self.minimum_usd:,.0f}"
        )
        return RuleResult(passed=passed, reason=reason)


# --------------------------------------------------------------------------- #
# Quality gates (spec §6.2). Each gate is eliminatory: a missing datum fails the
# gate, since the screener will not vouch for a company it cannot measure.
# --------------------------------------------------------------------------- #

#: Industries excluded by default (banks + insurance, spec §6.2). Matching is
#: case-insensitive substring so Damodaran labels like "Bank (Money Center)" and
#: "Insurance (Life)" are caught without enumerating every variant.
DEFAULT_EXCLUDED_SECTORS: tuple[str, ...] = ("bank", "insurance")


@register
class MinMarketCap(Rule):
    """Quality gate: market cap must clear a floor (spec §6.2, default USD 100M)."""

    name = "min_market_cap"

    def __init__(self, minimum_usd: float = 100_000_000.0) -> None:
        self.minimum_usd = minimum_usd

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.market_cap is None:
            return RuleResult(passed=False, reason="market_cap unavailable")
        passed = company.market_cap >= self.minimum_usd
        reason = (
            f"market_cap {company.market_cap:,.0f} "
            f"{'>=' if passed else '<'} minimum {self.minimum_usd:,.0f}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class MinYearsHistory(Rule):
    """Quality gate: enough financial history to assess (spec §6.2, default 5y)."""

    name = "min_years_history"

    def __init__(self, minimum_years: int = 5) -> None:
        self.minimum_years = minimum_years

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        passed = company.years_of_financials >= self.minimum_years
        reason = (
            f"years_of_financials {company.years_of_financials} "
            f"{'>=' if passed else '<'} minimum {self.minimum_years}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class ExcludeSectors(Rule):
    """Quality gate: drop excluded sectors (spec §6.2, default banks + insurance).

    Excludes on either the ``is_financial_services`` flag or a case-insensitive
    substring match of ``industry`` against the configured list.
    """

    name = "exclude_sectors"

    def __init__(self, excluded: tuple[str, ...] = DEFAULT_EXCLUDED_SECTORS) -> None:
        self.excluded = tuple(s.lower() for s in excluded)

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.is_financial_services:
            return RuleResult(passed=False, reason="flagged as financial services")
        industry = (company.industry or "").lower()
        for token in self.excluded:
            if token in industry:
                return RuleResult(
                    passed=False,
                    reason=f"industry {company.industry!r} matches excluded {token!r}",
                )
        return RuleResult(
            passed=True, reason=f"industry {company.industry!r} not excluded"
        )


@register
class MaxNetDebtToEBITDA(Rule):
    """Quality gate: leverage within capacity (spec §6.2, default Net Debt/EBITDA < 4).

    Net cash (negative net debt) trivially clears the gate. With positive net
    debt and non-positive EBITDA the ratio is undefined/blown out, so the gate
    fails.
    """

    name = "max_net_debt_to_ebitda"

    def __init__(self, maximum: float = 4.0) -> None:
        self.maximum = maximum

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.net_debt is None or company.ebitda is None:
            return RuleResult(passed=False, reason="net_debt or ebitda unavailable")
        if company.net_debt <= 0:
            return RuleResult(passed=True, reason="net cash position")
        if company.ebitda <= 0:
            return RuleResult(
                passed=False, reason="positive net debt with non-positive EBITDA"
            )
        ratio = company.net_debt / company.ebitda
        passed = ratio <= self.maximum
        reason = (
            f"net_debt/ebitda {ratio:.2f} "
            f"{'<=' if passed else '>'} maximum {self.maximum:.2f}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class MinInterestCoverage(Rule):
    """Quality gate: EBIT covers interest (spec §6.2, default EBIT/Interest > 2).

    No interest expense (zero/negative) means coverage is effectively infinite,
    so the gate passes.
    """

    name = "min_interest_coverage"

    def __init__(self, minimum: float = 2.0) -> None:
        self.minimum = minimum

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.ebit is None or company.interest_expense is None:
            return RuleResult(
                passed=False, reason="ebit or interest_expense unavailable"
            )
        if company.interest_expense <= 0:
            return RuleResult(passed=True, reason="no interest expense")
        coverage = company.ebit / company.interest_expense
        passed = coverage >= self.minimum
        reason = (
            f"interest_coverage {coverage:.2f} "
            f"{'>=' if passed else '<'} minimum {self.minimum:.2f}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class PositiveOperatingCashflow(Rule):
    """Quality gate: operating cashflow positive in >= N of last 5 years (spec §6.2).

    Looks only at the most recent ``window`` years; older years do not count
    against the company. Insufficient history fails the gate.
    """

    name = "positive_operating_cashflow"

    def __init__(self, min_positive: int = 4, window: int = 5) -> None:
        self.min_positive = min_positive
        self.window = window

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        recent = company.operating_cashflow_history[-self.window :]
        if len(recent) < self.window:
            return RuleResult(
                passed=False,
                reason=(
                    f"insufficient history: {len(recent)} years "
                    f"(need {self.window})"
                ),
            )
        positive = sum(1 for cf in recent if cf > 0)
        passed = positive >= self.min_positive
        reason = (
            f"{positive}/{self.window} years positive operating cashflow "
            f"{'>=' if passed else '<'} required {self.min_positive}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class MaxGoodwillToAssets(Rule):
    """Quality gate: goodwill not dominating the balance sheet (spec §6.2, < 50%).

    Zero/negative total assets is degenerate and fails the gate.
    """

    name = "max_goodwill_to_assets"

    def __init__(self, maximum: float = 0.5) -> None:
        self.maximum = maximum

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.goodwill is None or company.total_assets is None:
            return RuleResult(
                passed=False, reason="goodwill or total_assets unavailable"
            )
        if company.total_assets <= 0:
            return RuleResult(passed=False, reason="non-positive total_assets")
        ratio = company.goodwill / company.total_assets
        passed = ratio <= self.maximum
        reason = (
            f"goodwill/total_assets {ratio:.2f} "
            f"{'<=' if passed else '>'} maximum {self.maximum:.2f}"
        )
        return RuleResult(passed=passed, reason=reason)


# --------------------------------------------------------------------------- #
# Value indicators (spec §6.3). At least one must pass for a candidate to be
# kept. All are relative to the company's sector medians (Damodaran datasets),
# so each rule first checks the relevant median is present and *skips* itself
# (``skipped=True``, never a pass) when the industry has no data — a skip must
# not, on its own, disqualify a company that other indicators vouch for. Missing
# company data is likewise a skip: cheapness cannot be judged from nothing.
# --------------------------------------------------------------------------- #


def _value_score(value: float, threshold: float) -> float:
    """Map a metric to a ``[0.0, 1.0]`` cheapness score for ranking (spec §6.5).

    ``value`` at the threshold scores ``0.0``; ``value`` at or below zero scores
    ``1.0``; in between it scales linearly with how far below the threshold the
    metric sits. ``threshold`` is assumed positive (callers only score after a
    positive-median check).
    """
    if threshold <= 0:
        return 0.0
    score = (threshold - value) / threshold
    return max(0.0, min(1.0, score))


@register
class PEBelowIndustryMultiple(Rule):
    """Value indicator: PE below a multiple of the sector median (spec §6.3).

    Default ``0.7x`` the industry-median PE. A non-positive company PE (loss
    maker) carries no cheapness signal and is skipped, as is a company or sector
    with no PE datum.
    """

    name = "pe_below_industry_multiple"

    def __init__(self, multiple: float = 0.7) -> None:
        self.multiple = multiple

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if benchmarks.pe is None or benchmarks.pe <= 0:
            return RuleResult(
                passed=False, skipped=True, reason="no sector PE median available"
            )
        if company.pe is None or company.pe <= 0:
            return RuleResult(
                passed=False, skipped=True, reason="company PE unavailable or non-positive"
            )
        threshold = benchmarks.pe * self.multiple
        passed = company.pe < threshold
        score = _value_score(company.pe, threshold) if passed else 0.0
        reason = (
            f"PE {company.pe:.2f} {'<' if passed else '>='} "
            f"{self.multiple:.2f}x sector median {benchmarks.pe:.2f} "
            f"(= {threshold:.2f})"
        )
        return RuleResult(passed=passed, score=score, reason=reason)


@register
class EVEBITDABelowIndustryMultiple(Rule):
    """Value indicator: EV/EBITDA below a multiple of the sector median (§6.3).

    Default ``0.7x`` the industry-median EV/EBITDA. Skipped when the company or
    sector lacks the datum.
    """

    name = "ev_ebitda_below_industry_multiple"

    def __init__(self, multiple: float = 0.7) -> None:
        self.multiple = multiple

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if benchmarks.ev_ebitda is None or benchmarks.ev_ebitda <= 0:
            return RuleResult(
                passed=False,
                skipped=True,
                reason="no sector EV/EBITDA median available",
            )
        if company.ev_ebitda is None or company.ev_ebitda <= 0:
            return RuleResult(
                passed=False,
                skipped=True,
                reason="company EV/EBITDA unavailable or non-positive",
            )
        threshold = benchmarks.ev_ebitda * self.multiple
        passed = company.ev_ebitda < threshold
        score = _value_score(company.ev_ebitda, threshold) if passed else 0.0
        reason = (
            f"EV/EBITDA {company.ev_ebitda:.2f} {'<' if passed else '>='} "
            f"{self.multiple:.2f}x sector median {benchmarks.ev_ebitda:.2f} "
            f"(= {threshold:.2f})"
        )
        return RuleResult(passed=passed, score=score, reason=reason)


@register
class PBVBelowIndustryMultipleWithROEAboveMedian(Rule):
    """Value indicator: cheap on P/BV *and* ROE above the sector median (§6.3).

    The classic "real value, not a trap" combination: P/BV below ``0.7x`` the
    sector median (default) **and** ROE above the sector median. Both legs need
    sector medians and company data; any of them missing skips the rule.
    """

    name = "pbv_below_industry_multiple_with_roe_above_median"

    def __init__(self, multiple: float = 0.7) -> None:
        self.multiple = multiple

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if benchmarks.pbv is None or benchmarks.pbv <= 0 or benchmarks.roe is None:
            return RuleResult(
                passed=False,
                skipped=True,
                reason="no sector P/BV or ROE median available",
            )
        if company.pbv is None or company.pbv <= 0 or company.roe is None:
            return RuleResult(
                passed=False,
                skipped=True,
                reason="company P/BV or ROE unavailable",
            )
        threshold = benchmarks.pbv * self.multiple
        cheap = company.pbv < threshold
        quality = company.roe > benchmarks.roe
        passed = cheap and quality
        score = _value_score(company.pbv, threshold) if passed else 0.0
        reason = (
            f"P/BV {company.pbv:.2f} {'<' if cheap else '>='} "
            f"{self.multiple:.2f}x sector median {benchmarks.pbv:.2f} "
            f"(= {threshold:.2f}); ROE {company.roe:.3f} "
            f"{'>' if quality else '<='} sector median {benchmarks.roe:.3f}"
        )
        return RuleResult(passed=passed, score=score, reason=reason)


@register
class FCFYieldAbove(Rule):
    """Value indicator: free-cash-flow yield above an absolute floor (§6.3).

    Default ``0.08`` (8%). Unlike the multiple rules this is an absolute
    threshold, not sector-relative, so it needs no benchmark — only the
    company's FCF yield, which is skipped when unavailable.
    """

    name = "fcf_yield_above"

    def __init__(self, minimum: float = 0.08) -> None:
        self.minimum = minimum

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.fcf_yield is None:
            return RuleResult(
                passed=False, skipped=True, reason="company FCF yield unavailable"
            )
        passed = company.fcf_yield > self.minimum
        score = min(1.0, company.fcf_yield / self.minimum) if passed else 0.0
        reason = (
            f"FCF yield {company.fcf_yield:.3f} "
            f"{'>' if passed else '<='} minimum {self.minimum:.3f}"
        )
        return RuleResult(passed=passed, score=score, reason=reason)
