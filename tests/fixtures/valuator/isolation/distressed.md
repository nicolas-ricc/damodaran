# DIST — DIST

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 1.04
- **Current price:** 1.50
- **Margin of safety:** 0.69x (potentially overvalued)
- **Story type:** distressed
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 74.7%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**distressed**

- historical revenue CAGR 0.3% over 3 years
- classified as distressed
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | 0.3% | historical_average |
| Operating margin | 12.0% | sector_default_damodaran |
| Sales-to-capital | 2.00 | sector_default_damodaran |
| Cost of equity | 10.0% | sector_default_damodaran |
| Pre-tax cost of debt | 6.0% | sector_default_damodaran |
| Equity weight | 76.9% | sector_default_damodaran |
| Debt weight | 23.1% | sector_default_damodaran |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 21.0% | sector_default_damodaran |
| Probability of bankruptcy | 20.0% | manual |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 1.01B | 121.61M | 96.07M | 1.70M | 94.37M | 86.75M |
| 2 | 1.02B | 122.02M | 96.39M | 1.71M | 94.69M | 80.01M |
| 3 | 1.02B | 122.43M | 96.72M | 1.71M | 95.01M | 73.80M |
| 4 | 1.02B | 122.84M | 97.04M | 1.72M | 95.33M | 68.06M |
| 5 | 1.03B | 123.25M | 97.37M | 1.72M | 95.65M | 62.78M |
| Terminal | — | — | — | — | 1.67B | — |

- **Enterprise value:** 1.47B
- **Equity value:** 1.04B
- **Net debt:** 920.00M

## 5. Sensitivity

### Tornado (±20% per assumption, ranked by impact)

| Assumption | Intrinsic @ -20% | Intrinsic @ +20% | Impact |
|---|---|---|---|
| cost_of_equity | 1.56 | 0.77 | 0.79 |
| operating_margin (yr 1) | 0.76 | 1.32 | 0.56 |
| terminal_growth | 0.95 | 1.17 | 0.22 |
| tax_rate | 1.10 | 0.98 | 0.12 |
| pretax_cost_of_debt | 1.09 | 0.99 | 0.10 |
| sales_to_capital | 0.98 | 1.08 | 0.09 |
| revenue_growth (yr 1) | 1.04 | 1.04 | 0.00 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -20% | -10% | +0% | +10% | +20% |
|---|---|---|---|---|---|
| -20% | 0.77x | 0.90x | 1.04x | 1.17x | 1.31x |
| -10% | 0.61x | 0.72x | 0.83x | 0.94x | 1.05x |
| +0% | 0.51x | 0.60x | 0.69x | 0.79x | 0.88x |
| +10% | 0.43x | 0.51x | 0.59x | 0.67x | 0.75x |
| +20% | 0.37x | 0.44x | 0.51x | 0.59x | 0.66x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'distressed' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | green | terminal value is 75% of enterprise value (<= 80%) |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E | — | 10.00 |
| EV/Sales | 1.46 | 1.20 |
