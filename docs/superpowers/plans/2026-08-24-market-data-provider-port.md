# Market-Data Provider Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put one `MarketDataProvider` seam between the ingest orchestration and FMP so the data source is swappable by writing a new adapter plus one wiring line, with provider-specific parsing sealed inside each adapter.

**Architecture:** A Protocol + canonical records in a new `src/bot/ingest/provider.py`; `fmp.py` becomes the sole FMP adapter (`FmpProvider`); `universe.py` and `utils/fx.py` orchestrate against the Protocol only; `cli.py` holds the single composition function `_make_provider`. A `FakeProvider` in tests is the second adapter that keeps the seam honest. Behaviour is refactor-neutral: rate-limit deferral, skip-probe, failure-rate, and merge-upsert semantics all stay identical.

**Tech Stack:** Python 3.12+ (Protocol, dataclasses), DuckDB, pytest, uv, ruff, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-08-24-market-data-provider-port-design.md` — read it first; conflicts resolve against it.

## Global Constraints

- `uv run ruff check .`, `uv run mypy src` (strict), and full `uv run pytest` green after every task; baseline 722 tests — never fewer.
- Conventional Commits; trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- After Task 6, **nothing outside `src/bot/ingest/fmp.py` imports `FmpClient`** (`bot.ingest.ibkr`, `sec_edgar`, `damodaran` are out of scope and unchanged).
- No runtime provider selection; no second live provider; `refresh_log` source labels keep their current values (`fmp`, `fmp_universe`, `fmp_prices_universe`, `fmp_fx`) by deriving them from `provider.name == "fmp"`.
- Existing behaviour is preserved: HTTP 429 → clean stop, remaining tickers `deferred`; probe errors non-fatal; per-ticker failures isolated; company merge-upsert semantics untouched.

---

### Task 1: The port module — Protocol, canonical records, neutral error

**Files:**
- Create: `src/bot/ingest/provider.py`
- Modify: `src/bot/ingest/fmp.py` (move `CompanyInfo` out; re-import; re-base `FmpRateLimitError`)
- Test: `tests/unit/test_provider_port.py` (new)

**Interfaces:**
- Consumes: `ParsedCompanyData` (currently defined in `bot.ingest.sec_edgar`, imported by `fmp.py` — check `fmp.py:28` — it stays where it is; `provider.py` imports it from there).
- Produces (later tasks rely on these exact names): `MarketDataProvider` (Protocol, `@runtime_checkable`), `CompanyInfo`, `FundamentalsBundle`, `PriceBar`, `FxRate`, `ProviderRateLimitError` — all importable from `bot.ingest.provider`. `FmpRateLimitError` (still in `fmp.py`) subclasses `ProviderRateLimitError`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_provider_port.py`:

```python
"""The provider port: canonical records and the neutral rate-limit error."""

from __future__ import annotations

from datetime import date

from bot.ingest.fmp import FmpRateLimitError
from bot.ingest.provider import (
    CompanyInfo,
    FxRate,
    MarketDataProvider,
    PriceBar,
    ProviderRateLimitError,
)


def test_fmp_rate_limit_error_is_a_provider_rate_limit_error() -> None:
    # Orchestration will catch only the neutral error; FMP's must satisfy it.
    assert issubclass(FmpRateLimitError, ProviderRateLimitError)


def test_price_bar_and_fx_rate_are_frozen_records() -> None:
    bar = PriceBar(date=date(2026, 1, 2), close=10.0, volume=1000.0, market_cap=None)
    fx = FxRate(date=date(2026, 1, 2), rate_to_usd=1.08)
    assert bar.close == 10.0
    assert fx.rate_to_usd == 1.08


def test_company_info_still_importable_from_fmp() -> None:
    # Back-compat: existing imports of CompanyInfo from bot.ingest.fmp keep working.
    from bot.ingest.fmp import CompanyInfo as FmpCompanyInfo

    assert FmpCompanyInfo is CompanyInfo


def test_protocol_is_runtime_checkable() -> None:
    class NotAProvider:
        pass

    assert not isinstance(NotAProvider(), MarketDataProvider)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_provider_port.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.ingest.provider'`.

- [ ] **Step 3: Create the port module**

Create `src/bot/ingest/provider.py`. `CompanyInfo` moves here **verbatim** from `fmp.py` (currently `fmp.py:42-55` — cut the whole `@dataclass(frozen=True) class CompanyInfo` block, docstring reworded to drop "FMP"):

