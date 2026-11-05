"""Additive ±1pp shocks for rate axes, multiplicative for sales_to_capital (#217).

The tornado moves a rate axis to base -1pp / +1pp and ``sales_to_capital`` to
×0.8 / ×1.2; the grid steps are -1, -0.5, 0, +0.5, +1 pp on a rate axis and
0.8 … 1.2 on ``sales_to_capital``. A shift that leaves the DCF's domain (terminal
growth at or above WACC, a tax rate outside [0, 1), a cost of capital ≤ 0) has
no value.
"""

from __future__ import annotations

import dataclasses

import pytest

from bot.valuator.dcf import Assumptions, Financials, dcf
from bot.valuator.sensitivity import (
    SensitivityAxis,
    ShockKind,
    TornadoEntry,
    grid_2d,
    grid_steps,
    shift_axis,
    tornado,
    tornado_steps,
)
from tests.unit.test_valuator_dcf import damodaran_assumptions, damodaran_financials

TOL = 1e-12
_ADDITIVE_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)
_MULTIPLICATIVE_STEPS = (0.8, 0.9, 1.0, 1.1, 1.2)


def _financials() -> Financials:
    return Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)


def _assumptions(**changes: object) -> Assumptions:
    base = Assumptions(
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
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def _entry(entries: list[TornadoEntry], axis: SensitivityAxis) -> TornadoEntry:
    return next(e for e in entries if e.axis is axis)


# --------------------------------------------------------------------------- #
# Kinds and step tables                                                        #
# --------------------------------------------------------------------------- #


def test_axis_kinds() -> None:
    for axis in SensitivityAxis:
        expected = (
            ShockKind.MULTIPLICATIVE
            if axis is SensitivityAxis.SALES_TO_CAPITAL
            else ShockKind.ADDITIVE
        )
        assert axis.kind is expected, axis


def test_shock_kind_values_serialise_as_plain_strings() -> None:
    assert ShockKind.ADDITIVE == "additive"
    assert ShockKind.MULTIPLICATIVE == "multiplicative"


def test_step_tables() -> None:
    assert tornado_steps(ShockKind.ADDITIVE) == pytest.approx((-0.01, 0.01), abs=TOL)
    assert tornado_steps(ShockKind.MULTIPLICATIVE) == pytest.approx((0.8, 1.2), abs=TOL)
    assert grid_steps(ShockKind.ADDITIVE) == pytest.approx(_ADDITIVE_STEPS, abs=TOL)
    assert grid_steps(ShockKind.MULTIPLICATIVE) == pytest.approx(_MULTIPLICATIVE_STEPS, abs=TOL)


# --------------------------------------------------------------------------- #
# shift_axis                                                                   #
# --------------------------------------------------------------------------- #


def test_shift_axis_moves_every_year_of_a_path_by_the_same_pp() -> None:
    base = _assumptions(revenue_growth=(0.30, 0.25, 0.20, 0.15, 0.10))
    shifted = shift_axis(base, SensitivityAxis.REVENUE_GROWTH, -0.01)
    assert shifted.revenue_growth == pytest.approx((0.29, 0.24, 0.19, 0.14, 0.09), abs=TOL)


def test_shift_axis_adds_to_a_scalar_rate() -> None:
    shifted = shift_axis(_assumptions(), SensitivityAxis.TERMINAL_GROWTH, 0.01)
    assert shifted.terminal_growth == pytest.approx(0.03, abs=TOL)


def test_shift_axis_multiplies_sales_to_capital() -> None:
    shifted = shift_axis(_assumptions(), SensitivityAxis.SALES_TO_CAPITAL, 1.2)
    assert shifted.sales_to_capital == pytest.approx(2.4, abs=TOL)


def test_shift_axis_couples_wacc_path_and_tax_rate_path() -> None:
    base = damodaran_assumptions()
    assert base.wacc_path is not None and base.tax_rate_path is not None

    coe = shift_axis(base, SensitivityAxis.COST_OF_EQUITY, 0.01)
    assert coe.cost_of_equity == pytest.approx(base.cost_of_equity + 0.01, abs=TOL)
    assert coe.wacc_path == pytest.approx(tuple(w + 0.01 for w in base.wacc_path), abs=TOL)

    tax = shift_axis(base, SensitivityAxis.TAX_RATE, -0.01)
    assert tax.tax_rate == pytest.approx(base.tax_rate - 0.01, abs=TOL)
    assert tax.tax_rate_path == pytest.approx(tuple(t - 0.01 for t in base.tax_rate_path), abs=TOL)


def test_shift_axis_does_not_mutate_input() -> None:
    base = _assumptions()
    snapshot = dataclasses.replace(base)
    shift_axis(base, SensitivityAxis.OPERATING_MARGIN, 0.01)
    assert base == snapshot


# --------------------------------------------------------------------------- #
# Tornado ends (acceptance criteria)                                           #
# --------------------------------------------------------------------------- #


def test_growth_one_percent_tornado_ends_are_zero_and_two_percent() -> None:
    entries = tornado(_financials(), _assumptions(revenue_growth=(0.01,) * 5))
    growth = _entry(entries, SensitivityAxis.REVENUE_GROWTH)
    assert growth.kind is ShockKind.ADDITIVE
    assert growth.low_value == pytest.approx(0.00, abs=TOL)
    assert growth.high_value == pytest.approx(0.02, abs=TOL)


def test_negative_growth_low_end_is_more_negative() -> None:
    entries = tornado(_financials(), _assumptions(revenue_growth=(-0.05,) * 5))
    growth = _entry(entries, SensitivityAxis.REVENUE_GROWTH)
    assert growth.low_value == pytest.approx(-0.06, abs=TOL)
    assert growth.high_value == pytest.approx(-0.04, abs=TOL)
    # Higher growth is the optimistic end: the bar does not invert.
    assert growth.intrinsic_high is not None and growth.intrinsic_low is not None
    assert growth.intrinsic_high > growth.intrinsic_low


def test_sales_to_capital_stays_multiplicative() -> None:
    entries = tornado(_financials(), _assumptions(sales_to_capital=2.0))
    s2c = _entry(entries, SensitivityAxis.SALES_TO_CAPITAL)
    assert s2c.kind is ShockKind.MULTIPLICATIVE
    assert s2c.low_value == pytest.approx(1.6, abs=TOL)
    assert s2c.high_value == pytest.approx(2.4, abs=TOL)


def test_rate_axes_move_one_pp_either_way() -> None:
    base = _assumptions()
    entries = tornado(_financials(), base)
    expected = {
        SensitivityAxis.OPERATING_MARGIN: 0.20,
        SensitivityAxis.TAX_RATE: 0.25,
        SensitivityAxis.TERMINAL_GROWTH: 0.02,
        SensitivityAxis.COST_OF_EQUITY: 0.11,
        SensitivityAxis.PRETAX_COST_OF_DEBT: 0.05,
    }
    for axis, value in expected.items():
        entry = _entry(entries, axis)
        assert entry.kind is ShockKind.ADDITIVE
        assert entry.low_value == pytest.approx(value - 0.01, abs=TOL), axis
        assert entry.high_value == pytest.approx(value + 0.01, abs=TOL), axis


def test_tornado_impact_is_recomputed_from_the_shifted_dcf() -> None:
    fin, base = _financials(), _assumptions()
    margin = _entry(tornado(fin, base), SensitivityAxis.OPERATING_MARGIN)
    low = dcf(fin, shift_axis(base, SensitivityAxis.OPERATING_MARGIN, -0.01)).intrinsic_value
    high = dcf(fin, shift_axis(base, SensitivityAxis.OPERATING_MARGIN, 0.01)).intrinsic_value
    assert margin.intrinsic_low == pytest.approx(low, rel=TOL)
    assert margin.intrinsic_high == pytest.approx(high, rel=TOL)
    assert margin.impact == pytest.approx(abs(high - low), rel=TOL)


# --------------------------------------------------------------------------- #
# Grid steps, kinds and centre                                                 #
# --------------------------------------------------------------------------- #


def test_grid_steps_per_kind() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.SALES_TO_CAPITAL,
    )
    assert grid.row_kind is ShockKind.ADDITIVE
    assert grid.row_steps == pytest.approx(_ADDITIVE_STEPS, abs=TOL)
    assert grid.col_kind is ShockKind.MULTIPLICATIVE
    assert grid.col_steps == pytest.approx(_MULTIPLICATIVE_STEPS, abs=TOL)


