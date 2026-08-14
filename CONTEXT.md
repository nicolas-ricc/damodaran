# investment-bot — Context

Personal investment bot. Local CLI tool. Single user. Greenfield project.

## Domain language

- **Universe**: set of companies the screener considers (~50k global once M2 is done).
- **Story type**: Damodaran's classification of a company's life-cycle / risk profile (`high-growth`, `mature-stable`, `mature-decline`, `cyclical`, `distressed`).
- **Margin of safety (MoS)**: `intrinsic_value / current_price`. > 1 = potentially undervalued.
- **Quality gates**: eliminatory filters in the screener (Capa B) that disqualify a company outright.
- **Value indicators**: filters checking cheapness relative to sector medians (Damodaran datasets).
- **Trap detection**: filters that flag companies that *look* cheap but are cheap for a reason.
- **Sector benchmark**: the Damodaran medians for one `(industry, region, year)`, against which a company's cheapness and quality are judged.
- **Coverage gate**: the eliminatory filter that removes a company with no usable sector benchmark from the universe. See [ADR 0006](docs/adr/0006-unmeasurable-companies-leave-the-universe.md).
- **Measured company**: one that has every input its screening and ranking require. Only measured companies enter the ranking percentiles.
- **Capas A/B/C**: see spec §3 — data / mechanical screener / interpretive analysis.
- **Listing currency**: the currency a share trades in on its exchange. Belongs to the price feed.
  _Avoid_: currency, local currency, trading currency.
- **Reporting currency**: the currency a company publishes its financial statements in. Belongs to the financial statements.
  _Avoid_: currency, reported currency, functional currency.
- **Valuation currency**: the currency a company is valued in — its reporting currency. Cash flows and discount rate are always expressed in it. See [ADR 0005](docs/adr/0005-currency-handling-and-valuation-currency.md).

## Source of truth

- **Spec**: `docs/superpowers/specs/2026-05-25-investment-bot-design.md`
- **ADRs**: `docs/adr/`
- **Active plan**: `docs/superpowers/plans/2026-05-25-m1-skeleton-damodaran-sec-edgar.md`
- **Open audit**: `docs/superpowers/notes/2026-08-14-grilling-pipeline-seams.md` — pipeline seam-by-seam audit; seams 1-2 closed (ADR 0005, 0006), seam 3 onward pending.

## External services

- **SEC EDGAR** (`data.sec.gov`): US fundamentals, free, requires User-Agent header.
- **Damodaran datasets** (`pages.stern.nyu.edu/~adamodar/`): industry/country benchmarks, annual.
- **Financial Modeling Prep** (M2): international fundamentals + global EOD prices.
- **Interactive Brokers TWS API** via `ib_async` (M5): portfolio sync, read-only. Needs a local TWS/IB Gateway on `BOT_IBKR_PORT` (default 7496). See [ADR 0004](docs/adr/0004-tws-api-via-ib-async.md).

## Conventions

- Type hints required everywhere (`mypy --strict`).
- Each ingest adapter is a pure module: `download → parse → upsert`. Functions accept paths/connections, no global state.
- Tests for `valuator/` (M4) and `screener/rules.py` (M3) will target 100% coverage when those modules exist.
- Integration tests use VCR cassettes (no live API calls in CI).
- Commits: Conventional Commits (`feat(m1): ...`, `fix: ...`, `docs: ...`).
