"""Declarative YAML configuration for the mechanical screener (spec §6.6).

The screener (Capa B) is configured entirely from a YAML file (spec §6.6): each
rule is referenced *by name* and maps to a registered :class:`~bot.screener.rules.Rule`
subclass, with optional per-rule ``params`` that are passed straight to the
class constructor. This keeps the YAML free of Python imports and lets the same
rule be reused with different thresholds across presets (``damodaran_value``,
``deep_value``, ``qarp`` — spec §6.6).

The schema mirrors the three eliminatory layers plus the ranking blend:

- ``quality_gates`` (spec §6.2) — eliminatory floors.
- ``value_indicators`` (spec §6.3) — at least one must pass.
- ``trap_detection`` (spec §6.4) — eliminatory "cheap for a reason" filters.
- ``ranking`` (spec §6.5) — the value/quality/growth/margin-of-safety weights.

:func:`load_screener_config` reads a YAML file, validates its shape with the
Pydantic models below, and resolves every rule ``name`` against the rule
registry — raising on an unknown rule so a typo fails loudly at load time rather
than silently dropping a filter. Importing this module imports
:mod:`bot.screener.rules`, which is what populates the registry; resolution
therefore always sees the full set of built-in rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Importing rules for its side effect: every built-in Rule registers itself with
# the registry at import time, so name resolution below sees the full set.
from bot.screener import rules as _rules  # noqa: F401  (import for registration)
from bot.screener.ranking import RankingWeights
from bot.screener.rules import Rule, get_rule


class RuleSpec(BaseModel):
    """A single rule reference in the YAML: a registered ``name`` plus ``params``.

    ``params`` is a free-form mapping passed verbatim as keyword arguments to the
    resolved rule class's constructor (e.g. ``{"minimum_usd": 1.0e8}`` for
    ``min_market_cap``). It defaults to empty so a rule used with its built-in
    defaults can be referenced by name alone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    def resolve(self) -> type[Rule]:
        """Return the registered rule class for ``name``.

        Raises:
            KeyError: if no rule is registered under ``name`` (re-raised from
                :func:`bot.screener.rules.get_rule`).
        """
        return get_rule(self.name)

    def build(self) -> Rule:
        """Instantiate the resolved rule class with this spec's ``params``.

        Raises:
            KeyError: if ``name`` is not registered.
            TypeError: if ``params`` does not match the rule constructor.
        """
        return self.resolve()(**self.params)


class _RuleLayer(BaseModel):
    """A named layer of the screener holding an ordered list of rule specs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: tuple[RuleSpec, ...] = Field(default_factory=tuple)

    def build(self) -> list[Rule]:
        """Instantiate every rule in declaration order."""
        return [spec.build() for spec in self.rules]


class QualityGates(_RuleLayer):
    """Eliminatory quality-gate rules (spec §6.2)."""


class ValueIndicators(_RuleLayer):
    """Value-indicator rules; at least one must pass (spec §6.3)."""


class TrapDetection(_RuleLayer):
    """Eliminatory trap-detection rules (spec §6.4)."""


class Ranking(BaseModel):
    """Ranking-score configuration: the four sub-score weights (spec §6.5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: RankingWeights = Field(default_factory=RankingWeights)


class ScreenerConfig(BaseModel):
    """Top-level screener configuration parsed from a YAML preset (spec §6.6).

    Bundles the three eliminatory layers and the ranking blend under a preset
    ``name`` (e.g. ``damodaran_value``). Every nested rule reference is validated
    *and* resolved against the registry at load time by
    :func:`load_screener_config`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    quality_gates: QualityGates = Field(default_factory=QualityGates)
    value_indicators: ValueIndicators = Field(default_factory=ValueIndicators)
    trap_detection: TrapDetection = Field(default_factory=TrapDetection)
    ranking: Ranking = Field(default_factory=Ranking)

    def rule_specs(self) -> list[RuleSpec]:
        """Return every rule spec across the three layers, in layer order."""
        return [
            *self.quality_gates.rules,
            *self.value_indicators.rules,
            *self.trap_detection.rules,
        ]

    def resolve_rules(self) -> None:
        """Resolve every referenced rule name against the registry.

        Raises:
            KeyError: on the first rule whose ``name`` is not registered.
        """
        for spec in self.rule_specs():
            spec.resolve()


def load_screener_config(path: Path) -> ScreenerConfig:
    """Load and fully validate a screener YAML preset (spec §6.6).

    The file is parsed as a single YAML mapping, validated against
    :class:`ScreenerConfig` (so a malformed shape is rejected), and every rule
    ``name`` is resolved against the rule registry (so an unknown rule is
    rejected). On success the returned config is guaranteed loadable into live
    rule instances via :meth:`ScreenerConfig.build`-style calls.

    Args:
        path: Path to the YAML preset.

    Returns:
        The validated, registry-resolved :class:`ScreenerConfig`.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the file is not a YAML mapping (e.g. empty, a list, or a
            scalar) — surfaced as a clear error rather than a Pydantic internal.
        pydantic.ValidationError: if the mapping does not match the schema.
        KeyError: if any referenced rule name is not registered.
    """
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"screener config {path} must be a YAML mapping, got {type(raw).__name__}"
        )
    config = ScreenerConfig.model_validate(raw)
    config.resolve_rules()
    return config


__all__ = [
    "QualityGates",
    "Ranking",
    "RuleSpec",
    "ScreenerConfig",
    "TrapDetection",
    "ValidationError",
    "ValueIndicators",
    "load_screener_config",
]