def test_grid_cell_applies_both_shifts() -> None:
    fin, base = _financials(), _assumptions()
    grid = grid_2d(fin, base, SensitivityAxis.OPERATING_MARGIN, SensitivityAxis.SALES_TO_CAPITAL)
    twisted = shift_axis(base, SensitivityAxis.OPERATING_MARGIN, -0.01)
    twisted = shift_axis(twisted, SensitivityAxis.SALES_TO_CAPITAL, 1.2)
    assert grid.cells[0][4].intrinsic_value == pytest.approx(
        dcf(fin, twisted).intrinsic_value, rel=TOL
    )


@pytest.mark.parametrize(
    ("axis_a", "axis_b"),
    [
        (SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.SALES_TO_CAPITAL),
        (SensitivityAxis.SALES_TO_CAPITAL, SensitivityAxis.COST_OF_EQUITY),
        (SensitivityAxis.COST_OF_EQUITY, SensitivityAxis.OPERATING_MARGIN),
    ],
)
def test_grid_centre_equals_base_margin_of_safety_exactly(
    axis_a: SensitivityAxis, axis_b: SensitivityAxis
) -> None:
    fin, base = _financials(), _assumptions()
    grid = grid_2d(fin, base, axis_a, axis_b, reference_price=50.0)
    assert grid.cells[2][2].margin_of_safety == dcf(fin, base).intrinsic_value / 50.0


