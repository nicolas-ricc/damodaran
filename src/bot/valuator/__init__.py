"""Capa C — intrinsic valuation (DCF and supporting models).

The valuator turns a story's projected inputs into an intrinsic value via the
two-stage DCF of spec §7.2. Everything here is pure: :func:`dcf` performs no
I/O and mutates none of its arguments, so it is exhaustively testable against
ground-truth numbers computed by hand.
"""

from bot.valuator.analysis import Analysis, SanityCheck, analyze
from bot.valuator.dcf import (
    Assumptions,
    DCFResult,
    Financials,
    YearProjection,
    dcf,
    terminal_wacc,
)
from bot.valuator.sensitivity import (
    Grid2D,
    GridCell,
    SensitivityAxis,
    ShockKind,
    TornadoEntry,
    active_axes,
    grid_2d,
    grid_steps,
    shift_axis,
    tornado,
    tornado_steps,
)

__all__ = [
    "Analysis",
    "Assumptions",
    "DCFResult",
    "Financials",
    "Grid2D",
    "GridCell",
    "SanityCheck",
    "SensitivityAxis",
    "ShockKind",
    "TornadoEntry",
    "YearProjection",
    "active_axes",
    "analyze",
    "dcf",
    "grid_2d",
    "grid_steps",
    "shift_axis",
    "terminal_wacc",
    "tornado",
    "tornado_steps",
]
