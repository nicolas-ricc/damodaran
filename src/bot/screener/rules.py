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
from itertools import pairwise

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


# --------------------------------------------------------------------------- #
# Trap detection (spec §6.4). The most Damodaran-specific filters: a company can
# look cheap on §6.3 value indicators yet be cheap *for a reason*. Each detector
# is eliminatory — tripping one disqualifies the candidate. A missing datum fails
# the gate (the screener will not vouch for a company it cannot measure), except
# where noted: ROICAboveSectorWACC *skips* when the sector WACC median is absent
# (a data gap in the benchmark, not the company, must not eliminate on its own),
# and the best-effort SEC flags pass when the datum is simply unknown.
# --------------------------------------------------------------------------- #


def _avg_growth_rate(series: tuple[float, ...]) -> float | None:
    """Mean year-over-year growth rate of ``series`` (most recent last).

    Returns ``None`` when fewer than two points, or any point is non-positive
    (a zero/negative base makes the rate undefined/meaningless).
    """
    if len(series) < 2:
        return None
    rates: list[float] = []
    for prev, curr in pairwise(series):
        if prev <= 0:
            return None
        rates.append((curr - prev) / prev)
    return sum(rates) / len(rates)


@register
class RevenueNotDeclining(Rule):
    """Trap detector: average revenue growth not deeply negative (spec §6.4).

    Eliminates companies whose top line is shrinking faster than ``max_decline``
    (default ``-0.05`` = -5%) on average over the last few years. Needs at least
    ``window + 1`` revenue points (default 4 years -> 3 growth observations);
    insufficient or non-positive history fails the gate.
    """

    name = "revenue_not_declining"

    def __init__(self, max_decline: float = -0.05, window: int = 3) -> None:
        self.max_decline = max_decline
        self.window = window

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        recent = company.revenue_history[-(self.window + 1) :]
        if len(recent) < self.window + 1:
            return RuleResult(
                passed=False,
                reason=(
                    f"insufficient revenue history: {len(recent)} years "
                    f"(need {self.window + 1})"
                ),
            )
        avg_growth = _avg_growth_rate(recent)
        if avg_growth is None:
            return RuleResult(
                passed=False, reason="non-positive revenue base; growth undefined"
            )
        passed = avg_growth > self.max_decline
        reason = (
            f"avg revenue growth {avg_growth:.3f} over last {self.window}y "
            f"{'>' if passed else '<='} floor {self.max_decline:.3f}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class OperatingMarginNotContracting(Rule):
    """Trap detector: operating margin not eroding sharply (spec §6.4).

    Eliminates companies whose operating margin contracted by more than
    ``max_contraction_bps`` (default ``-200`` bps) from the start to the end of
    the window. Margins are fractions (``0.18`` = 18%); the change is measured in
    basis points (1 bp = 0.0001). Fewer than two points fails the gate.
    """

    name = "operating_margin_not_contracting"

    def __init__(self, max_contraction_bps: float = -200.0, window: int = 3) -> None:
        self.max_contraction_bps = max_contraction_bps
        self.window = window

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        recent = company.operating_margin_history[-(self.window + 1) :]
        if len(recent) < 2:
            return RuleResult(
                passed=False,
                reason=(
                    f"insufficient operating-margin history: {len(recent)} years "
                    "(need >= 2)"
                ),
            )
        change_bps = (recent[-1] - recent[0]) * 10_000.0
        passed = change_bps >= self.max_contraction_bps
        reason = (
            f"operating margin change {change_bps:.0f}bps over last "
            f"{len(recent) - 1}y {'>=' if passed else '<'} floor "
            f"{self.max_contraction_bps:.0f}bps"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class ROICAboveSectorWACC(Rule):
    """Trap detector: company creates value — ROIC above sector WACC (spec §6.4).

    The central Damodaran filter: a company earning a return on invested capital
    below its sector's cost of capital is destroying value, however cheap it
    looks. Reads the sector WACC from the Damodaran ``damodaran_industry`` median
    (:class:`IndustryBenchmarks`), not an absolute hurdle. Missing company ROIC
    fails the gate; a missing sector-WACC median *skips* (the benchmark gap must
    not eliminate the company on its own).
    """

    name = "roic_above_sector_wacc"

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if benchmarks.wacc is None:
            return RuleResult(
                passed=False, skipped=True, reason="no sector WACC median available"
            )
        if company.roic is None:
            return RuleResult(passed=False, reason="company ROIC unavailable")
        passed = company.roic > benchmarks.wacc
        reason = (
            f"ROIC {company.roic:.3f} {'>' if passed else '<='} "
            f"sector WACC {benchmarks.wacc:.3f}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class SloanAccrualsBelow(Rule):
    """Trap detector: Sloan accruals ratio below a ceiling (spec §6.4).

    The Sloan ratio ``(net_income - operating_cashflow) / total_assets`` measures
    how much of reported earnings is *not* backed by cash. A high ratio (default
    ceiling ``0.10``) flags low earnings quality / aggressive accruals — a classic
    value trap. Strictly-below passes; missing data or non-positive total assets
    fails the gate.
    """

    name = "sloan_accruals_below"

    def __init__(self, maximum: float = 0.10) -> None:
        self.maximum = maximum

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if (
            company.net_income is None
            or company.operating_cashflow is None
            or company.total_assets is None
        ):
            return RuleResult(
                passed=False,
                reason="net_income, operating_cashflow or total_assets unavailable",
            )
        if company.total_assets <= 0:
            return RuleResult(passed=False, reason="non-positive total_assets")
        ratio = (company.net_income - company.operating_cashflow) / company.total_assets
        passed = ratio < self.maximum
        reason = (
            f"Sloan accruals {ratio:.3f} "
            f"{'<' if passed else '>='} maximum {self.maximum:.3f}"
        )
        return RuleResult(passed=passed, reason=reason)


@register
class ShareCountNotDiluting(Rule):
    """Trap detector: share count not growing too fast without M&A (spec §6.4).

    Persistent share issuance dilutes existing holders; above ``max_annual_growth``
    (default ``0.05`` = 5% per year, on average) it is a trap signal — *unless* a
    material acquisition justifies it (``company.had_recent_ma``), since
    stock-funded M&A is a different story. Fewer than two points, or a
    non-positive base, fails the gate.
    """

    name = "share_count_not_diluting"

    def __init__(self, max_annual_growth: float = 0.05) -> None:
        self.max_annual_growth = max_annual_growth

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        series = company.share_count_history
        if len(series) < 2:
            return RuleResult(
                passed=False,
                reason=(
                    f"insufficient share-count history: {len(series)} years "
                    "(need >= 2)"
                ),
            )
        avg_growth = _avg_growth_rate(series)
        if avg_growth is None:
            return RuleResult(
                passed=False, reason="non-positive share count; growth undefined"
            )
        if avg_growth <= self.max_annual_growth:
            return RuleResult(
                passed=True,
                reason=(
                    f"avg share-count growth {avg_growth:.3f} "
                    f"<= maximum {self.max_annual_growth:.3f}"
                ),
            )
        if company.had_recent_ma:
            return RuleResult(
                passed=True,
                reason=(
                    f"avg share-count growth {avg_growth:.3f} exceeds "
                    f"{self.max_annual_growth:.3f} but justified by recent M&A"
                ),
            )
        return RuleResult(
            passed=False,
            reason=(
                f"avg share-count growth {avg_growth:.3f} > maximum "
                f"{self.max_annual_growth:.3f} without M&A justification"
            ),
        )


@register
class AuditorChangesAndLateFilings(Rule):
    """Trap detector: recent auditor changes or late SEC filings (spec §6.4).

    A best-effort governance flag built on SEC data when present. An auditor
    change or late filing is a red flag and eliminates the company. The flags are
    ``None`` when the datum is unavailable: a data gap is *not* held against the
    company (it passes), so the rule only ever eliminates on a positively-known
    adverse signal.
    """

    name = "auditor_changes_and_late_filings"

    def evaluate(
        self, company: CompanyData, benchmarks: IndustryBenchmarks
    ) -> RuleResult:
        if company.auditor_changed is True:
            return RuleResult(passed=False, reason="recent auditor change flagged")
        if company.late_filings is True:
            return RuleResult(passed=False, reason="recent late SEC filings flagged")
        return RuleResult(
            passed=True, reason="no auditor change or late filing flagged"
        )
