# CYCL — CYCL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 14.27
- **Current price:** 0.90
- **Margin of safety:** 15.86x (potentially undervalued)
- **Story type:** cyclical
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 64.4%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**cyclical**

- historical revenue CAGR 4.7% over 4 years
- classified as cyclical
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1 → yr 10) | 4.7% → 4.0% | historical_average |
| Operating margin | 10.0% | historical_average |
| Sales-to-capital | 2.00 | sector_default_damodaran |
| Cost of equity | 10.0% | sector_default_damodaran |
| Pre-tax cost of debt | 6.0% | sector_default_damodaran |
| Equity weight | 76.9% | sector_default_damodaran |
| Debt weight | 23.1% | sector_default_damodaran |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 21.0% | country_default_damodaran |
| Probability of bankruptcy | 0.0% | rule_based |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 1.26B | 125.51M | 99.15M | 27.98M | 71.17M | 65.42M |
| 2 | 1.31B | 131.26M | 103.70M | 28.79M | 74.91M | 63.30M |
| 3 | 1.37B | 137.18M | 108.37M | 29.59M | 78.78M | 61.19M |
| 4 | 1.43B | 143.25M | 113.17M | 30.38M | 82.79M | 59.11M |
| 5 | 1.50B | 149.47M | 118.08M | 31.15M | 86.93M | 57.06M |
| 6 | 1.56B | 155.85M | 123.12M | 31.91M | 91.21M | 55.03M |
| 7 | 1.62B | 162.38M | 128.28M | 32.66M | 95.62M | 53.03M |
| 8 | 1.69B | 169.05M | 133.55M | 33.38M | 100.17M | 51.07M |
| 9 | 1.76B | 175.86M | 138.93M | 34.08M | 104.85M | 49.14M |
| 10 | 1.83B | 182.81M | 144.42M | 34.76M | 109.66M | 47.24M |
| Terminal | — | — | — | — | 2.36B | — |

- **Enterprise value:** 1.58B
- **Equity value:** 1.43B
- **Net debt:** 150.00M

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 17.29 | 12.08 | 5.21 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 12.17 | 16.37 | 4.20 |
| terminal_growth | -1.0pp / +1.0pp | 13.10 | 16.05 | 2.95 |
| sales_to_capital | ×0.8 / ×1.2 | 12.96 | 15.14 | 2.18 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 13.49 | 15.11 | 1.62 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 14.90 | 13.69 | 1.21 |
| tax_rate | -1.0pp / +1.0pp | 14.49 | 14.05 | 0.44 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 16.44x | 17.82x | 19.21x | 20.60x | 21.99x |
| -0.5pp | 14.85x | 16.12x | 17.39x | 18.66x | 19.93x |
| +0.0pp | 13.52x | 14.69x | 15.86x | 17.02x | 18.19x |
| +0.5pp | 12.39x | 13.47x | 14.55x | 15.63x | 16.71x |
| +1.0pp | 11.41x | 12.42x | 13.42x | 14.43x | 15.43x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| growth_reinvestment | green | Every year the reinvestment growth needs fits within after-tax operating profit (NOPAT). |
| beta_business_risk | unknown | not evaluated: the sector beta, the operating leverage or the company's debt share is missing. |
| terminal_value_share | green | 64% of enterprise value comes from the terminal value, within the 80% ceiling. |
| country_exposure | unknown | not evaluated: it needs revenue by geography and a revenue-weighted equity risk premium (ERP), and no data source supplies either. |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 9.51 | 10.00 |
| P/E market | 0.60 | 10.00 |
| EV/Sales | 1.31 | 1.20 |
