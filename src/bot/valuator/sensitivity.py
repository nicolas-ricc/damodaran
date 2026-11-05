"""Sensitivity analysis over the two-stage DCF (spec §7.4, issue #13 / M4.3, #217).

A single intrinsic value is "a point in a cloud" (spec §7.4): the headline only
means something next to the swing it shows under plausible alternative
assumptions. Two pure views over :func:`bot.valuator.dcf.dcf` make that swing
explicit. Each assumption is shocked in the unit it is quoted in (:class:`ShockKind`):
a rate axis (growth, margin, tax, terminal growth, cost of equity, cost of debt)
moves by *percentage points*, because ×0.8 / ×1.2 of a 2% rate is a 0.4pp move
while the same factor on a 40% rate is 8pp; ``sales_to_capital`` is a ratio, not
a rate, and moves by a factor.

* :func:`tornado` — move each assumption one at a time (base -1pp / +1pp for a
  rate axis, ×0.8 / ×1.2 for ``sales_to_capital``) and rank the resulting change
  in per-share intrinsic value, descending by absolute impact. The widest bars
  are the assumptions the thesis actually rests on.
* :func:`grid_2d` — a 5x5 grid over two chosen assumptions (typically the two
  widest tornado bars, growth x margin) with a margin-of-safety per cell, so
  the joint sensitivity is visible rather than just the two marginals. Rate
  axes step -1, -0.5, 0, +0.5, +1 pp; ``sales_to_capital`` steps ×0.8 … ×1.2.

When the assumptions carry a ``wacc_path`` (a story's all-in discount rate) the
cost-of-equity axis shifts that path by the same step and the cost-of-debt axis
is dropped, since it no longer moves the value; a ``tax_rate_path`` is shifted
with the tax rate.

A shift can leave the DCF's domain (terminal growth at or above WACC, a tax rate
outside [0, 1), a cost of equity or debt at or below 0); that scenario has no
value and is reported as ``None`` rather than crashing the analysis.

:func:`scenario_range` runs a plain DCF per named case (base plus the story's
scenarios) and returns the values side by side (#197).

Everything here is pure: no I/O, no global state, and the input assumptions are
never mutated — each scenario is built from a fresh, shifted copy via
:func:`shift_axis`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Mapping
from enum import StrEnum
from typing import Any

from bot.valuator.dcf import Assumptions, Financials, dcf, terminal_wacc

#: Tornado shock of a rate axis: base -1pp and base +1pp.
_TORNADO_SHIFT = 0.01

#: Tornado ends of a multiplicative axis: ×0.8 and ×1.2.
_TORNADO_LOW = 0.8
_TORNADO_HIGH = 1.2

#: Additive steps (percentage points) across the five rows/columns of the 2-D grid.
_GRID_SHIFTS: tuple[float, float, float, float, float] = (-0.01, -0.005, 0.0, 0.005, 0.01)

#: Multiplicative steps across the five rows/columns of the 2-D grid.
_GRID_MULTIPLIERS: tuple[float, float, float, float, float] = (0.8, 0.9, 1.0, 1.1, 1.2)


class ShockKind(StrEnum):
    """How an axis is shocked: by adding percentage points or by a factor."""

    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


def _identity(kind: ShockKind) -> float:
    """The step that leaves an axis unchanged (``0.0`` additive, ``1.0`` multiplicative)."""
    return 0.0 if kind is ShockKind.ADDITIVE else 1.0


def tornado_steps(kind: ShockKind) -> tuple[float, float]:
    """The ``(low, high)`` tornado steps for ``kind``: ``(-0.01, 0.01)`` or ``(0.8, 1.2)``."""
    if kind is ShockKind.ADDITIVE:
        return (-_TORNADO_SHIFT, _TORNADO_SHIFT)
    return (_TORNADO_LOW, _TORNADO_HIGH)


def grid_steps(kind: ShockKind) -> tuple[float, float, float, float, float]:
    """The five 2-D grid steps for ``kind``, centre (the base case) at index 2."""
    return _GRID_SHIFTS if kind is ShockKind.ADDITIVE else _GRID_MULTIPLIERS


class SensitivityAxis(StrEnum):
    """A DCF assumption that sensitivity analysis can vary.

    Each member names a field of :class:`bot.valuator.dcf.Assumptions`. The
    path-valued fields (``revenue_growth``, ``operating_margin``) are shifted
    element-wise — every forecast year moves by the same step — while the
    scalar fields are shifted directly. :attr:`kind` says whether a step is
    added (percentage points) or multiplied (a factor).
    """

    REVENUE_GROWTH = "revenue_growth"
    OPERATING_MARGIN = "operating_margin"
    TAX_RATE = "tax_rate"
    SALES_TO_CAPITAL = "sales_to_capital"
    TERMINAL_GROWTH = "terminal_growth"
    COST_OF_EQUITY = "cost_of_equity"
    PRETAX_COST_OF_DEBT = "pretax_cost_of_debt"

    @property
    def kind(self) -> ShockKind:
        """``MULTIPLICATIVE`` for ``sales_to_capital`` (a ratio), else ``ADDITIVE``."""
        if self is SensitivityAxis.SALES_TO_CAPITAL:
            return ShockKind.MULTIPLICATIVE
        return ShockKind.ADDITIVE


#: Axes whose underlying assumption is a per-year path rather than a scalar.
PATH_AXES = frozenset({SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.OPERATING_MARGIN})


@dataclasses.dataclass(frozen=True)
class TornadoEntry:
    """One assumption's low/high impact on intrinsic value (spec §7.4).

    Attributes:
        axis: The assumption that was moved.
        kind: How it was moved: base -1pp / +1pp (``ADDITIVE``) or ×0.8 / ×1.2
            (``MULTIPLICATIVE``, ``sales_to_capital`` only).
        low_value: The assumption's value at the low end. For a path axis this
            is *year 1 only* (``base_path[0]`` shifted by the low step) — every
            year moves by the same step (see :func:`shift_axis`), but a
            story-branched path (e.g. a high-growth fade or margin ramp, spec
            §7.1) is not uniform across years, so year 1 is not representative
            of the whole path; it is reported anyway as the year-1 figure,
            consistent with how the assumptions table labels path values "(yr 1)".
        high_value: The assumption's value at the high end (the high step applied
            to ``base_path[0]`` for a path axis, "(yr 1)" as above).
        intrinsic_low: Per-share intrinsic value with the axis at ``low_value``,
            or ``None`` if that shift leaves the DCF's domain.
        intrinsic_high: Per-share intrinsic value with the axis at ``high_value``
            (``None`` likewise).
        impact: ``abs(intrinsic_high - intrinsic_low)`` — the bar width by which
            entries are ranked; ``None`` if either end is out of domain.
    """

    axis: SensitivityAxis
    kind: ShockKind
    low_value: float
    high_value: float
    intrinsic_low: float | None
    intrinsic_high: float | None
    impact: float | None


@dataclasses.dataclass(frozen=True)
class GridCell:
    """One cell of the 2-D sensitivity grid.

    Attributes:
        intrinsic_value: Per-share intrinsic value with both axes shifted by this
            cell's row/column steps, or ``None`` if that scenario is outside the
            DCF's valid domain (e.g. terminal growth shifted to WACC or beyond,
            so the perpetuity diverges, or a tax rate outside [0, 1)).
        margin_of_safety: ``intrinsic_value / reference_price`` — the same
            quantity as the report's headline margin of safety, so the centre
            cell equals it exactly. ``None`` when the cell is out of domain or
            no (positive) reference price is available.
    """

    intrinsic_value: float | None
    margin_of_safety: float | None


@dataclasses.dataclass(frozen=True)
class Grid2D:
    """A 5x5 sensitivity grid over two assumptions (spec §7.4).

    ``cells[i][j]`` shifts ``axis_a`` by ``row_steps[i]`` and ``axis_b`` by
    ``col_steps[j]``; a step is percentage points for an ``ADDITIVE`` axis and a
    factor for a ``MULTIPLICATIVE`` one. The centre (``[2][2]``, both steps the
    identity) is the base case.

    Attributes:
        axis_a: The assumption varied across rows.
        axis_b: The assumption varied across columns.
        row_kind: How ``axis_a`` is stepped (see :class:`ShockKind`).
        col_kind: How ``axis_b`` is stepped.
        row_steps: Steps applied to ``axis_a``: -1 … +1pp (additive) or
            ×0.8 … ×1.2 (multiplicative).
        col_steps: Steps applied to ``axis_b``, likewise.
        cells: The 5x5 matrix of results, row-major (``cells[row][col]``).
        reference_price: The price each cell's margin of safety was measured
            against, or ``None`` if no price was available (every cell's
            ``margin_of_safety`` is then ``None`` too).
    """

    axis_a: SensitivityAxis
    axis_b: SensitivityAxis
    row_kind: ShockKind
    col_kind: ShockKind
    row_steps: tuple[float, float, float, float, float]
    col_steps: tuple[float, float, float, float, float]
    cells: tuple[tuple[GridCell, ...], ...]
    reference_price: float | None = None


def shift_axis(assumptions: Assumptions, axis: SensitivityAxis, step: float) -> Assumptions:
    """Return a copy of ``assumptions`` with ``axis`` moved by ``step``.

    ``step`` is a percentage-point delta (added) for an ``ADDITIVE`` axis and a
    factor (multiplied) for a ``MULTIPLICATIVE`` one. Path axes move element-wise
    (every forecast year by the same step); scalar axes directly.
    ``COST_OF_EQUITY`` also moves ``wacc_path`` and ``TAX_RATE`` also moves
    ``tax_rate_path`` when set, by the same step. The input is never mutated.

    Args:
        assumptions: The base assumptions to copy from.
        axis: Which assumption to move.
        step: The delta (e.g. ``-0.01``) or factor (e.g. ``1.2``) to apply.

    Returns:
        A new :class:`Assumptions` with only ``axis`` (and its coupled path) changed.
    """
    additive = axis.kind is ShockKind.ADDITIVE

    def move(value: float) -> float:
        return value + step if additive else value * step

    if axis in PATH_AXES:
        current: tuple[float, ...] = getattr(assumptions, axis.value)
        moved: Any = tuple(move(value) for value in current)
    else:
        scalar: float = getattr(assumptions, axis.value)
        moved = move(scalar)
    changes: dict[str, Any] = {axis.value: moved}
    if axis is SensitivityAxis.COST_OF_EQUITY and assumptions.wacc_path is not None:
        changes["wacc_path"] = tuple(move(value) for value in assumptions.wacc_path)
    elif axis is SensitivityAxis.TAX_RATE and assumptions.tax_rate_path is not None:
        changes["tax_rate_path"] = tuple(move(value) for value in assumptions.tax_rate_path)
    return dataclasses.replace(assumptions, **changes)


def active_axes(assumptions: Assumptions) -> tuple[SensitivityAxis, ...]:
    """The axes that can move the value, in enum order.

    Every axis, except ``PRETAX_COST_OF_DEBT`` when ``wacc_path`` is set: the
    path replaces the built-up WACC, so the cost of debt no longer matters.
    """
    return tuple(
        axis
        for axis in SensitivityAxis
        if not (axis is SensitivityAxis.PRETAX_COST_OF_DEBT and assumptions.wacc_path is not None)
    )


def _safe_intrinsic(
    financials: Financials,
    assumptions: Assumptions,
    moved: Collection[SensitivityAxis] = (),
) -> float | None:
    """Per-share intrinsic value, or ``None`` if the scenario is out of domain.

    A shift leaves the DCF's valid range when it pushes ``terminal_growth`` up to
    or past WACC (the perpetuity diverges), or, for an axis in ``moved``, takes a
    rate outside its range: ``TAX_RATE`` with ``tax_rate`` (or any
    ``tax_rate_path`` element) outside ``[0, 1)``, ``COST_OF_EQUITY`` with
    ``cost_of_equity`` or any ``wacc_path`` element ``<= 0``, and
    ``PRETAX_COST_OF_DEBT`` ``<= 0``. Such a scenario has no meaningful value, so
    it is reported as a ``None`` sentinel. The range guards cover only the axes
    actually moved, so a base case sitting on a domain edge (a hand-written
    ``pretax_cost_of_debt: 0``) keeps a valued centre; the ``terminal_growth``
    guard is unconditional. Any *other* :class:`ValueError` from :func:`dcf` is a
    genuine bug and is left to surface.
    """
    if assumptions.terminal_growth >= terminal_wacc(assumptions):
        return None
    if SensitivityAxis.TAX_RATE in moved:
        taxes = (assumptions.tax_rate, *(assumptions.tax_rate_path or ()))
        if any(not 0.0 <= tax < 1.0 for tax in taxes):
            return None
    if SensitivityAxis.COST_OF_EQUITY in moved:
        costs = (assumptions.cost_of_equity, *(assumptions.wacc_path or ()))
        if any(cost <= 0.0 for cost in costs):
            return None
    if SensitivityAxis.PRETAX_COST_OF_DEBT in moved and assumptions.pretax_cost_of_debt <= 0.0:
        return None
    return dcf(financials, assumptions).intrinsic_value


def _axis_endpoint_value(assumptions: Assumptions, axis: SensitivityAxis) -> float:
    """The scalar value reported for an axis's swung endpoint.

    For a path axis this is *year 1 only* (``path[0]``). ``shift_axis`` moves
    every year by the same step, so this is exact for a flat/uniform
    path, but a story-branched path (a high-growth fade or margin ramp, spec
    §7.1) is not uniform across years — year 1 is then only the first point of
    a moving path, not a stand-in for the whole horizon. Callers that display
    this value must label it "(yr 1)" for path axes, the same convention the
    assumptions table uses, so the report never implies a flat path that isn't
    one.
    """
    if axis in PATH_AXES:
        path: tuple[float, ...] = getattr(assumptions, axis.value)
        return path[0]
    value: float = getattr(assumptions, axis.value)
    return value


def tornado(financials: Financials, base_assumptions: Assumptions) -> list[TornadoEntry]:
    """Rank each assumption by its low/high impact on intrinsic value (spec §7.4).

    Each active axis (see :func:`active_axes`) is moved one at a time to its low
    and high end (base -1pp / +1pp for a rate axis, ×0.8 / ×1.2 for
    ``sales_to_capital``; see :func:`tornado_steps`), and the swing in per-share
    intrinsic value is recorded. An end outside the DCF's domain is ``None`` and
    its entry is ranked last. The returned list is ordered descending by absolute
    impact, so the first entry is the assumption the valuation is most sensitive to.

    Args:
        financials: The company's current-year financial state.
        base_assumptions: The base-case projection and discount-rate inputs.

    Returns:
        One :class:`TornadoEntry` per active axis, descending by absolute
        impact.
    """
    entries: list[TornadoEntry] = []
    for axis in active_axes(base_assumptions):
        low_step, high_step = tornado_steps(axis.kind)
        low_assumptions = shift_axis(base_assumptions, axis, low_step)
        high_assumptions = shift_axis(base_assumptions, axis, high_step)
        intrinsic_low = _safe_intrinsic(financials, low_assumptions, (axis,))
        intrinsic_high = _safe_intrinsic(financials, high_assumptions, (axis,))
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
                kind=axis.kind,
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
    *,
    reference_price: float | None = None,
) -> Grid2D:
    """Build a 5x5 margin-of-safety grid over two assumptions (spec §7.4).

    Each cell's ``margin_of_safety`` is ``intrinsic_value / reference_price`` — the
    same quantity as the report's headline margin of safety, so the centre cell
    equals it exactly. Without a ``reference_price`` (or with a non-positive one)
    every cell's margin is ``None`` while intrinsic values are still computed: the
    grid remains readable as a value surface.

    Rate axes step -1, -0.5, 0, +0.5, +1 pp and ``sales_to_capital`` steps
    ×0.8 … ×1.2 (see :func:`grid_steps`). A cell whose shifted assumptions leave the
    model's domain (terminal growth at or above WACC, a tax rate outside [0, 1), a
    cost of capital at or below 0) has no intrinsic value, hence no margin of
    safety. The range guards apply only to an axis moved off its identity step, so
    the centre keeps its value.

    Args:
        financials: The company's current-year financial state.
        base_assumptions: The base-case projection and discount-rate inputs.
        axis_a: The assumption varied across rows.
        axis_b: The assumption varied across columns (must differ from ``axis_a``).
        reference_price: The current price to measure margin of safety against.

    Returns:
        A :class:`Grid2D` with the 5x5 matrix of results.

    Raises:
        ValueError: If ``axis_a`` and ``axis_b`` are the same axis.
    """
    if axis_a is axis_b:
        raise ValueError("grid_2d requires two distinct axes")

    row_kind, col_kind = axis_a.kind, axis_b.kind
    row_steps, col_steps = grid_steps(row_kind), grid_steps(col_kind)

    rows: list[tuple[GridCell, ...]] = []
    for row_step in row_steps:
        row_assumptions = shift_axis(base_assumptions, axis_a, row_step)
        cells: list[GridCell] = []
        for col_step in col_steps:
            cell_assumptions = shift_axis(row_assumptions, axis_b, col_step)
            moved = [
                axis
                for axis, step, kind in (
                    (axis_a, row_step, row_kind),
                    (axis_b, col_step, col_kind),
                )
                if step != _identity(kind)
            ]
            intrinsic_value = _safe_intrinsic(financials, cell_assumptions, moved)
            # Margin of safety is value-over-price, identical in meaning to the
            # report headline. It needs an in-domain cell and a positive price.
            margin_of_safety = (
                intrinsic_value / reference_price
                if intrinsic_value is not None
                and reference_price is not None
                and reference_price > 0.0
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
        row_kind=row_kind,
        col_kind=col_kind,
        row_steps=row_steps,
        col_steps=col_steps,
        cells=tuple(rows),
        reference_price=reference_price,
    )


@dataclasses.dataclass(frozen=True)
class ScenarioResult:
    """The DCF values of one named scenario."""

    name: str
    intrinsic_value: float
    equity_value: float
    enterprise_value: float


def scenario_range(
    cases: Mapping[str, tuple[Financials, Assumptions]],
) -> tuple[ScenarioResult, ...]:
    """One plain :func:`dcf` per case, in mapping order."""
    results = []
    for name, (financials, assumptions) in cases.items():
        result = dcf(financials, assumptions)
        results.append(
            ScenarioResult(
                name=name,
                intrinsic_value=result.intrinsic_value,
                equity_value=result.equity_value,
                enterprise_value=result.enterprise_value,
            )
        )
    return tuple(results)
