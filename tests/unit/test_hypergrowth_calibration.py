"""Calibration of the hypergrowth resolver on Damodaran's Anthropic base case (#196).

Pure resolver + DCF, in millions, with the figures of his published sheet.
``CAL_*`` is his updated sheet of 2026-11-03 ("The Anthropic Feedback Loop",
https://aswathdamodaran.blogspot.com/2026/11/the-anthropic-feedback-loop-cost-of.html):
trailing revenue 35,286 after the leaked Q3 figures, year-1 growth cut to 190%
so next year's revenue stays near 100B, and debt plus commitments of 485,320.
Margins, cost of capital, tax, sales to capital, failure risk and terminal ROIC
are unchanged from his October sheet (story #192), kept as ``CAL_OCT_*`` because
his worst and best scenarios were run on it.

His November sheet values the equity at 1,450,951 (439.24/share). This model
computes 1,452,937 (439.98/share): the 0.14% gap is his sheet reinvesting one
year ahead of revenue (year ``t`` reinvestment funds year ``t + 1`` growth),
which this model deliberately does not do (it reinvests in the same year, as the
DCF always has). The 1% tolerance covers it; the terminal value, which does not
depend on that timing, is held to 0.1%. The October sheet gave 1,475,406
(447.34/share) against a computed 1,473,576 (446.79/share).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from bot.valuator.assumptions import Assumptions, AssumptionSource, Sourced
from bot.valuator.dcf import DCFResult, Financials, dcf
from bot.valuator.hypergrowth import StoryInputs, apply_story

#: Damodaran's base-case story of his 2026-11-03 sheet, in millions of USD.
CAL_STORY = StoryInputs(
    year1_growth=1.90,
    target_revenue_y10=1_004_515.60,
    year1_margin=0.05,
    target_margin=0.325,
    margin_converge_year=5,
    regulatory_drag=0.05,
    sales_to_capital=3.0,
    wacc_start=0.0974,
    wacc_terminal=0.0913,
    effective_tax_rate=0.0,
    terminal_roic=0.15,
    failure_probability=0.10,
    failure_proceeds_pct_of_value=0.50,
    fixed_commitments_pv=485_319.79,
    extra_cash=100_000,
    governance_discount=0.0,
)

#: Base-year (trailing) revenue (millions).
CAL_BASE_REVENUE = 35_286.0
#: Terminal growth of his sheet (the risk-free rate).
CAL_TERMINAL_GROWTH = 0.049
#: Marginal tax rate the tax path converges to.
CAL_MARGINAL_TAX = 0.25

#: Cash and non-operating assets total 216,318: 112,389 cash, 100,000 from the
#: offering and 3,929 other; options of 472.30 are netted from the latter.
CAL_FINANCIALS = Financials(
    revenue=35_286,
    net_debt=-112_389,
    shares_diluted=3_302.27,
    adjustments=3_929 - 472.30,
    fixed_commitments=485_319.79,
    extra_cash=100_000,
)

#: His October sheet (story #192), the base his scenarios were run on.
CAL_OCT_STORY = replace(
    CAL_STORY, year1_growth=4.00, target_revenue_y10=1_011_491, fixed_commitments_pv=472_336
)
CAL_OCT_BASE_REVENUE = 20_608.0
CAL_OCT_FINANCIALS = Financials(
    revenue=20_608,
    net_debt=-112_389,
    shares_diluted=3_298.14,
    adjustments=3_929 - 472,
    fixed_commitments=472_336,
    extra_cash=100_000,
)

CAL_GROWTH = (1.90, 0.42, 0.42, 0.42, 0.42, 0.3458, 0.2716, 0.1974, 0.1232, 0.0490)
CAL_MARGIN = (0.05, 0.14, 0.185, 0.23, 0.275, 0.275, 0.275, 0.275, 0.275, 0.275)
CAL_WACC = (0.0974,) * 5 + (0.0962, 0.0950, 0.0937, 0.0925, 0.0913)
CAL_TAX = (0.0,) * 5 + (0.05, 0.10, 0.15, 0.20, 0.25)


def generic_bundle(
    *,
    terminal_growth: float | None = CAL_TERMINAL_GROWTH,
    tax_rate: float | None = CAL_MARGINAL_TAX,
) -> Assumptions:
    """A bundle as the generic resolvers would leave it, before the story."""
    sector = AssumptionSource.SECTOR_DEFAULT_DAMODARAN

    def src(value: float | None, source: AssumptionSource) -> Sourced[float | None]:
        return Sourced(value, source if value is not None else AssumptionSource.UNRESOLVED)

    return Assumptions(
        revenue_growth=Sourced((0.5,) * 5, AssumptionSource.HISTORICAL_AVERAGE),
        operating_margin=Sourced((0.28,) * 5, sector),
        sales_to_capital=Sourced(1.5, sector),
        terminal_growth=src(terminal_growth, AssumptionSource.MANUAL),
        probability_of_bankruptcy=Sourced(0.0, AssumptionSource.RULE_BASED),
        distress_value_per_share=Sourced(0.0, AssumptionSource.RULE_BASED),
        cost_of_equity=Sourced(0.11, sector),
        pretax_cost_of_debt=Sourced(0.06, sector),
        equity_weight=Sourced(0.8, sector),
        debt_weight=Sourced(0.2, sector),
        tax_rate=src(tax_rate, AssumptionSource.MANUAL),
        story_type="hypergrowth",
    )


def _calibrated(
    story: StoryInputs = CAL_STORY,
    base_revenue: float = CAL_BASE_REVENUE,
    financials: Financials = CAL_FINANCIALS,
) -> tuple[Assumptions, DCFResult]:
    bundle = apply_story(generic_bundle(), story, base_revenue=base_revenue, sector_wacc=None)
    return bundle, dcf(financials, bundle.to_dcf_assumptions())


def test_calibration_paths_match_the_sheet() -> None:
    bundle, _ = _calibrated()
    assert bundle.revenue_growth.value == pytest.approx(CAL_GROWTH, abs=1e-6)
    assert bundle.operating_margin.value == pytest.approx(CAL_MARGIN, abs=1e-12)
    assert bundle.wacc_path is not None and bundle.tax_rate_path is not None
    assert bundle.wacc_path.value == pytest.approx(CAL_WACC, abs=1e-4)
    assert bundle.tax_rate_path.value == pytest.approx(CAL_TAX, abs=1e-12)


def test_calibration_reproduces_damodaran_base_case() -> None:
    _, result = _calibrated()
    assert result.projections[0].revenue == pytest.approx(102_329.40, abs=0.01)
    assert result.projections[-1].revenue == pytest.approx(1_004_515.60, abs=1)
    pv_terminal = result.terminal_value * result.projections[-1].discount_factor
    assert pv_terminal == pytest.approx(1_388_747.61, rel=0.001)
    # Computed 1,452,937 / 439.98: same-year reinvestment (see module docstring).
    assert result.equity_value == pytest.approx(1_450_950.80, rel=0.01)
    assert result.intrinsic_value == pytest.approx(439.24, rel=0.01)


def test_calibration_still_reproduces_the_october_sheet() -> None:
    _, result = _calibrated(CAL_OCT_STORY, CAL_OCT_BASE_REVENUE, CAL_OCT_FINANCIALS)
    assert result.projections[-1].revenue == pytest.approx(1_011_491, abs=1)
    pv_terminal = result.terminal_value * result.projections[-1].discount_factor
    assert pv_terminal == pytest.approx(1_398_391, rel=0.001)
    # Computed 1,473,576 / 446.79.
    assert result.equity_value == pytest.approx(1_475_406, rel=0.01)
    assert result.intrinsic_value == pytest.approx(447.34, rel=0.01)


#: His worst and best scenarios over the October base story (#197). Worst uses a
#: 10-point drag: that reproduces his -373B (a 15-point drag gives -452B).
CAL_SCENARIOS = {
    "worst": replace(
        CAL_OCT_STORY,
        target_revenue_y10=200_000,
        target_margin=0.10,
        sales_to_capital=1.0,
        wacc_start=0.0988,
        regulatory_drag=0.10,
    ),
    "best": replace(
        CAL_OCT_STORY,
        target_revenue_y10=1_500_000,
        target_margin=0.40,
        sales_to_capital=4.0,
        wacc_start=0.0779,
        regulatory_drag=0.0,
    ),
}


def test_calibration_reproduces_damodaran_scenario_range() -> None:
    from bot.valuator.hypergrowth import scenario_cases
    from bot.valuator.sensitivity import scenario_range

    bundle, base = _calibrated(CAL_OCT_STORY, CAL_OCT_BASE_REVENUE, CAL_OCT_FINANCIALS)
    results = scenario_range(
        scenario_cases(
            bundle,
            CAL_SCENARIOS,
            base_revenue=CAL_OCT_BASE_REVENUE,
            sector_wacc=None,
            financials=CAL_OCT_FINANCIALS,
        )
    )
    by_name = {r.name: r for r in results}
    assert [r.name for r in results] == ["base", "worst", "best"]
    assert by_name["base"].equity_value == base.equity_value
    # Computed -371,991 and 4,076,137.
    assert by_name["worst"].equity_value == pytest.approx(-373_000, rel=0.05)
    assert by_name["best"].equity_value == pytest.approx(4_040_000, rel=0.05)
