"""Redaction of a real Flex statement for the #110 fixture (#138).

Pure string-to-string: no network, no settings, no disk. The capture command
feeds :func:`redact_statement` the live statement and commits the result.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

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
