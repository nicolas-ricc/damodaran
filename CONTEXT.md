# investment-bot — Context

Personal investment bot. Local CLI tool. Single user. Greenfield project.

Current version: US-only (S&P 500).

## Domain language

- **Universe**: set of companies the screener considers (~50k global once M2 is done).
- **Story type**: Damodaran's classification of a company's life-cycle / risk profile (`hypergrowth`, `high-growth`, `mature-stable`, `mature-decline`, `cyclical`, `distressed`). See [ADR 0009](docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md).
- **Hypergrowth**: the story type of a young company growing explosively while its margin is still on the ramp. The classifier assigns it on four signals: last-year revenue growth of at least 50%, a revenue CAGR of at least 40%, an operating margin below the sector's, and a founded age of at most 15 years, or unknown (no `founded_year`). It is valued as such only from a story file (`story_type: hypergrowth` plus `story`); signals without one fall back to `high-growth` with a red flag. See [ADR 0009](docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md).
- **Story file**: the `story_type: hypergrowth` (required with `story`), `story`, `scenarios` and `founded_year` keys of `config/assumptions/<TICKER>.yaml`: the hand-written inputs of a hypergrowth valuation, with money amounts in the raw reporting currency. See [ADR 0009](docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md).
  _Avoid_: story override, narrative file.
- **Governance discount**: the `governance_discount` story key. A haircut applied to the intrinsic value before the margin of safety, never inside the DCF.
  _Avoid_: governance haircut in the WACC.
- **Margin of safety (MoS)**: `intrinsic_value_after_governance / current_price`, which equals `intrinsic_value / current_price` when there is no governance discount. `current_price` is the newest close converted into the valuation currency (a missing exchange rate means no price, hence no margin). > 1 = potentially undervalued. A holding mark uses the newest close on or before the snapshot date.
- **Verdict**: the one-word reading of the MoS: `>=1.3` potentially undervalued, `>=1.0` around fair value, `<1.0` potentially overvalued, `n/a` without a price. `margin_verdict` in `bot.reporting.analysis_report` is the single source.
- **Quality gates**: eliminatory filters in the screener (Capa B) that disqualify a company outright.
- **Value indicators**: filters checking cheapness relative to sector medians (Damodaran datasets).
- **Trap detection**: filters that flag companies that *look* cheap but are cheap for a reason.
- **Sector benchmark**: the Damodaran medians for one `(industry, region, year)`, against which a company's cheapness and quality are judged.
- **Coverage gate**: the eliminatory filter that removes a company it cannot measure from the universe, with exactly one reason, in precedence order: `industry_unmapped` (no Damodaran industry), `benchmark_missing` (no sector benchmark, or a NULL `wacc`), `currency_uncovered` (see **Uncovered currency**). See [ADR 0006](docs/adr/0006-unmeasurable-companies-leave-the-universe.md).
- **Measured company**: one that has every input its screening and ranking require. Only measured companies enter the ranking percentiles.
- **Fiscal year** (`fiscal_year`): the calendar year of the period's end date. An annual row is a duration fact of 350–380 days; Best Buy's year ending 2014-02-01 is fiscal_year 2014. A quarter belongs to the fiscal year it falls in, numbered by its position in it. Never the SEC `fy` field, which names the filing, nor `frame`.
- **Capas A/B/C**: see spec §3 — data / mechanical screener / interpretive analysis.
- **Listing currency**: the currency a share trades in on its exchange. Belongs to the price feed.
  _Avoid_: currency, local currency, trading currency.
- **Reporting currency**: the currency a company publishes its financial statements in. Belongs to the financial statements.
  _Avoid_: currency, reported currency, functional currency.
- **Uncovered currency**: a valuation currency with no row in `config/currencies.yaml` (or an unknown, NULL one). The company leaves the universe with reason `currency_uncovered`.
  _Avoid_: missing currency.
- **Company country** (`companies.country`): the ISO 3166 alpha-2 code providers store, translated to Damodaran's country name by `bot.reference.countries` before any Damodaran lookup.
  _Avoid_: using it as a `damodaran_country` key directly.
- **Valuation currency**: the currency a company is valued in — its reporting currency. Cash flows and discount rate are always expressed in it. See [ADR 0005](docs/adr/0005-currency-handling-and-valuation-currency.md).

## Source of truth

- **Spec**: `docs/superpowers/specs/2026-05-25-investment-bot-design.md`
- **ADRs**: `docs/adr/`
- **Active plan**: `docs/superpowers/plans/2026-08-17-conectar-fases-us-only.md`
- **Open audit**: `docs/superpowers/notes/2026-08-14-grilling-pipeline-seams.md` — pipeline seam-by-seam audit; seams 1-2 closed (ADR 0005, 0006), seam 3 onward pending.
- **The two plans**: `docs/plano/` — `plano.html` explains how the system is meant to work; `estado.html` says how much of it exists today. Read `estado.html` before starting a stage and update both when finishing one. See `docs/plano/README.md`.
- **The lesson**: `docs/leccion/` — `index.html` teaches the Damodaran pipeline chapter by chapter and points at the code; `check.py` fails when it cites a symbol that no longer exists. See `docs/leccion/README.md`.
- **The pipeline boards**: `docs/pipeline/` — d2 diagrams of the whole pipeline, cron to published site, drawn from the code: six boards (the overview and one per stage) and twenty-seven sub-boards, one per model group. `check.py` fails when a board cites a table, file or symbol that no longer exists. See `docs/pipeline/README.md`.
- **The pipeline models**: `docs/pipeline/models/` — TLA+ models of the stages, one unit through one run, checked by TLC in CI. A rule that breaks becomes an issue and a row in the Known broken rules table of `docs/pipeline/models/README.md`. See `docs/pipeline/models/README.md`.

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

- **SEC EDGAR** (`data.sec.gov`): US fundamentals (company facts, submissions, dei shares), free, requires User-Agent header. Default data provider (`edgar-stooq`); see [ADR 0007](docs/adr/0007-free-data-stack-edgar-stooq.md).
- **Stooq** (`stooq.com`): US EOD prices, free, no API key. Paired with SEC EDGAR as the default provider; see [ADR 0007](docs/adr/0007-free-data-stack-edgar-stooq.md).
- **Damodaran datasets** (`pages.stern.nyu.edu/~adamodar/`): industry/country benchmarks, annual.
- **Financial Modeling Prep** (optional, `BOT_DATA_PROVIDER=fmp`; M2): international fundamentals + global EOD prices, for the eventual non-US reopening. See [ADR 0007](docs/adr/0007-free-data-stack-edgar-stooq.md).
- **IBKR Flex Web Service** (M5): the only IBKR source. `bot portfolio` downloads one Activity Flex Query statement (positions, cash, trades, corporate actions) with `BOT_IBKR_FLEX_TOKEN` / `BOT_IBKR_FLEX_QUERY_ID`; no TWS, no local process. The snapshot is keyed on the statement date. See [ADR 0010](docs/adr/0010-flex-web-service-as-the-only-ibkr-source.md); supersedes [ADR 0004](docs/adr/0004-tws-api-via-ib-async.md).

## Conventions

- Type hints required everywhere (`mypy --strict`).
- Each ingest adapter is a pure module: `download → parse → upsert`. Functions accept paths/connections, no global state.
- Tests for `valuator/` (M4) and `screener/rules.py` (M3) will target 100% coverage when those modules exist.
- Integration tests use VCR cassettes (no live API calls in CI).
- Commits: Conventional Commits (`feat(m1): ...`, `fix: ...`, `docs: ...`).
