# DECL — DECL

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 1.35
- **Current price:** 1.20
- **Margin of safety:** 1.13x (around fair value)
- **Story type:** mature-decline
- **WACC (computed from the components in §3):** 8.8% (equity 76.9% / debt 23.1%)
- **Terminal value share of EV:** 66.4%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**mature-decline**

- historical revenue CAGR -5.3% over 3 years
- classified as mature-decline
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | -5.3% | historical_average |
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
| 1 | 966.22M | 115.95M | 91.60M | -26.89M | 118.49M | 108.92M |
| 2 | 915.27M | 109.83M | 86.77M | -25.47M | 112.24M | 94.84M |
| 3 | 867.01M | 104.04M | 82.19M | -24.13M | 106.32M | 82.59M |
| 4 | 821.29M | 98.55M | 77.86M | -22.86M | 100.72M | 71.91M |
| 5 | 777.99M | 93.36M | 73.75M | -21.65M | 95.41M | 62.62M |
| Terminal | — | — | — | — | 1.27B | — |

- **Enterprise value:** 1.25B
- **Equity value:** 1.35B
- **Net debt:** -100.00M

## 5. Sensitivity

### Tornado (±20% per assumption, ranked by impact)

| Assumption | Intrinsic @ -20% | Intrinsic @ +20% | Impact |
|---|---|---|---|
| cost_of_equity | 1.85 | 1.09 | 0.75 |
| operating_margin (yr 1) | 1.08 | 1.63 | 0.55 |
| terminal_growth | 1.27 | 1.47 | 0.21 |
| tax_rate | 1.41 | 1.29 | 0.12 |
| pretax_cost_of_debt | 1.40 | 1.31 | 0.10 |
| revenue_growth (yr 1) | 1.39 | 1.31 | 0.08 |
| sales_to_capital | 1.32 | 1.37 | 0.05 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -20% | -10% | +0% | +10% | +20% |
|---|---|---|---|---|---|
| -20% | 1.21x | 1.38x | 1.54x | 1.70x | 1.87x |
| -10% | 1.03x | 1.16x | 1.30x | 1.43x | 1.56x |
| +0% | 0.90x | 1.01x | 1.13x | 1.24x | 1.36x |
| +10% | 0.81x | 0.91x | 1.00x | 1.10x | 1.20x |
| +20% | 0.74x | 0.82x | 0.91x | 1.00x | 1.09x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'mature-decline' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | green | terminal value is 66% of enterprise value (<= 80%) |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

No manual overrides applied — all assumptions are sector defaults, rules, or
historical averages.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E | 15.92 | 10.00 |
| EV/Sales | 1.23 | 1.20 |
