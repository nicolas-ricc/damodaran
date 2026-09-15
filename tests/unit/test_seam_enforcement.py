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


def test_stooq_client_is_internal_to_its_adapters() -> None:
    assert _offenders(r"\bStooqClient\b", allowed={"stooq.py", "edgar_stooq.py"}) == []


def test_tiingo_client_is_internal_to_its_adapters() -> None:
    assert _offenders(r"\bTiingoClient\b", allowed={"tiingo.py", "edgar_tiingo.py"}) == []


def test_only_the_composition_root_names_the_free_stack_adapter() -> None:
    assert _offenders(r"\bEdgarStooqProvider\b", allowed={"edgar_stooq.py", "cli.py"}) == []


def test_only_the_composition_root_names_the_tiingo_adapter() -> None:
    assert _offenders(r"\bEdgarTiingoProvider\b", allowed={"edgar_tiingo.py", "cli.py"}) == []


def test_the_port_imports_no_concrete_adapter() -> None:
    port = (SRC / "ingest" / "provider.py").read_text(encoding="utf-8")
    concrete = r"(sec_edgar|fmp|stooq|edgar_stooq|tiingo|edgar_tiingo)"
    assert re.search(rf"from bot\.ingest\.{concrete}\b", port) is None
    assert re.search(rf"import bot\.ingest\.{concrete}\b", port) is None
