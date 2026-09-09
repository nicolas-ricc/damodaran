# Free Data Stack — SEC EDGAR fundamentals + Stooq EOD prices — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the paid FMP subscription with a $0/month data stack for the US-only universe: SEC EDGAR for fundamentals and company info, Stooq for EOD prices, composed into one `MarketDataProvider` adapter selected by a setting.

**Architecture:** One new composite adapter (`EdgarStooqProvider`) behind the existing `MarketDataProvider` port. It reuses the already-written `SecEdgarClient`/`parse_company_facts` for fundamentals, adds a submissions-API path for company info (name, SIC industry, exchange, latest filing date), and adds a small Stooq CSV client for prices. The industry gap (EDGAR has no Damodaran-mappable label) is closed by mapping SIC descriptions through the existing provider-keyed `industry_mapping.csv`. FMP stays available behind the same port, chosen by `BOT_DATA_PROVIDER`.

**Tech Stack:** Python 3.14, httpx (with `httpx.MockTransport` for tests), DuckDB, pydantic-settings, Typer, pytest, ruff, mypy `--strict`, `uv` as runner.

**Spec:** No standalone spec — the decision and its rationale are recorded as ADR 0007 (written in Task 8). Context: `CONTEXT.md` (US-only scope), `docs/superpowers/plans/2026-08-24-market-data-provider-port.md` (the port this plan writes a second real adapter for), attested Task 13 run in `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md` (why the FMP free tier is not viable: 3/25 imported).

## Global Constraints

- `uv run mypy src` must exit `Success` (`--strict`).
- `uv run ruff check src tests` must exit `All checks passed!` (`line-length = 100`).
- `uv run pytest -q` must pass completely at the end of **every** task.
- **Zero network calls in tests/CI.** HTTP is faked with `httpx.MockTransport` + committed fixtures under `tests/fixtures/`. The only exception is Task 8's real run — a manual operation, not a test.
- Each ingest adapter stays a pure module (`download → parse → upsert`); functions take paths/connections, no global state.
- Seam rule (spec 2026-08-24): concrete adapter classes are named only inside their own module and the composition root (`cli.py:_make_provider`). `tests/unit/test_seam_enforcement.py` enforces it; this plan extends those tests, never weakens them.
- Graceful degradation (spec §13.2): a missing datum never aborts a run; it is logged and the consumer decides. Rate limits are the exception: they raise `ProviderRateLimitError` subclasses so the existing defer/resume machinery cuts cleanly.
- Conventional Commits, one commit per task step where the task says so.
- SEC fair-use: every EDGAR request carries `Settings.sec_user_agent`; stay well under 10 req/s (the bulk loop is sequential, so this holds by construction).

## Scope decisions

- **US-only, USD-only.** `fx_rates` in the new adapter is a USD no-op. The `refresh --region` guard from the previous plan already blocks non-US regions.
- **`ipo_date` stays `None`** under the new provider. EDGAR has no IPO date; `analyze`'s `age_years` derivation already degrades to unknown. Recorded in ADR 0007, not worked around.
- **FMP is not deleted.** `BOT_DATA_PROVIDER=fmp` keeps working for anyone with a paid key. Default becomes `edgar-stooq`.
- **Stooq's soft daily-hit limit** is handled exactly like FMP's 429: a `ProviderRateLimitError` subclass triggers the existing clean cut + `deferred` outcomes + resume-tomorrow flow. No retry loops, no sleeping.
- **Restated financials, quarterly TTM, intraday**: out of scope, unchanged.

## File Structure

- Create: `src/bot/ingest/stooq.py` — Stooq CSV client: symbol mapping, fetch, parse to `PriceBar`, `StooqRateLimitError`.
- Create: `src/bot/ingest/edgar_stooq.py` — the composite `EdgarStooqProvider` adapter.
- Modify: `src/bot/ingest/sec_edgar.py` — submissions endpoint (`fetch_submissions`, `parse_submissions_info`, `latest_filing_date_from_submissions`), `shares_outstanding` via companyconcept, derived row fields (ebitda / free_cashflow / working_capital), `EdgarRateLimitError`, optional `transport` for tests.
- Modify: `src/bot/ingest/industry_mapping.csv` — seed `sec_edgar` rows (SIC description → Damodaran industry).
- Modify: `src/bot/config.py` — `data_provider` setting; `fmp_api_key` becomes optional.
- Modify: `src/bot/cli.py` — `_make_provider` branches on the setting; `doctor` becomes provider-aware; `refresh` gains `--fundamentals` as the primary flag name (`--fmp` kept as alias).
- Modify: `.env.example` — document `BOT_DATA_PROVIDER`, mark `BOT_FMP_API_KEY` optional.
- Create: `docs/adr/0007-free-data-stack-edgar-stooq.md` — the decision record (Task 8).
- Tests: `tests/unit/test_stooq.py`, `tests/unit/test_sec_edgar_submissions.py`, `tests/unit/test_sec_edgar_derived.py`, `tests/unit/test_industry_mapping_sic.py`, `tests/unit/test_edgar_stooq_provider.py`; modify `tests/unit/test_seam_enforcement.py`, `tests/unit/test_cli_doctor.py` (existing doctor tests), `tests/unit/test_config.py` if present.
- Fixtures: `tests/fixtures/stooq/aapl_daily.csv`, `tests/fixtures/edgar/aapl_submissions.json`, `tests/fixtures/edgar/aapl_shares_concept.json` (all committed, hand-trimmed to a few rows).

Task order: 1, 2, 3 are independent. 4 depends on 2 (SIC-description convention). 5 consumes 1–4. 6 consumes 5. 7 consumes 6. 8 is the manual close-out.

---

### Task 1: Stooq price client

**Files:**
- Create: `src/bot/ingest/stooq.py`
- Create: `tests/unit/test_stooq.py`
- Create: `tests/fixtures/stooq/aapl_daily.csv`

**Interfaces:**
- Consumes: `PriceBar`, `ProviderRateLimitError` from `bot.ingest.provider`.
- Produces: `stooq_symbol(ticker: str) -> str`; `parse_stooq_csv(text: str) -> list[PriceBar]`; `class StooqRateLimitError(ProviderRateLimitError)`; `class StooqClient` with `__init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None)`, `daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]`, `close()`, context-manager methods. Task 5 wraps this client.

- [ ] **Step 1: Commit the fixture**

