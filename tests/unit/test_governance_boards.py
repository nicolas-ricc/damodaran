"""The refresh boards say the fundamentals skip check counts governance filings (#275)."""

from __future__ import annotations

from pathlib import Path

import pytest

PIPELINE = Path(__file__).resolve().parents[2] / "docs" / "pipeline"
_CONST = "@const bot.ingest.sec_edgar.AUDITOR_CHANGE_ITEM"


def _line(board: str, needle: str) -> str:
    text = (PIPELINE / board).read_text("utf-8")
    lines = [ln for ln in text.splitlines() if ln.lstrip().startswith(needle)]
    assert len(lines) == 1, f"{board}: {needle!r} on {len(lines)} lines"
    return lines[0]


@pytest.mark.parametrize(
    ("board", "needle"),
    [
        ("refresh.d2", "skip: "),
        ("refresh-fundamentals.d2", "ticker_checked: "),
        ("refresh-fundamentals.d2", "edgar -> ticker_checked: "),
    ],
)
def test_skip_check_counts_late_filings_and_auditor_changes(board: str, needle: str) -> None:
    line = _line(board, needle)
    assert "10-K, 10-Q or 20-F filing date (amendments too)" in line
    assert "notification of late filing (NT 10-K, NT 10-Q)" in line
    assert "8-K reporting an auditor change (item 4.01)" in line
    assert _CONST in line


def test_filings_log_edge_says_8k_rows_carry_their_item_numbers() -> None:
    line = _line("refresh.d2", "fundamentals.import -> duckdb.filings_log: ")
    assert '"one row per form and filing date; 8-K rows carry their item numbers"' in line
