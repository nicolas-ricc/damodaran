# ADR 0006 — A company the bot cannot measure against its sector leaves the universe

## Status

Accepted (2026-08-11). Implemented (2026-08-19, coverage gate en screener/engine.py + persistencia de rechazados).

## Context

Every value indicator and the central trap detector (`roic_above_sector_wacc`)
compare a company against its Damodaran `(industry, region)` medians. When that
row is missing, the three screener layers disagreed on what to do:

- Quality gates never consulted `skipped` — an unmeasurable gate eliminated.
- Value indicators treated a skip as "not passed"; if all four skipped,
  `any_value` stayed false and the company was eliminated.
- Trap detection treated a skip as a pass — the company survived untested.

The combination changed the *philosophy* by nationality rather than merely
degrading it. Because only the US datasets are ingested today (#60), a non-US
company resolves no benchmark row, so its three sector-relative value indicators
skip, leaving only the absolute `fcf_yield_above` (8%) able to admit it — while
`roic_above_sector_wacc`, the value-destruction filter, skips and acquits. Outside
the US the screener therefore selected on high FCF yield alone with the central
Damodaran filter disabled: exactly the value-trap profile spec §6.4 exists to
reject.

Ranking compounded it. With `_EMPTY_BENCHMARKS`, `_quality_metric`'s ROIC-vs-WACC
spread collapsed to `0.0`, so an unmeasured company scored as if its ROIC exactly
matched its sector's WACC and then competed on percentile against companies that
had actually been measured. Absence of evidence was scored as average quality.

## Decision

**A company without usable sector benchmarks is not screened — it leaves the
universe**, via an explicit coverage gate that reports how many companies were
lost and why. Coverage becomes a visible number on every run instead of a silent
reshaping of the shortlist.

- **Ranking scores only fully measured companies.** A company missing an input a
  sub-score needs does not enter that percentile distribution at all; no metric
  ever defaults to a neutral zero.
- **`roic_above_sector_wacc` skipping is eliminatory**, including the residual
  case where the benchmark row exists but its `wacc` is NULL. No sector WACC, no
  candidate.

Rejected: *skip = fail in all three layers* — the same practical outcome, but the
reason scatters across five rules and yields no coverage metric. Rejected for now:
*substitute another region's medians and disclose it*, the way
`valuator/assumptions.py` already labels `sector_default_damodaran_cross_region`.
It is the right fallback once #60 actually ingests the regional datasets, but as
today's default it would compare a German company against US medians for the
entire non-US universe.

## Consequences

- Until #60 lands, the screener is explicitly US-only and says so, rather than
  quietly applying a different philosophy abroad.
- `industry_mapping.csv` coverage becomes load-bearing: an unmapped provider
  industry leaves `industry_damodaran` NULL, which now removes the company from
  the universe.
