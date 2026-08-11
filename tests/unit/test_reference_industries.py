"""The canonical Damodaran industry taxonomy."""

from __future__ import annotations

from bot.reference.industries import DAMODARAN_INDUSTRIES


def test_damodaran_industries_is_the_canonical_taxonomy() -> None:
    assert "Semiconductor" in DAMODARAN_INDUSTRIES
    assert "Financial Svcs. (Non-bank & Insurance)" in DAMODARAN_INDUSTRIES
    # The aggregate rows of wacc.xls are not industries a company belongs to.
    assert "Total Market" not in DAMODARAN_INDUSTRIES
    assert len(DAMODARAN_INDUSTRIES) == 94
