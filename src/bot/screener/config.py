"""YAML config loader for the screener (M3.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# Import rule modules to ensure the registry is populated before validation.
import bot.screener.trap_rules  # noqa: F401 - registers trap detection rules
from bot.screener.ranking import RankingWeights
from bot.screener.rules import get_rule


class RuleConfig(BaseModel):
    name: str
    args: dict[str, Any] = {}


class QualityGates(BaseModel):
    rules: list[RuleConfig]


class ValueIndicators(BaseModel):
    rules: list[RuleConfig]
    min_pass: int = 1


class TrapDetection(BaseModel):
    rules: list[RuleConfig]


class Ranking(BaseModel):
    weights: RankingWeights = Field(default_factory=RankingWeights)


class ScreenerConfig(BaseModel):
    quality_gates: QualityGates
    value_indicators: ValueIndicators
    trap_detection: TrapDetection
    ranking: Ranking = Field(default_factory=Ranking)


def load_screener_config(path: Path | str) -> ScreenerConfig:
    """Load and validate a screener YAML config file.

    Resolves every rule name against the global registry.

    Raises:
        yaml.YAMLError: file is not valid YAML.
        pydantic.ValidationError: YAML structure doesn't match the schema.
        KeyError: a rule name is not present in the registry.
    """
    with Path(path).open() as fh:
        raw: Any = yaml.safe_load(fh)

    config = ScreenerConfig.model_validate(raw)

    all_rule_configs = (
        config.quality_gates.rules + config.value_indicators.rules + config.trap_detection.rules
    )
    for rule_cfg in all_rule_configs:
        get_rule(rule_cfg.name)

    return config
