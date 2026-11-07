"""Unit tests for the five quantitative narrative flags (issue #15 / M4.5).

Spec §7.5: five proxies for story↔numbers consistency, each returning a
``{green, yellow, red, unknown}`` verdict with a reason. Each flag is a pure function over
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
import inspect
import itertools
from collections.abc import Callable

import pytest

import bot.valuator.narrative_flags as narrative_flags_module
from bot.valuator.dcf import Assumptions, DCFResult, Financials, dcf
from bot.valuator.narrative_flags import (
    FlagColor,
    NarrativeContext,
    NarrativeFlag,
    beta_business_risk_flag,
    country_exposure_flag,
    growth_reinvestment_flag,
    hypergrowth_flags,
    hypergrowth_revenue_scale_flag,
    hypergrowth_story_flag,
    hypergrowth_terminal_roic_flag,
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
    assert flag.reason == (
        "A high-growth story, but the operating margin of 30.0% already exceeds the "
        "sector's 20.0%: little room left for the margin to improve."
    )


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
    assert flag.reason == (
        "A high-growth story with an operating margin of 18.0%, at or below the "
        "sector's 20.0%: there is room for the margin to improve."
    )


def test_story_margin_unknown_when_inputs_missing() -> None:
    # A check that could not run must never read as a pass (spec §7.5).
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin, asm, _result(fin, asm), _ctx(story_type="high-growth")
    )
    assert flag.color is FlagColor.UNKNOWN
    assert flag.reason == (
        "not evaluated: the company's latest operating margin or the sector's "
        "median margin is missing."
    )


def test_story_margin_unknown_when_only_sector_margin_is_missing() -> None:
    # The realised company margin alone cannot decide the check.
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(story_type="high-growth", company_operating_margin=0.30),
    )
    assert flag.color is FlagColor.UNKNOWN


def test_story_margin_still_reaches_yellow_with_a_real_company_margin() -> None:
    # Turning the missing-data branch to UNKNOWN must not amputate the logic: a
    # genuinely divergent realised margin still lands on the yellow verdict.
    fin = _financials()
    asm = _assumptions()
    flag = story_margin_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(
            story_type="high-growth",
            company_operating_margin=0.412,
            sector_operating_margin=0.183,
        ),
    )
    assert flag.color is FlagColor.YELLOW
    assert flag.reason == (
        "A high-growth story, but the operating margin of 41.2% already exceeds the "
        "sector's 18.3%: little room left for the margin to improve."
    )


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
    assert flag.reason == (
        "In at least one year growth needs more reinvestment than after-tax operating "
        "profit (NOPAT) provides, so free cash flow to the firm (FCFF) turns negative."
    )


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
    assert flag.reason == (
        "In year 1 reinvestment takes 95% of after-tax operating profit (NOPAT): "
        "growth is funded, but only just."
    )


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
    assert flag.reason == (
        "Every year the reinvestment growth needs fits within after-tax operating "
        "profit (NOPAT)."
    )


# --------------------------------------------------------------------------- #
# 3. Beta vs business risk                                                     #
# --------------------------------------------------------------------------- #


def test_beta_business_risk_yellow_when_defensive_beta_high_leverage() -> None:
    fin = _financials()
    # Assumptions.debt_weight is the *sector's* WACC weight — deliberately left
    # low here to prove the flag reads context.company_debt_weight instead.
    asm = _assumptions(equity_weight=0.9, debt_weight=0.1)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=0.8, operating_leverage=2.0, company_debt_weight=0.5),
    )
    assert flag.color is FlagColor.YELLOW
    assert flag.name == "beta_business_risk"
    assert flag.reason == (
        "The sector beta of 0.80 is below 1, which looks defensive, but operating "
        "leverage of 2.00 is above 1.5 and debt at 50% of capital is above 40%: the "
        "beta understates the risk."
    )


def test_beta_business_risk_green_when_beta_high() -> None:
    fin = _financials()
    asm = _assumptions(equity_weight=0.5, debt_weight=0.5)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=1.2, operating_leverage=2.0, company_debt_weight=0.5),
    )
    assert flag.color is FlagColor.GREEN
    assert flag.reason == (
        "The sector beta of 1.20 fits operating leverage of 2.00 and debt at 50% of capital."
    )


def test_beta_business_risk_green_when_low_leverage() -> None:
    fin = _financials()
    asm = _assumptions(equity_weight=0.9, debt_weight=0.1)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=0.8, operating_leverage=1.0, company_debt_weight=0.1),
    )
    assert flag.color is FlagColor.GREEN


def test_beta_business_risk_uses_the_company_leverage() -> None:
    # The company is debt-heavy (55%) while its sector's D/E implies a light
    # structure. The flag must read the company's own leverage.
    fin = _financials()
    asm = _assumptions(debt_weight=0.10)
    flag = beta_business_risk_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(sector_beta=0.8, operating_leverage=2.0, company_debt_weight=0.55),
    )
    assert flag.color is FlagColor.YELLOW
    assert "debt at 55% of capital" in flag.reason


def test_beta_business_risk_unknown_without_company_leverage() -> None:
    # It used to read assumptions.debt_weight (the sector's WACC weight) as a
    # stand-in for the company's leverage, so it never went UNKNOWN even when
    # the company's own balance sheet was unavailable. Now it must.
    fin = _financials()
    asm = _assumptions()
    flag = beta_business_risk_flag(
        fin, asm, _result(fin, asm), _ctx(sector_beta=0.8, operating_leverage=2.0)
    )
    assert flag.color is FlagColor.UNKNOWN
    assert flag.reason == (
        "not evaluated: the sector beta, the operating leverage or the company's debt "
        "share is missing."
    )


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
    assert flag.reason == (
        "88% of enterprise value comes from the terminal value, above the 80% ceiling: "
        "the valuation rests almost entirely on the perpetuity."
    )


def test_terminal_value_share_green_below_ceiling() -> None:
    fin = _financials()
    asm = _assumptions()
    result = _result(fin, asm)
    assert result.terminal_value_share <= 0.80
    flag = terminal_value_share_flag(fin, asm, result, _ctx())
    assert flag.color is FlagColor.GREEN
    assert flag.reason == (
        "74% of enterprise value comes from the terminal value, within the 80% ceiling."
    )


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
    assert flag.reason == (
        "70% of revenue is earned abroad and the revenue-weighted equity risk premium "
        "(ERP) of 9.0% is 400 basis points above the listing country's 5.0%, more than "
        "the 300 basis points allowed: the discount rate under-prices country risk."
    )


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
    assert flag.reason == (
        "30% of revenue is earned abroad and the revenue-weighted equity risk premium "
        "(ERP) is 9.0% against 5.0% for the listing country, a gap of 400 basis points."
    )


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


def test_country_exposure_is_unknown_not_green_without_data() -> None:
    # It used to return GREEN with "figures unavailable", which reads as "checked
    # and fine". A check that did not run must not look like a pass.
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin, asm, _result(fin, asm), _ctx(foreign_revenue_share=0.70)
    )
    assert flag.color is FlagColor.UNKNOWN
    assert flag.reason == (
        "not evaluated: it needs revenue by geography and a revenue-weighted equity "
        "risk premium (ERP), and no data source supplies either."
    )


def test_country_exposure_red_when_the_data_is_present() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.70, erp_weighted=0.09, erp_listing=0.045),
    )
    assert flag.color is FlagColor.RED


def test_country_exposure_green_when_the_gap_is_small() -> None:
    fin = _financials()
    asm = _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.70, erp_weighted=0.046, erp_listing=0.045),
    )
    assert flag.color is FlagColor.GREEN


# --------------------------------------------------------------------------- #
# Aggregator                                                                   #
# --------------------------------------------------------------------------- #


_BASE_FLAG_NAMES = [
    "growth_reinvestment",
    "beta_business_risk",
    "terminal_value_share",
    "country_exposure",
]


def test_narrative_flags_runs_the_four_base_checks_in_spec_order() -> None:
    fin = _financials()
    asm = _assumptions()
    flags = narrative_flags(fin, asm, _result(fin, asm), _ctx())
    assert isinstance(flags, tuple)
    assert [f.name for f in flags] == _BASE_FLAG_NAMES
    assert all(isinstance(f, NarrativeFlag) for f in flags)


@pytest.mark.parametrize(
    "story_type",
    ["mature-stable", "mature-decline", "cyclical", "distressed", "hypergrowth", None],
)
def test_narrative_flags_omit_story_margin_for_other_story_types(
    story_type: str | None,
) -> None:
    # A check that does not apply is not emitted, the way hypergrowth_flags() omits its
    # flags; a margin far above the sector must not bring it back (issue #265).
    fin = _financials()
    asm = _assumptions()
    context = _ctx(
        story_type=story_type, company_operating_margin=0.40, sector_operating_margin=0.20
    )
    flags = narrative_flags(fin, asm, _result(fin, asm), context)
    assert [f.name for f in flags] == _BASE_FLAG_NAMES


def test_narrative_flags_runs_five_for_high_growth() -> None:
    fin = _financials()
    asm = _assumptions()
    flags = narrative_flags(fin, asm, _result(fin, asm), _ctx(story_type="high-growth"))
    assert [f.name for f in flags] == [
        "story_margin",
        "growth_reinvestment",
        "beta_business_risk",
        "terminal_value_share",
        "country_exposure",
    ]


def test_narrative_flags_keep_an_unknown_story_margin_for_high_growth() -> None:
    # The check applies and the data is missing: unknown stays visible (spec §7.5).
    fin = _financials()
    asm = _assumptions()
    flags = narrative_flags(fin, asm, _result(fin, asm), _ctx(story_type="high-growth"))
    assert flags[0].name == "story_margin"
    assert flags[0].color is FlagColor.UNKNOWN


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


# --------------------------------------------------------------------------- #
# Hypergrowth story flag (#195), outside the five §7.5 flags                  #
# --------------------------------------------------------------------------- #


def _hypergrowth_flag(**context: object) -> NarrativeFlag:
    fin, asm = _financials(), _assumptions()
    return hypergrowth_story_flag(fin, asm, _result(fin, asm), _ctx(**context))


def test_hypergrowth_story_red_without_story() -> None:
    flag = _hypergrowth_flag(hypergrowth_signals=True, story_file_present=False)
    assert flag.name == "hypergrowth_story"
    assert flag.color is FlagColor.RED
    assert flag.reason == (
        "The classifier sees hypergrowth signals but there is no story file, so the "
        "default valuation is not reliable."
    )


def test_hypergrowth_story_yellow_without_signals() -> None:
    flag = _hypergrowth_flag(
        story_type="hypergrowth", hypergrowth_signals=False, story_file_present=True
    )
    assert flag.color is FlagColor.YELLOW
    assert flag.reason == (
        "A story file is present but the classifier sees no hypergrowth signals: the two "
        "disagree."
    )


def test_hypergrowth_story_green_with_both() -> None:
    flag = _hypergrowth_flag(
        story_type="hypergrowth", hypergrowth_signals=True, story_file_present=True
    )
    assert flag.color is FlagColor.GREEN
    assert flag.reason == "The classifier's hypergrowth signals and the story file agree."


def _hypergrowth_flags(**context: object) -> tuple[NarrativeFlag, ...]:
    fin, asm = _financials(), _assumptions()
    return hypergrowth_flags(fin, asm, _result(fin, asm), _ctx(**context))


def test_hypergrowth_flags_empty_for_other_types() -> None:
    assert _hypergrowth_flags(story_type="high-growth") == ()
    assert _hypergrowth_flags() == ()


def test_hypergrowth_flags_on_signals() -> None:
    flags = _hypergrowth_flags(story_type="high-growth", hypergrowth_signals=True)
    assert [(f.name, f.color) for f in flags] == [("hypergrowth_story", FlagColor.RED)]


def test_hypergrowth_flags_on_story_type() -> None:
    flags = _hypergrowth_flags(story_type="hypergrowth", story_file_present=True)
    assert [(f.name, f.color) for f in flags] == [
        ("hypergrowth_story", FlagColor.YELLOW),
        ("hypergrowth_revenue_scale", FlagColor.GREEN),
        ("hypergrowth_terminal_roic", FlagColor.UNKNOWN),
    ]


def test_narrative_flags_stay_four_with_hypergrowth_signals() -> None:
    fin, asm = _financials(), _assumptions()
    flags = narrative_flags(fin, asm, _result(fin, asm), _ctx(hypergrowth_signals=True))
    assert len(flags) == 4
    assert "hypergrowth_story" not in {f.name for f in flags}


def test_hypergrowth_story_green_when_neither_signals_nor_story_file() -> None:
    flag = _hypergrowth_flag(
        story_type="hypergrowth", hypergrowth_signals=False, story_file_present=False
    )
    assert flag.color is FlagColor.GREEN
    assert flag.reason == "No hypergrowth signals and no story file: there is nothing to reconcile."


# --------------------------------------------------------------------------- #
# Hypergrowth revenue scale and terminal ROIC (#197)                           #
# --------------------------------------------------------------------------- #


def _with_year10_revenue(revenue: float) -> DCFResult:
    fin, asm = _financials(), _assumptions()
    result = _result(fin, asm)
    last = dataclasses.replace(result.projections[-1], revenue=revenue)
    return dataclasses.replace(result, projections=(*result.projections[:-1], last))


def _revenue_scale_flag(revenue: float) -> NarrativeFlag:
    fin, asm = _financials(), _assumptions()
    return hypergrowth_revenue_scale_flag(
        fin, asm, _with_year10_revenue(revenue), _ctx(story_type="hypergrowth")
    )


def test_revenue_scale_yellow_above_the_largest_company() -> None:
    flag = _revenue_scale_flag(750e9 + 1)
    assert flag.name == "hypergrowth_revenue_scale"
    assert flag.color is FlagColor.YELLOW
    assert flag.reason == (
        "Year-10 revenue of 750 billion is larger than the revenue of the largest "
        "company today, about 750 billion."
    )


def test_revenue_scale_green_at_the_largest_company() -> None:
    flag = _revenue_scale_flag(750e9)
    assert flag.name == "hypergrowth_revenue_scale"
    assert flag.color is FlagColor.GREEN
    assert flag.reason == (
        "Year-10 revenue of 750 billion is within the revenue of the largest company "
        "today, about 750 billion."
    )


def _terminal_roic_flag(**context: object) -> NarrativeFlag:
    fin, asm = _financials(), _assumptions()
    return hypergrowth_terminal_roic_flag(
        fin, asm, _result(fin, asm), _ctx(story_type="hypergrowth", **context)
    )


def test_terminal_roic_yellow_above_twice_the_sector() -> None:
    flag = _terminal_roic_flag(terminal_roic=0.24 + 1e-9, sector_roic=0.12)
    assert flag.name == "hypergrowth_terminal_roic"
    assert flag.color is FlagColor.YELLOW


def test_terminal_roic_yellow_reason() -> None:
    flag = _terminal_roic_flag(terminal_roic=0.30, sector_roic=0.12)
    assert flag.reason == (
        "The terminal return on invested capital (ROIC) of 30.0% is above 24.0%, 2 times "
        "the sector's 12.0%: the story claims an advantage far beyond the sector's."
    )


def test_terminal_roic_green_at_exactly_twice_the_sector() -> None:
    flag = _terminal_roic_flag(terminal_roic=0.24, sector_roic=0.12)
    assert flag.color is FlagColor.GREEN
    assert flag.reason == (
        "The terminal return on invested capital (ROIC) of 24.0% is within 24.0%, 2 times "
        "the sector's 12.0%."
    )


@pytest.mark.parametrize(
    ("terminal_roic", "sector_roic"), [(0.15, None), (None, 0.12), (None, None)]
)
def test_terminal_roic_unknown_without_both_roics(
    terminal_roic: float | None, sector_roic: float | None
) -> None:
    flag = _terminal_roic_flag(terminal_roic=terminal_roic, sector_roic=sector_roic)
    assert flag.color is FlagColor.UNKNOWN
    assert flag.reason == (
        "not evaluated: the terminal return on invested capital (ROIC) or the sector's "
        "ROIC is missing."
    )


def test_hypergrowth_flags_three_for_a_story_in_order() -> None:
    flags = _hypergrowth_flags(
        story_type="hypergrowth",
        hypergrowth_signals=True,
        story_file_present=True,
        terminal_roic=0.15,
        sector_roic=0.12,
    )
    assert [f.name for f in flags] == [
        "hypergrowth_story",
        "hypergrowth_revenue_scale",
        "hypergrowth_terminal_roic",
    ]


def test_hypergrowth_flags_one_for_signals_without_a_story() -> None:
    flags = _hypergrowth_flags(
        story_type="high-growth", hypergrowth_signals=True, terminal_roic=1.0, sector_roic=0.1
    )
    assert [f.name for f in flags] == ["hypergrowth_story"]


def test_narrative_flags_stay_four_for_a_hypergrowth_story() -> None:
    fin, asm = _financials(), _assumptions()
    flags = narrative_flags(
        fin, asm, _result(fin, asm), _ctx(story_type="hypergrowth", hypergrowth_signals=True)
    )
    assert [f.name for f in flags] == _BASE_FLAG_NAMES


@pytest.mark.parametrize("sector_roic", [0.0, -0.03])
def test_terminal_roic_unknown_when_the_sector_roic_is_not_positive(sector_roic: float) -> None:
    flag = _terminal_roic_flag(terminal_roic=0.15, sector_roic=sector_roic)
    assert flag.color is FlagColor.UNKNOWN
    assert flag.reason == (
        f"not evaluated: a sector return on invested capital (ROIC) of {sector_roic:.1%} "
        "is not a usable benchmark."
    )


# --------------------------------------------------------------------------- #
# Which flags can be red (issue #218)                                         #
# --------------------------------------------------------------------------- #
# The analyze-flags and portfolio-mark-events boards say only growth_reinvestment
# (of the five) and hypergrowth_story can be red, so only they fire new_red_flag.
# These tests break when that stops being true.

_NEVER_RED = (
    story_margin_flag,
    beta_business_risk_flag,
    terminal_value_share_flag,
    hypergrowth_revenue_scale_flag,
    hypergrowth_terminal_roic_flag,
)
#: NarrativeFlag.name of every flag that can return red.
_RED_CAPABLE = {"growth_reinvestment", "country_exposure", "hypergrowth_story"}


def _sweep_results() -> list[tuple[Financials, Assumptions, DCFResult]]:
    """Default, negative FCFF, terminal share > 80%, year-10 revenue > 750B."""
    cases = [
        (_financials(), _assumptions()),
        (_financials(), _assumptions(sales_to_capital=0.1)),
        (
            _financials(),
            _assumptions(
                revenue_growth=(0.01, 0.01, 0.01, 0.01, 0.01),
                terminal_growth=0.04,
                cost_of_equity=0.07,
                pretax_cost_of_debt=0.04,
            ),
        ),
        (Financials(revenue=1e12, net_debt=0.0, shares_diluted=100.0), _assumptions()),
    ]
    return [(fin, asm, _result(fin, asm)) for fin, asm in cases]


def _sweep_contexts() -> list[NarrativeContext]:
    return [
        NarrativeContext(
            story_type=story_type,
            company_operating_margin=company_margin,
            sector_operating_margin=sector_margin,
            sector_beta=beta,
            operating_leverage=operating_leverage,
            company_debt_weight=debt_weight,
            terminal_roic=terminal_roic,
            sector_roic=sector_roic,
        )
        for (
            story_type,
            company_margin,
            sector_margin,
            beta,
            operating_leverage,
            debt_weight,
            terminal_roic,
            sector_roic,
        ) in itertools.product(
            (None, "high-growth", "hypergrowth"),
            (None, 0.05, 0.30),
            (None, 0.10),
            (None, 0.5, 1.5),
            (None, 3.0),
            (None, 0.9),
            (None, 0.5),
            (None, 0.0, 0.1),
        )
    ]


def test_sweep_results_reach_the_bands() -> None:
    _, negative, fragile, huge = _sweep_results()
    assert any(p.fcff < 0.0 for p in negative[2].projections)
    assert fragile[2].terminal_value_share > 0.80
    assert huge[2].projections[-1].revenue > 750e9


def test_every_flag_is_classified_by_red_capability() -> None:
    # The flags analyze returns (bot.valuator.analysis.analyze): keep in sync with its
    # narrative_flags(...) + hypergrowth_flags(...) concatenation.
    # story_margin only comes out for high-growth, the hypergrowth flags only for signals
    # or the hypergrowth story type: the union of the two contexts emits every flag.
    fin, asm = _financials(), _assumptions()
    result = _result(fin, asm)
    emitted = {
        f.name
        for ctx in (
            _ctx(story_type="hypergrowth", hypergrowth_signals=True),
            _ctx(story_type="high-growth"),
        )
        for f in narrative_flags(fin, asm, result, ctx) + hypergrowth_flags(fin, asm, result, ctx)
    }
    never_red = {f.__name__.removesuffix("_flag") for f in _NEVER_RED}
    assert emitted == never_red | _RED_CAPABLE


def test_red_is_named_once_per_red_capable_flag() -> None:
    # A helper or a new red site anywhere in the module trips this, not only in the flag bodies.
    assert inspect.getsource(narrative_flags_module).count("FlagColor.RED") == len(_RED_CAPABLE)


@pytest.mark.parametrize("flag", _NEVER_RED, ids=lambda f: f.__name__)
def test_never_red_flag_source_names_no_red(
    flag: Callable[[Financials, Assumptions, DCFResult, NarrativeContext], NarrativeFlag],
) -> None:
    assert "FlagColor.RED" not in inspect.getsource(flag)


@pytest.mark.parametrize("flag", _NEVER_RED, ids=lambda f: f.__name__)
def test_never_red_flag_is_not_red_over_a_sweep(
    flag: Callable[[Financials, Assumptions, DCFResult, NarrativeContext], NarrativeFlag],
) -> None:
    contexts = _sweep_contexts()
    reds = [
        (fin, ctx)
        for fin, asm, result in _sweep_results()
        for ctx in contexts
        if flag(fin, asm, result, ctx).color is FlagColor.RED
    ]
    assert reds == []


# --------------------------------------------------------------------------- #
# Every reason reads as a sentence for a human (issue #265)                   #
# --------------------------------------------------------------------------- #


def test_country_exposure_green_reason_with_a_negative_gap() -> None:
    fin, asm = _financials(), _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.70, erp_weighted=0.045, erp_listing=0.05),
    )
    assert flag.color is FlagColor.GREEN
    assert flag.reason.endswith("a gap of -50 basis points.")


def test_country_exposure_green_reason_never_prints_minus_zero() -> None:
    fin, asm = _financials(), _assumptions()
    flag = country_exposure_flag(
        fin,
        asm,
        _result(fin, asm),
        _ctx(foreign_revenue_share=0.70, erp_weighted=0.04997, erp_listing=0.05),
    )
    assert flag.reason.endswith("a gap of 0 basis points.")


#: Each acronym a reason may use, with the expansion that must come before it.
_EXPANSIONS = {
    "NOPAT": "after-tax operating profit (NOPAT)",
    "FCFF": "free cash flow to the firm (FCFF)",
    "ERP": "equity risk premium (ERP)",
    "ROIC": "return on invested capital (ROIC)",
}

#: Every (name, colour) pair the eight checks can return.
_EVERY_BRANCH = {
    ("story_margin", FlagColor.GREEN),
    ("story_margin", FlagColor.YELLOW),
    ("story_margin", FlagColor.UNKNOWN),
    ("growth_reinvestment", FlagColor.GREEN),
    ("growth_reinvestment", FlagColor.YELLOW),
    ("growth_reinvestment", FlagColor.RED),
    ("beta_business_risk", FlagColor.GREEN),
    ("beta_business_risk", FlagColor.YELLOW),
    ("beta_business_risk", FlagColor.UNKNOWN),
    ("terminal_value_share", FlagColor.GREEN),
    ("terminal_value_share", FlagColor.YELLOW),
    ("country_exposure", FlagColor.GREEN),
    ("country_exposure", FlagColor.RED),
    ("country_exposure", FlagColor.UNKNOWN),
    ("hypergrowth_story", FlagColor.GREEN),
    ("hypergrowth_story", FlagColor.YELLOW),
    ("hypergrowth_story", FlagColor.RED),
    ("hypergrowth_revenue_scale", FlagColor.GREEN),
    ("hypergrowth_revenue_scale", FlagColor.YELLOW),
    ("hypergrowth_terminal_roic", FlagColor.GREEN),
    ("hypergrowth_terminal_roic", FlagColor.YELLOW),
    ("hypergrowth_terminal_roic", FlagColor.UNKNOWN),
}

_ALL_FLAGS = (
    story_margin_flag,
    growth_reinvestment_flag,
    beta_business_risk_flag,
    terminal_value_share_flag,
    country_exposure_flag,
    hypergrowth_story_flag,
    hypergrowth_revenue_scale_flag,
    hypergrowth_terminal_roic_flag,
)


def _every_reason() -> list[NarrativeFlag]:
    """Every check over inputs that reach each of its branches."""
    contexts = [
        *_sweep_contexts(),
        *(
            NarrativeContext(
                foreign_revenue_share=foreign, erp_weighted=weighted, erp_listing=listing
            )
            for foreign, weighted, listing in (
                (None, None, None),
                (0.70, 0.09, 0.05),
                (0.70, 0.046, 0.045),
            )
        ),
        *(
            NarrativeContext(hypergrowth_signals=signals, story_file_present=story)
            for signals, story in itertools.product((False, True), (False, True))
        ),
        NarrativeContext(terminal_roic=0.15, sector_roic=0.1),
    ]
    stretched = (
        _financials(),
        _assumptions(
            revenue_growth=(0.077,) * 5,
            operating_margin=(0.10,) * 5,
            sales_to_capital=1.0,
        ),
    )
    results = [
        *_sweep_results(),
        (stretched[0], stretched[1], _result(*stretched)),
    ]
    return [
        flag(fin, asm, result, ctx)
        for fin, asm, result in results
        for ctx in contexts
        for flag in _ALL_FLAGS
    ]


def test_every_reason_reads_for_a_person() -> None:
    flags = _every_reason()
    assert {(f.name, f.color) for f in flags} == _EVERY_BRANCH
    for reason in {f.reason for f in flags}:
        for notation in ("\u2014", "<=", ">", "bps", "~"):
            assert notation not in reason, (notation, reason)
        for acronym, expansion in _EXPANSIONS.items():
            if acronym in reason:
                assert expansion in reason, (acronym, reason)
                # The first use of the acronym is the one inside its expansion.
                assert reason.index(acronym) > reason.index(expansion), reason
