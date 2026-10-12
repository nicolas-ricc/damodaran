# IBKR Flex corporate actions importer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot portfolio` pulls the latest IBKR Flex statement before computing events and upserts its dividends and splits into `corporate_actions`, so the `DIVIDEND` and `SPLIT` detectors in `compute_events` can fire.

**Architecture:** A new ingest module `src/bot/ingest/ibkr_flex.py` follows the `download → parse → upsert` convention: `FlexClient` (two-GET Flex Web Service v3 protocol over an injectable `httpx` transport), a pure `parse_flex_statement`, an idempotent `upsert_corporate_actions`, and `import_corporate_actions`, which ties them together and is the only public entry point that knows about settings. `run_portfolio` gains an optional `corporate_actions_fn` hook, called between `sync_portfolio` and `compute_events`, and any exception it raises becomes a WARNING. `cli.py` wires the hook to the real importer.

**Tech Stack:** Python 3.12, `httpx` (`MockTransport` in tests), `xml.etree.ElementTree`, DuckDB, `structlog` (`structlog.testing.capture_logs` in tests), pydantic-settings, pytest.

**Spec:** GitHub issue #56 (nicolas-ricc/damodaran), "[M5.7] Corporate actions importer via IBKR Flex Web Service". The issue body is the spec: protocol, statement schema, mapping table, interfaces and acceptance criteria. Context: `src/bot/ingest/tiingo.py` (client pattern), `src/bot/portfolio/trades.py` (`ON CONFLICT DO NOTHING` + `_rowcount` pattern), `src/bot/portfolio/events.py:217,544` (detector and reader), `src/bot/portfolio/command.py`, `src/bot/cli.py:540`, ADR 0004, issue #110 (the Flex Query columns for the README).

## Global Constraints

- No live access. No token, no live call, no VCR cassette. Everything runs against `tests/fixtures/ibkr_flex/statement_sample.xml` and `httpx.MockTransport`.
- Settings: `ibkr_flex_token: str = ""` and `ibkr_flex_query_id: str = ""` (env `BOT_IBKR_FLEX_TOKEN`, `BOT_IBKR_FLEX_QUERY_ID`). "Configured" means both are non-empty after `.strip()`.
- Request URL: `https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest` with params `t=<token>&q=<queryId>&v=3`. Fetch: `GET <Url from step 1>` with params `q=<ReferenceCode>&t=<token>&v=3`.
- Retryable error codes on the fetch step: exactly `1019` and `1009`. `MAX_POLLS = 10`, `POLL_DELAY_SECONDS = 3.0` are module constants, not settings. Exhausting the polls is a failure.
- `httpx.Client(timeout=timeout, transport=transport)`, default timeout `30.0`.
- Never log the token. Scrub it from any URL or exception text that leaves `FlexClient`.
- `source = 'ibkr-flex'`. `action_id` is `ct:<transactionID>` or `ca:<actionID>`.
- `ratio` = `"N:M"` only when the description matches `SPLIT (\d+) FOR (\d+)`.
- `detect_corporate_action_events` is not changed. No merger or spin-off mapping.
- `FlexClient` is named only in `ibkr_flex.py` (seam test).
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` (strict) pass.

## Decisions (technical assumptions, declared)

1. **"When present" in `details`** means the attribute exists *and* is non-empty after `.strip()`. `code=""` in the sample is therefore omitted. Values are kept as the raw attribute strings (`"75.00"`, not `75.0`) so nothing is lost before #111 sees a real sample.
2. **Type matching.** `CashTransaction.type` is compared exactly (after `.strip()`) against `Dividends` and `Payment In Lieu Of Dividends`. `CorporateAction.type` is compared after `.strip().upper()` against `FS`/`RS`; any other non-empty value becomes `type.strip().lower()`. A `CorporateAction` with an empty `type` is skipped with a WARNING (it would otherwise produce an empty `action_type`, which the column forbids in spirit).
3. **Skip order for cash rows.** Non-dividend `CashTransaction` rows are skipped silently *before* the field checks; the "missing symbol / id / date" WARNING applies only to rows that would otherwise be imported. Withholding tax rows are expected noise, not anomalies.
4. **Date fallback.** "`settleDate`, else date part of `dateTime`" (and "`dateTime`, else `reportDate`") falls through when the first attribute is absent, empty, *or* unparseable. Parsing is `datetime.strptime(value.strip()[:8], "%Y%m%d").date()`; anything else is `None`.
5. **`account`** is `accountId` stripped, or `None` when absent (the column is nullable).
6. **Upsert counting** reuses the `trades.py` pattern: one `INSERT ... ON CONFLICT (action_id) DO NOTHING` per record, summing the affected-row count. Duplicates inside one statement are therefore harmless. `details` is stored with `json.dumps(..., sort_keys=True)`.
7. **Failure surface.** `FlexClient` raises a single `FlexError(RuntimeError)`. HTTP/transport errors are caught and re-raised as `FlexError` with the token scrubbed and no exception chaining (`from None`), because `httpx` puts the full URL, query string included, into its messages. A statement that is not well-formed XML raises `xml.etree.ElementTree.ParseError` from the parser. `import_corporate_actions` does not swallow anything; the `run_portfolio` hook wrapper is the single place a failure becomes a WARNING, and it logs `str(exc)` (or the type name) without `exc_info`.
8. **Parser root check.** `parse_flex_statement` raises `ValueError` when the root element is not `FlexQueryResponse`. It walks `root.iter("CorporateAction")` then `root.iter("CashTransaction")`, so any number of `FlexStatement` elements and absent or empty sections work without special cases.
9. **Poll delay in tests** is neutralised by `monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)`. The client reads the module global at call time and sleeps only *between* polls, never after the last one.
10. **Plans in `docs/plano/`.** CONTEXT.md asks for both plans to be updated after a stage. This issue changes three inventory rows (`ibkr-corp`, `ev-corp`, `tablas`), the M5 milestone row and the `dividend`/`split` notes in `views.py`. Without a full re-audit, `AUDITADO_EN`/`AUDITADO_EL` are left as they are: those rows describe the code at this commit, the audit stamp stays honest about the rest.

## Review Focus

1. **A token leaking through an exception message.** IBKR answers HTTP 5xx, or the network drops: `httpx` raises with the full URL (`...?t=<token>...`), and the `run_portfolio` hook would log it as a WARNING. Expected: the WARNING carries a scrubbed message. Task 3 tests an HTTP 500 and a transport error.
2. **A statement for an account whose sections are both empty, or a statement with no `FlexStatement` at all.** Expected: zero records, no error. Task 1 tests an empty `FlexStatements`.
3. **A split description in a format the regex does not cover** (e.g. lowercase, or no "FOR"). Expected: the row is still imported as `split`, `ratio` simply absent. Task 1.
4. **A re-run on the same day after a partially failed import.** Expected: no duplicates, the remaining rows get inserted. Covered by the upsert idempotence test plus `ON CONFLICT DO NOTHING` per row (Task 2).
5. **A `FlexStatementResponse` with `Status` `Success` on the fetch step, or an unknown root element.** Expected: a `FlexError`, not a parse of garbage into zero rows. Task 3.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/bot/ingest/ibkr_flex.py` (new) | Flex protocol client, statement parser, upsert, importer entry point |
| `tests/fixtures/ibkr_flex/statement_sample.xml` (new) | Synthetic statement covering every mapping row |
| `tests/unit/test_ibkr_flex_parser.py` (new) | Mapping table, skips, ratio rule |
| `tests/unit/test_ibkr_flex_client.py` (new) | Protocol, retries, failures, token scrubbing |
| `tests/unit/test_ibkr_flex_import.py` (new) | `import_corporate_actions` no-op and happy path |
| `tests/integration/test_ibkr_flex_events.py` (new) | Upsert idempotence, fixture → `compute_events` |
| `tests/unit/test_seam_enforcement.py` | `FlexClient` internal to `ibkr_flex.py` |
| `src/bot/config.py`, `.env.example`, `tests/unit/test_config.py` | Two new settings |
| `src/bot/portfolio/command.py`, `tests/integration/test_portfolio_command.py` | The hook |
| `src/bot/cli.py`, `tests/unit/test_cli_portfolio.py` | Wiring |
| `README.md`, `docs/adr/0004-tws-api-via-ib-async.md`, `src/bot/storage/schema.sql`, `src/bot/portfolio/trades.py`, `docs/plano/estado.py`, `docs/plano/views.py` | Docs |

