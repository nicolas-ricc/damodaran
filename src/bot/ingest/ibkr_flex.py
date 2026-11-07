"""IBKR Flex Web Service importer for corporate actions (M5, #56).

The TWS socket cannot supply dividends or splits (ADR 0004); IBKR's Flex Web
Service can. A user-defined Activity Flex Query with the *Corporate Actions*
and *Cash Transactions* sections is fetched over two GETs (protocol v3), parsed
into :class:`CorporateActionRecord` rows and upserted into
``corporate_actions``, where :func:`bot.portfolio.events.compute_events` reads
them.

The parser is validated against the redacted real statement captured by
``bot flex-capture`` (:mod:`bot.ingest.ibkr_flex_capture`); parser corrections
are tracked in #111.

Follows the ingest convention: download (:class:`FlexClient`) -> parse
(:func:`parse_flex_statement`, pure) -> upsert (:func:`upsert_corporate_actions`).
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from urllib.parse import quote, quote_plus

import httpx

from bot.ingest.ibkr import CashBalance, PortfolioPosition, TradeExecution
from bot.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable
    from zoneinfo import ZoneInfo

    import duckdb

    from bot.config import Settings

log = get_logger(__name__)

SOURCE = "ibkr-flex"

SEND_REQUEST_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
)
MAX_POLLS = 10
POLL_DELAY_SECONDS = 3.0
# 1019: statement generation in progress; 1009: server under heavy load.
RETRYABLE_CODES = frozenset({"1019", "1009"})

_DIVIDEND_TYPES = frozenset({"Dividends", "Payment In Lieu Of Dividends"})
_SPLIT_TYPES = frozenset({"FS", "RS"})
_RATIO = re.compile(r"SPLIT (\d+) FOR (\d+)")
_DETAIL_KEYS = (
    "conid",
    "isin",
    "currency",
    "description",
    "amount",
    "quantity",
    "proceeds",
    "value",
    "code",
)


@dataclass(frozen=True)
class CorporateActionRecord:
    """One ``corporate_actions`` row parsed from a Flex statement."""

    action_id: str
    account: str | None
    action_type: str
    ticker: str
    effective_date: date
    details: dict[str, str]


def _attr(el: ET.Element, name: str) -> str:
    return (el.get(name) or "").strip()


def _flex_date(value: str) -> date | None:
    """Date part of a Flex ``yyyyMMdd`` or ``yyyyMMdd;HHmmss`` value."""
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _details(el: ET.Element, flex_type: str) -> dict[str, str]:
    details = {"flex_type": flex_type}
    for key in _DETAIL_KEYS:
        value = _attr(el, key)
        if value:
            details[key] = value
    return details


def _record(
    el: ET.Element, *, id_attr: str, prefix: str, action_type: str, dates: tuple[str, str]
) -> CorporateActionRecord | None:
    symbol = _attr(el, "symbol")
    raw_id = _attr(el, id_attr)
    effective = _flex_date(_attr(el, dates[0])) or _flex_date(_attr(el, dates[1]))
    missing = [
        name
        for name, absent in (
            ("symbol", not symbol),
            (id_attr, not raw_id),
            ("date", effective is None),
            ("type", not action_type),
        )
        if absent
    ]
    if missing or effective is None:
        log.warning(
            "ibkr_flex_row_skipped",
            element=el.tag,
            missing=missing,
            **{"action_id" if prefix == "ca" else "transaction_id": raw_id or None},
            symbol=symbol or None,
            description=_attr(el, "description") or None,
        )
        return None
    flex_type = _attr(el, "type")
    details = _details(el, flex_type)
    if action_type == "split":
        match = _RATIO.search(details.get("description", ""))
        if match:
            details["ratio"] = f"{match.group(1)}:{match.group(2)}"
    return CorporateActionRecord(
        action_id=f"{prefix}:{raw_id}",
        account=_attr(el, "accountId") or None,
        action_type=action_type,
        ticker=symbol.upper(),
        effective_date=effective,
        details=details,
    )


def _flex_root(xml: str) -> ET.Element:
    """Parse *xml* and return its root, which must be a ``FlexQueryResponse``."""
    root = ET.fromstring(xml)
    if root.tag != "FlexQueryResponse":
        raise ValueError(f"expected a FlexQueryResponse, got {root.tag}")
    return root


def parse_flex_row(el: ET.Element) -> CorporateActionRecord | None:
    """Map one ``CorporateAction`` or ``CashTransaction`` element to a record (pure).

    ``CorporateAction``: ``FS``/``RS`` become ``split``; any other type keeps its
    raw type, lowercased. ``CashTransaction``: only dividend-type rows become
    ``dividend``; other cash transactions return ``None`` silently. Rows missing a
    symbol, an id or a parseable date return ``None`` with a WARNING. Any other
    tag raises :class:`ValueError`.
    """
    if el.tag == "CorporateAction":
        flex_type = _attr(el, "type").upper()
        return _record(
            el,
            id_attr="actionID",
            prefix="ca",
            action_type="split" if flex_type in _SPLIT_TYPES else flex_type.lower(),
            dates=("dateTime", "reportDate"),
        )
    if el.tag == "CashTransaction":
        if _attr(el, "type") not in _DIVIDEND_TYPES:
            return None
        return _record(
            el,
            id_attr="transactionID",
            prefix="ct",
            action_type="dividend",
            dates=("settleDate", "dateTime"),
        )
    raise ValueError(f"not a Flex row: {el.tag}")


def parse_flex_statement(xml: str) -> list[CorporateActionRecord]:
    """Map a ``FlexQueryResponse`` to corporate-action records (pure).

    All ``CorporateAction`` rows first, then all ``CashTransaction`` rows, each
    through :func:`parse_flex_row`; rows it returns ``None`` for are dropped.
    """
    root = _flex_root(xml)
    rows = (*root.iter("CorporateAction"), *root.iter("CashTransaction"))
    return [record for el in rows if (record := parse_flex_row(el)) is not None]


class FlexError(RuntimeError):
    """The Flex Web Service refused, failed or never produced the statement."""


@dataclass(frozen=True)
class FlexStatement:
    """Portfolio data and corporate actions parsed from one Flex response."""

    positions: list[PortfolioPosition]
    cash: list[CashBalance]
    trades: list[TradeExecution]
    corporate_actions: list[CorporateActionRecord]
    accounts: list[str]
    as_of: date


_TRADE_TIME_FORMAT = "%Y%m%d;%H%M%S"


def _describe(el: ET.Element) -> str:
    return f"<{el.tag} {_attr(el, 'accountId')} {_attr(el, 'symbol') or _attr(el, 'currency')}>".replace("  ", " ")


def _number(el: ET.Element, name: str) -> float:
    raw = _attr(el, name)
    try:
        return float(raw)
    except ValueError:
        raise FlexError(f"Flex {_describe(el)}: {name} {raw!r} is not a number") from None


def _int_or_zero(el: ET.Element, name: str) -> int:
    try:
        return int(_attr(el, name))
    except ValueError:
        return 0


def _trade_time(el: ET.Element, tz: ZoneInfo) -> datetime:
    raw = _attr(el, "dateTime")
    try:
        local = datetime.strptime(raw, _TRADE_TIME_FORMAT).replace(tzinfo=tz)
    except ValueError:
        raise FlexError(
            f"Flex {_describe(el)}: dateTime {raw!r} is not yyyyMMdd;HHmmss "
            "(keep IBKR's default date/time format in the Flex Query)"
        ) from None
    return local.astimezone(UTC)


def _position(el: ET.Element) -> PortfolioPosition:
    try:
        con_id = int(_attr(el, "conid"))
    except ValueError:
        raise FlexError(f"Flex {_describe(el)}: conid {_attr(el, 'conid')!r} is not an integer") from None
    return PortfolioPosition(
        account=_attr(el, "accountId"),
        con_id=con_id,
        symbol=_attr(el, "symbol"),
        sec_type=_attr(el, "assetCategory"),
        currency=_attr(el, "currency"),
        exchange=_attr(el, "listingExchange"),
        quantity=_number(el, "position"),
        avg_cost=_number(el, "costBasisPrice"),
    )


def _trade(el: ET.Element, tz: ZoneInfo) -> TradeExecution:
    return TradeExecution(
        account=_attr(el, "accountId"),
        exec_id=_attr(el, "ibExecID"),
        con_id=_int_or_zero(el, "conid"),
        symbol=_attr(el, "symbol"),
        sec_type=_attr(el, "assetCategory"),
        currency=_attr(el, "currency"),
        side=_attr(el, "buySell"),
        quantity=_number(el, "quantity"),
        price=_number(el, "tradePrice"),
        executed_at=_trade_time(el, tz),
        perm_id=_int_or_zero(el, "ibOrderID"),
    )


def _section(statement: ET.Element, name: str) -> ET.Element:
    section = statement.find(name)
    if section is None:
        raise FlexError(
            f"Flex statement for {_attr(statement, 'accountId')} has no {name} section: "
            "add it to the Flex Query (README)"
        )
    return section


def parse_statement(xml: str, *, tz: ZoneInfo) -> FlexStatement:
    """Map a ``FlexQueryResponse`` to positions, cash, trades and actions (pure).

    *tz* is the Flex reporting time zone of trade ``dateTime`` values. Raises
    :class:`FlexError` for a missing section, an unparseable number or trade
    time, a position without a ``conid``, or when no ``as_of`` date is found.
    """
    root = _flex_root(xml)
    positions: list[PortfolioPosition] = []
    cash: list[CashBalance] = []
    trades: list[TradeExecution] = []
    accounts: list[str] = []
    report_dates: list[date] = []
    to_dates: list[date] = []
    for statement in root.iter("FlexStatement"):
        account = _attr(statement, "accountId")
        if account and account not in accounts:
            accounts.append(account)
        if (to_date := _flex_date(_attr(statement, "toDate"))) is not None:
            to_dates.append(to_date)
        for el in _section(statement, "OpenPositions").iter("OpenPosition"):
            if _attr(el, "levelOfDetail") not in ("", "SUMMARY"):
                continue
            positions.append(_position(el))
            if (report_date := _flex_date(_attr(el, "reportDate"))) is not None:
                report_dates.append(report_date)
        for el in _section(statement, "CashReport").iter("CashReportCurrency"):
            if _attr(el, "levelOfDetail") != "Currency" or _attr(el, "currency") == "BASE_SUMMARY":
                continue
            cash.append(CashBalance(_attr(el, "accountId"), _attr(el, "currency"), _number(el, "endingCash")))
        for el in _section(statement, "Trades").iter("Trade"):
            if _attr(el, "levelOfDetail") == "EXECUTION":
                trades.append(_trade(el, tz))
    candidates = report_dates or to_dates
    if not candidates:
        raise FlexError("Flex statement has no OpenPosition reportDate or FlexStatement toDate to date it")
    return FlexStatement(
        positions=positions,
        cash=cash,
        trades=trades,
        corporate_actions=parse_flex_statement(xml),
        accounts=accounts,
        as_of=max(candidates),
    )


def upsert_corporate_actions(
    conn: duckdb.DuckDBPyConnection, records: Iterable[CorporateActionRecord]
) -> int:
    """Insert *records* de-duped on ``action_id``; return the number of new rows."""
    inserted = 0
    for r in records:
        result = conn.execute(
            "INSERT INTO corporate_actions "
            "(action_id, account, action_type, ticker, effective_date, details, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (action_id) DO NOTHING",
            [
                r.action_id,
                r.account,
                r.action_type,
                r.ticker,
                r.effective_date,
                json.dumps(r.details, sort_keys=True),
                SOURCE,
            ],
        )
        row = result.fetchone()
        inserted += int(row[0]) if row is not None and isinstance(row[0], int) else 0
    return inserted


class FlexClient:
    """Two-GET Flex Web Service v3 client: request a report, then poll for it."""

    def __init__(
        self,
        token: str,
        query_id: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._query_id = query_id
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FlexClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_statement(self) -> str:
        """Return the statement XML; raise :class:`FlexError` on any failure."""
        response = self._parse(self._get(SEND_REQUEST_URL, q=self._query_id))
        if response.tag != "FlexStatementResponse" or (response.findtext("Status") or "").strip() != "Success":
            raise FlexError(f"Flex SendRequest failed: {self._reason(response)}")
        reference = (response.findtext("ReferenceCode") or "").strip()
        url = (response.findtext("Url") or "").strip()
        if not reference or not url:
            raise FlexError("Flex SendRequest succeeded without a ReferenceCode or Url")

        code = ""
        for attempt in range(1, MAX_POLLS + 1):
            body = self._get(url, q=reference)
            root = self._parse(body)
            if root.tag == "FlexQueryResponse":
                return body
            code = (root.findtext("ErrorCode") or "").strip()
            if root.tag != "FlexStatementResponse" or code not in RETRYABLE_CODES:
                raise FlexError(f"Flex GetStatement failed: {self._reason(root)}")
            log.info("ibkr_flex_statement_pending", attempt=attempt, error_code=code)
            if attempt < MAX_POLLS:
                time.sleep(POLL_DELAY_SECONDS)
        raise FlexError(f"Flex statement not ready after {MAX_POLLS} polls (last error {code})")

    def _get(self, url: str, *, q: str) -> str:
        try:
            r = self._client.get(url, params={"q": q, "t": self._token, "v": "3"})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise FlexError(self._scrub(f"Flex request failed: {exc}")) from None
        return r.text

    def _parse(self, body: str) -> ET.Element:
        try:
            return ET.fromstring(body)
        except ET.ParseError as exc:
            raise FlexError(f"Flex response is not XML: {exc}") from None

    def _reason(self, root: ET.Element) -> str:
        status = (root.findtext("Status") or "").strip() or "?"
        code = (root.findtext("ErrorCode") or "").strip() or f"status {status}"
        message = (root.findtext("ErrorMessage") or "").strip() or root.tag
        return self._scrub(f"{code} {message}")

    def _scrub(self, text: str) -> str:
        if not self._token:
            return text
        for form in (self._token, quote(self._token, safe=""), quote_plus(self._token, safe="")):
            text = text.replace(form, "***")
        return text


def fetch_flex_statement(
    token: str,
    query_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Return the latest Flex statement XML; raise :class:`FlexError` on any failure."""
    with FlexClient(token, query_id, transport=transport) as client:
        return client.fetch_statement()


def import_corporate_actions(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> int | None:
    """Fetch the latest Flex statement and upsert its corporate actions.

    Returns ``None`` (after one INFO line) when the token or query id is not
    configured, otherwise the number of new rows. Failures propagate; the
    caller decides that they are not fatal.
    """
    token = settings.ibkr_flex_token.strip()
    query_id = settings.ibkr_flex_query_id.strip()
    if not token or not query_id:
        log.info("ibkr_flex_not_configured")
        return None
    statement = fetch_flex_statement(token, query_id, transport=transport)
    records = parse_flex_statement(statement)
    inserted = upsert_corporate_actions(conn, records)
    log.info("ibkr_flex_imported", records=len(records), inserted=inserted)
    return inserted
