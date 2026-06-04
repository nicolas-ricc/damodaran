"""Ground-truth unit tests for the two-stage DCF (issue #11 / M4.1, spec §7.2).

Every expected value below is computed independently of the implementation —
by hand / in a spreadsheet from the §7.2 formula — so these tests pin the
*arithmetic*, not just the code's self-consistency. WACC is built from its
capital-structure components::

    wacc = equity_weight * cost_of_equity
         + debt_weight * pretax_cost_of_debt * (1 - tax_rate)
"""

from __future__ import annotations

import math

import pytest

from bot.valuator.dcf import Assumptions, DCFResult, Financials, dcf

TOL = 1e-6


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #


def test_happy_path_matches_ground_truth() -> None:
    financials = Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)
    assumptions = Assumptions(
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

    result = dcf(financials, assumptions)

    assert result.wacc == pytest.approx(0.09550, abs=TOL)
    assert result.intrinsic_value == pytest.approx(16.745164916409884, abs=TOL)
    assert result.enterprise_value == pytest.approx(2174.5164916409885, abs=TOL)
    assert result.equity_value == pytest.approx(1674.5164916409883, abs=TOL)
    assert result.terminal_value == pytest.approx(2530.14204015894, abs=TOL)
    assert result.terminal_value_share == pytest.approx(0.7374291273591067, abs=TOL)


def test_happy_path_year_by_year_fcff() -> None:
    financials = Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)
    assumptions = Assumptions(
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

    result = dcf(financials, assumptions)

    expected_fcff = [115.0, 134.20000000000002, 153.252, 171.26208, 187.28012160000003]
    assert [p.fcff for p in result.projections] == pytest.approx(expected_fcff, abs=TOL)
    assert [p.year for p in result.projections] == [1, 2, 3, 4, 5]
    # Year-1 figures from first principles.
    first = result.projections[0]
    assert first.revenue == pytest.approx(1100.0, abs=TOL)
    assert first.ebit == pytest.approx(220.0, abs=TOL)
    assert first.nopat == pytest.approx(165.0, abs=TOL)
    assert first.reinvestment == pytest.approx(50.0, abs=TOL)


def test_equity_value_equals_intrinsic_times_shares() -> None:
    financials = Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)
    assumptions = Assumptions(
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

    result = dcf(financials, assumptions)

    assert result.equity_value == pytest.approx(
        result.intrinsic_value * financials.shares_diluted, abs=TOL
    )
    assert result.equity_weight == pytest.approx(0.8, abs=TOL)
    assert result.debt_weight == pytest.approx(0.2, abs=TOL)


# --------------------------------------------------------------------------- #
# Negative FCF in early years (heavy reinvestment outpaces NOPAT)             #
# --------------------------------------------------------------------------- #


def test_negative_early_fcff() -> None:
    financials = Financials(revenue=500.0, net_debt=200.0, shares_diluted=50.0)
    assumptions = Assumptions(
        revenue_growth=(0.50, 0.40, 0.20, 0.10, 0.05),
        operating_margin=(0.05, 0.08, 0.12, 0.15, 0.18),
        tax_rate=0.25,
        sales_to_capital=1.0,
        terminal_growth=0.02,
        cost_of_equity=0.12,
        pretax_cost_of_debt=0.06,
        equity_weight=0.7,
        debt_weight=0.3,
    )

    result = dcf(financials, assumptions)

    expected_fcff = [-221.875, -237.0, -96.60000000000001, 29.92500000000001, 127.16550000000007]
    assert [p.fcff for p in result.projections] == pytest.approx(expected_fcff, abs=TOL)
    # The first two years bleed cash...
    assert result.projections[0].fcff < 0.0
    assert result.projections[1].fcff < 0.0
    # ...yet the firm still has a positive intrinsic value.
    assert result.wacc == pytest.approx(0.09750, abs=TOL)
    assert result.intrinsic_value == pytest.approx(16.330770233076592, abs=TOL)
    assert result.enterprise_value == pytest.approx(1016.5385116538297, abs=TOL)


# --------------------------------------------------------------------------- #
# Growth > WACC in early years (must terminate gracefully)                    #
# --------------------------------------------------------------------------- #


def test_growth_above_wacc_in_explicit_years_terminates() -> None:
    financials = Financials(revenue=800.0, net_debt=300.0, shares_diluted=80.0)
    assumptions = Assumptions(
        revenue_growth=(0.30, 0.25, 0.20, 0.15, 0.10),
        operating_margin=(0.18, 0.18, 0.18, 0.18, 0.18),
        tax_rate=0.25,
        sales_to_capital=2.5,
        terminal_growth=0.02,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=0.9,
        debt_weight=0.1,
    )

    result = dcf(financials, assumptions)

    # Year-1 growth (30%) far exceeds WACC (~9.4%); the model must still
    # produce a finite, well-defined value because terminal growth < WACC.
    assert result.wacc == pytest.approx(0.09375, abs=TOL)
    assert assumptions.revenue_growth[0] > result.wacc
    assert math.isfinite(result.intrinsic_value)
    assert result.intrinsic_value == pytest.approx(29.090073351544994, abs=TOL)
    assert result.enterprise_value == pytest.approx(2627.2058681235994, abs=TOL)
    assert result.terminal_value == pytest.approx(3470.508203389829, abs=TOL)


def test_terminal_growth_at_or_above_wacc_raises() -> None:
    financials = Financials(revenue=800.0, net_debt=300.0, shares_diluted=80.0)
    assumptions = Assumptions(
        revenue_growth=(0.05,),
        operating_margin=(0.18,),
        tax_rate=0.25,
        sales_to_capital=2.5,
        terminal_growth=0.12,  # above the ~9.4% WACC -> diverges
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=0.9,
        debt_weight=0.1,
    )

    with pytest.raises(ValueError, match="converge"):
        dcf(financials, assumptions)


# --------------------------------------------------------------------------- #
# Terminal value share = 100%                                                 #
# --------------------------------------------------------------------------- #


def test_terminal_value_share_is_100_percent_when_explicit_fcff_zero() -> None:
    # Single explicit year tuned so reinvestment exactly cancels NOPAT, leaving
    # zero explicit FCFF, so the entire enterprise value rests on the perpetuity.
    financials = Financials(revenue=1000.0, net_debt=200.0, shares_diluted=100.0)
    assumptions = Assumptions(
        revenue_growth=(0.10,),
        operating_margin=(0.15,),
        tax_rate=0.25,
        sales_to_capital=100.0 / 123.75,  # makes year-1 reinvestment == NOPAT
        terminal_growth=0.02,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=1.0,
        debt_weight=0.0,
    )

    result = dcf(financials, assumptions)

    assert result.wacc == pytest.approx(0.10, abs=TOL)
    assert result.projections[0].fcff == pytest.approx(0.0, abs=TOL)
    assert result.terminal_value_share == pytest.approx(1.0, abs=TOL)
    assert result.intrinsic_value == pytest.approx(9.25, abs=TOL)
    assert result.enterprise_value == pytest.approx(1125.0, abs=TOL)


# --------------------------------------------------------------------------- #
# Distressed (probability of bankruptcy > 0)                                  #
# --------------------------------------------------------------------------- #


def test_distressed_blends_going_concern_and_distress_value() -> None:
    financials = Financials(revenue=600.0, net_debt=400.0, shares_diluted=50.0)
    assumptions = Assumptions(
        revenue_growth=(0.0, 0.0, 0.0, 0.0, 0.0),
        operating_margin=(0.10, 0.10, 0.10, 0.10, 0.10),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.01,
        cost_of_equity=0.15,
        pretax_cost_of_debt=0.09,
        equity_weight=0.5,
        debt_weight=0.5,
        probability_of_bankruptcy=0.30,
        distress_value_per_share=2.0,
    )

    result = dcf(financials, assumptions)

    assert result.wacc == pytest.approx(0.10875, abs=TOL)
    assert result.intrinsic_value == pytest.approx(0.9274586247818358, abs=TOL)
    assert result.enterprise_value == pytest.approx(423.38990177013113, abs=TOL)
    assert result.equity_value == pytest.approx(46.37293123909179, abs=TOL)
    # Flat revenue -> reinvestment is zero every year, FCFF is constant NOPAT.
    assert all(p.reinvestment == pytest.approx(0.0, abs=TOL) for p in result.projections)
    assert all(p.fcff == pytest.approx(45.0, abs=TOL) for p in result.projections)


def test_distress_probability_pulls_value_toward_recovery() -> None:
    base = Assumptions(
        revenue_growth=(0.03, 0.03, 0.03),
        operating_margin=(0.12, 0.12, 0.12),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.13,
        pretax_cost_of_debt=0.07,
        equity_weight=0.6,
        debt_weight=0.4,
    )
    financials = Financials(revenue=700.0, net_debt=250.0, shares_diluted=60.0)

    going_concern = dcf(financials, base)
    from dataclasses import replace

    distressed = dcf(
        financials,
        replace(base, probability_of_bankruptcy=0.50, distress_value_per_share=0.0),
    )

    # With 50% bankruptcy and zero recovery, value is exactly half the going
    # concern per-share value.
    assert distressed.intrinsic_value == pytest.approx(
        0.5 * going_concern.intrinsic_value, abs=TOL
    )


# --------------------------------------------------------------------------- #
# Edge cases / purity                                                         #
# --------------------------------------------------------------------------- #


def test_net_cash_company_has_equity_above_enterprise_value() -> None:
    financials = Financials(revenue=1000.0, net_debt=-300.0, shares_diluted=100.0)
    assumptions = Assumptions(
        revenue_growth=(0.05, 0.05),
        operating_margin=(0.18, 0.18),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=1.0,
        debt_weight=0.0,
    )

    result = dcf(financials, assumptions)

    # Net cash adds to equity, so equity value exceeds the enterprise value.
    assert result.equity_value > result.enterprise_value


def test_adjustments_flow_into_equity_value() -> None:
    common = dict(
        revenue_growth=(0.04, 0.04),
        operating_margin=(0.18, 0.18),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=1.0,
        debt_weight=0.0,
    )
    assumptions = Assumptions(**common)  # type: ignore[arg-type]

    without = dcf(Financials(revenue=1000.0, net_debt=200.0, shares_diluted=100.0), assumptions)
    with_adj = dcf(
        Financials(revenue=1000.0, net_debt=200.0, shares_diluted=100.0, adjustments=150.0),
        assumptions,
    )

    assert with_adj.equity_value == pytest.approx(without.equity_value + 150.0, abs=TOL)


def test_is_pure_does_not_mutate_inputs() -> None:
    financials = Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)
    assumptions = Assumptions(
        revenue_growth=(0.10, 0.05),
        operating_margin=(0.20, 0.20),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.11,
        pretax_cost_of_debt=0.05,
        equity_weight=0.8,
        debt_weight=0.2,
    )

    first = dcf(financials, assumptions)
    second = dcf(financials, assumptions)

    # Deterministic and non-mutating: identical inputs -> identical output.
    assert isinstance(first, DCFResult)
    assert first == second
    assert financials.revenue == 1000.0
    assert assumptions.revenue_growth == (0.10, 0.05)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"revenue_growth": (), "operating_margin": ()}, "horizon"),
        ({"operating_margin": (0.2, 0.2, 0.2)}, "equal length"),
        ({"sales_to_capital": 0.0}, "sales_to_capital"),
    ],
)
def test_invalid_assumptions_raise(kwargs: dict[str, object], match: str) -> None:
    defaults: dict[str, object] = dict(
        revenue_growth=(0.05, 0.05),
        operating_margin=(0.18, 0.18),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=1.0,
        debt_weight=0.0,
    )
    defaults.update(kwargs)
    assumptions = Assumptions(**defaults)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=match):
        dcf(Financials(revenue=1000.0, net_debt=0.0, shares_diluted=100.0), assumptions)