---

### Task 1: Fixture, record type and parser

**Files:**
- Create: `tests/fixtures/ibkr_flex/statement_sample.xml`
- Create: `src/bot/ingest/ibkr_flex.py`
- Test: `tests/unit/test_ibkr_flex_parser.py`

**Interfaces:**
- Produces:
  - `SOURCE: str = "ibkr-flex"`
  - `@dataclass(frozen=True) class CorporateActionRecord: action_id: str; account: str | None; action_type: str; ticker: str; effective_date: date; details: dict[str, str]`
  - `parse_flex_statement(xml: str) -> list[CorporateActionRecord]`
  - Fixture path `tests/fixtures/ibkr_flex/statement_sample.xml`, whose expected records are listed in Step 1.

- [ ] **Step 1: Write the fixture**

`tests/fixtures/ibkr_flex/statement_sample.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  SYNTHETIC statement, written by hand from IBKR's Flex Web Service and Activity
  Flex Query documentation (issue #56). It is NOT a real pull: account ids,
  conids, ids and amounts are invented. A redacted real sample arrives with #110;
  parser corrections found there land in #111.

  Expected import (see tests/unit/test_ibkr_flex_parser.py):
    ca:1001 split    AAPL U1234567 2026-09-15 ratio 4:1
    ca:1002 split    GE   U1234567 2026-09-16 ratio 1:8
    ca:1003 tc       ATVI U1234567 2026-09-22 (no dateTime: reportDate)
    ct:2001 dividend MSFT U1234567 2026-09-12
    ct:2003 dividend KO   U7654321 2026-09-18 (no settleDate: dateTime)
  Skipped: ct 2002 (Withholding Tax), ct 2004 (no symbol, WARNING).
-->
<FlexQueryResponse queryName="bot-corporate-actions" type="AF">
  <FlexStatements count="2">
    <FlexStatement accountId="U1234567" fromDate="20260901" toDate="20260930"
                   period="Last30CalendarDays" whenGenerated="20261001;083000">
      <CorporateActions>
        <CorporateAction accountId="U1234567" currency="USD" assetCategory="STK"
            symbol="AAPL" description="AAPL(US0378331005) SPLIT 4 FOR 1 (AAPL, APPLE INC, US0378331005)"
            conid="265598" isin="US0378331005" reportDate="20260915"
            dateTime="20260915;202000" actionID="1001" type="FS"
            quantity="300" amount="0" proceeds="0" value="0" code="" />
        <CorporateAction accountId="U1234567" currency="USD" assetCategory="STK"
            symbol="GE" description="GE(US3696043013) SPLIT 1 FOR 8 (GE, GENERAL ELECTRIC CO, US3696044003)"
            conid="498843743" isin="US3696043013" reportDate="20260917"
            dateTime="20260916;202500" actionID="1002" type="RS"
            quantity="-700" amount="0" proceeds="0" value="0" code="" />
        <CorporateAction accountId="U1234567" currency="USD" assetCategory="STK"
            symbol="ATVI" description="ATVI(US00507V1098) CASH MERGER (ATVI, ACTIVISION BLIZZARD INC, US00507V1098)"
            conid="47210839" isin="US00507V1098" reportDate="20260922"
            dateTime="" actionID="1003" type="TC"
            quantity="-50" amount="0" proceeds="4750" value="0" code="" />
      </CorporateActions>
      <CashTransactions>
        <CashTransaction accountId="U1234567" currency="USD" assetCategory="STK"
            symbol="MSFT" description="MSFT(US5949181045) CASH DIVIDEND USD 0.75 PER SHARE (Ordinary Dividend)"
            conid="272093" isin="US5949181045" dateTime="20260912;202000"
            settleDate="20260912" reportDate="20260912" amount="75.00"
            type="Dividends" transactionID="2001" code="" />
        <CashTransaction accountId="U1234567" currency="USD" assetCategory="STK"
            symbol="MSFT" description="MSFT(US5949181045) CASH DIVIDEND USD 0.75 PER SHARE - US TAX"
            conid="272093" isin="US5949181045" dateTime="20260912;202000"
            settleDate="20260912" reportDate="20260912" amount="-11.25"
            type="Withholding Tax" transactionID="2002" code="" />
      </CashTransactions>
    </FlexStatement>
    <FlexStatement accountId="U7654321" fromDate="20260901" toDate="20260930"
                   period="Last30CalendarDays" whenGenerated="20261001;083000">
      <CorporateActions />
      <CashTransactions>
        <CashTransaction accountId="U7654321" currency="USD" assetCategory="STK"
            symbol="KO" description="KO(US1912161007) PAYMENT IN LIEU OF DIVIDEND (Ordinary Dividend)"
            conid="8894" isin="US1912161007" dateTime="20260918;202000"
            settleDate="" reportDate="20260919" amount="48.50"
            type="Payment In Lieu Of Dividends" transactionID="2003" code="" />
        <CashTransaction accountId="U7654321" currency="USD" assetCategory="STK"
            description="UNKNOWN CASH DIVIDEND USD 0.10 PER SHARE"
            conid="0" dateTime="20260919;202000"
            settleDate="20260919" reportDate="20260919" amount="1.00"
            type="Dividends" transactionID="2004" code="" />
      </CashTransactions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>
```

