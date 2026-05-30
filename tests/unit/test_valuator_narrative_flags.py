"""Unit tests for the five quantitative narrative flags (issue #15 / M4.5).

Spec §7.5: five proxies for story↔numbers consistency, each returning a
``{green, yellow, red}`` verdict with a reason. Each flag is a pure function over
the DCF inputs/output plus a :class:`NarrativeContext` of the extra,
flag-specific data. These tests cover every color outcome of every flag and the
aggregator.

Where a flag depends on the DCF *output* (growth-reinvestment, terminal-value
share) the expected color is produced by running the real :func:`dcf` over a
fixture chosen to land in that color's band, so the test pins behaviour against
the actual arithmetic, not a hand-built ``DCFResult``.
"""

from __future__ import annotations

import dataclasses

import pytest

from bot.valuator.dcf import Assumptions, DCFResult, Financials, dcf
from bot.valuator.narrative_flags import (
    FlagColor,
    NarrativeContext,
    NarrativeFlag,
    beta_business_risk_flag,
    country_exposure_flag,
    growth_reinvestment_flag,
    narrative_flags,
    story_margin_flag,
    terminal_value_share_flag,
)


def _financials() -> Financials:
    return Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)


def _assumptions(**overrides: object) -> Assumptions:
    base = dict(
        revenue_growth=(0.10, 0.08, 0.06, 0.04, 0.02),
        operating_margin=(0.20, 0.20, 0.20, 0.20, 0.20),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.11,
        pretax_cost_of_debt=0.05,
        equity_weight=0.8,
        debt_weight=0.2,
    )
    base.update(overrides)
    return Assumptions(**base)  # type: ignore[arg-type]


def _result(financials: Financials, assumptions: Assumptions) -> DCFResult:
    return dcf(financials, assumptions)


def _ctx(**overrides: object) -> NarrativeContext:
    return NarrativeContext(**overrides)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 1. Story-margin consistency                                                 #
# --------------------------------------------------------------------------- #


def test_story_margin_yellow_when_high_growth_above_sector() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(
            story_type="high-growth",
            company_operating_margin=0.30,
            sector_operating_margin=0.20,
        ),
    )
    assert flag.color is FlagColor.YELLOW
    assert flag.name == "story_margin"
    assert "high-growth" in flag.reason


def test_story_margin_green_when_high_growth_at_or_below_sector() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(
            story_type="high-growth",
            company_operating_margin=0.18,
            sector_operating_margin=0.20,
        ),
    )
    assert flag.color is FlagColor.GREEN


def test_story_margin_green_for_other_story_types() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(
            story_type="mature-stable",
            company_operating_margin=0.40,
            sector_operating_margin=0.20,
        ),
    )
    assert flag.color is FlagColor.GREEN


def test_story_margin_green_when_inputs_missing() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin, asm, _result(fin, asm), _ctx(story_type="high-growth")
    )
    assert flag.color is FlagColor.GREEN
    assert "unavailable" in flag.reason


# --------------------------------------------------------------------------- #
# 2. Growth-reinvestment consistency                                          #
# --------------------------------------------------------------------------- #


def test_growth_reinvestment_red_when_reinvestment_exceeds_nopat() -> None:
    # Thin margins + low sales_to_capital + high growth => reinvestment > NOPAT
    # in the explicit years, so FCFF goes negative (growth unfunded).
    fin = _financials()
    asm = _assumptions(
        revenue_growth=(0.40, 0.40, 0.40, 0.40, 0.40),
        operating_margin=(0.05, 0.05, 0.05, 0.05, 0.05),
        sales_to_capital=0.5,
    )
    result = _result(fin, asm)
    assert any(p.fcff < 0.0 for p in result.projections)
    flag = growth_reinvestment_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.RED
    assert flag.name == "growth_reinvestment"


def test_growth_reinvestment_yellow_when_reinvestment_stretches_nopat() -> None:
    # Reinvestment eats > 90% of NOPAT but stays below it (positive FCFF).
    fin = _financials()
    asm = _assumptions(
        revenue_growth=(0.077, 0.077, 0.077, 0.077, 0.077),
        operating_margin=(0.10, 0.10, 0.10, 0.10, 0.10),
        sales_to_capital=1.0,
    )
    result = _result(fin, asm)
    assert all(p.fcff >= 0.0 for p in result.projections)
    worst = max(p.reinvestment / p.nopat for p in result.projections if p.nopat > 0)
    assert 0.90 < worst < 1.0
    flag = growth_reinvestment_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.YELLOW


def test_growth_reinvestment_red_when_nopat_non_positive_but_reinvesting() -> None:
    # Zero operating margin => NOPAT == 0 while positive growth still demands
    # reinvestment: growth is wholly unfunded by earnings.
    fin = _financials()
    asm = _assumptions(
        revenue_growth=(0.10, 0.10, 0.10, 0.10, 0.10),
        operating_margin=(0.0, 0.0, 0.0, 0.0, 0.0),
        sales_to_capital=2.0,
    )
    result = _result(fin, asm)
    assert all(p.nopat == 0.0 for p in result.projections)
    assert all(p.reinvestment > 0.0 for p in result.projections)
    flag = growth_reinvestment_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.RED


