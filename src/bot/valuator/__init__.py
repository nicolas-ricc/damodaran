"""Capa C — intrinsic valuation (DCF and supporting models).

The valuator turns a story's projected inputs into an intrinsic value via the
two-stage DCF of spec §7.2. Everything here is pure: :func:`dcf` performs no
I/O and mutates none of its arguments, so it is exhaustively testable against
ground-truth numbers computed by hand.
"""

from bot.valuator.dcf import Assumptions, DCFResult, Financials, YearProjection, dcf

__all__ = [
    "Assumptions",
    "DCFResult",
    "Financials",
    "YearProjection",
    "dcf",
]
