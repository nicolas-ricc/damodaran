# CYCL — CYCL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 14.28
- **Current price:** 0.90
- **Margin of safety:** 15.87x (potentially undervalued)
- **Story type:** cyclical
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 80.8%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**cyclical**

- historical revenue CAGR 4.7% over 4 years
- classified as cyclical
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | 4.7% | historical_average |
| Operating margin | 10.0% | historical_average |
| Sales-to-capital | 2.00 | sector_default_damodaran |
| Cost of equity | 10.0% | sector_default_damodaran |
| Pre-tax cost of debt | 6.0% | sector_default_damodaran |
| Equity weight | 76.9% | sector_default_damodaran |
| Debt weight | 23.1% | sector_default_damodaran |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 21.0% | sector_default_damodaran |
| Probability of bankruptcy | 0.0% | rule_based |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 1.26B | 125.51M | 99.15M | 27.98M | 71.17M | 65.42M |
| 2 | 1.31B | 131.36M | 103.78M | 29.29M | 74.49M | 62.94M |
| 3 | 1.38B | 137.49M | 108.62M | 30.65M | 77.96M | 60.56M |
| 4 | 1.44B | 143.90M | 113.68M | 32.08M | 81.60M | 58.26M |
| 5 | 1.51B | 150.61M | 118.98M | 33.58M | 85.41M | 56.06M |
| Terminal | — | — | — | — | 1.94B | — |

- **Enterprise value:** 1.58B
- **Equity value:** 1.43B
- **Net debt:** 150.00M

## 5. Sensitivity

### Tornado (±20% per assumption, ranked by impact)

| Assumption | Intrinsic @ -20% | Intrinsic @ +20% | Impact |
|---|---|---|---|
| cost_of_equity | 21.73 | 10.43 | 11.31 |
| operating_margin (yr 1) | 10.08 | 18.48 | 8.40 |
| terminal_growth | 13.07 | 15.95 | 2.88 |
| sales_to_capital | 12.97 | 15.15 | 2.18 |
| tax_rate | 15.19 | 13.34 | 1.85 |
| pretax_cost_of_debt | 15.04 | 13.59 | 1.45 |
| revenue_growth (yr 1) | 13.87 | 14.70 | 0.84 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -20% | -10% | +0% | +10% | +20% |
|---|---|---|---|---|---|
| -20% | 17.30x | 20.72x | 24.15x | 27.58x | 31.00x |
| -10% | 13.67x | 16.45x | 19.22x | 22.00x | 24.78x |
| +0% | 11.20x | 13.53x | 15.87x | 18.20x | 20.53x |
| +10% | 9.40x | 11.42x | 13.43x | 15.44x | 17.46x |
| +20% | 8.04x | 9.81x | 11.58x | 13.35x | 15.12x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'cyclical' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | yellow | terminal value is 81% of enterprise value (> 80%) — valuation is fragile |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E | 0.60 | 10.00 |
| EV/Sales | 1.31 | 1.20 |
