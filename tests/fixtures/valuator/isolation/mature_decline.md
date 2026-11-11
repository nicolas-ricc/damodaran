# DECL — DECL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 1.36
- **Current price:** 1.20
- **Margin of safety:** 1.13x (around fair value)
- **Story type:** mature-decline
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 52.7%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**mature-decline**

- historical revenue CAGR -5.3% over 3 years
- classified as mature-decline
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1 → yr 10) | -5.3% → 4.0% | historical_average |
| Operating margin | 12.0% | historical_average |
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
| 1 | 966.21M | 115.57M | 91.30M | -26.89M | 118.19M | 108.65M |
| 2 | 925.17M | 110.66M | 87.42M | -20.52M | 107.94M | 91.21M |
| 3 | 895.34M | 107.09M | 84.60M | -14.91M | 99.51M | 77.30M |
| 4 | 875.66M | 104.74M | 82.74M | -9.84M | 92.58M | 66.11M |
| 5 | 865.38M | 103.51M | 81.77M | -5.14M | 86.91M | 57.04M |
| 6 | 864.08M | 103.35M | 81.65M | -645.52K | 82.29M | 49.65M |
| 7 | 871.65M | 104.26M | 82.36M | 3.78M | 78.58M | 43.58M |
| 8 | 888.21M | 106.24M | 83.93M | 8.28M | 75.65M | 38.56M |
| 9 | 914.20M | 109.35M | 86.38M | 12.99M | 73.39M | 34.39M |
| 10 | 950.31M | 113.66M | 89.79M | 18.06M | 71.74M | 30.90M |
| Terminal | — | — | — | — | 1.54B | — |

- **Enterprise value:** 1.26B
- **Equity value:** 1.36B
- **Net debt:** -100.00M

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 1.56 | 1.21 | 0.35 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 1.25 | 1.48 | 0.23 |
| terminal_growth | -1.0pp / +1.0pp | 1.28 | 1.49 | 0.22 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 1.30 | 1.43 | 0.13 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 1.40 | 1.32 | 0.08 |
| sales_to_capital | ×0.8 / ×1.2 | 1.33 | 1.38 | 0.05 |
| tax_rate | -1.0pp / +1.0pp | 1.38 | 1.35 | 0.03 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 1.19x | 1.25x | 1.30x | 1.36x | 1.42x |
| -0.5pp | 1.11x | 1.16x | 1.21x | 1.26x | 1.32x |
| +0.0pp | 1.04x | 1.09x | 1.13x | 1.18x | 1.23x |
| +0.5pp | 0.98x | 1.02x | 1.07x | 1.11x | 1.16x |
| +1.0pp | 0.93x | 0.97x | 1.01x | 1.05x | 1.10x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| growth_reinvestment | green | Every year the reinvestment growth needs fits within after-tax operating profit (NOPAT). |
| beta_business_risk | unknown | not evaluated: the sector beta, the operating leverage or the company's debt share is missing. |
| terminal_value_share | green | 53% of enterprise value comes from the terminal value, within the 80% ceiling. |
| country_exposure | unknown | not evaluated: it needs revenue by geography and a revenue-weighted equity risk premium (ERP), and no data source supplies either. |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 16.02 | 10.00 |
| P/E market | 14.12 | 10.00 |
| EV/Sales | 1.24 | 1.20 |
