"""Unit tests for the M3.7 YAML screener config loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bot.screener.config import (
    QualityGates,
    RuleConfig,
    ScreenerConfig,
    TrapDetection,
    ValueIndicators,
    load_screener_config,
)

REPO_ROOT = Path(__file__).parent.parent.parent
PRESET_PATH = REPO_ROOT / "config" / "presets" / "damodaran_value.yaml"


# ---------------------------------------------------------------------------
# Preset loading
# ---------------------------------------------------------------------------


def test_load_damodaran_value_preset_succeeds() -> None:
    config = load_screener_config(PRESET_PATH)
    assert isinstance(config, ScreenerConfig)


def test_preset_quality_gates_count() -> None:
    config = load_screener_config(PRESET_PATH)
    assert len(config.quality_gates.rules) == 7


def test_preset_quality_gates_names() -> None:
    config = load_screener_config(PRESET_PATH)
    names = [r.name for r in config.quality_gates.rules]
    assert "min_market_cap" in names
    assert "min_years_history" in names
    assert "exclude_sectors" in names
    assert "max_net_debt_to_ebitda" in names
    assert "min_interest_coverage" in names
    assert "positive_operating_cashflow" in names
    assert "max_goodwill_to_assets" in names


def test_preset_value_indicators_count() -> None:
    config = load_screener_config(PRESET_PATH)
    assert len(config.value_indicators.rules) == 4


def test_preset_value_indicators_min_pass() -> None:
    config = load_screener_config(PRESET_PATH)
    assert config.value_indicators.min_pass == 1


def test_preset_trap_detection_count() -> None:
    config = load_screener_config(PRESET_PATH)
    assert len(config.trap_detection.rules) == 6


def test_preset_trap_detection_names() -> None:
    config = load_screener_config(PRESET_PATH)
    names = [r.name for r in config.trap_detection.rules]
    assert "revenue_not_declining" in names
    assert "roic_above_sector_wacc" in names
    assert "auditor_changes_and_late_filings" in names


def test_preset_ranking_weights_match_spec() -> None:
    config = load_screener_config(PRESET_PATH)
    w = config.ranking.weights
    assert w.value == pytest.approx(0.40)
    assert w.quality == pytest.approx(0.30)
    assert w.growth == pytest.approx(0.20)
    assert w.margin_of_safety == pytest.approx(0.10)


def test_preset_rule_args_preserved() -> None:
    config = load_screener_config(PRESET_PATH)
    min_cap = next(r for r in config.quality_gates.rules if r.name == "min_market_cap")
    assert min_cap.args["min_usd"] == pytest.approx(100_000_000)

    fcf = next(r for r in config.value_indicators.rules if r.name == "fcf_yield_above")
    assert fcf.args["min_yield"] == pytest.approx(0.08)


def test_preset_roic_rule_has_no_args() -> None:
    config = load_screener_config(PRESET_PATH)
    roic = next(r for r in config.trap_detection.rules if r.name == "roic_above_sector_wacc")
    assert roic.args == {}


# ---------------------------------------------------------------------------
# Malformed YAML rejected
# ---------------------------------------------------------------------------


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("[unclosed\n")
    with pytest.raises(yaml.YAMLError):
        load_screener_config(bad)


def test_wrong_schema_raises(tmp_path: Path) -> None:
    """Valid YAML that doesn't match the ScreenerConfig schema."""
    bad = tmp_path / "wrong.yaml"
    bad.write_text("just_a_string: true\n")
    with pytest.raises(ValidationError):
        load_screener_config(bad)


def test_missing_required_section_raises(tmp_path: Path) -> None:
    """YAML missing a required top-level key."""
    bad = tmp_path / "missing.yaml"
    bad.write_text("quality_gates:\n  rules: []\n")
    with pytest.raises(ValidationError):
        load_screener_config(bad)


# ---------------------------------------------------------------------------
# Unknown rule name rejected
# ---------------------------------------------------------------------------


def test_unknown_rule_in_quality_gates_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "unknown.yaml"
    cfg.write_text(
        "quality_gates:\n"
        "  rules:\n"
        "    - name: nonexistent_rule\n"
        "value_indicators:\n"
        "  rules:\n"
        "    - name: fcf_yield_above\n"
        "trap_detection:\n"
        "  rules:\n"
        "    - name: roic_above_sector_wacc\n"
        "ranking:\n"
        "  weights:\n"
        "    value: 0.40\n"
        "    quality: 0.30\n"
        "    growth: 0.20\n"
        "    margin_of_safety: 0.10\n"
    )
    with pytest.raises(KeyError):
        load_screener_config(cfg)


def test_unknown_rule_in_value_indicators_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "unknown2.yaml"
    cfg.write_text(
        "quality_gates:\n"
        "  rules:\n"
        "    - name: min_market_cap\n"
        "value_indicators:\n"
        "  rules:\n"
        "    - name: totally_made_up\n"
        "trap_detection:\n"
        "  rules:\n"
        "    - name: roic_above_sector_wacc\n"
        "ranking:\n"
        "  weights:\n"
        "    value: 0.40\n"
        "    quality: 0.30\n"
        "    growth: 0.20\n"
        "    margin_of_safety: 0.10\n"
    )
    with pytest.raises(KeyError):
        load_screener_config(cfg)


def test_unknown_rule_in_trap_detection_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "unknown3.yaml"
    cfg.write_text(
        "quality_gates:\n"
        "  rules:\n"
        "    - name: min_market_cap\n"
        "value_indicators:\n"
        "  rules:\n"
        "    - name: fcf_yield_above\n"
        "trap_detection:\n"
        "  rules:\n"
        "    - name: ghost_rule\n"
        "ranking:\n"
        "  weights:\n"
        "    value: 0.40\n"
        "    quality: 0.30\n"
        "    growth: 0.20\n"
        "    margin_of_safety: 0.10\n"
    )
    with pytest.raises(KeyError):
        load_screener_config(cfg)


# ---------------------------------------------------------------------------
# Pydantic model construction (no file I/O)
# ---------------------------------------------------------------------------


def test_rule_config_defaults_empty_args() -> None:
    rc = RuleConfig(name="some_rule")
    assert rc.args == {}


def test_screener_config_ranking_defaults_to_spec_weights() -> None:
    cfg = ScreenerConfig(
        quality_gates=QualityGates(rules=[]),
        value_indicators=ValueIndicators(rules=[]),
        trap_detection=TrapDetection(rules=[]),
    )
    assert cfg.ranking.weights.value == pytest.approx(0.40)
    assert cfg.ranking.weights.quality == pytest.approx(0.30)
    assert cfg.ranking.weights.growth == pytest.approx(0.20)
    assert cfg.ranking.weights.margin_of_safety == pytest.approx(0.10)
