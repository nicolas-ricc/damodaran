"""IBKR Flex Web Service importer for corporate actions (M5, #56).

The TWS socket cannot supply dividends or splits (ADR 0004); IBKR's Flex Web
Service can. A user-defined Activity Flex Query with the *Corporate Actions*
and *Cash Transactions* sections is fetched over two GETs (protocol v3), parsed
into :class:`CorporateActionRecord` rows and upserted into
``corporate_actions``, where :func:`bot.portfolio.events.compute_events` reads
them.

Written from IBKR's documentation against a synthetic fixture and not yet
verified against a real pull (#110); parser corrections land in #111.

Follows the ingest convention: download (:class:`FlexClient`) -> parse
(:func:`parse_flex_statement`, pure) -> upsert (:func:`upsert_corporate_actions`).
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from bot.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    import duckdb

log = get_logger(__name__)

SOURCE = "ibkr-flex"

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
    if not symbol or not raw_id or effective is None or not action_type:
        log.warning(
            "ibkr_flex_row_skipped",
            element=el.tag,
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


def parse_flex_statement(xml: str) -> list[CorporateActionRecord]:
    """Map a ``FlexQueryResponse`` to corporate-action records (pure).

    Dividend-type cash transactions become ``dividend``; ``FS``/``RS`` corporate
    actions become ``split``; any other corporate action keeps its raw type,
    lowercased. Other cash transactions are skipped silently; rows missing a
    symbol, an id or a parseable date are skipped with a WARNING.
    """
    root = ET.fromstring(xml)
    if root.tag != "FlexQueryResponse":
        raise ValueError(f"expected a FlexQueryResponse, got {root.tag}")
    records: list[CorporateActionRecord] = []
    for el in root.iter("CorporateAction"):
        flex_type = _attr(el, "type").upper()
        action_type = "split" if flex_type in _SPLIT_TYPES else flex_type.lower()
        record = _record(
            el,
            id_attr="actionID",
            prefix="ca",
            action_type=action_type,
            dates=("dateTime", "reportDate"),
        )
        if record is not None:
            records.append(record)
    for el in root.iter("CashTransaction"):
        if _attr(el, "type") not in _DIVIDEND_TYPES:
            continue
        record = _record(
            el,
            id_attr="transactionID",
            prefix="ct",
            action_type="dividend",
            dates=("settleDate", "dateTime"),
        )
        if record is not None:
            records.append(record)
    return records


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
