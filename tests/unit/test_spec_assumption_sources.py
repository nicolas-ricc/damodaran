"""Spec §7.3 states the implemented assumption model (issue #238, folds in #207).

The source list is the ``AssumptionSource`` enum, and the growth row fades to
terminal growth by year 10, as ``_resolve_revenue_growth`` does.
"""

from __future__ import annotations

import re
from pathlib import Path

from bot.valuator.assumptions import AssumptionSource, _resolve_revenue_growth

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _ROOT / "docs" / "superpowers" / "specs" / "2026-05-25-investment-bot-design.md"
_SOURCE_BULLET = re.compile(r"^- `([a-z_]+)`:", re.M)


def _section_7_3() -> str:
    text = _SPEC.read_text(encoding="utf-8")
    return text[text.index("### 7.3 ") : text.index("### 7.4 ")]


def _growth_row() -> str:
    rows = [
        line for line in _section_7_3().splitlines() if line.startswith("| Revenue growth path")
    ]
    assert len(rows) == 1
    return rows[0]


def test_source_list_is_the_enum() -> None:
    listed = set(_SOURCE_BULLET.findall(_section_7_3()))
    assert listed == {source.value for source in AssumptionSource}


def test_analyst_consensus_only_as_not_implemented() -> None:
    lines = [line for line in _section_7_3().splitlines() if "analyst_consensus" in line]
    assert lines
    for line in lines:
        assert "no implementado" in line and "#63" in line


def test_growth_does_not_converge_to_gdp() -> None:
    section = _section_7_3()
    assert "converge a GDP nominal" not in section
    for match in re.finditer(r"onverge([^.|]*)", section):
        assert "al terminal growth" in match.group(1)


def test_growth_row_targets_terminal_growth_over_ten_years() -> None:
    row = _growth_row()
    assert "terminal growth" in row and "y10" in row and "10 años" in row
    assert row.count("|") == 4


def test_growth_docstring_drops_gdp_convergence() -> None:
    assert "convergence to nominal GDP" not in (_resolve_revenue_growth.__doc__ or "")
