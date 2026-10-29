"""Redaction, type summary and capture of a real Flex statement for the #110 fixture.

#138: :func:`redact_statement` and :func:`summarize_statement` are pure
string-to-string: no network, no settings, no disk.

#139: :func:`capture` fetches the live statement through a
:class:`RecordingTransport`, renders a token-scrubbed VCR cassette
(:func:`render_cassette`) and writes it with the redacted statement and its
summary. Everything is rendered in memory first, so a failure writes nothing.
"""

from __future__ import annotations

import dataclasses
import json
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import yaml

from bot.ingest.ibkr_flex import _attr, _flex_date, _flex_root, fetch_flex_statement, parse_flex_row

if TYPE_CHECKING:
    from collections.abc import Sequence

    from bot.config import Settings

REDACTED_ACCOUNT = "U0000000"

_HEADER_COMMENT = (
    "Redacted real statement captured by bot flex-capture for #110. Account ids and "
    "money and quantity columns are fakes (a placeholder account id; amounts keep "
    "only sign and shape). Symbols, conids, isins, ids, dates, types and "
    "descriptions are real."
)
_NUMERIC_ATTRS = ("amount", "proceeds", "value", "quantity")

CASSETTE_PATH = Path("tests/fixtures/cassettes/ibkr_flex/statement_real.yaml")
REDACTED_XML_PATH = Path("tests/fixtures/ibkr_flex/statement_real_redacted.xml")
SUMMARY_PATH = Path("tests/fixtures/ibkr_flex/statement_real_summary.json")

_CASSETTE_HEADER = (
    "# Recorded by bot flex-capture (#110): the Flex token is scrubbed and the "
    "statement is redacted.\n"
)


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
        fake = sign + "1" + "0" * (integer_digits - 1)
        return fake + ("." + "0" * decimals if decimals else "")
    return f"{sign}0.1{'0' * (decimals - 1)}"


def redact_statement(xml: str) -> str:
    """Return the statement with account ids and money columns faked."""
    root = _flex_root(xml)
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
    root = _flex_root(xml)
    statements = list(root.iter("FlexStatement"))
    from_dates = [d for s in statements if (d := _flex_date(_attr(s, "fromDate"))) is not None]
    to_dates = [d for s in statements if (d := _flex_date(_attr(s, "toDate"))) is not None]
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


@dataclass(frozen=True)
class Interaction:
    """One recorded HTTP exchange."""

    method: str
    url: str
    status: int
    reason: str
    content_type: str | None
    body: str


class RecordingTransport(httpx.BaseTransport):
    """Forward every request to *inner* and keep what came back."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self.interactions: list[Interaction] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        response.read()
        self.interactions.append(
            Interaction(
                method=request.method,
                url=str(request.url),
                status=response.status_code,
                reason=response.reason_phrase,
                content_type=response.headers.get("content-type"),
                body=response.text,
            )
        )
        return response

    def close(self) -> None:
        self._inner.close()


class FlexCaptureError(RuntimeError):
    """The capture cannot proceed or must not write; ``exit_code`` is the CLI's."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class _LiteralDumper(yaml.SafeDumper):
    """SafeDumper that writes multi-line strings as ``|`` blocks, unfolded."""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_LiteralDumper.add_representer(str, _represent_str)


def _scrub_uri(url: str) -> str:
    parsed = httpx.URL(url)
    if "t" in parsed.params:
        return str(parsed.copy_set_param("t", "SCRUBBED"))
    return url


def _redact_if_statement(body: str) -> str:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return body
    return redact_statement(body) if root.tag == "FlexQueryResponse" else body


def render_cassette(interactions: Sequence[Interaction], *, token: str) -> str:
    """Render *interactions* as a VCR cassette with the token and statement scrubbed.

    Raises :class:`FlexCaptureError` if a non-empty *token* survives in any form.
    """
    entries: list[dict[str, Any]] = [
        {
            "request": {
                "body": "",
                "headers": {},
                "method": i.method,
                "uri": _scrub_uri(i.url),
            },
            "response": {
                "status": {"code": i.status, "message": i.reason},
                "headers": {"Content-Type": [i.content_type]} if i.content_type else {},
                "body": {"string": _redact_if_statement(i.body)},
            },
        }
        for i in interactions
    ]
    text = _CASSETTE_HEADER + yaml.dump(
        {"interactions": entries, "version": 1},
        Dumper=_LiteralDumper,
        sort_keys=False,
        allow_unicode=True,
        width=float("inf"),
    )
    forms = (token, urllib.parse.quote(token, safe=""), urllib.parse.quote_plus(token, safe=""))
    if token and any(form in text for form in forms):
        raise FlexCaptureError("token found in the rendered cassette; nothing written")
    return text


def capture(
    settings: Settings,
    *,
    root: Path,
    transport: httpx.BaseTransport | None = None,
) -> FlexSummary:
    """Fetch the live statement and write the cassette, redacted XML and summary under *root*."""
    token = settings.ibkr_flex_token.strip()
    query_id = settings.ibkr_flex_query_id.strip()
    if not token or not query_id:
        raise FlexCaptureError(
            "BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID must both be set "
            "(put them in .env); nothing was written",
            exit_code=2,
        )
    recorder = RecordingTransport(transport or httpx.HTTPTransport())
    statement = fetch_flex_statement(token, query_id, transport=recorder)
    redacted = redact_statement(statement)
    summary = summarize_statement(statement)
    cassette = render_cassette(recorder.interactions, token=token)
    for path, text in (
        (CASSETTE_PATH, cassette),
        (REDACTED_XML_PATH, redacted),
        (SUMMARY_PATH, summary.to_json()),
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return summary
