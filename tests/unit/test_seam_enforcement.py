"""The seam's enforcement line (spec: 'nothing outside fmp.py imports FmpClient').

A source-scan test, so a future import can't silently re-couple the pipeline
to one provider. cli.py is the sanctioned composition root for FmpProvider.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bot"


def _offenders(pattern: str, *, allowed: set[str]) -> list[str]:
    rx = re.compile(pattern)
    return [
        str(p.relative_to(SRC))
        for p in sorted(SRC.rglob("*.py"))
        if p.name not in allowed and rx.search(p.read_text(encoding="utf-8"))
    ]


def test_fmp_client_is_internal_to_the_adapter() -> None:
    assert _offenders(r"\bFmpClient\b", allowed={"fmp.py"}) == []


def test_only_the_composition_root_names_the_concrete_adapter() -> None:
    assert _offenders(r"\bFmpProvider\b", allowed={"fmp.py", "cli.py"}) == []
