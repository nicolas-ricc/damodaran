"""``parse_flex_row``: the per-element step of ``parse_flex_statement`` (#138)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bot.ingest.ibkr_flex import parse_flex_row, parse_flex_statement

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"


@pytest.fixture
def sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _rows(xml: str) -> list[ET.Element]:
    root = ET.fromstring(xml)
    return [*root.iter("CorporateAction"), *root.iter("CashTransaction")]


def test_parse_flex_row_matches_parser(sample: str) -> None:
    rows = [r for r in (parse_flex_row(el) for el in _rows(sample)) if r is not None]
    assert rows == parse_flex_statement(sample)


def test_parse_flex_row_skips_non_dividend_cash(sample: str) -> None:
    (withholding,) = (el for el in _rows(sample) if el.get("transactionID") == "2002")
    assert parse_flex_row(withholding) is None


def test_parse_flex_row_rejects_other_tags() -> None:
    with pytest.raises(ValueError, match="not a Flex row: FlexStatement"):
        parse_flex_row(ET.Element("FlexStatement"))
