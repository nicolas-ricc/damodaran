"""Capa C — intrinsic valuation (DCF and supporting models).

The valuator turns a story's projected inputs into an intrinsic value via the
two-stage DCF of spec §7.2. Everything here is pure: :func:`dcf` performs no
I/O and mutates none of its arguments, so it is exhaustively testable against
ground-truth numbers computed by hand.
"""

from bot.valuator.dcf import Assumptions, DCFResult, Financials, YearProjection, dcf
from bot.valuator.sensitivity import (
    Grid2D,
    GridCell,
    SensitivityAxis,
    TornadoEntry,
    grid_2d,
    scale_axis,
    tornado,
)

__all__ = [
    "Assumptions",
    "DCFResult",
    "Financials",
    "Grid2D",
    "GridCell",
    "SensitivityAxis",
    "TornadoEntry",
    "YearProjection",
    "dcf",
    "grid_2d",
    "scale_axis",
    "tornado",
]
