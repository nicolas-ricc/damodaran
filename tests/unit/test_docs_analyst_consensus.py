"""No doc presents analyst consensus as specified or missing (#320).

#63 closed analyst consensus as wontfix: revenue growth starts at the company's
historical revenue CAGR and fades to terminal growth by year 10, by decision. A
doc may still name analyst consensus when it states that decision (cites #63).
Dated plans under ``docs/plans/`` are historical records: one that names it
carries ``BANNER`` instead of a rewritten body. ``docs/superpowers/plans/`` is
outside the criterion.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import bot.valuator.assumptions

_ROOT = Path(__file__).resolve().parents[2]
_PATTERN = re.compile(r"analyst[ _-]consensus|consens\w* de (los )?analistas", re.I)
_PENDING = re.compile(
    r"\b(planned|planificado|pendiente|todavía|pide|gap)\b|no implementado|not implemented", re.I
)
_SKIPPED = ("docs/superpowers/plans/",)
_PLANS = "docs/plans/"
_BINARY = (".png", ".b64")
BANNER = (
    "> **Superseded (#320):** analyst consensus is not a source, by decision (#63);"
    " mentions of it below are historical."
)


def _tracked_docs() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "docs"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.splitlines() if not p.startswith(_SKIPPED) and not p.endswith(_BINARY)]


def _offending_lines(text: str) -> list[int]:
    return [
        n
        for n, line in enumerate(text.splitlines(), 1)
        if _PATTERN.search(line) and ("#63" not in line or _PENDING.search(line))
    ]


def test_no_doc_presents_analyst_consensus_as_pending() -> None:
    offending = []
    for path in _tracked_docs():
        text = (_ROOT / path).read_text(encoding="utf-8", errors="replace")
        if path.startswith(_PLANS):
            if _PATTERN.search(text) and BANNER not in text:
                offending.append(f"{path}: no banner")
            continue
        offending += [f"{path}:{n}" for n in _offending_lines(text)]
    assert offending == []


def test_assumptions_module_docstring_has_no_consensus_layer() -> None:
    doc = bot.valuator.assumptions.__doc__ or ""
    assert "Analyst consensus  —" not in doc
    assert _offending_lines(doc) == []


def test_pending_wording_is_flagged() -> None:
    assert _offending_lines("analyst consensus is planned (#63)") == [1]
    assert _offending_lines("Gap: no analyst_consensus (#63)") == [1]
    assert _offending_lines("el consenso de analistas") == [1]
    assert _offending_lines("analyst consensus is not a source, by decision (#63)") == []
    assert _offending_lines("lo impide el consenso de analistas (#63)") == []
