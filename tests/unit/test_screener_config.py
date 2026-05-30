"""Unit tests for the YAML screener-config loader (spec §6.6, issue M3.7).

Covers: loading the bundled ``damodaran_value`` preset and checking it matches
the spec §6 defaults, rejecting malformed YAML, and rejecting an unknown rule
name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.screener.config import (
    QualityGates,
    Ranking,
    RuleSpec,
    ScreenerConfig,
    TrapDetection,
    ValueIndicators,
    load_screener_config,
)
from bot.screener.ranking import RankingWeights
from bot.screener.rules import (
    ExcludeSectors,
    FCFYieldAbove,
    MaxNetDebtToEBITDA,
    MinMarketCap,
    ROICAboveSectorWACC,
    Rule,
)

PRESET_PATH = Path(__file__).resolve().parents[2] / "config" / "presets" / "damodaran_value.yaml"


# --------------------------------------------------------------------------- #
# Loading the bundled preset.
# --------------------------------------------------------------------------- #


def test_preset_file_exists() -> None:
    assert PRESET_PATH.is_file(), f"missing preset at {PRESET_PATH}"


def test_load_preset_returns_screener_config() -> None:
    config = load_screener_config(PRESET_PATH)
    assert isinstance(config, ScreenerConfig)
    assert config.name == "damodaran_value"
    assert isinstance(config.quality_gates, QualityGates)
    assert isinstance(config.value_indicators, ValueIndicators)
    assert isinstance(config.trap_detection, TrapDetection)
    assert isinstance(config.ranking, Ranking)


def test_preset_lists_all_three_layers() -> None:
    config = load_screener_config(PRESET_PATH)
    assert len(config.quality_gates.rules) == 7
    assert len(config.value_indicators.rules) == 4
    assert len(config.trap_detection.rules) == 6


def test_preset_rule_names_resolve_to_registered_classes() -> None:
    config = load_screener_config(PRESET_PATH)
    for spec in config.rule_specs():
        cls = spec.resolve()
        assert issubclass(cls, Rule)


def test_preset_builds_concrete_rule_instances() -> None:
    config = load_screener_config(PRESET_PATH)
    gates = config.quality_gates.build()
    assert all(isinstance(g, Rule) for g in gates)
    # Order is preserved and params are wired into the constructor.
    market_cap = gates[0]
    assert isinstance(market_cap, MinMarketCap)
    assert market_cap.minimum_usd == pytest.approx(100_000_000.0)


def test_preset_params_match_spec_defaults() -> None:
    config = load_screener_config(PRESET_PATH)
    by_name = {spec.name: spec for spec in config.rule_specs()}

    net_debt = MaxNetDebtToEBITDA(**by_name["max_net_debt_to_ebitda"].params)
    assert net_debt.maximum == pytest.approx(4.0)

    excluded = ExcludeSectors(**by_name["exclude_sectors"].params)
    assert excluded.excluded == ("bank", "insurance")

    fcf = FCFYieldAbove(**by_name["fcf_yield_above"].params)
    assert fcf.minimum == pytest.approx(0.08)


def test_preset_rule_with_no_params_uses_constructor_defaults() -> None:
    config = load_screener_config(PRESET_PATH)
    by_name = {spec.name: spec for spec in config.rule_specs()}
    # roic_above_sector_wacc has no params block in the preset.
    assert by_name["roic_above_sector_wacc"].params == {}
    built = by_name["roic_above_sector_wacc"].build()
    assert isinstance(built, ROICAboveSectorWACC)


def test_preset_ranking_weights_match_spec_defaults() -> None:
    config = load_screener_config(PRESET_PATH)
    weights = config.ranking.weights
    assert isinstance(weights, RankingWeights)
    assert weights.value == pytest.approx(0.40)
    assert weights.quality == pytest.approx(0.30)
    assert weights.growth == pytest.approx(0.20)
    assert weights.margin_of_safety == pytest.approx(0.10)


# --------------------------------------------------------------------------- #
# Rejecting bad input.
# --------------------------------------------------------------------------- #


def test_malformed_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: deep_value\nquality_gates: [this, is, not, a, mapping]\n")
    with pytest.raises(Exception):  # noqa: B017  (pydantic ValidationError)
        load_screener_config(bad)


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_screener_config(bad)


def test_empty_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "empty.yaml"
    bad.write_text("")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_screener_config(bad)


def test_unknown_rule_name_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "unknown.yaml"
    bad.write_text(
        "name: custom\n"
        "quality_gates:\n"
        "  rules:\n"
        "    - name: this_rule_does_not_exist\n"
    )
    with pytest.raises(KeyError, match="this_rule_does_not_exist"):
        load_screener_config(bad)


def test_unknown_rule_in_value_layer_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "unknown_value.yaml"
    bad.write_text(
        "name: custom\n"
        "value_indicators:\n"
        "  rules:\n"
        "    - name: nope\n"
    )
    with pytest.raises(KeyError, match="nope"):
        load_screener_config(bad)


def test_missing_name_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "noname.yaml"
    bad.write_text("quality_gates:\n  rules: []\n")
    with pytest.raises(Exception):  # noqa: B017  (pydantic ValidationError: name required)
        load_screener_config(bad)


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "extra.yaml"
    bad.write_text("name: x\nbogus_section:\n  foo: bar\n")
    with pytest.raises(Exception):  # noqa: B017  (extra=forbid)
        load_screener_config(bad)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_screener_config(tmp_path / "does_not_exist.yaml")


# --------------------------------------------------------------------------- #
# RuleSpec unit behaviour.
# --------------------------------------------------------------------------- #


def test_rulespec_resolve_unknown_raises() -> None:
    spec = RuleSpec(name="not_a_rule")
    with pytest.raises(KeyError, match="not_a_rule"):
        spec.resolve()


def test_rulespec_build_passes_params() -> None:
    spec = RuleSpec(name="min_market_cap", params={"minimum_usd": 5.0e8})
    built = spec.build()
    assert isinstance(built, MinMarketCap)
    assert built.minimum_usd == pytest.approx(5.0e8)
