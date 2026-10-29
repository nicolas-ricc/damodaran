"""Redaction and type summary of a real Flex statement for the #110 fixture (#138).

Pure string-to-string: no network, no settings, no disk. The capture command
feeds :func:`redact_statement` and :func:`summarize_statement` the live statement.
"""

from __future__ import annotations

import dataclasses
import json
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bot.ingest.ibkr_flex import _flex_date, parse_flex_row

REDACTED_ACCOUNT = "U0000000"

_HEADER_COMMENT = (
    "Redacted real statement captured by bot flex-capture for #110. Account ids and "
    "money and quantity columns are fakes (a placeholder account id; amounts keep "
    "only sign and shape). Symbols, conids, isins, ids, dates, types and "
    "descriptions are real."
)
_NUMERIC_ATTRS = ("amount", "proceeds", "value", "quantity")


def _fake_number(value: str) -> str:
    """Replace a number by a fake with the same sign, digit count and decimals.

    Zero, empty, non-numeric and non-finite text is returned unchanged.
    """
    text = value.strip()
    if not text:
        return value
    try:
        number = Decimal(text)
    except InvalidOperation:
        return value
    if not number.is_finite() or number == 0:
        return value
    sign = "-" if number < 0 else ""
    decimals = max(0, -int(number.as_tuple().exponent))
    integer_digits = number.adjusted() + 1
    if integer_digits >= 1:
        fake = sign + str(10 ** (integer_digits - 1))
        return fake + ("." + "0" * decimals if decimals else "")
    return f"{sign}0.1{'0' * (decimals - 1)}"


def redact_statement(xml: str) -> str:
    """Return the statement with account ids and money columns faked."""
    root = ET.fromstring(xml)
    if root.tag != "FlexQueryResponse":
        raise ValueError(f"expected a FlexQueryResponse, got {root.tag}")
    for el in root.iter():
        if "accountId" in el.attrib:
            el.set("accountId", REDACTED_ACCOUNT)
        if "acctAlias" in el.attrib:
            el.set("acctAlias", "")
        for key in _NUMERIC_ATTRS:
            if key in el.attrib:
                el.set(key, _fake_number(el.attrib[key]))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<!-- {_HEADER_COMMENT} -->\n"
        f"{ET.tostring(root, encoding='unicode')}\n"
    )


@dataclass(frozen=True)
class FlexSummary:
    """Counts of what a statement holds and what the parser makes of it."""

    accounts: int
    from_date: str | None
    to_date: str | None
    rows: int
    corporate_action_types: dict[str, int]
    cash_transaction_types: dict[str, int]
    parsed: int
    parsed_by_action_type: dict[str, int]
    skipped: dict[str, int]

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=2, sort_keys=True) + "\n"


def _sorted(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def summarize_statement(xml: str) -> FlexSummary:
    """Count statements, row types and parser outcomes of a ``FlexQueryResponse``."""
    root = ET.fromstring(xml)
    if root.tag != "FlexQueryResponse":
        raise ValueError(f"expected a FlexQueryResponse, got {root.tag}")
    statements = list(root.iter("FlexStatement"))
    from_dates = [d for s in statements if (d := _flex_date(s.get("fromDate", ""))) is not None]
    to_dates = [d for s in statements if (d := _flex_date(s.get("toDate", ""))) is not None]
    corporate_actions = list(root.iter("CorporateAction"))
    cash_transactions = list(root.iter("CashTransaction"))
    parsed_by_type: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    for el in (*corporate_actions, *cash_transactions):
        record = parse_flex_row(el)
        if record is None:
            skipped[f"{el.tag}/{el.get('type', '')}"] += 1
        else:
            parsed_by_type[record.action_type] += 1
    return FlexSummary(
        accounts=len(statements),
        from_date=min(from_dates).isoformat() if from_dates else None,
        to_date=max(to_dates).isoformat() if to_dates else None,
        rows=len(corporate_actions) + len(cash_transactions),
        corporate_action_types=_sorted(Counter(el.get("type", "") for el in corporate_actions)),
        cash_transaction_types=_sorted(Counter(el.get("type", "") for el in cash_transactions)),
        parsed=sum(parsed_by_type.values()),
        parsed_by_action_type=_sorted(parsed_by_type),
        skipped=_sorted(skipped),
    )
