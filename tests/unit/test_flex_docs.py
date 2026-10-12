"""The docs that used to say corporate_actions has no writer now point at the importer (#56)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_readme_has_the_flex_section() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Corporate actions via Flex Web Service" in readme
    assert (
        "Written from IBKR's documentation and not yet verified against the portal; see #110."
        in readme
    )
    assert "BOT_IBKR_FLEX_TOKEN" in readme and "BOT_IBKR_FLEX_QUERY_ID" in readme


@pytest.mark.parametrize(
    "path",
    ["docs/adr/0004-tws-api-via-ib-async.md", "src/bot/storage/schema.sql", "src/bot/portfolio/trades.py"],
)
def test_no_more_nothing_populates_wording(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "ibkr_flex" in text
    for stale in ("nothing populates it", "stays\n  empty", "stays empty", "nothing in this module populates it"):
        assert stale not in text
