"""Redaction and type summary of a Flex statement (#138), over the synthetic sample.

Both functions are pure: the capture command of #139 feeds them the live
statement; here they only see ``statement_sample.xml`` and inline snippets.
"""

from __future__ import annotations

import dataclasses
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bot.ingest.ibkr_flex import CorporateActionRecord, parse_flex_statement
from bot.ingest.ibkr_flex_capture import (
    REDACTED_ACCOUNT,
    FlexSummary,
    _fake_number,
    redact_statement,
    summarize_statement,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
MONEY_KEYS = ("amount", "proceeds", "quantity", "value")


@pytest.fixture
def sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def redacted(sample: str) -> str:
    return redact_statement(sample)


def _decimals(value: str) -> int:
    return len(value.split(".", 1)[1]) if "." in value else 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("75.00", "10.00"),
        ("-11.25", "-10.00"),
        ("48.50", "10.00"),
        ("4750", "1000"),
        ("-700", "-100"),
        ("300", "100"),
        ("-50", "-10"),
        ("1.00", "1.00"),
        ("0", "0"),
        ("0.75", "0.10"),
        ("", ""),
        ("-0.00", "-0.00"),
        ("-0.75", "-0.10"),
        ("1E+3", "1000"),
        ("1.5E+3", "1000"),
        ("7.5E-3", "0.1000"),
        ("007", "1"),
        ("1,234.56", "1,234.56"),
        ("abc", "abc"),
        (" 75.00 ", "10.00"),
        ("1E+5000", "1" + "0" * 5000),
    ],
)
def test_fake_number(value: str, expected: str) -> None:
    assert _fake_number(value) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_fake_number_leaves_non_finite_unchanged(value: str) -> None:
    assert _fake_number(value) == value


def test_redaction_is_deterministic(sample: str, redacted: str) -> None:
    assert redact_statement(sample) == redacted
    assert redacted.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
    assert redacted.endswith("\n")


def test_redaction_leaves_only_placeholder_account(redacted: str) -> None:
    assert REDACTED_ACCOUNT == "U0000000"
    assert set(re.findall(r"\bU\d{6,9}\b", redacted)) == {"U0000000"}


def test_redacted_output_reparses(redacted: str) -> None:
    assert ET.fromstring(redacted).tag == "FlexQueryResponse"


def test_redaction_preserves_records(sample: str, redacted: str) -> None:
    original = parse_flex_statement(sample)
    after = parse_flex_statement(redacted)

    def key(r: CorporateActionRecord) -> tuple[object, ...]:
        return (r.action_id, r.action_type, r.ticker, r.effective_date, r.details["description"])

    assert [key(r) for r in after] == [key(r) for r in original]
    assert {r.account for r in after} == {"U0000000"}


def test_redaction_preserves_sign_and_shape(sample: str, redacted: str) -> None:
    pairs = list(zip(parse_flex_statement(sample), parse_flex_statement(redacted), strict=True))
    checked = 0
    for before, after in pairs:
        for k in MONEY_KEYS:
            if k not in before.details:
                continue
            old, new = before.details[k], after.details[k]
            assert new.startswith("-") == old.startswith("-"), (k, old, new)
            assert _decimals(new) == _decimals(old), (k, old, new)
            checked += 1
    assert checked > 0
    by_id = {r.action_id: r for r in parse_flex_statement(redacted)}
    assert by_id["ca:1002"].details["quantity"] == "-100"
    assert by_id["ct:2001"].details["amount"] == "10.00"


def test_redaction_blanks_alias() -> None:
    xml = (
        '<FlexQueryResponse><FlexStatements count="1">'
        '<FlexStatement accountId="U1234567" acctAlias="Mine" />'
        "</FlexStatements></FlexQueryResponse>"
    )
    statement = ET.fromstring(redact_statement(xml)).find(".//FlexStatement")
    assert statement is not None
    assert statement.get("acctAlias") == ""
    assert statement.get("accountId") == "U0000000"


def test_redact_rejects_other_root() -> None:
    with pytest.raises(ValueError, match="expected a FlexQueryResponse, got Foo"):
        redact_statement("<Foo/>")


SAMPLE_SUMMARY = FlexSummary(
    accounts=2,
    from_date="2026-09-01",
    to_date="2026-09-30",
    rows=7,
    corporate_action_types={"FS": 1, "RS": 1, "TC": 1},
    cash_transaction_types={
        "Dividends": 2,
        "Payment In Lieu Of Dividends": 1,
        "Withholding Tax": 1,
    },
    parsed=5,
    parsed_by_action_type={"dividend": 2, "split": 2, "tc": 1},
    skipped={"CashTransaction/Dividends": 1, "CashTransaction/Withholding Tax": 1},
)


def test_summary_of_sample(sample: str) -> None:
    assert summarize_statement(sample) == SAMPLE_SUMMARY


def test_summary_survives_redaction(redacted: str) -> None:
    assert summarize_statement(redacted) == SAMPLE_SUMMARY


def test_summary_dict_keys_sorted(sample: str) -> None:
    for value in dataclasses.asdict(summarize_statement(sample)).values():
        if isinstance(value, dict):
            assert list(value) == sorted(value)


def test_to_json_round_trips(sample: str) -> None:
    summary = summarize_statement(sample)
    text = summary.to_json()
    assert json.loads(text) == dataclasses.asdict(summary)
    assert text.endswith("\n")


def test_summary_dates_none_when_absent() -> None:
    xml = (
        "<FlexQueryResponse><FlexStatements>"
        '<FlexStatement accountId="U1" />'
        "</FlexStatements></FlexQueryResponse>"
    )
    summary = summarize_statement(xml)
    assert (summary.from_date, summary.to_date) == (None, None)
    assert (summary.accounts, summary.rows) == (1, 0)


def test_summary_dates_tolerate_padding() -> None:
    xml = (
        "<FlexQueryResponse><FlexStatements>"
        '<FlexStatement accountId="U1" fromDate=" 20260901" toDate="20260930 " />'
        "</FlexStatements></FlexQueryResponse>"
    )
    summary = summarize_statement(xml)
    assert (summary.from_date, summary.to_date) == ("2026-09-01", "2026-09-30")


def test_summary_missing_type_counts_under_empty() -> None:
    xml = (
        "<FlexQueryResponse><FlexStatements>"
        '<FlexStatement accountId="U1" fromDate="20260901" toDate="20260930">'
        '<CorporateActions><CorporateAction symbol="X" actionID="9" /></CorporateActions>'
        "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )
    assert summarize_statement(xml).corporate_action_types == {"": 1}


def test_summarize_rejects_other_root() -> None:
    with pytest.raises(ValueError, match="expected a FlexQueryResponse, got Foo"):
        summarize_statement("<Foo/>")
