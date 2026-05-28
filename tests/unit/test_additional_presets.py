"""Unit tests for M3.9 additional presets: deep_value and qarp."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.screener.config import RuleConfig, ScreenerConfig, load_screener_config
from bot.screener.rules import CompanyData, IndustryBenchmarks, Rule, get_rule

REPO_ROOT = Path(__file__).parent.parent.parent
DEEP_VALUE_PATH = REPO_ROOT / "config" / "presets" / "deep_value.yaml"
QARP_PATH = REPO_ROOT / "config" / "presets" / "qarp.yaml"
DAMODARAN_VALUE_PATH = REPO_ROOT / "config" / "presets" / "damodaran_value.yaml"

_DAMODARAN_TRAP_RULE_NAMES = [
    "revenue_not_declining",
    "operating_margin_not_contracting",
    "roic_above_sector_wacc",
    "sloan_accruals_below",
    "share_count_not_diluting",
    "auditor_changes_and_late_filings",
]


def _make_rule(rule_cfg: RuleConfig) -> Rule:
    return get_rule(rule_cfg.name)(**rule_cfg.args)  # type: ignore[call-arg, return-value]


def _screen(
    config: ScreenerConfig,
    companies: list[CompanyData],
    benchmarks: IndustryBenchmarks,
) -> set[str]:
    """Return tickers of companies passing quality_gates + value_indicators + trap_detection."""
    passing: set[str] = set()
    for company in companies:
        if not all(
            _make_rule(r).evaluate(company, benchmarks).passed
            for r in config.quality_gates.rules
        ):
            continue
        vi_count = sum(
            1
            for r in config.value_indicators.rules
            if _make_rule(r).evaluate(company, benchmarks).passed
        )
        if vi_count < config.value_indicators.min_pass:
            continue
        if not all(
            _make_rule(r).evaluate(company, benchmarks).passed
            for r in config.trap_detection.rules
        ):
            continue
        passing.add(company.ticker)
    return passing


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------


def test_deep_value_preset_loads() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    assert isinstance(config, ScreenerConfig)


def test_qarp_preset_loads() -> None:
    config = load_screener_config(QARP_PATH)
    assert isinstance(config, ScreenerConfig)


# ---------------------------------------------------------------------------
# deep_value: attribute contracts
# ---------------------------------------------------------------------------


def test_deep_value_value_indicators_min_pass() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    assert config.value_indicators.min_pass == 2


def test_deep_value_cheapness_multiples_at_0_5() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    pe_rule = next(r for r in config.value_indicators.rules if r.name == "pe_below_industry_multiple")
    assert pe_rule.args["multiple"] == pytest.approx(0.5)
    ev_rule = next(
        r for r in config.value_indicators.rules if r.name == "ev_ebitda_below_industry_multiple"
    )
    assert ev_rule.args["multiple"] == pytest.approx(0.5)


def test_deep_value_fcf_yield_threshold_at_12_pct() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    fcf_rule = next(r for r in config.value_indicators.rules if r.name == "fcf_yield_above")
    assert fcf_rule.args["min_yield"] == pytest.approx(0.12)


def test_deep_value_relaxes_ocf_consistency_threshold() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    ocf_rule = next(
        r for r in config.quality_gates.rules if r.name == "positive_operating_cashflow"
    )
    assert ocf_rule.args["min_positive_years"] == 3


def test_deep_value_ranking_tilts_to_value() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    assert config.ranking.weights.value == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# qarp: attribute contracts
# ---------------------------------------------------------------------------


def test_qarp_value_indicators_min_pass() -> None:
    config = load_screener_config(QARP_PATH)
    assert config.value_indicators.min_pass == 1


def test_qarp_cheapness_multiples_at_0_9() -> None:
    config = load_screener_config(QARP_PATH)
    pe_rule = next(r for r in config.value_indicators.rules if r.name == "pe_below_industry_multiple")
    assert pe_rule.args["multiple"] == pytest.approx(0.9)


def test_qarp_fcf_yield_threshold_at_5_pct() -> None:
    config = load_screener_config(QARP_PATH)
    fcf_rule = next(r for r in config.value_indicators.rules if r.name == "fcf_yield_above")
    assert fcf_rule.args["min_yield"] == pytest.approx(0.05)


def test_qarp_tighter_leverage_gate() -> None:
    config = load_screener_config(QARP_PATH)
    debt_rule = next(
        r for r in config.quality_gates.rules if r.name == "max_net_debt_to_ebitda"
    )
    assert debt_rule.args["max_ratio"] == pytest.approx(2.0)


def test_qarp_tighter_cashflow_consistency() -> None:
    config = load_screener_config(QARP_PATH)
    ocf_rule = next(
        r for r in config.quality_gates.rules if r.name == "positive_operating_cashflow"
    )
    assert ocf_rule.args["min_positive_years"] == 5


def test_qarp_ranking_tilts_to_quality() -> None:
    config = load_screener_config(QARP_PATH)
    assert config.ranking.weights.quality == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# Both presets share trap detection with damodaran_value
# ---------------------------------------------------------------------------


def test_deep_value_trap_rules_match_damodaran_value() -> None:
    config = load_screener_config(DEEP_VALUE_PATH)
    assert [r.name for r in config.trap_detection.rules] == _DAMODARAN_TRAP_RULE_NAMES


def test_qarp_trap_rules_match_damodaran_value() -> None:
    config = load_screener_config(QARP_PATH)
    assert [r.name for r in config.trap_detection.rules] == _DAMODARAN_TRAP_RULE_NAMES


# ---------------------------------------------------------------------------
# Fixture universe — different shortlists on the same three candidates
#
#   VERY_CHEAP       passes damodaran_value + deep_value; fails qarp
#                    (net_debt/EBITDA = 3.5 > qarp’s 2.0 ceiling)
#   HIGH_QUALITY     fails damodaran_value + deep_value (no value indicator
#                    passes at 0.7× / 0.5×); passes qarp (all four at 0.9×)
#   MODERATELY_CHEAP passes damodaran_value + qarp; fails deep_value
#                    (not cheap enough for 0.5× on ≥ 2 indicators)
# ---------------------------------------------------------------------------

_BENCHMARKS = IndustryBenchmarks(
    industry="Technology",
    pe=20.0,
    ev_ebitda=14.0,
    pbv=5.0,
    roe=0.15,
    wacc=0.08,
)

# Trap-clean baseline spread into every fixture company via **.
_TRAP_BASE = {
    "revenue_3y": [1.0e9, 1.05e9, 1.10e9],
    "op_margin_3y": [0.15, 0.155, 0.16],
    "roic": 0.15,
    "net_income": 100_000_000.0,
    "operating_cashflow": 120_000_000.0,
    "shares_diluted_3y": [50_000_000.0, 50_500_000.0, 51_000_000.0],
    "auditor_changed": False,
    "has_late_filings": False,
}

_VERY_CHEAP = CompanyData(
    ticker="VERY_CHEAP",
    market_cap=500_000_000.0,
    years_history=7,
    sector="Technology",
    net_debt=7_000_000_000.0,
    ebitda=2_000_000_000.0,
    ebit=400_000_000.0,
    interest_expense=80_000_000.0,
    operating_cashflow_history=[1e8, 1.1e8, 1.2e8, 1.3e8, 1.4e8],
    goodwill=200_000_000.0,
    total_assets=2_000_000_000.0,
    pe_ratio=6.0,
    ev_ebitda=4.0,
    pbv=1.5,
    roe=0.25,
    fcf_yield=0.15,
    **_TRAP_BASE,  # type: ignore[arg-type]
)

_HIGH_QUALITY = CompanyData(
    ticker="HIGH_QUALITY",
    market_cap=2_000_000_000.0,
    years_history=10,
    sector="Technology",
    net_debt=1_000_000_000.0,
    ebitda=1_000_000_000.0,
    ebit=300_000_000.0,
    interest_expense=50_000_000.0,
    operating_cashflow_history=[2e8, 2.1e8, 2.2e8, 2.3e8, 2.4e8],
    goodwill=300_000_000.0,
    total_assets=4_000_000_000.0,
    pe_ratio=17.0,
    ev_ebitda=10.5,
    pbv=4.4,
    roe=0.20,
    fcf_yield=0.06,
    **_TRAP_BASE,  # type: ignore[arg-type]
)

_MODERATELY_CHEAP = CompanyData(
    ticker="MODERATELY_CHEAP",
    market_cap=800_000_000.0,
    years_history=7,
    sector="Technology",
    net_debt=1_500_000_000.0,
    ebitda=1_000_000_000.0,
    ebit=200_000_000.0,
    interest_expense=40_000_000.0,
    operating_cashflow_history=[1e8, 1.1e8, 1.2e8, 1.3e8, 1.4e8],
    goodwill=100_000_000.0,
    total_assets=2_000_000_000.0,
    pe_ratio=13.0,
    ev_ebitda=7.5,
    pbv=3.0,
    roe=0.20,
    fcf_yield=0.09,
    **_TRAP_BASE,  # type: ignore[arg-type]
)

_UNIVERSE = [_VERY_CHEAP, _HIGH_QUALITY, _MODERATELY_CHEAP]


def test_deep_value_shortlist_differs_from_damodaran_value() -> None:
    dam_cfg = load_screener_config(DAMODARAN_VALUE_PATH)
    dv_cfg = load_screener_config(DEEP_VALUE_PATH)
    dam_shortlist = _screen(dam_cfg, _UNIVERSE, _BENCHMARKS)
    dv_shortlist = _screen(dv_cfg, _UNIVERSE, _BENCHMARKS)
    assert dv_shortlist != dam_shortlist
    assert dv_shortlist == {"VERY_CHEAP"}
    assert dam_shortlist == {"VERY_CHEAP", "MODERATELY_CHEAP"}


def test_qarp_shortlist_differs_from_damodaran_value() -> None:
    dam_cfg = load_screener_config(DAMODARAN_VALUE_PATH)
    qarp_cfg = load_screener_config(QARP_PATH)
    dam_shortlist = _screen(dam_cfg, _UNIVERSE, _BENCHMARKS)
    qarp_shortlist = _screen(qarp_cfg, _UNIVERSE, _BENCHMARKS)
    assert qarp_shortlist != dam_shortlist
    assert qarp_shortlist == {"HIGH_QUALITY", "MODERATELY_CHEAP"}