`tests/fixtures/stooq/aapl_daily.csv` (Stooq's real column layout, trimmed):

```csv
Date,Open,High,Low,Close,Volume
2026-09-03,228.10,230.44,227.51,229.87,41250300
2026-09-04,229.90,231.02,228.75,230.55,38970100
2026-09-05,230.60,232.18,229.94,231.42,35520400
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_stooq.py`:

```python
"""Stooq CSV client — symbol mapping, parsing, rate-limit detection."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from bot.ingest.provider import ProviderRateLimitError
from bot.ingest.stooq import StooqClient, StooqRateLimitError, parse_stooq_csv, stooq_symbol

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "stooq"


def test_stooq_symbol_lowercases_and_appends_us_suffix() -> None:
    assert stooq_symbol("AAPL") == "aapl.us"


def test_stooq_symbol_maps_class_share_dot_to_dash() -> None:
    assert stooq_symbol("BRK.B") == "brk-b.us"


def test_parse_stooq_csv_yields_price_bars_without_market_cap() -> None:
    bars = parse_stooq_csv((FIXTURES / "aapl_daily.csv").read_text(encoding="utf-8"))
    assert len(bars) == 3
    assert bars[0].date == date(2026, 9, 3)
    assert bars[0].close == pytest.approx(229.87)
    assert bars[0].volume == pytest.approx(41250300)
    assert all(b.market_cap is None for b in bars)


def test_parse_stooq_csv_tolerates_empty_body_and_no_data_marker() -> None:
    assert parse_stooq_csv("") == []
    assert parse_stooq_csv("No data") == []


def _client_with(handler: httpx.MockTransport) -> StooqClient:
    return StooqClient(transport=handler)


def test_daily_prices_requests_symbol_and_since_and_parses() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, text=(FIXTURES / "aapl_daily.csv").read_text(encoding="utf-8"))

    bars = _client_with(httpx.MockTransport(handler)).daily_prices("AAPL", since=date(2026, 9, 1))
    assert seen["s"] == "aapl.us"
    assert seen["i"] == "d"
    assert seen["d1"] == "20260901"
    assert len(bars) == 3


def test_daily_hit_limit_raises_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Exceeded the daily hits limit")

    with pytest.raises(StooqRateLimitError):
        _client_with(httpx.MockTransport(handler)).daily_prices("AAPL", since=None)


def test_stooq_rate_limit_is_a_provider_rate_limit() -> None:
    assert issubclass(StooqRateLimitError, ProviderRateLimitError)
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/test_stooq.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.ingest.stooq'`.

- [ ] **Step 4: Implement `src/bot/ingest/stooq.py`**

```python
"""Stooq EOD price adapter internals — free CSV endpoint, no API key.

Stooq serves plain-CSV daily history at ``https://stooq.com/q/d/l/``. There is
no auth and no documented quota; past a soft daily hit limit the body becomes
the plain-text marker ``Exceeded the daily hits limit`` (HTTP 200), which this
module converts into :class:`StooqRateLimitError` so the bulk refresh defers
the remaining tickers exactly like an FMP 429.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import httpx

from bot.ingest.provider import PriceBar, ProviderRateLimitError
from bot.utils.coerce import coerce_date
from bot.utils.logging import get_logger

log = get_logger(__name__)

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
_RATE_LIMIT_MARKER = "exceeded the daily hits limit"


class StooqRateLimitError(ProviderRateLimitError):
    """Stooq answered with its daily-hit-limit marker; retry tomorrow."""


def stooq_symbol(ticker: str) -> str:
    """Map our ticker spelling to Stooq's (lowercase, ``.`` -> ``-``, ``.us``)."""
    return ticker.strip().lower().replace(".", "-") + ".us"


def parse_stooq_csv(text: str) -> list[PriceBar]:
    """Parse a Stooq daily CSV body into :class:`PriceBar` rows (no market cap)."""
    body = text.strip()
    if not body or body.lower().startswith("no data"):
        return []
    bars: list[PriceBar] = []
    for row in csv.DictReader(io.StringIO(body)):
        parsed = coerce_date(row.get("Date"))
        if parsed is None:
            continue
        close_raw = row.get("Close")
        volume_raw = row.get("Volume")
        bars.append(
            PriceBar(
                date=parsed,
                close=float(close_raw) if close_raw not in (None, "") else None,
                volume=float(volume_raw) if volume_raw not in (None, "") else None,
                market_cap=None,
            )
        )
    return bars


class StooqClient:
    """Thin HTTP client for Stooq's daily CSV endpoint."""

    def __init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StooqClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        params: dict[str, str] = {"s": stooq_symbol(ticker), "i": "d"}
        if since is not None:
            params["d1"] = since.strftime("%Y%m%d")
        r = self._client.get(STOOQ_DAILY_URL, params=params)
        r.raise_for_status()
        if _RATE_LIMIT_MARKER in r.text[:200].lower():
            raise StooqRateLimitError("Stooq daily hit limit reached; resume tomorrow")
        return parse_stooq_csv(r.text)
```

Note: if `bot.utils.coerce.coerce_date` lives elsewhere (it was unified in commit `209c3c0` as "one coerce_date for DB cells and provider date strings"), import it from wherever `fmp.py` imports it — copy that exact import line.

- [ ] **Step 5: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_stooq.py -q && uv run pytest -q && uv run mypy src && uv run ruff check src tests`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/stooq.py tests/unit/test_stooq.py tests/fixtures/stooq/
git commit -m "feat(ingest): Stooq EOD price client with clean rate-limit cut"
```

---

### Task 2: EDGAR submissions — company info and latest filing date

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py`
- Create: `tests/unit/test_sec_edgar_submissions.py`
- Create: `tests/fixtures/edgar/aapl_submissions.json`

**Interfaces:**
- Consumes: `CompanyInfo` from `bot.ingest.provider`; existing `SecEdgarClient`.
- Produces: `SecEdgarClient.fetch_submissions(self, cik: str) -> dict[str, Any]`; `SecEdgarClient.__init__` gains `transport: httpx.BaseTransport | None = None` (passed to its `httpx.Client`); module functions `parse_submissions_info(ticker: str, submissions: dict[str, Any]) -> CompanyInfo` and `latest_filing_date_from_submissions(submissions: dict[str, Any]) -> date | None`; `class EdgarRateLimitError(ProviderRateLimitError)` raised by the client when EDGAR answers 429 or 403. Task 5 consumes all of these.

- [ ] **Step 1: Commit the fixture**

`tests/fixtures/edgar/aapl_submissions.json` — the real submissions shape, trimmed:

```json
{
  "cik": 320193,
  "name": "Apple Inc.",
  "sic": "3571",
  "sicDescription": "Electronic Computers",
  "tickers": ["AAPL"],
  "exchanges": ["Nasdaq"],
  "addresses": {"business": {"stateOrCountry": "CA"}},
  "filings": {
    "recent": {
      "form": ["10-Q", "8-K", "10-K"],
      "filingDate": ["2026-08-01", "2026-07-15", "2025-11-01"],
      "accessionNumber": ["0000320193-26-000070", "0000320193-26-000061", "0000320193-25-000106"]
    }
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_sec_edgar_submissions.py`:

```python
"""EDGAR submissions endpoint — CompanyInfo and latest filing date."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from bot.ingest.provider import ProviderRateLimitError
from bot.ingest.sec_edgar import (
    EdgarRateLimitError,
    SecEdgarClient,
    latest_filing_date_from_submissions,
    parse_submissions_info,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "edgar"


def _submissions() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "aapl_submissions.json").read_text("utf-8"))
    return data


def test_parse_submissions_info_maps_name_sic_and_exchange() -> None:
    info = parse_submissions_info("aapl", _submissions())
    assert info.ticker == "AAPL"
    assert info.name == "Apple Inc."
    assert info.industry == "Electronic Computers"  # sicDescription is the mapping key
    assert info.exchange_short_name == "Nasdaq"
    assert info.country == "US"
    assert info.currency == "USD"
    assert info.is_actively_trading is True
    assert info.ipo_date is None  # EDGAR has no IPO date; documented in ADR 0007


def test_parse_submissions_info_survives_missing_sic_and_exchanges() -> None:
    data = _submissions()
    data["sicDescription"] = ""
    data["exchanges"] = []
    info = parse_submissions_info("AAPL", data)
    assert info.industry is None
    assert info.exchange_short_name is None


def test_latest_filing_date_considers_only_financial_forms() -> None:
    # The 8-K dated 2026-07-15 must not win over the 10-Q dated 2026-08-01.
    assert latest_filing_date_from_submissions(_submissions()) == date(2026, 8, 1)


def test_latest_filing_date_none_when_no_recent_filings() -> None:
    assert latest_filing_date_from_submissions({"filings": {"recent": {}}}) is None


def test_fetch_submissions_hits_the_cik_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_submissions())

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    data = client.fetch_submissions("0000320193")
    assert data["name"] == "Apple Inc."
    assert seen == ["https://data.sec.gov/submissions/CIK0000320193.json"]


def test_edgar_429_raises_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(EdgarRateLimitError):
        client.fetch_submissions("0000320193")


def test_edgar_rate_limit_is_a_provider_rate_limit() -> None:
    assert issubclass(EdgarRateLimitError, ProviderRateLimitError)
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/test_sec_edgar_submissions.py -q`
Expected: FAIL — `ImportError` (names don't exist yet).

- [ ] **Step 4: Implement in `sec_edgar.py`**

Add near the top:

```python
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"

_FINANCIAL_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A"}


class EdgarRateLimitError(ProviderRateLimitError):
    """EDGAR throttled us (429, or the 403 it serves for abusive traffic)."""
```

(`ProviderRateLimitError` is imported from `bot.ingest.provider` — the module already imports `ParsedCompanyData` from there; extend that import.)

`SecEdgarClient.__init__` gains `transport: httpx.BaseTransport | None = None` and passes `transport=transport` to `httpx.Client(...)`. Add a private response gate and use it in **every** fetch method (`_load_ticker_table`, `fetch_company_facts`, and the new ones):

```python
    def _checked(self, r: httpx.Response) -> httpx.Response:
        if r.status_code in (403, 429):
            raise EdgarRateLimitError(f"EDGAR throttled: HTTP {r.status_code} for {r.url}")
        r.raise_for_status()
        return r

    def fetch_submissions(self, cik: str) -> dict[str, Any]:
        """Fetch the submissions JSON (profile + recent filings) for a CIK."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        r = self._checked(self._client.get(SUBMISSIONS_URL_TEMPLATE.format(cik=cik)))
        result: dict[str, Any] = r.json()
        return result
```

Module-level parsers (import `CompanyInfo` from `bot.ingest.provider`, `date` from `datetime`):

```python
def parse_submissions_info(ticker: str, submissions: dict[str, Any]) -> CompanyInfo:
    """Map an EDGAR submissions payload to :class:`CompanyInfo`.

    ``industry`` carries ``sicDescription`` verbatim — that string is the
    ``sec_edgar`` key into ``industry_mapping.csv``. EDGAR has no IPO date and
    no sector taxonomy, so those stay ``None`` (ADR 0007).
    """
    exchanges = submissions.get("exchanges") or []
    exchange = str(exchanges[0]) if exchanges else None
    sic_description = str(submissions.get("sicDescription") or "").strip() or None
    return CompanyInfo(
        ticker=ticker.upper(),
        name=str(submissions.get("name") or ticker.upper()),
        exchange=exchange,
        exchange_short_name=exchange,
        country="US",
        currency="USD",
        sector=None,
        industry=sic_description,
        is_actively_trading=True,
        ipo_date=None,
    )


def latest_filing_date_from_submissions(submissions: dict[str, Any]) -> date | None:
    """Newest 10-K/10-Q filing date in ``filings.recent`` (parallel arrays)."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    latest: date | None = None
    for form, filed_raw in zip(forms, dates, strict=False):
        if form not in _FINANCIAL_FORMS:
            continue
        filed = coerce_date(filed_raw)
        if filed is None:
            continue
        if latest is None or filed > latest:
            latest = filed
    return latest
```

(`coerce_date`: same import as used elsewhere in the ingest package.)

- [ ] **Step 5: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_sec_edgar_submissions.py -q && uv run pytest -q && uv run mypy src && uv run ruff check src tests`
Expected: all green. If existing `sec_edgar` tests constructed `SecEdgarClient` and now fail on the `_checked` change, they were relying on unchecked responses — fix them to expect `EdgarRateLimitError` on 429/403.

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/sec_edgar.py tests/unit/test_sec_edgar_submissions.py tests/fixtures/edgar/aapl_submissions.json
git commit -m "feat(ingest): EDGAR submissions — CompanyInfo, latest filing date, rate-limit error"
```

---

### Task 3: EDGAR parser completions — derived fields and shares outstanding

The FMP statements carried `ebitda`, `free_cashflow` and `working_capital` pre-computed; EDGAR's XBRL facts don't. The screener (`build_company_data`) and valuator read those columns, so the EDGAR path must derive them or every company loses gates/inputs.

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (concept map + derivation + shares endpoint)
- Create: `tests/unit/test_sec_edgar_derived.py`
- Create: `tests/fixtures/edgar/aapl_shares_concept.json`

**Interfaces:**
- Consumes: `ANNUAL_CONCEPT_MAP`, `_collect_period_rows` (existing).
- Produces: rows out of `parse_company_facts` additionally carry `ebitda`, `free_cashflow`, `working_capital` when derivable; `SecEdgarClient.shares_outstanding(self, cik: str) -> float | None`. Task 5 consumes `shares_outstanding` for market cap.

- [ ] **Step 1: Commit the fixture**

`tests/fixtures/edgar/aapl_shares_concept.json` (real `companyconcept` shape, trimmed):

```json
{
  "cik": 320193,
  "taxonomy": "dei",
  "tag": "EntityCommonStockSharesOutstanding",
  "units": {
    "shares": [
      {"end": "2026-06-27", "val": 14840392000, "form": "10-Q", "filed": "2026-08-01"},
      {"end": "2025-09-27", "val": 15037870000, "form": "10-K", "filed": "2025-11-01"}
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_sec_edgar_derived.py`:

```python
"""Derived financial fields and shares outstanding for the EDGAR path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from bot.ingest.sec_edgar import SecEdgarClient, _derive_financial_fields

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "edgar"


def test_derives_ebitda_free_cashflow_and_working_capital() -> None:
    row: dict[str, Any] = {
        "ebit": 100.0,
        "depreciation": 20.0,
        "operating_cashflow": 90.0,
        "capex": 30.0,
        "_current_assets": 500.0,
        "_current_liabilities": 320.0,
    }
    _derive_financial_fields(row)
    assert row["ebitda"] == pytest.approx(120.0)
    assert row["free_cashflow"] == pytest.approx(60.0)
    assert row["working_capital"] == pytest.approx(180.0)
    assert "_current_assets" not in row and "_current_liabilities" not in row


def test_derivation_leaves_gaps_when_inputs_missing() -> None:
    row: dict[str, Any] = {"ebit": 100.0}  # no depreciation, no ocf/capex, no current a/l
    _derive_financial_fields(row)
    assert row.get("ebitda") is None
    assert row.get("free_cashflow") is None
    assert row.get("working_capital") is None


def test_derivation_never_overwrites_reported_values() -> None:
    row: dict[str, Any] = {"ebit": 100.0, "depreciation": 20.0, "ebitda": 999.0}
    _derive_financial_fields(row)
    assert row["ebitda"] == pytest.approx(999.0)


def test_shares_outstanding_returns_newest_value() -> None:
    payload = json.loads((FIXTURES / "aapl_shares_concept.json").read_text("utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        assert "companyconcept/CIK0000320193/dei/EntityCommonStockSharesOutstanding" in str(
            request.url
        )
        return httpx.Response(200, json=payload)

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    assert client.shares_outstanding("0000320193") == pytest.approx(14840392000)


def test_shares_outstanding_none_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = SecEdgarClient(
        user_agent="Test test@example.com", transport=httpx.MockTransport(handler)
    )
    assert client.shares_outstanding("0000320193") is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/test_sec_edgar_derived.py -q`
Expected: FAIL — `ImportError: cannot import name '_derive_financial_fields'`.

- [ ] **Step 4: Implement**

In `ANNUAL_CONCEPT_MAP`, add two underscore-prefixed working keys (the underscore marks "not a DB column — consumed by derivation"):

```python
    "_current_assets": ["AssetsCurrent"],
    "_current_liabilities": ["LiabilitiesCurrent"],
```

Add the derivation and call it on every row before returning from `_collect_period_rows` (both annual and quarterly paths — find where each row dict is finalized and apply `_derive_financial_fields(row)` there):

```python
def _derive_financial_fields(row: dict[str, Any]) -> None:
    """Fill ebitda / free_cashflow / working_capital when their inputs exist.

    EDGAR facts report the components, not the aggregates FMP pre-computed.
    Derivations only fill gaps — a reported aggregate is never overwritten —
    and missing inputs leave ``None`` (graceful degradation, spec §13.2).
    """
    ebit, dep = row.get("ebit"), row.get("depreciation")
    if row.get("ebitda") is None:
        row["ebitda"] = ebit + dep if ebit is not None and dep is not None else None
    ocf, capex = row.get("operating_cashflow"), row.get("capex")
    if row.get("free_cashflow") is None:
        row["free_cashflow"] = ocf - capex if ocf is not None and capex is not None else None
    ca = row.pop("_current_assets", None)
    cl = row.pop("_current_liabilities", None)
    if row.get("working_capital") is None:
        row["working_capital"] = ca - cl if ca is not None and cl is not None else None
```

Add the shares endpoint to `SecEdgarClient`:

```python
COMPANY_CONCEPT_URL_TEMPLATE = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/dei/"
    "EntityCommonStockSharesOutstanding.json"
)
```

```python
    def shares_outstanding(self, cik: str) -> float | None:
        """Newest reported common shares outstanding (dei), or None."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        r = self._client.get(COMPANY_CONCEPT_URL_TEMPLATE.format(cik=cik))
        if r.status_code == 404:
            return None
        if r.status_code in (403, 429):
            raise EdgarRateLimitError(f"EDGAR throttled: HTTP {r.status_code} for {r.url}")
        r.raise_for_status()
        entries = r.json().get("units", {}).get("shares", [])
        newest_val: float | None = None
        newest_end: date | None = None
        for entry in entries:
            end = coerce_date(entry.get("end"))
            val = entry.get("val")
            if end is None or val is None:
                continue
            if newest_end is None or end > newest_end:
                newest_end, newest_val = end, float(val)
        return newest_val
```

- [ ] **Step 5: Verify a real upsert still works — check the underscore keys never leak**

The existing `upsert_financials_annual` builds its column list from the row dicts or from a fixed column set — read it (`sec_edgar.py:288`) and confirm the popped `_current_assets`/`_current_liabilities` can never reach it. The `pop` in `_derive_financial_fields` guarantees this as long as derivation runs on **every** row; the first test asserts the pop.

- [ ] **Step 6: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_sec_edgar_derived.py -q && uv run pytest -q && uv run mypy src && uv run ruff check src tests`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/bot/ingest/sec_edgar.py tests/unit/test_sec_edgar_derived.py tests/fixtures/edgar/aapl_shares_concept.json
git commit -m "feat(ingest): EDGAR derives ebitda/fcf/working capital; dei shares endpoint"
```

---

### Task 4: SIC → Damodaran industry mapping

`companies.industry_damodaran` is what the coverage gate (ADR 0006), every sector-relative rule, and the valuator key off. Under EDGAR the provider label is the SIC description (Task 2). The existing mechanism already supports a second provider — `industry_mapping.csv` is keyed by `(provider, provider_industry)` and `IndustryMapping.resolve(provider, industry)` normalizes labels — so this task is data plus tests, no new code.

**Files:**
- Modify: `src/bot/ingest/industry_mapping.csv`
- Create: `tests/unit/test_industry_mapping_sic.py`

**Interfaces:**
- Consumes: `load_industry_mapping`, `IndustryMapping.resolve` (existing).
- Produces: `sec_edgar` rows in the packaged CSV. Task 5's provider passes `info.industry` (= SIC description) through the standard `_company_row` path — nothing else changes.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_industry_mapping_sic.py`:

```python
"""The sec_edgar side of the industry mapping — SIC descriptions to Damodaran."""

from __future__ import annotations

import csv

from bot.ingest.industry_mapping import default_mapping_path, load_industry_mapping


def _rows() -> list[dict[str, str]]:
    with default_mapping_path().open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_sec_edgar_rows_exist() -> None:
    assert sum(1 for r in _rows() if r["provider"] == "sec_edgar") >= 40


def test_sec_edgar_damodaran_labels_are_already_known_labels() -> None:
    """Guard against typos: every Damodaran label on a sec_edgar row must already
    appear on some fmp row — fmp's right-hand side was validated against the
    damodaran_industry table when that mapping shipped."""
    rows = _rows()
    fmp_labels = {r["damodaran_industry"] for r in rows if r["provider"] == "fmp"}
    for r in rows:
        if r["provider"] != "sec_edgar":
            continue
        assert r["damodaran_industry"] in fmp_labels, (
            f"unknown Damodaran label {r['damodaran_industry']!r} "
            f"for SIC {r['provider_industry']!r}"
        )


def test_common_sic_descriptions_resolve() -> None:
    mapping = load_industry_mapping()
    assert mapping.resolve("sec_edgar", "Electronic Computers") is not None
    assert mapping.resolve("sec_edgar", "Services-Prepackaged Software") is not None
    assert mapping.resolve("sec_edgar", "Pharmaceutical Preparations") is not None
    assert mapping.resolve("sec_edgar", "Totally Unknown Industry") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_industry_mapping_sic.py -q`
Expected: FAIL — zero `sec_edgar` rows.

- [ ] **Step 3: Seed the mapping**

Append `sec_edgar` rows to `src/bot/ingest/industry_mapping.csv`. Use EDGAR's canonical `sicDescription` strings on the left; on the right, **only labels that already appear in the fmp rows of the same file** (open the CSV and copy the exact spellings — e.g. if the fmp side says `Semiconductor`, do not write `Semiconductors`). Seed set (adjust right-hand spellings to the file's existing fmp labels):

```csv
sec_edgar,Electronic Computers,Computers/Peripherals
sec_edgar,Services-Prepackaged Software,Software (System & Application)
sec_edgar,Services-Computer Programming Data Processing,Software (Internet)
sec_edgar,Semiconductors & Related Devices,Semiconductor
sec_edgar,Pharmaceutical Preparations,Drugs (Pharmaceutical)
sec_edgar,Biological Products (No Diagnostic Substances),Drugs (Biotechnology)
sec_edgar,Surgical & Medical Instruments & Apparatus,Healthcare Products
sec_edgar,National Commercial Banks,Bank (Money Center)
sec_edgar,State Commercial Banks,Banks (Regional)
sec_edgar,Fire Marine & Casualty Insurance,Insurance (Prop/Cas.)
sec_edgar,Life Insurance,Insurance (Life)
sec_edgar,Crude Petroleum & Natural Gas,Oil/Gas (Production and Exploration)
sec_edgar,Petroleum Refining,Oil/Gas (Integrated)
sec_edgar,Electric Services,Utility (General)
sec_edgar,Natural Gas Transmission,Oil/Gas Distribution
sec_edgar,Retail-Variety Stores,Retail (General)
sec_edgar,Retail-Eating Places,Restaurant/Dining
sec_edgar,Retail-Drug Stores and Proprietary Stores,Retail (Special Lines)
sec_edgar,Retail-Catalog & Mail-Order Houses,Retail (Online)
sec_edgar,Motor Vehicles & Passenger Car Bodies,Auto & Truck
sec_edgar,Motor Vehicle Parts & Accessories,Auto Parts
sec_edgar,Aircraft,Aerospace/Defense
sec_edgar,Guided Missiles & Space Vehicles & Parts,Aerospace/Defense
sec_edgar,Air Transportation Scheduled,Air Transport
sec_edgar,Railroads Line-Haul Operating,Transportation (Railroads)
sec_edgar,Beverages,Beverage (Soft)
sec_edgar,Malt Beverages,Beverage (Alcoholic)
sec_edgar,Perfumes Cosmetics & Other Toilet Preparations,Household Products
sec_edgar,Soap Detergents Cleaning Preparations,Household Products
sec_edgar,Plastics Materials Synth Resins & Nonvulcan Elastomers,Chemical (Specialty)
sec_edgar,Industrial Inorganic Chemicals,Chemical (Basic)
sec_edgar,Steel Works Blast Furnaces & Rolling Mills,Steel
sec_edgar,Gold Mining,Metals & Mining
sec_edgar,Construction Machinery & Equip,Machinery
sec_edgar,Farm Machinery & Equipment,Machinery
sec_edgar,General Industrial Machinery & Equipment,Machinery
sec_edgar,Telephone Communications (No Radiotelephone),Telecom. Services
sec_edgar,Radiotelephone Communications,Telecom. (Wireless)
sec_edgar,Cable & Other Pay Television Services,Cable TV
sec_edgar,Real Estate Investment Trusts,R.E.I.T.
sec_edgar,Hotels & Motels,Hotel/Gaming
sec_edgar,Services-Advertising Agencies,Advertising
```

This seed is a floor, not full coverage: an unmapped SIC logs `ingest.industry_mapping.unmapped` (a warning) and the company hits the ADR 0006 coverage gate. Task 8's real run drives the unmapped count to zero over the actual S&P 500.

- [ ] **Step 4: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_industry_mapping_sic.py -q && uv run pytest -q && uv run mypy src && uv run ruff check src tests`
Expected: all green. If the label-validation test fails, fix the right-hand spellings against the fmp rows — that failure is the test doing its job.

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/industry_mapping.csv tests/unit/test_industry_mapping_sic.py
git commit -m "feat(ingest): seed the sec_edgar SIC-to-Damodaran industry mapping"
```

---

### Task 5: The composite adapter — `EdgarStooqProvider`

**Files:**
- Create: `src/bot/ingest/edgar_stooq.py`
- Create: `tests/unit/test_edgar_stooq_provider.py`
- Modify: `tests/unit/test_seam_enforcement.py`

**Interfaces:**
- Consumes: everything Tasks 1–3 produced; `parse_company_facts`, `SecEdgarClient` (existing); the port dataclasses.
- Produces: `class EdgarStooqProvider` satisfying `MarketDataProvider` — `__init__(self, sec_user_agent: str, timeout: float = 30.0, sec_transport: httpx.BaseTransport | None = None, stooq_transport: httpx.BaseTransport | None = None)`, `name == "edgar_stooq"`, plus the six port methods and context-manager support. Task 6's composition root constructs it.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_edgar_stooq_provider.py`:

```python
"""EdgarStooqProvider — the free-stack adapter behind the MarketDataProvider port."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from bot.ingest.edgar_stooq import EdgarStooqProvider
from bot.ingest.provider import MarketDataProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

_TICKER_TABLE = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _edgar_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("company_tickers.json"):
        return httpx.Response(200, json=_TICKER_TABLE)
    if "submissions/CIK0000320193" in url:
        payload: dict[str, Any] = json.loads(
            (FIXTURES / "edgar" / "aapl_submissions.json").read_text("utf-8")
        )
        return httpx.Response(200, json=payload)
    if "companyconcept/CIK0000320193" in url:
        return httpx.Response(
            200, json=json.loads((FIXTURES / "edgar" / "aapl_shares_concept.json").read_text("utf-8"))
        )
    if "companyfacts/CIK0000320193" in url:
        # Minimal but real-shaped company-facts body: one revenue fact.
        return httpx.Response(
            200,
            json={
                "cik": 320193,
                "entityName": "Apple Inc.",
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "units": {
                                "USD": [
                                    {
                                        "end": "2025-09-27",
                                        "val": 400000000000,
                                        "fy": 2025,
                                        "fp": "FY",
                                        "form": "10-K",
                                        "filed": "2025-11-01",
                                        "accn": "0000320193-25-000106",
                                    }
                                ]
                            }
                        }
                    }
                },
            },
        )
    raise AssertionError(f"unexpected EDGAR request: {url}")


