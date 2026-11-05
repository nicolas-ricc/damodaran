# DECL — DECL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 1.37
- **Current price:** 1.20
- **Margin of safety:** 1.14x (around fair value)
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
| Operating margin | 12.0% | sector_default_damodaran |
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
| 1 | 966.21M | 115.95M | 91.60M | -26.89M | 118.49M | 108.92M |
| 2 | 925.17M | 111.02M | 87.71M | -20.52M | 108.23M | 91.45M |
| 3 | 895.34M | 107.44M | 84.88M | -14.91M | 99.79M | 77.51M |
| 4 | 875.66M | 105.08M | 83.01M | -9.84M | 92.86M | 66.30M |
| 5 | 865.38M | 103.85M | 82.04M | -5.14M | 87.18M | 57.22M |
| 6 | 864.08M | 103.69M | 81.92M | -645.52K | 82.56M | 49.81M |
| 7 | 871.65M | 104.60M | 82.63M | 3.78M | 78.85M | 43.73M |
| 8 | 888.21M | 106.59M | 84.20M | 8.28M | 75.92M | 38.71M |
| 9 | 914.20M | 109.70M | 86.67M | 12.99M | 73.67M | 34.53M |
| 10 | 950.31M | 114.04M | 90.09M | 18.06M | 72.03M | 31.03M |
| Terminal | — | — | — | — | 1.55B | — |

- **Enterprise value:** 1.27B
- **Equity value:** 1.37B
- **Net debt:** -100.00M

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 1.57 | 1.22 | 0.35 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 1.25 | 1.48 | 0.23 |
| terminal_growth | -1.0pp / +1.0pp | 1.28 | 1.50 | 0.22 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 1.30 | 1.43 | 0.13 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 1.41 | 1.33 | 0.08 |
| sales_to_capital | ×0.8 / ×1.2 | 1.34 | 1.39 | 0.05 |
| tax_rate | -1.0pp / +1.0pp | 1.38 | 1.35 | 0.03 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 1.19x | 1.25x | 1.31x | 1.36x | 1.42x |
| -0.5pp | 1.11x | 1.16x | 1.22x | 1.27x | 1.32x |
| +0.0pp | 1.04x | 1.09x | 1.14x | 1.19x | 1.23x |
| +0.5pp | 0.98x | 1.03x | 1.07x | 1.12x | 1.16x |
| +1.0pp | 0.93x | 0.97x | 1.01x | 1.06x | 1.10x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'mature-decline' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | green | terminal value is 53% of enterprise value (<= 80%) |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 16.07 | 10.00 |
| P/E market | 14.12 | 10.00 |
| EV/Sales | 1.24 | 1.20 |
