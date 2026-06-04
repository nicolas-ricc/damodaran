"""Unit tests for sensitivity analysis (issue #13 / M4.3, spec §7.4).

Two pure functions over the §7.2 DCF:

* :func:`tornado` — moves each assumption ±20% and ranks the swing in the
  per-share intrinsic value, descending by absolute impact.
* :func:`grid_2d` — a 5x5 grid over the two chosen assumptions with a
  margin-of-safety (vs the base case) per cell.

Every expected number below is derived from the DCF arithmetic itself (run
once over a known fixture), so these tests pin the *ordering* and *structure*
required by the acceptance criteria rather than re-deriving the DCF formula.
"""

from __future__ import annotations

import pytest

from bot.valuator.dcf import Assumptions, Financials, dcf
from bot.valuator.sensitivity import (
    SensitivityAxis,
    TornadoEntry,
    grid_2d,
    scale_axis,
    tornado,
)

TOL = 1e-9


def _financials() -> Financials:
    return Financials(revenue=1000.0, net_debt=500.0, shares_diluted=100.0)


def _assumptions() -> Assumptions:
    return Assumptions(
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


# --------------------------------------------------------------------------- #
# scale_axis — the building block both functions share                        #
# --------------------------------------------------------------------------- #


def test_scale_axis_scales_scalar_assumption() -> None:
    base = _assumptions()
    scaled = scale_axis(base, SensitivityAxis.TERMINAL_GROWTH, 1.2)
    assert scaled.terminal_growth == pytest.approx(0.02 * 1.2, abs=TOL)
    # Everything else is untouched.
    assert scaled.tax_rate == base.tax_rate
    assert scaled.revenue_growth == base.revenue_growth


def test_scale_axis_scales_every_year_of_a_path() -> None:
    base = _assumptions()
    scaled = scale_axis(base, SensitivityAxis.REVENUE_GROWTH, 0.8)
    assert scaled.revenue_growth == pytest.approx(
        tuple(g * 0.8 for g in base.revenue_growth), abs=TOL
    )
    assert scaled.operating_margin == base.operating_margin


def test_scale_axis_does_not_mutate_input() -> None:
    base = _assumptions()
    scale_axis(base, SensitivityAxis.OPERATING_MARGIN, 1.2)
    assert base.operating_margin == (0.20, 0.20, 0.20, 0.20, 0.20)


# --------------------------------------------------------------------------- #
# tornado                                                                     #
# --------------------------------------------------------------------------- #


def test_tornado_has_one_entry_per_axis() -> None:
    entries = tornado(_financials(), _assumptions())
    assert {e.axis for e in entries} == set(SensitivityAxis)
    assert len(entries) == len(SensitivityAxis)


def test_tornado_entry_records_both_swung_values_and_their_intrinsics() -> None:
    fin, base = _financials(), _assumptions()
    entries = {e.axis: e for e in tornado(fin, base)}
    entry = entries[SensitivityAxis.OPERATING_MARGIN]

    # +20% / -20% margins, recomputed independently.
    high = dcf(fin, scale_axis(base, SensitivityAxis.OPERATING_MARGIN, 1.2))
    low = dcf(fin, scale_axis(base, SensitivityAxis.OPERATING_MARGIN, 0.8))

    assert entry.high_value == pytest.approx(0.20 * 1.2, abs=TOL)
    assert entry.low_value == pytest.approx(0.20 * 0.8, abs=TOL)
    assert entry.intrinsic_high == pytest.approx(high.intrinsic_value, abs=TOL)
    assert entry.intrinsic_low == pytest.approx(low.intrinsic_value, abs=TOL)
    assert entry.impact == pytest.approx(
        abs(high.intrinsic_value - low.intrinsic_value), abs=TOL
    )


def test_tornado_is_ordered_descending_by_abs_impact() -> None:
    entries = tornado(_financials(), _assumptions())
    impacts = [e.impact for e in entries]
    assert impacts == sorted(impacts, reverse=True)
    assert all(i >= 0.0 for i in impacts)


def test_tornado_ordering_is_the_known_ranking_for_the_fixture() -> None:
    # Computed once from the DCF over the fixture. The discount rate dominates
    # (it scales the whole stream and the ~74% terminal-value share), then the
    # operating margin, then the tax rate, with the near-flat reinvestment /
    # debt-cost sensitivities last.
    entries = tornado(_financials(), _assumptions())
    ranking = [e.axis for e in entries]
    assert ranking == [
        SensitivityAxis.COST_OF_EQUITY,
        SensitivityAxis.OPERATING_MARGIN,
        SensitivityAxis.TAX_RATE,
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.TERMINAL_GROWTH,
        SensitivityAxis.SALES_TO_CAPITAL,
        SensitivityAxis.PRETAX_COST_OF_DEBT,
    ]


def test_tornado_each_entry_is_a_tornado_entry() -> None:
    for entry in tornado(_financials(), _assumptions()):
        assert isinstance(entry, TornadoEntry)


# --------------------------------------------------------------------------- #
# grid_2d                                                                      #
# --------------------------------------------------------------------------- #


def test_grid_2d_is_five_by_five() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
    )
    assert len(grid.row_multipliers) == 5
    assert len(grid.col_multipliers) == 5
    assert len(grid.cells) == 5
    assert all(len(row) == 5 for row in grid.cells)


