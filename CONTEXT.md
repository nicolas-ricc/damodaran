# investment-bot — Context

Personal investment bot. Local CLI tool. Single user. Greenfield project.

Current version: US-only (S&P 500).

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
- **Active plan**: `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md`
- **Open audit**: `docs/superpowers/notes/2026-08-14-grilling-pipeline-seams.md` — pipeline seam-by-seam audit; seams 1-2 closed (ADR 0005, 0006), seam 3 onward pending.
- **The two plans**: `docs/plano/` — `plano.html` explains how the system is meant to work; `estado.html` says how much of it exists today. Read `estado.html` before starting a stage and update both when finishing one. See `docs/plano/README.md`.

## Working with the plans

The two plans are working tools, not decoration. They carry one claim each and
they age differently:

- **Before a stage**, `estado.html` shows what is actually there in the area you
  are about to touch. Pay attention to the `muerto` state: finished, typed,
  sometimes tested code that nothing calls. Wiring one is usually cheaper than
  writing a new thing beside it.
- **While working**, `plano.html` shows where a piece belongs, what pattern its
  neighbourhood uses, and the three live architectural tensions. If a change
  adds a fourth, it becomes visible.
- **After a stage**, both get updated. `build.py` fails loudly when the
  architecture plan stops matching the code, so that one is self-policing. The
  status plan is not: it is hand-curated from an audit and goes stale in
  silence, so it needs a real re-audit against the code (not against the spec).
  `build_estado.py` warns when `src/` moved after the recorded audit commit.
- **If a stage implements an ADR, say so in the ADR.** ADR 0005 and 0006 once
  both read "Accepted" while their decisions remained unimplemented, so anyone
  reading `docs/adr/` believed the code complied. ADR 0006 now says
  "Implemented"; ADR 0005 says explicitly that it isn't, and why that's safe
  under the current US-only scope. Do not let a fourth ADR go silent.

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
