# ADR 0004 — FX rates source: ECB over FMP

**Status:** Accepted (2026-05-27)

## Context

The `currencies` table stores daily FX rates against USD so that financial figures
reported in non-USD currencies can be normalised for comparison.  We need a
reliable, historical source for these rates.

Two candidates were evaluated:

| Source | Pro | Con |
|--------|-----|-----|
| **Financial Modeling Prep** (FMP) | Already used in M2 for fundamentals; one fewer dependency | FMP's FX endpoint consumes API call quota; the M2 FX work was kept independent of the FMP client to allow parallelism; cost is a concern at high volume |
| **ECB Statistical Data Warehouse** (SDW) | Free, no API key; machine-readable SDMX-JSON; daily rates going back to 1999; ECB rates are widely accepted reference rates in finance | EUR-centric (all rates quoted per EUR), so USD conversion for non-EUR currencies requires a cross via EUR |

## Decision

Use the **ECB SDW REST API** (`data-api.ecb.europa.eu/service/data/EXR`) as the
primary FX source.

Rate computation:

```
rate_to_usd[EUR] = ECB(D.USD.EUR.SP00.A)           # USD per 1 EUR
rate_to_usd[X]   = ECB(D.USD.EUR) / ECB(D.X.EUR)  # USD per 1 X
rate_to_usd[USD] = 1.0
```

FMP remains available as a future override if broader currency coverage is
needed (e.g., exotic EM currencies that ECB does not publish).

## Consequences

- No API key required; no rate-limit concerns.
- Coverage: all major currencies (EUR, GBP, JPY, CHF, CAD, AUD, CNY, …).
  ECB publishes ~30+ reference rates; exotic currencies not in the ECB basket
  will have `get_fx_rate` return `None`.
- Rates are published on ECB business days (~5 pm CET); weekends and holidays
  are absent from the DB.  `get_fx_rate` applies a nearest-prior lookup so
  Friday's rate is used for Saturday/Sunday conversions — standard industry
  practice for period-end financials.
- The `source` column in `currencies` is `'ecb'`; if we later add FMP as a
  fallback the value would be `'fmp'`, allowing provenance tracking.
