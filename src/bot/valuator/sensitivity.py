"""Sensitivity analysis over the two-stage DCF (spec §7.4, issue #13 / M4.3).

A single intrinsic value is "a point in a cloud" (spec §7.4): the headline only
means something next to the swing it shows under plausible alternative
assumptions. Two pure views over :func:`bot.valuator.dcf.dcf` make that swing
explicit:

* :func:`tornado` — move each assumption ±20% one at a time and rank the
  resulting change in per-share intrinsic value, descending by absolute impact.
  The widest bars are the assumptions the thesis actually rests on.
* :func:`grid_2d` — a 5x5 grid over two chosen assumptions (typically the two
  widest tornado bars, growth x margin) with a margin-of-safety per cell, so
  the joint sensitivity is visible rather than just the two marginals.

Everything here is pure: no I/O, no global state, and the input assumptions are
never mutated — each scenario is built from a fresh, scaled copy via
:func:`scale_axis`.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum
from typing import Any

from bot.valuator.dcf import Assumptions, Financials, _wacc, dcf

#: The two ends each assumption is swung to in the tornado.
_TORNADO_LOW = 0.8
_TORNADO_HIGH = 1.2

#: Multipliers spanning ±20% across the five rows/columns of the 2-D grid.
_GRID_MULTIPLIERS: tuple[float, float, float, float, float] = (0.8, 0.9, 1.0, 1.1, 1.2)


class SensitivityAxis(StrEnum):
    """A DCF assumption that sensitivity analysis can vary.

    Each member names a field of :class:`bot.valuator.dcf.Assumptions`. The
    path-valued fields (``revenue_growth``, ``operating_margin``) are scaled
    element-wise — every forecast year moves by the same multiplier — while the
    scalar fields are scaled directly.
    """

    REVENUE_GROWTH = "revenue_growth"
    OPERATING_MARGIN = "operating_margin"
    TAX_RATE = "tax_rate"
    SALES_TO_CAPITAL = "sales_to_capital"
    TERMINAL_GROWTH = "terminal_growth"
    COST_OF_EQUITY = "cost_of_equity"
    PRETAX_COST_OF_DEBT = "pretax_cost_of_debt"


#: Axes whose underlying assumption is a per-year path rather than a scalar.
_PATH_AXES = frozenset({SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.OPERATING_MARGIN})


@dataclasses.dataclass(frozen=True)
class TornadoEntry:
    """One assumption's ±20% impact on intrinsic value (spec §7.4).

    Attributes:
        axis: The assumption that was moved.
        low_value: The assumption's value at the -20% end. For a path axis this
            is the (uniform) scaled per-year value, i.e. ``base * 0.8``.
        high_value: The assumption's value at the +20% end (``base * 1.2``).
        intrinsic_low: Per-share intrinsic value with the axis at ``low_value``.
        intrinsic_high: Per-share intrinsic value with the axis at ``high_value``.
        impact: ``abs(intrinsic_high - intrinsic_low)`` — the bar width by which
            entries are ranked.
    """

    axis: SensitivityAxis
    low_value: float
    high_value: float
    intrinsic_low: float | None
    intrinsic_high: float | None
    impact: float | None


@dataclasses.dataclass(frozen=True)
class GridCell:
    """One cell of the 2-D sensitivity grid.

    Attributes:
        intrinsic_value: Per-share intrinsic value with both axes scaled by this
            cell's row/column multipliers, or ``None`` if that scenario is
            outside the DCF's valid domain (e.g. terminal growth scaled past
            WACC, so the perpetuity diverges).
        margin_of_safety: ``intrinsic_value`` relative to the base case
            (centre cell), i.e. ``intrinsic_value / base_intrinsic_value``. A
            value > 1 means the cell's assumptions are *more* favourable than
            the base case; the centre cell is exactly 1. ``None`` when the cell
            (or the base case) is undefined.
    """

    intrinsic_value: float | None
    margin_of_safety: float | None


@dataclasses.dataclass(frozen=True)
class Grid2D:
    """A 5x5 sensitivity grid over two assumptions (spec §7.4).

    ``cells[i][j]`` scales ``axis_a`` by ``row_multipliers[i]`` and ``axis_b`` by
    ``col_multipliers[j]``. The centre (``[2][2]``, both multipliers 1.0) is the
    base case.

    Attributes:
        axis_a: The assumption varied across rows.
        axis_b: The assumption varied across columns.
        row_multipliers: Multipliers applied to ``axis_a`` (spanning ±20%).
        col_multipliers: Multipliers applied to ``axis_b`` (spanning ±20%).
        cells: The 5x5 matrix of results, row-major (``cells[row][col]``).
    """

    axis_a: SensitivityAxis
    axis_b: SensitivityAxis
    row_multipliers: tuple[float, float, float, float, float]
    col_multipliers: tuple[float, float, float, float, float]
    cells: tuple[tuple[GridCell, ...], ...]


def scale_axis(assumptions: Assumptions, axis: SensitivityAxis, multiplier: float) -> Assumptions:
    """Return a copy of ``assumptions`` with ``axis`` scaled by ``multiplier``.

    Path axes are scaled element-wise (every forecast year moves by the same
    factor); scalar axes are scaled directly. The input is never mutated.

    Args:
        assumptions: The base assumptions to copy from.
        axis: Which assumption to scale.
        multiplier: The factor to multiply the assumption by (e.g. ``1.2``).

    Returns:
        A new :class:`Assumptions` with only ``axis`` changed.
    """
    if axis in _PATH_AXES:
        current: tuple[float, ...] = getattr(assumptions, axis.value)
        scaled: Any = tuple(value * multiplier for value in current)
    else:
        scalar: float = getattr(assumptions, axis.value)
        scaled = scalar * multiplier
    return dataclasses.replace(assumptions, **{axis.value: scaled})


def _safe_intrinsic(financials: Financials, assumptions: Assumptions) -> float | None:
    """Per-share intrinsic value, or ``None`` if the scenario is out of domain.

    The only way ±20% scaling moves an assumption outside the DCF's valid range
    is by pushing ``terminal_growth`` up to or past WACC, where the perpetuity
    diverges (the other scaled inputs stay in domain: ``sales_to_capital`` stays
    positive and the paths/share count are untouched). That scenario has no
    meaningful value, so it is reported as a ``None`` sentinel. Any *other*
    :class:`ValueError` from :func:`dcf` is a genuine bug and is left to surface.
    """
    if assumptions.terminal_growth >= _wacc(assumptions):
        return None
    return dcf(financials, assumptions).intrinsic_value


def _axis_endpoint_value(assumptions: Assumptions, axis: SensitivityAxis) -> float:
    """The representative scalar value an axis holds in ``assumptions``.

    For a path axis this is the (uniform) per-year value; the scaled copies in a
    tornado keep that uniformity, so the first element is representative.
    """
    if axis in _PATH_AXES:
        path: tuple[float, ...] = getattr(assumptions, axis.value)
        return path[0]
    value: float = getattr(assumptions, axis.value)
    return value


def tornado(financials: Financials, base_assumptions: Assumptions) -> list[TornadoEntry]:
    """Rank each assumption by its ±20% impact on intrinsic value (spec §7.4).

    Each :class:`SensitivityAxis` is moved to -20% and +20% of its base value,
    one at a time, and the swing in per-share intrinsic value is recorded. The
    returned list is ordered descending by absolute impact, so the first entry
    is the assumption the valuation is most sensitive to.

    Args:
        financials: The company's current-year financial state.
        base_assumptions: The base-case projection and discount-rate inputs.

    Returns:
        One :class:`TornadoEntry` per axis, descending by absolute impact.
    """
    entries: list[TornadoEntry] = []
    for axis in SensitivityAxis:
        low_assumptions = scale_axis(base_assumptions, axis, _TORNADO_LOW)
        high_assumptions = scale_axis(base_assumptions, axis, _TORNADO_HIGH)
        intrinsic_low = _safe_intrinsic(financials, low_assumptions)
        intrinsic_high = _safe_intrinsic(financials, high_assumptions)
        # The swing is only defined when both ends are in domain; otherwise the
        # impact is unknown and the entry is ranked last.
        impact = (
            abs(intrinsic_high - intrinsic_low)
            if intrinsic_low is not None and intrinsic_high is not None
            else None
        )
        entries.append(
            TornadoEntry(
                axis=axis,
                low_value=_axis_endpoint_value(low_assumptions, axis),
                high_value=_axis_endpoint_value(high_assumptions, axis),
                intrinsic_low=intrinsic_low,
                intrinsic_high=intrinsic_high,
                impact=impact,
            )
        )
    # Descending by impact, with undefined-impact entries sorted last.
    entries.sort(key=lambda entry: (entry.impact is None, -(entry.impact or 0.0)))
    return entries


def grid_2d(
    financials: Financials,
    base_assumptions: Assumptions,
    axis_a: SensitivityAxis,
    axis_b: SensitivityAxis,
) -> Grid2D:
    """Build a 5x5 margin-of-safety grid over two assumptions (spec §7.4).

    ``axis_a`` varies across the rows and ``axis_b`` across the columns, each
    spanning ±20% in five steps ``(0.8, 0.9, 1.0, 1.1, 1.2)``. The centre cell
    (both multipliers 1.0) is the base case, against which every cell's
    margin of safety is measured.

    Args:
        financials: The company's current-year financial state.
        base_assumptions: The base-case projection and discount-rate inputs.
        axis_a: The assumption varied across rows.
        axis_b: The assumption varied across columns (must differ from ``axis_a``).

    Returns:
        A :class:`Grid2D` with the 5x5 matrix of results.

    Raises:
        ValueError: If ``axis_a`` and ``axis_b`` are the same axis.
    """
    if axis_a is axis_b:
        raise ValueError("grid_2d requires two distinct axes")

    base_intrinsic = _safe_intrinsic(financials, base_assumptions)

    rows: list[tuple[GridCell, ...]] = []
    for row_multiplier in _GRID_MULTIPLIERS:
        row_assumptions = scale_axis(base_assumptions, axis_a, row_multiplier)
        cells: list[GridCell] = []
        for col_multiplier in _GRID_MULTIPLIERS:
            cell_assumptions = scale_axis(row_assumptions, axis_b, col_multiplier)
            intrinsic_value = _safe_intrinsic(financials, cell_assumptions)
            # Margin of safety needs this cell in domain and a non-zero base to
            # divide by; a None or 0.0 base (degenerate, e.g. equity wiped out)
            # leaves every cell's MoS undefined rather than dividing by zero.
            margin_of_safety = (
                intrinsic_value / base_intrinsic
                if intrinsic_value is not None and base_intrinsic
                else None
            )
            cells.append(
                GridCell(
                    intrinsic_value=intrinsic_value,
                    margin_of_safety=margin_of_safety,
                )
            )
        rows.append(tuple(cells))

    return Grid2D(
        axis_a=axis_a,
        axis_b=axis_b,
        row_multipliers=_GRID_MULTIPLIERS,
        col_multipliers=_GRID_MULTIPLIERS,
        cells=tuple(rows),
    )