```python
"""The market-data provider port (spec 2026-08-24).

One seam between the ingest orchestration and any concrete data source.
Adapters (bot.ingest.fmp today, a fake in tests) implement
:class:`MarketDataProvider` and translate their source's wire format into the
canonical records below. Orchestration and the CLI may import this module and
never a concrete adapter's client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable

from bot.ingest.sec_edgar import ParsedCompanyData


@dataclass(frozen=True)
class CompanyInfo:
    """Normalized basic company info from a provider's profile lookup."""

    ticker: str
    name: str
    exchange: str | None
    exchange_short_name: str | None
    country: str | None
    currency: str | None
    sector: str | None
    industry: str | None
    is_actively_trading: bool
    ipo_date: date | None = None


@dataclass(frozen=True)
class FundamentalsBundle:
    """Everything the company importer needs for one ticker, in one fetch."""

    info: CompanyInfo | None
    annual: ParsedCompanyData
    quarterly: ParsedCompanyData
    filings: list[dict[str, Any]]  # filings_log row shape (upsert_filings)


@dataclass(frozen=True)
class PriceBar:
    """One daily EOD price row (prices_daily shape, sans ticker/currency)."""

    date: date
    close: float | None
    volume: float | None
    market_cap: float | None


@dataclass(frozen=True)
class FxRate:
    """One daily FX rate to USD (currencies table shape, sans currency)."""

    date: date
    rate_to_usd: float


class ProviderRateLimitError(RuntimeError):
    """The provider's quota is exhausted: stop the run cleanly, defer the rest.

    Not a per-ticker failure. Concrete adapters raise a subclass (e.g.
    FmpRateLimitError); orchestration catches only this base class.
    """


@runtime_checkable
class MarketDataProvider(Protocol):
    """Everything the pipeline may know about a fundamentals+prices source."""

    @property
    def name(self) -> str:
        """Short id ("fmp") — prefixes refresh_log sources, fills company.source."""
        ...

    def lookup_company(self, ticker: str) -> CompanyInfo | None: ...

    def fundamentals(self, ticker: str) -> FundamentalsBundle: ...

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]: ...

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]: ...

    def latest_filing_date(self, ticker: str) -> date | None: ...

    def close(self) -> None: ...
```

