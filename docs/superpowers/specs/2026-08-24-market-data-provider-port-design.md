# Market-data provider port — design

**Goal.** Isolate the fetching of fundamentals, prices and FX behind one seam so the
data source can be swapped at implementation time (a new adapter + one wiring line)
without touching the pipeline. Provider-specific parsing lives inside each adapter.

**Status.** Approved in chat 2026-08-24. Scope decisions by the user: the seam covers
what FMP does today (company info, statements, prices, FX, filing-date probe);
Damodaran, SEC and IBKR stay as they are; swap is code-level wiring at a single
composition point — no runtime provider selection.

## Context

Downstream (screener, valuator, reporting) already reads only DuckDB — the storage
seam of ADR 0005. The coupling lives in the ingest orchestration: `universe.py`
exposes `refresh_universe_from_fmp` / `refresh_prices_from_fmp`, threads `api_key`,
constructs `FmpClient`, and catches `FmpRateLimitError`; `utils/fx.py` imports
`FmpClient` directly; `cli.py` names FMP throughout. Swapping providers today means
rewriting orchestration, not adding a client.

## The port

New module `src/bot/ingest/provider.py`. One Protocol — the interface is everything
the pipeline may know about a data source:

```python
class MarketDataProvider(Protocol):
    @property
    def name(self) -> str: ...                # "fmp": refresh_log source prefix, company.source
    def lookup_company(self, ticker: str) -> CompanyInfo | None: ...
    def fundamentals(self, ticker: str) -> FundamentalsBundle: ...
    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]: ...
    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]: ...
    def latest_filing_date(self, ticker: str) -> date | None: ...   # skip-probe
    def close(self) -> None: ...              # one instance == one bulk run's connection pool
```

Canonical records live beside the Protocol in `provider.py`:

- `CompanyInfo` and `ParsedCompanyData` **move** there from `fmp.py` (unchanged shape;
  `fmp.py` re-imports them). Adapters depend on canonical types, never the reverse.
- New frozen dataclass `FundamentalsBundle`: `info: CompanyInfo | None`,
  `annual: ParsedCompanyData`, `quarterly: ParsedCompanyData`,
  `filings: list[dict[str, Any]]` (the `filings_log` row shape `upsert_filings`
  already consumes). One `fundamentals()` call carries everything the importer
  needs for one ticker.
- New frozen dataclasses `PriceBar` (`date: date`, `close: float | None`,
  `volume: float | None`, `market_cap: float | None`) and `FxRate` (`date: date`,
  `rate_to_usd: float`) — the currency is the `fx_rates(currency, since)` argument and the
  `upsert_fx_rates(currency=...)` keyword, not a per-row field. These replace the raw `list[dict]` row shapes that
  `upsert_prices_daily` / `upsert_fx_rates` consume today.
- `ProviderRateLimitError(RuntimeError)` is the neutral rate-limit contract.
  `FmpRateLimitError` becomes a subclass (existing imports keep working).

## The FMP adapter

`fmp.py` becomes one adapter. `FmpProvider` implements the Protocol, owning as
internals: `FmpClient` (HTTP), `parse_fmp_fundamentals`, the latest-filing probe
logic now in `universe.make_fmp_latest_filing_probe`, and conversion of FMP JSON to
`PriceBar` / `FxRate`. After the refactor **nothing outside `fmp.py` imports
`FmpClient`** — that rule is the seam's enforcement line.

## Orchestration and composition root

- `universe.py`: `refresh_universe_from_fmp` → `refresh_universe(conn, provider, tickers, ...)`;
  `refresh_prices_from_fmp` → `refresh_prices(conn, provider, ...)`. No `api_key`
  parameters, no `_shared_fmp_client` (the caller-owned provider instance is the
  shared connection pool). The injectable `importer`/`probe` hooks collapse into the
  provider itself. The per-ticker DB-writing importer (`import_company_from_fmp`)
  becomes provider-neutral `import_company(conn, ticker, provider, mapping)` and
  moves out of `fmp.py` (into `universe.py`): it calls `provider.lookup_company` +
  `provider.fundamentals`, then upserts — pure port consumption.
- `utils/fx.py`: `import_fx_rates(..., provider)` — the `FmpClient` import goes away.
- Source labels derive from `provider.name` (`f"{provider.name}_universe"` etc.), so
  existing `refresh_log` rows stay valid.
- `cli.py` grows the single composition function:

```python
def _make_provider(settings: Settings) -> MarketDataProvider:
    return FmpProvider(api_key=settings.fmp_api_key)
```

  It is the only place a concrete adapter is named. CLI flags do not change.

## Error handling

Orchestration catches `ProviderRateLimitError` only; the 429 → clean-stop →
`deferred` behaviour becomes provider-independent. All other adapter exceptions keep
today's contract: caught per ticker, recorded as `failed`, run continues.

## Testing

- `tests/` gains a `FakeProvider` implementing the Protocol over in-memory fixture
  records — the second adapter that makes the seam real. mypy strict checks both
  adapters against the Protocol, so drift fails the type check.
- Unit tests that inject `importer`/`probe` migrate to injecting `FakeProvider`.
- The E2E test exercises the genuine `refresh_universe` orchestration through
  `FakeProvider` instead of seeding around it.
- Behaviour is refactor-neutral: the existing rate-limit/deferral, skip-probe,
  failure-rate and merge-upsert tests must pass unchanged in meaning.

## Out of scope

SEC, Damodaran, IBKR adapters; runtime provider registry; any second live provider;
batching/quota backlog items.
