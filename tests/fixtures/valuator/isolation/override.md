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
| Revenue growth (yr 1 → yr 5) | 8.0% → 4.0% | manual |
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

### Tornado (ranked by impact)

Rate assumptions move ±1 percentage point (every year of a path); `sales_to_capital` moves ×0.8 / ×1.2.

| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |
|---|---|---|---|---|
| cost_of_equity | -1.0pp / +1.0pp | 171.84 | 113.31 | 58.53 |
| terminal_growth | -1.0pp / +1.0pp | 115.77 | 170.60 | 54.83 |
| operating_margin (yr 1) | -1.0pp / +1.0pp | 130.91 | 142.46 | 11.56 |
| revenue_growth (yr 1) | -1.0pp / +1.0pp | 131.17 | 142.40 | 11.23 |
| pretax_cost_of_debt | -1.0pp / +1.0pp | 140.61 | 132.97 | 7.64 |
| sales_to_capital | ×0.8 / ×1.2 | 133.58 | 138.75 | 5.17 |
| tax_rate | -1.0pp / +1.0pp | 138.44 | 134.93 | 3.51 |
### 2-D grid — cost_of_equity (rows) × terminal_growth (cols), margin of safety (intrinsic ÷ price)| cost_of_equity ↓ / terminal_growth → | -1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp |
|---|---|---|---|---|---|
| -1.0pp | 0.93x | 1.02x | 1.15x | 1.31x | 1.55x |
| -0.5pp | 0.84x | 0.92x | 1.02x | 1.14x | 1.31x |
| +0.0pp | 0.77x | 0.83x | 0.91x | 1.01x | 1.14x |
| +0.5pp | 0.71x | 0.76x | 0.83x | 0.90x | 1.00x |
| +1.0pp | 0.66x | 0.70x | 0.76x | 0.82x | 0.90x |
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
