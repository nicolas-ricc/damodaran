# AAPL — Apple Inc

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 141.71
- **Current price:** 150.00
- **Margin of safety:** 0.94x (potentially overvalued)
- **Story type:** mature-stable
- **WACC (computed from the components in §3):** 8.1% (equity 83.3% / debt 16.7%)
- **Terminal value share of EV:** 82.4%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**mature-stable**

- historical revenue CAGR 4.2% over 3 years
- classified as mature-stable
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | 4.2% | historical_average |
| Operating margin | 28.0% | sector_default_damodaran |
| Sales-to-capital | 2.50 | sector_default_damodaran |
| Cost of equity | 9.0% | sector_default_damodaran |
| Pre-tax cost of debt | 4.5% | sector_default_damodaran |
| Equity weight | 83.3% | sector_default_damodaran |
| Debt weight | 16.7% | sector_default_damodaran |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 21.0% | sector_default_damodaran |
| Probability of bankruptcy | 0.0% | rule_based |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 448.09B | 125.46B | 99.12B | 7.24B | 91.88B | 85.00B |
| 2 | 466.94B | 130.74B | 103.29B | 7.54B | 95.75B | 81.95B |
| 3 | 486.58B | 136.24B | 107.63B | 7.86B | 99.77B | 79.00B |
| 4 | 507.05B | 141.97B | 112.16B | 8.19B | 103.97B | 76.16B |
| 5 | 528.38B | 147.95B | 116.88B | 8.53B | 108.35B | 73.42B |
| Terminal | — | — | — | — | 2,731.32B | — |

- **Enterprise value:** 2,246.49B
- **Equity value:** 2,196.49B
- **Net debt:** 50.00B

## 5. Sensitivity

### Tornado (±20% per assumption, ranked by impact)

| Assumption | Intrinsic @ -20% | Intrinsic @ +20% | Impact |
|---|---|---|---|
| cost_of_equity | 224.11 | 103.12 | 120.99 |
| operating_margin (yr 1) | 110.56 | 172.86 | 62.30 |
| terminal_growth | 123.24 | 168.88 | 45.63 |
| tax_rate | 148.83 | 134.48 | 14.35 |
| revenue_growth (yr 1) | 136.75 | 146.83 | 10.08 |
| pretax_cost_of_debt | 145.98 | 137.67 | 8.31 |
| sales_to_capital | 139.00 | 143.51 | 4.51 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -20% | -10% | +0% | +10% | +20% |
|---|---|---|---|---|---|
| -20% | 1.17x | 1.33x | 1.49x | 1.66x | 1.82x |
| -10% | 0.91x | 1.03x | 1.16x | 1.29x | 1.41x |
| +0% | 0.74x | 0.84x | 0.94x | 1.05x | 1.15x |
| +10% | 0.62x | 0.71x | 0.80x | 0.88x | 0.97x |
| +20% | 0.54x | 0.61x | 0.69x | 0.76x | 0.84x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'mature-stable' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | yellow | terminal value is 82% of enterprise value (> 80%) — valuation is fragile |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 21.96 | 22.00 |
| P/E market | 23.25 | 22.00 |
| EV/Sales | 5.22 | 5.00 |
