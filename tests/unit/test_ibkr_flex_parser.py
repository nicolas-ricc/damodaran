"""Parser tests for the IBKR Flex statement → corporate_actions mapping (#56).

Each test pins one row of the mapping table in the issue against the synthetic
fixture, plus the skip and ``ratio`` rules.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.ingest.ibkr_flex import CorporateActionRecord, parse_flex_statement

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"


@pytest.fixture
def records() -> dict[str, CorporateActionRecord]:
    return {r.action_id: r for r in parse_flex_statement(FIXTURE.read_text(encoding="utf-8"))}


def test_imports_exactly_the_mapped_rows(records: dict[str, CorporateActionRecord]) -> None:
    assert set(records) == {"ca:1001", "ca:1002", "ca:1003", "ct:2001", "ct:2003"}


def test_dividends_row(records: dict[str, CorporateActionRecord]) -> None:
    r = records["ct:2001"]
    assert (r.action_type, r.ticker, r.account, r.effective_date) == (
        "dividend", "MSFT", "U1234567", date(2026, 9, 12)
    )
    assert r.details == {
        "flex_type": "Dividends",
        "conid": "272093",
        "isin": "US5949181045",
        "currency": "USD",
        "description": "MSFT(US5949181045) CASH DIVIDEND USD 0.75 PER SHARE (Ordinary Dividend)",
        "amount": "75.00",
    }


def test_payment_in_lieu_row_falls_back_to_datetime(records: dict[str, CorporateActionRecord]) -> None:
    r = records["ct:2003"]
    assert (r.action_type, r.ticker, r.account, r.effective_date) == (
        "dividend", "KO", "U7654321", date(2026, 9, 18)
    )
    assert r.details["flex_type"] == "Payment In Lieu Of Dividends"


def test_withholding_tax_is_skipped(records: dict[str, CorporateActionRecord]) -> None:
    assert "ct:2002" not in records


def test_forward_split_carries_ratio(records: dict[str, CorporateActionRecord]) -> None:
    r = records["ca:1001"]
    assert (r.action_type, r.ticker, r.account, r.effective_date) == (
        "split", "AAPL", "U1234567", date(2026, 9, 15)
    )
    assert r.details["ratio"] == "4:1"
    assert r.details["flex_type"] == "FS"
    assert r.details["quantity"] == "300"
    assert "code" not in r.details


def test_reverse_split_uses_datetime_over_report_date(records: dict[str, CorporateActionRecord]) -> None:
    r = records["ca:1002"]
    assert (r.action_type, r.ticker, r.effective_date) == ("split", "GE", date(2026, 9, 16))
    assert r.details["ratio"] == "1:8"


def test_other_corporate_action_keeps_lowercased_type(records: dict[str, CorporateActionRecord]) -> None:
    r = records["ca:1003"]
    assert (r.action_type, r.ticker, r.effective_date) == ("tc", "ATVI", date(2026, 9, 22))
    assert "ratio" not in r.details
    assert r.details["proceeds"] == "4750"


def test_row_without_symbol_is_skipped_with_a_warning() -> None:
    with capture_logs() as logs:
        parsed = parse_flex_statement(FIXTURE.read_text(encoding="utf-8"))
    assert "ct:2004" not in {r.action_id for r in parsed}
    warnings = [e for e in logs if e["log_level"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["transaction_id"] == "2004"


def _statement(body: str) -> str:
    return (
        '<FlexQueryResponse queryName="q" type="AF"><FlexStatements count="1">'
        f'<FlexStatement accountId="U1">{body}</FlexStatement>'
        "</FlexStatements></FlexQueryResponse>"
    )


def test_split_without_ratio_pattern_omits_ratio() -> None:
    xml = _statement(
        '<CorporateActions><CorporateAction accountId="U1" symbol="xyz" '
        'description="XYZ(US0000000000) Stock Split" dateTime="20260901;000000" '
        'actionID="7" type="FS" /></CorporateActions>'
    )
    [r] = parse_flex_statement(xml)
    assert (r.action_type, r.ticker) == ("split", "XYZ")
    assert "ratio" not in r.details


@pytest.mark.parametrize(
    ("attrs", "missing"),
    [
        ('symbol="AAPL" dateTime="20260901;000000" type="FS"', "actionID"),
        ('symbol="AAPL" actionID="8" dateTime="nope" reportDate="" type="FS"', "date"),
        ('symbol="AAPL" actionID="9" dateTime="20260901;000000" type=""', "type"),
    ],
)
def test_corporate_action_missing_field_is_skipped(attrs: str, missing: str) -> None:
    xml = _statement(f"<CorporateActions><CorporateAction {attrs} /></CorporateActions>")
    with capture_logs() as logs:
        assert parse_flex_statement(xml) == []
    assert [(e["log_level"], e["missing"]) for e in logs] == [("warning", [missing])]


def test_unparseable_datetime_falls_back_to_report_date() -> None:
    xml = _statement(
        '<CorporateActions><CorporateAction symbol="AAPL" actionID="10" '
        'dateTime="garbage" reportDate="20260903" type="FS" /></CorporateActions>'
    )
    [r] = parse_flex_statement(xml)
    assert r.effective_date == date(2026, 9, 3)


def test_empty_statement_yields_nothing() -> None:
    xml = '<FlexQueryResponse queryName="q" type="AF"><FlexStatements count="0" /></FlexQueryResponse>'
    assert parse_flex_statement(xml) == []


def test_non_statement_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="FlexStatementResponse"):
        parse_flex_statement("<FlexStatementResponse><Status>Fail</Status></FlexStatementResponse>")
