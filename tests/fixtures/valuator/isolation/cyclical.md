# CYCL — CYCL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 14.28
- **Current price:** 0.90
- **Margin of safety:** 15.86x (potentially undervalued)
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

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 17.30 | 12.09 | 5.21 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 12.18 | 16.38 | 4.20 |
| terminal_growth | -1.0pp / +1.0pp | 12.81 | 16.52 | 3.71 |
| sales_to_capital | ×0.8 / ×1.2 | 12.97 | 15.15 | 2.18 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 14.90 | 13.70 | 1.21 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 13.84 | 14.74 | 0.90 |
| tax_rate | -1.0pp / +1.0pp | 14.50 | 14.06 | 0.44 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 16.44x | 17.83x | 19.22x | 20.61x | 22.00x |
| -0.5pp | 14.86x | 16.13x | 17.40x | 18.67x | 19.94x |
| +0.0pp | 13.53x | 14.70x | 15.86x | 17.03x | 18.20x |
| +0.5pp | 12.39x | 13.48x | 14.56x | 15.64x | 16.72x |
| +1.0pp | 11.42x | 12.42x | 13.43x | 14.44x | 15.44x |
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
| P/E implied (DCF) | 9.52 | 10.00 |
| P/E market | 0.60 | 10.00 |
| EV/Sales | 1.31 | 1.20 |