def test_grid_2d_multipliers_span_plus_minus_twenty_percent() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
    )
    assert grid.row_multipliers == pytest.approx((0.8, 0.9, 1.0, 1.1, 1.2), abs=TOL)
    assert grid.col_multipliers == pytest.approx((0.8, 0.9, 1.0, 1.1, 1.2), abs=TOL)


def test_grid_2d_records_the_axes() -> None:
    grid = grid_2d(
        _financials(),
        _assumptions(),
        SensitivityAxis.REVENUE_GROWTH,
        SensitivityAxis.OPERATING_MARGIN,
    )
    assert grid.axis_a is SensitivityAxis.REVENUE_GROWTH
    assert grid.axis_b is SensitivityAxis.OPERATING_MARGIN


def test_grid_2d_centre_cell_is_the_base_case() -> None:
    fin, base = _financials(), _assumptions()
    grid = grid_2d(
        fin, base, SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.OPERATING_MARGIN
    )
    centre = grid.cells[2][2]
    base_intrinsic = dcf(fin, base).intrinsic_value
    assert centre.intrinsic_value == pytest.approx(base_intrinsic, abs=TOL)
    # Margin of safety at the base case, relative to the base case, is 1.0.
    assert centre.margin_of_safety == pytest.approx(1.0, abs=TOL)


def test_grid_2d_cell_applies_both_axes() -> None:
    fin, base = _financials(), _assumptions()
    grid = grid_2d(
        fin, base, SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.OPERATING_MARGIN
    )
    # Top-left cell: row multiplier 0.8 on axis_a, col multiplier 0.8 on axis_b.
    twisted = scale_axis(base, SensitivityAxis.REVENUE_GROWTH, 0.8)
    twisted = scale_axis(twisted, SensitivityAxis.OPERATING_MARGIN, 0.8)
    expected = dcf(fin, twisted).intrinsic_value
    assert grid.cells[0][0].intrinsic_value == pytest.approx(expected, abs=TOL)


def test_grid_2d_margin_of_safety_is_intrinsic_over_base() -> None:
    fin, base = _financials(), _assumptions()
    grid = grid_2d(
        fin, base, SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.OPERATING_MARGIN
    )
    base_intrinsic = dcf(fin, base).intrinsic_value
    for row in grid.cells:
        for cell in row:
            assert cell.margin_of_safety == pytest.approx(
                cell.intrinsic_value / base_intrinsic, abs=TOL
            )


def test_grid_2d_rejects_identical_axes() -> None:
    with pytest.raises(ValueError, match="distinct"):
        grid_2d(
            _financials(),
            _assumptions(),
            SensitivityAxis.REVENUE_GROWTH,
            SensitivityAxis.REVENUE_GROWTH,
        )
