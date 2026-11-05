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

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 178.27 | 117.40 | 60.87 |
| terminal_growth | -1.0pp / +1.0pp | 119.29 | 178.39 | 59.10 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 135.83 | 147.81 | 11.98 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 136.15 | 147.27 | 11.13 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 146.47 | 137.24 | 9.24 |
| sales_to_capital | ×0.8 / ×1.2 | 139.00 | 143.51 | 4.51 |
| tax_rate | -1.0pp / +1.0pp | 143.41 | 140.00 | 3.42 |
### 2-D grid — cost_of_equity (rows) × terminal_growth (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / terminal_growth → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 0.95x | 1.06x | 1.19x | 1.37x | 1.62x |
| -0.5pp | 0.87x | 0.95x | 1.05x | 1.19x | 1.37x |
| +0.0pp | 0.80x | 0.86x | 0.94x | 1.05x | 1.19x |
| +0.5pp | 0.73x | 0.79x | 0.86x | 0.94x | 1.05x |
| +1.0pp | 0.68x | 0.73x | 0.78x | 0.85x | 0.94x |
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
