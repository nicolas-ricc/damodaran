"""Spec §7.3 states the implemented assumption model (issue #238, folds in #207).

Analyst consensus is not a source, by decision (#63); #320 drops it from the spec.

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


def test_section_7_3_does_not_name_analyst_consensus() -> None:
    # #320: analyst consensus was dropped by decision (#63), not left planned.
    section = _section_7_3().lower()
    assert "consensus" not in section and "consenso" not in section


def test_garbage_in_risk_names_the_historical_cagr() -> None:
    text = _SPEC.read_text(encoding="utf-8")
    risks = text[text.index("## 16. ") :]
    risk = next(line for line in risks.splitlines() if line.startswith("4. **DCF garbage-in"))
    assert "consens" not in risk.lower()
    assert "CAGR histórico" in risk


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


def test_growth_docstring_states_the_decision() -> None:
    doc = _resolve_revenue_growth.__doc__ or ""
    assert "planned" not in doc and "not implemented" not in doc
    assert "#63" in doc