def test_growth_reinvestment_green_when_comfortably_funded() -> None:
    fin = _financials()
    asm = _assumptions()  # 20% margins, modest growth, sales_to_capital 2.0
    result = _result(fin, asm)
    flag = growth_reinvestment_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.GREEN


# --------------------------------------------------------------------------- #
# 3. Beta vs business risk                                                     #
# --------------------------------------------------------------------------- #


def test_beta_business_risk_yellow_when_defensive_beta_high_leverage() -> None:
    fin = _financials()
    asm = _assumptions(equity_weight=0.5, debt_weight=0.5)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=0.8, operating_leverage=2.0),
    )
    assert flag.color is FlagColor.YELLOW
    assert flag.name == "beta_business_risk"


def test_beta_business_risk_green_when_beta_high() -> None:
    fin = _financials()
    asm = _assumptions(equity_weight=0.5, debt_weight=0.5)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=1.2, operating_leverage=2.0),
    )
    assert flag.color is FlagColor.GREEN


def test_beta_business_risk_green_when_low_leverage() -> None:
    fin = _financials()
    asm = _assumptions(equity_weight=0.9, debt_weight=0.1)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=0.8, operating_leverage=1.0),
    )
    assert flag.color is FlagColor.GREEN


def test_beta_business_risk_green_when_inputs_missing() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = beta_business_risk_flag(
        fin, asm, _result(fin, asm), _ctx(sector_beta=0.8)
    )
    assert flag.color is FlagColor.GREEN
    assert "unavailable" in flag.reason


# --------------------------------------------------------------------------- #
# 4. Terminal value share > 80%                                               #
# --------------------------------------------------------------------------- #


def test_terminal_value_share_yellow_above_ceiling() -> None:
    # Flat low explicit growth + thin discounting gap pushes the perpetuity to
    # dominate enterprise value.
    fin = _financials()
    asm = _assumptions(
        revenue_growth=(0.01, 0.01, 0.01, 0.01, 0.01),
        terminal_growth=0.04,
        cost_of_equity=0.07,
        pretax_cost_of_debt=0.04,
    )
    result = _result(fin, asm)
    assert result.terminal_value_share > 0.80
    flag = terminal_value_share_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.YELLOW
    assert flag.name == "terminal_value_share"


def test_terminal_value_share_green_below_ceiling() -> None:
    fin = _financials()
    asm = _assumptions()
    result = _result(fin, asm)
    assert result.terminal_value_share <= 0.80
    flag = terminal_value_share_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.GREEN


# --------------------------------------------------------------------------- #
# 5. Country exposure vs ERP                                                   #
# --------------------------------------------------------------------------- #


def test_country_exposure_red_when_foreign_and_erp_gap_wide() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.70, erp_weighted=0.09, erp_listing=0.05),
    )
    assert flag.color is FlagColor.RED
    assert flag.name == "country_exposure"
    assert "bps" in flag.reason


def test_country_exposure_green_when_mostly_domestic() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.30, erp_weighted=0.09, erp_listing=0.05),
    )
    assert flag.color is FlagColor.GREEN


def test_country_exposure_green_when_erp_gap_narrow() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.70, erp_weighted=0.055, erp_listing=0.05),
    )
    assert flag.color is FlagColor.GREEN


def test_country_exposure_green_when_inputs_missing() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin, asm, _result(fin, asm), _ctx(foreign_revenue_share=0.70)
    )
    assert flag.color is FlagColor.GREEN
    assert "unavailable" in flag.reason


# --------------------------------------------------------------------------- #
# Aggregator                                                                   #
# --------------------------------------------------------------------------- #


def test_narrative_flags_runs_all_five_in_spec_order() -> None:
    fin = _financials()
    asm = _assumptions()
    flags = narrative_flags(fin, asm, _result(fin, asm), _ctx())
    assert isinstance(flags, tuple)
    assert [f.name for f in flags] == [
        "story_margin",
        "growth_reinvestment",
        "beta_business_risk",
        "terminal_value_share",
        "country_exposure",
    ]
    assert all(isinstance(f, NarrativeFlag) for f in flags)


def test_narrative_flags_surfaces_each_flags_color() -> None:
    fin = _financials()
    asm = _assumptions(
        revenue_growth=(0.40, 0.40, 0.40, 0.40, 0.40),
        operating_margin=(0.05, 0.05, 0.05, 0.05, 0.05),
        sales_to_capital=0.5,
    )
    context = _ctx(
        story_type="high-growth",
        company_operating_margin=0.30,
        sector_operating_margin=0.20,
        foreign_revenue_share=0.70,
        erp_weighted=0.09,
        erp_listing=0.05,
    )
    flags = {f.name: f for f in narrative_flags(fin, asm, _result(fin, asm), context)}
    assert flags["story_margin"].color is FlagColor.YELLOW
    assert flags["growth_reinvestment"].color is FlagColor.RED
    assert flags["country_exposure"].color is FlagColor.RED


def test_narrative_flag_is_immutable() -> None:
    flag = NarrativeFlag(name="x", color=FlagColor.GREEN, reason="ok")
    with pytest.raises(dataclasses.FrozenInstanceError):
        flag.color = FlagColor.RED  # type: ignore[misc]
