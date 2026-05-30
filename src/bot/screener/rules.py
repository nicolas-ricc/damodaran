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
    """

    passed: bool
    score: float = 0.0
    reason: str = ""


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