def test_zero_enterprise_value_yields_zero_terminal_share() -> None:
    # A firm with no operating profit and no growth generates zero FCFF forever,
    # so EV is exactly zero; the terminal-value share guard must avoid a
    # division by zero and report 0.0.
    financials = Financials(revenue=1000.0, net_debt=0.0, shares_diluted=100.0)
    assumptions = Assumptions(
        revenue_growth=(0.0,),
        operating_margin=(0.0,),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.0,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=1.0,
        debt_weight=0.0,
    )

    result = dcf(financials, assumptions)

    assert result.enterprise_value == pytest.approx(0.0, abs=TOL)
    assert result.terminal_value_share == 0.0
    assert result.intrinsic_value == pytest.approx(0.0, abs=TOL)


def test_non_positive_shares_raise() -> None:
    assumptions = Assumptions(
        revenue_growth=(0.05,),
        operating_margin=(0.18,),
        tax_rate=0.25,
        sales_to_capital=2.0,
        terminal_growth=0.02,
        cost_of_equity=0.10,
        pretax_cost_of_debt=0.05,
        equity_weight=1.0,
        debt_weight=0.0,
    )

    with pytest.raises(ValueError, match="shares_diluted"):
        dcf(Financials(revenue=1000.0, net_debt=0.0, shares_diluted=0.0), assumptions)
