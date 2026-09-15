# 0007 — Free data stack: SEC EDGAR fundamentals + Stooq EOD prices

## Status

Accepted (2026-09-09). Implemented (2026-09-09, EdgarStooqProvider in ingest/edgar_stooq.py).
Amended (2026-09-15): Stooq's free tier proved unfit for bulk price refresh — its
HTTP endpoint is behind a JS anti-bot wall and its `db/` bulk archives require a paid
subscription (a free login neither unlocks bulk downloads nor meaningfully lifts the
per-ticker daily cap, ~17 tickers/run). The default price source is now **Tiingo**
(`edgar-tiingo`, EdgarTiingoProvider): a keyed REST API whose free tier covers the S&P
500. The EDGAR half is shared by both adapters via EdgarPricedProvider (ingest/edgar_base.py);
`edgar-stooq` remains selectable for the browser-recipe CSV path.

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
  machinery as FMP's 429 (StooqRateLimitError) — but that machinery addresses a quota,
  not a wall: as of 2026-09-09 Stooq serves a JavaScript anti-bot proof-of-work challenge
  to every client without a real browser (confirmed with both a plain and a browser
  User-Agent), so refresh --prices currently fails 100% of requests under this provider.
  Resolved (2026-09-09) with the browser-driven fetch path:
  scripts/stooq_browser_fetch.mjs harvests the CSVs through a real Chrome session
  (agent-browser over CDP — the browser solves the challenge, per-symbol quote-page
  warm-ups authorize each CSV), and BOT_STOOQ_DIR points refresh --prices at the
  harvested <TICKER>.csv files instead of the walled HTTP endpoint. The direct HTTP
  path remains in the adapter should the wall ever come down. Background in the
  "Real run (Task 8)" section of
  docs/superpowers/plans/2026-09-09-free-data-stack-edgar-stooq.md.
- XBRL concept variance across filers may leave more None gaps than FMP's
  standardized statements; the coverage gate (ADR 0006) makes those visible
  instead of silent.
- market_cap = close x latest dei shares; for dual-class companies this uses
  the primary listing's share count and may undercount total cap. Known,
  logged here, tolerable for the size gate's purpose.