# --------------------------------------------------------------------------- #
# Domain guards                                                                #
# --------------------------------------------------------------------------- #


def test_terminal_growth_plus_one_pp_at_wacc_is_none_and_ranked_last() -> None:
    # WACC = 0.8 * 0.11 + 0.2 * 0.05 * 0.75 = 0.0955; 0.087 + 0.01 = 0.097 >= WACC.
    entries = tornado(_financials(), _assumptions(terminal_growth=0.087))
    tg = _entry(entries, SensitivityAxis.TERMINAL_GROWTH)
    assert tg.intrinsic_high is None
    assert tg.intrinsic_low is not None
    assert tg.impact is None
    assert entries[-1] is tg
    assert all(e.impact is not None for e in entries[:-1])


def test_tax_rate_995_plus_one_pp_is_none_not_a_crash() -> None:
    entries = tornado(_financials(), _assumptions(tax_rate=0.995))
    tax = _entry(entries, SensitivityAxis.TAX_RATE)
    assert tax.intrinsic_high is None
    assert isinstance(tax.intrinsic_low, float)
    assert tax.impact is None
    assert entries[-1] is tax


def test_tax_rate_below_zero_is_none() -> None:
    entries = tornado(_financials(), _assumptions(tax_rate=0.005))
    tax = _entry(entries, SensitivityAxis.TAX_RATE)
    assert tax.intrinsic_low is None
    assert tax.intrinsic_high is not None


def test_tax_rate_path_outside_unit_interval_is_none() -> None:
    base = damodaran_assumptions()
    assert base.tax_rate_path is not None
    path = (0.995, *base.tax_rate_path[1:])
    entries = tornado(damodaran_financials(), dataclasses.replace(base, tax_rate_path=path))
    assert _entry(entries, SensitivityAxis.TAX_RATE).intrinsic_high is None


def test_cost_of_debt_shifted_to_zero_or_below_is_none() -> None:
    entries = tornado(_financials(), _assumptions(pretax_cost_of_debt=0.005))
    debt = _entry(entries, SensitivityAxis.PRETAX_COST_OF_DEBT)
    assert debt.intrinsic_low is None
    assert debt.intrinsic_high is not None


def test_cost_of_equity_shifted_to_zero_or_below_is_none() -> None:
    entries = tornado(_financials(), _assumptions(cost_of_equity=0.005, terminal_growth=0.0))
    coe = _entry(entries, SensitivityAxis.COST_OF_EQUITY)
    assert coe.intrinsic_low is None


def test_wacc_path_element_shifted_to_zero_or_below_is_none() -> None:
    base = damodaran_assumptions()
    assert base.wacc_path is not None
    path = (0.005, *base.wacc_path[1:])
    entries = tornado(damodaran_financials(), dataclasses.replace(base, wacc_path=path))
    coe = _entry(entries, SensitivityAxis.COST_OF_EQUITY)
    assert coe.intrinsic_low is None
    assert coe.intrinsic_high is not None


def test_base_on_domain_edge_keeps_a_valued_centre() -> None:
    fin, base = _financials(), _assumptions(pretax_cost_of_debt=0.0)
    grid = grid_2d(fin, base, SensitivityAxis.PRETAX_COST_OF_DEBT, SensitivityAxis.OPERATING_MARGIN)
    assert grid.cells[2][2].intrinsic_value == dcf(fin, base).intrinsic_value
    for row in grid.cells[:2]:
        assert all(cell.intrinsic_value is None for cell in row)
    for row in grid.cells[2:]:
        assert all(cell.intrinsic_value is not None for cell in row)


def test_grid_out_of_domain_cells_have_no_margin_of_safety() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(terminal_growth=0.087),
        SensitivityAxis.TERMINAL_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
        reference_price=50.0,
    )
    # Rows +0.5pp (0.092) and +1pp (0.097): 0.097 >= 0.0955 diverges.
    assert all(cell.intrinsic_value is None for cell in grid.cells[4])
    assert all(cell.margin_of_safety is None for cell in grid.cells[4])
    assert grid.cells[2][2].margin_of_safety is not None


def test_other_value_errors_still_surface() -> None:
    fin = Financials(revenue=1000.0, net_debt=500.0, shares_diluted=0.0)
    with pytest.raises(ValueError, match="shares_diluted"):
        tornado(fin, _assumptions())
