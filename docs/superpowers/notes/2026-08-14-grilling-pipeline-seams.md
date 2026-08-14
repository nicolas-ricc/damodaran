# Grilling session — pipeline seams (2026-08-11 → 2026-08-14)

Session goal: walk the pipeline stage by stage and verify each stage parses its
data correctly enough for the next one to work. Method: `grill-with-docs` +
`domain-modeling`, evidence read from the code, decisions written down as they
were resolved.

Baseline at the start of the session: `676 passed`, ruff and mypy clean, working
tree clean at `0ce1660`. **The pipeline has never run against real data** — there
is no `bot.duckdb` and no `reports/` in the repo.

## The pipeline, as audited

```
1. universe_default.csv (451 synthetic tickers) ──┐
2. FMP / SEC EDGAR ───────────────────────────────┼──▶ companies, financials_annual,
3. Damodaran .xls ────────────────────────────────┘    prices_daily, currencies,
                                                       damodaran_industry/_country
4. industry_mapping.csv ──▶ companies.industry_damodaran      ← join key
5. build_company_data ────▶ CompanyData                       ← derived ratios
6. rules → ranking ───────▶ screener_candidates
7. assumptions → dcf ─────▶ Analysis → report
```

Seams 1 and 2 were grilled and closed. Seam 3 onward was not started.

## Seam 1 — currency (CLOSED, see ADR 0005)

Findings:

- `companies.currency` held *either* the listing currency (FMP profile) *or* the
  reporting currency (`reportedCurrency` fallback, `fmp.py:110`, `fmp.py:713`) —
  one column for two concepts, never reconciled anywhere in the pipeline.
- Consequence in `build_company_data` (`engine.py:422-457`): `pe`, `pbv`,
  `ev_ebitda` and `fcf_yield` divide a price in the listing currency by a figure
  in the reporting currency. Only `market_cap` is converted (`_market_cap_usd`).
  Correct for a US-only universe, wrong for the global one.
- `damodaran.py:759-770` writes a **single** US risk-free rate into every row of
  `damodaran_country` (~150 countries), and `_DEFAULT_GDP_NOMINAL = 0.04`
  (`assumptions.py:60`) caps terminal growth for every company. So a Japanese
  company's yen cash flows are discounted at a USD-based rate — the canonical
  Damodaran international-valuation error, since the gap between a JPY and a USD
  risk-free rate is expected inflation, not risk. The bias has a predictable sign,
  so ranking by margin of safety was partly ranking by the reporting currency's
  inflation.

Decisions (ADR 0005): listing currency and reporting currency are distinct terms;
money is stored exactly as reported (no USD normalisation at ingest — closes #66
as *rejected*); conversion lives behind an obligatory seam rather than in each
caller; a company is valued in its own **valuation currency** (its reporting
currency), with a per-currency risk-free rate imported from Damodaran's dataset
and `g = min(rfr_of_that_currency, nominal GDP of that country)`.

## Seam 2 — the Damodaran join (CLOSED, see ADR 0006)

Findings:

- The three layers disagreed on missing data (`engine.py:539-570`): quality gates
  never consult `skipped` (eliminate), value indicators eliminate when *all* skip,
  trap detection treats a skip as a pass (acquit).
- Because only the US datasets are ingested (#60), a non-US company resolves no
  benchmark row. Its three sector-relative value indicators skip, leaving only the
  absolute `fcf_yield_above` (8%) able to admit it, while `roic_above_sector_wacc`
  skips and acquits. **Outside the US the screener selected on high FCF yield
  alone with the value-destruction filter disabled** — the exact value-trap
  profile spec §6.4 exists to reject. The philosophy changed by nationality, not
  merely the data quality.
- Ranking compounded it: with `_EMPTY_BENCHMARKS` the ROIC-vs-WACC spread collapses
  to `0.0` (`engine.py:507-521`), so an unmeasured company scored as if its ROIC
  exactly matched its sector's WACC and then competed on percentile against
  companies that were actually measured.

Decisions (ADR 0006): unmeasurable company → out of the universe via an explicit
coverage gate that reports the loss; ranking scores only fully measured companies
(no metric ever defaults to a neutral zero); `roic_above_sector_wacc` skipping is
eliminatory, including when the row exists but `wacc` is NULL.

Settled in passing: the coverage report distinguishes **unmapped industry** (fix:
edit `industry_mapping.csv`) from **region with no dataset** (fix: ingest the
files, #60) — two failures with two different remedies.

## Open questions — resume here

1. **Define "measured" as a predicate.** Proposed: benchmark row exists, `wacc`
   non-NULL, and *at least one* sector multiple non-NULL among `pe`, `ev_ebitda`,
   or the `pbv`+`roe` pair. The third clause is the one awaiting a call: if a US
   sector row exists but its multiples are NULL, the company could only qualify on
   FCF yield > 8% — the same degeneration ADR 0006 outlaws abroad. Apply the
   doctrine evenly (eliminate it too), or treat FCF yield as a self-sufficient
   value indicator (let it compete)?
2. **Code-reading vs a real run.** Seams 1 and 2 were visible by reading. Seam 3
   onward (Damodaran `.xls` parsing whose headers drift every January, fiscal-year
   ↔ price-date ↔ dataset-year alignment, per-ticker FMP gaps) is not: it shows up
   when real data lands. The FMP cassettes have never been re-recorded against the
   live API (#52). Proposal on the table: run `refresh --damodaran` plus a handful
   of tickers with a real FMP key, then grill seam 3 against a loaded database.

## Not yet grilled

- **Seam 3 — temporal alignment**: which fiscal year is compared against which
  price date and which Damodaran dataset year.
- Seam 4 — `assumptions` resolution and `Sourced` provenance.
- Seam 5 — DCF → sensitivity → narrative flags.
- Seam 6 — portfolio events derived from A/B/C.

## Implementation debt this session created

None of the decisions are implemented — ADR 0005 and 0006 describe the target, and
the code still does the old thing. Concretely pending:

- Split `companies.currency`; make `prices_daily` carry the listing currency and
  `financials_annual` the reporting currency.
- Build the conversion seam and stop every downstream reader from touching the raw
  tables.
- Import Damodaran's risk-free rates by currency; stop broadcasting the US scalar
  across `damodaran_country`; make `g` per-country.
- Add the coverage gate, the coverage report, and the "measured company" predicate;
  remove the neutral-zero defaults from ranking.
- Fix the stale docstrings that encode the old model — notably `CompanyData` in
  `screener/types.py`, which still claims the non-`market_cap` figures are in the
  "listing currency" and that full USD normalisation is merely deferred.

Also worth noting for later: `_quality_metric` adds a spread (`roic - wacc`) to a
level (`roe`). Flagged, not discussed.