- [ ] **Step 2: Write the failing parser tests**

`tests/unit/test_ibkr_flex_parser.py`:

```python
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
    ],
)
def test_corporate_action_missing_id_or_date_is_skipped(attrs: str, missing: str) -> None:
    xml = _statement(f"<CorporateActions><CorporateAction {attrs} /></CorporateActions>")
    with capture_logs() as logs:
        assert parse_flex_statement(xml) == []
    assert [e["log_level"] for e in logs] == ["warning"], missing


def test_empty_statement_yields_nothing() -> None:
    xml = '<FlexQueryResponse queryName="q" type="AF"><FlexStatements count="0" /></FlexQueryResponse>'
    assert parse_flex_statement(xml) == []


def test_non_statement_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="FlexStatementResponse"):
        parse_flex_statement("<FlexStatementResponse><Status>Fail</Status></FlexStatementResponse>")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ibkr_flex_parser.py -q`
Expected: FAIL at collection, `ModuleNotFoundError: No module named 'bot.ingest.ibkr_flex'`.

- [ ] **Step 4: Write the parser**

`src/bot/ingest/ibkr_flex.py` (later tasks append to this file):

```python
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

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime

from bot.utils.logging import get_logger

log = get_logger(__name__)

SOURCE = "ibkr-flex"

_DIVIDEND_TYPES = frozenset({"Dividends", "Payment In Lieu Of Dividends"})
_SPLIT_TYPES = frozenset({"FS", "RS"})
_RATIO = re.compile(r"SPLIT (\d+) FOR (\d+)")
_DETAIL_KEYS = (
    "conid", "isin", "currency", "description", "amount", "quantity", "proceeds", "value", "code",
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
            el, id_attr="actionID", prefix="ca", action_type=action_type,
            dates=("dateTime", "reportDate"),
        )
        if record is not None:
            records.append(record)
    for el in root.iter("CashTransaction"):
        if _attr(el, "type") not in _DIVIDEND_TYPES:
            continue
        record = _record(
            el, id_attr="transactionID", prefix="ct", action_type="dividend",
            dates=("settleDate", "dateTime"),
        )
        if record is not None:
            records.append(record)
    return records
```

Note: `details["flex_type"]` holds the raw `type` as written (`_details` is called with `_attr(el, "type")`, not the upper-cased form).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ibkr_flex_parser.py -q && uv run mypy src && uv run ruff check src tests`
Expected: all pass, mypy and ruff clean.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/ibkr_flex src/bot/ingest/ibkr_flex.py tests/unit/test_ibkr_flex_parser.py
git commit -m "feat(#56): parse IBKR Flex statements into corporate actions"
```

---

### Task 2: Upsert and the path into `compute_events`

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py`
- Test: `tests/integration/test_ibkr_flex_events.py`

**Interfaces:**
- Consumes: `parse_flex_statement`, `CorporateActionRecord`, `SOURCE`, the fixture (Task 1).
- Produces: `upsert_corporate_actions(conn: duckdb.DuckDBPyConnection, records: Iterable[CorporateActionRecord]) -> int` (rows inserted).

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_ibkr_flex_events.py`:

