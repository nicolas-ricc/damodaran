"""The PLACEHOLDER_MARGIN_OF_SAFETY comment describes the DCF fallback (#105)."""

from __future__ import annotations

import re
from pathlib import Path

from bot.screener import ranking
from bot.screener.ranking import PLACEHOLDER_MARGIN_OF_SAFETY

_RANKING = Path(__file__).resolve().parents[2] / "src" / "bot" / "screener" / "ranking.py"


def _placeholder_comment() -> str:
    """The ``#:`` comment directly above the constant, whitespace collapsed."""
    lines = _RANKING.read_text(encoding="utf-8").splitlines()
    assignments = [
        i for i, line in enumerate(lines) if line.startswith("PLACEHOLDER_MARGIN_OF_SAFETY = ")
    ]
    assert len(assignments) == 1, assignments
    comment: list[str] = []
    i = assignments[0] - 1
    while i >= 0 and lines[i].startswith("#:"):
        comment.insert(0, lines[i].removeprefix("#:"))
        i -= 1
    assert comment, "no #: comment directly above PLACEHOLDER_MARGIN_OF_SAFETY"
    return " ".join(" ".join(comment).split())


def test_comment_does_not_say_m47_is_pending() -> None:
    comment = _placeholder_comment()
    assert "M4.7" not in comment
    assert re.search(r"\buntil\b", comment, re.IGNORECASE) is None
    assert "cannot yet" not in comment.lower()


def test_comment_names_the_fallback_cases() -> None:
    comment = _placeholder_comment()
    assert "DCF cannot value" in comment
    assert "caller passes no margin" in comment
    assert "neither rewards nor penalises" in comment
    assert "ADR 0006" in comment


def test_placeholder_value_unchanged() -> None:
    assert PLACEHOLDER_MARGIN_OF_SAFETY == 0.5
    assert ranking.__doc__ is not None
    assert "(= 0.5)" in " ".join(ranking.__doc__.split())
