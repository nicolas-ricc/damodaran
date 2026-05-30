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
