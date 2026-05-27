# investment-bot — Context

Personal investment bot. Local CLI tool. Single user. Greenfield project.

## Domain language

- **Universe**: set of companies the screener considers (~50k global once M2 is done).
- **Story type**: Damodaran's classification of a company's life-cycle / risk profile (`high-growth`, `mature-stable`, `mature-decline`, `cyclical`, `distressed`).
- **Margin of safety (MoS)**: `intrinsic_value / current_price`. > 1 = potentially undervalued.
- **Quality gates**: eliminatory filters in the screener (Capa B) that disqualify a company outright.
- **Value indicators**: filters checking cheapness relative to sector medians (Damodaran datasets).
- **Trap detection**: filters that flag companies that *look* cheap but are cheap for a reason.
- **Capas A/B/C**: see spec §3 — data / mechanical screener / interpretive analysis.

## Source of truth

- **Spec**: `docs/superpowers/specs/2026-05-25-investment-bot-design.md`
- **ADRs**: `docs/adr/`
- **Active plan**: `docs/superpowers/plans/2026-05-25-m1-skeleton-damodaran-sec-edgar.md`

## External services

- **SEC EDGAR** (`data.sec.gov`): US fundamentals, free, requires User-Agent header.
- **Damodaran datasets** (`pages.stern.nyu.edu/~adamodar/`): industry/country benchmarks, annual.
- **Financial Modeling Prep** (M2): international fundamentals + global EOD prices.
- **Interactive Brokers Client Portal API** (M5): portfolio sync, read-only.

## Conventions

- Type hints required everywhere (`mypy --strict`).
- Each ingest adapter is a pure module: `download → parse → upsert`. Functions accept paths/connections, no global state.
- Tests for `valuator/` (M4) and `screener/rules.py` (M3) will target 100% coverage when those modules exist.
- Integration tests use VCR cassettes (no live API calls in CI).
- Commits: Conventional Commits (`feat(m1): ...`, `fix: ...`, `docs: ...`).