NOTE: if `ParsedCompanyData` is defined in `fmp.py` itself rather than `sec_edgar.py` (verify against `fmp.py:28-34`'s import block), import it from wherever it actually lives — do not move it in this task.

- [ ] **Step 4: Re-point `fmp.py`**

In `src/bot/ingest/fmp.py`: delete the moved `CompanyInfo` class; add `from bot.ingest.provider import CompanyInfo, ProviderRateLimitError` (keep `CompanyInfo` exported — existing code does `from bot.ingest.fmp import CompanyInfo`); change `class FmpRateLimitError(RuntimeError):` to `class FmpRateLimitError(ProviderRateLimitError):` (docstring unchanged).

- [ ] **Step 5: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_provider_port.py -v` → PASS.
Run: `uv run pytest && uv run ruff check . && uv run mypy src` → all green (726 tests now).

- [ ] **Step 6: Commit**

```bash
git add src/bot/ingest/provider.py src/bot/ingest/fmp.py tests/unit/test_provider_port.py
git commit -m "feat(ingest): the market-data provider port — protocol, canonical records, neutral rate-limit error"
```

---

### Task 2: `FmpProvider` — the FMP adapter behind the port

**Files:**
- Modify: `src/bot/ingest/fmp.py` (add `FmpProvider`; keep `FmpClient` and parsers as internals)
- Test: `tests/unit/test_fmp_provider.py` (new)

**Interfaces:**
- Consumes: `MarketDataProvider`, `FundamentalsBundle`, `PriceBar`, `FxRate`, `CompanyInfo` from `bot.ingest.provider` (Task 1); existing `FmpClient`, `parse_fmp_fundamentals`, `_collect_fmp_filings`, and `universe.py`'s `_latest_filing_from_statements` logic.
- Produces: `class FmpProvider` in `bot.ingest.fmp` with `__init__(self, api_key: str, timeout: float = 30.0)`, context-manager support (`__enter__`/`__exit__` calling `close()`), satisfying the Protocol under mypy strict. Later tasks construct it ONLY in `cli.py` and tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_fmp_provider.py`. Build the provider over a stubbed `FmpClient` (patch `FmpProvider._client`) — no HTTP:

```python
"""FmpProvider: FMP JSON in, canonical records out."""

from __future__ import annotations

from datetime import date
from typing import Any

from bot.ingest.fmp import FmpProvider
from bot.ingest.provider import FundamentalsBundle, FxRate, MarketDataProvider, PriceBar


class _StubClient:
    """Stands in for FmpClient; returns canned endpoint payloads."""

    def __init__(self) -> None:
        self.closed = False

    def historical_prices(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        return [{"date": "2026-01-02", "close": 10.5, "volume": 900.0, "market_cap": None}]

    def historical_fx(
        self, currency: str, *, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        return [{"date": "2026-01-02", "rate_to_usd": 1.08}]

    def income_statement(self, ticker: str, *, period: str) -> list[dict[str, Any]]:
        return []

    def balance_sheet(self, ticker: str, *, period: str) -> list[dict[str, Any]]:
        return []

    def cash_flow(self, ticker: str, *, period: str) -> list[dict[str, Any]]:
        return []

    def lookup_company(self, ticker: str) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _provider() -> FmpProvider:
    p = FmpProvider(api_key="test-key")
    p._client = _StubClient()  # type: ignore[assignment]
    return p


def test_fmp_provider_satisfies_the_protocol() -> None:
    p: MarketDataProvider = _provider()  # mypy enforces structural conformance
    assert p.name == "fmp"
    assert isinstance(p, MarketDataProvider)


def test_daily_prices_become_price_bars() -> None:
    bars = _provider().daily_prices("ACME", since=None)
    assert bars == [
        PriceBar(date=date(2026, 1, 2), close=10.5, volume=900.0, market_cap=None)
    ]


def test_fx_rates_become_fx_records() -> None:
    rates = _provider().fx_rates("EUR", since=None)
    assert rates == [FxRate(date=date(2026, 1, 2), rate_to_usd=1.08)]


def test_fundamentals_returns_a_bundle_even_when_empty() -> None:
    bundle = _provider().fundamentals("ACME")
    assert isinstance(bundle, FundamentalsBundle)
    assert bundle.info is None
    assert bundle.annual.annual == []
    assert bundle.filings == []


def test_close_closes_the_underlying_client() -> None:
    p = _provider()
    p.close()
    assert p._client.closed  # type: ignore[union-attr]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_fmp_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'FmpProvider'`.

- [ ] **Step 3: Implement `FmpProvider`**

Append to `src/bot/ingest/fmp.py` (after `FmpClient` and the parsers). It owns one lazily-created `FmpClient` for its lifetime — this replaces `universe.py`'s `_shared_fmp_client` pooling:

```python
class FmpProvider:
    """The FMP adapter behind :class:`bot.ingest.provider.MarketDataProvider`.

    One instance owns one :class:`FmpClient` (one connection pool) for its
    lifetime — construct per bulk run, close when done (context manager).
    Everything FMP-specific — endpoints, JSON shapes, parsing — stays inside.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: FmpClient | None = None

    @property
    def name(self) -> str:
        return "fmp"

    def _fmp(self) -> FmpClient:
        if self._client is None:
            self._client = FmpClient(api_key=self._api_key, timeout=self._timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> FmpProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        return self._fmp().lookup_company(ticker)

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        sym = ticker.upper()
        fmp = self._fmp()
        info = fmp.lookup_company(sym)
        inc_a = fmp.income_statement(sym, period="annual")
        bal_a = fmp.balance_sheet(sym, period="annual")
        cf_a = fmp.cash_flow(sym, period="annual")
        inc_q = fmp.income_statement(sym, period="quarter")
        bal_q = fmp.balance_sheet(sym, period="quarter")
        cf_q = fmp.cash_flow(sym, period="quarter")
        return FundamentalsBundle(
            info=info,
            annual=parse_fmp_fundamentals(sym, inc_a, bal_a, cf_a),
            quarterly=parse_fmp_fundamentals(sym, inc_q, bal_q, cf_q),
            filings=_collect_fmp_filings(sym, inc_a, inc_q),
        )

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        rows = self._fmp().historical_prices(ticker.upper(), start=since, end=None)
        return [
            PriceBar(
                date=_as_date(r["date"]),
                close=_float_or_none(r.get("close")),
                volume=_float_or_none(r.get("volume")),
                market_cap=_float_or_none(r.get("market_cap")),
            )
            for r in rows
        ]

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        rows = self._fmp().historical_fx(currency.upper(), start=since, end=None)
        return [
            FxRate(date=_as_date(r["date"]), rate_to_usd=float(r["rate_to_usd"]))
            for r in rows
        ]

    def latest_filing_date(self, ticker: str) -> date | None:
        sym = ticker.upper()
        rows = self._fmp().income_statement(sym, period="annual")
        return _latest_filing_from_rows(rows)


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
```

Supporting moves in this step:

- `_latest_filing_from_rows`: move the body of `universe.py`'s `_latest_filing_from_statements` (`universe.py:195`) into `fmp.py` under this name (same logic; it reads FMP statement rows, so it is adapter-internal). Leave the original in `universe.py` untouched for now — Task 4 deletes it.
- Check `FmpClient.historical_prices` / `historical_fx` signatures (`fmp.py:140-224`) and match the keyword names exactly (`start=`/`end=`); if `historical_prices` requires an `end` date rather than accepting `None`, pass what today's `import_prices_from_fmp` passes — mirror the existing call, don't invent parameters.
- Check what probe endpoint `make_fmp_latest_filing_probe` (`universe.py:171`) actually calls; `latest_filing_date` must hit the same endpoint with the same params so skip behaviour is unchanged. Mirror it exactly.

- [ ] **Step 4: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_fmp_provider.py -v` → PASS.
Run: `uv run pytest && uv run ruff check . && uv run mypy src` → green.

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/fmp.py tests/unit/test_fmp_provider.py
git commit -m "feat(ingest): FmpProvider adapter — FMP client and parsing sealed behind the port"
```

---

### Task 3: `FakeProvider` — the second adapter, for tests

**Files:**
- Create: `tests/fake_provider.py`
- Test: `tests/unit/test_fake_provider.py` (new)

**Interfaces:**
- Consumes: everything `bot.ingest.provider` exports (Task 1).
- Produces: `class FakeProvider` importable as `from tests.fake_provider import FakeProvider`. Constructor takes keyword-only dicts keyed by ticker/currency: `companies: dict[str, CompanyInfo]`, `bundles: dict[str, FundamentalsBundle]`, `prices: dict[str, list[PriceBar]]`, `fx: dict[str, list[FxRate]]`, `filing_dates: dict[str, date]`, plus `fail_with: dict[str, Exception]` (raise per-ticker) and `rate_limit_after: int | None` (raise `ProviderRateLimitError` after N `fundamentals` calls — for deferral tests). Records every call in `self.calls: list[tuple[str, str]]` (method, arg).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_fake_provider.py`:

```python
"""The fake provider is a real adapter: it must satisfy the same Protocol."""

from __future__ import annotations

import pytest

from bot.ingest.provider import MarketDataProvider, ProviderRateLimitError
from tests.fake_provider import FakeProvider


def test_fake_satisfies_the_protocol() -> None:
    p: MarketDataProvider = FakeProvider()  # mypy checks structure
    assert isinstance(p, MarketDataProvider)
    assert p.name == "fake"
    assert p.lookup_company("ACME") is None
    assert p.daily_prices("ACME", since=None) == []
    assert p.fx_rates("EUR", since=None) == []
    assert p.latest_filing_date("ACME") is None
    p.close()


def test_rate_limit_after_fires_on_the_nth_fundamentals_call() -> None:
    p = FakeProvider(rate_limit_after=1)
    p.fundamentals("AAA")  # first call OK (empty bundle)
    with pytest.raises(ProviderRateLimitError):
        p.fundamentals("BBB")


def test_fail_with_raises_for_the_configured_ticker_only() -> None:
    p = FakeProvider(fail_with={"BAD": RuntimeError("boom")})
    p.fundamentals("GOOD")
    with pytest.raises(RuntimeError, match="boom"):
        p.fundamentals("BAD")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_fake_provider.py -v`
Expected: FAIL — no module `tests.fake_provider`.

- [ ] **Step 3: Implement `FakeProvider`**

Create `tests/fake_provider.py`:

```python
"""In-memory MarketDataProvider adapter for tests — the seam's second adapter."""

from __future__ import annotations

from datetime import date

from bot.ingest.provider import (
    CompanyInfo,
    FundamentalsBundle,
    FxRate,
    PriceBar,
    ProviderRateLimitError,
)
from bot.ingest.sec_edgar import ParsedCompanyData


def _empty_parsed(ticker: str) -> ParsedCompanyData:
    return ParsedCompanyData(
        company={"ticker": ticker.upper(), "name": ticker.upper(), "currency": None,
                 "source": "fake", "status": "active"},
        annual=[],
        quarterly=[],
    )


class FakeProvider:
    """Serves canned records; records calls; can fail or rate-limit on demand."""

    def __init__(
        self,
        *,
        companies: dict[str, CompanyInfo] | None = None,
        bundles: dict[str, FundamentalsBundle] | None = None,
        prices: dict[str, list[PriceBar]] | None = None,
        fx: dict[str, list[FxRate]] | None = None,
        filing_dates: dict[str, date] | None = None,
        fail_with: dict[str, Exception] | None = None,
        rate_limit_after: int | None = None,
    ) -> None:
        self._companies = {k.upper(): v for k, v in (companies or {}).items()}
        self._bundles = {k.upper(): v for k, v in (bundles or {}).items()}
        self._prices = {k.upper(): v for k, v in (prices or {}).items()}
        self._fx = {k.upper(): v for k, v in (fx or {}).items()}
        self._filing_dates = {k.upper(): v for k, v in (filing_dates or {}).items()}
        self._fail_with = {k.upper(): v for k, v in (fail_with or {}).items()}
        self._rate_limit_after = rate_limit_after
        self._fundamentals_calls = 0
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    @property
    def name(self) -> str:
        return "fake"

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        self.calls.append(("lookup_company", ticker.upper()))
        return self._companies.get(ticker.upper())

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        sym = ticker.upper()
        self.calls.append(("fundamentals", sym))
        if self._rate_limit_after is not None and self._fundamentals_calls >= self._rate_limit_after:
            raise ProviderRateLimitError("fake quota exhausted")
        self._fundamentals_calls += 1
        if sym in self._fail_with:
            raise self._fail_with[sym]
        if sym in self._bundles:
            return self._bundles[sym]
        return FundamentalsBundle(
            info=self._companies.get(sym),
            annual=_empty_parsed(sym),
            quarterly=_empty_parsed(sym),
            filings=[],
        )

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        self.calls.append(("daily_prices", ticker.upper()))
        return self._prices.get(ticker.upper(), [])

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        self.calls.append(("fx_rates", currency.upper()))
        return self._fx.get(currency.upper(), [])

    def latest_filing_date(self, ticker: str) -> date | None:
        self.calls.append(("latest_filing_date", ticker.upper()))
        return self._filing_dates.get(ticker.upper())

    def close(self) -> None:
        self.closed = True
```

NOTE: match `ParsedCompanyData`'s real constructor (check its definition — it may not have exactly `company/annual/quarterly` fields; mirror what `parse_fmp_fundamentals` returns at `fmp.py:432`). If `tests/` is not a package (no `__init__.py`), import via the existing pattern other tests use for shared helpers (check `tests/conftest.py` — add the helper there if that's the convention).

- [ ] **Step 4: Run tests, then the full gate**

Run: `uv run pytest tests/unit/test_fake_provider.py -v` → PASS; then the full gate → green.

- [ ] **Step 5: Commit**

```bash
git add tests/fake_provider.py tests/unit/test_fake_provider.py
git commit -m "test(ingest): FakeProvider — the port's second adapter"
```

---

### Task 4: Neutral company importer and `refresh_universe`

**Files:**
- Modify: `src/bot/ingest/universe.py` (rewrite orchestration against the port), `src/bot/ingest/fmp.py` (retire `import_company_from_fmp`'s fetch half), `src/bot/cli.py` (call-site rename only — full composition root lands in Task 6)
- Test: `tests/unit/test_universe_refresh.py` and wherever `refresh_universe_from_fmp` / `import_company_from_fmp` / `make_fmp_latest_filing_probe` appear (run `grep -rn "refresh_universe_from_fmp\|import_company_from_fmp\|make_fmp_latest_filing_probe" tests/` first and migrate every hit)

**Interfaces:**
- Consumes: `MarketDataProvider`, `FundamentalsBundle`, `ProviderRateLimitError` (Task 1); `FmpProvider` (Task 2); `FakeProvider` (Task 3).
- Produces (Task 6 relies on these): in `bot.ingest.universe` —
  `import_company(conn, *, ticker: str, provider: MarketDataProvider, mapping: IndustryMapping | None = None, mapping_path: Path | None = None) -> IngestResult` and
  `refresh_universe(conn, *, provider: MarketDataProvider, tickers: list[str], progress_every: int = DEFAULT_PROGRESS_EVERY, mapping_path: Path | None = None) -> UniverseRefreshResult`.
  Deleted: `refresh_universe_from_fmp`, `make_fmp_latest_filing_probe`, `_latest_filing_from_statements`, `_shared_fmp_client`, the `importer`/`latest_filing_probe` injection params (the provider IS the injection point), and `fmp.py`'s `import_company_from_fmp`.

- [ ] **Step 1: Migrate the tests first (they define the contract)**

In `tests/unit/test_universe_refresh.py`, replace every injected `importer=` / `latest_filing_probe=` stub with a `FakeProvider`. The pattern for each existing behaviour test:

```python
from tests.fake_provider import FakeProvider
from bot.ingest.universe import refresh_universe

def test_rate_limit_defers_the_rest(conn: duckdb.DuckDBPyConnection) -> None:
    provider = FakeProvider(rate_limit_after=1)
    result = refresh_universe(conn, provider=provider, tickers=["AAA", "BBB", "CCC"])
    statuses = {o.ticker: o.status for o in result.outcomes}
    assert statuses["BBB"] == "deferred" and statuses["CCC"] == "deferred"
```

Keep every existing assertion's meaning: skip-when-filing-unchanged (use `filing_dates=` and pre-seeded `filings_log` rows), probe-error-falls-through (a `FakeProvider` subclass whose `latest_filing_date` raises), per-ticker failure isolation (`fail_with=`), failure-rate status resolution, `refresh_log` summary row (`source == "fmp_universe"` becomes `f"{provider.name}_universe"` — assert `"fake_universe"`). Do not delete a behaviour test because migration is awkward — rewrite it.

- [ ] **Step 2: Run to verify the migrated tests fail**

Run: `uv run pytest tests/unit/test_universe_refresh.py -v`
Expected: FAIL — `ImportError: cannot import name 'refresh_universe'`.

- [ ] **Step 3: Rewrite the orchestration**

In `src/bot/ingest/universe.py`:

`import_company` — move `import_company_from_fmp`'s body here (from `fmp.py:780`), fetching through the port. The DB half (upserts, `refresh_run`, transaction, `_company_row`, industry mapping) is unchanged — only the fetch half changes:

```python
def import_company(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    provider: MarketDataProvider,
    mapping: IndustryMapping | None = None,
    mapping_path: Path | None = None,
) -> IngestResult:
    """Fetch + upsert one ticker's fundamentals through the provider port."""
    sym = ticker.upper()
    with refresh_run(
        conn,
        source=provider.name,
        log=log,
        error_event="ingest.import.failed",
        log_fail_event="ingest.refresh_log_insert_failed",
    ) as run:
        run.details = {"ticker": sym}
        bundle = provider.fundamentals(sym)
        currency = (
            bundle.annual.company.get("currency")
            or bundle.quarterly.company.get("currency")
        )
        resolved_mapping = (
            mapping
            if mapping is not None
            else load_industry_mapping(resolve_mapping_path(mapping_path))
        )
        company = _company_row(sym, bundle.info, currency, mapping=resolved_mapping)
        with transaction(conn):
            upsert_company(conn, company)
            annual = upsert_financials_annual(conn, bundle.annual.annual)
            quarterly = upsert_financials_quarterly(conn, bundle.quarterly.quarterly)
            filings = upsert_filings(conn, bundle.filings)
        run.rows_affected = 1 + annual + quarterly + filings
        run.details = {"ticker": sym, "annual": annual, "quarterly": quarterly,
                       "filings": filings, "currency": currency}
    assert run.result is not None
    return run.result
```

Moves this implies: `_company_row` and `_collect_fmp_filings`'s consumer split — `_company_row` moves from `fmp.py` to `universe.py` if it is provider-neutral (it consumes `CompanyInfo` + mapping; check its body — if it hard-codes `"source": "fmp"`, take the source from `provider.name` via a parameter). `_collect_fmp_filings` stays in `fmp.py` (adapter-internal, feeds `FundamentalsBundle.filings`).

`refresh_universe` — replace `refresh_universe_from_fmp`:

```python
def refresh_universe(
    conn: duckdb.DuckDBPyConnection,
    *,
    provider: MarketDataProvider,
    tickers: list[str],
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    mapping_path: Path | None = None,
) -> UniverseRefreshResult:
    """Bulk-import ``tickers`` through the provider port, skipping unchanged ones."""
    mapping = load_industry_mapping(resolve_mapping_path(mapping_path))
    return _run_bulk_refresh(
        conn,
        items=tickers,
        process=lambda ticker: _refresh_one(
            conn, ticker=ticker, provider=provider, mapping=mapping
        ),
        source=f"{provider.name}_universe",
        label="universe",
        progress_every=progress_every,
    )
```

`_refresh_one` — same skip/fail semantics, port-shaped: probe via `provider.latest_filing_date(sym)` (probe exceptions other than `ProviderRateLimitError` are non-fatal: log and fall through to the import, exactly as today — check the current `_refresh_one` and `_should_skip` bodies and preserve them); import via `import_company(conn, ticker=sym, provider=provider, mapping=mapping)`. Every `except FmpRateLimitError: raise` in this module becomes `except ProviderRateLimitError: raise`. `_run_bulk_refresh` keeps its 429 clean-stop loop but catches `ProviderRateLimitError`.

Delete: `refresh_universe_from_fmp`, `make_fmp_latest_filing_probe`, `_latest_filing_from_statements`, `_shared_fmp_client`, the `Importer`/`LatestFilingProbe` type aliases if now unused, and `fmp.py`'s `import_company_from_fmp`. In `cli.py`, minimally patch the two call sites (`cli.py:182`, import at `cli.py:20-22`) to `refresh_universe(conn, provider=FmpProvider(api_key=settings.fmp_api_key), tickers=...)` with a `with ... as provider:` block so the client closes — Task 6 centralizes this.

- [ ] **Step 4: Run the migrated tests, then the full gate**

Run: `uv run pytest tests/unit/test_universe_refresh.py -v` → PASS.
Run: `uv run pytest && uv run ruff check . && uv run mypy src` → green. E2E and CLI tests that stubbed the old names must be migrated in this step too (the grep from **Files** is the checklist).

- [ ] **Step 5: Commit**

```bash
git add -A src/bot tests
git commit -m "refactor(ingest): universe refresh and company import orchestrate against the provider port"
```

---

### Task 5: Prices and FX through the port

**Files:**
- Modify: `src/bot/ingest/universe.py` (`refresh_prices_from_fmp` → `refresh_prices`, `refresh_fx_from_fmp` → `refresh_fx`), `src/bot/ingest/fmp.py` (move `upsert_prices_daily` + `_max_price_date` out; retire `import_prices_from_fmp`), `src/bot/utils/fx.py` (`import_fx_rates` takes a provider; drop the `FmpClient` import; `upsert_fx_rates` consumes `FxRate`), `src/bot/cli.py` (call sites at `cli.py:210` and `cli.py:216-219`)
- Test: every test touching `refresh_prices_from_fmp`, `import_prices_from_fmp`, `refresh_fx_from_fmp`, `import_fx_rates`, `upsert_prices_daily`, `upsert_fx_rates` (grep first, migrate all)

**Interfaces:**
- Consumes: `PriceBar`, `FxRate`, `MarketDataProvider`, `ProviderRateLimitError` (Task 1); `FakeProvider(prices=..., fx=...)` (Task 3).
- Produces (Task 6 relies on these): in `bot.ingest.universe` —
  `refresh_prices(conn, *, provider: MarketDataProvider, tickers: list[str], since_date: date | None = None, progress_every: int = DEFAULT_PROGRESS_EVERY) -> UniverseRefreshResult` and
  `refresh_fx(conn, *, provider: MarketDataProvider) -> IngestResult` (same return type `refresh_fx_from_fmp` has today — check `universe.py:478` and keep it);
  in `bot.utils.fx` — `import_fx_rates(conn, *, provider: MarketDataProvider, currency: str, start: date | None = None, end: date | None = None) -> IngestResult`;
  relocated `upsert_prices_daily(conn, *, ticker: str, bars: list[PriceBar], currency: str | None = None, source: str = "fmp") -> int` living in `bot.ingest.universe`, and `upsert_fx_rates(conn, *, currency: str, rates: list[FxRate], source: str = "fmp") -> int` in `bot.utils.fx`.

- [ ] **Step 1: Migrate the tests first**

Same discipline as Task 4. Representative shapes:

```python
def test_refresh_prices_writes_bars_through_the_port(conn) -> None:
    _seed_company(conn, "ACME", currency="USD")
    provider = FakeProvider(
        prices={"ACME": [PriceBar(date=date(2026, 1, 2), close=10.5, volume=900.0, market_cap=None)]}
    )
    result = refresh_prices(conn, provider=provider, tickers=["ACME"])
    row = conn.execute(
        "SELECT close, currency FROM prices_daily WHERE ticker = 'ACME'"
    ).fetchone()
    assert row == (10.5, "USD")

def test_import_fx_rates_writes_rates_through_the_port(conn) -> None:
    provider = FakeProvider(fx={"EUR": [FxRate(date=date(2026, 1, 2), rate_to_usd=1.08)]})
    result = import_fx_rates(conn, provider=provider, currency="EUR")
    assert result.is_success()
    assert conn.execute("SELECT rate_to_usd FROM currencies WHERE currency='EUR'").fetchone() == (1.08,)
```

Preserve the meaning of every existing incremental-`since` test: `refresh_prices` still derives each ticker's `since` from `_max_price_date` (moved alongside `upsert_prices_daily`) when `since_date` is None — assert via `provider.calls` that `daily_prices` was called and rows were written incrementally.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit -k "prices or fx" -v`
Expected: FAIL — import errors on the new names.

- [ ] **Step 3: Implement**

- Move `upsert_prices_daily` and `_max_price_date` from `fmp.py` (lines ~564-610) into `universe.py`; change `rows: list[dict]` to `bars: list[PriceBar]` (field access replaces `r["date"]`/`r.get(...)`; the `_float_or_none` coercion is no longer needed — bars are typed; keep the `DELETE`+`INSERT` idempotency and ISO date formatting exactly).
- In `utils/fx.py`: `upsert_fx_rates` takes `rates: list[FxRate]` (same replace-on-PK loop); `import_fx_rates` drops `api_key`/`client` for `provider: MarketDataProvider`, fetches `provider.fx_rates(ccy, since=start)` (drop the `end` pass-through only if the port has no `end` — it doesn't; verify no current caller passes `end`: grep, and if the CLI does, thread `since` only, matching today's actual usage), and sources `refresh_run(source=f"{provider.name}_fx", ...)`.
- In `universe.py`: `refresh_prices` mirrors Task 4's shape — no `_shared_fmp_client`, no `importer` param; `_refresh_one_price` fetches `bars = provider.daily_prices(sym, since)` with `since = since_date or _max_price_date(conn, sym)`, writes via `upsert_prices_daily(conn, ticker=sym, bars=bars, currency=currency, source=provider.name)` inside the same transaction/refresh-run structure `import_prices_from_fmp` uses today (move that structure here, then delete `import_prices_from_fmp` from `fmp.py`); `except FmpRateLimitError` → `except ProviderRateLimitError`. `refresh_fx` iterates `distinct_non_usd_currencies` exactly as `refresh_fx_from_fmp` does, calling the new `import_fx_rates` with the shared provider.
- `cli.py`: patch the call sites (`_refresh_prices`, `_refresh_fx`) to construct `FmpProvider` in a `with` block — Task 6 will unify.

- [ ] **Step 4: Run the migrated tests, then the full gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy src` → green.

- [ ] **Step 5: Commit**

```bash
git add -A src/bot tests
git commit -m "refactor(ingest): prices and FX flow through the provider port as typed records"
```

---

### Task 6: The composition root, and the seam's enforcement test

**Files:**
- Modify: `src/bot/cli.py` (single `_make_provider`; remove per-call-site construction from Tasks 4-5)
- Test: `tests/unit/test_seam_enforcement.py` (new), plus existing CLI tests (`grep -rn "FmpClient\|FmpProvider" tests/ src/bot` to find stragglers)

**Interfaces:**
- Consumes: `FmpProvider` (Task 2), `refresh_universe`/`refresh_prices`/`refresh_fx` (Tasks 4-5), `Settings` from `bot.config`.
- Produces: `_make_provider(settings: Settings) -> MarketDataProvider` in `cli.py` — the ONLY place in `src/bot` (outside `fmp.py` itself and `provider.py`) that names a concrete adapter.

- [ ] **Step 1: Write the failing enforcement test**

Create `tests/unit/test_seam_enforcement.py`:

```python
"""The seam's enforcement line (spec: 'nothing outside fmp.py imports FmpClient').

A source-scan test, so a future import can't silently re-couple the pipeline
to one provider. cli.py is the sanctioned composition root for FmpProvider.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bot"


def _offenders(pattern: str, *, allowed: set[str]) -> list[str]:
    rx = re.compile(pattern)
    return [
        str(p.relative_to(SRC))
        for p in sorted(SRC.rglob("*.py"))
        if p.name not in allowed and rx.search(p.read_text(encoding="utf-8"))
    ]


def test_fmp_client_is_internal_to_the_adapter() -> None:
    assert _offenders(r"\bFmpClient\b", allowed={"fmp.py"}) == []


def test_only_the_composition_root_names_the_concrete_adapter() -> None:
    assert _offenders(r"\bFmpProvider\b", allowed={"fmp.py", "cli.py"}) == []
```

- [ ] **Step 2: Run to verify current state**

Run: `uv run pytest tests/unit/test_seam_enforcement.py -v`
Expected: FAIL if any straggler import survived Tasks 4-5 (e.g. `utils/fx.py`); PASS is also acceptable — the test then locks the door. If it fails, the failure list is your worklist: remove each remaining `FmpClient` use outside `fmp.py`.

- [ ] **Step 3: Centralize construction in `cli.py`**

Add near the other helpers in `cli.py`:

```python
def _make_provider(settings: Settings) -> MarketDataProvider:
    """The composition root: the ONLY place a concrete data provider is named.

    Swapping the data source = writing a new adapter in bot/ingest/ and
    changing this return line (spec 2026-08-24).
    """
    return FmpProvider(api_key=settings.fmp_api_key)
```

Replace the per-call-site constructions from Tasks 4-5: each refresh path does `with closing(_make_provider(settings)) as provider:` (`from contextlib import closing` — the Protocol guarantees `close()`, and `closing` avoids requiring `__enter__` on the Protocol) and passes `provider` down. Imports in `cli.py`: `FmpProvider` from `bot.ingest.fmp`, `MarketDataProvider` from `bot.ingest.provider`; delete now-unused FMP imports.

- [ ] **Step 4: Full gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy src` → green, enforcement tests passing.

- [ ] **Step 5: Commit**

```bash
git add src/bot/cli.py tests/unit/test_seam_enforcement.py
git commit -m "feat(cli): _make_provider composition root + seam enforcement tests"
```

---

### Task 7: E2E through the real orchestration, and docs

**Files:**
- Modify: `tests/e2e/test_pipeline.py` (refresh phase runs `refresh_universe` with `FakeProvider` instead of seeding around orchestration — keep any direct-seed variant that tests something else), `docs/plano/estado.py` (re-audit entries touching ingest wiring, per CONTEXT.md duty), `CONTEXT.md`'s pointer if it names `refresh_universe_from_fmp` anywhere (grep)
- Test: the E2E itself

**Interfaces:**
- Consumes: `refresh_universe`, `refresh_prices` (Tasks 4-5), `FakeProvider` with `bundles=`/`prices=` (Task 3).
- Produces: an E2E that exercises the genuine orchestration path: `refresh_universe(conn, provider=fake, tickers=[...])` → `screen` → `analyze` on one DB, no network.

- [ ] **Step 1: Rework the E2E refresh phase**

In `tests/e2e/test_pipeline.py`, where the pipeline test currently seeds companies/financials directly (or via the old injectable importer), build a `FakeProvider` whose `bundles` carry the same fixture companies (construct `FundamentalsBundle` with `ParsedCompanyData` rows matching the rows the test seeds today — same tickers, same fiscal years, same values) and run:

```python
provider = FakeProvider(bundles=_fixture_bundles(), prices=_fixture_prices())
result = refresh_universe(conn, provider=provider, tickers=list(_fixture_bundles()))
assert result.failed == 0
refresh_prices(conn, provider=provider, tickers=list(_fixture_prices()))
```

The subsequent screen/analyze phases are unchanged — that's the point: the pipeline can't tell which adapter fed it. Keep the FMP-seed failure-path test (it asserts `IngestResult.error_message`) by migrating it to `FakeProvider(fail_with=...)`.

- [ ] **Step 2: Run the E2E**

Run: `uv run pytest tests/e2e -v`
Expected: PASS, no network access.

- [ ] **Step 3: Docs duty**

Update `docs/plano/estado.py` entries that describe FMP-coupled refresh wiring (re-audit only the ingest lines against the new code); grep `CONTEXT.md` and `README.md` for `refresh_universe_from_fmp` / `import_company_from_fmp` and update any hit. CLI behaviour didn't change, so the README quickstart stands.

- [ ] **Step 4: Full gate**

Run: `uv run pytest && uv run ruff check . && uv run mypy src` → green.

- [ ] **Step 5: Commit**

```bash
git add -A tests docs CONTEXT.md README.md
git commit -m "test(e2e): the pipeline runs through the provider port; docs re-audited"
```
