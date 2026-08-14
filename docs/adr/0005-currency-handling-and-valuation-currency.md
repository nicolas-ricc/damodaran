# ADR 0005 — Store money as reported; convert at the point of calculation; value in the company's own currency

## Status

Accepted (2026-08-11).

## Context

The bot mixes three money sources with different currencies: `financials_annual`
(the **reporting currency**, from the filing), `prices_daily` (the **listing
currency**, from the exchange), and the Damodaran benchmarks (USD). Two defects
made the mismatch concrete:

1. `companies.currency` held *either* the listing currency (FMP profile) *or*,
   as a silent fallback, the reporting currency — one column for two concepts.
   Nothing in the pipeline ever compared the two. As a result `build_company_data`
   computed `pe`, `pbv`, `ev_ebitda` and `fcf_yield` by dividing a price in the
   listing currency by a figure in the reporting currency. Correct for a US-only
   universe, wrong for the global universe the spec targets.
2. The Damodaran importer wrote a **single** US risk-free rate (scraped from the
   US "Industry Averages" pre-header) into every row of `damodaran_country`, and
   `_DEFAULT_GDP_NOMINAL = 0.04` (US) capped terminal growth for every company. A
   Japanese company's yen cash flows were therefore discounted at a USD-based
   rate — Damodaran's canonical international-valuation error, since the gap
   between a JPY and a USD risk-free rate is expected inflation, not risk. The
   resulting bias has a predictable sign, so ranking by margin of safety was
   partly ranking by the reporting currency's inflation.

## Decision

**1. Listing currency and reporting currency are distinct terms.** Each lives in
the table that owns it (`prices_daily`, `financials_annual`). `companies.currency`
is retired as a single ambiguous column.

**2. Money is stored exactly as reported — no USD normalisation at ingest.**
The database stays a faithful, immutable mirror of the source. Conversion happens
at the point of calculation.

Rejected: normalising to USD at ingest (issue #66). Per-period FX would have kept
ingest append-only but forces every consumer that needs a comparable growth series
to undo the conversion; a constant cut-off FX would make stored figures change on
every run with no new filing, breaking incremental ingest, the reproducibility
guarantee (spec §13.3) and the meaning of `is_restated`.

**3. Conversion lives behind an obligatory seam, not in each caller.** A single
constructor per stage (`build_company_data` for the screener, the assumptions
loader for the valuator) reads the raw figures with their currencies and returns a
currency-coherent snapshot. Nothing downstream reads `financials_annual` or
`prices_daily` directly. Downstream types carry no ambiguous money: they are
either dimensionless ratios or amounts in a currency declared on the object
itself.

Rejected: a `Money(amount, currency)` type propagated through the whole pipeline.
Stronger guarantees, but it spreads currency plumbing into every ratio and every
rule; the seam keeps the concern in one place.

**4. A company is valued in its own reporting currency — the *valuation
currency*.** Cash flows and discount rate must share a currency. The risk-free
rate comes from Damodaran's per-currency risk-free-rate dataset (a new importer),
and terminal growth becomes `min(risk_free_rate_of_that_currency, nominal GDP
growth of that country)` instead of today's two US-sourced halves.

Rejected: deriving the per-currency rate from an inflation differential
(`rfr_ccy = rfr_USD + (E[π_ccy] − E[π_USD])`) — Damodaran's own fallback, but it
needs an expected-inflation source per country that we do not have. Also rejected:
projecting in USD using forward FX from the interest-rate differential —
mathematically equivalent if done consistently, but far more machinery and error
surface.

## Consequences

- The pipeline needs exactly **one** FX conversion: the price, from listing
  currency into the valuation currency, at spot on the valuation date. Margin of
  safety is then dimensionless (value per share ÷ price, same currency) and
  depends on no FX rate at all.
- USD still appears where cross-company comparison is unavoidable — notably the
  absolute market-cap floor in the quality gates — and that conversion happens
  inside the seam, at spot.
- Growth series (the revenue-decline trap detector, the growth score) are in a
  single reporting currency by construction, so FX movement is never read as
  business deterioration. A company that *changes* its reporting currency
  mid-series remains an open edge case.
- The Damodaran importer gains a dataset (risk-free rates by currency) and loses
  the single-scalar broadcast into `damodaran_country`.
