# AAPL — Apple Inc

_Generated 2026-01-01 · currency USD · country United States_

## 1. Executive summary

- **Intrinsic value (per share):** 136.68
- **Current price:** 150.00
- **Margin of safety:** 0.91x (potentially overvalued)
- **Story type:** mature-stable
- **WACC (computed from the components in §3):** 8.2% (equity 85.0% / debt 15.0%)
- **Terminal value share of EV:** 81.6%

> A single intrinsic value is a point in a cloud — read the sensitivity section
> below before drawing any conclusion (spec §7.4).

## 2. Story type + auto-assignment reasons

**mature-stable**

- historical revenue CAGR 4.2% over 3 years
- classified as mature-stable
## 3. Assumptions

| Assumption | Value | Source |
|---|---|---|
| Revenue growth (yr 1) | 8.0% | manual |
| Operating margin | 30.0% → 26.0% | manual |
| Sales-to-capital | 2.50 | sector_default_damodaran |
| Cost of equity | 9.0% | sector_default_damodaran |
| Pre-tax cost of debt | 4.5% | sector_default_damodaran |
| Equity weight | 85.0% | manual |
| Debt weight | 15.0% | manual |
| Terminal growth | 4.0% | rule_based |
| Tax rate | 23.0% | manual |
| Probability of bankruptcy | 0.0% | rule_based |

## 4. DCF detail

| Year | Revenue | EBIT | NOPAT | Reinvestment | FCFF | PV |
|---|---|---|---|---|---|---|
| 1 | 464.40B | 139.32B | 107.28B | 13.76B | 93.52B | 86.45B |
| 2 | 496.91B | 144.10B | 110.96B | 13.00B | 97.96B | 83.72B |
| 3 | 526.72B | 147.48B | 113.56B | 11.93B | 101.64B | 80.30B |
| 4 | 553.06B | 149.33B | 114.98B | 10.53B | 104.45B | 76.29B |
| 5 | 575.18B | 149.55B | 115.15B | 8.85B | 106.30B | 71.78B |
| Terminal | — | — | — | — | 2,621.29B | — |

- **Enterprise value:** 2,168.60B
- **Equity value:** 2,118.60B
- **Net debt:** 50.00B

## 5. Sensitivity

### Tornado (±20% per assumption, ranked by impact)

| Assumption | Intrinsic @ -20% | Intrinsic @ +20% | Impact |
|---|---|---|---|
| cost_of_equity | 215.96 | 99.59 | 116.37 |
| operating_margin (yr 1) | 106.22 | 167.15 | 60.93 |
| terminal_growth | 119.47 | 161.83 | 42.37 |
| tax_rate | 144.70 | 128.55 | 16.15 |
| revenue_growth (yr 1) | 130.01 | 143.64 | 13.63 |
| pretax_cost_of_debt | 140.20 | 133.33 | 6.87 |
| sales_to_capital | 133.58 | 138.75 | 5.17 |
### 2-D grid — cost_of_equity (rows) × operating_margin (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / operating_margin → | -20% | -10% | +0% | +10% | +20% |
|---|---|---|---|---|---|
| -20% | 1.12x | 1.28x | 1.44x | 1.60x | 1.76x |
| -10% | 0.87x | 0.99x | 1.12x | 1.24x | 1.36x |
| +0% | 0.71x | 0.81x | 0.91x | 1.01x | 1.11x |
| +10% | 0.60x | 0.68x | 0.77x | 0.85x | 0.94x |
| +20% | 0.51x | 0.59x | 0.66x | 0.74x | 0.81x |
## 6. Narrative flags

| Flag | Colour | Reason |
|---|---|---|
| story_margin | green | story type 'mature-stable' is not 'high-growth' |
| growth_reinvestment | green | projected reinvestment is comfortably funded by NOPAT every year |
| beta_business_risk | unknown | not evaluated: sector beta, operating leverage or company leverage unavailable |
| terminal_value_share | yellow | terminal value is 82% of enterprise value (> 80%) — valuation is fragile |
| country_exposure | unknown | not evaluated: needs revenue by geography and a revenue-weighted ERP; no ingest path supplies either |
## 7. Manual overrides

isolation golden override

Overridden assumptions are marked `manual` in the assumptions table above.
## 8. Sanity check vs sector multiples

| Multiple | Implied | Sector (Damodaran) |
|---|---|---|
| P/E implied (DCF) | 21.19 | 22.00 |
| P/E market | 23.25 | 22.00 |
| EV/Sales | 5.04 | 5.00 |
