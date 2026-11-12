"""The rank() docstring describes the DCF fallback, not a pending M4.7 (#299)."""

from __future__ import annotations

from bot.screener.ranking import rank


def _doc() -> str:
    assert rank.__doc__ is not None
    return " ".join(rank.__doc__.split())


def test_rank_docstring_does_not_say_m47_is_pending() -> None:
    doc = _doc()
    assert "M4.7" not in doc
    assert "placeholder 0.5" not in doc


def test_rank_docstring_names_the_dcf_fallback() -> None:
    assert (
        "the neutral :data:`PLACEHOLDER_MARGIN_OF_SAFETY` when no DCF value is available" in _doc()
    )


def test_rank_docstring_keeps_the_unbounded_ratio() -> None:
    doc = _doc()
    assert "raw, absolute and unbounded ``intrinsic_value / price`` ratio" in doc
    assert "there is no strict ceiling" in doc