```python
"""Fixture -> upsert -> compute_events: Flex rows make DIVIDEND/SPLIT fire (#56)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from bot.ingest.ibkr_flex import parse_flex_statement, upsert_corporate_actions
from bot.portfolio.events import EventType, compute_events
from bot.storage.db import apply_schema

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
PREV = date(2026, 9, 1)
CURR = date(2026, 9, 30)
HELD = ("AAPL", "GE", "ATVI", "MSFT", "KO")


@pytest.fixture
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(str(tmp_path / "flex.duckdb"))
    apply_schema(c)
    return c


def _records() -> list:  # type: ignore[type-arg]
    return parse_flex_statement(FIXTURE.read_text(encoding="utf-8"))


def test_importing_the_fixture_twice_is_idempotent(conn: duckdb.DuckDBPyConnection) -> None:
    assert upsert_corporate_actions(conn, _records()) == 5
    assert upsert_corporate_actions(conn, _records()) == 0
    assert conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone() == (5,)


def test_upsert_stores_the_mapped_columns(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_corporate_actions(conn, _records())
    row = conn.execute(
        "SELECT account, action_type, ticker, effective_date, details, source "
        "FROM corporate_actions WHERE action_id = 'ca:1001'"
    ).fetchone()
    assert row is not None
    assert row[:4] == ("U1234567", "split", "AAPL", date(2026, 9, 15))
    assert json.loads(row[4])["ratio"] == "4:1"
    assert row[5] == "ibkr-flex"


def _snapshot(conn: duckdb.DuckDBPyConnection, day: date) -> None:
    for i, ticker in enumerate(HELD):
        conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
            "VALUES (?, 'U1234567', ?, ?, 10, 1000, 'USD')",
            [day, ticker, i + 1],
        )


def test_fixture_rows_become_dividend_and_split_events(conn: duckdb.DuckDBPyConnection) -> None:
    upsert_corporate_actions(conn, _records())
    _snapshot(conn, PREV)
    _snapshot(conn, CURR)

    events = compute_events(conn, PREV, CURR)
    corporate = sorted(
        (e.event_type, e.ticker)
        for e in events
        if e.event_type in (EventType.DIVIDEND, EventType.SPLIT)
    )
    assert corporate == sorted([
        (EventType.DIVIDEND, "MSFT"),
        (EventType.DIVIDEND, "KO"),
        (EventType.SPLIT, "AAPL"),
        (EventType.SPLIT, "GE"),
    ])
    assert not [e for e in events if e.ticker == "ATVI"]
```

Replace the `_records` annotation with `list[CorporateActionRecord]` (import it) if ruff/mypy object to the ignore; the suite type-checks `src` only, but keep tests clean.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_ibkr_flex_events.py -q`
Expected: FAIL, `ImportError: cannot import name 'upsert_corporate_actions'`.

- [ ] **Step 3: Implement the upsert**

Append to `src/bot/ingest/ibkr_flex.py` (add `import json`, `from collections.abc import Iterable`, and `from typing import TYPE_CHECKING` / `if TYPE_CHECKING: import duckdb` to the imports, matching `trades.py`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_ibkr_flex_events.py tests/unit/test_ibkr_flex_parser.py -q && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/ibkr_flex.py tests/integration/test_ibkr_flex_events.py
git commit -m "feat(#56): upsert Flex corporate actions idempotently"
```

---

### Task 3: `FlexClient` — the two-GET protocol

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py`
- Test: `tests/unit/test_ibkr_flex_client.py`
- Modify: `tests/unit/test_seam_enforcement.py`

**Interfaces:**
- Produces:
  - `SEND_REQUEST_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"`
  - `MAX_POLLS = 10`, `POLL_DELAY_SECONDS = 3.0`, `RETRYABLE_CODES = frozenset({"1019", "1009"})`
  - `class FlexError(RuntimeError)`
  - `class FlexClient(token: str, query_id: str, *, timeout: float = 30.0, transport: httpx.BaseTransport | None = None)` with `fetch_statement() -> str`, `close()`, `__enter__`/`__exit__` (as `TiingoClient`).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_ibkr_flex_client.py`:

```python
"""FlexClient against httpx.MockTransport: protocol, retries, failures, secrecy (#56)."""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest
from structlog.testing import capture_logs

from bot.ingest import ibkr_flex
from bot.ingest.ibkr_flex import MAX_POLLS, FlexClient, FlexError
from bot.utils.logging import configure_logging

TOKEN = "123456789012345678901234"
QUERY = "987654"
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
STATEMENT = '<FlexQueryResponse queryName="q" type="AF"><FlexStatements count="0" /></FlexQueryResponse>'

SUCCESS = (
    '<FlexStatementResponse timestamp="01 October, 2026 08:30 AM EDT">'
    "<Status>Success</Status><ReferenceCode>1234567890</ReferenceCode>"
    f"<Url>{GET_URL}</Url></FlexStatementResponse>"
)


def _error(status: str, code: str, message: str) -> str:
    return (
        f"<FlexStatementResponse><Status>{status}</Status>"
        f"<ErrorCode>{code}</ErrorCode><ErrorMessage>{message}</ErrorMessage>"
        "</FlexStatementResponse>"
    )


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)


