# DIST — DIST

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 1.04
- **Current price:** 1.50
- **Margin of safety:** 0.70x (potentially overvalued)
- **Story type:** distressed
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 59.4%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**distressed**

- historical revenue CAGR 0.3% over 3 years
- classified as distressed
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1 → yr 10) | 0.3% → 4.0% | historical_average |
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
| 1 | 1.01B | 121.60M | 96.07M | 1.68M | 94.39M | 86.77M |
| 2 | 1.02B | 122.50M | 96.77M | 3.72M | 93.05M | 78.63M |
| 3 | 1.03B | 123.89M | 97.87M | 5.80M | 92.07M | 71.52M |
| 4 | 1.05B | 125.79M | 99.38M | 7.94M | 91.44M | 65.29M |
| 5 | 1.07B | 128.23M | 101.30M | 10.17M | 91.14M | 59.82M |
| 6 | 1.09B | 131.24M | 103.68M | 12.51M | 91.16M | 55.00M |
| 7 | 1.12B | 134.84M | 106.52M | 15.01M | 91.52M | 50.76M |
| 8 | 1.16B | 139.08M | 109.87M | 17.68M | 92.20M | 47.00M |
| 9 | 1.20B | 144.01M | 113.77M | 20.56M | 93.21M | 43.68M |
| 10 | 1.25B | 149.70M | 118.27M | 23.70M | 94.56M | 40.74M |
| Terminal | — | — | — | — | 2.03B | — |

- **Enterprise value:** 1.47B
- **Equity value:** 1.04B
- **Net debt:** 920.00M

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 1.25 | 0.89 | 0.36 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 0.93 | 1.16 | 0.23 |
| terminal_growth | -1.0pp / +1.0pp | 0.95 | 1.18 | 0.23 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 0.98 | 1.11 | 0.13 |
| sales_to_capital | ×0.8 / ×1.2 | 0.99 | 1.08 | 0.10 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 1.09 | 1.00 | 0.08 |
| tax_rate | -1.0pp / +1.0pp | 1.06 | 1.03 | 0.03 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 0.74x | 0.79x | 0.84x | 0.88x | 0.93x |
| -0.5pp | 0.68x | 0.72x | 0.76x | 0.80x | 0.84x |
| +0.0pp | 0.62x | 0.66x | 0.70x | 0.74x | 0.77x |
| +0.5pp | 0.57x | 0.60x | 0.64x | 0.68x | 0.71x |
| +1.0pp | 0.53x | 0.56x | 0.59x | 0.63x | 0.66x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'distressed' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | green | terminal value is 59% of enterprise value (<= 80%) |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | — | 10.00 |
| P/E market | — | 10.00 |
| EV/Sales | 1.46 | 1.20 |