def _stooq_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, text=(FIXTURES / "stooq" / "aapl_daily.csv").read_text(encoding="utf-8")
    )


def _provider() -> EdgarStooqProvider:
    return EdgarStooqProvider(
        sec_user_agent="Test test@example.com",
        sec_transport=httpx.MockTransport(_edgar_handler),
        stooq_transport=httpx.MockTransport(_stooq_handler),
    )


def test_satisfies_the_port_protocol() -> None:
    assert isinstance(_provider(), MarketDataProvider)
    assert _provider().name == "edgar_stooq"


def test_lookup_company_carries_the_sic_description_as_industry() -> None:
    info = _provider().lookup_company("aapl")
    assert info is not None
    assert info.name == "Apple Inc."
    assert info.industry == "Electronic Computers"


def test_lookup_unknown_ticker_returns_none() -> None:
    def edgar(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("company_tickers.json"):
            return httpx.Response(200, json=_TICKER_TABLE)
        raise AssertionError("should not fetch beyond the ticker table")

    provider = EdgarStooqProvider(
        sec_user_agent="Test test@example.com",
        sec_transport=httpx.MockTransport(edgar),
        stooq_transport=httpx.MockTransport(_stooq_handler),
    )
    assert provider.lookup_company("NOPE") is None


def test_fundamentals_bundles_info_annual_and_filings() -> None:
    bundle = _provider().fundamentals("AAPL")
    assert bundle.info is not None and bundle.info.industry == "Electronic Computers"
    assert bundle.annual.company["source"] == "sec_edgar"
    assert len(bundle.annual.annual) == 1
    assert bundle.annual.annual[0]["revenue"] == pytest.approx(400000000000)
    assert bundle.quarterly.quarterly == []


def test_daily_prices_come_from_stooq_with_market_cap_on_newest_fresh_bar() -> None:
    bars = _provider().daily_prices("AAPL", since=None)
    assert len(bars) == 3
    newest = max(bars, key=lambda b: b.date)
    if (date.today() - newest.date).days <= 7:
        assert newest.market_cap == pytest.approx(newest.close * 14840392000)  # type: ignore[operator]
    else:  # fixture aged past freshness — cap must stay honest: None
        assert newest.market_cap is None
    assert all(b.market_cap is None for b in bars if b is not newest)


def test_fx_rates_usd_is_a_noop() -> None:
    assert _provider().fx_rates("USD", since=None) == []


def test_fx_rates_non_usd_returns_empty_and_does_not_raise() -> None:
    assert _provider().fx_rates("EUR", since=None) == []


def test_latest_filing_date_reads_submissions() -> None:
    assert _provider().latest_filing_date("AAPL") == date(2026, 8, 1)


def test_close_then_reuse_reopens() -> None:
    provider = _provider()
    assert provider.lookup_company("AAPL") is not None
    provider.close()
    assert provider.lookup_company("AAPL") is not None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_edgar_stooq_provider.py -q`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/bot/ingest/edgar_stooq.py`**

```python
"""The free-stack adapter: SEC EDGAR fundamentals + Stooq EOD prices (ADR 0007).

Composes the two free sources behind :class:`bot.ingest.provider
.MarketDataProvider`. EDGAR supplies company info (submissions), statements
(company facts) and shares outstanding; Stooq supplies daily closes. Market
cap is computed on the newest fresh bar as ``close x shares`` — mirroring the
FMP adapter's profile-onto-newest-bar behavior. FX is a USD no-op: this
adapter exists only under the US-only scope (listing = reporting = USD).
"""

from __future__ import annotations

import dataclasses
from datetime import date

import httpx

from bot.ingest.provider import CompanyInfo, FundamentalsBundle, FxRate, PriceBar
from bot.ingest.sec_edgar import (
    SecEdgarClient,
    latest_filing_date_from_submissions,
    parse_company_facts,
    parse_submissions_info,
)
from bot.ingest.stooq import StooqClient
from bot.utils.logging import get_logger

log = get_logger(__name__)

_FRESH_DAYS = 7


class EdgarStooqProvider:
    """EDGAR + Stooq behind the provider port. One instance per bulk run."""

    def __init__(
        self,
        sec_user_agent: str,
        timeout: float = 30.0,
        sec_transport: httpx.BaseTransport | None = None,
        stooq_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sec_user_agent = sec_user_agent
        self._timeout = timeout
        self._sec_transport = sec_transport
        self._stooq_transport = stooq_transport
        self._sec: SecEdgarClient | None = None
        self._stooq: StooqClient | None = None
        self._submissions_cache: dict[str, dict[str, object]] = {}

    @property
    def name(self) -> str:
        return "edgar_stooq"

    def _edgar(self) -> SecEdgarClient:
        if self._sec is None:
            self._sec = SecEdgarClient(
                user_agent=self._sec_user_agent,
                timeout=self._timeout,
                transport=self._sec_transport,
            )
        return self._sec

    def _prices(self) -> StooqClient:
        if self._stooq is None:
            self._stooq = StooqClient(timeout=self._timeout, transport=self._stooq_transport)
        return self._stooq

    def close(self) -> None:
        if self._sec is not None:
            self._sec.close()
            self._sec = None
        if self._stooq is not None:
            self._stooq.close()
            self._stooq = None
        self._submissions_cache.clear()

    def __enter__(self) -> EdgarStooqProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _cik(self, ticker: str) -> str | None:
        return self._edgar().lookup_cik(ticker)

    def _submissions(self, ticker: str) -> dict[str, object] | None:
        sym = ticker.upper()
        if sym in self._submissions_cache:
            return self._submissions_cache[sym]
        cik = self._cik(sym)
        if cik is None:
            return None
        data = self._edgar().fetch_submissions(cik)
        self._submissions_cache[sym] = data
        return data

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        submissions = self._submissions(ticker)
        if submissions is None:
            return None
        return parse_submissions_info(ticker, submissions)

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        sym = ticker.upper()
        cik = self._cik(sym)
        if cik is None:
            raise LookupError(f"{sym}: not in EDGAR's ticker table")
        parsed = parse_company_facts(sym, self._edgar().fetch_company_facts(cik))
        return FundamentalsBundle(
            info=self.lookup_company(sym),
            annual=dataclasses.replace(parsed, quarterly=[]),
            quarterly=dataclasses.replace(parsed, annual=[]),
            filings=parsed.filings,
        )

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        sym = ticker.upper()
        bars = self._prices().daily_prices(sym, since)
        if not bars:
            return bars
        newest_idx = max(range(len(bars)), key=lambda i: bars[i].date)
        newest = bars[newest_idx]
        if newest.close is not None and (date.today() - newest.date).days <= _FRESH_DAYS:
            cik = self._cik(sym)
            shares = self._edgar().shares_outstanding(cik) if cik is not None else None
            if shares is not None:
                bars[newest_idx] = dataclasses.replace(
                    newest, market_cap=newest.close * shares
                )
        return bars

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        if currency.upper() != "USD":
            log.warning("edgar_stooq.fx.unsupported", currency=currency)
        return []

    def latest_filing_date(self, ticker: str) -> date | None:
        submissions = self._submissions(ticker)
        if submissions is None:
            return None
        return latest_filing_date_from_submissions(submissions)
```

Note on `parse_company_facts`'s company row: it sets `"source": "sec_edgar"`. The importer (`universe.import_company`) overrides `source` with `provider.name` when building `_company_row`, so DB rows land as `edgar_stooq` — consistent with how `fmp` rows land today. Do not "fix" the parser.

- [ ] **Step 4: Extend the seam tests**

In `tests/unit/test_seam_enforcement.py`, add (mirroring the existing `_offenders` helper):

```python
def test_stooq_client_is_internal_to_its_adapters() -> None:
    assert _offenders(r"\bStooqClient\b", allowed={"stooq.py", "edgar_stooq.py"}) == []


def test_only_the_composition_root_names_the_free_stack_adapter() -> None:
    assert _offenders(r"\bEdgarStooqProvider\b", allowed={"edgar_stooq.py", "cli.py"}) == []
```

And extend `test_the_port_imports_no_concrete_adapter` to also reject `stooq` and `edgar_stooq` in `provider.py`'s imports (add them to both regex alternations).

- [ ] **Step 5: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_edgar_stooq_provider.py tests/unit/test_seam_enforcement.py -q && uv run pytest -q && uv run mypy src && uv run ruff check src tests`
Expected: all green. (`test_only_the_composition_root_names_the_free_stack_adapter` passes now and starts protecting Task 6's wiring.)

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/edgar_stooq.py tests/unit/test_edgar_stooq_provider.py tests/unit/test_seam_enforcement.py
git commit -m "feat(ingest): EdgarStooqProvider — the free-stack adapter behind the port"
```

---

### Task 6: Settings, composition root, doctor, CLI flag

**Files:**
- Modify: `src/bot/config.py`
- Modify: `src/bot/cli.py` (`_make_provider`, `doctor`, `refresh` flag)
- Modify: `.env.example`
- Modify/Create: tests — extend the existing doctor tests file and add `tests/unit/test_make_provider.py`

**Interfaces:**
- Consumes: `EdgarStooqProvider` (Task 5), `FmpProvider` (existing).
- Produces: `Settings.data_provider: Literal["edgar-stooq", "fmp"]` (default `"edgar-stooq"`); `Settings.fmp_api_key: str` (default `""`, no longer required); `_make_provider` returns the configured adapter or raises `typer.Exit(code=1)` with a clear message when `fmp` is selected without a key.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_make_provider.py`:

```python
"""The composition root selects the adapter from Settings.data_provider."""

from __future__ import annotations

import pytest
import typer

from bot.cli import _make_provider
from bot.config import Settings
from bot.ingest.edgar_stooq import EdgarStooqProvider  # noqa: F401 — seam: only cli names it
from bot.ingest.fmp import FmpProvider


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "sec_user_agent": "Test test@example.com",
        "_env_file": None,  # keep the developer's .env out of unit tests
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_default_provider_is_the_free_stack() -> None:
    settings = _settings()
    assert settings.data_provider == "edgar-stooq"
    provider = _make_provider(settings)
    assert provider.name == "edgar_stooq"


def test_fmp_selected_with_key_builds_fmp() -> None:
    provider = _make_provider(_settings(data_provider="fmp", fmp_api_key="k"))
    assert isinstance(provider, FmpProvider)


def test_fmp_selected_without_key_exits_with_guidance() -> None:
    with pytest.raises(typer.Exit):
        _make_provider(_settings(data_provider="fmp", fmp_api_key=""))
```

Note: this file names both concrete adapters, which is fine — the seam tests scan `src/`, not `tests/`. Confirm that by reading `_offenders` in `test_seam_enforcement.py`; if it scans tests too, add this file to its `allowed` sets.

Also update the doctor tests (the existing doctor test file — `40b3314` isolated it from a developer's `.env`): add one test asserting `doctor` exits 0 with `BOT_FMP_API_KEY` unset when `BOT_DATA_PROVIDER` is unset/`edgar-stooq`, and one asserting the FMP-key check still fires with `BOT_DATA_PROVIDER=fmp` and an empty key. Follow that file's existing invocation pattern (CliRunner + env patching) exactly.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_make_provider.py -q`
Expected: FAIL — `Settings` has no field `data_provider` / `fmp_api_key` is required.

- [ ] **Step 3: Implement `config.py`**

```python
    data_provider: Literal["edgar-stooq", "fmp"] = Field(
        default="edgar-stooq",
        description=(
            "Market data adapter: 'edgar-stooq' (free: SEC EDGAR fundamentals + Stooq EOD "
            "prices, US-only, ADR 0007) or 'fmp' (requires BOT_FMP_API_KEY)."
        ),
    )
    fmp_api_key: str = Field(
        default="",
        description="Financial Modeling Prep API key. Required only when BOT_DATA_PROVIDER=fmp.",
    )
```

(`Literal` from `typing`; keep field order — `fmp_api_key` stays where it was, dropping `...`.)

- [ ] **Step 4: Implement `_make_provider` and `doctor` in `cli.py`**

```python
def _make_provider(settings: Settings) -> MarketDataProvider:
    """The composition root: the ONLY place a concrete data provider is named.

    Swapping the data source = writing a new adapter in bot/ingest/ and
    adding a branch here (spec 2026-08-24; ADR 0007).
    """
    if settings.data_provider == "fmp":
        if not settings.fmp_api_key.strip():
            typer.echo(
                "BOT_DATA_PROVIDER=fmp but BOT_FMP_API_KEY is empty. "
                "Set the key, or switch to the free stack (BOT_DATA_PROVIDER=edgar-stooq).",
                err=True,
            )
            raise typer.Exit(code=1)
        return FmpProvider(api_key=settings.fmp_api_key)
    return EdgarStooqProvider(sec_user_agent=settings.sec_user_agent)
```

(Import `EdgarStooqProvider` from `bot.ingest.edgar_stooq` next to the existing `FmpProvider` import.)

In `doctor`, replace the unconditional FMP lines:

```python
    typer.echo(f"Data provider:    {settings.data_provider}")
    if settings.data_provider == "fmp":
        typer.echo(f"FMP API key:      {'set' if settings.fmp_api_key.strip() else 'MISSING'}")
        if not settings.fmp_api_key.strip():
            issues.append(
                "BOT_DATA_PROVIDER=fmp but the API key is empty (BOT_FMP_API_KEY) — "
                "refresh --fundamentals cannot work."
            )
```

In `refresh`, make `--fundamentals` the primary flag with `--fmp` as a compatibility alias — change only the option declaration, keeping the parameter name so no call sites move:

```python
    fmp: bool = typer.Option(
        False,
        "--fundamentals",
        "--fmp",
        help="Refresh universe fundamentals via the configured data provider.",
    ),
```

Update `.env.example`: add `# BOT_DATA_PROVIDER=edgar-stooq   # or: fmp (needs BOT_FMP_API_KEY)` and annotate the FMP key line as optional.

- [ ] **Step 5: Run the affected tests, then the full gate**

Run: `uv run pytest tests/unit/test_make_provider.py tests/unit/test_seam_enforcement.py -q && uv run pytest -q && uv run mypy src && uv run ruff check src tests`
Expected: all green. Any existing test that constructed `Settings` without an FMP key and expected a validation error now needs updating to the new contract (the key is optional; the check moved to `_make_provider`/`doctor`).

- [ ] **Step 6: Commit**

```bash
git add src/bot/config.py src/bot/cli.py .env.example tests/unit/test_make_provider.py tests/unit/test_cli_doctor.py
git commit -m "feat(cli): BOT_DATA_PROVIDER selects the adapter; free stack is the default"
```

---

### Task 7: End-to-end through the free stack (fixtures, no network)

The e2e test from the US-only plan (`3a8cc33`) proves the pipeline runs through the provider port with a fake. This task proves the same chain — `import_company` → `refresh_prices` → screen inputs present — through the **real** `EdgarStooqProvider` parsing code, with HTTP faked at the transport.

**Files:**
- Create: `tests/integration/test_e2e_edgar_stooq.py` (follow the existing e2e file's location convention — if the current e2e lives elsewhere, put this next to it)

**Interfaces:**
- Consumes: `EdgarStooqProvider` with injected transports (Task 5); `bot.ingest.universe.import_company`, `refresh_prices`; the fixtures from Tasks 1–3.

- [ ] **Step 1: Write the failing test**

```python
"""E2E: EDGAR+Stooq fundamentals and prices land in DuckDB through the port."""

from __future__ import annotations

from pathlib import Path

import duckdb
import httpx
import pytest

from bot.ingest.edgar_stooq import EdgarStooqProvider
from bot.ingest.universe import import_company, refresh_prices
from bot.storage.db import apply_schema, connect

# Reuse the handlers from the unit test — import them, do not copy.
from tests.unit.test_edgar_stooq_provider import _edgar_handler, _stooq_handler


@pytest.fixture()
def conn(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    c = connect(tmp_path / "test.duckdb")
    apply_schema(c)
    return c


def _provider() -> EdgarStooqProvider:
    return EdgarStooqProvider(
        sec_user_agent="Test test@example.com",
        sec_transport=httpx.MockTransport(_edgar_handler),
        stooq_transport=httpx.MockTransport(_stooq_handler),
    )


def test_import_company_lands_row_with_damodaran_industry(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    result = import_company(conn, ticker="AAPL", provider=_provider())
    assert result.status == "success"
    row = conn.execute(
        "SELECT name, industry, industry_damodaran, source FROM companies WHERE ticker='AAPL'"
    ).fetchone()
    assert row is not None
    name, industry, industry_damodaran, source = row
    assert name == "Apple Inc."
    assert industry == "Electronic Computers"
    assert industry_damodaran is not None  # Task 4's mapping resolved it
    assert source == "edgar_stooq"
    annual = conn.execute(
        "SELECT revenue FROM financials_annual WHERE ticker='AAPL'"
    ).fetchall()
    assert annual and annual[0][0] == pytest.approx(400000000000)


def test_refresh_prices_lands_stooq_bars(conn: duckdb.DuckDBPyConnection) -> None:
    import_company(conn, ticker="AAPL", provider=_provider())
    refresh_prices(conn, tickers=["AAPL"], provider=_provider())
    n = conn.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()
    assert n is not None and n[0] == 3
```

Adjust the two call signatures (`refresh_prices`, `connect`, `apply_schema` imports) to the real ones — read `src/bot/ingest/universe.py:494` and the existing e2e test for the exact parameters (e.g. `refresh_prices` may take `settings` or a `since` strategy); mirror the existing e2e's invocation style rather than inventing one.

- [ ] **Step 2: Run to verify it fails, then make it pass**

Run: `uv run pytest tests/integration/test_e2e_edgar_stooq.py -q`
Expected first: FAIL (import/signature mismatches you then fix in the test, per Step 1's note — the production code should need **no** changes; if it does, stop and re-read, something in Tasks 5–6 was wired wrong).
Then: PASS.

- [ ] **Step 3: Full gate + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests`

```bash
git add tests/integration/test_e2e_edgar_stooq.py
git commit -m "test(e2e): fundamentals and prices flow EDGAR+Stooq -> DuckDB through the port"
```

---

### Task 8: The real run, mapping completion, and documentation

Manual operation (the only networked step) plus the doc close-out CONTEXT.md demands.

**Files:**
- Create: `docs/adr/0007-free-data-stack-edgar-stooq.md`
- Modify: `src/bot/ingest/industry_mapping.csv` (fill unmapped SICs found by the real run)
- Modify: `CONTEXT.md` (External services section)
- Modify: `README.md` quickstart + `.env.example` if the run reveals gaps
- Modify: `docs/plano/estado.py` (re-audit touched items; bump `AUDITADO_EN`/`AUDITADO_EL`) and regenerate the planos

- [ ] **Step 1: Write ADR 0007**

`docs/adr/0007-free-data-stack-edgar-stooq.md`, following the structure of ADR 0004/0006:

```markdown
# 0007 — Free data stack: SEC EDGAR fundamentals + Stooq EOD prices

## Status

Accepted (2026-09-09). Implemented (<date>, EdgarStooqProvider in ingest/edgar_stooq.py).

## Context

The attested real run of 2026-09-02 showed the FMP free tier cannot feed the
S&P 500 universe (3/25 imported; symbol coverage, 5-period cap, hard 429s),
and the paid tiers start at ~$22/month for data that, for US companies, FMP
itself derives from EDGAR. The provider port (2026-08-24) made a second real
adapter cheap.

## Decision

Under the US-only scope the default data provider is a composite of two free
sources: SEC EDGAR (company facts for statements, submissions for profile/SIC/
latest filing date, dei shares for market cap) and Stooq (EOD closes).
Industry mapping runs SIC description -> Damodaran industry through the
existing provider-keyed industry_mapping.csv. FMP remains available behind
BOT_DATA_PROVIDER=fmp for the M2 global reopening — EDGAR is US-only by
nature, so this decision is scoped exactly like ADR 0005's deferral.

## Consequences

- $0/month; no API key beyond the SEC User-Agent already required.
- ipo_date is not available (EDGAR carries none): age_years degrades to
  unknown for story-type classification; acceptable, logged, revisit at M2.
- Stooq's undocumented daily hit limit is handled by the same defer/resume
  machinery as FMP's 429 (StooqRateLimitError).
- XBRL concept variance across filers may leave more None gaps than FMP's
  standardized statements; the coverage gate (ADR 0006) makes those visible
  instead of silent.
- market_cap = close x latest dei shares; for dual-class companies this uses
  the primary listing's share count and may undercount total cap. Known,
  logged here, tolerable for the size gate's purpose.
```

- [ ] **Step 2: The real run (manual, networked)**

From a shell with `.env` carrying only `BOT_SEC_USER_AGENT` (no FMP key, no `BOT_DATA_PROVIDER`):

```bash
uv run bot doctor
uv run bot refresh --damodaran
uv run bot refresh --fundamentals --limit 25
uv run bot refresh --prices --limit 25
uv run bot screen --preset damodaran_value --top 10
uv run bot analyze --from-screen
```

Then iterate on mapping coverage:

```bash
uv run bot refresh --fundamentals 2>&1 | grep industry_mapping.unmapped
```

For every distinct unmapped SIC description, add a `sec_edgar` CSV row (right-hand label must satisfy `test_sec_edgar_damodaran_labels_are_already_known_labels`; if a genuinely new Damodaran label is needed, verify it against `SELECT DISTINCT industry FROM damodaran_industry` in `bot.duckdb` and extend that test's rationale comment). Repeat `refresh --fundamentals` (deferred/resume handles Stooq/EDGAR limits across days if needed) until the unmapped count is zero across the 503 tickers. Record the run's numbers (imported/failed/deferred, screened, candidates, excluded-by-coverage) in this plan under a "Real run" heading, exactly like the previous plan's "Corrida real" section. Breakage found here gets fixed as `fix(ingest): ...` commits with tests.

- [ ] **Step 3: Docs**

- `CONTEXT.md` External services: add Stooq; note FMP as optional (`BOT_DATA_PROVIDER=fmp`, M2); point to ADR 0007.
- `README.md` quickstart: the free stack needs only `BOT_SEC_USER_AGENT`.
- `docs/plano/estado.py`: re-audit `universo`, `sec-import`, `cli-falta`, `doctor`, `datos-reales` and affected `BRECHAS` **against the code at HEAD**; add the new adapter to the inventory; update `AUDITADO_EN`/`AUDITADO_EL`; regenerate per `docs/plano/README.md` and confirm `build.py` doesn't protest.
- ADR 0007 Status line gets its "Implemented" date.

- [ ] **Step 4: Final gate + commit**

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests`

```bash
git add docs/adr/0007-free-data-stack-edgar-stooq.md CONTEXT.md README.md docs/plano/ src/bot/ingest/industry_mapping.csv docs/superpowers/plans/2026-09-09-free-data-stack-edgar-stooq.md
git commit -m "docs: ADR 0007 free data stack implemented; real run attested; estado re-audited"
```

---

## Self-Review

- **Coverage of the goal:** replace paid FMP end to end — prices (T1), company info + filing dates (T2), statement parity (T3), industry mapping so the coverage gate doesn't empty the universe (T4), the port adapter (T5), selection + operability (T6), regression proof (T7), real-world attestation + decision record (T8). FMP path preserved untouched behind the same port.
- **Type consistency:** `EdgarStooqProvider.__init__(sec_user_agent, timeout, sec_transport, stooq_transport)` is used identically in T5 tests, T6 `_make_provider` (defaults only), and T7. `SecEdgarClient` gains `transport` in T2 and it's what T3/T5/T7 pass. `StooqClient(timeout, transport)` matches T1 and T5. `parse_submissions_info` / `latest_filing_date_from_submissions` / `shares_outstanding` names match across T2/T3/T5. `data_provider` literal `"edgar-stooq"` (setting) vs `name == "edgar_stooq"` (provider id / DB source) is deliberate — settings use kebab, DB sources use snake, mirroring `fmp_universe`-style ids; both spellings are asserted in tests so a mix-up fails fast.
- **Known deltas the executor must resolve in place (flagged in their tasks):** the exact `coerce_date` import path (T1/T2), the exact row-finalization point in `_collect_period_rows` (T3), the exact fmp-side Damodaran label spellings (T4), `refresh_prices`'s real signature and the e2e file location (T7), and the doctor-test file's invocation pattern (T6). Each is a read-the-neighboring-code instruction, not a design gap.
- **Dependency order:** T2 before T4 (SIC-description convention), T1–T4 before T5, T5 before T6, T6 before T7, everything before T8. Seam tests extended in T5 so T6's wiring lands already-policed.
