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
| 1 | 1.01B | 121.60M | 96.07M | 1.68M | 94.39M | 86.77M |
| 2 | 1.02B | 122.01M | 96.39M | 1.68M | 94.70M | 80.02M |
| 3 | 1.02B | 122.41M | 96.71M | 1.69M | 95.02M | 73.80M |
| 4 | 1.02B | 122.82M | 97.03M | 1.69M | 95.33M | 68.07M |
| 5 | 1.03B | 123.23M | 97.35M | 1.70M | 95.65M | 62.78M |
| Terminal | — | — | — | — | 1.67B | — |

- **Enterprise value:** 1.47B
- **Equity value:** 1.04B
- **Net debt:** 920.00M

## 5. Sensitivity

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 1.25 | 0.89 | 0.36 |
| terminal_growth | -1.0pp / +1.0pp | 0.93 | 1.21 | 0.29 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 0.92 | 1.16 | 0.23 |
| sales_to_capital | ×0.8 / ×1.2 | 0.98 | 1.08 | 0.09 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 1.08 | 1.00 | 0.08 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 1.00 | 1.08 | 0.07 |
| tax_rate | -1.0pp / +1.0pp | 1.05 | 1.03 | 0.03 |
### 2-D grid — cost_of_equity (rows) × terminal_growth (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / terminal_growth → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 0.72x | 0.77x | 0.83x | 0.91x | 1.02x |
| -0.5pp | 0.67x | 0.71x | 0.76x | 0.82x | 0.90x |
| +0.0pp | 0.62x | 0.65x | 0.69x | 0.74x | 0.81x |
| +0.5pp | 0.58x | 0.60x | 0.64x | 0.68x | 0.73x |
| +1.0pp | 0.54x | 0.56x | 0.59x | 0.63x | 0.67x |
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
| P/E implied (DCF) | — | 10.00 |
| P/E market | — | 10.00 |
| EV/Sales | 1.46 | 1.20 |
