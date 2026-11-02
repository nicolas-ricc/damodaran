"""Calibration of the hypergrowth resolver on Damodaran's Anthropic base case (#196).

Pure resolver + DCF, in millions, with the figures of his published sheet
(story #192). The story fixture below is his base-case pick; base revenue,
bridge and share count are the S-1 numbers his sheet starts from.

His sheet values the equity at 1,475,406 (447.34/share). This model computes
1,473,576 (446.79/share): the 0.12% gap is his sheet reinvesting one year ahead
of revenue (year ``t`` reinvestment funds year ``t + 1`` growth), which this
model deliberately does not do (it reinvests in the same year, as the DCF
always has). The 1% tolerance covers it; the terminal value, which does not
depend on that timing, is held to 0.1%.
"""

from __future__ import annotations

import pytest

from bot.valuator.assumptions import Assumptions, AssumptionSource, Sourced
from bot.valuator.dcf import DCFResult, Financials, dcf
from bot.valuator.hypergrowth import StoryInputs, apply_story

#: Damodaran's base-case story, in millions of USD.
CAL_STORY = StoryInputs(
    year1_growth=4.00,
    target_revenue_y10=1_011_491,
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
    fixed_commitments_pv=472_336,
    extra_cash=100_000,
    governance_discount=0.0,
)

#: Base-year revenue (millions).
CAL_BASE_REVENUE = 20_608.0
#: Terminal growth of his sheet (the risk-free rate).
CAL_TERMINAL_GROWTH = 0.049
#: Marginal tax rate the tax path converges to.
CAL_MARGINAL_TAX = 0.25

CAL_FINANCIALS = Financials(
    revenue=20_608,
    net_debt=-112_389,
    shares_diluted=3_298.14,
    adjustments=3_929 - 472,
    fixed_commitments=472_336,
    extra_cash=100_000,
)

CAL_GROWTH = (4.00, 0.42, 0.42, 0.42, 0.42, 0.3458, 0.2716, 0.1974, 0.1232, 0.0490)
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


def _calibrated() -> tuple[Assumptions, DCFResult]:
    bundle = apply_story(
        generic_bundle(), CAL_STORY, base_revenue=CAL_BASE_REVENUE, sector_wacc=None
    )
    return bundle, dcf(CAL_FINANCIALS, bundle.to_dcf_assumptions())


def test_calibration_paths_match_the_sheet() -> None:
    bundle, _ = _calibrated()
    assert bundle.revenue_growth.value == pytest.approx(CAL_GROWTH, abs=1e-6)
    assert bundle.operating_margin.value == pytest.approx(CAL_MARGIN, abs=1e-12)
    assert bundle.wacc_path is not None and bundle.tax_rate_path is not None
    assert bundle.wacc_path.value == pytest.approx(CAL_WACC, abs=1e-4)
    assert bundle.tax_rate_path.value == pytest.approx(CAL_TAX, abs=1e-12)


def test_calibration_reproduces_damodaran_base_case() -> None:
    _, result = _calibrated()
    assert result.projections[-1].revenue == pytest.approx(1_011_491, abs=1)
    pv_terminal = result.terminal_value * result.projections[-1].discount_factor
    assert pv_terminal == pytest.approx(1_398_391, rel=0.001)
    # Computed 1,473,576 / 446.79: same-year reinvestment (see module docstring).
    assert result.equity_value == pytest.approx(1_475_406, rel=0.01)
    assert result.intrinsic_value == pytest.approx(447.34, rel=0.01)