def _client(statement_bodies: list[str], send_body: str = SUCCESS) -> tuple[FlexClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    bodies = iter(statement_bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/SendRequest"):
            return httpx.Response(200, text=send_body)
        return httpx.Response(200, text=next(bodies))

    return FlexClient(TOKEN, QUERY, transport=httpx.MockTransport(handler)), seen


def test_happy_path_sends_both_requests() -> None:
    client, seen = _client([STATEMENT])
    assert client.fetch_statement() == STATEMENT
    send, fetch = seen
    assert send.url.host == "ndcdyn.interactivebrokers.com"
    assert dict(send.url.params) == {"t": TOKEN, "q": QUERY, "v": "3"}
    assert str(fetch.url).startswith(GET_URL)
    assert dict(fetch.url.params) == {"q": "1234567890", "t": TOKEN, "v": "3"}


@pytest.mark.parametrize("code", ["1019", "1009"])
def test_retryable_code_then_success(code: str) -> None:
    client, seen = _client([_error("Warn", code, "Statement generation in progress."), STATEMENT])
    assert client.fetch_statement() == STATEMENT
    assert len(seen) == 3


def test_invalid_token_on_request_fails_fast_with_code() -> None:
    client, seen = _client([], send_body=_error("Fail", "1012", "Token has expired."))
    with pytest.raises(FlexError, match="1012"):
        client.fetch_statement()
    assert len(seen) == 1


def test_non_retryable_code_on_fetch_fails_fast() -> None:
    client, seen = _client([_error("Fail", "1015", "Token is invalid.")])
    with pytest.raises(FlexError, match="1015.*Token is invalid"):
        client.fetch_statement()
    assert len(seen) == 2


def test_exhausting_the_polls_fails() -> None:
    client, seen = _client([_error("Warn", "1019", "in progress")] * MAX_POLLS)
    with pytest.raises(FlexError, match=str(MAX_POLLS)):
        client.fetch_statement()
    assert len(seen) == 1 + MAX_POLLS


def test_success_status_on_fetch_is_not_a_statement() -> None:
    client, _ = _client([SUCCESS])
    with pytest.raises(FlexError):
        client.fetch_statement()


def _failing(handler: Callable[[httpx.Request], httpx.Response]) -> FlexClient:
    return FlexClient(TOKEN, QUERY, transport=httpx.MockTransport(handler))


def test_http_error_message_is_scrubbed() -> None:
    client = _failing(lambda request: httpx.Response(500, text="oops"))
    with pytest.raises(FlexError) as exc:
        client.fetch_statement()
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_transport_error_message_is_scrubbed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    with pytest.raises(FlexError) as exc:
        _failing(handler).fetch_statement()
    assert TOKEN not in str(exc.value)


def test_token_never_logged(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG")
    caplog.set_level(logging.DEBUG)
    client, _ = _client([_error("Warn", "1019", "in progress"), STATEMENT])
    with capture_logs() as logs:
        client.fetch_statement()
        failing, _ = _client([_error("Fail", "1015", "Token is invalid.")])
        with pytest.raises(FlexError):
            failing.fetch_statement()
    assert TOKEN not in caplog.text
    assert TOKEN not in capsys.readouterr().out
    assert TOKEN not in repr(logs)
```

Append to `tests/unit/test_seam_enforcement.py`:

```python
def test_flex_client_is_internal_to_its_module() -> None:
    assert _offenders(r"\bFlexClient\b", allowed={"ibkr_flex.py"}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ibkr_flex_client.py -q`
Expected: FAIL, `ImportError: cannot import name 'MAX_POLLS'`.

- [ ] **Step 3: Implement the client**

Add to `src/bot/ingest/ibkr_flex.py` (imports: `import time`, `import httpx`):

```python
SEND_REQUEST_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
)
MAX_POLLS = 10
POLL_DELAY_SECONDS = 3.0
# 1019: statement generation in progress; 1009: server under heavy load.
RETRYABLE_CODES = frozenset({"1019", "1009"})


class FlexError(RuntimeError):
    """The Flex Web Service refused, failed or never produced the statement."""


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
        if response.tag != "FlexStatementResponse" or response.findtext("Status") != "Success":
            raise FlexError(f"Flex SendRequest failed: {self._reason(response)}")
        reference = (response.findtext("ReferenceCode") or "").strip()
        url = (response.findtext("Url") or "").strip()
        if not reference or not url:
            raise FlexError("Flex SendRequest succeeded without a ReferenceCode or Url")

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
        raise FlexError(f"Flex statement not ready after {MAX_POLLS} polls")

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
        code = (root.findtext("ErrorCode") or "").strip() or "?"
        message = (root.findtext("ErrorMessage") or "").strip() or root.tag
        return self._scrub(f"{code} {message}")

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text
```

Note the SendRequest param order in the spec is `t, q, v`; httpx serialises the dict in insertion order, and the tests compare params as a dict, so order is not asserted. `_get` always passes the token as `t`: the spec puts it on both requests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ibkr_flex_client.py tests/unit/test_seam_enforcement.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/ibkr_flex.py tests/unit/test_ibkr_flex_client.py tests/unit/test_seam_enforcement.py
git commit -m "feat(#56): Flex Web Service client with bounded polling"
```

---

### Task 4: Settings and `import_corporate_actions`

**Files:**
- Modify: `src/bot/config.py` (after `ibkr_client_id`)
- Modify: `.env.example`
- Modify: `src/bot/ingest/ibkr_flex.py`
- Test: `tests/unit/test_ibkr_flex_import.py`, `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `FlexClient`, `parse_flex_statement`, `upsert_corporate_actions` (Tasks 1–3).
- Produces:
  - `Settings.ibkr_flex_token: str = ""`, `Settings.ibkr_flex_query_id: str = ""`
  - `import_corporate_actions(conn: duckdb.DuckDBPyConnection, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> int | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py` (follow the file's existing way of building `Settings`, e.g. with `monkeypatch.setenv("BOT_SEC_USER_AGENT", ...)` and `Settings(_env_file=None)`):

```python
def test_flex_settings_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Test test@example.com")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.ibkr_flex_token, s.ibkr_flex_query_id) == ("", "")


def test_flex_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Test test@example.com")
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", "tok")
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", "42")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.ibkr_flex_token, s.ibkr_flex_query_id) == ("tok", "42")


def test_env_example_documents_flex_settings() -> None:
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text()
    assert "BOT_IBKR_FLEX_TOKEN" in text and "BOT_IBKR_FLEX_QUERY_ID" in text
```

`tests/unit/test_ibkr_flex_import.py`:

```python
"""import_corporate_actions: no-op when unconfigured, full path when configured (#56)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import httpx
import pytest
from structlog.testing import capture_logs

from bot.config import Settings
from bot.ingest import ibkr_flex
from bot.ingest.ibkr_flex import import_corporate_actions
from bot.storage.db import apply_schema

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
SUCCESS = (
    "<FlexStatementResponse><Status>Success</Status><ReferenceCode>1</ReferenceCode>"
    "<Url>https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement</Url>"
    "</FlexStatementResponse>"
)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


def _settings(token: str, query_id: str) -> Settings:
    return Settings(
        sec_user_agent="Test test@example.com",
        ibkr_flex_token=token,
        ibkr_flex_query_id=query_id,
        _env_file=None,  # type: ignore[call-arg]
    )


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError("no HTTP call expected")


@pytest.mark.parametrize(
    ("token", "query_id"), [("", ""), ("tok", ""), ("", "42"), ("  ", "42"), ("tok", " ")]
)
def test_unconfigured_is_a_noop_with_one_info_line(
    conn: duckdb.DuckDBPyConnection, token: str, query_id: str
) -> None:
    with capture_logs() as logs:
        result = import_corporate_actions(
            conn, _settings(token, query_id), transport=httpx.MockTransport(_refuse)
        )
    assert result is None
    assert [e["log_level"] for e in logs] == ["info"]


def test_configured_imports_the_statement(
    conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)
    statement = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/SendRequest"):
            assert request.url.params["t"] == "tok" and request.url.params["q"] == "42"
            return httpx.Response(200, text=SUCCESS)
        return httpx.Response(200, text=statement)

    settings = _settings(" tok ", " 42 ")
    assert import_corporate_actions(conn, settings, transport=httpx.MockTransport(handler)) == 5
    assert import_corporate_actions(conn, settings, transport=httpx.MockTransport(handler)) == 0
```

(Adapt `Settings(...)` construction to whatever `test_config.py` already does if `_env_file` is passed differently there; the point is to keep a developer's `.env` out of the test.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_ibkr_flex_import.py tests/unit/test_config.py -q`
Expected: FAIL (`ImportError` for `import_corporate_actions`; config tests fail on the missing attribute and `.env.example`).

- [ ] **Step 3: Implement**

`src/bot/config.py`, after `ibkr_client_id`:

```python
    ibkr_flex_token: str = Field(
        default="",
        description=(
            "IBKR Flex Web Service token. With BOT_IBKR_FLEX_QUERY_ID set, `bot portfolio` "
            "imports dividends and splits from the Flex Query before computing events."
        ),
    )
    ibkr_flex_query_id: str = Field(
        default="",
        description="Id of the Activity Flex Query holding Corporate Actions and Cash Transactions.",
    )
```

`.env.example`, appended after the notifier block:

```bash
# BOT_IBKR_FLEX_TOKEN=""          # bot portfolio: IBKR Flex Web Service token (README → Corporate actions)
# BOT_IBKR_FLEX_QUERY_ID=""       # bot portfolio: Activity Flex Query id; both empty = no import
```

`src/bot/ingest/ibkr_flex.py` (add `from bot.config import Settings` under `TYPE_CHECKING`):

```python
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
    with FlexClient(token, query_id, transport=transport) as client:
        statement = client.fetch_statement()
    records = parse_flex_statement(statement)
    inserted = upsert_corporate_actions(conn, records)
    log.info("ibkr_flex_imported", records=len(records), inserted=inserted)
    return inserted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_ibkr_flex_import.py tests/unit/test_config.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/config.py .env.example src/bot/ingest/ibkr_flex.py tests/unit/test_ibkr_flex_import.py tests/unit/test_config.py
git commit -m "feat(#56): import corporate actions when the Flex settings are configured"
```

---

### Task 5: `run_portfolio` hook and CLI wiring

**Files:**
- Modify: `src/bot/portfolio/command.py`
- Modify: `src/bot/cli.py` (`portfolio` command, around line 577)
- Test: `tests/integration/test_portfolio_command.py`, `tests/unit/test_cli_portfolio.py`

**Interfaces:**
- Consumes: `import_corporate_actions` (Task 4).
- Produces: `run_portfolio(..., corporate_actions_fn: Callable[[duckdb.DuckDBPyConnection], int | None] | None = None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_portfolio_command.py`, reusing its `conn` fixture, `_client()` and `_no_analyze` helpers (read the file first; adapt names if they differ):

```python
def _state(conn: duckdb.DuckDBPyConnection, result: PortfolioRunResult) -> tuple[object, ...]:
    return (
        conn.execute(
            "SELECT * EXCLUDE (fetched_at) FROM portfolio_snapshots ORDER BY ALL"
        ).fetchall(),
        conn.execute(
            "SELECT event_type, ticker FROM events_log ORDER BY ALL"
        ).fetchall(),
        result.portfolio_path.read_text(),
        result.alerts_path.read_text(),
    )


def test_failing_corporate_actions_hook_changes_nothing(tmp_path: Path) -> None:
    def boom(_conn: duckdb.DuckDBPyConnection) -> int | None:
        raise RuntimeError("flex down")

    runs = []
    for name, hook in (("plain", None), ("hooked", boom)):
        c = duckdb.connect(str(tmp_path / f"{name}.duckdb"))
        apply_schema(c)
        with capture_logs() as logs:
            result = run_portfolio(
                c, _client(), reports_dir=tmp_path / name, today=date(2026, 5, 2),
                analyze_fn=_no_analyze, corporate_actions_fn=hook,
            )
        runs.append((_state(c, result), logs))

    (plain, _), (hooked, hooked_logs) = runs
    assert hooked == plain
    warnings = [e for e in hooked_logs if e["log_level"] == "warning"]
    assert [w["event"] for w in warnings] == ["corporate_actions_import_failed"]
    assert warnings[0]["error"] == "flex down"


def test_corporate_actions_hook_runs_after_sync_and_feeds_events(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    today = date(2026, 5, 2)
    seen_snapshot: list[int] = []

    def hook(c: duckdb.DuckDBPyConnection) -> int | None:
        row = c.execute(
            "SELECT COUNT(*) FROM portfolio_snapshots WHERE snapshot_date = ?", [today]
        ).fetchone()
        seen_snapshot.append(row[0] if row else 0)
        held = c.execute(
            "SELECT ticker FROM portfolio_snapshots WHERE snapshot_date = ? AND qty <> 0 LIMIT 1",
            [today],
        ).fetchone()
        assert held is not None
        c.execute(
            "INSERT INTO corporate_actions (action_id, action_type, ticker, effective_date) "
            "VALUES ('ct:1', 'dividend', ?, ?)",
            [held[0], today],
        )
        return 1

    result = run_portfolio(
        conn, _client(), reports_dir=tmp_path, today=today,
        analyze_fn=_no_analyze, corporate_actions_fn=hook,
    )
    assert seen_snapshot and seen_snapshot[0] > 0
    logged = conn.execute(
        "SELECT event_type FROM events_log WHERE curr_snapshot_date = ?", [today]
    ).fetchall()
    assert ("dividend",) in logged
    assert result.events >= 1
```

Imports to add: `from structlog.testing import capture_logs`, `from bot.portfolio.command import PortfolioRunResult` (if not already), `from bot.storage.db import apply_schema` (if not already). Check the `events_log` column names and the `event_type` stored value (`EventType.DIVIDEND.value`) against `schema.sql`/`events.py` and adjust the query.

Append to `tests/unit/test_cli_portfolio.py`, following the existing spy pattern at line ~160 (`monkeypatch.setattr(bot.cli, "run_portfolio", _spy)`) and the file's existing setup for a runnable `portfolio` command:

```python
def test_portfolio_wires_the_flex_importer(...) -> None:
    captured = {}

    def _spy(*args, **kwargs):
        captured.update(kwargs)
        return real_run_portfolio(*args, **kwargs)

    # ... invoke `bot portfolio` exactly as the neighbouring tests do ...
    hook = captured["corporate_actions_fn"]
    assert hook is not None
    # Flex settings are empty in the test environment: the hook is the no-op path.
    assert hook(conn) is None
```

(Write it concretely against the file's real fixtures; the assertion that matters is that `corporate_actions_fn` is passed and calling it with the test settings returns `None` without any network.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_portfolio_command.py tests/unit/test_cli_portfolio.py -q`
Expected: FAIL, `TypeError: run_portfolio() got an unexpected keyword argument 'corporate_actions_fn'` and `KeyError: 'corporate_actions_fn'`.

- [ ] **Step 3: Implement**

`src/bot/portfolio/command.py`:
- `from collections.abc import Callable, Sequence`.
- Docstring list: insert after step 1 "imports the latest corporate actions through the optional ``corporate_actions_fn`` hook (the IBKR Flex importer in the CLI); a failure there is logged as a WARNING and the run continues;" and renumber.
- Signature: add `corporate_actions_fn: Callable[[duckdb.DuckDBPyConnection], int | None] | None = None,` last; document it in `Args`.
- Body, right after `sync_portfolio(...)`:

```python
    # 1b. Best-effort corporate actions import (IBKR Flex); never fatal.
    if corporate_actions_fn is not None:
        try:
            corporate_actions_fn(conn)
        except Exception as exc:  # noqa: BLE001 — any importer failure is non-fatal by contract (#56)
            log.warning("corporate_actions_import_failed", error=str(exc) or type(exc).__name__)
```

(Check whether ruff has `BLE` enabled; drop the `noqa` if it does not flag the line.)

`src/bot/cli.py`: `from bot.ingest.ibkr_flex import import_corporate_actions`; in the `run_portfolio(...)` call add

```python
            corporate_actions_fn=lambda c: import_corporate_actions(c, settings),
```

and add one sentence to the `portfolio` docstring: "Before computing events it imports corporate actions from the IBKR Flex Web Service when ``BOT_IBKR_FLEX_TOKEN`` and ``BOT_IBKR_FLEX_QUERY_ID`` are set; a failure there is a warning, not an error."

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_portfolio_command.py tests/unit/test_cli_portfolio.py tests/unit/test_seam_enforcement.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot/portfolio/command.py src/bot/cli.py tests/integration/test_portfolio_command.py tests/unit/test_cli_portfolio.py
git commit -m "feat(#56): import corporate actions during bot portfolio"
```

---

### Task 6: Documentation

**Files:**
- Modify: `README.md` (new section after "### Configuration" inside "## Portfolio sync — Interactive Brokers (M5)", before "### Notifications")
- Modify: `docs/adr/0004-tws-api-via-ib-async.md:45-47` and the "Alternatives rejected" Flex bullet
- Modify: `src/bot/storage/schema.sql:232-239`
- Modify: `src/bot/portfolio/trades.py:10-15`
- Modify: `docs/plano/estado.py` (rows `ibkr-corp`, `tablas`, `ev-corp`, `m5`), `docs/plano/views.py:407`
- Test: `tests/unit/test_web_docs.py` (or a new `tests/unit/test_flex_docs.py`)

- [ ] **Step 1: Write the failing doc test**

`tests/unit/test_flex_docs.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_flex_docs.py -q`
Expected: FAIL on every assertion.

- [ ] **Step 3: Write the docs**

README section (exact opening line required by the issue):

````markdown
### Corporate actions via Flex Web Service

Written from IBKR's documentation and not yet verified against the portal; see #110.

The TWS socket does not report dividends or splits, so `bot portfolio` pulls them
from IBKR's **Flex Web Service** (`bot.ingest.ibkr_flex`) before computing the day's
events. Without the two settings below the import is skipped with one INFO line;
any failure during it is logged as a WARNING and the run carries on.

1. In Client Portal, **Performance & Reports → Flex Queries → Activity Flex Query**,
   create a query with:
   - **Corporate Actions**: accountId, currency, assetCategory, symbol, description,
     conid, isin, reportDate, dateTime, actionID, type, quantity, amount, proceeds,
     value, code.
   - **Cash Transactions**: accountId, currency, assetCategory, symbol, description,
     conid, isin, dateTime, settleDate, reportDate, amount, type, transactionID, code.
   - Period **Last 30 Calendar Days**, format **XML**, default date (`yyyyMMdd`) and
     time (`HHmmss`) formats with the `;` separator, all accounts.
   Note the query id.
2. **Settings → Reporting → Flex Web Service**: generate a token and note its expiry.
3. Put both in `.env` (never commit them):

   ```bash
   BOT_IBKR_FLEX_TOKEN=...      # Flex Web Service token
   BOT_IBKR_FLEX_QUERY_ID=...   # the Activity Flex Query id
   ```

Dividends and payments in lieu become `DIVIDEND` events, forward and reverse
splits become `SPLIT` events, for tickers held on the day. Other corporate
actions are stored with their raw IBKR type but raise no event yet.
````

ADR 0004, replace the "Corporate actions are out of reach" bullet with:

```markdown
- **Corporate actions come from elsewhere.** Dividends and splits need the IBKR
  Flex Web Service, not the socket. `src/bot/ingest/ibkr_flex.py` (#56) imports
  them into `corporate_actions` during `bot portfolio` when a Flex token and
  query id are configured, so the `DIVIDEND` and `SPLIT` events in spec §8.3 can
  fire. It was written against a synthetic statement; live validation is #110.
```

and in "Alternatives rejected", end the Flex bullet with "It now closes the corporate-actions gap alongside the socket (`src/bot/ingest/ibkr_flex.py`, #56)." in place of "It remains the candidate for closing the corporate-actions gap later."

`schema.sql` comment above `corporate_actions`:

```sql
-- Corporate actions — dividends received, splits, mergers (M5, #27).
-- The live TWS socket does NOT expose corporate actions in any reliable form
-- (see #27 addendum). They come from IBKR's Flex Web Service, imported by
-- src/bot/ingest/ibkr_flex.py (#56) during `bot portfolio` when a Flex token is
-- configured. `action_id` is 'ca:<actionID>' or 'ct:<transactionID>'. `details`
-- is a JSON blob holding the fields that vary by action type (split ratio,
-- IBKR's raw type, amounts, etc.).
```

`trades.py` docstring paragraph:

```text
Corporate actions are **deliberately out of scope** here. The live TWS socket
does not expose dividends/splits/mergers in any reliable form — they come from
IBKR's Flex Web Service, a separate HTTP integration with its own auth (see the
#27 addendum), imported by :mod:`bot.ingest.ibkr_flex` (#56).
```

`docs/plano/estado.py` (Spanish, like the rest of the file):
- `ibkr-corp`: state `"a-medias"`, evidence `"ingest/ibkr_flex.py; portfolio/command.py"`, note: `"El importador del Flex Web Service (#56) escribe corporate_actions en cada bot portfolio cuando hay token y query id. Está construido contra un statement sintético: falta validarlo contra una descarga real (#110)."`
- `tablas` note: replace `"corporate_actions sigue sin escritor (Flex, #56)"` with `"Las quince se escriben; corporate_actions solo cuando hay token de Flex (#56)"` and adjust the sentence start (`"Catorce se escriben; "` goes away).
- `ev-corp`: state `"a-medias"`, evidence `"portfolio/events.py:217,544; ingest/ibkr_flex.py"`, note `"El detector ya tiene quien le escriba la tabla: el importador de Flex (#56). Dispara solo con token configurado y no está validado contra datos reales (#110)."`
- `m5` milestone note: replace "las corporate actions siguen sin escritor: requieren el Flex Web Service (#56)" with "las corporate actions llegan por el Flex Web Service (#56), sin validar aún contra datos reales (#110)".
- `views.py:407`: `("dividend", "requiere token de Flex")`, `("split", "requiere token de Flex")`.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/unit/test_flex_docs.py tests/unit/test_web_docs.py -q && python3 docs/plano/build.py && python3 docs/plano/build_estado.py`
Expected: tests PASS; both builds succeed (a staleness warning from `build_estado.py` about `src/` moving after `AUDITADO_EN` is expected, see Decision 10). Do not commit generated HTML unless it is already tracked (`git status` tells).

- [ ] **Step 5: Full suite and lint, then commit**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: all green.

```bash
git add README.md docs/adr/0004-tws-api-via-ib-async.md src/bot/storage/schema.sql src/bot/portfolio/trades.py docs/plano/estado.py docs/plano/views.py tests/unit/test_flex_docs.py
git commit -m "docs(#56): document the Flex corporate actions importer"
```
